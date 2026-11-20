// ─────────────────────────── FORECASTING PAGE ────────────────────────────
function renderAdminForecast() {
  const d = state.data, sum = d.demandSummary || [], runs = d.runs || [];
  const next = new Date(Date.now() + 3600e3); next.setMinutes(0, 0, 0);
  const defStart = new Date(next - next.getTimezoneOffset() * 60000).toISOString().slice(0, 16);   // local time for the input
  return `
  <div class="page-header"><div class="page-title">Demand forecast</div>
    <div class="page-sub">Advice only. Nothing moves automatically.</div></div>

  <div class="card"><div class="card-title">Demand data</div>
    <div class="table-wrap"><table><thead><tr><th>Source</th><th>Rows</th><th>First slot</th><th>Last slot</th></tr></thead>
      <tbody>${sum.map(s => `<tr><td>${statusBadge(s.data_source)}</td><td>${s.rows}</td><td>${fmt(s.first_slot)}</td><td>${fmt(s.last_slot)}</td></tr>`).join('')
        || '<tr><td colspan="4" class="empty">No demand data yet. Generate demo data or build it from rides.</td></tr>'}</tbody></table></div>
    <div class="flex gap-2" style="margin-top:12px">
      <button class="btn btn-ghost" data-action="gen-synthetic">Generate synthetic demo data</button>
      <button class="btn btn-ghost" data-action="sync-demand">Build real data from rides</button>
    </div></div>

  <div class="card" style="margin-top:16px"><div class="card-title">Run a forecast</div>
    <form data-form="run-forecast" class="toolbar">
      <div class="field"><label>First hour</label><input type="datetime-local" name="start_time" value="${defStart}" required></div>
      <div class="field"><label>Hours</label><input type="number" name="hours" min="1" max="24" value="3" required></div>
      <div class="field"><label>Data</label><select name="data_source"><option>Synthetic</option><option>Real</option></select></div>
      <button class="btn btn-primary" type="submit">Run forecast</button>
    </form></div>

  ${d.runDetail ? renderRunDetail(d.runDetail) : ''}

  <div class="card" style="margin-top:16px"><div class="card-title">Past runs</div><div class="table-wrap"><table>
    <thead><tr><th>#</th><th>Created</th><th>Data</th><th>MAE</th><th>Range coverage</th><th>By</th><th></th></tr></thead>
    <tbody>${runs.map(r => `<tr><td class="mono">${r.run_id}</td><td>${fmt(r.created_at)}</td><td>${statusBadge(r.data_source)}</td>
      <td>${r.mae ?? '—'}</td><td>${r.interval_coverage == null ? '—' : r.interval_coverage + '%'}</td><td>${esc(r.created_by)}</td>
      <td><button class="btn btn-ghost btn-sm" data-action="view-run" data-id="${r.run_id}">View</button></td></tr>`).join('')
      || '<tr><td colspan="7" class="empty">No runs yet</td></tr>'}</tbody></table></div></div>`;
}

function renderRunDetail(r) {
  const ev = r.evaluation;
  return `
  <div class="card" style="margin-top:16px">
    <div class="card-title">Run #${r.run.run_id} ${statusBadge(r.run.data_source)}</div>
    ${r.warnings.map(w => `<div class="alert alert-error" style="margin-bottom:8px">${esc(w)}</div>`).join('')}
    <div class="stats">${statBox('MAE', r.run.mae ?? 'n/a')}${statBox('Range coverage', r.run.interval_coverage == null ? 'n/a' : r.run.interval_coverage + '%')}
      ${ev ? statBox('Test days', ev.test_days) : ''}</div>
    <p class="text-muted text-sm">${esc(r.model_note)} The range targets about 80%; report the measured coverage as it is.</p>

    <div class="card-title" style="margin-top:12px">Shortage risk</div>
    <p class="text-muted text-sm">${esc(r.risk_note)}</p>
    <div class="table-wrap"><table><thead><tr><th>Rank</th><th>Station</th><th>Usable bikes</th><th>Peak upper demand</th><th>Score</th><th>Class</th></tr></thead>
      <tbody>${r.station_risks.map(k => `<tr><td>${k.risk_rank}</td><td>${esc(k.station_name)}</td><td>${k.effective_available_fleet}</td>
        <td>${k.upper_demand}</td><td class="mono">${k.shortage_risk_score}</td><td>${statusBadge(k.classification)}</td></tr>`).join('')}</tbody></table></div>

    <div class="card-title" style="margin-top:12px">Balancing advice</div>
    ${r.recommendations.map(x => `<div class="alert alert-success" style="margin-bottom:8px"><b>Move ${x.bicycles_to_move} from ${esc(x.from_station)} to ${esc(x.to_station)}.</b> ${esc(x.reason)}</div>`).join('')
      || '<div class="empty">No moves recommended</div>'}
    ${(r.unmet_shortages || []).map(u => `<div class="alert alert-error" style="margin-bottom:8px">${esc(u.station_name)} still needs ${u.still_needed} more bicycle(s) and no station has spare.</div>`).join('')}

    <div class="card-title" style="margin-top:12px">Hourly forecast</div>
    <div class="table-wrap"><table><thead><tr><th>Station</th><th>Hour</th><th>Predicted</th><th>Range</th></tr></thead>
      <tbody>${r.forecasts.map(f => `<tr><td>${esc(f.station_name)}</td><td>${fmt(f.interval_start)}</td><td>${f.predicted_demand}</td><td class="mono">${f.lower_bound} to ${f.upper_bound}</td></tr>`).join('')}</tbody></table></div>
  </div>`;
}
