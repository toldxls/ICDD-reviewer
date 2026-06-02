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
    python3 gui/review_gui.py "/path/to/entries"            # opens http://127.0.0.1:5000
    python3 gui/review_gui.py "/path/to/entries" --port 8000 --no-browser

Security: binds to 127.0.0.1 only (not the network), Flask debug OFF, and the
browser only ever sends an entry KEY that the server maps to a file it indexed at
startup — no raw paths from the page, so no path traversal. No data leaves the
machine.
"""
import sys, os, re, io, json, html, glob, argparse, datetime, threading, webbrowser, subprocess

# --- repo layout: make the sibling code dirs importable by bare name -----------
import os as _o, sys as _s
_d = _o.path.dirname(_o.path.abspath(__file__))
_r = _o.path.dirname(_d) if _o.path.basename(_d) in ('tools', 'gui', 'mindat') else _d
for _x in ('tools', 'mindat', 'gui'):
    _p = _o.path.join(_r, _x)
    if _o.path.isdir(_p) and _p not in _s.path:
        _s.path.insert(0, _p)
# -------------------------------------------------------------------------------
import cell_lambda_check as C
import extra_checks as X
import annotate_review as A

try:
    from flask import Flask, jsonify, request, send_file, abort, Response
except ImportError:
    sys.exit("Flask is not installed — run: pip3 install -r requirements.txt "
             "(the GUI needs Flask; the CLI checks do not).")

HERE = os.path.dirname(os.path.abspath(__file__))   # the gui/ folder
ROOT = os.path.dirname(HERE)                          # repo root (tools/ is a sibling)
app = Flask(__name__, static_folder=os.path.join(HERE, 'static'),
            static_url_path='/static')

# ------------------------------------------------------------------ global state
# Set once at launch (single batch per process). `docx` is keyed by the docx
# basename STEM, which is unique within a folder and stable across reloads — the
# only identifier the browser ever sends back.
STATE = {
    'folder': None, 'out_dir': None,
    'docx': {},                    # key -> docx path
    'order': [],                   # keys, sorted
    'pdf': {}, 'cif': {}, 'dft': {},   # eid -> path
    'cache': {},                   # key -> {'fp': fingerprint, 'data': serialized}
    'triage': {},                  # key -> reviewer verdicts (separate sidecar)
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

def _pdf_scan(pdf_path, terms):
    """(n_pages, best_evidence_page) — the page with the most hits for `terms`."""
    import fitz
    best_pg, best_hits, n = 0, -1, 0
    try:
        doc = fitz.open(pdf_path)
        n = doc.page_count
        if terms:
            for i in range(n):
                hits = sum(len(doc[i].search_for(t)) for t in terms)
                if hits > best_hits:
                    best_hits, best_pg = hits, i
        doc.close()
    except Exception:
        pass
    return n, (best_pg if best_hits > 0 else 0)

def _cand(cd):
    if cd is None:
        return None
    return {'a': cd.a, 'b': cd.b, 'c': cd.c, 'al': cd.al, 'be': cd.be, 'ga': cd.ga,
            'V': cd.V, 'Z': cd.Z, 'context': cd.context, 'phase': cd.phase,
            'snippet': (cd.snippet or '').strip()}

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
        import mindat
        g = mindat.group_of(name)
        if g:
            block['group'], _strunz, block['matched_species'], block['ima_status'] = g
    except Exception:
        pass
    return block

# ------------------------------------------------------------------ serialization
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
        cell.update({'matched': _cand(cd), 'nmatch': cellt[2], 'ncomp': cellt[3],
                     'dev': cellt[4], 'mode': cellt[5]})
        cell['deltas'] = [list(t) for t in C.cell_axis_deltas(d.authors_cell, cd)]

    # which extra findings actually get written into the docx (same gate the
    # annotator uses); everything else is console-only.
    writable = {id(f) for f in A._writable_extras(res)}
    findings = [{'idx': i, 'code': f.code, 'sev': f.sev, 'anchor': f.anchor,
                 'msg': _u(f.msg), 'written': id(f) in writable,
                 'major': f.code not in LOW_PRIORITY_CODES}
                for i, f in enumerate(res.get('extra', []))]

    ent = None
    if entry:
        ent = {'name': entry.name, 'primary': entry.primary,
               'crystal_system': entry.crystal_system, 'space_group': entry.space_group,
               'cell': entry.cell, 'instr': entry.instr,
               'formulas': {k: _u(v) for k, v in entry.formulas.items()},
               'comments': {k: _u(v) for k, v in entry.comments.items()},
               'subfiles': entry.subfiles, 'refl_count': len(entry.refl)}

    # Always show the natural-species Mindat record; the UI notes that for a
    # synthetic the tool deliberately skips the Mindat CELL compare (the formula
    # check still applies, so the record is still worth showing).
    mindat = _mindat_block(name)

    pdfinfo = None
    if pdf:
        terms = _value_terms(d.authors_cell)
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
# Bump when the serialized shape / badge logic changes, so a stale on-disk cache
# (keyed only by source-file mtimes) is invalidated after a code change.
CACHE_VERSION = 4

def _fingerprint(key):
    path = STATE['docx'][key]; eid = C.entry_id(path)
    parts = [path, STATE['pdf'].get(eid), STATE['cif'].get(eid), STATE['dft'].get(eid)]
    fp = [CACHE_VERSION]
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
        with open(_cache_path()) as f:
            STATE['cache'] = json.load(f)
    except Exception:
        STATE['cache'] = {}

def _save_cache():
    try:
        os.makedirs(STATE['out_dir'], exist_ok=True)
        with open(_cache_path(), 'w') as f:
            json.dump(STATE['cache'], f)
    except Exception as ex:
        print('  !! could not write gui_cache.json: %s' % ex)

# ------------------------------------------------------------------ triage sidecar
def _triage_path():
    return os.path.join(STATE['out_dir'], 'triage.json')

def _load_triage():
    try:
        with open(_triage_path()) as f:
            STATE['triage'] = json.load(f)
    except Exception:
        STATE['triage'] = {}

def _save_triage():
    with STATE['lock']:
        os.makedirs(STATE['out_dir'], exist_ok=True)
        with open(_triage_path(), 'w') as f:
            json.dump(STATE['triage'], f, indent=1)

# ------------------------------------------------------------------ indexing / launch
def build_index(folder, out_dir):
    STATE['folder'] = os.path.abspath(folder)
    STATE['out_dir'] = os.path.abspath(out_dir or os.path.join(folder, 'review_out'))
    try:
        import mindat; mindat.refresh_struct_if_stale()
    except Exception:
        pass
    STATE['pdf'] = C.pdf_index(folder)
    STATE['cif'] = C.cif_index(folder)
    STATE['dft'] = C.dft_index(folder)
    docs = sorted(f for f in glob.glob(os.path.join(folder, '*.docx'))
                  if not os.path.basename(f).startswith('~$'))
    STATE['docx'] = {os.path.splitext(os.path.basename(d))[0]: d for d in docs}
    STATE['order'] = list(STATE['docx'].keys())
    _load_cache(); _load_triage()

def analyze_all():
    """Eager pass at launch so the dashboard's attention badges are populated the
    moment it opens (the badges ARE the silent-failure surfacing — they must not
    wait for per-entry visits). Cached results are reused; only changed entries
    re-run."""
    n = len(STATE['order'])
    print('[review_gui] analyzing %d entr%s in %s'
          % (n, 'y' if n == 1 else 'ies', STATE['folder']))
    for i, key in enumerate(STATE['order'], 1):
        try:
            data = get_analysis(key)
            tags = ' '.join('[%s]' % x['label'] for x in data['badges']
                            if x['level'] in ('danger', 'warn'))
        except Exception as ex:
            tags = '!! ' + str(ex)
        print('  [%2d/%2d] %-9s %-34s %s'
              % (i, n, C.entry_id(STATE['docx'][key]) or '?',
                 (STATE['cache'].get(key, {}).get('data', {}).get('name') or key)[:34], tags))
    _save_cache()

# ------------------------------------------------------------------ routes
@app.route('/')
def index():
    return send_file(os.path.join(HERE, 'index.html'))

@app.route('/api/entries')
def api_entries():
    rows = []
    for key in STATE['order']:
        d = get_analysis(key)
        badges = d['badges']
        rows.append({'key': key, 'eid': d['eid'], 'name': d['name'],
                     'files': d['files'], 'badges': badges,
                     'status': d['cell']['status'],
                     'fixes': d.get('fixes', 0),
                     'attention': _attention(badges),
                     'reviewed': bool(STATE['triage'].get(key, {}).get('reviewed'))})
    # primary lens = the major fixes; silent-failures/near-misses are the tiebreak.
    rows.sort(key=lambda r: (-r['fixes'], -r['attention'], r['eid'] or ''))
    return jsonify({'folder': STATE['folder'], 'out_dir': STATE['out_dir'], 'entries': rows})

@app.route('/api/entry/<key>')
def api_entry(key):
    if key not in STATE['docx']:
        abort(404)
    d = get_analysis(key)
    return jsonify({'analysis': d, 'triage': STATE['triage'].get(key, {})})

@app.route('/api/pdf/<key>/search')
def api_pdf_search(key):
    pdf = _pdf_path(key)
    if not pdf:
        abort(404)
    q = (request.args.get('q') or '').strip()
    if not q:
        return jsonify({'hits': []})
    import fitz
    hits = []
    try:
        doc = fitz.open(pdf)
        for i in range(doc.page_count):
            rects = doc[i].search_for(q)
            if rects:
                hits.append({'page': i, 'count': len(rects)})
        doc.close()
    except Exception as ex:
        return jsonify({'error': str(ex), 'hits': []})
    return jsonify({'hits': hits})

@app.route('/api/pdf/<key>/page/<int:n>.png')
def api_pdf_page(key, n):
    pdf = _pdf_path(key)
    if not pdf:
        abort(404)
    terms = [t for t in (request.args.get('find') or '').split('|') if t]
    import fitz
    try:
        doc = fitz.open(pdf)
        if n < 0 or n >= doc.page_count:
            doc.close(); abort(404)
        page = doc[n]
        for t in terms:
            for rect in page.search_for(t):
                page.add_highlight_annot(rect)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        png = pix.tobytes('png')
        doc.close()
    except Exception:
        abort(500)
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
    import fitz
    try:
        doc = fitz.open(pdf)
        if n < 0 or n >= doc.page_count:
            doc.close(); abort(404)
        page = doc[n]
        rects = []
        for t in terms:
            rects += list(page.search_for(t))
        pr = page.rect
        fw, fh = pr.width * 0.52, pr.height * 0.26          # ~half-column wide, quarter tall
        if rects:
            x0 = min(r.x0 for r in rects); y0 = min(r.y0 for r in rects)
            x1 = max(r.x1 for r in rects); y1 = max(r.y1 for r in rects)
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            halfw = max(fw / 2, (x1 - x0) / 2 + 12)          # never smaller than the hit span
            halfh = max(fh / 2, (y1 - y0) / 2 + 12)
        else:
            cx, cy, halfw, halfh = pr.width / 2, pr.height * 0.28, fw / 2, fh / 2
        cx = min(max(cx, pr.x0 + halfw), pr.x1 - halfw)      # keep the clip inside the page
        cy = min(max(cy, pr.y0 + halfh), pr.y1 - halfh)
        clip = fitz.Rect(cx - halfw, cy - halfh, cx + halfw, cy + halfh) & pr
        for t in terms:
            for r in page.search_for(t):
                page.add_highlight_annot(r)
        pix = page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=clip)
        png = pix.tobytes('png')
        doc.close()
    except Exception:
        abort(500)
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
    return [sys.executable, os.path.join(ROOT, 'tools', 'annotate_review.py'), STATE['folder'],
            '--triage', _triage_path()] + extra

def _run_annotate(cmd):
    # ensure the sidecar the rerun consumes is on disk
    _save_triage()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=1800)
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
    with open(path, 'w') as fh:
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
def main():
    ap = argparse.ArgumentParser(description='Local review-mode GUI for the PXRD review tool.')
    ap.add_argument('folder', help='the entries folder (same one passed to annotate_review.py)')
    ap.add_argument('--port', type=int, default=5000)
    ap.add_argument('--out', help='sidecar/output folder (default <folder>/review_out)')
    ap.add_argument('--no-browser', action='store_true', help='do not auto-open the browser')
    args = ap.parse_args()

    if not os.path.isdir(args.folder):
        sys.exit('not a folder: %s' % args.folder)
    build_index(args.folder, args.out)
    if not STATE['order']:
        sys.exit('no .docx entries found in %s' % args.folder)
    analyze_all()

    url = 'http://127.0.0.1:%d/' % args.port
    print('\n[review_gui] serving on %s  (localhost only — Ctrl-C to stop)' % url)
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    # 127.0.0.1 bind keeps it off the network; debug OFF (no code-exec debugger).
    app.run(host='127.0.0.1', port=args.port, debug=False)

if __name__ == '__main__':
    main()
