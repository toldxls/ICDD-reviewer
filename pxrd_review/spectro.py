"""The vibrational bands a paper states, and the distances it infers from them (`pxrd spectro <manuscript.docx|.pdf> [--cif X]`).

A description of a hydrated or uranyl mineral reads distances off its Raman / infrared spectrum with two
empirical relations, and both can be recomputed from the paper's own numbers:
  Bartlett & Cooney (1989)   d(U–O) of the uranyl ion from its stretching wavenumbers,
                             d = 106.5·ν1^(−2/3) + 0.575 Å and d = 91.41·ν3^(−2/3) + 0.804 Å;
  Libowitzky (1999)          ν(O–H) from the donor···acceptor distance of its hydrogen bond,
                             ν = 3592 − 304·10^9·exp(−d(O···O)/0.1321) and, from the H···O distance,
                             ν = 3632 − 1.79·10^6·exp(−d(H···O)/0.2146) (cm⁻¹, Å).
The coefficients are the published ones; the papers that print a band beside the distance it gave are the
proof that they are transcribed right (tools/corpus_spectra.py runs every such pair).

What is read, from the prose (`bands`, `stated_distances`):
  each band position with its technique, its shape words and the group and mode it is assigned to;
  each distance a sentence credits to one of the two relations, with the band it came from where the
  sentence says which.
What is said (`check_lines`), by grade:
  a stated distance its own band does not give             ' vs ' (a finding) — only where the sentence pairs
                                                           the two itself, and where the reading has proved
                                                           itself on the paper's other pairs or the sibling
                                                           relation reproduces the stated value exactly;
  the same without that proof                              information;
  the inferred distance beside the structure's own         information (a correlation's scatter is not an error);
  the formula's hydrogen and light groups beside the       information (`species_lines`): H2O in the formula with O–H
  bands stated                                             stretches stated and no H–O–H bending band; the text itself
                                                           saying no band stands there; a spectrum that reaches no O–H
                                                           region; water stated where the formula has only hydroxyl;
                                                           ammonium / carbonate / nitrate / hydronium with no band;
  an assignment table (.docx) beside the prose             information (`table_bands`, `table_lines`).
A band the sentence says the spectrum does NOT show ('no absorption band at ca. 1650 cm-1') and a region ('bands below
320 cm-1') are not bands of the spectrum (`absent_bands`, `band_ranges`).
The structure side (`uranyl_sites`, `hbond_distances`) reads the .cif through bv_check; nothing here is written
into a document, and the text never leaves the machine.
"""
import os, re, sys, json, math, argparse, functools
from collections import namedtuple

# ----------------------------------------------------------------------------- the relations

LIB_FREE_OO = 3592.0        # Libowitzky's O···O curve has no distance at or above this wavenumber (a free O–H)
LIB_FREE_HO = 3632.0


def bc_nu1(nu):
    """d(U–O), Å, from the uranyl symmetric stretch ν1 (cm⁻¹) — Bartlett & Cooney (1989)."""
    return 106.5 * nu ** (-2.0 / 3.0) + 0.575


def bc_nu3(nu):
    """d(U–O), Å, from the uranyl antisymmetric stretch ν3 (cm⁻¹) — Bartlett & Cooney (1989)."""
    return 91.41 * nu ** (-2.0 / 3.0) + 0.804


def bc_nu1_inv(d):
    return (106.5 / (d - 0.575)) ** 1.5 if d > 0.575 else None


def bc_nu3_inv(d):
    return (91.41 / (d - 0.804)) ** 1.5 if d > 0.804 else None


def lib_d(nu):
    """d(O···O), Å, of the hydrogen bond behind an O–H stretch at nu (cm⁻¹) — Libowitzky (1999); None at or
    above 3592 cm⁻¹, where the curve has no distance."""
    return -0.1321 * math.log((LIB_FREE_OO - nu) / 304e9) if nu < LIB_FREE_OO else None


def lib_nu(d):
    """ν(O–H), cm⁻¹, expected for a donor···acceptor distance d(O···O) (Å) — Libowitzky (1999)."""
    return LIB_FREE_OO - 304e9 * math.exp(-d / 0.1321)


def lib_d_ho(nu):
    """d(H···O), Å, from an O–H stretch — Libowitzky (1999), the H···O form."""
    return -0.2146 * math.log((LIB_FREE_HO - nu) / 1.79e6) if nu < LIB_FREE_HO else None


def lib_nu_ho(d):
    return LIB_FREE_HO - 1.79e6 * math.exp(-d / 0.2146)


# name -> (citation, what it gives, forward, inverse); the registry the checks and the spectrum window read
CORRELATIONS = {
    'bc_nu1': ('Bartlett & Cooney (1989)', 'd(U–O) from ν1 (UO2)2+', bc_nu1, bc_nu1_inv),
    'bc_nu3': ('Bartlett & Cooney (1989)', 'd(U–O) from ν3 (UO2)2+', bc_nu3, bc_nu3_inv),
    'lib_oo': ('Libowitzky (1999)', 'd(O···O) from ν(O–H)', lib_d, lib_nu),
    'lib_ho': ('Libowitzky (1999)', 'd(H···O) from ν(O–H)', lib_d_ho, lib_nu_ho),
}
BC = 'Bartlett & Cooney (1989)'
LIB = 'Libowitzky (1999)'

# ----------------------------------------------------------------------------- the text

_DASHES = str.maketrans('−–—‒‐‑', '------')
_DOTS = re.compile(r'\s?(?:[⋅·∙•.]\s?){3}|\s?[…⋯]\s?|s²s²s²')            # O⋅⋅⋅O, O···O, O. . .O, O…O, and a font that prints the dots as 's²'
_CM = re.compile(r'(?<=\d)\s*cm\s*[-\x00-\x08\x0b-\x1f]?\s*1(?![\d.,]\d)')            # cm–1, cm−1, cm-1, cm 1, cm1 (the minus lost), cm\x011 (a control code for it)
_CM_BARE = re.compile(r'(?<=\d{3})\s*cm(?=[\s,.;:)\]]|$)(?!\s*-?1)')          # the superscript lost altogether: '817 cm.'
# ν as a journal font sets it: υ, and the Symbol-font letters n / v / m before a mode number or an O–H
_GROUPS = (r'UO2|SO4|PO4|AsO4|VO4|CO3|SiO4|BO3|BO4|MoO4|WO4|SeO3|SeO4|TeO3|TeO6|NO3|NH4|CrO4|H2O|HPO4|PO3OH|AsO3OH|SO3OH|'
           r'Si2O7|V2O7|P2O7|SbO3|AsO3|IO3|GeO4')
_NU_NUM = re.compile(r'(?<![A-Za-z0-9])[υnvm]\s?([1-4])(?=\s*(?:\(\s*[δd]\s*\))?\s*(?:of\s+(?:the\s+)?)?(?:[\(\[]\s*)?(?:' + _GROUPS + r'|uranyl|sym|anti|asym|stretch|bend|doubly|triply|\())')
_NU_OH = re.compile(r'(?<![A-Za-z0-9])[υnvm]\s?(?=\(?\s*O\s?-?\s?H\b)')
_NU_AFTER = re.compile(r'(?<![A-Za-z0-9])((?:' + _GROUPS + r')\s)[υnvm]\s?([1-4])(?![\d.])')   # after its group: 'the PO4 n3 occurs at 1159'
_ABBR = re.compile(r'\b(Figs?|Tabs?|al|ca|cf|e\.g|i\.e|vs|approx|Nos?|Eqs?|Refs?|resp|et|sp|var|incl|min|max)\.')


def normalise(text):
    """The text as the band readers take it: one dash, one 'cm-1', one 'ν', 'O···O' for a hydrogen bond."""
    t = (text or '').translate(_DASHES).replace('υ', 'ν').replace('\u2009', ' ').replace('\u202f', ' ').replace('˚A', 'Å').replace('A\u030a', 'Å')
    t = _dots(t)
    t = _CM.sub(' cm-1', t)
    t = _CM_BARE.sub(' cm-1', t)
    t = _NU_NUM.sub(lambda m: 'ν' + m.group(1), t)
    t = _NU_AFTER.sub(lambda m: m.group(1) + 'ν' + m.group(2), t)
    t = _NU_OH.sub('ν ', t)
    t = re.sub(r'ν\s+(?=[1-4]\b)', 'ν', t)
    return re.sub(r'[ \t]+', ' ', t)


def _dots(t):
    """'O⋅⋅⋅O', 'O. . .O', 'O…O' -> 'O···O' — only between two atom labels, so an ellipsis in prose stays."""
    return re.sub(r'(?<=[A-Za-z\d)])' + r'(?:' + _DOTS.pattern + r')' + r'(?=\s?[A-Z(])', '···', t)


def sentences(t):
    """The sentences of a text. 'Fig. 3', 'et al.' and a decimal point do not end one."""
    s = _ABBR.sub(lambda m: m.group(1) + '\x00', t)
    parts = re.split(r'(?:(?<=[.!?])|(?<=[.!?]\)))\s+(?=[A-Z(\[νυ~∼])', s)
    return [p.replace('\x00', '.') for p in parts if p.strip()]


def split(text):
    """(the sentences as the paper prints them, the same sentences normalised) — the readers work on the second,
    and a finding quotes the first, so that its words can be found again in the document."""
    raw = sentences(body_of(text or ''))
    return raw, [normalise(x) for x in raw]


def body_of(t):
    """The text before the reference list (its entries name the relations' authors and state nothing)."""
    cut = -1
    for m in re.finditer(r'\b(?:References|REFERENCES|Literature cited|LITERATURE CITED|References cited|REFERENCES CITED)\b', t):
        if m.start() > len(t) * 0.5:
            cut = m.start(); break
    return t[:cut] if cut > 0 else t


# ----------------------------------------------------------------------------- bands

Band = namedtuple('Band', 'pos technique shape family mode sentence own')
#   pos: cm⁻¹;  technique: 'raman' | 'ir' | None;  shape: the words beside it ('sh', 'vs', 'broad' …);
#   family: 'UO2', 'SO4', 'OH', 'H2O', 'M-O' (a metal–oxygen bond), 'lattice', 'overtone' … or None;
#   mode: 1–4, 'stretch', 'bend', 'lib' or None;  own: False where the sentence gives another work's values
#   (a free ion's, a calculation's, the literature's)

_NUM = r'(?:[~∼≈]\s?|ca\.?\s?)?(\d{3,4}(?:\.\d)?)'
_PAREN = r'(?:\s?\(\s?([A-Za-z][A-Za-z ,.\-]{0,14})\))?'
_SEP = r'\s?(?:,\s?and|,|and|&|/|or|;)\s?'
_LIST_END = re.compile(r'((?:' + _NUM + _PAREN + _SEP + r')*' + _NUM + _PAREN + r')\s?$')
_RANGE_END = re.compile(r'(\d{3,4})\s?(?:-|to|and)\s?[~∼≈]?\s?(\d{3,4})\s?$')
_SHAPE = re.compile(r'\b(very strong|very weak|strong|weak|medium|broad|sharp|shoulder|intense|prominent|vs|vw|sh|br)\b', re.I)

_FAMILY = [                                                    # (family, how the text names it: formulas as written, words in any case)
    ('UO2', r'\(?\s?UO2\s?\)?(?:\s?2?\s?\+\s?2?)?|(?i:uranyl)'),
    ('SO4', r'\(?\s?SO4\s?\)?(?:\s?2?\s?-)?|(?i:sulfate|sulphate)|\s?\bSO\s?[2-4]?\s?-\s?4\b'),
    ('PO4', r'\(?\s?PO4\s?\)?(?:\s?3?\s?-)?|(?i:phosphate)|\s?\bPO\s?[2-4]?\s?-\s?4\b'),
    ('AsO4', r'\(?\s?AsO4\s?\)?(?:\s?3?\s?-)?|(?i:arsenate)|\s?\bAsO\s?[2-4]?\s?-\s?4\b'),
    ('VO4', r'\(?\s?VO4\s?\)?(?:\s?3?\s?-)?|(?i:vanadate)|\s?\bVO\s?[2-4]?\s?-\s?4\b'),
    ('CO3', r'\(?\s?CO3\s?\)?(?:\s?2?\s?-)?|(?i:carbonate)|\s?\bCO\s?[2-4]?\s?-\s?3\b'),
    ('SiO4', r'\(?\s?Si\d?O(?:4|3|7|10|11)\s?\)?(?:\s?\d?\s?-)?|(?i:\bsilicate)'),   # SiO3, Si2O7, Si4O10: silicate units (their ranges differ: the library's matter)
    ('BO3', r'\(?\s?BO3\s?\)?(?:\s?3?\s?-)?'),
    ('BO4', r'\(?\s?BO4\s?\)?(?:\s?5?\s?-)?'),
    ('MoO4', r'\(?\s?MoO4\s?\)?(?:\s?2?\s?-)?|(?i:molybdate)|\s?\bMoO\s?[2-4]?\s?-\s?4\b'),
    ('WO4', r'\(?\s?WO4\s?\)?(?:\s?2?\s?-)?|(?i:tungstate)|\s?\bWO\s?[2-4]?\s?-\s?4\b'),
    ('CrO4', r'\(?\s?CrO4\s?\)?(?:\s?2?\s?-)?|(?i:chromate)|\s?\bCrO\s?[2-4]?\s?-\s?4\b'),
    ('SeO3', r'\(?\s?SeO3\s?\)?(?:\s?2?\s?-)?|(?i:selenite)|\s?\bSeO\s?[2-4]?\s?-\s?3\b'),
    ('SeO4', r'\(?\s?SeO4\s?\)?(?:\s?2?\s?-)?|(?i:selenate)|\s?\bSeO\s?[2-4]?\s?-\s?4\b'),
    ('TeO3', r'\(?\s?TeO3\s?\)?(?:\s?2?\s?-)?|(?i:tellurite)'),
    ('NO3', r'\(?\s?NO3\s?\)?(?:\s?-)?|(?i:nitrate)|\s?\bNO\s?[2-4]?\s?-\s?3\b'),
    ('NH4', r'\(?\s?NH4\s?\)?(?:\s?\+)?|(?i:ammonium)|\bN-H\b'),
    ('H2O', r'\bH-O-H\b|H2O|(?i:\bwater\b)'),
    ('CH', r'\bC-H\b|(?i:\borganic)'),
    # a bond named by its atoms — 'Fe-O stretching', 'δ U-OH', 'As-O-H', 'O-P-O bending', 'Si-O-Si': an assignment of its
    # own, and what keeps its bands from the O-H or the group named next to it
    ('M-O', r'\b(?:O\s?-\s?)?[A-Z][a-z]?\d?\+?\s?-\s?(?:\(\s?O\s?,\s?OH\s?\)|O(?:\s?[,/]\s?OH\b)?(?:H|eq|ligand|yl|Ur)?)(?:\s?-\s?[A-Z][a-z]?)?\b|\bU-?OH\b'),   # 'M-O,OH', 'M-(O,OH)': one bond
    ('OH', r'(?<![A-Za-z\d-])O-H\b|\(OH\)|(?<![A-Za-z\d-])OH\b|(?i:hydroxyl)'),
    # an oxyanion or polyhedron the list does not name (VO5, WO6, TiO6, CO2 …): a group of its own, so that its mode is never
    # handed to the group named before it ('the uranyl ν1 … the band at 723 belongs to ν2 of VO5' had read as uranyl ν2);
    # the library holds no range for it, so nothing is judged on it
    ('other', r'\(?\s?\b[A-Z][a-z]?O[2-7]\b\s?\)?(?:\s?\d?\s?[-+])?(?:\s?(?:polyhedr|octahedr|tetrahedr|pyramid|group|unit|molecule)\w*)?'),
    ('lattice', r'(?i:lattice|external (?:mode|vibration)|phonon|translation|rotational)'),
    ('overtone', r'(?i:overtones?|combination (?:band|mode|tone)s?)'),
]
_BOND_KINDS = ('M-O', 'CH', 'lattice', 'overtone')            # not polyatomic groups: a numbered mode ν1–ν4 is never theirs
_FIXED_MODE = {'lattice': 'lattice', 'overtone': 'overtone'}
_FOREIGN = re.compile(r'\bin T\s?d symmetry|\bexhibits? (?:four|the) fundamental(?=[^.]*\b(?:free|T\s?d|isolated|undistorted)\b)|\bfundamental (?:vibrational )?modes\b(?! of (?:the )?(?:mineral|sample|studied))|\bfree\b|\b(?:have|has|had|were|was) been reported\b|\breported (?:for|by|in)\b|literature|theoretical|\bDFT\b|\bcomput|replicated|\bsimulat', re.I)
_FAM_RE = re.compile('|'.join('(?P<f%d>%s)' % (k, pat) for k, (_f, pat) in enumerate(_FAMILY)))
_MODE_NUM = re.compile(r'ν([1-4])')
_ANTI = re.compile(r'anti-?\s?symmetric|asymmetric', re.I)
_Q_WORD = r'(?:(?<![a-z-])symmetric|anti-?\s?symmetric|asymmetric)'
_JOINT_Q = _Q_WORD + r'\s?(?:,\s?)?(?:and|or|/)\s?(?:the\s)?' + _Q_WORD
_SYM = re.compile(r'(?<![a-z-])symmetric', re.I)


def _technique(s):
    r = bool(re.search(r'\bRaman\b', s)); i = bool(re.search(r'\binfrared\b|\bFTIR\b|\bIR\b|\bFT-IR\b|\babsorption band', s, re.I))
    return 'raman' if r and not i else 'ir' if i and not r else None


_MODE_WORD = re.compile(r'(librat)|(stretch)|(bend|deform|scissor|wag|rock|twist)', re.I)


def _family_hits(clause):
    """[(start, end, family)] — each group named in a clause; two names of one group side by side are one."""
    out = []
    for m in _FAM_RE.finditer(clause):
        fam = _FAMILY[int(m.lastgroup[1:])][0]
        if not m.group(0).strip():
            continue
        if out and out[-1][2] == fam and m.start() - out[-1][1] < 30 and not _MODE_WORD.search(clause[out[-1][1]: m.start()]) \
                and not re.search(r'\band\b|,', clause[out[-1][1]: m.start()]):
            out[-1] = (out[-1][0], m.end(), fam); continue
        out.append((m.start(), m.end(), fam))
    return out


def _word_mode(sent, s0, e0, lo, hi, water=False):
    """The mode the words beside a group name: the nearest of 'stretching' / 'bending' / 'libration' within the
    text up to the neighbouring groups (lo … hi), 'X stretching vibrations of GROUP' or 'GROUP stretching'."""
    best = None
    inside = _MODE_WORD.search(sent, s0, e0)
    if inside:
        best = (0, inside)
    for m in _MODE_WORD.finditer(sent, max(lo, s0 - 60), s0):
        if best and best[0] == 0:
            break
        if ';' in sent[m.end(): s0] or re.search(r'\d{3}|cm-1', sent[m.end(): s0]):
            continue                                             # never across a ';' or a band — '… H2O stretching vibrations; 1385 cm-1 to CO2 Fermi resonance'
        best = (s0 - m.end(), m)
    for m in _MODE_WORD.finditer(sent, e0, min(hi, e0 + 55)):
        if re.search(r'\bor\b|;|\d{3}|cm-1', sent[e0: m.start()]):
            break                                                # 'libration of H2O or WO5 bending': the bending is the other's; nor across a band
        if best is None or m.start() - e0 < best[0]:
            best = (m.start() - e0, m)
        break
    if not best:
        return None
    m = best[1]
    if m.group(1):
        return 'lib'
    if m.group(3):
        if water and re.match(r'rock|wag|twist', m.group(3), re.I):
            return 'lib'                                         # a water molecule's rocking / wagging / twisting is a libration
        return 'bend'
    pre = sent[max(lo, m.start() - 22): m.start()]
    # 'the symmetric and antisymmetric stretching modes', 'antisymmetric and symmetric SO4 stretching', 'symmetric and
    # antisymmetric (SO4) stretching': both, neither number
    if re.search(_JOINT_Q + r'\s?(?:\(?\s?[A-Z][A-Za-z\d]{0,8}\s?[\d+−-]*\s?\)?\s?)?$', sent[max(0, m.start() - 60): m.start()], re.I):
        return 'stretch'
    return 3 if _ANTI.search(pre) else 1 if _SYM.search(pre) else 'stretch'


def _assignments(sent):
    """[(start, end, family, mode)] — what a sentence assigns bands to, in the order it names them: a numbered
    mode with the group it belongs to, else a group with the words beside it (stretching, bending …)."""
    fams = _family_hits(sent)
    out = []; used = set()
    poly = [f for f in fams if f[2] not in _BOND_KINDS]
    for m in _MODE_NUM.finditer(sent):
        after = [f for f in poly if 0 <= f[0] - m.end() <= 90]
        before = [f for f in poly if 0 <= m.start() - f[1] <= 40]
        hit = after[0] if after else before[-1] if before else None
        fam = hit[2] if hit else (poly[0][2] if len({f[2] for f in poly}) == 1 else None)
        if hit:
            used.add(hit)
        if fam == 'OH':                                          # 'ν1 … of the hydroxyl' is no numbered mode of a polyatomic group
            fam = None
        if fam:
            out.append((m.start(), max(m.end(), hit[1]) if after else m.end(), fam, int(m.group(1))))
    for n, f in enumerate(fams):
        if f in used:
            continue
        s0, e0, fam = f
        if fam in _FIXED_MODE:
            out.append((s0, e0, fam, _FIXED_MODE[fam])); continue
        lo = fams[n - 1][1] if n else 0
        hi = fams[n + 1][0] if n + 1 < len(fams) else len(sent)
        mode = _word_mode(sent, s0, e0, lo, hi, water=fam in ('H2O', 'OH'))
        if fam == 'M-O':
            # a bond is an assignment only with its mode right beside it ('Fe-O stretching', 'stretching vibrations of
            # Si-O', 'ν(Mo-O)', 'δ U-OH') — 'U-O bond lengths' names a distance
            tight = re.match(r'\s?\)?\s?(?:symmetric |antisymmetric |asymmetric )?(?:stretch|bend|deform|vibration|mode)', sent[e0: e0 + 30], re.I) or \
                re.search(r'(?:[νδ]\s?\(?\s?|(?:stretch|bend|deform)\w*(?: vibrations?| modes?)? of (?:the )?)$', sent[max(0, s0 - 40): s0], re.I)
            if not tight or re.match(r'\s?\(?[a-z]*\)?\s?(?:bond|distance|length)', sent[e0: e0 + 22]):
                continue
            mode = mode or ('bend' if re.search(r'δ\s?\(?\s?$', sent[max(0, s0 - 4): s0]) else 'stretch')
        if fam in ('OH', 'H2O', 'NH4', 'CH', 'M-O') and mode in (1, 3):
            mode = 'stretch'
        if not mode and n and fams[n - 1][2] not in _BOND_KINDS and fam not in _BOND_KINDS and \
                re.fullmatch(r'\s?(?:,|and|,\s?and|or)\s?', sent[fams[n - 1][1]: s0]) and out and out[-1][:2] == fams[n - 1][:2]:
            mode = out[-1][3]                                    # 'the symmetric stretching modes of PO43- and CO32-': both stretch
        if mode and re.search(r'overtone|combination', sent[max(lo, s0 - 45): s0], re.I):
            fam, mode = 'overtone', 'overtone'                   # 'the overtone of H-O-H bending vibrations'
        if mode:
            out.append((s0, e0, fam, mode))
    # two modes of one group named in a row, 'respectively' after them: two assignments, in that order — one had stood for
    # both bands ('3552 and 1631 cm-1 … the stretching vibration and bending vibration of H2O, respectively' read both as bends)
    if re.search(r'respectively', sent):
        pair = re.compile(r'\b((?:anti-?\s?symmetric|asymmetric|symmetric)\s)?(stretching|bending)(?: vibrations?| modes?)?\s?(?:,\s?)?and\s(?:the\s)?'
                          r'((?:anti-?\s?symmetric|asymmetric|symmetric)\s)?(stretching|bending)(?: vibrations?| modes?)?', re.I)
        for pm in pair.finditer(sent):
            after_ = [f for f in fams if 0 <= f[0] - pm.end() <= 70 and f[2] not in _BOND_KINDS]
            before_ = [f for f in fams if 0 <= pm.start() - f[1] <= 25 and f[2] not in _BOND_KINDS]
            grp = (after_[0] if after_ else before_[-1] if before_ else None)
            if grp is None:
                continue
            def md(qual, word):
                if word.lower().startswith('bend'):
                    return 'bend'
                if grp[2] in ('OH', 'H2O', 'NH4', 'CH') or not qual:
                    return 'stretch'
                return 3 if _ANTI.search(qual) else 1
            a1 = (pm.start(), pm.start(4) - 1, grp[2], md(pm.group(1), pm.group(2)))
            a2 = (pm.start(4) - (len(pm.group(3)) if pm.group(3) else 0), max(pm.end(), grp[1]), grp[2], md(pm.group(3), pm.group(4)))
            if a1[3] == a2[3]:
                continue
            out = [a for a in out if not (a[2] == grp[2] and a[0] <= grp[1] and a[1] >= pm.start())] + [a1, a2]
        # the qualifiers coordinated: 'the symmetric and antisymmetric stretching modes, respectively, within the SeO4 groups'
        for pm in re.finditer(r'\b(symmetric|anti-?\s?symmetric|asymmetric)\s(?:,\s?)?and\s(?:the\s)?(symmetric|anti-?\s?symmetric|asymmetric)\s'
                              r'(?:\(?\s?[A-Z][A-Za-z\d]{0,8}\s?[\d+−-]*\s?\)?\s)?(stretching|stretch)\b', sent, re.I) if re.search(r'respectively', sent) else ():
            after_ = [f for f in fams if 0 <= f[0] - pm.end() <= 70 and f[2] not in _BOND_KINDS]
            before_ = [f for f in fams if 0 <= pm.start() - f[1] <= 25 and f[2] not in _BOND_KINDS]
            grp = (after_[0] if after_ else before_[-1] if before_ else None)
            if grp is None or grp[2] in ('OH', 'H2O', 'NH4', 'CH'):
                continue
            m1 = 3 if _ANTI.search(pm.group(1)) else 1; m2 = 3 if _ANTI.search(pm.group(2)) else 1
            if m1 == m2:
                continue
            a1 = (pm.start(1), pm.end(1), grp[2], m1); a2 = (pm.start(2), max(pm.end(), grp[1]), grp[2], m2)
            out = [a for a in out if not (a[2] == grp[2] and a[0] <= grp[1] and a[1] >= pm.start())] + [a1, a2]
    # 'As5+-O stretching vibrations of AsO43- groups': the bond of a polyanion's own central atom IS that polyanion's mode
    for n in range(len(out) - 1, 0, -1):
        a, b = out[n - 1], out[n]
        if a[2] == 'M-O' and b[2] in GROUP_ELEMENT and b[0] - a[1] < 50 and re.search(r'\bof\b', sent[a[1]: b[0]]):
            atom = re.match(r'\s?(?:O\s?-\s?)?([A-Z][a-z]?)', sent[a[0]: a[1]])
            if atom and atom.group(1) == GROUP_ELEMENT[b[2]]:
                out[n - 1] = (a[0], b[1], b[2], b[3] if b[3] not in (None, 'stretch', 'bend') or a[3] is None else a[3]); del out[n]
    # 'ν O-H stretching vibrations of the H2O molecules': the water named after an O-H stretch is that stretch's
    for n in range(len(out) - 1, 0, -1):
        a, b = out[n - 1], out[n]
        if a[2:] == ('OH', 'stretch') and b[2] == 'H2O' and b[3] == 'stretch' and b[0] - a[1] < 60:
            out[n - 1] = (a[0], b[1], 'OH', 'stretch'); del out[n]
    out.sort()
    uniq = []
    same_kind = lambda m1, m2: {m1, m2} <= {2, 4, 'bend'} or {m1, m2} <= {1, 3, 'stretch'}
    for a in out:                                                # 'O–H stretching vibrations of hydroxyl groups' names one thing twice
        if uniq and uniq[-1][2:] == a[2:] and a[0] - uniq[-1][1] < 80 and not re.search(r'\d{3}|cm-1', sent[uniq[-1][1]: a[0]]):
            uniq[-1] = (uniq[-1][0], max(uniq[-1][1], a[1])) + a[2:]   # never across a band: two of them, each its own
            continue
        if uniq and uniq[-1][2] == a[2] and a[0] - uniq[-1][1] < 60 and isinstance(uniq[-1][3], int) != isinstance(a[3], int) \
                and same_kind(uniq[-1][3], a[3]) and not re.search(r'\d{3}|cm-1', sent[min(uniq[-1][1], a[0]): max(uniq[-1][1], a[0])]) \
                and not re.search(r'\d{3}|cm-1', sent[uniq[-1][0]: a[0]]):
            num = uniq[-1][3] if isinstance(uniq[-1][3], int) else a[3]   # 'the ν2 H-O-H bending vibration of water': one assignment, the numbered one
            uniq[-1] = (uniq[-1][0], max(uniq[-1][1], a[1]), a[2], num)
            continue
        uniq.append(a)
    return uniq


_AT = re.compile(r'\b(?:bands?|shoulders?|peaks?|maxim(?:a|um)|components?|lines?|features?)\b[^.;:]{0,40}?\b(?:at|near|around)\s((?:' + _NUM + _PAREN + _SEP + r')*' + _NUM + _PAREN + r')'
                 r'(?!\s?cm-1)(?!\s?(?:Å|nm|°|K\b|%|GPa|eV|kV|mA|μm|mm|\d))', re.I)


def _band_groups(s):
    """[(start, end, [(pos, shape)], is_range)] — each run of numbers that a 'cm-1' closes, and a run that
    follows 'bands at' with the unit left to the next one ('bands at 917 and 870 (IR) correspond …')."""
    out = []
    for m in re.finditer(r' ?cm-1', s):
        head = s[max(0, m.start() - 200): m.start()]
        off = max(0, m.start() - 200)
        lm = _LIST_END.search(head)
        if not lm:
            continue
        txt = lm.group(1)
        items = [(float(a), (b or '').strip().lower()) for a, b in re.findall(_NUM + _PAREN, txt)]
        items = [(p, sh) for p, sh in items if 30 <= p <= 4500]
        if not items:
            continue
        start = off + lm.start(1)
        rng = False
        rm = _RANGE_END.search(head)
        if rm and len(items) <= 2:
            joiner = head[rm.start() + len(rm.group(1)): rm.end()]
            if '-' in joiner or ' to ' in joiner or re.search(r'\bbetween\s?[~∼≈]?\s?$', s[max(0, off + rm.start() - 12): off + rm.start()]):
                rng = True; start = off + rm.start()
                items = [(float(rm.group(1)), ''), (float(rm.group(2)), '')]
        elif len(items) == 1:
            pre = s[max(0, start - 30): start]
            pm = re.search(r'(\d{3,4})\s?(?:-|to)\s?[~∼≈]?\s?$', pre)
            if pm:                                               # '3200-2700 cm-1' split by the list walk
                rng = True; items = [(float(pm.group(1)), ''), items[0]]; start = max(0, start - 30) + pm.start()
        if re.search(r'[<>≤≥]\s?[~∼≈]?\s?$', s[max(0, start - 3): start]) or \
                re.search(r'\b(?:above|below|beyond|over|under|up to|down to|(?:higher|lower|greater|less) than)\s?[~∼≈]?\s?$', s[max(0, start - 14): start], re.I):
            rng = True                                           # '<400 cm-1', 'above 1700 cm-1': a region, not a band
        out.append((start, m.end(), items, rng))
    for m in _AT.finditer(s):
        if any(g[0] <= m.start(1) < g[1] for g in out):
            continue
        items = [(float(a), (b or '').strip().lower()) for a, b in re.findall(_NUM + _PAREN, m.group(1))]
        items = [(p, sh) for p, sh in items if 30 <= p <= 4500]
        if items and not re.match(r'\s?(?:-|to\b)', s[m.end(1): m.end(1) + 4]):
            out.append((m.start(1), m.end(1), items, False))
    out.sort()
    k = 0
    while k < len(out) - 1:
        a, b = out[k], out[k + 1]
        if len(a[2]) == 1 and len(b[2]) == 1 and re.fullmatch(r'\s?(?:-|to)\s?[~∼≈]?\s?', s[a[1]: b[0]]):
            # '1200 cm-1 - 600 cm-1': ONE range of two ends, as '1200-600 cm-1' is (band_ranges / absent_bands read a range as
            # a group of two; two one-band ranges were read by nothing)
            out[k] = (a[0], b[1], [a[2][0], b[2][0]], True); del out[k + 1]
        k += 1
    return out


# between a band and the assignment that follows it / between an assignment and the band that follows it
_VERB = re.compile(r'assign|attribut|relat|due to|ascrib|connect|correspond|belong|associat|caus|aris|link|interpret|represent|originat|result|characteristic|typical|indicat|reflect|'
                   r'\bis the\b|\bare the\b|\bto\b|:', re.I)
_LOC = re.compile(r'\bat\b|\bas\b|near|around|centred|centered|band|peak|observed|occur|present|appear|found|located|lies|shoulder|maxim|\bis\b|\bare\b', re.I)


def _pair(sent, groups, asg):
    """{group index: [assignment per band]} — a run of bands takes the assignments that FOLLOW it when the
    words between say so ('… cm-1 are assigned to …'), else the ones BEFORE it ('The ν1 … occurs as a band
    at …'); a run of assignments is shared in order, or by all when it is one."""
    toks = sorted([('G', g[0], g[1], k) for k, g in enumerate(groups)] + [('A', a[0], a[1], k) for k, a in enumerate(asg)], key=lambda x: (x[1], x[0]))
    runs = []
    for tk in toks:
        if runs and runs[-1][0] == tk[0] and (tk[0] == 'A' or (tk[1] - runs[-1][1][-1][2] <= 80 and ';' not in sent[runs[-1][1][-1][2]: tk[1]])):
            runs[-1][1].append(tk)
        else:
            runs.append((tk[0], [tk]))
    out = {}; taken = set(); used_front = {}
    for i, (kind, items) in enumerate(runs):
        if kind != 'G':
            continue
        nxt = runs[i + 1][1] if i + 1 < len(runs) else None
        prv = runs[i - 1][1] if i > 0 else None
        arun = None
        if prv and runs[i - 1][0] == 'A' and (i - 1) not in taken:
            between = sent[prv[-1][2]: items[0][1]]
            if len(between) < 70 and (re.search(r'\b(?:at|near|around)\s?[~∼≈]?\s?$', between) or len(between.strip()) <= 3) \
                    and not re.search(r'[;,]\s|\b(?:and|while|whereas|those|ones|that|but)\b', between):
                arun = prv
        if arun is None and nxt and runs[i + 1][0] == 'A':
            between = sent[items[-1][2]: nxt[0][1]]
            own_band = any(h[0] >= nxt[0][1] and h[0] <= nxt[-1][2] + 40 and h is not groups[items[-1][3]] and
                           re.search(r'\b(?:at|near|around)\s?[~∼≈]?\s?$', sent[nxt[0][1]: h[0]]) and
                           not re.search(r'[.;)]|,\s', sent[min(nxt[-1][2], h[0]): h[0]]) and          # '… mode), a band at 441': closed before it
                           not re.search(r'\bof (?:the |a )?(?:bands?|peaks?|lines?)\b', sent[nxt[0][1]: h[0]])   # 'an overtone of the band at 294': a reference
                           for h in groups)
            if len(between) < 170 and (_VERB.search(between) or (len(between.strip()) < 25 and not own_band)) and not re.search(r'[.;]\s', between):
                arun = nxt                                       # taken only once it is USED (below): a run that cannot use it leaves it to the next
                # (an assignment followed by its own band — 'PO4 ν1 stretching mode at 988' — is that band's, not the one before it)
        if arun is None and prv and runs[i - 1][0] == 'A' and (i - 1) not in taken:
            between = sent[prv[-1][2]: items[0][1]]
            if len(between) < 130 and _LOC.search(between) and not re.search(r';\s', between):
                arun = prv
        if arun is None:
            continue
        A = [asg[a[3]] for a in arun]
        if arun is prv:
            A = A[used_front.get(i - 1, 0):]                     # what the run of bands before it has not taken
        def _gap(x, y):                                          # the words between two assignments; 'ν1 and ν3 modes of SO4': both spans
            if x[1] <= y[0]:                                     # run on to the SO4, so the text between their starts, less the mode token
                return sent[x[1]: y[0]]
            return re.sub(r'^\s?ν\s?[1-4]', '', sent[x[0]: y[0]])
        if len(A) > 1 and not re.search(r'respectively', sent) and any(
                re.fullmatch(r'\s?(?:,|and|,\s?and|or|&)\s?', _gap(x, y)) for x, y in zip(A, A[1:])):
            continue                                             # 'the stretching modes of both H2O and NH4+ … maxima at 3020 and 3540': jointly, not one each
        if len(A) > 1 and len(items) > 1:
            rp = next((m.start() for m in re.finditer(r'respectively', sent) if m.start() > items[0][2]), None)
            if rp is not None and any(g[2] <= rp for g in items) and any(g[1] > rp for g in items):
                items = [g for g in items if g[2] <= rp]
        if arun is nxt and len(A) == len(items) + 1 and i + 2 < len(runs):
            # '… band at 808 is attributed to ν1 of UO2, overlapping the stretching vibrations of SiO4 at 750': the last
            # assignment of the run belongs to the band that follows it
            between = sent[arun[-1][2]: runs[i + 2][1][0][1]]
            if runs[i + 2][0] == 'G' and len(between) < 60 and re.search(r'\bat\b|near|around', between) and not re.search(r'[.;]\s', between):
                A = A[:-1]; taken.discard(i + 1); used_front[i + 1] = len(A)
        done = True
        if len(A) == 1:
            for g in items:
                out[g[3]] = [A[0]] * len(groups[g[3]][2])
        elif len(A) == len(items):
            for g, a in zip(items, A):
                out[g[3]] = [a] * len(groups[g[3]][2])
        elif len(items) == 1 and len(groups[items[0][3]][2]) == len(A) and re.search(r'respectively', sent):
            out[items[0][3]] = list(A)
        elif len(items) > len(A) and re.search(r'respectively', sent):
            # '… ~3200 cm-1 and a sharp peak at 1638 cm-1 (with a shoulder at 1610 cm-1) are due to H2O stretches and H-O-H
            # bends, respectively': a band in parentheses is the shoulder of the band before it, and shares its assignment
            heads = [g for g in items if not re.search(r'\((?:[^()]{0,30})$', sent[max(0, g[1] - 200): g[1]])]
            if len(heads) == len(A):
                cur = None; hi = iter(A)
                for g in items:
                    if g in heads:
                        cur = next(hi)
                    if cur is not None:
                        out[g[3]] = [cur] * len(groups[g[3]][2])
            else:
                done = False
        else:
            done = False
        if done and arun is nxt and (i + 1) not in used_front:   # a run whose last assignment was left to the band after it stays open
            taken.add(i + 1)
    # a band in parentheses belongs to the assignment its words stand in, whatever the runs said: inside the assignment's own
    # words ('H-O-H bending (at 1675 cm-1) vibrations of H2O and C-O stretching …' had gone to the carbonate), a numbered
    # mode inside the same parentheses ('(at 964 cm-1, non-degenerate A1(ν1) mode …)'), or right after the assignment it
    # completes ('ν2 CO32- out-of-plane bending (about 880 cm-1) and ν4 …' had gone to ν4)
    resp = {}                                                    # '… ν3, ν1 and ν4 modes of PO43- (at 1072 and 1001 cm-1 and in the range of 500-600 cm-1, respectively)'
    for m in re.finditer(r'\(([^()]*(?:\([^()]*\)[^()]*)*)\)', sent):
        if not re.search(r'respectively\s?$', m.group(1)):
            continue
        inner = [k for k, g in enumerate(groups) if m.start() < g[0] and g[1] <= m.end()]
        lead = [a for a in asg if a[1] <= m.start()]
        chain = []
        for a in reversed(lead):                                 # the list of assignments the parenthesis completes
            if chain and not (chain[0][0] - a[0] < 90 and re.search(r',|\band\b', sent[a[0]: chain[0][0]]) and ';' not in sent[a[0]: chain[0][0]]):
                break                                            # spans of numbered modes overlap (each runs on to its group): by their starts
            if not chain and not re.fullmatch(r'[\w\s\-]{0,40}', sent[a[1]: m.start()]):
                break
            chain.insert(0, a)
        slots = [(k, n) for k in inner for n in range(1 if groups[k][3] else len(groups[k][2]))]
        if len(chain) > 1 and len(slots) == len(chain):
            for (k, n), a in zip(slots, chain):
                resp.setdefault(k, []).append(a)
    for k, v in resp.items():
        if not groups[k][3]:
            out[k] = v
    for k, g in enumerate(groups):
        if g[3] or k in resp:
            continue
        a_ = None
        op = sent.rfind('(', 0, g[0])
        in_paren = op >= 0 and ')' not in sent[op: g[0]]
        # inside an assignment's own words — and in parentheses there ('H-O-H bending (at 1675 cm-1) vibrations of H2O'): a
        # numbered mode's span runs on to the group after it, and a band in that stretch of prose is not in its words
        inside = [a for a in asg if a[0] <= op and g[1] <= a[1]] if in_paren else []
        if inside:
            a_ = min(inside, key=lambda a: a[1] - a[0])
        if a_ is None and in_paren:
            cl = sent.find(')', g[1])
            cl = len(sent) if cl < 0 else cl
            numbered = [a for a in asg if g[1] < a[0] < cl and isinstance(a[3], int)
                        and not any(a[0] < h[0] < cl for h in groups)]   # '(ν1 ≈980 cm-1, ν2 ≈450 …)': a mode with its own band after it is that band's
            if numbered:
                a_ = numbered[0]
            else:
                before = [a for a in asg if a[1] <= op and re.fullmatch(r'[\w ,\-]{0,30}', sent[a[1]: op])]
                lead = sent[op + 1: g[0]]                        # '(at ', '(about ', '(a broad band centred on '
                if before and len(lead) <= 40 and not re.search(r'\d', lead) and not _FAM_RE.search(lead) and not _VERB.search(lead) \
                        and re.fullmatch(r"[\w\s\-]*?(?:\b(?:at|on|about|ca\.?|near|around))?\s?[~∼≈]?\s?", lead):
                    a_ = before[-1]
        if a_ is not None:
            out[k] = [a_] * len(g[2])
    return out


_TECH = re.compile(r'\b(Raman)\b|\b(infrared|FTIR|FT-IR|IR)\b')


def _tech_for(sent, g):
    """The technique of one run of bands: the '(IR)' / '(Raman)' right after it, else the last one named before it."""
    m = re.match(r'\s?\(\s?(Raman|IR|infrared|FTIR)\s?\)', sent[g[1]: g[1] + 14])
    if not m:
        m = re.search(r'\(\s?(Raman|IR|infrared|FTIR)\s?\)\s?$', sent[g[0]: g[1]].replace(' cm-1', ''))   # '870 (IR) cm-1'
    if m:
        return 'raman' if m.group(1) == 'Raman' else 'ir'
    last = None
    for last in _TECH.finditer(sent[:g[0]]):
        pass
    return ('raman' if last.group(1) else 'ir') if last else None


_SHAPE_CODE = ('sh', 'vs', 'vw', 's', 'm', 'w', 'br', 'vvw', 'm-s', 's-vs', 'w-m', 'vbr', 'b')

# 'no absorption band at ca. 1650 cm-1', 'the H-O-H bend near 1600 cm-1 is absent', 'the absence of bands at …': the
# sentence states that the spectrum has NO band there. Read within the clause the numbers stand in.
_CLAUSE = re.compile(r';|,\s(?:but|while|whereas|although|though)\b|\bbut\b|\bwhereas\b')
_NEG_BEFORE = re.compile(r'\b(?:no|absence of|lack(?:s|ing)? (?:of )?|lack of|without|devoid of|free of|neither)\b[^;]{0,90}$', re.I)
_NEG_AFTER = re.compile(r'^[^;]{0,70}?\b(?:(?:is|are|was|were|being)\s+(?:completely\s+|entirely\s+)?(?:absent|missing|lacking)|(?:is|are|was|were)\s+not\s+(?:observed|present|detected|seen|found|visible|recorded|apparent)|'
                        r'(?:is|are|was|were)\s+absent|not\s+(?:observed|detected|present))\b', re.I)


def _negated(sent, g, groups=()):
    """A run of bands the sentence says the spectrum does NOT show — also when the negation follows the LAST run of a
    list in the same clause ('bands of ν2 (about 880 cm-1) and ν4 (about 680 cm-1) were not observed')."""
    lo = 0
    for m in _CLAUSE.finditer(sent, 0, g[0]):
        lo = m.end()
    m = _CLAUSE.search(sent, g[1])
    hi = m.start() if m else len(sent)
    if _NEG_BEFORE.search(sent[lo: g[0]]) or _NEG_AFTER.search(sent[g[1]: hi]):
        return True
    later = [h for h in groups if g[1] <= h[0] < hi and not h[3]]
    if not later:
        return False
    # a LIST negated: a plural verb right after its last band ('… (about 680 cm-1) vibrations were not observed'), never a
    # relative clause on that band alone ('… a shoulder at 843 cm-1 which is not present in …')
    tail = sent[later[-1][1]: hi]
    m = re.match(r'[^;,]{0,30}?\b(?:were|are)\s+(?:not\s+(?:observed|present|detected|seen|found|visible|recorded|apparent)|absent|missing)\b', tail, re.I)
    return bool(m and not re.search(r'\b(?:which|that|where)\b', tail[:m.end()]) and
                not re.search(r'\b(?:is|are|was|were|occurs?|appears?|observed at)\b|,\s?with\b', sent[g[1]: later[-1][0]]))


def _sentence_bands(sent, tech=None):
    """[Band] of one normalised sentence; `tech` is the technique the sentences before it left standing."""
    if 'cm-1' not in sent or _tabular(sent):
        return []
    groups = _band_groups(sent)
    if not any(not g[3] for g in groups):
        return []
    pairs = _pair(sent, groups, _assignments(sent))
    own = not _FOREIGN.search(sent)
    out = []
    for k, g in enumerate(groups):
        if g[3] or _negated(sent, g, groups):
            continue
        gt = _tech_for(sent, g) or tech
        near = _shape_near(sent, g[0])
        for n, (p, sh) in enumerate(g[2]):
            a = pairs[k][n] if k in pairs else None
            if sh not in _SHAPE_CODE and not (sh and _SHAPE.fullmatch(sh)):
                # the number's own parentheses name what it is (read in the sentence: the item's copy is lower-cased)
                pm = re.search(r'(?<![\d.])%s(?:\s?cm-1)?\s?\(\s?([A-Za-z][^()]{0,30})\)' % re.escape(('%g' % p)), sent[g[0]: g[1] + 40])
                own_a = _assignments(pm.group(1)) if pm else []
                if len(own_a) == 1:
                    a = own_a[0]
            out.append(Band(p, gt, sh if sh in _SHAPE_CODE else near, a[2] if a else None, a[3] if a else None, sent, own))
    return out


def _bands_of(sents):
    out = []; tech = None
    for sent in sents:
        st = _technique(sent)
        if st or re.search(r'\bRaman\b|\binfrared\b|\bIR\b|\bFTIR\b', sent):
            tech = st                                            # a sentence naming both leaves the technique open
        out += _sentence_bands(sent, tech)
    return out


def bands(text):
    """[Band] — every band position the prose states, with what its sentence assigns it to (family and mode
    None where it names none, or names several with no way to tell which is whose)."""
    return _bands_of(split(text)[1])


def absent_bands(text, _split=None):
    """[(low, high, sentence as printed)] — where the text states that its spectrum shows NO band ('no absorption band
    at ca. 1650 cm-1', 'no peaks in the region of 1500-1600 cm-1'): a position (low = high) or a range. Evidence of its
    own kind, kept apart from the bands the spectrum has."""
    raw, norm = _split or split(text)
    out = []
    for r, sent in zip(raw, norm):
        if 'cm-1' not in sent or _tabular(sent):
            continue
        for g in _band_groups(sent):
            if not _negated(sent, g):
                continue
            if g[3] and len(g[2]) == 2:
                out.append((min(g[2][0][0], g[2][1][0]), max(g[2][0][0], g[2][1][0]), r))
            elif not g[3]:
                out += [(p, p, r) for p, _sh in g[2]]
    return out


def _shape_near(clause, start):
    m = None
    for m in _SHAPE.finditer(clause[max(0, start - 45): start]):
        pass
    return m.group(1).lower() if m else ''


def band_ranges(text):
    """[(lo, hi, sentence)] — the wavenumber ranges the prose states ('a broad band from 3550 to 3100 cm-1')."""
    out = []
    for sent in split(text)[1]:
        for g in _band_groups(sent):
            if g[3] and len(g[2]) == 2:
                a, b = g[2][0][0], g[2][1][0]
                out.append((min(a, b), max(a, b), sent))
    return out


# ----------------------------------------------------------------------------- stated distances

Claim = namedtuple('Claim', 'relation dist text decimals band mode paired sentence')
#   relation: 'bc' | 'lib_oo' | 'lib_ho';  dist: Å;  text: the distance as printed;  band: cm⁻¹ or None;
#   mode: 1 | 3 | None (bc; set only where the SENTENCE names it beside the distance);  paired: how the
#   distance is tied to its band —
#     'band'    the wavenumber stands beside the distance ('1.75 Å (856 cm-1)')
#     'mode'    ν1 / ν3 named beside it ('1.76 Å (ν1)')
#     'list'    a list of bands and a list of distances in one sentence, in one order
#     'ctx'     the same, the bands in the sentence before
#     'single'  one band and one distance in the sentence
#     'range'   one end of a stated range of distances
#     ''        a distance, the band left to the reader

_BC_D = r'(?<![\d.])(1\.[6-9]\d{1,2})(?![\d(])'
_LIB_D = r'(?<![\d.])([23]\.\d{1,3})(?![\d(])'
_HO_D = r'(?<![\d.])([12]\.\d{1,3})(?![\d(])'
# where a sentence turns from what the relation gave to what it is compared with (the X-ray distances follow)
_TURN = re.compile(r'\b(?:in (?:excellent|good|reasonable|fair|perfect|close)? ?(?:agreement|accordance|line)|agree|comparable|consistent with (?:the|those|what|dist)|'
                   r'match|close to|compare|X-ray|structure (?:refinement|determination|data|analysis)|refined|observed (?:in|distance)|determined from|'
                   r'within the range|within \d|obtained from the|somewhat (?:higher|lower)|on par)', re.I)
_HO_FORM = re.compile(r'(?<![A-Za-z-])H\s?···\s?(?:O|A)|H···Acceptor|\bd\(H|H-bonds? \(H')
# between a distance and the band it is said to come from, the distance stated first
_FROM = re.compile(r'\b(?:from|based on|using|calculated|derived|obtained|estimated|inferred|deduced|for)\b', re.I)


def _dec(txt):
    return len(txt.split('.')[1]) if '.' in txt else 0


def _tabular(s):
    """A 'sentence' that is a table's rows run together (the text layer of a pdf has no table)."""
    toks = s.split()
    if len(s) > 1200:
        return True
    return len(toks) >= 40 and sum(1 for x in toks if re.match(r'^[-(]?\d[\d.,()]*$', x)) > 0.4 * len(toks)


def _cites(s, name):
    """The sentence credits the relation (a reference-list entry 'Libowitzky, E. (1999) …' does not)."""
    return bool(re.search(name, s)) and not re.search(name + r',? [A-Z]\.', s) and not _tabular(s)


def stated_distances(text):
    """[Claim] — each distance a sentence credits to Bartlett & Cooney or to Libowitzky."""
    sents = split(text)[1]
    out = []
    for k, s in enumerate(sents):
        if _cites(s, 'Bartlett'):
            out += _bc_claims(s, sents, k)
        if _cites(s, 'Libowitzky'):
            out += _lib_claims(s, sents, k)
    return out


def _uranyl_context(sents, k, back=6):
    """[(Band, sentences back)] — the uranyl ν1 / ν3 bands of the claim's sentence and of those before it,
    nearest first; the walk back stops at the first sentence that has some once the claim's own has none."""
    want = lambda b: b.family == 'UO2' and b.mode in (1, 3)
    got = [(b, 0) for b in _sentence_bands(sents[k]) if want(b)]
    own = bool(got)
    for j in range(k - 1, max(-1, k - 1 - back), -1):
        if _tabular(sents[j]):
            continue
        bs = [(b, k - j) for b in _sentence_bands(sents[j]) if want(b)]
        if bs:
            got += bs
            if len(got) >= 2 and not own:
                break
    return got


def _numbers_before(sents, k, lo, hi, back=3):
    """The band positions within lo–hi of the nearest earlier sentence that states any (ranges left out)."""
    for j in range(k - 1, max(-1, k - 1 - back), -1):
        if _tabular(sents[j]):
            continue
        nums = [p for g in _band_groups(sents[j]) if not g[3] for p, _sh in g[2] if lo <= p <= hi]
        if nums:
            return nums
    return []


def _bc_claims(s, sents, k):
    # the stated part: up to the first turn to a comparison that follows a distance
    cutp = len(s)
    for m in _TURN.finditer(s):
        if re.search(_BC_D, s[:m.start()]):
            cutp = m.start(); break
    head = s[:cutp]
    out = []; used = set()
    def add(dtxt, band=None, mode=None, paired='', span=None):
        if span in used:
            return
        used.add(span)
        out.append(Claim('bc', float(dtxt), dtxt, _dec(dtxt), band, mode, paired, s))
    # 'N cm-1 [ν3; 1.763]'
    for m in re.finditer(r'(\d{3,4}) cm-1 \[\s?ν([13])\s?[;,]\s?' + _BC_D + r'\s?\]', s):
        add(m.group(3), float(m.group(1)), int(m.group(2)), 'band', m.start(3))
    # '1.76 for ν3 (856 cm-1)'
    for m in re.finditer(_BC_D + r'\s?Å?\s?(?:for|from)\s?ν([13])\s?\(\s?(\d{3,4}) cm-1\s?\)', head):
        add(m.group(1), float(m.group(3)), int(m.group(2)), 'band', m.start(1))
    # '1.75 Å (856 cm-1)', '1.77 (from 917 cm-1)', '1.78 Å/904 cm-1'
    for m in re.finditer(_BC_D + r'\s?Å?\s?(?:\(\s?(?:from |based on |for |at )?|/\s?)(\d{3,4}) cm-1', head):
        add(m.group(1), float(m.group(2)), None, 'band', m.start(1))
    # '1.76 Å (ν1)', '1.82 Å (based on ν3)', '1.773 (ν3)'
    for m in re.finditer(_BC_D + r'\s?Å?\s?\(\s?(?:from |based on |for )?ν([13])\s?\)', head):
        add(m.group(1), None, int(m.group(2)), 'mode', m.start(1))
    rest = [m for m in re.finditer(_BC_D, head) if m.start(1) not in used]
    own = [b for b in _sentence_bands(s) if b.family == 'UO2' and b.mode in (1, 3)]
    if len(rest) == 1 and len(own) == 1 and not out:
        at = s.find('%g' % own[0].pos)
        # the one uranyl band of the sentence before the one distance ('the ν1 band at 830 cm-1 gives 1.78 Å'), or after it
        # when the words between say the distance comes from the band ('1.78 Å was calculated from the ν1 band at 830 cm-1')
        if at < rest[0].start(1) or (at > rest[0].end(1) and _FROM.search(head[rest[0].end(1): at])):
            add(rest[0].group(1), own[0].pos, None, 'single', rest[0].start(1))
            rest = []
    for m in rest:
        if re.search(r'(?:\d\s?Å?\s?-|\bto)\s?[~∼≈]?\s?$', head[max(0, m.start(1) - 6): m.start(1)]) or re.match(r'\s?Å?\s?(?:-\s?[~∼≈]?\s?1\.\d|to\b)', head[m.end(1): m.end(1) + 8]):
            add(m.group(1), None, None, 'range', m.start(1)); continue
        add(m.group(1), None, None, '', m.start(1))
    return out


def _lib_claims(s, sents, k):
    ho = bool(_HO_FORM.search(s))
    pat = _HO_D if ho else _LIB_D
    rel = 'lib_ho' if ho else 'lib_oo'
    cutp = len(s)
    for m in _TURN.finditer(s):
        if re.search(pat, s[:m.start()]):
            cutp = m.start(); break
    head = s[:cutp]
    lo, hi = (1.3, 2.6) if ho else (2.35, 3.45)
    ds = [m for m in re.finditer(pat, head) if lo <= float(m.group(1)) <= hi and not re.match(r'\s?(?:%|cm|wt|GPa|°|vu|v\.u)', head[m.end(1): m.end(1) + 5])
          and not re.search(r'[<>≤≥]\s?$', head[max(0, m.start(1) - 3): m.start(1)])]
    if not ds:
        return []
    def mk(m, band=None, paired=''):
        return Claim(rel, float(m.group(1)), m.group(1), _dec(m.group(1)), band, None, paired, s)
    # '~2.66 Å (3028 cm-1) and ~2.72 Å (3253 cm-1)'
    beside = {}
    for m in re.finditer(pat + r'\s?Å?\s?\(\s?(?:from |for |at )?(\d{4}) cm-1\s?\)', head):
        beside[m.start(1)] = float(m.group(2))
    if beside and len(beside) == len(ds):
        return [mk(m, beside[m.start(1)], 'band') for m in ds]
    if len(ds) == 2 and (re.search(r'(?:\d\s?Å?\s?-|\bto|\band)\s?[~∼≈>]?\s?$', head[max(0, ds[1].start(1) - 7): ds[1].start(1)])
                         and re.search(r'\brang|between|\bvary|\bvaries|from\s?[~∼≈>]?\s?\d\.\d|\d\s?Å?\s?-\s?[~∼≈>]?\s?\d\.\d', head)):
        return [mk(m, None, 'range') for m in ds]
    nums = [p for g in _band_groups(s) if not g[3] and g[0] < ds[0].start(1) for p, _sh in g[2] if 2000 <= p <= 3800]
    if nums and len(nums) == len(ds):
        return [mk(m, p, 'list' if len(ds) > 1 else 'single') for m, p in zip(ds, nums)]
    if not nums:
        # the distance first, its bands after: '2.70 Å was derived from the band at 3400 cm-1', 'distances of 2.65 and
        # 2.75 Å, calculated from the bands at 3338 and 3057 cm-1' — the words between must say the one comes from the other
        after = [g for g in _band_groups(head) if not g[3] and g[0] > ds[-1].end(1)]
        if after and re.search(_FROM, head[ds[-1].end(1): after[0][0]]):
            nums = [p for g in after for p, _sh in g[2] if 2000 <= p <= 3800]
            if nums and len(nums) == len(ds):
                return [mk(m, p, 'list' if len(ds) > 1 else 'single') for m, p in zip(ds, nums)]
    if not nums:
        ctx = _numbers_before(sents, k, 2000, 3800)
        if ctx and len(ctx) == len(ds) and len(ds) > 1:
            return [mk(m, p, 'ctx') for m, p in zip(ds, ctx)]
    return [mk(m) for m in ds]


# ----------------------------------------------------------------------------- the checks

BC_SLACK = 0.006        # beyond the printed rounding: a value truncated instead of rounded (1.789 printed 1.78)
LIB_SLACK = 0.010       # the curve is read to two decimals from a three-figure wavenumber
MIN_DIFF = 0.02         # Å: under this a difference between stated and recomputed is never a finding
CTX_DIFF = 0.03         # Å: the same for a distance whose band is in the sentence before (paired by count alone)


def _tol(dec, slack):
    return 0.5 * 10 ** (-dec) + slack


def _fmt(d, dec):
    return '%.*f' % (max(2, dec), d)


def check_claims(text, _split=None):
    """The stated distances against the relations -> [{'claim', 'status', 'calc', 'line', 'grade', 'raw'}].
      status  'reproduced' | 'sibling' (the other of the two uranyl relations gives the stated value) | 'off' |
              'outlier' (one pair of a list that otherwise reproduces) | 'order' (a list that reproduces in
              another order) | 'range' | 'unpaired' (no band to recompute it from: nothing is said)
      grade   'flag' | 'info' | None (nothing to say);  raw: the sentence as the paper prints it"""
    raw, sents = _split or split(text)
    out = []
    for k, s in enumerate(sents):
        got = []
        if _cites(s, 'Bartlett'):
            cs = _bc_claims(s, sents, k)
            if cs:
                got += _judge_bc(cs, sents, k)
        if _cites(s, 'Libowitzky'):
            cs = _lib_claims(s, sents, k)
            if cs:
                got += _judge_lib(cs, sents, k)
        for r in got:
            r['raw'] = raw[k]
        out += got
    # the reading proves itself on the paper's other pairs: a pair the sentence makes itself, stated and not
    # reproduced, is a finding once another such pair of the same relation reproduces
    proved = {r['claim'].relation[:3] for r in out if r['status'] == 'reproduced' and r['claim'].paired in ('band', 'list', 'ctx', 'single')}
    for r in out:
        c = r['claim']
        if r['status'] == 'off' and r['grade'] == 'info' and c.paired == 'band' and c.relation[:3] in proved and r['calc'] is not None and abs(r['calc'] - c.dist) >= MIN_DIFF:
            r['grade'] = 'flag'
            # the information form '… stated for the band at N cm⁻¹; <relation> gives D Å for it (information)' as a finding
            r['line'] = re.sub(r'; (.+?) gives (\S+ Å) for it \(information\)$', r' vs \2 by \1', r['line'])
    return out


def _judge_bc(cs, sents, k):
    out = []
    ctx = _uranyl_context(sents, k)
    for c in cs:
        tol = _tol(c.decimals, BC_SLACK)
        rec = {'claim': c, 'status': 'unpaired', 'calc': None, 'line': None, 'grade': None}
        if c.band is not None:
            d1, d3 = bc_nu1(c.band), bc_nu3(c.band)
            if c.mode is None:                                  # the mode is the paper's assignment elsewhere, or unknown
                ms = {b.mode for b, _o in ctx if abs(b.pos - c.band) < 0.6}
                mode = ms.pop() if len(ms) == 1 else None
                best = d1 if abs(d1 - c.dist) <= abs(d3 - c.dist) else d3
                own = d1 if mode == 1 else d3 if mode == 3 else best
                if abs(own - c.dist) <= tol:
                    rec.update(status='reproduced', calc=own)
                elif abs(best - c.dist) <= tol:
                    # the relation of the OTHER mode gives the stated value. The mode is the reader's, from the paper's
                    # assignment elsewhere — worth a word, never a finding (a mode the sentence names itself is one)
                    rec.update(status='sibling', calc=own, grade='info',
                               line='U–O %s Å at %g cm⁻¹: the text assigns that band to ν%d, whose relation of %s gives %s Å; %s Å is what the ν%d relation gives (information)'
                                    % (c.text, c.band, mode, BC, _fmt(own, c.decimals), c.text, 3 if mode == 1 else 1))
                else:
                    rec.update(status='off', calc=own, grade='info',
                               line='U–O %s Å stated for the band at %g cm⁻¹; %s%s gives %s Å for it (information)'
                                    % (c.text, c.band, BC, ' (ν%d)' % mode if mode else '', _fmt(own, c.decimals)))
            else:
                own, sibv = (d1, d3) if c.mode == 1 else (d3, d1)
                if abs(own - c.dist) <= tol:
                    rec.update(status='reproduced', calc=own)
                elif abs(sibv - c.dist) <= tol and abs(own - c.dist) >= MIN_DIFF:
                    rec.update(status='sibling', calc=own, grade='flag',
                               line='U–O %s Å from ν%d at %g cm⁻¹ vs %s Å by the ν%d relation of %s — %s Å is what the ν%d relation gives for that wavenumber'
                                    % (c.text, c.mode, c.band, _fmt(own, c.decimals), c.mode, BC, c.text, 3 if c.mode == 1 else 1))
                else:
                    rec.update(status='off', calc=own, grade='info',
                               line='U–O %s Å stated for the band at %g cm⁻¹; %s (ν%d) gives %s Å for it (information)' % (c.text, c.band, BC, c.mode, _fmt(own, c.decimals)))
        elif c.paired == 'mode':
            fn, sib = (bc_nu1, bc_nu3) if c.mode == 1 else (bc_nu3, bc_nu1)
            cand = [b for b, _o in ctx if b.mode == c.mode]
            hit = [b for b in cand if abs(fn(b.pos) - c.dist) <= tol]
            if hit:
                rec.update(status='reproduced', calc=fn(hit[0].pos))
            elif len({b.pos for b in cand}) == 1 and abs(fn(cand[0].pos) - c.dist) >= MIN_DIFF:
                b = cand[0]
                if abs(sib(b.pos) - c.dist) <= tol:
                    rec.update(status='sibling', calc=fn(b.pos), grade='info',
                               line='U–O %s Å (ν%d): the ν%d band at %g cm⁻¹ gives %s Å by its own relation of %s, and %s Å by the ν%d relation (information)'
                                    % (c.text, c.mode, c.mode, b.pos, _fmt(fn(b.pos), c.decimals), BC, c.text, 3 if c.mode == 1 else 1))
                else:
                    rec.update(status='off', calc=fn(b.pos), grade='info',
                               line='U–O %s Å (ν%d): the ν%d band at %g cm⁻¹ gives %s Å by %s (information)'
                                    % (c.text, c.mode, c.mode, b.pos, _fmt(fn(b.pos), c.decimals), BC))
        else:
            calcs = [(b, (bc_nu1 if b.mode == 1 else bc_nu3)(b.pos), o) for b, o in ctx]
            if any(abs(d - c.dist) <= tol for _b, d, _o in calcs):
                rec.update(status='reproduced', calc=min((d for _b, d, _o in calcs), key=lambda d: abs(d - c.dist)))
            elif any(min(abs(bc_nu1(p) - c.dist), abs(bc_nu3(p) - c.dist)) <= tol for p in _numbers_before(sents, k + 1, 700, 1000)):
                rec.update(status='reproduced')                 # 'in the order given above': a band of the sentences before gives it
            elif c.paired == 'range':
                rec.update(status='range')
            else:
                near = [(b, d) for b, d, o in calcs if o <= 1]   # only what the sentence itself, or the one before, assigns
                if near and min(abs(d - c.dist) for _b, d in near) >= MIN_DIFF:
                    rec.update(status='off', calc=min((d for _b, d in near), key=lambda d: abs(d - c.dist)), grade='info',
                               line='U–O %s Å credited to %s: the uranyl bands the text assigns (%s cm⁻¹) give %s Å (information)'
                                    % (c.text, BC, ', '.join('ν%d %g' % (b.mode, b.pos) for b, _d in near[:4]),
                                       ', '.join(_fmt(d, c.decimals) for _b, d in near[:4])))
        out.append(rec)
    return out


def _judge_lib(cs, sents, k):
    ho = cs[0].relation == 'lib_ho'
    fwd, inv = (lib_d_ho, lib_nu_ho) if ho else (lib_d, lib_nu)
    what = 'H···O' if ho else 'O···O'
    recs = []
    for c in cs:
        rec = {'claim': c, 'status': 'range' if c.paired == 'range' else 'unpaired', 'calc': None, 'line': None, 'grade': None}
        if c.band is not None:
            rec['calc'] = fwd(c.band)
            rec['status'] = 'reproduced' if rec['calc'] is not None and abs(rec['calc'] - c.dist) <= _tol(c.decimals, LIB_SLACK) else 'off'
        recs.append(rec)
    loose = [r for r in recs if r['claim'].paired == '']
    if loose:                                                    # a distance with no band beside it: any O–H band stated just before may give it
        ctx = [p for g in _band_groups(sents[k]) if not g[3] for p, _sh in g[2] if 2000 <= p <= 3800] + _numbers_before(sents, k, 2000, 3800)
        for r in loose:
            c = r['claim']
            ds = [fwd(p) for p in ctx]
            if any(d is not None and abs(d - c.dist) <= _tol(c.decimals, LIB_SLACK) for d in ds):
                r['status'] = 'reproduced'
    paired = [r for r in recs if r['claim'].paired in ('list', 'ctx')]
    off = [r for r in paired if r['status'] == 'off']
    ok = [r for r in paired if r['status'] == 'reproduced']
    if off and len(paired) >= 2:
        # the same numbers in another order ('2.65 and 2.75' for the bands at 3338 and 3057)
        tol = _tol(paired[0]['claim'].decimals, LIB_SLACK) + 0.005
        a = sorted(r['claim'].dist for r in paired); b = sorted((r['calc'] if r['calc'] is not None else 9.0) for r in paired)
        if all(abs(x - y) <= tol for x, y in zip(a, b)):
            for r in off:
                r['status'] = 'reproduced' if r['claim'].paired == 'ctx' or not re.search(r'respectively', r['claim'].sentence) else 'order'
            first = next((r for r in off if r['status'] == 'order'), None)
            if first:
                first['grade'] = 'info'
                first['line'] = ('%s distances %s Å for the bands at %s cm⁻¹, ‘respectively’: %s gives %s Å in that order (information)'
                                 % (what, ', '.join(r['claim'].text for r in paired), ', '.join('%g' % r['claim'].band for r in paired), LIB,
                                    ', '.join(_fmt(r['calc'], r['claim'].decimals) if r['calc'] is not None else 'none' for r in paired)))
            return recs
    for r in recs:
        c = r['claim']
        if r['status'] != 'off':
            continue
        if r['calc'] is None:
            nu = inv(c.dist)
            # a band PREDICTED from a distance ('predicts bands at about 3600 … for O···O = 3.153 Å'), rounded: the relation's own
            # band for the distance is the comparison
            if nu is not None and abs(nu - c.band) <= 25 and re.search(r'\babout\b|~|∼|\bca\.|approximately|predict', c.sentence, re.I):
                r['status'] = 'reproduced'; continue
            r['grade'] = 'info'
            r['line'] = ('%s %s Å for the band at %g cm⁻¹: the curve of %s ends at %g cm⁻¹, below that band; %s Å gives %s cm⁻¹ (information)'
                         % (what, c.text, c.band, LIB, LIB_FREE_HO if ho else LIB_FREE_OO, c.text, '%.0f' % nu if nu is not None else 'no band'))
            continue
        if abs(r['calc'] - c.dist) < (CTX_DIFF if c.paired == 'ctx' else MIN_DIFF):
            r['status'] = 'reproduced'; continue
        if c.paired in ('list', 'ctx') and len(paired) >= 3 and len(off) == 1 and len(ok) >= 2:
            r['status'] = 'outlier'; r['grade'] = 'flag'
            r['line'] = ('%s %s Å for the band at %g cm⁻¹ vs %s Å by %s — the other %d pairs reproduce; %s Å is what a band at %.0f cm⁻¹ gives'
                         % (what, c.text, c.band, _fmt(r['calc'], c.decimals), LIB, len(ok), c.text, inv(c.dist)))
        elif c.paired in ('band', 'single', 'list'):
            r['grade'] = 'info'
            r['line'] = '%s %s Å stated for the band at %g cm⁻¹; %s gives %s Å for it (information)' % (what, c.text, c.band, LIB, _fmt(r['calc'], c.decimals))
        else:                                                  # bands of the sentence before, paired by count alone: a word, never a finding
            r['grade'] = 'info'
            r['line'] = ('%s %s Å: the bands stated just before (%s cm⁻¹) give %s Å by %s — %s Å has no band among them (information)'
                         % (what, c.text, ', '.join('%g' % x['claim'].band for x in paired), ', '.join(_fmt(x['calc'], c.decimals) if x['calc'] is not None else 'none' for x in paired),
                            LIB, c.text))
    return recs


def _short(s, around, n=70):
    """A stretch of the sentence around a term, for a Word comment's anchor."""
    i = s.find(around) if around else 0
    if i < 0:
        return s[:n].strip()
    a = max(0, i - n // 2); b = min(len(s), a + n)
    while a > 0 and s[a - 1] != ' ':
        a -= 1
    while b < len(s) and s[b] != ' ':
        b += 1
    return s[a: b].strip()


def check_lines(text, ex=None, cif=None, path=None, structure=None):
    """The spectroscopy section of a paper's checks: ['spectroscopy: …', line, …], or [] when the paper credits
    no distance to either relation and there is no structure to set its bands beside. `text` is the paper's
    (paper_extract.text_of); `cif` its structure, else `path` for the bond table it prints."""
    sp = split(text)
    if not any('cm-1' in x for x in sp[1]):
        return []
    res = check_claims(text, sp) if re.search(r'Bartlett|Libowitzky', text or '') else []
    prose = [b for b in _bands_of(sp[1]) if b.own]
    name = (ex or {}).get('name')
    if not name:
        try:
            from pxrd_review import paper_extract as PE
            name = PE.mineral_name(text)
        except Exception:
            name = ''
    try:
        tab = table_bands(path, name) if path else []
    except Exception:
        tab = []
    own = prose + tab
    nu1 = sorted({b.pos for b in own if b.family == 'UO2' and b.mode == 1})
    nu3 = sorted({b.pos for b in own if b.family == 'UO2' and b.mode == 3})
    oh = sorted({b.pos for b in own if b.family == 'OH' and b.mode == 'stretch' and 2000 <= b.pos <= 3800})
    if structure is None and cif:
        try:
            structure = structure_distances(cif)
        except Exception:
            structure = None
    if structure is None and path and not cif and (nu1 or nu3):
        try:
            structure = bond_table_distances(path, ex, text)
        except Exception:
            structure = None
    lines = []
    for r in res:
        if r['line']:
            c = r['claim']
            lines.append("%s ‘%s’" % (r['line'], _short(r['raw'], c.text)))
    if structure:
        lines += structure_lines(structure, nu1, nu3, oh)
    beside = bool(lines) and not res
    try:
        about = species_lines(text, ex, name, sp, tab)
    except Exception:
        about = []
    forms = []
    try:
        forms = paper_formulas(text, name or '')
        about += library_lines(own, forms)
    except Exception:
        pass
    try:
        about += table_lines(tab, prose)
    except Exception:
        pass
    try:
        about += assignment_lines(own)
    except Exception:
        pass
    try:
        about += rruff_lines(own, name, comparison_species(text, name, sp))
    except Exception:
        pass
    lines += about
    if not res and not lines:
        return []
    if res:
        n_bc = sum(1 for r in res if r['claim'].relation == 'bc'); n_lib = len(res) - n_bc
        n_ok = sum(1 for r in res if r['status'] == 'reproduced')
        n_open = sum(1 for r in res if r['status'] in ('unpaired', 'range'))
        head = 'spectroscopy: %d distance%s credited to %s — %d reproduced from the stated bands%s' % (
            len(res), '' if len(res) == 1 else 's', ' and '.join(x for x in ((BC if n_bc else ''), (LIB if n_lib else '')) if x), n_ok,
            ', %d with no single band to recompute from' % n_open if n_open else '')
    else:
        head = 'spectroscopy: the stated bands beside the %s' % ' and the '.join(x for x in (('structure' if beside else ''), ('formula' if any(not ln.startswith(('table:', 'rruff:', 'mode')) for ln in about) else ''),
                                                                                              ('assignment table' if any(ln.startswith('table:') for ln in about) else ''),
                                                                                              ('band library' if any(ln.startswith('mode') for ln in about) else ''),
                                                                                              ('RRUFF spectra' if any(ln.startswith('rruff:') for ln in about) else '')) if x)
    return [head] + lines


# ----------------------------------------------------------------------------- the formula beside the bands
#
# What a reviewer reads a spectrum of a new mineral FOR is, first of all, its hydrogen and its light groups: the
# things the microprobe cannot see. Is the water of the formula molecular water (a H-O-H bending band near 1600-1650
# cm-1 says so, and its absence says hydroxyl)? Is there any O-H band at all? Does the ammonium, the carbonate, the
# hydronium the formula invokes show? These lines set the formula the paper states beside the bands it states.
# INFORMATION, every one: a paper need not list every band it measured, a formula may be cut short by the reader, and
# on the corpus a band assigned to a group the formula lacks is nearly always a real minor substituent.

BEND = (1550.0, 1700.0)         # where H-O-H bends (the corpus window is 1569-1675, 5th-95th percentile)
STRETCH_LO = 2700.0             # an O-H stretch is above this
# a light group of the formula and where its bands stand (carbonate from the corpus windows; ammonium and nitrate and
# hydronium from the literature's usual positions — Farmer 1974)
LIGHT = (('CO3', 'carbonate', ((1350.0, 1560.0), (1040.0, 1120.0)), r'carbonat|CO3'),
         ('NH4', 'ammonium', ((1380.0, 1490.0),), r'ammoni|NH4|N-H'),
         ('NO3', 'nitrate', ((1300.0, 1450.0), (1035.0, 1065.0)), r'nitrat|NO3'),
         ('H3O', 'hydronium', ((1650.0, 1780.0),), r'hydroni|oxoni|H3O'))
# the element a group cannot be without, and how an analysis names it
GROUP_ELEMENT = {'UO2': 'U', 'SO4': 'S', 'PO4': 'P', 'AsO4': 'As', 'VO4': 'V', 'CO3': 'C', 'SiO4': 'Si', 'BO3': 'B', 'BO4': 'B', 'MoO4': 'Mo', 'WO4': 'W',
                 'CrO4': 'Cr', 'SeO3': 'Se', 'SeO4': 'Se', 'TeO3': 'Te', 'NO3': 'N', 'NH4': 'N'}
_ELEMENT_WORD = {'U': r'\buran', 'S': r'\bsul[fp]', 'P': r'\bphosph', 'As': r'\barsen', 'V': r'\bvanad', 'C': r'\bcarbonat', 'Si': r'\bsilicat', 'B': r'\bbor(?:on|at)',
                 'Mo': r'\bmolybd', 'W': r'\btungst|\bwolfram', 'Cr': r'\bchrom', 'Se': r'\bselen', 'Te': r'\btellur', 'N': r'\bnitrat|\bammoni'}
# a sentence that puts the band down to something that is not the mineral
_NOT_THE_MINERAL = re.compile(r'adsorb|absorbed|moisture|\bKBr\b|impurit|\btrace|\bminor\b|inclusion|admix|contaminat|humid|hygroscop|surface water|atmospher|'
                              r'substitut|-bearing|\bepoxy|\bresin|\bglue|organic', re.I)
_OTHER_MINERAL = re.compile(r'\b([a-zà-ÿ]{5,}ite)(?:-\([A-Za-z0-9]+\)|-\d[A-Za-z])?\b')


def formula_species(formula):
    """{'H2O', 'OH', 'H3O', 'NH4', 'CO3', 'NO3'} — the hydrogen species and light groups a formula WRITES."""
    f = re.sub(r'<[^>]+>|&#\d+;|\s|[\x00-\x1f]', '', formula or '')
    out = {k for k in ('H2O', 'H3O', 'NH4', 'CO3', 'NO3') if k in f}
    if 'OH' in f.replace('H2O', '').replace('H3O', ''):
        out.add('OH')
    return out


def paper_formulas(text, name=''):
    """[(formula as printed, {element: count}, 'ideal' | 'empirical')] — the formulas the paper states for its mineral:
    the ideal one first, then the empirical ones."""
    from pxrd_review import paper_extract as PE
    out = []
    try:
        idf = PE.ideal_formula(text)
        if idf:
            out.append((idf[0], dict(idf[1]), 'ideal'))
    except Exception:
        pass
    try:
        for f in PE._formulas(text, name or '')[:2]:
            if f[0] and f[1]:
                out.append((f[0], dict(f[1]), 'empirical'))
    except Exception:
        pass
    return out


def _wn(v):
    return ', '.join('%g' % p for p in v[:6]) + (' …' if len(v) > 6 else '')


LIBRARY_MIN = 700.0             # cm-1: below this the bends of every group and the metal-oxygen modes share the axis
LIBRARY_BANDS = 4               # a paper stating fewer bands than this gives a list, not a spectrum to set beside its formula


_COMPARE = re.compile(r'\b(compar\w*|similar\w*|resembl\w*|close to|analog\w*|related|typical of|same as|like that of|like those of|'
                      r'in contrast|contrast\w*|differ\w*|different|distinct\w*|common features|consistent with|agree\w*|identical)\b', re.I)
_NAME_WORD = re.compile(r"[A-Za-zÀ-ɏ][A-Za-zÀ-ɏ'’\-]{4,}(?:-\([A-Za-z0-9+,]+\))?")
_NOT_VIBRATIONAL = re.compile(r'reflectance|reflection|reflectivity|optical|(?<!infrared )(?<!IR )(?<!FTIR )absorption spectr|electronic|XANES|XPS|EXAFS|NMR|Mössbauer|EDS|energy[- ]dispersive|'
                              r'impurit|admix|intergrow|inclusion|geological setting|\bppm\b|crystal field|10Dq|edge position|heterostruct', re.I)   # not a vibrational spectrum compared, or a phase in the sample
_LIKE = re.compile(r"([A-Za-zÀ-ɏ][A-Za-zÀ-ɏ'’]{4,}(?:-\([A-Za-z0-9+,]+\))?)-(?:like|type)\b(?!\s*(?:phase|layer|structure|intergrow|unit|cell|arrangement))")
_NOT_A_SPECIMEN = re.compile(r'^\s*(?:anvil|cell|standard|substrate|window|holder|plate|powder standard|structure|heterostruct|sheet|chain|framework|group minerals? (?:structure|type))', re.I)   # 'diamond anvil', 'quartz standard', 'perovskite structure': not a spectrum compared
_GREEK_PREFIX = re.compile(r'(?:^|[^A-Za-zÀ-ɏ])[A-Za-zα-ωΑ-Ω]-$')                                              # 'α-quartz' (a transliterated 'a-quartz' too): a modification, not the mineral
_NOT_A_SPECTRUM = re.compile(r'^-(?:like|type)\s*(?:phase|layer|sheet|chain|structure|intergrow|unit|cell|arrangement|compound|modification|framework|[A-Z][a-z]?[A-Z0-9])', re.I)    # 'christelite-like phase', 'rutile-like GeO2': a structure, not a spectrum compared
COMPARE_SPAN = 160              # characters after a comparison word in which the species named is its object
TITLE_CHARS = 300               # the paper's title and first lines: a species named there is a subject of the paper (a second mineral it describes)
_NEW_MINERAL = re.compile(r'new (?:mineral|species)', re.I)
_NAME_LC = r"[a-zà-ɏ][a-zà-ɏ'’\-]{4,}(?:-\([a-z0-9+,]+\))?"
_SUBJECT = re.compile(r'new (?:mineral|species)s?(?:\s+\S+){0,2}?\s+(%s)|(%s),?(?:\s+(?:is|are|as|and))?\s+(?:an?|the|two|three|this)?\s*new (?:mineral|species)' % (_NAME_LC, _NAME_LC))


def _table_like(sent):
    """A table flattened into a 'sentence' (cell parameters, probe standards, comparative data): numbers crowd the words."""
    nums = len(re.findall(r'\d+(?:\.\d+)?', sent)); words = len(re.findall(r'[A-Za-zÀ-ɏ]{3,}', sent))
    return nums >= 12 and nums > 0.6 * words


def comparison_species(text, name, sp=None):
    """The known species a paper sets its SPECTRUM beside -> [(species as IMA writes it, the paper's sentence)]. A sentence
    about Raman / infrared spectra (not reflectance), not a table flattened into prose, with a comparison word followed
    within COMPARE_SPAN characters by a mineral name of the local snapshot ('exact' or 'spelling' only — never a root:
    'davidite' names two species), or '<species>-like'; never the paper's own mineral (its stem, diacritics folded),
    a mineral named in the title or called a new mineral in a sentence that compares nothing (a second mineral the paper
    describes), or a word of COMMON. 'isostructural with X' counts too (extra_checks._REL). Measured on the corpus before
    it fed a line (see the rules file). Snapshot only."""
    from pxrd_review import mineral_names as MN
    from pxrd_review import extra_checks as XC
    sp = sp or split(text)
    raw, norm = sp
    stem = MN._fold(re.sub(r'-\(.*\)$', '', (name or '').lower()))[:7]
    quote = {n: r for r, n in zip(raw, norm)}
    folded = MN._fold((text or '').lower())
    stop = re.search(r'[^.;]*(?:cm-1|spectr)', folded)              # the title and the lines before the first word of spectroscopy
    head = folded[:min(TITLE_CHARS, stop.start() if stop else TITLE_CHARS)]
    subjects = set()                                             # the species the paper DESCRIBES: in its title, or beside 'new mineral'
    for s in re.split(r'[.;]', folded):
        if _NEW_MINERAL.search(s) and not _COMPARE.search(s):    # 'the new mineral is similar to autunite' names a comparison, not a subject
            for m in _SUBJECT.finditer(s):                       # a name within two words of 'new mineral' ('the new mineral boevskite', 'zalesiite, a new mineral'):
                subjects.add(MN._fold(m.group(1) or m.group(2))) # the whole sentence took a reference list's 'of the mixite group' and an abstract's associations
    out, seen = [], set()
    def names_in(span):
        found = []
        for m in _NAME_WORD.finditer(span):
            w = m.group(0)
            after = span[m.end():m.end() + 30]
            if w.lower().endswith(('-like', '-type')):
                after = w[w.lower().rfind('-'):] + after                   # the affix is part of the word matched: 'christelite-like phase'
            if _GREEK_PREFIX.search(span[max(0, m.start() - 3):m.start()]) or _NOT_A_SPECIMEN.match(span[m.end():m.end() + 20]) or _NOT_A_SPECTRUM.match(after):
                continue
            tok, _affix = MN._clean_affix(w)
            if not tok or tok.lower() in MN.COMMON:
                continue
            if stem and MN._fold(tok.lower()).startswith(stem):
                continue
            how, norms = MN.lookup(tok)
            if how in ('exact', 'spelling') and len(norms) == 1:
                key = MN._fold(tok.lower())
                if re.search(r'(?<![a-z])%s(?![a-z])' % re.escape(key), head) or key in subjects:
                    continue                                              # in the title or called a new mineral: one the paper describes, not compares with
                found.append(norms[0])
        return found
    for sent in norm:
        if 'cm-1' not in sent and not re.search(r'Raman|infrared|\bIR\b|FTIR|spectr', sent):
            continue                                              # a spectroscopy sentence only: the comparison is of spectra ('bands' alone is geology too)
        if _NOT_VIBRATIONAL.search(sent) or _table_like(sent):
            continue
        spans = [sent[m.end():m.end() + COMPARE_SPAN] for m in _COMPARE.finditer(sent)] + [sent[m.end():m.end() + COMPARE_SPAN] for m in XC._REL.finditer(sent)]
        spans += [sent[max(0, m.start() - 3):m.end() + 30] for m in _LIKE.finditer(sent)]   # three characters before ('α-quartz-type' is no mineral), thirty after ('-like GeO2')
        for span in spans:
            for key in names_in(span):
                if key not in seen:
                    seen.add(key); out.append((key, quote.get(sent, sent)))
    return out


RRUFF_NEAR = 6.0        # cm⁻¹: a stated band 'within' a reference band — spectrum.compare_stated's tolerance
RRUFF_FAR = 15.0        # cm⁻¹: the wider tolerance — auto_fit's seed tolerance


def rruff_lines(own, name, comparisons=(), lib=None):
    """RRUFF's reference bands beside the paper's OWN stated bands — INFORMATION, one line per species and technique: the
    paper's mineral when RRUFF holds it (a reinvestigated species) and each species the paper compares with. Only bands
    the paper states as its own (`Band.own`: never a literature column of its table); its Raman bands beside the best
    Raman spectrum by `rruff.rank` (processed, excellent, unoriented, 532 nm), its infrared bands beside the species'
    infrared spectrum when RRUFF holds one (a sulfate ν3 strong in infrared is weak in Raman: the one says nothing of the
    other); bands by `rruff.bands_of`; when the paper's Raman bands reach the O–H region and RRUFF has a broad scan of
    that mineral, that scan's O–H bands too. Silent without a store."""
    try:
        from pxrd_review import rruff as RR, mindat as M
        lib = lib if lib is not None else RR.libraries(None)
    except Exception:
        return []
    if lib is None or not own:
        return []
    mine = [b for b in own if b.own and b.family != 'overtone' and b.pos >= 100]
    by_tech = {'raman': sorted({b.pos for b in mine if b.technique != 'ir'}), 'infrared': sorted({b.pos for b in mine if b.technique == 'ir'})}
    if not any(by_tech.values()):
        return []
    by = RR.by_species(lib)
    out, seen = [], set()
    for species in [name or ''] + [s for s, _sent in comparisons]:
        key = M._norm(species)
        if not key or key in seen or key not in by:
            continue
        seen.add(key)
        specs = by[key]
        for tech, pos in by_tech.items():
            if not pos:
                continue
            i, meta = next(((k, m) for k, m in specs if m.get('technique') == tech), (None, None))
            if i is None:
                continue
            try:
                x, y = lib.xy(i)
                ref = [p for p, _h in RR.bands_of(x, y)]
                if tech == 'raman' and pos[-1] > 2500:
                    j = next((k for k, m in specs if m.get('quality') == 'broad'), None)
                    if j is not None:
                        bx, by_ = lib.xy(j); ref += [p for p, _h in RR.bands_of(bx, by_, lattice=2500.0, n=6)]
            except Exception:
                continue
            ref = sorted({float(round(p)) for p in ref})
            if not ref:
                continue
            near = [p for p in pos if any(abs(p - r) <= RRUFF_NEAR for r in ref)]
            far = [p for p in pos if p not in near and any(abs(p - r) <= RRUFF_FAR for r in ref)]
            none = [p for p in pos if p not in near and p not in far]
            about = ', '.join(v for v in ('infrared' if tech == 'infrared' else '', (meta.get('laser') + ' nm') if meta.get('laser') else '', meta.get('quality') or '', meta.get('orient') or '') if v)
            line = 'rruff: %s (%s%s): bands at %s cm⁻¹' % (meta.get('name') or species, meta.get('id') or 'RRUFF', ', ' + about if about else '', _wn(ref))
            parts = []
            if near:
                parts.append('%s within %g of one' % (_wn(near), RRUFF_NEAR))
            if far:
                parts.append('%s within %g' % (_wn(far), RRUFF_FAR))
            if none:
                parts.append('%s near none' % _wn(none))
            if parts:
                line += '; the paper’s %s' % ('infrared ' if tech == 'infrared' else '') + ', '.join(parts)
            out.append(line + ' (information)')
    return out


def library_lines(own, forms):
    """The band library (pxrd_review.bands) beside the paper: the groups of its formula, where each one's bands are
    expected, and the stated bands that stand there — one line, INFORMATION. Only the modes above `LIBRARY_MIN`
    (stretches, the H-O-H bend), one entry per group; a group with no stated band in any of its ranges is named.
    NOT said, on measurement: the stated bands that fall in no range of the formula. On the corpus (96 papers, 190
    bands) those were the reader's as often as the paper's — the end of a stated range read as a band, a formula cut
    short of its water — so that question is left to `pxrd bands --at` and the spectrum window, where a person gives
    the band."""
    from pxrd_review import bands as BD
    if not forms:
        return []
    formula = re.sub(r'\s+', ' ', forms[0][0]).strip()
    keys = BD.groups_of(formula)
    if not keys or keys == ['sulfide']:
        return []
    pos = sorted({b.pos for b in own if b.family != 'overtone' and b.own})
    if len(pos) < LIBRARY_BANDS:
        return []
    tech = {b.technique for b in own}
    one = next(iter(tech)) if len(tech) == 1 and None not in tech else None            # a paper of one technique
    rows = [r for r in BD.expected(groups=keys, technique=one) if r['hi'] > LIBRARY_MIN]
    span = lambda r: (min(r['lo'], r['published']['p5']), max(r['hi'], r['published']['p95'])) if r['published'] else (r['lo'], r['hi'])
    shown = lambda r: '%d–%d' % ((r['published']['p5'], r['published']['p95']) if r['published'] else (r['lo'], r['hi']))
    parts = {}; order = []
    for r in rows:                                               # one entry per group: its modes with their ranges, then the bands in any of them
        lo, hi = span(r)
        inside = [p for p in pos if lo <= p <= hi]
        if r['broad']:
            continue
        oh = r['mode'] == 'stretch' and r['group'] in ('OH', 'H2O')                    # water and hydroxyl stretch in one place
        key = 'O–H' if oh else 'H2O bend' if (r['group'], r['mode']) == ('H2O', 'bend') else r['group']
        if key not in parts:
            parts[key] = {'modes': [], 'bands': set(), 'lo': lo, 'hi': hi}; order.append(key)
        e = parts[key]
        name = 'stretch' if oh else '' if key == 'H2O bend' else r['mode']
        if name not in [m for m, _s in e['modes']]:
            e['modes'].append((name, shown(r)))
        e['bands'].update(inside); e['lo'] = min(e['lo'], lo); e['hi'] = max(e['hi'], hi)
    has = []; none = []
    for key in order:
        e = parts[key]
        modes = ', '.join(('%s %s' % (m, s)).strip() for m, s in e['modes'])
        if e['bands']:
            has.append('%s (%s): %s' % (key, modes, _wn(sorted(e['bands']))) if len(e['modes']) > 1 or e['modes'][0][0] not in ('', 'stretch') else
                       '%s %s: %s' % (key if key != 'O–H' else 'O–H stretch', e['modes'][0][1], _wn(sorted(e['bands']))))
        elif key not in ('O–H', 'H2O bend') and pos[0] <= e['hi'] and pos[-1] >= e['lo']:      # … inside the stretch of axis the paper reports;
            none.append('%s (%s)' % (key, modes))                                              # the O-H bands are `species_lines`' to speak of
    if not has:
        return []
    shown_f = formula if len(formula) <= 60 else formula[:57] + '…'
    line = 'expected: the groups of %s and the stated bands in their ranges — %s' % (shown_f, '; '.join(has))
    if none:
        line += '; no band stated for %s' % ', '.join(none)
    return [line]


def species_lines(text, ex=None, name='', _split=None, extra_bands=()):
    """The formula's hydrogen species and light groups beside the bands the paper states -> lines (information).
    `extra_bands`: bands read from somewhere other than the prose (an assignment table)."""
    sp = _split or split(text)
    raw, norm = sp
    quote = {n: r for r, n in zip(raw, norm)}
    own = [b for b in _bands_of(norm) if b.own] + [b for b in extra_bands if b.own]
    if len({b.pos for b in own}) < 3:
        return []
    forms = paper_formulas(text, name or (ex or {}).get('name') or '')
    if not forms:
        return []
    ftxt = re.sub(r'\s+', ' ', forms[0][0]).strip()
    shown = ftxt if len(ftxt) <= 60 else ftxt[:57] + '…'
    each = [formula_species(f) for f, _c, _k in forms]
    elements = set().union(*[set(c) for _f, c, _k in forms])
    try:                                                         # what the analysis measured counts as carried
        from pxrd_review import epma as EP
        for c in ((ex or {}).get('epma') or {}).get('wt') or {}:
            try:
                elements.add(EP.parse_constituent(c).element)
            except Exception:
                pass
    except Exception:
        pass
    has = lambda k: k in each[0] and all(k in e or kind != 'ideal' for e, (_f, _c, kind) in zip(each, forms))     # the first formula writes it …
    anywhere = lambda k: any(k in e for e in each)
    hydrogen = 'H' in elements or anywhere('H2O') or anywhere('OH') or anywhere('H3O') or anywhere('NH4')
    pos = sorted({b.pos for b in own})
    ranges = [(lo, hi) for lo, hi, _s in band_ranges(text)]
    inside = lambda lo, hi: [p for p in pos if lo <= p <= hi]
    reaches = lambda lo, hi: bool(inside(lo, hi)) or any(a <= hi and b >= lo for a, b in ranges)
    said = lambda pat: any('cm-1' in x and re.search(pat, x, re.I) for x in norm)
    stretch = [p for p in pos if STRETCH_LO <= p <= 3800.0]
    stretch_any = bool(stretch) or pos[-1] >= STRETCH_LO or any(b >= STRETCH_LO and a <= 3800.0 for a, b in ranges) or any(b.family == 'OH' and b.mode == 'stretch' for b in own)
    bend_any = reaches(*BEND) or said(r'H-O-H|(?:bend|deform|scissor)\w*[^.;]{0,50}(?:water|H2O)|(?:water|H2O)[^.;]{0,70}(?:bend|deform|scissor)|δ\s?\(?\s?H2O') or \
        any(re.search(r'(?:\bat|near|around|about|ca\.?|[~∼≈])\s?1(?:5[5-9]|6\d)\d(?![\d.])', x) and re.search(r'H-O-H|\bwater\b|H2O|bend', x, re.I) for x in norm)    # 'a band at 1615 is assigned to the bending of H2O', the unit left out
    stem = re.sub(r'-\(.*\)$', '', (name or (ex or {}).get('name') or '').lower())[:7]
    other = lambda sent: any(not stem or not m.group(1).startswith(stem) for m in _OTHER_MINERAL.finditer(sent.lower()))    # the sentence is about another mineral's spectrum
    # the text saying that NO band stands where water bends: a position there, or a range the sentence itself ties to water
    water_bend = r'H\s?-\s?O\s?-\s?H|(?:bend|deform|scissor)\w*[^.;]{0,60}(?:water|H2O)|(?:water|H2O)[^.;]{0,80}(?:bend|deform|scissor)'
    gone = [(lo if lo == hi else 0.5 * (lo + hi), r) for lo, hi, r in absent_bands(text, sp)
            if (lo == hi and BEND[0] <= lo <= BEND[1]) or (lo < hi and lo <= BEND[1] and hi >= BEND[0] and re.search(water_bend, normalise(r), re.I))]
    gone = [g for g in gone if not other(g[1])]              # 'unlike the spectrum of X, that of Y shows no peak …': which of two minerals the formula is, is not known
    # a formula cut short by the reader lacks its water: the text writing '·2H2O' or '(H2O)4' anywhere says the mineral
    # (or one it is compared with) is hydrated, and the lines that rest on 'no H2O in the formula' are then not written
    wet_text = bool(re.search(r'[·⋅•\x02]\s?\d*(?:\.\d+)?\s?H2O|\(H2O\)|\d\s?H2O\b', text))
    lines = []
    q = lambda sent: " ‘%s’" % _short(quote.get(sent, sent), '', 90) if sent else ''
    if has('H2O'):
        if gone:
            lines.append("water: the formula carries H2O (%s) and the text states that the spectrum shows no band near %.0f cm⁻¹, where H–O–H bends (information) ‘%s’"
                         % (shown, gone[0][0], _short(gone[0][1].strip(), '', 110)))
        elif stretch_any and not bend_any:
            raman_only = not re.search(r'infrared|\bFTIR\b|\bFT-IR\b|\bIR\b', text)
            lines.append('water: the formula carries H2O (%s); O–H stretching bands are stated%s and no H–O–H bending band near 1600–1650 cm⁻¹ — the band that tells molecular water from hydroxyl%s (information)'
                         % (shown, ' (%s cm⁻¹)' % _wn(stretch) if stretch else '', '; it is weak in a Raman spectrum, and an infrared spectrum shows it' if raman_only else ''))
    if (has('H2O') or has('OH')) and not stretch_any and not bend_any and not gone:
        lines.append('hydrogen: the formula carries %s (%s); the %d bands stated (%g–%g cm⁻¹) reach neither the H–O–H bending region nor the O–H stretching region (information)'
                     % (' and '.join(k for k in ('H2O', 'OH') if has(k)), shown, len(pos), pos[0], pos[-1]))
    if has('OH') and not anywhere('H2O') and not wet_text:
        wb = [b for b in own if BEND[0] <= b.pos <= BEND[1] and not _NOT_THE_MINERAL.search(b.sentence) and not other(b.sentence) and
              not re.search(r'overtone|combination|at best|indication|\bmay\b|\bmight\b|possibl|tentativ', b.sentence, re.I) and
              (b.family == 'H2O' or re.search(r'H-O-H|\bwater\b|H2O', b.sentence))]
        if wb:
            lines.append('water: a band at %s cm⁻¹ is stated as molecular water; the formula carries OH and no H2O (%s) (information)%s' % (_wn(sorted({b.pos for b in wb})), shown, q(wb[0].sentence)))
    if not hydrogen and not wet_text and not re.search(r'\(OH\)|\bOH\d', text):
        hb = [b for b in own if b.family in ('OH', 'H2O') and not _NOT_THE_MINERAL.search(b.sentence) and not other(b.sentence)]
        if hb:
            lines.append('hydrogen: bands at %s cm⁻¹ are assigned to O–H or H2O; the formula carries no hydrogen (%s) (information)%s' % (_wn(sorted({b.pos for b in hb})), shown, q(hb[0].sentence)))
    for key, word, wins, pat in LIGHT:
        if has(key) and not any(b.family == key for b in own) and not said(pat) and not any(reaches(lo, hi) for lo, hi in wins):
            lines.append('%s: the formula carries %s (%s); no band is stated for it — it would stand near %s cm⁻¹, and the %d bands stated run %g–%g cm⁻¹ (information)'
                         % (word, key, shown, ' or '.join('%g–%g' % w for w in wins), len(pos), pos[0], pos[-1]))
    # a band assigned to a group that neither the formula nor the analysis carries
    by = {}
    for b in own:
        el = GROUP_ELEMENT.get(b.family)
        if not el or el in elements:
            continue
        rest = text.replace(quote.get(b.sentence, b.sentence), '')
        if re.search(r'\b%s\d*O\d*\b' % el, rest) or re.search(_ELEMENT_WORD[el], rest, re.I):
            continue                                             # the analysis or the description names the element elsewhere: a constituent after all
        if _NOT_THE_MINERAL.search(b.sentence) or other(b.sentence):
            continue                                             # an admixture, a substituent, or another mineral's spectrum
        by.setdefault(b.family, []).append(b)
    for fam, bs in by.items():
        lines.append('assignment: bands at %s cm⁻¹ are assigned to %s; neither the formula (%s) nor the rest of the text carries %s (information)%s'
                     % (_wn(sorted({b.pos for b in bs})), fam, shown, GROUP_ELEMENT[fam], q(bs[0].sentence)))
    return lines


# ----------------------------------------------------------------------------- an assignment table (.docx)
#
# A table pairs a band with its assignment by ROW: no grammar to follow, no mispairing. Few manuscripts carry one (and a
# .pdf's is not read: its rows come apart in the text layer) — where one does, its bands join the prose's, and the two
# are set beside each other.

_SYMBOL_FONT = {'F06E': 'ν', 'F064': 'δ', 'F075': 'υ', 'F072': 'ρ', 'F067': 'γ', 'F074': 'τ', 'F077': 'ω', 'F0B1': '±', 'F0B0': '°', 'F07E': '~'}
_TAB_SKIP = re.compile(r'calc|DFT|theor|comput|simulat|literature|\bref|synthetic|assign|vibration|mode|irrep|symmetr|intensit|description|tentative', re.I)
_CELL_NUM = re.compile(r'(?<![\d.–-])(\d{2,4}(?:\.\d)?)\s?(?:\(?\s?(vs|vw|sh|br|vbr|s|m|w|b)\s?\)?)?(?![\d.]|\s?[–-]\s?\d)')
TET = ('SO4', 'PO4', 'AsO4', 'VO4', 'SiO4', 'MoO4', 'WO4', 'CrO4', 'SeO4')


def _cell_text(cell):
    """A table cell's text with the symbol-font characters python-docx drops (a ν or δ set as w:sym) put back."""
    out = []
    for el in cell._tc.iter():
        tag = el.tag.rsplit('}', 1)[-1]
        if tag == 't':
            out.append(el.text or '')
        elif tag == 'sym':
            code = (el.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}char') or '').upper()
            out.append(_SYMBOL_FONT.get(code, ''))
        elif tag in ('br', 'p') and out and not out[-1].endswith(' '):
            out.append(' ')
    return re.sub(r'\s+', ' ', ''.join(out)).strip()


def _row_assignment(cell):
    """(family, mode) of an assignment cell — both None when it names none, or names two things ('ν2 CO3 bending or ν3
    UO2 stretching': which of them the band is, the table leaves open)."""
    t = normalise(cell)
    t = re.sub(r'(?<![\dA-Za-zν.])([1-4])\s?(?:\(\s?[δd]?\s?\)\s?)?(?=[\(\[]?\s?(?:' + _GROUPS + r'))', r'ν\1 ', t)     # the ν lost: '3 (CO3)2- asym. stretching'
    a = _assignments(t)
    kinds = {(x[2], x[3]) for x in a}
    return next(iter(kinds)) if len(kinds) == 1 else (None, None)


def table_bands(path, name=''):
    """[Band] from the band-assignment tables of a manuscript .docx: a column of assignments and one or more columns
    of wavenumbers. In a table that sets several minerals side by side the column of the paper's own is the one read;
    a calculated or literature column never is. [] for anything but a .docx, and for a .docx without such a table."""
    if not str(path).lower().endswith('.docx'):
        return []
    try:
        import docx
        doc = docx.Document(path)
    except Exception:
        return []
    stem = re.sub(r'-\(.*\)$', '', (name or '').lower())[:7]
    out = []
    for t in doc.tables:
        try:
            rows = []
            for r in t.rows:
                cells = []; seen = set()
                for c in r.cells:
                    if id(c._tc) in seen:                        # a merged cell comes once per column it spans
                        continue
                    seen.add(id(c._tc)); cells.append(_cell_text(c))
                rows.append(cells)
        except Exception:
            continue
        ncol = max((len(r) for r in rows), default=0)
        if len(rows) < 4 or ncol < 2:
            continue
        rows = [r + [''] * (ncol - len(r)) for r in rows]
        body = rows[1:]
        asg = [sum(1 for r in body if _row_assignment(r[k])[0] or re.search(r'stretch|bend|lattice|libr|deform|[νδ]', r[k], re.I)) for k in range(ncol)]
        num = [sum(1 for r in body if _CELL_NUM.search(r[k]) and not re.search(r'[A-Za-z]{4,}', r[k])) for k in range(ncol)]
        ak = max(range(ncol), key=lambda k: asg[k])
        if asg[ak] < max(3, 0.5 * len(body)):
            continue
        head = rows[0]
        if not re.search(r'cm|wavenumber|Raman|\bIR\b|infrared|FTIR|band|peak|assign|vibration|mode|shift', ' '.join(head), re.I) and sum(num) < 2 * len(body):
            continue
        cols = [k for k in range(ncol) if k != ak and num[k] >= max(3, 0.4 * len(body)) and not _TAB_SKIP.search(head[k])]
        mine = [k for k in cols if stem and stem in head[k].lower().replace(' ', '')]
        theirs = set() if mine else {k for k in cols if _other_species_column(head[k], stem)}    # 'Autunite (Frost et al. 2005)': the literature's, not the paper's
        cols = mine or cols
        for r in body:
            fam, mode = _row_assignment(r[ak])
            for k in cols:
                tech = 'raman' if re.search(r'raman', head[k], re.I) else 'ir' if re.search(r'\bIR\b|infrared|FTIR', head[k], re.I) else None
                for m in _CELL_NUM.finditer(r[k]):
                    p = float(m.group(1))
                    if 30 <= p <= 4500:
                        out.append(Band(p, tech, (m.group(2) or '').lower(), fam, mode, 'table row: %s | %s' % (r[k], r[ak]), k not in theirs))
    return out


def _other_species_column(header, stem):
    """A column header that names another mineral of the snapshot, or cites a source ('(Frost et al. 2005)'): the
    literature's bands set beside the paper's, never read as the paper's own."""
    if re.search(r'\(\s*[A-Z][^()]*\d{4}[a-z]?\s*\)|\bet al\b|\[\d+\]', header):
        return True
    from pxrd_review import mineral_names as MN
    for w in _NAME_WORD.findall(header):
        tok, _affix = MN._clean_affix(w)
        if not tok or tok.lower() in MN.COMMON or (stem and MN._fold(tok.lower()).startswith(stem)):
            continue
        how, norms = MN.lookup(tok)
        if how in ('exact', 'spelling') and len(norms) == 1:
            return True
    return False


# ----------------------------------------------------------------------------- the paper's assignments against themselves
#
# What a reviewer of a new mineral meets (the owner, 2026-11-01): a band given the wrong mode number, a ν1 and a ν3 swapped.
# Only the paper against itself is a finding: ν1 above every ν3 of the same group, in its stretching region (the symmetric
# stretch lies below the antisymmetric one in SO4, PO4, SiO4, CO3 and UO2; AsO4 and VO4 overlap and are left alone). A band
# outside its mode's range where another mode of the group holds it is information, and only where its sentence makes ONE
# assignment — on the corpus the out-of-range positions from longer sentences were the reader's pairing, not the paper's.
ORDERED = ('SO4', 'PO4', 'CO3', 'UO2')      # SiO4 left out: Si–O–Si of a polymerised silicate is not the tetrahedron's ν1 / ν3
RANGE_GROUPS_OUT = ('SiO4',)                # ranges by polymerisation are not in the library yet (orthosilicate values misjudge a sheet's)
LIB_MEASURED = 8                            # a range is used only if verified (no 'check' tag) or measured on this many papers
RANGE_SLACK = 25.0          # cm⁻¹ beyond the library's range (literature range ∪ measured 5–95 % window)
_SKIP_FAM = ('M-O', 'lattice', 'overtone', 'other', 'CH')


def _lib_range(fam, modes, technique=None, trusted=False):
    from pxrd_review import bands as BL
    rows = [r for r in BL.expected(groups=[fam], technique=technique) if r['mode'] in modes] or \
        [r for r in BL.expected(groups=[fam]) if r['mode'] in modes]
    if trusted:                                 # verified, or measured on enough papers: a range entered from memory judges nothing
        rows = [r for r in rows if not r.get('check') or ((r.get('published') or {}).get('papers') or 0) >= LIB_MEASURED]
    if not rows:
        return None
    lo = min(min(r['lo'], (r.get('published') or {}).get('p5') or r['lo']) for r in rows)
    hi = max(max(r['hi'], (r.get('published') or {}).get('p95') or r['hi']) for r in rows)
    return lo, hi


def _lib_modes(mode):
    return {'ν%d' % mode} if isinstance(mode, int) else {'stretch': {'ν1', 'ν3', 'stretch'}, 'bend': {'ν2', 'ν4', 'bend'}}.get(mode, {mode})


def _near_copy(a, b):
    """Two sentences that are one (a caption repeated in the text): most of their words shared."""
    wa, wb = set(re.findall(r'[a-z]{3,}', a.lower())), set(re.findall(r'[a-z]{3,}', b.lower()))
    return bool(wa and wb) and len(wa & wb) >= 0.9 * max(len(wa), len(wb)) and set(re.findall(r'\d{3,4}', a)) == set(re.findall(r'\d{3,4}', b))


def assignment_lines(own):
    """Lines on the paper's own band assignments set against each other and against the mode's range (see above)."""
    own = [b for b in own if b.own and b.family and b.mode and b.family not in _SKIP_FAM]
    lines = []
    for fam in ORDERED:
        n1 = sorted({b.pos for b in own if b.family == fam and b.mode == 1})
        n3 = sorted({b.pos for b in own if b.family == fam and b.mode == 3})
        reg = _lib_range(fam, {'ν1', 'ν3'})
        if not (n1 and n3 and reg):
            continue
        inside = lambda p: reg[0] - 60 <= p <= reg[1] + 60
        if all(inside(p) for p in n1 + n3) and max(n3) < min(n1):
            b1 = next(b for b in own if b.family == fam and b.mode == 1)
            lines.append('mode order: ν1 of %s at %s cm⁻¹ vs ν3 at %s cm⁻¹ — the symmetric stretch stands above every antisymmetric one, '
                         'where in %s it lies below: the two labels look swapped ‘%s’' % (fam, ', '.join('%g' % p for p in n1), ', '.join('%g' % p for p in n3), fam,
                                                                                        _short(b1.sentence, '%g' % b1.pos, 80)))
    said = set()
    for b in own:
        if (b.pos, b.family, b.mode) in said or b.family in RANGE_GROUPS_OUT:
            continue
        asg = _assignments(b.sentence)
        if len(asg) != 1:
            continue
        a0 = asg[0]
        # a second mode word with no group of its own ('… correspond to symmetric stretching, whereas … antisymmetric
        # stretching of SO4'), or an exception / a negation in the sentence: the pairing is not the paper's to be judged on
        if any(not (a0[0] - 30 <= m.start() <= a0[1] + 30) for m in _MODE_WORD.finditer(b.sentence)) or \
                re.search(r'\bexception\b|\bexcept\b|\bno bands?\b|\bnot\b|\bwithout\b|\babsen', b.sentence, re.I):
            continue
        rg = _lib_range(b.family, _lib_modes(b.mode), b.technique, trusted=True)
        if not rg or rg[0] - RANGE_SLACK <= b.pos <= rg[1] + RANGE_SLACK:
            continue
        alt = []
        for m_ in ('ν1', 'ν2', 'ν3', 'ν4', 'stretch', 'bend', 'lib'):
            if m_ in _lib_modes(b.mode):
                continue
            g = _lib_range(b.family, {m_}, b.technique, trusted=True)
            if g and g[0] - 10 <= b.pos <= g[1] + 10:
                alt.append('%s (%g–%g cm⁻¹)' % (m_, g[0], g[1]))
        if not alt:
            continue
        said.add((b.pos, b.family, b.mode))
        lines.append("mode: the band at %g cm⁻¹ is assigned to %s, whose range in minerals is %g–%g cm⁻¹; %s of the same group holds it (information) ‘%s’"
                     % (b.pos, _mode_name(b.family, b.mode).strip(), rg[0], rg[1], ' or '.join(alt), _short(b.sentence, '%g' % b.pos, 80)))
    seen = {}
    for b in own:
        seen.setdefault(b.pos, []).append(b)
    for pos, bs in sorted(seen.items()):
        kinds = {}
        for b in bs:
            kinds.setdefault((b.family, b.mode), b)
        kinds = {k: v for k, v in kinds.items() if isinstance(k[1], int)}
        sents = [b.sentence for b in kinds.values()]
        # two NUMBERED modes of ONE group, in two sentences that are not copies of each other ('ν4 … 435 and 428' in one,
        # 'ν2 … 435 and 428' in the next); a plain 'stretch' beside a ν3 says the same thing; two groups are the reader's
        # business more often than the paper's (overlapping bands of two groups, a second mineral)
        if len(kinds) < 2 or len({f for f, _m in kinds}) != 1 or len(set(sents)) < 2 or any(x.startswith('table row') for x in sents) \
                or _near_copy(sents[0], sents[1]):
            continue
        (a, b1), (c, b2) = list(kinds.items())[:2]
        lines.append("mode: the band at %g cm⁻¹ is assigned to %s in one place and to %s in another (information) ‘%s’ ‘%s’"
                     % (pos, _mode_name(*a).strip(), _mode_name(*c).strip(), _short(b1.sentence, '%g' % pos, 60), _short(b2.sentence, '%g' % pos, 60)))
    return lines


def _mode_name(fam, mode):
    return '%s %s' % ('ν%d' % mode if isinstance(mode, int) else (mode or ''), fam)


def table_lines(tbands, pbands):
    """An assignment table beside the prose, and against itself -> lines (information): a band the table gives to one
    group or mode and the text to another; within the table, a stretching mode of a group standing below one of its
    bending modes."""
    lines = []
    done = set()
    for t in tbands:
        if not t.family or not t.own:
            continue
        for p in pbands:
            if not p.own or not p.family or abs(p.pos - t.pos) > 1.0 or (t.pos, p.family, p.mode) in done:
                continue
            both_num = isinstance(t.mode, int) and isinstance(p.mode, int)
            if p.family in _BOND_KINDS or t.family in _BOND_KINDS or {p.family, t.family} == {'OH', 'H2O'}:
                continue
            if p.family != t.family or (both_num and p.mode != t.mode):
                done.add((t.pos, p.family, p.mode))
                lines.append("table: the band at %g cm⁻¹ is %s in the table and %s in the text (information) ‘%s’" % (t.pos, _mode_name(t.family, t.mode).strip(), _mode_name(p.family, p.mode).strip(), _short(p.sentence, '%g' % p.pos, 90)))
    by = {}
    for t in tbands:
        if t.family in TET + ('CO3', 'UO2') and isinstance(t.mode, int):
            by.setdefault(t.family, {}).setdefault(t.mode, []).append(t.pos)
    for fam, m in by.items():
        stretch = [(p, k) for k in (1, 3) for p in m.get(k, [])]; bend = [(p, k) for k in (2, 4) for p in m.get(k, [])]
        if stretch and bend and min(stretch)[0] < max(bend)[0]:
            lo, hi = min(stretch), max(bend)
            lines.append('table: ν%d of %s at %g cm⁻¹ stands below ν%d at %g cm⁻¹ — a stretching mode under a bending mode of the same group (information)' % (lo[1], fam, lo[0], hi[1], hi[0]))
    return lines


# ----------------------------------------------------------------------------- the structure side

URANYL_MAX = 1.95       # Å: a uranyl U–O is shorter
URANYL_ANGLE = 165.0    # ° O–U–O
URANYL_GAP = 0.20       # Å between the second and the third shortest U–O
BC_APART = 0.05         # Å: the inferred and the refined uranyl distance this far apart is worth a word — twice the
                        # scatter of the relation against the refined distances of the papers that give both (0.025 Å)
LIB_APART = 0.15        # Å: a stated O–H band whose distance lies this far outside the structure's D···A range
LIB_MIN_OO = 2.45       # Å: the shortest O···O the curve is asked about (below it the wavenumber it gives is no stretch)


def uranyl_sites(st):
    """[(U site, [d1, d2], mean)] — each symmetry-independent U site that carries a uranyl ion: two O within
    1.95 Å, near-linear, and set apart from the equatorial bonds."""
    from pxrd_review import bv_check as B
    out = []
    oxy = [s for s in st.sites if s.element == 'O']
    for site in st.sites:
        if site.element != 'U':
            continue
        near = st.images(site.positions[0], 2.75, oxy)
        if len(near) < 4:
            continue
        (_o1, d1, p1), (_o2, d2, p2) = near[0], near[1]
        if d2 > URANYL_MAX or near[2][1] - d2 < URANYL_GAP:
            continue
        if B.angle(st, p1, site.positions[0], p2) < URANYL_ANGLE:
            continue
        out.append((site, [d1, d2], (d1 + d2) / 2.0))
    return out


def hbond_distances(st):
    """[(donor label, acceptor label, d(D···A), how)] — the O–H···O hydrogen bonds of a structure whose H are
    located (the .cif's own loop, else its H positions); [] when it locates none."""
    from pxrd_review import bv_check as B
    out = []; seen = set()
    for g in B.hbond_geometry(st):
        if g['da_val'] is None or g['D'].element != 'O' or g['A'].element != 'O':
            continue
        key = (g['D'].label, g['A'].label, round(g['da_val'], 3))
        if key in seen:
            continue
        seen.add(key)
        out.append((g['D'].label, g['A'].label, g['da_val'], 'loop' if g['from_loop'] else 'H'))
    return out


def structure_distances(cif):
    """{'uranyl': [(label, [d1, d2], mean)], 'hbonds': [(D, A, d, how)], 'source'} from a .cif."""
    from pxrd_review import bv_check as B
    st = B.Structure(cif)
    return {'uranyl': [(s.label, ds, m) for s, ds, m in uranyl_sites(st)], 'hbonds': hbond_distances(st), 'source': 'the .cif'}


def bond_table_distances(path, ex=None, text=None):
    """The same from the bond distances the paper prints (no .cif): the two shortest U–O of each U, set apart
    from the rest — there are no angles to test and no hydrogen bonds to read."""
    from pxrd_review import paper_bonds as PB
    _st, result, _gii = PB.structure_for(path, ex, text)
    ur = []
    for row in result or []:
        c, bonds = row[0], row[1]
        if getattr(c, 'element', None) != 'U':
            continue
        ds = sorted(d for b in bonds for d in [b.dist] * max(1, int(round(b.count or 1))))
        if len(ds) >= 4 and ds[1] <= URANYL_MAX and ds[2] - ds[1] >= URANYL_GAP:
            ur.append((c.label, ds[:2], (ds[0] + ds[1]) / 2.0))
    return {'uranyl': ur, 'hbonds': [], 'source': 'the bond table the paper prints'} if ur else None


def _span(lo, hi, fmt):
    a, b = fmt % lo, fmt % hi
    return a if a == b else '%s–%s' % (a, b)


def structure_lines(structure, nu1, nu3, oh):
    """What the structure says beside the spectrum — information, never a finding: either relation scatters by
    more than the differences it would be asked to judge."""
    lines = []
    src = structure.get('source') or 'the structure'
    ur = structure.get('uranyl') or []
    if ur and (nu1 or nu3):
        means = [m for _l, _ds, m in ur]
        inferred = [('ν1', p, bc_nu1(p)) for p in nu1] + [('ν3', p, bc_nu3(p)) for p in nu3]
        far = [x for x in inferred if min(abs(x[2] - m) for m in means) >= BC_APART]
        lines.append('uranyl: mean U–O %s Å%s in %s; %s Å by %s%s (information)' % (
            ', '.join('%.3f' % m for m in means[:6]) + (' …' if len(means) > 6 else ''), ' (one per independent ion)' if len(means) > 1 else '',
            src, ', '.join('%s %g cm⁻¹ gives %.2f' % x for x in inferred[:6]), BC,
            ' — %s lie%s %.2f Å or more from every refined ion, where ν1 would stand at %s cm⁻¹' % (
                ', '.join('%s %g' % (x[0], x[1]) for x in far[:4]), 's' if len(far) == 1 else '', BC_APART,
                _span(bc_nu1_inv(max(means)), bc_nu1_inv(min(means)), '%.0f')) if far else ''))
        distinct = sorted({round(m, 2) for m in means})
        if len(ur) >= 2 and len(nu1) == 1 and distinct[-1] - distinct[0] >= 0.02:
            lines.append('uranyl: %d independent ions in %s (mean U–O %s Å) and one ν1 band stated (%g cm⁻¹) — by %s their ν1 lie %.0f cm⁻¹ apart (information)' % (
                len(ur), src, _span(distinct[0], distinct[-1], '%.2f'), nu1[0], BC, abs(bc_nu1_inv(distinct[-1]) - bc_nu1_inv(distinct[0]))))
        elif len(ur) == 1 and len(nu1) >= 2:
            lines.append('uranyl: %d ν1 bands stated (%s cm⁻¹) for the one independent ion of %s (information)' % (len(nu1), ', '.join('%g' % p for p in nu1[:5]), src))
    hb = [d for _D, _A, d, _h in (structure.get('hbonds') or []) if LIB_MIN_OO <= d <= 3.3]
    if hb and oh:
        lo, hi = min(hb), max(hb)
        got = [lib_d(p) for p in oh if p < LIB_FREE_OO]
        # a stated band that answers to a bond the structure has none near; a bond with no band stated is ordinary
        # (the weak and the overlapped are not listed)
        far = [p for p in oh if p < LIB_FREE_OO and (lo - lib_d(p) >= LIB_APART or lib_d(p) - hi >= LIB_APART)]
        lines.append('hydrogen bonds: %d in %s, D···A %s Å — O–H stretches expected at %s cm⁻¹ by %s; the stated O–H bands (%s cm⁻¹) answer to %s%s (information)' % (
            len(hb), src, _span(lo, hi, '%.2f'), _span(lib_nu(lo), lib_nu(hi), '%.0f'), LIB, ', '.join('%g' % p for p in oh[:8]) + (' …' if len(oh) > 8 else ''),
            (_span(min(got), max(got), '%.2f') + ' Å') if got else 'no distance (above %g cm⁻¹)' % LIB_FREE_OO,
            ' — %s cm⁻¹ answer%s to a distance %.2f Å or more outside that range' % (', '.join('%g' % p for p in far[:4]), 's' if len(far) == 1 else '', LIB_APART) if far else ''))
    return lines


# ----------------------------------------------------------------------------- the band windows

WINDOWS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'band_windows.json')


@functools.lru_cache(maxsize=1)
def band_windows():
    """{'SO4 ν1': {'any' | 'raman' | 'ir': {'n', 'papers', 'p5', 'p25', 'p50', 'p75', 'p95'}}} — where published
    mineral descriptions place each band (data/band_windows.json, built by tools/corpus_spectra.py); {} without it."""
    try:
        with open(WINDOWS_FILE, encoding='utf-8') as f:
            return json.load(f).get('windows') or {}
    except (OSError, ValueError):
        return {}


def suggest(pos, technique=None):
    """[(assignment, window)] — the groups and modes whose window (5th–95th percentile of the published positions)
    holds a band at `pos`, the one whose median is nearest first. A suggestion for a reader to weigh, never an
    assignment: windows of different groups overlap wherever their bands do."""
    out = []
    for name, entry in band_windows().items():
        w = entry.get(technique) or entry.get('any')
        if w and w['p5'] <= pos <= w['p95']:
            out.append((abs(pos - w['p50']) / max(1.0, w['p75'] - w['p25']), name, w))
    return [(name, w) for _d, name, w in sorted(out, key=lambda x: (x[0], x[1]))]


# ----------------------------------------------------------------------------- CLI

def review(path, cif=None):
    """{'bands': [Band], 'claims': [...], 'lines': [...]} for a manuscript .docx or a paper .pdf."""
    from pxrd_review import paper_extract as PE
    text = PE.text_of(path)
    return {'bands': bands(text) + table_bands(path, PE.mineral_name(text)), 'claims': check_claims(text), 'lines': check_lines(text, cif=cif, path=path)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('path', help='the manuscript .docx or the paper .pdf')
    ap.add_argument('--cif', help='the structure, for the distances the spectrum is set beside')
    ap.add_argument('--bands', action='store_true', help='list every band read, with its assignment')
    a = ap.parse_args(argv)
    if not os.path.exists(a.path):
        raise SystemExit('pxrd spectro: no such file: %s' % a.path)
    r = review(a.path, a.cif)
    print('SPECTROSCOPY — %s' % os.path.basename(a.path))
    if a.bands:
        for b in r['bands']:
            print('  %7g  %-5s %-8s %-8s %s%s' % (b.pos, b.technique or '', b.family or '', 'ν%d' % b.mode if isinstance(b.mode, int) else (b.mode or ''), b.shape,
                                               '' if b.own else '  (another work\'s value)'))
    if not r['lines']:
        print('  %d bands read; no distance is credited to %s or to %s, there is no structure to set them beside, and the formula raises nothing' % (len(r['bands']), BC, LIB))
        return 0
    print('  ' + r['lines'][0])
    for ln in r['lines'][1:]:
        print('    ' + ln)
    return 0


if __name__ == '__main__':
    sys.exit(main())
