"""Recall, not precision: how big does a fault have to be before the tool says so?

Every threshold in this tool was tuned by mining the CORRECTED corpus for false positives, so
every number we have is a precision number. Nothing measures the other side: of the faults a
paper could carry, which ones would the tool actually catch? This answers that by taking papers
whose checks currently PASS, injecting one fault of a known size, and recording whether the check
fires.

    python3 tools/seed_faults.py "<pdf+cif folders, comma-separated>" [--out DIR] [--tag TAG]
                                 [--papers LIST] [--limit N] [--only SUBSTR] [--jobs N]

No paper is touched. The fault is injected into the values already read from it, in memory, so
what is measured is the CHECK's recall given a correct read — the reader's own coverage is a
separate number (tools/corpus_paper_extract.py). Four faults, each the kind a real paper carries:

  formula  one coefficient of the published empirical formula scaled — the mistyped coefficient a
           reviewer most often finds
  wt%      one constituent's weight percent scaled — a mistyped digit in the analysis table. Note
           that normalising to a fixed basis DILUTES this one: a 20 % error in a single oxide moves
           the coefficients by much less, so it is a weaker fault than it sounds
  d        one calculated d-spacing scaled — a mistyped line in the powder table
  basis    the stated normalisation changed to a neighbouring one — 21 O written for 22 O

Each is seeded at a ladder of sizes, so the output is not one number but a detection curve: the
size at which each check starts to fire. An outcome is
  CAUGHT  the finding would be written into the review (a flag),
  NOTED   it reaches the console as an unverified note only,
  MISSED  the check still passes.
"""
import os, re, sys, csv, copy, glob, argparse
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pxrd_review import paper_extract as PE

_CTX = mp.get_context('spawn')

WT_SIZES = (0.01, 0.02, 0.05, 0.10, 0.20)          # relative, on the largest constituent
D_SIZES = (0.005, 0.01, 0.02, 0.03, 0.05)          # relative, on the strongest calculated line
BASIS_FAULTS = ('+1', '-1', 'x2')                  # 21 O -> 22 O, 21 O -> 20 O, 21 O -> 42 O
F_SIZES = (0.02, 0.05, 0.10, 0.20)                 # relative, on one coefficient of the published formula


# ----------------------------------------------------------------------------- the four faults

def _seed_wt(ex, frac):
    """Scale the largest constituent by (1 + frac), in every column it appears in — a wt% that is
    simply wrong, which the column-by-fit fallback cannot rescue. -> (ex, what was changed)."""
    ex = copy.deepcopy(ex)
    rows = (ex.get('epma') or {}).get('rows') or []
    if not rows:
        return None, None
    i = max(range(len(rows)), key=lambda k: rows[k].get('mean') or 0)
    r = rows[i]
    was = r['mean']
    k = 1 + frac
    r['mean'] = round(was * k, 4)
    if r.get('all'):
        r['all'] = [round(v * k, 4) if v else v for v in r['all']]
    # the row's own range and s.d. move with it: a paper whose printed mean fell outside its own
    # printed range would be caught by that alone, which is a different fault than the one meant here
    if r.get('range') and len(r['range']) == 2:
        r['range'] = tuple(round(v * k, 4) for v in r['range'])
    if r.get('sd'):
        r['sd'] = round(r['sd'] * k, 4)
    return ex, '%s %g -> %g' % (r['constituent'], was, r['mean'])


def _seed_d(ex, frac):
    """Scale the strongest calculated line's d by (1 + frac) — a mistyped d against its own
    indices. -> (ex, what was changed, the hkl that now lies)."""
    ex = copy.deepcopy(ex)
    obs, calc, pages = ex['_table']
    if not calc:
        return None, None, None
    i = max(range(len(calc)), key=lambda k: (calc[k][1] if calc[k][1] is not None else -1))
    d, I, hkl = calc[i]
    calc = list(calc); calc[i] = (round(d * (1 + frac), 4), I, hkl)
    ex['_table'] = (obs, calc, pages)
    return ex, '%g -> %g (%d %d %d)' % (d, calc[i][0], hkl[0], hkl[1], hkl[2]), hkl


def _seed_formula(fc, frac):
    """Scale the largest cation coefficient of the paper's published formula by (1 + frac) — the
    fault a reviewer most often finds, a mistyped coefficient. Injected into the parsed formula
    candidate rather than the page text, so the reader is not what is under test.
    -> (candidate, what was changed)."""
    fc = copy.deepcopy(list(fc))
    counts = fc[1]
    cands = [(v, k) for k, v in counts.items() if k not in ('H', 'O') and v and v > 0.1]
    if not cands:
        return None, None
    was, el = max(cands)
    counts[el] = round(was * (1 + frac), 4)
    return tuple(fc), '%s %g -> %g' % (el, was, counts[el])


def _seed_basis(ex, kind):
    """Change the stated basis to a neighbouring one — the paper says 21 O and means 22.
    -> (ex, what was changed)."""
    ex = copy.deepcopy(ex)
    b = ex.get('basis')
    if not b or not isinstance(b, (tuple, list)) or len(b) != 2:
        return None, None
    what, n = b[0], b[1]
    try:
        n = float(n)
    except (TypeError, ValueError):
        return None, None
    new = {'+1': n + 1, '-1': n - 1, 'x2': n * 2}[kind]
    if new <= 0:
        return None, None
    ex['basis'] = (what, new)
    return ex, '%s %g -> %g' % (what, n, new)


# ----------------------------------------------------------------------------- one paper

def _verdict_comp(comp):
    """A composition result -> 'caught' (a flag the review writes) | 'noted' | 'missed'."""
    if not comp:
        return 'missed'
    if comp['ok']:
        return 'missed'
    return 'caught' if comp.get('verified') else 'noted'


def _verdict_powder(cc, hkl):
    """Did the powder check name the line we broke? 'caught' when it is a red line, 'noted' when
    it is only the sits-N%-off note or a doubt about the table as a whole."""
    if not cc or cc.get('status') != 'checked':
        return 'noted'
    if any(tuple(r[2]) == tuple(hkl) for r in (cc.get('bad') or [])):
        return 'caught'
    tag = '(%d %d %d)' % (hkl[0], hkl[1], hkl[2])
    for ln in cc.get('lines') or []:
        if tag in ln or 'do not follow the cell' in ln or 'follows no cell' in ln:
            return 'noted'
    return 'missed'


def _run_one(job):
    """Seed every fault into one paper -> {'base', 'rows': [(kind, size, outcome, detail)], ...}.
    A fault is only seeded where the check PASSES on the paper as published: seeding into an
    already-failing check measures nothing."""
    pdf, cif, base = job
    try:
        ex = PE.extract(pdf, None, None, write=False)
        text = PE.text_of(pdf)
    except Exception as e:
        return {'base': base, 'rows': [], 'skip': 'could not read (%s)' % e}
    rows = []; seeded = set()
    try:
        comp0 = PE.check_composition(ex, text)
    except Exception:
        comp0 = None
    has_apfu = bool((ex.get('epma') or {}).get('apfu'))
    # a coefficient of the published formula, injected into the parsed candidate: the check is
    # _check_formula, the same one check_composition runs, with the candidate it would have chosen
    try:
        cands = PE._formulas(text, ex.get('name') or '')
        fc0 = cands[0] if cands else None
        base_f = PE._check_formula(ex, text, fc0) if fc0 else None
    except Exception:
        fc0 = base_f = None
    if fc0 and base_f and base_f['ok']:
        seeded.add('formula')
        for frac in F_SIZES:
            hurt, what = _seed_formula(fc0, frac)
            if hurt is None:
                seeded.discard('formula'); break
            try:
                v = _verdict_comp(PE._check_formula(ex, text, hurt))
            except Exception as e:
                v = 'error: %s' % e
            rows.append(('formula', frac, v, what, has_apfu))
    if comp0 and comp0['ok']:
        seeded.add('wt%')
        for frac in WT_SIZES:
            hurt, what = _seed_wt(ex, frac)
            if hurt is None:
                seeded.discard('wt%'); break
            try:
                v = _verdict_comp(PE.check_composition(hurt, text))
            except Exception as e:
                v = 'error: %s' % e
            rows.append(('wt%', frac, v, what, has_apfu))
        if ex.get('basis'):
            seeded.add('basis')
            for kind in BASIS_FAULTS:
                hurt, what = _seed_basis(ex, kind)
                if hurt is None:
                    seeded.discard('basis'); break
                try:
                    c = PE.check_composition(hurt, text)
                    v = 'caught' if (c and c.get('basis_flag')) else _verdict_comp(c)
                except Exception as e:
                    v = 'error: %s' % e
                rows.append(('basis', kind, v, what, has_apfu))
    try:
        pw0 = PE.cell_check(pdf, cif, text, table=ex['_table'])
    except Exception:
        pw0 = None
    if pw0 and pw0.get('status') == 'checked' and not pw0.get('bad'):
        seeded.add('d')
        for frac in D_SIZES:
            hurt, what, hkl = _seed_d(ex, frac)
            if hurt is None:
                seeded.discard('d'); break
            try:
                v = _verdict_powder(PE.cell_check(pdf, cif, text, table=hurt['_table']), hkl)
            except Exception as e:
                v = 'error: %s' % e
            rows.append(('d', frac, v, what, has_apfu))
    return {'base': base, 'rows': rows, 'seeded': sorted(seeded), 'apfu': has_apfu,
            'comp_ok': bool(comp0 and comp0['ok']), 'pw_ok': bool(pw0 and pw0.get('status') == 'checked')}


# ----------------------------------------------------------------------------- the corpus

def _jobs(pdf_dirs, only=None, subset=None, limit=None):
    """The same walk the paper-check harness uses, so the two runs talk about the same papers."""
    jobs = []; seen = set()
    for pd in pdf_dirs:
        for pdf in sorted(glob.glob(os.path.join(pd, '**', '*.pdf'), recursive=True)):
            if 'review_out' in pdf:
                continue
            base = os.path.basename(pdf)
            if re.search(r'supp|tables?\b', base, re.I):
                continue
            if only and only not in base:
                continue
            if subset is not None and base not in subset:
                continue
            ids = set(re.findall(r'I\d{6}', base)); key = tuple(sorted(ids)) or base
            if key in seen:
                continue
            seen.add(key)
            if limit and len(seen) > limit:
                break
            cif = next((c for c in glob.glob(os.path.join(os.path.dirname(pdf), '*.cif')) if any(i in os.path.basename(c) for i in ids)), None) if ids else None
            jobs.append((pdf, cif, base))
    return jobs


def _map_ordered(jobs, n_jobs):
    """_run_one over the papers, results in job order. A dead worker stops the run rather than
    reporting a paper it never measured (see tools/corpus_paper_extract.py for why)."""
    n_jobs = max(1, min(n_jobs, len(jobs)))
    if n_jobs <= 1:
        return [_run_one(j) for j in jobs]
    out = [None] * len(jobs)
    pool = ProcessPoolExecutor(max_workers=n_jobs, mp_context=_CTX)
    try:
        pending = {}; nxt = 0
        for i in range(len(jobs)):
            while nxt < len(jobs) and len(pending) < 4 * n_jobs:
                pending[nxt] = pool.submit(_run_one, jobs[nxt]); nxt += 1
            try:
                out[i] = pending.pop(i).result()
            except BrokenProcessPool:
                sys.stderr.write('a worker died; nothing written. Re-run with --jobs 1 to find the paper.\n')
                raise SystemExit(2)
    finally:
        try:
            pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        for proc in (getattr(pool, '_processes', None) or {}).values():
            try:
                proc.kill()
            except Exception:
                pass
    return out


def _ladder(rows, kind, sizes, fmt):
    """The detection curve for one fault: a line per size, counts of each outcome."""
    out = ['', '%s' % kind.upper(), '  %-8s %7s %7s %7s   %s' % ('size', 'caught', 'noted', 'missed', 'caught %')]
    for s in sizes:
        at = [r for r in rows if r[0] == kind and r[1] == s]
        if not at:
            continue
        c = sum(1 for r in at if r[2] == 'caught'); n = sum(1 for r in at if r[2] == 'noted')
        m = sum(1 for r in at if r[2] == 'missed')
        out.append('  %-8s %7d %7d %7d   %5.0f %%' % (fmt(s), c, n, m, 100.0 * c / max(len(at), 1)))
    return out


def main(pdf_dirs, out_dir, tag='', limit=None, only=None, subset=None, n_jobs=1):
    jobs = _jobs(pdf_dirs, only, subset, limit)
    res = [r for r in _map_ordered(jobs, n_jobs) if r]
    rows = [(kind, size, verdict, what, apfu, r['base']) for r in res for kind, size, verdict, what, apfu in r['rows']]
    nseed = lambda k: sum(1 for r in res if k in (r.get('seeded') or []))
    lines = ['Seeded faults — the tool\'s RECALL, measured by breaking papers it passes.',
             'Papers read: %d; composition checked and clean: %d; powder checked: %d; with an apfu column: %d'
             % (len(res), sum(1 for r in res if r.get('comp_ok')), sum(1 for r in res if r.get('pw_ok')), sum(1 for r in res if r.get('apfu'))),
             'Papers seeded: formula %d, wt%% %d, basis %d, d %d' % (nseed('formula'), nseed('wt%'), nseed('basis'), nseed('d'))]
    lines += _ladder(rows, 'formula', F_SIZES, lambda s: '%g %%' % (100 * s))
    lines += _ladder(rows, 'wt%', WT_SIZES, lambda s: '%g %%' % (100 * s))
    lines += _ladder(rows, 'd', D_SIZES, lambda s: '%g %%' % (100 * s))
    lines += _ladder(rows, 'basis', BASIS_FAULTS, lambda s: s)
    # the apfu column was added as an oracle on 2026-09-07: where a paper prints one, a wt% the
    # tool cannot reproduce is blamed on the tool's own reading, which is exactly the rule a
    # seeded wt% fault should expose
    wt = [r for r in rows if r[0] == 'wt%']
    for flag, label in ((True, 'papers WITH an apfu column'), (False, 'papers without one')):
        at = [r for r in wt if r[4] is flag and r[1] >= 0.05]
        if at:
            lines.append('  wt%% >= 5 %%, %-28s caught %d of %d (%.0f %%)'
                         % (label, sum(1 for r in at if r[2] == 'caught'), len(at), 100.0 * sum(1 for r in at if r[2] == 'caught') / len(at)))
    # the smallest size each paper's check catches: the honest per-paper threshold
    for kind, sizes, fmt in (('formula', F_SIZES, lambda s: '%g %%' % (100 * s)), ('wt%', WT_SIZES, lambda s: '%g %%' % (100 * s)), ('d', D_SIZES, lambda s: '%g %%' % (100 * s))):
        first = {}
        for k, s, v, _w, _a, base in rows:
            if k == kind and v == 'caught':
                first[base] = min(first.get(base, 99), s)
        seeded = {base for k, s, v, _w, _a, base in rows if k == kind}
        if seeded:
            lines += ['', 'smallest %s fault caught, per paper:' % kind]
            for s in sizes:
                n = sum(1 for b in first if first[b] == s)
                lines.append('  %-8s %d papers' % (fmt(s), n))
            lines.append('  %-8s %d papers (never caught at any size seeded)' % ('none', len(seeded) - len(first)))
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'seed_faults%s.tsv' % tag), 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, delimiter='\t'); w.writerow(['paper', 'fault', 'size', 'outcome', 'what was changed', 'apfu column'])
        for kind, size, verdict, what, apfu, base in rows:
            w.writerow([base, kind, size, verdict, what, 'yes' if apfu else 'no'])
    open(os.path.join(out_dir, 'seed_faults%s.txt' % tag), 'w', encoding='utf-8').write(
        __doc__.split('\n\n')[0] + '\n\n' + '\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('pdf_dirs', help='pdf + cif folders, comma-separated (searched recursively)')
    ap.add_argument('--out', default='/Users/travis/Desktop/Minerals_task_group/review_out')
    ap.add_argument('--tag', default='')
    ap.add_argument('--limit', type=int, help='stop after N papers')
    ap.add_argument('--only', help='only papers whose file name contains this')
    ap.add_argument('--papers', help='a file with one pdf basename per line (or a comma list)')
    ap.add_argument('--jobs', type=int, default=0, help='worker processes: 0 (default) = the cores, capped at 8')
    a = ap.parse_args()
    subset = None
    if a.papers:
        subset = set(open(a.papers, encoding='utf-8').read().split()) if os.path.exists(a.papers) else set(x.strip() for x in a.papers.split(',') if x.strip())
    main(a.pdf_dirs.split(','), a.out, a.tag, a.limit, a.only, subset, max(1, a.jobs or min(8, os.cpu_count() or 1)))
