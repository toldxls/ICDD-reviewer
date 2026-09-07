"""The bond distances a paper itself prints, and the bond valences that follow from them.

Nine papers in ten come without a .cif, and `paper_structure` — which rebuilds the whole structure
from the coordinates table, the cell and the space group — succeeds on very few of them: the
coordinates have to be read complete, the symbol has to be one the operator table knows, and the
right cell has to be picked out of the several a paper prints. A bond-distance table asks for none
of that. It states the two sites and the distance between them, which is everything a bond valence
needs: s = exp((R0 − d)/B).

So this reads that table and computes the sums from it. What it buys is an oracle for the papers
with no .cif: the bond-valence table the paper prints, checked against the distances the paper
prints, in the same units, by the same arithmetic the journal used. Nothing is inferred — no cell,
no space group, no coordinates — so unlike `paper_structure` this is not note-grade: the only
assumptions are which element sits on each site (the label says so, or the coordinates table's
occupancy column does) and its charge (the paper's own formula, else Mindat).

What it cannot do is anion sums: they need the site multiplicities, which the table does not print.
Cation sums and the individual bond valences are what it offers, and `check_bvs_sites` /
`check_bvs_table` are told to compare only those.

    st, result, g = structure_for(pdf)              # the best of the tables the paper prints
    if st is not None and g <= GII_GATE:             # its bonds add up: a verdict, not a doubt
        result, anion_sum, cells = compute(st, B.Params(prefer='gh'))   # the shapes bv_check's checkers expect
"""
import re
from collections import OrderedDict, namedtuple

from pxrd_review import bv_check as B
from pxrd_review import epma as EP

# one row of a bond-distance table: 'Pb1 – S7 2.814(14)', 'X –O(2) 2.503(4) × 3'
Row = namedtuple('Row', 'cation anion dist esd count page line col')

DIST = re.compile(r'^(\d\.\d{2,4})(?:\((\d{1,3})\))?$')
DASH = '–—−‐-'
# a site label, with the dash a continuation row carries: '–S15', 'O(2)', 'Ow1', 'OH2', 'O10H'.
# A trailing lowercase group is the symmetry code the paper superscripts onto the anion ('O1vi')
# and names an image of the site, not another site; a trailing UPPERCASE letter is part of the
# label ('O12W', 'O8H' — the refiner's mark for a water or hydroxyl oxygen).
LAB = re.compile(r"^[%s]?\s*([A-Z][A-Za-z]?)(?:\((\d{1,2})\)|(\d{1,2}))?([A-Z]?)([a-z]{0,4}['′*†‡#]{0,2})$" % DASH)
PAIR = re.compile(r"^([A-Z][A-Za-z]?(?:\(\d{1,2}\)|\d{1,2})?[A-Z]?)[%s]"
                  r"([A-Z][A-Za-z]?(?:\(\d{1,2}\)|\d{1,2})?[A-Z]?)[a-z]{0,4}$" % DASH)
BARE_DASH = re.compile(r'^[%s]+$' % DASH)
MULT_SIGNS = ('×', 'x', 'X', '·', '∙', '*')
# several corpus journals set the multiplication sign in a font whose '×' reaches the text as a 3
# ('0.10 3 0.01 3 0.01 mm' for a crystal size). It is read as one only BETWEEN the site label and
# the distance ('Si–O6 3 2 1.630(5)'), where a bare 3 has no other meaning; after the distance it
# would compete with the next column of numbers.
MULT_SIGNS_BEFORE = MULT_SIGNS + ('3',)
MULT = re.compile(r'^[×x·∙*]\s*(\d{1,2})$')

D_MIN, D_MAX = 1.0, 4.6         # nothing shorter than a B–O bond, nothing longer than the tables list
MIN_ROWS = 4                    # fewer than four bond cells on a page is prose, not a table
COL_GAP = 20                    # points between one column of cells and the next


def _label(tok):
    """('S15', True) — the normalised label and whether the token carried a leading dash."""
    m = LAB.match(tok.strip())
    if not m:
        return None, False
    head, par, plain, upper, _sym = m.groups()
    return head + (par or plain or '') + (upper or ''), bool(re.match(r'^[%s]' % DASH, tok.strip()))


def _pair_token(tok):
    """'Al1-O10H', 'M1-O1vi' typeset without spaces -> ('Al1', 'O10H') / ('M1', 'O1')."""
    m = PAIR.match(tok.strip())
    return (m.group(1), m.group(2)) if m else (None, None)


# A paper names its sites crystallographically — A1, M2, T(1), X, Y, Z — and two of those letters
# are also element symbols. 'Y1' in a tourmaline is not yttrium and 'W1' is usually water, so a
# label headed by one of these is trusted only when the paper's own formula contains that element.
AMBIGUOUS = {'Y', 'W'}

# a site-occupancy cell: 'Ca0.674(11)Mn0.326(11)', 'Mg0.85'. The symbol must carry an occupancy —
# the coordinates reader's tail can pick up a word from the prose printed beside the table
# ('Bragg' -> 'Br', 'Pa' out of 'parameters'), and a wrong element is worse than none.
OCC = re.compile(r'([A-Z][a-z]?)\s*(\d*\.\d+|[01](?:\.0*)?)(?:\(\d+\))?')


def site_elements(rows):
    """{label: element} from the coordinates table's site-occupancy column. `rows` is what
    `paper_structure.paper_sites` returns: (label, x, y, z, tail)."""
    out = {}
    for lab, _x, _y, _z, tail in rows or []:
        best = None
        for el, num in OCC.findall(re.sub(r'\(\d+\)', '', tail or '')):
            if el not in EP.ATOMIC_WEIGHTS:
                continue
            v = float(num)
            if not (0 < v <= 1.05):
                continue
            if best is None or v > best[1]:
                best = (el, v)
        if best:
            out[_key(lab)] = best[0]
    return out


def element_of(label, sites=None, known=None):
    """The element on a site. A label that names an element says so itself ('Pb1', 'O10H', 'Si3');
    a crystallographic site name ('X', 'M(2)', 'A1') does not, and for those the coordinates
    table's occupancy column is asked (`sites`, from `site_elements`). `known` — the elements the
    paper's formula names — is what settles a 'Y' or a 'W', and a site nothing can name is left
    out rather than guessed at."""
    m = re.match(r'^([A-Z][a-z]?)', label)
    head = None
    if m:
        head = m.group(1) if m.group(1) in EP.ATOMIC_WEIGHTS else (label[0] if label[0] in EP.ATOMIC_WEIGHTS else None)
    if head and head not in AMBIGUOUS:
        return head
    if sites:
        hit = sites.get(_key(label))
        if hit:
            return hit
    if head and (known is None or head in known):
        return head
    return None


def _key(label):
    return re.sub(r'[()\s]', '', label).upper()


def _mult_before(ws, j):
    """The '* 3' a table prints BETWEEN the anion and the distance ('X -O(2) * 3 2.474(3)').
    -> (count, index of the token left of it)."""
    if j >= 1 and re.fullmatch(r'\d{1,2}', ws[j][4].strip()) and ws[j - 1][4].strip() in MULT_SIGNS_BEFORE:
        return int(ws[j][4].strip()), j - 2
    m = MULT.match(ws[j][4].strip()) if j >= 0 else None
    if m:
        return int(m.group(1)), j - 1
    return 1, j


def _mult_after(ws, i):
    """The '* 3' printed after the distance instead ('X -O(2) 2.503(4) * 3')."""
    for k in range(i + 1, min(i + 3, len(ws))):
        t = ws[k][4].strip()
        m = MULT.match(t)
        if m:
            return int(m.group(1))
        if t in MULT_SIGNS:
            if k + 1 < len(ws) and re.fullmatch(r'\d{1,2}', ws[k + 1][4].strip()):
                return int(ws[k + 1][4].strip())
            return 1
        if DIST.match(t):
            break
    return 1


def _cells(line):
    """The bond cells of one typeset line: [(x where the cell starts, cation token or None, anion,
    d, esd, count)]. A line of a multi-column table holds one cell per column."""
    ws = line['w']
    out = []
    for i, w in enumerate(ws):
        m = DIST.match(w[4].strip())
        if not m:
            continue
        d = float(m.group(1))
        if not (D_MIN <= d <= D_MAX):
            continue
        count, j = _mult_before(ws, i - 1)
        if j < 0:
            continue
        an, dashed = _label(ws[j][4])
        cat = None
        if an is None:                              # 'Al1-O10H' as one token
            cat, an = _pair_token(ws[j][4])
            if an is None:
                continue
            dashed = True
        dash = j                                    # where the cell starts: the dash, attached or its own
        if not dashed:                              # 'Pb1 - S7 2.814': the dash is its own token
            if j >= 1 and BARE_DASH.match(ws[j - 1][4].strip()):
                dash = j - 1
            else:
                continue                            # no dash at all: a cell of some other table
        if cat is None and dash >= 1:
            c, c_dash = _label(ws[dash - 1][4])
            if c is not None and not c_dash:
                cat = c
        if count == 1:
            count = _mult_after(ws, i)
        # the cell starts at the dash, on the head row and on every continuation row alike; the
        # cation of the head row sits further left and would put that row in another column
        out.append((ws[dash][0], cat, an, d, int(m.group(2)) if m.group(2) else None, count))
    return out


def _columns(xs, gap=COL_GAP):
    """Cell-start x positions clustered into table columns."""
    cols = []
    for x in sorted(xs):
        if cols and x - cols[-1][-1] <= gap:
            cols[-1].append(x)
        else:
            cols.append([x])
    return [sum(c) / len(c) for c in cols]


def _caption(lines, li):
    """The 'Table 4. Selected bond lengths...' line above the first cell."""
    for k in range(min(li, len(lines) - 1), max(-1, li - 40), -1):
        head = ' '.join(w[4] for w in lines[k]['w'][:3])
        if re.match(r'^(TABLE|Table)\s+[A-Z]?\d+', head):
            return ' '.join(w[4] for w in lines[k]['w'])[:160]
    return ''


def read_tables(pdf, pages=None):
    """The paper's bond-distance tables, one entry per page that prints one. Cells are grouped
    into columns by where the cell starts, and within a column the cation carries down the
    continuation rows the way it is typeset ('Pb1 - S7 2.814' then '- S15 2.964'). Rows come back
    in COLUMN-MAJOR order — the order they are read in — which is what `candidates` needs to tell
    one table from the next. -> [{'page', 'caption', 'columns', 'bonds': [Row, ...]}]"""
    from pxrd_review import paper_extract as PE
    out = []
    for pno, lines in enumerate(pages if pages is not None else PE._pages(pdf)):
        found = [(li, c) for li, ln in enumerate(lines) for c in _cells(ln)]
        if len(found) < MIN_ROWS:
            continue
        centres = _columns([c[0] for _li, c in found])
        by_col = {}; carried = {}
        for li, c in sorted(found, key=lambda t: (t[0], t[1][0])):
            k = min(range(len(centres)), key=lambda i: abs(centres[i] - c[0]))
            cat = c[1] or carried.get(k)
            if c[1]:
                carried[k] = c[1]
            if not cat:
                continue
            by_col.setdefault(k, []).append(Row(cat, c[2], c[3], c[4], c[5], pno + 1, li, k))
        bonds = [r for k in sorted(by_col) for r in by_col[k]]
        if len(bonds) >= MIN_ROWS:
            out.append({'page': pno + 1, 'caption': _caption(lines, found[0][0]),
                        'columns': len(by_col), 'bonds': bonds})
    return out


def _sections(bonds):
    """Where one table ends and the next begins on the same page. A paper lists a site's bonds
    together, so a cation that reappears after another has intervened — in its own column — is the
    same site of a SECOND substance (a two-mineral paper prints a table each). The break is a line
    number, and it applies across every column, because the two tables are stacked. -> [row lists]"""
    breaks = set()
    for col in {r.col for r in bonds}:
        seen = set(); cur = None
        for r in sorted([b for b in bonds if b.col == col], key=lambda b: b.line):
            if r.cation != cur:
                if r.cation in seen:
                    breaks.add(r.line)
                    seen = set()
                seen.add(cur := r.cation)
    if not breaks:
        return [bonds]
    edges = sorted(breaks); out = []
    for lo, hi in zip([-1] + edges, edges + [10 ** 9]):
        part = [r for r in bonds if (lo == -1 or r.line >= lo) and r.line < hi]
        if part:
            out.append(part)
    return out


def _split_columns(part):
    """Two substances printed side by side, a table each ('Rasmussenite | Ca-glycinate trihydrate'):
    the same site label stands in two columns. One substance's table never splits a site's bonds
    across columns, so this is the tell, and each column is then a table of its own."""
    cols = {}
    for r in part:
        cols.setdefault(r.cation, set()).add(r.col)
    if not any(len(v) > 1 for v in cols.values()):
        return [part]
    return [[r for r in part if r.col == k] for k in sorted({r.col for r in part})]


def candidates(tables):
    """The structures a paper's bond tables stand for. A table continued on the next page names
    other cations, so it joins the one before it; a table that repeats a cation is a second
    substance, and merging the two would count a site's bonds twice. -> [[Row, ...]], the first
    being the paper's first (and usually only) structure."""
    parts = [q for t in tables for p in _sections(t['bonds']) for q in _split_columns(p)]
    out = []
    for part in parts:
        cats = {r.cation for r in part}
        for grp in out:
            if not (cats & {r.cation for r in grp}):
                grp.extend(part); break
        else:
            out.append(list(part))
    return out


# ----------------------------------------------------------------------------- the structure a bond table implies

class BondStructure:
    """What `bv_check`'s checkers need of a structure, built from a bond-distance table alone:
    the two sets of sites and, per cation, the bonds the paper prints. There are no coordinates,
    so there is no multiplicity and no symmetry — which is why anion sums are not offered."""

    from_bonds = True            # the checkers ask, to leave anion sums alone and to say so in the text

    def __init__(self, rows, elements=None, charges=None, known=None, name=''):
        self.name = name; self.notes = []; self.aliases = {}; self.path = None
        self.rows = list(rows)
        self.elements = {_key(k): v for k, v in (elements or {}).items()}
        self.charges = dict(charges or {})
        self.known = set(known) if known is not None else None
        self._build()

    def _element(self, label):
        return element_of(label, self.elements, self.known)

    def _build(self):
        cat_labels = OrderedDict(); an_labels = OrderedDict(); kept = []
        for r in self.rows:
            ce, ae = self._element(r.cation), self._element(r.anion)
            if not ce or not ae:
                continue
            kept.append(r); cat_labels.setdefault(r.cation, ce); an_labels.setdefault(r.anion, ae)
        # a label that is an anion in one row and a cation in another (a paper lists 'S1–Pb3' as
        # well) belongs where its element puts it
        has_o = any(e == 'O' for e in an_labels.values()) or any(e == 'O' for e in cat_labels.values())
        anion_els = set(B.ANION_OX)
        for lab, el in list(cat_labels.items()):
            if el in anion_els and el != 'H' and lab not in an_labels and not self._is_cation(el, has_o):
                an_labels[lab] = el; del cat_labels[lab]
        self.rows = [r for r in kept if r.cation in cat_labels and r.anion in an_labels]
        self.anions = [self._site(l, an_labels[l], has_o, anion=True) for l in an_labels]
        self.cations = [self._site(l, cat_labels[l], has_o) for l in cat_labels]
        self.sites = list(self.cations) + list(self.anions)
        self.bonds_of = OrderedDict((c.label, []) for c in self.cations)
        for r in self.rows:
            self.bonds_of[r.cation].append(r)

    def neighbours(self, site, cutoff):
        return []                # no coordinates: nothing can be found that the table does not list

    @staticmethod
    def _is_cation(el, has_o):
        """An anion element used as a cation: S in a sulfate, N in nitrate — only with oxygen
        about, and only when the paper's own charge says so."""
        return el in ('S', 'N', 'Se', 'Te', 'I', 'Cl') and has_o

    def _site(self, label, el, has_o, anion=False):
        if anion:
            ox = B.ANION_OX.get(el, -2)
        else:
            ox = self.charges.get(el)
            if ox is None:
                ox = (B.DEFAULT_OX if has_o else {**B.DEFAULT_OX, **B.DEFAULT_OX_NO_O}).get(el)
        sp = [B.Species(el, ox, 1.0)]
        return B.Site(label, el, None, sp, [], 1, 1.0, None)

    def site(self, label):
        for s in list(self.cations) + list(self.anions):
            if s.label == label:
                return s
        return None


def _merged(rows, tol=0.0015):
    """Rows that state the same bond twice — a paper lists the two symmetry images of one distance
    on their own lines ('Al1-O4' and "Al1-O4'") as often as it writes one line marked 'x2' — become
    one bond of count 2. The table it is being checked against prints them as one cell either way,
    so they have to be one bond here too."""
    out = []
    for r in rows:
        for i, k in enumerate(out):
            if k.anion == r.anion and abs(k.dist - r.dist) <= tol:
                out[i] = k._replace(count=k.count + r.count); break
        else:
            out.append(r)
    return out


def compute(st, params):
    """The bond valences of the paper's own table -> (result, anion_sum, cells) in the shapes
    `bv_check.check_bvs_sites` / `check_bvs_table` read. anion_sum is empty and every cell's
    across-count is its down-count: without multiplicities an anion's sum cannot be formed, and
    the callers are told not to compare one."""
    sites = {s.label: s for s in list(st.cations) + list(st.anions)}
    result = []; cells = {}
    for c in st.cations:
        bonds = []
        for r in _merged(st.bonds_of.get(c.label) or []):
            a = sites[r.anion]
            vals = []
            for sp in c.species:
                if sp.ox is None or sp.ox <= 0:
                    continue
                an_ox = a.species[0].ox
                vals.append((sp, params.valence(sp.element, sp.ox, a.element, an_ox, r.dist)))
            if vals and any(s is not None for _, s in vals):
                if max((s or 0.0) for _, s in vals) < B.MIN_S:
                    continue
                bonds.append(B.Bond(c, a, r.dist, r.count, vals))
        if not bonds:
            continue
        bvs = sum(sum((s or 0.0) for _sp, s in b.vals) * b.count for b in bonds)
        expected = sum(sp.ox for sp in c.species if sp.ox and sp.ox > 0)
        ncoord = sum(b.count for b in bonds)
        result.append((c, bonds, bvs, expected, sum(b.dist * b.count for b in bonds) / ncoord))
        for b in bonds:
            s_site = sum((s or 0.0) for _sp, s in b.vals)
            cells.setdefault((b.anion.label, c.label), []).append((s_site, b.count, b.count))
    return result, {}, cells


# The gate. A bond-valence sum that comes out at the site's formal valence is the check on the
# whole chain — the table was read right, the elements and charges are right, the parameters are
# the journal's. Scored against the .cif on the 156 corpus papers that have one: at 0.15 vu, 87 of
# 88 sites (98 %) reproduce the .cif's own sums, which is flag-grade; ungated it is 73 %, which is
# not. Between the two gates the reading is worth a note and no more.
GII_GATE = 0.15
GII_NOTE = 0.35


def analysed_elements(ex, text, name):
    """The elements the paper's ANALYSIS names — which is what settles whether a 'Y' or a 'W' site
    label is the element or a site name. The formula cannot settle it: a tourmaline writes its
    formula with the site letters in front of the groups (`X`(Na…)`Y`(Fe…)`Z`(Al…)), and parsing
    that yields a Y and a Z among its elements. An analytical table names no sites."""
    els = set()
    for row in ((ex or {}).get('epma') or {}).get('rows') or []:
        c = row[0] if isinstance(row, (list, tuple)) else getattr(row, 'name', None)
        for m in re.finditer(r'([A-Z][a-z]?)', str(c or '')):
            if m.group(1) in EP.ATOMIC_WEIGHTS:
                els.add(m.group(1))
    if els:
        return els
    from pxrd_review import paper_extract as PE
    fs = PE._formulas(text, name or '')
    return set(fs[0][1] or {}) if fs else None


def gii(result):
    """Root-mean-square deviation of the cation sums from their formal valences (vu), or None
    when no site states a valence."""
    devs = [bvs - exp for _c, _b, bvs, exp, _m in result if exp]
    return (sum(x * x for x in devs) / len(devs)) ** 0.5 if devs else None


def structure_for(pdf, ex=None, text=None):
    """The paper's own bond table as a structure, with the candidate whose bonds add up best.
    -> (BondStructure, result, gii) or (None, None, None). `ex`/`text` supply the site elements
    (the coordinates table) and the charges (the paper's formula)."""
    from pxrd_review import paper_extract as PE
    from pxrd_review import paper_structure as PS
    tabs = read_tables(pdf)
    if not tabs:
        return None, None, None
    text = PE.text_of(pdf) if text is None else text
    name = (ex or {}).get('name') or PE.mineral_name(text)
    try:
        els = site_elements(PS.paper_sites(pdf))
        charges = PS.element_charges(text, name)
        known = analysed_elements(ex, text, name)
    except Exception:
        els, charges, known = {}, {}, None
    P = B.Params(prefer='gh', u6='burns')
    best = None
    for rows in candidates(tabs):
        st = BondStructure(rows, els, charges, known, name or '')
        res, _an, _cells = compute(st, P)
        g = gii(res)
        if g is not None and (best is None or g < best[2]):
            best = (st, res, g)
    return best or (None, None, None)
