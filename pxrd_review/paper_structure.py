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
import os, re, shutil, tempfile, functools

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
    """'0.12345(7)' -> 0.12345; '1/2' -> 0.5; '-0.0123' -> -0.0123; None when not a coordinate.
    The sign arrives as whichever dash the font has: minus, en, em, figure, non-breaking hyphen."""
    t = re.sub(r'^[\u2212\u2013\u2014\u2012\u2011\u2010]', '-', t).rstrip(',')
    if t in VULGAR:
        return VULGAR[t]
    if t.startswith('-') and t[1:] in VULGAR:
        return -VULGAR[t[1:]]
    m = VAL.match(t)
    if not m:
        return None
    v = m.group(1)
    if '/' in v:
        a, b = v.split('/'); return float(a) / float(b) if float(b) else None   # '1/0' is no coordinate (a d/0 in a powder column)
    return float(v)

def _val_scaled(t, scale):
    """A coordinate printed as an integer under a '(×104)' caption — '876.9(2)', '5000', '0' -> the fraction."""
    t = re.sub(r'^[\u2212\u2013\u2014\u2012\u2011\u2010]', '-', t.strip()).rstrip(',')
    m = re.fullmatch(r'(-?\d{1,5}(?:\.\d)?)(?:\(\d+\))?', t)                # at most one decimal digit: '876.9(2)', '5000', '0' — a '0.2345' is a fraction already
    if not m:
        return None
    return float(m.group(1)) * scale

LABEL = re.compile(r"^([A-Z][a-z]?)\*?([A-Za-z]?\(?\d{0,2}[a-z]?\)?[A-Za-z]?(?:_\d)?'?|\d{0,2}\([A-Z][A-Za-z]?\d{0,2}[a-z]?(?:_\d)?\)'?)$")     # O1, Ow1, O1W, M(2), M(2a), Na1a, Fe2_1, O6' — and Cu(M1), Mn(X): the element with its site name     # O1, Ow1, O1W, M(2), Na1a — and Cu(M1), Mn(X): the element with its site name
_OCC_ELS = re.compile(r'^(?:[A-Z][a-z]?\d*\.\d+(?:\(\d+\))?){1,4}$')            # 'Fe0.84Al0.16(2)': an occupancy written by element
_OCC_NUMFIRST = re.compile(r'^(?:\d*\.\d+(?:\(\d+\))?[A-Z][a-z]?/?){1,4}$')        # '0.302(9)Sb/0.698Pb': the share before its element
WYCK = re.compile(r'^\(?\d{1,2}[a-z]\)?$')                                # a Wyckoff token between label and x
FRACT_MAX = 1.05                                                          # a fractional coordinate, nothing else
FRACT_HDR = 2.0                                                           # under a known x/y/z header a coordinate may be printed past 1 ('1.06477(6)'); an integer there never is

SITE_PAREN = re.compile(r'^\(([A-Z][A-Za-z]?\d{0,2}[a-z]?(?:_\d)?)\)[*†‡§]*$')    # '(X)', '(M1)', '(M3a)': the site name printed beside its element
CAPTION = re.compile(r'^(?:TABLE|Table)\s+[A-Z]?\d{1,2}[A-Za-z]?\s*[.:]')                # 'Table 6.' — where the next table begins
SUBSCRIPT = re.compile(r'^[A-Z]$')                                         # 'XO' 'M': the subscript of a site label, set as a token of its own
SITE_LETTERS = set('AMTXYZQDEGJLRW')                                       # a crystallographic site name: A1, M2A, T(1), X(3), Q2 — not an element

_SCALED = re.compile(r'(?:coordinates|positions|positional parameters|x,?\s*y,?\s*z)\s*\(\s*[x×χ]?\s?10\s?([45])\s*\)', re.I)   # 'coordinates (×104)': printed as integers — the COORDINATES, never the '(Å2 × 103)' of the displacement parameters beside them

_OCCUPANTS = re.compile(r'^([A-Z][A-Za-z]?[*∗]?\d{0,2}[a-z]?)\(((?:[A-Z][a-z]?,?){1,4})\)$')   # 'T1(Al,Si)': the site and its occupants, dominant first

def _split_occupants(t):
    """'T1(Al,Si)' -> ('T1', 'Al Si'); any other token -> (token, '')."""
    m = _OCCUPANTS.match(t.strip().rstrip(','))
    if m and not re.fullmatch(r'\((?:[A-Z][a-z]?,)+[A-Z][a-z]?\)', t.strip()):
        return m.group(1), m.group(2).replace(',', ' ')
    return t, ''

def _clean_label(t):
    """The label as printed, less what the typesetting welded onto it: a Wyckoff position ('A(16c)',
    'X(8b)'), the site it stands for ('Pb1(≡A)', and 'O1(≡X' when the ')' became its own token), a
    prime on a twin's label ('Sb1/Sb1’'), a trailing comma ('X(3),')."""
    t = t.strip().rstrip(',').replace('∗', '*')
    t = re.sub(r'\(≡[^)]*\)?$', '', t)
    t = re.sub(r'^([ABXYZ])\(\d{1,2}[a-z]\)$', r'\1', t)               # a pyrochlore's A(16c), X(8b): the position welded onto a bare site letter — M(2a), O(1a) are site names and stay
    t = re.sub(r"[′’`]", "'", t)                                        # a prime is part of the label (O6' is another site than O6), as one glyph
    return t

def _prose_between(ws, i, j):
    """Two or more running-text words ('noted', 'above,') between tokens i and j of a line: what
    stands before j is the facing column's sentence, not a row of the table."""
    return sum(1 for w in ws[i + 1:j] if re.fullmatch(r'[a-z][a-z,.;:-]{1,}', w[4])) >= 2

def _label_ok(t):
    """'O1', 'Si2', 'Na1a' — and 'Ow1'/'OW1', the water oxygen, whose two-letter head is not an
    element: fall back to the first letter, which is. A paper's own site name (A1, M2A, T(1), X(3))
    is a label too — its element comes from the occupancy column, and its coordinates are what map
    the paper's names onto the .cif's."""
    t = t.rstrip(',*†‡§')
    if t.lower() in ('cell', 'vol', 'volume', 'space', 'total', 'sum', 'table', 'atom', 'site', 'wyckoff', 'occ', 'occupancy', 'density', 'formula') \
            or re.fullmatch(r'U(?:eq|iso|equiv|11|22|33|12|13|23)|B(?:eq|iso|11|22|33|12|13|23)|Ueq\*?', t):
        return False                                                      # a crystal-data table's rows ('Cell', 'V', 'Z' — 70910 read them as Th, F, F sites at an instability index of 0.02); a transposed displacement table's ('Ueq', 'U11' … — uranium sites to the eye, 77074)
    if '/' in t:                                                          # 'Fe1/Al1', 'Ca/Mg', 'K/O': a split site, both halves labels
        parts = t.split('/')
        return len(parts) == 2 and all(p and _label_ok(p) for p in parts)
    if re.fullmatch(r'(?:REE|Ree|Ln|LN|TR)\d{0,2}[a-z]?', t):
        return True                                                       # 'REE1', 'Ln2': a rare-earth site named for the group (alexkuznetsovite)
    if re.fullmatch(r'\((?:[A-Z][a-z]?,)+[A-Z][a-z]?\)\d{0,2}', t):
        return True                                                       # '(Cu,Hg)', '(Bi,Pb)1': a mixed site named by its occupants (hansblockite)
    m = LABEL.match(t)
    if not m:
        return False
    if m.group(1) in EP.ATOMIC_WEIGHTS or m.group(1)[:1] in EP.ATOMIC_WEIGHTS:
        return True
    return len(m.group(1)) == 1 and (m.group(1) in SITE_LETTERS and bool(re.search(r'\d', m.group(2))) or (m.group(1) in 'XYZTMA' and not m.group(2))   # 'X', 'Y', 'Z', 'T': a tourmaline's sites, bare
                                     or (m.group(1) in SITE_LETTERS and re.fullmatch(r'[A-Z]', m.group(2)) is not None))   # 'MH', 'AP', 'XO': a site named by two letters

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
        # a value sits under its header within a share of the column spacing: a right-aligned '0.24850(10)'
        # under a centred 'y' in a wide table is 27 pt off, a narrow table's columns are 40 pt apart
        gaps = sorted(cols.values()); span = min((b - a) for a, b in zip(gaps, gaps[1:])) if len(gaps) >= 2 else 60
        tol = max(26.0, min(0.45 * span, 44.0))
        labx = next(((w[0] + w[2]) / 2 for w in ln['w']
                     if re.fullmatch(r'Site|Atom|Label|Ion|Position', w[4].strip('*.'), re.I)), None)
        # 'Table 4. Refined fractional atomic coordinates (×104)': the coordinates are printed as
        # integers (876.9(2), 5000), to be read at that scale — said in the caption within eight lines above
        scale = None
        for k in range(i - 1, -1, -1):                                   # by distance up the page, not by line count: a two-column page interleaves the other column's lines
            if ln['y'] - lines[k]['y'] > 90:
                break
            m_ = _SCALED.search(' '.join(w[4] for w in lines[k]['w']))
            if m_:
                scale = 1e-5 if m_.group(1) == '5' else 1e-4
        rows = []; miss = 0; seen_lab = set()
        for ln2 in lines[i + 1:]:
            ws = ln2['w']
            if not ws:
                continue
            if rows and CAPTION.match(' '.join(w[4] for w in ws[:3])):
                break                                    # the next table's caption: this one has ended
            xcol = cols['x']
            lab = _clean_label(_split_occupants(ws[0][4])[0]); lab_i = 0
            cands = [q for q, w in enumerate(ws) if (w[0] + w[2]) / 2 < xcol - 6 and _label_ok(_clean_label(_split_occupants(w[4])[0]))]
            if not _label_ok(lab) or (cands and cands[-1] > 0 and _prose_between(ws, 0, cands[-1])):
                # a two-column page can leave the neighbouring column's prose at the head of the line
                # ('As noted above, michalski M3 0.42295(8) …': 'As' is a word there, not arsenic); then
                # the label is the last label-like token still left of the x column
                if cands:
                    lab_i = cands[-1]; lab = _clean_label(_split_occupants(ws[lab_i][4])[0])
            occupants = _split_occupants(ws[lab_i][4])[1]
            rest = ws[lab_i + 1:]
            if rest and WYCK.match(rest[0][4]):
                rest = rest[1:]
            if re.fullmatch(r'[A-Z][a-z]?', lab) and rest and re.fullmatch(r'\d{1,2}', rest[0][4]) and rest[0][0] - ws[lab_i][2] < 12 \
                    and (rest[0][0] + rest[0][2]) / 2 < xcol - 20:
                lab = lab + rest[0][4]; rest = rest[1:]             # 'V 1', 'O 12': the label's number set as a token of its own (sincosite)
            if _label_ok(lab) and rest and (rest[0][0] + rest[0][2]) / 2 < xcol - 6 and (SITE_PAREN.match(rest[0][4].strip()) or (SUBSCRIPT.match(rest[0][4].strip()) and lab.isalpha())):
                lab = lab + rest[0][4].strip().rstrip('*†‡§,'); rest = rest[1:]   # 'Mn (X)', 'Al1 (M3a)': the site name beside the element; 'XO' 'M': a subscript set as its own token
            got = {}; used = set()
            for w in rest:
                v = _val_scaled(w[4], scale) if scale else None           # '876.9(2)' under '(×104)' is 0.08769, not a value of 876.9 to be thrown out
                if v is None:
                    v = _val(w[4])
                if v is None or abs(v) > FRACT_HDR or (abs(v) > FRACT_MAX and _ndec(w[4]) < 3 and not scale):   # Ueq, occupancy and any prose number are not coordinates
                    continue
                xc = (w[0] + w[2]) / 2
                k = min(cols, key=lambda c: abs(cols[c] - xc))
                if abs(cols[k] - xc) <= tol and k not in got:
                    got[k] = v; used.add(id(w))
            if _label_ok(lab) and len(got) == 3:
                zx = cols['z']
                tail = ' '.join(w[4] for w in rest if (w[0] + w[2]) / 2 > zx + 14)   # Uiso, then the occupancy
                left = [w[4] for w in rest if id(w) not in used and (w[0] + w[2]) / 2 < xcol - 6 and _occupancy('occ=' + w[4]) is not None]   # never a coordinate already placed
                if left:
                    tail = 'occ=' + left[-1] + ' ' + tail                              # the occupancy column printed before x
                named = [w[4] for w in rest if id(w) not in used and (w[0] + w[2]) / 2 < xcol - 6 and (_OCC_ELS.search(w[4]) or _OCC_NUMFIRST.match(w[4]))]
                if named:
                    tail = named[-1] + ' ' + tail                                       # 'K0.76N0.24(2)': the occupancy by element, for site_element
                elif not re.match(r'[A-Z][a-z]?', lab) or re.match(r'[A-Z][a-z]?', lab).group(0) not in EP.ATOMIC_WEIGHTS:
                    # 'Site, Wyckoff | Atom | s.o.f.': the element in a column of its own beside a site
                    # named crystallographically ('X(3), 8c Sb1 0.9421 …'; 'M1 4c 0.25 Fe3+ ¼ …'; 'T 8i
                    # 0.38(1) As5+ 0.12(1) P …' — a charge on the symbol, the share printed before it)
                    before = [w for w in rest if id(w) not in used and (w[0] + w[2]) / 2 < xcol - 6]
                    atoms = []
                    for q_, w in enumerate(before):
                        m_ = re.fullmatch(r'([A-Z][a-z]?)\d{0,2}(?:\d?[+\-−])?', w[4])
                        if m_ and m_.group(1) in EP.ATOMIC_WEIGHTS:
                            share = before[q_ - 1][4] if q_ >= 1 and re.fullmatch(r'0?\.\d+(?:\(\d+\))?|1(?:\.0+)?', before[q_ - 1][4]) else ''
                            atoms.append(m_.group(1) + re.sub(r'\(\d+\)', '', share))
                    if atoms:
                        tail = ' '.join(atoms) + ' ' + tail
                if occupants:
                    tail = occupants + ' ' + tail                                       # 'T1(Al,Si)': the occupants named on the label, dominant first
                lab = lab.rstrip('*†‡§,') if not re.match(r'^[A-Z][a-z]?\*\d', lab) else lab   # 'Mn*', 'M2**': a footnote mark is not the label; 'T*1' is a split site's own name
                key = lab.upper()
                if key in seen_lab:
                    prev = next((r for r in rows if r[0].upper() == key), None)
                    if prev and all(abs(prev[q] - got[c]) < 1e-6 for q, c in ((1, 'x'), (2, 'y'), (3, 'z'))):
                        # the same site again at the SAME coordinates: a split site's second occupant on a
                        # row of its own ('X(3), 8c Sb1 0.9421 …' then 'X(3), 8c As1 0.0578 …', 6994) —
                        # its element joins the row's tail, and the table goes on
                        rows[rows.index(prev)] = prev[:4] + (prev[4] + ' ' + tail,); miss = 0
                        continue
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
        occ = ''
        if len(nums) >= 4 and 0 < nums[0][1] <= 1 and _ndec(nums[0][0][4]) <= 3 and all(_ndec(w[4]) >= 4 for w, _v in nums[1:4]):
            occ = nums[0][0][4]; nums = nums[1:]        # 'Na1 0.62(3) 0.7763(8) 0.0146(16) 0.3690(9)': an occupancy before x, printed shorter
        if len(nums) < 3:
            cand.append(None); continue
        first_x = min((w[0] + w[2]) / 2 for w, _v in nums)
        labs_ = [q for q, w in enumerate(ws) if (w[0] + w[2]) / 2 < first_x and _label_ok(_clean_label(_split_occupants(w[4])[0]))]
        lab = None
        if labs_:
            q = labs_[-1] if (len(labs_) > 1 and _prose_between(ws, labs_[0], labs_[-1])) else labs_[0]
            lab = _clean_label(_split_occupants(ws[q][4])[0])
            if _split_occupants(ws[q][4])[1]:
                occ = (occ + ' ' if occ else '') + _split_occupants(ws[q][4])[1]
        cand.append((lab, nums, occ) if lab else None)
    best = []
    i = 0
    while i < len(cand):
        if cand[i] is None:
            i += 1; continue
        j = i; rows = []; seen = set(); gap = 0
        while j < len(cand) and gap <= 2:
            if cand[j] is None:
                gap += 1; j += 1; continue
            lab, nums, occ = cand[j]
            lab = lab.rstrip('*†‡§,'); key = lab.upper()
            if key in seen:
                break                                   # the same site again: the next table
            seen.add(key); rows.append((j, lab, nums, occ)); gap = 0; j += 1
        if len(rows) >= 3:
            xs = sorted((w[0] + w[2]) / 2 for _j, _l, nums, _o in rows for w, _v in nums)
            cols = []
            for x in xs:
                if cols and x - cols[-1][-1] <= 10:
                    cols[-1].append(x)
                else:
                    cols.append([x])
            cols = [sum(c) / len(c) for c in cols if len(c) >= max(2, 0.5 * len(rows))][:3]
            decs = [_ndec(w[4]) for _j, _l, nums, _o in rows for w, _v in nums if _ndec(w[4])]
            if len(cols) == 3 and decs and sorted(decs)[len(decs) // 2] >= 4:
                out = []
                for _j, lab, nums, occ in rows:
                    got = {}
                    for w, v in nums:
                        xc = (w[0] + w[2]) / 2
                        k = min(range(3), key=lambda k_: abs(cols[k_] - xc))
                        if abs(cols[k] - xc) <= 26 and k not in got:
                            got[k] = (v, w)
                    if len(got) == 3:
                        zx = cols[2]
                        tail = ' '.join(w[4] for w, _v in nums if (w[0] + w[2]) / 2 > zx + 14)
                        out.append((lab, got[0][0], got[1][0], got[2][0], ('occ=' + occ + ' ' + tail) if occ else tail))
                if len(out) > len(best):
                    best = out
        i = max(j, i + 1)
    return best


def paper_sites(pdf, with_page=False):
    """The paper's atom-site table, tried on the whole page and on each text column of it.
    `with_page` returns (rows, page number of the table) — the default return is unchanged."""
    best = []; best_page = None; best_w = 1.0
    try:
        pages = _page_tables(pdf)
    except Exception:
        return (best, best_page) if with_page else best
    for pno, rows, weight, _headed, _cont in pages:
        if len(rows) * weight > len(best) * best_w:
            best = rows; best_page = pno; best_w = weight
    # A table continued over a page break: the next page's part — the paper says so ('Table 4.
    # Cont.', 'continued'), or the part carries no header of its own and begins the page — joins
    # the part before it when their labels do not overlap. Only the best table's own continuation.
    if best_page is not None:
        by_page = {p: (rows, headed, cont) for p, rows, _w, headed, cont in pages}
        labels = {r[0].upper() for r in best}
        p = best_page + 1
        while p in by_page:
            rows, headed, cont = by_page[p]
            dup = next((i for i, r in enumerate(rows) if r[0].upper() in labels), None)
            if dup is not None:
                rows = rows[:dup]                        # the scan walked on into the next table (anisotropic parameters carry the same labels): the part before it is the continuation
            if len(rows) < 2 or not (cont or not headed or _continues(best, rows)):
                break
            best = list(best) + list(rows); labels |= {r[0].upper() for r in rows}; p += 1
            if dup is not None:
                break
        # and the part BEFORE it: the widest part of a continued table is often the second, whose
        # page says 'Cont.' (or which carries no header of its own); the first part, with the
        # header and the first sites, is on the page before
        _rows0, headed0, cont0 = by_page[best_page]
        p = best_page - 1
        while p in by_page and (cont0 or not headed0):
            rows, headed, cont = by_page[p]
            if len(rows) < 2 or not headed or any(r[0].upper() in labels for r in rows):
                break
            best = list(rows) + list(best); labels |= {r[0].upper() for r in rows}; best_page = p
            # the part just absorbed is now the head of the table: the walk goes on only when IT says
            # 'Cont.' as well. (`headed0 = False` here kept the loop condition true and walked into any
            # earlier headed table with other labels — another mineral's — audit 2026-09-10.)
            cont0, headed0 = cont, headed; p -= 1
    return (best, best_page) if with_page else best


def paper_site_tables(pdf, limit=3):
    """Every coordinates table the paper prints, the best one (with its continuations, as
    `paper_sites` reads it) first: a two-mineral paper prints one per mineral, labelled alike
    (U1, Ca1 … in both), and only the structure built from each — judged by its own bonds — says
    which is which. A second table is another page's headed table of three rows or more that
    carries labels the best does not (a continuation's labels are all within the best's).
    -> [(rows, page)], at most `limit`."""
    best, best_page = paper_sites(pdf, with_page=True)
    out = [(best, best_page)] if best else []
    if not best:
        return out
    labels = {r[0].upper() for r in best}
    try:
        pages = _page_tables(pdf)
    except Exception:
        return out
    for pno, rows, _w, headed, cont in pages:
        if pno == best_page or not headed or cont or len(rows) < max(3, 0.4 * len(best)):
            continue
        labs = {r[0].upper() for r in rows}
        if labs <= labels or not (labs & labels):
            continue                                                       # a continuation, or something else than a coordinates table of this kind
        if any(pg == pno for _r, pg in out):
            continue
        out.append((rows, pno))
        if len(out) >= limit:
            break
    return out


def _continues(prev, rows):
    """A table on the next page that repeats its header is still the same table when its site
    numbering carries on from the page before: O21… after O1…O20, with no label in common."""
    def num(lab):
        m = re.match(r'^([A-Za-z]+)(\d+)', lab)
        return (m.group(1).upper(), int(m.group(2))) if m else None
    top = {}
    for r in prev:
        k = num(r[0])
        if k:
            top[k[0]] = max(top.get(k[0], 0), k[1])
    cont = [num(r[0]) for r in rows]; cont = [k for k in cont if k]
    if len(cont) < 2 or len(cont) < 0.5 * len(rows):
        return False
    return all(k[0] in top and k[1] > top[k[0]] for k in cont)


def _page_tables(pdf):
    """Per page, the widest atom-site table -> [(page no, rows, weight, headed, continued)], where
    `headed` says the header-driven read found it, `continued` that the page announces a
    continued table near the top. The last four documents are kept, keyed as `paper_extract._pages`
    keys its pages — on the file's size and mtime — so a pdf replaced under a running GUI is read
    again rather than served its predecessor's tables."""
    try:
        st = os.stat(pdf); stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        stamp = None
    return _page_tables_cached(pdf, stamp)


@functools.lru_cache(maxsize=4)
def _page_tables_cached(pdf, _stamp):
    out = []
    for pno, page in enumerate(PE._pages(pdf), 1):
        best = []; best_w = 1.0; headed = False
        views = []
        for lines in ([l for l in page if not l.get('rot')], [l for l in page if l.get('rot')]):   # the upright text, and a table typeset sideways
            xs = [w[0] for ln in lines for w in ln['w']] + [w[2] for ln in lines for w in ln['w']]
            if not xs:
                continue
            mid = (min(xs) + max(xs)) / 2
            views += [lines, _view(lines, -1e9, mid + 8), _view(lines, mid - 8, 1e9)]
        lines = page
        for view in views:
            # the header-driven read knows which column is x; the content read guesses the first
            # three fractions, and an occupancy column before x fools it — so a header read of a
            # real table (three rows) is preferred unless the content read found twice as much
            head = _scan(view); body = _scan_by_content(view)
            for r, weight, h in ((head, 2.0 if len(head) >= 3 else 1.0, True), (body, 1.0, False)):
                if len(r) * weight > len(best) * best_w:
                    best = r; best_w = weight; headed = h
        if best:
            top = ' '.join(w[4] for ln in lines[:8] for w in ln['w'])
            cont = bool(re.search(r'\b(?:Cont\.|Cont\b|continued|Continued)', top))
            out.append((pno, best, best_w, headed, cont))
    return out

ELEM = re.compile(r'([A-Z][a-z]?)(\d+(?:\.\d+)?|\.\d+)?')
_OCC_TOKEN = re.compile(r'(?:[A-Z][a-z]?(?:\d*\.\d+|\d{1,2})?/?)+|(?:\d*\.\d+[A-Z][a-z]?/?)+|occ=\S+')   # an occupancy column's token: element-first, share-first, or the reader's own 'occ=' mark          # the share after its element; a bare '.' (a label's full stop) is no number

def site_element(label, tail):
    """The element a site carries. A paper labels sites crystallographically — A1, M2, T3 — and
    names the elements in the site-occupancy column ('Ca0.674(11)Mn0.326(11)'): the dominant one is
    the site's element. Only when that column says nothing does the label have to carry it."""
    best = None
    # only the tokens an occupancy column prints: 'Ca0.674(11)Mn0.326(11)', 'Se1.00', '0.302(9)Sb/0.698Pb',
    # a bare 'Fe' — never the facing page column's prose ('Siderite I found in', 'the Y site'), which the
    # tail of a two-column page's row carries and which reads as Si, Y, Li to a regex
    toks = [re.sub(r'\(\d+\)', '', w).rstrip('*∗†‡§') for w in (tail or '').split()]
    toks = [w for w in toks if _OCC_TOKEN.fullmatch(w)]
    t = ' '.join(toks)
    pairs = [(el, num) for el, num in ELEM.findall(t) if el in EP.ATOMIC_WEIGHTS]
    if pairs and not any(num for _el, num in pairs):
        # the share printed BEFORE its element — '0.302(9)Sb/0.698Pb', '0.92Ni/0.08Co' (hrabákite): read
        # element-first, both would count 1.0 and the first would win
        before = [(el, num) for num, el in re.findall(r'(\d*\.\d+)([A-Z][a-z]?)(?![a-z])', t) if el in EP.ATOMIC_WEIGHTS]
        if before:
            pairs = before
    for el, num in pairs:
        v = float(num) if num else 1.0
        if best is None or v > best[1]:
            best = (el, v)
    if best:
        return best[0]
    if '/' in label:                                                      # 'Fe1/Al1': the paper names the dominant occupant first
        label = label.split('/')[0]
    m = re.match(r'\(?([A-Z][a-z]?)', label)                              # '(Al,Fe)': a mixed site named by its occupants, dominant first
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

def synth_cif(cell, symtag, ops, sites, formula='', occ=None):
    """A CIF carrying the paper's cell, coordinates and site elements (with the charges its formula
    states), the operators its space-group symbol stands for, and the occupancies it prints."""
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
          '_atom_site_fract_x', '_atom_site_fract_y', '_atom_site_fract_z'] + (['_atom_site_occupancy'] if occ else [])
    for lab, ty, x, y, z in sites:
        L.append("%s %s %.5f %.5f %.5f%s" % (lab, ty or re.match(r'[A-Za-z]{1,2}', lab).group(0), x, y, z,
                                             (' %.3f' % occ.get(lab, 1.0)) if occ else ''))
    return '\n'.join(L) + '\n'


def _occupancy(tail):
    """The site occupancy the scanners tagged into the tail ('occ=0.62(3) 0.050(4)': the bare
    fraction a table prints before x), or None when the row printed none. Only the tagged number:
    the first number of an untagged tail is Ueq, and an element-weighted 'Ca0.674Mn0.326' is read by
    `site_element`, not here."""
    m = re.match(r'^\s*occ=(0?\.\d+|1(?:\.0+)?)(?:\(\d+\))?(?=\s|$)', tail or '')
    return float(m.group(1)) if m else None


def bond_hits(st, bonds, tol=0.03):
    """The printed bond distances the structure reproduces: for each (cation label, anion label,
    distance) the paper prints, whether the structure has that anion at that distance from that
    cation, within `tol` Å. -> (reproduced, compared, [the first misses as text]). Labels are
    matched as printed on both tables (parentheses and case aside). This is the paper's own check
    of its coordinates, cell and space group together — the one that needs no element, charge or
    formula to be read right first."""
    index = [{}, {}, {}]                                    # by the whole label, by the site name, by the element head
    for s_ in st.sites:
        for level, k in enumerate(_label_keys(s_.label)):
            if k:
                index[level].setdefault(k, []).append(s_)
    def find(label):
        # the whole label first ('Mn(X)' on both tables); then the site name the paper prints beside
        # the element — its own name for the site, kept when the numbering differs between tables
        # ('Al2 (M3a)' in the bond table, 'Al1 (M3a)' in the coordinates); then the element head,
        # which two sites may share ('Mn' twice): then every one of them is a candidate
        for k in _label_keys(label):
            for level in range(3):
                got = index[level].get(k) if k else None
                if got:
                    return got
        return []
    cache = {}; ok = n = 0; miss = []
    reach = min(4.6, max([3.6] + [d + 0.1 for _c, _a, d in bonds if d]))   # a paper's long Pb–S or K–O bonds (3.7 Å) must be within reach, or they count as misses of a structure that has them
    for cat, an, d in bonds:
        cats, ans = find(cat), find(an)
        if not cats or not ans or not d:
            continue
        n += 1
        for cs in cats:
            if cs.label not in cache:
                try:
                    cache[cs.label] = st.neighbours(cs, reach)
                except Exception:
                    cache[cs.label] = []
        an_labels = {a.label for a in ans}
        hit = any(o.label in an_labels and abs(dd - d) <= tol for cs in cats for o, dd, _c in cache[cs.label])
        if hit:
            ok += 1
        elif len(miss) < 6:
            near = sorted((dd for cs in cats for o, dd, _c in cache[cs.label] if o.label in an_labels), key=lambda x: abs(x - d))
            miss.append('%s–%s %.3f printed, %s in the structure' % (cat, an, d, ('%.3f' % near[0]) if near else 'no such neighbour'))
    return ok, n, miss


def _label_keys(label):
    """The three names a printed site label answers to, most specific first: the whole label with
    parentheses and spaces out ('Mn(X)' -> 'MNX'), the site name in parentheses when it has a
    letter ('X', 'M3a' -> 'M3A'; '(1)' of 'O(1)' is not a name), and the element head before it
    ('MN'). Bare labels have only the first."""
    t = re.sub(r'\s+', '', label or '').rstrip('*†‡§,')
    whole = re.sub(r'[()]', '', t).upper()
    m = re.match(r'^([A-Za-z]+\d*[a-z]?)\(([A-Za-z]+\d*[a-z]?)\)$', t)
    if not m:
        return [whole, None, None]
    return [whole, m.group(2).upper(), m.group(1).upper()]


def occupancy_any(tail):
    """The site's occupancy from its row, either way it is printed: the tagged bare fraction
    ('occ=0.62(3) …'), or the dominant element's share of an element-weighted string ('As0.70',
    'Na0.62(1)Ca0.38') — the weight a paper multiplies that column of its bond-valence table by."""
    v = _occupancy(tail)
    if v is not None:
        return v
    for tok in (tail or '').split():
        if _OCC_ELS.search(tok):
            shares = [float(x) for x in re.findall(r'[A-Z][a-z]?(\d*\.\d+)', tok)]
            if shares:
                return max(shares)
    return None


def occupancy_species(tail):
    """The species on a site as its row prints them — [(element, share), …], the dominant first —
    from an element-weighted occupancy ('Na0.62(1)Ca0.38' → [('Na', 0.62), ('Ca', 0.38)]; 'As0.70'
    → [('As', 0.70)], the rest a vacancy). [] when the row prints none."""
    for tok in (tail or '').split():
        if _OCC_ELS.search(tok):
            out = [(el, float(sh)) for el, sh in re.findall(r'([A-Z][a-z]?)(\d*\.\d+)', re.sub(r'\(\d+\)', '', tok)) if el in EP.ATOMIC_WEIGHTS]
            if out and sum(sh for _e, sh in out) <= 1.05:
                return sorted(out, key=lambda es: -es[1])
    return []


def _pb_key(lab):
    from pxrd_review import paper_bonds as PB
    return PB._key(lab)

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


def closure_count(st, counts):
    """The structure against the paper's formula by COUNT: cation sites to anion sites, with their
    multiplicities, against the formula's cations to anions (H left out of both). A site of mixed
    occupancy — Y = Fe0.6Mg0.4, named by its dominant element — breaks the element ratios that
    `closure` compares but not this one, while a table read only in part (its anions cut off, or
    half its cations) still fails it. -> relative deviation, or None when nothing to compare."""
    if not counts:
        return None
    cat = sum(s.mult * s.occ_total for s in st.cations if s.element != 'H')
    an = sum(s.mult * s.occ_total for s in st.anions if s.element != 'H')
    fc = sum(v for k, v in counts.items() if k not in ('H', 'O', 'F', 'Cl', 'S', 'Se', 'Te', 'Br', 'I', 'OH') and v > 0)
    fa = sum(v for k, v in counts.items() if k in ('O', 'F', 'Cl', 'S', 'Se', 'Te', 'Br', 'I', 'OH') and v > 0)
    if not (cat and an and fc and fa):
        return None
    return abs(cat / an - fc / fa) / (fc / fa)


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
    top = max(want.values())
    for el, v in want.items():
        if el not in cell and v < 0.2 * top:
            continue                                                       # a minor substituent (Cd 1.57 beside Cu 9.98) the table's site labels do not name: not a row lost
        mine = cell.get(el, 0.0) / cell[ref] * want[ref]
        devs.append(abs(mine - v) / max(v, 0.05))
    return sum(devs) / len(devs) if devs else None


def build(pdf, text=None, bonds=None, rows=None):
    """The structure the paper prints, or None. -> (Structure, info) where info carries 'gii',
    'closure', 'cell', 'sym' and 'sites'; (None, {'why': ...}) when it cannot be built or does not
    pass the instability gate. A paper prints several cells — a powder one, a single-crystal one,
    sometimes another phase's — so each is tried and the one whose valences come out closest is
    kept: the structure judges its own cell."""
    text = PE.text_of(pdf) if text is None else text
    rows = paper_sites(pdf) if rows is None else rows                   # `rows`: a second coordinates table of a two-mineral paper (paper_site_tables)
    if len(rows) < 3:
        return None, {'why': 'the paper prints no coordinates table the reader could find'}
    sym, _phrase = SO.find_in_text(text)
    # the cell a coordinates table belongs to is the single-crystal one: those first, the powder
    # cells last (a powder cell's angle variants would otherwise fill the budget before the true cell)
    rank = {'single': 0, 'unknown': 1, 'stated': 2, 'powder': 3}
    cells = [c for _ctx, c in sorted(PE._paper_cells(text), key=lambda xc: rank.get(xc[0], 2))][:8]
    # A paper states several symbols — its own, and its relatives' in the discussion. The one whose
    # crystal system a printed cell allows is the paper's: a P1̄ read from "space groups P1̄ and C2/c"
    # is not, when every cell printed is monoclinic. And a cell the symbol's system forbids (a
    # monoclinic cell under I-42d: another mineral's) is not tried.
    systems = set().union(*(SO.cell_system(c) for c in cells)) if cells else set()
    if systems and (not sym or SO.crystal_system(sym) not in systems):
        for m_ in SO._NEAR.finditer(text):
            s2, _p2 = SO.find_in_text(text[m_.start():m_.start() + 130])
            if s2 and SO.crystal_system(s2) in systems:
                sym = s2; break
    ops_variants = SO.lookup(sym) if sym else []
    if not ops_variants:
        return None, {'why': 'no space group in the text that the operator table knows'}
    want = SO.crystal_system(sym)
    if want and cells:
        cells = [c for c in cells if want in SO.cell_system(c)] or cells
    # The overbar of P1̄, R3̄, Fm3̄m is often a drawn stroke the text layer does not carry, so the
    # symbol arrives unbarred. The barred twin is tried as well and the structure judges: sites
    # given for P1̄ built in P1 are half a structure and their sums come out half, so the twin wins;
    # a structure that really is P1 built in P1̄ doubles its atoms and loses.
    twin = next((t for t in (sym[:i] + '-' + sym[i:] for i in range(1, len(sym))) if '-' not in sym and SO.lookup(t)), None)
    if twin:
        ops_variants = ops_variants + SO.lookup(twin)
    ops_variants = ops_variants[:6]                      # the standard setting and the commonest alternatives: eighteen settings of C2/c cost minutes and change no verdict
    variant_syms = [sym] * len(ops_variants)
    # the OTHER symbols the paper states (a relative's, a parent's — 75959 names Im3̄m for a related
    # mineral once and its own I213 twice) come after the chosen one's settings, two settings each,
    # under the same budget: the bonds oracle, or the index, decides between them
    try:
        others = [s2 for s2 in SO.find_all_in_text(text) if s2 != sym and s2 != twin and (not systems or SO.crystal_system(s2) in systems)]
    except Exception:
        others = []
    for s2 in others[:2]:
        extra = SO.lookup(s2)[:2]
        ops_variants = list(ops_variants) + extra; variant_syms += [s2] * len(extra)
    name = PE.mineral_name(text)
    charges = element_charges(text, name)
    try:
        mixed_els = {el for el, chs in element_charge_sets(text, name).items() if len(chs) > 1}   # Fe2+ AND Fe3+ in the formula: the site's own bonds settle which (see _structure_for_paper)
    except Exception:
        mixed_els = set()
    fs = PE._formulas(text, name)
    counts = fs[0][1] if fs else {}
    # A site the paper names crystallographically — M1, A(1), T2 — carries no element in its label
    # and, when the table prints no occupancy column, none in its row either: the paper's own
    # assignment ('M1 = 0.37Mn + 0.27Mg + 0.35Fe', a site-population row, the sentence) names it.
    # Right 11 times in 17 against the corpus .cif files, so such a site is built — the composition
    # needs it — but kept out of the instability index, as `paper_bonds` keeps its inferred sites.
    unnamed = [lab for lab, _x, _y, _z, tail in rows if not site_element(lab, tail)]
    named = {}
    if unnamed:
        try:
            from pxrd_review import paper_bonds as PB
            named = PB.sites_from_text(text, unnamed)
        except Exception:
            named = {}
    sites = []; inferred = set(); occs = {}
    placed = {site_element(lab, tail) for lab, _x, _y, _z, tail in rows if site_element(lab, tail)}
    cations = sorted(((v, k) for k, v in counts.items() if k not in ('H', 'O', 'F', 'Cl', 'S', 'Se', 'Te', 'Br', 'I') and v > 0), reverse=True)
    fallback = next((k for _v, k in cations if k not in placed), None) or (cations[0][1] if cations else None)
    def by_letter(lab):
        """The element a site LETTER stands for, by the convention the letters carry and the formula's
        elements: T is the tetrahedral site (Si, then P, As, S, B, Be, Al, Ge, V), A and X the large
        cation (Na, K, Ca, Ba, Sr, Pb, …), M, Y and Z the octahedral one (Fe, Mg, Mn, Al, Ti, …; Al
        first at Z, a tourmaline's). Before this, T(1) took whatever cation the formula had left —
        Ca into a silicate's tetrahedron, at an instability index of 218 vu (79066)."""
        large = ('Na', 'K', 'Ca', 'Ba', 'Sr', 'Pb', 'Rb', 'Cs', 'Tl', 'Bi', 'Y', 'Ce', 'La', 'Nd', 'U', 'Th')
        octa = ('Fe', 'Mg', 'Mn', 'Al', 'Ti', 'Cu', 'Zn', 'Ni', 'Co', 'Cr', 'V', 'Li', 'Sc', 'Nb', 'Ta', 'Zr', 'Sn', 'Sb', 'Ca', 'Na')
        pools = {'T': ('Si', 'P', 'As', 'S', 'B', 'Be', 'Al', 'Ge', 'V', 'Zn', 'Se', 'Mo', 'W'), 'A': large, 'X': large,
                 'M': octa, 'Y': octa, 'Z': ('Al',) + octa}
        return next((e for e in pools.get(lab[:1], ()) if counts.get(e, 0) > 0), None)
    for lab, x, y, z, tail in rows:
        el = site_element(lab, tail)
        if not el and named:
            el = named.get(_pb_key(lab))
            if el:
                inferred.add(lab)
        if not el and re.match(r'^[AMTXYZQ]', lab) and lab[:1] not in EP.ATOMIC_WEIGHTS:
            el = by_letter(lab) or fallback                               # M1, A(1), T2: a cation site by convention — the letter's element in the formula, else its dominant cation not yet placed; for the composition only
            if el:
                inferred.add(lab)
        if el:
            ch = charges.get(el)
            sites.append((lab, '%s%d+' % (el, ch) if ch and el not in mixed_els else el, x, y, z))   # a mixed-valence element is written bare: the .cif then 'states none' and the paper's per-site fit applies
            occ = _occupancy(tail)
            if occ is not None:
                occs[lab] = occ
    if len(sites) < 3:
        return None, {'why': 'no element could be named for the sites read'}
    if not cells:
        return None, {'why': 'no cell in the text'}
    best = None; best_outlier = None
    tmp = tempfile.mkdtemp(prefix='pxrd_ps_')
    keep = None; all_inferred = False
    # Every cell the paper prints is tried with the STANDARD setting before any alternate setting is
    # tried with any cell — the cell is far more often the unknown than the setting — under one budget
    # of builds: a paper that prints nine cells (angle variants restored) and a Cc with eighteen
    # settings cost minutes and changed no verdict.
    budget = 24
    try:
        for vi, ops in enumerate(ops_variants):
          for ci, cd in enumerate(cells):
            cell = [cd[k] for k in ('a', 'b', 'c', 'α', 'β', 'γ')]
            if True:
                budget -= 1
                if budget < 0:
                    break
                path = os.path.join(tmp, 'c%d_%d.cif' % (ci, vi))
                try:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(synth_cif(cell, '_space_group_symop_operation_xyz',
                                          [_op_str(o) for o in ops], sites, occ=occs))
                    st = B.Structure(path)
                    P = B.Params(prefer='gh', u6='burns')
                    notes = list(st.notes)
                    res, _an, _cells, _hb = B.compute(st, P, None, 'oo')
                    st.notes[:] = notes
                except Exception:
                    continue
                # the index is over the sites the paper NAMES by element and populates fully: an
                # inferred element is a guess, and a site a third occupied is a disordered position
                # whose own sum says nothing about the coordinates being read right
                judged = [(bvs, exp) for c_, _b, bvs, exp, _m in res if c_.label not in inferred and occs.get(c_.label, 1.0) >= 0.5]
                if not judged and not (bonds and len(bonds) >= 5):
                    all_inferred = True
                    continue
                # an amphibole's table names every site crystallographically (T1, M(1), A2): nothing
                # is left for the index to judge, but the printed bonds need no element at all
                # one site whose sum is off by a whole valence unit or more, among many that hold, is a
                # misread ROW (hyrslite's Pb3 at 21.9 vu, a digit of one coordinate) — an rms lets one
                # such site sink fifty good ones, so the worst site is left out of the index when it
                # alone is off by that much; the build then says which
                outlier = None
                if len(judged) >= 8:
                    devs_ = sorted(((abs(bvs - exp), bvs, exp) for bvs, exp in judged), reverse=True)
                    if devs_[0][0] >= 1.0 and devs_[1][0] < 0.5:
                        outlier = devs_[0]; judged = [(b_, e_) for b_, e_ in judged if abs(b_ - e_) < devs_[0][0]]
                gii = (sum((bvs - exp) ** 2 for bvs, exp in judged) / len(judged)) ** 0.5 if judged else 9.0
                # the printed bond distances are the direct check of the cell and setting: the
                # candidate that reproduces the most of them wins, the index deciding only ties
                hits = bond_hits(st, bonds) if bonds and len(bonds) >= 3 else (0, 0, [])
                score = (-hits[0], gii)
                if best is None or score < best[5]:
                    best = (st, gii, cell, variant_syms[vi], len(sites), score, hits); keep = path; best_outlier = outlier
                if (hits[1] and hits[0] >= 0.9 * hits[1]) or (not hits[1] and gii <= GII_GATE):
                    break                                # it holds together: another setting cannot change the verdict
          if (best is not None and ((best[6][1] and best[6][0] >= 0.9 * best[6][1]) or (not best[6][1] and best[1] <= GII_GATE))) or budget < 0:
                break
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
        return None, {'why': ('every site is a crystallographic name (T1, M(1), A2) put to the paper\'s own assignment — nothing the index can judge, and no bond table to judge it by'
                              if all_inferred else 'no cell and operator set gave a structure (the bond-valence parameters may be missing for these elements)')}
    st, gii, cell, sym, n, _score, hits = best
    try:
        info = {'gii': gii, 'cell': cell, 'sym': sym, 'sites': n, 'closure': closure(st, counts), 'closure_count': closure_count(st, counts),
                'bonds_ok': hits[0], 'bonds_n': hits[1], 'bonds_total': len(bonds or []), 'bonds_miss': hits[2], 'path': keep, 'dir': tmp}
    except Exception:
        _discard(keep, tmp)                              # the caller sees the exception, not a leaked directory
        raise
    info['bonds_verified'] = bool(hits[1] >= 5 and hits[0] >= max(5, 0.8 * hits[1]) and hits[1] >= 0.6 * len(bonds or []))
    info['inferred'] = sorted(inferred)
    if best_outlier:
        info['outlier'] = 'one site left out of the index: its sum %.1f vu against %.0f expected — a misread row (a digit of a coordinate), the rest holding' % (best_outlier[1], best_outlier[2])
    try:
        st.inferred = set(inferred)                      # the sites whose element is a guess (M(1) → the formula's dominant cation): out of the sums
    except Exception:                                    # comparison, as `paper_bonds` keeps its inferred sites — badalovite's M(1)/M(2) carry Fe3+ the paper
        pass                                             # weights from a site-population table the reader does not have
    if gii > GII_GATE and not info['bonds_verified']:
        _discard(keep, tmp)
        return None, dict(info, path=None, why='the structure the paper prints does not hold together '
                          '(instability index %.2f vu) — its cell, coordinates or space group is misread' % gii)
    return st, info                                          # a structure the printed bonds verify stands whatever its index says


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
