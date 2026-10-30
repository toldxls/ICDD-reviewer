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
  epma:   'Pick the probe file (xlsx / csv / txt: the oxide wt% columns and one row per point, or a worked-up sheet with the oxides down column A and their wt% beside them) — or a paper of the folder, whose analytical table is read — and the normalisation basis: O=21 (anions), cations=8, U=5, Si+Al=4 … Additions: H2O=structure:6, CO2=wt:14.02, H2O=difference. The ideal formula, (Cu,Zn)4SO4(OH)6, gives the Ideal column and writes the empirical formula in its layout — live in the .xlsx. Equivalent command: pxrd epma probe.xlsx --basis O=21 --add H2O=structure:6 --ideal "(Cu,Zn)4SO4(OH)6" --xlsx',
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
  TBS.cifs = r.cifs || []; TBS.data = r.data || []; TBS.outputs = r.outputs || []; TBS.pdfs = r.pdfs || []; TBS.subfolders = r.subfolders || [];
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

// ---- sidebar: every list in one order — by name, or by when the file was last saved (remembered, like the Manuscript list's)
function tbSortKey() { try { return localStorage.getItem('pxrd-tb-sort') || 'name'; } catch (_) { return 'name'; } }
function tbSorted(list) {
  const name = (a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base', numeric: true });
  const cmp = { name, newest: (a, b) => (b.mtime || 0) - (a.mtime || 0) || name(a, b),
                oldest: (a, b) => (a.mtime || 0) - (b.mtime || 0) || name(a, b) }[tbSortKey()] || name;
  return [...list].sort(cmp);
}
(() => { const sel = $('#tb-sort'); if (!sel) return; sel.value = tbSortKey(); if (sel.value !== tbSortKey()) sel.value = 'name';
  sel.addEventListener('change', () => { try { localStorage.setItem('pxrd-tb-sort', sel.value); } catch (_) {} tbFillSelects(); tbRenderLists(); }); })();
function tbRenderLists() {
  const ul = $('#tb-list'); ul.innerHTML = '';
  if (!TBS.cifs.length) ul.append(el('li', { class: 'muted' }, 'no .cif files'));
  for (const c of tbSorted(TBS.cifs)) {
    ul.append(el('li', { class: c.key === TBS.key ? 'sel' : '', onclick: () => tbPickCif(c.key) },
      el('div', { class: 'row1' }, el('span', { class: 'nm' }, c.name)),
      el('div', { class: 'row2' }, c.has_word ? badgeEl({ level: 'fix', label: 'tables.docx written' }) : '')));
  }
  const ud = $('#tb-data'); ud.innerHTML = '';
  if (!TBS.data.length) ud.append(el('li', { class: 'muted' }, 'no data files (txt / csv / xlsx)'));
  const used = new Set([tbOpt('epma', 'file'), tbOpt('pxrd', 'obs'), tbOpt('pxrd', 'calc')]);
  for (const d of tbSorted(TBS.data)) {
    ud.append(el('li', { class: used.has(d.key) ? 'sel' : '', onclick: () => tbPickData(d.key, d.kind),
                         title: 'click to use in the ' + (TBS.tab === 'pxrd' ? 'PXRD' : 'EPMA') + ' tab' },
      el('div', { class: 'row1' }, el('span', { class: 'nm' }, d.name)),
      el('div', { class: 'row2 muted' }, d.kind ? 'looks like: ' + { probe: 'probe data', obs: 'observed peaks', calc: 'calculated pattern' }[d.kind] : '')));
  }
  const up = $('#tb-papers'); up.innerHTML = '';
  const epf = tbOpt('epma', 'file');
  if (!TBS.pdfs.length) up.append(el('li', { class: 'muted' }, 'no .pdf or .docx in this folder'));
  for (const p of tbSorted(TBS.pdfs))
    up.append(el('li', { class: epf === 'paper:' + p.key ? 'sel' : '', onclick: () => tbPickData('paper:' + p.key, 'paper'),
                         title: 'read its analytical table in the EPMA tab (locally — nothing is sent anywhere)' },
      el('div', { class: 'row1' }, el('span', { class: 'nm' }, p.name))));
  if (TBS.subfolders && TBS.subfolders.length) {
    // nothing in the folder itself: the lists are not recursive — say where the files are, one click to open one
    const hint = el('li', { class: 'muted' }, 'no .cif or data file in this folder (its subfolders are not searched) — open one of its subfolders:');
    $('#tb-data').replaceChildren(hint);
    for (const f of TBS.subfolders)
      $('#tb-data').append(el('li', { onclick: () => msOpenFolder(f.path), title: 'open ' + f.path },
        el('div', { class: 'row1' }, el('span', { class: 'nm' }, f.name + ' ↘')), el('div', { class: 'row2 muted' }, f.n + ' file' + (f.n === 1 ? '' : 's'))));
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

// the paper last used here opens in the Manuscript mode on the next switch (msLoad takes it): its .pdf key is a file name, the
// manuscript list's key is the stem — a .docx key already is
function tbCarryPaper(key) { window.TB_CARRY = key ? key.replace(/^paper:/, '').replace(/\.pdf$/i, '') : null; }
function tbPickData(key, kind) {
  if (kind === 'paper' || key.startsWith('paper:')) {                // a paper's analytical table: the EPMA tab's input
    if (TBS.tab !== 'epma') tbSetTab('epma');
    tbSetOpt('epma', 'file', key); tbSetOpt('epma', 'block', ''); tbSetOpt('epma', 'region', ''); tbCarryPaper(key);
    tbRenderLists(); tbRender(); return;
  }
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
  fill($('#tb-gd-cif'), tbSorted(TBS.cifs), '(no .cif — measured density only)');
  fill($('#tb-paper'), tbSorted(TBS.pdfs), TBS.pdfs.length ? '(choose a paper)' : '(no .pdf or .docx in the folder)');
  const ep = $('#tb-epma-file'), cur = ep.value;                     // before fill(): a paper's option is not there yet
  fill(ep, tbSorted(TBS.data).filter(d => d.kind !== 'obs' && d.kind !== 'calc'), '(choose the probe file)');
  // the folder's papers too: their analytical table read in place (the same reader as Fill ▸, the paper's means)
  if (TBS.pdfs.length) {
    const g = el('optgroup', { label: 'analytical table of a paper (.pdf / .docx)' });
    for (const p of tbSorted(TBS.pdfs)) g.append(el('option', { value: 'paper:' + p.key }, p.name));
    ep.append(g);
  }
  if (cur && Array.from(ep.options).some(o => o.value === cur)) ep.value = cur;
  fill($('#tb-pxrd-obs'), tbSorted(TBS.data), '(observed peak list)');
  fill($('#tb-pxrd-calc'), tbSorted(TBS.data), '(calculated pattern)');
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
  const paper = ($('#tb-paper') && $('#tb-paper').value) ? '&paper=' + enc($('#tb-paper').value) : '';   // the chosen paper: its table / stated index goes on the workbook's check sheet
  if (tab === 'bvs' && fmt === 'xlsx') return TBS.key ? '/api/tb/bvs/' + enc(TBS.key) + '/export?' + q + paper : null;
  if (tab === 'coords' || tab === 'bvs') return TBS.key ? '/api/tb/word/' + enc(TBS.key) + '?' + q : null;
  if (tab === 'gd') return '/api/tb/gd/export?fmt=' + fmt + '&' + q + (fmt === 'xlsx' ? paper : '');
  if (tab === 'epma') return tbOpt('epma', 'file') ? '/api/tb/epma/' + enc(tbOpt('epma', 'file')) + '/export?fmt=' + fmt + '&' + q : null;
  if (tab === 'pxrd') return '/api/tb/pxrd/export?fmt=' + fmt + '&' + q;
  return null;
}

// ---- rendering
function tbSetTab(tab) {
  TBS.tab = tab;
  document.querySelectorAll('#tb-tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === tab));
  document.querySelectorAll('.tb-pane').forEach(p => p.classList.toggle('hidden', p.dataset.pane !== tab));
  if (tab !== 'epma') tbSheetClose();
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
  if (!r.ok) { tbRenderBody('<div class="empty muted">⚠ ' + esc(r.error || 'failed') + '</div>'); if (tab === 'epma') tbEpmaBlocks({}); return; }
  let status = '';
  if (tab === 'coords' || tab === 'bvs') status = [r.name, r.formula, r.sg].filter(Boolean).join(' · ') + ((r.notes || []).length ? ' — ' + r.notes.join(' · ') : '');
  else if (tab === 'gd') status = (r.summary || []).map(s => s[0] + ' D ' + s[1].toFixed(3) + ': 1 − KP/KC = ' + (s[3] >= 0 ? '+' : '') + s[3].toFixed(3) + ' (' + s[4] + ')').join(' · ') || ('K_C = ' + r.KC.toFixed(4) + ' — give a density for the compatibility');
  else if (tab === 'epma') { status = (r.formula_ideal || r.formula) + ' · factor ' + r.factor.toFixed(4) + ' · charge ' + (r.charge >= 0 ? '+' : '') + r.charge.toFixed(3) + ' · ' + (r.n_points === 1 ? 'one row (the means)' : r.n_points + ' points') + ' · ' + r.source
                                     + ((r.layout_notes || []).length ? ' — ' + r.layout_notes.join(' · ') : ''); TBS.epmaWt = r.wt; tbEpmaBlocks(r); }
  else if (tab === 'pxrd') status = r.n_obs + ' observed, ' + r.n_calc + ' calculated → ' + r.n_rows + ' rows (' + r.n_calc_only + ' calc-only)';
  $('#tb-status').textContent = status; $('#tb-status').title = status;
  const html = r.html + (r.text && tab !== 'coords' && tab !== 'bvs' ? '<details class="tb-text"><summary class="muted">reduction / working (as pxrd prints it)</summary><pre>' + esc(r.text) + '</pre></details>' : '')
             + (tab === 'coords' ? tbSymCodes(r.symcodes || []) : '');
  tbRenderBody(html);
  if (tab === 'bvs' && TBS.mscheck && (TBS.mscheck.fromPaper || TBS.mscheck.key === TBS.key)) tbShowCheck(TBS.mscheck);
  if (tab === 'epma' && TBS.papercheck) tbShowCheck(TBS.papercheck, 'what the paper says, checked against itself');
}

// ---- EPMA: the blocks of analyses a messy workbook holds — the one reduced is chosen here (stored in the hidden data-opt input)
function tbEpmaBlocks(r) {
  const sel = $('#tb-epma-block'), list = r.blocks || [];
  $('#tb-epma-block-l').classList.toggle('hidden', list.length < 2);
  sel.innerHTML = '';
  list.forEach((b, i) => sel.append(el('option', { value: String(i) }, (i + 1) + '. ' + b)));
  if (r.block != null) sel.value = String(r.block);
}
$('#tb-epma-block').addEventListener('change', e => { tbSetOpt('epma', 'block', e.target.value); tbRender(); });
$('#tb-epma-file').addEventListener('change', e => {                      // another file: its own default block, no region (runs before the pane's re-render)
  tbSetOpt('epma', 'block', ''); tbSetOpt('epma', 'region', '');
  if (e.target.value.startsWith('paper:')) tbCarryPaper(e.target.value);
  if (!$('#tb-sheet').classList.contains('hidden')) tbSheetOpen();
});

// ---- the sheet picker: the workbook as the reader sees it. Each block of analyses is shaded and numbered (click: use it);
// a drag over the cells picks a range, read by the same rules (`region`, on its sheet). The panel sits above the table.
const TBSH = { data: null, a: null, b: null, drag: false };
const tbColName = c => { let s = ''; c += 1; while (c) { const m = (c - 1) % 26; s = String.fromCharCode(65 + m) + s; c = (c - m - 1) / 26; } return s; };
const tbRange = (a, b) => tbColName(Math.min(a[1], b[1])) + (Math.min(a[0], b[0]) + 1) + ':' + tbColName(Math.max(a[1], b[1])) + (Math.max(a[0], b[0]) + 1);
async function tbSheetOpen(sheet) {
  const key = tbOpt('epma', 'file'), panel = $('#tb-sheet');
  panel.classList.remove('hidden');
  if (!key || key.startsWith('paper:')) { panel.innerHTML = '<div class="tb-sheet-bar muted">' + (key ? 'a paper has no sheet: its analytical table is read from the text' : 'choose a probe file first') + ' <span class="spacer"></span><button class="ghost mini" data-x>close ✕</button></div>'; panel.querySelector('[data-x]').onclick = tbSheetClose; return; }
  const sh = sheet || (tbOpt('epma', 'region') && tbOpt('epma', 'sheet')) || '';
  let r;
  try { r = await fetch('/api/tb/epma/' + enc(key) + '/grid' + (sh ? '?sheet=' + enc(sh) : '')).then(x => x.json()); } catch (ex) { r = { ok: false, error: String(ex) }; }
  if (!r.ok) { panel.innerHTML = '<div class="tb-sheet-bar">⚠ ' + esc(r.error || 'failed') + '</div>'; return; }
  TBSH.data = r; TBSH.a = TBSH.b = null;
  tbSheetDraw();
}
function tbSheetClose() { $('#tb-sheet').classList.add('hidden'); }
function tbSheetDraw() {
  const r = TBSH.data, panel = $('#tb-sheet');
  const region = tbOpt('epma', 'region'), chosen = tbOpt('epma', 'block');
  const cur = region || tbOpt('epma', 'sheet') ? -1 : (chosen !== '' ? +chosen : r.default);   // a typed sheet numbers its own blocks: no claim then
  const owner = {};                                                       // 'row,col' -> the block shading it (the first listed wins)
  r.blocks.filter(b => b.sheet === r.sheet).forEach(b => {
    const [r0, c0, r1, c1] = b.box;
    const cols = b.cols && b.cols.length ? b.cols : null;                  // only the columns read: not the MW / moles beside a worked-up column
    for (let i = r0; i <= r1; i++) for (let j = c0; j <= c1; j++) if ((!cols || cols.includes(j)) && !((i + ',' + j) in owner)) owner[i + ',' + j] = b;
  });
  const ncol = Math.max(0, ...r.rows.map(x => x.length));
  let h = '<table class="tb-grid"><thead><tr><th class="rh"></th>';
  for (let j = 0; j < ncol; j++) h += '<th>' + tbColName(j) + '</th>';
  h += '</tr></thead><tbody>';
  r.rows.forEach((row, i) => {
    h += '<tr><th class="rh">' + (i + 1) + '</th>';
    for (let j = 0; j < ncol; j++) {
      const v = row[j], b = owner[i + ',' + j];
      const cls = [typeof v === 'number' ? 'num' : '', b ? 'blk b' + (b.i % 6) : '', b && b.i === cur ? 'cur' : ''].filter(Boolean).join(' ');
      const badge = b && b.box[0] === i && b.box[1] === j ? '<span class="bno">' + (b.i + 1) + '</span>' : '';
      h += '<td data-r="' + i + '" data-c="' + j + '"' + (cls ? ' class="' + cls + '"' : '') + (b ? ' title="' + esc((b.i + 1) + '. ' + b.label) + ' — click to use it"' : '') + '>'
         + badge + (v == null ? '' : esc(typeof v === 'number' ? String(+v.toPrecision(6)) : String(v))) + '</td>';
    }
    h += '</tr>';
  });
  h += '</tbody></table>';
  const tabs = r.sheets.length > 1 ? r.sheets.map(t => '<button class="ghost mini' + (t === r.sheet ? ' on' : '') + '" data-sheet="' + esc(t) + '">' + esc(t) + '</button>').join('') : '<span class="muted">' + esc(r.sheet) + '</span>';
  const now = region ? 'reading the range ' + esc(tbOpt('epma', 'sheet')) + '!' + esc(region) : (cur != null && cur >= 0 ? 'reading block ' + (cur + 1) : tbOpt('epma', 'sheet') ? 'reading the sheet ' + esc(tbOpt('epma', 'sheet')) : 'no block found');
  panel.innerHTML = '<div class="tb-sheet-bar">' + tabs + '<span class="muted">· ' + now + ' · click a shaded block to use it, or drag over the cells (shift-click extends) to read a range'
    + (r.truncated ? ' · the first ' + r.rows.length + ' rows / 80 columns shown (' + r.nrows + ' rows)' : '') + '</span><span class="spacer"></span>'
    + '<span id="tb-sheet-pick" class="muted"></span><button class="mini" data-use disabled title="read only these cells (the blocks inside them, by the same rules)">Use range</button>'
    + (region ? '<button class="ghost mini" data-clear title="back to the blocks of the whole file">whole file</button>' : '')
    + '<button class="ghost mini" data-x>close ✕</button></div>'
    + '<div class="tb-sheet-scroll">' + h + '<div class="tb-sel hidden"></div></div>';
  panel.querySelectorAll('[data-sheet]').forEach(b => b.onclick = () => tbSheetOpen(b.dataset.sheet));
  panel.querySelector('[data-x]').onclick = tbSheetClose;
  const clr = panel.querySelector('[data-clear]');
  if (clr) clr.onclick = () => { tbSetOpt('epma', 'region', ''); tbSetOpt('epma', 'sheet', ''); tbSetOpt('epma', 'block', ''); tbRender(); tbSheetDraw(); };
  panel.querySelector('[data-use]').onclick = () => {
    if (!TBSH.a) return;
    tbSetOpt('epma', 'sheet', r.sheet); tbSetOpt('epma', 'region', tbRange(TBSH.a, TBSH.b)); tbSetOpt('epma', 'block', '');
    tbRender(); tbSheetDraw();
  };
  const grid = panel.querySelector('.tb-grid'), sel = panel.querySelector('.tb-sel'), scroll = panel.querySelector('.tb-sheet-scroll');
  const at = e => { const td = e.target.closest('td[data-r]'); return td ? [+td.dataset.r, +td.dataset.c] : null; };
  const paint = () => {
    if (!TBSH.a) { sel.classList.add('hidden'); return; }
    const td = (i, j) => grid.querySelector('td[data-r="' + i + '"][data-c="' + j + '"]');
    const p = td(Math.min(TBSH.a[0], TBSH.b[0]), Math.min(TBSH.a[1], TBSH.b[1])), q = td(Math.max(TBSH.a[0], TBSH.b[0]), Math.max(TBSH.a[1], TBSH.b[1]));
    const o = scroll.getBoundingClientRect(), pr = p.getBoundingClientRect(), qr = q.getBoundingClientRect();
    Object.assign(sel.style, { left: (pr.left - o.left + scroll.scrollLeft) + 'px', top: (pr.top - o.top + scroll.scrollTop) + 'px',
                               width: (qr.right - pr.left) + 'px', height: (qr.bottom - pr.top) + 'px' });
    sel.classList.remove('hidden');
    $('#tb-sheet-pick').textContent = r.sheet + '!' + tbRange(TBSH.a, TBSH.b);
    panel.querySelector('[data-use]').disabled = false;
  };
  grid.addEventListener('mousedown', e => {
    const p = at(e); if (!p || e.button !== 0) return;
    e.preventDefault();
    if (e.shiftKey && TBSH.a) { TBSH.b = p; paint(); return; }             // shift-click: extend to here (scroll between the two corners)
    TBSH.a = TBSH.b = p; TBSH.drag = true; TBSH.moved = false;
  });
  grid.addEventListener('mouseover', e => { if (!TBSH.drag) return; const p = at(e); if (p && (p[0] !== TBSH.b[0] || p[1] !== TBSH.b[1])) { TBSH.b = p; TBSH.moved = true; paint(); } });
  grid.addEventListener('mouseup', e => {
    if (!TBSH.drag) return; TBSH.drag = false;
    const td = e.target.closest('td[data-r]'), b = td && owner[td.dataset.r + ',' + td.dataset.c];
    if (!TBSH.moved && b) {                                                // a click on a shaded block: use that block of the whole file
      TBSH.a = null; paint();
      tbSetOpt('epma', 'region', ''); tbSetOpt('epma', 'sheet', ''); tbSetOpt('epma', 'block', String(b.i));
      tbRender(); tbSheetDraw(); return;
    }
    paint();
  });
  const first = grid.querySelector('td.cur');
  if (first) first.scrollIntoView({ block: 'nearest', inline: 'nearest' });
}
$('#tb-epma-sheet').addEventListener('click', () => $('#tb-sheet').classList.contains('hidden') ? tbSheetOpen() : tbSheetClose());

// ---- the symmetry-code cheat sheet under the bond tables: each superscript, the CIF code it came from, the
// operator with its translation and the bonds that use it; the tooltips say how a code n_klm is read
const TB_SYMTIP = 'A CIF symmetry code is n_klm. n = the operator\'s number in the .cif\'s symmetry-operator list '
  + '(_space_group_symop_operation_xyz). k, l, m = the lattice translation along a, b, c, written as 5 + the shift: '
  + '5 = no shift, 4 = −1, 6 = +1 (3 = −2, 7 = +2). The translation is added to the operator: 3_666 with operator 3 = '
  + '−x, −y, −z gives −x+1, −y+1, −z+1. A bond with no code (. or 1_555) is to the atom as listed: no superscript.';
function tbShift(t) {
  return t.map((v, i) => v ? (v > 0 ? '+' : '−') + Math.abs(v) + ' along ' + 'abc'[i] : '').filter(Boolean).join(', ') || 'no shift';
}
function tbSymCodes(list) {
  const rows = list.map(c => {
    const tip = c.base ? 'operator ' + c.base_n + ' of the .cif (' + c.base + '), translation ' + (c.code.split('_')[1] || '555')
                       + ' = ' + tbShift(c.shift) + ' → ' + c.op : 'not an n_klm code: written as the .cif gives it';
    return '<tr><td><sup>' + c.n + '</sup></td><td title="' + esc(tip) + '"><code>' + esc(c.code) + '</code></td><td>' + esc(c.op)
         + '</td><td>' + esc(c.used.join(', ')) + '</td></tr>';
  }).join('');
  return '<details class="tb-text tb-symcodes" open><summary class="muted" title="' + esc(TB_SYMTIP) + '">symmetry codes — cheat sheet ⓘ</summary>'
       + '<p class="muted" title="' + esc(TB_SYMTIP) + '">CIF code n_klm: operator n of the .cif, then a shift of k−5, l−5, m−5 cells along a, b, c '
       + '(5 = no shift, 4 = −1, 6 = +1). Hover a code for its breakdown.</p>'
       + (rows ? '<table><thead><tr><th>code</th><th>CIF</th><th>operator</th><th>used for</th></tr></thead><tbody>' + rows + '</tbody></table>'
               : '<p class="muted">no symmetry codes: every bond is to an atom as listed in the .cif.</p>')
       + '</details>';
}

// ---- the manuscript's own tables against the .cif (pxrd bv --table): the report goes above the tool's tables
function tbShowCheck(c, what) {
  const body = $('#tb-body'); const old = body.querySelector('.tb-mscheck'); if (old) old.remove();
  body.prepend(el('details', { class: 'tb-text tb-mscheck', open: 'open' }, el('summary', { class: 'muted' }, (what || (c.fromPaper ? 'manuscript table check against the structure the paper itself prints (no .cif of this mineral in the folder)' : 'manuscript table check')) + ' — ' + c.name), el('pre', {}, c.text)));
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
  msStatus('written ✓ review_out/' + r.file + (r.note ? ' — ' + r.note : ''));
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
  if (!key) { msStatus('pick a paper (.pdf or a manuscript .docx) first'); return; }
  tbCarryPaper(key);
  const btn = $('#tb-fill'); const label = btn.textContent; btn.disabled = true; btn.textContent = 'Reading…';
  let r;
  try { r = await fetch('/api/tb/extract?pdf=' + enc(key), { method: 'POST' }).then(x => x.json()); } catch (ex) { r = { ok: false, error: String(ex) }; }
  btn.disabled = false; btn.textContent = label;
  if (!r.ok) { msStatus('could not read the paper' + (r.error ? ': ' + r.error : '')); return; }
  let st = null;                                    // the written data files first, then the inputs
  try { st = await fetch('/api/tb/state').then(x => x.json()); } catch (_) {}
  if (st) { TBS.data = st.data || []; TBS.outputs = st.outputs || []; tbFillSelects(); }
  if (r.fill && r.fill._cif && TBS.cifs.some(c => c.key === r.fill._cif)) TBS.key = r.fill._cif;   // the same mineral's .cif
  TBS.mscheck = r.bvcheck && (r.bv_from_paper || TBS.key) ? { key: r.bv_from_paper ? 'paper:' + key : TBS.key, name: key, text: r.bvcheck, fromPaper: !!r.bv_from_paper } : null;   // the paper's bond-valence table vs that .cif — or vs the structure the paper prints, keyed to no .cif: shown on the Bond valence tab
  TBS.papercheck = r.checks ? { name: key, text: r.checks } : null;                            // what was read and what vouched for it: shown on the EPMA tab
  document.querySelectorAll('.tb-opts .opt[data-verified]').forEach(l => l.removeAttribute('data-verified'));
  for (const tab of Object.keys(r.fill || {})) {
    if (tab.startsWith('_')) continue;
    for (const [k, v] of Object.entries(r.fill[tab])) {
      if (tab === 'bvs' && k === 'params') document.querySelectorAll('#tb-params button').forEach(b => b.classList.toggle('on', b.dataset.params === v));
      tbSetOpt(tab, k, v);
      tbMark(tab, k, ((r.status || {})[tab] || {})[k]);
    }
  }
  tbRenderLists();
  const notes = r.notes || [];
  msStatus((r.readers || 'filled from the paper') + ' — ✓ an oracle agrees, ? unverified, ✗ disagrees');
  if (r.fill && r.fill.epma && r.fill.epma.file) tbSetTab('epma'); else tbRender();
  $('#tb-status').textContent = 'filled from ' + key + (notes.length ? ' — ' + notes.join(' · ') : '');
  $('#tb-status').title = notes.join('\n');
}
$('#tb-fill').addEventListener('click', () => tbFillFromPaper());   // not the event: a truthy pdfKey would reset the select
// the mark beside a filled input: what vouched for the value (an oracle agrees / disagrees, or nothing could)
const TB_MARK_TITLE = { agrees: 'an oracle agrees with this reading', disagrees: 'an oracle disagrees with this reading — see the checks', unverified: 'read, but not verified — check it', nooracle: 'read; nothing to check it against' };
function tbMark(tab, name, status) {
  const i = tbPane(tab).querySelector('[data-opt="' + name + '"]'); if (!i || !status || status === 'none') return;
  const lab = i.closest('.opt'); if (!lab) return;
  lab.setAttribute('data-verified', status); lab.title = TB_MARK_TITLE[status] || status;
}
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
  else if (tab === 'epma') {
    const f = tbOpt('epma', 'file'), pp = TBS.pdfs.find(p => 'paper:' + p.key === f);    // a paper's table writes <stem>_docx / _paper, as the server names it
    const st = pp ? pp.name.replace(/\.[^.]+$/, '') + (/\.docx$/i.test(pp.name) ? '_docx' : '_paper') : (f || '').replace(/\.[^.]+$/, '');
    if (f) cands = [st + '_epma.docx', st + '_epma.xlsx'];
  }
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
