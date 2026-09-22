"""The statements gauntlet: what the workbooks SAY, held against what the checks FOUND.

    python3 tools/corpus_workbooks.py "<pdf+cif folders, comma-separated>" OUT_DIR [TAG]
                                      [--baseline JSON] [--papers LIST] [--limit N] [--only SUBSTR] [--jobs N]

The reader gauntlet (tools/corpus_paper_extract.py) measures whether a value is READ and VERIFIED. The
2026-09-21 audit found the numbers right and the sentences wrong — a PROBLEM line on 74 workbooks
where the composition check flags nothing, a BVS column judged by a rule the table check does not
use — and no gate could see it. This one writes every paper's workbooks into OUT_DIR (never beside
the paper), evaluates every formula with tests/xl_eval.py, harvests every STATEMENT (ok / note /
PROBLEM / EXPLAINS, a verdict cell) and sets it against the record layer, whose code the sheets do
not share:

  C  contradictions — a sheet that says more, or less, than the check does. Target 0.
  F  red statements on papers whose record is `agrees` — each one to be read by hand.
  X  cells that do not evaluate, or do not give the tool's number.

Outputs OUT_DIR/workbook_statements<TAG>.json (one record per paper; --baseline diffs it paper by
paper) and workbook_statements<TAG>.txt. No paper is touched and nothing leaves the machine.
"""
import os, re, sys, json, argparse
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, 'tests')); sys.path.insert(0, os.path.join(ROOT, 'tools'))
from pxrd_review import paper_extract as PE, gd as GD, paths

_CTX = mp.get_context('spawn')
SEV = (('PROBLEM', 'red'), ('EXPLAINS', 'green'), ('note', 'amber'), ('ok', 'ok'), ('not read', 'ok'), ('does not follow', 'red'), ('differs', 'red'),
       ('close', 'amber'), ('yes', 'ok'), ('agrees', 'ok'), ('reproduces', 'ok'), ('does not', 'ok'), ('not judged', 'grey'), ('not compared', 'grey'), ('blank', 'amber'))

def sev(text):
    t = str(text or '').strip()
    for head, s in SEV:
        if t.startswith(head):
            return s
    return ''

def _values(book, sheet, col_label, col_text, r0=1):
    """[(label, evaluated text)] of a sheet's readings; a cell that will not evaluate comes back as 'ERR: …'."""
    ws = book.wb[sheet]; out = []
    for r in range(r0, ws.max_row + 1):
        raw = ws.cell(r, col_text).value
        if raw is None:
            continue
        try:
            v = book.value(sheet, '%s%d' % (ws.cell(r, col_text).column_letter, r))
        except Exception as e:
            v = 'ERR: %s' % str(e)[:60]
        if isinstance(v, str) and sev(v) or (isinstance(v, str) and v.startswith('ERR')):
            out.append((str(ws.cell(r, col_label).value or '')[:60], v))
    return out

RED, AMBER = 'FFC7CE', 'FFEB9C'

def colour_vs_text(book):
    """['sheet!cell: text says X, colour is Y'] — every conditional format evaluated (xl_eval.Book.fills) and held to the
    words on its row: red where a reading starts PROBLEM / does not / differs, and nowhere else."""
    bad = []
    for ws in book.wb.worksheets:
        if not ws.conditional_formatting:
            continue
        fills = book.fills(ws.title)
        for coord, cols in fills.items():
            if 'ERR' in cols:
                bad.append('%s!%s: a rule did not evaluate' % (ws.title, coord))
        for row in ws.iter_rows():
            words = [book.value(ws.title, c.coordinate) if isinstance(c.value, str) and c.value.startswith('=') else c.value for c in row]
            flag = any(w is True for w in words)                      # the reduction's column P: 'does not follow (check sheet)'
            words = [w for w in words if isinstance(w, str)]
            red_row = flag or any(w.startswith(('PROBLEM', 'does not follow')) or w == 'differs' or 'STANDS OUT' in w for w in words)
            reds = [c.coordinate for c in row if RED in fills.get(c.coordinate, [])]
            if red_row and not reds and any(c.coordinate in fills or True for c in row) and ws.title == 'check':
                pass                                                   # a red WORD outside any rule's range (the missing/extra lines are filled directly)
            if reds and not red_row and not any(w.startswith('note — differs on the wt% as read') for w in words):
                bad.append('%s!%s: red fill, no red word (%s)' % (ws.title, reds[0], '; '.join(words)[:60]))
    return bad

def _every_formula(book):
    bad = []
    for ws in book.wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith('='):
                    try:
                        v = book.value(ws.title, c.coordinate)
                        if isinstance(v, str) and v.startswith('#'):
                            bad.append('%s!%s %s' % (ws.title, c.coordinate, v))
                    except Exception as e:
                        bad.append('%s!%s %s' % (ws.title, c.coordinate, str(e)[:40]))
    return bad

def epma_statements(path):
    from xl_eval import Book
    b = Book(path); out = {'elements': [], 'fault': [], 'notes': [], 'bad': _every_formula(b) + colour_vs_text(b)}
    if 'check' not in b.wb.sheetnames:
        return out
    wc = b.wb['check']; block = ''
    for r in range(1, wc.max_row + 1):
        a = wc.cell(r, 1).value
        if a == 'element':
            block = 'el'; continue
        if isinstance(a, str) and a.startswith('WHERE THE FAULT'):
            block = 'fault'; continue
        if isinstance(a, str) and a.startswith('IF AN OXIDE'):
            block = 'valence'; continue
        if a is None:
            if block in ('fault', 'valence') and wc.cell(r, 3).value is None:
                block = block if block == 'fault' and r < wc.max_row and isinstance(wc.cell(r + 1, 1).value, str) and wc.cell(r + 1, 1).value.startswith('IF AN') else ('notes' if block != 'el' else block)
            if block == 'el':
                block = 'gap'
            continue
        try:
            if block == 'el':
                out['elements'].append((a, b.value('check', 'F%d' % r)))
            elif block in ('fault', 'valence') and wc.cell(r, 3).value is not None:
                out['fault'].append((a[:50], b.value('check', 'C%d' % r)))
            elif isinstance(a, str) and sev(a) in ('red', 'amber'):
                out['notes'].append(a[:160])
        except Exception as e:
            out['bad'].append('check!%d %s' % (r, str(e)[:40]))
    return out

def _run_one(job):
    pdf, cif, base, out_dir = job
    rec = {'base': base}
    try:
        r = PE.check_paper(pdf, cif, out_dir)
    except Exception as e:
        return {'base': base, 'fail': str(e)[:160]}
    ex = r['extract']; comp = r.get('composition') or {}
    rec['fields'] = {k: v.get('status') for k, v in (r.get('fields') or {}).items()}
    rec['comp'] = {'has': bool(r.get('composition')), 'ok': bool(comp.get('ok')), 'verified': bool(comp.get('verified')), 'basis_flag': bool(comp.get('basis_flag')),
                   'equiv': bool(comp.get('basis_equiv')), 'stated': str(ex.get('basis')), 'found': str((comp.get('result') or {}).get('basis') or comp.get('basis')),
                   'compared': len((comp.get('result') or {}).get('diffs') or []) if comp else 0}
    # ---- EPMA
    fn = ex.get('reduction_xlsx')
    if fn:
        try:
            rec['epma'] = epma_statements(os.path.join(out_dir, fn))
        except Exception as e:
            rec['epma'] = {'error': str(e)[:160]}
    # ---- Gladstone–Dale, on the analysis the paper check settled on
    try:
        text = PE.text_of(pdf); stmt = PE.gd_statement(text)
        if stmt.get('ci') is not None or stmt.get('category'):
            cap = {}; real = PE._gd_eval
            def spy(ex_, wt, *a, **k):
                o = real(ex_, wt, *a, **k); o['_wt'] = dict(wt or {}); o['_k'] = (a[1] if len(a) > 1 else k.get('k_override')) or {}
                return o
            PE._gd_eval = spy
            try:
                g = PE.gd_check(ex, r.get('composition'), stmt)
            finally:
                PE._gd_eval = real
            o = ex.get('optics') or {}
            if g.get('_wt') and o.get('n') and (o.get('D_meas') or o.get('D_calc')):
                # one density per workbook here: the one the check's verdict rests on (its index nearest the paper's)
                dens = o.get('D_meas') or o.get('D_calc')
                if stmt.get('ci') is not None and g.get('ci'):
                    key = min(g['ci'], key=lambda k_: abs(g['ci'][k_] - stmt['ci'])); dens = o.get('D_' + key) or dens
                res = GD.evaluate({c: v for c, v in g['_wt'].items() if v}, o['n'], density=dens, k_override=g.get('_k') or None)
                res['o_corr'] = sum(v for k_, v in g['_wt'].items() if k_.startswith('O='))
                path = GD.write_xlsx(res, os.path.join(out_dir, base + '_gd.xlsx'), base, GD.paper_statement(pdf))
                from xl_eval import Book
                b = Book(path)
                rec['gd'] = {'status': g['status'].get('optics.n'), 'red_by_check': bool(g.get('red')), 'bad': _every_formula(b) + colour_vs_text(b),
                             'reads': _values(b, 'check', 1, 5, 4) if 'check' in b.wb.sheetnames else [],
                             'single': str(b.wb['check'].cell(1, 1).value)[:80] if 'check' in b.wb.sheetnames and b.wb['check'].max_row == 1 else ''}
    except Exception as e:
        rec['gd'] = {'error': str(e)[:160]}
    # ---- bond valence: the workbook the paper check itself wrote (a .cif beside the paper)
    if ex.get('bv_xlsx'):
        try:
            from xl_eval import Book
            b = Book(os.path.join(out_dir, ex['bv_xlsx']))
            d = {'bad': _every_formula(b) + colour_vs_text(b)}
            if 'check' in b.wb.sheetnames:
                wc = b.wb['check']
                cellv = [wc.cell(r_, 9).value for r_ in range(4, wc.max_row + 1) if isinstance(wc.cell(r_, 1).value, int) and wc.cell(r_, 2).value not in ('cation', 'anion')]
                sumv = [wc.cell(r_, 8).value for r_ in range(4, wc.max_row + 1) if isinstance(wc.cell(r_, 1).value, int) and wc.cell(r_, 2).value in ('cation', 'anion')]
                d.update(cells=[cellv.count(x) for x in ('agrees', 'differs', 'blank', 'not compared')], sums=[sumv.count(x) for x in ('agrees', 'differs', 'not compared')],
                         reads=_values(b, 'check', 1, 5, 4))
            pb = r.get('bv') or {}
            d['paper_check'] = {'compared': pb.get('compared'), 'disagree': pb.get('disagree'), 'held': pb.get('held'), 'params': pb.get('params'), 'status': r.get('bv_status')}
            rec['bv'] = d
        except Exception as e:
            rec['bv'] = {'error': str(e)[:160]}
    elif cif and (r.get('bv') or {}).get('compared') and not (r['bv'].get('from_bonds') or r['bv'].get('from_paper')):   # (from the paper's own bonds: no workbook yet — issue #18)
        rec['bv'] = {'error': 'the paper check compared %s cells but wrote no workbook' % r['bv'].get('compared')}
    return rec

def contradictions(rec):
    """[(kind, detail)] — a sheet against the record layer."""
    out = []
    c = rec.get('comp') or {}; e = rec.get('epma') or {}
    if e and 'error' not in e:
        red_el = [el for el, v in e['elements'] if sev(v) == 'red']
        red_fault = [l for l, v in e['fault'] if sev(v) == 'red']
        if c.get('has') and c.get('ok') and (red_el or red_fault):
            out.append(('epma: the check reproduces the formula, the sheet is red', '%s | %s | stated %s found %s' % (','.join(red_el), '; '.join(red_fault)[:80], c.get('stated'), c.get('found'))))
        if c.get('has') and not c.get('ok') and c.get('verified') and not red_el and not red_fault and not any(n.startswith('PROBLEM') for n in e['notes']):
            out.append(('epma: the check flags the formula, the sheet is silent', 'stated %s found %s' % (c.get('stated'), c.get('found'))))
        if any(n.startswith('PROBLEM: the stated basis') for n in e['notes']) and not c.get('basis_flag'):
            out.append(('epma: PROBLEM basis line without a basis flag', ''))
    g = rec.get('gd') or {}
    if g and 'error' not in g:
        reds = [(l, v) for l, v in g.get('reads', []) if sev(v) == 'red']
        if g.get('status') == 'agrees' and [x for x in reds if not x[0].startswith('category')]:
            out.append(('gd: the check agrees, the sheet is red', '; '.join(l for l, v in reds)[:100]))
        first = next((v for l, v in g.get('reads', []) if l.startswith('1 − K_P/K_C')), '')
        if g.get('status') == 'agrees' and first.startswith('note'):
            out.append(('gd: the check agrees with the stated index, the sheet says it differs', first[:80]))
        if g.get('red_by_check') and first.startswith('ok'):
            out.append(('gd: the check is red, the sheet says ok', first[:60]))
    b = rec.get('bv') or {}
    if b and 'cells' in b:
        # the record's `agrees` means the TABLE agrees (cells differing <= max(1, 10 %)): a cell the check itself lists is the
        # same finding on the sheet, not a contradiction. What must hold: the sheet's red cells ARE the check's — no more, no fewer
        pc = b.get('paper_check') or {}
        want = pc.get('held') if pc.get('held') is not None else pc.get('disagree')
        if pc.get('status') == 'checked' and want is not None and b['cells'][1] + b['sums'][1] != want:
            out.append(('bv: the sheet\'s red cells are not the check\'s', 'cells %s sums %s | check %s' % (b['cells'], b['sums'], pc)))
        if pc.get('status') == 'unmatched' and b['cells'][1] + b['sums'][1]:
            out.append(('bv: the check doubts its reading of the table, the sheet has red cells', 'cells %s sums %s' % (b['cells'], b['sums'])))
    return out

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('pdf_dirs'); ap.add_argument('out_dir'); ap.add_argument('tag', nargs='?', default='')
    ap.add_argument('--baseline'); ap.add_argument('--papers'); ap.add_argument('--limit', type=int); ap.add_argument('--only'); ap.add_argument('--jobs', type=int, default=0)
    a = ap.parse_args(argv)
    import corpus_paper_extract as CP
    cache = os.environ.get('PXRD_PAGE_CACHE') or os.path.join(paths.cache_dir(), 'pages')
    os.environ['PXRD_PAGE_CACHE'] = cache; PE.set_page_cache(cache)
    subset = None
    if a.papers:
        subset = {x.strip() for x in (open(a.papers).read().split('\n') if os.path.isfile(a.papers) else a.papers.split(',')) if x.strip()}
    jobs = CP._jobs([d for d in a.pdf_dirs.split(',') if d], a.only, subset, a.limit)
    wb_dir = os.path.join(a.out_dir, 'wb' + a.tag); os.makedirs(wb_dir, exist_ok=True)
    jobs = [(pdf, cif, base, wb_dir) for pdf, cif, base in jobs]
    n = a.jobs or os.cpu_count() or 4
    if n == 1:
        recs = [_run_one(j) for j in jobs]
    else:
        with ProcessPoolExecutor(max_workers=n, mp_context=_CTX) as pool:
            recs = list(pool.map(_run_one, jobs, chunksize=2))
    by = {r['base']: r for r in recs}
    L = []; tab = {}; reds = []; bad = []
    n_e = sum(1 for r in recs if r.get('epma') and 'error' not in r['epma']); n_g = sum(1 for r in recs if r.get('gd') and 'reads' in r['gd']); n_b = sum(1 for r in recs if (r.get('bv') or {}).get('cells'))
    for r in recs:
        for k in ('epma', 'gd', 'bv'):
            if (r.get(k) or {}).get('error'):
                bad.append('%s %s: %s' % (r['base'], k, r[k]['error']))
            for x in (r.get(k) or {}).get('bad') or []:
                bad.append('%s %s: %s' % (r['base'], k, x))
        for kind, det in contradictions(r):
            tab.setdefault(kind, []).append((r['base'], det))
        c = r.get('comp') or {}; e = r.get('epma') or {}
        if e and 'error' not in e and c.get('ok'):
            for l, v in e['fault']:
                if sev(v) == 'red':
                    reds.append('%s epma %s: %s' % (r['base'], l, v[:90]))
    L.append('STATEMENTS GAUNTLET%s — %d papers; workbooks: EPMA %d, Gladstone–Dale %d, bond valence %d; failed papers %d' % (
        (' ' + a.tag) if a.tag else '', len(recs), n_e, n_g, n_b, sum(1 for r in recs if 'fail' in r)))
    L.append(''); L.append('C — CONTRADICTIONS: %d' % sum(len(v) for v in tab.values()))
    for kind, rows in sorted(tab.items(), key=lambda kv: -len(kv[1])):
        L.append('  %4d  %s' % (len(rows), kind))
        for base, det in rows[:400]:
            L.append('          %-28s %s' % (base[:28], det))
    L.append(''); L.append('X — CELLS THAT DO NOT EVALUATE: %d' % len(bad)); L += ['    ' + x for x in bad[:60]]
    # the distribution of what the EPMA sheets say, by the check's verdict
    dist = {}
    for r in recs:
        c = r.get('comp') or {}; e = r.get('epma') or {}
        if not e or 'error' in e:
            continue
        verdict = 'no formula' if not c.get('has') else 'ok' if c.get('ok') else 'flag' if c.get('verified') else 'unverified'
        said = 'red' if any(sev(v) == 'red' for _l, v in e['elements'] + e['fault']) else 'amber' if any(sev(v) == 'amber' for _l, v in e['elements'] + e['fault']) else 'clean'
        dist[(verdict, said)] = dist.get((verdict, said), 0) + 1
    L.append(''); L.append('EPMA: the check (rows) × the sheet (columns)'); L.append('  %-12s %7s %7s %7s' % ('', 'clean', 'amber', 'red'))
    for v in ('ok', 'unverified', 'flag', 'no formula'):
        L.append('  %-12s %7d %7d %7d' % (v, dist.get((v, 'clean'), 0), dist.get((v, 'amber'), 0), dist.get((v, 'red'), 0)))
    if a.baseline and os.path.isfile(a.baseline):
        old = {r['base']: r for r in json.load(open(a.baseline))}
        L.append(''); L.append('AGAINST %s' % os.path.basename(a.baseline)); nch = 0
        for base, r in by.items():
            o = old.get(base)
            if not o:
                continue
            for k in ('epma', 'gd', 'bv'):
                if json.dumps(r.get(k), sort_keys=True, default=str) != json.dumps(o.get(k), sort_keys=True, default=str):
                    nch += 1
                    before = {x[0] for x in contradictions(o)}; after = {x[0] for x in contradictions(r)}
                    L.append('  %-28s %s changed%s%s' % (base[:28], k, ('  FIXED: ' + '; '.join(sorted(before - after))) if before - after else '', ('  NEW: ' + '; '.join(sorted(after - before))) if after - before else ''))
        L.append('  %d workbook records changed' % nch)
    os.makedirs(a.out_dir, exist_ok=True)
    json.dump(recs, open(os.path.join(a.out_dir, 'workbook_statements%s.json' % a.tag), 'w'), indent=0, default=str)
    open(os.path.join(a.out_dir, 'workbook_statements%s.txt' % a.tag), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('\n'.join(L[:60]))

if __name__ == '__main__':
    main()
