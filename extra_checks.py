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
"""
import re, zipfile, math
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
    instr = {}                    # anode, lam, standard, spacing_instr, intensity_instr, intensity_type, camera
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
def check1_geometry(e, text):
    out = []
    spac = (e.instr.get('spacing_instr') or '').strip()
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
                if kw in low and kw.replace('–', '-') not in [f.replace('–', '-') for f in found]:
                    found.append(kw)
    if found:
        # the docx 'Spacing Instr.' is generic (Diffractometer/Film/Other); the
        # reviewer routinely annotates the SPECIFIC named geometry from the paper.
        out.append(Finding('geometry', 'info',
                   "PDF names a specific geometry/method: %s (docx Spacing Instr. = %r) "
                   "— consider annotating 'Powder data — %s'."
                   % (', '.join(found), spac or '(blank)', found[0]),
                   None))
    elif spac in ('', 'Other'):
        out.append(Finding('geometry', 'note',
                   "Spacing Instr. = %r and no named geometry found in PDF — set the method."
                   % (spac or '(blank)'), None))
    return out

# ----------------------------------------------------------------------------- 2. cell not refined from powder
PROV_KW = ['single-crystal', 'single crystal', 'scxrd', 'saed', 'selected-area',
           'electron diffraction', 'hrtem', 'fft', 'ebsd', 'precession electron']
def check2_cell_provenance(e, text):
    out = []
    spac = (e.instr.get('spacing_instr') or '').strip().lower()
    # docx signal: the cell/data is explicitly Calculated (overlaps with #4 but
    # for the CELL provenance specifically).
    if not text:
        return out
    # Strong, specific phrasings only — a paper merely HAVING a single-crystal
    # section is not evidence the entry's cell came from it (that fired on 27/44).
    # We want statements that the powder cell was NOT refined, or was taken from
    # single-crystal/electron data.
    STRONG = ['were not refined', 'was not refined', 'not refined from',
              'cell parameters from single', 'from single-crystal data', 'from the single-crystal',
              'cell from scxrd', 'cell from saed', 'from the saed', 'refined from single',
              'taken from the single-crystal', 'derived from single-crystal']
    low = text.lower()
    hits = [p for p in STRONG if p in low]
    if hits:
        sent = _find_sentences(text, any_of=hits)
        out.append(Finding('cell_provenance', 'info',
                   "PDF indicates the cell was not powder-refined / came from single-crystal "
                   "or electron data — confirm provenance.",
                   (sent[0] if sent else hits[0])[:160]))
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
    # the author often already filled Structure/Isomorphism/Polymorphism — surface it
    for code in ('Structure', 'Isomorphism', 'Polymorphism'):
        v = e.comments.get(code)
        if v:
            out.append(Finding('classification', 'info',
                       "docx %s comment present: %s" % (code, v[:120]), None))

    # AUTHORITATIVE: Mindat group membership (a mineral's groupid → group name).
    # Replaces guessing from prose. Cross-checks the docx Strunz-mindat field.
    mindat_found = False
    try:
        import mindat
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

    # PDF corroboration. Structural-RELATION statements ('isostructural with X')
    # are a comparison Mindat's groupid does NOT encode, so always surface them.
    if text:
        flat = re.sub(r'\s+', ' ', text)
        seen = set()
        for m in re.finditer(r'\b(isostructural|isotypic|homeotypic|isomorphous) with ([A-Z][a-z]{3,})', flat):
            frag = m.group(0)
            if frag.lower() in seen: continue
            seen.add(frag.lower())
            out.append(Finding('classification', 'note', "PDF structural relation: '%s'." % frag, None))
            if len(seen) >= 3: break
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
                           "PDF names a '%s' (Mindat has no group for this species — verify)." % frag, None))
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
        if sents and not (spac == 'calculated'):
            out.append(Finding('calculated', 'flag',
                       "PDF states the powder pattern was calculated from the structure.",
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
        out.append(Finding('wavelength', 'info', "PDF: Kα2 stripped in software.", None))
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
    sub_syn = any('synth' in c for c in cls)
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
                msg = ("%s=%s has no stated error (esd) — PDF gives %s=%s(%s); "
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
        dv = _val(d); hi, ki, li = _int(h), _int(k), _int(l)
        if dv is None or None in (hi, ki, li) or (hi == ki == li == 0):
            continue
        n_checked += 1
        ds2 = _dstar2(a, b, c, al, be, ga, hi, ki, li)
        if ds2 <= 0: continue
        d_calc = 1 / math.sqrt(ds2)
        rel = abs(d_calc - dv) / dv
        if rel > 0.03:                       # >3% off — significant d-spacing discrepancy
            bad.append((d, '%d%d%d' % (hi, ki, li), round(d_calc, 4), round(rel*100, 1)))
    if bad:
        worst = sorted(bad, key=lambda x: -x[3])[:5]
        msg = ("%d of %d indexed reflections disagree with the stated cell by >3%% "
               "(d_obs vs d_calc): %s" % (len(bad), n_checked,
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
                   "Optical sign mismatch: docx Sign=%s but PDF indicates Sign=%s"
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
    is_new = False
    for cue in (r'new mineral', r'approved by the ima', r'approved by the commission on new min'):
        for m in re.finditer(cue, low):
            seg = low[max(0, m.start() - 60): m.end() + 60]
            if name_root not in seg:
                continue
            # skip REFERENCE citations (a different 'new mineral' cited in the
            # bibliography): author-year '(YYYY)', newsletter, 'et al.', DOI, pages
            wide = low[max(0, m.start() - 120): m.end() + 60]
            if re.search(r'\(\d{4}\)|newsletter|et al|doi|\bpp\.|\d+\s*[-–]\s*\d+\.', wide):
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
    msg = ("PDF describes this as a new mineral but the docx IMA Number field is blank — add it"
           + (" (IMA %s)" % num if num else ""))
    out.append(Finding('ima', 'flag', msg + ".", None, 'ima'))
    return out

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
        out.append(Finding('cif', 'flag',
                   "Z mismatch: docx Z=%d but CIF Z=%d" % (docx_z, cif_z),
                   None, 'name'))
    # Space group: CIF comparison is unreliable for polytypic minerals and
    # entries where the CIF represents a different structural variant.
    # The correct reference is the PDF for the specific phase described.
    # SG check is therefore omitted here pending PDF-based SG extraction.
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
                       "the Analysis field." % field, None, 'formula'))
        elif text and re.search(
                r'microprobe\s+anal|electron\s+(?:micro)?probe\s+anal|'
                r'EPMA\s+(?:anal|data|result)|EMP\s+anal|'
                r'wt\.?\s*%[^.]{0,60}:\s*[A-Z][a-z]',
                text, re.I):
            # PDF clearly reports an analysis that never made it into the docx
            out.append(Finding('analysis', 'flag',
                       "PDF describes a chemical/microprobe analysis but the docx "
                       "Analysis field is empty — it may have been omitted.",
                       None, 'formula'))
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
                           "composition appears to be missing.", None, 'formula'))
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
                   "Analysis count missing — PDF gives n=%d" % n_pdf, None, 'formula'))
    elif n_pdf and n_docx and n_pdf != n_docx:
        out.append(Finding('analysis', 'flag',
                   "Analysis count mismatch: docx=%d, PDF=%d" % (n_docx, n_pdf),
                   None, 'formula'))

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
                           "Analysis: %s is calculated per PDF but not marked (calc) "
                           "in docx" % elem, None, 'formula'))

    # --- 3. wt.% total sanity ---
    # Prefer an explicit "Total XX.XX" stated in the analysis over summing values,
    # since summing is fragile (formula leakage, –O=F corrections, etc.)
    total_m = re.search(r'[Tt]otal\s+(\d{2,3}\.?\d*)', analysis_data)
    if total_m:
        total = float(total_m.group(1))
        if total < 94:
            out.append(Finding('analysis', 'flag',
                       "Analysis explicit total = %.1f%% (below 94%% — possible "
                       "missing oxide or transcription error)" % total, None, 'formula'))
        elif total > 103:
            out.append(Finding('analysis', 'flag',
                       "Analysis explicit total = %.1f%% (above 103%% — possible "
                       "transcription error)" % total, None, 'formula'))
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
        msg = ("Density mismatch: docx Dx=%.3f g/cm³ but PDF states %.3f "
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
                    "docx uses %s basis, PDF uses %s basis"
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
                   "PDF strongest line (I=100, d=%.4f Å) not found in docx "
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
CHECKS = [check1_geometry, check2_cell_provenance, check3_classification,
          check4_calculated, check5_wavelength, check6_ideal_formula,
          check7_synthetic, check8_precision_symmetry, check9_indexing,
          check10_optical, check11_ima, check12_analysis,
          check13_temperature, check15_strongest_lines]

def run_all(e, text, cif_data=None):
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
    import cell_lambda_check as C
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
