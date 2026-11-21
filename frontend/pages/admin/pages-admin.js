// ─────────────────────────── ADMIN PAGES ─────────────────────────────────
const BIKE_CONDITIONS = ['Good', 'NeedsInspection', 'Damaged'];
const opts = (list, sel) => list.map(v => `<option value="${v}" ${v === sel ? 'selected' : ''}>${v}</option>`).join('');

function renderAdminStations() {
  const f = state.data.fleet, rows = state.data.stations || [];
  return `
  <div class="page-header"><div class="page-title">Stations and fleet</div></div>
  ${f ? `<div class="stats">${statBox('Total bicycles', f.total_bicycles)}${statBox('Usable now', f.effective_available)}
    ${f.by_status.map(s => statBox(s.status, s.total)).join('')}</div>` : ''}
  <div class="card" style="max-width:520px"><div class="card-title">Add station</div>
    <form data-form="add-station" class="toolbar">
      <div class="field"><input name="name" placeholder="Station name" required minlength="2"></div>
      <button class="btn btn-primary" type="submit">Add station</button>
    </form></div>
  <div class="card" style="margin-top:16px"><div class="table-wrap"><table>
    <thead><tr><th>Station</th><th>Status</th><th>Bicycles</th><th>Usable</th><th>Reserved</th><th>Maintenance</th><th>Actions</th></tr></thead>
    <tbody>${rows.map(s => `
      <tr>
        <td>${esc(s.name)}</td><td>${statusBadge(s.is_active ? 'Active' : 'Cancelled').replace('Cancelled', 'Inactive')}</td>
        <td>${s.total_bicycles}</td><td>${s.effective_available ?? 0}</td><td>${s.reserved_count ?? 0}</td><td>${s.maintenance_count ?? 0}</td>
        <td class="flex gap-2">
          <button class="btn btn-ghost btn-sm" data-action="rename-station" data-id="${s.station_id}" data-name="${esc(s.name)}">Rename</button>
          <button class="btn btn-ghost btn-sm" data-action="toggle-station" data-id="${s.station_id}" data-active="${s.is_active ? 0 : 1}">${s.is_active ? 'Deactivate' : 'Activate'}</button>
        </td>
      </tr>`).join('') || '<tr><td colspan="7" class="empty">No stations</td></tr>'}
    </tbody></table></div></div>`;
}

function renderAdminBicycles() {
  const bikes = state.data.bikes || [], stations = (state.data.stations || []).filter(s => s.is_active);
  const f = state.data.bikeFilter || {};
  const stOpts = sel => stations.map(s => `<option value="${s.station_id}" ${String(s.station_id) === String(sel) ? 'selected' : ''}>${esc(s.name)}</option>`).join('');
  return `
  <div class="page-header"><div class="page-title">Bicycles</div><div class="page-sub">${bikes.length} shown</div></div>
  <div class="card" style="margin-bottom:16px"><div class="card-title">Add bicycle</div>
    <form data-form="add-bike" class="toolbar">
      <div class="field"><label>Code</label><input name="bicycle_code" required minlength="2"></div>
      <div class="field"><label>Station</label><select name="station_id" required>${stOpts()}</select></div>
      <div class="field"><label>Condition</label><select name="condition">${opts(BIKE_CONDITIONS)}</select></div>
      <button class="btn btn-primary" type="submit">Add bicycle</button>
    </form></div>
  <div class="toolbar">
    <div class="field"><label>Status</label><select data-change="bike-filter" data-key="status"><option value="">All</option>${opts(['Available','Reserved','InUse','Maintenance','Retired'], f.status)}</select></div>
    <div class="field"><label>Condition</label><select data-change="bike-filter" data-key="condition"><option value="">All</option>${opts(BIKE_CONDITIONS, f.condition)}</select></div>
    <div class="field"><label>Station</label><select data-change="bike-filter" data-key="station_id"><option value="">All</option>${stOpts(f.station_id)}</select></div>
  </div>
  <div class="card"><div class="table-wrap"><table>
    <thead><tr><th>Code</th><th>Station</th><th>Status</th><th>Condition</th><th>Actions</th></tr></thead>
    <tbody>${bikes.map(b => {
      const locked = ['Reserved', 'InUse', 'Retired'].includes(b.status);
      return `<tr>
        <td class="mono">${esc(b.bicycle_code)}</td><td>${esc(b.station_name || '—')}</td><td>${statusBadge(b.status)}</td>
        <td><select data-change="bike-cond" data-id="${b.bicycle_id}" ${locked ? 'disabled' : ''}>${opts(BIKE_CONDITIONS, b.condition)}</select></td>
        <td class="flex gap-2">
          ${locked ? '' : `<button class="btn btn-ghost btn-sm" data-action="bike-status" data-id="${b.bicycle_id}" data-status="${b.status === 'Maintenance' ? 'Available' : 'Maintenance'}">${b.status === 'Maintenance' ? 'Make available' : 'Maintenance'}</button>
          <button class="btn btn-danger btn-sm" data-action="bike-retire" data-id="${b.bicycle_id}">Retire</button>`}
          <button class="btn btn-ghost btn-sm" data-action="bike-history" data-id="${b.bicycle_id}" data-code="${esc(b.bicycle_code)}">History</button>
        </td></tr>`;
    }).join('') || '<tr><td colspan="5" class="empty">No bicycles match</td></tr>'}
    </tbody></table></div></div>`;
}

function renderAdminAnalytics() {
  const a = state.data.analytics, days = state.data.days || 30;
  if (!a) return '<div class="empty">No data</div>';
  const offset = new Date().getTimezoneOffset() / 60;   // show peak hours in the viewer's local time
  const peaks = a.peak_hours_utc.map(p => ({ label: String((p.hour_utc - offset + 24) % 24).padStart(2, '0') + ':00', rides: p.rides }));
  return `
  <div class="page-header flex justify-between"><div><div class="page-title">Analytics</div></div>
    <div class="field" style="margin:0"><select data-change="days">${[7, 30, 90].map(n => `<option value="${n}" ${n === days ? 'selected' : ''}>Last ${n} days</option>`).join('')}</select></div></div>
  <div class="stats">${statBox('Completed rides', a.totals.completed_rides)}${statBox('Total charge', money(a.totals.total_charge))}
    ${statBox('Avg duration', a.totals.avg_duration_minutes + ' min')}${statBox('Total minutes', a.totals.total_minutes)}</div>
  <div class="card"><div class="card-title">Rides started by station</div>${bars(a.station_usage, 'station_name', 'rides_started')}</div>
  <div class="card" style="margin-top:16px"><div class="card-title">Peak hours (local time)</div>${bars(peaks, 'label', 'rides')}</div>
  <div class="card" style="margin-top:16px"><div class="card-title">Bicycle utilization</div><div class="table-wrap"><table>
    <thead><tr><th>Bicycle</th><th>Rides</th><th>Minutes</th><th>Utilization</th></tr></thead>
    <tbody>${a.bicycle_utilization.map(b => `<tr><td class="mono">${esc(b.bicycle_code)}</td><td>${b.rides}</td><td>${b.total_minutes}</td><td>${b.utilization_percent}%</td></tr>`).join('')
      || '<tr><td colspan="4" class="empty">No bicycles</td></tr>'}</tbody></table></div></div>`;
}

function renderAdminRides() {
  const rows = state.data.rides || [], f = state.data.rideFilter || { status: '', offset: 0 };
  return `
  <div class="page-header"><div class="page-title">Trip records</div></div>
  <div class="toolbar"><div class="field"><label>Status</label>
    <select data-change="ride-status"><option value="">All</option>${opts(['Active', 'Completed'], f.status)}</select></div></div>
  <div class="card"><div class="table-wrap"><table>
    <thead><tr><th>#</th><th>Student</th><th>Bicycle</th><th>From</th><th>To</th><th>Started</th><th>Min</th><th>Charge</th><th>Status</th></tr></thead>
    <tbody>${rows.map(r => `<tr><td class="mono text-muted">${r.ride_id}</td><td>${esc(r.student_name)}</td><td class="mono">${esc(r.bicycle_code)}</td>
      <td>${esc(r.start_station_name)}</td><td>${esc(r.end_station_name || '—')}</td><td>${fmt(r.start_time)}</td>
      <td>${r.duration_minutes ?? '—'}</td><td class="mono">${r.charge == null ? '—' : money(r.charge)}</td><td>${statusBadge(r.status)}</td></tr>`).join('')
      || '<tr><td colspan="9" class="empty">No rides</td></tr>'}</tbody></table></div></div>
  <div class="flex gap-2" style="margin-top:12px">
    <button class="btn btn-ghost btn-sm" data-action="rides-page" data-offset="${Math.max(0, f.offset - 20)}" ${f.offset === 0 ? 'disabled' : ''}>Previous</button>
    <button class="btn btn-ghost btn-sm" data-action="rides-page" data-offset="${f.offset + 20}" ${rows.length < 20 ? 'disabled' : ''}>Next</button>
  </div>`;
}

function renderAdminStudents() {
  const students = state.data.students || [];
  return `
  <div class="page-header"><div class="page-title">Students</div><div class="page-sub">${students.length} registered</div></div>
  <div class="card"><div class="table-wrap"><table>
    <thead><tr><th>Name</th><th>Email</th><th>CNIC</th><th>Status</th><th>Joined</th><th>Rides</th><th>Total charge</th><th>Actions</th></tr></thead>
    <tbody>${students.map(s => `
      <tr>
        <td>${esc(s.full_name)}</td>
        <td class="mono">${esc(s.email)}</td>
        <td class="mono">${fmtCnic(s.cnic)}</td>
        <td>${statusBadge(s.is_active ? 'Active' : 'Cancelled').replace('Cancelled','Inactive')}</td>
        <td>${fmt(s.created_at)}</td>
        <td>${s.total_rides}</td>
        <td class="mono">${money(s.total_charge)}</td>
        <td><button class="btn btn-ghost btn-sm" data-action="view-student" data-id="${s.user_id}">View</button></td>
      </tr>`).join('') || '<tr><td colspan="8" class="empty">No students</td></tr>'}
    </tbody></table></div></div>`;
}

function renderStudentDetailModal(s) {
  if (!s) return '<div class="empty">Loading…</div>';
  return `
  <div class="modal-header"><div class="modal-title">${esc(s.full_name)}</div></div>
  <div class="modal-body">
    <div class="stats" style="margin-bottom:16px">
      ${statBox('Total rides', s.summary.total_rides)}
      ${statBox('Total minutes', s.summary.total_minutes)}
      ${statBox('Total charge', money(s.summary.total_charge))}
    </div>
    <table style="margin-bottom:16px;width:100%">
      <tbody>
        <tr><td style="color:var(--muted);width:120px">Email</td><td class="mono">${esc(s.email)}</td></tr>
        <tr><td style="color:var(--muted)">CNIC</td><td class="mono">${fmtCnic(s.cnic)}</td></tr>
        <tr><td style="color:var(--muted)">Status</td><td>${statusBadge(s.is_active ? 'Active' : 'Cancelled').replace('Cancelled','Inactive')}</td></tr>
        <tr><td style="color:var(--muted)">Joined</td><td>${fmt(s.created_at)}</td></tr>
      </tbody>
    </table>
    <div class="card-title">Ride history</div>
    <div class="table-wrap"><table>
      <thead><tr><th>#</th><th>Bicycle</th><th>From</th><th>To</th><th>Started</th><th>Min</th><th>Charge</th><th>Status</th></tr></thead>
      <tbody>${s.rides.map(r => `
        <tr>
          <td class="mono text-muted">${r.ride_id}</td>
          <td class="mono">${esc(r.bicycle_code)}</td>
          <td>${esc(r.start_station_name)}</td>
          <td>${esc(r.end_station_name || '—')}</td>
          <td>${fmt(r.start_time)}</td>
          <td>${r.duration_minutes ?? '—'}</td>
          <td class="mono">${r.charge == null ? '—' : money(r.charge)}</td>
          <td>${statusBadge(r.status)}</td>
        </tr>`).join('') || '<tr><td colspan="8" class="empty">No rides yet</td></tr>'}
      </tbody>
    </table></div>
  </div>`;
}

// Format a 13-digit CNIC string as XXXXX-XXXXXXX-X
function fmtCnic(raw) {
  if (!raw || raw.length !== 13) return esc(raw || '—');
  return `${raw.slice(0,5)}-${raw.slice(5,12)}-${raw.slice(12)}`;
}
