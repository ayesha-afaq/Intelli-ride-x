// ── LIVE RIDE TIMER (updates text only, no re-render) ─────────────────────
function tickTimers() {
  document.querySelectorAll('.ride-timer').forEach(el => {
    const ms   = Math.max(0, Date.now() - new Date(el.dataset.start).getTime());
    const secs = Math.floor(ms / 1000);
    const mins = Math.max(1, Math.ceil(ms / 60000));          // same rounding as the server
    el.textContent = `${Math.floor(secs / 60)}m ${secs % 60}s  ·  about ${money(mins * el.dataset.rate)}`;
  });
}
setInterval(tickTimers, 1000);

// ── BOOT ──────────────────────────────────────────────────────────────────
async function boot() {
  if (!state.token || !state.user) { render(); return; }
  state.page = DEFAULT_PAGE[state.user.role] || 'student-book';
  await loadPage(state.page);
}

boot();
