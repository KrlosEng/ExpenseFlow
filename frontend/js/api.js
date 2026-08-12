/**
 * AuraFinance API Client Module v2.0
 * Handles all async communication with backend REST API endpoints.
 */

const API_BASE_URL = window.location.origin.includes('http') 
    ? window.location.origin 
    : 'http://127.0.0.1:8000';

class AuraFinanceAPI {
    static async checkHealth() {
        try {
            const res = await fetch(`${API_BASE_URL}/api/health`);
            if (!res.ok) throw new Error("Offline");
            return await res.json();
        } catch (err) {
            return { status: "offline", error: err.message };
        }
    }

    static async getSummary() {
        const res = await fetch(`${API_BASE_URL}/api/summary`);
        if (!res.ok) throw new Error("Error obteniendo resumen");
        return await res.json();
    }

    static async getTransactions(type = "", category = "", search = "", startDate = "", endDate = "") {
        const params = new URLSearchParams();
        if (type) params.append("type", type);
        if (category) params.append("category", category);
        if (search) params.append("search", search);
        if (startDate) params.append("start_date", startDate);
        if (endDate) params.append("end_date", endDate);

        const res = await fetch(`${API_BASE_URL}/api/transactions?${params.toString()}`);
        if (!res.ok) throw new Error("Error obteniendo transacciones");
        return await res.json();
    }

    static async createTransaction(txData) {
        const res = await fetch(`${API_BASE_URL}/api/transactions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(txData)
        });
        if (!res.ok) throw new Error("Error al guardar transacción");
        return await res.json();
    }

    static async deleteTransaction(id) {
        const res = await fetch(`${API_BASE_URL}/api/transactions/${id}`, {
            method: 'DELETE'
        });
        if (!res.ok) throw new Error("Error al eliminar transacción");
        return await res.json();
    }

    static async getSavingsGoals() {
        const res = await fetch(`${API_BASE_URL}/api/savings_goals`);
        if (!res.ok) throw new Error("Error obteniendo metas de ahorro");
        return await res.json();
    }

    static async createSavingsGoal(goalData) {
        const res = await fetch(`${API_BASE_URL}/api/savings_goals`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(goalData)
        });
        if (!res.ok) throw new Error("Error al crear meta de ahorro");
        return await res.json();
    }

    static async depositToSavingsGoal(id, amount) {
        const res = await fetch(`${API_BASE_URL}/api/savings_goals/${id}/deposit`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ amount })
        });
        if (!res.ok) throw new Error("Error al depositar a meta de ahorro");
        return await res.json();
    }

    static async deleteSavingsGoal(id) {
        const res = await fetch(`${API_BASE_URL}/api/savings_goals/${id}`, {
            method: 'DELETE'
        });
        if (!res.ok) throw new Error("Error al eliminar meta de ahorro");
        return await res.json();
    }

    static async getSubscriptions() {
        const res = await fetch(`${API_BASE_URL}/api/subscriptions`);
        if (!res.ok) throw new Error("Error obteniendo suscripciones");
        return await res.json();
    }

    static async createSubscription(subData) {
        const res = await fetch(`${API_BASE_URL}/api/subscriptions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(subData)
        });
        if (!res.ok) throw new Error("Error al guardar suscripción");
        return await res.json();
    }

    static async toggleSubscription(id) {
        const res = await fetch(`${API_BASE_URL}/api/subscriptions/${id}/toggle`, {
            method: 'PUT'
        });
        if (!res.ok) throw new Error("Error al alternar estado de suscripción");
        return await res.json();
    }

    static async deleteSubscription(id) {
        const res = await fetch(`${API_BASE_URL}/api/subscriptions/${id}`, {
            method: 'DELETE'
        });
        if (!res.ok) throw new Error("Error al eliminar suscripción");
        return await res.json();
    }

    static async getBudgets() {
        const res = await fetch(`${API_BASE_URL}/api/budgets`);
        if (!res.ok) throw new Error("Error obteniendo presupuestos");
        return await res.json();
    }

    static async updateBudget(category, monthly_limit) {
        const res = await fetch(`${API_BASE_URL}/api/budgets`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ category, monthly_limit })
        });
        if (!res.ok) throw new Error("Error al actualizar presupuesto");
        return await res.json();
    }

    static async importJSON(transactionsArray) {
        const res = await fetch(`${API_BASE_URL}/api/import/json`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ transactions: transactionsArray })
        });
        if (!res.ok) throw new Error("Error al importar datos JSON");
        return await res.json();
    }
}

window.ExpenseFlowAPI = AuraFinanceAPI;
window.AuraFinanceAPI = AuraFinanceAPI;
