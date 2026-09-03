'use strict';
// Tables mode — front end. Five tabs over one folder: atom coordinates & bonds and the bond-valence
// table from a .cif (pxrd_review.tables), Gladstone–Dale compatibility (pxrd_review.gd), the EPMA
// reduction from a probe file (pxrd_review.epma) and the combined PXRD table from an observed peak
// list + calculated pattern (pxrd_review.pxrd_table). Each tab renders the same table the CLI
// prints and writes the same review_out/<name>_<tab>.docx / .xlsx. The server only ever receives
// file KEYS (names it listed itself) and option strings; every option is re-validated there.

const TBS = { cifs: [], data: [], outputs: [], pdfs: [], key: null, tab: 'coords', journal: 'manuscript', journals: [],
              opts: {}, last: {}, epmaWt: null, seq: 0, saveTimer: null };
const TB_TABS = ['coords', 'bvs', 'gd', 'epma', 'pxrd'];
const TB_HINT = {
  coords: 'Select a .cif in the sidebar — Table 1 (coordinates and displacement parameters), Table 2 (selected bond distances with symmetry codes) and the hydrogen-bond table are built from it. Equivalent command: pxrd tables mineral.cif --word',
  bvs:    'Select a .cif in the sidebar — the bond-valence analysis, one anion column per cation row. Equivalent command: pxrd tables mineral.cif (Table 4) / pxrd bv mineral.cif',
  gd:     'Give the composition (ideal formula as atoms per formula unit, or wt% oxides — the EPMA tab can hand its means over), the mean refractive index and a density (measured, or from a .cif and Z). Equivalent command: pxrd gd --formula "Ca=1,U=2,H2O=4" --n 1.70 --cif mineral.cif',
  epma:   'Pick the probe file (xlsx / csv / txt with the oxide wt% columns and one row per point) and the normalisation basis: O=21 (anions), cations=8, U=5, Si+Al=4 … Additions: H2O=structure:6, CO2=wt:14.02, H2O=difference. Equivalent command: pxrd epma probe.xlsx --basis O=21 --add H2O=structure:6 --xlsx',
  pxrd:   'Pick the observed peak list (JADE export, or any d / I list) and the calculated pattern; lines are matched by hkl then by d, unobserved reflections within the tolerance join the nearest strong peak, and the eight strongest observed lines are bold. Equivalent command: pxrd pxrd obs.txt calc.txt --dmin 1.45 --word',
};

function tbReset() { TBS.key = null; TBS.epmaWt = null; TBS.last = {}; tbRenderBody(); }

async function tbLoad() {
  let r;
  try { r = await fetch('/api/tb/state').then(x => x.json()); } catch (_) { return; }
  const parts = (r.folder || '').split('/').filter(Boolean);
  $('#folder').textContent = r.folder ? ((parts.length > 2 ? '…/' : '') + parts.slice(-2).join('/')) : '(no folder — click to choose)';
  $('#folder-ctl').title = (r.folder || '') + '  — click to change folder';
  $('#folder').dataset.path = r.folder || '';
  TBS.cifs = r.cifs || []; TBS.data = r.data || []; TBS.outputs = r.outputs || []; TBS.pdfs = r.pdfs || [];
  if (r.journals && r.journals.length && !TBS.journals.length) {
    TBS.journals = r.journals; TBS.journal = r.default_journal || TBS.journal;
    try { const j = localStorage.getItem('pxrd-tb-journal'); if (j && r.journals.some(x => x.key === j)) TBS.journal = j; } catch (_) {}
    const sel = $('#tb-journal'); sel.innerHTML = '';
    for (const j of r.journals) sel.append(el('option', { value: j.key }, j.name));
    sel.value = TBS.journal;
  }
  if (TBS.key && !TBS.cifs.some(c => c.key === TBS.key)) TBS.key = null;
  if (!TBS.key && TBS.cifs.length === 1) TBS.key = TBS.cifs[0].key;
  tbFillSelects();
  tbApplyOpts(r.opts || {});
  tbRenderLists();
  tbRender();
}

// ---- sidebar
function tbRenderLists() {
  const ul = $('#tb-list'); ul.innerHTML = '';
  if (!TBS.cifs.length) ul.append(el('li', { class: 'muted' }, 'no .cif files'));
  for (const c of TBS.cifs) {
    ul.append(el('li', { class: c.key === TBS.key ? 'sel' : '', onclick: () => tbPickCif(c.key) },
      el('div', { class: 'row1' }, el('span', { class: 'nm' }, c.name)),
      el('div', { class: 'row2' }, c.has_word ? badgeEl({ level: 'fix', label: 'tables.docx written' }) : '')));
  }
  const ud = $('#tb-data'); ud.innerHTML = '';
  if (!TBS.data.length) ud.append(el('li', { class: 'muted' }, 'no data files (txt / csv / xlsx)'));
  const used = new Set([tbOpt('epma', 'file'), tbOpt('pxrd', 'obs'), tbOpt('pxrd', 'calc')]);
  for (const d of TBS.data) {
    ud.append(el('li', { class: used.has(d.key) ? 'sel' : '', onclick: () => tbPickData(d.key, d.kind),
                         title: 'click to use in the ' + (TBS.tab === 'pxrd' ? 'PXRD' : 'EPMA') + ' tab' },
      el('div', { class: 'row1' }, el('span', { class: 'nm' }, d.name)),
      el('div', { class: 'row2 muted' }, d.kind ? 'looks like: ' + { probe: 'probe data', obs: 'observed peaks', calc: 'calculated pattern' }[d.kind] : '')));
  }
  const uo = $('#tb-outputs'); uo.innerHTML = '';
  if (!TBS.outputs.length) uo.append(el('li', { class: 'muted' }, 'nothing written yet'));
  for (const o of TBS.outputs) uo.append(el('li', { onclick: () => tbOpenFile(o), title: 'open review_out/' + o }, el('span', { class: 'nm' }, o + ' ↗')));
}

function tbPickCif(key) {
  TBS.key = key;
  const sel = $('#tb-gd-cif'); if (sel) { sel.value = key; tbSetOpt('gd', 'cif', key); }
  if (TBS.tab === 'gd') tbRender(); else if (TBS.tab !== 'coords' && TBS.tab !== 'bvs') tbSetTab('coords'); else tbRender();
  tbRenderLists();
}

function tbPickData(key, kind) {
  if (TBS.tab === 'pxrd') {
    const slot = kind === 'calc' ? 'calc' : (kind === 'obs' ? 'obs' : (tbOpt('pxrd', 'obs') ? 'calc' : 'obs'));
    tbSetOpt('pxrd', slot, key);
  } else {
    if (TBS.tab !== 'epma') tbSetTab('epma');
    tbSetOpt('epma', 'file', key);
  }
  tbRenderLists(); tbRender();
}

// ---- options: every input in a pane carries data-opt; the values round-trip through review_out/tables_opts.json
function tbPane(tab) { return document.querySelector('.tb-pane[data-pane="' + tab + '"]'); }
function tbInputs(tab) { return Array.from(tbPane(tab).querySelectorAll('[data-opt]')); }
function tbOpt(tab, name) {
  const i = tbPane(tab).querySelector('[data-opt="' + name + '"]');
  if (!i) return '';
  return i.type === 'checkbox' ? (i.checked ? '1' : '') : (i.value || '').trim();
}
function tbSetOpt(tab, name, value) {
  const i = tbPane(tab).querySelector('[data-opt="' + name + '"]');
  if (!i) return;
  if (i.type === 'checkbox') i.checked = value === '1' || value === true; else i.value = value == null ? '' : String(value);
  tbSaveOpts(tab);
}
function tbCollect(tab) {
  const o = {};
  for (const i of tbInputs(tab)) { const v = i.type === 'checkbox' ? (i.checked ? '1' : '') : (i.value || '').trim(); if (v) o[i.dataset.opt] = v; }
  return o;
}
function tbApplyOpts(saved) {
  for (const tab of TB_TABS) {
    const o = saved[tab] || {};
    for (const i of tbInputs(tab)) {
      if (!(i.dataset.opt in o)) continue;
      if (i.type === 'checkbox') i.checked = o[i.dataset.opt] === '1';
      else if (i.tagName === 'SELECT') { if (Array.from(i.options).some(x => x.value === o[i.dataset.opt])) i.value = o[i.dataset.opt]; }
      else i.value = o[i.dataset.opt];
    }
    if (tab === 'bvs') document.querySelectorAll('#tb-params button').forEach(b => b.classList.toggle('on', b.dataset.params === (o.params || 'gh')));
  }
  if (saved.gd && saved.gd.cif && !TBS.key && TBS.cifs.some(c => c.key === saved.gd.cif)) TBS.key = saved.gd.cif;
}
function tbSaveOpts(tab) {
  clearTimeout(TBS.saveTimer);
  TBS.saveTimer = setTimeout(() => {
    fetch('/api/tb/opts/' + tab, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(tbCollect(tab)) }).catch(() => {});
  }, 400);
}
function tbFillSelects() {
  const fill = (sel, items, blank) => {
    const cur = sel.value; sel.innerHTML = '';
    if (blank) sel.append(el('option', { value: '' }, blank));
    for (const it of items) sel.append(el('option', { value: it.key }, it.name));
    if (Array.from(sel.options).some(o => o.value === cur)) sel.value = cur;
  };
  fill($('#tb-gd-cif'), TBS.cifs, '(no .cif — measured density only)');
  fill($('#tb-paper'), TBS.pdfs, TBS.pdfs.length ? '(choose a paper)' : '(no .pdf in the folder)');
  fill($('#tb-epma-file'), TBS.data.filter(d => d.kind !== 'obs' && d.kind !== 'calc'), '(choose the probe file)');
  fill($('#tb-pxrd-obs'), TBS.data, '(observed peak list)');
  fill($('#tb-pxrd-calc'), TBS.data, '(calculated pattern)');
}

// ---- query strings per tab
function tbQuery(tab) {
  const q = new URLSearchParams(); q.set('journal', TBS.journal);
  const o = tbCollect(tab);
  if (tab === 'coords' || tab === 'bvs') {
    // the bond-valence pane's options shape every table of the .cif (the hydrogen-bond table too)
    const b = tbCollect('bvs');
    q.set('params', b.params || 'gh');
    for (const k of ['ox', 'cutoff', 'hb', 'hmax', 'donors', 'hbp', 'u6set']) if (b[k]) q.set(k, b[k]);
    if (o.noh) q.set('noh', '1');
    q.set('part', tab);
  }
  else for (const [k, v] of Object.entries(o)) q.set(k, v);
  if (tab === 'gd') { if (o.mode === 'wt') q.delete('formula'); else q.delete('wt'); q.delete('mode'); }
  return q.toString();
}
function tbUrl(tab) {
  if (tab === 'coords' || tab === 'bvs') return TBS.key ? '/api/tb/tables/' + enc(TBS.key) + '?' + tbQuery(tab) : null;
  if (tab === 'gd') return (tbOpt('gd', 'formula') || tbOpt('gd', 'wt')) && tbOpt('gd', 'n') ? '/api/tb/gd?' + tbQuery('gd') : null;
  if (tab === 'epma') return tbOpt('epma', 'file') ? '/api/tb/epma/' + enc(tbOpt('epma', 'file')) + '?' + tbQuery('epma') : null;
  if (tab === 'pxrd') return tbOpt('pxrd', 'obs') && tbOpt('pxrd', 'calc') ? '/api/tb/pxrd?' + tbQuery('pxrd') : null;
  return null;
}
function tbExportUrl(tab, fmt) {
  const q = tbQuery(tab);
  if (tab === 'bvs' && fmt === 'xlsx') return TBS.key ? '/api/tb/bvs/' + enc(TBS.key) + '/export?' + q : null;
  if (tab === 'coords' || tab === 'bvs') return TBS.key ? '/api/tb/word/' + enc(TBS.key) + '?' + q : null;
  if (tab === 'gd') return '/api/tb/gd/export?fmt=' + fmt + '&' + q;
  if (tab === 'epma') return tbOpt('epma', 'file') ? '/api/tb/epma/' + enc(tbOpt('epma', 'file')) + '/export?fmt=' + fmt + '&' + q : null;
  if (tab === 'pxrd') return '/api/tb/pxrd/export?fmt=' + fmt + '&' + q;
  return null;
}

// ---- rendering
function tbSetTab(tab) {
  TBS.tab = tab;
  document.querySelectorAll('#tb-tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === tab));
  document.querySelectorAll('.tb-pane').forEach(p => p.classList.toggle('hidden', p.dataset.pane !== tab));
  try { localStorage.setItem('pxrd-tb-tab', tab); } catch (_) {}
  tbRenderLists(); tbRender();
}
function tbRenderBody(html) {
  const body = $('#tb-body');
  if (html !== undefined) { body.innerHTML = html; return; }
  body.innerHTML = '<div class="empty muted"><p>' + esc(TB_HINT[TBS.tab] || '') + '</p></div>';
}
async function tbRender() {
  const tab = TBS.tab, url = tbUrl(tab), seq = ++TBS.seq;
  $('#tb-status').textContent = '';
  if (!url) { tbRenderBody(); return; }
  $('#tb-body').innerHTML = '<div class="empty muted">building…</div>';
  let r;
  try { r = await fetch(url).then(x => x.json()); } catch (ex) { r = { ok: false, error: String(ex) }; }
  if (seq !== TBS.seq || tab !== TBS.tab) return;
  if (!r.ok) { tbRenderBody('<div class="empty muted">⚠ ' + esc(r.error || 'failed') + '</div>'); return; }
  let status = '';
  if (tab === 'coords' || tab === 'bvs') status = [r.name, r.formula, r.sg].filter(Boolean).join(' · ') + ((r.notes || []).length ? ' — ' + r.notes.join(' · ') : '');
  else if (tab === 'gd') status = (r.summary || []).map(s => s[0] + ' D ' + s[1].toFixed(3) + ': 1 − KP/KC = ' + (s[3] >= 0 ? '+' : '') + s[3].toFixed(3) + ' (' + s[4] + ')').join(' · ') || ('K_C = ' + r.KC.toFixed(4) + ' — give a density for the compatibility');
  else if (tab === 'epma') { status = r.formula + ' · factor ' + r.factor.toFixed(4) + ' · charge ' + (r.charge >= 0 ? '+' : '') + r.charge.toFixed(3) + ' · ' + r.n_points + ' points'; TBS.epmaWt = r.wt; }
  else if (tab === 'pxrd') status = r.n_obs + ' observed, ' + r.n_calc + ' calculated → ' + r.n_rows + ' rows (' + r.n_calc_only + ' calc-only)';
  $('#tb-status').textContent = status; $('#tb-status').title = status;
  const html = r.html + (r.text && tab !== 'coords' && tab !== 'bvs' ? '<details class="tb-text"><summary class="muted">reduction / working (as pxrd prints it)</summary><pre>' + esc(r.text) + '</pre></details>' : '');
  tbRenderBody(html);
}

async function tbExport(tab, fmt) {
  const url = tbExportUrl(tab, fmt);
  if (!url) { msStatus('nothing to write yet — pick the inputs first'); return; }
  const btn = tbPane(tab).querySelector('[data-export="' + fmt + '"]'), orig = btn && btn.textContent;
  if (btn) { btn.disabled = true; btn.textContent = 'Writing…'; }
  let r;
  try { r = await fetch(url, { method: 'POST' }).then(x => x.json()); } catch (ex) { r = { ok: false, error: String(ex) }; }
  if (btn) { btn.disabled = false; btn.textContent = orig; }
  if (!r.ok) { msStatus('failed' + (r.error ? ': ' + r.error : '')); return; }
  TBS.last[tab] = r.file;
  msStatus('written ✓ review_out/' + r.file);
  if (!TBS.outputs.includes(r.file)) TBS.outputs.push(r.file), TBS.outputs.sort();
  if ((tab === 'coords' || tab === 'bvs') && fmt !== 'xlsx') { const row = TBS.cifs.find(c => c.key === TBS.key); if (row) row.has_word = true; }
  tbRenderLists();
}

// ---- fill from paper: the extractor's inputs go into the tabs' fields (data files into review_out)
async function tbFillFromPaper(pdfKey) {
  if (pdfKey) {
    if (!TBS.pdfs.length) { try { const st = await fetch('/api/tb/state').then(x => x.json()); TBS.pdfs = st.pdfs || []; tbFillSelects(); } catch (_) {} }
    $('#tb-paper').value = pdfKey;
  }
  const key = $('#tb-paper').value;
  if (!key) { msStatus('pick a paper (.pdf) first'); return; }
  const btn = $('#tb-fill'); btn.disabled = true; btn.textContent = 'Reading…';
  let r;
  try { r = await fetch('/api/tb/extract?pdf=' + enc(key), { method: 'POST' }).then(x => x.json()); } catch (ex) { r = { ok: false, error: String(ex) }; }
  btn.disabled = false; btn.textContent = 'Fill ▸';
  if (!r.ok) { msStatus('could not read the paper' + (r.error ? ': ' + r.error : '')); return; }
  let st = null;                                    // the written data files first, then the inputs
  try { st = await fetch('/api/tb/state').then(x => x.json()); } catch (_) {}
  if (st) { TBS.data = st.data || []; TBS.outputs = st.outputs || []; tbFillSelects(); }
  if (r.fill && r.fill._cif && TBS.cifs.some(c => c.key === r.fill._cif)) TBS.key = r.fill._cif;   // the same mineral's .cif
  for (const tab of Object.keys(r.fill || {})) {
    if (tab.startsWith('_')) continue;
    for (const [k, v] of Object.entries(r.fill[tab])) {
      if (tab === 'bvs' && k === 'params') document.querySelectorAll('#tb-params button').forEach(b => b.classList.toggle('on', b.dataset.params === v));
      tbSetOpt(tab, k, v);
    }
  }
  tbRenderLists();
  const notes = r.notes || [];
  msStatus('filled from the paper — check each tab; the EPMA basis and additions follow what the paper states');
  if (r.fill && r.fill.epma && r.fill.epma.file) tbSetTab('epma'); else tbRender();
  $('#tb-status').textContent = 'filled from ' + key + (notes.length ? ' — ' + notes.join(' · ') : '');
  $('#tb-status').title = notes.join('\n');
}
$('#tb-fill').addEventListener('click', tbFillFromPaper);
async function tbOpenFile(name) {
  let ok = false;
  try { ok = (await fetch('/api/tb/open?file=' + enc(name), { method: 'POST' })).ok; } catch (_) {}
  if (!ok) msStatus('could not open ' + name);
}

// ---- wiring
document.querySelectorAll('#tb-tabs button').forEach(b => b.addEventListener('click', () => tbSetTab(b.dataset.tab)));
$('#tb-journal').addEventListener('change', e => { TBS.journal = e.target.value; try { localStorage.setItem('pxrd-tb-journal', TBS.journal); } catch (_) {} tbRender(); });
document.querySelectorAll('#tb-params button').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('#tb-params button').forEach(x => x.classList.toggle('on', x === b));
  tbSetOpt('bvs', 'params', b.dataset.params); tbRender();
}));
document.querySelectorAll('#tb-gd-mode button').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('#tb-gd-mode button').forEach(x => x.classList.toggle('on', x === b));
  tbSetOpt('gd', 'mode', b.dataset.gdmode);
  $('#tb-gd-formula').classList.toggle('hidden', b.dataset.gdmode === 'wt'); $('#tb-gd-wt').classList.toggle('hidden', b.dataset.gdmode !== 'wt');
  tbRender();
}));
document.querySelectorAll('.tb-pane').forEach(p => {
  p.addEventListener('change', e => {
    if (!e.target.dataset.opt) return;
    tbSaveOpts(p.dataset.pane);
    if (p.dataset.pane === 'gd' && e.target.dataset.opt === 'cif' && e.target.value) TBS.key = e.target.value;
    tbRenderLists(); tbRender();
  });
  p.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target.dataset.opt) e.target.blur(); });
});
document.querySelectorAll('[data-export]').forEach(b => b.addEventListener('click', () => tbExport(b.closest('.tb-pane').dataset.pane, b.dataset.export)));
function tbOutputName(tab) {
  // the file this tab's inputs would write (so "open" works after a reload, not only after a Write)
  if (TBS.last[tab]) return TBS.last[tab];
  const stem = s => (s || '').replace(/[^\w.-]+/g, '_').replace(/^_+|_+$/g, '');
  let cands = [];
  if (tab === 'coords' || tab === 'bvs') cands = TBS.key ? [TBS.key + '_tables.docx'] : [];
  else if (tab === 'epma') { const f = tbOpt('epma', 'file'); if (f) { const st = f.replace(/\.[^.]+$/, ''); cands = [st + '_epma.docx', st + '_epma.xlsx']; } }
  else if (tab === 'gd') { const st = stem(tbOpt('gd', 'name')) || 'gd'; cands = [st + '_gd.docx', st + '_gd.xlsx']; }
  else if (tab === 'pxrd') { const st = stem(tbOpt('pxrd', 'name')) || (tbOpt('pxrd', 'obs') || '').replace(/\.[^.]+$/, ''); if (st) cands = [st + '_pxrd.docx', st + '_pxrd.xlsx']; }
  return cands.find(n => TBS.outputs.includes(n)) || null;
}
document.querySelectorAll('[data-open]').forEach(b => b.addEventListener('click', () => {
  const name = tbOutputName(b.closest('.tb-pane').dataset.pane);
  if (name) tbOpenFile(name); else msStatus('nothing written yet — click Write first');
}));
$('#tb-gd-from-epma').addEventListener('click', () => {
  if (!TBS.epmaWt) { msStatus('run the EPMA tab first — its mean wt% values are handed over from there'); return; }
  document.querySelector('#tb-gd-mode button[data-gdmode="wt"]').click();
  tbSetOpt('gd', 'wt', TBS.epmaWt.map(([k, v]) => k + '=' + v).join(','));
  tbRender();
});
try { const t = localStorage.getItem('pxrd-tb-tab'); if (TB_TABS.includes(t)) tbSetTab(t); } catch (_) {}
