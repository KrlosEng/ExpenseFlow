/**
 * AuraFinance Main UI Controller v2.0
 * Manages view tabs, health score, savings goals, calculator, search, filters and data bindings.
 */

let currentCalcInstallment = null;

document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

async function initApp() {
    setupNavigation();
    setupModals();
    setupFilters();
    setupForms();
    setupCalculator();

    // Check Backend Server Status
    await checkServerStatus();

    // Load initial data
    await refreshDashboard();
    await refreshSavingsGoals();
    await refreshTransactions();
    await refreshSubscriptions();
    await refreshBudgets();

    // Pre-fill today's date in form inputs
    const today = new Date().toISOString().split('T')[0];
    ['tx-date', 'sub-date', 'goal-date'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = today;
    });
}

// Check Backend API Connection
async function checkServerStatus() {
    const statusText = document.getElementById('api-status-text');
    const statusDot = document.querySelector('.status-dot');
    
    const res = await AuraFinanceAPI.checkHealth();
    if (res.status === "online") {
        statusText.textContent = "Online - SQLite Engine";
        statusDot.className = "status-dot online";
    } else {
        statusText.textContent = "Offline (Reintentando)";
        statusDot.className = "status-dot offline";
    }
}

// TAB NAVIGATION SYSTEM
function setupNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    const tabContents = document.querySelectorAll('.tab-content');
    const pageTitle = document.getElementById('page-title');
    const pageSubtitle = document.getElementById('page-subtitle');

    const titleMap = {
        'dashboard': { title: 'Dashboard Financiero', subtitle: 'Plataforma Inteligente de Gestión Financiera & Ahorro' },
        'savings': { title: 'Metas de Ahorro', subtitle: 'Alcancías virtuales para proyectos e inversiones a futuro' },
        'transactions': { title: 'Gestión de Transacciones', subtitle: 'Historial de movimientos con búsqueda avanzada y filtros por fecha' },
        'subscriptions': { title: 'Suscripciones Recurrentes', subtitle: 'Monitoreo de servicios en la nube y recordatorio de cobros' },
        'budgets': { title: 'Presupuestos Mensuales', subtitle: 'Límites de consumo por categoría e indicadores de gasto' },
        'calculator': { title: 'Calculadora de Cuotas', subtitle: 'Simulador de créditos y compras a plazos con amortización' }
    };

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const targetTab = item.getAttribute('data-tab');

            navItems.forEach(i => i.classList.remove('active'));
            tabContents.forEach(t => t.classList.remove('active'));

            item.classList.add('active');
            document.getElementById(`tab-${targetTab}`).classList.add('active');

            if (titleMap[targetTab]) {
                pageTitle.textContent = titleMap[targetTab].title;
                pageSubtitle.textContent = titleMap[targetTab].subtitle;
            }

            // Refresh target tab
            if (targetTab === 'dashboard') refreshDashboard();
            if (targetTab === 'savings') refreshSavingsGoals();
            if (targetTab === 'transactions') refreshTransactions();
            if (targetTab === 'subscriptions') refreshSubscriptions();
            if (targetTab === 'budgets') refreshBudgets();
        });
    });

    document.getElementById('btn-switch-subs-tab')?.addEventListener('click', () => {
        document.getElementById('nav-subscriptions').click();
    });

    document.getElementById('btn-export-csv')?.addEventListener('click', () => {
        window.location.href = `${window.location.origin.includes('http') ? window.location.origin : 'http://127.0.0.1:8000'}/api/export/csv`;
    });
}

// REFRESH DASHBOARD METRICS & CHARTS
async function refreshDashboard() {
    try {
        const summary = await AuraFinanceAPI.getSummary();

        document.getElementById('kpi-net-balance').textContent = `$${summary.net_balance.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
        document.getElementById('kpi-income').textContent = `$${summary.total_income.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
        document.getElementById('kpi-expense').textContent = `$${summary.total_expense.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
        document.getElementById('kpi-total-saved').textContent = `$${summary.total_saved.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;

        // Health Score Ring update
        const healthScoreVal = document.getElementById('health-score-val');
        const scoreStrokeFill = document.getElementById('score-stroke-fill');
        const healthTipsList = document.getElementById('health-tips-list');

        if (healthScoreVal && scoreStrokeFill) {
            const score = summary.health_score || 0;
            healthScoreVal.textContent = score;
            scoreStrokeFill.setAttribute('stroke-dasharray', `${score}, 100`);

            if (score >= 80) scoreStrokeFill.style.stroke = "var(--success-green)";
            else if (score >= 60) scoreStrokeFill.style.stroke = "var(--warning-amber)";
            else scoreStrokeFill.style.stroke = "var(--danger-red)";
        }

        if (healthTipsList && summary.health_tips) {
            healthTipsList.innerHTML = summary.health_tips.map(tip => `<li>${escapeHtml(tip)}</li>`).join('');
        }

        // Render Charts
        if (window.ExpenseFlowCharts) {
            window.ExpenseFlowCharts.renderCategoryChart(summary.expenses_by_category || []);
            window.ExpenseFlowCharts.renderTrendChart(summary.daily_trends || []);
        }

        // Render Upcoming Subscriptions list
        const subs = await AuraFinanceAPI.getSubscriptions();
        renderUpcomingSubsWidget(subs.filter(s => s.is_active));

    } catch (err) {
        console.error("Error refreshing dashboard:", err);
    }
}

function renderUpcomingSubsWidget(subs) {
    const container = document.getElementById('upcoming-subs-list');
    if (!container) return;

    if (subs.length === 0) {
        container.innerHTML = `<p class="text-muted" style="grid-column: 1/-1; text-align: center; padding: 20px;">No hay suscripciones activas registradas.</p>`;
        return;
    }

    const today = new Date();
    container.innerHTML = subs.slice(0, 3).map(sub => {
        const nextDate = new Date(sub.next_billing_date);
        const diffTime = nextDate - today;
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

        let badgeClass = 'normal';
        let badgeText = `En ${diffDays} días`;
        if (diffDays <= 0) {
            badgeClass = 'urgent';
            badgeText = 'Cobro hoy';
        } else if (diffDays <= 5) {
            badgeClass = 'urgent';
            badgeText = `Pronto (${diffDays}d)`;
        }

        return `
            <div class="upcoming-sub-item">
                <div class="sub-item-info">
                    <div class="sub-avatar">
                        <i class="fa-solid fa-credit-card"></i>
                    </div>
                    <div>
                        <div class="sub-item-title">${escapeHtml(sub.name)}</div>
                        <div class="sub-item-date">${sub.next_billing_date}</div>
                    </div>
                </div>
                <div class="sub-item-cost">
                    <div class="sub-price">$${sub.cost.toFixed(2)}</div>
                    <span class="badge-days ${badgeClass}">${badgeText}</span>
                </div>
            </div>
        `;
    }).join('');
}

// REFRESH SAVINGS GOALS TAB
async function refreshSavingsGoals() {
    try {
        const goals = await AuraFinanceAPI.getSavingsGoals();
        renderSavingsGoalsGrid(goals);
    } catch (err) {
        console.error("Error refreshing savings goals:", err);
    }
}

function renderSavingsGoalsGrid(goals) {
    const container = document.getElementById('goals-grid-container');
    if (!container) return;

    if (goals.length === 0) {
        container.innerHTML = `<p class="text-muted" style="grid-column: 1/-1; text-align: center; padding: 40px;">No hay metas de ahorro activas.</p>`;
        return;
    }

    container.innerHTML = goals.map(g => {
        const pct = g.percentage;
        let fillClass = 'safe';
        if (pct >= 100) fillClass = 'safe';
        else if (pct >= 50) fillClass = 'warning';

        return `
            <div class="goal-card">
                <div class="goal-card-header">
                    <div>
                        <div class="goal-title">${escapeHtml(g.title)}</div>
                        <div class="goal-cat"><i class="fa-solid fa-tag"></i> ${escapeHtml(g.category)}</div>
                    </div>
                    <div class="goal-icon-box">
                        <i class="fa-solid fa-vault"></i>
                    </div>
                </div>

                <div class="goal-amounts">
                    <span>Ahorrado: <strong style="color: var(--primary-blue);">$${g.current_amount.toFixed(2)}</strong></span>
                    <span>Meta: <strong style="color: var(--text-primary);">$${g.target_amount.toFixed(2)}</strong></span>
                </div>

                <div class="progress-bar-bg">
                    <div class="progress-bar-fill ${fillClass}" style="width: ${Math.min(pct, 100)}%;"></div>
                </div>
                
                <div style="display: flex; justify-content: space-between; font-size: 12px; margin-top: 6px;">
                    <span class="text-muted">Progreso</span>
                    <span style="font-weight: 700; color: var(--success-green);">${pct}%</span>
                </div>

                <div class="goal-footer-actions">
                    <button class="btn btn-secondary" style="font-size: 12px; padding: 6px 12px;" onclick="openDepositModal(${g.id}, '${escapeHtml(g.title)}')">
                        <i class="fa-solid fa-plus"></i> Abonar
                    </button>
                    <button class="btn-icon-del" onclick="handleDeleteGoal(${g.id})" title="Eliminar Meta">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

function openDepositModal(id, title) {
    document.getElementById('deposit-goal-id').value = id;
    document.getElementById('deposit-goal-name').textContent = title;
    document.getElementById('modal-deposit-goal').classList.add('active');
}
window.openDepositModal = openDepositModal;

async function handleDeleteGoal(id) {
    if (confirm("¿Estás seguro de eliminar esta meta de ahorro?")) {
        await AuraFinanceAPI.deleteSavingsGoal(id);
        await refreshSavingsGoals();
        await refreshDashboard();
    }
}
window.handleDeleteGoal = handleDeleteGoal;

// REFRESH TRANSACTIONS TAB
async function refreshTransactions() {
    try {
        const search = document.getElementById('tx-search-input')?.value || "";
        const type = document.getElementById('tx-filter-type')?.value || "";
        const category = document.getElementById('tx-filter-category')?.value || "";
        const startDate = document.getElementById('tx-filter-start')?.value || "";
        const endDate = document.getElementById('tx-filter-end')?.value || "";

        const txs = await AuraFinanceAPI.getTransactions(type, category, search, startDate, endDate);
        renderTransactionsTable(txs);
    } catch (err) {
        console.error("Error refreshing transactions:", err);
    }
}

function renderTransactionsTable(txs) {
    const tbody = document.getElementById('tx-table-body');
    if (!tbody) return;

    if (txs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 30px;">No se encontraron transacciones.</td></tr>`;
        return;
    }

    tbody.innerHTML = txs.map(tx => {
        const isExpense = tx.type === 'expense';
        const typeBadge = isExpense 
            ? `<span class="badge-type expense"><i class="fa-solid fa-arrow-down"></i> Gasto</span>`
            : `<span class="badge-type income"><i class="fa-solid fa-arrow-up"></i> Ingreso</span>`;
        const amountDisplay = isExpense 
            ? `<span style="color: var(--danger-red); font-weight: 700;">-$${tx.amount.toFixed(2)}</span>`
            : `<span style="color: var(--success-green); font-weight: 700;">+$${tx.amount.toFixed(2)}</span>`;

        return `
            <tr>
                <td>
                    <div style="font-weight: 600;">${escapeHtml(tx.title)}</div>
                    ${tx.notes ? `<div style="font-size: 11px; color: var(--text-muted);">${escapeHtml(tx.notes)}</div>` : ''}
                </td>
                <td>${typeBadge}</td>
                <td><span class="badge-cat">${escapeHtml(tx.category)}</span></td>
                <td style="color: var(--text-muted); font-size: 13px;">${tx.date}</td>
                <td><span style="font-size: 12px; color: var(--text-secondary);"><i class="fa-solid fa-credit-card"></i> ${escapeHtml(tx.payment_method || 'Tarjeta')}</span></td>
                <td>${amountDisplay}</td>
                <td>
                    <button class="btn-icon-del" onclick="handleDeleteTransaction(${tx.id})" title="Eliminar">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

async function handleDeleteTransaction(id) {
    if (confirm("¿Estás seguro de eliminar esta transacción?")) {
        await AuraFinanceAPI.deleteTransaction(id);
        await refreshTransactions();
        await refreshDashboard();
        await refreshBudgets();
    }
}
window.handleDeleteTransaction = handleDeleteTransaction;

// REFRESH SUBSCRIPTIONS TAB
async function refreshSubscriptions() {
    try {
        const subs = await AuraFinanceAPI.getSubscriptions();
        renderSubscriptionsGrid(subs);
    } catch (err) {
        console.error("Error refreshing subscriptions:", err);
    }
}

function renderSubscriptionsGrid(subs) {
    const container = document.getElementById('subs-grid-container');
    if (!container) return;

    if (subs.length === 0) {
        container.innerHTML = `<p class="text-muted" style="grid-column: 1/-1; text-align: center; padding: 40px;">No hay suscripciones registradas.</p>`;
        return;
    }

    container.innerHTML = subs.map(s => {
        const isMonthly = s.billing_cycle === 'monthly';
        const cycleText = isMonthly ? '/mes' : '/año';

        return `
            <div class="sub-card">
                <div class="sub-card-top">
                    <div class="sub-icon-box">
                        <i class="fa-solid fa-bolt"></i>
                    </div>
                    <div class="sub-card-cost">
                        <div class="sub-cost-amount">$${s.cost.toFixed(2)}</div>
                        <div class="sub-cycle-tag">${cycleText}</div>
                    </div>
                </div>
                <div class="sub-name">${escapeHtml(s.name)}</div>
                <div class="sub-category"><i class="fa-solid fa-tag"></i> ${escapeHtml(s.category)}</div>
                
                <div style="margin-bottom: 14px; font-size: 12px; color: var(--text-muted);">
                    <i class="fa-regular fa-calendar-check"></i> Próximo pago: <strong style="color: var(--text-secondary);">${s.next_billing_date}</strong>
                </div>

                <div class="sub-card-footer">
                    <label class="toggle-switch" title="Activar/Pausar Suscripción">
                        <input type="checkbox" ${s.is_active ? 'checked' : ''} onchange="handleToggleSub(${s.id})">
                        <span class="slider"></span>
                    </label>
                    <button class="btn-icon-del" onclick="handleDeleteSub(${s.id})" title="Eliminar Suscripción">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

async function handleToggleSub(id) {
    await AuraFinanceAPI.toggleSubscription(id);
    await refreshSubscriptions();
    await refreshDashboard();
}
window.handleToggleSub = handleToggleSub;

async function handleDeleteSub(id) {
    if (confirm("¿Estás seguro de eliminar esta suscripción?")) {
        await AuraFinanceAPI.deleteSubscription(id);
        await refreshSubscriptions();
        await refreshDashboard();
    }
}
window.handleDeleteSub = handleDeleteSub;

// REFRESH BUDGETS TAB
async function refreshBudgets() {
    try {
        const budgets = await AuraFinanceAPI.getBudgets();
        renderBudgetsGrid(budgets);
    } catch (err) {
        console.error("Error refreshing budgets:", err);
    }
}

function renderBudgetsGrid(budgets) {
    const container = document.getElementById('budgets-grid-container');
    if (!container) return;

    container.innerHTML = budgets.map(b => {
        const pct = b.percentage;
        let fillClass = 'safe';
        if (pct >= 100) fillClass = 'danger';
        else if (pct >= 80) fillClass = 'warning';

        return `
            <div class="budget-card">
                <div class="budget-header">
                    <div class="budget-cat-name"><i class="fa-solid fa-folder-open" style="color: var(--primary-blue); margin-right: 8px;"></i> ${escapeHtml(b.category)}</div>
                    <button class="btn-text" onclick="handleEditBudget('${escapeHtml(b.category)}', ${b.monthly_limit})">Editar Límite</button>
                </div>
                <div class="budget-stats">
                    <span class="text-muted">Gastado: <strong style="color: var(--text-primary);">$${b.spent.toFixed(2)}</strong></span>
                    <span class="text-muted">Límite: <strong style="color: var(--text-primary);">$${b.monthly_limit.toFixed(2)}</strong></span>
                </div>
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill ${fillClass}" style="width: ${Math.min(pct, 100)}%;"></div>
                </div>
                <div style="display: flex; justify-content: space-between; margin-top: 8px; font-size: 12px;">
                    <span class="text-muted">Consumo del mes</span>
                    <span style="font-weight: 700; color: ${pct >= 100 ? 'var(--danger-red)' : 'var(--text-secondary)'};">${pct}%</span>
                </div>
            </div>
        `;
    }).join('');
}

async function handleEditBudget(category, currentLimit) {
    const newLimit = prompt(`Nuevo límite de presupuesto mensual para "${category}":`, currentLimit);
    if (newLimit !== null && !isNaN(parseFloat(newLimit)) && parseFloat(newLimit) >= 0) {
        await AuraFinanceAPI.updateBudget(category, parseFloat(newLimit));
        await refreshBudgets();
    }
}
window.handleEditBudget = handleEditBudget;

// CALCULATOR MODULE
function setupCalculator() {
    const btnCalc = document.getElementById('btn-calculate');
    const btnAddTx = document.getElementById('btn-add-calc-tx');

    btnCalc?.addEventListener('click', () => {
        const title = document.getElementById('calc-title').value || "Compra a Plazos";
        const P = parseFloat(document.getElementById('calc-amount').value);
        const n = parseInt(document.getElementById('calc-months').value);
        const iPercent = parseFloat(document.getElementById('calc-interest').value);

        if (isNaN(P) || isNaN(n) || P <= 0 || n <= 0) {
            alert("Por favor ingresa un monto y número de cuotas válido.");
            return;
        }

        const i = (iPercent || 0) / 100.0;
        let monthlyPayment = 0;
        let totalPay = 0;
        let totalInterest = 0;

        if (i === 0) {
            monthlyPayment = P / n;
            totalPay = P;
            totalInterest = 0;
        } else {
            // Amortización sistema francés: PMT = P * [i / (1 - (1+i)^-n)]
            monthlyPayment = P * (i / (1 - Math.pow(1 + i, -n)));
            totalPay = monthlyPayment * n;
            totalInterest = totalPay - P;
        }

        document.getElementById('res-monthly-payment').textContent = `$${monthlyPayment.toFixed(2)}`;
        document.getElementById('res-total-interest').textContent = `$${totalInterest.toFixed(2)}`;
        document.getElementById('res-total-pay').textContent = `$${totalPay.toFixed(2)}`;

        currentCalcInstallment = {
            title: `Cuota 1/${n}: ${title}`,
            amount: parseFloat(monthlyPayment.toFixed(2)),
            type: "expense",
            category: document.getElementById('calc-category').value,
            date: new Date().toISOString().split('T')[0],
            payment_method: "Tarjeta Crédito",
            notes: `Financiado a ${n} meses (${iPercent}% int/mes)`
        };

        btnAddTx.disabled = false;
    });

    btnAddTx?.addEventListener('click', async () => {
        if (currentCalcInstallment) {
            await AuraFinanceAPI.createTransaction(currentCalcInstallment);
            alert("¡Primera cuota registrada exitosamente como gasto!");
            await refreshTransactions();
            await refreshDashboard();
            await refreshBudgets();
        }
    });
}

// MODALS HANDLING
function setupModals() {
    const modalTx = document.getElementById('modal-transaction');
    const modalSub = document.getElementById('modal-subscription');
    const modalGoal = document.getElementById('modal-savings-goal');
    const modalDeposit = document.getElementById('modal-deposit-goal');
    const modalImport = document.getElementById('modal-import-json');

    document.getElementById('btn-open-tx-modal')?.addEventListener('click', () => modalTx.classList.add('active'));
    document.getElementById('btn-open-sub-modal')?.addEventListener('click', () => modalSub.classList.add('active'));
    document.getElementById('btn-open-goal-modal')?.addEventListener('click', () => modalGoal.classList.add('active'));
    document.getElementById('btn-open-import-modal')?.addEventListener('click', () => modalImport.classList.add('active'));

    document.querySelectorAll('.close-modal').forEach(btn => {
        btn.addEventListener('click', () => {
            [modalTx, modalSub, modalGoal, modalDeposit, modalImport].forEach(m => m?.classList.remove('active'));
        });
    });

    [modalTx, modalSub, modalGoal, modalDeposit, modalImport].forEach(modal => {
        modal?.addEventListener('click', (e) => {
            if (e.target === modal) modal.classList.remove('active');
        });
    });
}

// SEARCH AND FILTERS LISTENER
function setupFilters() {
    const searchInput = document.getElementById('tx-search-input');
    const filterType = document.getElementById('tx-filter-type');
    const filterCategory = document.getElementById('tx-filter-category');
    const filterStart = document.getElementById('tx-filter-start');
    const filterEnd = document.getElementById('tx-filter-end');

    let debounceTimer;
    searchInput?.addEventListener('input', () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(refreshTransactions, 300);
    });

    [filterType, filterCategory, filterStart, filterEnd].forEach(el => {
        el?.addEventListener('change', refreshTransactions);
    });
}

// FORMS SUBMISSION
function setupForms() {
    // Transaction Form
    document.getElementById('form-transaction')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const payload = {
            title: document.getElementById('tx-title').value,
            amount: parseFloat(document.getElementById('tx-amount').value),
            type: document.getElementById('tx-type').value,
            category: document.getElementById('tx-category').value,
            date: document.getElementById('tx-date').value,
            payment_method: document.getElementById('tx-payment').value,
            notes: document.getElementById('tx-notes').value
        };

        await AuraFinanceAPI.createTransaction(payload);
        document.getElementById('modal-transaction').classList.remove('active');
        e.target.reset();
        
        document.getElementById('tx-date').value = new Date().toISOString().split('T')[0];

        await refreshDashboard();
        await refreshTransactions();
        await refreshBudgets();
    });

    // Savings Goal Form
    document.getElementById('form-savings-goal')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const payload = {
            title: document.getElementById('goal-title').value,
            target_amount: parseFloat(document.getElementById('goal-target').value),
            current_amount: parseFloat(document.getElementById('goal-initial').value || 0),
            category: document.getElementById('goal-category').value || "General",
            target_date: document.getElementById('goal-date').value
        };

        await AuraFinanceAPI.createSavingsGoal(payload);
        document.getElementById('modal-savings-goal').classList.remove('active');
        e.target.reset();
        document.getElementById('goal-date').value = new Date().toISOString().split('T')[0];

        await refreshSavingsGoals();
        await refreshDashboard();
    });

    // Deposit Goal Form
    document.getElementById('form-deposit-goal')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const id = parseInt(document.getElementById('deposit-goal-id').value);
        const amount = parseFloat(document.getElementById('deposit-amount').value);

        if (id && amount > 0) {
            await AuraFinanceAPI.depositToSavingsGoal(id, amount);
            document.getElementById('modal-deposit-goal').classList.remove('active');
            e.target.reset();

            await refreshSavingsGoals();
            await refreshDashboard();
            await refreshTransactions();
        }
    });

    // Subscription Form
    document.getElementById('form-subscription')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const payload = {
            name: document.getElementById('sub-name').value,
            cost: parseFloat(document.getElementById('sub-cost').value),
            billing_cycle: document.getElementById('sub-cycle').value,
            category: document.getElementById('sub-category').value,
            next_billing_date: document.getElementById('sub-date').value
        };

        await AuraFinanceAPI.createSubscription(payload);
        document.getElementById('modal-subscription').classList.remove('active');
        e.target.reset();

        document.getElementById('sub-date').value = new Date().toISOString().split('T')[0];

        await refreshSubscriptions();
        await refreshDashboard();
    });

    // Bulk Import JSON Form
    document.getElementById('form-import-json')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const rawText = document.getElementById('import-json-area').value;
        try {
            const data = JSON.parse(rawText);
            const arrayToImport = Array.isArray(data) ? data : (data.transactions || []);
            const res = await AuraFinanceAPI.importJSON(arrayToImport);
            alert(`¡Éxito! ${res.message}`);
            document.getElementById('modal-import-json').classList.remove('active');
            e.target.reset();

            await refreshTransactions();
            await refreshDashboard();
            await refreshBudgets();
        } catch (err) {
            alert("Error al procesar JSON. Verifica el formato.");
        }
    });
}

function escapeHtml(text) {
    if (!text) return "";
    return text.replace(/[&<>"']/g, (m) => {
        return {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        }[m];
    });
}
