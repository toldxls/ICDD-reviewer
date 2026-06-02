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
  pdfMode: 'page',    // 'page' = scrollable full pages | 'region' = zoomed crop around the hit
  pdfZoom: 1,         // display scale of whatever is shown
  focusKey: null,     // the finding currently driving the PDF pane
  pdfIO: null,        // IntersectionObserver for lazy page loading + current-page tracking
  pdfRatios: {},      // page -> visible ratio (to pick the current page)
  saveTimer: null,
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
  // default PDF focus = the cell evidence (full-page scroll, jumps to the cell page)
  S.pdfMode = 'page'; S.pdfZoom = 1;
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
  for (const f of a.findings) if (f.written) tally('f' + f.idx);
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
    rows.push({ fkey: 'f' + f.idx, level, code: f.code, msg: f.msg, written: f.written, anchor: f.anchor, minor: !f.major });
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
  const t = (S.t.findings[r.fkey] = S.t.findings[r.fkey] || {});
  t.label = `${r.code}: ${(r.msg || '').slice(0, 80)}`;
  const top = el('div', { class: 'f-top' }, el('span', { class: 'sev ' + r.level }, SEV_LABEL[r.level] || r.level));
  if (r.level !== 'ok')                       // an 'OK' result writes nothing — no tag needed
    top.append(r.written ? el('span', { class: 'wtag written' }, 'written to docx')
                         : el('span', { class: 'wtag console' }, 'console-only'));
  top.append(el('span', { class: 'f-code' }, r.code));
  return el('div', { class: 'finding lvl-' + r.level + (r.minor ? ' minor' : ''), 'data-fkey': r.fkey, onclick: () => focusFinding(r.fkey) },
    top,
    el('div', { class: 'f-msg' }, r.msg || ''),
    r.anchor ? el('div', { class: 'f-anchor' }, '↳ docx anchor: ' + r.anchor) : null,
    triageControls(r.fkey, t));
}

function triageControls(fkey, t) {
  const mk = (v, lbl) => el('button', {
    class: 'tbtn ' + v + (t.verdict === v ? ' on' : ''),
    onclick: ev => {
      ev.stopPropagation();
      // '? look' ALWAYS zooms the PDF to this finding's evidence (not gated on the
      // toggle state) — and zoom first, before the list re-render, so the first
      // click takes effect immediately.
      if (v === 'look') zoomToHighlight(fkey);
      t.verdict = (t.verdict === v ? null : v);
      saveTriage(); renderFindings();
    }
  }, lbl);
  const note = el('input', { class: 'tnote', type: 'text', placeholder: 'note…',
    value: t.note || '',
    onclick: ev => ev.stopPropagation(),
    oninput: ev => { t.note = ev.target.value; saveTriage(); } });
  return el('div', { class: 'triage' }, mk('confirm', '✓ confirm'),
    mk('dismiss', '✗ dismiss'), mk('look', '? look'), note);
}

// the PDF search terms + snippet for a given finding
function termsFor(fkey) {
  const a = S.a;
  let terms = [], snippet = '', label = '', page = (a.pdf ? a.pdf.evidence_page || 0 : 0);
  if (fkey === 'cell' || fkey.startsWith('param:')) {
    terms = (a.pdf && a.pdf.terms) || [];
    if (a.cell.matched) { snippet = a.cell.matched.snippet || ''; label = 'matched cell context [' + (a.cell.matched.context || '?') + ']'; }
  } else if (fkey === 'lam') {
    const m = /([A-Za-z]{1,2})\s*K/.exec(a.docx.radiation || '');
    if (m) terms = [m[1] + 'K'];
  } else if (fkey.startsWith('f')) {
    const f = a.findings[parseInt(fkey.slice(1), 10)];
    if (f) {
      if (f.code === 'indexing' && a.entry && (a.entry.refl_d || []).length) {
        // the reflection d-spacings cluster in the paper's powder table -> frame it
        terms = a.entry.refl_d;
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
    [/debye/i, 'Debye'], [/image[\s-]*plate|imaging plate/i, 'plate'], [/r[-\s]?axis/i, 'AXIS'],
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
  renderPdf(t.snippet, t.label, t.terms);
}

// zoom the PDF to a cropped region framing the finding's highlighted text. When the
// finding has many terms (e.g. an indexing finding's reflection d-spacings), find the
// page where they CLUSTER (the powder table) and let the region crop expand to it.
async function zoomToHighlight(fkey) {
  S.focusKey = fkey;
  const t = termsFor(fkey);
  if (!S.a.pdf || !t.terms.length) { focusFinding(fkey); return; }   // nothing to locate
  let page = t.page;
  try {
    const probe = t.terms.slice(0, 8);
    const res = await Promise.all(probe.map(term =>
      fetch(`/api/pdf/${encodeURIComponent(S.a.key)}/search?q=${encodeURIComponent(term)}`)
        .then(x => x.json()).catch(() => ({ hits: [] }))));
    const pageHits = {};
    for (const r of res) for (const h of (r.hits || [])) pageHits[h.page] = (pageHits[h.page] || 0) + h.count;
    const best = Object.keys(pageHits).sort((a, b) => pageHits[b] - pageHits[a])[0];
    if (best !== undefined) page = +best;
  } catch (e) { /* keep evidence page */ }
  S.pdfTerms = t.terms.slice(0, 20); S.pdfPage = page; S.pdfMode = 'region'; S.pdfZoom = 1;
  renderPdf(t.snippet, t.label, S.pdfTerms);
}

// ---- pdf pane --------------------------------------------------------------
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
    const img = el('img', { src: `/api/pdf/${enc(a.key)}/region/${S.pdfPage}.png?find=${enc(find)}`,
                            alt: 'highlight region' });
    img.style.width = (S.pdfZoom * 100) + '%';
    view.replaceChildren(img);
  } else {
    buildPageStack(a, find);
  }
  renderPager();
  syncZoomUI();
  if (snippet !== undefined) renderSnippet(snippet, snipLabel, hlTerms || S.pdfTerms);
}

// a continuously-scrollable stack of all pages, lazy-loaded as they approach view
function buildPageStack(a, find) {
  const view = $('#pdf-view');
  const url = i => `/api/pdf/${enc(a.key)}/page/${i}.png?find=${enc(find)}`;
  const wrap = el('div', { class: 'pdf-pages' });
  const slots = [];
  for (let i = 0; i < a.pdf.pages; i++) {
    const img = el('img', { alt: 'page ' + (i + 1) });
    img.style.width = (S.pdfZoom * 100) + '%';
    const slot = el('div', { class: 'pdf-page', 'data-page': i }, img);
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
        if (img && !img.src) img.src = url(i);
      }
    }
    let best = S.pdfPage, r = -1;                    // current page = most-visible slot
    for (const k in S.pdfRatios) if (S.pdfRatios[k] > r) { r = S.pdfRatios[k]; best = +k; }
    if (best !== S.pdfPage) { S.pdfPage = best; updatePagerLabel(); }
  }, { root: view, rootMargin: '600px 0px', threshold: [0, 0.25, 0.5, 1] });
  slots.forEach(s => S.pdfIO.observe(s));
  const target = slots[Math.min(S.pdfPage, slots.length - 1)];   // jump to the evidence page
  if (target) requestAnimationFrame(() => target.scrollIntoView({ block: 'start' }));
}

function syncZoomUI() {
  $('#zoom-val').textContent = Math.round(S.pdfZoom * 100) + '%';
  $('#zoom-page').classList.toggle('on', S.pdfMode === 'page');
  $('#zoom-hit').classList.toggle('on', S.pdfMode === 'region');
}

function setZoom(z) {
  S.pdfZoom = Math.max(0.5, Math.min(4, z));
  $('#pdf-view').querySelectorAll('img').forEach(img => img.style.width = (S.pdfZoom * 100) + '%');
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
    p.append(el('span', { class: 'muted' }, 'highlight crop · '),
      el('button', { onclick: () => { S.pdfMode = 'page'; S.pdfZoom = 1; renderPdf(undefined); } }, 'full page'));
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
  const r = await fetch(`/api/pdf/${encodeURIComponent(S.a.key)}/search?q=${encodeURIComponent(q)}`).then(x => x.json());
  const hits = r.hits || [];
  $('#pdf-hits').textContent = hits.length
    ? `${hits.reduce((s, h) => s + h.count, 0)} hit(s) on ${hits.length} page(s)`
    : 'no hits';
  if (hits.length) { S.pdfPage = hits[0].page; S.pdfTerms = [q]; S.pdfMode = 'page'; S.pdfZoom = 1; renderPdf('', '', [q]); }
}

// ---- docx pane -------------------------------------------------------------
function renderDocx() {
  const a = S.a, body = $('#docx-body'); body.innerHTML = '';
  const ac = a.docx.authors_cell || [];
  body.append(el('div', { class: 'sub' }, "Author's cell (docx)"));
  body.append(cellGrid(ac, a.params, a.cell.deltas));
  if (a.cell.matched) {
    const m = a.cell.matched;
    body.append(el('div', { class: 'sub' }, '.pdf matched cell — ' + (a.cell.provenance || m.context || '?') + (m.phase ? ' · ' + m.phase : '')));
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

const AXES = ['a', 'b', 'c', 'α', 'β', 'γ', 'SG', 'Z'];   // laid out 3-per-row: abc / αβγ / SG Z
function cellGrid(vals, params, deltas) {
  params = params || {}; deltas = deltas || [];
  const dmap = {}; for (const [lab, , , dd, ok] of deltas) dmap[lab] = { dd, ok };
  vals = vals.slice(0, 8);
  const g = el('div', { class: 'cellgrid' });
  for (let i = 0; i < 8; i++) {
    const ax = AXES[i]; let cls = 'cellcell';
    if (params[ax]) cls += ' bad';
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
  const key = S.key, payload = JSON.stringify(S.t);   // capture NOW — the entry may change before the timer fires
  S.saveTimer = setTimeout(() => {
    fetch('/api/triage/' + encodeURIComponent(key), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: payload,
    });
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
$('#zoom-in').addEventListener('click', () => setZoom(S.pdfZoom + 0.25));
$('#zoom-out').addEventListener('click', () => setZoom(S.pdfZoom - 0.25));
$('#zoom-hit').addEventListener('click', () => { if (S.focusKey) zoomToHighlight(S.focusKey); });
$('#zoom-page').addEventListener('click', () => {
  S.pdfMode = 'page'; S.pdfZoom = 1; renderPdf(undefined);
});
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
