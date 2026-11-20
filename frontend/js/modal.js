// ── MODAL ─────────────────────────────────────────────────────────────────
function renderModal() {
  const m = state.modal;
  if (m.type === 'bike-history') return `
  <div class="modal-overlay" id="modal-overlay"><div class="modal">
    <div class="modal-title">History: ${esc(m.code)}</div>
    <div class="table-wrap"><table><thead><tr><th>When</th><th>Status</th><th>Condition</th><th>By</th></tr></thead>
      <tbody>${m.rows.map(h => `<tr><td>${fmt(h.changed_at)}</td><td>${esc(h.old_status || '—')} → ${esc(h.new_status || '—')}</td>
        <td>${esc(h.old_condition || '—')} → ${esc(h.new_condition || '—')}</td><td>${esc(h.changed_by || 'System')}</td></tr>`).join('')
        || '<tr><td colspan="4" class="empty">No changes logged</td></tr>'}</tbody></table></div>
    <button class="btn btn-ghost" id="close-modal" style="margin-top:12px">Close</button>
  </div></div>`;
  return '';
}
