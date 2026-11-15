// Aplica el tema antes de pintar la página para evitar un destello.
// Preferencia guardada en localStorage ("ef-theme"); si no hay, se sigue al sistema.
(function () {
    var saved = null;
    try { saved = localStorage.getItem('ef-theme'); } catch (e) { /* modo privado */ }
    var dark = saved ? saved === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
})();
