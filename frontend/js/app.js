/**
 * ExpenseFlow — controlador de la interfaz.
 * Pantalla principal: "¿Cuánto me queda este mes y en qué se me está yendo?"
 */

const Charts = window.ExpenseFlowCharts;
let currentCalcInstallment = null;

// ---------- Formato ----------
// La moneda es de la cuenta (COP por defecto). Cambiarla solo cambia cómo se muestran los montos.
const CURRENCY_DECIMALS = { COP: 0, USD: 2, EUR: 2, MXN: 2 };
let currency = 'COP';
let moneyFmt, shortFmt;
function setCurrency(code) {
    currency = CURRENCY_DECIMALS[code] !== undefined ? code : 'COP';
    const decimals = CURRENCY_DECIMALS[currency];
    // COP se escribe "$ 4.800.000"; las demás llevan su símbolo (US$, €, MX$) para no confundirlas
    const display = currency === 'COP' ? 'narrowSymbol' : 'symbol';
    moneyFmt = new Intl.NumberFormat('es-CO', { style: 'currency', currency, currencyDisplay: display, minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    shortFmt = new Intl.NumberFormat('es-CO', { style: 'currency', currency, currencyDisplay: display, notation: 'compact', maximumFractionDigits: 1 });
    document.querySelectorAll('#user-currency').forEach(sel => { sel.value = currency; });
}
setCurrency('COP');
const money = (v) => moneyFmt.format(v || 0);
const moneySigned = (v) => `${v < 0 ? '−' : ''}${moneyFmt.format(Math.abs(v || 0))}`;
const moneyShort = (v) => shortFmt.format(v || 0);

// Últimas filas cargadas, para abrir el formulario de edición con sus datos
const cache = { tx: new Map(), subs: new Map(), goals: new Map() };
let txPage = 1;
const TX_PAGE_SIZE = 25;
let alertsShown = false;
const pctFmt = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 1 });
const pct = (v) => `${pctFmt.format(v || 0)} %`;
const dateFmt = new Intl.DateTimeFormat('es-CO', { day: 'numeric', month: 'short' });
const monthFmt = new Intl.DateTimeFormat('es-CO', { month: 'long', year: 'numeric' });

function parseDate(iso) {
    const [y, m, d] = iso.split('-').map(Number);
    return new Date(y, m - 1, d);
}
const shortDate = (iso) => dateFmt.format(parseDate(iso)).replace('.', '');
function daysUntil(iso) {
    const today = parseDate(localToday());
    return Math.round((parseDate(iso) - today) / 86400000);
}
function capitalize(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

function escapeHtml(text) {
    if (text === null || text === undefined) return "";
    return String(text).replace(/[&<>"']/g, (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]));
}

// Fecha local (YYYY-MM-DD); toISOString() usa UTC y adelanta el día por la noche en Colombia
function localToday() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// ---------- Avisos, estados y diálogos ----------
function toast(message, kind = 'info') {
    const box = document.getElementById('toasts');
    const item = document.createElement('div');
    item.className = `toast${kind === 'error' ? ' error' : ''}`;
    item.textContent = message;
    box.appendChild(item);
    setTimeout(() => item.remove(), kind === 'error' ? 6000 : 3500);
}

const loadingHtml = `<div aria-busy="true"><span class="skeleton"></span><span class="skeleton w60"></span><span class="skeleton w40"></span></div>`;
function emptyHtml(title, text, action) {
    return `<div class="state"><strong>${escapeHtml(title)}</strong>${escapeHtml(text)}${action ? `<div><button type="button" class="btn btn-secondary" data-open="${action.modal}">${escapeHtml(action.label)}</button></div>` : ''}</div>`;
}
function errorHtml(text) {
    return `<div class="state" role="alert"><strong>No se pudo cargar</strong>${escapeHtml(text)} <button type="button" class="link-btn" data-retry>Reintentar</button></div>`;
}

function openModal(id) {
    const dlg = document.getElementById(id);
    if (dlg && !dlg.open) dlg.showModal();
}
function closeModal(dlg) { if (dlg?.open) dlg.close(); }

/** Confirmación accesible en lugar de confirm(). Devuelve una promesa con true/false. */
function confirmAction(title, text, okLabel = 'Eliminar') {
    const dlg = document.getElementById('modal-confirm');
    document.getElementById('confirm-title').textContent = title;
    document.getElementById('confirm-text').textContent = text;
    document.getElementById('confirm-ok').textContent = okLabel;
    dlg.returnValue = '';
    dlg.showModal();
    return new Promise(resolve => dlg.addEventListener('close', () => resolve(dlg.returnValue === 'ok'), { once: true }));
}

// ---------- Arranque ----------
document.addEventListener('DOMContentLoaded', initApp);

async function initApp() {
    setupNavigation();
    setupModals();
    setupFilters();
    setupForms();
    setupCalculator();
    setupAuth();
    setupTheme();
    setupCurrency();

    await checkServerStatus();
    await loadCategories();

    const user = await ExpenseFlowAPI.me();
    if (!user) {
        showAuthScreen();
        return;
    }
    await startSession(user);
}

async function startSession(user) {
    document.getElementById('auth-screen').hidden = true;
    document.getElementById('current-user-name').textContent = user.name;
    setCurrency(user.currency);
    resetDates();
    await refreshAll();
}

function resetDates() {
    const today = localToday();
    ['tx-date', 'sub-date', 'goal-date'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = today;
    });
}

async function refreshAll() {
    await Promise.all([refreshDashboard(), refreshTransactions(), refreshBudgets(), refreshSavingsGoals(), refreshSubscriptions()]);
}

async function checkServerStatus() {
    const text = document.getElementById('api-status-text');
    const dot = document.getElementById('status-dot');
    const res = await ExpenseFlowAPI.checkHealth();
    if (res.status === "online") {
        text.textContent = res.database === "postgresql" ? "Conectado · PostgreSQL" : "Conectado · SQLite";
        dot.className = "status-dot online";
    } else {
        text.textContent = "Sin conexión con el servidor";
        dot.className = "status-dot offline";
    }
}

// ---------- Navegación ----------
function showTab(name) {
    document.querySelectorAll('.tab').forEach(t => { t.hidden = t.id !== `tab-${name}`; });
    document.querySelectorAll('.nav-item').forEach(n => {
        if (n.dataset.tab === name) n.setAttribute('aria-current', 'page');
        else n.removeAttribute('aria-current');
    });
    setMenu(false);
    document.getElementById('main').focus({ preventScroll: true });
    window.scrollTo(0, 0);

    if (name === 'dashboard') refreshDashboard();
    if (name === 'savings') refreshSavingsGoals();
    if (name === 'transactions') refreshTransactions();
    if (name === 'subscriptions') refreshSubscriptions();
    if (name === 'budgets') refreshBudgets();
}

function setMenu(open) {
    document.getElementById('sidebar').classList.toggle('open', open);
    document.getElementById('btn-menu').setAttribute('aria-expanded', String(open));
    document.getElementById('btn-menu').textContent = open ? 'Cerrar' : 'Menú';
}

function setupNavigation() {
    document.querySelectorAll('.nav-item').forEach(item =>
        item.addEventListener('click', () => showTab(item.dataset.tab)));

    document.getElementById('btn-menu').addEventListener('click', () =>
        setMenu(!document.getElementById('sidebar').classList.contains('open')));

    document.getElementById('btn-export-csv').addEventListener('click', () => {
        window.location.href = `${API_BASE_URL}/api/export/csv`;
    });
}

function setupTheme() {
    const btn = document.getElementById('btn-theme');
    const label = () => {
        btn.textContent = document.documentElement.dataset.theme === 'dark' ? 'Modo claro' : 'Modo oscuro';
    };
    label();
    btn.addEventListener('click', () => {
        const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
        document.documentElement.dataset.theme = next;
        try { localStorage.setItem('ef-theme', next); } catch (e) { /* sin almacenamiento */ }
        label();
    });
}

// ---------- Resumen ----------
async function refreshDashboard() {
    const ids = ['category-chart', 'near-budgets', 'trend-chart', 'upcoming-subs-list'];
    ids.forEach(id => { const el = document.getElementById(id); if (!el.innerHTML.trim()) el.innerHTML = loadingHtml; });

    let summary, budgets, subs;
    try {
        [summary, budgets, subs] = await Promise.all([
            ExpenseFlowAPI.getSummary(), ExpenseFlowAPI.getBudgets(), ExpenseFlowAPI.getSubscriptions()
        ]);
    } catch (err) {
        document.getElementById('dashboard-finding').textContent = 'No pudimos cargar tu resumen.';
        ids.forEach(id => { document.getElementById(id).innerHTML = errorHtml('Revisa tu conexión.'); });
        return;
    }

    const monthName = capitalize(monthFmt.format(parseDate(`${summary.month}-01`)));
    document.getElementById('title-dashboard').textContent = monthName;

    // Cifra principal: lo que queda del mes
    const net = document.getElementById('kpi-net-balance');
    net.textContent = moneySigned(summary.net_balance);
    net.classList.toggle('negative', summary.net_balance < 0);
    document.getElementById('hero-label').textContent = summary.net_balance < 0 ? 'Este mes vas en rojo por' : 'Te queda este mes';
    document.getElementById('kpi-income').textContent = money(summary.total_income);
    document.getElementById('kpi-expense').textContent = money(summary.total_expense);
    document.getElementById('kpi-total-saved').textContent = money(summary.total_saved);

    // Hallazgo del mes, junto al título
    document.getElementById('dashboard-finding').textContent = buildFinding(summary, budgets);

    // Salud financiera
    const score = summary.health_score ?? 0;
    document.getElementById('health-score-val').textContent = score;
    document.getElementById('health-score-meter').style.width = `${score}%`;
    document.getElementById('health-tips-list').innerHTML =
        (summary.health_tips || []).map(t => `<li>${escapeHtml(t)}</li>`).join('');

    // En qué se fue el dinero
    const cats = summary.expenses_by_category || [];
    const catBox = document.getElementById('category-chart');
    document.getElementById('cat-total').textContent = cats.length ? `${money(summary.total_expense)} en ${cats.length} categorías` : '';
    if (cats.length) {
        Charts.barList(catBox, cats.slice(0, 7).map(c => ({ label: c.category, value: c.total })), money);
    } else {
        catBox.innerHTML = emptyHtml('Aún no hay gastos este mes', 'Cuando registres uno, verás aquí en qué se va tu dinero.', { modal: 'modal-transaction', label: 'Registrar un gasto' });
    }

    // Gasto por día
    const trends = summary.daily_trends || [];
    const trendBox = document.getElementById('trend-chart');
    if (trends.length) {
        Charts.dailyBars(trendBox, trends, summary.month, moneyShort);
        const peak = trends.reduce((a, b) => (b.total > a.total ? b : a));
        document.getElementById('trend-caption').textContent = `El día de más gasto fue el ${shortDate(peak.date)}: ${money(peak.total)}`;
    } else {
        trendBox.innerHTML = emptyHtml('Sin gastos por día todavía', 'El gráfico se llena a medida que registras gastos.');
        document.getElementById('trend-caption').textContent = '';
    }

    renderNearBudgets(budgets);
    renderAlerts(budgets);
    renderUpcomingSubs(subs.filter(s => s.is_active));
}

function buildFinding(summary, budgets) {
    if (summary.total_income === 0 && summary.total_expense === 0) {
        return 'Todavía no hay movimientos este mes. Registra tu primer ingreso o gasto.';
    }
    if (summary.net_balance < 0) {
        return `Gastaste ${money(-summary.net_balance)} más de lo que entró este mes.`;
    }
    const over = budgets.filter(b => b.spent > b.monthly_limit);
    if (over.length) {
        const b = over[0];
        return `${b.category} ya pasó su límite por ${money(b.spent - b.monthly_limit)}.`;
    }
    const tight = [...budgets].sort((a, b) => b.percentage - a.percentage)[0];
    const today = new Date();
    const daysLeft = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate() - today.getDate();
    if (tight && tight.percentage >= 50) {
        return `${tight.category} va en ${pct(tight.percentage)} de su presupuesto y faltan ${daysLeft} días del mes.`;
    }
    const rate = summary.total_income > 0 ? Math.round((summary.net_balance / summary.total_income) * 100) : 0;
    return `Llevas guardado el ${rate} % de lo que entró este mes.`;
}

/** Avisos de presupuesto: pasado del límite, o en 80 % o más. Se muestran en el resumen y en Presupuestos. */
function renderAlerts(budgets) {
    const over = budgets.filter(b => b.spent > b.monthly_limit);
    const near = budgets.filter(b => b.spent <= b.monthly_limit && b.percentage >= 80);
    const items = [
        ...over.map(b => `<div class="alert over"><span><strong>${escapeHtml(b.category)}</strong> pasó su límite por ${money(b.spent - b.monthly_limit)}.</span><button type="button" class="link-btn" data-action="edit-budget" data-category="${escapeHtml(b.category)}" data-limit="${b.monthly_limit}">Cambiar límite</button></div>`),
        ...near.map(b => `<div class="alert"><span><strong>${escapeHtml(b.category)}</strong> va en ${pct(b.percentage)}: quedan ${money(b.monthly_limit - b.spent)}.</span><button type="button" class="link-btn" data-goto="budgets">Ver presupuestos</button></div>`),
    ].join('');
    ['budget-alerts', 'budget-alerts-tab'].forEach(id => {
        const box = document.getElementById(id);
        box.innerHTML = items;
        box.hidden = !items;
    });
    if (!alertsShown && over.length) {
        alertsShown = true;
        toast(over.length === 1 ? `${over[0].category} pasó su presupuesto del mes` : `${over.length} presupuestos pasaron su límite este mes`, 'error');
    }
}

function renderNearBudgets(budgets) {
    const box = document.getElementById('near-budgets');
    const list = [...budgets].filter(b => b.spent > 0).sort((a, b) => b.percentage - a.percentage).slice(0, 3);
    if (!list.length) {
        box.innerHTML = emptyHtml('Ningún presupuesto en uso', 'Los gastos de este mes todavía no tocan tus límites.');
        return;
    }
    box.innerHTML = `<ul class="progress-list">${list.map(b => budgetItem(b, false)).join('')}</ul>`;
}

function renderUpcomingSubs(subs) {
    const box = document.getElementById('upcoming-subs-list');
    if (!subs.length) {
        box.innerHTML = emptyHtml('Sin cobros próximos', 'No tienes suscripciones activas.', { modal: 'modal-subscription', label: 'Añadir suscripción' });
        return;
    }
    box.innerHTML = `<ul class="rows rows-2">${subs.slice(0, 4).map(s => `
        <li>
            <div>
                <div class="row-title">${escapeHtml(s.name)}</div>
                <div class="row-sub">${dueLabel(s.next_billing_date)}</div>
            </div>
            <div class="row-figure">${money(s.cost)}<div class="row-sub">${s.billing_cycle === 'monthly' ? 'al mes' : 'al año'}</div></div>
        </li>`).join('')}</ul>`;
}

function dueLabel(iso) {
    const d = daysUntil(iso);
    if (d < 0) return `Venció el ${shortDate(iso)}`;
    if (d === 0) return 'Se cobra hoy';
    if (d === 1) return 'Se cobra mañana';
    return `En ${d} días · ${shortDate(iso)}`;
}

// ---------- Movimientos ----------
async function refreshTransactions() {
    const tbody = document.getElementById('tx-table-body');
    const summary = document.getElementById('tx-summary');
    try {
        const page = await ExpenseFlowAPI.getTransactions(
            document.getElementById('tx-filter-type').value,
            document.getElementById('tx-filter-category').value,
            document.getElementById('tx-search-input').value.trim(),
            document.getElementById('tx-filter-start').value,
            document.getElementById('tx-filter-end').value,
            txPage, TX_PAGE_SIZE,
        );
        // Si se borró lo último de una página, volver a la anterior
        if (!page.items.length && txPage > 1) {
            txPage -= 1;
            return refreshTransactions();
        }
        cache.tx = new Map(page.items.map(t => [t.id, t]));
        renderTransactionsTable(page.items);
        summary.innerHTML = page.total
            ? `${page.total} ${page.total === 1 ? 'movimiento' : 'movimientos'} · entraron <strong>${money(page.income_total)}</strong> · salieron <strong>${money(page.expense_total)}</strong>`
            : '';
        renderPager(page);
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="6">${errorHtml('Revisa tu conexión.')}</td></tr>`;
    }
}

function renderPager(page) {
    const pages = Math.max(1, Math.ceil(page.total / page.page_size));
    const pager = document.getElementById('tx-pager');
    pager.hidden = pages <= 1;
    const first = (page.page - 1) * page.page_size + 1;
    const last = Math.min(page.page * page.page_size, page.total);
    document.getElementById('tx-page-info').textContent = `${first}–${last} de ${page.total}`;
    document.getElementById('tx-prev').disabled = page.page <= 1;
    document.getElementById('tx-next').disabled = page.page >= pages;
}

function hasTxFilters() {
    return ['tx-search-input', 'tx-filter-type', 'tx-filter-category', 'tx-filter-start', 'tx-filter-end']
        .some(id => document.getElementById(id).value);
}

function renderTransactionsTable(txs) {
    const tbody = document.getElementById('tx-table-body');
    if (!txs.length) {
        const content = hasTxFilters()
            ? emptyHtml('Nada coincide con los filtros', 'Prueba con otras fechas o quita la búsqueda.')
            : emptyHtml('Aún no hay movimientos', 'Registra tu primer ingreso o gasto para empezar.', { modal: 'modal-transaction', label: 'Registrar movimiento' });
        tbody.innerHTML = `<tr><td colspan="6">${content}</td></tr>`;
        return;
    }
    tbody.innerHTML = txs.map(tx => {
        const income = tx.type === 'income';
        return `<tr>
            <td>
                <div class="row-title">${escapeHtml(tx.title)}</div>
                ${tx.notes ? `<div class="row-sub">${escapeHtml(tx.notes)}</div>` : ''}
            </td>
            <td class="muted">${escapeHtml(tx.category)}</td>
            <td class="nowrap num">${shortDate(tx.date)}</td>
            <td class="muted">${escapeHtml(tx.payment_method || '—')}</td>
            <td class="right money ${income ? 'pos' : ''}">${income ? '+' : '−'}${money(tx.amount)}</td>
            <td class="right nowrap">
                <button type="button" class="link-btn" data-action="edit-tx" data-id="${tx.id}" aria-label="Editar ${escapeHtml(tx.title)}">Editar</button>
                <button type="button" class="link-btn danger" data-action="delete-tx" data-id="${tx.id}" data-title="${escapeHtml(tx.title)}" aria-label="Eliminar ${escapeHtml(tx.title)}">Eliminar</button>
            </td>
        </tr>`;
    }).join('');
}

async function handleDeleteTransaction(id, title) {
    if (!await confirmAction('¿Eliminar este movimiento?', `"${title}" se borrará y no se puede deshacer.`)) return;
    try {
        await ExpenseFlowAPI.deleteTransaction(id);
        toast('Movimiento eliminado');
        await refreshAll();
    } catch (err) { toast(err.message, 'error'); }
}

// ---------- Presupuestos ----------
function budgetItem(b, withAction) {
    const over = b.spent > b.monthly_limit;
    const left = b.monthly_limit - b.spent;
    const state = over
        ? `<span class="pill negative">Pasado por ${money(-left)}</span>`
        : b.percentage >= 80 ? `<span class="pill warning">Quedan ${money(left)}</span>`
        : `<span class="muted">Quedan ${money(left)}</span>`;
    const figure = `<span class="${b.spent === 0 ? 'muted' : ''}">${money(b.spent)}</span> <span class="muted" style="font-weight:400">de ${money(b.monthly_limit)}</span>`;
    return `<li class="progress-item">
        <div class="row-title">${escapeHtml(b.category)}</div>
        <div class="row-figure">${withAction ? figure : pct(b.percentage)}</div>
        <div class="meter${over ? ' over' : ''}" role="progressbar" aria-label="${escapeHtml(b.category)}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(b.percentage)}"><span style="width:${Math.min(b.percentage, 100)}%"></span></div>
        <div class="progress-meta">${state}${withAction ? `<button type="button" class="link-btn" data-action="edit-budget" data-category="${escapeHtml(b.category)}" data-limit="${b.monthly_limit}">Cambiar límite</button>` : `<span class="num">${figure}</span>`}</div>
    </li>`;
}

async function refreshBudgets() {
    const box = document.getElementById('budgets-grid-container');
    try {
        const budgets = await ExpenseFlowAPI.getBudgets();
        if (!budgets.length) {
            box.innerHTML = `<li>${emptyHtml('No tienes presupuestos', 'Se crean al registrarte; puedes definir uno al editar una categoría.')}</li>`;
            return;
        }
        renderAlerts(budgets);
        const sorted = [...budgets].sort((a, b) => b.percentage - a.percentage);
        box.innerHTML = sorted.map(b => budgetItem(b, true)).join('');
        const totalLimit = budgets.reduce((s, b) => s + b.monthly_limit, 0);
        const totalSpent = budgets.reduce((s, b) => s + b.spent, 0);
        const over = budgets.filter(b => b.spent > b.monthly_limit).length;
        document.getElementById('budgets-summary').textContent =
            `Este mes llevas ${money(totalSpent)} de ${money(totalLimit)} presupuestados` + (over ? ` · ${over} ${over === 1 ? 'categoría pasada' : 'categorías pasadas'} del límite.` : '.');
    } catch (err) {
        box.innerHTML = `<li>${errorHtml('Revisa tu conexión.')}</li>`;
    }
}

function openBudgetModal(category, limit) {
    document.getElementById('budget-category').value = category;
    document.getElementById('budget-category-name').textContent = category;
    document.getElementById('budget-limit').value = limit;
    openModal('modal-budget');
}

// ---------- Metas ----------
async function refreshSavingsGoals() {
    const box = document.getElementById('goals-grid-container');
    try {
        const goals = await ExpenseFlowAPI.getSavingsGoals();
        if (!goals.length) {
            box.innerHTML = `<li>${emptyHtml('Aún no tienes metas', 'Una meta te ayuda a apartar dinero para algo concreto: un viaje, un fondo de emergencia.', { modal: 'modal-savings-goal', label: 'Crear la primera' })}</li>`;
            document.getElementById('goals-summary').textContent = 'Dinero apartado para lo que quieres lograr.';
            return;
        }
        cache.goals = new Map(goals.map(g => [g.id, g]));
        box.innerHTML = goals.map(g => {
            const left = Math.max(g.target_amount - g.current_amount, 0);
            const done = left <= 0;
            const days = daysUntil(g.target_date);
            const when = days < 0 ? `La fecha pasó el ${shortDate(g.target_date)}` : `Para el ${shortDate(g.target_date)} (${days} días)`;
            return `<li class="progress-item">
                <div>
                    <div class="row-title">${escapeHtml(g.title)}</div>
                    <div class="row-sub">${escapeHtml(g.category)}</div>
                </div>
                <div class="row-figure">${money(g.current_amount)} <span class="muted" style="font-weight:400">de ${money(g.target_amount)}</span></div>
                <div class="meter" role="progressbar" aria-label="${escapeHtml(g.title)}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(g.percentage)}"><span style="width:${Math.min(g.percentage, 100)}%"></span></div>
                <div class="progress-meta">
                    <span>${done ? '<span class="pill positive">Meta cumplida</span>' : `Faltan ${money(left)} · ${when}`}</span>
                    <span class="progress-actions">
                        <button type="button" class="link-btn" data-action="edit-goal" data-id="${g.id}" aria-label="Editar ${escapeHtml(g.title)}">Editar</button>
                        ${done ? '' : `<button type="button" class="link-btn" data-action="deposit-goal" data-id="${g.id}" data-title="${escapeHtml(g.title)}" data-left="${left}">Abonar</button>`}
                        <button type="button" class="link-btn danger" data-action="delete-goal" data-id="${g.id}" data-title="${escapeHtml(g.title)}">Eliminar</button>
                    </span>
                </div>
            </li>`;
        }).join('');
        const saved = goals.reduce((s, g) => s + g.current_amount, 0);
        const target = goals.reduce((s, g) => s + g.target_amount, 0);
        document.getElementById('goals-summary').textContent = `Llevas ${money(saved)} de ${money(target)} en ${goals.length} ${goals.length === 1 ? 'meta' : 'metas'}.`;
    } catch (err) {
        box.innerHTML = `<li>${errorHtml('Revisa tu conexión.')}</li>`;
    }
}

function openDepositModal(id, title, left) {
    document.getElementById('deposit-goal-id').value = id;
    document.getElementById('deposit-goal-name').textContent = title;
    const input = document.getElementById('deposit-amount');
    input.max = left;
    document.getElementById('deposit-hint').textContent = `Le faltan ${money(left)} para completarse.`;
    openModal('modal-deposit-goal');
}

async function handleDeleteGoal(id, title) {
    if (!await confirmAction('¿Eliminar esta meta?', `"${title}" se borrará. Los abonos ya registrados se quedan en tus movimientos.`)) return;
    try {
        await ExpenseFlowAPI.deleteSavingsGoal(id);
        toast('Meta eliminada');
        await Promise.all([refreshSavingsGoals(), refreshDashboard()]);
    } catch (err) { toast(err.message, 'error'); }
}

// ---------- Suscripciones ----------
async function refreshSubscriptions() {
    const tbody = document.getElementById('subs-grid-container');
    try {
        const subs = await ExpenseFlowAPI.getSubscriptions();
        if (!subs.length) {
            tbody.innerHTML = `<tr><td colspan="6">${emptyHtml('No tienes suscripciones', 'Añade los servicios que te cobran cada mes o cada año para verlos venir.', { modal: 'modal-subscription', label: 'Añadir suscripción' })}</td></tr>`;
            document.getElementById('subs-summary').textContent = 'Servicios que te cobran cada mes o cada año.';
            return;
        }
        cache.subs = new Map(subs.map(s => [s.id, s]));
        tbody.innerHTML = subs.map(s => `<tr>
            <td><div class="row-title">${escapeHtml(s.name)}</div></td>
            <td class="muted">${escapeHtml(s.category)}</td>
            <td class="nowrap">${s.is_active ? dueLabel(s.next_billing_date) : '<span class="muted">Pausada</span>'}</td>
            <td class="right money">${money(s.cost)} <span class="muted" style="font-weight:400">${s.billing_cycle === 'monthly' ? '/mes' : '/año'}</span></td>
            <td>
                <label class="switch">
                    <input type="checkbox" ${s.is_active ? 'checked' : ''} data-action="toggle-sub" data-id="${s.id}" aria-label="${escapeHtml(s.name)} activa">
                    <span class="track" aria-hidden="true"></span>
                    <span>${s.is_active ? 'Activa' : 'Pausada'}</span>
                </label>
            </td>
            <td class="right nowrap">
                <button type="button" class="link-btn" data-action="edit-sub" data-id="${s.id}" aria-label="Editar ${escapeHtml(s.name)}">Editar</button>
                <button type="button" class="link-btn danger" data-action="delete-sub" data-id="${s.id}" data-title="${escapeHtml(s.name)}" aria-label="Eliminar ${escapeHtml(s.name)}">Eliminar</button>
            </td>
        </tr>`).join('');
        const active = subs.filter(s => s.is_active);
        const monthly = active.reduce((sum, s) => sum + (s.billing_cycle === 'monthly' ? s.cost : s.cost / 12), 0);
        document.getElementById('subs-summary').textContent =
            `${active.length} activas · te cuestan ${money(monthly)} al mes (las anuales, repartidas en 12).`;
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="6">${errorHtml('Revisa tu conexión.')}</td></tr>`;
    }
}

async function handleToggleSub(id) {
    try {
        const res = await ExpenseFlowAPI.toggleSubscription(id);
        toast(res.is_active ? 'Suscripción activada' : 'Suscripción pausada');
        await Promise.all([refreshSubscriptions(), refreshDashboard()]);
    } catch (err) { toast(err.message, 'error'); }
}

async function handleDeleteSub(id, name) {
    if (!await confirmAction('¿Eliminar esta suscripción?', `"${name}" dejará de aparecer en tus próximos cobros.`)) return;
    try {
        await ExpenseFlowAPI.deleteSubscription(id);
        toast('Suscripción eliminada');
        await Promise.all([refreshSubscriptions(), refreshDashboard()]);
    } catch (err) { toast(err.message, 'error'); }
}

// ---------- Calculadora ----------
function setupCalculator() {
    const btnAddTx = document.getElementById('btn-add-calc-tx');

    document.getElementById('form-calculator').addEventListener('submit', (e) => {
        e.preventDefault();
        const title = document.getElementById('calc-title').value.trim() || "Compra a plazos";
        const P = parseFloat(document.getElementById('calc-amount').value);
        const n = parseInt(document.getElementById('calc-months').value, 10);
        const iPercent = parseFloat(document.getElementById('calc-interest').value) || 0;
        const i = iPercent / 100;

        // Sistema francés: cuota = P · i / (1 − (1 + i)^−n)
        const monthly = i === 0 ? P / n : P * (i / (1 - Math.pow(1 + i, -n)));
        const monthlyRounded = Math.round(monthly * 100) / 100;
        const total = monthlyRounded * n;
        const interest = total - P;

        document.getElementById('res-monthly-payment').textContent = money(monthlyRounded);
        document.getElementById('res-total-interest').textContent = money(Math.max(interest, 0));
        document.getElementById('res-total-pay').textContent = money(total);

        currentCalcInstallment = {
            title: `Cuota 1/${n}: ${title}`,
            amount: monthlyRounded,
            type: "expense",
            category: document.getElementById('calc-category').value,
            date: localToday(),
            payment_method: "Tarjeta Crédito",
            notes: `A ${n} cuotas con ${iPercent} % de interés mensual`
        };
        btnAddTx.disabled = false;
    });

    btnAddTx.addEventListener('click', async () => {
        if (!currentCalcInstallment) return;
        btnAddTx.disabled = true;
        try {
            await ExpenseFlowAPI.createTransaction(currentCalcInstallment);
            toast('Primera cuota registrada como gasto');
            currentCalcInstallment = null;
            await refreshAll();
        } catch (err) {
            toast(err.message, 'error');
            btnAddTx.disabled = false;
        }
    });
}

// ---------- Diálogos ----------
function setupModals() {
    document.addEventListener('click', (e) => {
        const opener = e.target.closest('[data-open]');
        if (opener) openModal(opener.dataset.open);

        if (e.target.closest('[data-close]')) closeModal(e.target.closest('dialog'));

        const goto = e.target.closest('[data-goto]');
        if (goto) showTab(goto.dataset.goto);

        if (e.target.closest('[data-retry]')) refreshAll();
    });

    // Abrir un formulario con "data-open" siempre es para crear: se limpia el modo edición
    document.querySelectorAll('[data-open="modal-transaction"]').forEach(b => b.addEventListener('click', () => openTxForm()));
    document.querySelectorAll('[data-open="modal-subscription"]').forEach(b => b.addEventListener('click', () => openSubForm()));
    document.querySelectorAll('[data-open="modal-savings-goal"]').forEach(b => b.addEventListener('click', () => openGoalForm()));

    // Clic fuera del recuadro (en el fondo) cierra el diálogo; Esc lo cierra el navegador.
    document.querySelectorAll('dialog.modal').forEach(dlg => {
        dlg.addEventListener('click', (e) => { if (e.target === dlg) closeModal(dlg); });
    });
}

/** Prepara el formulario de movimiento para crear (sin datos) o editar (con el movimiento). */
function openTxForm(tx) {
    const form = document.getElementById('form-transaction');
    form.reset();
    resetDates();
    document.getElementById('tx-id').value = tx ? tx.id : '';
    document.getElementById('modal-tx-title').textContent = tx ? 'Editar movimiento' : 'Registrar movimiento';
    if (tx) {
        document.getElementById('tx-title').value = tx.title;
        document.getElementById('tx-amount').value = tx.amount;
        document.getElementById('tx-type').value = tx.type;
        document.getElementById('tx-category').value = tx.category;
        document.getElementById('tx-date').value = tx.date;
        document.getElementById('tx-payment').value = tx.payment_method || 'Tarjeta Crédito';
        document.getElementById('tx-notes').value = tx.notes || '';
        openModal('modal-transaction');
    }
}

function openSubForm(sub) {
    const form = document.getElementById('form-subscription');
    form.reset();
    resetDates();
    document.getElementById('sub-id').value = sub ? sub.id : '';
    document.getElementById('modal-sub-title').textContent = sub ? 'Editar suscripción' : 'Añadir suscripción';
    if (sub) {
        document.getElementById('sub-name').value = sub.name;
        document.getElementById('sub-cost').value = sub.cost;
        document.getElementById('sub-cycle').value = sub.billing_cycle;
        document.getElementById('sub-category').value = sub.category;
        document.getElementById('sub-date').value = sub.next_billing_date;
        openModal('modal-subscription');
    }
}

function openGoalForm(goal) {
    const form = document.getElementById('form-savings-goal');
    form.reset();
    resetDates();
    document.getElementById('goal-id').value = goal ? goal.id : '';
    document.getElementById('modal-goal-title').textContent = goal ? 'Editar meta' : 'Nueva meta de ahorro';
    // Lo ahorrado solo cambia con abonos, así queda registrado en los movimientos
    document.getElementById('goal-initial-field').hidden = !!goal;
    form.querySelector('button[type="submit"]').textContent = goal ? 'Guardar' : 'Crear meta';
    if (goal) {
        document.getElementById('goal-title').value = goal.title;
        document.getElementById('goal-target').value = goal.target_amount;
        document.getElementById('goal-category').value = goal.category || 'General';
        document.getElementById('goal-date').value = goal.target_date;
        openModal('modal-savings-goal');
    }
}

function setupFilters() {
    let timer;
    const reload = () => { txPage = 1; refreshTransactions(); };
    document.getElementById('tx-search-input').addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(reload, 300);
    });
    ['tx-filter-type', 'tx-filter-category', 'tx-filter-start', 'tx-filter-end'].forEach(id =>
        document.getElementById(id).addEventListener('change', reload));

    document.getElementById('tx-prev').addEventListener('click', () => { txPage = Math.max(1, txPage - 1); refreshTransactions(); });
    document.getElementById('tx-next').addEventListener('click', () => { txPage += 1; refreshTransactions(); });
}

function setupCurrency() {
    document.getElementById('user-currency').addEventListener('change', async (e) => {
        const previous = currency;
        try {
            const user = await ExpenseFlowAPI.updateProfile({ currency: e.target.value });
            setCurrency(user.currency);
            toast(`Montos en ${user.currency}. Los valores guardados no se convierten.`);
            await refreshAll();
        } catch (err) {
            setCurrency(previous);
            toast(err.message, 'error');
        }
    });
}

/** Envía un formulario con el botón desactivado mientras espera; muestra el error en un aviso. */
function onSubmit(formId, handler) {
    const form = document.getElementById(formId);
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const button = form.querySelector('button[type="submit"]');
        button.disabled = true;
        try {
            await handler(form);
        } catch (err) {
            toast(err.message, 'error');
        } finally {
            button.disabled = false;
        }
    });
}

function setupForms() {
    onSubmit('form-transaction', async (form) => {
        const id = document.getElementById('tx-id').value;
        const data = {
            title: document.getElementById('tx-title').value,
            amount: parseFloat(document.getElementById('tx-amount').value),
            type: document.getElementById('tx-type').value,
            category: document.getElementById('tx-category').value,
            date: document.getElementById('tx-date').value,
            payment_method: document.getElementById('tx-payment').value,
            notes: document.getElementById('tx-notes').value
        };
        if (id) await ExpenseFlowAPI.updateTransaction(id, data);
        else await ExpenseFlowAPI.createTransaction(data);
        closeModal(form.closest('dialog'));
        openTxForm();
        toast(id ? 'Movimiento actualizado' : 'Movimiento registrado');
        await refreshAll();
    });

    onSubmit('form-savings-goal', async (form) => {
        const id = document.getElementById('goal-id').value;
        const data = {
            title: document.getElementById('goal-title').value,
            target_amount: parseFloat(document.getElementById('goal-target').value),
            category: document.getElementById('goal-category').value || "General",
            target_date: document.getElementById('goal-date').value
        };
        if (id) await ExpenseFlowAPI.updateSavingsGoal(id, data);
        else await ExpenseFlowAPI.createSavingsGoal({ ...data, current_amount: parseFloat(document.getElementById('goal-initial').value || 0) });
        closeModal(form.closest('dialog'));
        openGoalForm();
        toast(id ? 'Meta actualizada' : 'Meta creada');
        await Promise.all([refreshSavingsGoals(), refreshDashboard()]);
    });

    onSubmit('form-deposit-goal', async (form) => {
        const id = parseInt(document.getElementById('deposit-goal-id').value, 10);
        const amount = parseFloat(document.getElementById('deposit-amount').value);
        await ExpenseFlowAPI.depositToSavingsGoal(id, amount);
        closeModal(form.closest('dialog'));
        form.reset();
        toast(`Abonaste ${money(amount)}`);
        await refreshAll();
    });

    onSubmit('form-subscription', async (form) => {
        const id = document.getElementById('sub-id').value;
        const data = {
            name: document.getElementById('sub-name').value,
            cost: parseFloat(document.getElementById('sub-cost').value),
            billing_cycle: document.getElementById('sub-cycle').value,
            category: document.getElementById('sub-category').value,
            next_billing_date: document.getElementById('sub-date').value
        };
        if (id) await ExpenseFlowAPI.updateSubscription(id, data);
        else await ExpenseFlowAPI.createSubscription(data);
        closeModal(form.closest('dialog'));
        openSubForm();
        toast(id ? 'Suscripción actualizada' : 'Suscripción añadida');
        // Una fecha ya vencida genera sus cobros: se recargan también los movimientos
        await refreshAll();
    });

    onSubmit('form-budget', async (form) => {
        const category = document.getElementById('budget-category').value;
        await ExpenseFlowAPI.updateBudget(category, parseFloat(document.getElementById('budget-limit').value));
        closeModal(form.closest('dialog'));
        toast(`Límite de ${category} actualizado`);
        await Promise.all([refreshBudgets(), refreshDashboard()]);
    });

    // Un archivo elegido se carga en el área de texto para revisarlo antes de importar
    document.getElementById('import-file').addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        if (file.size > 2_000_000) {
            toast('El archivo pesa más de 2 MB', 'error');
            e.target.value = '';
            return;
        }
        document.getElementById('import-json-area').value = await file.text();
    });

    onSubmit('form-import-json', async (form) => {
        const text = document.getElementById('import-json-area').value.trim();
        let res;
        if (text.startsWith('[') || text.startsWith('{')) {
            let data;
            try {
                data = JSON.parse(text);
            } catch (err) {
                throw new Error('El texto parece JSON pero no es válido. Revisa comas y comillas.');
            }
            res = await ExpenseFlowAPI.importJSON(Array.isArray(data) ? data : (data.transactions || []));
        } else {
            res = await ExpenseFlowAPI.importCSV(text);
        }
        closeModal(form.closest('dialog'));
        form.reset();
        toast(`Se importaron ${res.imported_count} movimientos`);
        await refreshAll();
    });
}

// Llena todos los selectores de categoría desde /api/categories (lista única del backend)
async function loadCategories() {
    let cats;
    try {
        cats = await ExpenseFlowAPI.getCategories();
    } catch (err) {
        toast('No se pudieron cargar las categorías', 'error');
        return;
    }
    const toOptions = (list) => list.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
    const expense = toOptions(cats.expense);
    const all = `<optgroup label="Gastos">${expense}</optgroup><optgroup label="Ingresos">${toOptions(cats.income)}</optgroup>`;

    const fill = (id, html, placeholder) => {
        const el = document.getElementById(id);
        if (el) el.innerHTML = (placeholder ? `<option value="">${placeholder}</option>` : '') + html;
    };
    fill('tx-filter-category', all, 'Todas las categorías');
    fill('tx-category', all);
    fill('calc-category', expense);
    fill('sub-category', expense);
}

// Acciones de botones generados dinámicamente. Se leen de data-* (sin onclick en línea):
// evita inyección de JS vía títulos/categorías y es compatible con la Content-Security-Policy.
document.addEventListener('click', (e) => {
    const el = e.target.closest('[data-action]');
    if (!el || el.matches('input[type="checkbox"]')) return;
    const id = Number(el.dataset.id);
    switch (el.dataset.action) {
        case 'deposit-goal': openDepositModal(id, el.dataset.title, Number(el.dataset.left)); break;
        case 'delete-goal': handleDeleteGoal(id, el.dataset.title); break;
        case 'delete-tx': handleDeleteTransaction(id, el.dataset.title); break;
        case 'delete-sub': handleDeleteSub(id, el.dataset.title); break;
        case 'edit-tx': if (cache.tx.has(id)) openTxForm(cache.tx.get(id)); break;
        case 'edit-sub': if (cache.subs.has(id)) openSubForm(cache.subs.get(id)); break;
        case 'edit-goal': if (cache.goals.has(id)) openGoalForm(cache.goals.get(id)); break;
        case 'edit-budget': openBudgetModal(el.dataset.category, Number(el.dataset.limit)); break;
    }
});
document.addEventListener('change', (e) => {
    const el = e.target.closest('[data-action="toggle-sub"]');
    if (el) handleToggleSub(Number(el.dataset.id));
});

// ---------- Autenticación ----------
function showAuthScreen(message) {
    document.getElementById('auth-screen').hidden = false;
    document.getElementById('auth-subtitle').textContent = message || 'Inicia sesión para ver tus finanzas.';
    document.querySelectorAll('dialog[open]').forEach(d => d.close());
    document.getElementById('login-email').focus();
}

function setAuthView(view) {
    document.getElementById('form-login').hidden = view !== 'login';
    document.getElementById('form-register').hidden = view !== 'register';
    document.getElementById(view === 'login' ? 'login-email' : 'register-name').focus();
}

function setupAuth() {
    document.querySelectorAll('[data-auth-view]').forEach(btn =>
        btn.addEventListener('click', () => setAuthView(btn.dataset.authView)));

    const submitWith = (formId, errorId, action) => {
        const form = document.getElementById(formId);
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const errorEl = document.getElementById(errorId);
            const button = form.querySelector('button[type="submit"]');
            errorEl.textContent = '';
            button.disabled = true;
            try {
                const user = await action();
                form.reset();
                await startSession(user);
            } catch (err) {
                errorEl.textContent = err.message;
            } finally {
                button.disabled = false;
            }
        });
    };

    submitWith('form-login', 'login-error', () => ExpenseFlowAPI.login(
        document.getElementById('login-email').value,
        document.getElementById('login-password').value));

    submitWith('form-register', 'register-error', () => ExpenseFlowAPI.register(
        document.getElementById('register-name').value,
        document.getElementById('register-email').value,
        document.getElementById('register-password').value,
        document.getElementById('register-sample').checked,
        document.getElementById('register-currency').value));

    document.getElementById('btn-logout').addEventListener('click', async () => {
        await ExpenseFlowAPI.logout();
        window.location.reload(); // limpia de la pantalla los datos del usuario anterior
    });

    window.addEventListener('auth-required', () => showAuthScreen('Tu sesión expiró. Vuelve a iniciar sesión.'));
}
