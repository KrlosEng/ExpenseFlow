import os
import tempfile
import unittest

# Base de datos temporal: los tests nunca tocan expenseflow.db
_TMP = tempfile.TemporaryDirectory()
os.environ["DB_PATH"] = os.path.join(_TMP.name, "test.db")
# En CI también se prueban contra PostgreSQL: TEST_DATABASE_URL apunta a una base desechable
if os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
else:
    os.environ.pop("DATABASE_URL", None)

from fastapi.testclient import TestClient

import auth
from app import app
from database import init_db


def new_client(email, sample_data=True):
    client = TestClient(app)
    res = client.post("/api/auth/register", json={
        "email": email, "password": "clave-segura-123", "name": "Tester", "sample_data": sample_data})
    assert res.status_code == 201, res.text
    return client


class TestExpenseFlowAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        auth._attempts.clear()
        cls.client = new_client("ana@example.com")

    def test_health_check(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("ExpenseFlow", data["system"])

    def test_summary_endpoint_with_health_score(self):
        response = self.client.get("/api/summary")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("net_balance", data)
        self.assertIn("health_score", data)
        self.assertIn("health_tips", data)
        self.assertIsInstance(data["health_score"], int)

    def test_transactions_crud_and_dates(self):
        # Create
        tx_payload = {
            "title": "Prueba Test Unitario v2",
            "amount": 150.00,
            "type": "expense",
            "category": "Alimentación & Supermercado",
            "date": "2026-08-05",
            "payment_method": "Tarjeta",
            "notes": "Testing backend v2"
        }
        res_create = self.client.post("/api/transactions", json=tx_payload)
        self.assertEqual(res_create.status_code, 201)
        created_id = res_create.json()["id"]

        # Read with date range filter
        res_get = self.client.get("/api/transactions?start_date=2026-08-01&end_date=2026-08-10")
        self.assertEqual(res_get.status_code, 200)
        txs = res_get.json()["items"]
        self.assertGreaterEqual(len(txs), 1)

        # Delete
        res_del = self.client.delete(f"/api/transactions/{created_id}")
        self.assertEqual(res_del.status_code, 200)

    def test_savings_goals_crud_and_deposit(self):
        # Create Goal
        goal_payload = {
            "title": "Meta Test Unitario",
            "target_amount": 500.00,
            "current_amount": 100.00,
            "target_date": "2026-12-31",
            "category": "Test"
        }
        res_create = self.client.post("/api/savings_goals", json=goal_payload)
        self.assertEqual(res_create.status_code, 201)
        goal_id = res_create.json()["id"]

        # Deposit to Goal
        res_deposit = self.client.put(f"/api/savings_goals/{goal_id}/deposit", json={"amount": 50.00})
        self.assertEqual(res_deposit.status_code, 200)
        self.assertEqual(res_deposit.json()["current_amount"], 150.00)

        # Delete Goal
        res_del = self.client.delete(f"/api/savings_goals/{goal_id}")
        self.assertEqual(res_del.status_code, 200)

    def test_subscriptions(self):
        res = self.client.get("/api/subscriptions")
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.json(), list)

    def test_budgets(self):
        res = self.client.get("/api/budgets")
        self.assertEqual(res.status_code, 200)
        self.assertIsInstance(res.json(), list)

    def test_categories_endpoint(self):
        res = self.client.get("/api/categories")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("Alimentación & Supermercado", data["expense"])
        self.assertIn("Ingresos & Salario", data["income"])

    def test_budget_categories_exist_in_catalog(self):
        cats = self.client.get("/api/categories").json()
        all_cats = set(cats["expense"]) | set(cats["income"])
        for b in self.client.get("/api/budgets").json():
            self.assertIn(b["category"], all_cats)

    def test_budgets_filter_by_month(self):
        payload = {"title": "Gasto viejo", "amount": 999.0, "type": "expense",
                   "category": "Mascotas", "date": "2001-01-15"}
        tx_id = self.client.post("/api/transactions", json=payload).json()["id"]
        try:
            self.client.post("/api/budgets", json={"category": "Mascotas", "monthly_limit": 100})
            old = {b["category"]: b for b in self.client.get("/api/budgets?month=2001-01").json()}
            now = {b["category"]: b for b in self.client.get("/api/budgets").json()}
            self.assertGreaterEqual(old["Mascotas"]["spent"], 999.0)
            self.assertLess(now["Mascotas"]["spent"], 999.0)
        finally:
            self.client.delete(f"/api/transactions/{tx_id}")

    def test_invalid_month_returns_422(self):
        self.assertEqual(self.client.get("/api/summary?month=2026-13").status_code, 422)

    # --- Fase 2: seguridad y validación ---
    def _tx(self, **over):
        base = {"title": "T", "amount": 10.0, "type": "expense",
                "category": "Mascotas", "date": "2026-01-01"}
        base.update(over)
        return self.client.post("/api/transactions", json=base)

    def test_invalid_transactions_rejected_with_422(self):
        for bad in ({"amount": -5}, {"amount": 0}, {"type": "robo"},
                    {"date": "2026-02-30"}, {"title": "   "}, {"notes": "x" * 501}):
            self.assertEqual(self._tx(**bad).status_code, 422, bad)

    def test_deposit_validation(self):
        gid = self.client.post("/api/savings_goals", json={
            "title": "Meta test", "target_amount": 100, "target_date": "2027-01-01"}).json()["id"]
        try:
            self.assertEqual(self.client.put(f"/api/savings_goals/{gid}/deposit", json={"amount": -10}).status_code, 422)
            self.assertEqual(self.client.put(f"/api/savings_goals/{gid}/deposit", json={"amount": 150}).status_code, 422)
            self.assertEqual(self.client.put(f"/api/savings_goals/{gid}/deposit", json={"amount": 100}).status_code, 200)
        finally:
            self.client.delete(f"/api/savings_goals/{gid}")

    def test_import_limit(self):
        tx = {"title": "x", "amount": 1, "type": "expense", "category": "Mascotas", "date": "2026-01-01"}
        res = self.client.post("/api/import/json", json={"transactions": [tx] * 1001})
        self.assertEqual(res.status_code, 422)

    def test_csv_formula_injection_neutralized(self):
        tx_id = self._tx(title="=HYPERLINK(\"http://evil\")").json()["id"]
        try:
            csv_text = self.client.get("/api/export/csv").text
            self.assertIn("'=HYPERLINK", csv_text)
        finally:
            self.client.delete(f"/api/transactions/{tx_id}")

    def test_security_headers_and_cors(self):
        res = self.client.get("/api/health", headers={"Origin": "https://evil.example"})
        self.assertEqual(res.headers.get("x-content-type-options"), "nosniff")
        self.assertIn("default-src 'self'", res.headers.get("content-security-policy", ""))
        self.assertNotIn("access-control-allow-origin", res.headers)


class TestAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        auth._attempts.clear()

    def test_protected_endpoints_require_login(self):
        anon = TestClient(app)
        for path in ("/api/summary", "/api/transactions", "/api/budgets",
                     "/api/subscriptions", "/api/savings_goals", "/api/export/csv"):
            self.assertEqual(anon.get(path).status_code, 401, path)
        self.assertEqual(anon.get("/api/health").status_code, 200)
        self.assertEqual(anon.get("/api/categories").status_code, 200)

    def test_register_login_logout_flow(self):
        c = new_client("flow@example.com", sample_data=False)
        cookie = c.cookies.get("ef_session")
        self.assertTrue(cookie)
        self.assertEqual(c.get("/api/auth/me").json()["email"], "flow@example.com")
        self.assertEqual(c.get("/api/transactions").json()["items"], [])  # sin datos de ejemplo
        self.assertEqual(len(c.get("/api/budgets").json()), 7)  # presupuestos por defecto

        c.post("/api/auth/logout")
        self.assertEqual(c.get("/api/auth/me").status_code, 401)

        bad = TestClient(app).post("/api/auth/login", json={"email": "flow@example.com", "password": "otra-clave"})
        self.assertEqual(bad.status_code, 401)
        ok = TestClient(app)
        login = ok.post("/api/auth/login", json={"email": "FLOW@example.com ", "password": "clave-segura-123"})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(ok.get("/api/auth/me").status_code, 200)

    def test_register_validation(self):
        c = TestClient(app)
        def register(email, password):
            return c.post("/api/auth/register", json={"email": email, "password": password, "name": "X"}).status_code

        self.assertEqual(register("x@example.com", "corta"), 422)
        self.assertEqual(register("no-es-correo", "clave-segura-123"), 422)
        new_client("dup@example.com", sample_data=False)
        self.assertEqual(register("dup@example.com", "clave-segura-123"), 409)

    def test_password_is_hashed(self):
        new_client("hash@example.com", sample_data=False)
        from database import get_db
        with get_db() as db:
            stored = db.fetchone("SELECT password_hash FROM users WHERE email = ?", ("hash@example.com",))["password_hash"]
        self.assertTrue(stored.startswith("scrypt$"))
        self.assertNotIn("clave-segura-123", stored)

    def test_tampered_token_rejected(self):
        c = TestClient(app)
        c.cookies.set("ef_session", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.firma-falsa")
        self.assertEqual(c.get("/api/summary").status_code, 401)

    def test_users_cannot_see_or_modify_each_other(self):
        a = new_client("a@example.com")
        b = new_client("b@example.com", sample_data=False)
        a_tx = a.get("/api/transactions").json()["items"]
        self.assertTrue(a_tx)
        self.assertEqual(b.get("/api/transactions").json()["items"], [])

        tx_id = a_tx[0]["id"]
        self.assertEqual(b.delete(f"/api/transactions/{tx_id}").status_code, 404)
        goal_id = a.get("/api/savings_goals").json()[0]["id"]
        self.assertEqual(b.put(f"/api/savings_goals/{goal_id}/deposit", json={"amount": 1}).status_code, 404)
        sub_id = a.get("/api/subscriptions").json()[0]["id"]
        self.assertEqual(b.put(f"/api/subscriptions/{sub_id}/toggle").status_code, 404)
        self.assertEqual(a.get("/api/transactions").json()["total"], len(a_tx))
        self.assertNotIn("Supermercado", b.get("/api/export/csv").text)

    def test_login_rate_limited(self):
        c = TestClient(app)
        codes = [c.post("/api/auth/login", json={"email": "nadie@example.com", "password": "x"}).status_code
                 for _ in range(auth.RATE_LIMIT + 1)]
        self.assertEqual(codes[-1], 429)


class TestPhase5(unittest.TestCase):
    """Edición, paginación, importación CSV, cobros recurrentes y moneda."""

    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        auth._attempts.clear()

    def _tx(self, client, **over):
        base = {"title": "Algo", "amount": 1000, "type": "expense", "category": "Mascotas", "date": "2026-01-10"}
        base.update(over)
        res = client.post("/api/transactions", json=base)
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()["id"]

    def test_edit_transaction_and_ownership(self):
        a = new_client("edit-a@example.com", sample_data=False)
        b = new_client("edit-b@example.com", sample_data=False)
        tx_id = self._tx(a)
        payload = {"title": "Concentrado", "amount": 85000, "type": "expense",
                   "category": "Mascotas", "date": "2026-01-11", "notes": "Bulto de 8 kg"}
        self.assertEqual(a.put(f"/api/transactions/{tx_id}", json=payload).status_code, 200)
        item = a.get("/api/transactions").json()["items"][0]
        self.assertEqual((item["title"], item["amount"], item["date"]), ("Concentrado", 85000, "2026-01-11"))
        self.assertEqual(b.put(f"/api/transactions/{tx_id}", json=payload).status_code, 404)
        self.assertEqual(a.put(f"/api/transactions/{tx_id}", json={**payload, "amount": -1}).status_code, 422)

    def test_edit_goal_and_subscription(self):
        a = new_client("edit-c@example.com", sample_data=False)
        gid = a.post("/api/savings_goals", json={"title": "Moto", "target_amount": 8_000_000,
                                                 "current_amount": 500_000, "target_date": "2027-06-01"}).json()["id"]
        res = a.put(f"/api/savings_goals/{gid}", json={"title": "Moto eléctrica", "target_amount": 9_000_000,
                                                      "target_date": "2027-08-01", "category": "Transporte"})
        self.assertEqual(res.status_code, 200)
        goal = a.get("/api/savings_goals").json()[0]
        self.assertEqual((goal["title"], goal["target_amount"], goal["current_amount"]), ("Moto eléctrica", 9_000_000, 500_000))

        sid = a.post("/api/subscriptions", json={"name": "Gimnasio", "cost": 90_000, "billing_cycle": "monthly",
                                                 "category": "Salud & Bienestar", "next_billing_date": "2030-01-05"}).json()["id"]
        res = a.put(f"/api/subscriptions/{sid}", json={"name": "Gimnasio", "cost": 99_000, "billing_cycle": "yearly",
                                                       "category": "Salud & Bienestar", "next_billing_date": "2030-02-05"})
        self.assertEqual(res.status_code, 200)
        sub = a.get("/api/subscriptions").json()[0]
        self.assertEqual((sub["cost"], sub["billing_cycle"]), (99_000, "yearly"))

    def test_pagination_and_totals(self):
        a = new_client("page@example.com", sample_data=False)
        for i in range(30):
            self._tx(a, title=f"Gasto {i}", amount=100, date=f"2026-01-{(i % 28) + 1:02d}")
        self._tx(a, title="Sueldo", amount=5000, type="income", category="Ingresos & Salario")
        p1 = a.get("/api/transactions?page=1&page_size=25").json()
        p2 = a.get("/api/transactions?page=2&page_size=25").json()
        self.assertEqual((p1["total"], len(p1["items"]), len(p2["items"])), (31, 25, 6))
        self.assertEqual((p1["income_total"], p1["expense_total"]), (5000, 3000))
        ids = {t["id"] for t in p1["items"]} | {t["id"] for t in p2["items"]}
        self.assertEqual(len(ids), 31)  # sin repetidos entre páginas
        self.assertEqual(a.get("/api/transactions?page=0").status_code, 422)

    def test_import_csv_roundtrip_and_formats(self):
        a = new_client("csv@example.com", sample_data=True)
        exported = a.get("/api/export/csv").text
        b = new_client("csv-b@example.com", sample_data=False)
        res = b.post("/api/import/csv", json={"csv": exported})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["imported_count"], a.get("/api/transactions").json()["total"])

        semicolon = "Fecha;Concepto;Valor;Tipo;Categoría\n2026-02-01;Arriendo;1.250.000,00;gasto;Vivienda & Alquiler\n"
        res = b.post("/api/import/csv", json={"csv": semicolon})
        self.assertEqual(res.status_code, 200, res.text)
        rent = b.get("/api/transactions?search=arriendo").json()["items"][0]
        self.assertEqual(rent["amount"], 1_250_000)

    def test_parse_amount_formats(self):
        import app as app_module
        cases = {"900.000": 900000, "1.250.000": 1250000, "1.234,50": 1234.5, "1,234.50": 1234.5,
                 "$ 45.900": 45900, "12.5": 12.5, "12,5": 12.5, "300000": 300000}
        for text, expected in cases.items():
            self.assertEqual(app_module.parse_amount(text), expected, text)

    def test_import_csv_rejects_bad_rows_atomically(self):
        a = new_client("csv-bad@example.com", sample_data=False)
        bad = "Título,Monto,Tipo,Categoría,Fecha\nBien,100,expense,Mascotas,2026-01-01\nMal,abc,expense,Mascotas,2026-01-02\n"
        res = a.post("/api/import/csv", json={"csv": bad})
        self.assertEqual(res.status_code, 422)
        self.assertIn("3", res.json()["detail"])
        self.assertEqual(a.get("/api/transactions").json()["total"], 0)
        self.assertEqual(a.post("/api/import/csv", json={"csv": "a,b\n1,2\n"}).status_code, 422)

    def test_due_subscription_generates_charges_and_advances(self):
        from datetime import date
        a = new_client("recurring@example.com", sample_data=False)
        today = date.today()
        # Fecha de hace dos meses: deben salir 3 cobros (hace 2 meses, hace 1 mes y este mes)
        two_ago = date(today.year - (1 if today.month <= 2 else 0), (today.month - 3) % 12 + 1, min(today.day, 28))
        a.post("/api/subscriptions", json={"name": "Streaming", "cost": 30_000, "billing_cycle": "monthly",
                                           "category": "Entretenimiento & Streaming",
                                           "next_billing_date": two_ago.isoformat()})
        subs = a.get("/api/subscriptions").json()
        self.assertGreater(subs[0]["next_billing_date"], today.isoformat())
        charges = a.get("/api/transactions?search=streaming").json()
        self.assertEqual(charges["total"], 3)
        self.assertTrue(all(t["payment_method"] == "Cobro automático" for t in charges["items"]))
        # Volver a leer no duplica cobros
        a.get("/api/summary")
        self.assertEqual(a.get("/api/transactions?search=streaming").json()["total"], 3)

    def test_paused_subscription_not_charged(self):
        a = new_client("paused@example.com", sample_data=False)
        sid = a.post("/api/subscriptions", json={"name": "Pausada", "cost": 10_000, "billing_cycle": "monthly",
                                                 "category": "Mascotas", "next_billing_date": "2026-01-01"}).json()["id"]
        # Pausar antes de cualquier lectura que procese cobros
        from database import get_db
        with get_db() as db:
            db.execute("UPDATE subscriptions SET is_active = 0 WHERE id = ?", (sid,))
        self.assertEqual(a.get("/api/transactions?search=pausada").json()["total"], 0)

    def test_add_cycle_end_of_month(self):
        from datetime import date

        import app as app_module
        self.assertEqual(app_module.add_cycle(date(2026, 1, 31), "monthly"), date(2026, 2, 28))
        self.assertEqual(app_module.add_cycle(date(2026, 12, 15), "monthly"), date(2027, 1, 15))
        self.assertEqual(app_module.add_cycle(date(2028, 2, 29), "yearly"), date(2029, 2, 28))

    def test_currency_default_and_update(self):
        a = new_client("money@example.com", sample_data=False)
        self.assertEqual(a.get("/api/auth/me").json()["currency"], "COP")
        self.assertEqual(a.put("/api/auth/me", json={"currency": "USD"}).json()["currency"], "USD")
        self.assertEqual(a.put("/api/auth/me", json={"currency": "BTC"}).status_code, 422)
        self.assertEqual(TestClient(app).put("/api/auth/me", json={"currency": "USD"}).status_code, 401)


class TestErrors(unittest.TestCase):
    """Respuestas de error: cada fallo devuelve el código correcto y un mensaje, nunca un 500."""

    @classmethod
    def setUpClass(cls):
        init_db()
        auth._attempts.clear()
        cls.c = new_client("errores@example.com", sample_data=False)

    def test_missing_resources_return_404(self):
        c = self.c
        cases = [
            c.delete("/api/transactions/999999"),
            c.put("/api/transactions/999999", json={"title": "x", "amount": 1, "type": "expense",
                                                    "category": "Mascotas", "date": "2026-01-01"}),
            c.delete("/api/subscriptions/999999"),
            c.put("/api/subscriptions/999999/toggle"),
            c.delete("/api/savings_goals/999999"),
            c.put("/api/savings_goals/999999/deposit", json={"amount": 1}),
            c.put("/api/savings_goals/999999", json={"title": "x", "target_amount": 1, "target_date": "2027-01-01"}),
        ]
        for res in cases:
            self.assertEqual(res.status_code, 404, res.request.url)
            self.assertIsInstance(res.json()["detail"], str)

    def test_bad_input_returns_422(self):
        c = self.c
        cases = [
            c.post("/api/subscriptions", json={"name": "x", "cost": 1, "billing_cycle": "weekly",
                                               "category": "Mascotas", "next_billing_date": "2026-01-01"}),
            c.post("/api/subscriptions", json={"name": "", "cost": 1, "billing_cycle": "monthly",
                                               "category": "Mascotas", "next_billing_date": "2026-01-01"}),
            c.post("/api/savings_goals", json={"title": "x", "target_amount": 0, "target_date": "2027-01-01"}),
            c.post("/api/savings_goals", json={"title": "x", "target_amount": 10, "current_amount": -1,
                                               "target_date": "2027-01-01"}),
            c.post("/api/budgets", json={"category": "Mascotas", "monthly_limit": -5}),
            c.post("/api/budgets", json={"category": "", "monthly_limit": 5}),
            c.get("/api/budgets?month=2026-1"),
            c.get("/api/transactions?page_size=500"),
            c.put("/api/transactions/abc", json={}),
            c.post("/api/transactions", content="no es json", headers={"Content-Type": "application/json"}),
        ]
        for res in cases:
            self.assertEqual(res.status_code, 422, f"{res.request.method} {res.request.url}: {res.text}")

    def test_empty_import_returns_400(self):
        self.assertEqual(self.c.post("/api/import/json", json={"transactions": []}).status_code, 400)
        self.assertEqual(self.c.post("/api/import/csv", json={"csv": "Título,Monto,Tipo,Categoría,Fecha\n"}).status_code, 400)

    def test_unknown_route_and_method(self):
        self.assertEqual(self.c.get("/api/no-existe").status_code, 404)
        self.assertEqual(self.c.patch("/api/transactions/1", json={}).status_code, 405)

    def test_health_reports_database(self):
        data = TestClient(app).get("/api/health").json()
        expected = "postgresql" if os.environ.get("TEST_DATABASE_URL") else "sqlite"
        self.assertEqual(data["database"], expected)


if __name__ == "__main__":
    unittest.main()
