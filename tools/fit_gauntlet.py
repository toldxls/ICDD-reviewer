#!/usr/bin/env python3
"""The fitter run over RRUFF's collection — crashes, coverage of the strong bands, background humps, typical widths.

    python3 tools/fit_gauntlet.py [--sample N] [--seed S] [--jobs J] [--baseline none|als] [--groups SO4,PO4] [--out DIR] [--widths] [--reaggregate]

Every spectrum (the store `pxrd rruff --fetch` built; processed Raman, broad scans left out): `prepare_series` with the
baseline asked for, then `auto_fit` REGION BY REGION as the window is used — the strong bands clustered into regions
(a gap over GAP cm⁻¹ splits; a margin of MARGIN or the band's own width on each side), each under SECONDS — one jsonl
line per spectrum (regions, components, χ², R², converged, each warning's class, the share of the strong bands with a
component within COVER cm⁻¹ or half the band's width (at most COVER_MAX), each component's position / width / η with
the mineral's library groups and the ONE mode whose window holds it — a band two of the formula's modes could hold
is filed under neither). The report says: crashes, coverage, the share with a band wider than half the grid (a hump),
the width percentiles per mode. A whole-store run (`--sample 0`) writes the baseline (`fit_gauntlet_baseline.json` in
--out) when none exists; later runs diff against it (a sample run against a whole-store baseline is said to be one).
`--widths` writes the aggregates to pxrd_review/data/fit_widths.json (p5–p95 FWHM per mode); `--reaggregate` rebuilds
them from the jsonl of an earlier run (same --out and --tag) without refitting. A dev tool; the per-spectrum jsonl
holds RRUFF ids (public data) and stays in --out, never the repo.
"""
import os, re, sys, json, time, random, collections, statistics
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from pxrd_review import spectrum as SPM, spectrum_formats as SPF, rruff as RR, bands as BD

COVER = 6.0                 # cm⁻¹: a strong band is 'fitted' when a component stands within this of it, or within half the band's own width
COVER_MAX = 30.0            # cm⁻¹: the half-width allowance stops here (a 350-wide band is not 'fitted' by a component 170 away)
HUMP_MIN = 300.0            # cm⁻¹: a component this wide (and half its region) is a hump, not a band
STRONG = 0.10               # of the top: a band whose coverage is counted
GAP = 80.0                  # cm⁻¹: strong bands further apart than this are fitted in separate regions
MARGIN = 40.0               # cm⁻¹: the region reaches this far beyond its outer bands
EXTRA = 4                   # components allowed beyond the strong bands of a region (the window's 'at most' set as a user would)
SECONDS = 10.0              # the search's time cap per region here (the window's is 30 s): a profile put 70 % of the time in a few wide regions
_W = {}                     # the worker's store and windows (opened once per worker, not pickled per task)


def regions_of(strong, lo, hi):
    """[(lo, hi)] — the strong bands [(pos, fwhm)] clustered at gaps over GAP, each cluster with a margin of MARGIN or the
    outer band's own width on each side (a 350-wide band needs a region that holds it), clipped to the grid."""
    out = []
    for p, w in sorted(strong):
        if out and p - out[-1][1] <= GAP:
            out[-1][1] = p; out[-1][3] = w
        else:
            out.append([p, p, w, w])
    spans = [(max(lo, a - max(MARGIN, wa)), min(hi, b + max(MARGIN, wb))) for a, b, wa, wb in out]
    merged = []
    for a, b in spans:                                               # wide bands' margins may reach each other: one region then, never two overlapping
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


WARN_CLASSES = [(re.compile(rx), name) for rx, name in (                       # a warning's class: `diagnose`'s wording without its positions and parameter names
    (r'^the fit stopped', 'stopped at the iteration limit'), (r'^the fit is singular', 'singular'), (r'^the residual runs', 'the residual runs'),
    (r'^the bands at .* closer than the resolution', 'two bands closer than the resolution'), (r'^the bands at .* under half their width', 'two bands under half their width apart'),
    (r'^the positions .* uncertain', 'positions uncertain by their spacing'), (r'narrower than the resolution', 'narrower than the resolution'),
    (r'wide — two or three points', 'two or three points wide'), (r'stands .* noise deviations', 'stands low in the noise'),
    (r'rests on the width limit', 'rests on the width limit'), (r'a background hump', 'a background hump'), (r'stands on the edge', 'stands on the edge'),
    (r'are correlated at|pairs of parameters are correlated', 'correlated parameters'), (r'driven to zero', 'driven to zero'), (r'left out', 'an edge band left out'))]


def warn_class(w):
    for rx, name in WARN_CLASSES:
        if rx.search(w):
            return name
    return re.sub(r'\d+(?:\.\d+)?', 'N', w)[:40].strip()


def formula_of(mineral, cache={}):
    from pxrd_review import paper_extract as PE
    if mineral not in cache:
        try:
            rec = PE.species_record(mineral)
            cache[mineral] = re.sub(r'<[^>]+>', '', rec['formula']) if rec and rec.get('formula') else ''
        except Exception:
            cache[mineral] = ''
    return cache[mineral]


def holders(windows):
    """{library mode label: (group, lo, hi, centre)} — the window a component is filed under: the RRUFF measured p5–p95
    (centre = its median) of the mode when there is one, else the library's own range (the groups with no ion geometry —
    Si–O, sulfide — have no measured mode windows, only a 'strongest' window that is no mode). Keyed by `bands.label` so
    the window's band table and the width note find it."""
    out = {}
    for g in BD.library()['groups']:
        for m in g['modes']:
            lab = BD.label({'group': g['key'], 'mode': m['mode']})
            w = windows.get('%s %s' % (g['key'], m['mode']))
            out[lab] = (g['key'], w['p5'], w['p95'], w.get('p50', 0.5 * (w['p5'] + w['p95']))) if w and w.get('p5') is not None else (g['key'], m['range'][0], m['range'][1], 0.5 * sum(m['range']))
    return out


def mode_of(pos, keys, held):
    """The library mode of ONE of the mineral's groups whose window holds `pos` ('SO4 ν1'): '' when none does or when
    two GROUPS could (cancrinite's 1056 lies in CO3 ν1 and SO4 ν3 alike: filed under neither, so no group's width feeds
    another's); within one group, whose modes' windows overlap at their edges (ν1 and ν3 of an arsenate), the mode with
    the nearer centre."""
    found = [(abs(pos - c), lab, g) for lab, (g, lo, hi, c) in held.items() if g in keys and lo <= pos <= hi]
    if not found or len({g for _d, _lab, g in found}) > 1:
        return ''
    return min(found)[1]


def _init(store, baseline):
    """Each worker opens the store itself (an mmap) and keeps the windows: no spectrum travels through a pipe."""
    _W['st'] = RR.open_store(store); _W['baseline'] = baseline; _W['held'] = holders(BD._rruff())
    SPM.AUTO_SECONDS = SECONDS


def one(i):
    st = _W['st']; meta = st.spectra[i]; x, y = st.xy(i); baseline = _W['baseline']; held = _W['held']
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
        for lo, hi in regions_of(strong, xs[0], xs[-1]):
            n_in = sum(1 for p, _w in strong if lo <= p <= hi)
            try:
                f, _trials = SPM.auto_fit(xs, ys, lo=lo, hi=hi, local_baseline='linear', max_n=min(12, n_in + EXTRA))
                fits.append(f)
            except ValueError as ex:                               # 'no band found' in a region of weak bands: counted, not a crash
                rec.setdefault('skipped', []).append(str(ex)[:60])
        comps = [c for f in fits for c in f.comps]
        total = max(1e-9, sum(c['area'] for c in comps))
        out_comps = [{'pos': round(c['pos'], 1), 'fwhm': round(c['fwhm'], 1), 'eta': round(c['eta'], 2), 'share': round(c['area'] / total, 3), 'mode': mode_of(c['pos'], keys, held)} for c in comps]
        rec.update(regions=len(fits), n=len(comps), chi2=round(statistics.median(f.chi2 for f in fits), 3) if fits else None, r2=round(min(f.r2 for f in fits), 5) if fits else None,
                   converged=all(f.converged for f in fits), seconds=round(time.time() - t0, 1),
                   warnings=sorted({warn_class(w) for f in fits for w in f.warnings}), strong=len(strong),
                   covered=sum(1 for p, w in strong if any(abs(c['pos'] - p) <= max(COVER, min(0.5 * w, COVER_MAX)) for c in comps)),
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
    ap.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 8) - 1))
    ap.add_argument('--baseline', default='none', choices=('none', 'als', 'snip', 'rubber'))
    ap.add_argument('--groups', help='only minerals of these library groups (comma-separated)')
    ap.add_argument('--out', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'review_out'))
    ap.add_argument('--tag', default='')
    ap.add_argument('--widths', action='store_true', help='write pxrd_review/data/fit_widths.json from this run')
    ap.add_argument('--store', help='the store folder (default: the cache)')
    ap.add_argument('--reaggregate', action='store_true', help='no fitting: re-read the jsonl of an earlier run (--out, --tag), re-file each component under the one mode holding it, rewrite the report and (with --widths) the width table')
    a = ap.parse_args(argv)
    if a.reaggregate:
        return reaggregate(a)
    st = RR.open_store(a.store)
    if st is None:
        print('no RRUFF store (pxrd rruff --fetch)'); return 1
    idx = [i for i, m in enumerate(st.spectra) if m.get('technique') == 'raman' and m.get('kind') == 'processed' and m.get('quality') != 'broad']
    if a.groups:
        want = set(a.groups.split(','))
        idx = [i for i in idx if want & set(BD.groups_of(formula_of(st.spectra[i].get('name') or '')))]
    if a.sample and a.sample < len(idx):
        random.Random(a.seed).shuffle(idx); idx = sorted(idx[:a.sample])
    store = st.folder
    st.close()
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    recs = []
    with Pool(a.jobs, initializer=_init, initargs=(store, a.baseline)) as pool:
        for k, r in enumerate(pool.imap_unordered(one, idx, chunksize=8), 1):
            recs.append(r)
            if k % 500 == 0 or k == len(idx):
                print('  %d / %d spectra, %.1f min' % (k, len(idx), (time.time() - t0) / 60), flush=True)
    recs.sort(key=lambda r: r['i'])
    with open(os.path.join(a.out, 'fit_gauntlet%s.jsonl' % a.tag), 'w', encoding='utf-8') as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    return report(a, recs, time.time() - t0)


def reaggregate(a):
    """The jsonl of an earlier run re-filed: each component under the one mode holding it (the rule may have changed since
    the run), the report and the width table rewritten — no fit repeated."""
    path = os.path.join(a.out, 'fit_gauntlet%s.jsonl' % a.tag)
    if not os.path.isfile(path):
        print('no run to re-aggregate:', os.path.normpath(path)); return 1
    held = holders(BD._rruff())
    recs = [json.loads(ln) for ln in open(path, encoding='utf-8') if ln.strip()]
    for r in recs:
        for c in r.get('comps') or []:
            c['mode'] = mode_of(c['pos'], r.get('groups') or [], held)
    print('re-aggregated %d spectra of %s' % (len(recs), os.path.normpath(path)))
    return report(a, recs, 0.0, diff=False)


def report(a, recs, seconds, diff=True):
    ok = [r for r in recs if 'error' not in r]
    strong = sum(r['strong'] for r in ok); covered = sum(r['covered'] for r in ok)
    warns = collections.Counter(w for r in ok for w in r['warnings'])
    widths = collections.defaultdict(list)
    for r in ok:
        for c in r['comps']:
            if c['mode'] and c['share'] >= 0.05:
                widths[c['mode']].append(c['fwhm'])
    summary = {'spectra': len(recs), 'crashes': len(recs) - len(ok), 'coverage': round(100.0 * covered / max(1, strong), 1), 'humps': sum(1 for r in ok if r['hump']),
               'not_converged': sum(1 for r in ok if not r['converged']), 'skipped': sum(1 for r in ok if r.get('skipped')),
               'median_seconds': round(statistics.median(r['seconds'] for r in recs), 1) if recs else 0,
               'baseline': a.baseline, 'sample': a.sample, 'seed': a.seed, 'minutes': round(seconds / 60, 1)}
    L = ['FIT GAUNTLET over %d RRUFF spectra, region by region (baseline %s; sample %d seed %d; at most the strong bands + %d components a region, %g s a region): %d crashes, %.1f %% of the strong bands fitted (within %g or half their width, at most %g), %d with a hump (a band %d cm⁻¹ and half its region wide), %d spectra with a region not converged, %d with a region skipped (no band found), %.1f s a spectrum'
         % (summary['spectra'], a.baseline, a.sample, a.seed, EXTRA, SECONDS, summary['crashes'], summary['coverage'], COVER, COVER_MAX, summary['humps'], round(HUMP_MIN), summary['not_converged'], summary['skipped'], summary['median_seconds']), '']
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
    if not diff:
        pass
    elif os.path.isfile(base):
        b = json.load(open(base, encoding='utf-8'))
        same = (b.get('sample') or 0) == a.sample and (not a.sample or b.get('seed') == a.seed)
        L += ['', '  against the baseline (%s, %d spectra%s): crashes %d → %d, coverage %.1f → %.1f %%, humps %d → %d'
              % (b.get('when', '?'), b['spectra'], '' if same else ' — NOT the same sample: the numbers are not comparable', b['crashes'], summary['crashes'], b['coverage'], summary['coverage'], b['humps'], summary['humps'])]
    elif a.sample:
        L += ['', '  no baseline written: only a whole-store run (--sample 0) is one']
    else:
        json.dump(dict(summary, when=time.strftime('%Y-%m-%d %H:%M')), open(base, 'w', encoding='utf-8'), indent=1)
        L += ['', '  baseline written: ' + os.path.normpath(base)]
    text = '\n'.join(L) + '\n'
    open(os.path.join(a.out, 'fit_gauntlet_report%s.txt' % a.tag), 'w', encoding='utf-8').write(text)
    print(text)
    if a.widths:
        dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pxrd_review', 'data', 'fit_widths.json')
        json.dump({'about': 'The width (FWHM, cm-1) of the fitted components of RRUFF\'s Raman spectra per band-library mode (keyed as the band table labels it): a component counts '
                            'under the ONE mode of its mineral\'s groups whose window holds it (none when two could), percentiles over the components of 5 % of the area or more, '
                            'from tools/fit_gauntlet.py over the fetched collection. A reading aid for the band table; never changes a fit. Aggregates only.',
                   'baseline': a.baseline, 'spectra': summary['spectra'], 'widths': agg}, open(dest, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
        print('written:', os.path.normpath(dest))
    return 0


if __name__ == '__main__':
    sys.exit(main())
