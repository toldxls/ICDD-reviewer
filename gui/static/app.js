'use strict';
// Review-mode GUI — front end. Talks only to the local review_gui.py backend.
// Renders the dashboard + the per-entry evidence panes and saves triage verdicts.
// Never edits a docx; POSTs verdicts to /api/triage which writes a sidecar only.

const S = {
  entries: [],        // dashboard rows
  key: null,          // current entry key
  a: null,            // current analysis
  t: null,            // current triage object
  view: 'fixes',      // dashboard lens: fixes | attention | clean | all
  pdfPage: 0,
  pdfTerms: [],
  saveTimer: null,
};

// ---- tiny DOM helper -------------------------------------------------------
function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  if (attrs) for (const k in attrs) {
    if (k === 'class') e.className = attrs[k];
    else if (k === 'html') e.innerHTML = attrs[k];
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), attrs[k]);
    else if (attrs[k] != null) e.setAttribute(k, attrs[k]);
  }
  for (const c of kids) if (c != null) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
}
const $ = sel => document.querySelector(sel);
const esc = s => (s == null ? '' : String(s));

// ---- dashboard -------------------------------------------------------------
async function loadEntries() {
  const r = await fetch('/api/entries').then(x => x.json());
  const parts = (r.folder || '').split('/').filter(Boolean);
  $('#folder').textContent = (parts.length > 2 ? '…/' : '') + parts.slice(-2).join('/');
  $('#folder').title = r.folder || '';
  S.entries = r.entries;
  renderList();
}

function hasAttn(e) { return e.badges.some(b => b.level === 'danger' || b.level === 'warn'); }
function matchesView(e) {
  if (S.view === 'all') return true;
  if (S.view === 'fixes') return e.fixes > 0;
  if (S.view === 'attention') return hasAttn(e);
  if (S.view === 'clean') return e.fixes === 0 && !hasAttn(e);
  return true;
}

function renderList() {
  const ul = $('#entry-list'); ul.innerHTML = '';
  const q = $('#filter').value.toLowerCase();
  let shown = 0, fixes = 0;
  for (const e of S.entries) {
    if (e.fixes > 0) fixes++;
    if (!matchesView(e)) continue;
    if (q && !((e.name || '').toLowerCase().includes(q) || (e.eid || '').toLowerCase().includes(q))) continue;
    shown++;
    const li = el('li', { class: (e.key === S.key ? 'sel ' : '') + (e.reviewed ? 'reviewed' : ''),
                          onclick: () => openEntry(e.key) },
      el('div', { class: 'row1' },
        e.reviewed ? el('span', { class: 'reviewed-tick' }, '✓') : null,
        el('span', { class: 'nm' }, e.name || e.key),
        el('span', { class: 'id' }, e.eid || '')),
      el('div', { class: 'row2' }, ...e.badges.map(badgeEl)));
    ul.append(li);
  }
  $('#counts').textContent = `${shown} shown · ${fixes}/${S.entries.length} with fixes`;
}

function badgeEl(b) { return el('span', { class: 'badge ' + b.level }, b.label); }

// ---- open an entry ---------------------------------------------------------
async function openEntry(key) {
  S.key = key;
  const r = await fetch('/api/entry/' + encodeURIComponent(key)).then(x => x.json());
  S.a = r.analysis;
  S.t = normalizeTriage(r.triage);
  $('#empty').classList.add('hidden');
  $('#entry').classList.remove('hidden');
  renderHead();
  renderFindings();
  renderDocx();
  renderMindat();
  // default PDF focus = the cell evidence
  if (S.a.pdf) { S.pdfTerms = S.a.pdf.terms || []; S.pdfPage = S.a.pdf.evidence_page || 0; }
  else { S.pdfTerms = []; S.pdfPage = 0; }
  renderPdf();
  focusFinding('cell');
  renderList();
}

function normalizeTriage(t) {
  t = t || {};
  t.findings = t.findings || {};
  return t;
}

// ---- head ------------------------------------------------------------------
function renderHead() {
  const a = S.a;
  $('#e-name').textContent = a.name || a.key;
  $('#e-eid').textContent = a.eid || '';
  $('#e-badges').replaceChildren(...a.badges.map(badgeEl));
  const f = a.files;
  const files = ['pdf', 'cif', 'dft'].map(k => `${k}${f[k] ? '✓' : '✗'}`).join(' ');
  $('#e-files').textContent = files;
  $('#e-output').textContent = 'writes: ' + a.preview.output_name;
  $('#e-accept').textContent = 'tool Accept: ' + a.preview.accept;
  // reviewer agree/disagree with the tool's Accept decision (recorded in triage)
  const at = $('#e-accept-triage'); at.innerHTML = '';
  const mkA = (v, lbl) => el('button', {
    class: 'tbtn ' + (v === 'agree' ? 'confirm' : 'look') + (S.t.accept === v ? ' on' : ''),
    onclick: () => { S.t.accept = (S.t.accept === v ? null : v); saveTriage(); renderHead(); }
  }, lbl);
  at.append(mkA('agree', '✓ agree'), mkA('disagree', '✗ disagree'));
  // live preview of what a rerun will write into this docx after triage
  const pv = postTriagePreview();
  $('#e-preview').textContent = pv.write
    ? `rerun writes ${pv.write}${pv.suppress ? ` · ${pv.suppress} suppressed` : ''}`
    : (pv.suppress ? `${pv.suppress} suppressed (clean)` : 'nothing to write');
  const rv = $('#e-reviewed'); rv.checked = !!S.t.reviewed;
  rv.onchange = () => { S.t.reviewed = rv.checked; saveTriage(); renderList(); };
}

// count what a rerun will actually write into the docx given current triage
function postTriagePreview() {
  const a = S.a, t = S.t;
  const dism = fk => (t.findings[fk] || {}).verdict === 'dismiss';
  let write = 0, suppress = 0;
  const tally = fk => { dism(fk) ? suppress++ : write++; };
  const cs = a.cell.status;
  if (cs === 'match') { for (const ax in a.params) tally('param:' + ax); }
  else tally('cell');                                   // investigate / no-match comment
  if (a.lam && a.lam[0] === 'flag') tally('lam');       // anode mismatch
  for (const f of a.findings) if (f.written) tally('f' + f.idx);
  return { write, suppress };
}

// ---- findings pane ---------------------------------------------------------
function renderFindings() {
  const a = S.a, body = $('#findings-body'); body.innerHTML = '';
  const rows = [];

  // cell verdict (pseudo-finding)
  const cs = a.cell.status;
  let cellMsg;
  if (cs === 'match') {
    const m = a.cell;
    cellMsg = `value match to a reported cell — ${m.nmatch}/${m.ncomp} axes, ${m.mode}, Σ|Δ|=${(m.dev||0).toFixed(4)} Å`;
  } else if (cs === 'investigate') {
    cellMsg = `no exact cell match — closest off by Σ|Δ|=${(a.cell.dev||0).toFixed(4)} Å over ${a.cell.ncomp} axes — INVESTIGATE`;
  } else if (cs === 'nocell') {
    cellMsg = 'no cell parsed from the .pdf (table-only?) — “No matching .pdf cell found.” is written';
  } else if (cs === 'nopdf') {
    cellMsg = 'no .pdf paired — cell cannot be validated';
  } else cellMsg = cs;
  const cellWritten = (cs !== 'match') || Object.keys(a.params).length > 0;
  rows.push(fRow('cell', 'verdict', 'cell', cellMsg, cellWritten, 'cell:' + cs));

  // per-parameter issues (these become docx highlights+comments)
  for (const ax in a.params) {
    const parts = a.params[ax].map(([kind, note]) => `${kind}: ${note}`).join('; ');
    rows.push(fRow('param:' + ax, 'flag', 'cell ' + ax, parts, true, 'cell:' + ax));
  }

  // radiation / wavelength verdict (anode mismatch = major; verify/unrec = low value)
  if (a.lam) {
    const [st, msg] = a.lam;
    if (st !== 'ok') {
      const sev = st === 'flag' ? 'flag' : (st === 'calc' ? 'note' : 'info');
      rows.push(fRow('lam', sev, 'radiation', msg, st === 'flag', 'radiation', null, st !== 'flag'));
    }
  }

  // extra-check findings (wavelength-family demoted to minor)
  for (const f of a.findings) {
    rows.push(fRow('f' + f.idx, f.sev, f.code, f.msg, f.written, f.anchor, f.code, !f.major));
  }

  for (const r of rows) body.append(r);
  $('#f-count').textContent = `(${rows.length})`;
}

function fRow(fkey, sev, code, msg, written, anchor, codeTag, minor) {
  const t = (S.t.findings[fkey] = S.t.findings[fkey] || {});
  t.label = `${code}: ${(msg || '').slice(0, 80)}`;
  const sevCls = sev === 'verdict' ? 'verdict' : (sev === 'flag' ? 'flag' : (sev === 'info' ? 'info' : 'note'));
  const wtag = written
    ? el('span', { class: 'wtag written' }, 'written to docx')
    : el('span', { class: 'wtag console' }, 'console-only');
  const div = el('div', { class: 'finding' + (minor ? ' minor' : ''), 'data-fkey': fkey, onclick: () => focusFinding(fkey) },
    el('div', { class: 'f-top' },
      el('span', { class: 'sev ' + sevCls }, sev),
      wtag,
      codeTag ? el('span', { class: 'f-code' }, codeTag) : null),
    el('div', { class: 'f-msg' }, msg || ''),
    anchor ? el('div', { class: 'f-anchor' }, '↳ docx anchor: ' + anchor) : null,
    triageControls(fkey, t));
  return div;
}

function triageControls(fkey, t) {
  const mk = (v, lbl) => el('button', {
    class: 'tbtn ' + v + (t.verdict === v ? ' on' : ''),
    onclick: ev => { ev.stopPropagation(); t.verdict = (t.verdict === v ? null : v);
                     saveTriage(); renderFindings(); }
  }, lbl);
  const note = el('input', { class: 'tnote', type: 'text', placeholder: 'note…',
    value: t.note || '',
    onclick: ev => ev.stopPropagation(),
    oninput: ev => { t.note = ev.target.value; saveTriage(); } });
  return el('div', { class: 'triage' }, mk('confirm', '✓ confirm'),
    mk('dismiss', '✗ dismiss'), mk('look', '? look'), note);
}

// focus a finding -> drive the PDF pane + snippet
function focusFinding(fkey) {
  document.querySelectorAll('.finding').forEach(d =>
    d.classList.toggle('focus', d.getAttribute('data-fkey') === fkey));
  const a = S.a;
  let terms = [], snippet = '', label = '';
  if (fkey === 'cell' || fkey.startsWith('param:')) {
    terms = (a.pdf && a.pdf.terms) || [];
    if (a.cell.matched) { snippet = a.cell.matched.snippet || ''; label = 'matched cell context [' + (a.cell.matched.context || '?') + ']'; }
    if (a.pdf) S.pdfPage = a.pdf.evidence_page || 0;
  } else if (fkey === 'lam') {
    const m = /([A-Za-z]{1,2})\s*K/.exec(a.docx.radiation || '');
    if (m) terms = [m[1] + 'K'];
  } else if (fkey.startsWith('f')) {
    const f = a.findings[parseInt(fkey.slice(1), 10)];
    if (f) { const nums = (f.msg.match(/\d+\.\d{2,}/g) || []).slice(0, 2); terms = nums; }
  }
  S.pdfTerms = terms;
  renderPdf(snippet, label, terms);
}

// ---- pdf pane --------------------------------------------------------------
function renderPdf(snippet, snipLabel, hlTerms) {
  const a = S.a, view = $('#pdf-view');
  $('#pdf-name').textContent = a.pdf ? a.pdf.name : '';
  if (!a.pdf) {
    view.innerHTML = '<div class="empty muted">no .pdf paired for this entry</div>';
    $('#pdf-pager').innerHTML = ''; $('#pdf-snippet').innerHTML = '';
    return;
  }
  const find = (S.pdfTerms || []).join('|');
  const url = `/api/pdf/${encodeURIComponent(a.key)}/page/${S.pdfPage}.png?find=${encodeURIComponent(find)}`;
  view.replaceChildren(el('img', { src: url, alt: 'page ' + (S.pdfPage + 1) }));
  renderPager();
  if (snippet !== undefined) renderSnippet(snippet, snipLabel, hlTerms || S.pdfTerms);
}

function renderPager() {
  const a = S.a, p = $('#pdf-pager'); p.innerHTML = '';
  p.append(
    el('button', { onclick: () => { if (S.pdfPage > 0) { S.pdfPage--; renderPdf(undefined); } } }, '‹'),
    el('span', {}, `p.${S.pdfPage + 1} / ${a.pdf.pages}`),
    el('button', { onclick: () => { if (S.pdfPage < a.pdf.pages - 1) { S.pdfPage++; renderPdf(undefined); } } }, '›'));
}

function renderSnippet(snippet, label, terms) {
  const box = $('#pdf-snippet');
  if (!snippet) { box.innerHTML = ''; return; }
  let h = esc(snippet);
  for (const t of (terms || [])) {
    if (!t) continue;
    h = h.replaceAll(t, '<span class="hl">' + t + '</span>');
  }
  box.innerHTML = (label ? '<b>' + esc(label) + ':</b> ' : '') + '…' + h + '…';
}

async function pdfSearch(q) {
  if (!S.a.pdf || !q) return;
  const r = await fetch(`/api/pdf/${encodeURIComponent(S.a.key)}/search?q=${encodeURIComponent(q)}`).then(x => x.json());
  const hits = r.hits || [];
  $('#pdf-hits').textContent = hits.length
    ? `${hits.reduce((s, h) => s + h.count, 0)} hit(s) on ${hits.length} page(s)`
    : 'no hits';
  if (hits.length) { S.pdfPage = hits[0].page; S.pdfTerms = [q]; renderPdf('', '', [q]); }
}

// ---- docx pane -------------------------------------------------------------
function renderDocx() {
  const a = S.a, body = $('#docx-body'); body.innerHTML = '';
  const ac = a.docx.authors_cell || [];
  body.append(el('div', { class: 'sub' }, "Author's cell (docx)"));
  body.append(cellGrid(ac, a.params, a.cell.deltas));
  if (a.cell.matched) {
    const m = a.cell.matched;
    body.append(el('div', { class: 'sub' }, '.pdf matched cell [' + (m.context || '?') + (m.phase ? ' · ' + m.phase : '') + ']'));
    body.append(cellGrid([m.a, m.b, m.c, m.al, m.be, m.ga, '', m.Z], {}, []));
  }

  const kv = [];
  kv.push(['Radiation', esc(a.docx.radiation) + (a.docx.lam ? '  λ=' + a.docx.lam : '')]);
  const e = a.entry;
  if (e) {
    if (e.crystal_system) kv.push(['Crystal system', e.crystal_system]);
    if (e.space_group) kv.push(['Space group', e.space_group]);
    const I = e.instr || {};
    for (const [k, lbl] of [['spacing_instr', 'Spacing Instr.'], ['intensity_instr', 'Intensity Instr.'],
      ['intensity_type', 'Intensity Type'], ['filter', 'Filter'], ['filtertype', 'FilterType'],
      ['camera', 'Camera'], ['standard', 'Standard']])
      if (I[k]) kv.push([lbl, I[k]]);
    if (e.refl_count) kv.push(['Reflections', e.refl_count + ' lines']);
  }
  body.append(kvTable(kv));

  if (e && e.formulas && Object.keys(e.formulas).length) {
    body.append(el('div', { class: 'sub' }, 'Formulas'));
    body.append(kvTable(Object.entries(e.formulas)));
  }
  if (e && e.comments && Object.keys(e.comments).length) {
    body.append(el('div', { class: 'sub' }, 'docx comment fields'));
    body.append(kvTable(Object.entries(e.comments).map(([k, v]) => [k, v])));
  }
  if (a.docx.comments && a.docx.comments.length) {
    body.append(el('div', { class: 'sub' }, 'existing reviewer comments'));
    body.append(kvTable(a.docx.comments.map(([au, tx]) => [au, tx])));
  }
}

const AXES = ['a', 'b', 'c', 'α', 'β', 'γ', 'SG', 'Z'];
function cellGrid(vals, params, deltas) {
  params = params || {}; deltas = deltas || [];
  const dmap = {}; for (const [lab, , , dd, ok] of deltas) dmap[lab] = { dd, ok };
  const g = el('div', { class: 'cellgrid' });
  for (const ax of AXES) g.append(el('div', { class: 'hdr' }, ax));
  vals = vals.slice(0, 8);
  for (let i = 0; i < 8; i++) {
    const ax = AXES[i]; let cls = '';
    if (params[ax]) cls = 'bad';
    else if (dmap[ax] && dmap[ax].ok && dmap[ax].dd > 0.002 && dmap[ax].dd <= 0.004) cls = 'near';
    const v = esc(vals[i]) || '·';
    g.append(el('div', { class: cls, title: ax + ' = ' + v }, v));   // title: full value (cells ellipsize)
  }
  return g;
}

function kvTable(pairs) {
  const t = el('table', { class: 'kv' });
  for (const [k, v] of pairs)
    t.append(el('tr', {}, el('td', { class: 'k' }, esc(k)), el('td', {}, esc(v))));
  return t;
}

// ---- mindat / cross-source pane -------------------------------------------
function renderMindat() {
  const a = S.a, body = $('#mindat-body'); body.innerHTML = '';
  const M = a.mindat;
  body.append(el('div', { class: 'sub' }, 'Mindat (IMA structural record)'));
  if (!M) {
    body.append(el('div', { class: 'note-line' },
      'not in the Mindat cache — a new/renamed species? verify classification & formula.'));
  } else {
    if (a.synthetic)
      body.append(el('div', { class: 'note-line' },
        'synthetic — the tool skips the Mindat CELL compare (a synthetic cell ≠ the natural species); the formula check still applies.'));
    body.append(cellGrid([M.a, M.b, M.c, M.al, M.be, M.ga, M.sg, ''], {}, []));
    const kv = [];
    if (M.sorted && M.sorted.length) kv.push(['sorted axes', M.sorted.map(x => (+x).toFixed(3)).join(', ')]);
    if (M.sg) kv.push(['SG (IT no.)', M.sg]);
    if (M.formula) kv.push(['IMA formula', M.formula]);
    if (M.group) kv.push(['group', M.group]);
    if (M.ima_status) kv.push(['IMA status', M.ima_status]);
    if (M.elements && M.elements.length) kv.push(['elements', M.elements.join(' ')]);
    body.append(kvTable(kv));
  }

  const cif = a.cif || {};
  if (cif && (cif.Z || (cif.cell && Object.keys(cif.cell).length) || cif.SG)) {
    body.append(el('div', { class: 'sub' }, '.cif (' + (a.files.cif_name || 'author') + ')'));
    const c = cif.cell || {};
    body.append(cellGrid([c['a'], c['b'], c['c'], c['α'], c['β'], c['γ'], cif.SG, cif.Z], {}, []));
    if (cif.mineral_name) body.append(kvTable([['name', cif.mineral_name]]));
  }
  const dft = a.dft || {};
  if (dft && (dft.Z || (dft.cell && Object.keys(dft.cell).length) || dft.SG)) {
    body.append(el('div', { class: 'sub' }, '.dft (ICDD — co-equal proxy, never written)'));
    const c = dft.cell || {};
    body.append(cellGrid([c['a'], c['b'], c['c'], c['α'], c['β'], c['γ'], dft.SG, dft.Z], {}, []));
    const kv = [];
    for (const [k, lbl] of [['geometry', 'geometry'], ['method', 'method'],
      ['volume', 'volume'], ['temperature', 'temp']]) if (dft[k]) kv.push([lbl, dft[k]]);
    if (kv.length) body.append(kvTable(kv));
  }
}

// ---- triage save (debounced) ----------------------------------------------
function saveTriage() {
  clearTimeout(S.saveTimer);
  S.saveTimer = setTimeout(async () => {
    await fetch('/api/triage/' + encodeURIComponent(S.key), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(S.t),
    });
    const row = S.entries.find(e => e.key === S.key);
    if (row) row.reviewed = !!S.t.reviewed;
  }, 350);
}

// flush any pending debounced triage save so a rerun reads the latest sidecar
async function flushTriage() {
  clearTimeout(S.saveTimer);
  if (!S.key) return;
  await fetch('/api/triage/' + encodeURIComponent(S.key), {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(S.t),
  });
}

// ---- rerun (regenerate docx with triage applied) ---------------------------
async function rerun(url, btn, busyLabel, doneLabel) {
  await flushTriage();
  const orig = btn.textContent;
  btn.classList.add('busy'); btn.textContent = busyLabel;
  $('#rerun-status').textContent = busyLabel;
  let r;
  try { r = await fetch(url, { method: 'POST' }).then(x => x.json()); }
  catch (ex) { r = { ok: false, error: String(ex) }; }
  btn.classList.remove('busy'); btn.textContent = orig;
  $('#rerun-status').textContent = r.ok ? doneLabel : ('rerun failed' + (r.error ? ': ' + r.error : ''));
  setTimeout(() => { $('#rerun-status').textContent = ''; }, 5000);
}

// ---- navigation ------------------------------------------------------------
function step(delta) {
  // navigate within the currently-visible (filtered/sorted) order
  const keys = S.entries.filter(e => visibleKey(e)).map(e => e.key);
  const i = keys.indexOf(S.key);
  if (i === -1) return;
  const j = i + delta;
  if (j >= 0 && j < keys.length) openEntry(keys[j]);
}
function visibleKey(e) {
  const q = $('#filter').value.toLowerCase();
  if (!matchesView(e)) return false;
  if (q && !((e.name || '').toLowerCase().includes(q) || (e.eid || '').toLowerCase().includes(q))) return false;
  return true;
}

// ---- wire up ---------------------------------------------------------------
$('#filter').addEventListener('input', renderList);
document.querySelectorAll('#views button').forEach(b =>
  b.addEventListener('click', () => {
    S.view = b.getAttribute('data-view');
    document.querySelectorAll('#views button').forEach(x => x.classList.toggle('on', x === b));
    renderList();
  }));
$('#rerun-entry').addEventListener('click', () =>
  rerun('/api/rerun/' + encodeURIComponent(S.key), $('#rerun-entry'),
        'Rerunning…', 'regenerated this docx ✓'));
$('#rerun-all').addEventListener('click', () =>
  rerun('/api/rerun', $('#rerun-all'), 'Rerunning all…', 'regenerated all docx ✓'));
$('#prev').addEventListener('click', () => step(-1));
$('#next').addEventListener('click', () => step(1));
$('#pdf-q').addEventListener('keydown', e => { if (e.key === 'Enter') pdfSearch(e.target.value.trim()); });
$('#export').addEventListener('click', async () => {
  const r = await fetch('/api/triage/export', { method: 'POST' }).then(x => x.json());
  $('#export').textContent = 'Exported ✓';
  setTimeout(() => $('#export').textContent = 'Export triage', 1800);
});
document.addEventListener('keydown', e => {
  if (e.target.matches('input, textarea')) return;
  if (e.key === 'j') step(1);
  else if (e.key === 'k') step(-1);
});

// ============================================================ appearance + layout
const LS_KEY = 'pxrd-gui';
const DEFAULTS = {
  theme: 'clear-dark', opacity: 0.72, blur: 14, density: 'comfortable', fontsize: 13,
  wSidebar: 320, wFind: 360, wSide: 380, hDocx: 300,
  collapsed: { findings: false, docx: false, mindat: false },
};
// switching theme applies its natural translucency (Solid Dark = opaque, no blur)
const THEME_PRESETS = {
  'clear-dark': { opacity: 0.72, blur: 14 }, 'solid-dark': { opacity: 1, blur: 0 },
  'midnight': { opacity: 0.74, blur: 14 }, 'graphite': { opacity: 0.78, blur: 12 },
};
const PANE_OF = { findings: '#findings', docx: '#docx', mindat: '#mindat' };
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

let CFG;
try { CFG = Object.assign(JSON.parse(JSON.stringify(DEFAULTS)), JSON.parse(localStorage.getItem(LS_KEY) || '{}')); }
catch (e) { CFG = JSON.parse(JSON.stringify(DEFAULTS)); }
CFG.collapsed = Object.assign({ findings: false, docx: false, mindat: false }, CFG.collapsed || {});

let cfgTimer = null;
function saveCfg() { clearTimeout(cfgTimer); cfgTimer = setTimeout(() => localStorage.setItem(LS_KEY, JSON.stringify(CFG)), 120); }
function rootVar(k, v) { document.documentElement.style.setProperty(k, v); }
function setSeg(sel, attr, val) {
  document.querySelectorAll(sel + ' button').forEach(b => b.classList.toggle('on', b.getAttribute(attr) === val));
}
function applySizes() {
  rootVar('--w-sidebar', CFG.wSidebar + 'px'); rootVar('--w-find', CFG.wFind + 'px');
  rootVar('--w-side', CFG.wSide + 'px'); rootVar('--h-docx', CFG.hDocx + 'px');
}
function updateSplitterStates() {
  const find = document.querySelector('.splitter[data-resize="find"]');
  if (find) find.classList.toggle('disabled', CFG.collapsed.findings);
  const dr = document.querySelector('.splitter[data-resize="docrow"]');
  if (dr) dr.classList.toggle('disabled', CFG.collapsed.docx || CFG.collapsed.mindat);
}
function applyCollapse() {
  for (const name in PANE_OF) {
    const el = document.querySelector(PANE_OF[name]);
    if (el) el.classList.toggle('collapsed', !!CFG.collapsed[name]);
  }
  updateSplitterStates();
}
function applyCfg() {
  const r = document.documentElement;
  r.setAttribute('data-theme', CFG.theme);
  r.setAttribute('data-density', CFG.density);
  rootVar('--panel-alpha', CFG.opacity); rootVar('--blur', CFG.blur + 'px'); rootVar('--fs', CFG.fontsize + 'px');
  applySizes();
  setSeg('#theme-picker', 'data-theme', CFG.theme);
  setSeg('#density-picker', 'data-density', CFG.density);
  $('#opacity').value = CFG.opacity; $('#opacity-val').textContent = Math.round(CFG.opacity * 100) + '%';
  $('#blur').value = CFG.blur; $('#blur-val').textContent = CFG.blur + 'px';
  $('#fontsize').value = CFG.fontsize; $('#fontsize-val').textContent = CFG.fontsize + 'px';
  applyCollapse();
}

function initSplitters() {
  document.querySelectorAll('.splitter').forEach(sp => {
    sp.addEventListener('mousedown', e => {
      if (sp.classList.contains('disabled')) return;
      e.preventDefault();
      const kind = sp.getAttribute('data-resize');
      const x0 = e.clientX, y0 = e.clientY;
      const s = { sidebar: CFG.wSidebar, find: CFG.wFind, side: CFG.wSide, docrow: CFG.hDocx };
      sp.classList.add('active'); document.body.style.userSelect = 'none';
      const move = ev => {
        const dx = ev.clientX - x0, dy = ev.clientY - y0;
        if (kind === 'sidebar') CFG.wSidebar = clamp(s.sidebar + dx, 180, 640);
        else if (kind === 'find') CFG.wFind = clamp(s.find + dx, 200, 760);
        else if (kind === 'side') CFG.wSide = clamp(s.side - dx, 220, 820);   // grows leftward
        else if (kind === 'docrow') CFG.hDocx = clamp(s.docrow + dy, 80, window.innerHeight - 220);
        applySizes();
      };
      const up = () => {
        document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up);
        sp.classList.remove('active'); document.body.style.userSelect = ''; saveCfg();
      };
      document.addEventListener('mousemove', move); document.addEventListener('mouseup', up);
    });
  });
}

function initAppearance() {
  applyCfg();
  initSplitters();
  $('#gear').addEventListener('click', e => { e.stopPropagation(); $('#settings').classList.toggle('hidden'); });
  document.addEventListener('click', e => {
    if (!$('#settings').classList.contains('hidden') &&
        !e.target.closest('#settings') && e.target !== $('#gear')) $('#settings').classList.add('hidden');
  });
  document.querySelectorAll('#theme-picker button').forEach(b => b.addEventListener('click', () => {
    CFG.theme = b.getAttribute('data-theme');
    const p = THEME_PRESETS[CFG.theme]; if (p) { CFG.opacity = p.opacity; CFG.blur = p.blur; }
    saveCfg(); applyCfg();
  }));
  document.querySelectorAll('#density-picker button').forEach(b => b.addEventListener('click', () => {
    CFG.density = b.getAttribute('data-density'); saveCfg(); applyCfg();
  }));
  $('#opacity').addEventListener('input', e => {
    CFG.opacity = parseFloat(e.target.value); rootVar('--panel-alpha', CFG.opacity);
    $('#opacity-val').textContent = Math.round(CFG.opacity * 100) + '%'; saveCfg();
  });
  $('#blur').addEventListener('input', e => {
    CFG.blur = parseInt(e.target.value, 10); rootVar('--blur', CFG.blur + 'px');
    $('#blur-val').textContent = CFG.blur + 'px'; saveCfg();
  });
  $('#fontsize').addEventListener('input', e => {
    CFG.fontsize = parseInt(e.target.value, 10); rootVar('--fs', CFG.fontsize + 'px');
    $('#fontsize-val').textContent = CFG.fontsize + 'px'; saveCfg();
  });
  $('#reset-layout').addEventListener('click', () => {
    CFG = JSON.parse(JSON.stringify(DEFAULTS)); saveCfg(); applyCfg();
  });
  document.querySelectorAll('.pane .collapse').forEach(btn => btn.addEventListener('click', () => {
    const id = btn.closest('.pane').id;       // findings / docx / mindat
    CFG.collapsed[id] = !CFG.collapsed[id]; saveCfg(); applyCollapse();
  }));
}

initAppearance();
loadEntries();
