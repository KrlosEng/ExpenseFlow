/**
 * ExpenseFlow — cliente de la API.
 * Todas las llamadas al backend pasan por aquí; la sesión viaja en una cookie HttpOnly.
 */

const API_BASE_URL = window.location.origin.includes('http') 
    ? window.location.origin 
    : 'http://127.0.0.1:8000';

// fetch con la cookie de sesión; si el servidor responde 401 avisa a la app para mostrar el login
async function apiFetch(url, options = {}) {
    const res = await fetch(url, { credentials: 'include', ...options });
    if (res.status === 401 && !url.includes('/api/auth/')) {
        window.dispatchEvent(new CustomEvent('auth-required'));
    }
    return res;
}

async function errorDetail(res, fallback) {
    const body = await res.json().catch(() => ({}));
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail) && body.detail[0]?.msg) return body.detail[0].msg;
    return fallback;
}

class ExpenseFlowAPI {
    static async me() {
        const res = await apiFetch(`${API_BASE_URL}/api/auth/me`);
        return res.ok ? await res.json() : null;
    }

    static async login(email, password) {
        const res = await apiFetch(`${API_BASE_URL}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });
        if (!res.ok) throw new Error(await errorDetail(res, "No se pudo iniciar sesión"));
        return await res.json();
    }

    static async register(name, email, password, sampleData, currency = "COP") {
        const res = await apiFetch(`${API_BASE_URL}/api/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, email, password, sample_data: sampleData, currency })
        });
        if (!res.ok) throw new Error(await errorDetail(res, "No se pudo crear la cuenta"));
        return await res.json();
    }

    static async logout() {
        await apiFetch(`${API_BASE_URL}/api/auth/logout`, { method: 'POST' });
    }

    /** Envía JSON y devuelve la respuesta; si falla, lanza el mensaje del servidor. */
    static async send(method, path, body, fallback) {
        const res = await apiFetch(`${API_BASE_URL}${path}`, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        if (!res.ok) throw new Error(await errorDetail(res, fallback));
        return await res.json();
    }

    static updateProfile(data) {
        return ExpenseFlowAPI.send('PUT', '/api/auth/me', data, "No se pudo guardar tu perfil");
    }

    static updateTransaction(id, data) {
        return ExpenseFlowAPI.send('PUT', `/api/transactions/${id}`, data, "No se pudo actualizar el movimiento");
    }

    static updateSubscription(id, data) {
        return ExpenseFlowAPI.send('PUT', `/api/subscriptions/${id}`, data, "No se pudo actualizar la suscripción");
    }

    static updateSavingsGoal(id, data) {
        return ExpenseFlowAPI.send('PUT', `/api/savings_goals/${id}`, data, "No se pudo actualizar la meta");
    }

    static importCSV(text) {
        return ExpenseFlowAPI.send('POST', '/api/import/csv', { csv: text }, "No se pudo importar el CSV");
    }

    static async checkHealth() {
        try {
            const res = await apiFetch(`${API_BASE_URL}/api/health`);
            if (!res.ok) throw new Error(await errorDetail(res, "Offline"));
            return await res.json();
        } catch (err) {
            return { status: "offline", error: err.message };
        }
    }

    static async getCategories() {
        const res = await apiFetch(`${API_BASE_URL}/api/categories`);
        if (!res.ok) throw new Error(await errorDetail(res, "Error obteniendo categorías"));
        return await res.json();
    }

    static async getSummary() {
        const res = await apiFetch(`${API_BASE_URL}/api/summary`);
        if (!res.ok) throw new Error(await errorDetail(res, "Error obteniendo resumen"));
        return await res.json();
    }

    static async getTransactions(type = "", category = "", search = "", startDate = "", endDate = "", page = 1, pageSize = 25) {
        const params = new URLSearchParams();
        if (type) params.append("type", type);
        if (category) params.append("category", category);
        if (search) params.append("search", search);
        if (startDate) params.append("start_date", startDate);
        if (endDate) params.append("end_date", endDate);
        params.append("page", page);
        params.append("page_size", pageSize);

        const res = await apiFetch(`${API_BASE_URL}/api/transactions?${params.toString()}`);
        if (!res.ok) throw new Error(await errorDetail(res, "Error obteniendo transacciones"));
        return await res.json();
    }

    static async createTransaction(txData) {
        const res = await apiFetch(`${API_BASE_URL}/api/transactions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(txData)
        });
        if (!res.ok) throw new Error(await errorDetail(res, "Error al guardar transacción"));
        return await res.json();
    }

    static async deleteTransaction(id) {
        const res = await apiFetch(`${API_BASE_URL}/api/transactions/${id}`, {
            method: 'DELETE'
        });
        if (!res.ok) throw new Error(await errorDetail(res, "Error al eliminar transacción"));
        return await res.json();
    }

    static async getSavingsGoals() {
        const res = await apiFetch(`${API_BASE_URL}/api/savings_goals`);
        if (!res.ok) throw new Error(await errorDetail(res, "Error obteniendo metas de ahorro"));
        return await res.json();
    }

    static async createSavingsGoal(goalData) {
        const res = await apiFetch(`${API_BASE_URL}/api/savings_goals`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(goalData)
        });
        if (!res.ok) throw new Error(await errorDetail(res, "Error al crear meta de ahorro"));
        return await res.json();
    }

    static async depositToSavingsGoal(id, amount) {
        const res = await apiFetch(`${API_BASE_URL}/api/savings_goals/${id}/deposit`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ amount })
        });
        if (!res.ok) {
            const body = await res.json().catch(() => ({}));
            throw new Error(typeof body.detail === 'string' ? body.detail : "Error al depositar a meta de ahorro");
        }
        return await res.json();
    }

    static async deleteSavingsGoal(id) {
        const res = await apiFetch(`${API_BASE_URL}/api/savings_goals/${id}`, {
            method: 'DELETE'
        });
        if (!res.ok) throw new Error(await errorDetail(res, "Error al eliminar meta de ahorro"));
        return await res.json();
    }

    static async getSubscriptions() {
        const res = await apiFetch(`${API_BASE_URL}/api/subscriptions`);
        if (!res.ok) throw new Error(await errorDetail(res, "Error obteniendo suscripciones"));
        return await res.json();
    }

    static async createSubscription(subData) {
        const res = await apiFetch(`${API_BASE_URL}/api/subscriptions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(subData)
        });
        if (!res.ok) throw new Error(await errorDetail(res, "Error al guardar suscripción"));
        return await res.json();
    }

    static async toggleSubscription(id) {
        const res = await apiFetch(`${API_BASE_URL}/api/subscriptions/${id}/toggle`, {
            method: 'PUT'
        });
        if (!res.ok) throw new Error(await errorDetail(res, "Error al alternar estado de suscripción"));
        return await res.json();
    }

    static async deleteSubscription(id) {
        const res = await apiFetch(`${API_BASE_URL}/api/subscriptions/${id}`, {
            method: 'DELETE'
        });
        if (!res.ok) throw new Error(await errorDetail(res, "Error al eliminar suscripción"));
        return await res.json();
    }

    static async getBudgets() {
        const res = await apiFetch(`${API_BASE_URL}/api/budgets`);
        if (!res.ok) throw new Error(await errorDetail(res, "Error obteniendo presupuestos"));
        return await res.json();
    }

    static async updateBudget(category, monthly_limit) {
        const res = await apiFetch(`${API_BASE_URL}/api/budgets`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ category, monthly_limit })
        });
        if (!res.ok) throw new Error(await errorDetail(res, "Error al actualizar presupuesto"));
        return await res.json();
    }

    static async importJSON(transactionsArray) {
        const res = await apiFetch(`${API_BASE_URL}/api/import/json`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ transactions: transactionsArray })
        });
        if (!res.ok) throw new Error(await errorDetail(res, "Error al importar datos JSON"));
        return await res.json();
    }
}

window.ExpenseFlowAPI = ExpenseFlowAPI;
