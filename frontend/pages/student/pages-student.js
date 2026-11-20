// ─────────────────────────── STUDENT PAGES ───────────────────────────────
function renderStudentBook() {
  const stations = state.data.stations || [], av = state.data.avail || {};
  return `
  <div class="page-header"><div class="page-title">Book a bicycle</div>
    <div class="page-sub">Check a station, then book. You can hold one booking at a time.</div></div>
  <div class="card"><div class="table-wrap"><table>
    <thead><tr><th>Station</th><th>Availability</th><th>Actions</th></tr></thead>
    <tbody>${stations.map(s => `
      <tr>
        <td>${esc(s.name)}</td>
        <td>${av[s.station_id]
          ? (av[s.station_id].available ? '<span class="badge badge-green">Bicycle available</span>' : '<span class="badge badge-gray">None available</span>')
          : '<span class="text-muted">Not checked</span>'}</td>
        <td class="flex gap-2">
          <button class="btn btn-ghost btn-sm" data-action="check-avail" data-id="${s.station_id}">Check</button>
          <button class="btn btn-primary btn-sm" data-action="book" data-id="${s.station_id}">Book</button>
        </td>
      </tr>`).join('') || '<tr><td colspan="3" class="empty">No stations yet</td></tr>'}
    </tbody></table></div></div>`;
}

function renderStudentRide() {
  const d = state.data, a = d.active, stations = d.stations || [];
  const booking = (d.bookings || []).find(b => b.status === 'Active');
  let html = `<div class="page-header"><div class="page-title">My ride</div></div>`;

  if (d.lastRide) html += `
    <div class="card" style="max-width:520px">
      <div class="card-title">Ride finished</div>
      <div class="stats">${statBox('Duration', d.lastRide.duration_minutes + ' min')}${statBox('Charge', money(d.lastRide.charge))}${statBox('Returned to', d.lastRide.end_station)}</div>
      <div class="text-muted text-sm">${esc(d.lastRide.message)}</div>
    </div>`;

  if (a) {
    html += `
    <div class="card" style="max-width:520px">
      <div class="card-title">Ride in progress ${statusBadge('Active')}</div>
      <p class="text-muted text-sm">Bicycle ${esc(a.bicycle_code)} from ${esc(a.start_station_name)}, started ${fmt(a.start_time)}</p>
      <p><span class="ride-timer" data-start="${esc(a.start_time)}" data-rate="${a.rate_per_minute}"></span></p>
      <form data-form="end-ride">
        <input type="hidden" name="ride_id" value="${a.ride_id}">
        <div class="field"><label>Return to station</label>
          <select name="end_station_id" required>${stations.map(s => `<option value="${s.station_id}">${esc(s.name)}</option>`).join('')}</select></div>
        <button class="btn btn-primary" type="submit">End ride</button>
      </form>
    </div>`;
  } else if (booking) {
    html += `
    <div class="card" style="max-width:520px">
      <div class="card-title">Booking confirmed ${statusBadge('Active')}</div>
      <p class="text-muted text-sm">Bicycle ${esc(booking.bicycle_code)} at ${esc(booking.station_name)}, booked ${fmt(booking.booking_time)}</p>
      <div class="flex gap-2">
        <button class="btn btn-primary" data-action="start-ride" data-id="${booking.booking_id}">Start ride</button>
        <button class="btn btn-danger" data-action="cancel-booking" data-id="${booking.booking_id}">Cancel booking</button>
      </div>
    </div>`;
  } else if (!d.lastRide) {
    html += `<div class="empty">No active booking or ride. <a href="#" data-page="student-book">Book a bicycle</a></div>`;
  }

  html += `
  <div class="card" style="margin-top:16px"><div class="card-title">My bookings</div><div class="table-wrap"><table>
    <thead><tr><th>Booked</th><th>Station</th><th>Bicycle</th><th>Status</th></tr></thead>
    <tbody>${(d.bookings || []).map(b => `
      <tr><td>${fmt(b.booking_time)}</td><td>${esc(b.station_name)}</td><td class="mono">${esc(b.bicycle_code)}</td><td>${statusBadge(b.status)}</td></tr>`).join('')
      || '<tr><td colspan="4" class="empty">No bookings yet</td></tr>'}
    </tbody></table></div></div>`;
  return html;
}

function renderStudentHistory() {
  const h = state.data.history;
  if (!h) return '<div class="empty">No data</div>';
  return `
  <div class="page-header"><div class="page-title">Ride history</div><div class="page-sub">${esc(h.summary.note)}</div></div>
  <div class="stats">${statBox('Rides', h.summary.total_rides)}${statBox('Minutes', h.summary.total_minutes)}${statBox('Total charge', money(h.summary.total_charge))}</div>
  <div class="card"><div class="table-wrap"><table>
    <thead><tr><th>Ended</th><th>Bicycle</th><th>From</th><th>To</th><th>Minutes</th><th>Charge</th></tr></thead>
    <tbody>${h.rides.map(r => `
      <tr><td>${fmt(r.end_time)}</td><td class="mono">${esc(r.bicycle_code)}</td><td>${esc(r.start_station_name)}</td>
      <td>${esc(r.end_station_name)}</td><td>${r.duration_minutes}</td><td class="mono">${money(r.charge)}</td></tr>`).join('')
      || '<tr><td colspan="6" class="empty">No completed rides yet</td></tr>'}
    </tbody></table></div></div>`;
}
