// The spectrum window (/spectra) — a Raman / infrared spectrum imported, cleaned, baselined and fitted.
// Every fitted number comes from the server (pxrd_review.spectrum, the same code `pxrd spectrum` runs); this page draws,
// lets the bands be edited, and sends back file NAMES and options — never a path. Nothing is written until Export.
'use strict';

const $ = sel => document.querySelector(sel);
const enc = encodeURIComponent;
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
// A region = one fitted stretch: {lo, hi, comps, fit, dirty, hist, redo, trials, prevBic}.
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
  layers: { raw: false, comps: true, ticks: true, stated: true, peaks: false, reverse: false, d2: false },
  busy: 0,
};
const LS = 'pxrd-sp2';                                    // 2: the defaults changed (smallest band 3 %) — remembered values start afresh
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
    cif: $('#sp-cif').value, ms: $('#sp-ms').value,
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
  fill($('#sp-cif'), s.cifs, 'none'); fill($('#sp-ms'), s.manuscripts, 'none');
  $('#sp-cif').value = keepCif; $('#sp-ms').value = keepMs;
  const pre = $('#sp-presets'); pre.textContent = '';
  for (const r of s.regions) pre.append(el('button', { onclick: () => setRegion(r.lo, r.hi, true) }, r.name + ' ' + r.lo + '–' + r.hi));
  pre.append(el('button', { onclick: () => { if (SP.d) { SP.view = [SP.d.x[0], SP.d.x[SP.d.x.length - 1]]; draw(); } } }, 'whole'));
  listOutputs(s.outputs);
  if (pick && s.files.some(f => f.name === pick)) { fsel.value = pick; await chooseFile(pick); }
}

async function chooseFile(name) {
  SP.file = name; SP.series = 0; SP.d = null; SP.d2 = null; SP.regions = []; SP.cur = -1; SP.sel = -1; SP.anchors = [];
  const ssel = $('#sp-series'); ssel.textContent = '';
  if (!name) { draw(); renderResult(); return; }
  try {
    const r = await api('/api/sp/series?name=' + enc(name));
    for (const t of r.series) ssel.append(el('option', { value: t.i }, t.name.replace(name + ' | ', '') + ' — ' + t.n + ' points' + (t.offset_copy ? ' (an offset copy)' : '')));
    SP.seriesList = r.series;
    const guess = r.series[0].kind;
    if (!$('#sp-kind').value && guess) setReverse(guess.startsWith('ir'));
    await process(true);
  } catch (e) { status(e.message, true); SP.d = null; draw(); renderResult(); }
}

function setReverse(on) {
  SP.layers.reverse = on;
  const cb = document.querySelector('#sp-layers [data-layer=reverse]'); if (cb) cb.checked = on;
}

async function process(resetView) {
  if (!SP.file) return;
  try {
    status('reading…');
    const d = SP.d = await api('/api/sp/process', opts());
    SP.d2 = null;
    if (resetView || !SP.view) SP.view = [d.x[0], d.x[d.x.length - 1]];
    status(d.x.length + ' points, ' + d.x[0] + '–' + d.x[d.x.length - 1] + ' cm⁻¹; noise ' + fmt(d.noise) + (d.kind ? '; ' + d.kind.replace('ir-', 'infrared, ') : ''));
    $('#sp-spikes').textContent = $('#sp-despike').checked ? (d.spikes.length ? d.spikes.length + ' removed: ' + d.spikes.slice(0, 8).map(s => Math.round(s[0])).join(', ') + (d.spikes.length > 8 ? ' …' : '') : 'none found') : '';
    const n = $('#sp-notes'); n.textContent = '';
    for (const t of d.notes) n.append(el('div', { class: 'note', title: t }, t));
    // a changed spectrum under fitted regions: their fits are of the spectrum before — to be fitted again
    if (!resetView) for (const r of SP.regions) if (r.comps.length) r.dirty = true;
    draw(); renderResult(); savePrefs();
    if (SP.layers.d2) loadD2();
  } catch (e) { status(e.message, true); }
}

async function loadD2() {
  if (!SP.d || !SP.layers.d2) return;
  const key = JSON.stringify([opts(), num('sp-d2w')]);
  if (SP.d2 && SP.d2.key === key) { draw(); return; }
  try {
    const r = await api('/api/sp/d2', Object.assign(opts(), { lo: SP.d.x[0], hi: SP.d.x[SP.d.x.length - 1], width: num('sp-d2w') || 25 }));
    SP.d2 = { x: r.x, d2: r.d2, key }; draw();
  } catch (e) { status(e.message, true); }
}

// ---- the plot ----------------------------------------------------------------
const M = { l: 58, r: 12, t: 16, b: 30, res: 64 };       // margins; res = the residual strip's height
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
  const ph = H - M.t - M.b - (hasRes ? M.res : 0), pw = W - M.l - M.r;
  const [vx0, vx1] = SP.view;
  const [i0, i1] = range(indexOf(vx0) - 1, indexOf(vx1) + 1);
  const ys = SP.layers.raw ? d.cleaned : d.y;
  let ymin = Infinity, ymax = -Infinity;
  for (let i = i0; i <= i1; i++) { const v = ys[i]; if (v < ymin) ymin = v; if (v > ymax) ymax = v; }
  if (!(ymax > ymin)) { ymax = ymin + 1; }
  if (!SP.layers.raw) ymin = Math.min(ymin, 0);
  const padY = 0.06 * (ymax - ymin); ymax += padY; ymin -= SP.layers.raw ? padY : 0.02 * (ymax - ymin);
  const rev = SP.layers.reverse;
  const X = v => M.l + (rev ? (vx1 - v) : (v - vx0)) / (vx1 - vx0) * pw;
  const Xinv = px => rev ? vx1 - (px - M.l) / pw * (vx1 - vx0) : vx0 + (px - M.l) / pw * (vx1 - vx0);
  const Y = v => M.t + (ymax - v) / (ymax - ymin) * ph;
  const Yinv = py => ymax - (py - M.t) / ph * (ymax - ymin);
  G = { X, Xinv, Y, Yinv, W, H, pw, ph, ymin, ymax };
  const svg = sv('svg', { viewBox: '0 0 ' + W + ' ' + H, preserveAspectRatio: 'none' });
  svg.append(sv('defs', null, sv('clipPath', { id: 'sp-clip' }, sv('rect', { x: M.l, y: M.t - 4, width: pw, height: ph + 4 + (hasRes ? M.res : 0) }))));
  const g = sv('g', { 'clip-path': 'url(#sp-clip)' }); svg.append(g);

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
      e.addEventListener('mousedown', ev => { if (ev.button !== 0) return; ev.stopPropagation(); ev.preventDefault(); r.edgeBefore = snapshot(r); drag = { kind: 'edge', reg: r, side, lo0: r.lo, hi0: r.hi, moved: false }; });
      edges.append(e);
    }
  });
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
    g.append(sv('path', { class: 'data', d: path(d.x, d.cleaned, i0, i1) }));
    if ($('#sp-baseline').value !== 'none') g.append(sv('path', { class: 'base', d: path(d.x, d.baseline, i0, i1) }));
    for (const s of d.spikes) g.append(sv('circle', { class: 'spike', cx: X(s[0]), cy: M.t + 2, r: 2.5 }, sv('title', null, 'a cosmic-ray event removed at ' + Math.round(s[0]) + ' cm⁻¹')));
  } else {
    g.append(sv('path', { class: 'data', d: path(d.x, d.y, i0, i1) }));
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
    if (SP.layers.comps) r.comps.forEach((b, j) => {
      const sel = k === SP.cur && j === SP.sel;
      const vals = c.x.map(v => profile(b, v) + bl(v));
      const p = sv('path', { class: 'comp' + (sel ? ' sel' : '') + (c.draft ? ' draft' : ''), d: path(c.x, vals, 0, c.x.length - 1) });
      p.addEventListener('mousedown', ev => { if (SP.mode === 'pan' && !ev.shiftKey) { ev.stopPropagation(); select(k, j); } });
      g.append(p);
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
    g.append(sv('path', { class: 'resid', d: path(c.x, c.residual, 0, c.x.length - 1, RY) }));
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
  svg.append(sv('rect', { id: 'sp-sel', class: 'sel', x: 0, y: M.t, width: 0, height: ph }));
  g.append(edges);
  g.append(handles);                                        // on top: a handle is never under a curve
  host.append(svg);
}

// ---- the pointer ---------------------------------------------------------------
function plotX(ev) { const r = $('#sp-plot').getBoundingClientRect(); return ev.clientX - r.left; }
function plotY(ev) { const r = $('#sp-plot').getBoundingClientRect(); return ev.clientY - r.top; }
let drag = null;

function readout(ev) {
  if (!G || !SP.d) return;
  const x = G.Xinv(plotX(ev)), i = Math.min(SP.d.x.length - 1, Math.max(0, indexOf(x)));
  const ws = [];
  for (const [name, e] of Object.entries(SP.state.windows || {})) { const w = e.any; if (w && x >= w.p5 && x <= w.p95) ws.push(name); }
  $('#sp-readout').textContent = x.toFixed(1) + ' cm⁻¹   ' + fmt((SP.layers.raw ? SP.d.cleaned : SP.d.y)[i]) + (ws.length ? '   — where papers place: ' + ws.slice(0, 5).join(', ') : '');
}

function setRegion(lo, hi, zoom) {
  if (!SP.d) return;
  [lo, hi] = [Math.round(Math.min(lo, hi)), Math.round(Math.max(lo, hi))];
  let k = SP.regions.findIndex(r => Math.abs(r.lo - lo) < 1 && Math.abs(r.hi - hi) < 1);
  if (k < 0) {
    // not a region as it stands: the bounds of the fitted region they overlap are being changed — the current one first
    const over = r => r.comps.length && r.lo < hi && r.hi > lo;
    const cur = SP.regions[SP.cur];
    const target = cur && over(cur) ? cur : SP.regions.filter(over).sort((a, b) => (Math.min(b.hi, hi) - Math.max(b.lo, lo)) - (Math.min(a.hi, hi) - Math.max(a.lo, lo)))[0];
    if (target) { SP.cur = SP.regions.indexOf(target); resizeRegion(target, lo, hi); if (zoom) zoomTo(target.lo, target.hi); return; }
  }
  $('#sp-lo').value = lo; $('#sp-hi').value = hi;
  if (k !== SP.cur) SP.sel = -1;
  SP.cur = k;
  if (zoom) zoomTo(lo, hi);
  draw(); renderResult();
}
function zoomTo(lo, hi) { const pad = 0.15 * (hi - lo); SP.view = [Math.max(SP.d.x[0], lo - pad), Math.min(SP.d.x[SP.d.x.length - 1], hi + pad)]; draw(); }
// A fitted region given new bounds: its bands stay (those now outside it go — undo brings them back), it stops at its
// neighbours, and the fit is done again over the new stretch.
function resizeRegion(reg, lo, hi) {
  const k = SP.regions.indexOf(reg), prev = SP.regions[k - 1], next = SP.regions[k + 1];
  lo = Math.max(lo, Math.ceil(SP.d.x[0]), prev ? prev.hi : -Infinity); hi = Math.min(hi, Math.floor(SP.d.x[SP.d.x.length - 1]), next ? next.lo : Infinity);
  if (!(hi - lo >= 10)) { $('#sp-lo').value = reg.lo; $('#sp-hi').value = reg.hi; status('a region is at least 10 cm⁻¹ wide and does not cross its neighbour', true); draw(); return; }
  if (lo === reg.lo && hi === reg.hi) { $('#sp-lo').value = lo; $('#sp-hi').value = hi; draw(); return; }
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
  SP.cur = k; SP.sel = j; draw(); renderResult();
}

// a band's handle: ● moves it and sets its height, ◆ sets its width
function startHandle(ev, k, j, what) {
  if (ev.button !== 0) return;
  ev.stopPropagation(); ev.preventDefault();
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
    } else {
      const sel = $('#sp-sel'); if (!sel) return;
      sel.setAttribute('x', Math.min(drag.px, x)); sel.setAttribute('width', Math.abs(x - drag.px)); drag.moved = Math.abs(x - drag.px) > 3;
    }
  });
  host.addEventListener('mousedown', ev => {
    if (!G || ev.button !== 0) return;
    const kind = ev.shiftKey || SP.mode === 'region' ? 'region' : SP.mode === 'pan' ? 'pan' : 'click';
    drag = { kind, px: plotX(ev), view: SP.view.slice(), G };
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
      r.lo = d.lo0; r.hi = d.hi0;                            // back to where it was, then moved properly (neighbours, bands outside, undo, refit)
      if (d.moved) resizeRegion(r, lo, hi); else { r.edgeBefore = null; draw(); }
      return;
    }
    if (d.kind === 'region' && d.moved) { setRegion(d.G.Xinv(d.px), d.G.Xinv(x), false); return; }
    if (d.kind === 'click' || (d.kind === 'pan' && !d.moved && SP.mode !== 'pan')) clickAt(G.Xinv(x), plotY(ev));
    else if (d.kind === 'pan' && !d.moved) {                            // a plain click in move mode: the region under it
      const v = G.Xinv(x), k = SP.regions.findIndex(r => v >= r.lo && v <= r.hi);
      if (k >= 0) { if (k !== SP.cur) SP.sel = -1; setRegion(SP.regions[k].lo, SP.regions[k].hi, false); }
    }
  });
  host.addEventListener('wheel', ev => {
    if (!G || !SP.d) return;
    ev.preventDefault();
    const x = G.Xinv(plotX(ev)), f = ev.deltaY > 0 ? 1.25 : 0.8;
    const lo = SP.d.x[0], hi = SP.d.x[SP.d.x.length - 1];
    const a = x - (x - SP.view[0]) * f, b = x + (SP.view[1] - x) * f;
    if (b - a < 4) return;
    SP.view = [Math.max(lo, a), Math.min(hi, b)]; draw();
  }, { passive: false });
  host.addEventListener('dblclick', () => { if (SP.d) { SP.view = [SP.d.x[0], SP.d.x[SP.d.x.length - 1]]; draw(); } });
  host.addEventListener('dragover', ev => { ev.preventDefault(); host.classList.add('drop'); });
  host.addEventListener('dragleave', () => host.classList.remove('drop'));
  host.addEventListener('drop', ev => { ev.preventDefault(); host.classList.remove('drop'); if (ev.dataTransfer.files.length) upload(ev.dataTransfer.files[0]); });
  new ResizeObserver(() => draw()).observe(host);
  // the selected band from the keyboard: Delete removes it, the arrows nudge it; ⌘Z / Ctrl-Z undoes
  window.addEventListener('keydown', ev => {
    if (/^(INPUT|SELECT|TEXTAREA)$/.test((ev.target && ev.target.tagName) || '')) return;
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
    if (!reg) {                                             // no region there yet: one around the click
      const lo = Math.max(SP.d.x[0], x - 60), hi = Math.min(SP.d.x[SP.d.x.length - 1], x + 60);
      $('#sp-lo').value = Math.round(lo); $('#sp-hi').value = Math.round(hi); reg = currentRegion(true);
    } else { $('#sp-lo').value = reg.lo; $('#sp-hi').value = reg.hi; SP.cur = SP.regions.indexOf(reg); }
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
const snapshot = r => JSON.stringify({ lo: r.lo, hi: r.hi, comps: r.comps.map(bare) });
function restore(r, snap) {                                  // a snapshot back: the bands and the region's bounds
  const s = JSON.parse(snap);
  r.comps = Array.isArray(s) ? s : s.comps;
  if (!Array.isArray(s)) { r.lo = s.lo; r.hi = s.hi; if (r === SP.regions[SP.cur]) { $('#sp-lo').value = r.lo; $('#sp-hi').value = r.hi; } }
}
function mutate(reg, fn) {                                  // every change to the bands goes through here: undo, preview, refit
  reg.hist.push(snapshot(reg)); if (reg.hist.length > 60) reg.hist.shift(); reg.redo = [];
  fn();
  changed(reg);
}
function changed(reg) {
  reg.dirty = true;
  if (SP.sel >= reg.comps.length) SP.sel = reg.comps.length - 1;
  if (!reg.comps.length) { reg.fit = null; reg.dirty = false; }
  draw(); renderResult();                                   // the change itself at once (dashed), the fit when it comes
  if ($('#sp-live').checked && reg.comps.length) fitRegion(reg, reg.comps);
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
const twin = (reg, j) => { const a = reg.comps[j], b = reg.comps[j + 1]; return !!(a && b && Math.abs(b.pos - a.pos) < 0.25 * (a.fwhm + b.fwhm)); };
function mergeBands(reg, j) {                                // two bands the data cannot tell apart, as one
  mutate(reg, () => {
    const a = reg.comps[j], b = reg.comps[j + 1], h = a.height + b.height || 1;
    reg.comps.splice(j, 2, Object.assign(bare(a.height >= b.height ? a : b), { pos: (a.pos * a.height + b.pos * b.height) / h || 0.5 * (a.pos + b.pos), height: Math.max(a.height, b.height), fwhm: Math.max(a.fwhm, b.fwhm) }));
    SP.sel = j;
  });
}
function undo() {
  const r = SP.regions[SP.cur]; if (!r || !r.hist.length) { status('nothing to undo in this region'); return; }
  r.redo.push(snapshot(r)); restore(r, r.hist.pop()); changed(r);
}
function redo() {
  const r = SP.regions[SP.cur]; if (!r || !r.redo.length) return;
  r.hist.push(snapshot(r)); restore(r, r.redo.pop()); changed(r);
}

// ---- fitting -------------------------------------------------------------------
let fitSeq = 0;
async function fitRegion(reg, comps, extra) {
  const body = Object.assign(fitOpts(reg), extra || {});
  if (comps && comps.length) body.comps = comps.map(bare);
  else {
    const n = num('sp-n'); if (n && !body.n) body.n = n;
    if ($('#sp-seed').checked && SP.d) body.seeds = SP.d.ticks.filter(t => t.pos >= reg.lo && t.pos <= reg.hi);
  }
  const seq = ++fitSeq;
  try {
    status('fitting ' + reg.lo + '–' + reg.hi + ' cm⁻¹…');
    const r = await api('/api/sp/fit', body);
    if (seq !== fitSeq) return;                             // a later change is already being fitted: this answer is stale
    if (!(comps && comps.length) || (extra && extra.add)) { reg.hist.push(snapshot(reg)); reg.redo = []; }
    reg.prevBic = reg.fit && reg.fit.lo === r.fit.lo && reg.fit.n === r.fit.n ? reg.fit.bic : null;
    const selPos = SP.sel >= 0 && reg.comps[SP.sel] ? reg.comps[SP.sel].pos : null;
    reg.fit = r.fit; reg.comps = r.fit.comps.map(bare); reg.dirty = false;
    reg.trials = r.trials;                                  // the models an automatic fit or '+ band' tried; none for a plain refit
    if (selPos != null && reg === SP.regions[SP.cur]) {      // the selected band, wherever the fit left it
      let best = -1; reg.comps.forEach((c, j) => { if (best < 0 || Math.abs(c.pos - selPos) < Math.abs(reg.comps[best].pos - selPos)) best = j; }); SP.sel = best;
    }
    reg.local = body.local; reg.share_width = body.share_width; reg.share_eta = body.share_eta;
    status(r.fit.comps.length + ' band' + (r.fit.comps.length === 1 ? '' : 's') + ' fitted, ' + reg.lo + '–' + reg.hi + ' cm⁻¹' + (r.fit.converged ? '' : ' — not converged'));
  } catch (e) { if (seq === fitSeq) status(e.message, true); }
  draw(); renderResult();
}

function renderResult(light) {
  const tb = $('#sp-table'), st = $('#sp-stats'), wn = $('#sp-warnings'), cp = $('#sp-compare');
  const reg = SP.cur >= 0 ? SP.regions[SP.cur] : null;
  if (light && reg) {                                       // during a drag: the numbers of the dragged band only
    const row = tb.querySelectorAll('tr')[SP.sel + 1], b = reg.comps[SP.sel];
    if (row && b) { const inp = row.querySelectorAll('input[type=number]'); if (inp.length >= 3) { inp[0].value = b.pos.toFixed(1); inp[1].value = b.fwhm.toFixed(1); inp[2].value = +b.height.toPrecision(5); } }
    return;
  }
  tb.textContent = ''; st.textContent = ''; wn.textContent = ''; cp.textContent = '';
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
  const info = f && !reg.dirty ? f.comps : [];
  const total = info.reduce((s, c) => s + (c.area || 0), 0) || 1;
  tb.append(el('tr', null, ...['position (cm⁻¹)', 'FWHM', 'height', 'area %', 'shape', 'hold', 'where papers place it', 'distance', ''].map(h => el('th', null, h))));
  reg.comps.forEach((c, k) => {
    const fc = info[k] || {};
    const cell = (key, digits) => {
      const inp = el('input', { type: 'number', step: key === 'height' ? 'any' : '0.1', value: key === 'height' ? +c[key].toPrecision(5) : c[key].toFixed(digits) });
      inp.addEventListener('change', () => { const v = parseFloat(inp.value); if (Number.isFinite(v) && (key === 'pos' || v > 0 || key === 'height')) mutate(reg, () => { reg.comps[k][key] = v; }); });
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
      el('td', { class: 'w' }, (fc.suggest || []).join(', ')), el('td', { class: 'w' }, fc.distance || ''),
      el('td', null, twin(reg, k) ? el('button', { class: 'lim', title: 'this band and the next are closer than half their width — the data cannot tell them apart: make them one band, and refit', onclick: ev => { ev.stopPropagation(); mergeBands(reg, k); } }, 'merge ↓') : null, ' ',
        el('button', { title: 'split this band into two narrower ones side by side, and refit', onclick: ev => { ev.stopPropagation(); splitBand(reg, k); } }, 'split'), ' ',
        el('button', { title: 'remove this band (Delete, when it is selected)', onclick: ev => { ev.stopPropagation(); removeBand(reg, k); } }, '×')));
    tr.addEventListener('mousedown', ev => { if (!/^(INPUT|SELECT|BUTTON|LABEL|OPTION)$/.test(ev.target.tagName) && SP.sel !== k) { SP.sel = k; draw(); renderResult(); } });
    tb.append(tr);
  });
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
  if (SP.regions.some(r => r.dirty && r.comps.length)) { status('a region was changed since its fit: press ‘Fit these’ first, so the table written is a fit', true); return; }
  // the bands as they stand are written — no fitting on the way out: the table is the fit on the screen
  const regions = SP.regions.filter(r => r.fit && r.comps.length).map(r => ({ lo: r.lo, hi: r.hi, comps: r.comps.map(bare), local: r.local || $('#sp-local').value, share_width: !!r.share_width,
    share_eta: !!r.share_eta, max_fwhm: num('sp-wmax'), min_fwhm: num('sp-wmin'), converged: r.fit.converged }));
  if (!regions.length) { status('nothing fitted yet: fit a region first', true); return; }
  try {
    const r = await api('/api/sp/export', Object.assign(opts(), { regions, fmt: fmt_ }));
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
async function applySession(s, label) {
  if (!s || !Array.isArray(s.fits) || !s.options) { status((label || 'that file') + ' is not a session written by this window', true); return; }
  const o = s.options, file = o.name || s.file;
  if (!SP.state.files.some(f => f.name === file)) {
    SP.pending = s;
    status('this session is of ‘' + file + '’, which is not in the folder: open that spectrum (Open file…) and the session follows', true);
    return;
  }
  SP.pending = null;
  const set = (id, v) => { if (v != null && $('#' + id)) $('#' + id).value = v; };
  set('sp-kind', o.kind || ''); set('sp-threshold', o.threshold); set('sp-resolution', o.resolution == null ? '' : o.resolution); set('sp-baseline', o.baseline || 'none');
  set('sp-lam', o.lam ? +Math.log10(o.lam).toFixed(2) : null); set('sp-p', o.p); set('sp-width', o.width);
  $('#sp-despike').checked = !!o.despike; showBaselineRows();
  if (o.cif && SP.state.cifs.includes(o.cif)) $('#sp-cif').value = o.cif;
  if (o.ms && SP.state.manuscripts.includes(o.ms)) $('#sp-ms').value = o.ms;
  $('#sp-file').value = file;
  SP.file = file; SP.series = o.series || 0; SP.d = null; SP.d2 = null; SP.regions = []; SP.cur = -1; SP.sel = -1; SP.anchors = (o.anchors || []).slice();
  try {
    const r = await api('/api/sp/series?name=' + enc(file));
    const ssel = $('#sp-series'); ssel.textContent = '';
    for (const t of r.series) ssel.append(el('option', { value: t.i }, t.name.replace(file + ' | ', '') + ' — ' + t.n + ' points'));
    SP.seriesList = r.series; ssel.value = String(SP.series);
  } catch (e) { status(e.message, true); return; }
  await process(true);
  if (!SP.d) return;
  if ((o.kind || SP.d.kind || '').startsWith('ir')) setReverse(true);
  s.fits.forEach((f, k) => {
    const rg = (o.regions || [])[k] || {};
    const lo = Math.round(rg.lo != null ? rg.lo : f.lo), hi = Math.round(rg.hi != null ? rg.hi : f.hi);
    SP.regions.push({ lo, hi, comps: f.components.map(bare), fit: null, dirty: true, hist: [], redo: [], trials: [], local: rg.local || (f.baseline && f.baseline[1] ? 'linear' : 'const'),
      share_width: !!rg.share_width, share_eta: !!rg.share_eta });
  });
  // each region as it was written: its curve and statistics, with no fitting
  for (const reg of SP.regions) {
    try {
      const r = await api('/api/sp/fit', Object.assign(opts(), { lo: reg.lo, hi: reg.hi, comps: reg.comps, local: reg.local, share_width: reg.share_width, share_eta: reg.share_eta, evaluate: true, min_share: num('sp-share') }));
      reg.fit = r.fit; reg.comps = r.fit.comps.map(bare); reg.dirty = false;
    } catch (e) { status(e.message, true); }
  }
  if (SP.regions.length) {
    const r0 = SP.regions[0]; SP.cur = 0; $('#sp-lo').value = r0.lo; $('#sp-hi').value = r0.hi; $('#sp-local').value = r0.local;
    $('#sp-share-w').checked = r0.share_width; $('#sp-share-eta').checked = r0.share_eta;
    const pad = 0.1 * (r0.hi - r0.lo); SP.view = [Math.max(SP.d.x[0], r0.lo - pad), Math.min(SP.d.x[SP.d.x.length - 1], r0.hi + pad)];
  }
  status('session reopened: ' + SP.regions.length + ' region' + (SP.regions.length === 1 ? '' : 's') + ', ' + SP.regions.reduce((n, r) => n + r.comps.length, 0) + ' bands, as they were written');
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
  $('#sp-series').addEventListener('change', e => { SP.series = parseInt(e.target.value, 10) || 0; SP.regions = []; SP.cur = -1; SP.sel = -1; const t = SP.seriesList[SP.series]; if (t && !$('#sp-kind').value) setReverse((t.kind || '').startsWith('ir')); process(true); });
  $('#sp-kind').addEventListener('change', e => { if (e.target.value) setReverse(e.target.value.startsWith('ir')); process(false); });
  $('#sp-open').addEventListener('click', () => $('#sp-upload').click());
  $('#sp-upload').addEventListener('change', e => { if (e.target.files.length) upload(e.target.files[0]); e.target.value = ''; });
  for (const id of ['sp-despike', 'sp-threshold', 'sp-resolution', 'sp-lam', 'sp-p', 'sp-width', 'sp-cif', 'sp-ms'])
    $('#' + id).addEventListener('change', () => process(false));
  $('#sp-baseline').addEventListener('change', () => { showBaselineRows(); process(false); });
  $('#sp-anchors-clear').addEventListener('click', () => { SP.anchors = []; process(false); });
  for (const id of ['sp-lo', 'sp-hi']) $('#' + id).addEventListener('change', () => { const lo = num('sp-lo'), hi = num('sp-hi'); if (lo != null && hi != null && hi > lo) setRegion(lo, hi, false); });
  // how the region is fitted: a change refits the bands there are (when 'refit as I edit' is on)
  for (const id of ['sp-local', 'sp-share-w', 'sp-share-eta', 'sp-wmax', 'sp-wmin']) $('#' + id).addEventListener('change', () => { savePrefs(); const r = SP.regions[SP.cur]; if (r && r.comps.length) changed(r); });
  for (const id of ['sp-shape', 'sp-maxn', 'sp-share', 'sp-live', 'sp-refine']) $('#' + id).addEventListener('change', savePrefs);
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
    const r = currentRegion(false); if (!r || !r.comps.length) return;
    const area = c => c.height * c.fwhm; let j = 0; r.comps.forEach((c, k) => { if (area(c) < area(r.comps[j])) j = k; });
    removeBand(r, j);
  });
  $('#sp-undo').addEventListener('click', undo); $('#sp-redo').addEventListener('click', redo);
  $('#sp-clear').addEventListener('click', () => { if (SP.cur >= 0) { SP.regions.splice(SP.cur, 1); SP.cur = -1; SP.sel = -1; draw(); renderResult(); } });
  for (const b of document.querySelectorAll('#sp-mode button')) b.addEventListener('click', () => {
    SP.mode = b.getAttribute('data-m');
    for (const o of document.querySelectorAll('#sp-mode button')) o.classList.toggle('on', o === b);
  });
  for (const cb of document.querySelectorAll('#sp-layers input[data-layer]')) {
    const k = cb.getAttribute('data-layer'); cb.checked = !!SP.layers[k];
    cb.addEventListener('change', () => { SP.layers[k] = cb.checked; savePrefs(); if (k === 'd2' && cb.checked) loadD2(); else draw(); });
  }
  for (const b of document.querySelectorAll('[data-fmt]')) b.addEventListener('click', () => exportAll(b.getAttribute('data-fmt')));
  wirePlot(); wireSplit();
}

// ---- start ---------------------------------------------------------------------
loadPrefs(); showBaselineRows(); wire();
(async () => {
  const q = new URLSearchParams(location.search);
  try {
    await loadState(null);
    if (q.get('cif') && SP.state.cifs.includes(q.get('cif'))) $('#sp-cif').value = q.get('cif');
    if (q.get('ms') && SP.state.manuscripts.includes(q.get('ms'))) $('#sp-ms').value = q.get('ms');
    const pick = q.get('file') || (SP.state.files.length === 1 ? SP.state.files[0].name : '');
    if (pick && SP.state.files.some(f => f.name === pick)) { $('#sp-file').value = pick; await chooseFile(pick); } else draw();
  } catch (e) { status(e.message, true); draw(); }
})();

// The server exits a while after its last window closes. This window keeps it alive like the main one (a heartbeat),
// and says it is closing ONLY when the main window is already gone: closing the spectrum window beside an open main
// window must never start the server's shutdown.
setInterval(() => fetch('/api/ping').catch(() => {}), 15000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) fetch('/api/ping').catch(() => {}); });
window.addEventListener('pagehide', () => { try { if (!window.opener || window.opener.closed) navigator.sendBeacon('/api/closing'); } catch (_) {} });
