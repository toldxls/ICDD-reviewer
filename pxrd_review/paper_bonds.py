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
Row = namedtuple('Row', 'cation anion dist esd count page line col site', defaults=(None,))   # site: the name printed beside the element, 'Mn (X)' -> 'X'

DIST = re.compile(r'^(\d\.\d{2,4})(?:\((\d{1,3})\))?$')
DASH = '–—−‐-'
# a site label, with the dash a continuation row carries: '–S15', 'O(2)', 'Ow1', 'OH2', 'O10H'.
# A trailing lowercase group is the symmetry code the paper superscripts onto the anion ('O1vi')
# and names an image of the site, not another site; a trailing UPPERCASE letter is part of the
# label ('O12W', 'O8H' — the refiner's mark for a water or hydroxyl oxygen).
# A letter INSIDE the brackets is part of the label, not a symmetry code: 'M(2a)' and 'M(2b)' are
# the two halves of a split site and have to stay apart. Outside them the same letter is left to
# the symmetry-code rule below, where 'O1vi' must still read as O1.
LAB = re.compile(r"^[%s]?\s*([A-Z][A-Za-z]?)(?:\((\d{1,2}[a-z]?)\)|(\d{1,2}))?([A-Z]?)([a-z]{0,4}['′*†‡#]{0,2})$" % DASH)
PAIR = re.compile(r"^([A-Z][A-Za-z]?(?:\(\d{1,2}[a-z]?\)|\d{1,2})?[A-Z]?)[%s]"
                  r"([A-Z][A-Za-z]?(?:\(\d{1,2}[a-z]?\)|\d{1,2})?[A-Z]?)[a-z]{0,4}['′″*†‡#]{0,2}$" % DASH)   # 'Z–O8′': the same anion under a symmetry code, a second bond
BARE_DASH = re.compile(r'^[%s]+$' % DASH)
MULT_SIGNS = ('×', 'x', 'X', '·', '∙', '*')
# several corpus journals set the multiplication sign in a font whose '×' reaches the text as a 3
# ('0.10 3 0.01 3 0.01 mm' for a crystal size). It is read as one only BETWEEN the site label and
# the distance ('Si–O6 3 2 1.630(5)'), where a bare 3 has no other meaning; after the distance it
# would compete with the next column of numbers.
MULT_SIGNS_BEFORE = MULT_SIGNS + ('3',)
MULT = re.compile(r'^[×x·∙*]\s*(\d{1,2})$')
# the same multiplier printed in brackets, as its own token ('O6B (×2) 2.645(5)') or welded to the
# site label ('Sn-O4(×3) 1.998(2)', 'O5(×3)'). Several journals set it that way throughout, so a
# table written in that style yielded no cells at all until this was read.
MULT_PAREN = re.compile(r'^[(\[]\s*[×x·∙*]\s*(\d{1,2})\s*[)\]][↓→]?$')
MULT_TAIL = re.compile(r'(?:[(\[]\s*[×x·∙*]\s*(\d{1,2})\s*[)\]]|[×·∙*]\s*(\d{1,2}))[↓→]?$')


def _strip_mult(tok):
    """('O4', 3) for 'O4(×3)' — the count a paper welds onto its anion label. The caller keeps
    the stripped form only when it parses as a label, so a real label ending in a digit is safe."""
    m = MULT_TAIL.search(tok.strip())
    if not m:
        return tok, 1
    return tok[:m.start()].strip(), int(m.group(1) or m.group(2))

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
    """'Al1-O10H', 'M1-O1vi' typeset without spaces -> ('Al1', 'O10H') / ('M1', 'O1'). Both halves
    come back in the same normalised form `_label` gives, so 'M(1)-S(1)' and a continuation row's
    '-S(1)' name the same two sites."""
    m = PAIR.match(tok.strip())
    if not m:
        return None, None
    return (_label(m.group(1))[0] or m.group(1), _label(m.group(2))[0] or m.group(2))


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


# The elements the paper assigns to a site it names crystallographically. 'M1', 'T2', 'A', 'X'
# say nothing themselves, and the coordinates table's occupancy column — the other place to look —
# is often unreadable or absent; a paper that names its sites that way nearly always says what is
# on them, in a footnote to the very table ('*M1 = 0.37Mn + 0.27Mg + 0.35Fe'), in a site-population
# table ('Z 79.40(24) 4.54 Al + 0.18 Fe3+'), or in a sentence beside it.
def sites_from_text(text, labels):
    """{label: element} for the site names the paper itself assigns, over `labels` alone — asking
    only about sites a bond table named keeps the search off ordinary prose. Four ways a paper
    says it, in the order they are trusted:
      'M1 = 0.37Mn + 0.27Mg + 0.35Fe'   the shares, and the largest of them wins
      'M1 13.6 Al0.62Fe3+0.38'          a site-population table's row, the same arithmetic
      'T1 = (CrO4)/(SeO4)/(SO4)'        an assignment with no shares: the first element named
      'the M2 site is occupied by Cd'   the sentence, as a last resort
    """
    out = {}
    text = text.replace('¼', '=')                                    # the font's '=' ('MO(1) ¼ Ti')
    for lab in labels:
        if not re.fullmatch(r"[A-Z][A-Za-z]?\(?\d{0,2}\)?[a-z]?'?", lab):
            continue
        hit = _pop_weighted(text, lab) or _pop_named(text, lab) or _pop_prefixed(text, lab)
        if hit:
            out[_key(lab)] = hit
    return out


def _pop_prefixed(text, lab):
    """The site-prefixed formula — 'A(1)Na A(1)′□ M(1)Mg M(2)(Mg0.5Fe3+0.5)2(AsO4)3': each site name is
    followed by what sits on it, an element or a bracketed group whose first element is the dominant
    one. Read only where the run prefixes at least two sites, so a bare label in prose is never one."""
    pat = re.compile(r"(?<![A-Za-z0-9])%s[′']?\s?(?:\(([^()]{1,60})\)|([A-Z][a-z]?)(?![a-z]))" % re.escape(lab))
    for m in pat.finditer(text):
        around = text[max(0, m.start() - 80):m.end() + 80]
        if len(re.findall(r"(?<![A-Za-z0-9])[A-Z][A-Za-z]?\(?\d{0,2}\)?[′']?\s?(?:\([A-Z][a-z]?\d*\.\d|[A-Z][a-z]?(?![a-z]))", around)) < 2:
            continue
        inner = m.group(1) or m.group(2) or ''
        em = re.match(r'([A-Z][a-z]?)', inner)
        if em and em.group(1) in EP.ATOMIC_WEIGHTS and em.group(1) not in ('O', 'H'):
            return em.group(1)
    return None


_POP_EL = re.compile(r'(?:(\d*\.\d+|\d+)\s*([A-Z][a-z]?)|([A-Z][a-z]?)\s*(?:\d\+|\d-)?\s*(\d*\.\d+))(?![a-z])')
_POP_ANY = re.compile(r'(?<![A-Za-z])([A-Z][a-z]?)(?![a-z])')
_POP_SAID = re.compile(r'(?:occupied|populated|filled|dominated)\s+(?:by|with)\s+(?:[a-z]+\s+){0,2}([A-Z][a-z]?)(?![a-z])')


def _pop_segments(text, lab):
    """The stretches of text that state what is on site `lab`: after an '=' or ':' assignment
    (footnote or sentence), and after the label at the start of a line (a site-population table
    row). Each is cut at the next site's assignment so two sites' shares never mix."""
    segs = []
    for m in re.finditer(r'(?:(?<=^)|(?<=[\n(*;,:])|(?<=[\n(*;,:]\s))\s*%s\s*\*?\s*[=:]' % re.escape(lab), text, re.M):
        segs.append(re.split(r";|\n|,?\s+[A-Z][A-Za-z]?\(?\d{0,2}\)?'?\s*=", text[m.end():m.end() + 90])[0])
    for m in re.finditer(r'^\s*%s\s+(?=[\d(])' % re.escape(lab), text, re.M):
        segs.append(text[m.end():m.end() + 90].split('\n')[0])
    return segs


def _pop_weighted(text, lab):
    """The element with the largest printed share, over every stretch that names the site."""
    best = None
    for seg in _pop_segments(text, lab):
        seg = re.sub(r'\(\d{1,3}\)', '', seg)                     # the esd of a site-scattering value
        for em in _POP_EL.finditer(seg):
            num, el = (em.group(1), em.group(2)) if em.group(2) else (em.group(4), em.group(3))
            if el not in EP.ATOMIC_WEIGHTS or el in ('O', 'H'):
                continue
            try:
                v = float(num)
            except (TypeError, ValueError):
                continue
            if 0 < v <= 20 and (best is None or v > best[1]):
                best = (el, v)
    return best[0] if best else None


def _pop_named(text, lab):
    """No shares printed: the first element of an assignment ('T1 = (CrO4)/(SeO4)'), else the one
    a sentence names ('the M2 site was found to be fully occupied by Cd')."""
    for seg in _pop_segments(text, lab):
        for em in _POP_ANY.finditer(re.sub(r'\(\d{1,3}\)', '', seg)):
            el = em.group(1)
            if el in EP.ATOMIC_WEIGHTS and el not in ('O', 'H'):
                return el
        break                                                     # only the first assignment: later ones are other sentences
    for m in re.finditer(r'(?<![A-Za-z0-9])%s\s+(?:site|position)' % re.escape(lab), text):
        said = _POP_SAID.search(text[m.end():m.end() + 120])
        if said and said.group(1) in EP.ATOMIC_WEIGHTS and said.group(1) not in ('O', 'H'):
            return said.group(1)
    return None


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
    if head and head not in AMBIGUOUS and not (len(head) == 1 and known and head not in known and re.fullmatch(r'[A-Z]\d{0,2}', label)):
        return head                                              # a bare 'B' (with 'A' and 'X' beside it) in a paper whose analysis names no boron is a site letter, put to the paper's own assignment
    if sites:
        hit = sites.get(_key(label))
        if hit:
            return hit
    if head == 'W' and WATER_LABEL.match(label) and not (known and 'W' in known):
        return 'O'          # 'W1', 'W2': the refiner's name for a water molecule. Tungsten only
                            # where the paper's own analysis names it — and then `known` says so.
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
    m = (MULT.match(ws[j][4].strip()) or MULT_PAREN.match(ws[j][4].strip())) if j >= 0 else None
    if m:
        return int(m.group(1)), j - 1
    # the same font trap, with the sign and the count welded into one token: 'Cr1–O2 33 1.677(10)'
    # is Cr1–O2 ×3. A bare '33' means nothing else where the cell's own label stands to its left,
    # and the multiplicities a table prints run 2 to 9 — '30' and '31' are left as the numbers
    # they look like.
    m = re.fullmatch(r'3([2-9])', ws[j][4].strip()) if j >= 1 else None
    if m and (_label(ws[j - 1][4])[0] or _pair_token(ws[j - 1][4])[1]):
        return int(m.group(1)), j - 1
    return 1, j


def _mult_after(ws, i, mangled=False):
    """The '* 3' printed after the distance instead ('X -O(2) 2.503(4) * 3'). On a page set in the
    font that loses its symbols (`_mangled`) the sign and the count arrive welded into one token,
    'O1 2.196(3) 32' — read only in the very next token, since further right the next column
    begins, and only on such a page: elsewhere a two-digit number after a distance is a column."""
    if i + 1 < len(ws):
        t1 = ws[i + 1][4].strip()
        m = MULT_PAREN.match(t1) or (re.fullmatch(r'3([2-9])', t1) if mangled else None)
        if m:                                  # the bracketed and the welded forms, in the very
            return int(m.group(1))             # next token only — further right is the next column
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


# In the relaxed pass the dash is the only thing missing, so something else has to say that a
# number is a bond: the second site is an ANION (no bond table pairs two cations), and the distance
# carries the esd a refined one always carries. 'CaO 3.03' of a composition table survives neither.
ANION_HEADS = frozenset(('O', 'F', 'Cl', 'S', 'N', 'Se', 'Te', 'Br', 'I'))
# the other thing a bond table puts in the anion column: the refiner's name for a water molecule.
# 'W' is tungsten too, but a bond table pairs a cation with an anion, and a W in that slot is water
# far more often than it is a tungstate's own cation — and `element_of` still has the last word.
WATER_LABEL = re.compile(r'^(?:W|OW|Ow|Wat|HOH)\d{0,2}[A-Za-z]?$')
SITE_PAREN = re.compile(r"^\(([A-Z][A-Za-z]?\d{0,2}[a-z]?)\)$")     # 'Mn (X) O1 2.196(3)': the site name beside its element


def _cation_left(ws, dash):
    """The cation of a row whose dash is typeset onto the CATION instead of the anion — 'T 1A– O1A
    1.630(2)', where the site label is split across two words as well ('T' set in italic, '1A' not).
    -> (label, False) or (None, False)."""
    for k in (dash - 1, dash - 2):
        if k < 0:
            continue
        tok = ''.join(w[4] for w in ws[k:dash]).strip()
        if not re.search(r'[%s]$' % DASH, tok):
            continue
        lab, _d = _label(tok.rstrip(DASH))
        if lab:
            return lab, False
    return None, False


def _cells(line, relaxed=False, mangled=False):
    """The bond cells of one typeset line: [(x where the cell starts, cation token or None, anion,
    d, esd, count)]. A line of a multi-column table holds one cell per column. `relaxed` reads the
    journals that print no dash at all ('Mn (X) O1 2.196(3)', and the continuation rows 'O5
    2.334(2)' under it) — see `_bond_caption`, which is what admits a page to that pass; `mangled`
    says the page is set in the font of `_mangled`."""
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
        tok, welded = _strip_mult(ws[j][4])         # 'O4(×3)', 'Sn-O4(×3)': the count welded onto the label
        an, dashed = _label(tok)
        cat = None; site = None
        if an is None:                              # 'Al1-O10H' as one token
            cat, an = _pair_token(tok)
            if an is None:
                continue
            dashed = True
        if welded > 1:
            count = welded if count == 1 else count * welded
        dash = j                                    # where the cell starts: the dash, attached or its own
        if not dashed:                              # 'Pb1 - S7 2.814': the dash is its own token
            if j >= 1 and BARE_DASH.match(ws[j - 1][4].strip()):
                dash = j - 1
            elif relaxed and m.group(2) and (re.match(r'^([A-Z][a-z]?)', an).group(1) in ANION_HEADS
                                             or WATER_LABEL.match(an)):
                pass                                # no dash anywhere: the anion and the esd stand for it
            else:
                continue                            # no dash at all: a cell of some other table
        if cat is None and dash >= 1:
            c, c_dash = _label(ws[dash - 1][4])
            if c is None and dash >= 2 and SITE_PAREN.match(ws[dash - 1][4].strip()):
                c, c_dash = _label(ws[dash - 2][4])  # 'Mn (X) O1': the element, with its site name between
                if c is not None:
                    site = SITE_PAREN.match(ws[dash - 1][4].strip()).group(1)
            if c is None:
                c, c_dash = _cation_left(ws, dash)   # 'T 1A– O1A': the dash on the cation, its label split
            if c is not None and not c_dash:
                cat = c
        if count == 1:
            count = _mult_after(ws, i, mangled)
        # the cell starts at the dash, on the head row and on every continuation row alike; the
        # cation of the head row sits further left and would put that row in another column
        out.append((ws[dash][0], cat, an, d, int(m.group(2)) if m.group(2) else None, count, site))
    return out


_BOND_CAPTION = re.compile(r'(?:TABLE|Table)\s+[A-Za-z]?\d+[A-Za-z]?\s*[.:]?[^\n]{0,90}?'
                           r'(?:bond|inter-?atomic|interatomic|coordination)[^\n]{0,20}?(?:length|distance)', re.I)


def _mangled(lines):
    """Whether a page is set in the font several journals use whose symbols reach the text as other
    characters: '+' as 'þ' ('Mn2þ'), '=' as '¼' ('R1 ¼ 3.96%'), '×' as '3'. The first two identify
    it — no English page prints them otherwise — and they are what licenses reading the third."""
    txt = '\n'.join(' '.join(w[4] for w in ln['w']) for ln in lines)
    return txt.count('þ') + txt.count('¼') >= 2


def _bond_caption(lines):
    """Whether a page carries a bond-distance table's own caption. It is what admits the page to
    the dashless pass: a composition or powder table on a page of its own never does, and a page
    that prints one alongside the bond table still has to get its cells past `_cells`."""
    return any(_BOND_CAPTION.search(' '.join(w[4] for w in ln['w'])) for ln in lines)


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
        mang = _mangled(lines); capt = _bond_caption(lines)
        found = [(li, c) for li, ln in enumerate(lines) for c in _cells(ln, mangled=mang)]
        if capt:                                          # the page says it prints a bond table: read the
            loose = [(li, c) for li, ln in enumerate(lines) for c in _cells(ln, True, mang)]
            if len(loose) > len(found):                   # dashless journals too, which yield nothing above
                found = loose
        # four cells is what tells a table from prose that happens to state a distance. Where the
        # page carries the table's own caption three will do — a simple structure prints a short
        # table ('N(NH4)–O (×12) 3.161(5)' and two more lines is the whole of it).
        floor = 3 if capt else MIN_ROWS
        if len(found) < floor:
            continue
        centres = _columns([c[0] for _li, c in found])
        placed = [(li, min(range(len(centres)), key=lambda i: abs(centres[i] - c[0])), c)
                  for li, c in sorted(found, key=lambda t: (t[0], t[1][0]))]
        heads = _column_heads(lines, centres, placed)
        by_col = {}; carried = {}; sites = {}
        for li, k, c in placed:
            cat = c[1] or carried.get(k) or heads.get(k)
            if c[1]:
                carried[k] = c[1]; sites[k] = c[6] if len(c) > 6 else None
            if not cat:
                continue
            by_col.setdefault(k, []).append(Row(cat, c[2], c[3], c[4], c[5], pno + 1, li, k, sites.get(k) if cat == carried.get(k) else None))
        bonds = [r for k in sorted(by_col) for r in by_col[k]]
        if len(bonds) >= floor:
            out.append({'page': pno + 1, 'caption': _caption(lines, found[0][0]),
                        'columns': len(by_col), 'bonds': bonds, 'sums': _bvs_marks(lines, centres, by_col)})
    return out


BVS_MARK = re.compile(r'^(?:BVS|BVSs|ΣBVS|BVsum|Σbv)\*{0,2}[:=]?$', re.I)


def _bvs_marks(lines, centres, by_col):
    """The bond-valence sum a bond table prints under each site's own block — 'BVS 2.12' below
    '<Ca1–O> 2.400', the way the Canadian Mineralogist and American Mineralogist set it. The mark
    stands in the label column, so its x names the column and the last cation read in that column
    above it names the site. -> [(site label, value)], one per mark."""
    out = []
    for li, ln in enumerate(lines):
        ws = ln['w']
        for i, w in enumerate(ws):
            if not BVS_MARK.match(w[4].strip()) or i + 1 >= len(ws):
                continue
            m = re.fullmatch(r'(\d{1,2}\.\d{1,3})', ws[i + 1][4].strip())
            if not m or not (0.02 <= float(m.group(1)) <= 12.0):
                continue
            k = min(range(len(centres)), key=lambda c: abs(centres[c] - w[0]))
            above = [r for r in by_col.get(k) or [] if r.line < li]
            if above:
                out.append((above[-1].cation, float(m.group(1))))
    return out


def _column_heads(lines, centres, placed):
    """The cation a table names once, over the whole column, instead of on its first row:

        Pb1        Pb2        Pb3        As1
        –O4 2.27(1)  –O5 2.38(1)  –O6 2.303(9)  –O3 1.77(1)

    Every cell of such a column is a continuation row with nothing to carry down, so without this
    the whole table is dropped. Only columns that name no cation of their own are looked up, and
    only at a line above them that holds a site label and nothing else in that column's width.
    -> {column: label}."""
    first = {}
    named = set()
    for li, k, c in placed:
        first.setdefault(k, li)
        if c[1]:
            named.add(k)
    out = {}
    for k, li0 in first.items():
        if k in named:
            continue
        lo, hi = centres[k] - 30, centres[k] + 70
        for j in range(li0 - 1, max(-1, li0 - 6), -1):
            ws = [w for w in lines[j]['w'] if lo <= (w[0] + w[2]) / 2 <= hi]
            if not ws:
                continue
            heads = [re.sub(r'[%s]+$' % DASH, '', w[4].strip()) for w in ws]   # 'Pb1–', 'Me4–': the dash of the bonds below, typeset on the head (the sartorite homologues)
            labs = [_label(h)[0] for h in heads if _label(h)[0] and not _label(h)[1]]
            if len(labs) == len(ws):                 # the line holds site names in this column and nothing else
                out[k] = labs[0]
            break                                    # the first line above with anything on it, or none
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

    def __init__(self, rows, elements=None, charges=None, known=None, name='', inferred=(), occ=None):
        self.name = name; self.notes = []; self.aliases = {}; self.path = None
        self.inferred = {_key(x) for x in inferred or ()}
        self.occ = {_key(k): v for k, v in (occ or {}).items()}          # the coordinates table's site occupancies, for the checker's weighting
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
        species = None if anion else self.occ.get(_key(label))
        if isinstance(species, list) and species:                        # 'Na0.62Ca0.38': the site as the paper populates it — a cell of its table is the share-weighted sum
            sp = []
            for el_i, share in species:
                ox_i = self.charges.get(el_i)
                if ox_i is None:
                    ox_i = (B.DEFAULT_OX if has_o else {**B.DEFAULT_OX, **B.DEFAULT_OX_NO_O}).get(el_i)
                if ox_i:
                    sp.append(B.Species(el_i, ox_i, share))
            if sp:
                return B.Site(label, sp[0].element, None, sp, [], 1, min(1.0, sum(x.occ for x in sp)), None)
        share = species if isinstance(species, (int, float)) and 0 < species < 1 else 1.0   # a bare fraction: the element's own share, the rest a vacancy
        sp = [B.Species(el, ox, share)]
        return B.Site(label, el, None, sp, [], 1, share, None)

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
        # a site's valences and its formal valence are the share-weighted sums over its species:
        # a fully occupied one-element site is the plain case (share 1)
        bvs = sum(sum((s or 0.0) * sp.occ for sp, s in b.vals) * b.count for b in bonds)
        expected = sum(sp.ox * sp.occ for sp in c.species if sp.ox and sp.ox > 0)
        ncoord = sum(b.count for b in bonds)
        result.append((c, bonds, bvs, expected, sum(b.dist * b.count for b in bonds) / ncoord))
        for b in bonds:
            s_site = sum((s or 0.0) * sp.occ for sp, s in b.vals)
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


def gii(result, skip=()):
    """Root-mean-square deviation of the cation sums from their formal valences (vu), or None
    when no site states a valence. `skip` leaves out the sites whose element the paper's prose
    supplied rather than the table: a wrong guess there is not evidence about the reading."""
    devs = [bvs - exp for c, _b, bvs, exp, _m in result if exp and _key(c.label) not in skip]
    return (sum(x * x for x in devs) / len(devs)) ** 0.5 if devs else None


def context(pdf, tabs, text, name, ex=None):
    """What a bond table needs besides its distances: the element on each site, the charge of each
    element, the elements the paper's analysis names, and the site names left over.
    -> (elements, charges, known, unnamed, inferred). The coordinates table's occupancy column
    answers first; the sites it cannot name ('M1', 'T2', 'A') are put to the paper's own
    assignments ('M1 = 0.37Mn + …'), and what even those leave unnamed comes back as `unnamed` —
    those labels are certainly sites of this structure, so they can say what a bond-valence
    table's columns are without pretending to say what sits on them. `inferred` names the sites
    the paper's own words resolved: measured against the corpus .cif files that reading is right
    11 times in 17, so those sites are computed but kept out of the instability index, which is
    the gate on whether the TABLE was read right and must not answer for them."""
    from pxrd_review import paper_structure as PS
    try:
        els = site_elements(PS.paper_sites(pdf))
        charges = PS.element_charges(text, name)
        known = analysed_elements(ex, text, name)
    except Exception:
        els, charges, known = {}, {}, None
    labs = {r.cation for t in tabs for r in t['bonds']} | {r.anion for t in tabs for r in t['bonds']}
    unknown = {l for l in labs if element_of(l, els, known) is None}
    if unknown:                                          # 'M1', 'T2', 'A': the paper's own assignment
        try:
            els = dict(sites_from_text(text, unknown), **els)
        except Exception:
            pass
    inferred = {l for l in unknown if element_of(l, els, known) is not None}
    return els, charges, known, {l for l in unknown if element_of(l, els, known) is None}, inferred


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
    els, charges, known, unnamed, inferred = context(pdf, tabs, text, name, ex)
    P = B.Params(prefer='gh', u6='burns')
    sums = [pair for t in tabs for pair in (t.get('sums') or [])]
    best = None
    try:
        occs = {}
        for lab, _x, _y, _z, tail in PS.paper_sites(pdf):
            sp = PS.occupancy_species(tail); v = PS._occupancy(tail)
            if sp and (len(sp) > 1 or sp[0][1] < 0.999):
                occs[lab] = sp
            elif v is not None and v < 0.999:
                occs[lab] = v
    except Exception:
        occs = {}
    for rows in candidates(tabs):
        st = BondStructure(rows, els, charges, known, name or '', inferred, occ=occs)
        labs = {r.cation for r in rows}
        st.printed_sums = [(lab, v) for lab, v in sums if lab in labs]     # the BVS this table's own sites carry
        st.unnamed = labs & unnamed                                        # sites of this structure, element unknown
        res, _an, _cells = compute(st, P)
        g = gii(res, st.inferred)
        # a candidate whose every site is one the paper's prose named has no index of its own —
        # `gii` is deliberately blind to those — but its bonds are still the paper's, and a grid of
        # individual valences is checked against them without an index. It ranks behind any
        # candidate that has one.
        key = (0, g) if g is not None else (1, 0.0)
        if res and (best is None or key < best[3]):
            best = (st, res, g, key)
    return best[:3] if best else (None, None, None)
