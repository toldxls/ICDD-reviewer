#!/usr/bin/env python3
"""
Extra review checks (prototype, additive) — the 10 most common reviewer comments
that the cell/wavelength comparator does NOT yet cover, mined from the reviewer's
own Word comments across TAO/MTG batches.

These are deliberately kept in a SEPARATE module from cell_lambda_check (the
single source of truth for cell/λ matching). They are more heuristic, so they
must be easy to read, tune, and switch off individually while we troubleshoot.

Each check returns a list of Finding(code, sev, msg, evidence):
  sev 'flag' = likely needs an edit/comment;  'info' = surface for the reviewer
  to confirm (acceptable in many entries);    'note' = low-confidence FYI.

Inputs available to a check:
  e    — Entry, the structured docx fields (parse_entry below)
  text — full PDF text (already mojibake-normalised), or None if no PDF paired

Checks (numbered to match the review write-up):
  1  instrument geometry / camera method      (docx field + PDF vocabulary)
  2  cell not refined from powder (SCXRD/SAED/TEM/calc)
  3  group / structural classification
  4  PXRD pattern calculated, not measured
  5  wavelength canonical value & Kα2 stripped
  6  ideal formula vs empirical analysis
  7  synthetic vs natural (name / subfile)
  8  precision / esd / symmetry consistency    (docx-internal, no PDF)
  9  hkl indexing vs the stated cell           (docx-internal, no PDF)
 10  IMA proposal number missing on a new mineral
 16  instrumentation designator vocabulary + cross-field consistency
     (typos/casing; β-filter element vs anode; monochromator material;
      Calculated coherence)   — curated from the corrected corpus
 18  mineral name vs ideal formula (Levinson rare-earth suffix; polytype letter)
"""
import re, zipfile, math, html
from collections import namedtuple
from xml.etree import ElementTree as ET

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
def _t(e): return e.tag.replace(W, '')

# `anchor` tells the annotator which docx cell to attach the comment to:
#   'cell:a'..'cell:γ' (Author's-Cell value), 'instr', 'refl', 'ima', 'formula',
#   'name', or None (annotator picks a default). evidence/anchor default to None
# so existing 3- and 4-arg Finding(...) calls keep working.
Finding = namedtuple('Finding', 'code sev msg evidence anchor', defaults=(None, None))

# ----------------------------------------------------------------------------- docx structured parse
def _cell_text(tc):
    """Cell text with tracked insertions applied, deletions dropped (matches
    cell_lambda_check.cell_value), inter-run whitespace preserved for prose
    fields but collapsible by the caller."""
    return ''.join(el.text or '' for el in tc.iter()
                   if _t(el) == 't' and _t(el) != 'delText')

def _rows(path):
    root = ET.fromstring(zipfile.ZipFile(path).read('word/document.xml'))
    out = []
    for tr in root.iter(W + 'tr'):
        out.append([_cell_text(tc) for tc in tr.findall(W + 'tc')])
    return out

def _sq(s):                       # squeeze whitespace
    return re.sub(r'\s+', ' ', s or '').strip()
def _ns(s):                       # no spaces (for label matching)
    return re.sub(r'\s+', '', s or '')

Entry = namedtuple('Entry', 'name primary subfiles formulas crystal_system space_group '
                            'cell instr comments refl raw_rows')

def parse_entry(path):
    rows = _rows(path)
    name = primary = None
    subfiles = []                 # [(class, subclass)]
    formulas = {}                 # Chemical/General/Structural/Empirical -> str
    crystal_system = space_group = None
    cell = {}                     # a..γ + SG + Z (raw strings, esd kept)
    instr = {}                    # anode, lam, standard, filter, filtertype, spacing_instr, intensity_instr, intensity_type, camera
    comments = {}                 # Desc code -> text  (IMA Number, Analysis, Structure, GC, DC, …)
    refl = []                     # [(d,I,h,k,l)] from both halves of the reflection table
    section = None

    for r in rows:
        if not r:
            continue
        h = r[0].strip(); hk = _ns(h)
        # section headers (single-cell rows)
        if len(r) == 1:
            section = hk
            continue
        # --- names
        if h == 'Mineral' and len(r) > 1 and not name:
            name = _sq(r[1])
        if h == 'Primary' and len(r) > 1 and section != 'References' and not primary:
            primary = _sq(r[1])
        # --- formulas
        if h in ('Chemical', 'General', 'Structural', 'Empirical') and len(r) > 1:
            formulas[h] = _sq(r[1])
        # --- cell parameters block
        if hk.startswith('CrystalSystem') and len(r) > 1:
            crystal_system = r[1].strip()
        if h == "Author's Cell" and len(r) >= 9:
            keys = ['a', 'b', 'c', 'α', 'β', 'γ', 'SG', 'Z']
            for k, v in zip(keys, [_ns(x) for x in r[1:9]]):
                cell[k] = v
            space_group = r[7].strip()
        # --- subfiles (rows: '' | class | subclass)
        if section == 'SubFiles' and len(r) == 3 and r[1].strip() and r[1].strip() != 'Chemical Class':
            subfiles.append((r[1].strip(), r[2].strip()))
        # --- instrumentation
        if hk.startswith('Radiation='):
            instr['anode'] = r[1].strip() if len(r) > 1 else ''
            for i, x in enumerate(r):
                xs = _ns(x).lower()
                if xs.startswith('l=') and i + 1 < len(r):
                    instr['lam'] = _ns(r[i + 1])
                if xs.startswith('standard') and i + 1 < len(r):
                    instr['standard'] = r[i + 1].strip()
                if xs.startswith('filter:') and i + 1 < len(r):
                    instr['filter'] = r[i + 1].strip()
                if xs.startswith('filtertype') and i + 1 < len(r):
                    instr['filtertype'] = r[i + 1].strip()
        for i, x in enumerate(r):
            xs = _ns(x)
            if xs.startswith('SpacingInstr') and i + 1 < len(r):
                instr['spacing_instr'] = r[i + 1].strip()
            if xs.startswith('IntensityInstr') and i + 1 < len(r):
                instr['intensity_instr'] = r[i + 1].strip()
            if xs.startswith('IntensityType') and i + 1 < len(r):
                instr['intensity_type'] = r[i + 1].strip()
            if xs.startswith('CameraDiameter') and i + 1 < len(r):
                instr['camera'] = r[i + 1].strip()
        # --- comments section: Desc code -> text
        if section == 'Comments' and len(r) >= 2 and h and h != 'Desc.':
            comments[h] = _sq(r[1])
        # --- reflection list (two side-by-side d/I/h/k/l triples per row)
        if section == 'ReflectionList' and len(r) >= 5 and _ns(r[0]) not in ('d(A)', 'd(Å)'):
            for base in (0, 8):
                try:
                    d = r[base]; I = r[base + 1]; hh, kk, ll = r[base + 2], r[base + 3], r[base + 4]
                except IndexError:
                    continue
                if not _ns(d):
                    continue
                refl.append((_ns(d), _ns(I), _ns(hh), _ns(kk), _ns(ll)))

    return Entry(name, primary, subfiles, formulas, crystal_system, space_group,
                 cell, instr, comments, refl, rows)

# ----------------------------------------------------------------------------- numeric helpers
def _val(s):
    if not s: return None
    m = re.match(r'-?\d+(?:\.\d+)?', re.sub(r'\(\d+\)', '', re.sub(r'\s+', '', s)))
    return float(m.group(0)) if m else None
def _esd(s):
    m = re.search(r'\((\d+)\)', s or '')
    return m.group(1) if m else None
def _dec(s):
    m = re.match(r'-?\d+(?:\.(\d+))?', re.sub(r'\(\d+\)', '', re.sub(r'\s+', '', s or '')))
    return len(m.group(1)) if m and m.group(1) else 0
def _int(s):
    """Signed integer index. Crystallographic indices are often negative, written
    with an ASCII '-' or a Unicode overbar/minus — all must keep their sign or
    the d-spacing check (which squares h,k,l in cross terms) mis-indexes."""
    if not s: return None
    s = re.sub(r'(\d)̅', r'-\1', s)  # combining overbar → negative sign
    s = s.replace('−', '-')           # Unicode minus sign → ASCII hyphen-minus
    m = re.search(r'-?\d+', s)
    return int(m.group(0)) if m else None

# ----------------------------------------------------------------------------- PDF prose helpers
def _sentences(text):
    flat = re.sub(r'\s+', ' ', text)
    return re.split(r'(?<=[.;:])\s+', flat)

def _find_sentences(text, must_all=(), any_of=(), exclude=()):
    """Sentences containing every term in must_all and at least one of any_of,
    excluding any term in exclude. Case-insensitive. Returns up to 3."""
    out = []
    for s in _sentences(text):
        low = s.lower()
        if any(x in low for x in exclude): continue
        if not all(x in low for x in must_all): continue
        if any_of and not any(x in low for x in any_of): continue
        out.append(s.strip())
        if len(out) >= 3: break
    return out

# ----------------------------------------------------------------------------- 1. geometry / camera method
GEOMETRY_KW = [
    'bragg-brentano', 'bragg–brentano', 'debye-scherrer', 'debye–scherrer',
    'pseudo-gandolfi', 'gandolfi', 'guinier', 'image plate', 'image-plate',
    'transmission geometry', 'reflection geometry', 'capillary',
    'time-of-flight', 'time of flight', 'neutron',
]
# 'neutron' / 'time-of-flight' are RADIATION-TYPE methods, not X-ray powder
# geometries. A stray mention of a *planned future* study ("…will require additional
# data, such as powder neutron diffraction…") sits in a powder sentence and would
# masquerade as the collection method. Only count one in an ACTUAL collection
# statement (past-tense verb) that is not future/hypothetical.
RADIATION_METHOD = {'time-of-flight', 'time of flight', 'neutron'}
_COLLECTED = re.compile(r'\b(collect|measur|record|perform|obtain|acquir|gather|carried out)', re.I)
_HYPOTHETICAL = re.compile(r'\b(will|would|could|should|future|propos|recommend|plan|'
                           r'such as|requir|suggest|prospect|anticipat)', re.I)
# Specific instruments the reviewer recognises; naming one helps confirm the
# designators (the geometry still goes in a comment, not the Spacing Instr.).
INSTRUMENTS = [
    ('Rigaku R-AXIS RAPID II', r'r-?axis\s*rapid'),
    ('Rigaku XtaLAB Synergy',  r'xtalab\s*synergy|synergy[- ]?s\b'),
    ('Rigaku/Oxford SuperNova', r'supernova'),
    ('Rigaku MiniFlex',        r'miniflex'),
    ('Rigaku SmartLab',        r'smartlab'),
    ('Bruker D8',              r'\bd8\b|bruker\s+d8'),
    ('Bruker APEX/SMART',      r'\bapex\s*(?:ii|iii)?\b|\bsmart\b'),
    ('STOE (IPDS/Stadi)',      r'\bstoe\b|ipds|stadi'),
    # \b before X avoids matching 'eXPERT' (the word 'expert'); covers X'Pert/X-Pert/XPert
    ('PANalytical Empyrean',   r'empyrean|\bx[’\'\- ]?pert'),
]
# A POWDER-specific cue (NOT bare 'diffraction', which also opens single-crystal
# sentences) — used to tie a named instrument to the POWDER pattern.
_POW_INSTR_CTX = re.compile(r'\bpowder\b|pxrd|p-?xrd|gandolfi|debye[- ]?scherrer|guinier', re.I)
def check1_geometry(e, text):
    out = []
    spac = (e.instr.get('spacing_instr') or '').strip()
    iinstr = (e.instr.get('intensity_instr') or '').strip()
    is_calc = spac.lower() == 'calculated'
    # PDF vocabulary — only count a geometry keyword when it shares a sentence
    # with a diffraction/powder term, so a stray 'neutron'/'capillary' mention in
    # a reference or unrelated method doesn't masquerade as the powder geometry.
    found = []
    if text:
        for s in _sentences(text):
            low = s.lower()
            if not re.search(r'powder|pxrd|diffract|rietveld|patter|camera', low):
                continue
            for kw in GEOMETRY_KW:
                if kw not in low:
                    continue
                if kw in RADIATION_METHOD and (not _COLLECTED.search(low) or _HYPOTHETICAL.search(low)):
                    continue                  # planned/future mention, not the method used
                if kw.replace('–', '-') not in [f.replace('–', '-') for f in found]:
                    found.append(kw)
    instrument = instrument_match = None      # recognised anywhere (soft confirm)
    powder_instrument = powder_match = None   # recognised in a POWDER-context sentence (confident)
    # capture the instrument text AS WRITTEN in the .pdf so the GUI highlights the actual
    # name (e.g. 'R-AXIS Rapid'), not a generic substring like 'axis'.
    if text:
        for name, pat in INSTRUMENTS:
            mm = re.search(pat, text, re.I)
            if mm:
                instrument, instrument_match = name, mm.group(0)
                break
        for s in _sentences(text):
            if not _POW_INSTR_CTX.search(s):
                continue
            for name, pat in INSTRUMENTS:
                mm = re.search(pat, s, re.I)
                if mm:
                    powder_instrument, powder_match = name, mm.group(0)
                    break
            if powder_instrument:
                break
    # (1) Spacing/Intensity Instr. FIELD value: a recognised diffractometer named in a
    # POWDER-context sentence is high-confidence that the pattern was collected on a
    # diffractometer, so 'Other'/blank should be 'Diffractometer' (FLAG → highlight +
    # suggest). The curated INSTRUMENTS are all diffractometers; the corrected corpus
    # is near-unanimous (R-AXIS RAPID II, D8, Empyrean… → 'Diffractometer'). Skip
    # CALCULATED patterns (no collection instrument) and require the powder tie-in so a
    # single-crystal-only instrument (e.g. a D8 Venture used for SC-XRD) is NOT assumed.
    # Evidence = the instrument text as written in the .pdf (for the highlight).
    field_flagged = False
    if powder_instrument and not is_calc:
        if spac.lower() in ('', 'other'):
            out.append(Finding('instr_class', 'flag',
                       "Spacing Instr. = %r, but the .pdf states the powder pattern was collected on a "
                       "%s (a diffractometer) — set Spacing Instr. to 'Diffractometer'."
                       % (spac or '(blank)', powder_instrument), powder_match, 'spacing_instr'))
            field_flagged = True
        if iinstr.lower() in ('', 'other'):
            out.append(Finding('instr_class', 'flag',
                       "Intensity Instr. = %r, but the powder pattern was collected on a "
                       "%s (a diffractometer) — set Intensity Instr. to 'Diffractometer'."
                       % (iinstr or '(blank)', powder_instrument), powder_match, 'intensity_instr'))
            field_flagged = True
    # (2) The SPECIFIC geometry/method (Debye-Scherrer, image-plate, Gandolfi) is
    # descriptive metadata, NOT a required ICDD field. Only nudge when the Spacing Instr.
    # designator is MISSING (Other/blank) and we did not already pin it down as a
    # diffractometer above — a genuine gap. When the designator is already set
    # (Diffractometer/Film/Calculated), say nothing: the method is correct/obvious and
    # the reviewer routinely documents it in a comment. (This used to fire on every
    # named geometry, nagging entries whose Spacing Instr. was already correct.)
    if not field_flagged and not is_calc and spac in ('', 'Other'):
        if instrument:
            out.append(Finding('geometry', 'info',
                       ".pdf names a %s (docx Spacing Instr. = %r) — set the method."
                       % (instrument, spac or '(blank)'), instrument_match))
        elif found:
            out.append(Finding('geometry', 'note',
                       ".pdf method: %s (docx Spacing Instr. = %r) — set the method."
                       % (', '.join(found), spac or '(blank)'), found[0]))
        else:
            out.append(Finding('geometry', 'note',
                       "Spacing Instr. = %r and no named geometry in .pdf — set the method."
                       % (spac or '(blank)'), None))
    return out

# ----------------------------------------------------------------------------- 2. cell not refined from powder
# A statement that the (unit-)cell WAS refined/determined from the POWDER data —
# if present, the powder cell is fine, regardless of any single-crystal prose.
# This is the common case of a powder pattern collected on a single-crystal
# instrument via a Gandolfi-like / crystal-rotation motion (a SC cell is reported
# alongside, but the entry's cell is powder-refined). e.g. nigelcookite/
# plumbojohntomaite: "Refined unit-cell parameters from the powder data using CHECKCELL".
POWDER_REFINED = re.compile(
    r'(unit[- ]?cell|lattice)\s*(parameters?|constants?|dimensions?)?[^.]{0,80}\b(from|using|by|based on|with)\b[^.]{0,50}\bpowder\b'
    r'|\bpowder\b[^.]{0,90}(unit[- ]?cell|lattice)[^.]{0,50}(refin|determin|index|calculat)'
    r'|refined\s+from\s+the\s+powder\s+data', re.I)
_CELLISH = re.compile(r'unit[- ]?cell|lattice|cell parameter|cell constant|cell volume', re.I)
# the strong phrase must NOT sit in a comparison ("…agree with the single-crystal
# values"), a calculated-pattern table note ("calculated values from single-crystal
# data"), or an unrelated 'not refined' (atom displacement / extinction coefficient).
_PROV_COMPARE = re.compile(r'agree|consistent|compar|similar to|in line with|and powder', re.I)
_PROV_CALCNOTE = re.compile(r'calculated pattern|for the calculated|calculated value|calculated d[- ]?spacing', re.I)
_PROV_NONCELL = re.compile(r'extinction|displacement|thermal|occupanc|isotropic|anisotropic|u\s*iso|u\s*eq|atom', re.I)
# Routine "Dcalc was computed from the empirical formula and the (single-crystal)
# unit-cell" boilerplate appears in nearly every new-mineral description — it is NOT
# an actionable provenance problem (a single-crystal cell is acceptable), so a
# density-calculation sentence does not count. (Corpus: this was 7 of 8 training fires.)
_PROV_DENSITY = re.compile(r'densit|d[_\s-]?calc|d[_\s-]?x\b|d[_\s-]?meas|g\s*[^A-Za-z0-9]{0,2}\s*cm', re.I)

def _sentence_around(text, i):
    a = text.rfind('.', 0, i); b = text.find('.', i)
    return re.sub(r'\s+', ' ', text[a + 1:(b if b > 0 else i + 140)]).strip()

def check2_cell_provenance(e, text):
    out = []
    if not text:
        return out
    low = text.lower()
    if POWDER_REFINED.search(text):       # cell is powder-refined — never flag provenance
        return out
    # Strong, specific phrasings only that the powder cell was NOT refined, or was
    # taken from single-crystal/electron data — and only when the matching sentence
    # is genuinely about the CELL (not a comparison / calc-note / ADP-extinction).
    STRONG = ['were not refined', 'was not refined', 'not refined from',
              'cell parameters from single', 'from single-crystal data',
              'cell from scxrd', 'cell from saed', 'from the saed',
              'taken from the single-crystal', 'derived from single-crystal', 'refined from single']
    for p in STRONG:
        i = low.find(p)
        while i >= 0:
            sent = _sentence_around(text, i); sl = sent.lower()
            if (_CELLISH.search(sl) and not _PROV_COMPARE.search(sl)
                    and not _PROV_CALCNOTE.search(sl) and not _PROV_NONCELL.search(sl)
                    and not _PROV_DENSITY.search(sl)):
                out.append(Finding('cell_provenance', 'info',
                           ".pdf indicates the cell was not powder-refined / came from single-crystal "
                           "or electron data — confirm provenance.", sent[:160]))
                return out
            i = low.find(p, i + 1)
    return out

# ----------------------------------------------------------------------------- 3. group / structural classification
# Words that look like '<Cap> group' but are NOT a mineral-group claim. Besides
# crystallographic uses, '<Place> Group' is overwhelmingly a STRATIGRAPHIC rock
# unit (a group/formation of rocks), unrelated to a mineral group.
_NOT_GROUP = {'space', 'point', 'site', 'wyckoff', 'laue', 'functional', 'this',
              'the', 'a', 'an', 'its', 'each', 'same', 'amphibole',
              'creek', 'mountain', 'formation', 'member', 'series', 'basin',
              'river', 'lake', 'hill', 'hills', 'ridge', 'valley', 'volcanic',
              'sandstone', 'limestone', 'shale', 'granite', 'complex', 'terrane'}
# a mineral (and hence a mineral-group root) almost always ends like this
_MINERALISH = re.compile(r'(ite|ine|ase|yte|ide|ate|lite|site|ote)$', re.I)

def _docx_group_text(e):
    """The group/classification text stated in the docx 'IMA Classifications'
    section (an 'IMA Classifications: ...' header line and/or labelled
    Group/Subgroup/Supergroup rows). Returns '' if none present."""
    out = []
    for r in (e.raw_rows or []):
        cells = [c.strip() for c in r if c and c.strip()]
        if not cells:
            continue
        first = cells[0]
        if first.lower().startswith('ima classification'):
            out.append(first)
        elif first in ('Group', 'Subgroup', 'Supergroup') and len(cells) > 1:
            out.append(cells[1])
    return ' '.join(out)

def check3_classification(e, text):
    out = []
    # A docx Structure/Isomorphism/Polymorphism comment is the CORRECT state, not
    # something to surface — restating it was noise. The actionable case (the paper
    # asserts a structural relation but the docx records none) is checked from the
    # .pdf below.

    # AUTHORITATIVE: Mindat group membership (a mineral's groupid → group name).
    # Replaces guessing from prose. Cross-checks the docx Strunz-mindat field.
    mindat_found = False
    try:
        from pxrd_review import mindat
        mindat.refresh_if_stale()      # auto-refresh if the cache is >2 weeks old (once/process)
        if mindat.available():
            nm = e.name or e.primary or ''
            g = mindat.group_of(nm)
            if g:
                mindat_found = True
                gname, gstrunz, sp, status = g
                def _zs(x): return re.sub(r'[.\s]+$', '', (x or '').strip())
                docx_strunz = _zs(e.comments.get('Strunz-mindat classification', ''))
                strunz_ok = bool(gstrunz and docx_strunz and
                                 (_zs(gstrunz).startswith(docx_strunz) or
                                  docx_strunz.startswith(_zs(gstrunz))))
                # The docx usually states the group in its 'IMA Classifications'
                # section ('Group: <subgroup> > <group>'), even when
                # the Strunz-mindat field is blank. If the docx already names the
                # same (sub/super)group as Mindat, the classification is correct.
                docx_grp = _docx_group_text(e).lower()
                roots = [w for w in re.findall(r'[a-z][a-z\-()]{3,}', (gname or '').lower())
                         if w not in ('group', 'subgroup', 'supergroup')]
                group_ok = bool(roots) and any(w in docx_grp for w in roots)
                if gname and not strunz_ok and not group_ok:
                    msg = "Mindat: %s is in the %s (Strunz %s)" % (sp, gname, gstrunz or '?')
                    if docx_strunz:
                        msg += " — docx Strunz field = %r (differs)" % docx_strunz
                    out.append(Finding('classification', 'info', msg, None, 'name'))
                # ungrouped or correctly classified — no annotation needed
            elif nm and not re.search(r'unnamed', nm, re.I):
                out.append(Finding('classification', 'note',
                           "Mindat: %r not found among IMA species (new/renamed? verify classification)." % nm,
                           None))
    except Exception as ex:
        out.append(Finding('classification', 'note', 'mindat lookup skipped: %s' % ex, None))

    # Structural RELATION — the actionable gap. ICDD entries should carry a Structure/
    # Isomorphism/Polymorphism comment when the paper asserts an obvious structural
    # relationship. Surface a CHECK only when the .pdf states one AND the docx records
    # NONE (a docx that already has such a comment is correct — say nothing).
    if text:
        flat = re.sub(r'\s+', ' ', text)
        seen = set()
        has_struct = any((e.comments.get(c) or '').strip()
                         for c in ('Structure', 'Isomorphism', 'Polymorphism'))
        if not has_struct:
            import unicodedata
            norm = unicodedata.normalize('NFC', flat)   # compose split diacritics (jo¨rg -> jörg)
            rel = re.search(r'\b(isostructural|isotypic|homeotypic|isomorphous|structurally\s+related)'
                            r'\s+(with|to)\s+(?:the\s+)?([A-Za-zÀ-ɏ]{4,})', norm, re.I)
            if rel and _MINERALISH.search(rel.group(3)):
                phrase = '%s %s %s' % (rel.group(1).lower(), rel.group(2).lower(), rel.group(3))
                out.append(Finding('classification', 'info',
                           "docx has no Structure/Isomorphism/Polymorphism comment, but the .pdf states "
                           "'%s' — add a Structure comment recording the relationship." % phrase,
                           rel.group(3)))   # evidence = the related mineral, so GUI '? look' can find the sentence
        # Named 'X group/family' prose is noisy (geological formations like 'Creek
        # group'), and Mindat already gives membership authoritatively — so only
        # fall back to it when Mindat did NOT find the species (a new/renamed
        # mineral, where the paper's own classification is all we have).
        if not mindat_found:
            for m in re.finditer(r'\b([A-Z][a-zü]{3,})\s+((?:super|sub)?group|family)\b', flat):
                root = m.group(1)
                # skip crystallographic/stratigraphic uses, and require the root
                # to look like a mineral (a mineral group is named after one)
                if root.lower() in _NOT_GROUP or not _MINERALISH.search(root):
                    continue
                frag = m.group(0)
                if frag.lower() in seen: continue
                seen.add(frag.lower())
                out.append(Finding('classification', 'note',
                           ".pdf names a '%s' (Mindat has no group for this species — verify)." % frag, None))
                if len(seen) >= 3: break
    return out

# ----------------------------------------------------------------------------- 4. PXRD calculated, not measured
def check4_calculated(e, text):
    out = []
    spac = (e.instr.get('spacing_instr') or '').strip().lower()
    inten = (e.instr.get('intensity_instr') or '').strip().lower()
    if spac == 'calculated' or inten == 'calculated':
        # The docx is already (correctly) marked Calculated — this is normal for a
        # new mineral with only single-crystal data and is NOT an error. Keep it as
        # a console-only note (not written into the docx) so the review isn't
        # cluttered restating what the docx already says. It still suppresses the
        # radiation mismatch flag (handled in annotate_review via e.instr).
        out.append(Finding('calculated', 'note',
                   "docx pattern is Calculated (Spacing=%r, Intensity=%r) — normal "
                   "for a structure-derived pattern; anode/λ is the calculation "
                   "wavelength, not the experimental radiation."
                   % (e.instr.get('spacing_instr'), e.instr.get('intensity_instr')), None, 'instr'))
    # PDF: per reviewer, the powder data is its OWN paragraph and the giveaway is
    # phrasing like 'PXRD was calculated from (the) structure'. Require a powder
    # term AND a calculate/simulate verb in the SAME sentence to avoid the many
    # benign uses of 'calculated' (e.g. 'calculated density').
    if text:
        sents = _find_sentences(
            text,
            any_of=['calculated from', 'were calculated', 'was calculated', 'calculated powder',
                    'simulated', 'computed from'],
        )
        # The PDF-inferred path should fire ONLY when the entry's own pattern is
        # genuinely calculated (no measured pattern exists). Reject any sentence
        # that signals a MEASURED pattern or a COMPARISON between observed and
        # calculated:
        #   - "observed/experimental/measured pattern", "matches/fits/agreement"
        #     → a measured pattern exists; the calc is just a comparison column
        #   - "theoretical pattern"                    → comparison reference
        #   - "calculated/refined FROM (the) powder data", "indexing of powder"
        #     → the cell was DERIVED from measured powder (pattern is measured)
        _MEASURED = re.compile(
            r'observed|experiment|measured|\bmatch|\bfits?\b|agreement|consistent\s+with'
            r'|\btheoretical\b|from\s+(?:the\s+)?powder|refined\s+from\s+powder|indexing\s+of',
            re.I)
        sents = [s for s in sents if re.search(r'powder|pxrd|x-ray diffraction pattern|diffraction pattern', s.lower())
                 and re.search(r'structure|single-crystal|cif|refinement|atomic', s.lower())
                 and not re.search(r'\bcompar', s.lower())
                 and not _MEASURED.search(s)]
        # Multi-species papers often say "for all species EXCEPT <name>, … were
        # calculated". If THIS entry is the excepted species, its pattern was
        # measured, not calculated — don't flag it.
        nm = (e.name or e.primary or '').strip().lower()
        nm_root = re.sub(r'[^a-z]', '', nm)[:6]
        def _excepted(s):
            if not nm_root:
                return False
            m = re.search(r'\bexcept\b(.{0,60})', s, re.I)
            return bool(m and nm_root in re.sub(r'[^a-z]', '', m.group(1).lower()))
        sents = [s for s in sents if not _excepted(s)]
        if sents and not (spac == 'calculated'):
            out.append(Finding('calculated', 'flag',
                       ".pdf states the powder pattern was calculated from the structure.",
                       sents[0][:170], 'instr'))
    return out

# ----------------------------------------------------------------------------- 5. wavelength canonical value & Kα2 stripped
# canonical emission wavelengths (Å): Kα1, Kα (intensity-weighted mean), Kα2
CANON = {
    'cu': dict(ka1=1.540598, ka=1.541874, ka2=1.544426),
    'mo': dict(ka1=0.709319, ka=0.710730, ka2=0.713609),
    'co': dict(ka1=1.788996, ka=1.790260, ka2=1.792850),
    'fe': dict(ka1=1.936042, ka=1.937355, ka2=1.939980),
    'cr': dict(ka1=2.289760, ka=2.291000, ka2=2.293663),
    'ag': dict(ka1=0.559422, ka=0.560885, ka2=0.563813),
}
def _anode_key(s):
    s = (s or '').lower()
    for k in CANON:
        if k in s: return k
    return None
def check5_wavelength(e, text):
    out = []
    anode = e.instr.get('anode'); lam = e.instr.get('lam')
    k = _anode_key(anode)
    lv = _val(lam)
    if k and lv is not None:
        opts = CANON[k]
        nearest = min(opts.items(), key=lambda kv: abs(kv[1] - lv))
        if abs(nearest[1] - lv) > 0.0006:
            out.append(Finding('wavelength', 'flag',
                       "docx λ=%s for %s is non-standard (closest canonical %s=%.6f, Δ=%.5f Å)."
                       % (lam, anode, nearest[0], nearest[1], abs(nearest[1] - lv)), None))
        # subscript-1 line used but the value is the weighted mean (or vice-versa)
        elif re.search(r'k[aα]1\b', (anode or '').lower()) and nearest[0] == 'ka':
            out.append(Finding('wavelength', 'note',
                       "anode labelled Kα1 but λ=%s matches the weighted-mean Kα." % lam, None))
    # Kα2 stripped is a method note the reviewer records; surface it from the PDF
    if text and re.search(r'k[aα]2[\s-]*(strip|remov|elimin)', text.lower()):
        out.append(Finding('wavelength', 'info', ".pdf: Kα2 stripped in software.", None))
    return out

# ----------------------------------------------------------------------------- analysis-field helpers (shared by check6 & check12)
# Comment fields that legitimately hold their own content — not analysis spillover.
_ANALYSIS_OWN_FIELDS = {'Analysis', 'Color', 'Habit', 'Physical Properties',
    'Optical Data', 'Smpl.Src.Local.', 'Wyckoff', 'DC', 'IMA Number',
    'Mohs Hardness', 'Strunz-mindat classification', 'Warning'}

def _misplaced_analysis_field(e):
    """If microprobe/wt.% analytical data sits in a comment field other than
    'Analysis', return that field name; else None. Catches data pasted into
    'Absolute Configuration', 'Structure', etc."""
    for field, content in (e.comments or {}).items():
        if field in _ANALYSIS_OWN_FIELDS:
            continue
        if re.search(r'microprobe|average\s+of\s+\d*\s*\(?\s*wt|wt\.?\s*%\s*[):]',
                     content or '', re.I):
            return field
    return None

def _looks_empirical(formula):
    """A measured/empirical formula carries non-stoichiometric coefficients
    (odd decimals); an ideal end-member formula is clean stoichiometry. Returns
    True when ≥2 coefficients are non-simple decimals."""
    if not formula:
        return False
    odd = 0
    for c in re.findall(r'\d+\.\d+', formula):
        frac = float(c) - int(float(c))
        if not any(abs(frac - f) < 0.02 for f in (0.0, 0.5, 0.25, 0.75, 0.333, 0.667)):
            odd += 1
    return odd >= 2

# ----------------------------------------------------------------------------- 6. analysis stated as an average of N
def check6_ideal_formula(e, text):
    out = []
    # The empty-Analysis-field cases (misplaced data / omitted / ideal-only
    # formula) are all handled in check12 so each scenario yields one comment.
    # Here we only check: when an analysis IS present, that it states an
    # 'average of N' (reviewer: 'no average is given for the N analyses').
    analysis = e.comments.get('Analysis', '')
    if analysis and not re.search(r'average of\s+\d+|mean of\s+\d+', analysis.lower()):
        if re.search(r'analys|wt\.?%|at\.?%|epma|eds|microprobe', analysis.lower()):
            out.append(Finding('ideal_formula', 'note',
                       "Analysis present but no 'average of N' stated — confirm it is an "
                       "average, not a single point.", analysis[:120]))
    return out

# ----------------------------------------------------------------------------- 7. synthetic vs natural
def check7_synthetic(e, text):
    out = []
    nm = (e.name or '') + ' ' + (e.primary or '')
    name_syn = bool(re.search(r'-\s*syn\b|\bsyn\b|synthetic', nm, re.I))
    cls = [c.lower() for c, _ in e.subfiles]
    # A genuine 'this sample is synthetic' subfile is class AND subclass synthetic
    # (e.g. Synthetic / Synthetic). The 'Synthetic Rock-forming minerals' subfile
    # (class Synthetic, subclass 'Rock-forming minerals') is a broad CATEGORY that
    # natural minerals are also filed under — it does NOT mean the sample is synthetic.
    sub_syn = any('synth' in c.lower() and 'synth' in (sub or '').lower() for c, sub in e.subfiles)
    sub_nat = any('natural' in c for c in cls)
    if name_syn and sub_nat and not sub_syn:
        out.append(Finding('synthetic', 'flag',
                   "Name indicates synthetic (%s) but SubFile class is Natural — reconcile."
                   % _sq(nm), None))
    elif sub_syn and not name_syn:
        out.append(Finding('synthetic', 'note',
                   "SubFile class is Synthetic but the name does not say so.", None))
    elif sub_syn or name_syn:
        out.append(Finding('synthetic', 'info', "Synthetic material — verify data sources are "
                   "consistently synthetic (probe vs XRD).", None))
    return out

# ----------------------------------------------------------------------------- 8. precision / esd / symmetry consistency (docx-internal)
def _sys_letter(e):
    """Single-letter crystal system from the docx field, or inferred from the
    space-group symbol's lattice + symmetry."""
    cs = (e.crystal_system or '').strip()
    if cs:
        return cs[0].lower() if cs[0].lower() in 'amothrc' else cs
    return None

def _constraints(e):
    """(equal_axis_groups, equal_angle_groups, fixed_angles) for the entry's
    symmetry. fixed_angles maps param->required constant value."""
    cell = e.cell
    sg = (e.space_group or '')
    cs = _sys_letter(e)
    ga = _val(cell.get('γ')); al = _val(cell.get('α')); be = _val(cell.get('β'))
    # rhombohedral setting: all three angles equal and ≠ 90
    if cs in ('r', 'h') or sg.startswith('R') or sg.startswith('P3') or sg.startswith('P6') or sg.startswith('P-3') or sg.startswith('P-6'):
        if al and be and ga and abs(al - be) < 1e-6 and abs(be - ga) < 1e-6 and abs(ga - 90) > 1:
            return ([('a', 'b', 'c')], [('α', 'β', 'γ')], {})          # rhombohedral axes
        return ([('a', 'b')], [], {'α': 90, 'β': 90, 'γ': 120})        # hexagonal setting
    if cs == 'c' or re.search(r'(^|\s)(F|I|P)?[m\-]?23|m-3', sg):
        return ([('a', 'b', 'c')], [], {'α': 90, 'β': 90, 'γ': 90})
    if cs == 't':
        return ([('a', 'b')], [], {'α': 90, 'β': 90, 'γ': 90})
    if cs == 'o':
        return ([], [], {'α': 90, 'β': 90, 'γ': 90})
    if cs == 'm':
        return ([], [], {'α': 90, 'γ': 90})                            # β free
    if cs == 'a':
        return ([], [], {})
    # unknown system: infer fixed angles from the values themselves (90/120 with
    # no esd are clearly constrained)
    fixed = {}
    for k in ('α', 'β', 'γ'):
        v = _val(cell.get(k))
        if v in (90.0, 120.0) and not _esd(cell.get(k)):
            fixed[k] = v
    return ([], [], fixed)

def _pdf_esd_for(value, text):
    """If the PDF states the same numeric value WITH a parenthesised esd
    (e.g. docx 'c=12.219' and PDF 'c = 12.219(2)'), return the esd digits."""
    if not text or not value:
        return None
    num = re.sub(r'\(\d+\)', '', value).strip()
    m = re.search(re.escape(num) + r'\s*\((\d+)\)', re.sub(r'\s+', ' ', text))
    return m.group(1) if m else None

def check8_precision_symmetry(e, text):
    out = []
    cell = e.cell
    if not cell or not _val(cell.get('a')):
        return out
    eq_axes, eq_angles, fixed = _constraints(e)
    # (a) symmetry-equal parameters must share value AND esd
    for grp in eq_axes + eq_angles:
        present = [(k, cell.get(k)) for k in grp if cell.get(k)]
        vals = {(_val(v), _esd(v)) for _, v in present}
        if len(present) >= 2 and len(vals) > 1:
            out.append(Finding('symmetry', 'flag',
                       "Symmetry-equal parameters %s differ: %s — value and esd should match."
                       % ('='.join(grp), ', '.join('%s=%s' % (k, v) for k, v in present)),
                       None, 'cell:%s' % present[-1][0]))
    # (b) fixed angles must equal the constant and carry no esd
    for k, const in fixed.items():
        v = cell.get(k)
        if not v: continue
        if _val(v) is not None and abs(_val(v) - const) > 0.01:
            out.append(Finding('symmetry', 'flag',
                       "Angle %s=%s but symmetry fixes it at %g." % (k, v, const),
                       None, 'cell:%s' % k))
        if _esd(v):
            out.append(Finding('symmetry', 'flag',
                       "Angle %s=%s carries an esd but is symmetry-fixed at %g (no error expected)."
                       % (k, v, const), None, 'cell:%s' % k))
    # (c) refined parameters quoted to several decimals but with NO esd. When the
    # PDF reports the same value WITH an esd, name it so the reviewer can add it.
    for k in ('a', 'b', 'c'):
        v = cell.get(k)
        if v and _dec(v) >= 3 and not _esd(v):
            pdf_esd = _pdf_esd_for(v, text)
            if pdf_esd:
                msg = ("%s=%s has no stated error (esd) — .pdf gives %s=%s(%s); "
                       "add the (%s)." % (k, v, k, v, pdf_esd, pdf_esd))
            else:
                msg = "%s=%s is quoted to %d decimals but has no stated error (esd)." % (k, v, _dec(v))
            out.append(Finding('precision', 'flag', msg, None, 'cell:%s' % k))
    # (d) esd magnitude sanity: a 1–2 digit esd applies to the last quoted
    # decimal; flag obviously misplaced precision (e.g. 15.637 with esd on 0.000X)
    return out

# ----------------------------------------------------------------------------- 9. hkl indexing vs the stated cell (docx-internal)
def _dstar2(a, b, c, al, be, ga, h, k, l):
    """1/d^2 for (hkl) from the direct cell via the reciprocal metric. General
    (triclinic) — works for every system. Angles in degrees."""
    ar, br, gr = math.radians(al), math.radians(be), math.radians(ga)
    ca, cb, cg = math.cos(ar), math.cos(br), math.cos(gr)
    sa, sb, sg = math.sin(ar), math.sin(br), math.sin(gr)
    V = a * b * c * math.sqrt(max(1e-12, 1 - ca*ca - cb*cb - cg*cg + 2*ca*cb*cg))
    S11 = (b*c*sa)**2
    S22 = (a*c*sb)**2
    S33 = (a*b*sg)**2
    S12 = a*b*c*c*(ca*cb - cg)
    S23 = a*a*b*c*(cb*cg - ca)
    S13 = a*b*b*c*(cg*ca - cb)
    return (S11*h*h + S22*k*k + S33*l*l + 2*S12*h*k + 2*S23*k*l + 2*S13*h*l) / (V*V)

def _candidate_hkls(h, k, l):
    """Integer (h,k,l) interpretations of a reflection row: the literal indices, PLUS — for
    OVERLAPPED lines written with indices concatenated per column (h='10', k='01', l='44' =
    (1,0,4)+(0,1,4)) — the per-digit split when h,k,l are digits-only of equal length >1.
    (Signed indices like '-2' never use this packing, so they fall through to the literal.)"""
    cands = []
    hi, ki, li = _int(h), _int(k), _int(l)
    if None not in (hi, ki, li):
        cands.append((hi, ki, li))
    hs, ks, ls = str(h).strip(), str(k).strip(), str(l).strip()
    if hs.isdigit() and ks.isdigit() and ls.isdigit() and len(hs) == len(ks) == len(ls) > 1:
        cands += [(int(hs[i]), int(ks[i]), int(ls[i])) for i in range(len(hs))]
    return cands

def check9_indexing(e, text):
    out = []
    cell = e.cell
    a, b, c = _val(cell.get('a')), _val(cell.get('b')), _val(cell.get('c'))
    al = _val(cell.get('α')) or 90; be = _val(cell.get('β')) or 90; ga = _val(cell.get('γ')) or 90
    if not (a and b and c) or not e.refl:
        return out
    bad = []
    n_checked = 0
    for d, I, h, k, l in e.refl:
        dv = _val(d)
        if dv is None:
            continue
        cands = [t for t in _candidate_hkls(h, k, l) if t != (0, 0, 0)]
        if not cands:
            continue
        n_checked += 1
        # A reflection is OK if ANY interpretation matches d_obs — take the closest candidate
        # (handles overlapped lines packed per column) before deciding it disagrees.
        best = None
        for hi, ki, li in cands:
            ds2 = _dstar2(a, b, c, al, be, ga, hi, ki, li)
            if ds2 <= 0:
                continue
            d_calc = 1 / math.sqrt(ds2); rel = abs(d_calc - dv) / dv
            if best is None or rel < best[0]:
                best = (rel, (hi, ki, li), d_calc)
        if best is None:
            continue
        # Weak reflections (relative intensity <20) are low-leverage and noisier, so a
        # small d-spacing discrepancy there isn't worth flagging — require >5% for them;
        # strong (or unknown-intensity) lines keep the >3% bar.
        Iv = _val(I)
        thresh = 0.05 if (Iv is not None and Iv < 20) else 0.03
        if best[0] > thresh:
            bad.append((d, '%d%d%d' % best[1], round(best[2], 4), round(best[0]*100, 1)))
    if bad:
        worst = sorted(bad, key=lambda x: -x[3])[:5]
        msg = ("%d of %d indexed reflections disagree with the stated cell "
               "(d_obs vs d_calc; >3%%, or >5%% for weak lines I<20): %s" % (len(bad), n_checked,
               '; '.join('%s (hkl %s)→%.4f [%.1f%%]' % (d, hkl, dc, p) for d, hkl, dc, p in worst)))
        large_esd = []
        for k in ('a', 'b', 'c'):
            s = cell.get(k, '')
            es = _esd(s); dec = _dec(s)
            if es and dec and int(es) * 10**(-dec) > 0.010:
                large_esd.append('%s=±%.3f' % (k, int(es) * 10**(-dec)))
        if large_esd:
            msg += (' — note large cell ESDs (%s Å); borderline discrepancies'
                    ' may reflect cell precision rather than errors' % ', '.join(large_esd))
        out.append(Finding('indexing', 'flag', msg, None, 'refl'))
    return out

# ----------------------------------------------------------------------------- 10. optical sign cross-check (docx vs PDF)
def check10_optical(e, text):
    out = []
    opt = e.comments.get('Optical Data', '')
    # extract sign from docx: "Sign=+" or "Sign=-"
    m = re.search(r'Sign\s*=\s*([+-])', opt or '', re.I)
    if not m or not text:
        return out
    docx_sign = m.group(1)

    # Normalise only genuine minus variants (Unicode minus U+2212, en/em-dashes).
    # Do NOT map control chars: the ± glyph in '(uniaxial −)/(biaxial +)' is often
    # dropped entirely by PDF extraction, leaving a control char like \x02 that may
    # have been EITHER sign — guessing it is a minus invents false mismatches
    # (e.g. real entries that are '+' in both PDF and docx). When the sign
    # can't be read cleanly we leave it undetermined and do not flag.
    norm = re.sub(r'[−–—]', '-', text)

    # scan PDF for optical sign phrases; stop at the first unambiguous statement
    sign_pats = [
        (r'optically\s+(?:uniaxial|biaxial)\s*[\(]?\s*([+-])', None),
        (r'(?:uniaxial|biaxial)\s*[\(]?\s*([+-])',              None),
        (r'optically\s+(positive|negative)',     {'positive': '+', 'negative': '-'}),
        (r'\bsign\s*[=:]\s*([+-])',             None),
        (r'\b(positive|negative)\s+(?:sign|optical)', {'positive': '+', 'negative': '-'}),
    ]
    pdf_sign = None
    for patt, word_map in sign_pats:
        pm = re.search(patt, norm, re.I)
        if pm:
            raw = pm.group(1)
            if word_map:
                pdf_sign = word_map.get(raw.lower())
            elif raw in ('+', '-'):
                pdf_sign = raw
            if pdf_sign:
                break

    if pdf_sign and pdf_sign != docx_sign:
        out.append(Finding('optical', 'flag',
                   "Optical sign mismatch: docx Sign=%s but .pdf indicates Sign=%s"
                   % (docx_sign, pdf_sign), None, 'name'))
    return out

# ----------------------------------------------------------------------------- 11. IMA number missing on a new mineral
def check11_ima(e, text):
    out = []
    ima = (e.comments.get('IMA Number') or '').strip()
    ima_given = bool(re.search(r'(?:19|20)\d{2}\D{1,3}\d', ima))   # 2018-131; sep may be any dash glyph
    if ima_given or not text:
        return out
    # Trigger only when the paper describes THIS mineral as NEW. A bare
    # 'IMA YYYY-NNN' is usually a REFERENCE citation for a different species
    # (e.g. 'Author… (year) Othername, IMA 20XX-XXX. CNMNC …'), and structural
    # reinvestigations of established minerals carry no proposal number — so keying
    # on the number alone both false-flags reinvestigations and
    # misses new minerals whose number is bracketed/odd-formatted.
    # The reliable signal: the entry's OWN name sits next to a new-mineral/approval
    # cue (and not merely in a reference to some other 'new mineral species').
    flat = re.sub(r'\s+', ' ', text)
    low = flat.lower()
    name = (e.name or '').strip().lower()
    name_root = re.sub(r'-?\([^)]*\)\s*$', '', name)        # drop '-(Y)' / '(Ce)'
    name_root = re.sub(r'-syn(thetic)?$', '', name_root).strip()
    if len(name_root) < 4:
        return out
    # A REDEFINITION / re-investigation of an EXISTING mineral is not 'new' — its blank
    # IMA-Number field is correct (the proposal is a redefinition, e.g. '22-F', not a new
    # IMA number). Suppress only when the entry's OWN name is the OBJECT of the cue (right
    # after it: 'redefinition of/for <name>') — NOT merely nearby, since a group paper may
    # redefine a DIFFERENT related species while THIS one is new (e.g. 'redefinition of
    # hiortdahlite' next to the new mineral moxuanxueite; donnayite-(Y) IS the redefined one).
    if re.search(r'(?:redefin|re-?investigat|re-?examin|re-?stud)\w*\b[^.]{0,18}?' + re.escape(name_root), low):
        return out
    is_new = False
    for cue in (r'new mineral', r'approved by the ima', r'approved by the commission on new min'):
        for m in re.finditer(cue, low):
            seg = low[max(0, m.start() - 60): m.end() + 60]
            if name_root not in seg:
                continue
            # skip REFERENCE citations (a different 'new mineral' cited in the
            # bibliography): author-year '(YYYY)', newsletter, 'et al.', DOI, pages
            wide = low[max(0, m.start() - 120): m.end() + 90]
            if re.search(r'\(\d{4}\)|newsletter|et al|doi|\bpp\.|'
                         r'\d+\s*[-–]\s*\d+\s*[.,]\s*(?:19|20)\d{2}|'   # <pages>, <year> citation tail
                         r'\d+\s*[-–]\s*\d+\.', wide):
                continue
            is_new = True; break
        if is_new:
            break
    if not is_new:
        return out
    # best-effort: pull the proposal number from an approval (non-reference) context
    NUM = r'((?:19|20)\d{2}\s*[-‐-―−–—]\s*\d{2,3}[A-Za-z]?)'
    num = None
    for m in re.finditer(r'IMA\s*(?:No\.?|Number|n[°o]\.?)?\s*' + NUM, flat):
        ctx = low[max(0, m.start() - 110): m.end() + 20]
        if re.search(r'\.\s*cnmnc|newsletter|\(\d{4}\)\s+[a-zü-]+,?\s*ima', ctx):
            continue                                        # reference citation
        num = re.sub(r'\s+', '', m.group(1)); break
    msg = (".pdf describes this as a new mineral but the docx IMA Number field is blank — add it"
           + (" (IMA %s)" % num if num else ""))
    out.append(Finding('ima', 'flag', msg + ".", None, 'ima'))
    return out

# ----------------------------------------------------------------------------- Mindat structural resolver (offline cache)
_MINDAT_STRUCT_IDX = None
def mindat_struct(name, exact=False):
    """Resolve a mineral name to its Mindat structural record — dict with cell
    (a,b,c,al,be,ga), sg (IT number), elements, formula, groupid — or None.
    Uses the offline struct cache (no API call during a review). Most reviewed
    species ARE in Mindat (~93% of the corpus); new minerals return None.
    NB: Mindat's cell is usually the SINGLE-CRYSTAL cell, so a comparison to the
    submitted powder cell must tolerate real powder-vs-SCXRD variance.
    exact=True matches only the exact normalised name (no variety/polytype
    fallback) — required for chemistry, where a variety ('Gypsum-strontian') or a
    Levinson suffix ('Parisite-(Nd)') has different elements than the base."""
    global _MINDAT_STRUCT_IDX
    if not name:
        return None
    try:
        from pxrd_review import mindat
        if _MINDAT_STRUCT_IDX is None:
            _MINDAT_STRUCT_IDX = {}
            for r in mindat.struct_db().get('recs', []):
                _MINDAT_STRUCT_IDX.setdefault(r['norm'], r)
        cands = [mindat._norm(name)] if exact else list(mindat._candidates(name))
        for cand in cands:
            if cand in _MINDAT_STRUCT_IDX:
                return _MINDAT_STRUCT_IDX[cand]
    except Exception:
        return None
    return None

# periodic-table symbols, for element-set extraction from formulas
_PT_ELEMENTS = frozenset((
    "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu "
    "Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba "
    "La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi "
    "Po At Rn Fr Ra Ac Th Pa U Np Pu").split())

def _clean_formula(f):
    f = f or ''
    f = re.sub(r'</?su[bp]>', '', f)              # <sub>/<sup>
    f = re.sub(r'&#?\w+;', ' ', f)                # HTML entities (&#60; &middot; vacancy box …)
    return re.sub(r'\$[A-Z]+[0-9.]*', ' ', f)     # $SI/$XS site markup

def _all_formula_elements(f):
    return {t for t in re.findall(r'[A-Z][a-z]?', _clean_formula(f)) if t in _PT_ELEMENTS}

def _essential_formula_elements(f):
    """Species-defining elements of an ideal formula: standalone elements with a
    non-trace coefficient (≥0.5), plus the DOMINANT (first-listed) cation of each
    multi-cation substitution site `(A,B,…)`. Excludes substituents and traces, and
    keeps polyanions/water (single-cation `(XO4)`/`(H2O)`/`(OH)`) whole. Order of
    site cations doesn't matter for the absent-from-other test that uses this."""
    f = _clean_formula(f)
    ess = set()
    for inner in re.findall(r'\(([^()]*)\)', f):
        els = [t for t in re.findall(r'[A-Z][a-z]?', inner) if t in _PT_ELEMENTS]
        non_o = [x for x in dict.fromkeys(els) if x not in ('O', 'H')]
        if len(non_o) <= 1:
            ess.update(els)                       # polyanion / water / hydroxyl — all essential
        else:
            seen = False
            for x in els:                         # substitution site: dominant cation only
                if x in ('O', 'H'):
                    ess.add(x)
                elif not seen:
                    ess.add(x); seen = True
    outside = re.sub(r'\([^()]*\)', ' ', f)       # standalone elements (skip traces <0.5)
    for m in re.finditer(r'([A-Z][a-z]?)\s*([0-9]*\.?[0-9]+)?', outside):
        el, co = m.group(1), m.group(2)
        if el in _PT_ELEMENTS and not (co and float(co) < 0.5):
            ess.add(el)
    return ess

# ----------------------------------------------------------------------------- CIF cross-check (Z and space group)
def parse_cif(cif_path):
    """Extract Z and space group from a CIF file, using the best structural data block."""
    try:
        with open(cif_path, encoding='utf-8', errors='replace') as f:
            text = f.read()
    except Exception:
        return {}

    def _block_data(block):
        d = {}
        m = re.search(r'_cell_formula_units_Z\s+(\d+)', block)
        if m:
            z = int(m.group(1))
            if 1 <= z <= 192:
                d['Z'] = z
        # cell parameters (kept as raw strings with esd, like the docx/.dft). The
        # .cif is normally the SINGLE-CRYSTAL determination, so a cross-check vs the
        # submitted powder cell must use a high tolerance (see check_sources).
        cell = {}
        for ax, tag in (('a', '_cell_length_a'), ('b', '_cell_length_b'), ('c', '_cell_length_c'),
                        ('α', '_cell_angle_alpha'), ('β', '_cell_angle_beta'), ('γ', '_cell_angle_gamma')):
            mm = re.search(tag + r'\s+(-?\d[\d.]*(?:\(\d+\))?)', block)
            if mm:
                cell[ax] = mm.group(1).strip()
        if cell:
            d['cell'] = cell
        for tag in ('_space_group_name_H-M_alt',
                    '_symmetry_space_group_name_H-M',
                    '_space_group_name_H-M'):
            m = re.search(tag + r"\s+'([^']+)'|" + tag + r'\s+(\S+)', block)
            if m:
                sg = (m.group(1) or m.group(2) or '').strip()
                if sg and sg != '?':
                    d['SG'] = sg
                    break
        for tag in ('_chemical_name_mineral', '_chemical_name_common'):
            m = re.search(tag + r"\s+'([^']+)'|" + tag + r'\s+(\S+)', block)
            if m:
                nm = (m.group(1) or m.group(2) or '').strip()
                if nm and nm != '?' and len(nm) > 2:
                    d.setdefault('mineral_name', nm)
                    break
        m = re.search(r"_chemical_formula_sum\s+(?:'([^']+)'|(\S[^\n]*))", block)
        if m:
            f = (m.group(1) or m.group(2) or '').strip()
            if f and f != '?':
                d['formula'] = f
        return d

    # Split into data blocks; pick the one that has both Z and SG (structural block)
    blocks = re.split(r'\ndata_', '\n' + text)
    best = {}
    for block in blocks[1:]:
        d = _block_data(block)
        # prefer a block that has atom-site data (genuine structure block)
        is_structural = bool(re.search(r'_atom_site_', block))
        if 'Z' in d and 'SG' in d and (is_structural or not best):
            best = d
            if is_structural:
                break   # atom_site block is authoritative — stop here
    if not best:                          # no Z+SG block — keep the richest (e.g. cell-only)
        for block in blocks[1:]:
            d = _block_data(block)
            if len(d) > len(best):
                best = d
    return best

def _norm_sg(s):
    """Normalise a H-M symbol for comparison.

    Handles ICDD long-form notation (P121/m1, C121, P1211, …) by removing
    the explicit identity-axis '1' markers that bracket the unique direction,
    then strips spaces and origin/setting suffixes.
    """
    s = re.sub(r'\s+', '', s or '').upper()
    s = re.sub(r':[0-9HR]$', '', s)         # :1 :2 :H :R origin suffixes
    # Long-form monoclinic: P121/m1 → P21/m, C121 → C2, P1211 → P21
    # Pattern: single lattice letter, then '1', middle op(s), then '1' at end
    s = re.sub(r'^([A-Z])1(.+?)1$', r'\1\2', s)
    return s

def _cif_name_ok(cif_data, e):
    """Return True if the CIF mineral name is compatible with the docx mineral name,
    or if the CIF has no name (can't verify). Catches mis-filed CIFs like one
    mineral's CIF stored under a different mineral's entry ID."""
    cif_nm = cif_data.get('mineral_name', '')
    if not cif_nm:
        return True   # no name in CIF — can't reject
    docx_nm = (e.name or e.primary or '')
    def _words(s): return set(re.findall(r'[a-z]{4,}', s.lower()))
    return bool(_words(cif_nm) & _words(docx_nm))

def _formula_atoms(s):
    """{element: count(float)} from a formula string ('H2 Mo O4'/'Mo2 O8'/'Pb1.50 O4.50');
    counts default to 1; fractional occupancies kept; charges/brackets/·nH2O ignored —
    enough to reconcile Z across formula-unit conventions."""
    d = {}
    for el, n in re.findall(r'([A-Z][a-z]?)\s*(\d+(?:\.\d+)?)?', s or ''):
        if el:
            d[el] = d.get(el, 0.0) + (float(n) if n else 1.0)
    return d

def check_cif(e, cif_data):
    """Cross-check docx Z against the CIF, skipping obviously wrong CIF matches."""
    out = []
    if not cif_data:
        return out
    if not _cif_name_ok(cif_data, e):
        return out   # CIF is for a different mineral — ignore entirely
    # Z — reliable across polytypes and settings; only flag when CIF Z > 1
    # (Z=1 in CIF often means Z per asymmetric unit, not per unit cell)
    docx_z_raw = e.cell.get('Z', '')
    docx_z = int(_val(docx_z_raw)) if _val(docx_z_raw) is not None else None
    cif_z = cif_data.get('Z')
    if docx_z is not None and cif_z is not None and cif_z > 1 and docx_z != cif_z:
        # The docx and CIF may use formula UNITS that differ by a multiple (e.g. docx
        # MoO3·H2O vs CIF Mo2O8), so Z differs while the cell CONTENTS are identical.
        # Reconcile via the DOMINANT framework cation (largest count, not O/H — it is fully
        # occupied so it scales cleanly, unlike refined fractional substituents): same cell
        # contents iff docx_Z·atoms == cif_Z·atoms for it. Flag only if it does NOT reconcile
        # (or the CIF lacks that cation entirely — e.g. a wrong/different-mineral CIF).
        da = _formula_atoms(e.formulas.get('Empirical') or e.formulas.get('Chemical') or '')
        ca = _formula_atoms(cif_data.get('formula') or '')
        cats = [el for el in da if el not in ('O', 'H')]
        anchor = max(cats, key=lambda el: da[el]) if cats else None
        if anchor and ca and not ca.get(anchor):
            # CIF lacks the mineral's dominant cation -> it is a different compound (a
            # mis-filed/garbage CIF), not a Z error. Note it (log only), don't docx-flag.
            out.append(Finding('cif', 'note',
                       "CIF chemistry doesn't match this mineral (no %s in the CIF formula) — "
                       "possibly a mis-filed CIF; Z cross-check skipped." % anchor, None, 'cif'))
        elif not (anchor and ca.get(anchor)
                  and abs(docx_z * da[anchor] - cif_z * ca[anchor]) < 0.5):
            out.append(Finding('cif', 'flag',
                       "Z mismatch: docx Z=%d but CIF Z=%d" % (docx_z, cif_z),
                       None, 'cell:Z'))
    # Space group: CIF comparison is unreliable for polytypic minerals and
    # entries where the CIF represents a different structural variant.
    # The correct reference is the PDF for the specific phase described.
    # SG check is therefore omitted here pending PDF-based SG extraction.
    return out

# ----------------------------------------------------------------------------- ICDD .dft (DataQuacker) parse — co-equal proxy, soft cross-check only
def _dft_comment_loop(text):
    """Parse the `loop_ _icdd_PDF_comment_type / _icdd_PDF_comment` block into
    {type: text}. Handles inline values ("IM 2021-068", "OP '…'") and ;-delimited
    multi-line blocks (AB analysis, DC data-collection)."""
    lines = text.splitlines()
    out = {}
    i = 0
    while i < len(lines):
        if lines[i].strip() == '_icdd_PDF_comment' and i and lines[i-1].strip() == '_icdd_PDF_comment_type':
            break
        i += 1
    i += 1
    cur = None
    while i < len(lines):
        s = lines[i].strip()
        if s.startswith('#') or s.startswith('data_') or s == 'loop_':
            break
        if s == ';':
            i += 1; buf = []
            while i < len(lines) and lines[i].strip() != ';':
                buf.append(lines[i].strip()); i += 1
            if cur:
                out[cur] = _sq(' '.join(buf))
            cur = None
        else:
            m = re.match(r"^([A-Z]{2})\s+'?(.*?)'?\s*$", s)
            if m and m.group(2):
                out[m.group(1)] = m.group(2).strip(); cur = None
            elif re.match(r'^[A-Z]{2}$', s):
                cur = s
        i += 1
    return out

def parse_dft(dft_path):
    """Extract the structured fields of an ICDD DataQuacker .dft (CIF-like). Returns
    {} on any failure — the .dft is supplementary, never load-bearing."""
    try:
        with open(dft_path, encoding='utf-8', errors='replace') as f:
            text = f.read()
    except Exception:
        return {}
    def g(key):
        m = re.search(r'^%s\s+(.+?)\s*$' % re.escape(key), text, re.M)
        if not m:
            return None
        v = m.group(1).strip().strip("'").strip()
        return None if v in ('', '?') else v
    d = {}
    cell = {}
    for ax, key in (('a', '_cell_length_a'), ('b', '_cell_length_b'), ('c', '_cell_length_c'),
                    ('α', '_cell_angle_alpha'), ('β', '_cell_angle_beta'), ('γ', '_cell_angle_gamma')):
        v = g(key)
        if v:
            cell[ax] = v
    d['cell'] = cell
    z = g('_cell_formula_units_Z')
    if z and re.match(r'\d+$', z):
        d['Z'] = int(z)
    for k, key in (('SG', '_space_group_name_H-M_alt'), ('volume', '_cell_volume'),
                   ('density', '_icdd_density_calculated'), ('temperature', '_diffrn_ambient_temperature'),
                   ('geometry', '_pd_instr_geometry'), ('method', '_exptl_method'),
                   ('intensity_details', '_icdd_PDF_intensity_meas_details')):
        v = g(key)
        if v:
            d[k] = v
    formulas = {}
    for fk, key in (('iupac', '_chemical_formula_iupac'), ('structural', '_chemical_formula_structural'),
                    ('analytical', '_chemical_formula_analytical'), ('general', '_icdd_PDF_general_formula')):
        v = g(key)
        if v:
            formulas[fk] = v
    d['formulas'] = formulas
    d['comments'] = _dft_comment_loop(text)   # {HB,OP,IM,AB,DC,...}
    return d

def _dft_fmt(s):
    """Display a .dft cell value, dropping a malformed esd (>4 digits) some .dft
    files carry, e.g. '124.0889970000(70000000)' -> '124.089'."""
    m = re.match(r'\s*(-?\d+\.?\d*)\s*(?:\((\d+)\))?', s or '')
    if not m:
        return s
    val, esd = m.group(1), m.group(2)
    if '.' in val and len(val.split('.')[1]) > 6:        # absurd precision -> round
        val = ('%.4f' % float(val)).rstrip('0').rstrip('.')
    return '%s(%s)' % (val, esd) if (esd and len(esd) <= 4) else val

def check_dft(e, dft_data):
    """Soft docx ↔ ICDD-.dft cross-check. The .dft is a CO-EQUAL PROXY, not ground
    truth (the PDF is the arbiter), so every finding is sev='note' — surfaced in the
    console/log as 'verify vs ICDD .dft', NEVER written into the docx. Stays quiet
    when they agree (≈91% of cells match exactly). Deliberately limited to the
    reliable structured signals: cell VALUE divergence, Z, and (measured-only)
    geometry. SG (notation differences), precision/esd (overlaps check8, and the
    docx is often the more complete one), temperature (.dft field is ambiguous) and
    the comment-loop fields (IMA/optical — garbled in some .dft) are NOT compared."""
    out = []
    if not dft_data:
        return out
    PRE = 'verify vs ICDD .dft'
    dcell = dft_data.get('cell', {})
    # Compare the cell HOLISTICALLY. Emit per-axis notes only when it's the SAME
    # cell with 1–2 discrepant axes (transcription-level). If most axes differ
    # (axis permutation / different setting or phase — common between a powder docx
    # and an SC .dft), stay quiet: that is not a transcription issue and the
    # docx-vs-PDF cell check is the real validator.
    diffs, ncomp = [], 0
    for k in ('a', 'b', 'c', 'α', 'β', 'γ'):
        dv_s, fv_s = e.cell.get(k), dcell.get(k)
        if not dv_s or not fv_s:
            continue
        dv, fv = _val(dv_s), _val(fv_s)
        if dv is None or fv is None:
            continue
        if k in ('α', 'β', 'γ') and fv in (90.0, 120.0) and dv in (90.0, 120.0):
            continue
        ncomp += 1
        tol = 0.05 if k in ('α', 'β', 'γ') else 0.0015
        if abs(dv - fv) > tol:
            diffs.append((k, dv_s, fv_s, abs(dv - fv)))
    same_cell = ncomp > 0 and len(diffs) <= 2 and (ncomp - len(diffs)) >= 1
    if diffs and same_cell:
        for k, dv_s, fv_s, d in diffs:
            out.append(Finding('dft', 'note', "%s — %s: docx=%s but .dft=%s (Δ=%.4f)."
                       % (PRE, k, _dft_fmt(dv_s), _dft_fmt(fv_s), d), None))
    # Z: only meaningful when the cells otherwise agree (a different cell scales Z
    # proportionally, which is not an error). Z-vs-CIF is covered separately.
    dz = _val(e.cell.get('Z'))
    if same_cell and not diffs and dz is not None and dft_data.get('Z') is not None and int(dz) != dft_data['Z']:
        out.append(Finding('dft', 'note', "%s — Z: docx=%d but .dft=%d (check the paper; a phase's "
                   "Z should match between SCXRD and powder)." % (PRE, int(dz), dft_data['Z']), None))
    # geometry: only for genuinely measured methods (a .dft 'Diffractometer:' default
    # vs a docx 'Calculated'/'Other' is not a real disagreement).
    sp = (e.instr.get('spacing_instr') or '').strip()
    geo = dft_data.get('geometry', '')
    if sp.lower() in MEASURED_METHODS and geo:
        geo_cls = geo.split(':')[0].strip()
        if geo_cls and sp.lower() != geo_cls.lower() and sp.lower() not in geo.lower():
            out.append(Finding('dft', 'note', "%s — Spacing Instr.=%r but .dft geometry=%r."
                       % (PRE, sp, geo), None))
    return out

# ----------------------------------------------------------------------------- 12. microprobe analysis field
# Elements commonly determined by calculation rather than direct measurement
_CALC_ELEMS = [
    ('H2O',      r'H2O'),
    ('CO2',      r'CO2'),
    ('B2O3',     r'B2O3'),
    ('(NH4)2O',  r'\(NH4\)2O'),
    ('F',        r'\bF\b'),
    ('N',        r'\bN\b(?!\s*a)'),   # avoid "Na"
]
# PDF phrases that indicate an element was calculated, not measured
_CALC_PDF = re.compile(
    r'(?:H2O|CO2|B(?:2O3)?|\(NH4\)|water|fluorine|nitrogen)'
    r'\s*(?:was\s+)?(?:calculated|by\s+stoich|by\s+differ|from\s+stoich)',
    re.I)
_CALC_PDF2 = re.compile(
    r'(?:calculated|stoichiometr\w+)\s+[^.]{0,40}?(?:H2O|CO2|B2O3|water)',
    re.I)

def check12_analysis(e, text):
    out = []
    analysis = (e.comments.get('Analysis') or '').strip()

    # --- 0. Analysis field empty: one combined comment per scenario ---
    if not analysis:
        field = _misplaced_analysis_field(e)
        if field:
            # data exists but in the wrong field — combine "empty" + "move it"
            out.append(Finding('analysis', 'flag',
                       "Analysis field is empty, but microprobe/analytical data is "
                       "present in the '%s' comment field — it should be moved to "
                       "the Analysis field." % field, None, 'analysis'))
        elif text and re.search(
                r'microprobe\s+anal|electron\s+(?:micro)?probe\s+anal|'
                r'EPMA\s+(?:anal|data|result)|EMP\s+anal|'
                r'wt\.?\s*%[^.]{0,60}:\s*[A-Z][a-z]',
                text, re.I):
            # PDF clearly reports an analysis that never made it into the docx
            out.append(Finding('analysis', 'flag',
                       ".pdf describes a chemical/microprobe analysis but the docx "
                       "Analysis field is empty — it may have been omitted.",
                       None, 'analysis'))
        else:
            # No analysis anywhere. Worth flagging only for a natural mineral whose
            # listed formula is clean end-member stoichiometry (i.e. likely the
            # ideal composition standing in for missing measured data). An already
            # non-stoichiometric formula means the empirical composition is present.
            is_mineral = any(c.lower() == 'mineral' for c, _ in e.subfiles)
            is_natural = any(c.lower() == 'natural' for c, _ in e.subfiles)
            formula = e.formulas.get('Empirical') or e.formulas.get('Chemical') or ''
            if is_mineral and is_natural and formula and not _looks_empirical(formula):
                out.append(Finding('analysis', 'flag',
                           "Analysis field is empty and the listed formula is clean "
                           "end-member stoichiometry — the measured (empirical) "
                           "composition appears to be missing.", None, 'analysis'))
        return out

    # strip formula portion that sometimes follows a bare ':'
    # handles ": Ca1.00...", ": (Pd0.76...)", ":(K0.65...)" etc.
    analysis_data = re.split(r':\s*[\(\[]|:\s*(?=[A-Z][a-z])', analysis)[0]

    # --- 1. Number of analyses ---
    m_docx = re.search(r'average\s+of\s+(\d+)', analysis, re.I)
    n_docx = int(m_docx.group(1)) if m_docx else None
    n_pdf  = None
    if text:
        for pat in [
            r'average\s+of\s+(\d+)\s*(?:analyses|points|spots|measurements|grains)',
            r'(?<![.\d])(\d+)\s+(?:electron[-\s]?)?(?:micro)?probe\s+(?:point\s+)?anal',
            r'(?<![.\d])(\d+)\s+(?:WDS|EDS|EPMA)\s+(?:anal|point|spot|meas)',
        ]:
            m = re.search(pat, text, re.I)
            if m:
                n = int(m.group(1))
                if 2 <= n <= 50:   # sanity: typical microprobe session
                    n_pdf = n
                break
    if n_pdf and not n_docx:
        out.append(Finding('analysis', 'flag',
                   "Analysis count missing — .pdf gives n=%d" % n_pdf, None, 'analysis'))
    elif n_pdf and n_docx and n_pdf != n_docx:
        out.append(Finding('analysis', 'flag',
                   "Analysis count mismatch: docx=%d, .pdf=%d" % (n_docx, n_pdf),
                   None, 'analysis'))

    # --- 2. Calculated light elements missing (calc) notation ---
    if text:
        pdf_calc_txt = text.lower()
        for elem, pat in _CALC_ELEMS:
            # does the PDF indicate this element was calculated?
            # Only flag when the element name is directly followed by a
            # "calculated" qualifier — avoids "calculation of empirical formula"
            # false positives where 'calculated' appears later in the same passage.
            pdf_says_calc = bool(re.search(
                r'(?:' + pat + r')\s*(?:\([^)]*\)\s*)?(?:was\s+)?'
                r'(?:calculated|by\s+stoich|by\s+differ|from\s+stoich)',
                text, re.I
            ))
            if not pdf_says_calc:
                continue
            # is the element present in the docx analysis field?
            if not re.search(pat, analysis_data, re.I):
                continue
            # is it already marked (calc)?
            marked = bool(re.search(
                pat + r'\s*\(calc|\(calc\)\s*' + pat, analysis_data, re.I))
            if not marked:
                out.append(Finding('analysis', 'flag',
                           "Analysis: %s is calculated per .pdf but not marked (calc) "
                           "in docx" % elem, None, 'analysis'))

    # --- 3. wt.% total sanity ---
    # Prefer an explicit "Total XX.XX" stated in the analysis over summing values,
    # since summing is fragile (formula leakage, –O=F corrections, etc.)
    total_m = re.search(r'[Tt]otal\s+(\d{2,3}\.?\d*)', analysis_data)
    if total_m:
        total = float(total_m.group(1))
        if total < 94:
            out.append(Finding('analysis', 'flag',
                       "Analysis explicit total = %.1f%% (below 94%% — possible "
                       "missing oxide or transcription error)" % total, None, 'analysis'))
        elif total > 103:
            out.append(Finding('analysis', 'flag',
                       "Analysis explicit total = %.1f%% (above 103%% — possible "
                       "transcription error)" % total, None, 'analysis'))
    return out

# ----------------------------------------------------------------------------- 13. non-ambient PXRD collection temperature
def check13_temperature(e, text):
    out = []
    temp_str = (e.comments.get('Temperature') or '').strip()
    if not temp_str:
        return out
    # parse temperature in K or °C
    m = re.search(r'(-?\d+(?:\.\d+)?)\s*K', temp_str)
    t_k = float(m.group(1)) if m else None
    if t_k is None:
        m = re.search(r'(-?\d+(?:\.\d+)?)\s*[°]?\s*C', temp_str)
        t_k = float(m.group(1)) + 273.15 if m else None
    if t_k is None or 283 <= t_k <= 310:
        return out   # ambient or unreadable — skip
    dc = (e.comments.get('DC') or '').lower()
    if re.search(r'single.crystal|synchrotron|scxrd', dc, re.I):
        note = ('note: if this temperature refers to the SCXRD not the PXRD '
                'collection, the entry cell is unaffected — verify')
    else:
        note = ('non-ambient PXRD collection; confirm cell parameters represent '
                'the correct temperature state of the material')
    out.append(Finding('temperature', 'flag',
               "Collection temperature = %s (%g K) — %s" % (temp_str, t_k, note),
               None, 'instr'))
    return out

# ----------------------------------------------------------------------------- density helpers
# Standard atomic weights (IUPAC, abridged) — enough for rock-forming chemistry.
_ATWT = {
 'H':1.008,'Li':6.941,'Be':9.012,'B':10.811,'C':12.011,'N':14.007,'O':15.999,
 'F':18.998,'Na':22.990,'Mg':24.305,'Al':26.982,'Si':28.086,'P':30.974,'S':32.06,
 'Cl':35.45,'K':39.098,'Ca':40.078,'Sc':44.956,'Ti':47.867,'V':50.942,'Cr':51.996,
 'Mn':54.938,'Fe':55.845,'Co':58.933,'Ni':58.693,'Cu':63.546,'Zn':65.38,'Ga':69.723,
 'Ge':72.630,'As':74.922,'Se':78.971,'Br':79.904,'Rb':85.468,'Sr':87.62,'Y':88.906,
 'Zr':91.224,'Nb':92.906,'Mo':95.95,'Ag':107.868,'Cd':112.414,'In':114.818,'Sn':118.710,
 'Sb':121.760,'Te':127.60,'I':126.904,'Cs':132.905,'Ba':137.327,'La':138.905,'Ce':140.116,
 'Pr':140.908,'Nd':144.242,'Sm':150.36,'Eu':151.964,'Gd':157.25,'Tb':158.925,'Dy':162.500,
 'Ho':164.930,'Er':167.259,'Tm':168.934,'Yb':173.045,'Lu':174.967,'Hf':178.49,'Ta':180.948,
 'W':183.84,'Re':186.207,'Os':190.23,'Ir':192.217,'Pt':195.084,'Au':196.967,'Hg':200.592,
 'Tl':204.38,'Pb':207.2,'Bi':208.980,'Th':232.038,'U':238.029,
}
def _formula_mass(formula):
    """Molar mass of a simple space/paren-free integer formula like
    'Cs F2 Li2 O10 Si4 Ti'. Returns None if any element is unknown or no atoms."""
    if not formula:
        return None
    # strip charges/parentheses/commas; tokens are Element + optional integer count
    cleaned = re.sub(r'[(),]|[+\-]\d*', ' ', formula)
    total = 0.0; n = 0
    for el, cnt in re.findall(r'([A-Z][a-z]?)(\d*\.?\d*)', cleaned):
        if el not in _ATWT:
            return None
        c = float(cnt) if cnt else 1.0
        total += _ATWT[el] * c; n += 1
    return total if n else None

def _cell_volume(cell):
    """Unit-cell volume (Å³) from the docx cell dict; general triclinic formula."""
    a, b, c = _val(cell.get('a')), _val(cell.get('b')), _val(cell.get('c'))
    al = math.radians(_val(cell.get('α')) or 90)
    be = math.radians(_val(cell.get('β')) or 90)
    ga = math.radians(_val(cell.get('γ')) or 90)
    if not (a and b and c):
        return None
    ca, cb, cg = math.cos(al), math.cos(be), math.cos(ga)
    fac = 1 - ca*ca - cb*cb - cg*cg + 2*ca*cb*cg
    return a*b*c*math.sqrt(fac) if fac > 0 else None

def _ideal_density(e):
    """Density (g/cm³) computed from the integer ideal/end-member formula in the
    docx (the 'Empirical' field holds the summed ideal composition), with the
    docx cell volume and Z. Returns (Dx, M, V, Z) or None."""
    formula = e.formulas.get('Empirical') or e.formulas.get('Chemical') or ''
    M = _formula_mass(formula)
    V = _cell_volume(e.cell)
    z = _val(e.cell.get('Z'))
    if not (M and V and z):
        return None
    return (1.66054 * z * M / V, M, V, int(z))

# ----------------------------------------------------------------------------- 14. calculated density vs PDF
def check14_density(e, text):
    out = []
    # extract Dx from raw rows (row label 'Dx : ' or 'Xtl Dx')
    dx_docx = None
    for r in (e.raw_rows or []):
        if r and re.search(r'^Dx\s*:?\s*$', (r[0] or '').strip()):
            val = r[1].strip() if len(r) > 1 else ''
            try:
                dx_docx = float(val)
            except ValueError:
                pass
            break
    if not dx_docx or not text:
        return out
    # extract calculated density from PDF prose
    dx_pdf = None
    for patt in [
        r'(?:calculated\s+)?density[^.\n]{0,60}?=\s*([\d]+\.[\d]{2,4})\s*g',
        r'[ρDd][cx]\s*=\s*([\d]+\.[\d]{2,4})\s*g',
        r'density\s*\(calc[^)]*\)\s*[=:]\s*([\d]+\.[\d]{2,4})',
        r'ρ\s*calc\s*=\s*([\d]+\.[\d]{2,4})',
        r'calculated density[^.\n]{0,40}?([\d]+\.[\d]{2,3})\s*g\s*/\s*cm',
    ]:
        m = re.search(patt, text, re.I)
        if m:
            v = float(m.group(1))
            if 1.0 < v < 25.0:
                dx_pdf = v
                break
    if dx_pdf is None:
        return out
    diff_pct = abs(dx_docx - dx_pdf) / dx_pdf * 100
    if diff_pct > 3.0:
        msg = ("Density mismatch: docx Dx=%.3f g/cm³ but .pdf states %.3f "
               "(%.1f%% difference)" % (dx_docx, dx_pdf, diff_pct))
        # Resolve the basis: compute the ideal/end-member density from the docx
        # cell + Z. Whichever stated value it matches reveals the formula basis;
        # a value well below ideal indicates the empirical (vacancy/substituted)
        # formula was used.
        idl = _ideal_density(e)
        if idl:
            d_ideal = idl[0]
            def near(x): return abs(x - d_ideal) / d_ideal < 0.01
            tag_docx = 'ideal' if near(dx_docx) else 'empirical/other'
            tag_pdf  = 'ideal' if near(dx_pdf) else 'empirical/other'
            msg += (". Ideal-formula density = %.3f (Z=%d, V=%.1f Å³) → "
                    "docx uses %s basis, .pdf uses %s basis"
                    % (d_ideal, idl[3], idl[2], tag_docx, tag_pdf))
        out.append(Finding('density', 'flag', msg, None, 'name'))
    return out

# ----------------------------------------------------------------------------- 15. strongest-lines cross-check (egregious mismatches only)
def check15_strongest_lines(e, text):
    """Flag only when the PDF's explicitly stated I=100 line is absent from the
    docx reflection list — egregious missing-line cases, not minor rank shifts."""
    out = []
    if not e.refl or not text:
        return out
    # extract the top d-spacing (I=100) from the PDF "strongest lines" passage
    # common patterns: "3.276 [100]", "d=3.276 I=100", "3.276(100)"
    pdf_100 = None
    for patt in [
        r'([\d]+\.[\d]{2,4})\s*[(\[{/]\s*100\s*[)\]/}]',
        r'd\s*=\s*([\d]+\.[\d]{2,4})[^\n]{0,20}I\s*=\s*100',
        r'100\.0?\s*[(\[/]\s*([\d]+\.[\d]{2,4})',
    ]:
        m = re.search(patt, text, re.I)
        if m:
            v = float(m.group(1))
            if 0.5 < v < 15.0:
                pdf_100 = v
                break
    if pdf_100 is None:
        return out
    # check if this d-spacing appears in the docx reflection list (within 1%)
    docx_ds = [_val(d) for d, I, h, k, l in e.refl if _val(d)]
    if not docx_ds:
        return out
    match = any(abs(d - pdf_100) / pdf_100 < 0.01 for d in docx_ds)
    if not match:
        # confirm it's not just a combined/multiplet line
        closest = min(docx_ds, key=lambda d: abs(d - pdf_100))
        out.append(Finding('strongest_lines', 'flag',
                   ".pdf strongest line (I=100, d=%.4f Å) not found in docx "
                   "reflection list (closest: %.4f Å, %.1f%% off) — possible "
                   "missing reflection or wrong cell assignment"
                   % (pdf_100, closest, abs(closest-pdf_100)/pdf_100*100),
                   None, 'refl'))
    return out

# ----------------------------------------------------------------------------- driver
# NOTE: check14_density is intentionally NOT registered. A batch survey showed the
# docx Dcalc is computed from the empirical formula about as often as from the ideal
# end-member (no single convention), so a docx/PDF density difference is normally
# just a formula-basis choice, not an error. (The ideal-density helpers are retained
# for possible future use, e.g. catching a grossly mistyped density.)
# =============================================================================
# 16/17. Instrumentation designators + 18. mineral naming
# -----------------------------------------------------------------------------
# Reference tables below were derived by mining the corrected corpus
# (ICDD/TAO/Tony's/2028) and then hand-curated. They are deliberately small and
# editable. Per the project's convention these checks COMMENT/SUGGEST only — the
# annotator highlights the cell and writes the suggested value; it never rewrites
# a field. Note: the reviewer keeps 'Spacing Instr.' generic (Diffractometer/
# Film/Other) and records the SPECIFIC camera/geometry as a comment — so the
# instrument logic SURFACES the geometry (info), it does not "correct" Spacing
# Instr. to e.g. 'Gandolfi'.
# =============================================================================

# --- controlled vocabularies: canonical spellings seen in corrected entries ---
VOCAB_CANON = {
    'spacing_instr':   {'Diffractometer', 'Calculated', 'Film', 'Camera', 'Gandolfi',
                        'Guinier', 'Debye-Scherrer', 'Visual', 'Image plate', 'Other'},
    'intensity_instr': {'Diffractometer', 'Calculated', 'Film', 'Gandolfi', 'Guinier',
                        'Debye-Scherrer', 'Visual', 'Image plate', 'Other'},
    'intensity_type':  {'Integrated', 'Peak', 'Visual'},
    'filter':          {'Monochromator Crystal', 'Beta-Filter', 'None'},
}
# observed misspellings / casing variants -> canonical (lowercased keys)
VOCAB_FIX = {
    'spacing_instr':   {'diffractomter': 'Diffractometer', 'diffractomer': 'Diffractometer'},
    'intensity_instr': {'diffractomter': 'Diffractometer', 'diffractomer': 'Diffractometer'},
    'intensity_type':  {'visual?': 'Visual'},
    'filter':          {'monochromator crystal': 'Monochromator Crystal',
                        'monochromator': 'Monochromator Crystal',
                        'beta-filter': 'Beta-Filter', 'beta filter': 'Beta-Filter',
                        'β-filter': 'Beta-Filter'},
}
# Kβ-filter element fixed by the anode (foil with Z just below the anode's).
KBETA_FILTER = {'cr': 'V', 'fe': 'Mn', 'co': 'Fe', 'ni': 'Co', 'cu': 'Ni', 'mo': 'Zr', 'ag': 'Pd'}
# crystal-monochromator materials that legitimately appear as FilterType
MONO_MATERIALS = {'graph', 'graphite', 'ge', 'si', 'quartz', 'lif', 'diamond'}
# genuinely MEASURED collection methods (anode/intensity-type are then required).
# Excludes 'Calculated' and 'Other' (collapsed/derived from single-crystal data),
# where a blank radiation/intensity-type is legitimate.
MEASURED_METHODS = {'diffractometer', 'film', 'camera', 'gandolfi', 'guinier',
                    'debye-scherrer', 'visual', 'image plate'}

# UNAMBIGUOUS PDF monochromator/β-filter phrases -> (display, Filter, FilterType).
# Used only to FILL a blank docx Filter when the phrase sits in a powder-context
# sentence (so the single-crystal monochromator is not mis-attributed). The element
# prefix on '<El>-filtered' avoids the sample-prep 'was/then filtered' false hits.
PDF_FILTER_PATTERNS = [
    (r'graphite[\s-]*monochromat',                 'graphite monochromator', 'Monochromator Crystal', 'Graph'),
    (r'(?:germanium|\bGe)[\s-]*monochromat',       'Ge monochromator',       'Monochromator Crystal', 'Ge'),
    (r'(?:silicon|\bSi)[\s-]*monochromat',         'Si monochromator',       'Monochromator Crystal', 'Si'),
    (r'quartz[\s-]*monochromat',                   'quartz monochromator',   'Monochromator Crystal', 'Quartz'),
    (r'(?:nickel|\bNi)[\s-]*filter(?:ed)?\b',      'Ni β-filter',            'Beta-Filter', 'Ni'),
    (r'(?:iron|\bFe)[\s-]*filter(?:ed)?\b',        'Fe β-filter',            'Beta-Filter', 'Fe'),
    (r'(?:manganese|\bMn)[\s-]*filter(?:ed)?\b',   'Mn β-filter',            'Beta-Filter', 'Mn'),
    (r'(?:zirconium|\bZr)[\s-]*filter(?:ed)?\b',   'Zr β-filter',            'Beta-Filter', 'Zr'),
    (r'(?:vanadium|\bV)[\s-]*filter(?:ed)?\b',     'V β-filter',             'Beta-Filter', 'V'),
]
_POWDER_CTX = re.compile(r'powder|pxrd|p-?xrd|gandolfi|debye|guinier', re.I)
# PDF cues that the radiation is synchrotron (tunable λ, anode should be 'Sync').
_SYNCHROTRON = re.compile(r'synchrotron|beamline|\bSR-?(?:PXD|XRD|PD)\b|\bESRF\b|\bALBA\b|'
                          r'\bAPS\b|diamond light|spring-?8|\bDESY\b|\bELETTRA\b|petra\s*iii',
                          re.I)

def _anode_from_lambda(lam):
    """Reverse-lookup a docx λ to a characteristic anode line (display, Δ) within
    0.002 Å, else None — e.g. a tunable synchrotron wavelength matches nothing."""
    lv = _val(lam)
    if lv is None:
        return None
    best = None
    for el, lines in CANON.items():
        for line, wl in lines.items():
            d = abs(wl - lv)
            if best is None or d < best[1]:
                best = (el.capitalize() + 'K' + {'ka1': 'α1', 'ka': 'α', 'ka2': 'α2'}[line], d)
    return best if (best and best[1] <= 0.002) else None

def _anode_el2(anode):
    a = (anode or '').lower()
    for el in ('cr', 'fe', 'co', 'ni', 'cu', 'mo', 'ag'):
        if a.startswith(el):
            return el
    return None

def check16_instr_vocab(e, text):
    """Controlled-vocabulary spelling/casing of the instrumentation designators,
    plus cross-field physics consistency (β-filter element, monochromator
    material, Calculated coherence). Suggests the canonical value in a comment."""
    import difflib
    out = []
    instr = e.instr
    for field, label in (('spacing_instr', 'Spacing Instr.'), ('intensity_instr', 'Intensity Instr.'),
                         ('intensity_type', 'Intensity Type'), ('filter', 'Filter')):
        v = (instr.get(field) or '').strip()
        if not v:
            continue
        canon = VOCAB_CANON.get(field, set())
        if v in canon:
            continue
        fix = VOCAB_FIX.get(field, {}).get(v.lower())
        if not fix:
            # catch unseen typos by closeness, but never force a far-off value
            m = difflib.get_close_matches(v, canon, n=1, cutoff=0.86)
            fix = m[0] if m else None
        if fix and fix != v:
            out.append(Finding('instr_vocab', 'flag',
                       "%s = %r — should be %r." % (label, v, fix), None, 'instr'))
    # β-filter element must match the anode
    filt = (instr.get('filter') or '').strip().lower()
    ft = (instr.get('filtertype') or '').strip()
    el = _anode_el2(instr.get('anode'))
    if filt.replace(' ', '').startswith('beta') and el and el in KBETA_FILTER:
        want = KBETA_FILTER[el]
        if ft and ft.lower() != want.lower():
            out.append(Finding('instr_vocab', 'flag',
                       "FilterType = %r with a β-filter on %s — the Kβ filter for %s is %s."
                       % (ft, instr.get('anode'), instr.get('anode'), want), None, 'instr'))
        elif not ft:
            out.append(Finding('instr_vocab', 'note',
                       "β-filter on %s but FilterType is blank — expected %s."
                       % (instr.get('anode'), want), None, 'instr'))
    # monochromator crystal carries a crystal material, not a β-filter foil
    if 'monochromator' in filt and ft and ft.lower() not in MONO_MATERIALS:
        out.append(Finding('instr_vocab', 'note',
                   "Filter = Monochromator Crystal but FilterType = %r (expected a crystal "
                   "material, e.g. Graph/Ge/Si)." % ft, None, 'instr'))
    # Measured (empirical) powder data must record its radiation source and an
    # intensity type. We only assert these for genuinely MEASURED methods — NOT for
    # 'Calculated'/'Other' (a pattern collapsed/derived from single-crystal data),
    # where a blank is legitimate. Corpus blank rates among measured entries are low
    # (anode 1/83, intensity-type 3/83), so these are rare, high-confidence catches.
    # (We do NOT prescribe Integrated vs Peak: the same instrument uses both.)
    sp_raw = (instr.get('spacing_instr') or '').strip()
    if sp_raw.lower() in MEASURED_METHODS:
        if not (instr.get('anode') or '').strip():
            # a blank anode with a λ given isn't really "missing": derive the source
            # from the wavelength (characteristic line, or synchrotron via the PDF).
            lam = (instr.get('lam') or '').strip()
            guess = _anode_from_lambda(lam) if lam else None
            if guess:
                out.append(Finding('instr_vocab', 'flag',
                           "Radiation/anode is blank but λ=%s is given — matches %s (Δ=%.5f Å); "
                           "set the anode." % (lam, guess[0], guess[1]), None, 'radiation'))
            elif lam and text and _SYNCHROTRON.search(text):
                out.append(Finding('instr_vocab', 'flag',
                           "Radiation/anode is blank; λ=%s matches no characteristic tube line and the "
                           ".pdf describes synchrotron radiation — set the anode to Sync." % lam,
                           None, 'radiation'))
            elif lam:
                out.append(Finding('instr_vocab', 'flag',
                           "Radiation/anode is blank; λ=%s matches no characteristic tube line "
                           "(synchrotron?) — specify the source." % lam, None, 'radiation'))
            else:
                out.append(Finding('instr_vocab', 'flag',
                           "Radiation/anode is blank but the powder data are measured "
                           "(Spacing Instr.=%s) — specify the radiation source." % sp_raw,
                           None, 'radiation'))
        if not (instr.get('intensity_type') or '').strip():
            out.append(Finding('instr_vocab', 'flag',
                       "Intensity Type is blank for measured powder data "
                       "(Spacing Instr.=%s) — set Integrated or Peak." % sp_raw, None, 'instr'))
    # NB: do NOT flag 'Spacing=Calculated, Intensity=Other' as incoherent. That is
    # the standard, correct encoding for a powder pattern calculated from single-
    # crystal/synchrotron structure data: d-spacings calculated from the cell, but
    # the intensities 'Other' = collapsed/derived from the (observed) single-crystal
    # structure factors rather than model-calculated. 'Calculated/Calculated' (both
    # simulated from the atomic model) and 'Calculated/Other' (intensities collapsed
    # from real data) are BOTH valid. 'Other' is a meaningful designator, not a
    # placeholder for 'unknown', so there is no cross-field rule to enforce here.
    return out

# --- 17. PDF monochromator/β-filter -> fill a blank docx Filter --------------
def check17_pdf_filter(e, text):
    """When the docx Filter field is BLANK but the PDF unambiguously names the
    monochromator/β-filter IN A POWDER-CONTEXT sentence (so the single-crystal
    monochromator isn't mis-attributed), suggest filling it as a comment."""
    out = []
    if not text or (e.instr.get('filter') or '').strip():
        return out                       # no PDF, or Filter already populated
    for s in _sentences(text):
        if not _POWDER_CTX.search(s):
            continue                     # only powder-context sentences
        for pat, display, filt, ftype in PDF_FILTER_PATTERNS:
            if re.search(pat, s):
                out.append(Finding('instr_filter', 'flag',
                           "Filter field is blank but the .pdf describes a %s for the powder "
                           "data — add Filter = %s, FilterType = %s." % (display, filt, ftype),
                           _sq(s)[:160], 'filter'))
                return out               # one suggestion is enough
    return out

# --- 18. mineral name vs ideal formula --------------------------------------
REE_ELEMENTS = ['La', 'Ce', 'Pr', 'Nd', 'Pm', 'Sm', 'Eu', 'Gd', 'Tb', 'Dy', 'Ho',
                'Er', 'Tm', 'Yb', 'Lu', 'Y', 'Sc']
# polytype trailing letter -> acceptable crystal-system letter(s) in the docx
# (trigonal 'T' is reported under hexagonal/rhombohedral here; tetragonal is 'Q').
POLYTYPE_SYS = {'A': {'a'}, 'M': {'m'}, 'O': {'o'}, 'Q': {'t'},
                'T': {'h', 'r'}, 'H': {'h', 'r'}, 'R': {'r', 'h'}, 'C': {'c'}}

def _ree_coeffs(formula):
    """{REE element: max numeric coefficient seen} from a formula string. A REE
    with no explicit number counts as 1.0 (lookahead avoids matching e.g. 'Y'
    inside 'Yb')."""
    out = {}
    for el in REE_ELEMENTS:
        for m in re.finditer(el + r'(?![a-z])\s*([0-9]+\.?[0-9]*)?', formula or ''):
            v = float(m.group(1)) if m.group(1) else 1.0
            out[el] = max(out.get(el, 0.0), v)
    return out

def check18_name_formula(e, text):
    """Levinson rare-earth suffix must name the dominant REE in the formula;
    polytype suffix letter must be consistent with the crystal system."""
    out = []
    nm = e.primary or e.name or ''
    # Levinson suffix -(Ce)/-(La)/-(Y)... — use the empirical/measured formula
    m = re.search(r'-\(([A-Z][a-z]?)\)\s*$', nm)
    if m and m.group(1) in REE_ELEMENTS:
        suf = m.group(1)
        formula = (e.formulas.get('Empirical') or e.formulas.get('Structural')
                   or e.formulas.get('Chemical') or e.formulas.get('General') or '')
        coeffs = _ree_coeffs(formula)
        numbered = {el: v for el, v in coeffs.items() if re.search(el + r'(?![a-z])\s*[0-9]', formula or '')}
        base = re.sub(r'-\([A-Za-z]+\)\s*$', '', nm)
        if len(numbered) >= 2:
            top = max(numbered.values())
            winners = [el for el, v in numbered.items() if abs(v - top) < 1e-9]
            if len(winners) == 1 and winners[0] != suf:
                out.append(Finding('name_formula', 'flag',
                           "Levinson suffix -(%s) but the dominant rare-earth in the formula is "
                           "%s — name should be %s-(%s)." % (suf, winners[0], base, winners[0]),
                           None, 'name'))
        elif coeffs and suf not in coeffs:
            out.append(Finding('name_formula', 'note',
                       "Levinson suffix -(%s) but %s is not present in the formula — verify the "
                       "dominant rare-earth." % (suf, suf), None, 'name'))
    # polytype suffix -1M / -2O / -3T ...
    mp = re.search(r'-(\d+)([A-Z])\s*$', nm)
    if mp:
        letter = mp.group(2)
        sysl = _sys_letter(e)
        allowed = POLYTYPE_SYS.get(letter)
        if allowed and sysl and sysl in 'amothrc' and sysl not in allowed:
            out.append(Finding('name_formula', 'flag',
                       "Polytype suffix -%s%s implies a %s lattice, but the crystal system is %r "
                       "— verify." % (mp.group(1), letter, letter, e.crystal_system or sysl),
                       None, 'name'))
    return out

# --- 19. Intensity Type follows the detector -------------------------------
# Area detectors collect the diffraction as a 2D ring and INTEGRATE it over the
# area (Integrated): image plate, Gandolfi / pseudo-Gandolfi, Guinier, R-AXIS
# RAPID, curved imaging plate. Bragg-Brentano slit optics give true peak heights
# (Peak). (Detected only in a powder-context sentence so an SC detector isn't
# mis-attributed.) This is the reviewer's single most frequent comment.
# 'Guinier' is also a common author surname (André Guinier) — require camera/method
# context so a "Guinier et al." citation isn't read as the diffraction method.
AREA_DETECTOR  = (r'image[- ]?plate|imaging plate|gandolfi|r-?axis\s*rapid|curved imaging'
                  # modern 2D / area detectors — a PXRD pattern from one is Integrated
                  r'|pixel[- ]?array|hybrid[- ]?photon|photon[- ]?counting|pilatus|eiger|dectris'
                  r'|\bccd\b|\bcmos\b|area detector|2d detector')
GUINIER_CAMERA = r'guinier[\s-]?(?:camera|geometry|focusing|method|film|image|de[\s-]?wolff)'
BRAGG_BRENTANO = r'bragg[\s–-]?brentano'

def check19_intensity_detector(e, text):
    out = []
    it = (e.instr.get('intensity_type') or '').strip()
    if not it or not text:
        return out
    # Intensity Type is meaningless for most CALCULATED patterns (it's a modelling
    # choice, not a detector fact). The patterns where it does matter are recorded
    # as measured in the docx (e.g. Kiryuite is Spacing=Diffractometer even though
    # the paper calculated the pattern), so they still reach this check.
    if (e.instr.get('spacing_instr') or '').strip().lower() == 'calculated' or \
       (e.instr.get('intensity_instr') or '').strip().lower() == 'calculated':
        return out
    area_kw = bb_kw = None                       # remember the matched phrase (for the GUI zoom)
    for s in _sentences(text):
        if not _POWDER_CTX.search(s):
            continue
        m = re.search(AREA_DETECTOR, s, re.I) or re.search(GUINIER_CAMERA, s, re.I)
        if m:
            area_kw = area_kw or m.group(0)
        mb = re.search(BRAGG_BRENTANO, s, re.I)
        if mb:
            bb_kw = bb_kw or mb.group(0)
    if area_kw and not bb_kw and it.lower() == 'peak':
        out.append(Finding('intensity_type', 'flag',
                   ".pdf describes an area detector (%s), so Intensity Type should be "
                   "Integrated, not Peak." % area_kw, area_kw, 'instr'))
    elif bb_kw and not area_kw and it.lower() == 'integrated':
        out.append(Finding('intensity_type', 'flag',
                   ".pdf describes Bragg-Brentano geometry, so Intensity Type should be "
                   "Peak, not Integrated.", bb_kw, 'instr'))
    return out

# --- 20. calculated pattern must document its wavelength --------------------
def check20_calc_wavelength(e, text):
    """A calculated pattern should state the λ it was computed at. When the docx is
    Calculated and its λ does not appear in the paper, flag it (the reviewer's 'no
    mention of the wavelength the calculated pattern was based on')."""
    out = []
    if not text:
        return out
    spac = (e.instr.get('spacing_instr') or '').strip().lower()
    inten = (e.instr.get('intensity_instr') or '').strip().lower()
    if spac != 'calculated' and inten != 'calculated':
        return out
    lam = (e.instr.get('lam') or '').strip()
    lv = _val(lam)
    if lv is None:
        return out
    flat = re.sub(r'\s+', ' ', text)
    near = {'%.3f' % (lv + d) for d in (-0.001, 0.0, 0.001)} | {'%.2f' % lv}
    if any(n in flat for n in near):
        return out                                   # the numeric λ is documented
    el = _anode_el2(e.instr.get('anode'))            # …or the anode is named (e.g. 'CuKα')
    if el and re.search(r'\b%s\s*k' % el, flat, re.I):
        return out
    out.append(Finding('calc_wavelength', 'flag',
               "Calculated pattern: λ=%s is not stated in the paper — confirm the wavelength "
               "used for the calculation." % lam, None, 'radiation'))
    return out

# --- 21. Primary (systematic) name normalization ---------------------------
# Mechanical nomenclature fixes the reviewers make to the Primary name, learned
# from the tracked-change edits and validated to reproduce real fixes with ZERO
# false positives on accepted names. Deliberately limited to STRING-mechanical
# rules; composition-dependent fixes (e.g. dropping a non-dominant cation, or the
# acid-salt 'Arsenate + Hydroxide → Hydrogen-Arsenate', or '<Metal> Oxide →
# oxoanion' which needs the formula to tell molybdate from molybdite) are left to
# the reviewer.
OXOANIONS = {'Arsenate', 'Silicate', 'Phosphate', 'Sulfate', 'Vanadate', 'Carbonate', 'Borate',
             'Selenate', 'Tellurate', 'Molybdate', 'Tungstate', 'Niobate', 'Tantalate', 'Chromate',
             'Nitrate', 'Antimonate', 'Germanate', 'Selenite', 'Arsenite', 'Sulfite'}

def _normalize_primary(nm):
    toks = nm.split()
    toks = [t for t in toks if t != 'Aqua']                      # R1: 'Aqua' is redundant (→ Hydrate)
    out, i = [], 0
    while i < len(toks):                                         # R2: 'Hydrogen <oxoanion>' → 'Hydrogen-<oxoanion>'
        if toks[i] == 'Hydrogen' and i + 1 < len(toks) and toks[i + 1] in OXOANIONS:
            out.append('Hydrogen-' + toks[i + 1]); i += 2
        else:
            out.append(toks[i]); i += 1
    toks = out
    # R4-narrow: an oxoanion must precede Hydroxide/Hydrate (NOT relative to
    # halides — accepted names keep e.g. 'Hydroxide Fluoride'/'Hydroxide Chloride').
    tpos = [i for i, t in enumerate(toks) if t in ('Hydroxide', 'Hydrate')]
    if tpos:
        first = tpos[0]
        moved = [t for t in toks[first:] if t in OXOANIONS]
        if moved:
            rest = [t for t in toks[first:] if t not in OXOANIONS]
            toks = toks[:first] + moved + rest
    return ' '.join(toks)

# --- 22. cross-source cell consensus (.cif / Mindat) + Mindat feedback ---------
# Compare unit cells across docx (powder), .cif (single-crystal), and Mindat
# (usually single-crystal) using SORTED axis lengths — angle-free (Mindat stores
# γ=0 for uniaxial cells, so a volume comparison wrongly inflates hexagonal cells
# by 1/sin120°≈1.155) and robust to axis relabeling between powder and SCXRD.
def _cell_lengths(cell):
    def n(x):
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x) or None          # Mindat stores 0 for a missing/uniaxial axis
        return _val(x)                        # docx/.cif strings like '5.196(1)'
    a, b, c = n(cell.get('a')), n(cell.get('b')), n(cell.get('c'))
    if not (a and c):
        return None
    return sorted([a, b or a, c])

def _len_maxdiff(l1, l2):
    return max(abs(x - y) / max(x, y) for x, y in zip(l1, l2))

_CELL_RAT = [2, 3, 4, 3 / 2, 2 / 3]
def _len_rational(l1, l2):
    """A super/sub-cell (polytype) relation — some sorted axis ratio is a simple
    rational, not a transcription error."""
    return any(abs(x / y - q) / q < 0.05 or abs(y / x - q) / q < 0.05
               for x, y in zip(l1, l2) for q in _CELL_RAT)

def check22_cross_sources(e, cif_data, dft_data):
    """docx↔.cif↔Mindat cell consensus. The .cif/Mindat are usually the SCXRD cell,
    which legitimately differs a little from the submitted powder cell — so this
    uses a HIGH tolerance and only speaks on large, non-polytype differences.
    Two outcomes:
      * docx≈.cif but Mindat differs → 'mindat_fix' NOTE, routed to a separate
        mindat_discrepancies log (NOT written to the docx) — a list to verify and
        follow up; EITHER side may be the one to fix (Mindat is sometimes the correct
        one, e.g. a synchrotron-refined cell that deviates from the published cell).
      * the powder cell differs grossly from the SCXRD structure (docx ≠ .cif≈Mindat)
        → 'cell_cif' flag for the reviewer."""
    out = []
    SAME = 0.03
    # A SYNTHETIC phase (e.g. 'Dypingite-syn') is not itself in Mindat; _norm strips
    # '-syn' and matches the NATURAL species. Its CELL legitimately differs (hydration,
    # synthesis), so skip the Mindat CELL comparison — but its IDEAL FORMULA should
    # still match the natural IMA formula (unless a redefinition, flagged in the text),
    # so the chemistry/status cross-checks DO run. The docx↔.cif comparison runs too.
    nm_full = (e.name or '') + ' ' + (e.primary or '')
    is_syn = bool(re.search(r'-\s*syn\b|\bsyn\b|synthetic', nm_full, re.I)) \
        or any('synth' in (c or '').lower() for c, _ in (e.subfiles or []))
    docx = _cell_lengths(e.cell)
    cif = _cell_lengths((cif_data or {}).get('cell', {}))
    M = None if is_syn else mindat_struct(e.name or e.primary or '')
    mind = _cell_lengths({'a': M['a'], 'b': M['b'], 'c': M['c']}) if M else None
    fmt = lambda l: '/'.join('%.3f' % x for x in l)
    if docx and cif and mind and _len_maxdiff(docx, cif) < SAME \
            and _len_maxdiff(docx, mind) >= SAME and not _len_rational(docx, mind):
        out.append(Finding('mindat_fix', 'note',
                   "docx and .cif agree on the cell (a,b,c≈%s) but Mindat lists %s (off %.0f%%) "
                   "— verify which is correct and follow up (either side may be the one to fix)."
                   % (fmt(docx), fmt(mind), _len_maxdiff(docx, mind) * 100), None))
    if docx and cif and _len_maxdiff(docx, cif) > 0.05 and not _len_rational(docx, cif) \
            and (mind is None or _len_maxdiff(cif, mind) < SAME):
        out.append(Finding('cell_cif', 'flag',
                   "Powder cell differs substantially from the .cif single-crystal structure "
                   "(docx a,b,c=%s vs .cif %s, %.0f%%) — verify." % (fmt(docx), fmt(cif), _len_maxdiff(docx, cif) * 100),
                   None, 'cell:a'))
    # axis-swap: same cell magnitudes but the axes are in a DIFFERENT ORDER than the
    # .cif — a likely transcription error (axis permutations shouldn't normally occur
    # for the same phase). Only when the axes are distinct enough for a swap to mean
    # something (skip near-equal axes / uniaxial).
    dp = [_val(e.cell.get(k)) for k in ('a', 'b', 'c')]
    cp = [_val((cif_data.get('cell') or {}).get(k)) for k in ('a', 'b', 'c')]
    if all(dp) and all(cp) and (max(dp) - min(dp)) / max(dp) > 0.05:
        pos = max(abs(x - y) / max(x, y) for x, y in zip(dp, cp))     # positional mismatch
        srt = _len_maxdiff(sorted(dp), sorted(cp))                    # sorted (set) match
        if srt < 0.02 and pos > 0.05:
            out.append(Finding('cell_swap', 'flag',
                       "docx cell axes appear reordered vs the .cif structure (docx a,b,c=%s; "
                       ".cif=%s) — possible transcription swap; verify."
                       % ('/'.join('%.3f' % x for x in dp), '/'.join('%.3f' % x for x in cp)), None, 'cell:a'))
    # chemistry: the docx IDEAL formula vs Mindat's IMA formula (ground truth, from
    # the IMA list — EXACT species only; a variety/Levinson suffix differs from the
    # base). Flag only a MAJOR discrepancy: a SPECIES-DEFINING element in one formula
    # entirely ABSENT from the other (not a substituent, not a trace, order-
    # independent). Mindat lags the CNMNC newsletter, so this cuts both ways → a
    # verify note in the Mindat cross-check log, never written into the docx.
    Mx = mindat_struct(e.name or e.primary or '', exact=True)   # formula check runs for synthetics too
    docx_f = e.formulas.get('Chemical') or e.formulas.get('Structural') or ''
    if Mx and Mx.get('formula') and docx_f:
        d_all, m_all = _all_formula_elements(docx_f), _all_formula_elements(Mx['formula'])
        if d_all and m_all:
            mindat_lacks = _essential_formula_elements(docx_f) - m_all
            docx_lacks = _essential_formula_elements(Mx['formula']) - d_all
            if mindat_lacks or docx_lacks:
                bits = []
                if mindat_lacks:
                    bits.append("docx has %s, Mindat's formula lacks it" % ','.join(sorted(mindat_lacks)))
                if docx_lacks:
                    bits.append("Mindat's formula has %s, docx lacks it" % ','.join(sorted(docx_lacks)))
                out.append(Finding('mindat_chem', 'note',
                           "ideal formula vs Mindat: %s — verify (may be non-essential void/channel "
                           "or substituent content, or a Mindat lag) (docx=%r, Mindat=%r)."
                           % ('; '.join(bits), docx_f[:48],
                              html.unescape(re.sub(r'</?su[bp]>', '', Mx['formula']))[:48]), None))
    # IMA status from the lightweight cache (QUESTIONABLE species are worth a look)
    try:
        from pxrd_review import mindat
        rec = mindat.lookup(e.name or e.primary or '')
        st = (rec or {}).get('ima_status') or []
        st = st if isinstance(st, list) else [st]
        if 'QUESTIONABLE' in st:
            out.append(Finding('ima_status', 'note',
                       "Mindat lists this species' IMA status as QUESTIONABLE — confirm.", None))
    except Exception:
        pass
    return out

def check21_primary_name(e, text):
    nm = (e.primary or '').strip()
    if not nm:
        return []
    suggested = _normalize_primary(nm)
    if suggested and suggested != nm:
        return [Finding('primary_name', 'flag',
                "Primary name %r — suggest %r (remove 'Aqua'; hyphenate Hydrogen-oxoanion; "
                "oxoanions before Hydroxide/Hydrate)." % (nm, suggested), None, 'primary')]
    return []

CHECKS = [check1_geometry, check2_cell_provenance, check3_classification,
          check4_calculated, check5_wavelength, check6_ideal_formula,
          check7_synthetic, check8_precision_symmetry, check9_indexing,
          check10_optical, check11_ima, check12_analysis,
          check13_temperature, check15_strongest_lines,
          check16_instr_vocab, check17_pdf_filter, check18_name_formula,
          check19_intensity_detector, check20_calc_wavelength, check21_primary_name]

def run_all(e, text, cif_data=None, dft_data=None):
    findings = []
    for fn in CHECKS:
        try:
            findings.extend(fn(e, text))
        except Exception as ex:
            findings.append(Finding(fn.__name__, 'note', 'check errored: %s' % ex, None))
    try:
        findings.extend(check_cif(e, cif_data or {}))
    except Exception as ex:
        findings.append(Finding('check_cif', 'note', 'CIF check errored: %s' % ex, None))
    try:
        findings.extend(check_dft(e, dft_data or {}))
    except Exception as ex:
        findings.append(Finding('dft', 'note', '.dft check errored: %s' % ex, None))
    try:
        findings.extend(check22_cross_sources(e, cif_data or {}, dft_data or {}))
    except Exception as ex:
        findings.append(Finding('cell_cif', 'note', 'cross-source check errored: %s' % ex, None))
    return findings

_SEV = {'flag': '⚑', 'info': 'ℹ', 'note': '·'}

def print_findings(path, text):
    e = parse_entry(path)
    fs = run_all(e, text)
    if not fs:
        print('  EXTRA : (no extra-check findings)')
        return
    print('  EXTRA CHECKS:')
    for f in fs:
        print('    %s [%s] %s' % (_SEV.get(f.sev, '?'), f.code, f.msg))
        if f.evidence:
            print('        evidence: …%s…' % _sq(f.evidence))

if __name__ == '__main__':
    import sys, glob, os
    from pxrd_review import cell_lambda_check as C
    folder = sys.argv[1]
    only = sys.argv[2] if len(sys.argv) > 2 else None
    idx = C.pdf_index(folder)
    for dp in sorted(glob.glob(os.path.join(folder, '*.docx'))):
        if os.path.basename(dp).startswith('~$'): continue
        if only and only not in os.path.basename(dp): continue
        eid = C.entry_id(dp); pdf = idx.get(eid)
        print('=' * 78); print(os.path.basename(dp), '<-', os.path.basename(pdf) if pdf else '(no pdf)')
        text = C.pdf_text(pdf) if pdf else None
        print_findings(dp, text)
