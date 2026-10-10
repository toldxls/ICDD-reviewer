#!/usr/bin/env python3
"""The band library's ranges measured on a RRUFF Raman library — the store `pxrd rruff --fetch` builds, or a Thermo OMNIC
copy (RRUFFLib.lbd + RRUFFLib.lbt).

    python3 tools/rruff_windows.py <store folder (index.json) | OMNIC folder> [out_dir] [--which raman|broad|ir] [--write] [--check] [--show GROUP]

The non-circular key is the SINGLE-GROUP minerals: in a spectrum of a mineral whose formula holds one library group
(OH and H2O aside), every strong band above the lattice region belongs to that group, and the numbered modes follow
from the ion's geometry alone — ν3 above ν1 above ν4 above ν2 for a tetrahedral ion, ν3 > ν1 > ν2 > ν4 for a planar
one, ν2 > ν4 among a pyramidal ion's bends — the same ordering tests/test_bands.py pins. No range of the library is
used to assign a band, so what comes out can be set against the library's ranges as an independent measurement.
  * ν1 = the strongest band of the spectrum above the lattice region (the symmetric stretch dominates a Raman spectrum
    of every XO4 / XO3 ion); ν3 = the other stretches (within −15 … +30 % of ν1: ν3 lies BELOW ν1 for WO4, MoO4, VO4);
    the bends (30–80 % of ν1) split into the upper and the lower cluster at their largest gap — a single bend band, or
    no clear gap, goes to a 'bend' bucket set against the union of the two ranges.
  * a group with no numbered modes (Si–O, V–O, Ti–O … sulfides) gets the distribution of its strongest band and of all
    its strong bands, unassigned, for the reader to set beside the ranges.
One spectrum per RRUFF id: the best by `rruff.rank` (processed, excellent, unoriented, 532 nm first). `--which` picks the
spectra walked: 'raman' (processed, the broad scans left out — the default), 'broad' (RRUFF's broad scans, to the O–H
region), 'ir' (the infrared collection). Outputs (out_dir, default review_out beside the corpus): rruff_windows_report.txt,
rruff_windows.jsonl (one line per assigned band — private); --write MERGES the aggregates into
pxrd_review/data/band_windows_rruff.json: a run replaces only the keys it owns (`OWNED`), the others stay.
"""
import os, re, sys, json, collections, statistics
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from pxrd_review import spectrum as SPM, bands as BD, paper_extract as PE

LATTICE = 150.0            # cm-1: below this a Raman band is a lattice mode of any mineral
STRONG = 0.05              # of the strongest band: a band counted at all (= rruff.STRONG_SHARE)
KINDS = ('processed', 'clean', 'corrected')          # kinds a Raman run accepts (never 'raw'); the infrared collection is RAW only and runs under --which ir
TRIM = 3.0                 # robust sigmas, as tools/corpus_spectra.py
MIN_MINERALS = 3           # a window needs this many minerals


from pxrd_review import rruff as RR
from pxrd_review.omnic_lib import split_name, open_library, is_library

WHICH = ('raman', 'broad', 'ir')


def spectra_of(folder, which='raman'):
    """[(meta, x, y)] from a fetched store (index.json) or an OMNIC folder. `which`: 'raman' = processed Raman spectra,
    broad scans left out; 'broad' = RRUFF's broad scans; 'ir' = the infrared collection (RAW on RRUFF's side, bands up).
    An OMNIC copy yields 'raman' only. Each meta is the store's (name, id, kind, laser, quality, orient, technique …)."""
    if which not in WHICH:
        raise ValueError('which: one of %s' % ', '.join(WHICH))
    if os.path.isfile(os.path.join(folder, 'index.json')):
        st = RR.Store(folder)
        out = []
        for i, m in enumerate(st.spectra):
            tech, q, kind = m.get('technique'), m.get('quality'), m.get('kind')
            keep = (tech == 'raman' and q != 'broad' and kind == 'processed') if which == 'raman' else \
                   (tech == 'raman' and q == 'broad') if which == 'broad' else (tech == 'infrared')
            if keep:
                x, y = st.xy(i)
                out.append((m, x, y))
        st.close()
        return out
    if which != 'raman' or not is_library(folder):
        return []
    lib = open_library(folder)
    return [(lib.meta(i), lib.x, lib.spectrum(i)) for i in range(lib.n) if lib.meta(i).get('id')]


def label_of(meta):
    """'Quartz R040031 processed 532' — the record's name in the report and the jsonl."""
    return ' '.join(str(meta.get(k) or '') for k in ('name', 'id', 'kind', 'laser')).strip()


def formula_of(mineral, cache={}):
    key = mineral.lower()
    if key not in cache:
        rec = None
        for form in (mineral, re.sub(r'\s+', '', mineral)):
            try:
                rec = PE.species_record(form)
            except Exception:
                rec = None
            if rec:
                break
        cache[key] = re.sub(r'<[^>]+>', '', rec['formula']) if rec and rec.get('formula') else ''
    return cache[key]


def peaks_of(x, y, lattice=None):
    """[(pos, height)] of the bands above the lattice region, the weak ones (under STRONG of the strongest) dropped —
    `rruff.bands_of`, the one reading of a strong band."""
    return RR.bands_of(x, y, lattice=LATTICE if lattice is None else lattice, share=STRONG, n=None)


def _split_bends(bends):
    """Two clusters at the largest gap (>= 40 cm-1) -> (upper, lower); else (None, None)."""
    if len(bends) < 2:
        return None, None
    gaps = [(bends[k + 1] - bends[k], k) for k in range(len(bends) - 1)]
    g, k = max(gaps)
    if g < 40:
        return None, None
    return bends[k + 1:], bends[:k + 1]


RATIO_TOL = 0.12           # a band is a mode's when it lies within this of the free-ion ratio to ν1, scaled by the measured ν1
NU1_TOL = 0.20             # the strongest band is ν1 only within this of the free-ion ν1 (else the spectrum is left out: a silicate whose bends dominate)
ASSIGN_STRONG = 0.08       # of the strongest band: a band assigned to a mode at all


def assign(shape, modes, pk, free=None, anchor=None):
    """{mode: [positions]} for one spectrum of a single-group mineral. ν1 is the strongest band above the lattice region
    (and, where the free ion's ν1 is known, within NU1_TOL of it — else nothing is assigned: in a few silicates the bends
    dominate). Every other strong band goes to the mode whose FREE-ION position, scaled by the measured ν1, is nearest
    within RATIO_TOL — the free-ion values are the one literature input, and they are not the ranges being measured.
    A group with no free-ion values (borates) falls back to geometry windows. `modes` = the library's mode names (a
    combined 'ν2, ν4' row takes both); `free` = {mode: free-ion cm-1}.
    `anchor` = ('ν3', pos): the infrared run, where ν3 dominates — that band is the anchor, the scale is pos / free['ν3'],
    ν1 joins the modes placed by ratio, and a spectrum with no anchor goes to '(no anchor)'."""
    out = collections.defaultdict(list)
    if not pk:
        return out
    free = {k: v for k, v in (free or {}).items() if v}
    floor = {'tetrahedral': 300.0, 'planar': 600.0, 'pyramidal': 500.0, 'linear': 700.0}.get(shape, 300.0)
    cand = [(p, h) for p, h in pk if p >= floor]
    if not cand:
        return out
    top = max(h for _p, h in pk)
    if anchor:
        amode, nu1 = anchor
        if not free.get(amode):
            out['(no anchor)'].append(nu1)
            return out
    else:
        amode = 'ν1'
        nu1 = max(cand, key=lambda t: t[1])[0]
        if free.get('ν1') and abs(nu1 / free['ν1'] - 1.0) > NU1_TOL:
            out['(ν1 not dominant)'].append(nu1)
            return out
    out[amode].append(nu1)
    pos = [p for p, h in pk if h >= ASSIGN_STRONG * top and abs(p - nu1) > 0.02 * nu1]
    combined = next((m for m in modes if ',' in m), None)
    others = {m: v for m, v in free.items() if m != amode}
    if combined and free.get(amode):                          # a combined row: its one free value stands for both bends
        others[combined] = free.get(combined) or free.get('ν2') or free.get('ν4')
        others = {m: v for m, v in others.items() if v and (m == combined or m in ('ν3', 'ν1'))}
    if others and free.get(amode):
        scale = nu1 / free[amode]
        for p in pos:
            best = min(others, key=lambda m: abs(p / (others[m] * scale) - 1.0))
            if abs(p / (others[best] * scale) - 1.0) <= RATIO_TOL:
                out[best].append(p)
            else:
                out['(unassigned)'].append(p)
        return out
    if anchor:                                                # no free values beyond the anchor: nothing to place by ratio
        return out
    if shape == 'tetrahedral':
        out['ν3'] += [p for p in pos if 0.85 * nu1 <= p <= 1.30 * nu1 and abs(p - nu1) > 0.02 * nu1]
        bends = [p for p in pos if 0.30 * nu1 <= p <= 0.80 * nu1]
        if combined:
            out[combined] += bends
        else:
            up, lo = _split_bends(bends)
            if up:
                out['ν4'] += up; out['ν2'] += lo
            elif bends:
                out['bend'] += bends
    elif shape == 'planar':
        out['ν3'] += [p for p in pos if 1.15 * nu1 < p <= 1.45 * nu1]
        out['ν2'] += [p for p in pos if 0.76 * nu1 <= p < 0.90 * nu1]
        out['ν4'] += [p for p in pos if 0.55 * nu1 <= p < 0.76 * nu1]
    elif shape == 'pyramidal':
        out['ν3'] += [p for p in pos if 0.80 * nu1 <= p <= 1.15 * nu1 and abs(p - nu1) > 0.02 * nu1]
        bends = [p for p in pos if 0.35 * nu1 <= p <= 0.70 * nu1]
        if combined:
            out[combined] += bends
        else:
            up, lo = _split_bends(bends)
            if up:
                out['ν2'] += up; out['ν4'] += lo
            elif bends:
                out['bend'] += bends
    elif shape == 'linear':
        out['ν2'] += [p for p in pos if 180 <= p <= 320]
    return out


def ir_anchor(pk, free):
    """The band an infrared spectrum is anchored on: the strongest band within NU1_TOL of the free-ion ν3, else of ν1 —
    -> ('ν3' | 'ν1', pos) or None (the spectrum is left out)."""
    if not pk:
        return None
    for mode in ('ν3', 'ν1'):
        f = (free or {}).get(mode)
        if not f:
            continue
        near = [(p, h) for p, h in pk if abs(p / f - 1.0) <= NU1_TOL]
        if near:
            return mode, max(near, key=lambda t: t[1])[0]
    return None


OH_LO, OH_HI = 2500.0, 3800.0     # the O–H stretching region of a broad scan
BEND_LO, BEND_HI = 1550.0, 1750.0  # the H–O–H bend
HUMP = 600.0                       # cm⁻¹: a 'band' this wide in the O–H region is a fluorescence hump, not a stretch
NO_BEND = ('CO3', 'NO3', 'C2O4', 'NH4', 'H3O')     # groups with a band of their own near the water bend: no bend measured in their minerals


def oh_bands(x, y):
    """The O–H region of a broad scan -> {'stretch': pos | None, 'bend': pos | None}: the strongest band of 2500–3800 that is
    narrower than HUMP (find_bands' own width), and the strongest in 1550–1750."""
    try:
        pk = SPM.find_peaks(x, y)
    except Exception:
        return {'stretch': None, 'bend': None}
    st = [p for p in pk if OH_LO <= p['pos'] <= OH_HI and p['height'] > 0 and p['fwhm'] < HUMP]
    bd = [p for p in pk if BEND_LO <= p['pos'] <= BEND_HI and p['height'] > 0]
    return {'stretch': max(st, key=lambda p: p['height'])['pos'] if st else None, 'bend': max(bd, key=lambda p: p['height'])['pos'] if bd else None}


def trimmed(v):
    if len(v) < 4:
        return list(v), 0
    med = statistics.median(v); mad = statistics.median(abs(t - med) for t in v) * 1.4826 or 1.0
    keep = [t for t in v if abs(t - med) <= TRIM * mad]
    return keep, len(v) - len(keep)


def pct(v, q):
    v = sorted(v); k = (len(v) - 1) * q / 100.0; i = int(k)
    return v[i] + (v[min(i + 1, len(v) - 1)] - v[i]) * (k - i)


def window(vals):
    """{'p5' … 'p95', 'n', 'minerals', 'dropped'} over [(pos, mineral)]."""
    pos, dropped = trimmed([p for p, _m in vals])
    kept = set(p for p in pos)
    minerals = {m for p, m in vals if p in kept}
    return {'p5': round(pct(pos, 5)), 'p25': round(pct(pos, 25)), 'p50': round(pct(pos, 50)), 'p75': round(pct(pos, 75)), 'p95': round(pct(pos, 95)),
            'n': len(pos), 'minerals': len(minerals), 'dropped': dropped}


def verdict(w, lo, hi, slack=15):
    """How the measured window sits against a library range."""
    if w['minerals'] < MIN_MINERALS:
        return 'too few minerals'
    parts = []
    if w['p5'] < lo - slack:
        parts.append('runs %d below the range' % (lo - w['p5']))
    if w['p95'] > hi + slack:
        parts.append('runs %d above the range' % (w['p95'] - hi))
    if not parts:
        return 'agrees' if w['p50'] >= lo and w['p50'] <= hi else 'inside but the median %d is outside the range' % w['p50']
    if w['p50'] < lo or w['p50'] > hi:
        parts.append('median %d outside the range' % w['p50'])
    return '; '.join(parts)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('folder', help='the folder holding RRUFFLib.lbd and RRUFFLib.lbt, or a fetched store (pxrd rruff --fetch: index.json)')
    ap.add_argument('out_dir', nargs='?', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'review_out'))
    ap.add_argument('--write', action='store_true', help='write the aggregates to pxrd_review/data/band_windows_rruff.json')
    ap.add_argument('--check', action='store_true', help='the alignment of names and spectra: the strongest band of a few well-known minerals')
    ap.add_argument('--show', help='print every assigned band of one group (e.g. SO4)')
    ap.add_argument('--which', choices=WHICH, default='raman', help="the spectra walked: processed Raman (default), RRUFF's broad scans, or the infrared collection")
    ap.add_argument('--activity', action='store_true', help="the minerals with BOTH techniques: per library mode, the share with a band in the mode's range in Raman and in infrared, beside the 'active' column (report only)")
    ap.add_argument('--evidence', action='store_true', help='every check-tagged library row with its measured windows (Raman, O–H, infrared) and a proposed range — for the keeper of the library (report only)')
    ap.add_argument('--composites', action='store_true', help="write pxrd_review/data/band_composites.json.gz: per library group the median of its single-group minerals' spectra (the window's composite layer)")
    ap.add_argument('--orientation', action='store_true', help="write pxrd_review/data/rruff_orientation.json: per group, how much the two strongest bands' intensity ratio varies across a sample's orientations")
    a = ap.parse_args(argv)
    if a.orientation:
        return orientation(a.folder)
    if a.activity:
        return activity(a.folder, a.out_dir)
    if a.evidence:
        return evidence(a.out_dir)
    if a.composites:
        return composites(a.folder)
    spectra = spectra_of(a.folder, a.which)
    lib = BD.library()
    groups = {g['key']: g for g in lib['groups']}
    # one spectrum per RRUFF id: the best by rruff.rank (processed, excellent, unoriented, 532 nm first) — `alternatives`
    # keeps the id's other spectra in rank order, for a best one that yields no anchor (a uranyl at 532 nm fluoresces)
    best = {}; alternatives = collections.defaultdict(list)
    for meta, x, y in spectra:
        rid, kind = meta.get('id') or '', meta.get('kind') or ''
        if not rid or (a.which != 'ir' and kind not in KINDS):
            continue
        alternatives[rid].append((RR.rank(meta), meta.get('name') or '', label_of(meta), x, y))
    for rid, alts in alternatives.items():
        alts.sort(key=lambda t: t[0]); best[rid] = alts[0]
    if a.check:
        want = {'raman': {'Quartz': 464, 'Calcite': 1086, 'Barite': 988, 'Fluorapatite': 965, 'Anhydrite': 1017, 'Scheelite': 911, 'Forsterite': 856},
                'broad': {'Gypsum': 3400, 'Quartz': 464, 'Calcite': 1086}, 'ir': {'Calcite': 1420, 'Quartz': 1085, 'Gypsum': 1120}}[a.which]
        for _r, mineral, name, x, y in sorted(best.values(), key=lambda t: t[2]):
            if mineral in want:
                pk = peaks_of(x, y)
                top = max(pk, key=lambda t: t[1])[0] if pk else None
                print('%-32s strongest band %s (expected ~%d) %s' % (name, None if top is None else round(top), want[mineral], '' if top is not None and abs(top - want[mineral]) < 12 else '<-- CHECK'))
        return 0
    rows = collections.defaultdict(list)          # (group, mode) -> [(pos, mineral)]
    strongest = collections.defaultdict(list)     # group -> [(pos, mineral)] of unnumbered groups
    allstrong = collections.defaultdict(list)
    records = []
    counts = collections.Counter()
    if a.which == 'broad':                        # the O–H region: H2O-only and OH-only minerals, whatever their other group
        for _r, mineral, name, x, y in best.values():
            f = formula_of(mineral) or next((m.get('chem') for m, _x, _y in spectra if m.get('name') == mineral and m.get('chem')), '')
            if not f:
                counts['no formula'] += 1; continue
            keys = BD.groups_of(f)
            wet = [k for k in keys if k in ('OH', 'H2O')]
            if len(wet) != 1:
                counts['no hydrogen group' if not wet else 'both water and hydroxyl'] += 1; continue
            g = wet[0]; counts['%s-only spectra' % g] += 1
            got = oh_bands(x, y)
            if got['stretch']:
                rows[(g, 'stretch')].append((got['stretch'], mineral)); records.append({'group': g, 'mode': 'stretch', 'pos': round(got['stretch'], 1), 'mineral': mineral, 'spectrum': name})
            if g == 'H2O' and got['bend'] and not any(k in NO_BEND for k in keys):
                rows[(g, 'bend')].append((got['bend'], mineral)); records.append({'group': g, 'mode': 'bend', 'pos': round(got['bend'], 1), 'mineral': mineral, 'spectrum': name})
    for rid, (_r, mineral, name, x, y) in ([] if a.which == 'broad' else best.items()):
        f = formula_of(mineral)
        if not f:
            counts['no formula'] += 1; continue
        keys = [k for k in BD.groups_of(f) if k not in ('OH', 'H2O')]
        if len(keys) != 1:
            counts['no group' if not keys else 'several groups'] += 1; continue
        g = keys[0]; counts['single-group spectra'] += 1
        shape = groups[g].get('shape')
        free = {m['mode']: m.get('free') for m in groups[g]['modes']}
        free_v1 = next((v for k, v in free.items() if k.startswith('ν1') and v), None)     # 'ν1' or 'ν1, ν3' (H3O): the stretch's free value
        if a.which == 'ir':
            if not shape or not (free.get('ν3') or free.get('ν1')):
                counts['no free-ion ν3 or ν1 to anchor on (UO2, BO3, BO4, H3O …)'] += 1; continue
            got = None
            for _r2, _m2, name2, x2, y2 in alternatives[rid]:                 # the id's spectra in rank order: the first with an anchor
                pk = peaks_of(x2, y2, lattice=400.0)
                anc = ir_anchor(pk, free)
                if anc:
                    got = assign(shape, [m['mode'] for m in groups[g]['modes']], pk, free, anchor=anc); name = name2; break
            if got is None:
                counts['no anchor in the spectrum'] += 1; continue
            for mode, ps in got.items():
                for p in ps:
                    rows[(g, mode)].append((p, mineral)); records.append({'group': g, 'mode': mode, 'pos': round(p, 1), 'mineral': mineral, 'spectrum': name})
            continue
        if shape and free_v1 and free_v1 > x[-1]:
            counts['group above the grid'] += 1; continue
        if shape and not free_v1 and shape != 'linear':
            counts['no free-ion ν1 to anchor on'] += 1; continue      # H3O ('ν1, ν3' carries no free value) and BO4: 'the strongest band' would be anything; the uranyl ion (linear) is anchored by its geometry: its stretch dominates
        pk = peaks_of(x, y)
        if shape:
            got = assign(shape, [m['mode'] for m in groups[g]['modes']], pk, free)
            if '(ν1 not dominant)' in got and len(alternatives[rid]) > 1:   # the best spectrum of the id has no ν1 to anchor on: the next (a 532 nm uranyl fluoresces)
                for _r2, _m2, name2, x2, y2 in alternatives[rid][1:]:
                    got2 = assign(shape, [m['mode'] for m in groups[g]['modes']], peaks_of(x2, y2), free)
                    if 'ν1' in got2:
                        got = got2; name = name2; counts['anchored on another spectrum of the id'] += 1; break
            for mode, ps in got.items():
                for p in ps:
                    rows[(g, mode)].append((p, mineral)); records.append({'group': g, 'mode': mode, 'pos': round(p, 1), 'mineral': mineral, 'spectrum': name})
        elif pk:
            top = max(pk, key=lambda t: t[1])[0]
            strongest[g].append((top, mineral)); allstrong[g] += [(p, mineral) for p, _h in pk]
            records.append({'group': g, 'mode': 'strongest', 'pos': round(top, 1), 'mineral': mineral, 'spectrum': name})
    os.makedirs(a.out_dir, exist_ok=True)
    with open(os.path.join(a.out_dir, 'rruff_windows.jsonl'), 'w', encoding='utf-8') as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + '\n')
    if a.show:
        for (g, mode), vals in sorted(rows.items()):
            if g == a.show:
                print(g, mode, sorted((round(p), m) for p, m in vals))
        for m, s in sorted(strongest.get(a.show, [])):
            print(a.show, 'strongest', round(m), s)
        return 0
    L = ['BAND LIBRARY vs the RRUFF library, %s spectra (%d spectra, %d RRUFF ids, one spectrum each; the first grid %d–%d cm-1)' % (a.which, len(spectra), len(best), round(spectra[0][1][0]), round(spectra[0][1][-1])),
         '  ' + ', '.join('%s %d' % (k, v) for k, v in sorted(counts.items())),
         '  numbered modes by geometry alone (ν1 = the strongest band; see the file head); windows = 5th–95th percentile after a %g-sigma trim; a row needs %d minerals' % (TRIM, MIN_MINERALS),
         '  "*" = a library range entered from memory of its source (check); "published" = the windows of band_windows.json (papers)',
         '']
    head = ('group', 'mode', 'library range', 'measured p5–p95 (p50)', 'bands', 'minerals', 'verdict', 'published')
    body = []; agg = {}
    pubw = BD._windows()
    for g in lib['groups']:
        key = g['key']
        for m in g['modes']:
            vals = rows.get((key, m['mode']))
            lo, hi = m['range']
            pub = pubw.get('%s %s' % (key, m['mode'])) or {}
            pub = pub.get('raman') or pub.get('any')
            pubt = '%d–%d (%d papers)' % (pub['p5'], pub['p95'], pub['papers']) if pub else ''
            rng = '%d–%d%s' % (lo, hi, ' *' if m.get('check') else '')
            if vals:
                w = window(vals)
                body.append((key, m['mode'], rng, '%d–%d (%d)' % (w['p5'], w['p95'], w['p50']), str(w['n']), str(w['minerals']), verdict(w, lo, hi), pubt))
                if w['minerals'] >= MIN_MINERALS:
                    agg['%s %s' % (key, m['mode'])] = w
            elif g.get('shape'):
                why = 'no single-group mineral in the library' if not any(k == key for k, _m in rows) and not any(r['group'] == key for r in records) else 'no band assigned'
                if m['active'] == 'IR' and a.which != 'ir':
                    why = 'infrared only'
                if hi > 1495 and a.which == 'raman':
                    why = 'above the library grid'
                body.append((key, m['mode'], rng, '', '', '', why, pubt))
            else:
                body.append((key, m['mode'], rng, '', '', '', '', pubt))
        for extra in ('(ν1 not dominant)', '(no anchor)', '(unassigned)'):
            if (key, extra) in rows:
                vals = rows[(key, extra)]
                body.append((key, extra, '', '%d–%d (%d)' % (round(pct([p for p, _m in vals], 5)), round(pct([p for p, _m in vals], 95)), round(pct([p for p, _m in vals], 50))),
                             str(len(vals)), str(len({m for _p, m in vals})),
                             'spectra left out: the strongest band is not near the free-ion ν1' if 'dominant' in extra else 'spectra left out: no band near the free-ion ν3 or ν1' if 'anchor' in extra else 'strong bands near no mode of the ion', ''))
        if key in rows and any(mode == 'bend' for (k, mode) in rows if k == key):
            w = window(rows[(key, 'bend')])
            lo = min(mm['range'][0] for mm in g['modes'] if mm['mode'] in ('ν2', 'ν4')); hi = max(mm['range'][1] for mm in g['modes'] if mm['mode'] in ('ν2', 'ν4'))
            body.append((key, 'bend (ν2/ν4 unsplit)', '%d–%d' % (lo, hi), '%d–%d (%d)' % (w['p5'], w['p95'], w['p50']), str(w['n']), str(w['minerals']), verdict(w, lo, hi), ''))
        if key in strongest:
            w = window(strongest[key]); w2 = window(allstrong[key])
            body.append((key, 'strongest band', '', '%d–%d (%d)' % (w['p5'], w['p95'], w['p50']), str(w['n']), str(w['minerals']), 'unassigned: read against the ranges above', ''))
            body.append((key, 'all strong bands', '', '%d–%d (%d)' % (w2['p5'], w2['p95'], w2['p50']), str(w2['n']), str(w2['minerals']), '', ''))
            agg['%s strongest' % key] = w
    wd = [max(len(r[i]) for r in [head] + body) for i in range(len(head))]
    for r in [head] + body:
        L.append('  ' + '  '.join(c.ljust(wd[i]) for i, c in enumerate(r)).rstrip())
    L += ['', 'ROWS THE SPECTRA DISAGREE WITH (a check-tagged range first):']
    for r in body:
        if r[6] and r[6] not in ('agrees', 'too few minerals') and r[3] and r[2] and 'unassigned' not in r[6]:
            L.append('  %s%s %s: range %s, measured %s over %s minerals — %s' % ('* ' if '*' in r[2] else '  ', r[0], r[1], r[2].rstrip(' *'), r[3], r[5], r[6]))
    text = '\n'.join(L) + '\n'
    out = os.path.join(a.out_dir, 'rruff_windows_report.txt')
    open(out, 'w', encoding='utf-8').write(text)
    print(text)
    print('written:', out)
    if a.write:
        path = write_windows(agg, a.which, '%s: %d spectra walked, %d RRUFF ids, %d single-group' % (os.path.basename(os.path.abspath(a.folder)), len(spectra), len(best), counts['single-group spectra']))
        print('written:', os.path.normpath(path))
    return 0


def _best_per_id(spectra, which):
    best = {}
    for meta, x, y in spectra:
        rid, kind = meta.get('id') or '', meta.get('kind') or ''
        if not rid or (which != 'ir' and kind not in KINDS):
            continue
        r = RR.rank(meta)
        if rid not in best or r < best[rid][0]:
            best[rid] = (r, meta.get('name') or '', label_of(meta), x, y)
    return best


def activity(folder, out_dir):
    """The library's activity column against the spectra: for every mineral RRUFF holds in BOTH techniques whose formula
    holds one library group, whether a band of ASSIGN_STRONG of the top stands inside each mode's range — in Raman and in
    infrared. A share per mode and technique; report only (rruff_activity_report.txt)."""
    lib = BD.library(); groups = {g['key']: g for g in lib['groups']}
    raman = _best_per_id(spectra_of(folder, 'raman'), 'raman'); ir = _best_per_id(spectra_of(folder, 'ir'), 'ir')
    by_min = {}
    for rid, (_r, mineral, name, x, y) in raman.items():
        by_min.setdefault(mineral, {})['raman'] = (x, y)
    for rid, (_r, mineral, name, x, y) in ir.items():
        by_min.setdefault(mineral, {})['ir'] = (x, y)
    seen = collections.defaultdict(lambda: collections.Counter())      # (group, mode) -> {'raman': n with a band, 'ir': …, 'minerals': n}
    n_both = 0
    for mineral, d in by_min.items():
        if 'raman' not in d or 'ir' not in d:
            continue
        f = formula_of(mineral)
        keys = [k for k in BD.groups_of(f) if k not in ('OH', 'H2O')] if f else []
        if len(keys) != 1:
            continue
        g = keys[0]; n_both += 1
        bands = {}
        for tech, (x, y) in d.items():
            pk = peaks_of(x, y, lattice=400.0 if tech == 'ir' else None)
            top = max((h for _p, h in pk), default=0.0)
            bands[tech] = [p for p, h in pk if h >= ASSIGN_STRONG * top]
        for m in groups[g]['modes']:
            lo, hi = m['range']
            c = seen[(g, m['mode'])]; c['minerals'] += 1
            for tech in ('raman', 'ir'):
                c[tech] += any(lo <= p <= hi for p in bands[tech])
    L = ['ACTIVITY — the library\'s Raman / infrared column against the minerals RRUFF holds in both techniques (%d single-group minerals; a band = %d %% of the strongest, inside the mode\'s range)' % (n_both, round(100 * ASSIGN_STRONG)),
         '  a share near 1 in one technique and near 0 in the other says the mode is seen in one only; the infrared grid starts at 400 cm-1, so a mode below it cannot be seen there', '',
         '  %-8s %-14s %-9s %-10s %8s %8s   %s' % ('group', 'mode', 'library', 'minerals', 'Raman', 'infrared', 'note')]
    for g in lib['groups']:
        for m in g['modes']:
            c = seen.get((g['key'], m['mode']))
            if not c or c['minerals'] < MIN_MINERALS:
                continue
            r, i = c['raman'] / c['minerals'], c['ir'] / c['minerals']
            lib_act = lib['activity'].get(m['active'], m['active'])
            note = ''
            if m['active'] == 'IR' and r >= 0.5:
                note = 'listed infrared only, seen in Raman'
            elif m['active'] == 'R' and i >= 0.5 and m['range'][0] >= 400:
                note = 'listed Raman only, seen in infrared'
            elif m['active'] == 'R+IR' and (r < 0.2 or (i < 0.2 and m['range'][0] >= 400)):
                note = 'listed both, seldom seen in %s' % ('Raman' if r < 0.2 else 'infrared')
            L.append('  %-8s %-14s %-9s %-10d %7.0f%% %7.0f%%   %s' % (g['key'], m['mode'], lib_act, c['minerals'], 100 * r, 100 * i, note))
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, 'rruff_activity_report.txt')
    open(out, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('\n'.join(L)); print('written:', out)
    return 0


def evidence(out_dir):
    """Every check-tagged row of the library beside what the spectra measured (the Raman, O–H and infrared windows in the
    data files) and a proposed range — a report for the keeper of the library, who alone drops a tag."""
    lib = BD.library()
    ram = BD._rruff(); ir = {}
    try:
        with open(os.path.join(DATA, 'band_windows_rruff_ir.json'), encoding='utf-8') as fh:
            ir = json.load(fh).get('windows') or {}
    except (OSError, ValueError):
        pass
    L = ['EVIDENCE for the check-tagged library rows (entered from memory of their source): the measured windows beside each — the keeper decides', '',
         '  %-8s %-14s %-10s %-26s %-26s %-12s %s' % ('group', 'mode', 'library', 'Raman p5–p95 (p50) n', 'infrared p5–p95 (p50) n', 'proposed', 'verdict')]
    n_rows = n_measured = 0
    for g in lib['groups']:
        for m in g['modes']:
            if not m.get('check'):
                continue
            n_rows += 1
            key = '%s %s' % (g['key'], m['mode']); lo, hi = m['range']
            wr, wi = ram.get(key), ir.get(key)
            def fmt(w):
                return '%d–%d (%d) %d' % (w['p5'], w['p95'], w['p50'], w['minerals']) if w and w.get('minerals', 0) >= MIN_MINERALS else ''
            best = wr if wr and wr.get('minerals', 0) >= MIN_MINERALS else wi if wi and wi.get('minerals', 0) >= MIN_MINERALS else None
            if best:
                n_measured += 1
                prop = '%d–%d' % (best['p5'] - 10, best['p95'] + 10)
                v = verdict(best, lo, hi)
            else:
                prop, v = '', 'not measured'
            L.append('  %-8s %-14s %-10s %-26s %-26s %-12s %s' % (g['key'], m['mode'], '%d–%d' % (lo, hi), fmt(wr), fmt(wi), prop, v))
    L += ['', '  %d check-tagged rows, %d with a measurement of %d minerals or more; "proposed" = p5 − 10 … p95 + 10 of the fuller measurement' % (n_rows, n_measured, MIN_MINERALS)]
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, 'library_evidence.txt')
    open(out, 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('\n'.join(L)); print('written:', out)
    return 0


MIN_ORIENT = 3                 # orientations of one sample for a ratio to count


def orientation(folder, path=None):
    """How much a mineral's relative band intensities depend on orientation: per sample with MIN_ORIENT or more oriented
    spectra, the ratio of the two strongest bands' heights (the two found in the unoriented or best spectrum) across
    its orientations, max over min; per group the median of those ratios and the count -> rruff_orientation.json."""
    by_id = collections.defaultdict(list)
    for meta, x, y in spectra_of(folder, 'raman'):
        if meta.get('orient') == 'oriented' and meta.get('id'):
            by_id[meta['id']].append((meta, x, y))
    per_group = collections.defaultdict(list); n_samples = 0
    for rid, specs in by_id.items():
        if len(specs) < MIN_ORIENT:
            continue
        mineral = specs[0][0].get('name') or ''
        f = formula_of(mineral)
        keys = [k for k in BD.groups_of(f) if k not in ('OH', 'H2O')] if f else []
        if len(keys) != 1:
            continue
        ratios = []
        ref = None
        for meta, x, y in specs:
            pk = peaks_of(x, y)
            if len(pk) < 2:
                continue
            top2 = sorted(pk, key=lambda t: -t[1])[:2]
            if ref is None:
                ref = sorted(p for p, _h in top2)                 # the two bands of the first spectrum: followed in the others
            heights = []
            for r in ref:
                near = [h for p, h in pk if abs(p - r) <= 6.0]
                heights.append(max(near) if near else 0.0)
            if heights[0] > 0 and heights[1] > 0:
                ratios.append(heights[0] / heights[1])
        if len(ratios) >= MIN_ORIENT:
            per_group[keys[0]].append(max(ratios) / min(ratios)); n_samples += 1
    out = {g: {'median': round(statistics.median(v), 1), 'p75': round(pct(v, 75), 1), 'samples': len(v)} for g, v in per_group.items() if len(v) >= MIN_MINERALS}
    path = path or os.path.join(DATA, 'rruff_orientation.json')
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump({'about': "How much the relative intensity of a mineral's two strongest Raman bands varies with crystal orientation, from RRUFF's oriented sets: per group, "
                            'the median over samples (each with %d orientations or more) of the ratio max/min of the two bands\' height ratio. A reading aid (tools/rruff_windows.py --orientation). Aggregates only.' % MIN_ORIENT,
                   'samples': n_samples, 'groups': out}, fh, indent=1, ensure_ascii=False)
    print('written: %s (%d samples, %d groups: %s)' % (os.path.normpath(path), n_samples, len(out), ', '.join('%s ×%.1f (%d)' % (g, v['median'], v['samples']) for g, v in sorted(out.items()))))
    return 0


COMP_GRID = (100.0, 1500.0, 2.0)       # cm⁻¹: the composite's grid (start, end, step); the broad scans' O–H part on 1500–4000
COMP_OH = (1500.0, 4000.0, 2.0)


def _resample(x, y, lo, hi, step):
    """y on the grid lo..hi by linear interpolation; None where the spectrum does not reach."""
    out = []; k = 0; n = len(x)
    v = lo
    while v <= hi + 1e-9:
        while k + 1 < n and x[k + 1] < v:
            k += 1
        if v < x[0] or v > x[-1] or k + 1 >= n:
            out.append(None)
        else:
            x0, x1, y0, y1 = x[k], x[k + 1], y[k], y[k + 1]
            out.append(y0 + (y1 - y0) * (v - x0) / (x1 - x0) if x1 > x0 else y0)
        v += step
    return out


def composites(folder, path=None):
    """Per library group, the median spectrum of its single-group minerals (one spectrum per id, the best by rank, each
    normalised to its maximum over the Raman grid) on COMP_GRID — and for H2O / OH the broad scans' O–H part on COMP_OH —
    gzipped JSON: {group: {'x0', 'dx', 'y': [...], 'minerals': n}}. A reading aid for the window: what a sulfate looks like."""
    import gzip, statistics
    lib = BD.library()
    out = {}
    for which, grid in (('raman', COMP_GRID), ('broad', COMP_OH)):
        best = _best_per_id(spectra_of(folder, which), which)
        per_group = collections.defaultdict(dict)                  # group -> mineral -> resampled, normalised
        for rid, (_r, mineral, name, x, y) in best.items():
            f = formula_of(mineral)
            if not f:
                continue
            keys = BD.groups_of(f)
            if which == 'broad':
                wet = [k for k in keys if k in ('OH', 'H2O')]
                if len(wet) != 1:
                    continue
                g = wet[0]
            else:
                keys = [k for k in keys if k not in ('OH', 'H2O')]
                if len(keys) != 1:
                    continue
                g = keys[0]
            if mineral in per_group[g]:
                continue                                           # one spectrum per mineral: a species with ten samples is not ten votes
            lo, hi, step = grid
            ys = _resample(x, y, lo, hi, step)
            top = max((v for v in ys if v is not None), default=0.0)
            floor = min((v for v in ys if v is not None), default=0.0)
            if top <= floor:
                continue
            per_group[g][mineral] = [None if v is None else (v - floor) / (top - floor) for v in ys]
        for g, specs in per_group.items():
            if len(specs) < MIN_MINERALS:
                continue
            cols = list(zip(*specs.values()))
            med = []
            for col in cols:
                vals = [v for v in col if v is not None]
                med.append(round(statistics.median(vals), 3) if len(vals) >= MIN_MINERALS else None)
            out[g] = {'x0': grid[0], 'dx': grid[2], 'y': med, 'minerals': len(specs)}
    path = path or os.path.join(DATA, 'band_composites.json.gz')
    with gzip.open(path, 'wt', encoding='utf-8') as fh:
        json.dump({'about': 'Per band-library group, the median spectrum of RRUFF\'s single-group minerals (one spectrum per mineral, each normalised 0–1 on its grid): '
                            'Raman 100–1500 cm-1 per group; the O–H region 1500–4000 from the broad scans for H2O and OH. A reading aid, never a finding. '
                            'Aggregates only (tools/rruff_windows.py --composites).', 'composites': out}, fh)
    print('written: %s (%d groups: %s)' % (os.path.normpath(path), len(out), ', '.join('%s %d' % (g, v['minerals']) for g, v in sorted(out.items()))))
    return 0


OH_KEYS = ('H2O stretch', 'OH stretch', 'H2O bend')
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pxrd_review', 'data')


def owned_keys(which, keys):
    """The keys a run of `which` may replace in the file: 'raman' owns every key but the O–H ones, 'broad' the O–H ones."""
    if which == 'broad':
        return [k for k in keys if k in OH_KEYS]
    return [k for k in keys if k not in OH_KEYS]


def write_windows(agg, which, source, path=None):
    """MERGE `agg` into the aggregates file: the keys this run owns are replaced, every other key stays; 'ir' goes to its
    own file (band_windows_rruff_ir.json). `sources` records each run."""
    path = path or os.path.join(DATA, 'band_windows_rruff_ir.json' if which == 'ir' else 'band_windows_rruff.json')
    try:
        with open(path, encoding='utf-8') as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        doc = {}
    windows = dict(doc.get('windows') or {})
    for k in list(windows):
        if which == 'ir' or k in owned_keys(which, [k]):
            del windows[k]
    for k in owned_keys(which, list(agg)) if which != 'ir' else list(agg):
        windows[k] = agg[k]
    sources = dict(doc.get('sources') or {})
    if doc.get('source') and not sources:
        sources['raman'] = doc['source']
    sources[which] = source
    out = {'about': 'Where the bands of single-group minerals stand in a RRUFF library (the collection fetched from rruff.net by pxrd rruff --fetch, '
                    'or a Thermo OMNIC copy): percentiles per group and mode, modes assigned by the ion geometry alone (tools/rruff_windows.py); '
                    + ('the infrared collection, anchored on ν3 or ν1. ' if which == 'ir' else "processed Raman spectra; the O–H keys from RRUFF's broad scans. ")
                    + 'Aggregates only.',
           'sources': sources, 'percentiles': [5, 25, 50, 75, 95], 'trim_sigmas': TRIM, 'min_minerals': MIN_MINERALS,
           'technique': 'ir' if which == 'ir' else 'raman', 'windows': dict(sorted(windows.items()))}
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(out, fh, indent=1, ensure_ascii=False)
    return path


if __name__ == '__main__':
    sys.exit(main())
