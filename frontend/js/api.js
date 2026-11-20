// ── API HELPERS ───────────────────────────────────────────────────────────
async function api(method, path, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (state.token) opts.headers['Authorization'] = 'Bearer ' + state.token;
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(API + path, opts);
  const json = await r.json().catch(() => ({}));
  if (!r.ok) {
    if (r.status === 401 && state.token) { logout(); throw new Error('Session expired. Please log in again.'); }
    let detail = json.detail;
    if (Array.isArray(detail)) {
      detail = detail.map(e => `${e.loc ? e.loc[e.loc.length - 1] : 'field'}: ${e.msg}`).join('; ');
    } else if (typeof detail !== 'string') {
      detail = JSON.stringify(detail);
    }
    throw new Error(detail || 'An unexpected error occurred');
  }
  return json;
}
const get  = path      => api('GET', path);
const post = (path, b) => api('POST', path, b);
const put  = (path, b) => api('PUT', path, b);
const del  = path      => api('DELETE', path);

// ── PAGE DATA LOADER ──────────────────────────────────────────────────────
async function loadPage(page) {
  const u = state.user;
  if (!u) { setState({ loading: false }); return; }
  setState({ loading: true, error: null });
  try {
    const D = state.data;
    let d = {};

    if (page === 'student-book') {
      d = { stations: await get('/student/stations'), avail: {} };

    } else if (page === 'student-ride') {
      const [bookings, active, stations] = await Promise.all([
        get('/student/my-bookings/' + u.user_id),
        get('/student/active-ride/' + u.user_id),
        get('/student/stations'),
      ]);
      d = { bookings, active: active.active_ride, stations };

    } else if (page === 'student-history') {
      d = { history: await get('/student/my-rides/' + u.user_id) };

    } else if (page === 'admin-stations') {
      d = { fleet: await get('/admin/dashboard/fleet'), stations: await get('/admin/stations') };

    } else if (page === 'admin-bicycles') {
      const f  = D.bikeFilter || {};
      const qs = Object.entries(f).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');
      d = { bikes: await get('/admin/bicycles' + (qs ? '?' + qs : '')), stations: await get('/admin/stations') };

    } else if (page === 'admin-analytics') {
      d = { analytics: await get('/admin/analytics/summary?days=' + (D.days || 30)) };

    } else if (page === 'admin-rides') {
      const f = D.rideFilter || { status: '', offset: 0 };
      d = { rides: await get(`/admin/rides?limit=20&offset=${f.offset}` + (f.status ? '&status=' + f.status : '')) };

    } else if (page === 'admin-forecast') {
      const [demandSummary, runs] = await Promise.all([get('/admin/forecast/demand-summary'), get('/admin/forecast/runs')]);
      d = { demandSummary, runs };
    }

    setState({ data: { ...state.data, ...d }, loading: false });
  } catch (e) {
    setState({ loading: false, error: e.message });
  }
}
