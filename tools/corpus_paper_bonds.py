"""Validation of `paper_bonds` against the .cif, on the corpus papers that have one.

The point of paper_bonds is the papers with NO .cif, where nothing can score it. So it is scored
where a .cif does exist: the bond distances read from the paper's own table, and the bond-valence
sums that follow from them, against the same sums computed from the .cif. A site whose sum
reproduces the .cif's says the table was read right and the arithmetic is the journal's.

    python3 tools/corpus_paper_bonds.py "<pdf+cif folders, comma-separated>" [OUT_DIR] [TAG] [--limit N] [--jobs N]

Output: review_out/paper_bonds_<tag>.{txt,tsv} — per paper: sites read, sites matched to the .cif,
sites whose sum agrees within 0.10 vu, and the worst offenders.
"""
import os, re, sys, csv, glob, argparse
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pxrd_review import paper_bonds as PB
from pxrd_review import bv_check as B

_CTX = mp.get_context('spawn')
TOL = 0.10          # vu; the spread between parameter sets is itself ~0.05


def _jobs(dirs, limit=None):
    jobs = []; seen = set()
    for pd in dirs:
        for pdf in sorted(glob.glob(os.path.join(pd, '**', '*.pdf'), recursive=True)):
            if 'review_out' in pdf or re.search(r'supp|tables?\b', os.path.basename(pdf), re.I):
                continue
            base = os.path.basename(pdf)
            ids = set(re.findall(r'I\d{6}', base)); key = tuple(sorted(ids)) or base
            if key in seen:
                continue
            cif = next((c for c in glob.glob(os.path.join(os.path.dirname(pdf), '*.cif'))
                        if any(i in os.path.basename(c) for i in ids)), None) if ids else None
            if not cif:
                continue
            seen.add(key)
            if limit and len(seen) > limit:
                return jobs
            jobs.append((pdf, cif, base))
    return jobs


def _run_one(job):
    from pxrd_review import paper_extract as PE
    from pxrd_review import paper_structure as PS
    pdf, cif, base = job
    try:
        tabs = PB.read_tables(pdf)
    except Exception as e:
        return {'base': base, 'fail': 'read: %s' % e}
    cands = PB.candidates(tabs)
    if not cands:
        return {'base': base, 'nrows': 0, 'sites': 0, 'matched': 0, 'agree': 0, 'worst': []}
    try:
        text = PE.text_of(pdf)
        name = PE.mineral_name(text)
        els, charges, known, _unnamed, inferred = PB.context(pdf, tabs, text, name)   # the same resolution structure_for uses
        P = B.Params(prefer='gh', u6='burns')
        real = B.Structure(cif)
        rres, _ras, _rc, _rh = B.compute(real, P, None, 'oo')
    except Exception as e:
        return {'base': base, 'fail': '%s: %s' % (type(e).__name__, e)}
    ref = {}
    for r in rres:
        for x in r[0].label.split('/'):
            ref[B._norm_label(x)] = (r[0].label, r[2])
        ref[B._norm_label(r[0].label)] = (r[0].label, r[2])
    best = None
    for rows in cands:                      # a two-mineral paper prints a table each; the .cif is one of them
        try:
            st = PB.BondStructure(rows, els, charges, known, base, inferred)
            res, _an, _cells = PB.compute(st, P)
        except Exception as e:
            return {'base': base, 'fail': '%s: %s' % (type(e).__name__, e)}
        gii = PB.gii(res, st.inferred)
        matched = 0; agree = 0; worst = []; inf = 0
        for c, _b, bvs, _e, _m in res:
            hit = ref.get(B._norm_label(c.label))
            if not hit:
                continue
            if PB._key(c.label) in st.inferred:
                inf += 1; continue                  # the element came from the paper's prose, not the table: reported apart
            matched += 1
            if abs(bvs - hit[1]) <= TOL + 0.03 * max(bvs, hit[1]):
                agree += 1
            else:
                worst.append((c.label, round(bvs, 2), round(hit[1], 2)))
        worst.sort(key=lambda t: -abs(t[1] - t[2]))
        cand = {'base': base, 'nrows': len(rows), 'sites': len(res), 'matched': matched, 'agree': agree,
                'worst': worst[:4], 'tables': len(tabs), 'gii': gii, 'inferred': inf}
        if best is None or (matched, agree) > (best['matched'], best['agree']):
            best = cand
    return best


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('dirs'); ap.add_argument('out_dir', nargs='?', default=None)
    ap.add_argument('tag', nargs='?', default='')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--jobs', type=int, default=None)
    a = ap.parse_args(argv)
    dirs = [d.strip() for d in a.dirs.split(',') if d.strip()]
    out_dir = a.out_dir or os.path.join(os.path.dirname(dirs[0].rstrip('/')), 'review_out')
    os.makedirs(out_dir, exist_ok=True)
    jobs = _jobs(dirs, a.limit)
    n_jobs = a.jobs if a.jobs is not None else min(8, os.cpu_count() or 1)
    print('%d papers with a .cif; %d workers' % (len(jobs), n_jobs))
    if n_jobs <= 1:
        out = [_run_one(j) for j in jobs]
    else:
        with ProcessPoolExecutor(max_workers=n_jobs, mp_context=_CTX) as ex:
            out = list(ex.map(_run_one, jobs))
    tot = dict(papers=0, with_table=0, rows=0, sites=0, matched=0, agree=0, fail=0)
    lines = []; rows_tsv = []; gates = []
    for r in out:
        tot['papers'] += 1
        if r.get('fail'):
            tot['fail'] += 1; lines.append('==== %-40s FAILED %s' % (r['base'][:40], r['fail'])); continue
        if not r['nrows']:
            lines.append('==== %-40s no bond table read' % r['base'][:40]); continue
        tot['with_table'] += 1; tot['rows'] += r['nrows']; tot['sites'] += r['sites']
        tot['matched'] += r['matched']; tot['agree'] += r['agree']
        gates.append((r['gii'], r['matched'], r['agree']))
        lines.append('==== %-40s %3d bonds, %2d sites, %2d matched, %2d agree, gii %s%s' % (
            r['base'][:40], r['nrows'], r['sites'], r['matched'], r['agree'],
            '%.2f' % r['gii'] if r['gii'] is not None else '  - ',
            '   worst: ' + ', '.join('%s %.2f/%.2f' % w for w in r['worst']) if r['worst'] else ''))
        for w in r['worst']:
            rows_tsv.append([r['base'], w[0], w[1], w[2], round(w[1] - w[2], 2)])
    head = ['paper_bonds vs the .cif (%d papers with one)' % tot['papers'],
            '  bond table read      %d (%d %%)' % (tot['with_table'], 100 * tot['with_table'] // max(tot['papers'], 1)),
            '  bonds read           %d' % tot['rows'],
            '  cation sites         %d, of which %d matched a .cif site' % (tot['sites'], tot['matched']),
            '  sums reproduced      %d of %d (%d %%)' % (tot['agree'], tot['matched'], 100 * tot['agree'] // max(tot['matched'], 1)),
            '  papers that raised   %d' % tot['fail'],
            '', '  gated on the paper\'s own bonds adding up (root-mean-square Sigma - formal valence):']
    for g in (0.10, 0.15, 0.20, 0.25, 0.35, 0.50, 99):
        sel = [x for x in gates if x[0] is not None and x[0] <= g]
        nm = sum(x[1] for x in sel); ok = sum(x[2] for x in sel)
        head.append('    gii <= %-5s %3d papers, %3d sites matched, %3d reproduced (%d %%)'
                    % (g if g < 90 else 'any', len(sel), nm, ok, 100 * ok // max(nm, 1)))
    head.append('')
    txt = os.path.join(out_dir, 'paper_bonds%s.txt' % (('_' + a.tag) if a.tag else ''))
    with open(txt, 'w', encoding='utf-8') as f:
        f.write('\n'.join(head + lines) + '\n')
    with open(txt[:-4] + '.tsv', 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, delimiter='\t'); w.writerow(['paper', 'site', 'from bonds', 'from .cif', 'diff']); w.writerows(rows_tsv)
    print('\n'.join(head)); print('->', txt)


if __name__ == '__main__':
    main()
