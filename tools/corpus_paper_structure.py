"""Prototype: build a structure from a paper's PRINTED atomic coordinates and check it against the
same mineral's .cif — the validation set being the corpus papers that have both.

What it isolates: whether coordinates as printed (4-5 decimals, no esds, occasionally a fraction)
are good enough to reproduce the .cif's bond-valence sums. Symmetry operators and the site type
symbols are taken FROM THE .CIF on purpose: turning 'Pna21' into operators is a table lookup (a
solved, deterministic problem — no table is bundled yet), and valence assignment is a separate
question. Everything geometric — the cell and every x, y, z — comes from the paper.

    python3 tools/corpus_paper_structure.py "<folder with .cif + .pdf>" [more folders]
    CELL_FROM=cif ...      take the cell from the .cif too, isolating the coordinates alone

Measured 2026-09-06 over 176 pairs: 85 papers yielded a coordinate table, 49 of them complete
enough to use, 47 compared. With the .cif's cell: 28 structures (60 %) reproduce every cation's
bond-valence sum within 0.05 vu, 158/200 sites (79 %), median worst deviation 0.006 vu. End to
end (the paper's cell as well): 19 structures, 109/200 sites. The failures are gross, not
marginal (p25 0.000, median 0.004, p75 0.810 vu), so a gate can refuse them.
"""
import os, re, sys, glob, tempfile, collections

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pxrd_review import bv_check as B, paper_extract as PE, epma as EP, symops as SO

HDR = re.compile(r'(?<![A-Za-z])(x/a|y/b|z/c|x|y|z|U ?eq|U ?iso|B ?iso|Wyck\w*|Site|Atom|occ\.?|s\.o\.f\.?)(?![A-Za-z])', re.I)
AXIS = re.compile(r'^\(?([xyz])(?:/[abc])?\)?$', re.I)      # 'x', 'x/a', '(x)'
VAL = re.compile(r'^([-−]?(?:\d*\.\d+|[01](?:\.0*)?|\d/\d))(?:\((\d+)\))?$')
VULGAR = {'½': 0.5, '⅓': 1 / 3.0, '⅔': 2 / 3.0, '¼': 0.25, '¾': 0.75, '⅙': 1 / 6.0, '⅚': 5 / 6.0,
          '⅛': 0.125, '⅜': 0.375, '⅝': 0.625, '⅞': 0.875}
def _val(t):
    """'0.12345(7)' -> 0.12345; '1/2' -> 0.5; '-0.0123' -> -0.0123; None when not a coordinate."""
    t = t.replace('\u2212', '-').rstrip(',')
    if t in VULGAR:
        return VULGAR[t]
    if t.startswith('-') and t[1:] in VULGAR:
        return -VULGAR[t[1:]]
    m = VAL.match(t)
    if not m:
        return None
    v = m.group(1)
    if '/' in v:
        a, b = v.split('/'); return float(a) / float(b)
    return float(v)

LABEL = re.compile(r'^([A-Z][a-z]?)([A-Za-z]?\(?\d{0,2}\)?[A-Za-z]?)$')     # O1, Ow1, O1W, M(2), Na1a
WYCK = re.compile(r'^\(?\d{1,2}[a-z]\)?$')                                # a Wyckoff token between label and x
FRACT_MAX = 1.05                                                          # a fractional coordinate, nothing else

def _label_ok(t):
    m = LABEL.match(t.rstrip(',*†‡§'))
    return bool(m) and m.group(1) in EP.ATOMIC_WEIGHTS

def _view(lines, lo, hi):
    """The page restricted to one text column: page_lines merges both columns of a two-column page
    into one line, so filtering the words by x is exactly what reading that column gives."""
    out = []
    for ln in lines:
        ws = [w for w in ln['w'] if lo <= (w[0] + w[2]) / 2 <= hi]
        if ws:
            out.append(dict(ln, w=ws))
    return out

def _scan(lines):
    """The widest atom-site table in one view -> [(label, x, y, z)]."""
    best = []
    for i, ln in enumerate(lines):
        hits = {h.lower()[0] for h in HDR.findall(' '.join(w[4] for w in ln['w']))}
        if not {'x', 'y', 'z'} <= hits:
            continue
        cols = {}
        for w in ln['w']:
            m = AXIS.match(w[4])
            if m and m.group(1).lower() not in cols:
                cols[m.group(1).lower()] = (w[0] + w[2]) / 2
        if len(cols) < 3:
            continue
        labx = next(((w[0] + w[2]) / 2 for w in ln['w']
                     if re.fullmatch(r'Site|Atom|Label|Ion|Position', w[4].strip('*.'), re.I)), None)
        rows = []; miss = 0; seen_lab = set()
        for ln2 in lines[i + 1:]:
            ws = ln2['w']
            if not ws:
                continue
            xcol = cols['x']
            lab = ws[0][4].strip()
            if not _label_ok(lab):
                # a two-column page can leave the neighbouring column's digits at the head of the
                # line; then the label is the last label-like token still left of the x column
                cands = [w for w in ws if (w[0] + w[2]) / 2 < xcol - 6 and _label_ok(w[4].strip())]
                if cands:
                    lab = cands[-1][4].strip()
            rest = ws[1:]
            if rest and WYCK.match(rest[0][4]):
                rest = rest[1:]
            got = {}
            for w in rest:
                v = _val(w[4])
                if v is None or abs(v) > FRACT_MAX:      # Ueq, occupancy and any prose number are not coordinates
                    continue
                xc = (w[0] + w[2]) / 2
                k = min(cols, key=lambda c: abs(cols[c] - xc))
                if abs(cols[k] - xc) <= 26 and k not in got:
                    got[k] = v
            if _label_ok(lab) and len(got) == 3:
                zx = cols['z']
                tail = ' '.join(w[4] for w in rest if (w[0] + w[2]) / 2 > zx + 14)   # Uiso, then the occupancy
                key = lab.upper().strip('*†‡§,')
                if key in seen_lab:
                    break            # the same site again: the scan has walked into the NEXT table —
                                     # anisotropic displacement parameters carry the same labels and
                                     # values in the same range, and would be read as coordinates
                seen_lab.add(key)
                rows.append((lab, got['x'], got['y'], got['z'], tail)); miss = 0
            else:
                miss += 1
                if rows and miss >= 4:
                    break
        if len(rows) > len(best):
            best = rows
    return best

def _ndec(t):
    """How many decimals a token is printed to — 0.12345(7) -> 5. The one thing that separates a
    coordinates table from its neighbours: coordinates are given to 4-5 decimals, bond valences to
    2-3, and a displacement parameter is small as well as short."""
    m = re.match(r'^-?\d*\.(\d+)', t.replace('\u2212', '-'))
    return len(m.group(1)) if m else 0


def _scan_by_content(lines):
    """A coordinates table found by what its columns hold, for the papers that print no header the
    reader knows. A row is a site label followed by three numbers in [-1, 1]; a run of at least
    three such rows is a table, and it is only accepted when the numbers are printed to four
    decimals or more — which is what tells it from a bond-valence table (2-3 decimals, and its rows
    are anions) or a displacement-parameter table (small values, and the same labels again)."""
    cand = []
    for i, ln in enumerate(lines):
        ws = ln['w']
        vals = [(w, _val(w[4])) for w in ws]
        nums = [(w, v) for w, v in vals if v is not None and abs(v) <= FRACT_MAX]
        if len(nums) < 3:
            cand.append(None); continue
        first_x = min((w[0] + w[2]) / 2 for w, _v in nums)
        lab = next((w[4].strip() for w in ws
                    if (w[0] + w[2]) / 2 < first_x and _label_ok(w[4].strip())), None)
        cand.append((lab, nums) if lab else None)
    best = []
    i = 0
    while i < len(cand):
        if cand[i] is None:
            i += 1; continue
        j = i; rows = []; seen = set(); gap = 0
        while j < len(cand) and gap <= 2:
            if cand[j] is None:
                gap += 1; j += 1; continue
            lab, nums = cand[j]
            key = lab.upper().strip('*†‡§,')
            if key in seen:
                break                                   # the same site again: the next table
            seen.add(key); rows.append((j, lab, nums)); gap = 0; j += 1
        if len(rows) >= 3:
            xs = sorted((w[0] + w[2]) / 2 for _j, _l, nums in rows for w, _v in nums)
            cols = []
            for x in xs:
                if cols and x - cols[-1][-1] <= 10:
                    cols[-1].append(x)
                else:
                    cols.append([x])
            cols = [sum(c) / len(c) for c in cols if len(c) >= max(2, 0.5 * len(rows))][:3]
            decs = [_ndec(w[4]) for _j, _l, nums in rows for w, _v in nums if _ndec(w[4])]
            if len(cols) == 3 and decs and sorted(decs)[len(decs) // 2] >= 4:
                out = []
                for _j, lab, nums in rows:
                    got = {}
                    for w, v in nums:
                        xc = (w[0] + w[2]) / 2
                        k = min(range(3), key=lambda k_: abs(cols[k_] - xc))
                        if abs(cols[k] - xc) <= 26 and k not in got:
                            got[k] = (v, w)
                    if len(got) == 3:
                        zx = cols[2]
                        tail = ' '.join(w[4] for w, _v in nums if (w[0] + w[2]) / 2 > zx + 14)
                        out.append((lab, got[0][0], got[1][0], got[2][0], tail))
                if len(out) > len(best):
                    best = out
        i = max(j, i + 1)
    return best


def paper_sites(pdf):
    """The paper's atom-site table, tried on the whole page and on each text column of it."""
    best = []
    try:
        pages = PE._pages(pdf)
    except Exception:
        return best
    for lines in pages:
        xs = [w[0] for ln in lines for w in ln['w']] + [w[2] for ln in lines for w in ln['w']]
        if not xs:
            continue
        mid = (min(xs) + max(xs)) / 2
        for view in (lines, _view(lines, -1e9, mid + 8), _view(lines, mid - 8, 1e9)):
            for r in (_scan(view), _scan_by_content(view)):
                if len(r) > len(best):
                    best = r
    return best

ELEM = re.compile(r'([A-Z][a-z]?)(\d*\.?\d*)')

def site_element(label, tail):
    """The element a site carries. A paper labels sites crystallographically — A1, M2, T3 — and
    names the elements in the site-occupancy column ('Ca0.674(11)Mn0.326(11)'): the dominant one is
    the site's element. Only when that column says nothing does the label have to carry it."""
    best = None
    for el, num in ELEM.findall(re.sub(r'\(\d+\)', '', tail or '')):
        if el not in EP.ATOMIC_WEIGHTS:
            continue
        v = float(num) if num else 1.0
        if best is None or v > best[1]:
            best = (el, v)
    if best:
        return best[0]
    m = re.match(r'([A-Z][a-z]?)', label)
    if m and m.group(1) in EP.ATOMIC_WEIGHTS:
        return m.group(1)
    return (label[:1] if label[:1] in EP.ATOMIC_WEIGHTS else None)

def element_charges(text, name=None):
    """{element: oxidation state} from the paper's own formulas — 'Fe3+1.52' states the charge — and
    from the species' ideal formula on Mindat when the paper's does not say."""
    ox = {}
    try:
        for _t, _c, _i, charges, _k, _s in PE._formulas(text, name or ''):
            for el, chs in (charges or {}).items():
                if len(chs) == 1:
                    ox.setdefault(el, sorted(chs)[0])
    except Exception:
        pass
    try:
        rec = PE.species_record(name) if name else None
        for el, ch in re.findall(r'([A-Z][a-z]?)(\d)\+', (rec or {}).get('formula') or ''):
            ox.setdefault(el, int(ch))
    except Exception:
        pass
    return ox

def norm(lab):
    return re.sub(r'[^A-Za-z0-9]', '', lab).upper()

def cif_sites(path):
    b = [x for x in B.read_cif(path) if B._loop(x, '_atom_site_fract_x')[1]][0]
    tags, rows = B._loop(b, '_atom_site_fract_x')
    g = lambda t, d=None: B._col(tags, rows, t, d)
    out = []
    for lab, ty, x, y, z in zip(g('_atom_site_label'), g('_atom_site_type_symbol', ''),
                                g('_atom_site_fract_x'), g('_atom_site_fract_y'), g('_atom_site_fract_z')):
        out.append((lab, ty, B._num(x), B._num(y), B._num(z)))
    return out, b

def symop_text(block):
    tags, rows = B._loop(block, '_space_group_symop_operation_xyz')
    tag = '_space_group_symop_operation_xyz'
    if rows is None:
        tags, rows = B._loop(block, '_symmetry_equiv_pos_as_xyz'); tag = '_symmetry_equiv_pos_as_xyz'
    if rows is None:
        return None
    return tag, B._col(tags, rows, tag)

def synth_cif(cell, symtag, ops, sites, formula=''):
    """A CIF carrying the paper's cell, coordinates and site elements (with the charges its formula
    states), and the operators its space-group symbol stands for."""
    L = ['data_paper']
    if formula:
        L.append("_chemical_formula_sum '%s'" % formula)
    for k, v in zip(('a', 'b', 'c'), cell[:3]):
        L.append('_cell_length_%s %.5f' % (k, v))
    for k, v in zip(('alpha', 'beta', 'gamma'), cell[3:]):
        L.append('_cell_angle_%s %.4f' % (k, v))
    L += ['loop_', symtag]
    L += ["'%s'" % s for s in ops]
    L += ['loop_', '_atom_site_label', '_atom_site_type_symbol',
          '_atom_site_fract_x', '_atom_site_fract_y', '_atom_site_fract_z']
    for lab, ty, x, y, z in sites:
        L.append("%s %s %.5f %.5f %.5f" % (lab, ty or re.match(r'[A-Za-z]{1,2}', lab).group(0), x, y, z))
    return '\n'.join(L) + '\n'

def bvs_map(st):
    """{site: (bvs, expected valence)} for every cation, plus the global instability index."""
    P = B.Params(prefer='gh', u6='burns')
    res, anion_sum, cells, hb = B.compute(st, P, None, 'oo')
    out = {}
    for c, bonds, bvs, exp, md in res:
        fx, fy, fz = c.frac
        out[norm(c.label)] = (bvs, exp, fx, fy, fz)
    gii = 0.0
    if out:
        gii = (sum((v[0] - v[1]) ** 2 for v in out.values()) / len(out)) ** 0.5
    return out, gii


def pairs(folder):
    cifs = glob.glob(os.path.join(folder, '*.cif')); pdfs = glob.glob(os.path.join(folder, '*.pdf'))
    out = []
    for c in sorted(cifs):
        ids = set(re.findall(r'I\d{6}', os.path.basename(c))) | set(re.findall(r'^\d{4,5}', os.path.basename(c)))
        m = [p for p in pdfs if any(i in os.path.basename(p) for i in ids)]
        if m:
            out.append((c, sorted(m)))
    return out


def structure_from_paper(pdf, tmpdir):
    """A structure built from nothing but the paper: its coordinates table, the space group its text
    states (expanded through the operator table), the cell it prints, and the charges its formula
    gives. Several cells may be printed — a powder one, a single-crystal one, another phase's — so
    each is tried and the one whose bond valences come out closest to the expected ones is kept.
    That is the structure judging its own cell: a wrong cell gives an absurd instability index.
    -> (Structure, info dict) or (None, why)."""
    text = PE.text_of(pdf)
    rows = paper_sites(pdf)
    if len(rows) < 3:
        return None, {'why': 'no coordinate table read'}
    sym, phrase = SO.find_in_text(text)
    if not sym:
        return None, {'why': 'no space group the operator table knows'}
    ops_variants = SO.lookup(sym)
    if not ops_variants:
        return None, {'why': 'space group %s not in the operator table' % sym}
    name = PE.mineral_name(text)
    charges = element_charges(text, name)
    fs = PE._formulas(text, name)
    counts = fs[0][1] if fs else {}
    sites = []
    for lab, x, y, z, tail in rows:
        el = site_element(lab, tail)
        if not el:
            continue
        ch = charges.get(el)
        sites.append((lab, '%s%d+' % (el, ch) if ch else el, x, y, z))
    if len(sites) < 3:
        return None, {'why': 'no site element could be named'}
    cands = [c for _ctx, c in PE._paper_cells(text)][:6]
    if not cands:
        return None, {'why': 'no cell in the text'}
    best = None
    for ci, cd in enumerate(cands):
        cell = [cd[k] for k in ('a', 'b', 'c', 'α', 'β', 'γ')]
        for vi, ops in enumerate(ops_variants):
            path = os.path.join(tmpdir, 'p%d_%d.cif' % (ci, vi))
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(synth_cif(cell, '_space_group_symop_operation_xyz',
                                      ['%s' % _op_str(o) for o in ops], sites, ''))
                st = B.Structure(path)
                m, gii = bvs_map(st)
            except Exception:
                continue
            if not m:
                continue
            if best is None or gii < best[1]:
                best = (st, gii, cell, sym, len(sites))
    if best is None:
        return None, {'why': 'no cell and operator set gave a structure'}
    st, gii, cell, sym, n = best
    return st, {'gii': gii, 'cell': cell, 'sym': sym, 'sites': n, 'cells_tried': len(cands),
                'closure': closure(st, counts)}


def _op_str(op):
    """(rot, tr) -> 'x, y+1/2, -z' for the synthetic CIF."""
    rot, tr = op
    parts = []
    for i in range(3):
        t = ''
        for j, v in enumerate(('x', 'y', 'z')):
            c = rot[i][j]
            if abs(c) < 1e-6:
                continue
            t += ('-' if c < 0 else ('+' if t else '')) + (v if abs(abs(c) - 1) < 1e-6 else '%g%s' % (abs(c), v))
        f = tr[i] - int(tr[i])
        if f > 1e-6:
            num = int(round(f * 12))
            from math import gcd
            g = gcd(num, 12)
            t += '+%d/%d' % (num // g, 12 // g)
        parts.append(t or '0')
    return ', '.join(parts)


def closure(st, counts):
    """The structure against the paper's own formula: the sites, taken with their multiplicities,
    must hold the elements in the proportions the formula states. Compared as ratios to the most
    abundant cation, so no Z is needed. -> mean relative deviation, or None when nothing to compare.

    This catches what the instability index cannot: a coordinates table read only in part still
    gives sound valences for the sites it did read, but its composition is not the mineral's."""
    if not counts:
        return None
    cell = {}
    for site in list(st.cations) + list(st.anions):
        for sp in site.species:
            cell[sp.element] = cell.get(sp.element, 0.0) + site.mult * sp.occ
    cell.pop('H', None)
    want = {k: v for k, v in counts.items() if k not in ('H',) and v > 0}
    if not cell or not want:
        return None
    ref = max((k for k in want if k in cell), key=lambda k: want[k], default=None)
    if ref is None or not cell.get(ref):
        return None
    devs = []
    for el, v in want.items():
        mine = cell.get(el, 0.0) / cell[ref] * want[ref]
        devs.append(abs(mine - v) / max(v, 0.05))
    return sum(devs) / len(devs)


GATE = float(os.environ.get('GII_GATE', '0.25'))       # a structure whose valences do not come out is refused


def _use_layout_reader():
    """PAGES=docling reads the tables through the layout model instead of the pdf's word positions —
    a coordinates table is dense and gridded, the case a word-position reader finds hardest."""
    if os.environ.get('PAGES') != 'docling':
        return False
    from pxrd_review import layout_reader as LR
    if not LR.available():
        print('PAGES=docling asked for but docling is not installed'); return False
    PE.set_pages_reader(LR.pages, 'replace')
    return True


def main(folders):
    stat = collections.Counter(); rows = []
    if _use_layout_reader():
        print('reading pages through the layout model (docling)\n')
    tmpdir = tempfile.mkdtemp(prefix='paperstruct_')
    for folder in folders:
        for cif, pdfs in pairs(folder):
            name = os.path.basename(cif); stat['pairs'] += 1
            try:
                truth, gii_cif = bvs_map(B.Structure(cif))
            except Exception as e:
                stat['cif unusable'] += 1; rows.append((name, 'cif unusable: %s' % str(e)[:48], None)); continue
            if not truth:
                stat['cif has no cations'] += 1; continue
            st = None
            for pdf in pdfs:
                st, info = structure_from_paper(pdf, tmpdir)
                if st is not None:
                    break
            if st is None:
                stat[info['why']] += 1; rows.append((name, info['why'], None)); continue
            stat['structure built from the paper'] += 1
            mine, gii = bvs_map(st)
            clo = info.get('closure')
            if gii > GATE:
                stat['refused by the instability gate'] += 1
                rows.append((name, 'built, but GII %.2f vu > %.2f — refused' % (gii, GATE), None)); continue
            stat['passed the gate'] += 1
            # match sites by POSITION, not by label: a paper names sites A1/M2/T3, a .cif by element
            pairs_ = []
            for k, (bv, exp, x, y, z) in mine.items():
                bestm = None
                for k2, (bv2, exp2, x2, y2, z2) in truth.items():
                    d = max(abs((x - x2 + .5) % 1 - .5), abs((y - y2 + .5) % 1 - .5), abs((z - z2 + .5) % 1 - .5))
                    if bestm is None or d < bestm[0]:
                        bestm = (d, k2, bv2)
                if bestm and bestm[0] < 0.02:
                    pairs_.append((k, bestm[1], bv, bestm[2]))
            if not pairs_:
                stat['no site matched by position'] += 1; rows.append((name, 'no site matched by position', None)); continue
            ok = sum(1 for _a, _b, x, y in pairs_ if abs(x - y) <= 0.05)
            worst = max(abs(x - y) for _a, _b, x, y in pairs_)
            stat['compared'] += 1
            stat['every site within 0.05 vu'] += (ok == len(pairs_))
            rows.append((name, 'GII %.3f | closure %s | sites %d matched of %d | BVS %d/%d within 0.05 vu, worst %.3f'
                         % (gii, ('%.2f' % clo) if clo is not None else '  - ', len(pairs_), len(truth), ok, len(pairs_), worst),
                         (ok, len(pairs_), worst, clo)))
    print('=== per pair')
    for n, msg, _ in rows:
        print('  %-34s %s' % (n[:34], msg))
    print('\n=== totals')
    for k, v in stat.most_common():
        print('  %4d  %s' % (v, k))
    good = [r[2] for r in rows if r[2]]
    if good:
        tot = sum(g[1] for g in good); okk = sum(g[0] for g in good)
        print('\n  cation sites compared: %d; within 0.05 vu: %d (%.0f %%)' % (tot, okk, 100.0 * okk / tot))
        print('  worst deviation per structure: median %.3f vu, max %.3f vu'
              % (sorted(g[2] for g in good)[len(good) // 2], max(g[2] for g in good)))


if __name__ == '__main__':
    main(sys.argv[1:])
