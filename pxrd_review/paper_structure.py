"""A structure from the paper itself, for the papers that come without a .cif.

`bv_check` needs a structure; roughly half the corpus's papers print one — a coordinates table, a
space-group symbol and a cell — and the other half deposit it with the CCDC or CSD instead. Where a
paper prints one, this builds it: the coordinates as typeset, the operators the symbol stands for
(`symops`), the element of each site from the site-occupancy column, and the charges from the
paper's own formula.

Two gates decide whether the result may be used, and they catch different faults:

  the global instability index   bond valences that do not come out mean the cell, the coordinates
                                 or the space group is wrong. Threshold 0.15 vu.
  composition closure            the sites, taken with their multiplicities, must hold the elements
                                 in the proportions the paper's formula states. This is what catches
                                 a coordinates table read only in part — its sites still give sound
                                 valences, but its composition is not the mineral's.

Measured over 176 corpus papers that have BOTH a printed structure and a .cif to score against:
at GII <= 0.15, 17 papers pass and 49 of their 54 cation sites (91 %) reproduce the .cif's
bond-valence sums within 0.05 vu. That is note-grade, not flag-grade, and the tool treats it so:
every line this produces is marked [unverified]. With composition closure required as well, 4
papers pass and all 13 of their sites are exact — flag-grade, but too few to rely on.
"""
import os, re, shutil, tempfile

from pxrd_review import bv_check as B
from pxrd_review import epma as EP
from pxrd_review import paper_extract as PE
from pxrd_review import symops as SO

GII_GATE = 0.15                 # note-grade: 91 % of sites reproduce the .cif at this threshold
CLOSURE_GATE = 0.25             # with this as well the sample was exact, but only 4 papers wide


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

SITE_LETTERS = set('AMTXYZQDEGJLRW')                                       # a crystallographic site name: A1, M2A, T(1), X(3), Q2 — not an element

def _label_ok(t):
    """'O1', 'Si2', 'Na1a' — and 'Ow1'/'OW1', the water oxygen, whose two-letter head is not an
    element: fall back to the first letter, which is. A paper's own site name (A1, M2A, T(1), X(3))
    is a label too — its element comes from the occupancy column, and its coordinates are what map
    the paper's names onto the .cif's."""
    t = t.rstrip(',*†‡§')
    m = LABEL.match(t)
    if not m:
        return False
    if m.group(1) in EP.ATOMIC_WEIGHTS or m.group(1)[:1] in EP.ATOMIC_WEIGHTS:
        return True
    return len(m.group(1)) == 1 and (m.group(1) in SITE_LETTERS and bool(re.search(r'\d', m.group(2))) or (m.group(1) in 'XYZTMA' and not m.group(2)))   # 'X', 'Y', 'Z', 'T': a tourmaline's sites, bare

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

def element_charge_sets(text, name=None):
    """{element: {oxidation states}} the paper's formulas state ('Fe2+', 'Fe3+' — both, for a
    mixed-valence mineral), else the species' ideal formula on Mindat."""
    ox = {}
    try:
        for _t, _c, _i, charges, _k, _s in PE._formulas(text, name or ''):
            for el, chs in (charges or {}).items():
                ox.setdefault(el, set()).update(chs)
    except Exception:
        pass
    try:                                                                # Mindat for the elements the paper's formulas leave uncharged
        rec = PE.species_record(name) if name else None
        mindat = {}
        for el, ch in re.findall(r'([A-Z][a-z]?)(\d)\+', re.sub(r'<[^>]+>', '', (rec or {}).get('formula') or '')):
            mindat.setdefault(el, set()).add(int(ch))
        for el, chs in mindat.items():
            ox.setdefault(el, chs)
    except Exception:
        pass
    return ox

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
        for el, ch in re.findall(r'([A-Z][a-z]?)(\d)\+', re.sub(r'<[^>]+>', '', (rec or {}).get('formula') or '')):   # 'V<sup>3+</sup>' on Mindat
            ox.setdefault(el, int(ch))
    except Exception:
        pass
    return ox

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


def build(pdf, text=None):
    """The structure the paper prints, or None. -> (Structure, info) where info carries 'gii',
    'closure', 'cell', 'sym' and 'sites'; (None, {'why': ...}) when it cannot be built or does not
    pass the instability gate. A paper prints several cells — a powder one, a single-crystal one,
    sometimes another phase's — so each is tried and the one whose valences come out closest is
    kept: the structure judges its own cell."""
    text = PE.text_of(pdf) if text is None else text
    rows = paper_sites(pdf)
    if len(rows) < 3:
        return None, {'why': 'the paper prints no coordinates table the reader could find'}
    sym, _phrase = SO.find_in_text(text)
    ops_variants = SO.lookup(sym) if sym else []
    if not ops_variants:
        return None, {'why': 'no space group in the text that the operator table knows'}
    name = PE.mineral_name(text)
    charges = element_charges(text, name)
    fs = PE._formulas(text, name)
    counts = fs[0][1] if fs else {}
    sites = []
    for lab, x, y, z, tail in rows:
        el = site_element(lab, tail)
        if el:
            ch = charges.get(el)
            sites.append((lab, '%s%d+' % (el, ch) if ch else el, x, y, z))
    if len(sites) < 3:
        return None, {'why': 'no element could be named for the sites read'}
    cells = [c for _ctx, c in PE._paper_cells(text)][:6]
    if not cells:
        return None, {'why': 'no cell in the text'}
    best = None
    tmp = tempfile.mkdtemp(prefix='pxrd_ps_')
    keep = None
    try:
        for ci, cd in enumerate(cells):
            cell = [cd[k] for k in ('a', 'b', 'c', 'α', 'β', 'γ')]
            for vi, ops in enumerate(ops_variants):
                path = os.path.join(tmp, 'c%d_%d.cif' % (ci, vi))
                try:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(synth_cif(cell, '_space_group_symop_operation_xyz',
                                          [_op_str(o) for o in ops], sites))
                    st = B.Structure(path)
                    P = B.Params(prefer='gh', u6='burns')
                    notes = list(st.notes)
                    res, _an, _cells, _hb = B.compute(st, P, None, 'oo')
                    st.notes[:] = notes
                except Exception:
                    continue
                if not res:
                    continue
                gii = (sum((bvs - exp) ** 2 for _c, _b, bvs, exp, _m in res) / len(res)) ** 0.5
                if best is None or gii < best[1]:
                    best = (st, gii, cell, sym, len(sites)); keep = path
    finally:
        for fn in os.listdir(tmp):                       # the losing cells' files go at once
            f_ = os.path.join(tmp, fn)
            if f_ != keep:
                try:
                    os.unlink(f_)
                except OSError:
                    pass
    if best is None:
        _discard(keep, tmp)
        return None, {'why': 'no cell and operator set gave a structure'}
    st, gii, cell, sym, n = best
    try:
        info = {'gii': gii, 'cell': cell, 'sym': sym, 'sites': n, 'closure': closure(st, counts), 'path': keep, 'dir': tmp}
    except Exception:
        _discard(keep, tmp)                              # the caller sees the exception, not a leaked directory
        raise
    if gii > GII_GATE:
        _discard(keep, tmp)
        return None, dict(info, path=None, why='the structure the paper prints does not hold together '
                          '(instability index %.2f vu) — its cell, coordinates or space group is misread' % gii)
    return st, info


def _discard(path, tmpdir):
    """Remove the synthetic .cif and its directory. `build` hands back a path so the caller can pass
    it to anything that reads a .cif; the caller calls this when done."""
    for f_ in (path,):
        if f_:
            try:
                os.unlink(f_)
            except OSError:
                pass
    if tmpdir and os.path.basename(tmpdir).startswith('pxrd_ps_'):
        shutil.rmtree(tmpdir, ignore_errors=True)         # the tool's own directory, whatever a failed build left in it


def discard(info):
    """Clean up after a build() whose path was used."""
    if info and info.get('dir'):
        _discard(info.get('path'), info['dir'])
