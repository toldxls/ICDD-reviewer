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
    python3 -m pxrd_review.gui.review_gui "/path/to/entries"            # opens http://127.0.0.1:5000
    python3 -m pxrd_review.gui.review_gui "/path/to/entries" --port 8000 --no-browser

Security: binds to 127.0.0.1 only (not the network), Flask debug OFF, and the
browser only ever sends an entry KEY that the server maps to a file it indexed at
startup — no raw paths from the page, so no path traversal. No data leaves the
machine.
"""
import sys, os, re, io, json, html, glob, argparse, datetime, threading, webbrowser, subprocess, hashlib, zipfile, shutil

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

@app.before_request
def _guard_localhost():
    if not _ALLOWED_HOSTS:
        return                                       # pre-launch / unconfigured
    if (request.host or '').lower() not in _ALLOWED_HOSTS:
        abort(403)                                   # wrong Host -> DNS-rebinding / off-host
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        src = request.headers.get('Origin') or request.headers.get('Referer') or ''
        if src:                                      # cross-site state change -> CSRF
            netloc = src.split('://', 1)[-1].split('/', 1)[0].lower()
            if netloc not in _ALLOWED_HOSTS:
                abort(403)

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
    findings = [{'idx': i, 'code': f.code, 'sev': f.sev, 'anchor': f.anchor,
                 'msg': _u(f.msg), 'written': id(f) in writable,
                 'major': f.code not in LOW_PRIORITY_CODES,
                 'evidence': _u(f.evidence) if f.evidence else None}   # short keyword -> GUI 'look' zoom
                for i, f in enumerate(res.get('extra', []))]

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
    if status in ('investigate', 'nocell', 'nopdf'):
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
    h = hashlib.md5()
    for mod in (C, X, A, sys.modules[__name__]):
        f = getattr(mod, '__file__', None)
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
    try:
        with open(_triage_path(), encoding='utf-8') as f:
            STATE['triage'] = json.load(f)
    except Exception:
        STATE['triage'] = {}

def _save_triage():
    with STATE['lock']:
        os.makedirs(STATE['out_dir'], exist_ok=True)
        with open(_triage_path(), 'w', encoding='utf-8') as f:
            json.dump(STATE['triage'], f, indent=1)

# ------------------------------------------------------------------ indexing / launch
def _source_pool(folder, explicit=None):
    """Locate a 'source pool' of .pdf/.cif/.dft files when the entries folder itself holds none —
    e.g. a reviewer's own docx-only folder (Tony2028Part1/…) whose papers live up in a shared
    sibling Files/. An explicit --pdf-root wins; otherwise walk up to 5 ancestors and take the
    nearest that contains any .pdf (checked lazily, so we stop at the first hit). Returns None
    when nothing is found — the paper pane just stays empty, as before."""
    if explicit:
        return os.path.abspath(explicit)
    cur = os.path.abspath(folder)
    for _ in range(5):
        parent = os.path.dirname(cur)
        if parent == cur:                                # reached the filesystem root
            break
        cur = parent
        if next(glob.iglob(os.path.join(cur, '**', '*.[pP][dD][fF]'), recursive=True), None):
            return cur
    return None

def build_index(folder, out_dir, pdf_root=None):
    STATE['folder'] = os.path.abspath(folder)
    STATE['out_dir'] = os.path.abspath(out_dir or os.path.join(folder, 'review_out'))
    STATE['pdf_root'] = None                            # cleared; set below only if the pool kicks in
    try:
        from pxrd_review import mindat; mindat.refresh_struct_if_stale()
    except Exception:
        pass
    STATE['pdf'] = C.pdf_index(folder)
    STATE['cif'] = C.cif_index(folder)
    STATE['dft'] = C.dft_index(folder)
    # A reviewer's own folder may hold only docx (the .pdf/.cif/.dft files sit up in a shared
    # Files/ pool). When no .pdf is found beside the entries, pull the paper/CIF/DFT panes from
    # an ancestor 'source pool' (explicit --pdf-root, else the nearest ancestor with .pdf files)
    # so the source-comparison panes still populate. docx discovery stays on `folder` — we show
    # THIS folder's copies (e.g. Tony's); only the read-only source indexes fall back.
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
    _load_cache(); _load_triage()

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
    threading.Thread(target=analyze_all, args=(STATE['gen'],), daemon=True).start()

# ------------------------------------------------------------------ routes
@app.route('/')
def index():
    return send_file(os.path.join(HERE, 'index.html'))

def _eid_key(r):
    """Sort key for ascending ICDD id: prefix letters first, then the number
    (e.g. I003599 < I003600 < O002127), tolerant of any digit width."""
    eid = r['eid'] or ''
    m = re.search(r'\d+', eid)
    return (re.sub(r'\d+', '', eid), int(m.group()) if m else 0, eid)

def _light_row(key):
    """A dashboard row for an entry not analysed yet: name/id from the filename, file presence
    from the indexes, no badges. Lets the list render instantly while analysis runs in the
    background (the badges fill in as the dashboard polls /api/entries)."""
    path = STATE['docx'][key]
    eid = C.entry_id(path) or key
    return {'key': key, 'eid': eid, 'name': C.entry_name(path) or eid,
            'files': {k: bool(STATE[k].get(eid)) for k in ('pdf', 'cif', 'dft')},
            'badges': [], 'status': 'pending', 'fixes': 0, 'attention': False,
            'reviewed': bool(STATE['triage'].get(key, {}).get('reviewed')), 'pending': True}

@app.route('/api/entries')

def api_entries():
    """Non-blocking: analysed entries return a full row from cache; not-yet-analysed ones return
    a lightweight row (name/id/files, no badges) so the list renders instantly. `pending` counts
    the un-analysed ones — the dashboard polls until it reaches 0."""
    rows, pending = [], 0
    for key in STATE['order']:
        c = STATE['cache'].get(key)
        if c and c.get('fp') == _fingerprint(key):      # already analysed (source unchanged)
            d = c['data']; badges = d['badges']
            rows.append({'key': key, 'eid': d['eid'], 'name': d['name'],
                         'files': d['files'], 'badges': badges,
                         'status': d['cell']['status'], 'fixes': d.get('fixes', 0),
                         'attention': _attention(badges),
                         'reviewed': bool(STATE['triage'].get(key, {}).get('reviewed')),
                         'pending': False})
        else:
            rows.append(_light_row(key)); pending += 1
    # list in ascending ICDD-id order (earlier I-numbers first) — a stable, predictable
    # order to work through the batch. The per-view filter (Fixes/Attention/Clean) picks
    # WHICH entries show; the id orders them.
    rows.sort(key=_eid_key)
    return jsonify({'folder': STATE['folder'], 'out_dir': STATE['out_dir'],
                    'pending': pending, 'entries': rows})

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
      2. otherwise the SOURCE docx itself — for a reviewer's own folder (e.g. Tony's copies,
         which carry his tracked changes/comments directly, with no review_out twin).
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
                cells = ''.join('<td>%s</td>' % ''.join(block(x) for x in tc if _ln(x.tag) in ('p', 'tbl'))
                                for tc in tr if _ln(tc.tag) == 'tc')
                rows.append('<tr>%s</tr>' % cells)
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

@app.route('/api/entry/<key>')
def api_entry(key):
    if key not in STATE['docx']:
        abort(404)
    d = get_analysis(key)
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
def api_open_docx(key):
    """Open this entry's docx in the OS default app (Word) so the reviewer can inspect the
    tracked changes/comments in place. Localhost-only tool; opens only a docx the GUI has
    already indexed (never an arbitrary path)."""
    path = STATE['docx'].get(key)
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
    if not C.discover(folder):                          # validate BEFORE build_index mutates STATE, so a
        return jsonify({'ok': False,                    # rejected switch can't strand the tool on an empty
                        'error': 'no .docx entries found under %s' % folder}), 400   # folder
    build_index(folder, None)
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
            r = subprocess.run(['osascript', '-e',
                                'POSIX path of (choose folder with prompt "Choose the entries folder")'],
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
    if key not in STATE['docx']:
        abort(404)
    data = request.get_json(force=True, silent=True) or {}
    data['ts'] = datetime.datetime.now().isoformat(timespec='seconds')
    with STATE['lock']:
        STATE['triage'][key] = data
    _save_triage()
    return jsonify({'ok': True})

@app.route('/api/triage/export', methods=['POST'])
def api_triage_export():
    path = _export_report()
    return jsonify({'ok': True, 'path': path})

# ------------------------------------------------------------------ rerun (regenerate docx)
def _annotate_cmd(extra):
    """annotate_review invocation that feeds the triage sidecar (comment-only:
    suppress dismissed, fold notes, override Accept). No --force, so manual edits
    in an existing output are preserved (refresh-in-place)."""
    return [sys.executable, '-m', 'pxrd_review.annotate_review', STATE['folder'],
            '--triage', _triage_path()] + extra

def _run_annotate(cmd):
    # ensure the sidecar the rerun consumes is on disk
    _save_triage()
    # the subprocess is a fresh interpreter: put the repo root on PYTHONPATH so
    # `-m pxrd_review.annotate_review` resolves even when not pip-installed (dev)
    env = {**os.environ, 'PYTHONPATH': P.repo_root() + os.pathsep + os.environ.get('PYTHONPATH', '')}
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=P.repo_root(), env=env, timeout=1800)
    except Exception as ex:
        return jsonify({'ok': False, 'error': str(ex)}), 500
    tail = '\n'.join((r.stdout or '').strip().splitlines()[-12:])
    return jsonify({'ok': r.returncode == 0, 'returncode': r.returncode,
                    'stdout': tail, 'stderr': (r.stderr or '')[-600:]})

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
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('PXRD review — triage report\n')
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
            verdicts = t.get('findings', {})
            note_entry = t.get('note')
            if not verdicts and not note_entry and not t.get('reviewed') and t.get('accept') is None:
                continue
            d = get_analysis(key)
            fh.write('\n%s   (%s)%s\n'
                     % ((d['name'] or key).upper(), d['eid'] or '?',
                        '   [REVIEWED]' if t.get('reviewed') else ''))
            fh.write('-' * 78 + '\n')
            if t.get('accept') is not None:
                fh.write('  Accept decision : %s\n' % t.get('accept'))
            for fkey, v in verdicts.items():
                label = VERDICT_LABEL.get(v.get('verdict'), v.get('verdict') or '?')
                line = '  [%-12s] %s' % (label, v.get('label', fkey))
                fh.write(line + '\n')
                if v.get('note'):
                    fh.write('       note: %s\n' % v['note'])
            if note_entry:
                fh.write('  entry note: %s\n' % note_entry)
    print('[review_gui] triage report -> %s' % path)
    return path

# ------------------------------------------------------------------ main
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
    print('\n[review_gui] serving on %s  (localhost only — Ctrl-C to stop)' % url)
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    # 127.0.0.1 bind keeps it off the network; debug OFF (no code-exec debugger).
    app.run(host='127.0.0.1', port=port, debug=False)

if __name__ == '__main__':
    main()
