"""Diagnosis accuracy of the Gladstone–Dale check sheet: seed ONE known cause of a difference, read what the sheet NAMES.

    python3 tools/seed_statements_gd.py "<pdf folders>" OUT_DIR [TAG] [--limit N] [--only S] [--jobs N]

Papers whose stated compatibility index the tool reproduces are taken, with the analysis the paper
check settled on. The PAPER'S index is then replaced by the one a known cause would give — the tool's
own arithmetic under that cause — and the sheet is asked what explains the difference:

  none      the tool's own index                            right = 'ok — reproduces', nothing coloured
  variant   K_C on one of Mandarino's variant constants     right = 'EXPLAINS IT' on that oxide's line (and only that)
  norm      the analysis normalised to 100 % first          right = 'EXPLAINS IT — normalised' (seeded only where the total is off 100)
  category  the word one class away from the number         right = the category line red, nothing else red
  n, D      n + 0.04 / D × 1.05   (past the 0.03 the constants allow)                             right = amber difference, and the 'needed' n / D within rounding of the seeded one

A seeded cause that moves the index by less than 0.005 is invisible by construction and left out.
No paper is touched; workbooks go to OUT_DIR and are removed.
"""
import os, re, sys, json, argparse
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, 'tests')); sys.path.insert(0, os.path.join(ROOT, 'tools'))
from pxrd_review import paper_extract as PE, gd as GD, paths

_CTX = mp.get_context('spawn')
CATS = ['superior', 'excellent', 'good', 'fair', 'poor']

def read(path):
    from xl_eval import Book
    b = Book(path); wc = b.wb['check']; out = {'first': '', 'explains': [], 'red': [], 'amber': [], 'needed': {}}
    block = ''
    for r in range(4, wc.max_row + 1):
        a = wc.cell(r, 1).value
        if not isinstance(a, str):
            continue
        if a.startswith('WHAT WOULD EXPLAIN'):
            block = 'x'; continue
        if a.startswith('WHAT WOULD GIVE'):
            block = 'need'; continue
        if block == 'need':
            try:
                out['needed'][a.split(' ')[0]] = b.value('check', 'B%d' % r)
            except Exception:
                pass
            continue
        v = wc.cell(r, 5).value
        if v is None:
            continue
        try:
            v = b.value('check', 'E%d' % r)
        except Exception as e:
            v = 'ERR %s' % e
        if not isinstance(v, str):
            continue
        if a.startswith('1 − K_P') and not out['first']:
            out['first'] = v
        if v.startswith('EXPLAINS'):
            out['explains'].append(a)
        elif v.startswith('PROBLEM'):
            out['red'].append(a)
        elif v.startswith('note'):
            out['amber'].append(a)
    return out

def _run_one(job):
    pdf, base, out_dir = job
    try:
        ex = PE.extract(pdf, None, write=False); text = PE.text_of(pdf); stmt = PE.gd_statement(text)
        if stmt.get('ci') is None:
            return None
        comp = PE.check_composition(ex, text) if ex.get('epma') else None
        real = PE._gd_eval
        def spy(ex_, wt, *a, **k):
            o = real(ex_, wt, *a, **k); o['_wt'] = dict(wt or {}); o['_k'] = (a[1] if len(a) > 1 else k.get('k_override')) or {}
            return o
        PE._gd_eval = spy
        try:
            g = PE.gd_check(ex, comp, stmt)
        finally:
            PE._gd_eval = real
    except Exception as e:
        return {'base': base, 'fail': str(e)[:100]}
    o = ex.get('optics') or {}
    if g['status'].get('optics.n') != 'agrees' or not g.get('_wt') or not g.get('ci') or g.get('_k'):
        return None
    key = min(g['ci'], key=lambda k_: abs(g['ci'][k_] - stmt['ci'])); D = o.get('D_' + key); n = o.get('n')
    wt = {c: v for c, v in g['_wt'].items() if v}
    res = GD.evaluate(wt, n, density=D); res['o_corr'] = sum(v for k_, v in wt.items() if k_.startswith('O='))
    ci0 = res['CI_meas']; KC = res['KC']; KP = (n - 1) / D
    total = sum(v for v in wt.values())
    K = GD.constants(); runs = []
    def sheet(tag, paper, res_=res):
        path = os.path.join(out_dir, '%s__%s.xlsx' % (base[:40], tag))
        GD.write_xlsx(res_, path, base, paper)
        try:
            return read(path)
        finally:
            os.remove(path)
    def add(kind, target, said, right, shift):
        runs.append({'kind': kind, 'target': target, 'class': right(said), 'shift': shift, 'said': {k: said[k] for k in ('first', 'explains', 'red', 'amber')}})
    try:
        add('none', '', sheet('none', {'ci': round(ci0, 3), 'category': GD.category(round(ci0, 3))}),
            lambda s: 'RIGHT' if s['first'].startswith('ok — reproduces') and not s['red'] and not s['explains'] and not s['amber'] else ('FALSE-ALARM' if s['red'] or s['explains'] else 'NOISY'), 0)
        # a variant constant
        for c, w in sorted(wt.items(), key=lambda kv: -kv[1]):
            var = [v for v in (K.get(c, {}).get('variants') or []) if v.get('k') is not None and abs(v['k'] - K[c]['k']) > 1e-9]
            if var and w >= 3:
                ci1 = 1 - KP / (KC + (var[0]['k'] - K[c]['k']) * w / 100)
                if abs(ci1 - ci0) >= 0.006:
                    add('variant', c, sheet('var', {'ci': round(ci1, 3)}),
                        lambda s, c=c: 'RIGHT' if any(a.startswith(c + ' with k') for a in s['explains']) and len({a.split(' ')[0] for a in s['explains']}) == 1 and not any('normalised' in a for a in s['explains'])
                        else 'PARTIAL' if any(a.startswith(c + ' with k') for a in s['explains']) else ('WRONG-KIND' if s['explains'] else 'MISSED'), abs(ci1 - ci0))
                break
        # normalised to 100 %
        tot = total + res['o_corr'] if not any(k_.startswith('O=') for k_ in wt) else total
        if abs(tot - 100) >= 1.5:
            ci1 = 1 - KP / (KC * 100 / tot)
            if abs(ci1 - ci0) >= 0.006:
                add('norm', '', sheet('norm', {'ci': round(ci1, 3)}),
                    lambda s: 'RIGHT' if any('normalised' in a for a in s['explains']) and len(s['explains']) == 1 else 'PARTIAL' if any('normalised' in a for a in s['explains']) else ('WRONG-KIND' if s['explains'] else 'MISSED'), abs(ci1 - ci0))
        # the word one class off
        i = CATS.index(GD.category(round(ci0, 3))); wrong = CATS[i + 1] if i + 1 < len(CATS) else CATS[i - 1]
        add('category', wrong, sheet('cat', {'ci': round(ci0, 3), 'category': wrong}),
            lambda s: 'RIGHT' if s['red'] == ['category'] else ('MISSED' if not s['red'] else 'WRONG-KIND'), 0)
        # n and D
        for kind, res1, want in (('n', GD.evaluate(wt, n + 0.04, density=D), n), ('D', GD.evaluate(wt, n, density=D * 1.05), D)):
            res1['o_corr'] = res['o_corr']
            said = sheet(kind, {'ci': round(ci0, 3)}, res1)
            need = said['needed'].get(kind)
            if abs(res1['CI_meas'] - ci0) <= 0.032:
                continue                                                 # inside what the constants allow: nothing a sheet should say
            add(kind, '', said, lambda s, need=need, want=want: 'RIGHT' if s['first'].startswith('note') and not s['red'] and need is not None and abs(need - want) <= 0.004 * want + 0.002
                else 'PARTIAL' if s['first'].startswith('note') and not s['red'] else ('WRONG-KIND' if s['red'] else 'MISSED'), abs(res1['CI_meas'] - ci0))
    except Exception as e:
        return {'base': base, 'fail': 'seed: ' + str(e)[:120]}
    return {'base': base, 'runs': runs, 'halogen': any(c in ('F', 'Cl') for c in wt), 'total': round(tot, 2)}

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('pdf_dirs'); ap.add_argument('out_dir'); ap.add_argument('tag', nargs='?', default='')
    ap.add_argument('--limit', type=int); ap.add_argument('--only'); ap.add_argument('--jobs', type=int, default=0)
    a = ap.parse_args(argv)
    import corpus_paper_extract as CP
    cache = os.environ.get('PXRD_PAGE_CACHE') or os.path.join(paths.cache_dir(), 'pages')
    os.environ['PXRD_PAGE_CACHE'] = cache; PE.set_page_cache(cache)
    wb = os.path.join(a.out_dir, 'seedgd' + a.tag); os.makedirs(wb, exist_ok=True)
    jobs = [(pdf, base, wb) for pdf, _c, base in CP._jobs([d for d in a.pdf_dirs.split(',') if d], a.only, None, a.limit)]
    with ProcessPoolExecutor(max_workers=a.jobs or os.cpu_count() or 4, mp_context=_CTX) as pool:
        recs = [r for r in pool.map(_run_one, jobs, chunksize=2) if r]
    fails = [r for r in recs if 'fail' in r]; recs = [r for r in recs if 'runs' in r]
    CL = ('RIGHT', 'PARTIAL', 'NOISY', 'MISSED', 'WRONG-KIND', 'FALSE-ALARM')
    L = ['DIAGNOSIS ACCURACY of the Gladstone–Dale check sheet%s — %d papers whose stated index the tool reproduces' % ((' ' + a.tag) if a.tag else '', len(recs)),
         '', '  %-10s %5s  ' % ('seeded', 'n') + ' '.join('%11s' % c for c in CL)]
    for kind in ('none', 'variant', 'norm', 'category', 'n', 'D'):
        xs = [x for r in recs for x in r['runs'] if x['kind'] == kind]
        if xs:
            L.append('  %-10s %5d  ' % (kind, len(xs)) + ' '.join('%10.0f%%' % (100.0 * sum(1 for x in xs if x['class'] == c) / len(xs)) for c in CL))
    from collections import Counter
    cnt = Counter(); exm = {}
    for r in recs:
        for x in r['runs']:
            if x['class'] not in ('RIGHT',):
                k = (x['class'], x['kind'], x['said']['first'][:28], tuple(sorted({re.sub(r'[\d.]+', 'N', e)[:34] for e in x['said']['explains']}))[:2], tuple(x['said']['red'])[:2], tuple(re.sub(r'[\d.]+', 'N', e)[:24] for e in x['said']['amber'])[:2])
                cnt[k] += 1; exm.setdefault(k, '%s %s' % (r['base'], x['target']))
    L += ['', 'WORKLIST']
    for k, n_ in cnt.most_common(18):
        L.append('  %4d  %s   e.g. %s' % (n_, k, exm[k]))
    L += ['', 'failed: %d' % len(fails)] + ['  %s %s' % (r['base'], r['fail']) for r in fails[:8]]
    json.dump(recs, open(os.path.join(a.out_dir, 'seed_statements_gd%s.json' % a.tag), 'w'), default=str)
    open(os.path.join(a.out_dir, 'seed_statements_gd%s.txt' % a.tag), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('\n'.join(L))

if __name__ == '__main__':
    main()
