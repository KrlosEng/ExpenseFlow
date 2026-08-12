import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "expenseflow.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Tabla de Transacciones (Gastos e Ingresos)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            amount REAL NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('expense', 'income')),
            category TEXT NOT NULL,
            date TEXT NOT NULL,
            payment_method TEXT DEFAULT 'Tarjeta',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Tabla de Suscripciones
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            cost REAL NOT NULL,
            billing_cycle TEXT NOT NULL CHECK(billing_cycle IN ('monthly', 'yearly')),
            category TEXT NOT NULL,
            next_billing_date TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            icon TEXT DEFAULT 'credit-card',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Tabla de Presupuestos por Categoría
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT UNIQUE NOT NULL,
            monthly_limit REAL NOT NULL,
            period TEXT DEFAULT 'monthly'
        )
    """)

    # Tabla de Metas de Ahorro
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS savings_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            target_amount REAL NOT NULL,
            current_amount REAL DEFAULT 0.0,
            target_date TEXT NOT NULL,
            category TEXT DEFAULT 'General',
            icon TEXT DEFAULT 'piggy-bank',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    # Check if seed data is needed
    cursor.execute("SELECT COUNT(*) as count FROM transactions")
    if cursor.fetchone()['count'] == 0:
        seed_sample_data(conn)

    conn.close()

def seed_sample_data(conn):
    cursor = conn.cursor()
    today = datetime.now()

    # Presupuestos por defecto
    default_budgets = [
        ("Alimentación & Supermercado", 450.00),
        ("Servicios, Luz & Agua", 200.00),
        ("Servidores, Cloud & Software", 150.00),
        ("Entretenimiento & Streaming", 120.00),
        ("Transporte & Gasolina", 140.00),
        ("Compras & Estilo de Vida", 250.00),
        ("Salud & Bienestar", 100.00)
    ]
    cursor.executemany(
        "INSERT OR IGNORE INTO budgets (category, monthly_limit) VALUES (?, ?)",
        default_budgets
    )

    # Transacciones de ejemplo
    sample_transactions = [
        ("Sueldo / Freelance", 3200.00, "income", "Ingresos", (today - timedelta(days=2)).strftime("%Y-%m-%d"), "Transferencia", "Pago de proyecto web"),
        ("Supermercado Metro", 142.50, "expense", "Alimentación", (today - timedelta(days=1)).strftime("%Y-%m-%d"), "Tarjeta Crédito", "Mercado semanal"),
        ("AWS Cloud Hosting", 35.80, "expense", "Servicios y Cloud", (today - timedelta(days=3)).strftime("%Y-%m-%d"), "Tarjeta Débito", "Servidores de desarrollo"),
        ("Cine & Snacks", 28.00, "expense", "Entretenimiento", (today - timedelta(days=4)).strftime("%Y-%m-%d"), "Efectivo", "Salida fines de semana"),
        ("Gasolina / Uber", 45.00, "expense", "Transporte", (today - timedelta(days=5)).strftime("%Y-%m-%d"), "Tarjeta Crédito", "Recarga semana"),
        ("Curso Udemy Fullstack", 14.99, "expense", "Educación", (today - timedelta(days=7)).strftime("%Y-%m-%d"), "PayPal", "Curso Python FastAPI"),
        ("Restaurante Gourmet", 85.00, "expense", "Alimentación", (today - timedelta(days=8)).strftime("%Y-%m-%d"), "Tarjeta Crédito", "Cena de equipo"),
        ("Spotify Premium", 9.99, "expense", "Entretenimiento", (today - timedelta(days=10)).strftime("%Y-%m-%d"), "Tarjeta Crédito", "Suscripción mensual")
    ]
    cursor.executemany(
        "INSERT INTO transactions (title, amount, type, category, date, payment_method, notes) VALUES (?, ?, ?, ?, ?, ?, ?)",
        sample_transactions
    )

    # Suscripciones de ejemplo
    sample_subs = [
        ("Netflix Ultra HD", 17.99, "monthly", "Entretenimiento", (today + timedelta(days=4)).strftime("%Y-%m-%d"), 1, "tv"),
        ("Spotify Premium", 9.99, "monthly", "Entretenimiento", (today + timedelta(days=12)).strftime("%Y-%m-%d"), 1, "music"),
        ("GitHub Copilot / AI", 10.00, "monthly", "Servicios y Cloud", (today + timedelta(days=18)).strftime("%Y-%m-%d"), 1, "code"),
        ("ChatGPT Plus", 20.00, "monthly", "Servicios y Cloud", (today + timedelta(days=22)).strftime("%Y-%m-%d"), 1, "bot"),
        ("GSuite Business Mail", 72.00, "yearly", "Servicios y Cloud", (today + timedelta(days=145)).strftime("%Y-%m-%d"), 1, "mail")
    ]
    cursor.executemany(
        "INSERT INTO subscriptions (name, cost, billing_cycle, category, next_billing_date, is_active, icon) VALUES (?, ?, ?, ?, ?, ?, ?)",
        sample_subs
    )

    # Metas de ahorro de ejemplo
    sample_goals = [
        ("Fondo de Emergencia", 2500.00, 1200.00, (today + timedelta(days=180)).strftime("%Y-%m-%d"), "Seguridad", "shield-halved"),
        ("Laptop Gaming / Dev", 1800.00, 950.00, (today + timedelta(days=90)).strftime("%Y-%m-%d"), "Tecnología", "laptop"),
        ("Viaje Vacaciones", 1200.00, 400.00, (today + timedelta(days=120)).strftime("%Y-%m-%d"), "Viajes", "plane")
    ]
    cursor.executemany(
        "INSERT INTO savings_goals (title, target_amount, current_amount, target_date, category, icon) VALUES (?, ?, ?, ?, ?, ?)",
        sample_goals
    )

    conn.commit()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at:", DB_PATH)
