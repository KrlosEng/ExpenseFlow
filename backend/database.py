"""
Capa de acceso a datos de ExpenseFlow.

- Si existe la variable DATABASE_URL (postgres://...), usa PostgreSQL (Neon, Supabase, etc.).
- Si no, usa SQLite local (archivo expenseflow.db, o la ruta de DB_PATH).

Las consultas se escriben con placeholders "?" y la clase Db los adapta a cada motor.
"""
import logging
import os
import sqlite3
from datetime import datetime, timedelta

log = logging.getLogger("expenseflow.db")

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
IS_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))

# Lista única de categorías: la usan los datos de ejemplo, los presupuestos y el frontend (/api/categories)
EXPENSE_CATEGORIES = [
    "Alimentación & Supermercado", "Servicios, Luz & Agua", "Servidores, Cloud & Software",
    "Entretenimiento & Streaming", "Transporte & Gasolina", "Salud & Bienestar",
    "Vivienda & Alquiler", "Educación & Cursos", "Compras & Estilo de Vida",
    "Ahorro e Inversión", "Viajes & Turismo", "Mascotas", "Hobbies & Tecnología",
    "Impuestos & Trámites", "Regalos & Donaciones",
]
INCOME_CATEGORIES = ["Ingresos & Salario", "Freelance & Negocios"]
CATEGORIES = EXPENSE_CATEGORIES + INCOME_CATEGORIES


def get_db_path():
    if os.environ.get("DB_PATH"):
        return os.environ["DB_PATH"]
    if os.environ.get("VERCEL"):
        # Sin DATABASE_URL en Vercel solo queda /tmp, que se borra en cada cold start.
        log.warning("DATABASE_URL no está definida: usando SQLite en /tmp (los datos NO persisten).")
        return "/tmp/expenseflow.db"
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "expenseflow.db")


class Db:
    """Conexión mínima que funciona igual con SQLite y PostgreSQL. Filas como dict."""

    def __init__(self):
        if IS_POSTGRES:
            import psycopg
            from psycopg.rows import dict_row
            self.conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        else:
            self.conn = sqlite3.connect(get_db_path())
            self.conn.row_factory = lambda cur, row: {d[0]: row[i] for i, d in enumerate(cur.description)}
            self.conn.execute("PRAGMA foreign_keys = ON")

    def _sql(self, sql):
        return sql.replace("?", "%s") if IS_POSTGRES else sql

    def execute(self, sql, params=()):
        cur = self.conn.cursor()
        cur.execute(self._sql(sql), params)
        return cur

    def fetchone(self, sql, params=()):
        return self.execute(sql, params).fetchone()

    def fetchall(self, sql, params=()):
        return self.execute(sql, params).fetchall()

    def insert(self, sql, params=()):
        """Ejecuta un INSERT y devuelve el id creado."""
        if IS_POSTGRES:
            return self.execute(sql + " RETURNING id", params).fetchone()["id"]
        return self.execute(sql, params).lastrowid

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        if exc_type is None:
            self.commit()
        else:
            self.conn.rollback()
        self.close()


def get_db():
    return Db()


def _schema():
    pk = "SERIAL PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    real = "DOUBLE PRECISION" if IS_POSTGRES else "REAL"
    owner = "user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE"
    return [
        f"""CREATE TABLE IF NOT EXISTS users (
            id {pk},
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            currency TEXT NOT NULL DEFAULT 'COP',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        f"""CREATE TABLE IF NOT EXISTS transactions (
            id {pk},
            {owner},
            title TEXT NOT NULL,
            amount {real} NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('expense', 'income')),
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            payment_method TEXT DEFAULT 'Tarjeta',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        f"""CREATE TABLE IF NOT EXISTS subscriptions (
            id {pk},
            {owner},
            name TEXT NOT NULL,
            cost {real} NOT NULL,
            billing_cycle TEXT NOT NULL CHECK(billing_cycle IN ('monthly', 'yearly')),
            category TEXT NOT NULL,
            next_billing_date TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            icon TEXT DEFAULT 'credit-card',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        f"""CREATE TABLE IF NOT EXISTS budgets (
            id {pk},
            {owner},
            category TEXT NOT NULL,
            monthly_limit {real} NOT NULL,
            period TEXT DEFAULT 'monthly',
            UNIQUE(user_id, category)
        )""",
        f"""CREATE TABLE IF NOT EXISTS savings_goals (
            id {pk},
            {owner},
            title TEXT NOT NULL,
            target_amount {real} NOT NULL,
            current_amount {real} DEFAULT 0.0,
            target_date TEXT NOT NULL,
            category TEXT DEFAULT 'General',
            icon TEXT DEFAULT 'piggy-bank',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        "CREATE INDEX IF NOT EXISTS idx_tx_user_date ON transactions(user_id, date)",
        "CREATE INDEX IF NOT EXISTS idx_subs_user ON subscriptions(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_goals_user ON savings_goals(user_id)",
    ]


def _backup_legacy_sqlite():
    """Las bases SQLite de versiones anteriores no tienen usuarios. Se guardan aparte y se empieza de cero."""
    if IS_POSTGRES:
        return
    path = get_db_path()
    if not os.path.exists(path):
        return
    conn = sqlite3.connect(path)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(transactions)").fetchall()]
    finally:
        conn.close()
    if cols and "user_id" not in cols:
        backup = path.replace(".db", f".legacy-{datetime.now():%Y%m%d%H%M%S}.db")
        os.replace(path, backup)
        log.warning("Base de datos sin usuarios respaldada en %s; se creó una nueva.", backup)


CURRENCIES = ["COP", "USD", "EUR", "MXN"]


def _column_exists(db, table, column):
    if IS_POSTGRES:
        row = db.fetchone(
            "SELECT 1 AS ok FROM information_schema.columns WHERE table_name = ? AND column_name = ?",
            (table, column))
        return bool(row)
    return any(r["name"] == column for r in db.fetchall(f"PRAGMA table_info({table})"))


def _migrate(db):
    """Cambios de esquema sobre bases ya creadas (idempotente)."""
    if not _column_exists(db, "users", "currency"):
        db.execute("ALTER TABLE users ADD COLUMN currency TEXT NOT NULL DEFAULT 'COP'")


def init_db():
    _backup_legacy_sqlite()
    with get_db() as db:
        for stmt in _schema():
            db.execute(stmt)
        _migrate(db)


# Montos en pesos colombianos (la moneda por defecto de una cuenta nueva)
DEFAULT_BUDGETS = [
    ("Alimentación & Supermercado", 1_400_000),
    ("Servicios, Luz & Agua", 450_000),
    ("Servidores, Cloud & Software", 300_000),
    ("Entretenimiento & Streaming", 250_000),
    ("Transporte & Gasolina", 400_000),
    ("Compras & Estilo de Vida", 500_000),
    ("Salud & Bienestar", 300_000),
]


def seed_user_data(db, user_id, with_samples=False):
    """Presupuestos por defecto para un usuario nuevo y, opcionalmente, datos de ejemplo."""
    for category, limit in DEFAULT_BUDGETS:
        db.execute(
            "INSERT INTO budgets (user_id, category, monthly_limit) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, category) DO NOTHING",
            (user_id, category, limit),
        )
    if not with_samples:
        return

    today = datetime.now()

    def d(days):
        return (today + timedelta(days=days)).strftime("%Y-%m-%d")

    for tx in [
        ("Sueldo", 4_800_000, "income", "Ingresos & Salario", d(-2), "Transferencia", "Pago de nómina"),
        ("Mercado de la semana", 285_400, "expense", "Alimentación & Supermercado", d(-1), "Tarjeta Débito", ""),
        ("Hosting en la nube", 152_000, "expense", "Servidores, Cloud & Software", d(-3), "Tarjeta Crédito",
         "Servidor de desarrollo"),
        ("Cine y crispetas", 64_000, "expense", "Entretenimiento & Streaming", d(-4), "Efectivo", ""),
        ("Gasolina", 120_000, "expense", "Transporte & Gasolina", d(-5), "Tarjeta Débito", "Tanqueada"),
        ("Curso en línea", 59_900, "expense", "Educación & Cursos", d(-7), "Tarjeta Crédito", "Curso de Python"),
        ("Almuerzo de equipo", 178_000, "expense", "Alimentación & Supermercado", d(-8), "Tarjeta Crédito", ""),
        ("Spotify Premium", 16_900, "expense", "Entretenimiento & Streaming", d(-10), "Tarjeta Crédito", "Suscripción mensual"),
    ]:
        db.execute(
            "INSERT INTO transactions (user_id, title, amount, type, category, date, payment_method, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, *tx),
        )

    for sub in [
        ("Netflix", 44_900, "monthly", "Entretenimiento & Streaming", d(4), 1, "tv"),
        ("Spotify Premium", 16_900, "monthly", "Entretenimiento & Streaming", d(20), 1, "music"),
        ("GitHub Copilot", 42_000, "monthly", "Servidores, Cloud & Software", d(18), 1, "code"),
        ("ChatGPT Plus", 84_000, "monthly", "Servidores, Cloud & Software", d(22), 1, "bot"),
        ("Google Workspace", 312_000, "yearly", "Servidores, Cloud & Software", d(145), 1, "mail"),
    ]:
        db.execute(
            "INSERT INTO subscriptions (user_id, name, cost, billing_cycle, category, next_billing_date, is_active, icon) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, *sub),
        )

    for goal in [
        ("Fondo de emergencia", 10_000_000, 4_200_000, d(180), "Seguridad", "shield-halved"),
        ("Portátil nuevo", 5_500_000, 2_300_000, d(90), "Tecnología", "laptop"),
        ("Viaje a Cartagena", 3_800_000, 1_100_000, d(120), "Viajes", "plane"),
    ]:
        db.execute(
            "INSERT INTO savings_goals (user_id, title, target_amount, current_amount, target_date, category, icon) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, *goal),
        )


if __name__ == "__main__":
    init_db()
    print("Base de datos inicializada:", "PostgreSQL" if IS_POSTGRES else get_db_path())
