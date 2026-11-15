/**
 * Gráficos de ExpenseFlow, dibujados a mano (HTML y SVG, sin librerías).
 * Un gráfico responde una pregunta; el color dorado (--data) marca el dato principal.
 */
(function () {
    const SVG_NS = 'http://www.w3.org/2000/svg';

    function esc(text) {
        return String(text ?? '').replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m]));
    }

    /**
     * Lista de barras horizontales ordenadas de mayor a menor.
     * items: [{ label, value }]; fmt: función que formatea el valor.
     */
    function barList(container, items, fmt) {
        const total = items.reduce((s, i) => s + i.value, 0);
        const max = Math.max(...items.map(i => i.value), 0);
        container.innerHTML = `<ul class="barlist">${items.map(i => {
            const width = max > 0 ? (i.value / max) * 100 : 0;
            const share = total > 0 ? Math.round((i.value / total) * 100) : 0;
            return `<li class="barlist-row">
                <span class="barlist-label">${esc(i.label)}</span>
                <span class="barlist-value">${esc(fmt(i.value))}<span class="barlist-share">${share} %</span></span>
                <span class="barlist-track" aria-hidden="true"><span class="barlist-fill" style="width:${width.toFixed(1)}%"></span></span>
            </li>`;
        }).join('')}</ul>`;
    }

    /** Escala "bonita" para el eje y: 1, 2 o 5 por potencia de 10. */
    function niceMax(value) {
        if (value <= 0) return 1;
        const pow = Math.pow(10, Math.floor(Math.log10(value)));
        const n = value / pow;
        const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
        return step * pow;
    }

    function el(name, attrs, text) {
        const node = document.createElementNS(SVG_NS, name);
        Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
        if (text !== undefined) node.textContent = text;
        return node;
    }

    /**
     * Columnas por día del mes. Los días con gasto van en dorado; el resto queda vacío.
     * trends: [{ date: 'AAAA-MM-DD', total }]; month: 'AAAA-MM'; fmtAxis: formato corto del eje.
     */
    function dailyBars(container, trends, month, fmtAxis) {
        const [year, mon] = month.split('-').map(Number);
        const days = new Date(year, mon, 0).getDate();
        const byDay = new Map(trends.map(t => [Number(t.date.slice(8, 10)), t.total]));
        const top = niceMax(Math.max(...trends.map(t => t.total), 0));

        const W = 720, H = 250, left = 44, right = 4, topPad = 8, bottom = 22;
        const plotW = W - left - right, plotH = H - topPad - bottom;
        const slot = plotW / days;
        const barW = Math.max(2, slot * 0.62);

        const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, class: 'chart-svg', role: 'img' });
        svg.setAttribute('aria-label', `Gasto por día del mes. ${trends.length} días con gastos.`);

        // Tres líneas guía: 0, la mitad y el máximo de la escala
        [0, 0.5, 1].forEach(f => {
            const y = topPad + plotH * (1 - f);
            svg.appendChild(el('line', { x1: left, x2: W - right, y1: y, y2: y, class: 'grid-line' }));
            svg.appendChild(el('text', { x: left - 8, y: y + 4, 'text-anchor': 'end' }, fmtAxis(top * f)));
        });

        for (let d = 1; d <= days; d++) {
            const x = left + slot * (d - 1) + (slot - barW) / 2;
            const v = byDay.get(d) || 0;
            if (v > 0) {
                const h = Math.max(2, (v / top) * plotH);
                const rect = el('rect', { x: x.toFixed(1), y: (topPad + plotH - h).toFixed(1), width: barW.toFixed(1), height: h.toFixed(1), class: 'bar', rx: 1 });
                rect.appendChild(el('title', {}, `Día ${d}: ${fmtAxis(v)}`));
                svg.appendChild(rect);
            }
            if (d === 1 || d % 5 === 0) {
                svg.appendChild(el('text', { x: (left + slot * (d - 1) + slot / 2).toFixed(1), y: H - 6, 'text-anchor': 'middle' }, String(d)));
            }
        }

        container.replaceChildren(svg);
    }

    window.ExpenseFlowCharts = { barList, dailyBars };
})();
