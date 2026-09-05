#!/usr/bin/env python3
"""
Review-mode GUI — a local, read-only window into what the review tools found.

The CLI checks (cell_lambda_check / extra_checks / annotate_review) are a black
box: they write Word comments + highlights and an annotation_log.txt, but there
is no way to SEE the evidence behind each finding, so two failure classes are
invisible — silent failures (no .pdf paired, no cell parsed, parse_entry threw,
Mindat didn't resolve, a sibling-phase match) and close calls (a cell match near
the 0.004 Å tolerance, a λ 'verify', an info/note finding that never became a
docx flag).

This serves a small web app, on localhost only, that for each entry shows the
extracted .pdf snippet/page, the docx values and the Mindat values side-by-side,
lists every finding (tagged 'written to docx' vs 'console-only'), and lets the
reviewer triage each one and export a verdict.

It is a THIN PRESENTATION/TRIAGE LAYER over annotate_review.analyze() — it reuses
the check logic verbatim, never duplicates or changes it, and NEVER edits a docx.
Its only writes are its own sidecars (gui_cache.json, triage.json,
triage_report.txt) under <folder>/review_out.

Run:
    python3 -m pxrd_review.gui.review_gui "/path/to/entries"            # opens http://127.0.0.1:8000
    #   (default port 8000; --port to override. NOT 5000 — macOS AirPlay Receiver squats on it.)
    python3 -m pxrd_review.gui.review_gui "/path/to/entries" --port 8000 --no-browser

Security: binds to 127.0.0.1 only (not the network), Flask debug OFF, and the
browser only ever sends an entry KEY that the server maps to a file it indexed at
startup — no raw paths from the page, so no path traversal. A per-launch auth token
(in the printed/opened URL, redeemed for a session cookie) keeps OTHER local users on
a shared machine out; Host-allowlist + Origin checks handle DNS rebinding and CSRF.
No data leaves the machine.
"""
import sys, os, re, io, json, html, argparse, datetime, threading, webbrowser, subprocess, hashlib, zipfile, shutil, time, secrets

from pxrd_review import cell_lambda_check as C
from pxrd_review import extra_checks as X
from pxrd_review import annotate_review as A
from pxrd_review import paths as P
from pxrd_review.gui import _pdf_worker as PW   # MuPDF ops run in a subprocess (crash isolation)

# analyze()'s PDF text parse uses fitz, which (a) is NOT thread-safe and (b) interprets the page
# content stream — so a malformed embedded image can segfault libmupdf, an UNCATCHABLE native fault
# that would take the whole Flask server down (a try/except can't catch a SIGSEGV). Route text
# extraction through the SAME isolating worker pool as the render path: a crash or stall degrades to
# '' (→ analyze()'s 'no text layer' verdict) instead of killing the server, and the pool's separate
# processes sidestep fitz's thread-unsafety with no in-process lock. The CLI keeps the faster
# in-process reader (C._pdf_text_fitz) — a crash there just fails that one run, with no server to
# protect. PW.text is a byte-identical join, so a valid PDF's analysis is unchanged.
def _worker_pdf_reader(path):
    return PW.run(PW.text, path, default='')
C.set_pdf_reader(_worker_pdf_reader)

try:
    from flask import Flask, jsonify, request, send_file, abort, Response, redirect
except ImportError:
    sys.exit("Flask is not installed — run: pip3 install -r requirements.txt "
             "(the GUI needs Flask; the CLI checks do not).")

HERE = os.path.dirname(os.path.abspath(__file__))   # the packaged gui/ folder (assets live here)
app = Flask(__name__, static_folder=os.path.join(HERE, 'static'),
            static_url_path='/static')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0      # don't let the browser cache app.js/css/index

# Security guard for a localhost-only server:
#  - Host-header allowlist defeats DNS-rebinding — a malicious domain pointed at 127.0.0.1
#    still sends its OWN Host header, not ours, so it's rejected.
#  - For state-changing requests, an Origin/Referer check blocks cross-site POSTs (CSRF) —
#    a page on another site can't silently drive /api/rerun (regenerate docx) or /api/triage.
#  - A per-launch token gates every request: browsers can't forge the above, but another OS
#    user on a shared machine can (curl sets any header) — without the token they could list
#    directories (/api/browse), open files, and trigger reruns as whoever runs the GUI. The
#    launch URL carries it once (?t=…); the index route swaps it for a session cookie.
# Populated at launch once the port is known (see main()); empty => not yet configured (allow).
_ALLOWED_HOSTS = set()
_AUTH_TOKEN = None
_AUTH_COOKIE = 'pxrd_token'

_last_seen = None                                    # monotonic time of the most recent client request
_closing_at = None                                   # monotonic time a tab reported it is unloading
_inflight = 0                                        # requests currently being served (auto-exit gate)
_inflight_lock = threading.Lock()

@app.before_request
def _guard_localhost():
    global _last_seen, _inflight
    with _inflight_lock:
        _inflight += 1                               # balanced by teardown_request (runs even on abort)
    if not _ALLOWED_HOSTS:
        _last_seen = time.monotonic()
        return                                       # pre-launch / unconfigured
    if (request.host or '').lower() not in _ALLOWED_HOSTS:
        abort(403)                                   # wrong Host -> DNS-rebinding / off-host
    if _AUTH_TOKEN and not secrets.compare_digest(request.cookies.get(_AUTH_COOKIE) or '', _AUTH_TOKEN):
        # no session cookie: the only way in is the launch URL's token, on '/' (which
        # redeems it for the cookie) — anything else is another local user probing the port
        if not (request.path == '/'
                and secrets.compare_digest(request.args.get('t') or '', _AUTH_TOKEN)):
            abort(403)
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        # CSRF: a state-changing request must prove it came from this page. Browsers attach
        # Origin to every cross-origin fetch/XHR/form POST, so REQUIRE one of Origin/Referer
        # and require it to be us — accepting a request that carries NEITHER (the old `if src:`)
        # left the header-less form-POST corner open for nothing.
        src = request.headers.get('Origin') or request.headers.get('Referer') or ''
        if not src:
            abort(403)
        netloc = src.split('://', 1)[-1].split('/', 1)[0].lower()
        if netloc not in _ALLOWED_HOSTS:
            abort(403)
    # Heartbeat LAST — only a request that cleared the Host/token/CSRF gate counts as "a tab is
    # open". Updated earlier, a rejected probe from another local user refreshed the timer and kept
    # the server alive under a closed browser (the auto-exit watchdog keys on _last_seen).
    _last_seen = time.monotonic()

@app.teardown_request
def _request_done(exc=None):
    global _inflight
    with _inflight_lock:
        _inflight = max(0, _inflight - 1)

@app.after_request
def _no_cache_ui(resp):
    """A localhost dev tool: never cache the UI assets, so edits show on a plain
    reload (no hard-refresh). The expensive PDF renders (/api/pdf/.../*.png) stay
    cacheable — they don't change."""
    if request.path == '/' or request.path.startswith('/static/'):
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    if request.path == '/':
        # defence-in-depth for the innerHTML-heavy docx view: everything is served from
        # this origin; style needs 'unsafe-inline' for the per-author --au style attributes.
        resp.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; "
            "form-action 'self'; frame-ancestors 'none'")
    return resp

# ------------------------------------------------------------------ global state
# Set once at launch (single batch per process). `docx` is keyed by the docx
# basename STEM, which is unique within a folder and stable across reloads — the
# only identifier the browser ever sends back.
STATE = {
    'folder': None, 'out_dir': None,
    'pdf_root': None,              # source pool for PDFs/CIFs/DFTs when the entries folder has none
    'docx': {},                    # key -> docx path
    'order': [],                   # keys, sorted
    'pdf': {}, 'cif': {}, 'dft': {},   # eid -> path
    'cache': {},                   # key -> {'fp': fingerprint, 'data': serialized}
    'triage': {},                  # key -> reviewer verdicts (separate sidecar)
    'gen': 0,                      # folder generation — bumped on each (re)index; aborts stale bg analysis
    'lock': threading.RLock(),
}

# ------------------------------------------------------------------ helpers
def _u(s):
    """Unescape HTML entities for display (docx formulas carry &lt; / &#…;)."""
    return html.unescape(s) if isinstance(s, str) else s

def _mantissa(s):
    """Bare numeric mantissa of a cell value, esd dropped: '5.6751(5)'->'5.6751'.
    Used to search the RAW .pdf text — these survive the mojibake normalisation,
    unlike CellCand.pos (an offset into the normalised string)."""
    m = re.match(r'\s*(-?\d+\.\d+)', s or '')
    return m.group(1) if m else None

def _value_terms(authors_cell):
    """Distinct a/b/c mantissas to locate the cell on a .pdf page."""
    out = []
    for v in (authors_cell or [])[:3]:
        t = _mantissa(v)
        if t and t not in out:
            out.append(t)
    return out

def _is_synthetic(name):
    return bool(re.search(r'(?:-|,\s*)syn\b|synthetic', name or '', re.I))

# Instrument-specific wavelength findings are low value to ICDD (per the reviewer):
# they are still shown, but muted and excluded from the 'fixes needed' count/sort so
# the GUI foregrounds the major annotations/fixes. (The anode-mismatch λ FLAG —
# Mo vs Cu — is a real transcription error and is NOT demoted.)
LOW_PRIORITY_CODES = {'wavelength', 'calc_wavelength'}

def _pdf_path(key):
    eid = C.entry_id(STATE['docx'].get(key, '')) if key in STATE['docx'] else None
    return STATE['pdf'].get(eid) if eid else None

def _dval(s):
    """A reflection d-spacing as a robust PDF-search token: the mantissa with
    trailing zeros stripped ('4.1440' -> '4.144'), so it substring-matches both
    '4.144' and '4.1440' in the paper's powder table. None if too short to be
    distinctive."""
    m = re.match(r'\s*(\d+\.\d{2,})', s or '')
    if not m:
        return None
    v = m.group(1).rstrip('0').rstrip('.')
    return v if len(v) >= 4 else None        # e.g. keep '4.14'+; drop '5.' / '12'

def _pdf_scan(pdf_path, terms):
    """(n_pages, best_evidence_page) — the page with the most hits for `terms`. Runs in a
    subprocess so a malformed-image segfault degrades to (0, 0) instead of killing the server."""
    n, best = PW.run(PW.scan, pdf_path, terms, default=[0, 0])
    return n, best

def _cand(cd):
    if cd is None:
        return None
    return {'a': cd.a, 'b': cd.b, 'c': cd.c, 'al': cd.al, 'be': cd.be, 'ga': cd.ga,
            'V': cd.V, 'Z': cd.Z, 'context': cd.context, 'phase': cd.phase,
            'snippet': (cd.snippet or '').strip()}

def _provenance(cd):
    """Matched-cell source label — delegates to the shared classifier so the GUI
    label and the cell_source check stay in lock-step."""
    return C.provenance_label(cd)

def _mindat_block(name):
    """Mindat structural record + group/status, for the Mindat pane. None if the
    species isn't in the cache (a new mineral) — surfaced as an attention badge."""
    try:
        M = X.mindat_struct(name)
    except Exception:
        M = None
    if not M:
        return None
    lens = sorted([x for x in (M.get('a'), M.get('b'), M.get('c')) if x])
    block = {'a': M.get('a'), 'b': M.get('b'), 'c': M.get('c'),
             'al': M.get('al'), 'be': M.get('be'), 'ga': M.get('ga'),
             'sorted': lens, 'sg': M.get('sg'),
             'formula': _u(M.get('formula') or ''), 'elements': M.get('elements') or [],
             'groupid': M.get('groupid'), 'group': None, 'ima_status': None,
             # Type locality — REFERENCE ONLY, straight from the cache. No check reads it: Mindat's
             # locality is not authority over the paper, and a mismatch here means nothing on its
             # own. It is here because the reviewer usually wants to know where the type material
             # came from while reading the entry.
             'locality': _u(M.get('tl') or '')}
    try:
        from pxrd_review import mindat
        g = mindat.group_of(name)
        if g:
            block['group'], _strunz, block['matched_species'], block['ima_status'] = g
    except Exception:
        pass
    return block

# ------------------------------------------------------------------ serialization
def _finding_keys(findings):
    """Content-stable triage keys for the extra findings — annotate_review.finding_keys
    ('f:' + sha1('code|anchor|msg[:120]')[:10], '#2'/'#3' suffixes on identical
    duplicates), so a verdict survives findings being added/removed/reordered.
    Local fallback implements the same contract for a not-yet-updated annotate_review."""
    fk = getattr(A, 'finding_keys', None)
    if fk is not None:
        return fk(findings)
    keys, seen = [], {}
    for f in findings:
        raw = '%s|%s|%s' % (f.code, f.anchor or '', (f.msg or '')[:120])
        k = 'f:' + hashlib.sha1(raw.encode('utf-8')).hexdigest()[:10]
        seen[k] = seen.get(k, 0) + 1
        keys.append(k if seen[k] == 1 else '%s#%d' % (k, seen[k]))
    return keys

def _compound_names(entry):
    """The reviewer-relevant identifiers from the docx 'Compound Names' section —
    the Mineral name, the Primary (Warr) symbol, and the Primary systematic name —
    as [[desc, name], …]. parse_entry only keeps the first of each, so read the rows."""
    rows = getattr(entry, 'raw_rows', None) or []
    out, insec = [], False
    for r in rows:
        cells = [c.strip() for c in r if c and c.strip()]
        if not cells:
            continue
        if cells[0] == 'Compound Names':
            insec = True
            continue
        if not insec:
            continue
        if len(cells) == 1:                       # next section header ends the block
            break
        desc, name = cells[0], cells[1]
        if desc in ('Mineral', 'Primary') and name.lower() not in ('add new name here.', 'mineral'):
            out.append([desc, name])
    return out

def _serialize(key):
    """Run analyze() (the single source of truth) and render its verdict + the
    surrounding evidence to a JSON-able dict. Triage state is NOT included here —
    it is a separate sidecar so the analysis cache stays pure."""
    path = STATE['docx'][key]
    base = os.path.basename(path)
    eid = C.entry_id(path)
    pdf = STATE['pdf'].get(eid); cif = STATE['cif'].get(eid); dft = STATE['dft'].get(eid)

    res = A.analyze(path, pdf, cif, dft)

    entry, parse_error = None, None
    try:
        entry = X.parse_entry(path)
    except Exception as ex:
        parse_error = str(ex)
    cif_data = X.parse_cif(cif) if cif else {}
    dft_data = X.parse_dft(dft) if dft else {}

    name = (entry.name if entry else None) or C.entry_name(path) or ''
    is_syn = _is_synthetic(name)

    d = res['docx']
    cellt = res['cell']
    status = cellt[0]
    cd = cellt[1] if len(cellt) > 1 else None
    cell = {'status': status}
    if cd is not None:
        # a CALCULATED pattern is simulated from the single-crystal structure, so the
        # cell is unambiguously the SCXRD cell — no 'powder vs SCXRD' ambiguity to confirm.
        is_calc = bool(entry) and (entry.instr.get('spacing_instr') or '').strip().lower() == 'calculated'
        prov = ('SCXRD cell — the docx pattern is calculated/simulated from the single-crystal '
                'structure (no measured powder cell to compare)') if is_calc else _provenance(cd)
        cell.update({'matched': _cand(cd), 'nmatch': cellt[2], 'ncomp': cellt[3],
                     'dev': cellt[4], 'mode': cellt[5], 'provenance': prov})
        cell['deltas'] = [list(t) for t in C.cell_axis_deltas(d.authors_cell, cd)]

    # which extra findings actually get written into the docx (same gate the
    # annotator uses); everything else is console-only.
    writable = {id(f) for f in A._writable_extras(res)}
    extras = res.get('extra', [])
    fkeys = _finding_keys(extras)               # content-stable triage keys ('idx' kept for display)
    findings = [{'idx': i, 'fkey': fkeys[i], 'code': f.code, 'sev': f.sev, 'anchor': f.anchor,
                 'msg': _u(f.msg), 'written': id(f) in writable,
                 'major': f.code not in LOW_PRIORITY_CODES,
                 'evidence': _u(f.evidence) if f.evidence else None}   # short keyword -> GUI 'look' zoom
                for i, f in enumerate(extras)]

    ent = None
    if entry:
        ent = {'name': entry.name, 'primary': entry.primary,
               'compound_names': [[d, _u(n)] for d, n in _compound_names(entry)],
               'crystal_system': entry.crystal_system, 'space_group': entry.space_group,
               'cell': entry.cell, 'instr': entry.instr,
               'formulas': {k: _u(v) for k, v in entry.formulas.items()},
               'comments': {k: _u(v) for k, v in entry.comments.items()},
               'subfiles': entry.subfiles, 'refl_count': len(entry.refl),
               # d-spacings of the reflection list — search tokens to locate the
               # paper's powder table (used by the indexing finding's "? look")
               'refl_d': [d for d in (_dval(r[0]) for r in entry.refl) if d][:24]}

    # Always show the natural-species Mindat record; the UI notes that for a
    # synthetic the tool deliberately skips the Mindat CELL compare (the formula
    # check still applies, so the record is still worth showing).
    mindat = _mindat_block(name)

    pdfinfo = None
    if pdf:
        terms = _value_terms(d.authors_cell)
        # also highlight the MATCHED .pdf cell's own a/b/c — for an INVESTIGATE the
        # docx value is a transcription error absent from the paper (e.g. nigelcookite
        # b=12.2770), so the deviant axis only shows if we search the .pdf value (12.2377).
        if cd is not None:
            for x in (cd.a, cd.b, cd.c):
                t = _mantissa(x)
                if t and t not in terms:
                    terms.append(t)
        npages, evp = _pdf_scan(pdf, terms)
        pdfinfo = {'name': os.path.basename(pdf), 'pages': npages,
                   'evidence_page': evp, 'terms': terms}

    clean = A._is_clean(res)
    severe = A._is_severe(res)
    preview = {'clean': clean, 'severe': severe,
               'accept': 'blank (decide manually)' if severe else 'x (auto-accept)',
               'output_name': A.output_name(base, not clean)}

    out = {
        'key': key, 'eid': eid, 'name': name, 'docx_basename': base,
        'synthetic': is_syn,
        'files': {'pdf': bool(pdf), 'cif': bool(cif), 'dft': bool(dft),
                  'pdf_name': os.path.basename(pdf) if pdf else None,
                  'cif_name': os.path.basename(cif) if cif else None,
                  'dft_name': os.path.basename(dft) if dft else None},
        'cell': cell,
        'params': {k: [list(t) for t in v] for k, v in res.get('params', {}).items()},
        'lam': list(res['lam']) if res.get('lam') else None,
        'lam_evidence': res.get('lam_evidence'),   # structured '? look' target (no message parsing)
        'docx': {'authors_cell': list(d.authors_cell) if d.authors_cell else [],
                 'radiation': d.radiation, 'lam': d.lam,
                 'comments': [list(c) for c in (d.comments or [])]},
        'entry': ent, 'parse_error': parse_error,
        'cif': {'Z': cif_data.get('Z'), 'cell': cif_data.get('cell', {}),
                'SG': cif_data.get('SG'), 'mineral_name': cif_data.get('mineral_name')} if cif_data else {},
        'dft': {'cell': dft_data.get('cell', {}), 'Z': dft_data.get('Z'),
                'SG': dft_data.get('SG'), 'geometry': dft_data.get('geometry'),
                'method': dft_data.get('method'), 'volume': dft_data.get('volume'),
                'temperature': dft_data.get('temperature'),
                'formulas': dft_data.get('formulas', {})} if dft_data else {},
        'mindat': mindat,
        'findings': findings,
        'pdf': pdfinfo,
        'preview': preview,
    }
    # 'fixes' = the major annotations the tool writes into the docx — the GUI's
    # primary lens. Counts each flagged cell parameter, the cell-level comment
    # (investigate / no-match), an anode-mismatch λ flag, and each written extra
    # finding that is NOT a low-priority wavelength note.
    fixes = len(out['params'])
    if status in ('investigate', 'nocell', 'nopdf', 'notext'):
        fixes += 1
    if out['lam'] and out['lam'][0] == 'flag':
        fixes += 1
    fixes += sum(1 for f in findings if f['written'] and f['major'])
    out['fixes'] = fixes
    out['low_priority_written'] = sum(1 for f in findings
                                      if f['written'] and not f['major'])
    out['badges'] = _badges(out)
    return out

# ------------------------------------------------------------------ attention badges
def _badges(s):
    """The silent-failure / close-call surfacing — this is the core of the tool.
    Each badge: {kind, label, level}; level drives colour + the attention sort."""
    b = []
    def add(kind, label, level):
        b.append({'kind': kind, 'label': label, 'level': level})

    # the headline: how many major fixes the tool wrote into this entry.
    if s.get('fixes'):
        add('fixes', '%d fix%s' % (s['fixes'], '' if s['fixes'] == 1 else 'es'), 'fix')

    status = s['cell']['status']
    if status == 'nopdf' or not s['files']['pdf']:
        add('no-pdf', 'no .pdf', 'danger')
    if status == 'notext':
        add('no-text', '.pdf: no text layer', 'danger')   # scanned image — cell/λ not checked
    if status == 'nocell':
        add('no-cell', 'no cell parsed', 'danger')
    if status == 'investigate':
        add('investigate', 'cell INVESTIGATE', 'danger')
    if status == 'match':
        # near-tolerance: an axis within the 2–4 mÅ band — matched, but only just.
        for lab, dv, nv, dd, ok in s['cell'].get('deltas', []):
            if ok and isinstance(dd, (int, float)) and 0.002 < dd <= C.MATCH_TOL + 1e-9:
                add('near-tol', 'cell near tolerance', 'warn'); break

    if s['parse_error']:
        add('parse-error', 'docx parse error', 'danger')

    lam = s['lam']
    if lam and lam[0] == 'unrec':
        add('lam', 'λ unrec', 'warn')        # docx anode not recognised — worth a look
    elif lam and lam[0] == 'verify':
        # anode present but no clear powder-context radiation — a soft FYI, not a
        # likely error; info level so it is surfaced without crowding the
        # needs-attention sort (the repo ethos: conservative > comprehensive).
        add('lam', 'λ verify', 'info')

    if s['mindat'] is None and not s['synthetic']:
        add('mindat', 'Mindat: not resolved', 'warn')

    n_console = sum(1 for f in s['findings'] if not f['written'] and f['sev'] in ('info', 'note'))
    if n_console:
        add('console-only', '%d console-only' % n_console, 'info')

    n_written = sum(1 for f in s['findings'] if f['written'])
    n_written += len(s['params']) + (1 if (lam and lam[0] == 'flag') else 0)
    if n_written:
        add('written', '%d written' % n_written, 'info')

    if s['preview']['severe']:
        add('severe', 'Accept left blank', 'danger')
    if s['preview']['clean']:
        add('clean', 'clean', 'ok')
    return b

ATTENTION = {'danger': 100, 'warn': 10, 'info': 0, 'ok': 0}
def _attention(badges):
    return sum(ATTENTION.get(x['level'], 0) for x in badges)

# ------------------------------------------------------------------ cache
# A hash of the analysis source files' mtimes — folded into every cache key so that
# editing a check (or the serializer) AUTO-invalidates the on-disk cache. Replaces the
# old manual 'bump CACHE_VERSION on every change' ritual (easy to forget → stale cache).
def _code_fingerprint():
    files = [getattr(mod, '__file__', None) for mod in (C, X, A, sys.modules[__name__])]
    try:
        from pxrd_review import mindat as _mindat
        # the Mindat module + its two offline caches: a --refresh (new cell/SG/
        # formula data) must invalidate cached analyses just like a code edit does
        files += [getattr(_mindat, '__file__', None), _mindat.CACHE, _mindat.STRUCT_CACHE]
    except Exception:
        pass
    h = hashlib.md5()
    for f in files:
        try:
            h.update(('%s:%d;' % (f, int(os.path.getmtime(f)))).encode())
        except (OSError, TypeError):
            pass
    return h.hexdigest()[:12]

CODE_FP = _code_fingerprint()

def _fingerprint(key):
    path = STATE['docx'][key]; eid = C.entry_id(path)
    parts = [path, STATE['pdf'].get(eid), STATE['cif'].get(eid), STATE['dft'].get(eid)]
    fp = [CODE_FP]
    for p in parts:
        try:
            fp.append(int(os.path.getmtime(p)) if p else 0)
        except OSError:
            fp.append(0)
    return fp

def get_analysis(key, force=False):
    with STATE['lock']:
        if key not in STATE['docx']:                 # the folder switched mid-request — entry gone
            raise KeyError(key)
        fp = _fingerprint(key)
        c = STATE['cache'].get(key)
        if not force and c and c.get('fp') == fp:
            return c['data']
        data = _serialize(key)
        STATE['cache'][key] = {'fp': fp, 'data': data}
        return data

def _cache_path():
    return os.path.join(STATE['out_dir'], 'gui_cache.json')

def _load_cache():
    try:
        with open(_cache_path(), encoding='utf-8') as f:
            STATE['cache'] = json.load(f)
    except Exception:
        STATE['cache'] = {}

def _save_cache():
    try:
        os.makedirs(STATE['out_dir'], exist_ok=True)
        with open(_cache_path(), 'w', encoding='utf-8') as f:
            json.dump(STATE['cache'], f)
    except Exception as ex:
        print('  !! could not write gui_cache.json: %s' % ex)

# ------------------------------------------------------------------ triage sidecar
def _triage_path():
    return os.path.join(STATE['out_dir'], 'triage.json')

def _load_triage():
    path = _triage_path()
    try:
        with open(path, encoding='utf-8') as f:
            STATE['triage'] = json.load(f)
        return
    except OSError:
        pass                                    # no sidecar yet — a fresh folder
    except Exception as ex:                     # present but unparseable — keep the evidence
        try:
            shutil.copyfile(path, path + '.corrupt')
            print('  !! triage.json is unreadable (%s) — copied aside to triage.json.corrupt' % ex)
        except OSError:
            print('  !! triage.json is unreadable (%s); could not copy it aside' % ex)
    STATE['triage'] = {}

def _save_triage():
    with STATE['lock']:
        os.makedirs(STATE['out_dir'], exist_ok=True)
        path = _triage_path()
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(STATE['triage'], f, indent=1)
        os.replace(tmp, path)   # atomic: the rerun subprocess never sees a half-written file

# ------------------------------------------------------------------ indexing / launch
_VERDICT_RANK = {'confirm': 2, 'dismiss': 1}            # 'look' / None -> 0 (look is navigation, not a verdict)
def _reconcile_triage_keys():
    """Self-heal the triage. Triage is keyed by the docx basename STEM, but which copy discover
    picks for an entry id can change mid-review (a clean '(Name).docx' vs a reviewed
    '(Name)_edited.docx'), and '? look' is no longer a verdict. For each CURRENT entry, merge every
    triage record saved for its id under ANY stem — taking the strongest real verdict per finding
    (confirm > dismiss > none), dropping stale 'look' marks, and keeping notes / accept / reviewed.
    Recovers confirms orphaned by a copy-selection change or shadowed by an accidental 'look'. A
    normal folder (one stem per id) merges a single record → just drops any 'look'. Every OTHER
    saved field (entry note, per-finding label, timestamps, …) is carried over verbatim, with the
    current stem's own values taking priority — the merge never discards data. In-memory,
    persisted on the next save; the original per-stem keys are left untouched."""
    tri = STATE['triage']
    if not tri:
        return
    def idof(s):
        m = re.search(C.ID_RE, s or '')                 # shared id regex — 5/6 digits, I/O/i/o
        return (m.group(1).upper() + m.group(2)) if m else None
    groups = {}                                         # entry id -> [triage records under any stem]
    for k, v in tri.items():
        eid = idof(k)
        if eid and isinstance(v, dict):                 # id-less stems never cross-merge
            groups.setdefault(eid, []).append(v)
    for key in STATE['order']:
        eid = idof(key)
        recs = groups.get(eid) if eid else None
        if not recs:
            continue
        own = tri.get(key)                              # the current stem's own record wins gap-fills
        ordered = ([own] if isinstance(own, dict) else []) + [r for r in recs if r is not own]
        merged = {'findings': {}}
        for r in ordered:
            for k2, v2 in r.items():                    # carry every entry-level field (accept, note, …)
                if k2 == 'findings':
                    continue
                if k2 == 'reviewed':
                    merged['reviewed'] = bool(merged.get('reviewed')) or bool(v2)
                elif merged.get(k2) is None and v2 is not None:
                    merged[k2] = v2
            for fk, fv in (r.get('findings') or {}).items():
                if not isinstance(fv, dict):
                    continue
                cur = merged['findings'].setdefault(fk, {'verdict': None})
                ver = fv.get('verdict')
                ver = ver if ver in _VERDICT_RANK else None     # retire 'look' -> no verdict
                if _VERDICT_RANK.get(ver, 0) > _VERDICT_RANK.get(cur.get('verdict'), 0):
                    cur['verdict'] = ver
                for k2, v2 in fv.items():               # keep label / note / any other finding field
                    if k2 != 'verdict' and cur.get(k2) is None and v2 is not None:
                        cur[k2] = v2
        tri[key] = merged

def _has_pdf_below(root, max_dirs=3000, max_depth=4):
    """True if any .pdf lives within `max_depth` levels below `root`, visiting at most
    `max_dirs` directories. The bound matters: the ancestor probe below can reach very
    large trees (a home directory), and an unbounded recursive glob there walks the
    whole disk before giving up — the folder switch would hang for minutes."""
    base = root.rstrip(os.sep).count(os.sep)
    seen = 0
    for dp, dns, fns in os.walk(root):
        seen += 1
        if seen > max_dirs:
            return False
        if dp.rstrip(os.sep).count(os.sep) - base >= max_depth:
            dns[:] = []
        else:
            dns[:] = [d for d in dns if not d.startswith('.') and d not in ('review_out', '.edit_backup')]
        if any(f.lower().endswith('.pdf') for f in fns):
            return True
    return False

def _source_pool(folder, explicit=None):
    """Locate a 'source pool' of .pdf/.cif/.dft files when the entries folder itself holds none —
    e.g. a reviewer's own docx-only folder (<reviewer>2028Part1/…) whose papers live up in a shared
    sibling Files/. An explicit --pdf-root wins; otherwise walk up to 5 ancestors (never above the
    home directory) and take the nearest whose bounded scan finds any .pdf. Returns None when
    nothing is found — the paper pane just stays empty, as before."""
    if explicit:
        return os.path.abspath(explicit)
    home = os.path.expanduser('~')
    cur = os.path.abspath(folder)
    for _ in range(5):
        parent = os.path.dirname(cur)
        if parent == cur:                                # reached the filesystem root
            break
        cur = parent
        if _has_pdf_below(cur):
            return cur
        if cur == home:                                  # never probe above the home directory
            break
    return None

def build_index(folder, out_dir, pdf_root=None):
    STATE['folder'] = os.path.abspath(folder)
    STATE['out_dir'] = os.path.abspath(out_dir or os.path.join(folder, 'review_out'))
    STATE['pdf_root'] = None                            # cleared; set below only if the pool kicks in
    try:
        from pxrd_review import mindat; mindat.refresh_struct_if_stale()
    except Exception:
        pass
    global CODE_FP
    CODE_FP = _code_fingerprint()               # the Mindat caches may have just refreshed
    STATE['pdf'] = C.pdf_index(folder)
    STATE['cif'] = C.cif_index(folder)
    STATE['dft'] = C.dft_index(folder)
    # A reviewer's own folder may hold only docx (the .pdf/.cif/.dft files sit up in a shared
    # Files/ pool). When no .pdf is found beside the entries, pull the paper/CIF/DFT panes from
    # an ancestor 'source pool' (explicit --pdf-root, else the nearest ancestor with .pdf files)
    # so the source-comparison panes still populate. docx discovery stays on `folder` — we show
    # THIS folder's copies (the reviewer's own); only the read-only source indexes fall back.
    if not STATE['pdf']:
        pool = _source_pool(folder, pdf_root)
        if pool and os.path.abspath(pool) != STATE['folder']:
            STATE['pdf'] = C.pdf_index(pool)
            STATE['cif'] = STATE['cif'] or C.cif_index(pool)
            STATE['dft'] = STATE['dft'] or C.dft_index(pool)
            STATE['pdf_root'] = pool
            print('[review_gui] no .pdf beside the entries — pulling paper/CIF/DFT from %s '
                  '(%d found)' % (pool, len(STATE['pdf'])))
    docs = sorted(C.discover(folder).values())     # recursive: docx at any depth under the root
    STATE['docx'] = {os.path.splitext(os.path.basename(d))[0]: d for d in docs}
    STATE['order'] = list(STATE['docx'].keys())
    _load_cache(); _load_triage(); _reconcile_triage_keys()

def analyze_all(gen=None):
    """Analyze every entry so the dashboard's attention badges populate. Runs in a BACKGROUND
    thread (see start_analysis) so opening or switching a folder shows the entry list instantly
    and the badges fill in progressively — the checks never block navigation. Aborts early if a
    newer folder switch has superseded this run (gen mismatch). Cached results are reused."""
    n = len(STATE['order'])
    print('[review_gui] analyzing %d entr%s in %s (background)'
          % (n, 'y' if n == 1 else 'ies', STATE['folder']))
    for i, key in enumerate(STATE['order'], 1):
        if gen is not None and STATE.get('gen') != gen:
            print('  (superseded by a newer folder — stopping this pass)'); return
        try:
            data = get_analysis(key)
            tags = ' '.join('[%s]' % x['label'] for x in data['badges']
                            if x['level'] in ('danger', 'warn'))
        except Exception as ex:
            tags = '!! ' + str(ex)
        print('  [%2d/%2d] %-9s %-34s %s'
              % (i, n, C.entry_id(STATE['docx'][key]) or '?',
                 (STATE['cache'].get(key, {}).get('data', {}).get('name') or key)[:34], tags))
    if gen is None or STATE.get('gen') == gen:
        _save_cache()

def start_analysis():
    """Kick a background pass over the current folder. Bumps the generation counter so any
    in-flight pass over a previous folder aborts; the dashboard polls /api/entries until the
    badges are in. Returns immediately — navigation never waits on the check suite."""
    STATE['gen'] = STATE.get('gen', 0) + 1
    t = threading.Thread(target=analyze_all, args=(STATE['gen'],), daemon=True)
    STATE['athread'] = t                                # so /api/entries can tell a pass is live
    t.start()

# ------------------------------------------------------------------ routes
@app.route('/')
def index():
    # Redeem the launch URL's token for the session cookie every request is gated on,
    # then strip it from the address bar with a redirect (so a copied/shared URL — or a
    # screen-shared address bar — doesn't carry it).
    if _AUTH_TOKEN and secrets.compare_digest(request.args.get('t') or '', _AUTH_TOKEN):
        resp = redirect('/')
        resp.set_cookie(_AUTH_COOKIE, _AUTH_TOKEN, httponly=True, samesite='Strict',
                        max_age=7 * 86400)
        return resp
    return send_file(os.path.join(HERE, 'index.html'))

@app.route('/api/ping')
def api_ping():
    return jsonify({'ok': True})                     # heartbeat target (the before_request refreshes _last_seen)

@app.route('/api/closing', methods=['POST'])
def api_closing():
    """A tab is unloading (close / navigate / reload). Arm the auto-exit grace; a reload or another
    open tab reconnects within it and cancels (see _auto_exit_watchdog). Beacon target."""
    global _closing_at
    _closing_at = time.monotonic()
    return ('', 204)

def _eid_key(r):
    """Sort key for ascending ICDD id: prefix letters first, then the number
    (e.g. I003599 < I003600 < O002127), tolerant of any digit width."""
    eid = r['eid'] or ''
    m = re.search(r'\d+', eid)
    return (re.sub(r'\d+', '', eid), int(m.group()) if m else 0, eid)

def _row(key, d=None):
    """One dashboard row. With `d` (cached analysis data) the row is complete; without it, a
    lightweight pending row — name/id from the filename, file presence from the indexes, no
    badges — so the list renders instantly while analysis runs in the background (the badges
    fill in as the dashboard polls /api/entries)."""
    reviewed = bool(STATE['triage'].get(key, {}).get('reviewed'))
    if d:
        return {'key': key, 'eid': d['eid'], 'name': d['name'], 'files': d['files'],
                'badges': d['badges'], 'status': d['cell']['status'], 'fixes': d.get('fixes', 0),
                'attention': _attention(d['badges']), 'reviewed': reviewed, 'pending': False}
    path = STATE['docx'][key]
    eid = C.entry_id(path) or key
    return {'key': key, 'eid': eid, 'name': C.entry_name(path) or eid,
            'files': {k: bool(STATE[k].get(eid)) for k in ('pdf', 'cif', 'dft')},
            'badges': [], 'status': 'pending', 'fixes': 0, 'attention': False,
            'reviewed': reviewed, 'pending': True}

@app.route('/api/entries')
def api_entries():
    """Non-blocking: analysed entries return a full row from cache; not-yet-analysed ones return
    a lightweight row (name/id/files, no badges) so the list renders instantly. `pending` counts
    the un-analysed ones — the dashboard polls until it reaches 0."""
    rows, pending = [], 0
    for key in STATE['order']:
        c = STATE['cache'].get(key)
        if c and c.get('fp') == _fingerprint(key):      # already analysed (source unchanged)
            rows.append(_row(key, c['data']))
        else:
            rows.append(_row(key)); pending += 1
    # Rows can go stale AFTER the launch/switch pass finished (e.g. the docx was edited in Word
    # via the 'open' button, or a paired source file changed). Kick a fresh background pass so
    # the badges come back — without this they would stay 'analyzing…' forever. Throttled so a
    # permanently-failing entry cannot spin analysis on every poll.
    alive = STATE.get('athread') is not None and STATE['athread'].is_alive()
    now = time.monotonic()
    if pending and not alive and now - STATE.get('rekick_at', 0) > 30:
        STATE['rekick_at'] = now
        start_analysis()
    # list in ascending ICDD-id order (earlier I-numbers first) — a stable, predictable
    # order to work through the batch. The per-view filter (Fixes/Attention/Clean) picks
    # WHICH entries show; the id orders them.
    rows.sort(key=_eid_key)
    return jsonify({'folder': STATE['folder'], 'out_dir': STATE['out_dir'],
                    'pending': pending, 'entries': rows, 'mindat': _mindat_status()})

def _mindat_status():
    """Cache age for the header chip. The Mindat-backed checks (group/classification,
    chemistry, cell cross-check) find nothing at all when the cache is absent, which is
    indistinguishable from a clean batch — so the GUI states the cache's age rather than
    letting a stale/missing one quietly weaken the review."""
    try:
        from pxrd_review import mindat
        state, line = mindat.cache_status()
        # what this user can DO about it: with a key, refresh; without one, they cannot — their
        # only route to fresher data is a newer release.
        return {'state': state, 'text': line, 'action': mindat.cache_action()}
    except Exception as ex:
        return {'state': 'missing', 'text': 'mindat cache: unreadable (%s)' % ex,
                'action': {'kind': 'upgrade', 'text': mindat.RELEASES_URL}}

def _ln(tag):
    """local-name of a namespaced lxml tag ('{…}ins' -> 'ins')."""
    return tag.rsplit('}', 1)[-1]

def _reviewer_marks_from(path):
    """Structured reviewer marks in `path`: [{'author','kind','text'}] with kind in
    {'change','ins','del','comment'}. Same content as A._extract_reviewer_edits (tracked
    changes + non-tool comments, an adjacent del+ins paired into one 'old → new' change),
    but returned as FIELDS so the GUI can filter by author and render richly. Kept separate
    here so the shared annotation-log helper stays byte-identical. Best-effort -> []."""
    q, xml = A._q, A._xml
    out = []
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            droot = xml(C._zread(z, 'word/document.xml'))
            revs = []
            for e in droot.iter():
                # skip the tool's own tracked changes (its applied fixes): the reviewer-marks
                # pane is for what PEOPLE did to the docx.
                if e.tag in (q('ins'), q('del')) and (e.get(q('author')) or '') == A.AUTHOR:
                    continue
                if e.tag == q('ins'):
                    revs.append(('ins', e.get(q('author')) or '?',
                                 ''.join(t.text or '' for t in e.iter(q('t')))))
                elif e.tag == q('del'):
                    revs.append(('del', e.get(q('author')) or '?',
                                 ''.join(t.text or '' for t in e.iter(q('delText')))))
            i = 0
            while i < len(revs):
                kind, auth, txt = revs[i]
                nxt = revs[i + 1] if i + 1 < len(revs) else None
                if nxt and nxt[1] == auth and {kind, nxt[0]} == {'ins', 'del'}:
                    old, new = (txt, nxt[2]) if kind == 'del' else (nxt[2], txt)
                    old, new = old.strip(), new.strip()
                    if old or new:
                        out.append({'author': auth, 'kind': 'change',
                                    'text': '%s → %s' % (old or '∅', new or '∅')})
                    i += 2
                else:
                    t = txt.strip()
                    if t:
                        out.append({'author': auth, 'kind': kind, 'text': t})
                    i += 1
            if 'word/comments.xml' in names:
                for c in xml(C._zread(z, 'word/comments.xml')):
                    if c.tag == q('comment') and c.get(q('author')) != A.AUTHOR:
                        body = ' '.join(t.text or '' for t in c.iter(q('t'))).strip()
                        out.append({'author': c.get(q('author')) or '?', 'kind': 'comment', 'text': body})
    except Exception:
        return out
    return out

def _entry_user_edits(d, src_path=None):
    """The reviewer's OWN marks (tracked changes / non-tool comments) for this entry, read
    LIVE (never folded into the cached analysis — the cache keys on the SOURCE docx, so a
    cached copy would go stale the moment the output is edited). Two sources, in order:
      1. the edited output in review_out (the normal review workflow — the reviewer's marks
         live in the _edited.docx twin, checked in both naming variants);
      2. otherwise the SOURCE docx itself — for a reviewer's own folder (their copies
         carry the tracked changes/comments directly, with no review_out twin).
    The tool's own comments are excluded (author != AUTHOR), so only human marks show."""
    marks = []
    base = d.get('docx_basename')
    if base:
        for name in (A.output_name(base, True), A.output_name(base, False)):
            p = os.path.join(STATE['out_dir'], name)
            if os.path.exists(p):
                marks = _reviewer_marks_from(p)
                if marks:
                    break
    if not marks and src_path and os.path.exists(src_path):
        marks = _reviewer_marks_from(src_path)   # reviewer marks embedded in the source docx
    return marks

# Finding anchor -> the docx cell it points at, resolved on one table ROW at a time.
#
# Two shapes exist in the ICDD template and they must be handled differently:
#   * ROW-HEAD fields — the label IS the row's first cell, value next to it:
#         [0]Primary Reference  [1]<citation>
#   * INLINE fields — the label sits in the MIDDLE of a row, value in the next cell:
#         [0]Camera Diameter =  [2]I/Ic =  [4]Spacing Instr. :  [5]Other  [6]Intensity Instr. : …
#     Anchoring these by row header is what made every instrument finding land on the
#     'Radiation =' row (the only instrument row whose header matched anything).
# The Author's Cell row is positional: a b c α β γ SG Z in columns 1-8.
_DOCX_ROWHEAD = [
    (re.compile(r"^primary reference\b", re.I), 'reference'),
    (re.compile(r'^ima number\b', re.I),        'ima'),
    (re.compile(r'^optical data\b', re.I),      'optical'),
    (re.compile(r'^analysis$', re.I),           'analysis'),
    (re.compile(r'^mineral$', re.I),            'name'),
    (re.compile(r'^primary$', re.I),            'primary'),
]
_DOCX_INLINE = [
    (re.compile(r'^spacing\s*instr', re.I),   'spacing_instr'),
    (re.compile(r'^intensity\s*instr', re.I), 'intensity_instr'),
    (re.compile(r'^intensity\s*type', re.I),  'intensity_type'),
    (re.compile(r'^radiation\s*=', re.I),     'radiation'),
    (re.compile(r'^filter\s*:', re.I),        'filter'),
]
_DOCX_AXES = ['a', 'b', 'c', 'α', 'β', 'γ', 'SG', 'Z']       # Author's Cell columns 1..8

def _docx_anchor_cells(texts):
    """{column index -> anchor} for one row of cell texts."""
    out = {}
    if not texts:
        return out
    first = texts[0].strip()
    if re.match(r"^author'?s cell\b", first, re.I):
        out[0] = 'cell'                                   # the summary comment's anchor
        for i, ax in enumerate(_DOCX_AXES, start=1):
            if i < len(texts):
                out[i] = 'cell:' + ax
        return out
    if re.match(r'^d\(a\)|^d\(å\)', first, re.I):
        out[0] = 'refl'
        return out
    # The annotator falls back to the Comments-section header when an entry has NO 'IMA Number' /
    # 'Analysis' row — and those rows are absent precisely on the entries where those checks fire
    # (they fire BECAUSE the field is missing). Tag the header so '? look' can land where the
    # highlight actually is, instead of finding nothing and doing nothing at all.
    if first.strip().lower() == 'comments':
        out[0] = 'comments'
        return out
    for rx, name in _DOCX_ROWHEAD:                        # label is the row's first cell
        if rx.match(first) and len(texts) > 1:
            out[1] = name
            return out
    for j, t in enumerate(texts):                         # label sits mid-row
        for rx, name in _DOCX_INLINE:
            if rx.match((t or '').strip()) and j + 1 < len(texts):
                out.setdefault(j + 1, name)
    return out

def _docx_html(path):
    """Render a docx BODY to a lightweight HTML fragment for the in-app 'docx' view —
    paragraphs and tables in document order, with tracked changes shown inline (w:ins as
    <ins>, w:del as <del>, both author-titled) and comment anchors as chips carrying the
    comment text. python-docx silently drops tracked changes/comments, so we walk the XML
    directly. Best-effort -> '' on any error (the pane just shows a fallback)."""
    q, xml = A._q, A._xml
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            droot = xml(C._zread(z, 'word/document.xml'))
            comments = {}
            if 'word/comments.xml' in names:
                for c in xml(C._zread(z, 'word/comments.xml')):
                    if _ln(c.tag) == 'comment':
                        body = ' '.join(t.text or '' for t in c.iter(q('t'))).strip()
                        comments[c.get(q('id'))] = (c.get(q('author')) or '?', body)
    except Exception:
        return ''

    esc = html.escape
    # a stable, distinct colour per author (the tool muted grey; each human reviewer a colour from
    # a legible palette, assigned in sorted order so overlapping reviewers never share one). Drives
    # the per-author highlighting + the legend at the top of the view.
    authors = set()
    for e in droot.iter():
        if _ln(e.tag) in ('ins', 'del'):
            authors.add(e.get(q('author')) or '?')
    for au, _b in comments.values():
        authors.add(au)
    _PAL = ['#ffb454', '#5aa9ff', '#57c98a', '#c58aff', '#6cc4ff', '#ff8f6b', '#ffd86b', '#ff9db1', '#8ad6c0', '#b0a8ff']
    colormap = {A.AUTHOR: 'hsl(0,0%,60%)'}                 # the tool: muted grey (de-emphasised)
    for i, au in enumerate(sorted(a for a in authors if a != A.AUTHOR)):
        colormap[au] = _PAL[i % len(_PAL)]
    def col(au):
        return colormap.get(au, '#8b93a3')
    def cmt_chip(cid):
        au, cbody = comments.get(cid, ('?', ''))
        return ('<span class="cmt" data-author="%s" style="--au:%s" title="%s">\U0001f4ac %s</span>'
                % (esc(au), col(au), esc(cbody), esc(au)))
    def inline(node):
        buf = []
        for ch in node:
            t = _ln(ch.tag)
            if t in ('pPr', 'rPr'):
                continue
            if t == 'r':                         # a run: text (w:t / w:delText) + any inline comment ref
                for rc in ch:
                    rt = _ln(rc.tag)
                    if rt in ('t', 'delText'):
                        buf.append(esc(rc.text or ''))
                    elif rt == 'commentReference':
                        buf.append(cmt_chip(rc.get(q('id'))))
            elif t == 'ins':
                au = ch.get(q('author')) or '?'
                buf.append('<ins data-author="%s" style="--au:%s" title="inserted by %s">%s</ins>'
                           % (esc(au), col(au), esc(au), inline(ch)))
            elif t == 'del':
                au = ch.get(q('author')) or '?'
                buf.append('<del data-author="%s" style="--au:%s" title="deleted by %s">%s</del>'
                           % (esc(au), col(au), esc(au), inline(ch)))
            elif t == 'commentReference':
                buf.append(cmt_chip(ch.get(q('id'))))
            elif len(ch):                       # hyperlink / smartTag / sdt / other container
                buf.append(inline(ch))
        return ''.join(buf)
    pc = [0]                      # paragraph counter — the same document order refs_check.load_docx
                                  # uses (tables and content controls included, text boxes excluded), so
                                  # a manuscript finding's paragraph index lands on the right <p data-p>
    _CONTAINERS = ('sdt', 'sdtContent', 'customXml', 'smartTag')
    def block(node):
        t = _ln(node.tag)
        if t == 'p':
            h = inline(node); n = pc[0]; pc[0] += 1
            return '<p data-p="%d">%s</p>' % (n, h if h.strip() else '&nbsp;')
        if t in _CONTAINERS:
            return ''.join(block(x) for x in node if _ln(x.tag) in ('p', 'tbl') + _CONTAINERS)
        if t == 'tbl':
            rows = []
            for tr in node:
                if _ln(tr.tag) != 'tr':
                    continue
                tcs = [tc for tc in tr if _ln(tc.tag) == 'tc']
                texts = [' '.join(''.join(x.text or '' for x in tc.iter(q('t'))).split())
                         for tc in tcs]
                # Tag the cell each finding ANCHOR points at, so '? look' lands exactly where the
                # annotator writes its highlight. Resolved the way the annotator resolves it —
                # by LABEL cell, not by row header: 'Spacing Instr. :' is cell 4 of a row whose
                # first cell is 'Camera Diameter =', so a row-header scheme can never find it and
                # silently lands on the Radiation row instead.
                anchors = _docx_anchor_cells(texts)
                head = (texts[0] if texts else '').lower()
                cells = ''.join(
                    '<td data-c="%d"%s>%s</td>'
                    % (i, (' data-anchor="%s"' % esc(anchors[i])) if i in anchors else '',
                       ''.join(block(x) for x in tc if _ln(x.tag) in ('p', 'tbl') + _CONTAINERS))
                    for i, tc in enumerate(tcs))
                rows.append('<tr data-h="%s">%s</tr>' % (esc(head[:60]), cells))
            return '<table class="docxtbl">%s</table>' % ''.join(rows)
        return ''
    body = next((ch for ch in droot if _ln(ch.tag) == 'body'), None)
    if body is None:
        return ''
    try:                                                   # honour the best-effort contract: the
        doc_html = ''.join(block(ch) for ch in body)       # block/inline recursion could overflow on
    except Exception:                                      # a pathological/corrupt docx -> '' not a 500
        return ''
    if authors:                                            # colour legend = per-author toggle buttons
        chips = ''.join('<button type="button" class="au" data-author="%s" style="--au:%s" '
                        'title="show / hide this author\'s edits"><span class="sw"></span>%s</button>'
                        % (esc(au), col(au), esc(au)) for au in sorted(authors))
        return '<div class="docx-authors">%s</div>%s' % (chips, doc_html)
    return doc_html

_FIDX_RE = re.compile(r'^f\d+$')
def _migrate_triage_fkeys(key, d):
    """One-time move of this entry's OLD index-keyed triage records ('f0', 'f1', …)
    to the content-stable fkeys. Matched via the saved label ('CODE: msg[:80]') —
    only when it matches exactly ONE current finding, and never clobbering a record
    already saved under the new key. Persisted immediately."""
    with STATE['lock']:
        fnd = (STATE['triage'].get(key) or {}).get('findings')
        if not fnd:
            return
        labels = {}
        for f in d.get('findings', []):
            if f.get('fkey'):
                lab = '%s: %s' % (f['code'], (f['msg'] or '')[:80])
                labels.setdefault(lab, []).append(f['fkey'])
        moved = False
        for old in [k for k in fnd if _FIDX_RE.match(k)]:
            rec = fnd[old]
            targets = labels.get(rec.get('label')) if isinstance(rec, dict) else None
            if targets and len(targets) == 1 and targets[0] not in fnd:
                fnd[targets[0]] = fnd.pop(old)
                moved = True
        if moved:
            _save_triage()

@app.route('/api/entry/<key>')
def api_entry(key):
    if key not in STATE['docx']:
        abort(404)
    try:
        d = get_analysis(key)
    except KeyError:                                 # folder switched between the check and the lock
        abort(404)
    except Exception as ex:                          # analysis crash -> clean JSON, not an HTML 500
        return jsonify({'ok': False, 'error': '%s: %s' % (type(ex).__name__, ex)}), 500
    _migrate_triage_fkeys(key, d)
    return jsonify({'analysis': d, 'triage': STATE['triage'].get(key, {}),
                    'user_edits': _entry_user_edits(d, STATE['docx'].get(key))})

@app.route('/api/docx/<key>.html')
def api_docx_html(key):
    """The entry docx rendered to an HTML fragment (tracked changes + comments inline) for
    the middle pane's 'docx' view — an in-app alternative to flipping to Word."""
    path = STATE['docx'].get(key)
    if not path or not os.path.exists(path):
        abort(404)
    return jsonify({'html': _docx_html(path), 'name': os.path.basename(path)})

@app.route('/api/open/<key>', methods=['POST'])
def api_open(key):
    """Open this entry's PDF or docx in the OS default app (PDF viewer / Word) so the
    reviewer can inspect it in place. `?kind=pdf|docx` selects which — the button opens
    whichever the middle pane is currently showing (default docx, back-compat). Localhost
    -only tool; opens only a file the GUI has already indexed (never an arbitrary path)."""
    kind = (request.args.get('kind') or 'docx').lower()
    path = _pdf_path(key) if kind == 'pdf' else STATE['docx'].get(key)
    if not path or not os.path.exists(path):
        abort(404)
    try:
        if sys.platform == 'darwin':
            subprocess.Popen(['open', path])
        elif os.name == 'nt':
            os.startfile(path)                       # type: ignore[attr-defined]  # noqa
        else:
            subprocess.Popen(['xdg-open', path])
    except Exception as ex:
        return jsonify({'ok': False, 'error': str(ex)}), 500
    return jsonify({'ok': True, 'name': os.path.basename(path)})

# the review-out logs the dashboard 'Log' button can open (whitelist — never an arbitrary path)
_LOG_FILES = ('annotation_log.txt', 'triage_report.txt', 'mindat_discrepancies.txt', 'sweep_report.txt')

@app.route('/api/logs')
def api_logs():
    """Which whitelisted review-out logs currently exist (drives the dashboard 'Log' button)."""
    od = STATE['out_dir'] or ''
    return jsonify({'out_dir': od, 'logs': [n for n in _LOG_FILES if os.path.exists(os.path.join(od, n))]})

@app.route('/api/log')
def api_log():
    """Serve one review-out log inline as plain text (the 'Log' button opens it in a new tab).
    Whitelisted filename only, always resolved under out_dir — no arbitrary path / traversal."""
    name = request.args.get('name') or 'annotation_log.txt'
    if name not in _LOG_FILES:
        abort(404)
    path = os.path.join(STATE['out_dir'] or '', name)
    if not os.path.exists(path):
        abort(404)
    with open(path, encoding='utf-8', errors='replace') as f:
        return Response(f.read(), mimetype='text/plain; charset=utf-8')

@app.route('/api/browse')
def api_browse():
    """List a directory's subfolders + a docx/.pdf content hint, so the GUI folder picker can
    walk the local filesystem. Read-only listing; localhost only. Defaults to the current folder."""
    path = request.args.get('path') or STATE['folder'] or os.path.expanduser('~')
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(path):
        path = os.path.dirname(path) or os.path.abspath(os.sep)
    try:
        dirs = sorted((e.name for e in os.scandir(path)
                       if e.is_dir() and not e.name.startswith('.')), key=str.lower)
    except OSError:
        dirs = []
    d = p = seen = 0                                    # bounded content hint — keep navigation snappy
    for _dp, dns, fns in os.walk(path):
        dns[:] = [x for x in dns if not x.startswith('.') and x not in ('review_out', '.edit_backup')]
        for fn in fns:
            seen += 1
            low = fn.lower()
            if low.endswith('.docx') and not fn.startswith('~$'): d += 1
            elif low.endswith('.pdf'): p += 1
        if seen > 1500:
            break
    parent = os.path.dirname(path)
    return jsonify({'path': path, 'parent': parent if parent != path else None,
                    'dirs': dirs, 'docx': d, 'pdf': p})

@app.route('/api/folder', methods=['POST'])
def api_set_folder():
    """Re-point the GUI at a different entries folder WITHOUT restarting: rebuild the docx/pdf/
    cif/dft indexes, load that folder's sidecars, and re-analyze. Localhost only."""
    data = request.get_json(silent=True) or {}
    folder = os.path.expanduser((data.get('folder') or '').strip())
    if not folder or not os.path.isdir(folder):
        return jsonify({'ok': False, 'error': 'not a folder: %s' % (folder or '(empty)')}), 400
    folder = folder.rstrip('/\\') or folder
    found = C.discover(folder)
    # Picking a bare 'review_out' sidecar folder (its own triage.json / cache, but no entry docx of
    # its own) means "resume the review this belongs to" — open the PARENT that owns it, whose
    # review_out is exactly this folder, so their triage loads.
    if not found and os.path.basename(folder) == 'review_out':
        parent = os.path.dirname(folder)
        pfound = C.discover(parent) if parent else {}
        if pfound:
            folder, found = parent, pfound
    if not found:                                       # validate BEFORE build_index mutates STATE, so a
        return jsonify({'ok': False,                    # rejected switch can't strand the tool on an empty
                        'error': 'no .docx entries found under %s' % folder}), 400   # folder
    with STATE['lock']:                                 # serialize with get_analysis: an in-flight
        STATE['gen'] += 1                               # analysis completes first, later ones see the
        build_index(folder, None)                       # bumped gen (or a KeyError) and stand down
    start_analysis()                                    # background; return at once so the switch is instant
    return jsonify({'ok': True, 'folder': STATE['folder'], 'out_dir': STATE['out_dir'],
                    'pdf_root': STATE.get('pdf_root'), 'count': len(STATE['order'])})

@app.route('/api/pick-folder', methods=['POST'])
def api_pick_folder():
    """Pop the OS-native folder chooser and return the chosen path (macOS: AppleScript
    'choose folder'; Linux: zenity when present). The dialog appears on the machine hosting
    the GUI — localhost only. {cancelled:true} if the user dismisses it."""
    try:
        if sys.platform == 'darwin':
            # 'tell me to activate' brings the dialog frontmost WITH keyboard focus — without it
            # ⌘↑ (up one folder), ⌘⇧G (go to a typed path) and the arrow keys land in the browser
            # instead of the panel. Open INSIDE the current entries folder. NOTE the panel's ‹ ›
            # arrows are HISTORY buttons (greyed until you navigate) — the mouse route UP is the
            # folder-name dropdown in the toolbar, so the prompt spells that out.
            start = STATE.get('folder')
            # a control character can't be escaped into an AppleScript string literal —
            # a newline in a folder name would end the string and inject script lines
            if not (start and os.path.isdir(start)) or any(c in start for c in '\r\n'):
                start = os.path.expanduser('~')
            loc = start.replace('\\', '\\\\').replace('"', '\\"')
            # The panel is Finder's, not osascript's: 'tell me to activate' registers osascript as a
            # foreground app on every click (2 s before the panel shows); activating Finder, which
            # already runs, takes 0.1 s and gives the panel focus just the same
            choose = ('set f to choose folder with prompt '
                      '"Choose the entries folder — go UP via the folder-name menu below (or ⌘↑)" '
                      'default location (POSIX file "%s")\n' % loc)
            via_finder = 'tell application "Finder"\nactivate\n' + choose + 'end tell\nPOSIX path of f'
            via_self = 'tell me to activate\n' + choose + 'POSIX path of f'      # the old route: 2 s slower, needs no consent
            run = lambda s: subprocess.run(['osascript', '-e', s], capture_output=True, text=True, timeout=300)
            try:
                r = run(via_finder)
                # Telling Finder anything is an Apple event, which macOS gates behind an Automation
                # consent ("Terminal wants access to control Finder"). Denied (-1743) or otherwise
                # refused, the old route still works — only a Cancel (-128) is the user's answer.
                if r.returncode != 0 and '-128' not in (r.stderr or ''):
                    r = run(via_self)
            except subprocess.TimeoutExpired:
                return jsonify({'ok': False, 'error': 'the folder dialog got no answer in 5 minutes (a consent sheet may be waiting behind another window)'}), 504
            if r.returncode != 0:
                if '-128' in (r.stderr or ''):
                    return jsonify({'ok': False, 'cancelled': True})     # user hit Cancel
                return jsonify({'ok': False, 'error': 'the folder dialog could not open: ' + (r.stderr or '').strip()[-200:]}), 500
            return jsonify({'ok': True, 'folder': r.stdout.strip()})
        if os.name == 'nt':                                          # Windows: Shell folder dialog
            ps = ('$s = New-Object -ComObject Shell.Application; '
                  '$f = $s.BrowseForFolder(0, "Choose the entries folder", 0); '
                  'if ($f -ne $null) { [Console]::Out.Write($f.Self.Path) }')
            r = subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                               capture_output=True, text=True, timeout=300)
            path = (r.stdout or '').strip()
            if not path:
                return jsonify({'ok': False, 'cancelled': True})     # user hit Cancel / no selection
            return jsonify({'ok': True, 'folder': path})
        if shutil.which('zenity'):
            r = subprocess.run(['zenity', '--file-selection', '--directory',
                                '--title=Choose the entries folder'], capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                return jsonify({'ok': False, 'cancelled': True})
            return jsonify({'ok': True, 'folder': r.stdout.strip()})
        return jsonify({'ok': False, 'error': 'no native folder picker on this platform — type the path'}), 400
    except Exception as ex:
        return jsonify({'ok': False, 'error': str(ex)}), 500

@app.route('/api/pdf/<key>/search')
def api_pdf_search(key):
    pdf = _pdf_path(key)
    if not pdf:
        abort(404)
    q = (request.args.get('q') or '').strip()
    empty = {'pages': [], 'hits': [], 'sizes': {}}
    if not q:
        return jsonify(empty)
    return jsonify(PW.run(PW.search, pdf, q, default=empty))

@app.route('/api/pdf/<key>/sizes.json')
def api_pdf_sizes(key):
    pdf = _pdf_path(key)
    if not pdf:
        abort(404)
    return jsonify(PW.run(PW.sizes, pdf, default=[]))

@app.route('/api/pdf/<key>/words/<int:n>.json')
def api_pdf_words(key, n):
    """Word boxes for a page (PDF points) — drives the selectable text layer the GUI
    overlays on the rendered page so the reviewer can select/copy text and use the
    browser's native find. {w,h} are the page size in points; words = [x0,y0,x1,y1,text]."""
    pdf = _pdf_path(key)
    if not pdf:
        abort(404)
    out = PW.run(PW.words, pdf, n, default=None)
    if out is None:
        abort(404)
    return jsonify(out)

@app.route('/api/pdf/<key>/page/<int:n>.png')
def api_pdf_page(key, n):
    pdf = _pdf_path(key)
    if not pdf:
        abort(404)
    terms = [t for t in (request.args.get('find') or '').split('|') if t]
    png = PW.run(PW.page_png, pdf, n, terms, default=None)
    if png is None:
        abort(404)                                # out-of-range page or a render crash
    return Response(png, mimetype='image/png')

@app.route('/api/pdf/<key>/region/<int:n>.png')
def api_pdf_region(key, n):
    """A zoomed CROP of page n framing the search-hit text — ~half-page wide (one
    column of a 2-column article) x ~quarter-page tall, rendered at 3x with the hits
    highlighted. Falls back to a sensible region when nothing is found."""
    pdf = _pdf_path(key)
    if not pdf:
        abort(404)
    terms = [t for t in (request.args.get('find') or '').split('|') if t]
    png = PW.run(PW.region_png, pdf, n, terms, default=None)
    if png is None:
        abort(404)                                # out-of-range page or a render crash
    return Response(png, mimetype='image/png')

@app.route('/api/triage', methods=['GET'])
def api_triage_get():
    return jsonify(STATE['triage'])

@app.route('/api/triage/<key>', methods=['POST'])
def api_triage_set(key):
    data = request.get_json(force=True, silent=True) or {}
    data['ts'] = datetime.datetime.now().isoformat(timespec='seconds')
    # key check + write + save under ONE lock hold: a folder switch (which swaps
    # STATE['docx']/'triage'/'out_dir' under the same lock) can't interleave, so a
    # decision can never land in another folder's triage.json.
    with STATE['lock']:
        if key not in STATE['docx']:
            abort(404)
        STATE['triage'][key] = data
        _save_triage()
    return jsonify({'ok': True})

@app.route('/api/triage/export', methods=['POST'])
def api_triage_export():
    try:
        path = _export_report()
    except Exception as ex:                          # keep the failure a clean JSON, not an HTML 500
        return jsonify({'ok': False, 'error': str(ex)}), 500
    return jsonify({'ok': True, 'path': path})

# ------------------------------------------------------------------ rerun (regenerate docx)
def _annotate_cmd(extra):
    """annotate_review invocation that feeds the triage sidecar (comment-only:
    suppress dismissed, fold notes, override Accept). No --force, so manual edits
    in an existing output are preserved (refresh-in-place)."""
    return [sys.executable, '-m', 'pxrd_review.annotate_review', STATE['folder'],
            '--triage', _triage_path()] + extra

# one rerun at a time — Flask serves requests on threads, and two concurrent
# annotate_review subprocesses would race on the same output docx / logs
_rerun_lock = threading.Lock()

def _run_annotate(cmd):
    if not _rerun_lock.acquire(blocking=False):
        return jsonify({'ok': False, 'error': 'a rerun is already in progress'}), 409
    try:
        # ensure the sidecar the rerun consumes is on disk
        _save_triage()
        # the subprocess is a fresh interpreter: put the repo root on PYTHONPATH so
        # `-m pxrd_review.annotate_review` resolves even when not pip-installed (dev).
        # PYTHONUTF8: on Windows a PIPED child otherwise encodes stdout as cp1252 and
        # the checks' λ/α/→ output raises UnicodeEncodeError — every rerun would fail;
        # decode our end as UTF-8 to match (errors='replace': never crash on output).
        env = {**os.environ, 'PYTHONPATH': P.repo_root() + os.pathsep + os.environ.get('PYTHONPATH', ''),
               'PYTHONUTF8': '1'}
        try:
            r = subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace',
                               cwd=P.repo_root(), env=env, timeout=1800)
        except Exception as ex:
            return jsonify({'ok': False, 'error': str(ex)}), 500
        tail = '\n'.join((r.stdout or '').strip().splitlines()[-12:])
        return jsonify({'ok': r.returncode == 0, 'returncode': r.returncode,
                        'stdout': tail, 'stderr': (r.stderr or '')[-600:]})
    finally:
        _rerun_lock.release()

@app.route('/api/rerun/<key>', methods=['POST'])
def api_rerun_entry(key):
    if key not in STATE['docx']:
        abort(404)
    eid = C.entry_id(STATE['docx'][key])
    # --no-logs so a single-entry rerun doesn't clobber the batch annotation_log.txt
    return _run_annotate(_annotate_cmd(['--id', eid, '--no-logs']))

@app.route('/api/rerun', methods=['POST'])
def api_rerun_all():
    return _run_annotate(_annotate_cmd([]))

# ------------------------------------------------------------------ export
VERDICT_LABEL = {'confirm': 'CONFIRMED', 'dismiss': 'dismissed', 'look': 'NEEDS A LOOK'}

def _export_report():
    os.makedirs(STATE['out_dir'], exist_ok=True)
    path = os.path.join(STATE['out_dir'], 'triage_report.txt')
    fh = io.StringIO()                          # build in memory; tmp + os.replace below, so one
    fh.write('PXRD review — triage report\n')   # failing entry can't truncate a good report
    fh.write('source folder : %s\n' % STATE['folder'])
    fh.write('generated     : %s\n' % datetime.datetime.now().isoformat(timespec='seconds'))
    reviewed = [k for k in STATE['order'] if STATE['triage'].get(k, {}).get('reviewed')]
    fh.write('entries       : %d total | %d marked reviewed\n'
             % (len(STATE['order']), len(reviewed)))
    fh.write('=' * 78 + '\n')
    for key in STATE['order']:
        t = STATE['triage'].get(key)
        if not t:
            continue
        # only records the reviewer actually acted on — a bare label (no verdict,
        # no note) is rendering residue, not a decision
        verdicts = {fk: v for fk, v in (t.get('findings') or {}).items()
                    if isinstance(v, dict) and (v.get('verdict') or v.get('note'))}
        note_entry = t.get('note')
        if not verdicts and not note_entry and not t.get('reviewed') and t.get('accept') is None:
            continue
        try:
            d = get_analysis(key)
            ent = io.StringIO()                 # per-entry buffer: all-or-nothing lines
            ent.write('\n%s   (%s)%s\n'
                      % ((d['name'] or key).upper(), d['eid'] or '?',
                         '   [REVIEWED]' if t.get('reviewed') else ''))
            ent.write('-' * 78 + '\n')
            if t.get('accept') is not None:
                ent.write('  Accept decision : %s\n' % t.get('accept'))
            for fkey, v in verdicts.items():
                label = VERDICT_LABEL.get(v.get('verdict'), v.get('verdict') or '?')
                line = '  [%-12s] %s' % (label, v.get('label', fkey))
                ent.write(line + '\n')
                if v.get('note'):
                    ent.write('       note: %s\n' % v['note'])
            if note_entry:
                ent.write('  entry note: %s\n' % note_entry)
            fh.write(ent.getvalue())
        except Exception as ex:                 # one broken entry must not sink the report
            fh.write('\n!! %s: analysis failed (%s)\n' % (key, ex))
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(fh.getvalue())
    os.replace(tmp, path)
    print('[review_gui] triage report -> %s' % path)
    return path

# ------------------------------------------------------------------ manuscript mode
# A second mode in the same GUI: one MANUSCRIPT at a time (a paper .docx, its companion table
# files, later its .cif) rather than a folder of ICDD entries. It reuses the shell — token gate,
# folder picker, docx renderer, triage sidecar pattern — and calls refs_check verbatim; the GUI
# never edits a document (the tool writes review_out/<name>_refs.docx, a copy).
from pxrd_review import refs_check as RC

MS = {
    'folder': None, 'out_dir': None,
    'files': {},                   # key (docx stem) -> path
    'order': [],
    'cifs': {},                    # key (cif stem) -> path  (the tables mode)
    'pdfs': {},                    # key (file name) -> path  (papers to fill the tables mode from)
    'data': {},                    # file name -> path: probe / peak-list files for the EPMA and PXRD tabs
    'tb_opts': {},                 # tables mode: per-tab options remembered in review_out/tables_opts.json
    'cache': {},                   # key -> {'fp': fingerprint, 'data': serialized analysis}
    'triage': {},                  # key -> {'findings': {fkey: {verdict, note, label}}, 'reviewed', 'companions'}
    'gen': 0, 'lock': threading.RLock(), 'initial': False, 'athread': None,
}

def _ms_triage_path():
    return os.path.join(MS['out_dir'], 'ms_triage.json')

def _ms_load_triage():
    try:
        with open(_ms_triage_path(), encoding='utf-8') as f:
            MS['triage'] = json.load(f)
    except Exception:
        MS['triage'] = {}

def _ms_save_triage():
    with MS['lock']:
        os.makedirs(MS['out_dir'], exist_ok=True)
        path = _ms_triage_path(); tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(MS['triage'], f, indent=1)
        os.replace(tmp, path)

def _ms_remember(folder):
    try:
        from pxrd_review import cli as _cli
        _cli._save('ms', folder)
    except Exception:
        pass

_DATA_EXT = ('.txt', '.csv', '.tsv', '.xlsx', '.xlsm', '.dat', '.prn')

def ms_set_folder(folder):
    """Point the manuscript mode at a folder: every .docx that is not a tool output is a
    candidate manuscript (non-recursive — any folder is allowed here, so never walk it);
    .cif files are noted for the tables mode. False when the folder holds no docx."""
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        return False
    files, cifs, data, pdfs = {}, {}, {}, {}
    try:
        names = sorted(os.listdir(folder), key=str.lower)
    except OSError:
        return False
    for fn in names:
        low = fn.lower()
        if fn.startswith('~$') or fn.startswith('.'):
            continue
        if low.endswith('.docx') and not low.endswith(('_refs.docx', '_bv.docx')):
            files[os.path.splitext(fn)[0]] = os.path.join(folder, fn)
        elif low.endswith('.cif'):
            cifs[os.path.splitext(fn)[0]] = os.path.join(folder, fn)
        elif low.endswith(_DATA_EXT):
            data[fn] = os.path.join(folder, fn)                 # keyed by the full name: obs.txt ≠ obs.xlsx
        elif low.endswith('.pdf'):
            pdfs[fn] = os.path.join(folder, fn)                 # papers the Tables mode can be filled from
    for fn, path in pdfs.items():
        files.setdefault(os.path.splitext(fn)[0], path)   # a paper .pdf is a manuscript too
    if not files and not cifs and not data:
        return False
    with MS['lock']:
        MS['folder'] = folder
        MS['out_dir'] = os.path.join(folder, 'review_out')
        MS['files'] = files; MS['order'] = list(files); MS['cifs'] = cifs; MS['data'] = data; MS['pdfs'] = pdfs
        MS['cache'] = {}; MS['gen'] += 1
        _ms_load_triage()
        _tb_load_opts()
    t = threading.Thread(target=_ms_analyze_all, args=(MS['gen'],), daemon=True)
    MS['athread'] = t; t.start()
    _ms_remember(folder)
    return True

# ------------------------------------------------------------------ tables mode
# The third mode: publishable tables from a .cif (pxrd_review.tables), rendered in the page and
# written to review_out/<name>_tables.docx on request. Same folder as the manuscript mode — the
# .cif files it lists — and the same rule: keys only from the page, never paths.
from pxrd_review import tables as TB
from pxrd_review import update as UPD

from pxrd_review import epma as EP, gd as GD, pxrd_table as PX, bv_check as BV

_TB_TABS = ('coords', 'bvs', 'gd', 'epma', 'pxrd')

def _tb_opts_path():
    return os.path.join(MS['out_dir'], 'tables_opts.json')

def _tb_load_opts():
    try:
        with open(_tb_opts_path(), encoding='utf-8') as f:
            d = json.load(f)
        MS['tb_opts'] = {k: v for k, v in d.items() if k in _TB_TABS and isinstance(v, dict)}
    except Exception:
        MS['tb_opts'] = {}

def _tb_save_opts(tab, opts):
    """Remember one tab's inputs (strings only, bounded) so tomorrow's session starts where this
    one stopped. Values are re-validated on every use — this is convenience, not trust."""
    clean = {str(k)[:40]: str(v)[:400] for k, v in opts.items() if isinstance(v, (str, int, float, bool))}
    with MS['lock']:
        MS['tb_opts'][tab] = dict(list(clean.items())[:40])
        os.makedirs(MS['out_dir'], exist_ok=True)
        path = _tb_opts_path(); tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(MS['tb_opts'], f, indent=1)
        os.replace(tmp, path)

def _tb_journal():
    jk = request.args.get('journal') or TB.DEFAULT_JOURNAL
    return jk if jk in TB.JOURNALS else TB.DEFAULT_JOURNAL

def _tb_opts():
    """The bond-valence / table options of a request, re-validated (keyword arguments of
    tables.build / tables.run)."""
    params = request.args.get('params') or 'gh'
    if params not in ('gh', 'bo', 'ba'):
        params = 'gh'
    ox = re.sub(r'\s+', '', (request.args.get('ox') or ''))[:200]        # 'Fe = 2, mn=3' -> 'Fe=2,mn=3'
    if ox and not re.fullmatch(r'[A-Za-z]{1,2}=[+-]?\d{1,2}(,[A-Za-z]{1,2}=[+-]?\d{1,2})*', ox):
        ox = ''
    hb = request.args.get('hb') or 'oo'
    if hb not in ('oo', 'h', 'none'):
        hb = 'oo'
    lab = r'[A-Za-z][A-Za-z0-9/]{0,11}'
    donors = re.sub(r'\s+', '', request.args.get('donors') or '')[:300]
    if donors and not re.fullmatch(r'%s=\d(,%s=\d)*' % (lab, lab), donors):
        donors = ''
    pairs = re.sub(r'\s+', '', request.args.get('hbp') or '')[:300]
    if pairs and not re.fullmatch(r'%s>%s(,%s>%s)*' % (lab, lab, lab, lab), pairs):
        pairs = ''
    return dict(params=params, ox=ox or None, cutoff=_qf('cutoff', 1.0, 6.0), include_h=request.args.get('noh') != '1',
                journal_key=_tb_journal(), hbond=hb, hmax=_qf('hmax', 2.6, 4.0), donors=donors or None, hb=pairs or None,
                u6='params' if request.args.get('u6set') == '1' else 'burns')

def _q(name, default='', n=300):
    v = request.args.get(name)
    return (v if v is not None else default)[:n]

def _qf(name, lo, hi):
    """A float query parameter inside [lo, hi], else None."""
    try:
        v = float(request.args.get(name))
    except (TypeError, ValueError):
        return None
    return v if lo <= v <= hi else None

def _tb_data_kind(fn):
    low = fn.lower()
    if low.endswith(('.xlsx', '.xlsm', '.csv', '.tsv')) or re.search(r'epma|probe|wds|eds|analys|chem', low):
        return 'probe'
    if 'calc' in low:
        return 'calc'
    if re.search(r'obs|peak|jade|pxrd|xrd|list', low):
        return 'obs'
    return ''

_TB_OUTPUT = re.compile(r'[^/\\]+_(tables|epma|gd|pxrd|bv)\.(docx|xlsx|txt)')

def _tb_output_ok(name):
    """Only the tool's own outputs in review_out may be opened — a basename of the recognised
    shape, existing there (never a path from the page)."""
    if not name or not _TB_OUTPUT.fullmatch(name) or not MS['out_dir']:
        return None
    path = os.path.join(MS['out_dir'], name)
    return path if os.path.isfile(path) else None

@app.route('/api/version')
def api_version():
    """The installed version and, once the launch-time check has run, what GitHub holds — the
    header's version chip. Nothing is fetched on request; main() starts the check once."""
    return jsonify(UPD.status())

_GUI_ARGV = []                        # the server's own arguments, for the post-update relaunch
_GUI_PORT = None

@app.route('/api/update', methods=['POST'])
def api_update():
    """Update now: pull the checkout or pip-install main, then restart this server with the same
    token and port so the open tab reconnects. Refused when GitHub holds nothing newer."""
    st = UPD.status(); res = st.get('result') or {}
    if not st.get('checkout') and not res.get('newer'):
        return jsonify({'ok': False, 'error': 'nothing newer on GitHub'}), 409
    r = UPD.gui_update(_GUI_ARGV, {'PXRD_GUI_TOKEN': _AUTH_TOKEN or '', 'PXRD_GUI_PORT': str(_GUI_PORT or '')})
    return jsonify(dict(r, ok=True))

@app.route('/api/update/status')
def api_update_status():
    return jsonify(UPD.run_status())

@app.route('/api/tb/state')
def api_tb_state():
    out = MS['out_dir'] or ''
    cifs = [{'key': k, 'name': os.path.basename(p), 'has_word': os.path.exists(os.path.join(out, k + '_tables.docx'))}
            for k, p in sorted(MS['cifs'].items())]
    data = [{'key': k, 'name': k, 'kind': _tb_data_kind(k)} for k in sorted(MS['data'], key=str.lower)]
    outputs = []
    if out and os.path.isdir(out):
        outputs = sorted(fn for fn in os.listdir(out) if _TB_OUTPUT.fullmatch(fn) and not fn.endswith('.txt'))
    pdfs = [{'key': k, 'name': k} for k in sorted(MS.get('pdfs') or {}, key=str.lower)]
    pdfs += [{'key': k, 'name': os.path.basename(v)} for k, v in sorted(MS['files'].items(), key=lambda kv: kv[0].lower()) if v.lower().endswith('.docx')]   # a manuscript .docx is a paper too
    return jsonify({'folder': MS['folder'], 'cifs': cifs, 'data': data, 'outputs': outputs, 'opts': MS['tb_opts'], 'pdfs': pdfs,
                    'journals': [{'key': k, 'name': v['name']} for k, v in TB.JOURNALS.items()], 'default_journal': TB.DEFAULT_JOURNAL})

@app.route('/api/tb/opts/<tab>', methods=['POST'])
def api_tb_opts(tab):
    if tab not in _TB_TABS:
        abort(404)
    d = request.get_json(silent=True) or {}
    if not isinstance(d, dict):
        abort(400)
    _tb_save_opts(tab, d)
    return jsonify({'ok': True})

_TB_PARTS = {'coords': ('coords', 'bonds', 'hbonds'), 'bvs': ('bvs',)}

@app.route('/api/tb/tables/<key>')
def api_tb_tables(key):
    if key not in MS['cifs']:
        abort(404)
    opts = _tb_opts()
    keep = _TB_PARTS.get(request.args.get('part') or '')
    try:
        st, tabs = TB.build(MS['cifs'][key], **opts)
    except Exception as ex:
        return jsonify({'ok': False, 'error': E.explain(ex, MS['cifs'][key])}), 500
    if keep:
        tabs = [(k, t) for k, t in tabs if k in keep]
    return jsonify({'ok': True, 'name': st.name, 'formula': st.formula, 'sg': st.sg,
                    'notes': st.notes, 'html': TB.render_html(tabs), 'text': TB.render_text(tabs)})

@app.route('/api/tb/bvs/<key>/export', methods=['POST'])
def api_tb_bvs_export(key):
    """The bond-valence workbook: every bond with R0, b and s as live formulas, the anion and
    cation sums, the hydrogen bonds — the calculation itself, to check a paper's."""
    if key not in MS['cifs']:
        abort(404)
    opts = _tb_opts()
    try:
        st, result, anion_sum, cells, text = BV.run(MS['cifs'][key], params=opts['params'], ox=opts['ox'], cutoff=opts['cutoff'],
                                                    include_h=opts['include_h'], out_dir=MS['out_dir'], quiet=True, xlsx=True,
                                                    hbond=opts['hbond'], hmax=opts['hmax'], donors=opts['donors'], hb=opts['hb'], u6=opts['u6'])
    except Exception as ex:
        return jsonify({'ok': False, 'error': E.explain(ex, MS['cifs'][key])}), 500
    return jsonify({'ok': True, 'file': key + '_bv.xlsx'})

def _tb_docx_path(key):
    """One of the folder's manuscript .docx files by key (never a path from the page)."""
    path = MS['files'].get(key) if key else None
    return path if path and path.lower().endswith('.docx') else None

@app.route('/api/tb/extract', methods=['POST'])
def api_tb_extract():
    """Fill the tabs from a paper: the analytical table, the basis and the way the unmeasured
    constituents were handled, the optics, the bond-valence parameter set, the powder table. Writes
    the data files the EPMA and PXRD tabs read into review_out and returns the inputs to set."""
    key = request.args.get('pdf') or ''
    path = (MS.get('pdfs') or {}).get(key) or _tb_docx_path(key)
    if not path:
        abort(404)
    from pxrd_review import paper_extract as PE
    stem = os.path.splitext(os.path.basename(path))[0]
    try:
        ex = PE.extract(path, MS['out_dir'], stem)
    except Exception as e:
        return jsonify({'ok': False, 'error': E.explain(e, path)}), 500
    # the written data files join the folder's data list so the tabs can select them
    with MS['lock']:
        for fn in ex['files'].values():
            MS['data'][fn] = os.path.join(MS['out_dir'], fn)
    fill = {'epma': {}, 'gd': {}, 'bvs': {}, 'pxrd': {}}
    name = ex.get('name') or stem
    meth = ex['method']
    if ex['files'].get('epma'):
        fill['epma']['file'] = ex['files']['epma']
    if ex['basis']:
        fill['epma']['basis'] = PE.basis_string(ex['basis'])
    if meth.get('h2o') == 'difference':
        fill['epma']['add'] = 'H2O=difference'
    if meth.get('charge') == 'Fe':
        fill['epma']['charge'] = 'Fe'
    if ex['epma'] and any(r.get('standard') for r in ex['epma']['rows']):
        fill['epma']['standards'] = ','.join('%s=%s' % (r['constituent'], r['standard']) for r in ex['epma']['rows'] if r.get('standard'))[:400]
    fill['epma']['name'] = name
    fill['epma']['method'] = ' | '.join([('basis: ' + ex['basis_sentence']) if ex['basis_sentence'] else ''] + meth['sentences'][:4]).strip(' |')[:1400]
    if ex['optics'].get('n'):
        fill['gd']['n'] = '%.4f' % ex['optics']['n']
    if ex['optics'].get('D_meas'):
        fill['gd']['density'] = '%.3f' % ex['optics']['D_meas']
    fill['gd']['name'] = name
    cif_key = next((k for k in MS['cifs'] if name and name.split('-')[0][:6].lower() in k.lower()), None)
    if cif_key:
        fill['gd']['cif'] = cif_key; fill['_cif'] = cif_key           # the structure of the same mineral, when the folder has it
    if ex['bv'].get('params'):
        fill['bvs']['params'] = ex['bv']['params']
    if ex['bv'].get('u6') == 'params':
        fill['bvs']['u6set'] = '1'
    if ex['files'].get('obs'):
        fill['pxrd']['obs'] = ex['files']['obs']
    if ex['files'].get('calc'):
        fill['pxrd']['calc'] = ex['files']['calc']
    fill['pxrd']['name'] = name
    notes = list(ex['notes'])
    if ex['epma']:
        notes.append('analytical table: %d constituents (%s)%s' % (len(ex['epma']['rows']), ('page %d' % ex['epma']['page']) if ex['epma'].get('page') else 'a table of the manuscript',
                                                                  (', total %.2f' % ex['epma']['total']) if ex['epma']['total'] else ''))
    bvcheck = None
    if cif_key:                                                          # the paper's bond-valence table against the same mineral's .cif
        bc = PE.bv_check_paper(path, MS['cifs'][cif_key], ex)
        if bc.get('lines') is None:
            notes.append('bond valence: ' + bc['message'])                # no table / a stranger's table / the .cif failed: say which
        else:
            notes.append(bc['head'])
            bvcheck = bc['head'] + '\n' + '\n'.join('  ' + ln for ln in bc['lines'])
    if ex['basis_sentence']:
        notes.append('basis: ' + PE.basis_string(ex['basis']))
    notes += meth['sentences'][:3]
    notes += ex['optics']['sentences'][:3]
    notes += ex['bv']['sentences'][:2]
    if ex['pxrd']['obs'] or ex['pxrd']['calc']:
        notes.append('powder table: %d observed, %d calculated lines' % (ex['pxrd']['obs'], ex['pxrd']['calc']))
    return jsonify({'ok': True, 'fill': fill, 'notes': notes, 'files': ex['files'], 'name': name, 'bvcheck': bvcheck})

@app.route('/api/tb/word/<key>', methods=['POST'])
def api_tb_word(key):
    if key not in MS['cifs']:
        abort(404)
    opts = _tb_opts()
    try:
        st, tabs, text = TB.run(MS['cifs'][key], word=True, out_dir=MS['out_dir'], quiet=True, **opts)
    except Exception as ex:
        return jsonify({'ok': False, 'error': E.explain(ex, MS['cifs'][key])}), 500
    return jsonify({'ok': True, 'file': key + '_tables.docx', 'path': os.path.join(MS['out_dir'], key + '_tables.docx')})

# ---- EPMA: wt% oxides from a probe file -> empirical formula + the published composition table
def _tb_epma_args():
    a = request.args
    split = lambda v: [x for x in re.split(r'[;,]', v) if x.strip()]
    return dict(basis=_q('basis', 'O=1', 60), charge=a.get('charge') if a.get('charge') in ('H2O', 'Fe') else None,
                anions=_qf('anions', 0.1, 500), raw_anions=a.get('raw') == '1',
                adds=split(_q('add', '', 400)), converts=split(_q('convert', '', 200)), drop=split(_q('drop', '', 200)),
                points=_q('points', '', 60), standards=_q('standards', '', 400), ideal=_q('ideal', '', 400),
                name=_q('name', '', 80), sheet=_q('sheet', '', 80) or None, method=_q('method', '', 1400))

def _tb_epma(key):
    if key not in MS['data']:
        abort(404)
    path = MS['data'][key]
    try:
        return path, EP.prepare(path, **_tb_epma_args()), None
    except ValueError as ex:
        return path, None, (str(ex), 400)
    except Exception as ex:
        return path, None, (E.explain(ex, path), 500)

@app.route('/api/tb/epma/<key>')
def api_tb_epma(key):
    path, res, err = _tb_epma(key)
    if err:
        return jsonify({'ok': False, 'error': err[0]}), err[1]
    ds, red, table, text = res
    return jsonify({'ok': True, 'html': TB.render_html(EP.to_tabs(table, _tb_journal())), 'text': text,
                    'formula': red.formula(), 'factor': red.factor, 'charge': red.charge, 'total': red.total,
                    'wt': [[k, round(r.wt, 3)] for k, r in red.rows.items()],
                    'constituents': [c.formula for c in ds.constituents], 'n_points': len(ds.points), 'source': ds.source})

@app.route('/api/tb/epma/<key>/export', methods=['POST'])
def api_tb_epma_export(key):
    fmt = request.args.get('fmt') or 'xlsx'
    path, res, err = _tb_epma(key)
    if err:
        return jsonify({'ok': False, 'error': err[0]}), err[1]
    ds, red, table, text = res
    stem = os.path.splitext(key)[0]
    try:
        paths = EP.export(ds, red, table, text, MS['out_dir'], stem, word=fmt == 'word', xlsx=fmt == 'xlsx', journal_key=_tb_journal(),
                          method=_q('method', '', 1400))
    except Exception as ex:
        return jsonify({'ok': False, 'error': E.explain(ex, path)}), 500
    return jsonify({'ok': True, 'file': os.path.basename(paths.get(fmt, paths['text']))})

# ---- Gladstone–Dale: composition (formula or wt%) + n + a density (measured, or from a .cif and Z)
def _tb_gd():
    cif_key = request.args.get('cif') or ''
    cif = MS['cifs'].get(cif_key) if cif_key else None
    if cif_key and not cif:
        abort(404)
    try:
        res = GD.prepare(_q('formula', '', 400), _q('wt', '', 600), _q('oxide', '', 200), _qf('n', 1.0, 4.0),
                         _qf('density', 0.5, 25.0), cif, _qf('z', 0.5, 200), _q('k', '', 300))
    except ValueError as ex:
        return None, (str(ex), 400)
    except Exception as ex:
        return None, (E.explain(ex, cif or ''), 500)
    return res, None

@app.route('/api/tb/gd')
def api_tb_gd():
    res, err = _tb_gd()
    if err:
        return jsonify({'ok': False, 'error': err[0]}), err[1]
    name = _q('name', '', 80)
    return jsonify({'ok': True, 'html': TB.render_html(GD.table(res, name, _tb_journal())), 'text': GD.report_text(res, name),
                    'KC': res['KC'], 'summary': GD.summary(res), 'D_calc': res.get('D_calc'), 'fw': res.get('fw')})

@app.route('/api/tb/gd/export', methods=['POST'])
def api_tb_gd_export():
    fmt = request.args.get('fmt') or 'xlsx'
    res, err = _tb_gd()
    if err:
        return jsonify({'ok': False, 'error': err[0]}), err[1]
    name = _q('name', '', 80)
    stem = re.sub(r'[^\w.-]+', '_', name).strip('_') or 'gd'
    os.makedirs(MS['out_dir'], exist_ok=True)
    try:
        if fmt == 'word':
            path = os.path.join(MS['out_dir'], stem + '_gd.docx'); TB.write_word(None, GD.table(res, name, _tb_journal()), path)
        else:
            path = GD.write_xlsx(res, os.path.join(MS['out_dir'], stem + '_gd.xlsx'), name)
    except Exception as ex:
        return jsonify({'ok': False, 'error': str(ex)}), 500
    return jsonify({'ok': True, 'file': os.path.basename(path)})

# ---- PXRD: observed peak list + calculated pattern -> the combined table, eight strongest in bold
def _tb_pxrd():
    obs, calc = request.args.get('obs') or '', request.args.get('calc') or ''
    if obs not in MS['data'] or calc not in MS['data']:
        abort(404)
    try:
        r = PX.prepare(MS['data'][obs], MS['data'][calc], _qf('tol', 0.01, 10.0) or 1.2, _qf('min_i', 0.0, 100.0) if request.args.get('min_i') else 3.5,
                       _qf('dmin', 0.3, 50.0), _qf('wavelength', 0.1, 5.0), _q('name', '', 80), _tb_journal(), int(_qf('blocks', 1, 4) or 2))
    except ValueError as ex:
        return None, (str(ex), 400)
    except Exception as ex:
        return None, (E.explain(ex, MS['data'][obs]), 500)
    return r, None

@app.route('/api/tb/pxrd')
def api_tb_pxrd():
    r, err = _tb_pxrd()
    if err:
        return jsonify({'ok': False, 'error': err[0]}), err[1]
    obs, calc, rows, t = r
    return jsonify({'ok': True, 'html': TB.render_html([('pxrd', t)]), 'text': TB.render_text([('pxrd', t)]),
                    'n_obs': len(obs), 'n_calc': len(calc), 'n_rows': len(rows), 'n_calc_only': sum(1 for x in rows if x.Iobs is None),
                    'bold': [[x.Iobs, x.dobs] for x in rows if x.obs_id in PX.strongest(rows)]})

@app.route('/api/tb/pxrd/export', methods=['POST'])
def api_tb_pxrd_export():
    fmt = request.args.get('fmt') or 'word'
    r, err = _tb_pxrd()
    if err:
        return jsonify({'ok': False, 'error': err[0]}), err[1]
    obs, calc, rows, t = r
    stem = (re.sub(r'[^\w.-]+', '_', _q('name', '', 80)).strip('_') or os.path.splitext(request.args.get('obs'))[0])
    try:
        paths = PX.export(obs, calc, rows, t, MS['out_dir'], stem, word=fmt == 'word', xlsx=fmt == 'xlsx')
    except Exception as ex:
        return jsonify({'ok': False, 'error': str(ex)}), 500
    return jsonify({'ok': True, 'file': os.path.basename(paths.get(fmt, paths['text']))})

@app.route('/api/tb/open', methods=['POST'])
def api_tb_open():
    """Open one of the tool's outputs (review_out/<x>_tables|epma|gd|pxrd.docx|xlsx) or a listed .cif."""
    key = request.args.get('cif')
    path = MS['cifs'].get(key) if key else _tb_output_ok(request.args.get('file') or '')
    if not path:
        abort(404)
    try:
        if sys.platform == 'darwin':
            subprocess.Popen(['open', path])
        elif os.name == 'nt':
            os.startfile(path)                       # type: ignore[attr-defined]  # noqa
        else:
            subprocess.Popen(['xdg-open', path])
    except Exception as ex:
        return jsonify({'ok': False, 'error': str(ex)}), 500
    return jsonify({'ok': True})

_COMPANION_NAME = re.compile(r'(^|[^a-z])(table|tables|supp|supplement|supplementary|appendix|si|esm)([^a-z]|$)', re.I)

def _ms_default_companions(key):
    """Until the reviewer decides, the other docx whose NAMES say they hold tables or supplementary
    material ('Table 1.docx', 'paper_Supp.docx') count as companions of every manuscript that is not
    itself one of those."""
    if _COMPANION_NAME.search(key):
        return []
    return [k for k in MS['order'] if k != key and _COMPANION_NAME.search(k)]

def _ms_companions(key):
    """The companion keys saved for a manuscript (or the by-name default when nothing was saved),
    resolved to paths later (keys only ever come from the page — never a path)."""
    rec = MS['triage'].get(key) or {}
    keys = rec['companions'] if 'companions' in rec else _ms_default_companions(key)
    return [k for k in keys if k in MS['files'] and k != key]

def _ms_fingerprint(key):
    parts = [CODE_FP]
    for k in [key] + _ms_companions(key):
        p = MS['files'].get(k)
        try:
            st = os.stat(p); parts.append('%s:%d:%d' % (k, int(st.st_mtime), st.st_size))
        except OSError:
            parts.append(k + ':missing')
    return '|'.join(parts)

def _ms_outputs(key):
    od = MS['out_dir'] or ''
    return {'annotated': os.path.join(od, key + '_refs.docx'), 'report': os.path.join(od, key + '_refs_report.txt')}

def ms_analysis(key):
    """The refs_check analysis of one manuscript (cached by file fingerprint), serialized."""
    with MS['lock']:
        path = MS['files'][key]
        c = MS['cache'].get(key); fp = _ms_fingerprint(key)
        if c and c['fp'] == fp:
            return c['data']
        comps = [MS['files'][k] for k in _ms_companions(key)]
    doc, paras = RC._load(path)
    for extra in comps:
        _, more = RC._load(extra)
        paras += [RC.Para(len(paras) + i, p.text, None, 'with:' + os.path.basename(extra)) for i, p in enumerate(more)]
    res = RC.analyze(paras)
    data = RC.serialize(paras, res)
    data['key'] = key; data['name'] = os.path.basename(path)
    if path.lower().endswith(('.pdf', '.docx')):                 # a paper's or a manuscript's own numbers against themselves
        data['findings'] += _ms_paper_findings(key, path)
    data['summary'] = {k: sum(1 for f in data['findings'] if f['kind'] == k) for k in ('orphan', 'uncited', 'pair', 'form', 'calc', 'calcinfo')}
    with MS['lock']:
        if key in MS['files']:
            MS['cache'][key] = {'fp': fp, 'data': data}
    return data

_CALC_FLAG = re.compile(r' vs |but the \.cif|blank but|not in the wt|does not|do not|disagree(?!.*0 disagree)|could not|paper \d|not follow|FAILED|is not a|listed twice|no space|zero written|not reconciled', re.I)

def _ms_cif_for(key, name=''):
    """The .cif of the same mineral in the folder: the same stem, the mineral's name, or the only one."""
    cifs = MS.get('cifs') or {}
    if key in cifs:
        return cifs[key]
    stem = key.lower(); nm = (name or '').split('-')[0].lower()[:6]
    for k, p in cifs.items():
        if k.lower() in stem or stem in k.lower() or (nm and nm in k.lower()):
            return p
    return next(iter(cifs.values())) if len(cifs) == 1 else None

def _ms_paper_findings(key, path):
    """Composition and bond-valence checks of a paper .pdf against its own numbers (and the
    folder's .cif), as manuscript findings: 'calc' where a number does not follow, 'calcinfo' for
    what was re-done and how."""
    from pxrd_review import paper_extract as PE
    out = []
    try:
        chk = PE.check_paper(path, _ms_cif_for(key, PE.mineral_name(PE.text_of(path))), out_dir=None)
    except Exception as ex:
        return [{'kind': 'calcinfo', 'fkey': 'calc:error', 'label': 'paper checks', 'msg': 'could not run (%s: %s)' % (type(ex).__name__, ex),
                 'para': None, 'start': None, 'end': None, 'text': ''}]
    epma = (chk.get('extract') or {}).get('epma') or {}
    if chk['composition'] is None and not epma and chk.get('bv_status') in (None, 'none'):
        return []                                                   # nothing to check: no analytical table, no bond-valence table (a manuscript without tables) — a failed or foreign check still reports
    from pxrd_review import epma as EP
    def constituents_of(el):                                        # 'Si' -> ['SiO2']: the element's constituents as the paper's table writes them
        out_ = []
        for r in epma.get('rows') or []:
            try:
                if EP.parse_constituent(r.get('constituent') or '').element == el:
                    out_.append(r['constituent'])
            except Exception:
                pass
        return out_
    section = ''; page = None
    pdf_name = os.path.basename(path) if path.lower().endswith('.pdf') and os.path.basename(path) in (MS.get('pdfs') or {}) else None
    epma_page = ((chk.get('extract') or {}).get('epma') or {}).get('page')
    for ln in chk['lines']:
        s = ln.strip()
        if not s:
            continue
        head = not ln.startswith('  ')
        if head:
            section = s.split(':', 1)[0]
            m = re.search(r'\(p(\d+)\)', s)                                      # 'the paper's table (p6) vs the .cif'
            page = int(m.group(1)) if m else (epma_page if section.startswith('composition') else None)
        kind = 'calcinfo' if head or not _CALC_FLAG.search(s) or '[unverified]' in s or s.startswith('not verifiable') else 'calc'
        fkey = 'calc:' + hashlib.sha1(s.encode('utf-8')).hexdigest()[:12]
        # what '? look' highlights on the page: the bond's two labels, or the constituents of a composition line
        find = None
        if section.startswith('bond'):                                     # 'O1–Pb4 0.02 vs 0.06', 'Σ for O7': the site labels
            m = re.search(r'([A-Z][A-Za-z]*\d+)[–-]([A-Z][A-Za-z]*\d+)', s) or re.search(r'Σ for ([A-Z][A-Za-z]*\d+)', s)
            find = '|'.join(g for g in m.groups() if g) if m else None
        else:                                                              # 'Si: paper 2.99, …' -> 'SiO2': the bare symbol would light every 'si' on the page
            m = re.match(r'([A-Z][a-z]?)(?: \(informational\))?:', s)
            find = '|'.join(constituents_of(m.group(1))[:3]) or None if m else None
        out.append({'kind': kind, 'fkey': fkey, 'label': section or 'paper', 'msg': s, 'para': None, 'start': None, 'end': None, 'text': '',
                    'page': page if pdf_name else None, 'pdf': pdf_name, 'find': find})
    return out

@app.route('/api/ms/pdf/<key>/page/<int:n>.png')
def api_ms_pdf_page(key, n):
    """Page n (1-based) of one of the folder's papers, the finding's terms highlighted — what
    '? look' shows for a calculation finding, which has no paragraph in a docx to jump to."""
    path = (MS.get('pdfs') or {}).get(key)
    if not path:
        abort(404)
    terms = [t for t in (request.args.get('find') or '').split('|') if t][:6]
    png = PW.run(PW.page_png, path, n - 1, terms, default=None)
    if png is None:
        abort(404)
    return Response(png, mimetype='image/png')

def _ms_analyze_all(gen):
    for key in list(MS['order']):
        if MS.get('gen') != gen:
            return
        try:
            ms_analysis(key)
        except Exception as ex:
            with MS['lock']:
                MS['cache'][key] = {'fp': _ms_fingerprint(key),
                                    'data': {'key': key, 'name': os.path.basename(MS['files'].get(key, key)),
                                             'error': '%s: %s' % (type(ex).__name__, ex), 'findings': [],
                                             'summary': {}, 'list': None, 'style': None}}

def _ms_row(key):
    c = MS['cache'].get(key)
    t = MS['triage'].get(key) or {}
    outs = _ms_outputs(key)
    pdf = next((k for k in (MS.get('pdfs') or {}) if os.path.splitext(k)[0] == key), None) or (key if _tb_docx_path(key) else None)   # what the Tables mode can be filled from
    row = {'key': key, 'name': os.path.basename(MS['files'][key]), 'reviewed': bool(t.get('reviewed')),
           'has_annotated': os.path.exists(outs['annotated']), 'pending': True, 'summary': None, 'error': None, 'pdf': pdf}
    if c and c['fp'] == _ms_fingerprint(key):
        d = c['data']
        row.update(pending=False, summary=d.get('summary') or {}, error=d.get('error'),
                   no_list=(d.get('list') is None and not d.get('error')))
    return row

@app.route('/api/ms/state')
def api_ms_state():
    rows = [_ms_row(k) for k in MS['order']] if MS['folder'] else []
    pending = sum(1 for r in rows if r['pending'])
    alive = MS.get('athread') is not None and MS['athread'].is_alive()
    if pending and not alive and MS['folder']:
        t = threading.Thread(target=_ms_analyze_all, args=(MS['gen'],), daemon=True); MS['athread'] = t; t.start()
    return jsonify({'folder': MS['folder'], 'out_dir': MS['out_dir'], 'initial': MS['initial'],
                    'files': rows, 'pending': pending, 'cifs': sorted(MS['cifs'])})

@app.route('/api/ms/folder', methods=['POST'])
def api_ms_folder():
    data = request.get_json(silent=True) or {}
    folder = os.path.expanduser((data.get('folder') or '').strip())
    if not folder or not os.path.isdir(folder):
        return jsonify({'ok': False, 'error': 'not a folder: %s' % (folder or '(empty)')}), 400
    if not ms_set_folder(folder):
        return jsonify({'ok': False, 'error': 'no .docx in %s (manuscripts are looked for in the folder itself, not its subfolders)' % folder}), 400
    return jsonify({'ok': True, 'folder': MS['folder'], 'count': len(MS['order'])})

@app.route('/api/ms/doc/<key>')
def api_ms_doc(key):
    if key not in MS['files']:
        abort(404)
    try:
        d = ms_analysis(key)
    except Exception as ex:
        return jsonify({'ok': False, 'error': '%s: %s' % (type(ex).__name__, ex)}), 500
    outs = _ms_outputs(key)
    return jsonify({'analysis': d, 'triage': MS['triage'].get(key, {}),
                    'companions': _ms_companions(key),
                    'others': [k for k in MS['order'] if k != key],
                    'has_annotated': os.path.exists(outs['annotated']),
                    'has_report': os.path.exists(outs['report'])})

@app.route('/api/ms/triage/<key>', methods=['POST'])
def api_ms_triage(key):
    data = request.get_json(force=True, silent=True) or {}
    data['ts'] = datetime.datetime.now().isoformat(timespec='seconds')
    with MS['lock']:
        if key not in MS['files']:
            abort(404)
        old = (MS['triage'].get(key) or {}).get('companions') or []
        comps = [k for k in (data.get('companions') or []) if k in MS['files'] and k != key]
        data['companions'] = comps
        MS['triage'][key] = data
        if comps != old:
            MS['cache'].pop(key, None)                  # the body text changed: re-analyse on next open
        _ms_save_triage()
    return jsonify({'ok': True, 'reanalyse': comps != old})

_ms_run_lock = threading.Lock()

@app.route('/api/ms/run/<key>', methods=['POST'])
def api_ms_run(key):
    """Write the annotated copy (review_out/<name>_refs.docx) applying the triage: dismissed
    findings are not written, reviewer notes are folded into the comments. The source is never
    modified. An output someone has since commented on / tracked-changed is not overwritten
    unless ?force=1."""
    if key not in MS['files']:
        abort(404)
    if not _ms_run_lock.acquire(blocking=False):
        return jsonify({'ok': False, 'error': 'a run is already in progress'}), 409
    try:
        _ms_save_triage()
        path = MS['files'][key]; outs = _ms_outputs(key)
        force = request.args.get('force') == '1'
        if os.path.exists(outs['annotated']) and not force and (A._has_foreign_comment(outs['annotated'])
                                                                or A._has_tracked_changes(outs['annotated'])):
            return jsonify({'ok': False, 'needs_force': True,
                            'error': 'the annotated copy carries someone\'s comments or tracked changes — '
                                     'overwrite it?'})
        t = (MS['triage'].get(key) or {}).get('findings') or {}
        comps = [MS['files'][k] for k in _ms_companions(key)]
        try:
            res = RC.check_file(path, MS['out_dir'], annotate=True, force=True, quiet=True,
                                companions=comps, triage=t)
        except Exception as ex:
            return jsonify({'ok': False, 'error': E.explain(ex, path)}), 500
        MS['cache'].pop(key, None)
        return jsonify({'ok': True, 'annotated': os.path.exists(outs['annotated']),
                        'findings': bool(res['orphans'] or res['uncited'] or res['pairs'] or res.get('form'))})
    finally:
        _ms_run_lock.release()

@app.route('/api/ms/docx/<key>.html')
def api_ms_docx_html(key):
    """The manuscript (source, or the tool's annotated copy) rendered for the middle pane."""
    if key not in MS['files']:
        abort(404)
    which = request.args.get('which') or 'annotated'
    path = _ms_outputs(key)['annotated'] if which == 'annotated' else MS['files'][key]
    if not os.path.exists(path):
        if which == 'annotated':
            path = MS['files'][key]; which = 'source'
        else:
            abort(404)
    if path.lower().endswith('.pdf'):
        _, paras = RC._load(path)
        body = ''.join('<p data-p="%d">%s</p>' % (i, html.escape(p.text)) for i, p in enumerate(paras))
        return jsonify({'html': '<div class="pdftext">%s</div>' % body, 'name': os.path.basename(path), 'which': 'source'})
    return jsonify({'html': _docx_html(path), 'name': os.path.basename(path), 'which': which})

@app.route('/api/ms/report/<key>')
def api_ms_report(key):
    if key not in MS['files']:
        abort(404)
    path = _ms_outputs(key)['report']
    if not os.path.exists(path):
        return jsonify({'text': ''})
    with open(path, encoding='utf-8', errors='replace') as f:
        return jsonify({'text': f.read()})

@app.route('/api/ms/open/<key>', methods=['POST'])
def api_ms_open(key):
    """Open the source, the annotated copy or the report in the OS default app — only files the
    mode has indexed or written, never an arbitrary path."""
    if key not in MS['files']:
        abort(404)
    which = request.args.get('which') or 'source'
    outs = _ms_outputs(key)
    path = {'source': MS['files'][key], 'annotated': outs['annotated'], 'report': outs['report']}.get(which)
    if not path or not os.path.exists(path):
        abort(404)
    try:
        if sys.platform == 'darwin':
            subprocess.Popen(['open', path])
        elif os.name == 'nt':
            os.startfile(path)                       # type: ignore[attr-defined]  # noqa
        else:
            subprocess.Popen(['xdg-open', path])
    except Exception as ex:
        return jsonify({'ok': False, 'error': str(ex)}), 500
    return jsonify({'ok': True, 'name': os.path.basename(path)})

@app.route('/api/ms/export', methods=['POST'])
def api_ms_export():
    """review_out/ms_triage_report.txt — the reviewer's verdicts and notes, per manuscript."""
    if not MS['folder']:
        return jsonify({'ok': False, 'error': 'no manuscript folder open'}), 400
    os.makedirs(MS['out_dir'], exist_ok=True)
    path = os.path.join(MS['out_dir'], 'ms_triage_report.txt')
    fh = io.StringIO()
    fh.write('PXRD review — manuscript triage report\nfolder    : %s\ngenerated : %s\n%s\n'
             % (MS['folder'], datetime.datetime.now().isoformat(timespec='seconds'), '=' * 78))
    for key in MS['order']:
        t = MS['triage'].get(key) or {}
        verdicts = {fk: v for fk, v in (t.get('findings') or {}).items()
                    if isinstance(v, dict) and (v.get('verdict') or v.get('note'))}
        if not verdicts and not t.get('reviewed'):
            continue
        fh.write('\n%s%s\n%s\n' % (os.path.basename(MS['files'][key]), '   [REVIEWED]' if t.get('reviewed') else '', '-' * 78))
        if t.get('companions'):
            fh.write('  companions: %s\n' % ', '.join(t['companions']))
        for fk, v in verdicts.items():
            fh.write('  [%-12s] %s\n' % (VERDICT_LABEL.get(v.get('verdict'), v.get('verdict') or '?'), v.get('label', fk)))
            if v.get('note'):
                fh.write('       note: %s\n' % v['note'])
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(fh.getvalue())
    os.replace(tmp, path)
    return jsonify({'ok': True, 'path': path})

# ------------------------------------------------------------------ main
def _auto_exit_watchdog(grace=90):
    """Shut the server down shortly after the browser tab is CLOSED — NOT on idle. A tab beacons
    /api/closing as it unloads (close / navigate / reload); the watchdog then waits `grace` seconds
    and exits only if no further request arrives. A reload or another open tab reconnects within the
    grace and cancels it, so reloading never kills the server. Crucially, a tab that is merely open —
    idle, backgrounded, or with the laptop asleep — sends no beacon, so the server stays up
    indefinitely. The default grace must exceed a browser's background-tab timer throttling
    (Chrome runs a hidden tab's 15 s heartbeat at most once per MINUTE), or closing one tab
    would kill the server under another still-open, backgrounded tab. Never exits while a
    request is still being served (e.g. a long rerun). Disable entirely with --no-auto-exit;
    tune the grace with $PXRD_GUI_EXIT_GRACE."""
    global _closing_at
    step = min(5.0, max(0.5, grace / 4.0))               # poll finer for a short grace (keeps tests fast)
    while True:
        time.sleep(step)
        if _closing_at is None:
            continue
        if _last_seen is not None and _last_seen > _closing_at:
            _closing_at = None                       # a client came back (reload / another tab) — cancel
            continue
        if time.monotonic() - _closing_at > grace:
            if _inflight > 0:                        # a request is mid-flight (a rerun can run for
                continue                             # minutes) — never yank the process under it
            print('\n[review_gui] browser closed — shutting down.')
            try:
                PW.shutdown()                        # stop the MuPDF worker subprocesses too
            except Exception:
                pass
            os._exit(0)

def _pick_port(pref, tries=25):
    """First bindable localhost port at/after `pref`. Default 8000 sidesteps the
    macOS AirPlay Receiver (which squats on 5000 and returns 403); the fallback
    also covers a port that is simply already in use, so --port is rarely needed."""
    import socket
    for p in range(pref, pref + tries):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(('127.0.0.1', p)); s.close(); return p
        except OSError:
            s.close()
    return pref

def main():
    ap = argparse.ArgumentParser(description='Local review-mode GUI for the PXRD review tool.')
    ap.add_argument('folder', help='the entries folder (same one passed to annotate_review.py)')
    ap.add_argument('--port', type=int, default=8000, help='preferred port (auto-falls back to the next free one)')
    ap.add_argument('--out', help='sidecar/output folder (default <folder>/review_out)')
    ap.add_argument('--pdf-root', help='folder holding the source .pdf/.cif/.dft files when the '
                    'entries folder has none (default: auto-detect the nearest ancestor with .pdf)')
    ap.add_argument('--no-browser', action='store_true', help='do not auto-open the browser')
    ap.add_argument('--no-auto-exit', action='store_true',
                    help='keep serving after the browser tab is closed (default: auto-shutdown '
                         'shortly after the last tab closes — never while one is open)')
    ap.add_argument('--manuscript', action='store_true',
                    help='open in Manuscript mode on this folder (a folder of paper .docx, not entries)')
    args = ap.parse_args()

    if not os.path.isdir(args.folder):
        sys.exit('not a folder: %s' % args.folder)
    build_index(args.folder, args.out, args.pdf_root)
    if args.manuscript or not STATE['order']:
        # no ICDD entries here: a folder of manuscripts (or .cif files) opens in the other modes
        if ms_set_folder(args.folder):
            MS['initial'] = 'manuscript' if MS['order'] else 'tables'
            print('[review_gui] %d manuscript(s), %d .cif in %s — opening in %s mode'
                  % (len(MS['order']), len(MS['cifs']), args.folder, MS['initial'].capitalize()))
        elif not STATE['order']:
            sys.exit('no .docx entries (or manuscripts) found in %s' % args.folder)
    if STATE['order']:
        start_analysis()                                # background; the server comes up at once

    relaunched = os.environ.get('PXRD_GUI_PORT', '').isdigit()
    if relaunched:
        args.port = int(os.environ['PXRD_GUI_PORT'])          # a relaunch after Update now: same port
    port = _pick_port(args.port)
    if relaunched and port != args.port:
        args.no_browser = False                               # the old tab cannot find us: open a new one
    if port != args.port:
        print('[review_gui] port %d busy — using %d' % (args.port, port))
    global _ALLOWED_HOSTS, _AUTH_TOKEN, _GUI_ARGV, _GUI_PORT
    _ALLOWED_HOSTS = {'127.0.0.1:%d' % port, 'localhost:%d' % port}   # Host/CSRF allowlist
    # a relaunch after Update now reuses the token so the open tab's cookie still passes
    _AUTH_TOKEN = os.environ.pop('PXRD_GUI_TOKEN', None) or secrets.token_urlsafe(16)
    os.environ.pop('PXRD_GUI_PORT', None)
    _GUI_ARGV = list(sys.argv[1:]); _GUI_PORT = port
    url = 'http://127.0.0.1:%d/?t=%s' % (port, _AUTH_TOKEN)
    UPD.start()                                      # the version chip's one-off check (PXRD_NO_UPDATE_CHECK=1 to skip)
    exit_note = '' if args.no_auto_exit else ' — closes itself when the browser does'
    print('\n[review_gui] serving on %s  (localhost only — Ctrl-C to stop%s)' % (url, exit_note))
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    if not args.no_auto_exit:                        # auto-shutdown once the last tab closes
        try:
            _grace = float(os.environ.get('PXRD_GUI_EXIT_GRACE') or 90)
        except ValueError:
            _grace = 90
        threading.Thread(target=lambda: _auto_exit_watchdog(_grace), daemon=True).start()
    # 127.0.0.1 bind keeps it off the network; debug OFF (no code-exec debugger).
    app.run(host='127.0.0.1', port=port, debug=False)

if __name__ == '__main__':
    main()
