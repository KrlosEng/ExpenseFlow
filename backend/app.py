import calendar
import csv
import io
import os
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

try:
    from auth import current_user
    from auth import router as auth_router
    from database import EXPENSE_CATEGORIES, INCOME_CATEGORIES, IS_POSTGRES, get_db, init_db
except ImportError:  # al ejecutar como "uvicorn backend.app:app" desde la raíz
    from backend.auth import current_user
    from backend.auth import router as auth_router
    from backend.database import EXPENSE_CATEGORIES, INCOME_CATEGORIES, IS_POSTGRES, get_db, init_db


@asynccontextmanager
async def lifespan(_app):
    init_db()
    yield


app = FastAPI(title="ExpenseFlow FinTech API", version="3.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # Orígenes permitidos: variable ALLOWED_ORIGINS separada por comas (p. ej. el dominio de Vercel)
    allow_origins=[o.strip() for o in os.environ.get(
        "ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5500,http://127.0.0.1:5500"
    ).split(",") if o.strip()],
    allow_credentials=True,  # necesario para la cookie de sesión si el frontend se sirve desde otro origen permitido
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


app.include_router(auth_router)

# --- MODELOS PYDANTIC ---
MAX_AMOUNT = 1_000_000_000
MAX_IMPORT = 1000


class TransactionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    amount: float = Field(gt=0, le=MAX_AMOUNT)
    type: Literal["expense", "income"]
    category: str = Field(min_length=1, max_length=60)
    date: date
    payment_method: str | None = Field(default="Tarjeta", max_length=40)
    notes: str | None = Field(default="", max_length=500)

    @field_validator("title", "category")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("no puede estar vacío")
        return v


class SubscriptionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    cost: float = Field(gt=0, le=MAX_AMOUNT)
    billing_cycle: Literal["monthly", "yearly"]
    category: str = Field(min_length=1, max_length=60)
    next_billing_date: date
    icon: str | None = Field(default="credit-card", max_length=40)


class BudgetUpdate(BaseModel):
    category: str = Field(min_length=1, max_length=60)
    monthly_limit: float = Field(gt=0, le=MAX_AMOUNT)


class SavingsGoalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    target_amount: float = Field(gt=0, le=MAX_AMOUNT)
    current_amount: float | None = Field(default=0.0, ge=0, le=MAX_AMOUNT)
    target_date: date
    category: str | None = Field(default="General", max_length=60)
    icon: str | None = Field(default="piggy-bank", max_length=40)


class SavingsGoalUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    target_amount: float = Field(gt=0, le=MAX_AMOUNT)
    target_date: date
    category: str | None = Field(default="General", max_length=60)


class CsvImport(BaseModel):
    csv: str = Field(min_length=1, max_length=2_000_000)


class SavingsGoalDeposit(BaseModel):
    amount: float = Field(gt=0, le=MAX_AMOUNT)


class BulkImportJSON(BaseModel):
    transactions: list[TransactionCreate] = Field(default_factory=list, max_length=MAX_IMPORT)


User = Depends(current_user)

TX_INSERT = ("INSERT INTO transactions (user_id, title, amount, type, category, date, payment_method, notes) "
             "VALUES (?, ?, ?, ?, ?, ?, ?, ?)")


def tx_params(uid, tx: TransactionCreate):
    return (uid, tx.title, tx.amount, tx.type, tx.category, tx.date.isoformat(), tx.payment_method, tx.notes)


def resolve_month(month: str | None) -> str:
    """Devuelve 'YYYY-MM'; por defecto el mes actual."""
    if not month:
        return datetime.now().strftime("%Y-%m")
    # strptime acepta "2026-1", pero las fechas se guardan como "2026-01-05": se exige el formato exacto
    try:
        if len(month) != 7 or month[4] != "-":
            raise ValueError
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        raise HTTPException(status_code=422, detail="month debe tener formato YYYY-MM")
    return month


def add_cycle(d: date, cycle: str) -> date:
    """Suma un mes o un año; si el día no existe (31 de febrero) usa el último día del mes."""
    months = 1 if cycle == "monthly" else 12
    month_index = d.month - 1 + months
    year, month = d.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


MAX_CATCH_UP = 24  # cobros pendientes que se generan como máximo por suscripción


def process_due_subscriptions(db, uid: int) -> int:
    """Registra como gasto cada cobro de suscripción activa ya vencido y avanza su próxima fecha.

    Se llama al leer el resumen, los movimientos, los presupuestos o las suscripciones, así no
    hace falta un proceso programado (en Vercel no lo hay). Devuelve cuántos cobros generó.
    """
    today = date.today()
    created = 0
    subs = db.fetchall(
        "SELECT id, name, cost, billing_cycle, category, next_billing_date FROM subscriptions "
        "WHERE user_id = ? AND is_active = 1 AND next_billing_date <= ?", (uid, today.isoformat()))
    for sub in subs:
        due = date.fromisoformat(sub["next_billing_date"])
        steps = 0
        while due <= today and steps < MAX_CATCH_UP:
            db.execute(TX_INSERT, (uid, sub["name"], sub["cost"], "expense", sub["category"], due.isoformat(),
                                   "Cobro automático", "Cargo mensual" if sub["billing_cycle"] == "monthly" else "Cargo anual"))
            due = add_cycle(due, sub["billing_cycle"])
            steps += 1
            created += 1
        if due <= today:  # demasiados cobros atrasados: se salta al siguiente futuro
            while due <= today:
                due = add_cycle(due, sub["billing_cycle"])
        db.execute("UPDATE subscriptions SET next_billing_date = ? WHERE id = ? AND user_id = ?",
                   (due.isoformat(), sub["id"], uid))
    return created


def update_owned(db, table: str, item_id: int, uid: int, fields: dict, not_found: str):
    cols = ", ".join(f"{k} = ?" for k in fields)
    cur = db.execute(f"UPDATE {table} SET {cols} WHERE id = ? AND user_id = ?", (*fields.values(), item_id, uid))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail=not_found)


def delete_owned(table: str, item_id: int, uid: int, not_found: str):
    with get_db() as db:
        cur = db.execute(f"DELETE FROM {table} WHERE id = ? AND user_id = ?", (item_id, uid))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail=not_found)


# --- ENDPOINTS PÚBLICOS ---
@app.get("/api/health")
def health_check():
    return {
        "status": "online",
        "system": "ExpenseFlow FinTech Engine v3.0",
        "database": "postgresql" if IS_POSTGRES else "sqlite",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/categories")
def get_categories():
    return {"expense": EXPENSE_CATEGORIES, "income": INCOME_CATEGORIES}


# --- RESUMEN ---
@app.get("/api/summary")
def get_summary(month: str | None = None, user: dict = User):
    month = resolve_month(month)
    uid = user["id"]
    with get_db() as db:
        process_due_subscriptions(db, uid)
        rows = db.fetchall(
            "SELECT type, SUM(amount) AS total FROM transactions "
            "WHERE user_id = ? AND substr(date, 1, 7) = ? GROUP BY type", (uid, month))
        type_totals = {r["type"]: r["total"] or 0.0 for r in rows}
        total_income = type_totals.get("income", 0.0)
        total_expense = type_totals.get("expense", 0.0)
        net_balance = total_income - total_expense

        subs = db.fetchall("SELECT cost, billing_cycle FROM subscriptions WHERE user_id = ? AND is_active = 1", (uid,))
        monthly_subs_cost = sum(s["cost"] if s["billing_cycle"] == "monthly" else s["cost"] / 12.0 for s in subs)

        expenses_by_category = [
            {"category": r["category"], "total": round(r["category_total"], 2)}
            for r in db.fetchall(
                "SELECT category, SUM(amount) AS category_total FROM transactions "
                "WHERE user_id = ? AND type = 'expense' AND substr(date, 1, 7) = ? "
                "GROUP BY category ORDER BY category_total DESC", (uid, month))
        ]

        daily_trends = [
            {"date": r["date"], "total": round(r["day_total"], 2)}
            for r in db.fetchall(
                "SELECT date, SUM(amount) AS day_total FROM transactions "
                "WHERE user_id = ? AND type = 'expense' AND substr(date, 1, 7) = ? "
                "GROUP BY date ORDER BY date ASC", (uid, month))
        ]

        saved = db.fetchone("SELECT SUM(current_amount) AS total_saved FROM savings_goals WHERE user_id = ?", (uid,))
        total_saved = (saved or {}).get("total_saved") or 0.0

    # ALGORITMO DE FINANCIAL HEALTH SCORE (0-100 pts)
    score = 70.0
    tips = []
    if total_income > 0:
        savings_rate = (net_balance / total_income) * 100
        if savings_rate >= 20:
            score += 15
            tips.append("Gran tasa de ahorro (>20% de tus ingresos).")
        elif savings_rate >= 10:
            score += 8
            tips.append("Tasa de ahorro saludable (10-20%).")
        else:
            score -= 10
            tips.append("Intenta destinar al menos el 15% de tus ingresos al ahorro.")
    else:
        tips.append("Registra tus ingresos para un análisis completo de salud financiera.")

    if total_expense > 0:
        subs_ratio = (monthly_subs_cost / total_expense) * 100
        if subs_ratio > 30:
            score -= 12
            tips.append(f"Tus suscripciones representan el {round(subs_ratio, 1)}% de tus gastos. Revisa servicios en desuso.")
        elif subs_ratio < 15:
            score += 10
            tips.append("Control excelente sobre costos fijos y suscripciones.")

    if net_balance < 0:
        score -= 25
        tips.append("Atención: Tus gastos superan a tus ingresos en este periodo.")

    return {
        "month": month,
        "net_balance": round(net_balance, 2),
        "total_income": round(total_income, 2),
        "total_expense": round(total_expense, 2),
        "monthly_subs_cost": round(monthly_subs_cost, 2),
        "total_saved": round(total_saved, 2),
        "health_score": int(max(0, min(100, score))),
        "health_tips": tips,
        "expenses_by_category": expenses_by_category,
        "daily_trends": daily_trends,
    }


# --- TRANSACTIONS API ---
@app.get("/api/transactions")
def get_transactions(
    type: str | None = None,
    category: str | None = None,
    search: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    user: dict = User,
):
    where = " WHERE user_id = ?"
    params = [user["id"]]
    if type:
        where += " AND type = ?"
        params.append(type)
    if category:
        where += " AND category = ?"
        params.append(category)
    if search:
        # LOWER() para que la búsqueda no distinga mayúsculas también en PostgreSQL
        where += " AND (LOWER(title) LIKE ? OR LOWER(COALESCE(notes, '')) LIKE ?)"
        params += [f"%{search.lower()}%"] * 2
    if start_date:
        where += " AND date >= ?"
        params.append(start_date)
    if end_date:
        where += " AND date <= ?"
        params.append(end_date)
    with get_db() as db:
        process_due_subscriptions(db, user["id"])
        totals = db.fetchone(
            "SELECT COUNT(*) AS total, "
            "COALESCE(SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END), 0) AS income_total, "
            "COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0) AS expense_total "
            "FROM transactions" + where, params)
        items = db.fetchall(
            "SELECT * FROM transactions" + where + " ORDER BY date DESC, id DESC LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size])
    return {
        "items": items,
        "total": totals["total"],
        "page": page,
        "page_size": page_size,
        "income_total": round(totals["income_total"], 2),
        "expense_total": round(totals["expense_total"], 2),
    }


@app.post("/api/transactions", status_code=201)
def create_transaction(tx: TransactionCreate, user: dict = User):
    with get_db() as db:
        tx_id = db.insert(TX_INSERT, tx_params(user["id"], tx))
    return {"id": tx_id, "message": "Transacción registrada exitosamente"}


@app.put("/api/transactions/{tx_id}")
def update_transaction(tx_id: int, tx: TransactionCreate, user: dict = User):
    with get_db() as db:
        update_owned(db, "transactions", tx_id, user["id"], {
            "title": tx.title, "amount": tx.amount, "type": tx.type, "category": tx.category,
            "date": tx.date.isoformat(), "payment_method": tx.payment_method, "notes": tx.notes,
        }, "Transacción no encontrada")
    return {"id": tx_id, "message": "Transacción actualizada"}


@app.delete("/api/transactions/{tx_id}")
def delete_transaction(tx_id: int, user: dict = User):
    delete_owned("transactions", tx_id, user["id"], "Transacción no encontrada")
    return {"message": f"Transacción #{tx_id} eliminada"}


# --- SAVINGS GOALS API ---
@app.get("/api/savings_goals")
def get_savings_goals(user: dict = User):
    with get_db() as db:
        goals = db.fetchall("SELECT * FROM savings_goals WHERE user_id = ? ORDER BY target_date ASC", (user["id"],))
    for g in goals:
        g["percentage"] = min(round((g["current_amount"] / g["target_amount"]) * 100, 1), 100.0) if g["target_amount"] > 0 else 0
    return goals


@app.post("/api/savings_goals", status_code=201)
def create_savings_goal(goal: SavingsGoalCreate, user: dict = User):
    with get_db() as db:
        goal_id = db.insert(
            "INSERT INTO savings_goals (user_id, title, target_amount, current_amount, target_date, category, icon) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user["id"], goal.title, goal.target_amount, goal.current_amount,
             goal.target_date.isoformat(), goal.category, goal.icon),
        )
    return {"id": goal_id, "message": "Meta de ahorro creada"}


@app.put("/api/savings_goals/{goal_id}")
def update_savings_goal(goal_id: int, goal: SavingsGoalUpdate, user: dict = User):
    with get_db() as db:
        update_owned(db, "savings_goals", goal_id, user["id"], {
            "title": goal.title, "target_amount": goal.target_amount,
            "target_date": goal.target_date.isoformat(), "category": goal.category,
        }, "Meta no encontrada")
    return {"id": goal_id, "message": "Meta actualizada"}


@app.put("/api/savings_goals/{goal_id}/deposit")
def deposit_to_goal(goal_id: int, deposit: SavingsGoalDeposit, user: dict = User):
    uid = user["id"]
    with get_db() as db:
        row = db.fetchone(
            "SELECT current_amount, target_amount, title FROM savings_goals WHERE id = ? AND user_id = ?",
            (goal_id, uid))
        if not row:
            raise HTTPException(status_code=404, detail="Meta no encontrada")

        remaining = row["target_amount"] - row["current_amount"]
        if deposit.amount > remaining + 1e-9:
            raise HTTPException(status_code=422,
                                detail=f"El depósito supera lo que falta para la meta ({round(max(remaining, 0), 2)})")
        new_amount = row["current_amount"] + deposit.amount
        db.execute("UPDATE savings_goals SET current_amount = ? WHERE id = ? AND user_id = ?", (new_amount, goal_id, uid))

        # Registrar el movimiento de ahorro en el historial
        db.execute(
            TX_INSERT,
            (uid, f"Ahorro: {row['title']}", deposit.amount, "expense", "Ahorro e Inversión",
             datetime.now().strftime("%Y-%m-%d"), "Transferencia", f"Depósito a meta de ahorro #{goal_id}"),
        )
    return {"id": goal_id, "current_amount": round(new_amount, 2)}


@app.delete("/api/savings_goals/{goal_id}")
def delete_savings_goal(goal_id: int, user: dict = User):
    delete_owned("savings_goals", goal_id, user["id"], "Meta no encontrada")
    return {"message": "Meta eliminada"}


# --- SUBSCRIPTIONS API ---
@app.get("/api/subscriptions")
def get_subscriptions(user: dict = User):
    with get_db() as db:
        process_due_subscriptions(db, user["id"])
        return db.fetchall("SELECT * FROM subscriptions WHERE user_id = ? ORDER BY next_billing_date ASC", (user["id"],))


@app.post("/api/subscriptions", status_code=201)
def create_subscription(sub: SubscriptionCreate, user: dict = User):
    with get_db() as db:
        sub_id = db.insert(
            "INSERT INTO subscriptions (user_id, name, cost, billing_cycle, category, next_billing_date, icon) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user["id"], sub.name, sub.cost, sub.billing_cycle, sub.category,
             sub.next_billing_date.isoformat(), sub.icon),
        )
    return {"id": sub_id, "message": "Suscripción añadida exitosamente"}


@app.put("/api/subscriptions/{sub_id}")
def update_subscription(sub_id: int, sub: SubscriptionCreate, user: dict = User):
    with get_db() as db:
        update_owned(db, "subscriptions", sub_id, user["id"], {
            "name": sub.name, "cost": sub.cost, "billing_cycle": sub.billing_cycle,
            "category": sub.category, "next_billing_date": sub.next_billing_date.isoformat(),
        }, "Suscripción no encontrada")
    return {"id": sub_id, "message": "Suscripción actualizada"}


@app.put("/api/subscriptions/{sub_id}/toggle")
def toggle_subscription(sub_id: int, user: dict = User):
    with get_db() as db:
        row = db.fetchone("SELECT is_active FROM subscriptions WHERE id = ? AND user_id = ?", (sub_id, user["id"]))
        if not row:
            raise HTTPException(status_code=404, detail="Suscripción no encontrada")
        new_state = 0 if row["is_active"] == 1 else 1
        db.execute("UPDATE subscriptions SET is_active = ? WHERE id = ? AND user_id = ?", (new_state, sub_id, user["id"]))
    return {"id": sub_id, "is_active": new_state}


@app.delete("/api/subscriptions/{sub_id}")
def delete_subscription(sub_id: int, user: dict = User):
    delete_owned("subscriptions", sub_id, user["id"], "Suscripción no encontrada")
    return {"message": "Suscripción eliminada"}


# --- BUDGETS API ---
@app.get("/api/budgets")
def get_budgets(month: str | None = None, user: dict = User):
    month = resolve_month(month)
    with get_db() as db:
        process_due_subscriptions(db, user["id"])
        # Una sola consulta: presupuesto + gasto del mes en esa categoría
        budgets = db.fetchall(
            """SELECT b.id, b.category, b.monthly_limit, b.period,
                      COALESCE(SUM(t.amount), 0) AS spent
               FROM budgets b
               LEFT JOIN transactions t
                 ON t.user_id = b.user_id AND t.category = b.category
                AND t.type = 'expense' AND substr(t.date, 1, 7) = ?
               WHERE b.user_id = ?
               GROUP BY b.id, b.category, b.monthly_limit, b.period
               ORDER BY b.id""",
            (month, user["id"]))
    for b in budgets:
        b["spent"] = round(b["spent"], 2)
        b["percentage"] = min(round((b["spent"] / b["monthly_limit"]) * 100, 1), 100.0) if b["monthly_limit"] > 0 else 0
    return budgets


@app.post("/api/budgets")
def set_budget(b: BudgetUpdate, user: dict = User):
    with get_db() as db:
        db.execute(
            "INSERT INTO budgets (user_id, category, monthly_limit) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, category) DO UPDATE SET monthly_limit = excluded.monthly_limit",
            (user["id"], b.category, b.monthly_limit))
    return {"message": "Presupuesto actualizado"}


# --- IMPORT JSON API ---
@app.post("/api/import/json")
def import_json(data: BulkImportJSON, user: dict = User):
    if not data.transactions:
        raise HTTPException(status_code=400, detail="No se enviaron transacciones para importar")
    with get_db() as db:
        for tx in data.transactions:
            db.execute(TX_INSERT, tx_params(user["id"], tx))
    count = len(data.transactions)
    return {"imported_count": count, "message": f"Se importaron {count} transacciones con éxito"}


# --- IMPORT CSV API ---
CSV_COLUMNS = {
    "title": ("título", "titulo", "title", "concepto"),
    "amount": ("monto", "amount", "valor"),
    "type": ("tipo", "type"),
    "category": ("categoría", "categoria", "category"),
    "date": ("fecha", "date"),
    "payment_method": ("método pago", "metodo pago", "método", "metodo", "payment_method"),
    "notes": ("notas", "nota", "notes"),
}
TYPE_WORDS = {"expense": "expense", "gasto": "expense", "income": "income", "ingreso": "income"}


def parse_amount(text: str) -> float:
    """Acepta 1234.5, 1.234,50 y 900.000 (formato colombiano), 1,234.50 y $ 1.234.

    Un solo punto seguido de exactamente tres dígitos se toma como separador de miles
    (900.000 = novecientos mil), que es como se escriben los montos en Colombia.
    """
    t = text.strip().replace("$", "").replace(" ", "").replace("\u00a0", "")
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    elif t.count(".") > 1 or (t.count(".") == 1 and len(t.split(".")[1]) == 3):
        t = t.replace(".", "")
    return float(t)


@app.post("/api/import/csv")
def import_csv(data: CsvImport, user: dict = User):
    """Importa el mismo CSV que genera la exportación (o uno con columnas equivalentes, separadas por , o ;)."""
    text = data.csv.lstrip("\ufeff")
    try:
        dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = {(h or "").strip().lower(): h for h in (reader.fieldnames or [])}
    mapping = {}
    for field, names in CSV_COLUMNS.items():
        for n in names:
            if n in headers:
                mapping[field] = headers[n]
                break
    missing = [f for f in ("title", "amount", "type", "category", "date") if f not in mapping]
    if missing:
        raise HTTPException(status_code=422, detail=f"Faltan columnas en el CSV: {', '.join(missing)}")

    txs, errors = [], []
    for line, row in enumerate(reader, start=2):
        if len(txs) + len(errors) >= MAX_IMPORT:
            raise HTTPException(status_code=422, detail=f"El CSV tiene más de {MAX_IMPORT} filas")
        try:
            raw = {f: (row.get(col) or "").strip() for f, col in mapping.items()}
            raw["title"] = raw["title"].lstrip("'")  # deshace la protección contra fórmulas de la exportación
            raw["type"] = TYPE_WORDS[raw["type"].lower()]
            raw["amount"] = parse_amount(raw["amount"])
            txs.append(TransactionCreate(**raw))
        except Exception:
            errors.append(line)
    if errors:
        shown = ", ".join(map(str, errors[:10])) + ("…" if len(errors) > 10 else "")
        raise HTTPException(status_code=422, detail=f"No se pudo leer {len(errors)} fila(s): {shown}. No se importó nada.")
    if not txs:
        raise HTTPException(status_code=400, detail="El CSV no tiene filas")
    with get_db() as db:
        for tx in txs:
            db.execute(TX_INSERT, tx_params(user["id"], tx))
    return {"imported_count": len(txs), "message": f"Se importaron {len(txs)} transacciones con éxito"}


# --- EXPORT API ---
def csv_safe(value):
    """Evita inyección de fórmulas en Excel/Sheets (celdas que empiezan con = + - @ tab o CR)."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", chr(9), chr(13)):
        return "'" + value
    return value


@app.get("/api/export/csv")
def export_csv(user: dict = User):
    with get_db() as db:
        rows = db.fetchall("SELECT * FROM transactions WHERE user_id = ? ORDER BY date DESC", (user["id"],))

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Título", "Monto", "Tipo", "Categoría", "Fecha", "Método Pago", "Notas"])
    for r in rows:
        writer.writerow([r["id"], csv_safe(r["title"]), r["amount"], r["type"], csv_safe(r["category"]),
                         r["date"], csv_safe(r["payment_method"]), csv_safe(r["notes"])])

    return Response(content=output.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=expenseflow_transactions.csv"})


# --- SERVIR FRONTEND ESTÁTICO ---
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(FRONTEND_DIR):
    css_dir = os.path.join(FRONTEND_DIR, "css")
    js_dir = os.path.join(FRONTEND_DIR, "js")
    if os.path.exists(css_dir):
        app.mount("/css", StaticFiles(directory=css_dir), name="css")
    if os.path.exists(js_dir):
        app.mount("/js", StaticFiles(directory=js_dir), name="js")

    @app.get("/")
    def read_root():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
