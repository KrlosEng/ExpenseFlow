/**
 * ExpenseFlow Charts Module
 * Manages Chart.js visualizations for category expenses & trend analysis.
 */

let categoryChartInstance = null;
let trendChartInstance = null;

function renderCategoryChart(categoryData) {
    const ctx = document.getElementById('categoryChart')?.getContext('2d');
    if (!ctx) return;

    if (categoryChartInstance) {
        categoryChartInstance.destroy();
    }

    const labels = categoryData.map(c => c.category);
    const dataValues = categoryData.map(c => c.total);

    const colors = [
        '#38BDF8', '#818CF8', '#10B981', '#F43F5E', '#F59E0B', '#A855F7', '#EC4899'
    ];

    categoryChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: dataValues,
                backgroundColor: colors.slice(0, labels.length),
                borderWidth: 2,
                borderColor: '#121829'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        color: '#94A3B8',
                        font: { family: 'Outfit', size: 12 },
                        padding: 14,
                        usePointStyle: true
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return ` ${context.label}: $${context.parsed.toFixed(2)}`;
                        }
                    }
                }
            },
            cutout: '70%'
        }
    });
}

function renderTrendChart(dailyData) {
    const ctx = document.getElementById('trendChart')?.getContext('2d');
    if (!ctx) return;

    if (trendChartInstance) {
        trendChartInstance.destroy();
    }

    const labels = dailyData.map(d => d.date);
    const dataValues = dailyData.map(d => d.total);

    const gradient = ctx.createLinearGradient(0, 0, 0, 250);
    gradient.addColorStop(0, 'rgba(56, 189, 248, 0.35)');
    gradient.addColorStop(1, 'rgba(56, 189, 248, 0.0)');

    trendChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Gasto Diarios ($)',
                data: dataValues,
                borderColor: '#38BDF8',
                borderWidth: 3,
                pointBackgroundColor: '#38BDF8',
                pointRadius: 4,
                pointHoverRadius: 6,
                fill: true,
                backgroundColor: gradient,
                tension: 0.35
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: {
                    grid: { display: false, drawBorder: false },
                    ticks: { color: '#64748B', font: { family: 'Outfit', size: 11 } }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: {
                        color: '#64748B',
                        font: { family: 'Outfit', size: 11 },
                        callback: function(value) { return '$' + value; }
                    }
                }
            }
        }
    });
}

window.ExpenseFlowCharts = {
    renderCategoryChart,
    renderTrendChart
};
