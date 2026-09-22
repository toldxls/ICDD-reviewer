"""Diagnosis accuracy of the EPMA check sheet: seed ONE fault of a known kind, read what the sheet NAMES.

    python3 tools/seed_statements.py "<pdf folders, comma-separated>" OUT_DIR [TAG] [--papers LIST] [--limit N] [--jobs N]

tools/seed_faults.py asks whether a check FIRES. This asks whether the sheet says the RIGHT THING —
the element, the kind of fault — because a reviewer acts on the sentence, not on the colour. Papers
whose composition check passes cleanly (the stated basis reproduces the formula, no constant factor,
no apfu column standing in for the wt%) are taken; the fault goes into the values already read, in
memory; the workbook is written to OUT_DIR, evaluated with tests/xl_eval.py, and its readings classed:

  wt       one major constituent's wt% × (1 + size)      right = 'ONE element stands alone: <that element>'
  coeff    one major printed coefficient × (1 + size)    right = the same
  basis    the anion / cation basis N -> N + 1            right = 'every coefficient off by ONE factor', the basis named
  valence  a two-valence oxide reduced the other way      right = the valence line 'explains the common factor'
  two      two constituents' wt% at once                  right = 'N elements stand out', never one name
  none     nothing seeded                                 right = nothing red

Output: OUT_DIR/seed_statements<TAG>.{txt,json} — a confusion matrix (seeded × said) per stratum
(majors compared < 3 / >= 3, basis kind, a halogen in the table). No paper is touched.
"""
import os, re, sys, json, random, argparse, hashlib
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, 'tests')); sys.path.insert(0, os.path.join(ROOT, 'tools'))
from pxrd_review import paper_extract as PE, epma as EP, paths

_CTX = mp.get_context('spawn')
SIZES = (0.05, 0.10, 0.20)

def read_sheet(path):
    """-> {'factor': class, 'standing': ('none'|'one'|'many', element), 'valence': [explaining lines], 'red': {elements}, 'few': bool}"""
    from xl_eval import Book
    b = Book(path); wc = b.wb['check']; out = {'factor': '', 'standing': ('none', ''), 'valence': [], 'red': set(), 'basis_needed': None, 'few': False, 'sugg': {}}
    block = ''
    for r in range(1, wc.max_row + 1):
        a = wc.cell(r, 1).value
        if a == 'element':
            block = 'el'; continue
        if isinstance(a, str) and a.startswith('WHERE THE FAULT'):
            block = 'fault'; continue
        if isinstance(a, str) and a.startswith('IF AN OXIDE'):
            block = 'valence'; continue
        if a is None:
            if block == 'el':
                block = ''
            continue
        if block == 'el':
            v = b.value('check', 'F%d' % r)
            if isinstance(v, str) and v.startswith('does not'):
                out['red'].add(a)
            try:
                sg = b.value('check', 'L%d' % r)
                if isinstance(sg, (int, float)):
                    out['sugg'][a] = sg
            except Exception:
                pass
        elif block in ('fault', 'valence') and wc.cell(r, 3).value is not None:
            v = b.value('check', 'C%d' % r); v = v if isinstance(v, str) else ''
            if a.startswith('common factor'):
                out['few'] = 'fewer than three' in v
                out['factor'] = ('basis' if 'ONE factor' in v else 'scatter' if 'scatter' in v else 'dilution' if 'ONE wrong value' in v else
                                 'shift' if 'within tolerance' in v else 'few' if out['few'] else 'ok')
            elif a.startswith('elements left standing'):
                m = re.search(r'stands alone: (\w+)', v)
                out['standing'] = ('one', m.group(1)) if m else ('many', '') if v.startswith('PROBLEM') or ('do not follow' in v and not v.startswith('ok')) else ('none', '')
            elif a.startswith('the basis that would'):
                out['whole'] = 'a WHOLE number' in v
                try:
                    out['basis_needed'] = b.value('check', 'B%d' % r)
                except Exception:
                    pass
            elif block == 'valence' and 'explain the common factor' in v and v.startswith('PROBLEM'):
                out['valence'].append(a)
    return out

def classify(kind, target, said, extra=None):
    """What the sheet said about a seeded fault -> RIGHT | PARTIAL | WRONG-NAME | WRONG-KIND | MISSED."""
    st, el = said['standing']
    if kind == 'none':
        return 'RIGHT' if not said['red'] and said['factor'] in ('ok', 'few', 'shift') and st == 'none' else 'FALSE-ALARM'
    if kind in ('wt', 'coeff'):
        if st == 'one':
            return 'RIGHT' if el == target else 'WRONG-NAME'
        if said['factor'] == 'basis' or said['valence']:
            return 'WRONG-KIND'
        if target in said['red']:
            return 'PARTIAL'                          # its row is red, but the sheet does not single it out (few majors, or several red)
        return 'MISSED' if not said['red'] else 'WRONG-NAME'
    if kind == 'basis':
        named = extra and said['basis_needed'] and abs(said['basis_needed'] - extra) <= 0.02 * extra
        if said['factor'] == 'basis':
            # a valence line may ALSO fit the factor: right when the basis row names the true basis as a whole number
            return 'RIGHT' if named and (said.get('whole') or not said['valence']) else 'PARTIAL'
        if said['factor'] == 'shift':
            return 'PARTIAL' if named else 'MISSED'       # inside the tolerance (N >= 20, +-1): a note that names the basis
        return 'WRONG-KIND' if st == 'one' or said['valence'] else ('PARTIAL' if said['red'] else 'MISSED')
    if kind == 'valence':
        if said['valence']:
            return 'RIGHT' if target in said['valence'][0] and not said.get('whole') else 'PARTIAL'
        return 'WRONG-KIND' if st == 'one' else ('PARTIAL' if said['factor'] in ('basis', 'shift') else ('MISSED' if not said['red'] else 'WRONG-KIND'))
    if kind == 'two':
        if st == 'one':
            return 'WRONG-NAME'
        return 'RIGHT' if st == 'many' or said['factor'] == 'scatter' else ('WRONG-KIND' if said['factor'] == 'basis' or said['valence'] else ('PARTIAL' if said['red'] else 'MISSED'))
    return '?'

def _run_one(job):
    pdf, base, out_dir = job
    try:
        ex = PE.extract(pdf, None, write=False)
        if not ex.get('epma'):
            return None
        comp = PE.check_composition(ex, PE.text_of(pdf))
    except Exception as e:
        return {'base': base, 'fail': str(e)[:120]}
    r = (comp or {}).get('result') or {}
    if not comp or not comp.get('ok') or not comp.get('verified') or r.get('factor') or comp.get('apfu_vouches') or comp.get('basis_equiv') or not ex.get('basis'):
        return None
    basis = tuple(r.get('basis') or ())
    if not basis or not PE._same_basis(ex['basis'], basis) or r.get('water_oh'):
        return None
    wt = {c: v for c, v in (comp.get('wt') or {}).items() if PE._parses(c) and v}
    counts = dict(comp.get('counts') or {})
    cons = {c: EP.parse_constituent(c) for c in wt}
    el_of = {c: ('H' if k.kind == 'water' else k.element) for c, k in cons.items()}
    two_val = {el for el, v in (comp.get('ox_paper') or {}).items() if len(v or ()) > 1}
    majors = [c for c in wt if counts.get(el_of[c], 0) >= 0.1 and el_of[c] not in ('H', 'O') and el_of[c] not in two_val
              and cons[c].kind in ('oxide', 'other', 'element') and sum(1 for c2 in wt if el_of[c2] == el_of[c]) == 1]
    if len(majors) < 2:
        return None
    rng = random.Random(int(hashlib.sha1(base.encode()).hexdigest()[:8], 16))
    printed = re.findall(r'([A-Z][a-z]?)(?:\d[+-])?\s*(\d+)[.:](\d+)', comp.get('formula') or '')
    dec = {}
    for el, _i, d in printed:
        dec[el] = min(dec.get(el, 9), len(d))
    common = max(dec.values() or [2])
    decimals = {el: dec.get(el, common) for el in counts}
    n_major = len([c for c in wt if counts.get(el_of[c], 0) >= 0.1 and el_of[c] != 'H'])
    strata = {'majors': '<3' if n_major < 3 else '>=3', 'basis': basis[0], 'halogen': any(k.kind == 'element-anion' for k in cons.values())}
    out = {'base': base, 'strata': strata, 'runs': []}
    def sheet(tag, wt_, counts_, basis_):
        ds = EP.Dataset([cons.get(c) or EP.parse_constituent(c) for c in wt_], [list(wt_.values())], ['mean'], {}, base, None)
        red = EP.reduce(ds, basis_)
        if not red.factor:
            return None
        path = os.path.join(out_dir, '%s__%s.xlsx' % (base[:40], tag))
        EP.write_xlsx(red, None, path, published=counts_, single=True, decimals=decimals)
        try:
            said = read_sheet(path)
        finally:
            os.remove(path)
        # VISIBLE = the fault puts some compared coefficient past the check's own tolerance (0.03 apfu or 5 %): below that
        # there is nothing a sheet could say, and the honest denominator leaves those out
        got = {}
        for k_, row in red.rows.items():
            e_ = 'H' if row.c.kind == 'water' else row.c.element
            got[e_] = got.get(e_, 0.0) + row.apfu
        said['visible'] = any(abs(got[e_] - v) > max(0.03, 0.05 * v) for e_, v in counts_.items() if e_ in got and e_ not in ('H', 'O') and v)
        return said
    def run(kind, size, target, said, extra=None, note=''):
        if said is None:
            return
        out['runs'].append({'kind': kind, 'size': size, 'target': target, 'class': classify(kind, target, said, extra), 'visible': bool(said.get('visible')),
                            'said': {'factor': said['factor'], 'standing': list(said['standing']), 'valence': said['valence'], 'red': sorted(said['red'])}, 'note': note})
    try:
        run('none', 0, '', sheet('none', wt, counts, basis))
        big = [c for c in majors if counts.get(el_of[c], 0) >= 0.6] or majors      # a coefficient on which 5 % is past the absolute 0.03
        c1 = rng.choice(big)
        for size in SIZES:
            said = sheet('wt%d' % int(size * 100), dict(wt, **{c1: wt[c1] * (1 + size)}), counts, basis)
            note = ''
            if said and el_of[c1] in said.get('sugg', {}):
                note = 'suggested %.2f for %.2f' % (said['sugg'][el_of[c1]], wt[c1])
            run('wt', size, el_of[c1], said, note=note)
            run('coeff', size, el_of[c1], sheet('co%d' % int(size * 100), wt, dict(counts, **{el_of[c1]: counts[el_of[c1]] * (1 + size)}), basis))
        if basis[0] in ('O', 'cations'):
            run('basis', 1, '', sheet('basis', wt, counts, (basis[0], basis[1] + 1)), extra=basis[1])
            if basis[1] > 2:
                run('basis', -1, '', sheet('basism', wt, counts, (basis[0], basis[1] - 1)), extra=basis[1])
        if basis[0] == 'O':
            for c in wt:
                for alt in EP._OTHER_OXIDE.get(c, []):
                    if c in majors or counts.get(el_of[c], 0) >= 0.3:
                        ka, kb = cons[c], EP.parse_constituent(alt)
                        wt_alt = {(alt if k_ == c else k_): (v * (kb.mw / kb.n_cat) / (ka.mw / ka.n_cat) if k_ == c else v) for k_, v in wt.items()}
                        if alt in wt:
                            continue
                        # the PAPER reduced it as `alt`: its coefficients are those of the alt reduction, the sheet reduces the table as read
                        ds = EP.Dataset([EP.parse_constituent(k_) for k_ in wt_alt], [list(wt_alt.values())], ['m'], {}, base, None)
                        red_alt = EP.reduce(ds, basis)
                        counts_alt = dict(counts)
                        for k_, row in red_alt.rows.items():
                            e_ = 'H' if row.c.kind == 'water' else row.c.element
                            if e_ in counts_alt and sum(1 for c2 in wt_alt if ('H' if EP.parse_constituent(c2).kind == 'water' else EP.parse_constituent(c2).element) == e_) == 1:
                                counts_alt[e_] = round(row.apfu, decimals.get(e_, 2))
                        run('valence', 0, '%s as %s' % (c, alt), sheet('val', wt, counts_alt, basis))
                        break
        if len(majors) >= 3:
            c2 = rng.choice([c for c in big if c != c1] or [c for c in majors if c != c1])
            run('two', 0.15, '', sheet('two', dict(wt, **{c1: wt[c1] * 1.15, c2: wt[c2] * 0.85}), counts, basis))
    except Exception as e:
        out['error'] = str(e)[:160]
    return out

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('pdf_dirs'); ap.add_argument('out_dir'); ap.add_argument('tag', nargs='?', default='')
    ap.add_argument('--papers'); ap.add_argument('--limit', type=int); ap.add_argument('--only'); ap.add_argument('--jobs', type=int, default=0); ap.add_argument('--baseline')
    a = ap.parse_args(argv)
    import corpus_paper_extract as CP
    cache = os.environ.get('PXRD_PAGE_CACHE') or os.path.join(paths.cache_dir(), 'pages')
    os.environ['PXRD_PAGE_CACHE'] = cache; PE.set_page_cache(cache)
    subset = None
    if a.papers:
        subset = {x.strip() for x in (open(a.papers).read().split('\n') if os.path.isfile(a.papers) else a.papers.split(',')) if x.strip()}
    wb = os.path.join(a.out_dir, 'seed' + a.tag); os.makedirs(wb, exist_ok=True)
    jobs = [(pdf, base, wb) for pdf, _cif, base in CP._jobs([d for d in a.pdf_dirs.split(',') if d], a.only, subset, a.limit)]
    n = a.jobs or os.cpu_count() or 4
    if n == 1:
        recs = [_run_one(j) for j in jobs]
    else:
        with ProcessPoolExecutor(max_workers=n, mp_context=_CTX) as pool:
            recs = list(pool.map(_run_one, jobs, chunksize=2))
    recs = [r for r in recs if r and 'runs' in r]
    CL = ('RIGHT', 'PARTIAL', 'MISSED', 'WRONG-NAME', 'WRONG-KIND', 'FALSE-ALARM')
    def table(rows, title):
        L = ['', title, '  %-14s %5s  ' % ('seeded', 'n') + ' '.join('%11s' % c for c in CL)]
        keys = sorted({(x['kind'], x['size']) for x in rows}, key=lambda k: (('none', 'wt', 'coeff', 'basis', 'valence', 'two').index(k[0]), k[1]))
        for k in keys:
            every = [x for x in rows if (x['kind'], x['size']) == k]
            xs = [x for x in every if x['visible'] or k[0] == 'none']                 # of the faults a sheet COULD see
            if not xs:
                L.append('  %-14s %5d   (none past the tolerance, of %d seeded)' % ('%s %s' % (k[0], k[1] or ''), 0, len(every))); continue
            L.append('  %-14s %5d  ' % ('%s %s' % (k[0], ('%+d' % k[1]) if k[0] == 'basis' else ('%d%%' % int(k[1] * 100)) if k[1] else ''), len(xs))
                     + ' '.join('%10.0f%%' % (100.0 * sum(1 for x in xs if x['class'] == c) / len(xs)) for c in CL) + '   (%d seeded)' % len(every))
        return L
    allruns = [dict(x, base=r['base'], **r['strata']) for r in recs for x in r['runs']]
    L = ['DIAGNOSIS ACCURACY of the EPMA check sheet%s — %d clean papers, %d seeded sheets' % ((' ' + a.tag) if a.tag else '', len(recs), len(allruns))]
    L += table(allruns, 'ALL')
    for name, f in (('majors >= 3', lambda x: x['majors'] == '>=3'), ('majors < 3', lambda x: x['majors'] == '<3'), ('anion basis', lambda x: x['basis'] == 'O'),
                    ('cation basis', lambda x: x['basis'] == 'cations'), ('element basis', lambda x: x['basis'] == 'element'), ('a halogen in the table', lambda x: x['halogen'])):
        rows = [x for x in allruns if f(x)]
        if rows:
            L += table(rows, name.upper() + ' (%d papers)' % len({x['base'] for x in rows}))
    L += ['', 'WORKLIST — what was said where it was wrong (class | seeded | said)']
    from collections import Counter
    cnt = Counter(); exm = {}
    for x in allruns:
        if x['class'] in ('WRONG-NAME', 'WRONG-KIND', 'FALSE-ALARM', 'MISSED') and (x['visible'] or x['kind'] == 'none'):
            k = (x['class'], x['kind'], x['said']['factor'], x['said']['standing'][0], bool(x['said']['valence']), x['majors'])
            cnt[k] += 1; exm.setdefault(k, []).append('%s %s %s' % (x['base'], x['size'], x['target']))
    for k, n_ in cnt.most_common(25):
        L.append('  %4d  %-11s %-8s factor=%-8s standing=%-5s valence=%-5s majors%s   e.g. %s' % ((n_,) + k + ('; '.join(exm[k][:2]),)))
    errs = [r for r in recs if r.get('error')]
    L += ['', 'errors: %d' % len(errs)] + ['  %s %s' % (r['base'], r['error']) for r in errs[:10]]
    os.makedirs(a.out_dir, exist_ok=True)
    json.dump(recs, open(os.path.join(a.out_dir, 'seed_statements%s.json' % a.tag), 'w'), default=str)
    open(os.path.join(a.out_dir, 'seed_statements%s.txt' % a.tag), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('\n'.join(L))

if __name__ == '__main__':
    main()
