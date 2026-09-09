"""What a paper PRINTS, read with deliberately crude regexes on the raw pdf text — the
denominator of the gauntlet (tools/corpus_paper_extract.py, the GAUNTLET section).

The readers are what is being measured, so the question "does this paper print an EPMA table,
a bond-valence table, a coordinates table, a compatibility index, optics" must be answered by
something that shares no code with them: the raw PyMuPDF text layer (not paper_extract.text_of,
which de-hyphenates and rewrites fonts) and five regexes anyone can read in a minute. They are
crude on purpose — a paper that mentions 'bond valence' in a table caption counts as printing
the table whether or not any reader can find it. A dev module, never shipped.
"""
import re

HAS_KEYS = ('epma', 'bv', 'coords', 'gd', 'optics')

_OX = (r'(?:SiO2|TiO2|Al2O3|Fe2O3|FeO|MnO|MgO|CaO|Na2O|K2O|P2O5|SO3|As2O5|As2O3|V2O5|UO3|UO2|ZnO|CuO|PbO|BaO|SrO|B2O3|CO2|H2O|'
       r'Li2O|ZrO2|Nb2O5|Ta2O5|WO3|MoO3|Sb2O3|Sb2O5|Bi2O3|Ag2O|Tl2O|Cs2O|Rb2O|Cr2O3|NiO|CoO|SnO2|GeO2|Ga2O3|In2O3|Sc2O3|Y2O3|'
       r'La2O3|Ce2O3|Nd2O3|ThO2|SeO2|TeO2|BeO|HfO2|Mn2O3|MnO2|SO2|CdO|HgO)')
_OX_RE = re.compile(r'\b' + _OX + r'\b')
_WT = re.compile(r'wt\.?\s?%|weight\s?%|wt\s?per\s?cent|\bwt\b', re.I)
_ANALYSED = re.compile(r'microprobe|EPMA|WDS|EDS|electron probe|electron-probe|SEM|ICP|analys', re.I)
_BV_CAPTION = re.compile(r'[Tt]able\s*S?\d+[^\n]{0,150}[Bb]ond[- ][Vv]alence|[Bb]ond[- ][Vv]alence[^\n]{0,150}[Tt]able\s*S?\d+')
# a STATED compatibility index or category — not the Gladstone–Dale relationship used to calculate an
# index the paper could not measure ('the Gladstone–Dale relationship gives n = 1.88'): that paper
# reports no compatibility, and its n is checked by the optics reader instead
_GD = re.compile(r'compatibility index|compatibility[^\n]{0,80}(superior|excellent|good|fair|poor)|K\s?[pP]\s*/\s*K\s?[cC]|1\s*[-–−]\s*\(?\s*K\s?[pP]', re.I)
_OPTICS = re.compile(r'\b2V\b|refractive ind|indices of refraction|index of refraction|\bn\s?\(?calc\)?\b|\bn\s*=\s*1\.\d|[αβγωε]\s*=\s*1\.\d|'
                     r'biaxial \(|uniaxial \(|\bisotropic,? n\b', re.I)
# a coordinates table by its SHAPE: an 'x y z' header, a caption announcing it, or three rows of
# label + three fractions of 3–5 decimals (scanned line by line — never a backtracking regex over
# the whole text)
_XYZ_HEAD = re.compile(r'^\s*(?:Atom|Site|Label)?\s*\|?\s*x\s*[|/]?\s*y\s*[|/]?\s*z\b|x/a\s+y/b\s+z/c|\bx\s+y\s+z\s+(?:U\s?eq|Uiso|B\s?eq|Biso|occ|U\s?iso)', re.I)
# the caption itself, at the start of a line — never the sentence "atom coordinates … in Online Materials
# Table S2", which announces a table the paper does not print
_COORD_CAP = re.compile(r'^\s*Table\s+S?\d+[.:]?\s+[^\n]{0,120}?(coordinates|atom(ic)? positions|positional parameters|site positions)', re.I | re.M)
_FRAC = r'[-−]?[01]?\.\d{3,5}(?:\(\d+\))?'
_COORD_ROW = re.compile(r'^[A-Z][A-Za-z]{0,2}\(?\d{0,2}\)?[A-Za-z]?\s+' + _FRAC + r'\s+' + _FRAC + r'\s+' + _FRAC)


def raw_text(pdf):
    """The pdf's own text layer, page by page — nothing normalised."""
    import pymupdf
    with pymupdf.open(pdf) as doc:
        return '\n'.join(page.get_text() for page in doc)


def features(text):
    """{'epma', 'bv', 'coords', 'gd', 'optics': bool} — what the text prints, crudely."""
    t = text or ''
    n_ox = len(set(_OX_RE.findall(t)))
    coords = bool(_COORD_CAP.search(t))
    if not coords:
        rows = 0
        for ln in t.split('\n'):
            if _XYZ_HEAD.search(ln):
                coords = True; break
            if _COORD_ROW.match(ln):
                rows += 1
                if rows >= 3:
                    coords = True; break
    return {'epma': bool(_WT.search(t)) and n_ox >= 4 and bool(_ANALYSED.search(t)),
            'bv': bool(_BV_CAPTION.search(t)),
            'coords': coords,
            'gd': bool(_GD.search(t)),
            'optics': bool(_OPTICS.search(t))}


def is_target(has):
    """The gauntlet's subset: a paper that prints all five."""
    return bool(has) and all(has.get(k) for k in HAS_KEYS)
