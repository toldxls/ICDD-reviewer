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
  sort: 'id',         // list order: id | id-desc | az | za | fixes | clean (see SORTS)
  pdfPage: 0,
  pdfTerms: [],
  pdfMode: 'page',    // 'page' = scrollable full pages | 'region' = zoomed crop around the hit
  pdfZoom: 1,         // display scale of whatever is shown
  lookStep: {},       // per-finding '? look' cycle index (findings with ordered look-groups)
  lookLabel: '',      // label of the current '? look' target (shown in the region pager)
  focusKey: null,     // the finding currently driving the PDF pane
  pdfIO: null,        // IntersectionObserver for lazy page loading + current-page tracking
  pdfRatios: {},      // page -> visible ratio (to pick the current page)
  pdfHits: [],        // flat search hits [{page, rect}] for hit-to-hit stepping
  pdfSizes: {},       // page -> [w,h] in points, for placing a flash box in page-%
  hitIdx: -1,         // current hit in pdfHits
  pdfQuery: '',       // the live search query (Enter again steps to the next hit)
  pageSizes: null,    // [[w,h], …] every page's size — reserves slot heights (no scroll-shift)
  pageSizesKey: null, // which entry pageSizes belongs to
  sizesPromise: null, // in-flight sizes fetch
  midMode: 'pdf',     // middle pane: 'pdf' (paper render) | 'docx' (transcription + tracked changes)
  docxHtml: {},       // key -> rendered docx HTML (cached; live from /api/docx)
  docxHidden: new Set(), // authors toggled OFF in the docx view (persists across entries)
  cmtPop: null,       // the pinned comment popover element, if any
  ue: [],             // current entry's reviewer marks [{author,kind,text}]
  ueAuthor: 'All',    // reviewer-edits author filter (persists across entries when present)
  pollTimer: null,    // re-poll /api/entries while entries are still analysing in the background
  saveTimer: null,
  pendingSave: null,  // {key,payload} of a debounced triage write not yet sent (flushed on navigate)
};
const enc = encodeURIComponent;

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
const mantissa = s => (s == null ? '' : String(s).replace(/\(.*$/, '').trim());   // '12.277(4)' -> '12.277'

// ---- dashboard -------------------------------------------------------------
async function loadEntries() {
  clearTimeout(S.pollTimer);
  const r = await fetch('/api/entries').then(x => x.json());
  const parts = (r.folder || '').split('/').filter(Boolean);
  $('#folder').textContent = (parts.length > 2 ? '…/' : '') + parts.slice(-2).join('/');
  $('#folder-ctl').title = (r.folder || '') + '  — click to change folder';
  $('#folder').dataset.path = r.folder || '';             // the bare path (the title is decorated)
  S.entries = r.entries;
  renderList();
  // analysis runs in the background — poll until every entry's badges are in
  if (r.pending > 0) S.pollTimer = setTimeout(loadEntries, 1200);
}

// ---- folder picker: re-point the tool at a different entries folder, live ---
function openFolderPanel() {
  $('#settings').classList.add('hidden');
  $('#folderpanel').classList.remove('hidden');
  browseFolder($('#folder').dataset.path || '');          // start at the current folder
}
async function browseFolder(path) {
  let r;
  try { r = await fetch('/api/browse?path=' + enc(path)).then(x => x.json()); } catch (_) { return; }
  $('#folder-path').value = r.path;
  $('#folder-hint').innerHTML = `<b>${r.docx}</b> docx · <b>${r.pdf}</b> .pdf here`
    + (r.docx && !r.pdf ? ' — no .pdf beside them; the GUI will look up a level' : '')
    + (!r.docx ? ' — no entries here; drill into a subfolder' : '');
  const list = $('#folder-list'); list.innerHTML = '';
  if (r.parent) list.append(el('div', { class: 'fp-item fp-up', onclick: () => browseFolder(r.parent) }, '⬆  ..'));
  for (const d of r.dirs)
    list.append(el('div', { class: 'fp-item', title: d,
      onclick: () => browseFolder(r.path.replace(/\/+$/, '') + '/' + d) }, '📁  ' + d));
}
// pop the OS-native folder chooser (Finder), then open the chosen folder
async function pickFolderNative() {
  $('#folder-hint').textContent = 'waiting for the Finder dialog…';
  let r;
  try { r = await fetch('/api/pick-folder', { method: 'POST' }).then(x => x.json()); }
  catch (_) { r = { ok: false, error: 'request failed' }; }
  if (r && r.cancelled) { $('#folder-hint').textContent = ''; return; }
  if (!r || !r.ok) { $('#folder-hint').textContent = '⚠ ' + ((r && r.error) || 'picker failed'); return; }
  $('#folder-path').value = r.folder;
  openFolder(r.folder);
}
async function openFolder(path) {
  path = (path || '').trim();
  if (!path) return;
  await flushTriage();              // persist any pending triage BEFORE re-pointing the tool
                                    // (un-awaited, the POST could land in the new folder's sidecar)
  const btns = ['#folder-open', '#folder-browse'].map($).filter(Boolean);
  btns.forEach(b => b.disabled = true);
  $('#folder-hint').textContent = 'opening…';
  let r;
  try {
    r = await fetch('/api/folder', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder: path }) }).then(x => x.json());
  } catch (_) { r = { ok: false, error: 'request failed' }; }
  btns.forEach(b => b.disabled = false);
  if (!r.ok) { $('#folder-hint').textContent = '⚠ ' + (r.error || 'could not open'); return; }
  $('#folderpanel').classList.add('hidden');
  S.key = null; S.a = null; S.docxHtml = {}; S.docxHidden = new Set();     // reset per-entry view + caches
  $('#entry').classList.add('hidden'); $('#empty').classList.remove('hidden');
  await loadEntries();                                     // reload the dashboard for the new folder
}

function hasAttn(e) { return e.badges.some(b => b.level === 'danger' || b.level === 'warn'); }
function matchesView(e) {
  if (S.view === 'all') return true;
  if (S.view === 'fixes') return e.fixes > 0;
  if (S.view === 'attention') return hasAttn(e);
  if (S.view === 'clean') return e.fixes === 0 && !hasAttn(e);
  return true;
}

// ---- list ordering ----------------------------------------------------------
// ascending ICDD id: prefix letters first, then the number (I003599 < I003600 < O002127) —
// mirrors the server's _eid_key so 'id' order matches what /api/entries sends.
function cmpEid(a, b) {
  const ea = a.eid || '', eb = b.eid || '';
  const pa = ea.replace(/\d+/g, ''), pb = eb.replace(/\d+/g, '');
  if (pa !== pb) return pa < pb ? -1 : 1;
  const na = (ea.match(/\d+/) || [0])[0], nb = (eb.match(/\d+/) || [0])[0];
  return (parseInt(na, 10) - parseInt(nb, 10)) || ea.localeCompare(eb);
}
const nameOf = e => (e.name || e.key || '').toLowerCase();
const SORTS = {
  'id':      cmpEid,
  'id-desc': (a, b) => cmpEid(b, a),
  'az':      (a, b) => nameOf(a).localeCompare(nameOf(b)) || cmpEid(a, b),
  'za':      (a, b) => nameOf(b).localeCompare(nameOf(a)) || cmpEid(a, b),
  'fixes':   (a, b) => (b.fixes - a.fixes) || (hasAttn(b) - hasAttn(a)) || cmpEid(a, b),
  'clean':   (a, b) => (a.fixes - b.fixes) || (hasAttn(a) - hasAttn(b)) || cmpEid(a, b),
};
// the list in its display order — renderList AND prev/next navigation both use this,
// so stepping through entries always follows what's on screen.
function sortedEntries() {
  return [...S.entries].sort(SORTS[S.sort] || SORTS.id);
}

function renderList() {
  const ul = $('#entry-list'); ul.innerHTML = '';
  const q = $('#filter').value.toLowerCase();
  let shown = 0, fixes = 0;
  for (const e of sortedEntries()) {
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
      e.pending ? el('div', { class: 'row2' }, el('span', { class: 'pending muted' }, 'analyzing…'))
                : el('div', { class: 'row2' }, ...e.badges.map(badgeEl)));
    ul.append(li);
  }
  const pend = S.entries.filter(e => e.pending).length;
  $('#counts').textContent = `${shown} shown · ${fixes}/${S.entries.length} with fixes`
    + (pend ? ` · analyzing ${pend}…` : '');
}

function badgeEl(b) { return el('span', { class: 'badge ' + b.level }, b.label); }

// ---- open an entry ---------------------------------------------------------
async function openEntry(key) {
  flushTriage();                    // persist the previous entry's triage before switching
  S.key = key;                      // selection intent — stale responses check against it
  let r;
  try {
    const resp = await fetch('/api/entry/' + encodeURIComponent(key));
    r = await resp.json().catch(() => null);            // 404/500 HTML would throw here
    if (!r || !r.analysis) throw new Error((r && r.error) || ('HTTP ' + resp.status));
  } catch (ex) {
    if (S.key !== key) return;      // a newer selection superseded this one — its owner reports
    // surface the failure and clear the half-open state so triage can't save under this key
    S.key = null; S.a = null; S.t = null;
    $('#entry').classList.add('hidden'); $('#empty').classList.remove('hidden');
    const st = $('#rerun-status');
    st.textContent = 'could not open entry: ' + ((ex && ex.message) || ex);
    setTimeout(() => { st.textContent = ''; }, 6000);
    renderList();                   // un-stick the selected row
    return;
  }
  if (S.key !== key) return;        // out-of-order response — a newer entry owns the panes now
  S.a = r.analysis;
  S.t = normalizeTriage(r.triage);
  S.ue = r.user_edits || [];  // reviewer's own marks in the reviewed copy (live, not cached)
  S.lookStep = {};            // reset '? look' cycles for the new entry
  $('#empty').classList.add('hidden');
  $('#entry').classList.remove('hidden');
  renderHead();
  renderFindings();
  renderDocx();
  renderMindat();
  // open the PDF at the TOP of page 1 — a predictable starting point (not a heuristic
  // 'evidence page' that felt random); the reviewer drives from there via findings / search
  S.pdfMode = 'page'; S.pdfZoom = 1; S.pdfPage = 0;
  S.pdfTerms = []; S.pdfHits = []; S.pdfQuery = ''; S.hitIdx = -1; S.focusKey = 'cell';
  $('#pdf-hits').textContent = '';
  document.querySelectorAll('.finding').forEach(d => d.classList.toggle('focus', d.getAttribute('data-fkey') === 'cell'));
  renderPdf('', '', []);
  setMidMode('pdf');            // every entry opens on the paper; the toggle flips to the docx
  renderList();
}

function normalizeTriage(t) {
  t = t || {};
  t.findings = t.findings || {};
  return t;
}

// a finding's triage key: the server's content-stable fkey, falling back to the old
// index key for an analysis served from a stale gui_cache (pre-fkey)
function fkeyOf(f) { return f.fkey || ('f' + f.idx); }
function findingOf(fkey) {
  if (!S.a || !fkey) return null;
  return S.a.findings.find(f => fkeyOf(f) === fkey) || null;
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
  rv.onchange = () => {
    S.t.reviewed = rv.checked;
    const row = S.entries.find(e => e.key === S.key);
    if (row) row.reviewed = rv.checked;   // sync the sidebar tick NOW, before renderList
    saveTriage(); renderList();
  };
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
  for (const f of a.findings) if (f.written) tally(fkeyOf(f));
  return { write, suppress };
}

// ---- findings pane ---------------------------------------------------------
// severity levels: flag (red, real problem, written) · check (orange, confirm) ·
// note (gray, low-confidence FYI) · ok (green, clean). The cell/radiation rows carry
// the level that matches their outcome (no more abstract "verdict").
const SEV_LABEL = { flag: 'FLAG', check: 'CHECK', note: 'NOTE', ok: 'OK' };

function renderFindings() {
  const a = S.a, body = $('#findings-body'); body.innerHTML = '';
  const rows = [];

  // cell-match result
  const cs = a.cell.status, m = a.cell;
  let cellMsg, cellLevel, cellWritten;
  if (cs === 'match') {
    cellMsg = `value match to a reported cell — ${m.nmatch}/${m.ncomp} axes, ${m.mode}, Σ|Δ|=${(m.dev||0).toFixed(4)} Å`;
    cellLevel = 'ok'; cellWritten = false;
  } else if (cs === 'investigate') {
    cellMsg = `no exact cell match — closest off by Σ|Δ|=${(m.dev||0).toFixed(4)} Å over ${m.ncomp} axes — INVESTIGATE`;
    cellLevel = 'flag'; cellWritten = true;
  } else if (cs === 'nocell') {
    cellMsg = 'no cell parsed from the .pdf (table-only?) — “No matching .pdf cell found.” is written';
    cellLevel = 'flag'; cellWritten = true;
  } else if (cs === 'nopdf') {
    cellMsg = 'no .pdf paired — the cell cannot be validated';
    cellLevel = 'flag'; cellWritten = true;
  } else if (cs === 'notext') {
    cellMsg = '.pdf has no text layer (scanned image?) — cell/λ not checked';
    cellLevel = 'flag'; cellWritten = true;
  } else { cellMsg = cs; cellLevel = 'note'; cellWritten = false; }
  if (m.provenance) {
    // on an INVESTIGATE the docx did NOT match — say "closest is", not "matches"
    const prov = cs === 'investigate' ? m.provenance.replace(/^matches /, 'closest is ') : m.provenance;
    cellMsg += `\n↳ ${prov}`;
  }
  rows.push({ fkey: 'cell', level: cellLevel, code: 'CELL', msg: cellMsg, written: cellWritten, anchor: 'cell:' + cs });

  // per-parameter issues (written docx highlights+comments)
  for (const ax in a.params) {
    const parts = a.params[ax].map(([kind, note]) => `${kind}: ${note}`).join('; ');
    rows.push({ fkey: 'param:' + ax, level: 'flag', code: 'CELL ' + ax, msg: parts, written: true, anchor: 'cell:' + ax });
  }

  // radiation: anode mismatch = flag; verify/unrec = check; calc = note
  if (a.lam) {
    const [st, msg] = a.lam;
    if (st !== 'ok') {
      const level = st === 'flag' ? 'flag' : (st === 'calc' ? 'note' : 'check');
      rows.push({ fkey: 'lam', level, code: 'RADIATION', msg, written: st === 'flag', anchor: 'radiation', minor: st !== 'flag' });
    }
  }

  // extra-check findings
  for (const f of a.findings) {
    const level = f.sev === 'flag' ? 'flag' : (f.sev === 'info' ? 'check' : 'note');
    rows.push({ fkey: fkeyOf(f), level, code: f.code, msg: f.msg, written: f.written, anchor: f.anchor, minor: !f.major });
  }

  // promote by severity: FLAG (real problems) first, then CHECK (confirm), then OK,
  // with NOTE (low-confidence FYI) ranked last. Stable sort keeps the cell→λ→checks
  // order within each tier.
  const LVL_RANK = { flag: 0, check: 1, ok: 2, note: 3 };
  rows.sort((x, y) => (LVL_RANK[x.level] ?? 9) - (LVL_RANK[y.level] ?? 9));

  let hidden = 0;
  for (const r of rows) {
    if (CFG.hideNotes && r.level === 'note') { hidden++; continue; }
    body.append(fRow(r));
  }
  $('#f-count').textContent = hidden
    ? `(${rows.length - hidden} of ${rows.length} · ${hidden} note${hidden > 1 ? 's' : ''} hidden)`
    : `(${rows.length})`;
}

function fRow(r) {
  const t = S.t.findings[r.fkey] || {};       // READ-ONLY — rendering must never mutate triage
  const label = `${r.code}: ${(r.msg || '').slice(0, 80)}`;
  const top = el('div', { class: 'f-top' }, el('span', { class: 'sev ' + r.level }, SEV_LABEL[r.level] || r.level));
  if (r.level !== 'ok')                       // an 'OK' result writes nothing — no tag needed
    top.append(r.written ? el('span', { class: 'wtag written' }, 'written to docx')
                         : el('span', { class: 'wtag console' }, 'console-only'));
  top.append(el('span', { class: 'f-code' }, r.code));
  return el('div', { class: 'finding lvl-' + r.level + (r.minor ? ' minor' : ''), 'data-fkey': r.fkey, onclick: () => focusFinding(r.fkey) },
    top,
    el('div', { class: 'f-msg' }, r.msg || ''),
    r.anchor ? el('div', { class: 'f-anchor' }, '↳ docx anchor: ' + r.anchor) : null,
    triageControls(r.fkey, t, label));
}

function triageControls(fkey, t, label) {
  // create-and-label the stored record only when the reviewer actually ACTS — a
  // label-only record for every rendered finding used to persist on any save and
  // fill triage_report.txt with [?] lines.
  const rec = () => {
    const x = (S.t.findings[fkey] = S.t.findings[fkey] || {});
    x.label = label;
    return x;
  };
  const mk = (v, lbl) => el('button', {
    class: 'tbtn ' + v + (t.verdict === v ? ' on' : ''),
    onclick: ev => {
      ev.stopPropagation();
      const x = rec();
      x.verdict = (x.verdict === v ? null : v);       // confirm / dismiss are the only verdicts
      saveTriage(); renderFindings();
    }
  }, lbl);
  // '? look' is pure NAVIGATION — it jumps the .pdf to this finding's evidence and does NOT set a
  // verdict, so investigating a flag can never overwrite a confirm/dismiss. Lands in the live page.
  const look = el('button', { class: 'tbtn look',
    onclick: ev => { ev.stopPropagation(); lookInPage(fkey); } }, '? look');
  const note = el('input', { class: 'tnote', type: 'text', placeholder: 'note…',
    value: t.note || '',
    onclick: ev => ev.stopPropagation(),
    oninput: ev => { rec().note = ev.target.value; saveTriage(); } });
  return el('div', { class: 'triage' }, mk('confirm', '✓ confirm'),
    mk('dismiss', '✗ dismiss'), look, note);
}

// Some findings have no number/keyword in their message to search, but the reviewer
// still wants to land on the evidence. Return ORDERED groups of search terms; repeated
// '? look' clicks cycle through them. null = use the default term logic below.
function lookGroups(f) {
  if (!f) return null;
  // chemical-analysis findings: the evidence is the docx Analysis string (oxide wt%
  // values) — those exact numbers appear in the paper's EPMA/EDS table, so they pinpoint
  // it. Second click -> the 'Chemical composition' prose.
  if (f.code === 'ideal_formula' || f.code === 'analysis' || f.code === 'mindat_chem') {
    const nums = (f.evidence || '').match(/\d+\.\d{1,3}/g) || [];
    const table = nums.length ? [...new Set(nums)].slice(0, 8)
                              : ['wt.%', 'apfu', 'Range', 'Mean', 'Total', 'Probe'];
    return [
      { label: 'EPMA / analysis table', terms: table },
      { label: 'chemical-composition text', terms: ['Chemical composition', 'Chemical analysis',
        'Chemical Data', 'electron microprobe', 'microprobe', 'EPMA', 'EDS', 'WDS'] },
    ];
  }
  return null;
}

// the PDF search terms + snippet for a given finding. `step` selects the look-group
// for findings that cycle (see lookGroups); it is ignored otherwise.
function termsFor(fkey, step = 0) {
  const a = S.a;
  let terms = [], snippet = '', label = '', page = (a.pdf ? a.pdf.evidence_page || 0 : 0);
  if (fkey === 'cell' || fkey.startsWith('param:')) {
    terms = (a.pdf && a.pdf.terms) || [];
    if (fkey.startsWith('param:')) {
      const key = fkey.slice(6), m = a.cell.matched;
      const AX = { a: 0, b: 1, c: 2, 'α': 3, 'β': 4, 'γ': 5 };
      if (key === 'Z' && m && m.Z != null && m.Z !== '') {
        // a Z mismatch -> locate the .pdf 'Z = N' statement, not the a/b/c cell values
        terms = [`Z = ${m.Z}`, `Z=${m.Z}`];
      } else if (AX[key] != null) {
        // a single-axis flag (e.g. β differs): search the deviant axis VALUE so the
        // exact cell parameter highlights in the .pdf table, not the whole cell
        const i = AX[key];
        const pdfv = m ? mantissa([m.a, m.b, m.c, m.al, m.be, m.ga][i]) : '';
        const docxv = mantissa((a.docx.authors_cell || [])[i]);
        terms = [...new Set([pdfv, docxv, ...terms].filter(Boolean))];   // deviant value first
      }
    }
    if (a.cell.matched) { snippet = a.cell.matched.snippet || ''; label = 'matched cell context [' + (a.cell.matched.context || '?') + ']'; }
  } else if (fkey === 'lam') {
    // a radiation flag/verify is about a specific .pdf radiation — the matched/conflicting
    // POWDER radiation for a flag, the docx anode for verify/unrec. The server computes this
    // (lam_evidence: {anode, lam}) so the GUI never parses the message prose (that coupling
    // broke the zoom twice). anode is the lowercase element ('cu'); its λ pinpoints the line.
    const ev = a.lam_evidence || {};
    if (ev.anode) {
      const sym = ev.anode.charAt(0).toUpperCase() + ev.anode.slice(1) + 'K';
      terms = [sym, ...(ev.lam ? [ev.lam] : [])];
    } else {                                  // unrecognised docx anode (e.g. Sync) — last resort
      const docxrad = /([A-Za-z]{1,2})\s*K/.exec(a.docx.radiation || '');
      if (docxrad) terms = [docxrad[1] + 'K'];
    }
  } else {
    const f = findingOf(fkey);
    if (f) {
      const groups = lookGroups(f);
      if (groups) {
        const g = groups[((step % groups.length) + groups.length) % groups.length];
        terms = g.terms; label = g.label;
      } else if (f.code === 'indexing' && a.entry && (a.entry.refl_d || []).length) {
        // the reflection d-spacings cluster in the paper's powder table -> frame it
        terms = a.entry.refl_d;
      } else if (f.code === 'instr_class' || f.code === 'geometry') {
        // highlight the instrument as written in the .pdf (evidence, e.g. 'R-AXIS Rapid')
        // plus 'diffractometer' — not the generic 'axis' that matches everywhere
        terms = [...new Set([f.evidence, 'diffractometer'].filter(t => t && t.length < 40))];
      } else {
        const nums = (f.msg.match(/\d+\.\d{2,}/g) || []).slice(0, 2);
        // a short evidence keyword (e.g. the detected "Gandolfi") is the best locator
        const ev = (f.evidence && f.evidence.length < 40) ? [f.evidence] : [];
        terms = [...new Set([...ev, ...phraseTerms(f.msg), ...phraseTerms(f.evidence || ''), ...nums])];
      }
    }
  }
  return { terms, snippet, label, page };
}

// distinctive, dash/case-robust PDF-search tokens for a text finding's message
// (e.g. "Bragg-Brentano geometry" -> "Brentano", which matches "bragg–brentano")
function phraseTerms(msg) {
  const KW = [[/brentano/i, 'Brentano'], [/gandolfi/i, 'Gandolfi'], [/guinier/i, 'Guinier'],
    [/scherrer/i, 'Scherrer'], [/precession/i, 'precession'], [/synchrotron/i, 'synchrotron'],
    [/debye/i, 'Debye'], [/image[\s-]*plate|imaging plate/i, 'plate'], [/r[-\s]?axis\s*rapid/i, 'AXIS Rapid'],
    [/rietveld/i, 'Rietveld'], [/le ?bail/i, 'Bail']];
  const out = [];
  for (const [re, tok] of KW) if (re.test(msg) && !out.includes(tok)) out.push(tok);
  return out;
}

// focus a finding -> drive the PDF pane (full page) + snippet
function focusFinding(fkey) {
  S.focusKey = fkey;
  document.querySelectorAll('.finding').forEach(d =>
    d.classList.toggle('focus', d.getAttribute('data-fkey') === fkey));
  const t = termsFor(fkey);
  S.pdfTerms = t.terms; S.pdfPage = t.page; S.pdfMode = 'page'; S.pdfZoom = 1;
  S.pdfHits = []; S.pdfQuery = ''; S.hitIdx = -1; $('#pdf-hits').textContent = '';   // reset search hit-nav
  renderPdf(t.snippet, t.label, t.terms);
}

// zoom the PDF to a cropped region framing the finding's highlighted text. When the
// finding has many terms (e.g. an indexing finding's reflection d-spacings), find the
// page where they CLUSTER (the powder table) and let the region crop expand to it.
async function zoomToHighlight(fkey) {
  const key = S.key;                 // bail after any await if the entry changed under us
  S.focusKey = fkey;
  const step = S.lookStep[fkey] || 0;
  const t = termsFor(fkey, step);
  if (!S.a.pdf || !t.terms.length) { focusFinding(fkey); return; }   // nothing to locate
  S.lookStep[fkey] = step + 1;       // next click cycles to the next look-group (if any)
  S.lookLabel = t.label || '';
  let page = t.page;
  try {
    const probe = t.terms.slice(0, 8);
    const res = await Promise.all(probe.map(term =>
      fetch(`/api/pdf/${encodeURIComponent(S.a.key)}/search?q=${encodeURIComponent(term)}`)
        .then(x => x.json()).catch(() => ({ hits: [] }))));
    const pageHits = {};
    for (const r of res) for (const h of (r.pages || [])) pageHits[h.page] = (pageHits[h.page] || 0) + h.count;
    const best = Object.keys(pageHits).sort((a, b) => pageHits[b] - pageHits[a])[0];
    if (best !== undefined) page = +best;
  } catch (e) { /* keep evidence page */ }
  if (S.key !== key) return;         // stale continuation — a different entry owns the pane
  S.pdfHits = []; S.pdfQuery = ''; S.hitIdx = -1; $('#pdf-hits').textContent = '';   // not a search context
  S.pdfTerms = t.terms.slice(0, 20); S.pdfPage = page; S.pdfMode = 'region'; S.pdfZoom = 1;
  renderPdf(t.snippet, t.label, S.pdfTerms);
}

// '? look' — land on the finding's evidence IN THE LIVE, scrollable page (scroll + flash) at a
// readable zoom, instead of a dead-end tight crop. Locates every occurrence of the finding's
// terms so the ‹ › stepper can walk them; lands on the page where they cluster. Repeated '? look'
// clicks still cycle a multi-group finding's look-groups (via lookStep).
async function lookInPage(fkey) {
  const key = S.key;                 // bail after any await if the entry changed under us
  S.focusKey = fkey;
  const step = S.lookStep[fkey] || 0;
  const t = termsFor(fkey, step);
  if (!S.a.pdf || !t.terms.length) { focusFinding(fkey); return; }
  S.lookStep[fkey] = step + 1;
  S.lookLabel = t.label || '';
  S.pdfTerms = t.terms.slice(0, 20);
  S.pdfMode = 'page'; S.pdfZoom = 1.5;          // moderate zoom — readable but still navigable
  let hits = [], sizes = {};
  try {
    const probe = t.terms.slice(0, 8);
    const res = await Promise.all(probe.map(term =>
      fetch(`/api/pdf/${enc(S.a.key)}/search?q=${enc(term)}`).then(x => x.json()).catch(() => ({ hits: [], sizes: {} }))));
    for (const r of res) { for (const h of (r.hits || [])) hits.push(h); Object.assign(sizes, r.sizes || {}); }
  } catch (e) { /* fall through to evidence page */ }
  if (S.key !== key) return;         // stale continuation — a different entry owns the pane
  if (!hits.length) {                            // terms didn't match -> just open the evidence page
    S.pdfHits = []; S.hitIdx = -1; S.pdfQuery = ''; S.pdfPage = t.page; $('#pdf-hits').textContent = '';
    renderPdf(t.snippet, t.label, S.pdfTerms); return;
  }
  const per = {}; for (const h of hits) per[h.page] = (per[h.page] || 0) + 1;
  const page = +Object.keys(per).sort((a, b) => per[b] - per[a])[0];   // cluster page
  const seen = new Set();
  hits = hits.filter(h => { const k = h.page + ':' + h.rect.join(','); if (seen.has(k)) return false; seen.add(k); return true; });
  hits.sort((a, b) => a.page - b.page || a.rect[1] - b.rect[1]);       // reading order
  S.pdfHits = hits; S.pdfSizes = sizes; S.hitIdx = -1; S.pdfQuery = ''; S.pdfPage = page;
  renderPdf(t.snippet, t.label, S.pdfTerms);     // page stack with the terms highlighted
  renderHitNav();
  const landIdx = hits.findIndex(h => h.page === page);
  requestAnimationFrame(() => gotoHit(landIdx >= 0 ? landIdx : 0));
}

// ---- pdf pane --------------------------------------------------------------
// ---- middle pane: swap between the .pdf render and the docx transcription ----
function setMidMode(mode) {
  S.midMode = mode;
  document.querySelectorAll('#mid-toggle button').forEach(b => b.classList.toggle('on', b.dataset.mid === mode));
  const docx = mode === 'docx';
  $('#pdf-view').classList.toggle('hidden', docx);
  $('#pdf-snippet').classList.toggle('hidden', docx);
  const search = $('.pdf-search'); if (search) search.classList.toggle('hidden', docx);
  const pager = $('#pdf-pager'); if (pager) pager.style.visibility = docx ? 'hidden' : '';
  $('#docx-view').classList.toggle('hidden', !docx);
  if (docx) loadDocxView();
}

async function loadDocxView() {
  const key = S.key, view = $('#docx-view');
  if (!key || !view) return;
  if (S.docxHtml[key] != null) { view.innerHTML = S.docxHtml[key]; wireDocxView(); return; }
  view.innerHTML = '<div class="empty muted">rendering docx…</div>';
  let h = '';
  try {
    const r = await fetch('/api/docx/' + enc(key) + '.html').then(x => x.json());
    h = r.html || '';
  } catch (_) { h = ''; }
  if (h) S.docxHtml[key] = h;                  // cache only a successful render — a failure
  else h = '<div class="empty muted">could not render this docx</div>';   // retries on next open
  if (S.midMode === 'docx' && S.key === key) { view.innerHTML = h; wireDocxView(); }  // still on this entry/view
}

// wire the docx view after its HTML is injected: legend = per-author toggle buttons,
// comment chips = click-to-pin their text (no more hover-only tooltips).
function wireDocxView() {
  const view = $('#docx-view');
  view.querySelectorAll('.docx-authors .au').forEach(btn => {
    btn.onclick = e => {
      e.stopPropagation();
      const au = btn.dataset.author;
      S.docxHidden.has(au) ? S.docxHidden.delete(au) : S.docxHidden.add(au);
      applyDocxAuthorFilter();
    };
  });
  view.querySelectorAll('.cmt').forEach(chip => {
    chip.onclick = e => { e.stopPropagation(); showCmtPopover(chip); };
  });
  applyDocxAuthorFilter();
}

// hide/show each author's marks per S.docxHidden; reflect state on the legend buttons.
// "hide author" = show the document as if they never edited it: drop their insertions and
// comments, but for a DELETION keep its ORIGINAL (struck) text and merely un-strike it —
// removing a <del> would delete the base text and read as if the deletion were accepted.
function applyDocxAuthorFilter() {
  $('#docx-view').querySelectorAll('[data-author]').forEach(elm => {
    const off = S.docxHidden.has(elm.dataset.author);
    if (elm.classList.contains('au')) { elm.classList.toggle('off', off); return; }   // legend button
    const keepText = off && elm.tagName === 'DEL';                        // a hidden deletion: keep text
    elm.style.display = (off && !keepText) ? 'none' : '';                 // ins / comment: remove
    elm.classList.toggle('au-off', keepText);                            // del: neutralise to plain text
  });
}

// a pinned popover with a comment's full text (click a chip; click-away / Esc dismisses)
function showCmtPopover(chip) {
  hideCmtPopover();
  const pop = el('div', { class: 'cmt-pop', style: '--au:' + chip.style.getPropertyValue('--au'),
      onclick: e => e.stopPropagation() },
    el('div', { class: 'cmt-pop-au' }, chip.dataset.author || ''),
    el('div', { class: 'cmt-pop-body' }, chip.getAttribute('title') || '(empty comment)'));
  document.body.append(pop);
  const r = chip.getBoundingClientRect();
  pop.style.left = Math.max(8, Math.min(r.left, window.innerWidth - pop.offsetWidth - 12)) + 'px';
  pop.style.top = Math.min(r.bottom + 6, window.innerHeight - pop.offsetHeight - 8) + 'px';
  S.cmtPop = pop;
}
function hideCmtPopover() { if (S.cmtPop) { S.cmtPop.remove(); S.cmtPop = null; } }

async function openDocxInWord() {
  if (!S.key) return;
  const b = $('#open-docx'), old = b.textContent;
  b.textContent = 'opening…';
  let ok = false;
  try { ok = (await fetch('/api/open/' + enc(S.key), { method: 'POST' }).then(x => x.json())).ok; } catch (_) {}
  b.textContent = ok ? 'opened ✓' : 'open failed';
  setTimeout(() => { b.textContent = old; }, 1600);
}

function renderPdf(snippet, snipLabel, hlTerms) {
  const a = S.a, view = $('#pdf-view');
  $('#pdf-name').textContent = a.pdf ? a.pdf.name : '';
  if (S.pdfIO) { S.pdfIO.disconnect(); S.pdfIO = null; }
  if (!a.pdf) {
    view.innerHTML = '<div class="empty muted">no .pdf paired for this entry</div>';
    $('#pdf-pager').innerHTML = ''; $('#pdf-snippet').innerHTML = '';
    return;
  }
  const find = (S.pdfTerms || []).join('|');
  if (S.pdfMode === 'region') {
    const img = wireImgRetry(el('img', { src: `/api/pdf/${enc(a.key)}/region/${S.pdfPage}.png?find=${enc(find)}`,
                                         alt: 'highlight region' }));
    img.style.width = (S.pdfZoom * 100) + '%';
    view.replaceChildren(img);
  } else {
    buildPageStack(a, find);
  }
  renderPager();
  syncZoomUI();
  if (snippet !== undefined) renderSnippet(snippet, snipLabel, hlTerms || S.pdfTerms);
}

// Fetch every page's point size ONCE per entry, so each page slot can reserve its true
// height up front (via aspect-ratio). Without this, unloaded pages hold a short placeholder
// and a far scroll-to-hit lands wrong once real images load and shift the layout.
function ensureSizes() {
  if (S.pageSizesKey === S.a.key && S.pageSizes) return S.sizesPromise || Promise.resolve();
  S.pageSizesKey = S.a.key; S.pageSizes = null;
  S.sizesPromise = fetch(`/api/pdf/${enc(S.a.key)}/sizes.json`).then(x => x.json())
    .then(arr => { S.pageSizes = arr || []; applyPageAspects(); })
    .catch(() => { S.pageSizes = []; });
  return S.sizesPromise;
}
function applyPageAspects() {
  if (!S.pageSizes || !S.pageSizes.length) return;
  $('#pdf-view').querySelectorAll('.pdf-page .page-inner').forEach(inner => {
    const i = +inner.parentElement.getAttribute('data-page'), sz = S.pageSizes[i];
    if (sz && sz[1]) inner.style.aspectRatio = (sz[0] / sz[1]).toFixed(4);
  });
}

// One automatic retry for a page render that failed (a 404 while the crashed MuPDF
// worker pool rebuilds, a dropped connection): without it the failed <img> keeps its
// src, so the `!img.src` lazy-load guard never re-requests it and the slot stays
// blank forever. Retries once after ~1.5 s (dataset attempt counter, max 2).
function wireImgRetry(img) {
  img.addEventListener('error', () => {
    const attempt = +(img.dataset.attempt || 1);
    const src = img.getAttribute('src');
    if (attempt >= 2 || !src) return;                  // one retry only
    img.dataset.attempt = String(attempt + 1);
    img.removeAttribute('src');
    setTimeout(() => { if (img.isConnected && !img.getAttribute('src')) img.src = src; }, 1500);
  });
  return img;
}

// a continuously-scrollable stack of all pages, lazy-loaded as they approach view
function buildPageStack(a, find) {
  const view = $('#pdf-view');
  const url = i => `/api/pdf/${enc(a.key)}/page/${i}.png?find=${enc(find)}`;
  const wrap = el('div', { class: 'pdf-pages' });
  const slots = [];
  for (let i = 0; i < a.pdf.pages; i++) {
    const img = wireImgRetry(el('img', { alt: 'page ' + (i + 1) }));
    const tl = el('div', { class: 'text-layer' });        // selectable text overlay (copy + native find)
    const inner = el('div', { class: 'page-inner' }, img, tl);   // shrink-wraps the img; the text layer aligns to it
    inner.style.width = (S.pdfZoom * 100) + '%';                 // zoom lives on the wrapper so the overlay tracks the img
    const slot = el('div', { class: 'pdf-page', 'data-page': i }, inner);
    wrap.append(slot); slots.push(slot);
  }
  view.replaceChildren(wrap);
  S.pdfRatios = {};
  S.pdfIO = new IntersectionObserver(ents => {
    for (const e of ents) {
      const i = +e.target.getAttribute('data-page');
      S.pdfRatios[i] = e.isIntersecting ? e.intersectionRatio : 0;
      if (e.isIntersecting) {                       // lazy-load on approach
        const img = e.target.querySelector('img');
        if (img && !img.src) { img.src = url(i); buildTextLayer(a, i, e.target); }
      }
    }
    let best = S.pdfPage, r = -1;                    // current page = most-visible slot
    for (const k in S.pdfRatios) if (S.pdfRatios[k] > r) { r = S.pdfRatios[k]; best = +k; }
    if (best !== S.pdfPage) { S.pdfPage = best; updatePagerLabel(); }
  }, { root: view, rootMargin: '600px 0px', threshold: [0, 0.25, 0.5, 1] });
  slots.forEach(s => S.pdfIO.observe(s));
  ensureSizes();                   // (clears stale sizes on entry switch, then) fetches if needed
  applyPageAspects();              // reserve true heights now if this entry's sizes are known
  const target = slots[Math.min(S.pdfPage, slots.length - 1)];   // jump to the evidence page
  if (target) requestAnimationFrame(() => target.scrollIntoView({ block: 'start' }));
}

// Overlay transparent, word-positioned, selectable text on a rendered page so the
// reviewer can SELECT/COPY text and use the browser's native find (Cmd/Ctrl-F, with
// its own next/prev). Positions are % of the page; font-size uses container-query
// height units so it scales with zoom automatically (no rebuild on zoom).
async function buildTextLayer(a, i, slot) {
  const tl = slot.querySelector('.text-layer');
  if (!tl || tl.dataset.built) return;
  tl.dataset.built = '1';
  try {
    const d = await fetch(`/api/pdf/${enc(a.key)}/words/${i}.json`).then(x => x.json());
    if (!d.w || !d.h || !d.words) return;
    const frag = document.createDocumentFragment();
    for (const w of d.words) {
      const [x0, y0, x1, y1, word] = w;
      const s = document.createElement('span');
      // Trailing space so copy/paste keeps word separators: get_text('words')
      // yields one box per word with no whitespace, and adjacent inline spans
      // serialize as 'wordword'. The span is color:transparent, so it stays invisible.
      s.textContent = word + ' ';
      s.style.left = (x0 / d.w * 100) + '%';
      s.style.top = (y0 / d.h * 100) + '%';
      s.style.fontSize = ((y1 - y0) / d.h * 100 * 0.82) + 'cqh';
      frag.append(s);
    }
    tl.append(frag);
  } catch (e) { /* no text layer for this page */ }
}

function syncZoomUI() {
  $('#zoom-val').textContent = Math.round(S.pdfZoom * 100) + '%';
  $('#zoom-page').classList.toggle('on', S.pdfMode === 'page');
  $('#zoom-hit').classList.toggle('on', S.pdfMode === 'region');
}

function setZoom(z) {
  S.pdfZoom = Math.max(0.5, Math.min(4, z));
  const v = $('#pdf-view'), w = (S.pdfZoom * 100) + '%';
  v.querySelectorAll('.page-inner').forEach(p => p.style.width = w);   // page mode (img + text layer track the wrapper)
  v.querySelectorAll(':scope > img').forEach(img => img.style.width = w);   // region mode (bare img)
  $('#zoom-val').textContent = Math.round(S.pdfZoom * 100) + '%';
}

function updatePagerLabel() {
  const l = document.getElementById('pager-label');
  if (l && S.a && S.a.pdf) l.textContent = `p.${S.pdfPage + 1} / ${S.a.pdf.pages}`;
}
function scrollToPage(i) {
  i = Math.max(0, Math.min(S.a.pdf.pages - 1, i));
  const slot = $('#pdf-view').querySelector(`.pdf-page[data-page="${i}"]`);
  if (slot) slot.scrollIntoView({ block: 'start', behavior: 'smooth' });
}

function renderPager() {
  const a = S.a, p = $('#pdf-pager'); p.innerHTML = '';
  if (S.pdfMode === 'region') {
    const crop = S.lookLabel ? 'crop: ' + S.lookLabel + ' · ' : 'highlight crop · ';
    p.append(el('span', { class: 'muted' }, crop),
      el('button', { onclick: () => { S.pdfMode = 'page'; S.pdfZoom = 1; renderPdf(undefined); } }, 'full page'));
    // hint that another '? look' cycles to the next target (multi-group findings only)
    const f = findingOf(S.focusKey);      // null for the cell/param/lam pseudo-keys
    const g = lookGroups(f);
    if (g && g.length > 1) {
      const next = g[(S.lookStep[S.focusKey] || 0) % g.length].label;
      p.append(el('span', { class: 'muted' }, ' · ? look → ' + next));
    }
    return;
  }
  p.append(
    el('button', { onclick: () => scrollToPage(S.pdfPage - 1) }, '‹'),
    el('span', { id: 'pager-label' }, `p.${S.pdfPage + 1} / ${a.pdf.pages}`),
    el('button', { onclick: () => scrollToPage(S.pdfPage + 1) }, '›'));
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
  // pressing Enter again on the same query steps to the next hit (Acrobat-style)
  if (q === S.pdfQuery && S.pdfHits.length) { stepHit(1); return; }
  S.pdfQuery = q;
  const r = await fetch(`/api/pdf/${enc(S.a.key)}/search?q=${enc(q)}`)
    .then(x => x.json()).catch(() => ({ pages: [], hits: [], sizes: {} }));
  S.pdfHits = r.hits || []; S.pdfSizes = r.sizes || {}; S.hitIdx = -1;
  S.pdfTerms = [q]; S.pdfMode = 'page'; S.pdfZoom = 1;
  if (S.pdfHits.length) S.pdfPage = S.pdfHits[0].page;
  renderPdf('', '', [q]);                 // rebuild the page stack with q highlighted
  renderHitNav();
  if (S.pdfHits.length) requestAnimationFrame(() => gotoHit(0));
}

// the search-box hit counter + ‹ › stepper (Acrobat-style click-through)
function renderHitNav() {
  const box = $('#pdf-hits'); box.innerHTML = '';
  const n = S.pdfHits.length;
  if (!n) { box.textContent = S.pdfQuery ? 'no hits' : ''; return; }
  const pages = new Set(S.pdfHits.map(h => h.page)).size;
  box.append(
    el('button', { class: 'hitnav', title: 'previous hit (Shift-Enter)', onclick: () => stepHit(-1) }, '‹'),
    el('span', { id: 'hit-counter' }, `${Math.max(S.hitIdx + 1, 1)}/${n}`),
    el('button', { class: 'hitnav', title: 'next hit (Enter)', onclick: () => stepHit(1) }, '›'),
    el('span', { class: 'muted' }, ` · ${n} hit${n > 1 ? 's' : ''} on ${pages} page${pages > 1 ? 's' : ''}`));
}

function stepHit(d) {
  if (!S.pdfHits.length) return;
  const n = S.pdfHits.length;
  gotoHit(((S.hitIdx + d) % n + n) % n);   // wrap around
}

// jump to one search hit: scroll the live page-stack to it and flash a box on it
function gotoHit(idx) {
  const h = S.pdfHits[idx]; if (!h) return;
  S.hitIdx = idx;
  const c = $('#hit-counter'); if (c) c.textContent = `${idx + 1}/${S.pdfHits.length}`;
  scrollToHit(h.page, h.rect);
}

// scroll #pdf-view so the hit on `page` (rect in PDF points) is centred, then flash it.
// Stays in the navigable page view — no dead-end crop. Awaits page sizes first so every slot
// has reserved its true height (no layout shift) and the scroll target is exact.
async function scrollToHit(page, rect) {
  const view = $('#pdf-view');
  await ensureSizes();                                   // heights stable before we measure
  const slot = view.querySelector(`.pdf-page[data-page="${page}"]`);
  if (!slot) return;
  S.pdfPage = page; updatePagerLabel();
  const img = slot.querySelector('img');
  if (img && !img.getAttribute('src')) {                 // load the target page's image (visual)
    img.src = `/api/pdf/${enc(S.a.key)}/page/${page}.png?find=${enc((S.pdfTerms || []).join('|'))}`;
    buildTextLayer(S.a, page, slot);
  }
  requestAnimationFrame(() => {
    const inner = slot.querySelector('.page-inner');
    const sz = (S.pageSizes && S.pageSizes[page]) || S.pdfSizes[page];
    if (!sz || !inner) { slot.scrollIntoView({ block: 'center' }); return; }
    const [w, hh] = sz;
    // measure the page-inner (the box the hit % are relative to) — at zoom>1 it is wider than
    // the slot and overflows it, so the slot's width would under-shoot a right-column hit
    const ir = inner.getBoundingClientRect(), vr = view.getBoundingClientRect();
    const fb = el('div', { class: 'hit-flash' });
    fb.style.left = (rect[0] / w * 100) + '%'; fb.style.top = (rect[1] / hh * 100) + '%';
    fb.style.width = ((rect[2] - rect[0]) / w * 100) + '%';
    fb.style.height = ((rect[3] - rect[1]) / hh * 100) + '%';
    inner.appendChild(fb);
    setTimeout(() => fb.remove(), 1900);
    const hitTop = (ir.top - vr.top) + view.scrollTop + (rect[1] / hh) * ir.height;
    const hitH = ((rect[3] - rect[1]) / hh) * ir.height;
    const hitCx = (ir.left - vr.left) + view.scrollLeft + ((rect[0] + rect[2]) / 2 / w) * ir.width;
    view.scrollTo({ top: Math.max(0, hitTop - view.clientHeight / 2 + hitH / 2),
                    left: Math.max(0, hitCx - view.clientWidth / 2), behavior: 'smooth' });   // centre both axes
  });
}

// ---- docx pane -------------------------------------------------------------
function renderDocx() {
  const a = S.a, body = $('#docx-body'); body.innerHTML = '';
  const ac = a.docx.authors_cell || [];
  // green = the docx axis value matches the .pdf cell, red = it differs (a/b/c via the
  // match tolerance; angles by direct compare). Only when a .pdf cell was actually matched.
  let cmp = null;
  if (a.cell.matched) {
    cmp = {};
    for (const d of (a.cell.deltas || [])) cmp[d[0]] = !!d[4];        // a, b, c : within tolerance?
    const m = a.cell.matched;
    for (const [ax, dv, pv] of [['α', ac[3], m.al], ['β', ac[4], m.be], ['γ', ac[5], m.ga]]) {
      const x = parseFloat(dv), y = parseFloat(pv);
      if (isFinite(x) && isFinite(y)) cmp[ax] = Math.abs(x - y) <= 0.1;
    }
  }
  body.append(el('div', { class: 'sub' }, 'DOCX cell'));
  body.append(cellGrid(ac, a.params, a.cell.deltas, cmp));
  if (a.cell.matched) {
    const m = a.cell.matched;
    body.append(el('div', { class: 'sub' }, 'Cell from PDF' + (m.phase ? ' · ' + m.phase : '')));
    body.append(cellGrid([m.a, m.b, m.c, m.al, m.be, m.ga, '', m.Z], {}, []));
  }

  // Compound Names (docx): Mineral, Primary Warr symbol, Primary systematic name
  const cn = (a.entry && a.entry.compound_names) || [];
  if (cn.length) {
    body.append(el('div', { class: 'sub' }, 'Compound Names'));
    body.append(kvTable(cn));
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
  // the reviewer's OWN marks — tracked changes / non-tool comments the tool preserves but
  // never writes (from the reviewed copy, or the source docx when pointed at a reviewer's own
  // folder). Filterable by author; each item is kind + text + author. Read live.
  renderReviewerEdits(body);
}

const REKIND = { change: 'change', ins: 'insert', del: 'delete', comment: 'comment' };
function renderReviewerEdits(body) {
  const ue = S.ue || [];
  if (!ue.length) return;
  const authors = [...new Set(ue.map(m => m.author))];
  if (S.ueAuthor !== 'All' && !authors.includes(S.ueAuthor)) S.ueAuthor = 'All';  // stale filter -> reset
  const shown = ue.filter(m => S.ueAuthor === 'All' || m.author === S.ueAuthor);

  const head = el('div', { class: 'sub re-sub' },
    el('span', {}, 'reviewer edits'),
    el('span', { class: 'muted' }, ` ${shown.length}${shown.length !== ue.length ? '/' + ue.length : ''}`));
  // author filter — one chip per distinct author (+ All). Persists across entries when the
  // author is present, so paging through one reviewer's folder keeps their marks in view.
  if (authors.length > 1 || S.ueAuthor !== 'All') {
    const filt = el('span', { class: 're-filter' });
    const chip = (val, lbl) => el('button', {
      class: 're-chip' + (S.ueAuthor === val ? ' on' : ''),
      onclick: () => { S.ueAuthor = val; renderDocx(); }
    }, lbl);
    filt.append(chip('All', 'All'), ...authors.map(a => chip(a, a)));
    head.append(el('span', { class: 'spacer' }), filt);
  }
  body.append(head);

  const box = el('div', { class: 'reviewer-edits' });
  for (const m of shown)
    box.append(el('div', { class: 'redit' },
      el('span', { class: 're-kind k-' + m.kind }, REKIND[m.kind] || m.kind),
      el('span', { class: 're-text' }, m.text || ''),
      el('span', { class: 're-auth' }, m.author || '')));
  body.append(box);
}

const AXES = ['a', 'b', 'c', 'α', 'β', 'γ', 'SG', 'Z'];   // laid out 3-per-row: abc / αβγ / SG Z
function cellGrid(vals, params, deltas, cmp) {
  params = params || {}; deltas = deltas || []; cmp = cmp || null;
  const dmap = {}; for (const [lab, , , dd, ok] of deltas) dmap[lab] = { dd, ok };
  vals = vals.slice(0, 8);
  const g = el('div', { class: 'cellgrid' });
  for (let i = 0; i < 8; i++) {
    const ax = AXES[i]; let cls = 'cellcell';
    const flagged = params[ax];                              // the tool flagged this axis
    if (flagged) cls += flagged.some(([k]) => k === 'value') ? ' miss' : ' near';  // value diff -> red, sig-fig/esd -> orange
    else if (cmp && ax in cmp) cls += cmp[ax] ? ' ok' : ' miss';   // green = matches .pdf cell, red = differs
    else if (dmap[ax] && dmap[ax].ok && dmap[ax].dd > 0.002 && dmap[ax].dd <= 0.004) cls += ' near';
    const v = esc(vals[i]) || '—';                // em dash = not reported (vs a stray dot)
    g.append(el('div', { class: cls, title: ax + ' = ' + v },
      el('span', { class: 'cl' }, ax), el('span', { class: 'cv' }, v)));
  }
  return g;
}

function kvTable(pairs) {
  const t = el('table', { class: 'kv' });
  for (const [k, v] of pairs)
    t.append(el('tr', {}, el('td', { class: 'k' }, esc(k)),
                          el('td', {}, (v && v.nodeType) ? v : esc(v))));   // allow a DOM node value (e.g. a formatted formula)
  return t;
}

// Render a chemical formula's <sub>/<sup> markup (Mindat ima_formula) as a node —
// sanitised: only those two tags pass through, everything else stays literal text.
function fmtFormula(s) {
  const span = el('span', { class: 'formula' });
  span.textContent = s || '';                                   // escapes < > & to entities
  span.innerHTML = span.innerHTML.replace(/&lt;(\/?)(sub|sup)&gt;/gi, '<$1$2>');
  return span;
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
    if (M.formula) kv.push(['IMA formula', fmtFormula(M.formula)]);
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
  if (!S.key || !S.t) return;       // no entry cleanly open — nothing to save under
  clearTimeout(S.saveTimer);
  S.pendingSave = { key: S.key, payload: JSON.stringify(S.t) };   // capture NOW (entry may change first)
  S.saveTimer = setTimeout(flushTriage, 350);
}
// write any debounced triage IMMEDIATELY — called before we open another entry, switch folder,
// rerun, or close the tab, so a confirm/dismiss can never be lost to the debounce window or a
// folder change. Returns the save's promise (a rerun awaits it so it reads the latest sidecar);
// no-op when nothing is pending — the server already has the latest state.
function flushTriage() {
  clearTimeout(S.saveTimer);
  const p = S.pendingSave; S.pendingSave = null;
  if (!p) return Promise.resolve();
  return fetch('/api/triage/' + encodeURIComponent(p.key), {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: p.payload, keepalive: true,   // keepalive => still sent if the page is unloading
  }).catch(() => {});
}

// ---- rerun (regenerate docx with triage applied) ---------------------------
async function rerun(url, btn, busyLabel, doneLabel) {
  await flushTriage();
  // both buttons off while ANY rerun is in flight — the server 409s a concurrent
  // rerun anyway (two subprocesses would race on the same output docx)
  const btns = ['#rerun-entry', '#rerun-all'].map($).filter(Boolean);
  if (btns.some(b => b.disabled)) return;
  btns.forEach(b => { b.disabled = true; });
  const orig = btn.textContent;
  btn.classList.add('busy'); btn.textContent = busyLabel;
  $('#rerun-status').textContent = busyLabel;
  let r;
  try { r = await fetch(url, { method: 'POST' }).then(x => x.json()); }
  catch (ex) { r = { ok: false, error: String(ex) }; }
  btns.forEach(b => { b.disabled = false; });
  btn.classList.remove('busy'); btn.textContent = orig;
  $('#rerun-status').textContent = r.ok ? doneLabel : ('rerun failed' + (r.error ? ': ' + r.error : ''));
  setTimeout(() => { $('#rerun-status').textContent = ''; }, 5000);
}

// ---- navigation ------------------------------------------------------------
function step(delta) {
  // navigate within the currently-visible (filtered/sorted) order
  const keys = sortedEntries().filter(e => visibleKey(e)).map(e => e.key);
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
$('#sort').addEventListener('change', ev => { S.sort = ev.target.value; renderList(); });
document.querySelectorAll('#views button').forEach(b =>
  b.addEventListener('click', () => {
    S.view = b.getAttribute('data-view');
    document.querySelectorAll('#views button').forEach(x => x.classList.toggle('on', x === b));
    renderList();
  }));
$('#rerun-entry').addEventListener('click', () => {
  if (!S.key) return;               // no entry cleanly open
  rerun('/api/rerun/' + encodeURIComponent(S.key), $('#rerun-entry'),
        'Rerunning…', 'regenerated this docx ✓');
});
$('#rerun-all').addEventListener('click', () =>
  rerun('/api/rerun', $('#rerun-all'), 'Rerunning all…', 'regenerated all docx ✓'));
document.querySelectorAll('#mid-toggle button').forEach(b =>
  b.addEventListener('click', () => setMidMode(b.dataset.mid)));
$('#open-docx').addEventListener('click', openDocxInWord);
window.addEventListener('beforeunload', flushTriage);                           // don't lose a triage click on tab close
document.addEventListener('click', hideCmtPopover);                              // click-away closes the comment popover
document.addEventListener('keydown', e => { if (e.key === 'Escape') hideCmtPopover(); });
// dashboard 'Log' button: open the tool's change log (annotation_log.txt) in a new tab,
// falling back to whatever review-out log exists (triage_report / mindat_discrepancies / sweep).
$('#open-log').addEventListener('click', async () => {
  let logs = [];
  try { logs = (await fetch('/api/logs').then(x => x.json())).logs || []; } catch (_) {}
  const pick = logs.includes('annotation_log.txt') ? 'annotation_log.txt' : logs[0];
  if (!pick) {
    const s = $('#rerun-status');
    s.textContent = "no log yet — run 'Rerun all' (annotation_log) or 'Export triage'";
    setTimeout(() => { s.textContent = ''; }, 4000);
    return;
  }
  window.open('/api/log?name=' + enc(pick), '_blank');
});
$('#prev').addEventListener('click', () => step(-1));
$('#next').addEventListener('click', () => step(1));
$('#pdf-q').addEventListener('keydown', e => {
  if (e.key !== 'Enter') return;
  const v = e.target.value.trim();
  if (e.shiftKey && v === S.pdfQuery && S.pdfHits.length) stepHit(-1);   // Shift-Enter = previous hit
  else pdfSearch(v);
});
$('#zoom-in').addEventListener('click', () => setZoom(S.pdfZoom + 0.25));
$('#zoom-out').addEventListener('click', () => setZoom(S.pdfZoom - 0.25));
// trackpad two-finger pinch (and ctrl+scroll) over the .pdf pane zooms the PDF ONLY, not the
// whole window: browsers deliver a pinch as a wheel event with ctrlKey set, so we take it on a
// NON-passive listener, preventDefault() to stop the page zoom, scale the PDF via setZoom, and
// adjust scroll so the point under the cursor stays put (focal zoom). Per-event step is capped
// so a coarse ctrl+mouse-wheel can't jump in one tick.
$('#pdf-view').addEventListener('wheel', e => {
  if (!e.ctrlKey || !S.a || !S.a.pdf) return;     // only a pinch/ctrl-scroll over a loaded PDF
  e.preventDefault();
  const v = $('#pdf-view'), r = v.getBoundingClientRect();
  const cx = e.clientX - r.left, cy = e.clientY - r.top;   // cursor within the view
  const before = S.pdfZoom;
  const step = Math.max(0.8, Math.min(1.25, Math.exp(-e.deltaY * 0.01)));   // pinch out (Δy<0) → in
  setZoom(before * step);
  const f = S.pdfZoom / before;                   // actual factor after setZoom's 0.5–4 clamp
  if (f !== 1) { v.scrollLeft = (v.scrollLeft + cx) * f - cx; v.scrollTop = (v.scrollTop + cy) * f - cy; }
}, { passive: false });
$('#zoom-hit').addEventListener('click', () => { if (S.focusKey) zoomToHighlight(S.focusKey); });
$('#zoom-page').addEventListener('click', () => {
  S.pdfMode = 'page'; S.pdfZoom = 1; renderPdf(undefined);
});
$('#export').addEventListener('click', async () => {
  let r;
  try { r = await fetch('/api/triage/export', { method: 'POST' }).then(x => x.json()); }
  catch (ex) { r = { ok: false, error: String(ex) }; }
  $('#export').textContent = r && r.ok ? 'Exported ✓' : 'Export failed';
  if (!(r && r.ok)) {
    const st = $('#rerun-status');
    st.textContent = 'triage export failed' + (r && r.error ? ': ' + r.error : '');
    setTimeout(() => { st.textContent = ''; }, 5000);
  }
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
  hideNotes: false,
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
  // folder picker: the header chip (path + Change…) toggles it; close on click-away
  $('#folder-ctl').addEventListener('click', e => {
    e.stopPropagation();
    if ($('#folderpanel').classList.contains('hidden')) openFolderPanel();
    else $('#folderpanel').classList.add('hidden');
  });
  $('#folder-browse').addEventListener('click', pickFolderNative);
  $('#folder-open').addEventListener('click', () => openFolder($('#folder-path').value));
  $('#folder-path').addEventListener('keydown', e => { if (e.key === 'Enter') openFolder(e.target.value); });
  document.addEventListener('click', e => {
    if (!$('#folderpanel').classList.contains('hidden') &&
        !e.target.closest('#folderpanel') && !e.target.closest('#folder-ctl'))
      $('#folderpanel').classList.add('hidden');
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
  const hn = $('#hide-notes');
  hn.checked = !!CFG.hideNotes;
  hn.addEventListener('change', () => { CFG.hideNotes = hn.checked; saveCfg(); if (S.a) renderFindings(); });
}

initAppearance();
loadEntries();

// Auto-shutdown: the server exits shortly after this tab CLOSES — never on idle.
// - on unload (close / navigate / reload) beacon the server so it starts a short grace;
// - a light heartbeat lets a still-open tab (or a reload) reconnect within that grace and cancel
//   the shutdown. An open tab — idle, backgrounded, or asleep — is never shut down.
window.addEventListener('pagehide', () => { try { navigator.sendBeacon('/api/closing'); } catch (_) {} });
setInterval(() => fetch('/api/ping').catch(() => {}), 15000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) fetch('/api/ping').catch(() => {}); });
