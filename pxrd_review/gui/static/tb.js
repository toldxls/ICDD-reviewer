'use strict';
// Tables mode — front end. The third mode: pick a .cif in the folder, see the four publishable
// tables rendered (pxrd_review.tables), write them to review_out/<name>_tables.docx. Reuses the
// app.js helpers and the shared folder panel; the server only ever receives keys and options.

const TBS = { cifs: [], key: null, params: 'gh', ox: '', noh: false, journal: 'manuscript', journals: [], loading: null };

function tbReset() { TBS.key = null; $('#tb-doc').classList.add('hidden'); $('#tb-empty').classList.remove('hidden'); }

async function tbLoad() {
  let r;
  try { r = await fetch('/api/tb/state').then(x => x.json()); } catch (_) { return; }
  const parts = (r.folder || '').split('/').filter(Boolean);
  $('#folder').textContent = r.folder ? ((parts.length > 2 ? '…/' : '') + parts.slice(-2).join('/')) : '(no folder — click to choose)';
  $('#folder-ctl').title = (r.folder || '') + '  — click to change folder';
  $('#folder').dataset.path = r.folder || '';
  TBS.cifs = r.cifs || [];
  if (r.journals && r.journals.length && !TBS.journals.length) {
    TBS.journals = r.journals; TBS.journal = r.default_journal || TBS.journal;
    const sel = $('#tb-journal'); sel.innerHTML = '';
    for (const j of r.journals) sel.append(el('option', { value: j.key }, j.name));
    sel.value = TBS.journal;
  }
  tbRenderList();
}

function tbRenderList() {
  const ul = $('#tb-list'); ul.innerHTML = '';
  if (!TBS.cifs.length) ul.append(el('li', { class: 'muted' }, 'no .cif files in this folder'));
  for (const c of TBS.cifs) {
    ul.append(el('li', { class: c.key === TBS.key ? 'sel' : '', onclick: () => tbOpen(c.key) },
      el('div', { class: 'row1' }, el('span', { class: 'nm' }, c.name)),
      el('div', { class: 'row2' }, c.has_word ? badgeEl({ level: 'fix', label: 'tables.docx written' }) : '')));
  }
}

function tbQuery() {
  const q = new URLSearchParams();
  q.set('params', TBS.params);
  q.set('journal', TBS.journal);
  if (TBS.ox) q.set('ox', TBS.ox);
  if (TBS.noh) q.set('noh', '1');
  return q.toString();
}

async function tbOpen(key) {
  TBS.key = key;
  $('#tb-empty').classList.add('hidden'); $('#tb-doc').classList.remove('hidden');
  $('#tb-name').textContent = key; $('#tb-meta').textContent = ''; $('#tb-notes').textContent = '';
  $('#tb-body').innerHTML = '<div class="empty muted">building tables…</div>';
  tbRenderList();
  let r;
  try { r = await fetch('/api/tb/tables/' + enc(key) + '?' + tbQuery()).then(x => x.json()); }
  catch (ex) { r = { ok: false, error: String(ex) }; }
  if (TBS.key !== key) return;
  if (!r.ok) { $('#tb-body').innerHTML = '<div class="empty muted">' + esc(r.error || 'failed') + '</div>'; return; }
  $('#tb-name').textContent = r.name || key;
  $('#tb-meta').textContent = [r.formula, r.sg].filter(Boolean).join(' · ');
  $('#tb-notes').textContent = (r.notes || []).join(' · ');
  $('#tb-notes').title = (r.notes || []).join('\n');
  $('#tb-body').innerHTML = r.html;            // server-rendered from the tool's own escaped cells
}

document.querySelectorAll('#tb-params button').forEach(b => b.addEventListener('click', () => {
  TBS.params = b.dataset.params;
  document.querySelectorAll('#tb-params button').forEach(x => x.classList.toggle('on', x === b));
  if (TBS.key) tbOpen(TBS.key);
}));
$('#tb-journal').addEventListener('change', e => { TBS.journal = e.target.value; if (TBS.key) tbOpen(TBS.key); });
$('#tb-ox').addEventListener('change', e => { TBS.ox = e.target.value.trim(); if (TBS.key) tbOpen(TBS.key); });
$('#tb-noh').addEventListener('change', e => { TBS.noh = e.target.checked; if (TBS.key) tbOpen(TBS.key); });
$('#tb-word').addEventListener('click', async () => {
  if (!TBS.key) return;
  const b = $('#tb-word'), orig = b.textContent; b.disabled = true; b.textContent = 'Writing…';
  let r;
  try { r = await fetch('/api/tb/word/' + enc(TBS.key) + '?' + tbQuery(), { method: 'POST' }).then(x => x.json()); }
  catch (ex) { r = { ok: false, error: String(ex) }; }
  b.disabled = false; b.textContent = orig;
  msStatus(r.ok ? 'tables written ✓ (review_out/' + TBS.key + '_tables.docx)' : ('failed' + (r.error ? ': ' + r.error : '')));
  if (r.ok) { const row = TBS.cifs.find(c => c.key === TBS.key); if (row) row.has_word = true; tbRenderList(); }
});
$('#tb-open').addEventListener('click', async () => {
  if (!TBS.key) return;
  let ok = false;
  try { ok = (await fetch('/api/tb/open/' + enc(TBS.key), { method: 'POST' }).then(x => x.json())).ok; } catch (_) {}
  if (!ok) msStatus('nothing written yet — click Write .docx first');
});
