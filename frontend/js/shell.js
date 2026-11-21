// ── ICONS ─────────────────────────────────────────────────────────────────
const icons = {
  bike:  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="5.5" cy="17" r="3.5"/><circle cx="18.5" cy="17" r="3.5"/><path d="M5.5 17 9 8h6l3.5 9M9 8 12 17M14 5h2"/></svg>`,
  list:  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>`,
  pin:   `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 22s8-7 8-12a8 8 0 0 0-16 0c0 5 8 12 8 12z"/><circle cx="12" cy="10" r="3"/></svg>`,
  chart: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 3v18h18M7 15l4-4 3 3 5-6"/></svg>`,
};

function navItem(page, icon, label) {
  return `<div class="nav-item ${state.page === page ? 'active' : ''}" data-page="${page}">${icon}<span>${label}</span></div>`;
}

function renderNav(role) {
  if (role === 'Student') return `
    <div class="nav-section">Ride</div>
    ${navItem('student-book', icons.bike, 'Book a bicycle')}
    ${navItem('student-ride', icons.pin, 'My ride')}
    ${navItem('student-history', icons.list, 'Ride history')}`;
  if (role === 'Administrator') return `
    <div class="nav-section">Fleet</div>
    ${navItem('admin-stations', icons.pin, 'Stations')}
    ${navItem('admin-bicycles', icons.bike, 'Bicycles')}
    <div class="nav-section">Insight</div>
    ${navItem('admin-analytics', icons.chart, 'Analytics')}
    ${navItem('admin-rides', icons.list, 'Trip records')}
    ${navItem('admin-forecast', icons.chart, 'Forecast')}
    <div class="nav-section">Users</div>
    ${navItem('admin-students', icons.list, 'Students')}`;
  return '';
}

// ── RENDER ─────────────────────────────────────────────────────────────────
function render() {
  document.getElementById('app').innerHTML = !state.token ? renderAuth() : renderApp();
  bindEvents();
  tickTimers();
}

function renderApp() {
  const u = state.user;
  return `
  <div class="app">
    <div class="sidebar">
      <div class="sidebar-logo"><div class="logo-text">&gt; intelliride-x</div><div class="logo-role">${esc(u.role)}</div></div>
      <nav class="sidebar-nav">${renderNav(u.role)}</nav>
      <div class="sidebar-footer">
        <div class="user-info"><div class="user-avatar">${esc(u.name[0].toUpperCase())}</div>
          <div><div class="user-name">${esc(u.name)}</div><div class="user-email">${esc(u.role)}</div></div></div>
        <button class="btn btn-ghost btn-sm" id="logout-btn" style="width:100%; justify-content:center; margin-top:6px;">Logout</button>
      </div>
    </div>
    <main class="main">
      ${state.error ? `<div class="alert alert-error">${esc(state.error)}</div>` : ''}
      ${state.success ? `<div class="alert alert-success">${esc(state.success)}</div>` : ''}
      ${state.loading ? '<div class="loading">Loading</div>' : renderPage()}
    </main>
  </div>
  ${state.modal ? renderModal() : ''}`;
}

function renderPage() {
  switch (state.page) {
    case 'student-book':    return renderStudentBook();
    case 'student-ride':    return renderStudentRide();
    case 'student-history': return renderStudentHistory();
    case 'admin-stations':  return renderAdminStations();
    case 'admin-bicycles':  return renderAdminBicycles();
    case 'admin-analytics': return renderAdminAnalytics();
    case 'admin-rides':     return renderAdminRides();
    case 'admin-forecast':  return renderAdminForecast();
    case 'admin-students':  return renderAdminStudents();
    default: return `<div class="empty">Page not found</div>`;
  }
}
