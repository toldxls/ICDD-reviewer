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


def _data_file():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'symops.json.gz')


@functools.lru_cache(maxsize=1)
def _table():
    try:
        with gzip.open(_data_file(), 'rt', encoding='utf-8') as f:
            d = json.load(f)
        return d.get('groups') or {}, d.get('frac', 12)
    except (OSError, ValueError):
        return {}, 12


def available():
    return bool(_table()[0])


def normalize(s):
    """'P 2₁/c' -> 'P21/C'; 'R-3m (hexagonal axes)' -> 'R-3M'; an overbar folded to '-'."""
    s = (s or '').strip().strip("'\"")
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
        flat = normalize(seg)
        best = None
        for k in vocab:
            i = flat.find(k)
            if i < 0:
                continue
            # a symbol must not be the tail of a longer word ('...PNMA' inside a reference)
            if best is None or i < best[1] or (i == best[1] and len(k) > len(best[0])):
                best = (k, i)
        if best and best[1] <= 24:                       # the symbol stands near the phrase, not a page away
            return key_for(best[0]) or best[0], text[m.start():m.end() + window][:120]
    return None, ''
