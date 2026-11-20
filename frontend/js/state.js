// ── STATE ─────────────────────────────────────────────────────────────────
const API = 'http://127.0.0.1:8000';

let state = {
  token: localStorage.getItem('token') || null,
  user: JSON.parse(localStorage.getItem('user') || 'null'),
  page: 'student-book',
  data: {},
  loading: false,
  error: null,
  success: null,
  modal: null,
};

let _successTimer = null;

function setState(patch) {
  Object.assign(state, patch);
  render();
  if (patch.success) {
    clearTimeout(_successTimer);
    _successTimer = setTimeout(() => { state.success = null; render(); }, 4000);
  }
}

function setPage(page, extra = {}) {
  setState({ page, error: null, success: null, data: { ...state.data, lastRide: null }, ...extra });
  loadPage(page);
}

// ── SMALL HELPERS ─────────────────────────────────────────────────────────
const esc   = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' }[c]));
const fmt   = v => v ? new Date(v).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '—';  // API sends UTC with Z
const money = n => 'PKR ' + Number(n || 0).toFixed(2);

function statusBadge(s) {
  const map = {
    Active: 'badge-blue', Started: 'badge-amber', Completed: 'badge-green', Cancelled: 'badge-gray',
    Available: 'badge-green', Reserved: 'badge-amber', InUse: 'badge-blue', Maintenance: 'badge-orange', Retired: 'badge-gray',
    Good: 'badge-green', NeedsInspection: 'badge-amber', Damaged: 'badge-red',
    Shortage: 'badge-red', Surplus: 'badge-teal', Balanced: 'badge-green',
    Real: 'badge-green', Synthetic: 'badge-purple', Student: 'badge-teal', Administrator: 'badge-red',
  };
  return `<span class="badge ${map[s] || 'badge-gray'}">${esc(s ?? '—')}</span>`;
}

function statBox(label, value) {
  return `<div class="stat"><div class="stat-num">${esc(value)}</div><div class="stat-label">${esc(label)}</div></div>`;
}

function bars(items, labelKey, valueKey) {
  const max = Math.max(1, ...items.map(i => i[valueKey]));
  return items.map(i => `
    <div class="bar-row"><span>${esc(i[labelKey])}</span>
      <div class="bar-track"><div class="bar" style="width:${i[valueKey] / max * 100}%"></div></div>
      <span class="mono">${i[valueKey]}</span></div>`).join('') || '<div class="empty">No data yet</div>';
}
