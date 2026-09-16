"""Space-group symbols and the operators they stand for.

`bv_check` needs symmetry operators, and a .cif that carries no `_space_group_symop_operation_xyz`
loop has until now been refused outright (only P1 and P-1 could be handled without a table). A paper
never prints operators at all — it prints a Hermann-Mauguin symbol and expects the reader to know
what it means. This module is that knowledge: `data/symops.json.gz`, built by `tools/build_symops.py`
from the corpus's own .cif files, every operator set verified to be a closed group with an identity
and inverses.

Two jobs:
  `lookup(symbol)`      the operators a symbol stands for -> [(rot, tr), …] per variant, commonest
                        first (a symbol with two variants is one written in two origin choices).
  `find_in_text(text)`  the symbol a paper states, read by matching the table's own vocabulary
                        rather than by guessing at a regex — 'space group and the cell' otherwise
                        yields the symbol 'And'.

Symbols are compared normalised: spaces out, upper case, subscripts and overbars folded, a
parenthesised setting note dropped, ':H'/':R' and a bare trailing H/R treated alike.
"""
import os, re, gzip, json, functools

_SUB = str.maketrans('₀₁₂₃₄₅₆₇₈₉', '0123456789')
_DASH = str.maketrans({'–': '-', '—': '-', '−': '-', '̄': '-', '̅': '-', '‾': '-'})
_CTRL = re.compile(r'(?<=[A-Za-z0-9])[\x00-\x08\x0b-\x1f](?=\d)')   # the overbar of P1̄ / R3̄ / Fm3̄m as the text layer delivers it: a control code before the digit


def _data_file():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'symops.json.gz')


@functools.lru_cache(maxsize=1)
def _table():
    try:
        with gzip.open(_data_file(), 'rt', encoding='utf-8') as f:
            d = json.load(f)
        _table.numbers = d.get('numbers') or {}
        return d.get('groups') or {}, d.get('frac', 12)
    except (OSError, ValueError):
        _table.numbers = {}
        return {}, 12


def number(symbol):
    """The International Tables number of a symbol, or None."""
    _table()
    k = key_for(symbol)
    return getattr(_table, 'numbers', {}).get(k) if k else None


SYSTEMS = ((2, 'triclinic'), (15, 'monoclinic'), (74, 'orthorhombic'), (142, 'tetragonal'), (167, 'trigonal'), (194, 'hexagonal'), (230, 'cubic'))


def crystal_system(symbol):
    """'triclinic' … 'cubic' from the group's number, or None when the symbol is unknown."""
    n = number(symbol)
    if not n:
        return None
    return next(name for top, name in SYSTEMS if n <= top)


ALL_SYSTEMS = frozenset(name for _top, name in SYSTEMS)


def cell_system(cell, tol=0.002):
    """The crystal systems a cell's metric allows — {'a','b','c','α','β','γ'} in Å and degrees —
    as the DOWNWARD closure of the metric's highest symmetry: the metric only bounds the symmetry
    from above, since a crystal of lower symmetry may print a cell of higher metric symmetry
    (a pseudo-orthorhombic monoclinic cell prints β = 90.00; a cell whose angles the text layer lost
    arrives at 90° by default), and the symbol's system, not the metric, has the say. So a cell at
    90° allows orthorhombic, monoclinic and triclinic — tetragonal too with two axes equal, cubic
    with three — and one angle off allows monoclinic and triclinic. The hexagonal metric (a = b,
    γ = 120) allows hexagonal and trigonal only, the rhombohedral one trigonal: no lower-symmetry
    crystal prints its cell in those axes. A cell missing an angle allows every system. Without the
    closure, three triclinic minerals whose angles the text lost were disowned for a relative's
    monoclinic symbol (audit 2026-09-16)."""
    a, b, c = cell['a'], cell['b'], cell['c']
    if any(k not in cell for k in ('α', 'β', 'γ')):
        return set(ALL_SYSTEMS)
    al, be, ga = cell['α'], cell['β'], cell['γ']
    eq = lambda x, y: abs(x - y) <= tol * max(x, y)
    right = [abs(x - 90) < 0.05 for x in (al, be, ga)]
    if all(right):
        out = {'orthorhombic', 'monoclinic', 'triclinic'}
        if eq(a, b) or eq(b, c) or eq(a, c):
            out.add('tetragonal')
        if eq(a, b) and eq(b, c):
            out.add('cubic')
        return out
    if eq(a, b) and abs(ga - 120) < 0.05 and right[0] and right[1]:
        return {'hexagonal', 'trigonal'}
    if eq(a, b) and eq(b, c) and abs(al - be) < 0.05 and abs(be - ga) < 0.05:
        return {'trigonal'}                                 # rhombohedral axes
    if sum(right) == 2:
        return {'monoclinic', 'triclinic'}
    return {'triclinic'}


def available():
    return bool(_table()[0])


def normalize(s):
    """'P 2₁/c' -> 'P21/C'; 'R-3m (hexagonal axes)' -> 'R-3M'; an overbar folded to '-'. A control
    code inside a symbol ('P\\x021', 'R\\x013') is the font's overbar glyph: the bar itself."""
    s = (s or '').strip().strip("'\"")
    s = _CTRL.sub('-', s)
    s = s.translate(_SUB).translate(_DASH)
    s = re.sub(r'\([^)]*\)', '', s)
    return re.sub(r'\s+', '', s).upper()


def _variants(n):
    """The forms a symbol may be written in, most specific first."""
    out = [n]
    m = re.match(r'^(R[^:]*?)[:]?([HR])$', n)          # 'R-3mH', 'R-3m:H' -> 'R-3M'
    if m:
        out += [m.group(1), m.group(1) + ':' + m.group(2)]
    if ':' in n:
        out.append(n.split(':')[0])
    out += [n + ':H', re.sub(r'^([A-Z])1(.+)1$', r'\1\2', n)]   # 'P121/C1' -> 'P21/C'
    seen = set(); uniq = []
    for x in out:
        if x and x not in seen:
            seen.add(x); uniq.append(x)
    return uniq


def key_for(symbol):
    """The table key a symbol resolves to, or None."""
    groups, _ = _table()
    for cand in _variants(normalize(symbol)):
        if cand in groups:
            return cand
    return None


def lookup(symbol):
    """[[(rot, tr), …], …] — one operator list per known variant, commonest first; [] when the
    symbol is not in the table. Translations are floats in [0, 1)."""
    groups, frac = _table()
    k = key_for(symbol)
    if not k:
        return []
    out = []
    for var in groups[k]:
        out.append([([list(r) for r in rot], [t / float(frac) for t in tr]) for rot, tr in var['ops']])
    return out


@functools.lru_cache(maxsize=1)
def _vocabulary():
    """The table's keys, longest first, for matching inside running text."""
    groups, _ = _table()
    keys = set(groups)
    for k in list(groups):
        keys.update(_variants(k))
    return sorted(keys, key=len, reverse=True)


_NEAR = re.compile(r'space[\s-]*group|spatial group|sp\.?\s*gr\.?|symmetry', re.I)
# the symbol set right after the crystal system — 'Smamite is triclinic, P1, a = …', a crystal-data block's
# 'Monoclinic, C2/m' — for a paper that prints no 'space group' phrase at all: looked at only then, because a
# relative's 'triclinic, P1' in the introduction outranked puninite's own 'space group C2/c' (70643) when both were one list
_NEAR_LOOSE = re.compile(r'space[\s-]*group|spatial group|sp\.?\s*gr\.?|symmetry'
                         r'|(?:triclinic|monoclinic|orthorhombic|tetragonal|trigonal|hexagonal|cubic|rhombohedral),\s*(?=[A-Z][\d\-/])', re.I)
# the phrases that NAME the space group, as against 'symmetry' and the crystal-system comma: a
# two-letter symbol with no digit or bar (An, Am, Pa, Pm, Cm, Cc, Im, Ia, Pb …) is an English word
# or an element as often as a setting, and is taken only right after one of these, with no sentence
# end between — 'symmetry. An average of 22 analyses' had read the setting An (audit 2026-09-16)
_EXPLICIT = re.compile(r'space[\s-]*group|spatial group|sp\.?\s*gr\.?', re.I)
_WORDLIKE = re.compile(r'^[A-Z][A-Z]$')


def find_in_text(text, window=90):
    """The space group a paper states, matched against the table's vocabulary in the text after a
    'space group' phrase — or, when the paper prints none, after its crystal system ('triclinic,
    P1, a = …'). -> (symbol as the table keys it, the phrase it was read from) or (None, '')."""
    if not text:
        return None, ''
    vocab = _vocabulary()
    if not vocab:
        return None, ''
    cands = [(k, k) for k in vocab] + [(k, k.replace('-', '')) for k in vocab if '-' in k and k.replace('-', '') not in vocab]   # the barred group's unbarred twin ('FD3M' for Fd3̄m, the overbar lost to the font) when that form is no group of its own (P31m is)
    for near in (_NEAR, _NEAR_LOOSE):
        for m in near.finditer(text):
            seg = text[m.end():m.end() + window]
            flat, back = _flat(seg)
            explicit = _EXPLICIT.match(m.group(0)) is not None
            best = None
            for k, k_ in cands:
                i = flat.find(k_)
                while i >= 0:
                    # the symbol is a word of its own in the raw text: 'and the cell' is not the A-centred
                    # setting 'An' followed by 'd', and '...Pnma' inside a reference is not a symbol
                    r0, r1 = back[i], back[i + len(k_) - 1] + 1
                    if not (r0 > 0 and seg[r0 - 1].isalpha()) and not (r1 < len(seg) and seg[r1].isalpha()) and seg[r0].isupper() \
                            and (not _WORDLIKE.match(k_) or (explicit and '.' not in seg[:r0])):
                        break                                # and the lattice letter is a capital: 'an inversion twin' is not the setting An
                    i = flat.find(k_, i + 1)
                if i < 0:
                    continue
                if best is None or i < best[1] or (i == best[1] and len(k_) > len(best[2])):
                    best = (k, i, k_)
            if best and best[1] <= 24:                       # the symbol stands near the phrase, not a page away
                return key_for(best[0]) or best[0], text[m.start():m.end() + window][:120]
    return None, ''


_LOOKALIKE = str.maketrans({'С': 'C', 'Р': 'P', 'В': 'B', 'А': 'A', 'Н': 'H', 'Ι': 'I', 'Ρ': 'P', '¯': '-', '\u0304': '-', '\u0305': '-', '‾': '-'})

def find_all_in_text(text, window=90):
    """Every space-group symbol the text states after a 'space group' phrase, distinct, the most
    often stated first — a paper names its relatives' groups too (75959: Im3̄m for a related mineral
    once, its own I213 twice), and which is its own is for the structure to decide."""
    counts = {}
    if not text:
        return []
    for m in _NEAR_LOOSE.finditer(text):
        sym, _ph = find_in_text(text[m.start():m.end() + window], window)
        if sym:
            counts[sym] = counts.get(sym, 0) + 1
    return [k for k, _v in sorted(counts.items(), key=lambda kv: -kv[1])]


_OWN = re.compile(r'\b(?:the|this) (?:new )?mineral (?:is|was)\b', re.I)
_CELL_STMT = re.compile(r'\ba\s*[=:]?\s*\d{1,2}\.\d')
_SENT_END = re.compile(r'\.\s+(?=[A-Z])')


def find_own_in_text(text, mineral, window=90):
    """The symbol the paper states as ITS OWN in the abstract's crystallographic sentence —
    'Xenophyllite is triclinic, P1 or P-1, a 9.643(6) …', 'The mineral is trigonal, R3m, with
    a = 10.7527(7) …' — read only when that is the FIRST symbol statement of the text and its
    sentence names the mineral (or says 'the mineral is') and states the cell. A paper's first
    explicit 'space group' phrase is otherwise its own symbol, but it may be a relative's ('the
    unit-cell parameters of sarcopside (space group P21/c) are …', a hypothetical 'the symmetry
    should be lowered to monoclinic space group Im') — and the abstract, when it states the symbol
    with the mineral and the cell, is the one place that cannot be. -> (symbol, phrase) or (None, '').
    Twelve corpus papers move against the first-phrase choice, every one to its own symbol or a
    setting/twin of it (audit 2026-09-16)."""
    if not text:
        return None, ''
    root = re.sub(r'[^a-z]', '', (mineral or '').lower())[:6]
    hits = list(_NEAR_LOOSE.finditer(text))
    for i, m in enumerate(hits):
        # the segment ends where the next phrase begins: read from THIS phrase, not from an explicit
        # 'space group' phrase further along the window that `find_in_text` would prefer
        end = min(m.start() + window + 40, hits[i + 1].start() if i + 1 < len(hits) else len(text))
        sym, phrase = find_in_text(text[m.start():end], window)
        if not sym:
            continue
        # the sentence: from the last sentence end before the phrase to the first after it — a
        # period followed by space and a capital, so 'a 9.643(6)' does not end it
        stop = _SENT_END.search(text, m.end())
        s0, s1 = max(text.rfind('. ', 0, m.start()), 0), (stop.start() + 1 if stop else len(text))
        sent = text[s0:s1]
        named = (root and root in re.sub(r'[^a-z]', '', sent.lower())) or _OWN.search(sent)
        if named and _CELL_STMT.search(text[m.start():min(s1, m.start() + 200)]):
            return sym, phrase
        return None, ''                     # only the first symbol statement of the text may be the abstract's
    return None, ''


def _flat(seg):
    """The segment normalised as `normalize` does — spaces out, upper case, subscripts and dashes
    folded, parenthesised notes dropped — with, for each character kept, the index it came from."""
    flat = []; back = []; depth = 0
    seg = seg.translate(_LOOKALIKE)                    # a Cyrillic С in 'Сmcm', a macron '¯' for the overbar: the text layer's look-alikes
    for i, ch in enumerate(seg):
        if ch == '(':
            depth += 1; continue
        if ch == ')':
            depth = max(0, depth - 1); continue
        if depth or ch.isspace():
            continue
        if ord(ch) < 32:
            ch = '-' if (i + 1 < len(seg) and seg[i + 1].isdigit() and i > 0 and seg[i - 1].isalnum()) else ''   # the overbar as a control code, else noise
            if not ch:
                continue
        ch = ch.translate(_SUB).translate(_DASH).upper()
        for c in ch:
            flat.append(c); back.append(i)
    return ''.join(flat), back


# ----------------------------------------------------------------------------- reflection conditions
def absent(ops, hkl):
    """Whether a reflection is systematically absent under an operator list: it is when some
    operator (R, t) maps h onto itself (h·R = h) and shifts its phase by a non-integer h·t —
    which covers the lattice centrings (R = 1, t = the centring vector), glide planes and screw
    axes at once, with no table of conditions to transcribe. Operators as `lookup` returns them:
    rotation rows and a translation in [0, 1). h, k, l are integers; (0 0 0) is never absent."""
    h, k, l = hkl
    if h == k == l == 0:
        return False
    for rot, tr in ops:
        # h·R (h a row vector on the left): h'_j = Σ_i h_i R_ij
        hr = (h * rot[0][0] + k * rot[1][0] + l * rot[2][0],
              h * rot[0][1] + k * rot[1][1] + l * rot[2][1],
              h * rot[0][2] + k * rot[1][2] + l * rot[2][2])
        if hr != (h, k, l):
            continue
        phase = h * tr[0] + k * tr[1] + l * tr[2]
        if abs(phase - round(phase)) > 1e-6:
            return True
    return False


def absences(symbol, hkls):
    """[hkl, …] of the given indices that the space group forbids — under EVERY setting the
    symbol has in the table (a nonstandard setting the writer meant is not a mis-index), so an
    index is reported only when no known setting of the symbol allows it. [] when the symbol is
    unknown, or the indices are all allowed."""
    variants = lookup(symbol)
    if not variants:
        return []
    out = []
    for hkl in hkls:
        try:
            t = tuple(int(v) for v in hkl)
        except (TypeError, ValueError):
            continue
        if all(absent(ops, t) for ops in variants):
            out.append(t)
    return out
