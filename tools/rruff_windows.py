#!/usr/bin/env python3
"""The band library's ranges measured on a RRUFF Raman library (a Thermo OMNIC library: RRUFFLib.lbd + RRUFFLib.lbt).

    python3 tools/rruff_windows.py <folder with RRUFFLib.lbd/.lbt> [out_dir] [--write] [--check] [--show GROUP]

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
What the library cannot measure: the grid ends at 1495 cm-1 (no O–H stretch, no H2O bend, no oxalate C=O), it is Raman
only (an infrared-only mode is absent by nature), and the 2007 set holds one or two minerals of many groups.
Outputs (out_dir, default review_out beside the corpus): rruff_windows_report.txt, rruff_windows.jsonl (one line per
assigned band — private); --write puts the AGGREGATES into pxrd_review/data/band_windows_rruff.json.
"""
import os, re, sys, json, struct, collections, statistics
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from pxrd_review import spectrum as SPM, bands as BD, paper_extract as PE

LATTICE = 150.0            # cm-1: below this a Raman band is a lattice mode of any mineral
STRONG = 0.05              # of the strongest band: a band counted at all
KINDS = ('processed', 'clean', 'corrected')          # one spectrum per RRUFF id, the first of these it has (never 'raw')
TRIM = 3.0                 # robust sigmas, as tools/corpus_spectra.py
MIN_MINERALS = 3           # a window needs this many minerals


def read_omnic(folder):
    """[(name, x, y)] in the library's order. The .lbd: a text header of the length its first field says, then fixed
    records (759 float32 on one grid, then 12 bytes); the .lbt: one 256-character name per record, each closed by \\x17."""
    lbd = open(os.path.join(folder, 'RRUFFLib.lbd'), 'rb').read()
    lbt = open(os.path.join(folder, 'RRUFFLib.lbt'), 'rb').read()
    # the header's lines end in \r\n or \x00\n: tokens, not lines — length, company, library, version, '000', count,
    # record size, …, points, first x, last x
    toks = [t.strip().decode('latin-1') for t in re.split(rb'[\r\n\x00]+', lbd[:4000]) if t.strip()]
    hlen = int(toks[0]); n = int(toks[5]); rec = int(toks[6]); npts = int(toks[13])
    x0, x1 = float(toks[14]), float(toks[15])
    if hlen + n * rec != len(lbd) or rec < 4 * npts:
        raise SystemExit('the .lbd header (%d records of %d bytes, %d points, header %d) does not add up to its size %d' % (n, rec, npts, hlen, len(lbd)))
    dx = (x1 - x0) / (npts - 1)
    x = [x0 + k * dx for k in range(npts)]
    # each text record: a one-byte kind, \x01\xff, then the name in a 256-character field (space-padded; some kinds
    # close it with \x17 inside the field), then the record's numbers; the records stand in the .lbd's order
    found = {m.start(1) - 3: m.group(1) for m in re.finditer(rb'[\x00-\xff]\x01\xff([ -~\x80-\xff\x17]{256})', lbt)}
    # … and a few older records write the name as a length-prefixed string with no field at all ('\x16Sanbornite R050001_raw')
    spans = sorted((p + 3, p + 259) for p in found)
    for m in re.finditer(rb'([A-Z][A-Za-z\-\(\)\. ]{2,60}?R\d{6}[A-Za-z0-9_]{0,24})', lbt):
        p = m.start()
        if lbt[p - 1] == len(m.group(1)) and not any(a <= p < b for a, b in spans):
            found[p - 3] = m.group(1)
    names = {p: re.sub(r'[\x00-\x1f]', '', v.decode('latin-1')).strip() for p, v in found.items()}
    if len(names) != n:
        raise SystemExit('the .lbt holds %d names for %d spectra — the record layout is not the one this reader knows' % (len(names), n))
    # each data record ends in a pointer to its text record: three bytes b0 b1 b2 -> b0 + 256·b2 + 65536·b1 (so the
    # names are matched by pointer, not by order — though the two orders agree in this library)
    out = []; order = sorted(names); missed = 0
    for i in range(n):
        r = lbd[hlen + i * rec: hlen + (i + 1) * rec]
        b = r[4 * npts: 4 * npts + 3]
        ptr = b[0] + 256 * b[2] + 65536 * b[1]
        name = names.get(ptr)
        if name is None:
            missed += 1; name = names[order[i]]
        out.append((name, x, list(struct.unpack('<%df' % npts, r[:4 * npts]))))
    if missed:
        print('note: %d of %d text pointers matched no record; those names were taken by order' % (missed, n))
    return out


_ID = re.compile(r'R\d{6}')


def split_name(name):
    """'Whiteite-(CaFeMg)R060912_785processed' -> ('Whiteite-(CaFeMg)', 'R060912', 'processed')."""
    m = _ID.search(name)
    if not m:
        return name.strip(), '', ''
    mineral = name[:m.start()].strip().strip('_').strip()
    tail = name[m.end():].lower()
    kind = next((k for k in ('processed', 'clean', 'corrected', 'raw') if k in tail or (k == 'processed' and 'proc' in tail) or (k == 'raw' and tail.endswith('ra'))), '')
    return mineral, m.group(0), kind


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


def peaks_of(x, y):
    """[(pos, height)] of the bands above the lattice region, the weak ones (under STRONG of the strongest) dropped."""
    try:
        pk = SPM.find_peaks(x, y)
    except Exception:
        return []
    pk = [(p['pos'], p['height']) for p in pk if p['pos'] >= LATTICE and p['height'] > 0]
    if not pk:
        return []
    top = max(h for _p, h in pk)
    return sorted((p, h) for p, h in pk if h >= STRONG * top)


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


def assign(shape, modes, pk, free=None):
    """{mode: [positions]} for one spectrum of a single-group mineral. ν1 is the strongest band above the lattice region
    (and, where the free ion's ν1 is known, within NU1_TOL of it — else nothing is assigned: in a few silicates the bends
    dominate). Every other strong band goes to the mode whose FREE-ION position, scaled by the measured ν1, is nearest
    within RATIO_TOL — the free-ion values are the one literature input, and they are not the ranges being measured.
    A group with no free-ion values (borates) falls back to geometry windows. `modes` = the library's mode names (a
    combined 'ν2, ν4' row takes both); `free` = {mode: free-ion cm-1}."""
    out = collections.defaultdict(list)
    if not pk:
        return out
    free = {k: v for k, v in (free or {}).items() if v}
    floor = {'tetrahedral': 300.0, 'planar': 600.0, 'pyramidal': 500.0, 'linear': 700.0}.get(shape, 300.0)
    cand = [(p, h) for p, h in pk if p >= floor]
    if not cand:
        return out
    nu1 = max(cand, key=lambda t: t[1])[0]
    top = max(h for _p, h in pk)
    if free.get('ν1') and abs(nu1 / free['ν1'] - 1.0) > NU1_TOL:
        out['(ν1 not dominant)'].append(nu1)
        return out
    out['ν1'].append(nu1)
    pos = [p for p, h in pk if h >= ASSIGN_STRONG * top and abs(p - nu1) > 0.02 * nu1]
    combined = next((m for m in modes if ',' in m), None)
    others = {m: v for m, v in free.items() if m != 'ν1'}
    if combined and free.get('ν1'):                           # a combined row: its one free value stands for both bends
        others[combined] = free.get(combined) or free.get('ν2') or free.get('ν4')
        others = {m: v for m, v in others.items() if v and (m == combined or m == 'ν3')}
    if others and free.get('ν1'):
        scale = nu1 / free['ν1']
        for p in pos:
            best = min(others, key=lambda m: abs(p / (others[m] * scale) - 1.0))
            if abs(p / (others[best] * scale) - 1.0) <= RATIO_TOL:
                out[best].append(p)
            else:
                out['(unassigned)'].append(p)
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
    ap.add_argument('folder', help='the folder holding RRUFFLib.lbd and RRUFFLib.lbt')
    ap.add_argument('out_dir', nargs='?', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'review_out'))
    ap.add_argument('--write', action='store_true', help='write the aggregates to pxrd_review/data/band_windows_rruff.json')
    ap.add_argument('--check', action='store_true', help='the alignment of names and spectra: the strongest band of a few well-known minerals')
    ap.add_argument('--show', help='print every assigned band of one group (e.g. SO4)')
    a = ap.parse_args(argv)
    spectra = read_omnic(a.folder)
    lib = BD.library()
    groups = {g['key']: g for g in lib['groups']}
    # one spectrum per RRUFF id, the best kind it has
    best = {}
    for name, x, y in spectra:
        mineral, rid, kind = split_name(name)
        if not rid or kind not in KINDS:
            continue
        rank = KINDS.index(kind)
        if rid not in best or rank < best[rid][0]:
            best[rid] = (rank, mineral, name, x, y)
    if a.check:
        want = {'Quartz': 464, 'Calcite': 1086, 'Barite': 988, 'Fluorapatite': 965, 'Anhydrite': 1017, 'Scheelite': 911, 'Forsterite': 856}
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
    for _r, mineral, name, x, y in best.values():
        f = formula_of(mineral)
        if not f:
            counts['no formula'] += 1; continue
        keys = [k for k in BD.groups_of(f) if k not in ('OH', 'H2O')]
        if len(keys) != 1:
            counts['no group' if not keys else 'several groups'] += 1; continue
        g = keys[0]; counts['single-group spectra'] += 1
        pk = peaks_of(x, y)
        shape = groups[g].get('shape')
        free = {m['mode']: m.get('free') for m in groups[g]['modes']}
        if shape and free.get('ν1') and free['ν1'] > x[-1]:
            counts['group above the grid'] += 1; continue
        if shape:
            got = assign(shape, [m['mode'] for m in groups[g]['modes']], pk, free)
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
    L = ['BAND LIBRARY vs the RRUFF Raman library (%d spectra, %d RRUFF ids, one spectrum each; grid %d–%d cm-1)' % (len(spectra), len(best), round(spectra[0][1][0]), round(spectra[0][1][-1])),
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
                if m['active'] == 'IR':
                    why = 'infrared only'
                if hi > 1495:
                    why = 'above the library grid'
                body.append((key, m['mode'], rng, '', '', '', why, pubt))
            else:
                body.append((key, m['mode'], rng, '', '', '', '', pubt))
        for extra in ('(ν1 not dominant)', '(unassigned)'):
            if (key, extra) in rows:
                vals = rows[(key, extra)]
                body.append((key, extra, '', '%d–%d (%d)' % (round(pct([p for p, _m in vals], 5)), round(pct([p for p, _m in vals], 95)), round(pct([p for p, _m in vals], 50))),
                             str(len(vals)), str(len({m for _p, m in vals})), 'spectra left out: the strongest band is not near the free-ion ν1' if 'dominant' in extra else 'strong bands near no mode of the ion', ''))
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
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'pxrd_review', 'data', 'band_windows_rruff.json')
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump({'about': 'Where the bands of single-group minerals stand in a RRUFF Raman library (2007 OMNIC set, %d spectra, grid to 1495 cm-1): '
                                'percentiles per group and mode, modes assigned by the ion geometry alone (tools/rruff_windows.py). Aggregates only.' % len(spectra),
                       'percentiles': [5, 25, 50, 75, 95], 'trim_sigmas': TRIM, 'min_minerals': MIN_MINERALS, 'technique': 'raman', 'windows': agg}, fh, indent=1, ensure_ascii=False)
        print('written:', os.path.normpath(path))
    return 0


if __name__ == '__main__':
    sys.exit(main())
