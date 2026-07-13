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
startup — no raw paths from the page, so no path traversal. No data leaves the
machine.
"""
import sys, os, re, io, json, html, argparse, datetime, threading, webbrowser, subprocess, hashlib, zipfile, shutil, time

from pxrd_review import cell_lambda_check as C
from pxrd_review import extra_checks as X
from pxrd_review import annotate_review as A
from pxrd_review import paths as P
from pxrd_review.gui import _pdf_worker as PW   # MuPDF ops run in a subprocess (crash isolation)

# analyze()'s PDF text parse uses fitz, which is not thread-safe — two request threads calling it
# at once (e.g. during a live folder re-point) could corrupt libmupdf and crash the server. Unlike
# the render path (get_pixmap can segfault on a JPEG-2000 decode, so it MUST run in the isolating
# subprocess), get_text() has no such crash on the corpus — so we keep it IN-PROCESS for speed
# (~0.06 s/pdf; a subprocess round-trip per entry is far slower) and just SERIALISE it under a lock.
_pdf_read_lock = threading.Lock()
def _serial_pdf_reader(path):
    with _pdf_read_lock:
        return C._pdf_text_fitz(path)
C.set_pdf_reader(_serial_pdf_reader)

try:
    from flask import Flask, jsonify, request, send_file, abort, Response
except ImportError:
    sys.exit("Flask is not installed — run: pip3 install -r requirements.txt "
             "(the GUI needs Flask; the CLI checks do not).")

HERE = os.path.dirname(os.path.abspath(__file__))   # the packaged gui/ folder (assets live here)
app = Flask(__name__, static_folder=os.path.join(HERE, 'static'),
            static_url_path='/static')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0      # don't let the browser cache app.js/css/index

# Security guard for a localhost-only server (no authentication by design):
#  - Host-header allowlist defeats DNS-rebinding — a malicious domain pointed at 127.0.0.1
#    still sends its OWN Host header, not ours, so it's rejected.
#  - For state-changing requests, an Origin/Referer check blocks cross-site POSTs (CSRF) —
#    a page on another site can't silently drive /api/rerun (regenerate docx) or /api/triage.
# Populated at launch once the port is known (see main()); empty => not yet configured (allow).
_ALLOWED_HOSTS = set()

_last_seen = None                                    # monotonic time of the most recent client request
_closing_at = None                                   # monotonic time a tab reported it is unloading
_inflight = 0                                        # requests currently being served (auto-exit gate)
_inflight_lock = threading.Lock()

@app.before_request
def _guard_localhost():
    global _last_seen, _inflight
    _last_seen = time.monotonic()                    # heartbeat: any request means a tab is open
    with _inflight_lock:
        _inflight += 1
    if not _ALLOWED_HOSTS:
        return                                       # pre-launch / unconfigured
    if (request.host or '').lower() not in _ALLOWED_HOSTS:
        abort(403)                                   # wrong Host -> DNS-rebinding / off-host
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
             'groupid': M.get('groupid'), 'group': None, 'ima_status': None}
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
        return {'state': state, 'text': line}
    except Exception as ex:
        return {'state': 'missing', 'text': 'mindat cache: unreadable (%s)' % ex}

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
            droot = xml(z.read('word/document.xml'))
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
                for c in xml(z.read('word/comments.xml')):
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
            droot = xml(z.read('word/document.xml'))
            comments = {}
            if 'word/comments.xml' in names:
                for c in xml(z.read('word/comments.xml')):
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
    def block(node):
        t = _ln(node.tag)
        if t == 'p':
            h = inline(node)
            return '<p>%s</p>' % (h if h.strip() else '&nbsp;')
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
                       ''.join(block(x) for x in tc if _ln(x.tag) in ('p', 'tbl')))
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
            if not (start and os.path.isdir(start)):
                start = os.path.expanduser('~')
            loc = start.replace('\\', '\\\\').replace('"', '\\"')
            script = ('tell me to activate\n'
                      'set f to choose folder with prompt '
                      '"Choose the entries folder — go UP via the folder-name menu below (or ⌘↑)" '
                      'default location (POSIX file "%s")\n'
                      'POSIX path of f' % loc)
            r = subprocess.run(['osascript', '-e', script],
                               capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                return jsonify({'ok': False, 'cancelled': True})     # user hit Cancel
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
    args = ap.parse_args()

    if not os.path.isdir(args.folder):
        sys.exit('not a folder: %s' % args.folder)
    build_index(args.folder, args.out, args.pdf_root)
    if not STATE['order']:
        sys.exit('no .docx entries found in %s' % args.folder)
    start_analysis()                                    # background; the server comes up at once

    port = _pick_port(args.port)
    if port != args.port:
        print('[review_gui] port %d busy — using %d' % (args.port, port))
    global _ALLOWED_HOSTS
    _ALLOWED_HOSTS = {'127.0.0.1:%d' % port, 'localhost:%d' % port}   # Host/CSRF allowlist
    url = 'http://127.0.0.1:%d/' % port
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
