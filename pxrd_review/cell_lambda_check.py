#!/usr/bin/env python3
"""
ICDD PXRD review helper — cell-parameter & wavelength comparator (prototype).

Compares the Author's Cell (a,b,c,alpha,beta,gamma,space group,Z) and the
radiation wavelength entered in an entry .docx against the values reported in
the source .pdf article.

Design notes grounded in real batch data:
  * Papers commonly report TWO unit cells: one refined from POWDER data and one
    from SINGLE-CRYSTAL data. The PXRD entry should normally use the powder
    cell. When it uses the single-crystal cell even though a powder cell is
    available, that is flagged for human judgement (sometimes fine, sometimes
    not — the reviewer decides).
  * Radiation has the same trap: powder runs may use a different anode (e.g.
    FeKa) than the single-crystal instrument (e.g. MoKa).
  * Tracked-change insertions split numbers across runs, so docx values are
    read with insertions applied, deletions dropped, and inter-run spaces
    removed.

We do NOT check diffractometer / camera type (per reviewer instruction).

Usage:
    python3 -m pxrd_review.cell_lambda_check /path/to/entries
    python3 -m pxrd_review.cell_lambda_check /path/to/entries --id Innnnnn
"""
import sys, os, re, glob, zipfile, argparse
from xml.etree import ElementTree as ET
from collections import namedtuple

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
def _t(e): return e.tag.replace(W, '')

# ----------------------------------------------------------------------------- docx parsing
def cell_value(tc):
    """Text of a table cell with tracked insertions kept, deletions dropped,
    and inter-run whitespace removed (so a split number like 7.0895(1 2 7)
    becomes 7.0895(127))."""
    parts = []
    for el in tc.iter():
        tag = _t(el)
        if tag == 'delText':
            continue                      # dropped: this text was deleted by a reviewer
        if tag == 't':
            parts.append(el.text or '')
    s = ''.join(parts)
    return s

def docx_rows(path):
    root = ET.fromstring(zipfile.ZipFile(path).read('word/document.xml'))
    rows = []
    for tr in root.iter(W + 'tr'):
        rows.append([cell_value(tc) for tc in tr.findall(W + 'tc')])
    return rows

NUM = r'-?\d{1,4}(?:\.\d+)?(?:\(\d+\))?'   # 6.3032(6) / 90 / 120.000

def num_val(s):
    """Strip esd parens & spaces -> float, or None."""
    if s is None: return None
    s = re.sub(r'\s+', '', s)
    m = re.match(r'(-?\d+(?:\.\d+)?)', re.sub(r'\(\d+\)', '', s))
    return float(m.group(1)) if m else None

def split_num(s):
    """'7.08950(12)' -> (value_float, mantissa_str, esd_str, n_decimals).
    mantissa keeps trailing zeros (needed for the precision check)."""
    if s is None: return (None, '', '', None)
    s = re.sub(r'\s+', '', s)
    em = re.search(r'\((\d+)\)', s); esd = em.group(1) if em else ''
    mant = re.sub(r'\(\d+\)', '', s)
    m = re.match(r'-?\d+(?:\.\d+)?', mant)
    if not m: return (None, '', esd, None)
    mant = m.group(0)
    dec = len(mant.split('.')[1]) if '.' in mant else 0
    return (float(mant), mant, esd, dec)

def axis_issues(dv, pv):
    """Compare one docx-vs-pdf parameter (e.g. a, or beta). Returns a list of
    (kind, note); kind in {'value','precision','esd'}. Empty = clean match.
    Priorities reflect the reviewer: matching numbers, correct significant
    figures, and correct error (esd) values."""
    dval, dman, desd, ddec = split_num(dv)
    pval, pman, pesd, pdec = split_num(pv)
    if dval is None or pval is None: return []
    out = []
    common = min(ddec, pdec)
    if round(dval, common) != round(pval, common):
        out.append(('value', 'docx=%s  pdf=%s' % (dman, pman)))
        return out                       # value wrong -> esd/precision moot
    if ddec != pdec:                     # agree at common precision but sig-figs differ
        out.append(('precision', 'docx %d dp (%s)  vs  pdf %d dp (%s)' % (ddec, dman, pdec, pman)))
    if desd and pesd and desd != pesd:   # error value differs (only when both parsed)
        out.append(('esd', 'docx (%s)  vs  pdf (%s)' % (desd, pesd)))
    return out

def parse_comments(path):
    """Reviewer comments from word/comments.xml -> [(author, text)]."""
    z = zipfile.ZipFile(path)
    if 'word/comments.xml' not in z.namelist(): return []
    root = ET.fromstring(z.read('word/comments.xml'))
    out = []
    for c in root.iter(W + 'comment'):
        txt = ''.join(t.text or '' for t in c.iter() if _t(t) == 't').strip()
        if txt: out.append((c.get(W + 'author', '?'), txt))
    return out

DocxData = namedtuple('DocxData', 'authors_cell crystal_cell radiation lam raw_cell raw_lam comments')

def parse_docx(path):
    rows = docx_rows(path)
    ac = cc = None; anode = None; lam = None; raw_cell = raw_lam = None
    for r in rows:
        cells = [re.sub(r'\s+', '', c) for c in r]
        if not cells: continue
        head = cells[0]
        if head.startswith("Author'sCell") or head.startswith("Author"):
            ac = cells[1:9]; raw_cell = r[1:9]
        elif head.startswith('CrystalCell'):
            cc = cells[1:9]
        if 'Radiation=' in head or head == 'Radiation':
            # row: Radiation = | FeKa | l = | 1.54184 | ...
            joined = r
            anode = joined[1].strip() if len(joined) > 1 else None
            # find the wavelength: cell after the one containing 'l ='
            for i, c in enumerate(joined):
                if re.sub(r'\s+', '', c).lower().startswith('l='):
                    if i + 1 < len(joined):
                        lam = re.sub(r'\s+', '', joined[i + 1]); raw_lam = joined[i + 1]
                    break
    return DocxData(ac, cc, anode, lam, raw_cell, raw_lam, parse_comments(path))

# ----------------------------------------------------------------------------- pdf parsing
# Ligatures PyMuPDF leaves as single glyphs ('speciﬁc'→'specific', 'reﬂection'→
# 'reflection'); they silently break every word/keyword search that crosses them.
_LIGATURES = {'ﬁ': 'fi', 'ﬂ': 'fl', 'ﬀ': 'ff', 'ﬃ': 'ffi', 'ﬄ': 'ffl', 'ﬆ': 'st', 'ﬅ': 'ft'}
# Dash glyphs (hyphen-variants, en/em dash, minus) used WITHIN a word; canonicalised
# to ASCII '-' so 'Debye–Scherrer' matches 'Debye-Scherrer' and 'Bragg–Brentano' too.
_WORD_DASH = re.compile(r'(?<=[A-Za-z])[‐‑‒–—−](?=[A-Za-z])')

def _norm_pdf(s):
    """Repair the predictable damage PyMuPDF leaves in extracted text, ONCE at the
    source, so every downstream check reads clean words (it is line-structure
    preserving — the vertical-table parsers still see their newlines). Validated
    against the corpus: lifts the DC-term↔PDF match rate substantially. Fixes:
      • '¼'→'=' and 'þ'→'+' (font mojibake: in several journals the '=' glyph extracts
        as '¼' and the superscript-charge '+' as 'þ' — 'Fe3þ'→'Fe3+', '[4þ1þ1]'→'[4+1+1]');
      • the 'A˚'/'A ˚'/decomposed-ring angstrom glyph → 'Å';
      • exotic Unicode spaces (nbsp, thin/en/hair space) → a normal space (newlines kept);
      • ligatures ('speciﬁc'→'specific') and soft hyphens;
      • line-break hyphenation ('microdif-\\nfractometer'→'microdiffractometer',
        'pow-\\nder'→'powder') — the dominant artifact behind powder/single misses;
      • word-internal en/em/minus dashes → '-' ('Debye–Scherrer'→'Debye-Scherrer');
      • esds that extract with a stray space ('8.8593 (2)'→'8.8593(2)')."""
    s = s.replace('¼', '=').replace('þ', '+')
    s = re.sub(r'[\u00a0\u2000-\u200a\u202f\u205f]', ' ', s)   # special spaces -> normal (keep \n)
    s = re.sub(r'A ?˚', 'Å', s).replace('Å', 'Å')
    for lig, rep in _LIGATURES.items():
        s = s.replace(lig, rep)
    s = s.replace('­', '')                          # discretionary/soft hyphen
    # rejoin a word split across a line by a hyphen: only lowercase→lowercase, so
    # 'X-\nray' and line-broken proper nouns keep their hyphen.
    s = re.sub(r'([a-z])-\n[ \t]*([a-z])', r'\1\2', s)
    s = _WORD_DASH.sub('-', s)
    s = re.sub(r'(?<=\d)\s+\((\d{1,3})\)', r'(\1)', s)   # '8.8593 (2)' -> '8.8593(2)'
    return s

def pdf_text(path):
    import fitz
    with fitz.open(path) as doc:                  # close the handle (was leaked)
        return _norm_pdf('\n'.join(p.get_text() for p in doc))

# `phase` tags a cell with the mineral name it sits under (multi-phase papers list
# several cells; the phase name disambiguates which belongs to the entry under
# review). Defaults None so existing CellCand(...) calls are unaffected.
CellCand = namedtuple('CellCand', 'a b c al be ga V Z context pos snippet phase',
                      defaults=(None,))

POWDER_KW = ['powder', 'pxrd']
SINGLE_KW = ['single-crystal', 'single crystal', 'single‑crystal', 'singlecrystal', 'scxrd']

# Instrument/geometry lexicon mined from 221 reviewer-written DC ('Data Collection')
# fields and validated against the paired PDFs: each term, when present, IMPLIES the
# experiment mode even though the bare word 'powder'/'single-crystal' may be absent.
# Restricted to MODE-DETERMINING terms only — the GEOMETRY/MOTION, never the instrument
# MODEL, because nearly every modern area-detector diffractometer is DUAL-USE:
#   • A Debye-Scherrer / Gandolfi / Bragg-Brentano (or pseudo-Gandolfi / Gandolfi-like
#     MOTION) signature = powder; a kappa / four-circle goniometer = single-crystal.
#   • 'gandolfi' (substring) already covers 'pseudo-Gandolfi' and 'Gandolfi-like'.
#   • NO single-crystal MODEL names: Photon II/III, XtaLAB/Synergy, Xcalibur, Apex, D8
#     Venture, R-AXIS Rapid II all run pseudo-Gandolfi/Gandolfi-like scans to collect
#     POWDER on a traditionally single-crystal area-detector instrument (per the task-
#     group experts; R-AXIS Rapid II mislabelled a single-crystal cell as powder in
#     I002535). So a model name can't fix the mode — only the geometry/motion word can.
#   • Powder side keeps DEDICATED Bragg-Brentano benchtop/floor diffractometers (D8
#     Advance/Discover, Empyrean), which have no single-crystal capability — the asymmetry
#     is real: powder-only instruments exist, single-crystal-only area instruments don't.
#   • Excludes source terms 'rotating anode'/'microfocus' (moabite's POWDER used both).
# Also REFINEMENT-SOFTWARE / METHOD cues, which (unlike the instruments) ARE mode-
# determining — Rietveld is a powder method by definition, and SHELX/OLEX refine a
# single-crystal STRUCTURE (no powder mode). Validated by mining the cue's context across
# the paired PDFs. Excludes software that does BOTH powder & single (JANA — both
# Jana2006 and Jana2020 — and SUPERFLIP) and SAINT (Bruker integration). Per the experts,
# the CrysAlisPro and Bruker APEX SUITES primarily do single-crystal workup, so they ARE
# single cues — the version digit ('apex3'..'apex6') separates the software from the dual-use
# 'Apex II'/'Apex DUO' INSTRUMENT, and the one-sided rule drops to None on a genuine pseudo-
# Gandolfi paper (which also carries a powder cue). For a cue whose bare alnum-canon form
# collides with a common word/mineral, use a longer CHARACTERISTIC snippet that the
# collider can't contain (these names are versioned/suffixed consistently across papers):
# JADE→'jade2010'/'jadepro'/'jade9' (not in 'jadeite'); SIR→'sir2011'/… (versioned);
# X'Celerator→'xceler' (not in 'accelerator'). Genuinely stuck (no distinguishing snippet,
# so omitted): X'Pert ('expert' contains 'xpert'; empyrean covers PANalytical powder) and
# 'unitcell' (canon == the phrase 'unit cell'). Matched separator-blind (see _instr_mode).
POWDER_INSTR = ['debye-scherrer', 'gandolfi', 'bragg-brentano', 'd8 advance', 'd8 discover', 'empyrean',
                'rietveld', 'le bail', 'pawley', 'gsas', 'expgui', 'fullprof', 'rietan', 'topas',
                'dicvol', 'chekcell',
                # profile/whole-pattern fitting (powder) + powder analysis software + 1D
                # powder strip detectors (NOT area detectors, so not the dual-use trap).
                # 'xceler' = PANalytical X'Celerator; the X'-prefix makes it unique so it
                # does NOT collide with 'accelerator' (bare 'celerator' would):
                'profile fit', 'whole-pattern', 'highscore', 'lynxeye', 'mythen', 'xceler',
                # MDI JADE (powder analysis/Rietveld) via its versioned forms — collision-safe
                # vs 'jadeite' (96 powder contexts in the corpus, 0 in jadeite):
                'jade2010', 'jadepro', 'jade9', 'mdijade',
                # Osc2tab/Osc2xrd (Britvin) — derive a POWDER pattern from single-crystal
                # area-detector frames; the OUTPUT is always a PXRD pattern (powder-method
                # software, not a dual-use instrument). Used widely by the Russian new-
                # mineral groups; found only by open-ended discovery, not a fixed cue list.
                'osc2tab', 'osc2xrd']
SINGLE_INSTR = ['four-circle', 'three-circle', 'kappa', 'shelx', 'olex', 'sadabs',
                # SIR direct-methods (single-crystal structure solution) — always versioned,
                # so 'sir2011'/… are unique (bare 'sir' would collide):
                'sir92', 'sir97', 'sir2004', 'sir2008', 'sir2011', 'sir2014', 'sir2019',
                # CrysAlisPro (Rigaku/Oxford) + Bruker APEX software suite — primarily single-
                # crystal data workup. 'crysalis' covers CrysAlis/CrysAlisPro (not 'chrysalis');
                # 'apex<digit>' is the software (vs the dual-use 'Apex II'/'DUO' instrument):
                'crysalis', 'apex2', 'apex3', 'apex4', 'apex5', 'apex6']

# PDF line-break hyphenation splits a word as 'pow-\nder'; after a whitespace collapse
# that reads 'pow- der', so a substring search for 'powder' (or 'single-crystal') misses
# it. Normalise a context haystack before the keyword search: rejoin a soft hyphen
# between two lowercase letters ('pow- der'→'powder', 'single- crystal'→'singlecrystal'
# — hence the no-separator SINGLE_KW form above; 'X-ray', 'semi-cylindrical', en-dashes
# and number ranges are untouched), then collapse whitespace so a multi-word cue like
# 'single crystal' still matches when a newline fell between the two words.
def _norm_ctx(s):
    s = s.lower()
    s = re.sub(r'([a-z])-\s+([a-z])', r'\1\2', s)
    return re.sub(r'\s+', ' ', s)

# A 'calculated/simulated [X-ray] powder/PXRD' pattern is generated from the (single-crystal)
# structure — e.g. exported by a visualizer (Mercury, PLATON, CrystalDiffract) — not a powder
# experiment, so it must not count as powder context (mirrors the 'calc' sentence skip in
# radiation_context). Covers both 'powder' and 'pxrd'. Anchored on 'calculat'/'simulat', NOT
# bare 'calc\\w*' which also swallowed 'calcined powder' (a real heat-treated powder sample).
# 'calculated and observed powder profiles' (a genuine Rietveld fit) keeps its 'powder' since
# the 'and observed' breaks the adjacency. Used by classify_context before the keyword search.
_CALC_POWDER = re.compile(r'(?:calculat|simulat)\w*\s+(?:x[- ]?ray\s+)?(?:powder|pxrd)')

def _nearest(hay, keys):
    """smallest distance from the END of `hay` to any keyword (for preceding
    text) — i.e. how far back the keyword is."""
    best = None
    for kw in keys:
        i = hay.rfind(kw)
        if i != -1:
            d = len(hay) - i
            if best is None or d < best: best = d
    return best

def _nearest_fwd(hay, keys):
    best = None
    for kw in keys:
        i = hay.find(kw)
        if i != -1 and (best is None or i < best): best = i
    return best

def _canon(s):
    """alnum-only lowercase — erases hyphen/space/dash typography so an instrument
    term matches regardless of how the PDF split it ('D8 Venture'/'D8-Venture')."""
    return re.sub(r'[^a-z0-9]', '', s.lower())
_POWDER_INSTR_C = [_canon(t) for t in POWDER_INSTR]
_SINGLE_INSTR_C = [_canon(t) for t in SINGLE_INSTR]

def _instr_mode(win):
    """Mode inferred from the instrument/geometry lexicon — ONE-SIDED only: returns
    'powder'/'single' when the window names a mode-specific instrument for just ONE
    mode, else None. Conservative by design (a window naming BOTH instruments stays
    unknown rather than guessing); used only as a fallback when no explicit powder/
    single word sits near the cell, so a paper that states its geometry/instrument but
    not the bare word — incl. non-English papers, where brand names stay Latin — still
    classifies."""
    cw = _canon(win)
    pw = any(t in cw for t in _POWDER_INSTR_C)
    sg = any(t in cw for t in _SINGLE_INSTR_C)
    if pw == sg:
        return None
    return 'powder' if pw else 'single'

def radiation_context(text, pos):
    """Context for a RADIATION token. A radiation is attached to a COLLECTION verb
    whose grammatical SUBJECT sets the mode, so prefer the sentence's FIRST XRD-mode
    keyword over the nearest one: '… Powder XRD data were collected … on the same
    instrument as single-crystal XRD data were collected, using CuKα …' is a POWDER
    statement even though 'single-crystal' sits nearer the token. Falls back to the
    position-based classify_context. Skips a 'calculated' sentence (the powder there
    is modelled from the single-crystal structure, not collected with this anode)."""
    start = text.rfind('.', 0, pos) + 1
    end = text.find('.', pos); end = len(text) if end == -1 else end
    sent = _norm_ctx(text[start:end])
    if 'calc' not in sent:
        p, s = _nearest_fwd(sent, POWDER_KW), _nearest_fwd(sent, SINGLE_KW)
        if p is not None and (s is None or p < s):
            return 'powder'
    return classify_context(text, pos)

def classify_context(text, pos, pre=750, post=200):
    """Classify the cell at `pos` as powder / single / unknown. A cell is
    almost always introduced by a clause that PRECEDES it ('refined from the
    powder data ... a = ...'), so preceding text wins; following text is only a
    fallback. `text`/`pos` must be the same string the offset came from."""
    before = _CALC_POWDER.sub('calc', _norm_ctx(text[max(0, pos - pre):pos]))
    after = _CALC_POWDER.sub('calc', _norm_ctx(text[pos:pos + post]))
    p, s = _nearest(before, POWDER_KW), _nearest(before, SINGLE_KW)
    if p is not None or s is not None:
        if s is None: return 'powder'
        if p is None: return 'single'
        return 'powder' if p <= s else 'single'
    p, s = _nearest_fwd(after, POWDER_KW), _nearest_fwd(after, SINGLE_KW)
    if p is None and s is None:
        # no explicit powder/single word near the cell — fall back to the mined
        # instrument/geometry lexicon (preceding text wins, then following).
        return _instr_mode(before) or _instr_mode(after) or 'unknown'
    if s is None: return 'powder'
    if p is None: return 'single'
    return 'powder' if p <= s else 'single'

def find_cells_table(text):
    """Vertical label/value tables: a line that is JUST an axis/angle label
    ('a (Å)', 'b (Å)', 'c (Å)' …) immediately followed by a numeric line — the
    layout of many Rietveld-refinement tables, where the inline-narrative
    parser finds nothing.  Handles the 'β' → 'b'/'ß' mojibake: β is often
    re-labelled 'b (Å)' a second time and recognised here as the off-90 angle.
    Strict labels (single letter + parenthesised unit) keep it from firing on
    atom-coordinate or composition tables."""
    lines = text.splitlines()
    LBL = re.compile(r'^\s*([abcαβγß])\s*\(\s*(?:Å|°)\s*\)\s*$', re.I)
    VAL = re.compile(r'^\s*(-?\d+(?:\.\d+)?(?:\s*\(\d+\))?)\s*(?:°|Å3?)?\s*$')
    # Record values BY their axis label (not positionally): trigonal/hexagonal
    # tables omit the 'b (Å)' row since b=a, so a positional a/b/c assignment
    # would wrongly put c's value into b. Keep every occurrence per letter.
    occ = {}                                   # letter -> [(value_str, line_index), …]
    for i, ln in enumerate(lines):
        mlbl = LBL.match(ln)
        if not mlbl:
            continue
        letter = mlbl.group(1).lower().replace('ß', 'β')
        for j in range(i + 1, min(i + 3, len(lines))):   # next bare-number line
            v = VAL.match(lines[j])
            if v:
                occ.setdefault(letter, []).append((v.group(1).replace(' ', ''), i))
                break
    def _len(v): vv = num_val(v); return vv is not None and 2.5 <= vv <= 80
    def _ang(v): vv = num_val(v); return vv is not None and 80 < vv <= 180
    def first_len(letter):                     # first length-valued entry for a letter
        for v, li in occ.get(letter, []):
            if _len(v): return v, li
        return None, None
    def first_ang(letters):                    # first angle-valued entry across letters
        for L in letters:
            for v, li in occ.get(L, []):
                if _ang(v): return v
        return None
    a, ali = first_len('a'); b, _ = first_len('b'); c, _ = first_len('c')
    if a is None or c is None:                 # need at least a and c to be a real cell
        return []
    if b is None:                              # uniaxial/cubic: b-row omitted, b = a
        b = a
    # angles: α/β/γ, plus the 'b (°)' β-mojibake captured as an angle-valued 'b'
    al = first_ang(['α']); be = first_ang(['β', 'b']); ga = first_ang(['γ'])
    if be and not al and not ga:               # only β present → monoclinic
        al = ga = '90'
    pos = sum(len(l) + 1 for l in lines[:ali])
    snippet = re.sub(r'\s+', ' ', ' '.join(lines[ali:ali + 8])).strip()
    return [CellCand(a, b, c, al, be, ga, None, None,
                     classify_context(text, pos), pos, snippet)]

# ---- multi-phase table parsers (so a paper describing several minerals exposes
#      EACH phase's cell, tagged with its name, not just the first one found) ----
NAME_RE = r'[A-Z][a-zA-Zü]{3,}(?:-\(?[A-Za-z0-9+]+\)?)?'   # '#mineral', '#mineral-(La)'
SG_TOK  = r'[PCIFRA][0-9\-mcabnd][0-9A-Za-z/\-_]{0,7}'      # 'P21', 'P-1', 'Pnma', 'R-3m', 'C2/c'

def find_cells_named_rows(text):
    """Grid rows led by a phase NAME and space group, then the cell:
    '#mineral† P21 8.8593(2) 8.3846(5) 32.655(4) 97.801(8) 2424(1) 2'. The
    leading name tags the cell so multi-phase comparison tables disambiguate.
    The 4th number here is an angle (β), not V, so the volume-anchored grid
    parser below skips it — this one keys on the name+SG anchor instead.
    Whitespace (incl. newlines) is collapsed so PyMuPDF's one-token-per-line
    table extraction parses the same as an inline row."""
    flat = re.sub(r'\s+', ' ', text)
    pat = re.compile(r'(' + NAME_RE + r')[†*‡§]?\s+(' + SG_TOK + r')\s+'
                     r'((?:' + NUM + r'[ ,]*){3,8})')
    out = []
    for m in pat.finditer(flat):
        nums = re.findall(NUM, m.group(3))
        vals = [num_val(x) for x in nums]
        axes = [nums[i] for i in range(len(nums)) if vals[i] is not None and 2.5 <= vals[i] <= 80]
        if len(axes) < 3:
            continue
        a, b, c = axes[:3]
        angles = [nums[i] for i in range(len(nums)) if vals[i] is not None and 80 < vals[i] <= 180]
        al = be = ga = None
        if len(angles) == 1:   be = angles[0]; al = ga = '90'
        elif len(angles) >= 3: al, be, ga = angles[:3]
        pos = m.start()
        out.append(CellCand(a, b, c, al, be, ga, None, None,
                            classify_context(flat, pos), pos, m.group(0)[:120], phase=m.group(1)))
    return out

def find_cells_multicol(text):
    """Comparison tables with one parameter per ROW and one phase per COLUMN:
    'a (Å) v1 v2 v3 v4  b (Å) w1 w2 w3 w4  c (Å) x1 x2 x3 x4'. Builds one cell per
    column (the inline/vertical parsers only saw the first column). Whitespace
    (incl. newlines) is collapsed so newline-tokenised tables parse too."""
    flat = re.sub(r'\s+', ' ', text)
    seg = re.compile(r'\ba\s*\(\s*Å\s*\)\s*((?:' + NUM + r'[ ,]*){2,8})'
                     r'b\s*\(\s*Å\s*\)\s*((?:' + NUM + r'[ ,]*){2,8})'
                     r'c\s*\(\s*Å\s*\)\s*((?:' + NUM + r'[ ,]*){2,8})')
    out = []
    for m in seg.finditer(flat):
        A = re.findall(NUM, m.group(1)); B = re.findall(NUM, m.group(2)); Cn = re.findall(NUM, m.group(3))
        K = min(len(A), len(B), len(Cn))
        if K < 2:                                   # need ≥2 columns to be a comparison table
            continue
        pos = m.start()
        for i in range(K):
            av = num_val(A[i])
            if av is None or not (2.5 <= av <= 80):
                continue
            out.append(CellCand(A[i], B[i], Cn[i], None, None, None, None, None,
                                classify_context(flat, pos), pos, m.group(0)[:120]))
    return out

def find_cells(text):
    flat = re.sub(r'[\n\r]+', ' ', text)
    flat = re.sub(r'[ \t]+', ' ', flat)
    cands = []
    for m in re.finditer(r'\ba\s*=\s*(' + NUM + r')', flat):
        pos = m.start()
        window = flat[pos:pos + 220]
        def grab(letter, alt=None):
            pat = r'\b' + letter + r'\s*=\s*(' + NUM + r')'
            mm = re.search(pat, window)
            if not mm and alt:
                mm = re.search(alt + r'\s*=\s*(' + NUM + r')', window)
            return mm.group(1).replace(' ', '') if mm else None
        a = m.group(1).replace(' ', '')
        b = grab('b'); c = grab('c')
        al = grab('α', 'alpha'); be = grab('β', 'beta'); ga = grab('γ', 'gamma')
        Vm = re.search(r'\bV\s*=\s*(' + NUM + r')', window)
        Zm = re.search(r'\bZ\s*=\s*(\d+)', window)
        if not (b or c):
            # Cubic/isometric cells are quoted with only 'a' (b=c=a implied).
            # Accept when the surrounding text says so, or V matches a^3.
            before = flat[max(0, pos - 140):pos].lower()
            av, vv = num_val(a), (num_val(Vm.group(1)) if Vm else None)
            cubic = ('cubic' in before or 'isometric' in before or
                     (av and vv and abs(vv - av ** 3) <= 0.03 * vv))
            if not cubic:
                continue           # otherwise need a second axis to be a real cell
            b = c = a
            al = be = ga = '90'
        present = [num_val(x) for x in (a, b, c) if x]
        if present and max(present) < 2.5:   # bond lengths, not a unit cell
            continue
        cands.append(CellCand(a, b, c, al, be, ga,
                              Vm.group(1).replace(' ', '') if Vm else None,
                              Zm.group(1) if Zm else None,
                              classify_context(flat, pos),   # classify on the same flat string
                              pos, flat[max(0, pos - 90):pos + 90]))
    # Chained-equality form (uniaxial): 'a = b = 5.17552(9) Å, c = 14.0584(5) Å'
    # (hexagonal/trigonal/tetragonal) and 'a = b = c = 6.09(1) Å' (cubic). The
    # inline grab above fails here because a '=' is followed by 'b', not a number.
    for m in re.finditer(r'\ba\s*=\s*b\s*=\s*(c\s*=\s*)?(' + NUM + r')', flat):
        pos = m.start(); a = m.group(2).replace(' ', '')
        if num_val(a) is None or num_val(a) < 2.5:
            continue
        window = flat[pos:pos + 160]
        if m.group(1):                       # 'a = b = c =' -> cubic
            b = c = a; al = be = ga = '90'
        else:
            b = a
            cm = re.search(r'\bc\s*=\s*(' + NUM + r')', window)
            c = cm.group(1).replace(' ', '') if cm else None
            gm = re.search(r'γ\s*=\s*(' + NUM + r')', window)
            al = be = '90'; ga = gm.group(1).replace(' ', '') if gm else None
        cands.append(CellCand(a, b, c, al, be, ga, None, None,
                              classify_context(flat, pos), pos, flat[max(0, pos - 60):pos + 100]))
    # Space-separated form (no '='): 'a 23.9019(7), b 10.99(3), c 17.05(5) Å'.
    # Anchored on the trailing Å + comma structure to avoid matching prose.
    for m in re.finditer(r'\ba\s+(' + NUM + r')\s*,\s*b\s+(' + NUM +
                         r')\s*,\s*c\s+(' + NUM + r')\s*Å', flat):
        pos = m.start()
        a, b, c = (g.replace(' ', '') for g in m.groups())
        if num_val(a) is None or num_val(a) < 2.5:
            continue
        tail = flat[m.end() - 1:m.end() + 60]    # '…Å, b 118.284(1)°'
        bm = re.search(r'[,]\s*[βb]\s+(' + NUM + r')\s*°', tail)
        be = bm.group(1).replace(' ', '') if bm else None
        Zm = re.search(r'\bZ\s*=?\s*(\d+)', flat[pos:pos + 220])
        cands.append(CellCand(a, b, c, None, be, None,
                              None, Zm.group(1) if Zm else None,
                              classify_context(flat, pos), pos,
                              flat[max(0, pos - 90):pos + 90]))
    # Cubic single-parameter TABLE form (no '='): a one-line crystal-data table
    # like 'Cubic, Pm-3m a (Å) 3.5784(2) V (Å3) 45.820(6) Z 1'. Only 'a' is given
    # (b=c=a). Accept as cubic when 'cubic' is nearby or V ≈ a³.
    for m in re.finditer(r'\ba\s*\(\s*Å\s*\)\s*(' + NUM + r')', flat):
        pos = m.start(); a = m.group(1).replace(' ', '')
        av = num_val(a)
        if av is None or av < 2.5:
            continue
        win = flat[pos:pos + 120]; before = flat[max(0, pos - 120):pos].lower()
        # A separate 'c (Å)' value in the window means it is NOT cubic (it is a
        # uniaxial cell with b omitted) — let find_cells_table handle that.
        cm = re.search(r'\bc\s*\(\s*Å\s*\)\s*(' + NUM + r')', win)
        if cm and num_val(cm.group(1)) is not None and abs(num_val(cm.group(1)) - av) > 0.01:
            continue
        Vm = re.search(r'\bV\s*\(\s*Å\s*[³3]?\s*\)\s*(' + NUM + r')', win) \
            or re.search(r'\bV\s*=\s*(' + NUM + r')', win)
        vv = num_val(Vm.group(1)) if Vm else None
        # require an explicit 'cubic'/'isometric' nearby, or a TIGHT V≈a³ match
        cubic = ('cubic' in before or 'isometric' in before or
                 (vv is not None and abs(vv - av ** 3) <= 0.005 * vv))
        if not cubic:
            continue
        Zm = re.search(r'\bZ\s*=?\s*(\d+)', win)
        cands.append(CellCand(a, a, a, '90', '90', '90',
                              Vm.group(1).replace(' ', '') if Vm else None,
                              Zm.group(1) if Zm else None,
                              classify_context(flat, pos), pos,
                              flat[max(0, pos - 60):pos + 90]))
    # fallback: vertical label/value tables the inline parsers can't see
    cands += find_cells_table(text)
    # multi-phase papers: named grid rows and multi-column comparison tables
    cands += find_cells_named_rows(text)
    cands += find_cells_multicol(text)
    # fallback: numeric grid rows 'spacegroup  a  b  c  V' (one phase per row).
    # Anchored on volume consistency — a strong crystallographic constraint that
    # all but eliminates chance 4-number runs.  V ≤ a·b·c always (non-90 angles
    # only shrink the cell), and stays above ~0.55·a·b·c for real cells, so the
    # ratio band covers cubic/tetragonal (≈1), hexagonal (≈0.87) and oblique.
    for m in re.finditer(r'(' + NUM + r')\s+(' + NUM + r')\s+(' + NUM +
                         r')\s+(' + NUM + r')', flat):
        a, b, c, V = (g.replace(' ', '') for g in m.groups())
        av, bv, cv, vv = (num_val(x) for x in (a, b, c, V))
        if None in (av, bv, cv, vv) or vv <= 30:
            continue
        if not all(2.5 <= x <= 60 for x in (av, bv, cv)):
            continue
        if not (0.55 <= vv / (av * bv * cv) <= 1.03):
            continue
        pos = m.start()
        cands.append(CellCand(a, b, c, None, None, None, V, None,
                              classify_context(flat, pos), pos,
                              flat[max(0, pos - 90):pos + 90]))
    # de-duplicate by (a,b,c,context); when duplicated, keep the phase-tagged one
    seen = {}; out = []
    for cd in cands:
        key = (cd.a, cd.b, cd.c, cd.context)
        if key in seen:
            if cd.phase and not out[seen[key]].phase:
                out[seen[key]] = cd          # upgrade to the named version
            continue
        seen[key] = len(out); out.append(cd)
    return out

# wavelength
ANODE_LAMBDA = {'cu': 1.5406, 'mo': 0.71073, 'fe': 1.93604, 'co': 1.78897,
                'cr': 2.28970, 'ag': 0.55941}
def anode_key(s):
    if not s: return None
    s = s.lower()
    for k in ANODE_LAMBDA:
        if k in s: return k
    return None

# 'Sync' is a valid ICDD radiation designator (synchrotron). Its λ is beamline-
# tunable, so it matches no characteristic tube line and anode_key() returns None —
# but that's correct, not "unrecognised". Recognise it so the λ check stays quiet.
_SYNC_ANODE = re.compile(r'\bsync(?:hrotron)?\b', re.I)
def is_sync_anode(s):
    return bool(s and _SYNC_ANODE.search(s))

_SYNCHROTRON_CUE = re.compile(
    r'synchrotron|beamline|\bSR-?(?:PXD|XRD|PD)\b|\bESRF\b|\bALBA\b|\bAPS\b|'
    r'diamond light|spring-?8|\bDESY\b|\bELETTRA\b|petra\s*iii', re.I)
def pdf_mentions_synchrotron(text):
    return bool(text and _SYNCHROTRON_CUE.search(text))

def find_radiation(text):
    flat = re.sub(r'\s+', ' ', text)
    out = []
    # The Kα α-glyph is frequently dropped by PDF text extraction ('CuKα' → 'CuK',
    # 'MoKα radiation' → 'MoK radiation'). Accept the α-less form too: element + K
    # followed by α/a, a subscript digit, whitespace, a closing bracket, or
    # punctuation/end — but NOT another letter or hyphen (excludes 'Kr', 'K-edge').
    for m in re.finditer(r'(Cu|Mo|Fe|Co|Cr|Ag)\s?K(?=[αa\d\s)\].,;）]|$)', flat):
        pos = m.start()
        lam = None
        mm = re.search(r'λ\s*=?\s*(\d\.\d{3,5})', flat[pos:pos + 60]) \
            or re.search(r'(\d\.\d{3,5})\s*Å', flat[pos:pos + 60])
        if mm: lam = mm.group(1)
        # Skip electron-microprobe STANDARD emission lines, which are written as
        # 'mineral (FeKα)' inside a parenthesised enumeration — not the diffraction
        # source. Recognise them as: element-K opening/continuing a parenthetical
        # list, with no wavelength and no 'radiation/source/tube/anode' word after.
        before_char = flat[pos - 1] if pos > 0 else ' '
        after = flat[m.end():m.end() + 18]
        is_rad_phrase = (lam is not None
                         or bool(re.match(r'[αa]?\d?\s*(radiation|source|tube|anode|line)', after, re.I)))
        if before_char in '(,/' and not is_rad_phrase:
            continue
        out.append((m.group(1).lower(), lam, radiation_context(text, pos)))
    return out

# ----------------------------------------------------------------------------- comparison
# Lattice values in these papers are quoted to 4-5 decimals; powder vs
# single-crystal cells of the same phase typically differ by 1-10 mAngstrom.
# So matching must be TIGHT and rank by closeness, never "first within a loose
# window" (that is how the prototype mis-picked the single-crystal cell).
MATCH_TOL = 0.004        # axis counts as matched if |Δ| <= 4 mÅ (or exact string)

def close(x, y, abstol=MATCH_TOL, reltol=0.0):
    if x is None or y is None: return False
    return abs(x - y) <= max(abstol, reltol * max(abs(x), abs(y)))

def cell_axis_deltas(docx_abc, cd):
    """Per-axis (label, docx_str, pdf_str, |Δ|, matched?) for the closest cell.
    One axis off while the rest match = transcription typo in that axis; several
    off = the closest PDF cell is likely a different phase/cell (multi-cell PDF)."""
    out = []
    for lab, dv, nv in zip('abc', docx_abc[:3], [cd.a, cd.b, cd.c]):
        x, y = num_val(dv), num_val(nv)
        if x is None or y is None:
            continue
        out.append((lab, dv, nv, abs(x - y), close(x, y)))
    return out

def _phase_match(prefer, phase):
    """True if a candidate's tagged phase name is the entry under review (root
    name in either direction): '#mineral-(La)' ~ '#mineral'."""
    if not prefer or not phase:
        return False
    a = re.sub(r'[^a-z]', '', prefer.lower())
    b = re.sub(r'[^a-z]', '', phase.lower())
    if len(a) < 4 or len(b) < 4:
        return False
    return a in b or b in a or a[:6] == b[:6]

def best_match(docx_abc, cands, prefer_phase=None):
    """Pick the PDF cell closest to the docx cell.
    Returns (cand, n_matched, n_comparable, total_dev, mode).
    Only axes present in BOTH are compared (uniaxial PDFs omit b; docx sets
    b=a, so we also try docx[a,a,c] vs candidate[a,_,c]). When several cells are
    equally close (sibling phases in a multi-phase paper), a cell whose tagged
    `phase` matches the entry name breaks the tie."""
    A = [num_val(x) for x in docx_abc]
    best = (None, -1, 0, 9e9, None); best_key = (-1, 0, 9e9)
    for cd in cands:
        cabc = [num_val(cd.a), num_val(cd.b), num_val(cd.c)]
        if cabc[1] is None and cabc[0] is not None:   # uniaxial PDF omits b (=a)
            cabc[1] = cabc[0]
        pbonus = 1 if _phase_match(prefer_phase, cd.phase) else 0
        # Among EXACTLY-tied candidates, prefer the powder-context cell: a paper
        # quotes the same cubic/uniaxial value in the abstract, a crystal-data
        # table AND the powder-refinement sentence — only the last carries a powder
        # cue, so a tie that resolves to the abstract copy mislabels the cell as
        # SCXRD. ICDD entries carry the powder cell, so surface that one (ranked
        # last, below -dev, so it only ever breaks a true tie — never overrides a
        # closer cell).
        powbonus = 1 if cd.context == 'powder' else 0
        for mode, order in (('direct', A), ('reordered', sorted([v for v in A if v]))):
            if mode == 'reordered':
                cc = sorted([v for v in cabc if v]); aa = order
                pairs = list(zip(aa, cc))
            else:
                pairs = [(A[i], cabc[i]) for i in range(3)]
            comp = [(x, y) for x, y in pairs if x is not None and y is not None]
            if len(comp) < 2: continue
            nmatch = sum(close(x, y) for x, y in comp)
            dev = sum(abs(x - y) for x, y in comp)
            # rank: more matched axes, then SMALLER deviation (the docx was
            # transcribed from its source cell, so the closest cell is the right
            # one — this prefers a full-precision prose cell over a rounded summary
            # table), with the phase-name match breaking near-ties (≤1 mÅ) so a
            # multi-phase paper still resolves to the correctly-named sibling.
            key = (nmatch, -round(dev, 3), pbonus, -dev, powbonus)
            if key > best_key:
                best_key = key; best = (cd, nmatch, len(comp), dev, mode)
    return best

# --------------------------------------------------------------- cell SOURCE (powder vs SCXRD)
# PXRD-refinement cues (GSAS/EXPGUI/Rietveld/"from the powder data" …) and positive
# single-crystal cues. POWDER evidence wins: a stray 'single-crystal' word elsewhere in
# the snippet must NOT flip a powder/Rietveld cell to SCXRD (that produced false flags).
_POWDER_CUE = re.compile(r'\bpowder\b|rietveld|gsas|expgui|fullprof|profile fit|le ?bail|pawley|gandolfi'
                         r'|debye|unitcell|celref|dicvol|treor|chekcell|checkcell|\bμxrd\b|micro[- ]?xrd', re.I)
_SC_CUE = re.compile(r'single[- ]?crystal|scxrd|centroids|\d+\s+reflections|reflections (?:above|with|collected|measured)', re.I)

def provenance_label(cd):
    """Readable label for a matched cell's likely source. POWDER evidence is checked
    first; then POSITIVE single-crystal evidence; then a weaker 'refined unit-cell …
    space group …' heuristic (hedged 'likely … confirm'). Heuristic by nature, so
    only the definitive single-crystal label drives a docx flag (see cell_source_finding)."""
    ctx = cd.context or 'unknown'
    snip = cd.snippet or ''
    if ctx == 'powder' or _POWDER_CUE.search(snip):
        return 'matches the powder cell'
    if ctx == 'single' or _SC_CUE.search(snip):
        return 'matches the single-crystal (SCXRD) cell'
    if re.search(r'refined unit[- ]?cell|space group|structure (?:was )?(?:solved|refined)', snip, re.I):
        return 'likely the single-crystal (SCXRD) structure-refinement cell — confirm'
    return 'powder vs SCXRD context unclear — confirm'

def find_powder_conflict(docx_abc, matched, cands):
    """A DISTINCT powder-context cell of the SAME phase (sorted axes each within 10 %)
    that differs from the matched (SCXRD) cell beyond tolerance — i.e. the paper has a
    powder-refined cell for this phase that the docx did not use. Returns it or None."""
    A = sorted([num_val(x) for x in docx_abc[:3] if num_val(x) is not None])
    if len(A) < 3:
        return None
    for c in cands:
        if c is matched or c.context != 'powder':          # only an explicit powder cell counts
            continue
        if _SC_CUE.search(c.snippet or ''):                # …and not one mislabeled (it's an SC cell)
            continue
        cc = sorted([v for v in (num_val(c.a), num_val(c.b), num_val(c.c)) if v is not None])
        if len(cc) < 3:
            continue
        same_phase = all(abs(x - y) <= 0.10 * y for x, y in zip(cc, A))
        distinct = any(abs(x - y) > MATCH_TOL for x, y in zip(cc, A))
        if same_phase and distinct:
            return c
    return None

def _docx_matches_a_powder_cell(docx_abc, cands):
    """True if a POWDER-context cell equals the docx cell (within tol) — then the docx
    already used a powder cell (e.g. a single-crystal AND a 3DED/μXRD refinement that
    agree to the same value), so the 'used the SCXRD cell' flag must NOT fire."""
    A = sorted([num_val(x) for x in docx_abc[:3] if num_val(x) is not None])
    if len(A) < 3:
        return False
    for c in cands:
        if c.context != 'powder' or _SC_CUE.search(c.snippet or ''):
            continue
        cc = sorted([v for v in (num_val(c.a), num_val(c.b), num_val(c.c)) if v is not None])
        if len(cc) == 3 and all(close(x, y) for x, y in zip(cc, A)):
            return True
    return False

def cell_source_finding(docx_abc, matched, cands):
    """(sev, msg, evidence) for the 'docx used the single-crystal cell' check, or None.
    ICDD entries should carry the POWDER-refined cell. FLAG when the matched cell is the
    SCXRD cell AND the paper ALSO reports a DISTINCT same-phase POWDER/PXRD cell the docx
    did not use — find_powder_conflict is conservative enough (same-phase sorted axes
    within 10 %, distinct beyond tol, powder-context, not SC-cued) to drive the flag on
    its own; the multi-phase trap (e.g. julgoldite's pectolite/hematite cells) is filtered
    out by its same-phase test, so those stay a soft NOTE."""
    if matched is None:
        return None
    # If the docx cell equals a PARSED powder-context cell, the docx used the powder
    # cell — full stop. A multi-cell paper repeats the same cubic/uniaxial value in
    # the abstract and a crystal-data table (neither carrying a powder cue), so the
    # matched copy may read 'SCXRD' even though the identical powder cell is right
    # there; don't emit a phantom SCXRD finding (nor the false 'no separate powder
    # cell was parsed' note) when a powder cell that equals the docx exists.
    if _docx_matches_a_powder_cell(docx_abc, cands):
        return None
    prov = provenance_label(matched)
    if 'single-crystal' not in prov:
        return None
    pc = find_powder_conflict(docx_abc, matched, cands)
    if pc is not None:
        return ('flag',
                'docx cell is the single-crystal (SCXRD) cell, but the paper reports a refined '
                'POWDER (PXRD) cell for this phase (a=%s b=%s c=%s) — ICDD entries use the PXRD '
                'cell; flag that the powder cell was refined but the SCXRD cell was entered.'
                % (pc.a, pc.b, pc.c),
                re.sub(r'\s+', ' ', (pc.snippet or '')).strip()[:160])
    return ('note',
            'matched cell appears to be the single-crystal (SCXRD) cell — ICDD entries use the '
            'powder-refined cell; confirm the powder cell was entered (no separate powder cell was parsed).',
            re.sub(r'\s+', ' ', (matched.snippet or '')).strip()[:160])

# ----------------------------------------------------------------------------- pairing docx<->pdf
# Entry ids are I-prefixed (most) or O-prefixed (e.g. O002127); keys are the
# full prefixed string ('Innnnnn'/'Onnnnnn') so I/O never collide numerically.
# Two id widths coexist in the corpus: 6-digit (newer batches, e.g. I003559) and
# 5-digit (the older ICDD Task Group tree, e.g. I10636). Some files use a LOWERCASE
# prefix ('i11397', 'i12605'), so the prefix is case-insensitive and the key is
# upper-cased (build keys via _mk_key, never raw group(1), so 'i11397' pairs 'I11397').
# The leading (?<![A-Za-z0-9]) keeps a lowercase i/o inside a word (e.g. a DOI) from
# matching; the trailing (?!\d) stops a 5-digit match biting the front off a longer
# number; keys preserve the source width (no zero-padding) so 'I10636'~'77539_I10636'.
ID_RE = r'(?<![A-Za-z0-9])([IOio])(\d{5,6})(?!\d)'

def _mk_key(pre, num):
    return pre.upper() + num

def _is_supp(name):
    """True for supplementary / table PDFs (…_Supp, _Supp1, _TableS1, …). The
    primary article PDF carries the unit cell; supplementary files usually
    don't (or hold a different table), so they must not be paired in preference."""
    return bool(re.search(r'supp|table', name, re.I))

def pdf_index(folder):
    cand = {}                                        # id -> [paths]
    for p in glob.glob(os.path.join(folder, '**', '*.pdf'), recursive=True):
        name = os.path.basename(p)
        ids = re.findall(ID_RE, name)
        if not ids: continue
        if len(ids) >= 2 and '-' in name:            # range-named PDF, e.g. Innnnnn-Innnnnn.pdf
            pre = ids[0][0].upper(); w = len(ids[0][1])   # preserve the source id width (5 or 6)
            keys = ['%s%0*d' % (pre, w, n) for n in range(int(ids[0][1]), int(ids[-1][1]) + 1)]
        else:
            keys = [_mk_key(pre, num) for pre, num in ids]
        for k in keys: cand.setdefault(k, []).append(p)
    # prefer the primary article PDF (no supp/table marker), then the shorter name
    return {k: sorted(ps, key=lambda p: (_is_supp(os.path.basename(p)), len(os.path.basename(p))))[0]
            for k, ps in cand.items()}

def cif_index(folder):
    """Build entry-id → CIF path index, looking in folder and its Files/ subfolder."""
    cand = {}
    for p in glob.glob(os.path.join(folder, '**', '*.[cC][iI][fF]'), recursive=True):
        ids = re.findall(ID_RE, os.path.basename(p))
        for pre, num in ids:
            cand.setdefault(_mk_key(pre, num), []).append(p)
    # prefer shorter names (less likely to be supplementary)
    return {k: sorted(ps, key=lambda p: len(os.path.basename(p)))[0]
            for k, ps in cand.items()}

def dft_index(folder):
    """Build entry-id → ICDD DataQuacker .dft path index (recursive). The .dft is a
    co-equal proxy (CIF-like structured ICDD record), used only as a soft cross-check."""
    cand = {}
    for p in glob.glob(os.path.join(folder, '**', '*.[dD][fF][tT]'), recursive=True):
        ids = re.findall(ID_RE, os.path.basename(p))
        for pre, num in ids:
            cand.setdefault(_mk_key(pre, num), []).append(p)
    return {k: sorted(ps, key=lambda p: len(os.path.basename(p)))[0]
            for k, ps in cand.items()}

def entry_id(path):
    m = re.search(ID_RE, os.path.basename(path))
    return _mk_key(m.group(1), m.group(2)) if m else None

def entry_name(path):
    """Mineral name from the docx filename parenthetical, e.g.
    'Innnnnn(#mineral-(La)).docx' -> '#mineral-(La)'."""
    m = re.search(r'\((.+)\)\.docx$', os.path.basename(path))
    return m.group(1) if m else None

# ----------------------------------------------------------------------------- report
def report(docx_path, pdf_path):
    name = os.path.basename(docx_path)
    print('=' * 78)
    print(name, ' <- ', os.path.basename(pdf_path) if pdf_path else '(NO .pdf FOUND)')
    d = parse_docx(docx_path)
    if d.authors_cell:
        print('  docx Author\'s Cell : a=%s b=%s c=%s  α=%s β=%s γ=%s  SG=%s Z=%s'
              % tuple((x or '') for x in d.authors_cell))
    else:
        print('  docx Author\'s Cell : (not found)')
    print('  docx Radiation     : %s  λ=%s' % (d.radiation, d.lam))
    for au, txt in d.comments:
        print('  reviewer comment   : [%s] %s' % (au, txt))
    if not pdf_path:
        _run_extra(docx_path, None)        # docx-internal checks still apply (symmetry, indexing, …)
        return
    text = pdf_text(pdf_path)
    cands = find_cells(text)

    # --- cell comparison.  Priorities (per reviewer): a matching cell exists;
    #     numbers match; correct significant figures; correct esd/error values.
    #     Whether a matched cell is SCXRD vs PXRD is INFO only (often acceptable);
    #     the reviewer decides — we just surface the context + any existing note.
    if d.authors_cell and any(d.authors_cell[:3]):
        cd, nmatch, ncomp, dev, mode = best_match(d.authors_cell[:3], cands, entry_name(docx_path))
        full = cd is not None and ncomp >= 2 and nmatch == ncomp
        if cd is None:
            print('  CELL  : ✗ no inline cell parsed from .pdf (cell may be table-only) — CHECK MANUALLY')
        elif full:
            print('  CELL  : ✓ value match to a reported cell  [%d/%d axes, %s, Σ|Δ|=%.4f Å]'
                  % (nmatch, ncomp, mode, dev))
            print('          .pdf cell: a=%s b=%s c=%s α=%s β=%s γ=%s V=%s Z=%s'
                  % (cd.a, cd.b, cd.c, cd.al, cd.be, cd.ga, cd.V, cd.Z))
            # significant-figure & esd checks across every comparable parameter
            docx_p = dict(zip(['a','b','c','α','β','γ'], d.authors_cell[:6]))
            pdf_p  = dict(zip(['a','b','c','α','β','γ'], [cd.a,cd.b,cd.c,cd.al,cd.be,cd.ga]))
            any_issue = False
            for k in ['a','b','c','α','β','γ']:
                # symmetry-fixed angles (90, 120) are constrained, not transcribed
                # from the paper, and inline grabs of α/γ often catch a stray
                # number from another phase — so skip them.
                if k in ('α','β','γ') and num_val(docx_p[k]) in (90.0, 120.0):
                    continue
                for kind, note in axis_issues(docx_p[k], pdf_p[k]):
                    any_issue = True
                    label = {'value':'VALUE MISMATCH','precision':'sig-figs differ',
                             'esd':'error (esd) differs'}[kind]
                    print('          ↳ %s: %s — %s' % (k, label, note))
            if not any_issue:
                print('          ↳ numbers, significant figures and esds all match')
            if cd.context == 'single':
                print('          ℹ matched cell sits in a SINGLE-CRYSTAL/SCXRD context '
                      '(acceptable for some entries; reviewer to confirm)')
                print('            evidence: …%s…' % re.sub(r'\s+', ' ', cd.snippet).strip())
            src = cell_source_finding(d.authors_cell, cd, cands)
            if src:
                print('          %s [cell source] %s' % ('⚑' if src[0] == 'flag' else '·', src[1]))
        else:
            print('  CELL  : ⚠ no exact cell match in .pdf — INVESTIGATE '
                  '(closest off by Σ|Δ|=%.4f Å over %d axes)' % (dev, ncomp))
            # Per-axis diagnosis. A single axis off while the rest match tightly is
            # the signature of a transcription typo in that axis (e.g. nigelcookite
            # b=12.2770 where the paper says 12.2377); many axes off usually means
            # the parser matched a sibling phase / wrong cell in a multi-cell PDF.
            diffs = cell_axis_deltas(d.authors_cell, cd)
            out_axes = [t for t in diffs if not t[4]]
            in_axes = [t for t in diffs if t[4]]
            if len(out_axes) == 1 and in_axes:
                lab, dv, nv, dd, _ = out_axes[0]
                print('          ↳ SINGLE-AXIS discrepancy: %s docx=%s vs pdf=%s (Δ=%.4f Å); '
                      'other axes match exactly — likely a transcription error in %s' % (lab, dv, nv, dd, lab))
            elif len(out_axes) >= 2:
                print('          ↳ %d of %d axes differ — the closest .pdf cell is probably a '
                      'different phase/cell (multi-cell .pdf); the matching cell may be unparsed' %
                      (len(out_axes), len(diffs)))
            for lab, dv, nv, dd, ok in diffs:
                print('          %s: docx=%-12s pdf=%-12s Δ=%.4f %s' % (lab, dv, nv, dd, '✓' if ok else '✗'))
            print('          near cell context: [%s]' % cd.context)
        if cands:
            print('          .pdf reported cells:')
            for c in cands:
                print('            [%-7s] a=%s b=%s c=%s β=%s' % (c.context, c.a, c.b, c.c, c.be))

    # --- wavelength comparison
    rads = find_radiation(text)
    dk = anode_key(d.radiation)
    powder_rads = [r for r in rads if r[2] == 'powder']
    any_match = any(anode_key(r[0]) == dk for r in rads)
    pk = powder_rads[0] if powder_rads else None
    if dk is None:
        if is_sync_anode(d.radiation):
            conf = ' (.pdf confirms synchrotron)' if pdf_mentions_synchrotron(text) else ''
            print('  λ     : ✓ docx anode %s — synchrotron radiation; λ is beamline-specific%s'
                  % (d.radiation, conf))
        else:
            print('  λ     : docx anode not recognised (%s)' % d.radiation)
    elif pk is not None:
        if anode_key(pk[0]) == dk:
            print('  λ     : ✓ docx anode %s matches .pdf POWDER radiation' % d.radiation)
        else:
            print('  λ     : ⚠ docx anode %s but .pdf POWDER radiation is %sKα — FLAG'
                  % (d.radiation, pk[0].capitalize()))
        if pk[1] and d.lam and not close(float(pk[1]), num_val(d.lam), abstol=0.003):
            print('          ↳ λ value docx=%s pdf=%s' % (d.lam, pk[1]))
    elif any_match:
        distinct = {anode_key(r[0]) for r in rads}; distinct.discard(None)
        if distinct == {dk}:
            print('  λ     : ✓ docx anode %s matches the .pdf radiation (single source — powder shares it, '
                  'e.g. Gandolfi/crystal-rotation on a single-crystal instrument)' % d.radiation)
        else:
            print('  λ     : • docx anode %s appears in .pdf (no clear powder-context radiation found — verify)' % d.radiation)
    else:
        anodes = sorted(set(r[0].capitalize() + 'Kα' for r in rads)) or ['(none found)']
        print('  λ     : ⚠ docx anode %s NOT found in .pdf; .pdf mentions: %s — verify'
              % (d.radiation, ', '.join(anodes)))
    _run_extra(docx_path, text)

def _run_extra(docx_path, text):
    """The 10 additional reviewer-comment checks (see extra_checks.py). Imported
    lazily so the comparator has no hard dependency on the extras while they are
    still being tuned; a failure here never breaks the core report."""
    try:
        from pxrd_review import extra_checks
        extra_checks.print_findings(docx_path, text)
    except Exception as e:
        print('  EXTRA : (extra checks unavailable: %s)' % e)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('folder')
    ap.add_argument('--id', help='only this entry id, e.g. Innnnnn')
    args = ap.parse_args()
    idx = pdf_index(args.folder)
    docs = sorted(f for f in glob.glob(os.path.join(args.folder, '*.docx'))
                  if not os.path.basename(f).startswith('~$'))
    for dp in docs:
        if args.id and args.id not in os.path.basename(dp): continue
        eid = entry_id(dp)
        report(dp, idx.get(eid))

if __name__ == '__main__':
    main()
