// ── HELPERS ───────────────────────────────────────────────────────────────
async function run(fn) {
  setState({ loading: true, error: null });
  try { await fn(); } catch (e) { setState({ loading: false, error: e.message }); }
}

async function go(page, msg) {            // show a message, then reload a page's data
  setState({ page, success: msg || null, error: null });
  await loadPage(page);
}

const setData = patch => setState({ loading: false, data: { ...state.data, ...patch } });

// ── BUTTON ACTIONS ────────────────────────────────────────────────────────
async function handleAction(action, ds) {
  const id = parseInt(ds.id);
  setState({ error: null, success: null });

  await run(async () => {
    // Student
    if (action === 'check-avail') {
      const r = await get('/student/availability/' + id);
      setData({ avail: { ...(state.data.avail || {}), [id]: r } });
    } else if (action === 'book') {
      await post('/student/book', { station_id: id });
      await go('student-ride', 'Booking confirmed');
    } else if (action === 'cancel-booking') {
      if (!confirm('Cancel this booking?')) return setState({ loading: false });
      await post('/student/cancel-booking/' + id);
      await go('student-ride', 'Booking cancelled');
    } else if (action === 'start-ride') {
      await post('/student/start-ride', { booking_id: id });
      await go('student-ride', 'Ride started');

    // Admin: stations
    } else if (action === 'toggle-station') {
      await put('/admin/stations/' + id, { is_active: ds.active === '1' });
      await go('admin-stations', 'Station updated');
    } else if (action === 'rename-station') {
      const name = prompt('New station name', ds.name);
      if (!name) return setState({ loading: false });
      await put('/admin/stations/' + id, { name });
      await go('admin-stations', 'Station renamed');

    // Admin: bicycles
    } else if (action === 'bike-status') {
      await put('/admin/bicycles/' + id, { status: ds.status });
      await go('admin-bicycles', 'Bicycle updated');
    } else if (action === 'bike-retire') {
      if (!confirm('Retire this bicycle? This cannot be undone.')) return setState({ loading: false });
      await del('/admin/bicycles/' + id);
      await go('admin-bicycles', 'Bicycle retired');
    } else if (action === 'bike-history') {
      const rows = await get(`/admin/bicycles/${id}/history`);
      setState({ loading: false, modal: { type: 'bike-history', code: ds.code, rows } });

    // Admin: rides and forecast
    } else if (action === 'rides-page') {
      setData({ rideFilter: { ...(state.data.rideFilter || {}), offset: parseInt(ds.offset) } });
      await loadPage('admin-rides');
    } else if (action === 'gen-synthetic') {
      const r = await post('/admin/forecast/generate-synthetic', { days: 30 });
      await go('admin-forecast', r.message);
    } else if (action === 'sync-demand') {
      const r = await post('/admin/forecast/sync-demand');
      await go('admin-forecast', r.message);
    } else if (action === 'view-run') {
      const r = await get('/admin/forecast/runs/' + id);
      setData({ runDetail: r });
      window.scrollTo(0, 0);
    }
  });
}

// ── SELECT / FILTER CHANGES ───────────────────────────────────────────────
async function handleChange(kind, el) {
  await run(async () => {
    if (kind === 'bike-cond') {
      await put('/admin/bicycles/' + el.dataset.id, { condition: el.value });
      await go('admin-bicycles', 'Condition updated');
    } else if (kind === 'bike-filter') {
      setData({ bikeFilter: { ...(state.data.bikeFilter || {}), [el.dataset.key]: el.value } });
      await loadPage('admin-bicycles');
    } else if (kind === 'days') {
      setData({ days: parseInt(el.value) });
      await loadPage('admin-analytics');
    } else if (kind === 'ride-status') {
      setData({ rideFilter: { status: el.value, offset: 0 } });
      await loadPage('admin-rides');
    }
  });
}

// ── FORMS ─────────────────────────────────────────────────────────────────
const formHandlers = {
  login:    d => login(d.email, d.password),
  register: d => register(d),

  'end-ride': async d => {
    const res = await post('/student/end-ride/' + d.ride_id, { end_station_id: parseInt(d.end_station_id) });
    setData({ lastRide: res });
    await go('student-ride', 'Ride ended');
  },
  'add-station': async d => {
    await post('/admin/stations', { name: d.name });
    await go('admin-stations', 'Station added');
  },
  'add-bike': async d => {
    await post('/admin/bicycles', { bicycle_code: d.bicycle_code, station_id: parseInt(d.station_id), condition: d.condition });
    await go('admin-bicycles', 'Bicycle added');
  },
  'run-forecast': async d => {
    // the input is local time; the API wants UTC
    const res = await post('/admin/forecast/run', {
      start_time: new Date(d.start_time).toISOString(), hours: parseInt(d.hours), data_source: d.data_source,
    });
    setData({ runDetail: res });
    await go('admin-forecast', 'Forecast complete');
    window.scrollTo(0, 0);
  },
};

// ── EVENT BINDING ─────────────────────────────────────────────────────────
function bindEvents() {
  document.querySelectorAll('[data-tab]').forEach(el =>
    el.addEventListener('click', () => setState({ data: { ...state.data, authTab: el.dataset.tab }, error: null, success: null })));

  document.querySelectorAll('[data-page]').forEach(el =>
    el.addEventListener('click', e => { e.preventDefault(); setPage(el.dataset.page); }));

  const logoutBtn = document.getElementById('logout-btn');
  if (logoutBtn) logoutBtn.addEventListener('click', logout);

  const closeModal = document.getElementById('close-modal');
  if (closeModal) closeModal.addEventListener('click', () => setState({ modal: null }));
  const overlay = document.getElementById('modal-overlay');
  if (overlay) overlay.addEventListener('click', e => { if (e.target === overlay) setState({ modal: null }); });

  document.querySelectorAll('[data-action]').forEach(el =>
    el.addEventListener('click', () => handleAction(el.dataset.action, el.dataset)));

  document.querySelectorAll('[data-change]').forEach(el =>
    el.addEventListener('change', () => handleChange(el.dataset.change, el)));

  document.querySelectorAll('form[data-form]').forEach(form =>
    form.addEventListener('submit', e => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(form));
      run(() => formHandlers[form.dataset.form](d));
    }));
}
