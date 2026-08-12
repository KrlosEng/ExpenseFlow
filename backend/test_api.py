import unittest
import os
import json
from fastapi.testclient import TestClient
from app import app
from database import init_db

class TestExpenseFlowAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

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
            "category": "Alimentación",
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
        txs = res_get.json()
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

if __name__ == "__main__":
    unittest.main()
