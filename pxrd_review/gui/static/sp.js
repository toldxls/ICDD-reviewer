// The spectrum window (/spectra) — a Raman / infrared spectrum imported, cleaned, baselined and fitted.
// Every fitted number comes from the server (pxrd_review.spectrum, the same code `pxrd spectrum` runs); this page draws,
// lets the bands be edited, and sends back file NAMES and options — never a path. Nothing is written until Export.
'use strict';

const $ = sel => document.querySelector(sel);
const enc = encodeURIComponent;
if (!window.chemNodes) {                                  // chem.js did not load (an old Safari without regex lookbehind): formulas plain, nothing breaks
  window.chemTokens = t => [['', t == null ? '' : String(t)]];
  window.chemNodes = t => document.createTextNode(t == null ? '' : String(t));
  window.chemSvg = (e, t) => { e.append(document.createTextNode(t == null ? '' : String(t))); return e; };
}
function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  if (attrs) for (const k in attrs) {
    if (k === 'class') e.className = attrs[k];
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), attrs[k]);
    else if (attrs[k] != null) e.setAttribute(k, attrs[k]);
  }
  for (const c of kids) if (c != null) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
}
const NS = 'http://www.w3.org/2000/svg';
function sv(tag, attrs, ...kids) {
  const e = document.createElementNS(NS, tag);
  if (attrs) for (const k in attrs) if (attrs[k] != null) e.setAttribute(k, attrs[k]);
  for (const c of kids) if (c != null) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
}

// ---- state -------------------------------------------------------------------
// A region = one fitted stretch: {lo, hi, comps, fit, dirty, hist, redo, trials, prevBic, seq} + HOW it was fitted
// (local, share_width, share_eta, max_fwhm, min_fwhm, refine): what an export, a session and an undo evaluate it with —
// the controls on the left may have moved on to another region since.
//   comps  the WORKING bands — what the table shows and the handles move: [{shape, pos, height, fwhm, eta, fix[], wmax?}]
//   fit    the server's last fit of them (its curve and residual are drawn while !dirty)
//   dirty  the bands were changed since that fit: they are drawn dashed, with their own sum, until fitted again
const SP = {
  state: null,            // /api/sp/state
  file: '', series: 0, seriesList: [],
  d: null,                // /api/sp/process: x, raw, cleaned, baseline, y, spikes, peaks, ticks, stated, notes
  d2: null,               // {x, d2, key} — the second derivative shown
  view: null,             // [x0, x1] shown
  regions: [],
  cur: -1,                // the region the table shows
  sel: -1,                // the selected band of that region
  anchors: [],
  mode: 'pan',
  layers: { raw: false, comps: true, ticks: true, stated: true, peaks: false, reverse: false, d2: false, oo: true, uo: false, lib: true, composite: true },
  busy: 0,
  gen: 0,                 // counts the spectra shown: a fit answering for the curve before is dropped
  pseq: 0,                // … and the requests for one: the last asked for is the one shown
  fits: 0, fitting: 0,    // fits on their way; those that may move bands (the fit buttons wait for them)
  lists: [], listsRedo: [],   // the list of regions before a region was cleared, replaced or made: undo of those
  yz: 1,                  // vertical zoom
  ready: false,           // the spectrum and what was left of its fit are in: from here on the work is kept
};
const LS = 'pxrd-sp3';                                    // 3: the defaults changed (at most 12 bands; 2: smallest band 3 %) — remembered values start afresh
const KEEP = ['sp-refine', 'sp-shape', 'sp-local', 'sp-baseline', 'sp-lam', 'sp-p', 'sp-width', 'sp-threshold', 'sp-resolution', 'sp-maxn', 'sp-share', 'sp-d2w'];
const KEEP_CB = ['sp-despike', 'sp-share-w', 'sp-share-eta', 'sp-live'];
function loadPrefs() {
  try {
    const cfg = JSON.parse(localStorage.getItem('pxrd-gui') || '{}');          // the main window's appearance
    if (cfg.theme) document.documentElement.setAttribute('data-theme', cfg.theme);
    if (cfg.density) document.documentElement.setAttribute('data-density', cfg.density);
    const p = JSON.parse(localStorage.getItem(LS) || '{}');
    if (p.layers) Object.assign(SP.layers, p.layers);
    for (const id of KEEP) if (typeof p[id] === 'string' && p[id] !== '' && $('#' + id)) $('#' + id).value = p[id];
    for (const id of KEEP_CB) if (p[id] != null && $('#' + id)) $('#' + id).checked = !!p[id];
  } catch (_) {}
}
function savePrefs() {
  try {
    const p = { layers: SP.layers, plotH: (JSON.parse(localStorage.getItem(LS) || '{}')).plotH };
    for (const id of KEEP) p[id] = $('#' + id).value;
    for (const id of KEEP_CB) p[id] = $('#' + id).checked;
    localStorage.setItem(LS, JSON.stringify(p));
  } catch (_) {}
}

function status(msg, bad) {
  const s = $('#sp-status'); s.textContent = msg || ''; s.title = msg || ''; s.style.color = bad ? 'var(--danger)' : '';
}
async function api(url, body) {
  SP.busy++; document.body.style.cursor = 'progress';
  try {
    const r = await fetch(url, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    let j = null;
    try { j = await r.json(); } catch (_) {}
    if (!r.ok || !j || j.ok === false) throw new Error((j && j.error) || ('the server answered ' + r.status));
    return j;
  } finally {
    if (--SP.busy <= 0) { SP.busy = 0; document.body.style.cursor = ''; }
  }
}
const num = id => { const v = parseFloat($('#' + id).value); return Number.isFinite(v) ? v : null; };

// what the server needs to make the same cleaned spectrum again
function opts() {
  return {
    name: SP.file, series: SP.series, kind: $('#sp-kind').value,
    despike: $('#sp-despike').checked, threshold: num('sp-threshold'), resolution: num('sp-resolution'),
    baseline: $('#sp-baseline').value, anchors: SP.anchors, lam: Math.pow(10, num('sp-lam') == null ? 7 : num('sp-lam')), p: num('sp-p'), width: num('sp-width'),
    cif: $('#sp-cif').value, ms: $('#sp-ms').value, laser: num('sp-laser'), formula: $('#sp-formula').value.trim(),
    groups: SP.pick,                                        // the groups picked by hand (null: the chemistry's own)
  };
}
// … and how a region is to be fitted
function fitOpts(reg) {
  return Object.assign(opts(), {
    lo: reg.lo, hi: reg.hi, shape: $('#sp-shape').value, local: $('#sp-local').value, share_width: $('#sp-share-w').checked, share_eta: $('#sp-share-eta').checked,
    max_fwhm: num('sp-wmax'), min_fwhm: num('sp-wmin'), min_share: num('sp-share'), max_n: num('sp-maxn'), refine: $('#sp-refine').value,
  });
}

// ---- loading -----------------------------------------------------------------
async function loadState(pick) {
  const s = SP.state = await api('/api/sp/state');
  const fsel = $('#sp-file'); fsel.textContent = '';
  fsel.append(el('option', { value: '' }, s.files.length ? 'choose a spectrum…' : 'no spectrum file in the folder — Open file…'));
  for (const f of s.files) fsel.append(el('option', { value: f.name }, f.name + (f.source === 'upload' ? '  (opened here)' : '')));
  const fill = (sel, items, none) => { sel.textContent = ''; sel.append(el('option', { value: '' }, none)); for (const k of items) sel.append(el('option', { value: k }, k)); };
  const keepCif = $('#sp-cif').value, keepMs = $('#sp-ms').value;
  fill($('#sp-cif'), s.cifs, '.cif: none'); fill($('#sp-ms'), s.manuscripts, 'manuscript: none');      // the label's word is in the control: the bar stays one line
  $('#sp-cif').value = keepCif; $('#sp-ms').value = keepMs;
  const pre = $('#sp-presets'); pre.textContent = '';
  for (const r of s.regions) pre.append(el('button', { onclick: () => setRegion(r.lo, r.hi, true) }, r.name + ' ' + r.lo + '–' + r.hi));
  pre.append(el('button', { onclick: () => { if (SP.d) { SP.view = [SP.d.x[0], SP.d.x[SP.d.x.length - 1]]; draw(); } } }, 'whole'));
  if (!SP.figsBack) {                                        // once: the curves read off figures before the server was last started
    SP.figsBack = true;
    if (await restoreFigures()) return loadState(pick);
  }
  listOutputs(s.outputs);
  for (const b of document.querySelectorAll('[data-fmt]')) {     // an export goes into the open folder's review_out
    b.disabled = !s.folder; b.title = s.folder ? '' : 'No folder is open: open the folder that holds the manuscript in the main window first — the table is written into its review_out.';
  }
  if (pick && s.files.some(f => f.name === pick)) { fsel.value = pick; await chooseFile(pick); }
}

async function chooseFile(name) {
  SP.ready = false; SP.gen++;
  SP.file = name; SP.series = 0; SP.d = null; SP.d2 = null; SP.regions = []; SP.cur = -1; SP.sel = -1; SP.anchors = []; SP.lists = []; SP.listsRedo = []; SP.yz = 1;
  $('#sp-kind').value = ''; $('#sp-laser').value = '';      // what the last file was said to be is not what this one is
  const ssel = $('#sp-series'); ssel.textContent = ''; ssel.classList.add('hidden');
  if (!name) { draw(); renderResult(); return; }
  try {
    const r = await api('/api/sp/series?name=' + enc(name));
    for (const t of r.series) ssel.append(el('option', { value: t.i }, t.name.replace(name + ' | ', '') + ' — ' + t.n + ' points' + (t.offset_copy ? ' (an offset copy)' : '')));
    SP.seriesList = r.series; ssel.classList.toggle('hidden', r.series.length < 2);
    const guess = r.series[0].kind;
    if (!$('#sp-kind').value && guess) setReverse(guess.startsWith('ir'));
    await process(true);
    await restoreWork();
  } catch (e) { status(e.message, true); SP.d = null; draw(); renderResult(); }
  SP.ready = true;
}

// ---- the work in hand is kept ------------------------------------------------------
// Every region's bands, as they stand, are kept in this browser per spectrum (band parameters and options only — never
// the spectrum): another file, a reload or a closed window loses nothing, and the spectrum opens on the fit left on it.
const WORK = 'pxrd-sp-work';
const workKey = () => ((SP.state && SP.state.folder) || '') + '|' + SP.file + '|' + SP.series;
const asFitted = r => ({ lo: r.lo, hi: r.hi, comps: r.comps.map(bare), local: r.local || $('#sp-local').value, share_width: !!r.share_width, share_eta: !!r.share_eta,
  max_fwhm: r.max_fwhm || null, min_fwhm: r.min_fwhm || null, refine: r.refine || '', converged: r.fit ? r.fit.converged : r.converged !== false,
  base: r.fit ? r.fit.base : r.base0 || null, x0: r.fit ? r.fit.x0 : r.x0 });
let workTimer = null;
function saveWork() {
  clearTimeout(workTimer);
  if (!SP.ready || !SP.file || !SP.d) return;
  workTimer = setTimeout(() => {
    if (!SP.ready || !SP.file || !SP.d) return;
    try {
      const all = JSON.parse(localStorage.getItem(WORK) || '{}'), key = workKey();
      const regs = SP.regions.filter(r => r.comps.length);
      if (regs.length) {
        const how = regs.map(asFitted);
        all[key] = { t: Date.now(), s: { options: Object.assign(opts(), { groups: undefined, regions: how.map(h => Object.assign({}, h, { comps: undefined })) }),   // the pick is the folder's, not this file's
          fits: how.map(h => ({ lo: h.lo, hi: h.hi, baseline: h.base, x0: h.x0, converged: h.converged, components: h.comps })) } };
      } else delete all[key];
      for (const k of Object.keys(all).sort((a, b) => all[b].t - all[a].t).slice(12)) delete all[k];
      localStorage.setItem(WORK, JSON.stringify(all));
    } catch (_) {}
  }, 300);
}
// A curve read off a figure is held by the server in memory only. The page keeps its points (per folder), gives them back
// to a server that has been started again, and the curve is in the list as before — with the fit that was left on it.
const FIGS = 'pxrd-sp-figs';
function keepFigure(d) {
  if (!d || !d.figure || !d.figure_meta) return;
  try {
    const all = JSON.parse(localStorage.getItem(FIGS) || '{}');
    all[((SP.state && SP.state.folder) || '') + '|' + SP.file] = { t: Date.now(), name: SP.file, x: d.x, y: d.figure_meta.y, cm_per_px: d.figure_meta.cm_per_px, notes: d.figure_meta.notes };
    for (const k of Object.keys(all).sort((a, b) => all[b].t - all[a].t).slice(6)) delete all[k];
    localStorage.setItem(FIGS, JSON.stringify(all));
  } catch (_) {}
}
async function restoreFigures() {
  let all = {}; try { all = JSON.parse(localStorage.getItem(FIGS) || '{}'); } catch (_) {}
  const pre = ((SP.state && SP.state.folder) || '') + '|'; let n = 0;
  for (const [k, f] of Object.entries(all)) {
    if (!k.startsWith(pre) || SP.state.files.some(q => q.name === f.name)) continue;
    try { await api('/api/sp/fig/restore', { name: f.name, x: f.x, y: f.y, cm_per_px: f.cm_per_px, notes: f.notes }); n++; } catch (_) {}
  }
  return n;
}
async function restoreWork() {
  let w = null;
  try { w = (JSON.parse(localStorage.getItem(WORK) || '{}'))[workKey()]; } catch (_) {}
  if (!w || !w.s || !Array.isArray(w.s.fits) || !w.s.fits.length) return;
  await applySession(w.s, null, true);
  const n = SP.regions.reduce((k, r) => k + r.comps.length, 0);
  if (n) status('the fit left on this spectrum is back (' + n + ' band' + (n === 1 ? '' : 's') + ', as they stood) — Clear removes a region');
}

function setLayer(k, on) {
  SP.layers[k] = on;
  const cb = document.querySelector('#sp-layers [data-layer=' + k + ']'); if (cb) cb.checked = on;
}
const setReverse = on => setLayer('reverse', on);

// ---- the band library ----------------------------------------------------------
// What the mineral's chemistry is expected to give (pxrd_review.bands): the formula typed in 'chemistry' (or a mineral
// name), else the one the manuscript beside the spectrum states. SP.lib is the server's answer for (typed, manuscript,
// kind): the groups, and per mode the literature's range and the published window. It is drawn over the plot, listed
// under the fitted bands, read by the pointer, and — on the server — names what each fitted band can be.
// One colour per group of the library — fixed, so sulfate is always yellow and phosphate always orange whatever else is
// drawn: [hue, saturation]. The oxoanions take the wheel at full saturation, each its own hue, the commonest farthest
// apart; the metal–oxygen bond groups (P–OH, Si–O, V–O …) a muted version of their anion's hue. A key not listed takes
// a hue by its place in the pick.
const LIB_HUES = { AsO4: [0, 80], MoO4: [14, 80], PO4: [28, 80], TeO3: [41, 80], SO4: [55, 80], TeO6: [69, 80], SO3: [83, 80], UO2: [97, 80],
  CrO4: [111, 80], BO3: [124, 80], BO4: [138, 80], sulfide: [152, 60], CO3: [166, 80], C2O4: [180, 80], SiO4: [194, 80], H3O: [208, 80],
  H2O: [221, 80], WO4: [235, 80], OH: [249, 80], IO3: [263, 80], NO3: [277, 80], SeO3: [291, 80], VO4: [304, 80], NH4: [318, 80],
  SeO4: [332, 80], AsO3: [346, 80],
  'P-OH': [28, 40], 'As-OH': [0, 40], 'V-O': [304, 40], 'Si-O': [194, 40], 'Mo-O': [14, 40], 'W-O': [235, 40], 'Ti-O': [180, 40], 'Nb-O': [263, 40] };
const LIB_FALLBACK = [212, 32, 125, 325, 258, 182, 8, 58, 150, 290, 100, 350];
const SHADES = [74, 62, 51, 42];                         // lightness of a group's 1st, 2nd, 3rd, 4th mode (the library's order: ν1, ν3, ν4, ν2)
const LANE = 20;                                         // the height of one row of library bars over the plot
const kindNow = () => $('#sp-kind').value || (SP.d && SP.d.kind) || '';
const libSpan = r => [Math.min(r.lo, r.published ? r.published.p5 : r.lo), Math.max(r.hi, r.published ? r.published.p95 : r.hi)];
const libHolds = (r, x) => { const [a, b] = libSpan(r); return x >= a && x <= b; };
const groupHue = key => key in LIB_HUES ? LIB_HUES[key] : [LIB_FALLBACK[Math.max(0, (SP.lib ? SP.lib.groups : []).findIndex(g => g.key === key)) % LIB_FALLBACK.length], 80];
const groupColour = key => { const [h, s] = groupHue(key); return 'hsl(' + h + ' ' + s + '% 57%)'; };
const libColour = r => groupColour(r.group);
// the modes of one group in four shades of its hue — ν1 light, ν3 mid, ν4 and ν2 dark (r.k: the mode's place in the library)
const rowColour = r => { const [h, s] = groupHue(r.group); return 'hsl(' + h + ' ' + s + '% ' + SHADES[Math.min(SHADES.length - 1, r.k || 0)] + '%)'; };
// an ion, a formula or a mode label as a chemist writes it — chem.js: '(SO4)2−' → (SO<sub>4</sub>)<sup>2−</sup>, 'SO4 ν3' → SO<sub>4</sub> ν3
const ionNodes = text => chemNodes(text), labelNodes = label => chemNodes(label);
const chemList = (items, sep = ', ') => { const f = document.createDocumentFragment(); items.forEach((t, i) => { if (i) f.append(sep); f.append(chemNodes(t)); }); return f; };
// the chemistry typed belongs to the folder's mineral, not to one spectrum of it: kept per folder, back at the next start
const CHEM = 'pxrd-sp-chem';
function keepChem() {
  try {
    const all = JSON.parse(localStorage.getItem(CHEM) || '{}'), k = (SP.state && SP.state.folder) || '', v = $('#sp-formula').value.trim();
    if (v) all[k] = v; else delete all[k];
    localStorage.setItem(CHEM, JSON.stringify(all));
  } catch (_) {}
}
function recallChem() {
  try { const v = JSON.parse(localStorage.getItem(CHEM) || '{}')[(SP.state && SP.state.folder) || '']; if (v && !$('#sp-formula').value) $('#sp-formula').value = v; } catch (_) {}
}
// the groups picked by hand (SP.pick: null = the chemistry's own, [] = none) belong to the folder too
const PICK = 'pxrd-sp-pick';
function keepPick() {
  try {
    const all = JSON.parse(localStorage.getItem(PICK) || '{}'), k = (SP.state && SP.state.folder) || '';
    if (SP.pick) all[k] = SP.pick; else delete all[k];
    localStorage.setItem(PICK, JSON.stringify(all));
  } catch (_) {}
}
function recallPick() {
  try { const v = JSON.parse(localStorage.getItem(PICK) || '{}')[(SP.state && SP.state.folder) || '']; if (Array.isArray(v)) SP.pick = v.map(String); } catch (_) {}
  pickSummary();
}
// 'Chem search' says when a pick is in force, and how many groups it holds
function pickSummary() {
  const sum = $('#sp-pick > summary'), lab = $('#sp-pick-label'); if (!sum || !lab) return;
  lab.textContent = 'Chem search' + (SP.pick ? ' (' + SP.pick.length + ')' : ''); sum.classList.toggle('picked', !!SP.pick);
}
async function loadLib() {
  const typed = $('#sp-formula').value.trim(), key = JSON.stringify([typed, $('#sp-ms').value, kindNow(), SP.pick]);
  if (SP.lib && SP.lib.key === key) return;
  const seq = SP.libSeq = (SP.libSeq || 0) + 1;
  try {
    const r = await api('/api/sp/bands', { formula: typed, ms: $('#sp-ms').value, kind: kindNow(), groups: SP.pick });
    if (seq !== SP.libSeq) return;
    const was = SP.lib ? JSON.stringify([SP.lib.formula, SP.lib.groups.map(g => g.key)]) : '';
    SP.lib = Object.assign(r, { key });
    $('#sp-formula').placeholder = r.source === 'manuscript' && r.formula ? r.formula : 'chemistry: formula or mineral';
    draw(); renderLibrary(); renderPicker();
    if (was !== JSON.stringify([r.formula, r.groups.map(g => g.key)])) for (const reg of SP.regions) if (reg.fit && reg.comps.length && !reg.dirty) relabel(reg);
  } catch (e) { status(e.message, true); }
}
// the chemistry changed: what each fitted band is expected to be is asked again — nothing is fitted, nothing moves
async function relabel(reg) {
  const seq = reg.seq, gen = SP.gen;
  try {
    const r = await api('/api/sp/fit', Object.assign(opts(), asFitted(reg), { evaluate: true, min_share: num('sp-share') }));
    if (seq !== reg.seq || gen !== SP.gen || !SP.regions.includes(reg) || reg.dirty) return;
    reg.fit = r.fit; renderResult();
  } catch (_) {}
}
// the rows of the library in view, each given a lane so that no bar or label sits on another
function libLanes(vx0, vx1, pw) {
  if (!SP.layers.lib || !SP.lib || !SP.lib.rows.length) return [];
  const perPx = (vx1 - vx0) / Math.max(1, pw), ends = [], out = [];
  const both = SP.lib.rows.some(r => r.label === 'OH stretch');      // water and hydroxyl stretch in one place: one bar
  const rows = SP.lib.rows.filter(r => !r.broad && !(both && r.label === 'H2O stretch') && libSpan(r)[0] <= vx1 && libSpan(r)[1] >= vx0)
    .map(r => { const [a, b] = libSpan(r), lo = Math.max(a, vx0), hi = Math.min(b, vx1), half = (r.label.length * 5.6 + 12) * perPx / 2, mid = (lo + hi) / 2;
      return { r, a: Math.min(lo, mid - half), b: Math.max(hi, mid + half), mid }; })
    .sort((p, q) => p.a - q.a);
  for (const it of rows) {
    let lane = ends.findIndex(e => e <= it.a);
    if (lane < 0) { if (ends.length >= 6) continue; lane = ends.length; ends.push(0); }
    ends[lane] = it.b; out.push(Object.assign(it, { lane }));
  }
  return out;
}
function renderLibrary() {
  const host = $('#sp-library'); if (!host) return;
  host.textContent = '';
  const L = SP.lib;
  if (L && L.source === 'unresolved') {                      // a name typed that the snapshot does not know: said, never read as a formula
    host.append(el('summary', null, 'Band library — no species named ‘' + L.name + '’ in the local Mindat snapshot: check the spelling, or type its formula'));
    return;
  }
  if (L && L.source === 'picked') {
    const sum = el('summary', null, 'Band library — expected of the groups picked: ');
    const writesOf = k => (PK.cat && PK.cat.groups.find(g => g.key === k) || L.groups.find(g => g.key === k) || {}).writes || k;
    sum.append(el('b', null, L.groups.length ? chemList(L.groups.map(g => g.writes || g.key)) : 'none'),
      ...(L.formula ? [' (the chemistry ' + (L.name ? L.name + ', ' : ''), chemNodes(L.formula), ' holds ', L.own.length ? chemList(L.own.map(writesOf)) : 'no group of the library', ')'] : []),
      L.groups.length ? '' : ' — pick a group under ‘Chem search’ over the plot, or go back to the chemistry’s own');
    host.append(sum);
    if (!L.rows.length) return;
  } else if (!L || !L.formula) {
    host.append(el('summary', null, 'Band library — type the mineral’s formula or its name in ‘chemistry’ above (or choose the manuscript), or pick groups by hand under ‘Chem search’ over the plot: the bands those groups are expected to give are listed here and drawn over the plot'));
    return;
  } else {
    const sum = el('summary', null, 'Band library — expected of ');
    sum.append(el('b', null, (L.name ? L.name + ', ' : ''), chemNodes(L.formula)), L.source === 'manuscript' ? ' (the manuscript’s formula)' : '', ': ' + (L.groups.map(g => g.name).join(', ') || 'no group of the library — its bands are metal–anion and lattice modes, below about 600 cm⁻¹'));
    for (const b of compareButtons(L)) sum.append(' ', b);
    host.append(sum);
  }
  if (!L.rows.length) return;
  const stated = SP.d ? [...new Set(SP.d.stated.map(b => b.pos))].sort((a, b) => a - b) : [];
  const fitted = []; for (const reg of SP.regions) for (const c of reg.comps) fitted.push(c.pos);
  fitted.sort((a, b) => a - b);
  const tb = el('table');
  const anyRruff = L.rows.some(r => r.rruff), anyIr = L.rows.some(r => r.rruff_ir);
  tb.append(el('tr', null, ...['band', 'what', 'active in', 'free ion', 'range in minerals', 'published positions'].concat(anyRruff ? ['RRUFF spectra'] : [], anyIr ? ['RRUFF infrared'] : [], ['stated in the manuscript', 'fitted here']).map(h => el('th', null, h))));
  let last = null, starred = false;
  for (const r of L.rows) {
    const p = r.published && r.published.of !== 'rruff' ? r.published : null, st = stated.filter(x => libHolds(r, x)), ft = fitted.filter(x => libHolds(r, x));
    const rr = r.rruff;
    const rruffTd = anyRruff ? [el('td', { title: rr ? 'the 5th–95th percentile of this band in the Raman spectra of minerals whose formula holds this group alone (a RRUFF library; modes by the ion’s geometry)' : 'fewer than three single-group minerals of the RRUFF library' },
      rr ? rr.p5 + '–' + rr.p95 + ', median ' + rr.p50 + ' (' + rr.minerals + ' minerals)' : '')] : [];
    const ri = r.rruff_ir;
    const irTd = anyIr ? [el('td', { title: ri ? 'the same percentiles on RRUFF’s infrared spectra of single-group minerals, anchored on ν3 or ν1' : 'no infrared measurement of this mode' },
      ri ? ri.p5 + '–' + ri.p95 + ', median ' + ri.p50 + ' (' + ri.minerals + ' minerals)' : '')] : [];
    const sw = el('i', { class: 'sw' }); sw.style.background = rowColour(r);
    const g = L.groups.find(q => q.key === r.group), o = g && g.orientation;
    const name = el('td', { title: r.source + (r.width ? '. Typical width in RRUFF\'s fits: ' + r.width.p5 + '–' + r.width.p95 + ' cm⁻¹ (median ' + r.width.p50 + ', ' + r.width.n + ' bands)' : '') +
      (o ? '. In RRUFF the relative intensity of this group\'s two strongest bands typically varies ' + o.median + '× with crystal orientation (the median over ' + o.samples + ' oriented samples; a quarter vary ' + o.p75 + '× or more)' : '') }, sw, labelNodes(r.label));
    starred = starred || r.check;
    const tr = el('tr', { class: r.group !== last ? 'g' : '' }, name, el('td', { class: 'w' }, chemNodes(r.what)), el('td', null, r.active), el('td', null, r.free == null ? '' : String(r.free)),
      el('td', { title: r.source + (r.check ? ' — entered from memory of the source, not yet compared with it line by line' : '') }, r.lo + '–' + r.hi + (r.check ? ' *' : '')),
      el('td', { title: p ? 'the 5th–95th percentile of the positions published mineral descriptions assign to this mode' + (p.of === 'any' ? '' : ' (' + (p.of === 'ir' ? 'infrared' : 'Raman') + ' only)') : 'fewer than 8 papers of the corpus assign a band to this mode' },
        p ? p.p5 + '–' + p.p95 + ', median ' + p.p50 + ' (' + p.papers + ' papers)' : ''),
      ...rruffTd, ...irTd,
      el('td', { class: st.length ? '' : 'none' }, stated.length ? (st.join(', ') || '—') : ''),
      el('td', { class: ft.length ? '' : 'none' }, fitted.length ? (ft.map(x => x.toFixed(1)).join(', ') || '—') : ''));
    last = r.group; tb.append(tr);
  }
  host.append(tb);
  host.append(el('div', { class: 'foot' }, (starred ? '* entered from memory of the source, not yet compared with it line by line (data/band_library.json). ' : '') +
    'A band can belong to any mode whose range holds it: the ranges of different groups overlap. Sources: ' + [...new Set(L.rows.map(r => r.source))].join('; ') + '.'));
}

// 'compare with RRUFF ▸': the mineral named (typed, or the manuscript's) and the species the manuscript sets its spectrum
// beside, when the library on this machine has a spectrum of them — the overlay, nothing scored
function compareButtons(L) {
  const out = [];
  if (!RR.choose || !RR.minerals) return out;
  const names = [L.name].concat(L.comparisons || []).filter(Boolean);
  for (const n of names) {
    const m = RR.byName[rrKey(n)];
    if (!m) continue;
    const b = el('button', { class: 'cmp', title: 'Draw the RRUFF spectrum of ' + m.name + ' under the curve (' + m.spectra.length + ' spectr' + (m.spectra.length === 1 ? 'um' : 'a') + ' in the library)' + (n === L.name ? '' : ' — a species the manuscript compares with') }, 'compare with RRUFF ' + m.name + ' ▸');
    b.addEventListener('click', ev => { ev.preventDefault(); ev.stopPropagation(); RR.choose(m.name, 'overlay'); });
    out.push(b);
  }
  return out;
}

const sameCurve = (a, b) => a.y.length === b.y.length && a.x[0] === b.x[0] && a.y.every((v, i) => v === b.y[i]);
async function process(resetView) {
  if (!SP.file) return;
  const seq = ++SP.pseq, before = SP.d;
  try {
    status('reading…');
    const d = await api('/api/sp/process', opts());
    if (seq !== SP.pseq) return;                             // another spectrum was asked for meanwhile: that one is shown
    keepFigure(d);
    const same = !resetView && before && sameCurve(before, d);   // the manuscript or the .cif beside it changed, not the curve
    SP.d = d; SP.d2 = null;
    if (!same) SP.gen++;                                     // a fit still on its way is of the curve before
    if (resetView || !SP.view) SP.view = [d.x[0], d.x[d.x.length - 1]];
    status(d.x.length + ' points, ' + d.x[0] + '–' + d.x[d.x.length - 1] + ' cm⁻¹; noise ' + fmt(d.noise) + (d.kind ? '; ' + d.kind.replace('ir-', 'infrared, ') : ''));
    $('#sp-spikes').textContent = $('#sp-despike').checked ? (d.spikes.length ? d.spikes.length + ' removed: ' + d.spikes.slice(0, 8).map(s => Math.round(s[0])).join(', ') + (d.spikes.length > 8 ? ' …' : '') : 'none found') : '';
    $('#sp-laser-row').classList.toggle('hidden', !(num('sp-laser') || d.notes.some(t => /axis is in nm/.test(t))));     // asked for only when the axis is in nanometres
    const n = $('#sp-notes'); n.textContent = '';
    for (const t of d.notes) n.append(el('div', { class: 'note', title: t }, t));
    if (d.on_curve) {                                        // a curve read off a figure: which of the manuscript's stated bands it has a feature for
      const c = d.on_curve, list = v => v.join(', ');
      if (c.found.length) n.append(el('div', { class: 'on-curve' }, 'Stated in the manuscript, with a feature on the traced curve (within ±' + c.tol + ' cm⁻¹): ' + list(c.found.map(p => p[0]))));
      if (c.none.length) n.append(el('div', { class: 'on-curve' }, 'Stated, with no feature of its own on the traced curve: ' + list(c.none) + ' cm⁻¹ — a fitted component of an envelope needs none; a band the figure has no sign of is worth a look'));
    }
    // a changed curve under fitted regions: their fits are of the curve before. The bands stay where they are and their
    // heights follow (as after an edit) — or, with that off, they wait for 'Fit these'. An unchanged curve changes nothing.
    if (!SP.layers.uo && SP.uoFor !== SP.file && d.ticks.some(t => /UO2/.test(t.label))) { SP.uoFor = SP.file; setLayer('uo', true); }
    const stale = !resetView && !same ? SP.regions.filter(r => r.comps.length) : [];
    for (const r of stale) r.dirty = true;
    draw(); renderResult(); savePrefs();
    loadLib();
    if (SP.layers.d2) loadD2();
    if ($('#sp-live').checked) for (const r of stale) fitRegion(r, r.comps, { refine: 'heights', keep_dead: true });
  } catch (e) { if (seq === SP.pseq) status(e.message, true); }
}

async function loadD2() {
  if (!SP.d || !SP.layers.d2) return;
  const key = JSON.stringify([opts(), num('sp-d2w')]);
  if (SP.d2 && SP.d2.key === key) { draw(); return; }
  try {
    const r = await api('/api/sp/d2', Object.assign(opts(), { lo: SP.d.x[0], hi: SP.d.x[SP.d.x.length - 1], d2_width: num('sp-d2w') || 25 }));
    SP.d2 = { x: r.x, d2: r.d2, key }; draw();
  } catch (e) { status(e.message, true); }
}

// ---- the plot ----------------------------------------------------------------
const M = { l: 58, r: 12, t: 16, b: 30, res: 64 };       // margins (t grows by a row per distance ruler shown); res = the residual strip's height
const RULER = 15;                                        // the height of one ruler row
// the distance rulers switched on (the O···O one; the two U–O ones together)
const rulersOn = () => ((SP.state && SP.state.rulers) || []).filter(r => r.key === 'oo' ? SP.layers.oo : SP.layers.uo);
// the distance a ruler gives at a wavenumber (between two of its ticks, a hundredth of an ångström apart), or null outside it
function rulerAt(r, x) {
  const t = r.ticks;
  for (let i = 1; i < t.length; i++) {
    const a = t[i - 1], b = t[i];
    if ((x - a[1]) * (x - b[1]) <= 0 && a[1] !== b[1]) return a[0] + (b[0] - a[0]) * (x - a[1]) / (b[1] - a[1]);
  }
  return null;
}
let G = null;                                            // the last drawing's geometry (for the pointer)

function fmt(v) {
  if (v == null || !Number.isFinite(v)) return '';
  const a = Math.abs(v);
  return a === 0 ? '0' : a >= 1e5 || a < 1e-3 ? v.toExponential(2) : a >= 100 ? v.toFixed(0) : a >= 10 ? v.toFixed(1) : a >= 1 ? v.toFixed(2) : v.toFixed(3);
}
function niceStep(span, target) {
  const raw = span / target, p = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / p;
  return (f < 1.5 ? 1 : f < 3.5 ? 2 : f < 7.5 ? 5 : 10) * p;
}
function range(i0, i1) { return [Math.max(0, i0), Math.min(SP.d.x.length - 1, i1)]; }
function indexOf(x) {                                    // the first index with d.x[i] >= x
  const a = SP.d.x; let lo = 0, hi = a.length;
  while (lo < hi) { const m = (lo + hi) >> 1; if (a[m] < x) lo = m + 1; else hi = m; }
  return lo;
}
function profile(c, x) {                                  // the band as the server fits it — here for drawing and previews only
  const t = (x - c.pos) / c.fwhm, g = Math.exp(-4 * Math.LN2 * t * t), l = 1 / (1 + 4 * t * t);
  return c.height * (c.shape === 'gauss' ? g : c.shape === 'lorentz' ? l : c.eta * l + (1 - c.eta) * g);
}
// a region's bands as curves on its own points: from the fit while it stands, else from the working bands (a preview)
function curves(reg) {
  const d = SP.d, f = reg.fit;
  if (f && !reg.dirty) return { x: f.x, model: f.model, residual: f.residual, base: f.base, x0: f.x0, draft: false };
  const [a, b] = range(indexOf(reg.lo), indexOf(reg.hi + 1e-9) - 1);
  const step = Math.max(1, Math.floor((b - a + 1) / 1200));
  const base = f ? f.base : [0, 0], x0 = f ? f.x0 : 0.5 * (reg.lo + reg.hi);
  const x = [], model = [], residual = [];
  for (let i = a; i <= b; i += step) {
    const v = d.x[i]; let s = base[0] + base[1] * (v - x0);
    for (const c of reg.comps) s += profile(c, v);
    x.push(v); model.push(s); residual.push(d.y[i] - s);
  }
  return { x, model, residual, base, x0, draft: true };
}

function draw() {
  const host = $('#sp-plot'); host.textContent = '';
  const d = SP.d;
  if (!d) {
    host.append(el('div', { class: 'empty' }, SP.file ? 'This file could not be read as a spectrum.' : 'Choose a spectrum of the folder above, open a file, or drop one here.'));
    G = null; return;
  }
  const W = host.clientWidth || 800, H = host.clientHeight || 400;
  const hasRes = SP.regions.some(r => r.comps.length);
  const [vx0, vx1] = SP.view;
  const rulers = rulersOn().filter(r => r.ticks.some(t => t[1] >= vx0 && t[1] <= vx1));     // those with a stretch in view
  const lanes = libLanes(vx0, vx1, W - M.l - M.r), nLanes = lanes.reduce((n, it) => Math.max(n, it.lane + 1), 0);
  M.t = 16 + RULER * rulers.length + LANE * nLanes;
  const ph = H - M.t - M.b - (hasRes ? M.res : 0), pw = W - M.l - M.r;
  const [i0, i1] = range(indexOf(vx0) - 1, indexOf(vx1) + 1);
  const ys = SP.layers.raw ? d.cleaned : d.y;
  let ymin = Infinity, ymax = -Infinity;
  for (let i = i0; i <= i1; i++) { const v = ys[i]; if (v < ymin) ymin = v; if (v > ymax) ymax = v; }
  if (!(ymax > ymin)) { ymax = ymin + 1; }
  const high = ymin > 0.3 * ymax;                           // bands on a high background (no baseline taken off): zero is not forced into view
  if (!SP.layers.raw && !high) ymin = Math.min(ymin, 0);
  const padY = 0.06 * (ymax - ymin); ymax += padY; ymin -= SP.layers.raw || high ? padY : 0.02 * (ymax - ymin);
  ymax = ymin + (ymax - ymin) / SP.yz;                      // the vertical zoom: the foot of the curve enlarged
  const rev = SP.layers.reverse;
  const X = v => M.l + (rev ? (vx1 - v) : (v - vx0)) / (vx1 - vx0) * pw;
  const Xinv = px => rev ? vx1 - (px - M.l) / pw * (vx1 - vx0) : vx0 + (px - M.l) / pw * (vx1 - vx0);
  const Y = v => M.t + (ymax - v) / (ymax - ymin) * ph;
  const Yinv = py => ymax - (py - M.t) / ph * (ymax - ymin);
  G = { X, Xinv, Y, Yinv, W, H, pw, ph, ymin, ymax };
  const svg = sv('svg', { viewBox: '0 0 ' + W + ' ' + H, preserveAspectRatio: 'none' });
  svg.append(sv('defs', null, sv('clipPath', { id: 'sp-clip' }, sv('rect', { x: M.l, y: M.t - 4, width: pw, height: ph + 4 })),
    sv('clipPath', { id: 'sp-clip-r' }, sv('rect', { x: M.l, y: M.t + ph + 2, width: pw, height: M.res - 4 }))));
  const g = sv('g', { 'clip-path': 'url(#sp-clip)' }); svg.append(g);
  const gr = sv('g', { 'clip-path': 'url(#sp-clip-r)' }); svg.append(gr);     // the residual strip: nothing of the plot runs into it

  // one path of a curve, thinned to the pixels there are: per pixel column its lowest and highest point
  const path = (xs, vals, a, b, yf) => {
    const n = b - a + 1; if (n <= 0) return '';
    const yf_ = yf || Y; const per = Math.max(1, Math.floor(n / (2 * pw)));
    const out = [];
    for (let i = a; i <= b; i += per) {
      if (per === 1) { out.push(X(xs[i]).toFixed(1) + ',' + yf_(vals[i]).toFixed(1)); continue; }
      let lo = i, hi = i;
      for (let k = i; k < Math.min(b + 1, i + per); k++) { if (vals[k] < vals[lo]) lo = k; if (vals[k] > vals[hi]) hi = k; }
      const [p, q] = lo < hi ? [lo, hi] : [hi, lo];
      out.push(X(xs[p]).toFixed(1) + ',' + yf_(vals[p]).toFixed(1)); if (q !== p) out.push(X(xs[q]).toFixed(1) + ',' + yf_(vals[q]).toFixed(1));
    }
    return 'M' + out.join(' L');
  };

  // the fitted regions behind everything
  const edges = sv('g');
  SP.regions.forEach((r, k) => {
    const a = X(r.lo), b = X(r.hi);
    g.append(sv('rect', { class: 'region' + (k === SP.cur ? ' cur' : ''), x: Math.min(a, b), y: M.t - 4, width: Math.abs(b - a), height: ph + 4 }));
    if (k === SP.cur) for (const side of ['lo', 'hi']) {
      const x = X(r[side]);
      const e = sv('g', { class: 'r-edge' }, sv('line', { x1: x, x2: x, y1: M.t - 4, y2: M.t + ph }), sv('rect', { x: x - 5, y: M.t - 4, width: 10, height: ph + 4 }),
        sv('path', { d: 'M' + (x - 4) + ',' + (M.t + ph / 2 - 9) + ' h8 v18 h-8 Z' }),
        sv('title', null, 'drag to move this end of the fitted region (' + r[side] + ' cm⁻¹); its bands stay'));
      e.addEventListener('mousedown', ev => { if (ev.button !== 0) return; ev.stopPropagation(); ev.preventDefault(); r.edgeBefore = snapshot(r); drag = { kind: 'edge', reg: r, side, lo0: r.lo, hi0: r.hi, dirty0: !!r.dirty, moved: false }; });
      edges.append(e);
    }
  });
  // a stretch chosen and not fitted yet: drawn, so that a drag or a preset shows where it landed
  const plo = num('sp-lo'), phi = num('sp-hi');
  if (plo != null && phi != null && phi > plo && !SP.regions.some(r => Math.abs(r.lo - plo) < 1 && Math.abs(r.hi - phi) < 1)) {
    const a = X(plo), b = X(phi);
    g.append(sv('rect', { class: 'pending', x: Math.min(a, b), y: M.t - 3, width: Math.abs(b - a), height: ph + 2 }));
    g.append(sv('text', { class: 'pending-l', x: Math.min(a, b) + 6, y: M.t + 12 }, plo + '–' + phi + ' cm⁻¹: Auto fit, or ‘band’ and click'));
  }
  // the second derivative, bands up, on a scale of its own (the lower part of the plot)
  if (SP.layers.d2 && SP.d2) {
    const q = SP.d2; let a = 0; while (a < q.x.length - 1 && q.x[a + 1] < vx0) a++;
    let b = q.x.length - 1; while (b > 0 && q.x[b - 1] > vx1) b--;
    let top = 1e-12; for (let i = a; i <= b; i++) top = Math.max(top, Math.abs(q.d2[i]));
    const DY = v => M.t + ph * (0.72 - 0.55 * v / top);
    g.append(sv('line', { x1: M.l, x2: M.l + pw, y1: DY(0), y2: DY(0), stroke: 'var(--line)' }));
    g.append(sv('path', { class: 'd2', d: path(q.x, q.d2, a, b, DY) }, sv('title', null, 'the second derivative (bands up), smoothed over ' + (num('sp-d2w') || 25) + ' cm⁻¹')));
  }
  if (SP.layers.raw) {
    if (d.spikes.length && d.raw) g.append(sv('path', { class: 'rawdata', d: path(d.x, d.raw, i0, i1) }, sv('title', null, 'as recorded, before the cosmic rays were taken out')));
    g.append(sv('path', { class: 'data', d: path(d.x, d.cleaned, i0, i1) }));
    if ($('#sp-baseline').value !== 'none') g.append(sv('path', { class: 'base', d: path(d.x, d.baseline, i0, i1) }));
    for (const s of d.spikes) g.append(sv('circle', { class: 'spike', cx: X(s[0]), cy: M.t + 2, r: 2.5 }, sv('title', null, 'a cosmic-ray event removed at ' + Math.round(s[0]) + ' cm⁻¹')));
  } else {
    g.append(sv('path', { class: 'data', d: path(d.x, d.y, i0, i1) }));
  }
  // a RRUFF spectrum under the curve: scaled so its top in view meets the current curve's top in view
  if (SP.overlay && $('#sp-overlay').checked) {
    const o = SP.overlay, first = o.x.findIndex(v => v >= vx0), past = o.x.findIndex(v => v > vx1);
    const oa = Math.max(0, (first < 0 ? o.x.length : first) - 1), ob = Math.min(o.x.length - 1, (past < 0 ? o.x.length : past));
    let omax = 0, cmax = 0; const cur = SP.layers.raw ? d.cleaned : d.y;
    for (let k = oa; k <= ob; k++) omax = Math.max(omax, o.y[k]);
    for (let k = i0; k <= i1; k++) cmax = Math.max(cmax, cur[k]);
    const s = omax > 0 ? cmax / omax : 1;
    if (ob > oa) g.append(sv('path', { class: 'overlay', d: path(o.x, o.y.map(v => v * s), oa, ob) }, sv('title', null, o.name + ' — scaled to the curve in view')));
    // the reference's own bands: short ticks at the foot of the plot, in the overlay's colour (a reading aid, nothing is matched)
    for (const p of o.peaks || []) if (p >= vx0 && p <= vx1)
      g.append(sv('line', { class: 'overlay ref-tick', x1: X(p), x2: X(p), y1: M.t + ph - 7, y2: M.t + ph }, sv('title', null, 'a band of ' + o.name + ' at ' + p + ' cm⁻¹')));
  }
  // the composite spectrum of each group shown (the median of RRUFF's single-group minerals): a faint area in the group's
  // hue, scaled like the overlay — what a sulfate looks like; a reading aid, never a finding
  if (SP.layers.composite && SP.lib && SP.lib.composites && SP.lib.rows.length) {
    const cur = SP.layers.raw ? d.cleaned : d.y;
    let cmax = 0; for (let k = i0; k <= i1; k++) cmax = Math.max(cmax, cur[k]);
    for (const [key, c] of Object.entries(SP.lib.composites)) {
      const xs = [], ys = [];
      const sm = k => { let n = 0, t = 0; for (let j = k - 3; j <= k + 3; j++) if (j >= 0 && j < c.y.length && c.y[j] != null) { t += c.y[j]; n++; } return n ? t / n : null; };   // a 14 cm⁻¹ running mean: an envelope, not the medians' jitter
      for (let k = 0; k < c.y.length; k++) { const v = c.x0 + k * c.dx, y = sm(k); if (v >= vx0 && v <= vx1 && y != null) { xs.push(v); ys.push(y); } }
      if (xs.length < 3) continue;
      let omax = 0; for (const v of ys) omax = Math.max(omax, v);
      const s = omax > 0 ? cmax / omax : 1;
      let dd = 'M' + X(xs[0]) + ' ' + Y(0);
      for (let k = 0; k < xs.length; k++) dd += 'L' + X(xs[k]) + ' ' + Y(ys[k] * s);
      dd += 'L' + X(xs[xs.length - 1]) + ' ' + Y(0) + 'Z';
      const [h, sat] = groupHue(key);
      g.append(sv('path', { class: 'composite', d: dd, fill: 'hsl(' + h + ' ' + sat + '% 57%)' }, sv('title', null, 'the median RRUFF Raman spectrum of ' + c.minerals + ' ' + key + ' minerals (each normalised, one per mineral) — a reading aid')));
    }
  }
  // fits: bands, their sum, the residual; the current region's bands carry handles
  const cv = SP.regions.map(r => r.comps.length ? curves(r) : null);
  let rmax = 0;
  for (const c of cv) if (c) for (const v of c.residual) rmax = Math.max(rmax, Math.abs(v));
  const RY = v => M.t + ph + 6 + (M.res - 12) * 0.5 * (1 - v / (rmax || 1));
  const handles = sv('g');
  SP.regions.forEach((r, k) => {
    const c = cv[k]; if (!c) return;
    const off = SP.layers.raw ? v => d.baseline[Math.min(d.x.length - 1, indexOf(v))] || 0 : () => 0;
    const bl = v => c.base[0] + c.base[1] * (v - c.x0) + off(v);
    // the widest first: a narrow band on a broad one is drawn — and clicked — on top of it
    if (SP.layers.comps) r.comps.map((b, j) => [b, j]).sort((p, q) => q[0].fwhm - p[0].fwhm).forEach(([b, j]) => {
      const sel = k === SP.cur && j === SP.sel;
      const vals = c.x.map(v => profile(b, v) + bl(v));
      // the area under the band down to the local baseline (closed along it: a band cut by the region's edge filled as a wedge), and its curve
      const last = c.x.length - 1, curve = path(c.x, vals, 0, last);
      const area = sv('path', { class: 'comp-f' + (sel ? ' sel' : ''), d: curve + ' L' + X(c.x[last]).toFixed(1) + ',' + Y(bl(c.x[last])).toFixed(1) + ' L' + X(c.x[0]).toFixed(1) + ',' + Y(bl(c.x[0])).toFixed(1) + ' Z' });
      const p = sv('path', { class: 'comp' + (sel ? ' sel' : '') + (c.draft ? ' draft' : ''), d: curve });
      for (const q of [area, p]) q.addEventListener('mousedown', () => { picked = [k, j]; });      // selected on mouse-up if the pointer did not move: a drag from here pans
      g.append(area, p);
      g.append(sv('text', { class: 'lab', x: X(b.pos), y: Math.max(M.t + 8, Y(b.height + bl(b.pos)) - 8), 'text-anchor': 'middle' }, b.pos.toFixed(0)));
      if (k === SP.cur) {
        const hp = sv('circle', { class: 'h-pos' + (sel ? ' sel' : ''), cx: X(b.pos), cy: Y(b.height + bl(b.pos)), r: sel ? 5.5 : 4.5 },
          sv('title', null, 'drag to move this band and set its height'));
        hp.addEventListener('mousedown', ev => startHandle(ev, k, j, 'pos'));
        const wx = X(b.pos + (rev ? -1 : 1) * b.fwhm / 2), wy = Y(b.height / 2 + bl(b.pos));
        const hw = sv('rect', { class: 'h-w' + (sel ? ' sel' : ''), x: wx - 4, y: wy - 4, width: 8, height: 8, transform: 'rotate(45 ' + wx.toFixed(1) + ' ' + wy.toFixed(1) + ')' },
          sv('title', null, 'drag sideways to set this band’s width'));
        hw.addEventListener('mousedown', ev => startHandle(ev, k, j, 'fwhm'));
        handles.append(hw, hp);
      }
    });
    g.append(sv('path', { class: 'model' + (c.draft ? ' draft' : ''), d: path(c.x, c.model.map((v, i) => v + off(c.x[i])), 0, c.x.length - 1) }));
    gr.append(sv('path', { class: 'resid', d: path(c.x, c.residual, 0, c.x.length - 1, RY) }));
    // where the residual still holds a band: a mark to click
    if (k === SP.cur && r.fit && !r.dirty) for (const nx of r.fit.next || []) {
      const x = X(nx.pos), y = M.t + ph - 2;
      const m = sv('path', { class: 'next', d: 'M' + (x - 6) + ',' + y + ' L' + (x + 6) + ',' + y + ' L' + x + ',' + (y - 10) + ' Z' },
        sv('title', null, 'the residual holds a band near ' + nx.pos + ' cm⁻¹ (about ' + nx.fwhm + ' wide) — click to add it and refit'));
      m.addEventListener('mousedown', ev => { ev.stopPropagation(); addBand(r, { pos: nx.pos, height: nx.height, fwhm: nx.fwhm }); });
      handles.append(m);
    }
  });
  if (hasRes) {
    svg.append(sv('line', { class: 'axis', x1: M.l, x2: M.l + pw, y1: RY(0), y2: RY(0), stroke: 'var(--line)' }));
    svg.append(sv('text', { x: M.l - 6, y: RY(0) + 4, 'text-anchor': 'end' }, 'residual'));
  }
  // what is set beside the spectrum
  if (SP.layers.peaks) for (const p of d.peaks) if (p.pos >= vx0 && p.pos <= vx1) g.append(sv('line', { class: 'peak', x1: X(p.pos), x2: X(p.pos), y1: M.t + ph - 8, y2: M.t + ph }, sv('title', null, 'a band found at ' + p.pos + ' cm⁻¹, about ' + p.fwhm + ' wide')));
  if (SP.layers.ticks) {
    let lastX = -1e9, row = 0;                              // labels that would run into each other step down a line
    for (const t of d.ticks.filter(t => t.pos >= vx0 && t.pos <= vx1).sort((a, b) => X(a.pos) - X(b.pos))) {
      const x = X(t.pos), text = t.label.split(',')[0];
      row = x - lastX < 6.2 * text.length ? (row + 1) % 4 : 0; lastX = x;
      g.append(sv('line', { class: 'tick', x1: x, x2: x, y1: M.t + 10, y2: M.t + ph }, sv('title', null, 'expected at ' + t.pos + ' cm⁻¹ from the structure: ' + t.label)));
      g.append(sv('text', { class: 'tick-l', x: x + 3, y: M.t + 18 + 11 * row }, text));
    }
  }
  if (SP.layers.stated) for (const b of d.stated) if (b.pos >= vx0 && b.pos <= vx1) {
    const x = X(b.pos);
    g.append(sv('path', { class: 'stated', d: 'M' + (x - 4) + ',' + (M.t - 3) + ' L' + (x + 4) + ',' + (M.t - 3) + ' L' + x + ',' + (M.t + 5) + ' Z' },
      sv('title', null, 'the manuscript states ' + b.pos + ' cm⁻¹' + (b.family ? ' — ' + (b.mode || '') + ' ' + b.family : '') + (b.technique ? ' (' + b.technique + ')' : '') + '\n' + b.sentence)));
  }
  if ($('#sp-baseline').value === 'anchors') for (const a of SP.anchors) if (a >= vx0 && a <= vx1)
    g.append(sv('circle', { class: 'anchor', cx: X(a), cy: Y(SP.layers.raw ? d.baseline[indexOf(a)] : 0), r: 4 }, sv('title', null, 'a baseline anchor at ' + Math.round(a) + ' cm⁻¹ — click it (anchor mode) to remove')));
  // axes
  const ax = sv('g', { class: 'axis' });
  ax.append(sv('line', { x1: M.l, x2: M.l + pw, y1: M.t + ph, y2: M.t + ph }), sv('line', { x1: M.l, x2: M.l, y1: M.t, y2: M.t + ph }));
  const xs = niceStep(vx1 - vx0, Math.max(3, pw / 90));
  for (let v = Math.ceil(vx0 / xs) * xs; v <= vx1 + 1e-9; v += xs) {
    ax.append(sv('line', { x1: X(v), x2: X(v), y1: H - M.b, y2: H - M.b + 4 }), sv('text', { x: X(v), y: H - M.b + 16, 'text-anchor': 'middle' }, String(+v.toFixed(6))));
  }
  const ystep = niceStep(ymax - ymin, Math.max(2, ph / 50));
  for (let v = Math.ceil(ymin / ystep) * ystep; v <= ymax; v += ystep)
    ax.append(sv('line', { x1: M.l - 4, x2: M.l, y1: Y(v), y2: Y(v) }), sv('text', { x: M.l - 6, y: Y(v) + 4, 'text-anchor': 'end' }, fmt(v)));
  ax.append(sv('text', { x: M.l + pw, y: H - 3, 'text-anchor': 'end' }, 'wavenumber (cm⁻¹)'));
  svg.append(ax);
  // the distance rulers over the plot: a tick every 0.01 Å, labelled where there is room (round values first), and a
  // dot for every fitted band
  rulers.forEach((r, row) => {
    const yb = 14 + RULER * row, gq = sv('g', { class: 'ruler' }, sv('title', null, r.name + ': ' + r.of + ' — ' + r.cite + '. A correlation with scatter: it places a band, it does not measure a bond.'));
    const vis = r.ticks.filter(t => t[1] >= vx0 && t[1] <= vx1);
    const xs = vis.map(t => X(t[1]));
    gq.append(sv('line', { x1: Math.min(...xs), x2: Math.max(...xs), y1: yb, y2: yb }));
    gq.append(sv('text', { class: 'name', x: M.l - 6, y: yb, 'text-anchor': 'end' }, r.name));
    const placed = [];
    for (const m of [10, 5, 2, 1]) vis.forEach((t, i) => {     // tenths first, then twentieths … each label only where none stands within 34 px
      if (Math.round(t[0] * 100) % m || placed.some(p => Math.abs(p - xs[i]) < 34)) return;
      placed.push(xs[i]);
      gq.append(sv('text', { x: xs[i], y: yb - 5, 'text-anchor': 'middle' }, t[0].toFixed(2)));
    });
    vis.forEach((t, i) => { const big = placed.includes(xs[i]); gq.append(sv('line', { x1: xs[i], x2: xs[i], y1: yb - (big ? 4 : 2), y2: yb })); });
    for (const reg of SP.regions) for (const c of reg.comps) {
      const dist = c.pos >= vx0 && c.pos <= vx1 ? rulerAt(r, c.pos) : null;
      if (dist != null) gq.append(sv('circle', { cx: X(c.pos), cy: yb, r: 3 }, sv('title', null, 'the band at ' + c.pos.toFixed(1) + ' cm⁻¹: ' + r.name.replace(' Å', '') + ' ' + dist.toFixed(r.key === 'oo' ? 2 : 3) + ' Å — ' + r.cite)));
    }
    svg.append(gq);
  });
  // the band library over the plot: per mode of the chemistry a thin bar for the range in minerals, a thick one for the
  // published window (a notch at its median), a ◆ at the free-ion value
  if (nLanes) {
    const gl = sv('g', { class: 'lib' }), clipX = v => Math.max(M.l, Math.min(M.l + pw, X(v)));
    const both = SP.lib.rows.some(r => r.label === 'OH stretch');      // one bar for the water and the hydroxyl stretch (libLanes left the other out)
    for (const it of lanes) {
      const r = it.r, col = rowColour(r), yb = 10 + RULER * rulers.length + LANE * it.lane + 15, p = r.published;
      const gq = sv('g', null, sv('title', null, r.label + ' — ' + r.what + '. In minerals ' + r.lo + '–' + r.hi + ' cm⁻¹' + (r.check ? ' (from memory of the source: check)' : '') +
        (r.free != null ? '; free ion ' + r.free : '') + (p ? '; published positions ' + p.p5 + '–' + p.p95 + ', median ' + p.p50 + ' (' + p.papers + ' papers)' : '') + '; active in ' + r.active + '. ' + r.source));
      gq.append(sv('line', { class: 'range', x1: clipX(r.lo), x2: clipX(r.hi), y1: yb, y2: yb, stroke: col }));
      if (p) {
        gq.append(sv('line', { class: 'pub', x1: clipX(p.p5), x2: clipX(p.p95), y1: yb, y2: yb, stroke: col }));
        if (p.p50 >= vx0 && p.p50 <= vx1) gq.append(sv('line', { class: 'med', x1: X(p.p50), x2: X(p.p50), y1: yb - 2, y2: yb + 2 }));
      }
      if (r.free != null && r.free >= vx0 && r.free <= vx1) gq.append(sv('path', { d: 'M' + X(r.free) + ' ' + (yb - 4) + 'l3 4l-3 4l-3 -4z', fill: col }));
      gq.append(chemSvg(sv('text', { x: Math.max(M.l + 2, Math.min(M.l + pw - 2, X(it.mid))), y: yb - 5, 'text-anchor': 'middle', fill: col }), both && r.label === 'OH stretch' ? 'O–H stretch' : r.label));
      gl.append(gq);
    }
    svg.append(gl);
  }
  svg.append(sv('rect', { id: 'sp-sel', class: 'sel', x: 0, y: M.t, width: 0, height: ph }));
  g.append(edges);
  g.append(handles);                                        // on top: a handle is never under a curve
  host.append(svg);
}

// ---- the pointer ---------------------------------------------------------------
function plotX(ev) { const r = $('#sp-plot').getBoundingClientRect(); return ev.clientX - r.left; }
function plotY(ev) { const r = $('#sp-plot').getBoundingClientRect(); return ev.clientY - r.top; }
let drag = null;
let picked = null;                                         // the band under a mouse-down, until the mouse-up says click or drag

function readout(ev) {
  if (!G || !SP.d) return;
  const x = G.Xinv(plotX(ev)), i = Math.min(SP.d.x.length - 1, Math.max(0, indexOf(x)));
  const ws = [], ofFormula = !!(SP.lib && SP.lib.rows.length);
  if (ofFormula) { for (const b of [false, true]) for (const r of SP.lib.rows) if (r.broad === b && libHolds(r, x)) ws.push(r.label); }     // of this chemistry: the modes standing on their own first
  else for (const [name, e] of Object.entries(SP.state.windows || {})) { const w = e.any; if (w && x >= w.p5 && x <= w.p95) ws.push(name); }
  const ds = rulersOn().map(r => [r, rulerAt(r, x)]).filter(p => p[1] != null).map(([r, v]) => r.name.replace(' Å', '') + ' ' + v.toFixed(r.key === 'oo' ? 2 : 3) + ' Å');
  const of = SP.lib && SP.lib.source === 'picked' ? 'the groups picked' : 'the formula', ro = $('#sp-readout');
  ro.textContent = x.toFixed(1) + ' cm⁻¹   ' + fmt((SP.layers.raw ? SP.d.cleaned : SP.d.y)[i]) + (ds.length ? '   ' + ds.join(' · ') : '') + (ws.length ? (ofFormula ? '   — expected of ' + of + ': ' : '   — where papers place: ') : ofFormula ? '   — no group of ' + of + ' is expected here' : '');
  if (ws.length) ro.append(chemList(ws.slice(0, 5)));
  if (SP.overlay && SP.overlay.peaks && SP.overlay.peaks.length) {
    const near = SP.overlay.peaks.reduce((a, b) => Math.abs(b - x) < Math.abs(a - x) ? b : a);
    if (Math.abs(near - x) <= 8) ro.append('   · reference band at ' + near.toFixed(1));
  }
}

function setRegion(lo, hi, zoom) {
  if (!SP.d) return;
  [lo, hi] = [Math.round(Math.min(lo, hi)), Math.round(Math.max(lo, hi))];
  let k = SP.regions.findIndex(r => Math.abs(r.lo - lo) < 1 && Math.abs(r.hi - hi) < 1);
  if (k < 0) {
    // not a region as it stands: the bounds of the fitted region they overlap are being changed — the one the stretch
    // MOSTLY covers; the current region only when it holds at least half of the stretch (a drag that began a little
    // inside the current region and ran over its neighbour had resized the current one and removed its bands)
    const over = r => r.comps.length && r.lo < hi && r.hi > lo;
    const covered = r => Math.min(r.hi, hi) - Math.max(r.lo, lo);
    const cur = SP.regions[SP.cur];
    const target = cur && over(cur) && covered(cur) >= 0.5 * (hi - lo) ? cur : SP.regions.filter(over).sort((a, b) => covered(b) - covered(a))[0];
    // … unless the stretch is more than twice that region: then it is a stretch of its own (typing the first limit of
    // another region made the fitted one swallow half the spectrum, and refitted it there)
    if (target && hi - lo <= 2 * (target.hi - target.lo)) { SP.cur = SP.regions.indexOf(target); resizeRegion(target, lo, hi); if (zoom) zoomTo(target.lo, target.hi); return; }
    if (target) status(lo + '–' + hi + ' cm⁻¹ chosen (dashed). Auto fit fits it afresh and replaces the fitted region inside it — undo brings that back. To widen the fitted region instead, drag its edge.');
  }
  $('#sp-lo').value = lo; $('#sp-hi').value = hi;
  if (k !== SP.cur) SP.sel = -1;
  SP.cur = k;
  if (k >= 0) syncControls(SP.regions[k]);
  else if (!SP.regions.some(r => r.comps.length && r.lo < hi && r.hi > lo)) status(lo + '–' + hi + ' cm⁻¹ chosen (dashed): Auto fit, or ‘band’ and click where a band is');
  if (zoom) zoomTo(lo, hi);
  draw(); renderResult();
}
// the controls on the left show how the region now current was fitted
function syncControls(r) {
  if (!r || r.local == null) return;
  $('#sp-local').value = r.local; $('#sp-share-w').checked = !!r.share_width; $('#sp-share-eta').checked = !!r.share_eta;
  $('#sp-wmax').value = r.max_fwhm || ''; $('#sp-wmin').value = r.min_fwhm || '';
  const fold = $('#sp-fit-more');                            // a region fitted with one of the finer settings shows them: the fold opens
  if (fold && (r.share_width || r.share_eta || r.max_fwhm || r.min_fwhm)) fold.open = true;
}
function zoomTo(lo, hi) { const pad = 0.15 * (hi - lo); SP.view = [Math.max(SP.d.x[0], lo - pad), Math.min(SP.d.x[SP.d.x.length - 1], hi + pad)]; draw(); }
// A fitted region given new bounds: its bands stay (those now outside it go — undo brings them back), it stops at its
// neighbours, and the fit is done again over the new stretch.
function resizeRegion(reg, lo, hi) {
  const k = SP.regions.indexOf(reg), prev = SP.regions[k - 1], next = SP.regions[k + 1];
  lo = Math.max(lo, Math.ceil(SP.d.x[0]), prev ? prev.hi : -Infinity); hi = Math.min(hi, Math.floor(SP.d.x[SP.d.x.length - 1]), next ? next.lo : Infinity);
  if (!(hi - lo >= 10)) { $('#sp-lo').value = reg.lo; $('#sp-hi').value = reg.hi; reg.edgeBefore = null; status('a region is at least 10 cm⁻¹ wide and does not cross its neighbour', true); draw(); renderResult(); return; }
  if (lo === reg.lo && hi === reg.hi) { $('#sp-lo').value = lo; $('#sp-hi').value = hi; reg.edgeBefore = null; draw(); renderResult(); return; }
  const out = reg.comps.filter(c => c.pos < lo || c.pos > hi).length;
  reg.hist.push(reg.edgeBefore || snapshot(reg)); reg.edgeBefore = null; if (reg.hist.length > 60) reg.hist.shift(); reg.redo = [];
  reg.lo = lo; reg.hi = hi; reg.comps = reg.comps.filter(c => c.pos >= lo && c.pos <= hi);
  $('#sp-lo').value = lo; $('#sp-hi').value = hi;
  status('region now ' + lo + '–' + hi + ' cm⁻¹' + (out ? '; ' + out + ' band' + (out === 1 ? '' : 's') + ' outside it removed (undo brings ' + (out === 1 ? 'it' : 'them') + ' back)' : ''));
  changed(reg);
}
function currentRegion(make) {
  const lo = num('sp-lo'), hi = num('sp-hi');
  if (lo == null || hi == null || hi <= lo) { status('choose a region first: drag across the bands (region), or use a preset', true); return null; }
  let k = SP.regions.findIndex(r => Math.abs(r.lo - lo) < 1 && Math.abs(r.hi - hi) < 1);
  if (k < 0 && make) {
    keepList();                                                        // undo brings back what this replaces
    SP.regions = SP.regions.filter(r => r.hi <= lo || r.lo >= hi);     // a region replaces the ones it overlaps
    SP.regions.push({ lo, hi, fit: null, trials: [], comps: [], dirty: false, hist: [], redo: [] }); SP.regions.sort((a, b) => a.lo - b.lo);
    k = SP.regions.findIndex(r => r.lo === lo && r.hi === hi);
  }
  if (k !== SP.cur) SP.sel = -1;
  SP.cur = k;
  return k >= 0 ? SP.regions[k] : null;
}
function select(k, j) {
  const r = SP.regions[k]; if (!r) return;
  $('#sp-lo').value = r.lo; $('#sp-hi').value = r.hi;
  if (k !== SP.cur) syncControls(r);
  SP.cur = k; SP.sel = j; draw(); renderResult();
}
// the list of regions as it stands, before one is cleared, replaced or made: what undo goes back to when the current
// region has nothing left to undo
function keepList() { SP.lists.push({ regions: SP.regions.slice(), cur: SP.cur }); if (SP.lists.length > 20) SP.lists.shift(); SP.listsRedo = []; }
function backToList(from, to) {
  const s = from.pop(); to.push({ regions: SP.regions.slice(), cur: SP.cur });
  SP.regions = s.regions; SP.cur = s.cur < SP.regions.length ? s.cur : -1; SP.sel = -1;
  const r = SP.regions[SP.cur]; if (r) { $('#sp-lo').value = r.lo; $('#sp-hi').value = r.hi; syncControls(r); }
  draw(); renderResult();
}
function blurField() { const a = document.activeElement; if (a && a !== document.body && /^(INPUT|SELECT|TEXTAREA)$/.test(a.tagName)) a.blur(); }

// a band's handle: ● moves it and sets its height, ◆ sets its width
function startHandle(ev, k, j, what) {
  if (ev.button !== 0) return;
  ev.stopPropagation(); ev.preventDefault();
  blurField();                                               // a number still being typed is taken first
  const r = SP.regions[k]; SP.cur = k; SP.sel = j;
  drag = { kind: 'handle', what, reg: r, j, before: snapshot(r), moved: false };
}

function wirePlot() {
  const host = $('#sp-plot');
  host.addEventListener('mousemove', ev => {
    readout(ev);
    if (!drag || !G) return;
    const x = plotX(ev);
    if (drag.kind === 'edge') {                              // an end of the region follows the pointer; the bands are drawn as they stand
      const r = drag.reg, v = Math.round(G.Xinv(x));
      if (drag.side === 'lo') r.lo = Math.max(Math.ceil(SP.d.x[0]), Math.min(v, r.hi - 10)); else r.hi = Math.min(Math.floor(SP.d.x[SP.d.x.length - 1]), Math.max(v, r.lo + 10));
      $('#sp-lo').value = r.lo; $('#sp-hi').value = r.hi; r.dirty = true; drag.moved = true; draw();
    } else if (drag.kind === 'handle') {
      const b = drag.reg.comps[drag.j], f = drag.reg.fit, v = G.Xinv(x);
      if (drag.what === 'pos') {
        const base = f ? f.base[0] + f.base[1] * (v - f.x0) : 0;
        b.pos = Math.min(drag.reg.hi, Math.max(drag.reg.lo, v));
        b.height = Math.max(0, G.Yinv(plotY(ev)) - base - (SP.layers.raw ? (SP.d.baseline[Math.min(SP.d.x.length - 1, indexOf(v))] || 0) : 0));
      } else b.fwhm = Math.max(2 * Math.abs(SP.d.x[1] - SP.d.x[0]), 2 * Math.abs(v - b.pos));
      drag.moved = true; drag.reg.dirty = true; draw(); renderResult(true);
    } else if (drag.kind === 'pan') {
      const dx = (G.Xinv(drag.px) - G.Xinv(x));
      let [a, b] = [drag.view[0] + dx, drag.view[1] + dx];
      const lo = SP.d.x[0], hi = SP.d.x[SP.d.x.length - 1];
      if (a < lo) { b += lo - a; a = lo; } if (b > hi) { a -= b - hi; b = hi; }
      SP.view = [Math.max(lo, a), Math.min(hi, b)]; drag.moved = true; draw();
    } else if (drag.kind === 'region') {
      const sel = $('#sp-sel'); if (!sel) return;
      sel.setAttribute('x', Math.min(drag.px, x)); sel.setAttribute('width', Math.abs(x - drag.px)); drag.moved = Math.abs(x - drag.px) > 3;
    } else {                                                 // band / anchor mode: a drag is no click — nothing is drawn and nothing added
      drag.moved = drag.moved || Math.abs(x - drag.px) > 3;
    }
  });
  host.addEventListener('mousedown', ev => {
    if (!G || ev.button !== 0) return;
    blurField();                                             // the keys go to the plot from here (Delete was eating a digit of the field last typed in)
    const kind = ev.shiftKey || SP.mode === 'region' ? 'region' : SP.mode === 'pan' ? 'pan' : 'click';
    drag = { kind, px: plotX(ev), view: SP.view.slice(), G, pick: picked }; picked = null;
    ev.preventDefault();
  });
  window.addEventListener('mouseup', ev => {
    if (!drag || !G) { drag = null; return; }
    const d = drag; drag = null;
    const x = plotX(ev);
    if (d.kind === 'handle') {
      if (d.moved) { d.reg.hist.push(d.before); d.reg.redo = []; changed(d.reg); } else { draw(); renderResult(); }
      return;
    }
    if (d.kind === 'edge') {
      const r = d.reg, lo = r.lo, hi = r.hi;
      r.lo = d.lo0; r.hi = d.hi0; r.dirty = d.dirty0;        // back to where it was, then moved properly (neighbours, bands outside, undo, refit)
      if (d.moved) resizeRegion(r, lo, hi); else { r.edgeBefore = null; draw(); }
      return;
    }
    if (d.kind === 'region' && d.moved) { setRegion(d.G.Xinv(d.px), d.G.Xinv(x), false); return; }
    if (d.kind === 'click' && d.moved) { status('a drag adds no band: click where the band is — to choose a stretch use region mode or Shift-drag, to pan use pan mode'); return; }
    if (d.kind === 'click' || (d.kind === 'pan' && !d.moved && SP.mode !== 'pan')) clickAt(G.Xinv(x), plotY(ev));
    else if (d.kind === 'pan' && !d.moved && d.pick) select(d.pick[0], d.pick[1]);   // a plain click on a band: that band
    else if (d.kind === 'pan' && !d.moved) {                            // … elsewhere: the region under it
      const v = G.Xinv(x), k = SP.regions.findIndex(r => v >= r.lo && v <= r.hi);
      if (k >= 0) { if (k !== SP.cur) SP.sel = -1; setRegion(SP.regions[k].lo, SP.regions[k].hi, false); }
    }
  });
  host.addEventListener('wheel', ev => {
    if (!G || !SP.d) return;
    ev.preventDefault();
    if (ev.shiftKey || ev.altKey || plotX(ev) < M.l) {        // over the height axis, or with Shift / Alt: the vertical zoom (the foot of the curve enlarged)
      const dy = ev.deltaY || ev.deltaX; if (!dy) return;
      SP.yz = Math.min(500, Math.max(1, SP.yz * (dy > 0 ? 0.8 : 1.25))); draw(); return;
    }
    const x = G.Xinv(plotX(ev)), f = ev.deltaY > 0 ? 1.25 : 0.8;
    const lo = SP.d.x[0], hi = SP.d.x[SP.d.x.length - 1];
    const a = x - (x - SP.view[0]) * f, b = x + (SP.view[1] - x) * f;
    if (b - a < 4) return;
    SP.view = [Math.max(lo, a), Math.min(hi, b)]; draw();
  }, { passive: false });
  host.addEventListener('dblclick', () => { if (SP.d && SP.mode !== 'band' && SP.mode !== 'anchor') { SP.view = [SP.d.x[0], SP.d.x[SP.d.x.length - 1]]; SP.yz = 1; draw(); } });
  host.addEventListener('dragover', () => host.classList.add('drop'));
  host.addEventListener('dragleave', () => host.classList.remove('drop'));
  host.addEventListener('drop', () => host.classList.remove('drop'));
  // a file dropped ANYWHERE on the page is opened here (dropped beside the plot, the browser left the page for the file)
  window.addEventListener('dragover', ev => ev.preventDefault());
  window.addEventListener('drop', ev => {
    ev.preventDefault();
    const f = ev.dataTransfer && ev.dataTransfer.files[0]; if (!f) return;
    const picture = /\.(png|jpe?g|tiff?|bmp|gif|pdf)$/i.test(f.name);
    if (picture) { $('#sp-fig').classList.remove('hidden'); fgUpload(f); } else upload(f);
  });
  new ResizeObserver(() => draw()).observe(host);
  // the selected band from the keyboard: Delete removes it, the arrows nudge it; ⌘Z / Ctrl-Z undoes
  window.addEventListener('keydown', ev => {
    if (!$('#sp-fig').classList.contains('hidden')) return;   // the figure panel is open over the plot
    const t = ev.target || {};                              // a key typed into a field is the field's; a ticked box takes none
    if (t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || (t.tagName === 'INPUT' && !/^(checkbox|radio|button)$/.test(t.type))) return;
    const r = SP.regions[SP.cur];
    if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === 'z') { ev.preventDefault(); if (ev.shiftKey) redo(); else undo(); return; }
    if (!r || SP.sel < 0 || !r.comps[SP.sel]) return;
    if (ev.key === 'Delete' || ev.key === 'Backspace') { ev.preventDefault(); removeBand(r, SP.sel); }
    else if (ev.key === 'ArrowLeft' || ev.key === 'ArrowRight') {
      ev.preventDefault(); mutate(r, () => { r.comps[SP.sel].pos += (ev.key === 'ArrowLeft' ? -1 : 1) * (SP.layers.reverse ? -1 : 1) * (ev.shiftKey ? 5 : 1); });
    }
  });
}

function clickAt(x, py) {
  if (!SP.d) return;
  if (SP.mode === 'anchor') {
    const near = SP.anchors.findIndex(a => Math.abs(G.X(a) - G.X(x)) < 6);
    if (near >= 0) SP.anchors.splice(near, 1); else SP.anchors.push(+x.toFixed(1));
    SP.anchors.sort((a, b) => a - b);
    if ($('#sp-baseline').value !== 'anchors') { $('#sp-baseline').value = 'anchors'; showBaselineRows(); }
    process(false); return;
  }
  if (SP.mode === 'band') {
    let reg = SP.regions.find(r => x >= r.lo && x <= r.hi);
    if (!reg) {                                             // no region there yet: one around the click, up to its neighbours and never over them
      const prev = SP.regions.filter(r => r.hi < x).pop(), next = SP.regions.find(r => r.lo > x);
      const lo = Math.ceil(Math.max(SP.d.x[0], x - 60, prev ? prev.hi : -Infinity)), hi = Math.floor(Math.min(SP.d.x[SP.d.x.length - 1], x + 60, next ? next.lo : Infinity));
      if (hi - lo < 10) { status('no room for a region of its own between the fitted regions there: widen one of them (drag its edge)', true); return; }
      $('#sp-lo').value = lo; $('#sp-hi').value = hi; reg = currentRegion(true);
    } else { $('#sp-lo').value = reg.lo; $('#sp-hi').value = reg.hi; SP.cur = SP.regions.indexOf(reg); }
    const there = reg.comps.findIndex(c => Math.abs(G.X(c.pos) - G.X(x)) < 3);     // the second click of a double click: the band is there already
    if (there >= 0) { SP.sel = there; draw(); renderResult(); return; }
    // the band as clicked: at the height of the click above what the other bands already give there, as wide as a
    // band the finder saw there — else a tenth of the region
    const near = SP.d.peaks.find(p => Math.abs(p.pos - x) < Math.max(8, 0.3 * p.fwhm));
    const f = reg.fit; let under = f ? f.base[0] + f.base[1] * (x - f.x0) : 0;
    for (const c of reg.comps) under += profile(c, x);
    const i = Math.min(SP.d.x.length - 1, indexOf(x));
    const h = Math.max(G.Yinv(py) - (SP.layers.raw ? (SP.d.baseline[i] || 0) : 0) - under, 0) || Math.max(SP.d.y[i] - under, 0);
    const wmax = num('sp-wmax');
    let w = near ? near.fwhm : Math.max(8, 0.1 * (reg.hi - reg.lo)); if (wmax) w = Math.min(w, wmax);
    addBand(reg, { pos: +x.toFixed(1), height: h, fwhm: w });
  }
}

// ---- editing the bands -----------------------------------------------------------
const bare = c => ({ shape: c.shape, pos: c.pos, height: c.height, fwhm: c.fwhm, eta: c.eta == null ? 0.5 : c.eta, fix: (c.fix || []).slice(), wmax: c.wmax || null, wmin: c.wmin || null });
// A snapshot is the region as it stood: its bounds, its bands and their FIT (curve, statistics, warnings). Undo and redo
// put it back as it was — nothing is fitted again (an evaluation on the way back gave other numbers than had been shown).
const HOW = ['local', 'share_width', 'share_eta', 'max_fwhm', 'min_fwhm', 'refine'];
const snapshot = r => JSON.stringify({ lo: r.lo, hi: r.hi, comps: r.comps.map(bare), fit: r.fit, dirty: !!r.dirty, trials: r.trials || [], how: HOW.map(k => r[k]) });
function restore(r, snap) {
  const s = JSON.parse(snap);
  r.comps = s.comps; r.fit = s.fit || null; r.dirty = s.fit ? s.dirty : r.comps.length > 0; r.trials = s.trials || []; r.prevBic = null;
  if (s.how) { HOW.forEach((k, i) => { r[k] = s.how[i]; }); if (r === SP.regions[SP.cur]) syncControls(r); }
  r.lo = s.lo; r.hi = s.hi; if (r === SP.regions[SP.cur]) { $('#sp-lo').value = r.lo; $('#sp-hi').value = r.hi; }
  if (SP.sel >= r.comps.length) SP.sel = r.comps.length - 1;
}
function mutate(reg, fn) {                                  // every change to the bands goes through here: undo, preview, refit
  reg.hist.push(snapshot(reg)); if (reg.hist.length > 60) reg.hist.shift(); reg.redo = [];
  fn();
  changed(reg);
}
// What a change sets off (when 'heights follow edits' is on; off, the change is only previewed):
//   'edit'     a band was moved, added, removed, split, merged, typed over, or the region resized — the HEIGHTS of all
//              bands are fitted again and nothing else moves; no band is removed (a refit of everything after each edit
//              walked hand-placed bands away and deleted the one just dragged)
//   'options'  how the region is fitted was changed (local baseline, one width, widest …) — a fit as 'Fit these' does
// (undo / redo do not come here: a snapshot carries its fit)
function changed(reg, how) {
  reg.dirty = true; reg.seq = (reg.seq || 0) + 1;          // a fit still on its way is of the bands before this change
  clearTimeout(reg.timer);
  if (SP.sel >= reg.comps.length) SP.sel = reg.comps.length - 1;
  if (!reg.comps.length) { reg.fit = null; reg.dirty = false; }
  draw(); renderResult();                                   // the change itself at once (dashed), the fit when it comes
  if (!$('#sp-live').checked || !reg.comps.length) return;
  if (how === 'options') fitRegion(reg, reg.comps);
  else reg.timer = setTimeout(() => fitRegion(reg, reg.comps, { refine: 'heights', keep_dead: true }), 150);   // ten arrow presses are one fit, not ten in a queue
}
function addBand(reg, b) {
  mutate(reg, () => { reg.comps.push(Object.assign({ shape: $('#sp-shape').value, eta: 0.5, fix: [] }, b)); reg.comps.sort((a, c) => a.pos - c.pos); SP.sel = reg.comps.findIndex(c => c.pos === b.pos); });
}
function removeBand(reg, j) { mutate(reg, () => { reg.comps.splice(j, 1); SP.sel = Math.min(j, reg.comps.length - 1); }); }
function splitBand(reg, j) {                                 // one band into two a third of its width apart, each narrower
  mutate(reg, () => {
    const c = reg.comps[j], d = c.fwhm / 3;
    reg.comps.splice(j, 1, Object.assign(bare(c), { pos: c.pos - d / 2, fwhm: 0.75 * c.fwhm, height: 0.6 * c.height }), Object.assign(bare(c), { pos: c.pos + d / 2, fwhm: 0.75 * c.fwhm, height: 0.6 * c.height }));
  });
}
const twin = (reg, j) => {                                   // as spectrum.twins: closer than half the narrower width, and of like width
  const a = reg.comps[j], b = reg.comps[j + 1]; if (!a || !b) return false;
  const lo = Math.min(a.fwhm, b.fwhm), hi = Math.max(a.fwhm, b.fwhm);
  return Math.abs(b.pos - a.pos) < 0.5 * lo && hi < 2 * lo;
};
function mergeBands(reg, j) {                                // two bands the data cannot tell apart, as one
  mutate(reg, () => {
    const a = reg.comps[j], b = reg.comps[j + 1], h = a.height + b.height || 1;
    reg.comps.splice(j, 2, Object.assign(bare(a.height >= b.height ? a : b), { pos: (a.pos * a.height + b.pos * b.height) / h || 0.5 * (a.pos + b.pos), height: Math.max(a.height, b.height), fwhm: Math.max(a.fwhm, b.fwhm) }));
    SP.sel = j;
  });
}
function undo() {
  const r = SP.regions[SP.cur];
  if (r && r.hist.length) {
    r.seq = (r.seq || 0) + 1; clearTimeout(r.timer);        // a fit still on its way belongs to the state being left
    r.redo.push(snapshot(r)); restore(r, r.hist.pop()); draw(); renderResult(); return;
  }
  // nothing left in the region (or none is current): the list of regions as it was before one was cleared, replaced or made
  if ((!r || !r.comps.length) && SP.lists.length) { backToList(SP.lists, SP.listsRedo); status('the regions as they were before'); return; }
  status(r ? 'nothing to undo in this region' : 'nothing to undo: click a region first');
}
function redo() {
  const r = SP.regions[SP.cur];
  if (r && r.redo.length) {
    r.seq = (r.seq || 0) + 1; clearTimeout(r.timer);
    r.hist.push(snapshot(r)); restore(r, r.redo.pop()); draw(); renderResult(); return;
  }
  if (SP.listsRedo.length) { backToList(SP.listsRedo, SP.lists); return; }
  status('nothing to redo');
}

// ---- fitting -------------------------------------------------------------------
// An answer is taken only while it is still of what is on the screen: the region's own count (another fit or an edit of
// THAT region since), the spectrum's (another curve since), and the region still there. One count for all regions
// dropped the answer of a slow fit when a quick one of another region came in between.
// how a region that is NOT current is fitted again: with its own settings. The controls show the current region's
// (syncControls), so reading them for another region wrote the current one's settings into it (a baseline change refitted
// every stale region that way and recorded one width / widest where they had never been asked for)
function howOf(reg) {
  if (reg.local == null) return {};
  return { local: reg.local, share_width: !!reg.share_width, share_eta: !!reg.share_eta, max_fwhm: reg.max_fwhm || null, min_fwhm: reg.min_fwhm || null };
}
async function fitRegion(reg, comps, extra) {
  const body = Object.assign(fitOpts(reg), reg !== SP.regions[SP.cur] ? howOf(reg) : {}, extra || {});
  if (comps && comps.length) body.comps = comps.map(bare);
  else {
    const n = num('sp-n'); if (n && !body.n) body.n = n;
    if ($('#sp-seed').checked && SP.d) body.seeds = SP.d.ticks.filter(t => t.pos >= reg.lo && t.pos <= reg.hi);
  }
  clearTimeout(reg.timer);
  const seq = reg.seq = (reg.seq || 0) + 1, gen = SP.gen, full = !(extra && (extra.keep_dead || extra.evaluate));
  const live = () => seq === reg.seq && gen === SP.gen && SP.regions.includes(reg);
  busy(1, full);
  try {
    status('fitting ' + reg.lo + '–' + reg.hi + ' cm⁻¹…');
    const r = await api('/api/sp/fit', body);
    if (!live()) return;                                    // a later change is already being fitted, or the spectrum is another: this answer is stale
    if (full) { reg.hist.push(snapshot(reg)); if (reg.hist.length > 60) reg.hist.shift(); reg.redo = []; }   // a fit that may move bands is a step undo takes back; the heights refit after an edit belongs to the edit's own step
    reg.prevBic = reg.fit && reg.fit.lo === r.fit.lo && reg.fit.n === r.fit.n ? reg.fit.bic : null;
    const selPos = SP.sel >= 0 && reg.comps[SP.sel] ? reg.comps[SP.sel].pos : null;
    reg.fit = r.fit; reg.comps = r.fit.comps.map(bare); reg.dirty = false;
    reg.trials = r.trials;                                  // the models an automatic fit or '+ band' tried; none for a plain refit
    if (selPos != null && reg === SP.regions[SP.cur]) {      // the selected band, wherever the fit left it
      let best = -1; reg.comps.forEach((c, j) => { if (best < 0 || Math.abs(c.pos - selPos) < Math.abs(reg.comps[best].pos - selPos)) best = j; }); SP.sel = best;
    }
    // how it was fitted stays with the region: an export, a session and an undo evaluate it with these, whatever the controls say by then
    reg.local = body.local; reg.share_width = body.share_width; reg.share_eta = body.share_eta; reg.max_fwhm = body.max_fwhm; reg.min_fwhm = body.min_fwhm;
    reg.refine = body.comps ? body.refine || '' : '';
    status(r.fit.comps.length + ' band' + (r.fit.comps.length === 1 ? '' : 's') + ' fitted, ' + reg.lo + '–' + reg.hi + ' cm⁻¹' + (r.fit.converged ? '' : ' — not converged'));
  } catch (e) { if (live()) status(e.message, true); }
  finally { busy(-1, full); }
  if (live()) { draw(); renderResult(); }
}
function busy(by, full) {
  SP.fits = Math.max(0, SP.fits + by); if (full) SP.fitting = Math.max(0, SP.fitting + by);
  $('#sp-busy').classList.toggle('hidden', !SP.fits); $('#sp-plot').classList.toggle('busy', SP.fitting > 0);
  for (const id of ['sp-auto', 'sp-refit', 'sp-add']) $('#' + id).disabled = SP.fitting > 0;     // a click on a fit already running queued another
}

function renderResult(light) {
  const tb = $('#sp-table'), st = $('#sp-stats'), wn = $('#sp-warnings'), cp = $('#sp-compare');
  const reg = SP.cur >= 0 ? SP.regions[SP.cur] : null;
  if (!light) renderLibrary();                              // its 'fitted here' column follows the bands
  if (light && reg) {                                       // during a drag: the numbers of the dragged band only
    const row = tb.querySelectorAll('tr')[SP.sel + 1], b = reg.comps[SP.sel];
    if (row && b) { const inp = row.querySelectorAll('input[type=number]'); if (inp.length >= 3) { inp[0].value = b.pos.toFixed(1); inp[1].value = b.fwhm.toFixed(1); inp[2].value = +b.height.toPrecision(5); } }
    return;
  }
  // the cell being typed in keeps the focus (and what was typed) across the rebuild: Tab goes on to the next cell
  const ae = document.activeElement; let keep = null;
  if (ae && ae.tagName === 'INPUT' && ae.type === 'number' && tb.contains(ae)) {
    const tr = ae.closest('tr'); keep = [[...tb.children].indexOf(tr), [...tr.querySelectorAll('input[type=number]')].indexOf(ae), ae.value !== ae.defaultValue ? ae.value : null];
  }
  saveWork();
  tb.textContent = ''; st.textContent = ''; wn.textContent = ''; cp.textContent = '';
  const hint = $('#sp-hint'); hint.textContent = ''; hint.classList.add('hidden');
  $('#sp-export').classList.toggle('hidden', !SP.regions.some(r => r.fit && r.comps.length));
  if (!SP.d) return;
  if (!reg || !reg.comps.length) {
    st.textContent = SP.regions.some(r => r.comps.length) ? 'Click a fitted region to see its bands, or choose another region and fit it.'
      : 'Choose a region (drag across the bands with ‘region’, or a preset on the left) and press Auto fit — or choose ‘band’ and click where you see one.';
    return;
  }
  const f = reg.fit;
  if (f) {
    const gain = reg.prevBic != null && !reg.dirty ? reg.prevBic - f.bic : null;
    st.textContent = reg.lo + '–' + reg.hi + ' cm⁻¹: ' + f.n + ' points, ' + f.k + ' parameters; reduced χ² ' + fmt(f.chi2) + ', R² ' + f.r2.toFixed(4) + ', BIC ' + f.bic.toFixed(1)
      + (gain != null && Math.abs(gain) >= 0.05 ? ' (' + (gain > 0 ? 'better' : 'WORSE') + ' by ' + Math.abs(gain).toFixed(1) + ' than the fit before)' : '')
      + (f.converged ? '' : '; NOT CONVERGED') + (reg.dirty ? '   — changed since this fit: press ‘Fit these’' : '')
      + (reg.trials && reg.trials.length && !reg.dirty ? '   · models tried: ' + reg.trials.map(t => t.n + ' (BIC ' + t.bic.toFixed(0) + ')').join(', ') : '');
  } else st.textContent = reg.lo + '–' + reg.hi + ' cm⁻¹: not fitted yet — press ‘Fit these’';
  if (f && !reg.dirty && f.envelope && !num('sp-wmax')) {
    const e = f.envelope;
    hint.classList.remove('hidden');
    hint.append('The band at ' + e.pos.toFixed(0) + ' cm⁻¹ is ' + e.fwhm.toFixed(0) + ' wide and has finer bands inside it (' + e.inside.map(v => v.toFixed(0)).join(', ') +
      '). One broad band, or an envelope of narrower ones? The data do not say.',
      el('button', { title: 'Sets ‘widest’ to ' + e.cap + ' cm⁻¹ and fits the region again from scratch: no band may be wider, so the envelope comes apart into several. Undo brings this fit back.',
        onclick: () => { $('#sp-wmax').value = e.cap; SP.sel = -1; fitRegion(reg, null); } }, 'Fit as an envelope (widest ' + e.cap + ')'));
  }
  const info = f && !reg.dirty ? f.comps : [];
  const total = info.reduce((s, c) => s + (c.area || 0), 0) || 1;
  tb.append(el('tr', null, ...['position (cm⁻¹)', 'FWHM', 'height', 'area %', 'shape', 'hold', SP.lib && SP.lib.rows.length ? (SP.lib.source === 'picked' ? 'expected of the groups picked' : 'expected of the formula') : 'where papers place it', 'distance', ''].map(h => el('th', null, h))));
  reg.comps.forEach((c, k) => {
    const fc = info[k] || {};
    const cell = (key, digits) => {
      let shown = String(key === 'height' ? +c[key].toPrecision(5) : c[key].toFixed(digits));
      const inp = el('input', { type: 'number', step: key === 'height' ? 'any' : '0.1', value: shown });
      // taken when the field is left or Enter is pressed — a moment later, so that the focus has moved on first (Tab)
      const commit = () => {
        if (inp.value === shown) return;
        const v = parseFloat(inp.value);
        if (!Number.isFinite(v) || (key === 'height' ? v < 0 : key === 'fwhm' ? v <= 0 : false)) { inp.value = shown; status(key === 'height' ? 'a height is zero or more' : 'a width is above zero', true); return; }
        shown = inp.value;
        setTimeout(() => { if (reg.comps[k] && SP.regions.includes(reg)) mutate(reg, () => { reg.comps[k][key] = v; }); }, 0);
      };
      inp.addEventListener('change', commit); inp.addEventListener('blur', commit);
      inp.addEventListener('focus', () => { if (SP.sel !== k) { SP.sel = k; draw(); [...tb.querySelectorAll('tr')].slice(1).forEach((tr, j) => tr.classList.toggle('sel', j === k)); } });
      const e = fc.esd && fc.esd[key];
      return el('td', null, inp, e ? el('span', { class: 'esd' }, ' ± ' + (key === 'height' ? fmt(e) : e >= 0.095 ? e.toFixed(1) : e.toPrecision(1))) : null,
        key === 'fwhm' && fc.at_limit ? el('span', { class: 'lim', title: 'this width rests on its limit' }, ' ⇥') : null);
    };
    const shape = el('select', { title: 'the shape of this band' }, ...[['pvoigt', 'pseudo-Voigt' + (c.shape === 'pvoigt' ? ' η ' + (+c.eta).toFixed(2) : '')], ['gauss', 'Gaussian'], ['lorentz', 'Lorentzian']].map(([v, t]) => el('option', { value: v }, t)));
    shape.value = c.shape;
    shape.addEventListener('change', () => mutate(reg, () => { reg.comps[k].shape = shape.value; }));
    const hold = (what, letter, tip) => {
      const cb = el('input', { type: 'checkbox' }); cb.checked = (c.fix || []).includes(what);
      cb.addEventListener('change', () => mutate(reg, () => { const fx = new Set(reg.comps[k].fix || []); if (cb.checked) fx.add(what); else fx.delete(what); reg.comps[k].fix = [...fx]; }));
      return el('label', { title: tip }, cb, letter);
    };
    const tr = el('tr', { class: (k === SP.sel ? 'sel' : '') + (reg.dirty ? ' edited' : '') }, cell('pos', 1), cell('fwhm', 1), cell('height', 0),
      el('td', null, fc.area != null ? (100 * fc.area / total).toFixed(0) : ''),
      el('td', null, shape),
      el('td', { class: 'hold' }, hold('pos', 'pos', 'keep this position as it is in the fit'), hold('fwhm', 'width', 'keep this width as it is in the fit'), hold('height', 'height', 'keep this height as it is in the fit')),
      el('td', { class: 'w' }, chemList(fc.suggest || [])), el('td', { class: 'w' }, chemNodes(fc.distance || '')),
      el('td', null, twin(reg, k) ? el('button', { class: 'lim', title: 'this band and the next are closer than half their width — the data cannot tell them apart: make them one band, and refit', onclick: ev => { ev.stopPropagation(); mergeBands(reg, k); } }, 'merge ↓') : null, ' ',
        el('button', { title: 'split this band into two narrower ones side by side, and refit', onclick: ev => { ev.stopPropagation(); splitBand(reg, k); } }, 'split'), ' ',
        el('button', { title: 'remove this band (Delete, when it is selected)', onclick: ev => { ev.stopPropagation(); removeBand(reg, k); } }, '×')));
    tr.addEventListener('mousedown', ev => { if (!/^(INPUT|SELECT|BUTTON|LABEL|OPTION)$/.test(ev.target.tagName) && SP.sel !== k) { SP.sel = k; draw(); renderResult(); } });
    tb.append(tr);
  });
  if (keep) {
    const tr = tb.children[keep[0]], inp = tr && tr.querySelectorAll('input[type=number]')[keep[1]];
    if (inp) { inp.focus(); if (keep[2] != null) inp.value = keep[2]; else inp.select(); }
  }
  if (f && !reg.dirty) for (const w of f.warnings) wn.append(el('div', { class: 'warn' }, w));
  if (f && !reg.dirty && (f.next || []).length) wn.append(el('div', { class: 'muted' }, 'The residual still holds a band near ' + f.next.map(n => n.pos.toFixed(0)).join(', ') + ' cm⁻¹ (▲ under the plot: click one, or ‘+ band’).'));
  if (f && !reg.dirty && f.stated) {
    const s = f.stated;
    if (s.matched.length) cp.append(el('div', null, 'Stated in the manuscript and fitted: ' + s.matched.map(m => m[0] + ' (fitted ' + m[1].toFixed(1) + ')').join(', ')));
    if (s.not_fitted.length) cp.append(el('div', { class: 'lost' }, 'Stated in the manuscript, no fitted band near: ' + s.not_fitted.join(', ') + ' cm⁻¹'));
    if (s.not_stated.length) cp.append(el('div', { class: 'muted' }, 'Fitted, not stated in the manuscript: ' + s.not_stated.map(v => v.toFixed(1)).join(', ') + ' cm⁻¹'));
  }
}

// ---- files, export ---------------------------------------------------------------
async function upload(file) {
  if (/\.json$/i.test(file.name)) {                           // a session: read here, nothing is sent
    try { await applySession(JSON.parse(await file.text()), file.name); } catch (e) { status(file.name + ' is not a session written by this window', true); }
    return;
  }
  const fd = new FormData(); fd.append('file', file);
  status('opening ' + file.name + '…');
  try {
    const r = await fetch('/api/sp/upload', { method: 'POST', body: fd });
    const j = await r.json().catch(() => null);
    if (!r.ok || !j || !j.ok) throw new Error((j && j.error) || ('the server answered ' + r.status));
    const waiting = SP.pending && ((SP.pending.options || {}).name || SP.pending.file) === j.name ? SP.pending : null;
    await loadState(waiting ? null : j.name);
    if (waiting) await applySession(waiting, 'the session');     // the spectrum a session was waiting for
  } catch (e) { status(e.message, true); }
}
// a written file, by its kind: a workbook or a Word file opens in its own program, the table and the figure in a browser
// tab, and a session takes the fit up again
function openOutput(n) {
  if (/\.json$/.test(n)) return loadSession(n);
  if (/\.(txt|svg)$/.test(n)) { window.open('/api/sp/file?name=' + enc(n), '_blank'); return; }
  fetch('/api/sp/open?file=' + enc(n), { method: 'POST' }).then(r => { if (!r.ok) status('that file is no longer in review_out', true); }).catch(() => {});
}
const outputTitle = n => /\.json$/.test(n) ? 'reopen this session: its options and bands as they were written' : /\.(txt|svg)$/.test(n) ? 'show ' + n + ' in a new tab' : 'open ' + n;
function listOutputs(names) {
  const o = $('#sp-outputs'); o.textContent = '';
  for (const n of names || []) o.append(el('a', { title: outputTitle(n), onclick: () => openOutput(n) }, n));
}
async function exportAll(fmt_) {
  const ed = SP.regions.find(r => r.dirty && r.comps.length);
  if (ed) { status('the region ' + ed.lo + '–' + ed.hi + ' cm⁻¹ was changed since its fit (dashed): click it and press ‘Fit these’, so that the table written is a fit', true); return; }
  // the bands as they stand are written, each region as IT was fitted — no fitting on the way out: the table is the fit on the screen
  const regions = SP.regions.filter(r => r.fit && r.comps.length).map(asFitted);
  if (!regions.length) { status('nothing fitted yet: fit a region first', true); return; }
  try {
    const r = await api('/api/sp/export', Object.assign(opts(), { regions, fmt: fmt_, reverse: !!SP.layers.reverse }));
    status('written into ' + r.folder);
    const box = $('#sp-exported'); box.textContent = ''; box.classList.remove('hidden');
    const main = fmt_ === 'xlsx' ? r.files.xlsx : fmt_ === 'word' ? r.files.docx : r.files.txt;
    box.append(el('div', null, 'Written into ', el('span', { class: 'path' }, r.folder), el('button', { title: 'show the written file in the file manager', onclick: () => fetch('/api/sp/reveal?file=' + enc(main), { method: 'POST' }).catch(() => {}) }, 'show folder'),
      el('button', { title: 'hide this', onclick: () => box.classList.add('hidden') }, '×')));
    box.append(el('div', null, ...Object.values(r.files).map(n => el('a', { title: outputTitle(n), onclick: () => openOutput(n) }, n))));
    if (fmt_ === 'xlsx' || fmt_ === 'word') openOutput(main);       // what was asked for, opened
    const s = await api('/api/sp/state'); listOutputs(s.outputs);
  } catch (e) { status(e.message, true); }
}

// ---- sessions: a fit taken up again ---------------------------------------------
// An export writes <name>_sp.json: the options and every band as they stood. Loading one sets the options, opens the
// spectrum it names (from the folder, or one opened here — else it waits for that file), and puts the bands back.
async function loadSession(name) {
  try {
    const r = await fetch('/api/sp/file?as=json&name=' + enc(name));
    if (!r.ok) throw new Error('that session is no longer in review_out');
    await applySession(await r.json(), name);
  } catch (e) { status(e.message, true); }
}
async function applySession(s, label, quiet) {
  if (!s || !Array.isArray(s.fits) || !s.options) { status((label || 'that file') + ' is not a session written by this window', true); return; }
  const was = SP.ready; SP.ready = false;                    // nothing is kept of the half-opened state
  try { await applySession_(s, quiet); } finally { SP.ready = was || !quiet; }
  if (SP.ready) saveWork();
}
async function applySession_(s, quiet) {
  const o = s.options, file = o.name || s.file;
  if (!SP.state.files.some(f => f.name === file) && s.figure && s.figure.name === file) {      // a curve read off a figure travels in its session
    try {
      await api('/api/sp/fig/restore', { name: file, x: s.figure.x, y: s.figure.y, cm_per_px: s.figure.cm_per_px, notes: s.figure.notes });
      await loadState(null);
    } catch (e) { status(e.message, true); return; }
  }
  if (!SP.state.files.some(f => f.name === file)) {
    SP.pending = s;
    status('this session is of ‘' + file + '’, which is not in the folder: open that spectrum (Open file…) and the session follows', true);
    return;
  }
  SP.pending = null;
  const set = (id, v) => { if (v != null && $('#' + id)) $('#' + id).value = v; };
  set('sp-kind', o.kind || ''); set('sp-threshold', o.threshold); set('sp-resolution', o.resolution == null ? '' : o.resolution); set('sp-baseline', o.baseline || 'none');
  set('sp-lam', o.lam ? +Math.log10(o.lam).toFixed(2) : null); set('sp-p', o.p); set('sp-width', o.width); $('#sp-laser').value = o.laser == null ? '' : o.laser;
  $('#sp-despike').checked = !!o.despike; showBaselineRows();
  if (o.cif && SP.state.cifs.includes(o.cif)) $('#sp-cif').value = o.cif;
  if (o.ms && SP.state.manuscripts.includes(o.ms)) $('#sp-ms').value = o.ms;
  const chem = o.formula_typed != null ? o.formula_typed : (o.formula || '');
  if (chem) $('#sp-formula').value = chem;                  // a session that names no chemistry leaves the one in the field
  if (Array.isArray(o.groups)) { SP.pick = o.groups.map(String); keepPick(); } else if (o.groups === null) { SP.pick = null; keepPick(); }   // a session written before the picker leaves it
  pickSummary();
  $('#sp-file').value = file;
  SP.gen++;
  SP.file = file; SP.series = o.series || 0; SP.d = null; SP.d2 = null; SP.regions = []; SP.cur = -1; SP.sel = -1; SP.anchors = (o.anchors || []).slice(); SP.lists = []; SP.listsRedo = [];
  try {
    const r = await api('/api/sp/series?name=' + enc(file));
    const ssel = $('#sp-series'); ssel.textContent = '';
    for (const t of r.series) ssel.append(el('option', { value: t.i }, t.name.replace(file + ' | ', '') + ' — ' + t.n + ' points'));
    SP.seriesList = r.series; ssel.value = String(SP.series); ssel.classList.toggle('hidden', r.series.length < 2);
  } catch (e) { status(e.message, true); return; }
  await process(true);
  if (!SP.d) return;
  if ((o.kind || SP.d.kind || '').startsWith('ir')) setReverse(true);
  s.fits.forEach((f, k) => {
    const rg = (o.regions || [])[k] || {};
    const lo = Math.round(rg.lo != null ? rg.lo : f.lo), hi = Math.round(rg.hi != null ? rg.hi : f.hi);
    SP.regions.push({ lo, hi, comps: f.components.map(bare), fit: null, dirty: true, hist: [], redo: [], trials: [], local: rg.local || (f.baseline && f.baseline[1] ? 'linear' : 'const'),
      share_width: !!rg.share_width, share_eta: !!rg.share_eta, max_fwhm: rg.max_fwhm || null, min_fwhm: rg.min_fwhm || null, refine: rg.refine || '',
      base0: f.baseline || null, x0: f.x0, converged: f.converged });
  });
  // each region as it was written: its curve and statistics, with no fitting
  for (const reg of SP.regions) {
    try {
      const r = await api('/api/sp/fit', Object.assign(opts(), asFitted(reg), { evaluate: true, min_share: num('sp-share') }));
      reg.fit = r.fit; reg.comps = r.fit.comps.map(bare); reg.dirty = false;
    } catch (e) { status(e.message, true); }
  }
  if (SP.regions.length) {
    const r0 = SP.regions[0]; SP.cur = 0; $('#sp-lo').value = r0.lo; $('#sp-hi').value = r0.hi; syncControls(r0);
    const pad = 0.1 * (r0.hi - r0.lo); SP.view = [Math.max(SP.d.x[0], r0.lo - pad), Math.min(SP.d.x[SP.d.x.length - 1], r0.hi + pad)];
  }
  if (!quiet) status('session reopened: ' + SP.regions.length + ' region' + (SP.regions.length === 1 ? '' : 's') + ', ' + SP.regions.reduce((n, r) => n + r.comps.length, 0) + ' bands, as they were written');
  draw(); renderResult();
}

function showBaselineRows() {
  const k = $('#sp-baseline').value;
  for (const row of document.querySelectorAll('.sp-b')) row.classList.toggle('hidden', !row.classList.contains('sp-b-' + k));
}

// the divider under the plot: drag it to give the plot or the band table more room (remembered)
function wireSplit() {
  const bar = $('#sp-split'), plot = $('#sp-plot'), main = $('#sp-main');
  const apply = h => { plot.style.flex = '0 0 ' + Math.round(h) + 'px'; };
  try { const h = JSON.parse(localStorage.getItem(LS) || '{}').plotH; if (h > 120) apply(Math.min(h, window.innerHeight - 200)); } catch (_) {}
  let from = null;
  bar.addEventListener('mousedown', ev => { from = { y: ev.clientY, h: plot.getBoundingClientRect().height }; ev.preventDefault(); document.body.style.cursor = 'row-resize'; });
  window.addEventListener('mousemove', ev => { if (from) apply(Math.max(140, Math.min(main.getBoundingClientRect().height - 110, from.h + ev.clientY - from.y))); });
  window.addEventListener('mouseup', () => {
    if (!from) return; from = null; document.body.style.cursor = '';
    try { const p = JSON.parse(localStorage.getItem(LS) || '{}'); p.plotH = plot.getBoundingClientRect().height; localStorage.setItem(LS, JSON.stringify(p)); } catch (_) {}
  });
  bar.addEventListener('dblclick', () => { plot.style.flex = ''; try { const p = JSON.parse(localStorage.getItem(LS) || '{}'); delete p.plotH; localStorage.setItem(LS, JSON.stringify(p)); } catch (_) {} });
}

function wire() {
  $('#sp-file').addEventListener('change', e => chooseFile(e.target.value));
  $('#sp-series').addEventListener('change', async e => {
    SP.ready = false; SP.gen++;
    SP.series = parseInt(e.target.value, 10) || 0; SP.regions = []; SP.cur = -1; SP.sel = -1; SP.lists = []; SP.listsRedo = [];
    const t = SP.seriesList[SP.series]; if (t && !$('#sp-kind').value) setReverse((t.kind || '').startsWith('ir'));
    await process(true); await restoreWork(); SP.ready = true;
  });
  $('#sp-kind').addEventListener('change', e => { if (e.target.value) setReverse(e.target.value.startsWith('ir')); process(false); });
  $('#sp-formula').addEventListener('change', () => { keepChem(); saveWork(); loadLib(); });
  $('#sp-formula').addEventListener('keydown', e => { if (e.key === 'Enter') e.target.blur(); e.stopPropagation(); });
  $('#sp-open').addEventListener('click', () => $('#sp-upload').click());
  wireRruff();
  // the 'more ▾' and 'Chem search' popovers close on a click elsewhere or Escape (a <details> stays open until its summary is clicked again)
  for (const pop of document.querySelectorAll('details.pop')) {
    document.addEventListener('mousedown', ev => { if (pop.open && !pop.contains(ev.target)) pop.open = false; });
    document.addEventListener('keydown', ev => { if (ev.key === 'Escape' && pop.open) pop.open = false; });
  }
  wirePicker();
  $('#sp-upload').addEventListener('change', e => { if (e.target.files.length) upload(e.target.files[0]); e.target.value = ''; });
  for (const id of ['sp-despike', 'sp-threshold', 'sp-resolution', 'sp-lam', 'sp-p', 'sp-width', 'sp-cif', 'sp-ms', 'sp-laser'])
    $('#' + id).addEventListener('change', () => process(false));
  $('#sp-baseline').addEventListener('change', () => { showBaselineRows(); process(false); });
  $('#sp-anchors-clear').addEventListener('click', () => { SP.anchors = []; process(false); });
  // typed limits are applied when BOTH fields are settled: 'change' fired on the first field (Tab, click away) while the
  // other still held the old bound, and that pair resized the region at once — narrowing it and removing its bands
  // before the second limit was typed. So: 'focusout' (which knows where the focus goes — 'change' fires before it
  // moves) applies unless the focus went to the other limit field; Enter in a field applies at once, an explicit commit.
  const limitsTyped = () => { const lo = num('sp-lo'), hi = num('sp-hi'); if (lo != null && hi != null && hi > lo) setRegion(lo, hi, false); };
  const otherLimit = id => $('#' + (id === 'sp-lo' ? 'sp-hi' : 'sp-lo'));
  for (const id of ['sp-lo', 'sp-hi']) {
    $('#' + id).addEventListener('keydown', ev => { if (ev.key === 'Enter') { ev.preventDefault(); limitsTyped(); } });
    $('#' + id).addEventListener('focusout', ev => {
      if (ev.relatedTarget === otherLimit(id)) return;
      const r = SP.regions[SP.cur], lo = num('sp-lo'), hi = num('sp-hi');
      if (lo != null && hi != null && (!r || lo !== r.lo || hi !== r.hi)) limitsTyped();
    });
  }
  // how the region is fitted: a change refits the bands there are (when 'refit as I edit' is on)
  for (const id of ['sp-local', 'sp-share-w', 'sp-share-eta', 'sp-wmax', 'sp-wmin']) $('#' + id).addEventListener('change', () => { savePrefs(); const r = SP.regions[SP.cur]; if (r && r.comps.length) changed(r, 'options'); });
  for (const id of ['sp-maxn', 'sp-share', 'sp-live', 'sp-refine']) $('#' + id).addEventListener('change', savePrefs);
  // the shape: of every band of the current region (one step of undo), and of the bands added from here on
  $('#sp-shape').addEventListener('change', () => { savePrefs(); const r = SP.regions[SP.cur], v = $('#sp-shape').value; if (r && r.comps.some(c => c.shape !== v)) mutate(r, () => { for (const c of r.comps) c.shape = v; }); });
  $('#sp-d2w').addEventListener('change', () => { savePrefs(); loadD2(); });
  $('#sp-auto').addEventListener('click', () => { const r = currentRegion(true); if (r) { SP.sel = -1; fitRegion(r, null); } });
  $('#sp-refit').addEventListener('click', () => {
    const r = currentRegion(false);
    if (!r || !r.comps.length) { status('no bands in this region yet: Auto fit, or add one with ‘band’', true); return; }
    fitRegion(r, r.comps);
  });
  $('#sp-add').addEventListener('click', () => {
    const r = currentRegion(true); if (!r) return;
    if (!r.comps.length) { fitRegion(r, null, { n: 1 }); return; }
    fitRegion(r, r.comps, { add: true });
  });
  $('#sp-less').addEventListener('click', () => {
    const r = currentRegion(false); if (!r || !r.comps.length) { status('no band to take out: click a fitted region first', true); return; }
    const area = c => c.height * c.fwhm; let j = 0; r.comps.forEach((c, k) => { if (area(c) < area(r.comps[j])) j = k; });
    removeBand(r, j);
  });
  $('#sp-undo').addEventListener('click', undo); $('#sp-redo').addEventListener('click', redo);
  $('#sp-clear').addEventListener('click', () => {
    if (SP.cur < 0) { status('no region is selected: click the one to clear', true); return; }
    keepList(); const r = SP.regions.splice(SP.cur, 1)[0]; SP.cur = -1; SP.sel = -1;
    status('the region ' + r.lo + '–' + r.hi + ' cm⁻¹ and its ' + r.comps.length + ' band' + (r.comps.length === 1 ? '' : 's') + ' cleared — undo brings them back');
    draw(); renderResult();
  });
  for (const b of document.querySelectorAll('#sp-mode button')) b.addEventListener('click', () => {
    SP.mode = b.getAttribute('data-m');
    for (const o of document.querySelectorAll('#sp-mode button')) o.classList.toggle('on', o === b);
  });
  for (const cb of document.querySelectorAll('#sp-layers input[data-layer]')) {
    const k = cb.getAttribute('data-layer'); cb.checked = !!SP.layers[k];
    cb.addEventListener('change', () => { SP.layers[k] = cb.checked; savePrefs(); if (k === 'd2' && cb.checked) loadD2(); else draw(); });
  }
  for (const b of document.querySelectorAll('[data-fmt]')) b.addEventListener('click', () => exportAll(b.getAttribute('data-fmt')));
  wirePlot(); wireSplit(); wireFig();
}

// ---- a spectrum from a figure ------------------------------------------------------
// A page of a paper or an image; on it the user confirms the plot's FRAME, two points of its AXIS with their values,
// and the CURVE (a click gives its colour and says which of several is meant). The server traces; the red line over the
// figure is what it followed. All coordinates are the image's own pixels.
const FG = { name: '', i: 0, w: 0, h: 0, frames: [], box: null, x1: null, x2: null, colour: null, seed: null, trace: null, downSet: false, drag: null,
  ticks: [],              // the evenly spaced tick strokes found on the frame's axis (pixel x): what a mark dropped near the axis snaps to
  peaks: null };          // the tops of the traced curve's peaks (pixel x), after a Trace: what a mark dropped on a peak snaps to
const fgStatus = (msg, bad) => { const s = $('#sp-fig-status'); s.textContent = msg || ''; s.title = msg || ''; s.style.color = bad ? 'var(--danger)' : ''; };
// ---- the group picker: 'Chem search' over the plot -------------------------------------------------------------------
// The library's groups by element (P: PO4, P–OH; As: AsO4, As–OH, AsO3 …) as chips; a chip toggles its group, the element
// letter all of its groups. SP.pick is null while the pick follows the chemistry's own groups (ticked, marked ·); the
// first click makes the pick explicit. Under the chips: the modes drawn (their colours and ranges) and the species of the
// local Mindat snapshot holding every group picked — a RRUFF spectrum of each where this machine has one.
const PK = { cat: null, seq: 0, filter: '', only: false, sort: 'name' };   // sort: 'name' | 'spectra' (those with one first)
const pickNow = () => SP.pick != null ? SP.pick.slice() : (SP.lib ? SP.lib.groups.map(g => g.key) : []);
function setPick(keys) {
  SP.pick = keys; keepPick(); pickSummary(); saveWork(); loadLib();
}
function wirePicker() {
  const pk = $('#sp-pick'); if (!pk) return;
  pk.addEventListener('toggle', () => { if (pk.open) renderPicker(); });
}
async function renderPicker() {
  const pk = $('#sp-pick'), host = $('#sp-pick-body'); if (!pk || !host || !pk.open) return;
  if (!PK.cat) {
    try { PK.cat = await api('/api/sp/groups'); } catch (e) { host.textContent = e.message; return; }
    if (!pk.open) return;
  }
  const on = new Set(pickNow()), own = new Set(SP.lib && SP.lib.own ? SP.lib.own : []);
  host.textContent = '';
  const asChem = el('button', { title: 'Back to the groups of the chemistry (the ‘chemistry’ field, else the manuscript’s formula)' }, 'as the chemistry');
  asChem.disabled = SP.pick == null; asChem.addEventListener('click', () => setPick(null));
  const none = el('button', { title: 'No group: no bars over the plot' }, 'none'); none.addEventListener('click', () => setPick([]));
  host.append(el('div', { class: 'pk-head' }, el('span', null, 'The groups whose bands are drawn over the plot — a chip toggles a group, the element letter all of its groups; · marks the chemistry’s own.'), asChem, none));
  const byEl = new Map();
  for (const g of PK.cat.groups) { if (!byEl.has(g.element)) byEl.set(g.element, []); byEl.get(g.element).push(g); }
  const strip = el('div', { class: 'pk-strip' });
  for (const [e, gs] of byEl) {
    const letter = el('b', { title: (gs.every(g => on.has(g.key)) ? 'drop' : 'pick') + ' every group of ' + e + ': ' + gs.map(g => g.writes).join(', ') }, e);
    letter.addEventListener('click', () => { const keys = pickNow(), all = gs.every(g => on.has(g.key)); setPick(all ? keys.filter(k => !gs.some(g => g.key === k)) : keys.concat(gs.filter(g => !on.has(g.key)).map(g => g.key))); });
    const span = el('span', { class: 'pk-el' }, letter);
    for (const g of gs) {
      const chip = el('button', { class: 'pk-chip' + (on.has(g.key) ? ' on' : '') + (own.has(g.key) ? ' own' : ''),
        title: g.name + ' — ' + g.modes.map(m => m.label + ' ' + m.lo + '–' + m.hi).join(', ') + '. ' + g.species + ' species of the snapshot' + (PK.cat.rruff ? ', ' + g.rruff + ' with a RRUFF spectrum' : '') + (own.has(g.key) ? '. A group of the chemistry' : '') }, ionNodes(g.writes));
      if (on.has(g.key)) chip.style.setProperty('--c', groupColour(g.key));
      chip.addEventListener('click', () => { const keys = pickNow(); setPick(on.has(g.key) ? keys.filter(k => k !== g.key) : keys.concat([g.key])); });
      span.append(chip);
    }
    strip.append(span);
  }
  host.append(strip);
  if (SP.lib && SP.lib.rows.length) {
    const leg = el('div', { class: 'pk-legend' });
    for (const r of SP.lib.rows) { if (r.broad) continue; const sw = el('i', { class: 'sw' }); sw.style.background = rowColour(r); leg.append(el('span', { title: r.what + '; ' + r.active }, sw, labelNodes(r.label), ' ' + r.lo + '–' + r.hi)); }
    host.append(leg);
  }
  const sp = el('div', { class: 'pk-species' }); host.append(sp);
  loadSpecies(sp);
}
let speciesTimer = null;
async function loadSpecies(host, keep) {
  const keys = pickNow(), seq = ++PK.seq;
  if (!keys.length) { host.textContent = ''; host.append(el('span', { class: 'muted' }, 'No group picked: no species to list.')); return; }
  if (!keep) { host.textContent = ''; host.append(el('span', { class: 'muted' }, 'looking for the species that hold ', chemList(keys, ' + '), '…')); }
  let r;
  try { r = await api('/api/sp/species', { groups: keys, q: PK.filter.trim(), only_spectra: PK.only }); } catch (e) { host.textContent = e.message; return; }
  if (seq !== PK.seq) return;
  const had = keep ? host.querySelector('input[type=text]') : null, caret = had ? had.selectionStart : null;
  host.textContent = '';
  const filt = el('input', { type: 'text', placeholder: 'filter by name or formula…', spellcheck: 'false', autocomplete: 'off' }); filt.value = PK.filter;
  const list = el('div', { class: 'pk-list' });
  const withSpectra = PK.cat && PK.cat.rruff && RR.choose;
  const again = () => { clearTimeout(speciesTimer); speciesTimer = setTimeout(() => loadSpecies(host, true), 250); };   // the server filters the WHOLE list
  const fill = () => {
    list.textContent = ''; let n = 0;
    const rows = PK.sort === 'spectra' ? r.species.slice().sort((a, b) => (!a.rruff) - (!b.rruff)) : r.species;    // a stable sort: by name within each half
    for (const s of rows) {
      if (++n > 600) { list.append(el('div', { class: 'muted' }, '… and more: narrow the filter')); break; }
      const f = el('span', { class: 'f' }); f.innerHTML = s.html || s.formula;             // Mindat's own sub/sup, every other tag escaped on the server
      const row = el('div', { class: 'pk-sp' + (s.rruff ? ' rr' : '') }, el('b', { title: s.rruff ? 'open the RRUFF spectrum of ' + s.name + ' here (' + s.rruff.n + ' spectr' + (s.rruff.n === 1 ? 'um' : 'a') + ' in the library)' : s.formula }, s.name), f);
      if (s.rruff && RR.choose) {                            // a name with a spectrum opens it in the window; 'overlay' draws it under the curve instead
        row.firstChild.addEventListener('click', () => RR.choose(s.rruff.name, 'open'));
        const v = el('button', { title: 'Draw the RRUFF spectrum of ' + s.name + ' under the current curve, scaled to it' }, 'overlay');
        v.addEventListener('click', () => RR.choose(s.rruff.name, 'overlay'));
        row.append(v);
      }
      list.append(row);
    }
    if (!n) list.append(el('div', { class: 'muted' }, (PK.only ? 'no species with a spectrum on this machine holds ' : 'no species of the snapshot holds '), chemList(keys, ' + '), (PK.filter.trim() ? ' and matches ‘' + PK.filter.trim() + '’' : '')));
  };
  filt.addEventListener('input', () => { PK.filter = filt.value; again(); });
  filt.addEventListener('keydown', e => { e.stopPropagation(); if (e.key === 'Escape') $('#sp-pick').open = false; });
  const q = PK.filter.trim();
  const head = el('div', { class: 'pk-species-head' }, el('span', { class: 'muted' }, r.total + ' species of the local Mindat snapshot hold ', chemList(keys, ' + '),
    (withSpectra ? ' · ' + r.with_rruff + ' with a RRUFF spectrum on this machine, highlighted — a name opens its spectrum here' : '') +
    (q || PK.only ? ' · ' + r.matching + ' match' : '') + (r.matching > r.species.length ? ' · the first ' + r.species.length + ' listed' : '')), filt);
  if (withSpectra) {
    const sort = el('select', { title: 'The order of the list' }, el('option', { value: 'name' }, 'A–Z'), el('option', { value: 'spectra' }, 'with a spectrum first'));
    sort.value = PK.sort; sort.addEventListener('change', () => { PK.sort = sort.value; fill(); });
    const cb = el('input', { type: 'checkbox' }); cb.checked = PK.only; cb.addEventListener('change', () => { PK.only = cb.checked; loadSpecies(host, true); });
    head.append(sort, el('label', { class: 'muted', title: 'List only the species the RRUFF library on this machine has a spectrum of' }, cb, ' only with a spectrum'));
  }
  host.append(head, list);
  fill();
  if (had) { filt.focus(); try { filt.setSelectionRange(caret, caret); } catch (_) {} }
}

// ---- the RRUFF library on this machine: a mineral's spectrum pulled up here, or drawn under the curve -------------
// The list comes from /api/sp/rruff/list once (hidden when there is no library); a mineral typed into the box fills the
// select with its spectra; 'open' holds the spectrum on the server under a name and opens it like a file opened here;
// 'overlay' draws it under the current curve, scaled to the curve in view (SP.overlay = {name, x, y}; draw()).
const RR = { minerals: null, byName: {} };
// a name as a key: diacritics folded, lowercase (Mindat writes 'Nybøite', RRUFF 'Nyboite'; the server keys on mindat._norm the same way)
const rrKey = s => String(s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/ø/g, 'o').replace(/Ø/g, 'O').replace(/æ/g, 'ae').replace(/ß/g, 'ss').replace(/ł/g, 'l').replace(/đ/g, 'd').toLowerCase().trim();
// the list's answer put into the box (a datalist of minerals); with no library, the 'RRUFF library…' button instead
function rruffFill(r) {
  const box = $('#sp-rruff-box'), find = $('#sp-rruff-find'), setb = $('#sp-rruff-set');
  if (!r || !r.minerals || !r.minerals.length) { box.classList.add('hidden'); find.classList.remove('hidden'); return false; }
  RR.minerals = r.minerals; RR.byName = {};
  const dl = $('#sp-rruff-list'); dl.textContent = '';
  for (const m of r.minerals) { RR.byName[rrKey(m.name)] = m; dl.append(el('option', { value: m.name })); }
  find.classList.add('hidden'); setb.classList.add('hidden'); box.classList.remove('hidden');
  $('#sp-rruff').title = $('#sp-rruff').title.replace(/ \d+ minerals,.*$/, '') + ' ' + r.minerals.length + ' minerals, ' + r.n + ' spectra (' + r.folder + ').' + (r.citation ? ' Cite: ' + r.citation : '');
  $('#sp-rruff-more').classList.toggle('hidden', !!r.store);  // a fuller collection can be fetched beside an OMNIC copy
  PK.cat = null;                                               // the picker learns which species have a spectrum
  if (SP.lib) renderLibrary();                                 // the library may have rendered first: its 'compare with RRUFF' buttons need the list
  return true;
}
const specLabel = s => s.id + ' ' + (s.kind || 'spectrum') + (s.laser ? ' ' + s.laser + ' nm' : '') + (s.technique === 'infrared' ? ' IR' : '') +
  (s.quality || s.orient ? ' · ' + [s.quality, s.orient].filter(Boolean).join(', ') : '');
// the fetch from rruff.net: started on the server, followed here every two seconds until it is done
let fetchTimer = null;
async function rruffFetch() {
  try {
    await api('/api/sp/rruff/fetch', {});
    status('fetching RRUFF from rruff.net…'); rruffFollow();
  } catch (e) { status(e.message, true); if (/already running/.test(e.message)) rruffFollow(); }
}
function rruffFollow() {
  clearTimeout(fetchTimer);
  fetchTimer = setTimeout(async () => {
    let r; try { r = await api('/api/sp/rruff/status'); } catch (e) { status(e.message, true); return; }
    const f = r.fetch || {};
    if (!f.stage) { status('the RRUFF fetch is no longer running on the server (restarted?) — fetch again if the store is incomplete', true); return; }
    if (!f.finished) {
      const mb = v => (v / 1048576).toFixed(0);
      status(f.stage === 'reading' ? 'RRUFF: reading ' + (f.set || '') + ' — ' + (f.spectra || 0) + ' spectra so far'
           : 'RRUFF: downloading ' + (f.set || '') + (f.total ? ' — ' + mb(f.done || 0) + ' of ' + mb(f.total) + ' MB' : ''));
      rruffFollow(); return;
    }
    if (f.error) { status('RRUFF fetch failed: ' + f.error, true); return; }
    try { const l = await api('/api/sp/rruff/list'); if (rruffFill(l)) { status('RRUFF: ' + l.n + ' spectra of ' + l.minerals.length + ' minerals in the cache — found from now on whatever folder is open' + (f.missing && f.missing.length ? ' (not on rruff.net: ' + f.missing.join(', ') + ')' : '')); if ($('#sp-pick').open) renderPicker(); } } catch (e) { status(e.message, true); }
  }, 2000);
}
async function wireRruff() {
  const box = $('#sp-rruff-box'); if (!box) return;
  // the folder named by hand: kept by the server for every later start
  $('#sp-rruff-find').addEventListener('click', () => { $('#sp-rruff-set').classList.toggle('hidden'); if (!$('#sp-rruff-set').classList.contains('hidden')) $('#sp-rruff-path').focus(); });
  $('#sp-rruff-path').addEventListener('keydown', e => { e.stopPropagation(); if (e.key === 'Enter') $('#sp-rruff-use').click(); if (e.key === 'Escape') $('#sp-rruff-set').classList.add('hidden'); });
  $('#sp-rruff-fetch').addEventListener('click', rruffFetch); $('#sp-rruff-more').addEventListener('click', rruffFetch);
  $('#sp-rruff-use').addEventListener('click', async () => {
    try {
      const r = await api('/api/sp/rruff/set', { folder: $('#sp-rruff-path').value });
      if (rruffFill(r)) { status('RRUFF library: ' + r.minerals.length + ' minerals, ' + r.n + ' spectra (' + r.folder + ') — remembered for every folder'); if ($('#sp-pick').open) renderPicker(); }
      else status('that folder holds no spectra', true);
    } catch (e) { status(e.message, true); }
  });
  const specSel = $('#sp-rruff-spec'), openBtn = $('#sp-rruff-open'), ovLab = $('#sp-rruff-ov');
  const pick = () => {
    const m = RR.byName[rrKey($('#sp-rruff').value)];
    specSel.textContent = '';
    if (!m) { specSel.classList.add('hidden'); openBtn.classList.add('hidden'); ovLab.classList.add('hidden'); return; }
    const seen = {};
    for (const s of m.spectra) { const lab = specLabel(s); seen[lab] = (seen[lab] || 0) + 1; specSel.append(el('option', { value: s.key }, lab + (seen[lab] > 1 ? ' (' + seen[lab] + ')' : ''))); }   // one sample, many orientations
    specSel.classList.remove('hidden'); openBtn.classList.remove('hidden'); ovLab.classList.remove('hidden');
    if ($('#sp-overlay').checked) overlayNow();
  };
  const overlayNow = async () => {
    const key = specSel.value;
    if (!key || !$('#sp-overlay').checked) { SP.overlay = null; draw(); return; }
    try {
      const r = await api('/api/sp/rruff/curve?key=' + enc(key));
      if (specSel.value !== key) return;                     // another was chosen while this one loaded
      SP.overlay = { name: r.name, x: r.x, y: r.y, peaks: r.peaks || [] }; draw();
      status(r.name + ' drawn under the curve (overlay)');
    } catch (e) { status(e.message, true); }
  };
  RR.choose = (name, action) => {                           // the species list of the group picker: a mineral put into the box, then opened or overlaid
    $('#sp-rruff').value = name; pick();
    if (!RR.byName[rrKey(name)]) { status('no spectrum of ' + name + ' in the RRUFF library', true); return; }
    if (action === 'open') openBtn.click();
    else if (action === 'overlay') { $('#sp-overlay').checked = true; overlayNow(); }
  };
  $('#sp-rruff').addEventListener('change', pick);
  $('#sp-rruff').addEventListener('input', () => { if (RR.byName[rrKey($('#sp-rruff').value)]) pick(); });
  specSel.addEventListener('change', overlayNow);
  $('#sp-overlay').addEventListener('change', overlayNow);
  openBtn.addEventListener('click', async () => {
    const key = specSel.value; if (!key) return;
    if ($('#sp-overlay').checked) { $('#sp-overlay').checked = false; SP.overlay = null; }   // the reference becomes the curve: not drawn under itself
    try {
      const r = await api('/api/sp/rruff/open', { key: +key });
      await loadState(r.name);                                // the list of files now holds it (opened here); it opens as the current spectrum
    } catch (e) { status(e.message, true); }
  });
  let r = null;                                              // wired above whether or not a library is there yet: one named later fills the same box
  try { r = await api('/api/sp/rruff/list'); } catch (_) { r = null; }
  rruffFill(r);
  if (r && r.fetch && r.fetch.stage && !r.fetch.finished) { status('a RRUFF fetch is running…'); rruffFollow(); }
}

async function fgOpen() {
  $('#sp-fig').classList.remove('hidden');
  // a page already open comes back as it was left — frame, marks, values, colour, trace (Close and Escape only hide the
  // panel); the list of sources is refreshed in case a file was added. The first version reopened on the first starred
  // page and wiped everything confirmed by hand.
  if (FG.name && FG.w) { await fgSources(FG.name, true); fgDraw(); return; }
  await fgSources();
}
async function fgSources(pick, keepPage) {
  try { SP.state = await api('/api/sp/state'); } catch (e) { fgStatus(e.message, true); return; }
  const sel = $('#sp-fig-src'); sel.textContent = '';
  const names = SP.state.figures || [];
  if (!names.length) sel.append(el('option', { value: '' }, 'no .pdf, .docx or image in the folder — Open image…'));
  for (const n of names) sel.append(el('option', { value: n }, n));
  const ms = $('#sp-ms').value;                              // the manuscript set beside the spectrum, when it is one of them
  const want = pick || FG.name || names.find(n => ms && n.replace(/\.[^.]+$/, '') === ms) || names[0] || '';
  sel.value = want;
  if (keepPage && want === FG.name && names.includes(want)) return;    // the page open stays open
  if (want) await fgPages(want);
}
async function fgPages(name) {
  FG.name = name; FG.i = 0;
  const sel = $('#sp-fig-page'); sel.textContent = '';
  try {
    const r = await api('/api/sp/fig/sources?name=' + enc(name));
    for (const s of r.sources) sel.append(el('option', { value: s.index }, (s.spectrum ? '★ ' : '') + s.label));
    sel.classList.toggle('hidden', r.sources.length < 2);
    const first = r.sources.find(s => s.spectrum) || r.sources[0];
    if (!first) { fgStatus('nothing to show in ' + name, true); return; }
    sel.value = String(first.index);
    await fgPage(first.index);
  } catch (e) { fgStatus(e.message, true); }
}
async function fgPage(i) {
  FG.i = i; FG.box = null; FG.trace = null; FG.colour = null; FG.seed = null; FG.frames = []; FG.x1 = FG.x2 = null; FG.downSet = false; FG.ticks = []; FG.peaks = null;
  $('#sp-fig-use').disabled = true; $('#sp-fig-v1').value = ''; $('#sp-fig-v2').value = ''; $('#sp-fig-down').checked = false; $('#sp-fig-swatch').style.background = '';
  const img = $('#sp-fig-img');
  fgStatus('opening…');
  await new Promise(res => { img.onload = res; img.onerror = res; img.src = '/api/sp/fig/image?name=' + enc(FG.name) + '&i=' + i + '&t=' + Date.now(); });
  if (!img.naturalWidth) { fgStatus('that page could not be shown', true); return; }
  FG.w = img.naturalWidth; FG.h = img.naturalHeight;
  try {
    const r = await api('/api/sp/fig/detect', { name: FG.name, i });
    FG.frames = r.frames;
    // the frame offered: one whose axis numbers the page keeps as text and that look like wavenumbers, else the largest
    const good = r.frames.find(f => f.ticks.length >= 3 && Math.abs(f.ticks[f.ticks.length - 1][1] - f.ticks[0][1]) >= 300) || r.frames[0];
    if (good) fgTake(good);
    fgDraw();
    if (FG.box) $('#sp-fig-view').scrollTop = Math.max(0, FG.box[1] * FG.scale - 70);     // the frame offered, in view
    fgStatus(r.frames.length ? r.frames.length + ' frame' + (r.frames.length === 1 ? '' : 's') + ' found' + (good && good.ticks.length ? '; the axis is scaled from the numbers under it — check the two marks' : '; put the two marks on two numbered ticks and type their numbers') : 'no frame found: drag one around the plot');
  } catch (e) { fgStatus(e.message, true); }
  fgDraw();
}
function fgTake(f, keepAxis) {
  FG.box = f.box.slice(); FG.trace = null; FG.peaks = null; $('#sp-fig-use').disabled = true;
  FG.ticks = f.marks || [];
  if (keepAxis) return;
  if (f.ticks && f.ticks.length >= 2) {
    const a = f.ticks[0], b = f.ticks[f.ticks.length - 1];
    FG.x1 = a[0]; FG.x2 = b[0]; $('#sp-fig-v1').value = a[1]; $('#sp-fig-v2').value = b[1];
  } else if (FG.ticks.length >= 2) {                         // a picture: the marks start on its first and last tick, their numbers to be typed
    FG.x1 = FG.ticks[0]; FG.x2 = FG.ticks[FG.ticks.length - 1]; $('#sp-fig-v1').value = ''; $('#sp-fig-v2').value = '';
  } else {
    const wd = FG.box[2] - FG.box[0];
    FG.x1 = FG.box[0] + 0.1 * wd; FG.x2 = FG.box[2] - 0.1 * wd; $('#sp-fig-v1').value = ''; $('#sp-fig-v2').value = '';
  }
}
// a mark let go: onto the nearest tick when it is dropped near the axis, onto the nearest peak's top when it is dropped
// higher on a traced curve — within nine screen pixels, and not at all with Alt held
function fgSnap(key, x, y, free) {
  const b = FG.box; if (!b || free) return '';
  const nearAxis = y > b[3] - 0.2 * (b[3] - b[1]);
  const pool = nearAxis || !FG.peaks ? [FG.ticks, 'a tick'] : [FG.peaks, 'the top of a peak'];
  let best = null;
  for (const t of pool[0]) if (best == null || Math.abs(t - x) < Math.abs(best - x)) best = t;
  if (best == null || Math.abs(best - x) * FG.scale > 9) return '';
  FG[key] = best;
  return pool[1];
}
function fgLoupe(ev, x, y) {
  const lp = $('#sp-fig-loupe');
  if (!ev) { lp.classList.add('hidden'); return; }
  const Z = Math.max(3, 2.5 / FG.scale);                    // image pixels enlarged: at least three screen pixels each
  lp.classList.remove('hidden');
  lp.style.backgroundImage = 'url("' + $('#sp-fig-img').src + '")';
  lp.style.backgroundSize = (FG.w * Z) + 'px ' + (FG.h * Z) + 'px';
  lp.style.backgroundPosition = (110 - x * Z) + 'px ' + (75 - y * Z) + 'px';
  lp.style.left = Math.min(window.innerWidth - 240, ev.clientX + 24) + 'px'; lp.style.top = Math.max(8, ev.clientY - 180) + 'px';
}
function fgDraw() {
  const img = $('#sp-fig-img'), svg = $('#sp-fig-svg'), view = $('#sp-fig-view');
  if (!FG.w) return;
  // a page (taller than wide) as wide as the panel, scrolled to its plot; a picture of a plot (wider than tall) whole in the panel
  const wfit = (view.clientWidth - 30) / FG.w, hfit = (view.clientHeight - 20) / FG.h;
  const scale = Math.min(1.5, FG.w >= FG.h ? Math.min(wfit, hfit) : wfit);
  FG.scale = scale;
  img.style.width = Math.round(FG.w * scale) + 'px';
  svg.setAttribute('viewBox', '0 0 ' + FG.w + ' ' + FG.h); svg.style.width = Math.round(FG.w * scale) + 'px'; svg.style.height = Math.round(FG.h * scale) + 'px';
  svg.textContent = '';
  const px = 1 / scale;                                      // one screen pixel in image pixels
  for (const f of FG.frames) {
    if (FG.box && f.box.every((v, k) => Math.abs(v - FG.box[k]) < 2)) continue;
    const r = sv('rect', { class: 'f-other', x: f.box[0], y: f.box[1], width: f.box[2] - f.box[0], height: f.box[3] - f.box[1] }, sv('title', null, 'another frame found: click to take it'));
    r.addEventListener('mousedown', ev => { ev.stopPropagation(); fgTake(f); fgDraw(); });
    svg.append(r);
  }
  if (FG.box) {
    const b = FG.box;
    svg.append(sv('rect', { class: 'f-box', x: b[0], y: b[1], width: b[2] - b[0], height: b[3] - b[1] }));
    for (const [key, id] of [['x1', 'sp-fig-v1'], ['x2', 'sp-fig-v2']]) {
      const x = FG[key]; if (x == null) continue;
      const top = Math.max(b[1] - 26 * px, 16 * px), g = sv('g', { class: 'f-mark' },      // the handle over the frame — inside the picture when the frame reaches its top
        sv('line', { x1: x, x2: x, y1: top, y2: b[3] + 10 * px }),
        sv('path', { d: 'M' + (x - 8 * px) + ',' + (top - 12 * px) + ' h' + 16 * px + ' v' + 9 * px + ' l' + (-8 * px) + ',' + 9 * px + ' l' + (-8 * px) + ',' + (-9 * px) + ' Z' }),
        sv('rect', { x: x - 7 * px, y: top, width: 14 * px, height: b[3] - top }),
        sv('text', { x: x + 10 * px, y: top - 2 * px, 'font-size': 13 * px }, $('#' + id).value === '' ? '?' : $('#' + id).value),
        sv('title', null, 'drag onto a numbered tick of the axis, then type its number (' + (key === 'x1' ? 'left' : 'right') + ' mark)'));
      g.addEventListener('mousedown', ev => { ev.stopPropagation(); ev.preventDefault(); FG.drag = { kind: 'mark', key }; });
      svg.append(g);
    }
  }
  if (FG.box) for (const t of FG.ticks) svg.append(sv('line', { class: 'f-tick', x1: t, x2: t, y1: FG.box[3] + 2 * px, y2: FG.box[3] + 9 * px }));
  if (FG.trace) svg.append(sv('polyline', { class: 'f-trace', points: FG.trace.map(p => p[0] + ',' + p[1]).join(' ') }));
  if (FG.trace && FG.peaks) {                                // the tops a mark can be dropped on
    const yAt = x => { let b = FG.trace[0]; for (const p of FG.trace) if (Math.abs(p[0] - x) < Math.abs(b[0] - x)) b = p; return b[1]; };
    for (const p of FG.peaks) svg.append(sv('circle', { class: 'f-apex', cx: p, cy: yAt(p), r: 3 * px }));
  }
  if (FG.seed) svg.append(sv('circle', { class: 'f-seed', cx: FG.seed[0], cy: FG.seed[1], r: 7 * px }));
  if (FG.drag && FG.drag.kind === 'box' && FG.drag.moved) {
    const d = FG.drag;
    svg.append(sv('rect', { class: 'f-drag', x: Math.min(d.x0, d.x), y: Math.min(d.y0, d.y), width: Math.abs(d.x - d.x0), height: Math.abs(d.y - d.y0) }));
  }
}
function fgPoint(ev) {
  const r = $('#sp-fig-svg').getBoundingClientRect();
  return [Math.max(0, Math.min(FG.w, (ev.clientX - r.left) / FG.scale)), Math.max(0, Math.min(FG.h, (ev.clientY - r.top) / FG.scale))];
}
async function fgTrace(use) {
  if (!FG.box) { fgStatus('drag a frame around the plot first', true); return; }
  const v1 = num('sp-fig-v1'), v2 = num('sp-fig-v2');
  if (use && (v1 == null || v2 == null)) { fgStatus('type the axis values at the two marks (drag each onto a numbered tick first)', true); return; }
  const body = { name: FG.name, i: FG.i, box: FG.box, x1: FG.x1, v1, x2: FG.x2, v2, colour: FG.colour, seed: FG.seed, use: !!use };
  if (FG.downSet) body.down = $('#sp-fig-down').checked;
  try {
    fgStatus('tracing…');
    const r = await api('/api/sp/fig/trace', body);
    FG.trace = r.trace; FG.peaks = r.peaks || null; $('#sp-fig-use').disabled = !!r.pixels_only;
    if (!FG.downSet) $('#sp-fig-down').checked = r.down;
    if (r.colour) $('#sp-fig-swatch').style.background = 'rgb(' + r.colour.join(',') + ')';
    if (r.pixels_only) {                                     // the curve followed, the axis not scaled yet
      fgStatus('the curve is followed (' + r.n + ' points, ' + (r.how === 'vector' ? 'the drawing’s own curve' : 'through the pixels') + '). Now the axis: put the two marks on two numbered ticks and type their numbers, then Trace again.');
      fgDraw(); return;
    }
    fgStatus(r.n + ' points, ' + Math.round(r.lo) + '–' + Math.round(r.hi) + ' cm⁻¹; a pixel is ' + r.cm_per_px.toFixed(1) + ' cm⁻¹; ' + (r.how === 'vector' ? 'the drawing’s own curve' : 'followed through the pixels') +
      (r.coverage < 0.9 ? '; found on ' + Math.round(100 * r.coverage) + ' % of the frame’s width — click on the curve if this is not it' : '') + (r.down ? '; bands down' : ''));
    fgDraw();
    if (use && r.name) {
      $('#sp-fig').classList.add('hidden');
      const stem = FG.name.replace(/\.[^.]+$/, '');
      await loadState(r.name);
      if (SP.state.manuscripts.includes(stem) && $('#sp-ms').value !== stem) { $('#sp-ms').value = stem; await process(false); }   // its own text's bands beside it
    }
  } catch (e) { fgStatus(e.message, true); }
}
function wireFig() {
  $('#sp-fig-open').addEventListener('click', fgOpen);
  $('#sp-fig-close').addEventListener('click', () => $('#sp-fig').classList.add('hidden'));
  $('#sp-fig-src').addEventListener('change', e => { if (e.target.value) fgPages(e.target.value); });
  $('#sp-fig-page').addEventListener('change', e => fgPage(parseInt(e.target.value, 10) || 0));
  $('#sp-fig-file').addEventListener('click', () => $('#sp-fig-upload').click());
  $('#sp-fig-upload').addEventListener('change', async e => {
    const f = e.target.files[0]; e.target.value = ''; if (!f) return;
    await fgUpload(f);
  });
  for (const id of ['sp-fig-v1', 'sp-fig-v2']) $('#' + id).addEventListener('input', () => { FG.trace = null; $('#sp-fig-use').disabled = true; fgDraw(); });
  $('#sp-fig-down').addEventListener('change', () => { FG.downSet = true; });
  $('#sp-fig-trace').addEventListener('click', () => fgTrace(false));
  $('#sp-fig-use').addEventListener('click', () => fgTrace(true));
  const svg = $('#sp-fig-svg');
  svg.addEventListener('mousedown', ev => {
    if (ev.button !== 0 || !FG.w) return;
    ev.preventDefault();
    const [x, y] = fgPoint(ev); FG.drag = { kind: 'box', x0: x, y0: y, x, y, moved: false };
  });
  window.addEventListener('mousemove', ev => {
    const d = FG.drag; if (!d || $('#sp-fig').classList.contains('hidden')) return;
    const [x, y] = fgPoint(ev);
    if (d.kind === 'mark') {                                  // the loupe on the axis while the mark is near it (the ticks under the hairline), on the pointer higher up (a peak)
      FG[d.key] = x; $('#sp-fig-use').disabled = true;
      const b = FG.box; fgLoupe(ev, x, b && y > b[3] - 0.2 * (b[3] - b[1]) ? b[3] + 3 : y);
    }
    else { d.x = x; d.y = y; d.moved = d.moved || Math.abs(x - d.x0) * FG.scale > 5 || Math.abs(y - d.y0) * FG.scale > 5; }
    fgDraw();
  });
  window.addEventListener('mouseup', async ev => {
    const d = FG.drag; if (!d) return; FG.drag = null;
    if ($('#sp-fig').classList.contains('hidden')) return;
    if (d.kind === 'mark') {
      fgLoupe(null);
      const [x, y] = fgPoint(ev), on = fgSnap(d.key, x, y, ev.altKey);
      fgStatus(on ? 'the mark is on ' + on + ': type its number' : 'the mark is where it was dropped (no tick or peak within reach): type its number');
      fgDraw(); return;
    }
    if (d.moved) {                                           // a frame of the user's own
      const box = [Math.round(Math.min(d.x0, d.x)), Math.round(Math.min(d.y0, d.y)), Math.round(Math.max(d.x0, d.x)), Math.round(Math.max(d.y0, d.y))];
      if (box[2] - box[0] > 30 && box[3] - box[1] > 30) {
        const keep = FG.x1 != null && num('sp-fig-v1') != null && num('sp-fig-v2') != null;      // an axis already scaled stays scaled: the two marks are of the axis, not of the frame
        let own = { box, ticks: [], marks: [] };
        try { const r = await api('/api/sp/fig/detect', { name: FG.name, i: FG.i, box }); if (r.own) own = r.own; } catch (_) {}     // the ticks on this frame's axis
        fgTake(own, keep);
      }
      fgDraw(); return;
    }
    try {                                                    // a click: the curve's colour, and which curve
      const r = await api('/api/sp/fig/colour', { name: FG.name, i: FG.i, x: d.x0, y: d.y0 });
      FG.colour = r.colour; FG.seed = r.seed; FG.trace = null; $('#sp-fig-use').disabled = true;
      $('#sp-fig-swatch').style.background = 'rgb(' + r.colour.join(',') + ')';
      fgStatus('the curve’s colour taken: Trace');
    } catch (e) { fgStatus(e.message, true); }
    fgDraw();
  });
  window.addEventListener('resize', () => { if (!$('#sp-fig').classList.contains('hidden')) fgDraw(); });
  window.addEventListener('keydown', ev => {                 // Escape hides the panel (its state is kept) — not from inside one of its fields
    const t = ev.target || {};
    if (ev.key === 'Escape' && !$('#sp-fig').classList.contains('hidden') && !((t.tagName === 'INPUT' || t.tagName === 'SELECT') && $('#sp-fig').contains(t))) $('#sp-fig').classList.add('hidden');
  });
}
async function fgUpload(f) {
  const fd = new FormData(); fd.append('file', f);
  fgStatus('opening ' + f.name + '…');
  try {
    const r = await fetch('/api/sp/fig/upload', { method: 'POST', body: fd });
    const j = await r.json().catch(() => null);
    if (!r.ok || !j || !j.ok) throw new Error((j && j.error) || ('the server answered ' + r.status));
    await fgSources(j.name);
  } catch (e) { fgStatus(e.message, true); }
}

// ---- start ---------------------------------------------------------------------
loadPrefs(); showBaselineRows(); wire();
(async () => {
  const q = new URLSearchParams(location.search);
  try {
    await loadState(null);
    recallChem(); recallPick();
    if (q.get('cif') && SP.state.cifs.includes(q.get('cif'))) $('#sp-cif').value = q.get('cif');
    if (q.get('ms') && SP.state.manuscripts.includes(q.get('ms'))) $('#sp-ms').value = q.get('ms');
    const pick = q.get('file') || (SP.state.files.length === 1 ? SP.state.files[0].name : '');
    if (pick && SP.state.files.some(f => f.name === pick)) { $('#sp-file').value = pick; await chooseFile(pick); } else draw();
    loadLib();
  } catch (e) { status(e.message, true); draw(); }
})();

// The server exits a while after its last window closes. This window keeps it alive like the main one (a heartbeat),
// and says it is closing ONLY when the main window is already gone: closing the spectrum window beside an open main
// window must never start the server's shutdown.
setInterval(() => fetch('/api/ping').catch(() => {}), 15000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) fetch('/api/ping').catch(() => {}); });
window.addEventListener('pagehide', () => { try { if (!window.opener || window.opener.closed) navigator.sendBeacon('/api/closing'); } catch (_) {} });
