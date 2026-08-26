'use strict';
// Manuscript mode — front end. A second mode in the same page: one paper .docx at a time, its
// citations checked against its own reference list (refs_check), with triage saved to
// review_out/ms_triage.json and 'Run' writing the annotated COPY. Reuses app.js helpers
// (el, $, esc, badgeEl, showCmtPopover, CFG) and the shared folder panel; never edits a docx.

window.MODE = 'entries';
const MSS = {
  files: [], key: null, a: null, t: null, others: [], companions: [],
  view: 'findings', which: 'annotated', pollTimer: null, saveTimer: null, pendingSave: null,
  docxHtml: {},           // key|which -> rendered HTML
  lookIdx: {},            // fkey -> which target was shown last (a pair has two)
};
const MS_KIND = {
  orphan:  { sev: 'flag',  code: 'CITED, NOT LISTED', title: 'Cited but not in the reference list' },
  uncited: { sev: 'check', code: 'LISTED, NOT CITED', title: 'Listed but never cited' },
  pair:    { sev: 'flag',  code: 'MISMATCH',          title: 'Probably the same reference — year or spelling differs' },
  form:    { sev: 'check', code: 'FORM',              title: 'Citation and entry disagree in form' },
};

// ---- mode toggle -------------------------------------------------------------
function setMode(mode, opts) {
  window.MODE = mode;
  clearTimeout(MSS.pollTimer);                       // the manuscript list stops polling outside its mode
  const ms = mode !== 'entries', tb = mode === 'tables';
  document.querySelectorAll('#mode button').forEach(b => b.classList.toggle('on', b.dataset.mode === mode));
  $('#app').classList.toggle('hidden', ms);
  $('#ms-app').classList.toggle('hidden', !ms || tb);
  $('#tb-app').classList.toggle('hidden', !tb);
  // entries-only controls
  for (const id of ['#rerun-all', '#export', '#open-log']) { const e = $(id); if (e) e.classList.toggle('hidden', ms); }
  const chip = $('#mindat-chip'); if (chip) { if (ms) chip.classList.add('hidden'); else if (chip.textContent) chip.classList.remove('hidden'); }
  document.querySelectorAll('.ms-only').forEach(e => e.classList.toggle('hidden', mode !== 'manuscript'));
  try { localStorage.setItem('pxrd-mode', mode); } catch (_) {}
  if (tb) tbLoad(); else if (ms) msLoad(); else loadEntries();
  if (!(opts && opts.quiet)) { $('#folderpanel').classList.add('hidden'); }
}
document.querySelectorAll('#mode button').forEach(b => b.addEventListener('click', () => setMode(b.dataset.mode)));

// ---- dashboard --------------------------------------------------------------
async function msLoad() {
  clearTimeout(MSS.pollTimer);
  let r;
  try { r = await fetch('/api/ms/state').then(x => x.json()); } catch (_) { return; }
  const parts = (r.folder || '').split('/').filter(Boolean);
  $('#folder').textContent = r.folder ? ((parts.length > 2 ? '…/' : '') + parts.slice(-2).join('/')) : '(no manuscript folder — click to choose)';
  $('#folder-ctl').title = (r.folder || '') + '  — click to change folder';
  $('#folder').dataset.path = r.folder || '';
  MSS.files = r.files || []; MSS.ncifs = (r.cifs || []).length;
  msRenderList();
  if (r.pending > 0 && window.MODE === 'manuscript') MSS.pollTimer = setTimeout(msLoad, 1000);
}

function msSummaryBadges(f) {
  const s = f.summary || {}; const out = [];
  if (f.error) return [{ level: 'danger', label: 'error' }];
  if (f.no_list) return [{ level: 'info', label: 'no reference list' }];
  if (s.orphan) out.push({ level: 'danger', label: `${s.orphan} not listed` });
  if (s.pair) out.push({ level: 'danger', label: `${s.pair} mismatch` });
  if (s.uncited) out.push({ level: 'warn', label: `${s.uncited} uncited` });
  if (s.form) out.push({ level: 'warn', label: `${s.form} form` });
  if (!out.length) out.push({ level: 'ok', label: 'clean' });
  if (f.has_annotated) out.push({ level: 'fix', label: 'annotated copy' });
  return out;
}
const msHasFindings = f => f.summary && Object.values(f.summary).some(n => n > 0);
function msMatchesView(f) {
  if (MSS.view === 'all') return true;
  if (MSS.view === 'findings') return f.pending || msHasFindings(f) || f.error;
  if (MSS.view === 'clean') return !f.pending && !msHasFindings(f) && !f.error;
  return true;
}
function msVisible() {
  const q = $('#ms-filter').value.toLowerCase();
  return MSS.files.filter(f => msMatchesView(f) && (!q || f.name.toLowerCase().includes(q)));
}
function msRenderList() {
  const ul = $('#ms-list'); ul.innerHTML = '';
  const vis = msVisible();
  for (const f of vis) {
    const li = el('li', { class: (f.key === MSS.key ? 'sel ' : '') + (f.reviewed ? 'reviewed' : ''), onclick: () => msOpen(f.key) },
      el('div', { class: 'row1' }, f.reviewed ? el('span', { class: 'reviewed-tick' }, '✓') : null,
        el('span', { class: 'nm' }, f.name)),
      f.pending ? el('div', { class: 'row2' }, el('span', { class: 'pending muted' }, 'analyzing…'))
                : el('div', { class: 'row2' }, ...msSummaryBadges(f).map(badgeEl)));
    ul.append(li);
  }
  const pend = MSS.files.filter(f => f.pending).length;
  const withF = MSS.files.filter(msHasFindings).length;
  $('#ms-counts').textContent = MSS.files.length
    ? `${vis.length} shown · ${withF}/${MSS.files.length} with findings` + (pend ? ` · analyzing ${pend}…` : '')
    : (MSS.ncifs ? `no manuscripts here — ${MSS.ncifs} .cif (switch to Tables)` : 'no manuscripts in this folder');
}
document.querySelectorAll('#ms-views button').forEach(b => b.addEventListener('click', () => {
  MSS.view = b.dataset.view;
  document.querySelectorAll('#ms-views button').forEach(x => x.classList.toggle('on', x === b));
  msRenderList();
}));
$('#ms-filter').addEventListener('input', msRenderList);

// ---- folder -----------------------------------------------------------------
async function msOpenFolder(path) {
  await msFlushTriage();
  const btns = ['#folder-open', '#folder-browse'].map($).filter(Boolean);
  btns.forEach(b => b.disabled = true);
  $('#folder-hint').textContent = 'opening…';
  let r;
  try {
    r = await fetch('/api/ms/folder', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder: path }) }).then(x => x.json());
  } catch (_) { r = { ok: false, error: 'request failed' }; }
  btns.forEach(b => b.disabled = false);
  if (!r.ok) { $('#folder-hint').textContent = '⚠ ' + (r.error || 'could not open'); return; }
  $('#folderpanel').classList.add('hidden');
  MSS.key = null; MSS.a = null; MSS.docxHtml = {};
  $('#ms-doc').classList.add('hidden'); $('#ms-empty').classList.remove('hidden');
  if (window.MODE === 'tables') { tbReset(); await tbLoad(); } else await msLoad();
}

// ---- open a manuscript --------------------------------------------------------
async function msOpen(key) {
  msFlushTriage();
  MSS.key = key;
  let r;
  try {
    const resp = await fetch('/api/ms/doc/' + enc(key));
    r = await resp.json().catch(() => null);
    if (!r || !r.analysis) throw new Error((r && r.error) || ('HTTP ' + resp.status));
  } catch (ex) {
    if (MSS.key !== key) return;
    MSS.key = null; MSS.a = null; MSS.t = null;
    $('#ms-doc').classList.add('hidden'); $('#ms-empty').classList.remove('hidden');
    msStatus('could not open: ' + ((ex && ex.message) || ex));
    msRenderList(); return;
  }
  if (MSS.key !== key) return;
  MSS.a = r.analysis;
  MSS.t = r.triage || {}; MSS.t.findings = MSS.t.findings || {};
  MSS.others = r.others || []; MSS.companions = r.companions || [];
  MSS.lookIdx = {};
  $('#ms-empty').classList.add('hidden'); $('#ms-doc').classList.remove('hidden');
  msRenderHead(r);
  msRenderFindings();
  MSS.which = r.has_annotated ? 'annotated' : 'source';
  msSetWhich(MSS.which);
  msLoadReport();
  msRenderList();
}

function msStatus(text, ms) {
  const st = $('#rerun-status'); st.textContent = text || '';
  if (text) setTimeout(() => { if (st.textContent === text) st.textContent = ''; }, ms || 6000);
}

function msRenderHead(r) {
  const a = MSS.a;
  $('#ms-name').textContent = a.name || a.key;
  $('#ms-badges').replaceChildren(...msSummaryBadges({ summary: a.summary, error: a.error, no_list: a.list == null && !a.error,
                                                        has_annotated: r && r.has_annotated }).map(badgeEl));
  $('#ms-stats').textContent = a.error ? a.error
    : (a.list == null ? (a.note || 'no reference list found')
       : `${a.n_entries} entries · ${a.n_cites} citations · ${a.style}`);
  // companions: the other docx in the folder — tick the ones whose citations count as body text
  const box = $('#ms-companions'); box.innerHTML = '';
  if (!MSS.others.length) box.append(el('span', { class: 'muted' }, 'none in folder'));
  for (const k of MSS.others) {
    const on = MSS.companions.includes(k);
    box.append(el('span', { class: 'ms-comp' + (on ? ' on' : ''), title: (on ? 'counted as body text — click to drop' : 'click to count its citations as body text (a table file, captions, supplement)'),
      onclick: async () => {
        MSS.companions = on ? MSS.companions.filter(x => x !== k) : [...MSS.companions, k];
        MSS.t.companions = MSS.companions;
        await msFlushTriage(true);           // the server re-analyses with the new body
        msOpen(MSS.key);
      } }, k));
  }
  const rv = $('#ms-reviewed'); rv.checked = !!MSS.t.reviewed;
  rv.onchange = () => {
    MSS.t.reviewed = rv.checked;
    const row = MSS.files.find(f => f.key === MSS.key); if (row) row.reviewed = rv.checked;
    msSaveTriage(); msRenderList();
  };
  msPreview();
}
function msPreview() {
  const a = MSS.a; if (!a) return;
  let write = 0, sup = 0;
  for (const f of a.findings) ((MSS.t.findings[f.fkey] || {}).verdict === 'dismiss') ? sup++ : write++;
  $('#ms-preview').textContent = write ? `run writes ${write} comment${write > 1 ? 's' : ''}${sup ? ` · ${sup} suppressed` : ''}`
                                       : (sup ? `${sup} suppressed (clean)` : 'nothing to write');
}

// ---- findings ---------------------------------------------------------------
function msRenderFindings() {
  const a = MSS.a, body = $('#ms-findings-body'); body.innerHTML = '';
  const hide = $('#ms-hide-dismissed').checked;
  let n = 0, hidden = 0;
  for (const kind of ['orphan', 'pair', 'form', 'uncited']) {
    const rows = a.findings.filter(f => f.kind === kind);
    if (!rows.length) continue;
    body.append(el('div', { class: 'ms-sec' }, `${MS_KIND[kind].title} (${rows.length})`));
    for (const f of rows) {
      const t = MSS.t.findings[f.fkey] || {};
      if (hide && t.verdict === 'dismiss') { hidden++; continue; }
      n++;
      body.append(msRow(f, t));
    }
  }
  if (!a.findings.length) body.append(el('div', { class: 'empty muted' }, a.list == null ? (a.note || 'no reference list found — nothing to check') : 'every citation has an entry, every entry is cited, and their forms agree'));
  $('#ms-fcount').textContent = hidden ? `(${n} shown · ${hidden} dismissed hidden)` : `(${n})`;
}
function msRow(f, t) {
  const k = MS_KIND[f.kind];
  const label = `${k.code}: ${f.label}`;
  const sev = t.verdict === 'dismiss' ? 'note' : k.sev;
  const top = el('div', { class: 'f-top' }, el('span', { class: 'sev ' + sev }, SEV_LABEL[k.sev]),
    el('span', { class: 'wtag ' + (t.verdict === 'dismiss' ? 'console' : 'written') }, t.verdict === 'dismiss' ? 'suppressed' : 'comment on run'),
    el('span', { class: 'f-code' }, k.code));
  const rec = () => { const x = (MSS.t.findings[f.fkey] = MSS.t.findings[f.fkey] || {}); x.label = label; return x; };
  const mk = (v, lbl) => el('button', { class: 'tbtn ' + v + (t.verdict === v ? ' on' : ''),
    onclick: ev => { ev.stopPropagation(); const x = rec(); x.verdict = (x.verdict === v ? null : v); msSaveTriage(); msRenderFindings(); msPreview(); } }, lbl);
  const look = el('button', { class: 'tbtn look', onclick: ev => { ev.stopPropagation(); msLook(f); } }, '? look');
  const note = el('input', { class: 'tnote', type: 'text', placeholder: 'note…', value: t.note || '',
    onclick: ev => ev.stopPropagation(), oninput: ev => { rec().note = ev.target.value; msSaveTriage(); } });
  return el('div', { class: 'finding lvl-' + sev, 'data-fkey': f.fkey, onclick: () => msLook(f) },
    top,
    el('div', { class: 'f-msg' }, f.label + ' — ' + f.msg),
    f.entry && f.kind !== 'uncited' ? el('div', { class: 'f-anchor' }, '↳ ' + f.entry) : null,
    f.text ? el('div', { class: 'f-text' }, '¶' + (f.para + 1) + '  ' + f.text) : null,
    el('div', { class: 'triage' }, mk('confirm', '✓ confirm'), mk('dismiss', '✗ dismiss'), look, note));
}
$('#ms-hide-dismissed').addEventListener('change', () => { if (MSS.a) msRenderFindings(); });

// '? look': scroll the docx view to the finding's paragraph (a pair alternates citation / entry)
async function msLook(f) {
  document.querySelectorAll('#ms-findings-body .finding').forEach(d => d.classList.toggle('focus', d.getAttribute('data-fkey') === f.fkey));
  const targets = [f.para]; if (f.entry_para != null) targets.push(f.entry_para);
  const i = (MSS.lookIdx[f.fkey] || 0) % targets.length; MSS.lookIdx[f.fkey] = i + 1;
  const para = targets[i];
  await msLoadDocx();
  const view = $('#ms-docx-view');
  const p = view.querySelector('p[data-p="' + para + '"]');
  if (!p) { msStatus('that paragraph is in a companion file (open it in Word)'); return; }
  view.querySelectorAll('.docx-hit').forEach(x => x.classList.remove('docx-hit'));
  p.classList.add('docx-hit');
  // Animate the scroll ourselves: the browser's own smooth scroll is cancelled in this pane (a
  // native smooth scrollTo moves a couple of pixels and stops), and an instant jump reads as a
  // twitch. A short eased scroll driven by requestAnimationFrame depends on nothing.
  requestAnimationFrame(() => {
    const r = p.getBoundingClientRect(), vr = view.getBoundingClientRect();
    const target = Math.max(0, Math.min(view.scrollHeight - view.clientHeight,
      r.top - vr.top + view.scrollTop - view.clientHeight / 2 + r.height / 2));
    msAnimateScroll(view, target, 420).then(() => {
      p.classList.remove('docx-flash'); void p.offsetWidth; p.classList.add('docx-flash');
    });
  });
}

// eased scroll of a container to `top` over `ms` milliseconds (ease-in-out); a newer call on the
// same element supersedes an older one, so rapid '? look' clicks never fight each other.
function msAnimateScroll(view, top, ms) {
  return new Promise(resolve => {
    const from = view.scrollTop, delta = top - from, t0 = performance.now();
    const token = (view._scrollToken = (view._scrollToken || 0) + 1);
    if (Math.abs(delta) < 1 || document.hidden) { view.scrollTop = top; resolve(); return; }
    let framed = false, done = false;
    const finish = () => { if (!done) { done = true; resolve(); } };
    const step = now => {
      framed = true;
      if (view._scrollToken !== token) { finish(); return; }        // superseded by a newer look
      const k = Math.min(1, (now - t0) / ms);
      const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      view.scrollTop = from + delta * e;
      if (k < 1) requestAnimationFrame(step); else finish();
    };
    requestAnimationFrame(step);
    // frame callbacks pause in a background tab: if none ran, land instantly rather than never —
    // and retire this animation's token so a late first frame cannot restart it from the top
    setTimeout(() => { if (!framed && view._scrollToken === token) { view._scrollToken++; view.scrollTop = top; finish(); } }, 150);
  });
}

// ---- docx view ----------------------------------------------------------------
function msSetWhich(which) {
  MSS.which = which;
  document.querySelectorAll('#ms-which button').forEach(b => b.classList.toggle('on', b.dataset.which === which));
  msLoadDocx(true);
}
document.querySelectorAll('#ms-which button').forEach(b => b.addEventListener('click', () => msSetWhich(b.dataset.which)));
async function msLoadDocx(force) {
  const key = MSS.key, view = $('#ms-docx-view'); if (!key) return;
  const ck = key + '|' + MSS.which;
  if (MSS.docxHtml[ck] != null && (force || !view.dataset.ck || view.dataset.ck !== ck)) { view.innerHTML = MSS.docxHtml[ck]; view.dataset.ck = ck; msWire(); return; }
  if (view.dataset.ck === ck && !force) return;
  view.innerHTML = '<div class="empty muted">rendering docx…</div>';
  let r = null;
  try { r = await fetch('/api/ms/docx/' + enc(key) + '.html?which=' + enc(MSS.which)).then(x => x.json()); } catch (_) {}
  if (MSS.key !== key) return;
  const h = (r && r.html) || '<div class="empty muted">could not render this docx</div>';
  if (r && r.html) MSS.docxHtml[ck] = r.html;
  if (r && r.which && r.which !== MSS.which) {     // no annotated copy yet: the source is shown
    MSS.which = r.which; document.querySelectorAll('#ms-which button').forEach(b => b.classList.toggle('on', b.dataset.which === r.which));
  }
  $('#ms-view-name').textContent = (r && r.name) || '';
  view.innerHTML = h; view.dataset.ck = ck; msWire();
}
function msWire() {
  const view = $('#ms-docx-view');
  view.querySelectorAll('.cmt').forEach(chip => { chip.onclick = e => { e.stopPropagation(); showCmtPopover(chip); }; });
  view.querySelectorAll('.docx-authors .au').forEach(btn => { btn.onclick = e => { e.stopPropagation(); btn.classList.toggle('off');
    const off = btn.classList.contains('off'), au = btn.dataset.author;
    view.querySelectorAll('[data-author]').forEach(x => { if (x.dataset.author === au && !x.classList.contains('au')) x.style.display = off ? 'none' : ''; }); }; });
}
$('#ms-open').addEventListener('click', async () => {
  if (!MSS.key) return;
  const b = $('#ms-open'), old = b.textContent; b.textContent = 'opening…';
  let ok = false;
  try { ok = (await fetch('/api/ms/open/' + enc(MSS.key) + '?which=' + enc(MSS.which), { method: 'POST' }).then(x => x.json())).ok; } catch (_) {}
  b.textContent = ok ? 'opened ✓' : 'open failed'; setTimeout(() => { b.textContent = old; }, 1600);
});
$('#ms-open-report').addEventListener('click', async () => {
  if (!MSS.key) return;
  try { await fetch('/api/ms/open/' + enc(MSS.key) + '?which=report', { method: 'POST' }); } catch (_) {}
});
async function msLoadReport() {
  const key = MSS.key; let r = null;
  try { r = await fetch('/api/ms/report/' + enc(key)).then(x => x.json()); } catch (_) {}
  if (MSS.key !== key) return;
  $('#ms-report-body').textContent = (r && r.text) || '';
  $('#ms-report-note').textContent = (r && r.text) ? '' : '(no report yet — Run writes it)';
}

// ---- triage save + run ----------------------------------------------------------
function msSaveTriage() {
  if (!MSS.key || !MSS.t) return;
  clearTimeout(MSS.saveTimer);
  MSS.t.companions = MSS.companions;
  MSS.pendingSave = { key: MSS.key, payload: JSON.stringify(MSS.t) };
  MSS.saveTimer = setTimeout(msFlushTriage, 350);
}
function msFlushTriage(now) {
  clearTimeout(MSS.saveTimer);
  if (now && MSS.key && MSS.t) { MSS.t.companions = MSS.companions; MSS.pendingSave = { key: MSS.key, payload: JSON.stringify(MSS.t) }; }
  const p = MSS.pendingSave; MSS.pendingSave = null;
  if (!p) return Promise.resolve();
  return fetch('/api/ms/triage/' + enc(p.key), { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: p.payload, keepalive: true }).catch(() => {});
}
window.addEventListener('beforeunload', msFlushTriage);

async function msRun(force) {
  if (!MSS.key) return;
  await msFlushTriage(true);
  const b = $('#ms-run'), orig = b.textContent;
  b.disabled = true; b.classList.add('busy'); b.textContent = 'Running…';
  let r;
  try { r = await fetch('/api/ms/run/' + enc(MSS.key) + (force ? '?force=1' : ''), { method: 'POST' }).then(x => x.json()); }
  catch (ex) { r = { ok: false, error: String(ex) }; }
  b.disabled = false; b.classList.remove('busy'); b.textContent = orig;
  if (!r.ok && r.needs_force) {
    if (window.confirm(r.error + '\n\nOverwrite it?')) return msRun(true);
    msStatus('run cancelled'); return;
  }
  msStatus(r.ok ? 'annotated copy written ✓' : ('run failed' + (r.error ? ': ' + r.error : '')));
  if (r.ok) {
    delete MSS.docxHtml[MSS.key + '|annotated'];
    const row = MSS.files.find(f => f.key === MSS.key); if (row) row.has_annotated = r.annotated;
    msOpen(MSS.key);
  }
}
$('#ms-run').addEventListener('click', () => msRun(false));
$('#ms-export').addEventListener('click', async () => {
  let r; try { r = await fetch('/api/ms/export', { method: 'POST' }).then(x => x.json()); } catch (ex) { r = { ok: false, error: String(ex) }; }
  msStatus(r && r.ok ? 'triage report written ✓ (review_out/ms_triage_report.txt)' : 'export failed' + (r && r.error ? ': ' + r.error : ''));
});

// ---- navigation ---------------------------------------------------------------
function msStep(d) {
  const keys = msVisible().map(f => f.key), i = keys.indexOf(MSS.key);
  if (i === -1) return;
  const j = i + d; if (j >= 0 && j < keys.length) msOpen(keys[j]);
}
$('#ms-prev').addEventListener('click', () => msStep(-1));
$('#ms-next').addEventListener('click', () => msStep(1));

// ---- start ---------------------------------------------------------------------
(async () => {
  let initial = null;
  try { initial = await fetch('/api/ms/state').then(x => x.json()); } catch (_) {}
  let mode = 'entries';
  try { mode = localStorage.getItem('pxrd-mode') || 'entries'; } catch (_) {}
  if (initial && initial.initial) mode = initial.initial === true ? 'manuscript' : initial.initial;   // launched on a manuscript / cif folder
  if (mode === 'manuscript' || mode === 'tables') setMode(mode, { quiet: true });
})();
