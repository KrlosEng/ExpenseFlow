import os
import sqlite3
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from typing import Optional, List
import json
import csv
import io

from database import get_db_connection, init_db

app = FastAPI(title="ExpenseFlow FinTech API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_db():
    init_db()

# --- MODELOS PYDANTIC ---
class TransactionCreate(BaseModel):
    title: str
    amount: float
    type: str # 'expense' or 'income'
    category: str
    date: str
    payment_method: Optional[str] = "Tarjeta"
    notes: Optional[str] = ""

class SubscriptionCreate(BaseModel):
    name: str
    cost: float
    billing_cycle: str # 'monthly' or 'yearly'
    category: str
    next_billing_date: str
    icon: Optional[str] = "credit-card"

class BudgetUpdate(BaseModel):
    category: str
    monthly_limit: float

class SavingsGoalCreate(BaseModel):
    title: str
    target_amount: float
    current_amount: Optional[float] = 0.0
    target_date: str
    category: Optional[str] = "General"
    icon: Optional[str] = "piggy-bank"

class SavingsGoalDeposit(BaseModel):
    amount: float

class BulkImportJSON(BaseModel):
    transactions: Optional[List[TransactionCreate]] = []

# --- ENDPOINTS REST API ---

@app.get("/api/health")
def health_check():
    return {"status": "online", "system": "ExpenseFlow FinTech Engine v2.0", "timestamp": datetime.now().isoformat()}

@app.get("/api/summary")
def get_summary():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Ingresos vs Gastos
    cursor.execute("SELECT type, SUM(amount) as total FROM transactions GROUP BY type")
    type_totals = {row['type']: row['total'] for row in cursor.fetchall()}
    total_income = type_totals.get('income', 0.0)
    total_expense = type_totals.get('expense', 0.0)
    net_balance = total_income - total_expense

    # Suscripciones activas costo mensual equivalente
    cursor.execute("SELECT cost, billing_cycle FROM subscriptions WHERE is_active = 1")
    subs = cursor.fetchall()
    monthly_subs_cost = 0.0
    for s in subs:
        if s['billing_cycle'] == 'monthly':
            monthly_subs_cost += s['cost']
        elif s['billing_cycle'] == 'yearly':
            monthly_subs_cost += (s['cost'] / 12.0)

    # Gastos por Categoría
    cursor.execute("""
        SELECT category, SUM(amount) as category_total 
        FROM transactions 
        WHERE type = 'expense' 
        GROUP BY category 
        ORDER BY category_total DESC
    """)
    expenses_by_category = [{"category": row['category'], "total": round(row['category_total'], 2)} for row in cursor.fetchall()]

    # Tendencia de últimos días
    cursor.execute("""
        SELECT date, SUM(amount) as day_total
        FROM transactions
        WHERE type = 'expense'
        GROUP BY date
        ORDER BY date ASC
        LIMIT 30
    """)
    daily_trends = [{"date": row['date'], "total": round(row['day_total'], 2)} for row in cursor.fetchall()]

    # Total Ahorrado en Metas
    cursor.execute("SELECT SUM(current_amount) as total_saved FROM savings_goals")
    saved_row = cursor.fetchone()
    total_saved = saved_row['total_saved'] if saved_row and saved_row['total_saved'] else 0.0

    # ALGORITMO DE FINANCIAL HEALTH SCORE (0-100 pts)
    score = 70.0 # Base
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

    health_score = int(max(0, min(100, score)))

    conn.close()

    return {
        "net_balance": round(net_balance, 2),
        "total_income": round(total_income, 2),
        "total_expense": round(total_expense, 2),
        "monthly_subs_cost": round(monthly_subs_cost, 2),
        "total_saved": round(total_saved, 2),
        "health_score": health_score,
        "health_tips": tips,
        "expenses_by_category": expenses_by_category,
        "daily_trends": daily_trends
    }

# --- TRANSACTIONS API ---
@app.get("/api/transactions")
def get_transactions(
    type: Optional[str] = None, 
    category: Optional[str] = None, 
    search: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []

    if type:
        query += " AND type = ?"
        params.append(type)
    if category:
        query += " AND category = ?"
        params.append(category)
    if search:
        query += " AND (title LIKE ? OR notes LIKE ?)"
        params.append(f"%{search}%")
        params.append(f"%{search}%")
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)

    query += " ORDER BY date DESC, id DESC"
    cursor.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

@app.post("/api/transactions", status_code=201)
def create_transaction(tx: TransactionCreate):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO transactions (title, amount, type, category, date, payment_method, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (tx.title, tx.amount, tx.type, tx.category, tx.date, tx.payment_method, tx.notes)
    )
    tx_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"id": tx_id, "message": "Transacción registrada exitosamente"}

@app.delete("/api/transactions/{tx_id}")
def delete_transaction(tx_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transactions WHERE id = ?", (tx_id,))
    conn.commit()
    conn.close()
    return {"message": f"Transacción #{tx_id} eliminada"}

# --- SAVINGS GOALS API ---
@app.get("/api/savings_goals")
def get_savings_goals():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM savings_goals ORDER BY target_date ASC")
    goals = [dict(g) for g in cursor.fetchall()]
    for g in goals:
        g['percentage'] = min(round((g['current_amount'] / g['target_amount']) * 100, 1), 100.0) if g['target_amount'] > 0 else 0
    conn.close()
    return goals

@app.post("/api/savings_goals", status_code=201)
def create_savings_goal(goal: SavingsGoalCreate):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO savings_goals (title, target_amount, current_amount, target_date, category, icon)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (goal.title, goal.target_amount, goal.current_amount, goal.target_date, goal.category, goal.icon)
    )
    goal_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"id": goal_id, "message": "Meta de ahorro creada"}

@app.put("/api/savings_goals/{goal_id}/deposit")
def deposit_to_goal(goal_id: int, deposit: SavingsGoalDeposit):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT current_amount, target_amount, title FROM savings_goals WHERE id = ?", (goal_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Meta no encontrada")

    new_amount = row['current_amount'] + deposit.amount
    cursor.execute("UPDATE savings_goals SET current_amount = ? WHERE id = ?", (new_amount, goal_id))

    # Opcional: registrar como gasto de ahorro
    today_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute(
        """INSERT INTO transactions (title, amount, type, category, date, payment_method, notes)
           VALUES (?, ?, 'expense', 'Ahorro e Inversión', ?, 'Transferencia', ?)""",
        (f"Ahorro: {row['title']}", deposit.amount, today_str, f"Depósito a meta de ahorro #{goal_id}")
    )

    conn.commit()
    conn.close()
    return {"id": goal_id, "current_amount": round(new_amount, 2)}

@app.delete("/api/savings_goals/{goal_id}")
def delete_savings_goal(goal_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM savings_goals WHERE id = ?", (goal_id,))
    conn.commit()
    conn.close()
    return {"message": "Meta eliminada"}

# --- SUBSCRIPTIONS API ---
@app.get("/api/subscriptions")
def get_subscriptions():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM subscriptions ORDER BY next_billing_date ASC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

@app.post("/api/subscriptions", status_code=201)
def create_subscription(sub: SubscriptionCreate):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO subscriptions (name, cost, billing_cycle, category, next_billing_date, icon)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (sub.name, sub.cost, sub.billing_cycle, sub.category, sub.next_billing_date, sub.icon)
    )
    sub_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"id": sub_id, "message": "Suscripción añadida exitosamente"}

@app.put("/api/subscriptions/{sub_id}/toggle")
def toggle_subscription(sub_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_active FROM subscriptions WHERE id = ?", (sub_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Suscripción no encontrada")
    
    new_state = 0 if row['is_active'] == 1 else 1
    cursor.execute("UPDATE subscriptions SET is_active = ? WHERE id = ?", (new_state, sub_id))
    conn.commit()
    conn.close()
    return {"id": sub_id, "is_active": new_state}

@app.delete("/api/subscriptions/{sub_id}")
def delete_subscription(sub_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
    conn.commit()
    conn.close()
    return {"message": "Suscripción eliminada"}

# --- BUDGETS API ---
@app.get("/api/budgets")
def get_budgets():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM budgets")
    budgets = [dict(b) for b in cursor.fetchall()]

    for b in budgets:
        cursor.execute(
            """SELECT SUM(amount) as spent 
               FROM transactions 
               WHERE type = 'expense' AND category = ?""", 
            (b['category'],)
        )
        spent_row = cursor.fetchone()
        spent = spent_row['spent'] if spent_row and spent_row['spent'] else 0.0
        b['spent'] = round(spent, 2)
        b['percentage'] = min(round((spent / b['monthly_limit']) * 100, 1), 100.0) if b['monthly_limit'] > 0 else 0

    conn.close()
    return budgets

@app.post("/api/budgets")
def set_budget(b: BudgetUpdate):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO budgets (category, monthly_limit) VALUES (?, ?)
        ON CONFLICT(category) DO UPDATE SET monthly_limit = excluded.monthly_limit
    """, (b.category, b.monthly_limit))
    conn.commit()
    conn.close()
    return {"message": "Presupuesto actualizado"}

# --- IMPORT JSON API ---
@app.post("/api/import/json")
def import_json(data: BulkImportJSON):
    if not data.transactions:
        raise HTTPException(status_code=400, detail="No se enviaron transacciones para importar")

    conn = get_db_connection()
    cursor = conn.cursor()
    count = 0
    for tx in data.transactions:
        cursor.execute(
            """INSERT INTO transactions (title, amount, type, category, date, payment_method, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tx.title, tx.amount, tx.type, tx.category, tx.date, tx.payment_method, tx.notes)
        )
        count += 1
    conn.commit()
    conn.close()
    return {"imported_count": count, "message": f"Se importaron {count} transacciones con éxito"}

# --- EXPORT API ---
@app.get("/api/export/csv")
def export_csv():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM transactions ORDER BY date DESC")
    rows = cursor.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Título", "Monto", "Tipo", "Categoría", "Fecha", "Método Pago", "Notas"])
    for r in rows:
        writer.writerow([r['id'], r['title'], r['amount'], r['type'], r['category'], r['date'], r['payment_method'], r['notes']])

    return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=expenseflow_transactions.csv"})

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
    init_db()
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
