#!/usr/bin/env python3
"""The fitter run over RRUFF's collection — crashes, coverage of the strong bands, background humps, typical widths.

    python3 tools/fit_gauntlet.py [--sample N] [--seed S] [--jobs J] [--baseline none|als] [--groups SO4,PO4] [--out DIR] [--widths]

Every spectrum (the store `pxrd rruff --fetch` built; processed Raman, broad scans left out): `prepare_series` with the
baseline asked for, then `auto_fit` REGION BY REGION as the window is used — the strong bands clustered into regions
(a gap over GAP cm⁻¹ splits; a margin of MARGIN on each side), each under the 30 s cap — one jsonl line per spectrum
(regions, components, χ², R², converged, each warning's class, the share of the strong bands with a component within
COVER cm⁻¹, each component's position / width / η with the mineral's library group and the mode whose window holds it). The report says: crashes,
coverage, the share with a band wider than half the grid (a hump), the width percentiles per mode. The FIRST run on a
fixed sample (`--sample 1000 --seed 1`) is the baseline (`fit_gauntlet_baseline.json` in --out); later runs diff against
it. `--widths` writes the aggregates to pxrd_review/data/fit_widths.json (p5–p95 FWHM per group and mode). A dev tool;
the per-spectrum jsonl holds RRUFF ids (public data) and stays in --out, never the repo.
"""
import os, re, sys, json, time, random, collections, statistics
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from pxrd_review import spectrum as SPM, spectrum_formats as SPF, rruff as RR, bands as BD

COVER = 6.0                 # cm⁻¹: a strong band is 'fitted' when a component stands within this of it, or within half the band's own width
HUMP_MIN = 300.0            # cm⁻¹: a component this wide (and half its region) is a hump, not a band
STRONG = 0.10               # of the top: a band whose coverage is counted
GAP = 80.0                  # cm⁻¹: strong bands further apart than this are fitted in separate regions
MARGIN = 40.0               # cm⁻¹: the region reaches this far beyond its outer bands


def regions_of(strong, lo, hi):
    """[(lo, hi)] — the strong bands clustered at gaps over GAP, each cluster with MARGIN on both sides, clipped to the grid."""
    out = []
    for p in sorted(strong):
        if out and p - out[-1][1] <= GAP:
            out[-1][1] = p
        else:
            out.append([p, p])
    return [(max(lo, a - MARGIN), min(hi, b + MARGIN)) for a, b in out]
WARN_CLASS = re.compile(r'^(the fit stopped|the bands at|the positions|the band at .* is narrower|the band at .* is under|.* rests on the width limit|'
                        r'the band at .* wide|the band at .* on the edge|.* correlated|the fit is singular|the residual runs|.* driven to zero|.* left out|stopped after)')


def warn_class(w):
    m = WARN_CLASS.match(w)
    return (m.group(1) if m else w)[:40].strip()


def formula_of(mineral, cache={}):
    from pxrd_review import paper_extract as PE
    if mineral not in cache:
        try:
            rec = PE.species_record(mineral)
            cache[mineral] = re.sub(r'<[^>]+>', '', rec['formula']) if rec and rec.get('formula') else ''
        except Exception:
            cache[mineral] = ''
    return cache[mineral]


def mode_of(pos, keys, windows):
    """The library mode (of the mineral's groups) whose measured window holds `pos`: 'SO4 ν1', else ''."""
    for key in keys:
        for w, v in windows.items():
            if w.startswith(key + ' ') and v.get('p5', 0) <= pos <= v.get('p95', 0):
                return w
    return ''


def one(args):
    i, meta, x, y, baseline, windows = args
    t0 = time.time()
    rec = {'i': i, 'id': meta.get('id'), 'name': meta.get('name'), 'laser': meta.get('laser'), 'quality': meta.get('quality'), 'orient': meta.get('orient')}
    try:
        series = SPF._series('%s %s' % (meta.get('name'), meta.get('id')), x, y, format='rruff', kind='raman')
        prep = SPM.prepare_series([series], 0, baseline_kind=baseline, kind='raman')
        xs, ys = prep['x'], prep['y']
        found = [pk for pk in SPM.find_peaks(xs, ys) if pk['pos'] >= RR.LATTICE and pk['height'] > 0]
        top = max((pk['height'] for pk in found), default=0.0)
        strong = [(pk['pos'], pk['fwhm']) for pk in found if pk['height'] >= STRONG * top]
        keys = [k for k in BD.groups_of(formula_of(meta.get('name') or '')) if k not in ('OH', 'H2O')]
        fits = []
        for lo, hi in regions_of([p for p, _w in strong], xs[0], xs[-1]):
            try:
                f, _trials = SPM.auto_fit(xs, ys, lo=lo, hi=hi, local_baseline='linear')
                fits.append(f)
            except ValueError as ex:                               # 'no band found' in a region of weak bands: counted, not a crash
                rec.setdefault('skipped', []).append(str(ex)[:60])
        comps = [c for f in fits for c in f.comps]
        total = max(1e-9, sum(c['area'] for c in comps))
        out_comps = [{'pos': round(c['pos'], 1), 'fwhm': round(c['fwhm'], 1), 'eta': round(c['eta'], 2), 'share': round(c['area'] / total, 3), 'mode': mode_of(c['pos'], keys, windows)} for c in comps]
        rec.update(regions=len(fits), n=len(comps), chi2=round(statistics.median(f.chi2 for f in fits), 3) if fits else None, r2=round(min(f.r2 for f in fits), 5) if fits else None,
                   converged=all(f.converged for f in fits), seconds=round(time.time() - t0, 1),
                   warnings=sorted({warn_class(w) for f in fits for w in f.warnings}), strong=len(strong),
                   covered=sum(1 for p, w in strong if any(abs(c['pos'] - p) <= max(COVER, 0.5 * w) for c in comps)),
                   hump=any(c['fwhm'] >= max(HUMP_MIN, 0.5 * (f.hi - f.lo)) for f in fits for c in f.comps), groups=keys, comps=out_comps)
    except Exception as ex:
        rec.update(error='%s: %s' % (type(ex).__name__, str(ex)[:160]), seconds=round(time.time() - t0, 1))
    return rec


def main(argv=None):
    import argparse
    from multiprocessing import Pool
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--sample', type=int, default=0, help='this many spectra, drawn with --seed (0 = every processed Raman spectrum)')
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--jobs', type=int, default=8)
    ap.add_argument('--baseline', default='none', choices=('none', 'als', 'snip', 'rubber'))
    ap.add_argument('--groups', help='only minerals of these library groups (comma-separated)')
    ap.add_argument('--out', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'review_out'))
    ap.add_argument('--tag', default='')
    ap.add_argument('--widths', action='store_true', help='write pxrd_review/data/fit_widths.json from this run')
    ap.add_argument('--store', help='the store folder (default: the cache)')
    a = ap.parse_args(argv)
    st = RR.open_store(a.store)
    if st is None:
        print('no RRUFF store (pxrd rruff --fetch)'); return 1
    idx = [i for i, m in enumerate(st.spectra) if m.get('technique') == 'raman' and m.get('kind') == 'processed' and m.get('quality') != 'broad']
    if a.groups:
        want = set(a.groups.split(','))
        idx = [i for i in idx if want & set(BD.groups_of(formula_of(st.spectra[i].get('name') or '')))]
    if a.sample and a.sample < len(idx):
        random.Random(a.seed).shuffle(idx); idx = sorted(idx[:a.sample])
    windows = BD._rruff()
    jobs = [(i, st.spectra[i], *st.xy(i), a.baseline, windows) for i in idx]
    st.close()
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    with Pool(a.jobs) as pool:
        recs = pool.map(one, jobs, chunksize=4)
    with open(os.path.join(a.out, 'fit_gauntlet%s.jsonl' % a.tag), 'w', encoding='utf-8') as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    ok = [r for r in recs if 'error' not in r]
    strong = sum(r['strong'] for r in ok); covered = sum(r['covered'] for r in ok)
    warns = collections.Counter(w for r in ok for w in r['warnings'])
    widths = collections.defaultdict(list)
    for r in ok:
        for c in r['comps']:
            if c['mode'] and c['share'] >= 0.05:
                widths[c['mode']].append(c['fwhm'])
    summary = {'spectra': len(recs), 'crashes': len(recs) - len(ok), 'coverage': round(100.0 * covered / max(1, strong), 1), 'humps': sum(1 for r in ok if r['hump']),
               'not_converged': sum(1 for r in ok if not r['converged']), 'median_seconds': round(statistics.median(r['seconds'] for r in recs), 1) if recs else 0,
               'baseline': a.baseline, 'sample': a.sample, 'seed': a.seed, 'minutes': round((time.time() - t0) / 60, 1)}
    L = ['FIT GAUNTLET over %d RRUFF spectra, region by region (baseline %s; sample %d seed %d): %d crashes, %.1f %% of the strong bands fitted (within %g), %d with a hump (a band %d cm⁻¹ and half its region wide), %d not converged, %.1f s a spectrum'
         % (summary['spectra'], a.baseline, a.sample, a.seed, summary['crashes'], summary['coverage'], COVER, summary['humps'], round(HUMP_MIN), summary['not_converged'], summary['median_seconds']), '']
    L.append('  warnings: ' + ', '.join('%s %d' % (k, v) for k, v in warns.most_common(12)))
    L += ['', '  FWHM of the components by mode (p5–p50–p95 cm⁻¹, components of ≥ 5 % of the area):']
    agg = {}
    for mode, v in sorted(widths.items()):
        if len(v) < 8:
            continue
        v = sorted(v); p = lambda q: v[min(len(v) - 1, int(round((len(v) - 1) * q / 100.0)))]
        agg[mode] = {'p5': round(p(5), 1), 'p25': round(p(25), 1), 'p50': round(p(50), 1), 'p75': round(p(75), 1), 'p95': round(p(95), 1), 'n': len(v)}
        L.append('    %-14s %5.1f  %5.1f  %5.1f   (%d)' % (mode, agg[mode]['p5'], agg[mode]['p50'], agg[mode]['p95'], len(v)))
    errs = collections.Counter(r['error'].split(':')[0] for r in recs if 'error' in r)
    if errs:
        L += ['', '  errors: ' + ', '.join('%s %d' % kv for kv in errs.most_common())]
    base = os.path.join(a.out, 'fit_gauntlet_baseline.json')
    if os.path.isfile(base):
        b = json.load(open(base, encoding='utf-8'))
        L += ['', '  against the baseline (%s, %d spectra): crashes %d → %d, coverage %.1f → %.1f %%, humps %d → %d' % (b.get('when', '?'), b['spectra'], b['crashes'], summary['crashes'], b['coverage'], summary['coverage'], b['humps'], summary['humps'])]
    else:
        json.dump(dict(summary, when=time.strftime('%Y-%m-%d %H:%M')), open(base, 'w', encoding='utf-8'), indent=1)
        L += ['', '  baseline written: ' + os.path.normpath(base)]
    text = '\n'.join(L) + '\n'
    open(os.path.join(a.out, 'fit_gauntlet_report%s.txt' % a.tag), 'w', encoding='utf-8').write(text)
    print(text)
    if a.widths:
        dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pxrd_review', 'data', 'fit_widths.json')
        json.dump({'about': 'The width (FWHM, cm-1) of the fitted components of RRUFF\'s single-group minerals, per band-library mode: percentiles over the components of 5 % of the area or more, '
                            'from tools/fit_gauntlet.py over the fetched collection. A reading aid for the band table; never changes a fit. Aggregates only.',
                   'baseline': a.baseline, 'spectra': summary['spectra'], 'widths': agg}, open(dest, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
        print('written:', os.path.normpath(dest))
    return 0


if __name__ == '__main__':
    sys.exit(main())
