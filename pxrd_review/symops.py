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


def cell_system(cell, tol=0.002):
    """The lattice system a cell's metric allows — {'a','b','c','α','β','γ'} in Å and degrees — as
    the LOWEST-symmetry reading that fits: a cell with a = b and γ = 120 is hexagonal or trigonal,
    a = b = c with 90° angles cubic (or a rhombohedral cell at 90°), all 90° orthorhombic (which a
    tetragonal cell with a = b also is), one angle off monoclinic, else triclinic."""
    a, b, c = cell['a'], cell['b'], cell['c']; al, be, ga = cell.get('α', 90), cell.get('β', 90), cell.get('γ', 90)
    eq = lambda x, y: abs(x - y) <= tol * max(x, y)
    right = [abs(x - 90) < 0.05 for x in (al, be, ga)]
    if all(right):
        if eq(a, b) and eq(b, c):
            return {'cubic', 'tetragonal', 'orthorhombic'}
        if eq(a, b) or eq(b, c) or eq(a, c):
            return {'tetragonal', 'orthorhombic'}
        return {'orthorhombic'}
    if eq(a, b) and abs(ga - 120) < 0.05 and right[0] and right[1]:
        return {'hexagonal', 'trigonal'}
    if eq(a, b) and eq(b, c) and abs(al - be) < 0.05 and abs(be - ga) < 0.05:
        return {'trigonal'}                                 # rhombohedral axes
    if sum(right) == 2:
        return {'monoclinic'}
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


_NEAR = re.compile(r'space[\s-]*group|sp\.?\s*gr\.?|symmetry', re.I)


def find_in_text(text, window=90):
    """The space group a paper states, matched against the table's vocabulary in the text after a
    'space group' phrase. -> (symbol as the table keys it, the phrase it was read from) or (None, '')."""
    if not text:
        return None, ''
    vocab = _vocabulary()
    if not vocab:
        return None, ''
    for m in _NEAR.finditer(text):
        seg = text[m.end():m.end() + window]
        flat, back = _flat(seg)
        best = None
        for k in vocab:
            i = flat.find(k)
            while i >= 0:
                # the symbol is a word of its own in the raw text: 'and the cell' is not the A-centred
                # setting 'An' followed by 'd', and '...Pnma' inside a reference is not a symbol
                r0, r1 = back[i], back[i + len(k) - 1] + 1
                if not (r0 > 0 and seg[r0 - 1].isalpha()) and not (r1 < len(seg) and seg[r1].isalpha()) and seg[r0].isupper():
                    break                                # and the lattice letter is a capital: 'an inversion twin' is not the setting An
                i = flat.find(k, i + 1)
            if i < 0:
                continue
            if best is None or i < best[1] or (i == best[1] and len(k) > len(best[0])):
                best = (k, i)
        if best and best[1] <= 24:                       # the symbol stands near the phrase, not a page away
            return key_for(best[0]) or best[0], text[m.start():m.end() + window][:120]
    return None, ''


def _flat(seg):
    """The segment normalised as `normalize` does — spaces out, upper case, subscripts and dashes
    folded, parenthesised notes dropped — with, for each character kept, the index it came from."""
    flat = []; back = []; depth = 0
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
