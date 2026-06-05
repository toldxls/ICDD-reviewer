#!/usr/bin/env python3
"""Regression check — locks in the false-positive fixes and genuine catches that
were established by hand-auditing one private review batch (see README "Behavioral
contract"). Run after ANY change to the checks; every case must still PASS.

    python3 -m pxrd_review.regression_check "/path/to/fixtures"
    PXRD_REGRESSION_DIR="/path/to/fixtures" python3 -m pxrd_review.regression_check

The fixtures are a private ICDD review batch (not shipped with this repo);
point the script at your local copy via the argument or $PXRD_REGRESSION_DIR.

Read-only: it runs analyze() and inspects the verdict — it does not write docx.
Exit code 0 = all pass, 1 = a regression.
"""
import sys, os, glob

from pxrd_review import cell_lambda_check as C
from pxrd_review import annotate_review as A
from pxrd_review import extra_checks as X

def _stub_entry(z, formula):   # 'testite' name so _cif_name_ok passes and the Z logic runs
    return type('S', (), {'cell': {'Z': str(z)}, 'formulas': {'Empirical': formula},
                          'name': 'testite', 'comments': {}})()

FOLDER = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('PXRD_REGRESSION_DIR', '')
if not FOLDER:
    sys.exit("Regression fixtures not found. Pass the private review-batch folder as an "
             "argument or set $PXRD_REGRESSION_DIR — it is private ICDD data and is "
             "not included in this repository.")

_idx = C.pdf_index(FOLDER)
_cif = C.cif_index(FOLDER)
_dft = C.dft_index(FOLDER)
_cache = {}
def res_for(eid):
    if eid not in _cache:
        dp = glob.glob(os.path.join(FOLDER, eid + '*.docx'))
        if not dp:
            _cache[eid] = None
        else:
            _cache[eid] = A.analyze(dp[0], _idx.get(eid), _cif.get(eid), _dft.get(eid))
    return _cache[eid]

def extras(eid, code=None, sev=None, substr=None):
    r = res_for(eid)
    out = []
    for f in (r['extra'] if r else []):
        if code and f.code != code: continue
        if sev and f.sev != sev: continue
        if substr and substr.lower() not in (f.msg or '').lower(): continue
        out.append(f)
    return out

def cell_verdict(eid):
    r = res_for(eid); return r['cell'][0] if r else None
def lam_flag(eid):
    r = res_for(eid); return bool(r and r['lam'] and r['lam'][0] == 'flag')
def lam_verdict(eid):
    r = res_for(eid); return (r['lam'][0] if (r and r['lam']) else None)
def params(eid):
    r = res_for(eid); return set((r.get('params') or {})) if r else set()

# (description, predicate) — predicate returns True when behaviour is correct
CASES = [
 # --- calculated-pattern false positives (measured/comparison, not calculated) ---
 ("I003448 not flagged 'calculated'",        lambda: not extras('I003448', 'calculated', 'flag')),
 ("I003563 not 'calculated'",      lambda: not extras('I003563', 'calculated', 'flag')),
 ("I003815 not 'calculated'",          lambda: not extras('I003815', 'calculated', 'flag')),
 # 'dcalc from a Rietveld unit-cell refinement' / measured Iobs/Imeas table = MEASURED pattern
 ("calculated: Rietveld unit-cell dcalc not flagged", lambda: X.check4_calculated(
     type('S', (), {'instr': {}, 'name': 'testite', 'primary': ''}),
     'Calculated from PXRD Rietveld unit cell refinement with a = 9.00, b = 9.01 from the structure.') == []),
 ("calculated: real structure-simulated pattern still flags", lambda: [f for f in X.check4_calculated(
     type('S', (), {'instr': {}, 'name': 'testite', 'primary': ''}),
     'The powder X-ray diffraction pattern was calculated from the single-crystal structure model.') if f.sev == 'flag'] != []),
 # --- radiation ---
 ("O002127 radiation OK (CuK found)",  lambda: not lam_flag('O002127')),
 ("I003815 radiation NOT flagged",     lambda: not lam_flag('I003815')),
 ("I003699 radiation IS flagged (real)",   lambda: lam_flag('I003699')),
 # single anode matching the docx = OK, not 'verify' (powder shares the source via
 # Gandolfi/crystal-rotation on a single-crystal instrument); two anodes stay 'verify'
 ("I003562 lam OK (single MoKα source)",     lambda: lam_verdict('I003562') == 'ok'),
 # a radiation is attached to a collection verb whose SUBJECT sets the mode: 'powder
 # XRD data were collected … using CuKα' is the powder radiation even when a single-
 # crystal instrument/comparison sits nearer the token. docx CuKα matches -> OK.
 ("I003521 lam OK (powder collected with CuKα, matches docx)", lambda: lam_verdict('I003521') == 'ok'),
 ("I003823 lam OK (powder XRD with CuKα despite SC-instrument mention)", lambda: lam_verdict('I003823') == 'ok'),
 # 'Sync' is a valid synchrotron designator (λ is beamline-tunable, matches no tube
 # line) — OK, not 'unrec'/'docx anode not recognised'
 ("I003599 lam OK (Sync synchrotron anode)", lambda: lam_verdict('I003599') == 'ok'),
 ("I003554 lam OK (Sync synchrotron anode)", lambda: lam_verdict('I003554') == 'ok'),
 # a single-crystal radiation can be misclassified into a powder context (tarutinoite: the SC
 # MoKα sits nearer a 'powder diffraction patterns' phrase than 'single crystal data', so
 # _section_mode tags it powder). The powder radiation is ranked by the PAPER's evidence — only
 # CoKα sits in 'Powder XRD … collected … Debye-Scherrer … CoKα' — NOT by the docx anode.
 ("I003636 lam OK (CoKα has the powder-collection binding; MoKα is the SC source)", lambda: lam_verdict('I003636') == 'ok'),
 # the ranking must NOT lean on the docx: a token's powder-collection evidence is what counts
 ("radiation: CoKα powder-collection binding detected", lambda: C.powder_collected_near(
     'Powder X-ray diffraction data were collected using Debye-Scherrer geometry, CoKa', 78)),
 ("radiation: SC mounting sentence has NO powder binding", lambda: not C.powder_collected_near(
     'the crystal was mounted on a glass fibre and examined through a Supernova diffractometer, MoKa', 92)),
 # --- 1. geometry: a 'neutron'/ToF mention in a planned/future-work sentence must NOT
 #     masquerade as the collection method; the real X-ray geometry is still found ---
 ("I003599 no geometry 'neutron' grab (future-work)", lambda: not extras('I003599', 'geometry', substr='neutron')),
 # geometry method is descriptive metadata: when Spacing Instr. is already a valid
 # designator (Diffractometer), don't nag to annotate the specific method (I003510 is
 # Diffractometer and its DC comment already documents the Debye-Scherrer geometry)
 ("I003510 no geometry nag (Spacing Instr. already Diffractometer)", lambda: not extras('I003510', 'geometry')),
 # --- instr_class: a diffractometer named in a POWDER sentence -> 'Other'/blank
 #     Spacing/Intensity Instr. should be 'Diffractometer' (FLAG). Requires the powder
 #     tie-in (a single-crystal-only instrument is not assumed) and skips Calculated. ---
 ("I003414 Spacing Instr. -> Diffractometer flag",  lambda: bool(extras('I003414', 'instr_class', 'flag', 'Spacing Instr.'))),
 ("I003414 Intensity Instr. -> Diffractometer flag", lambda: bool(extras('I003414', 'instr_class', 'flag', 'Intensity Instr.'))),
 ("I003528 instr_class flag (powder on R-AXIS)",    lambda: bool(extras('I003528', 'instr_class', 'flag'))),
 # anaphoric 'the same diffractometer' (a pseudo-Gandolfi crystal-rotation setup on a
 # single-crystal area detector): the model is named only in the SC sentence, but the
 # literal word 'diffractometer' in the powder-COLLECTION sentence still pins Spacing/
 # Intensity Instr. -> Diffractometer, and the crystal-rotation method (= area detector)
 # -> Intensity Type Integrated. The weak 'no named geometry' note must not co-fire.
 ("I003548 Spacing Instr. -> Diffractometer flag (bare 'diffractometer')", lambda: bool(extras('I003548', 'instr_class', 'flag', 'Spacing Instr.'))),
 ("I003548 Intensity Instr. -> Diffractometer flag (bare 'diffractometer')", lambda: bool(extras('I003548', 'instr_class', 'flag', 'Intensity Instr.'))),
 ("I003548 Intensity Type Peak->Integrated (crystal rotation = pseudo-Gandolfi area detector)", lambda: bool(extras('I003548', 'intensity_type', 'flag'))),
 ("I003548 no weak geometry note (superseded by instr_class flag)", lambda: not extras('I003548', 'geometry')),
 # a .pdf line-break hyphenation ('R-\nAxis' -> 'R- Axis', yellowcatite/I003561) must still bind
 # the R-AXIS Rapid as the powder diffractometer (regex tolerates hyphen+whitespace, \b-anchored);
 # docx Other -> Diffractometer flag. \b stops 'polar axis rapid' matching. Unit-level (synthetic).
 ("instr_class: 'R- Axis Rapid' line-break hyphen recognised (Other -> Diffractometer)",
  lambda: bool([f for f in X.check1_geometry(
      type('S', (), {'instr': {'spacing_instr': 'Other', 'intensity_instr': 'Other'}}),
      'Powder X-ray diffraction data were collected on a Rigaku R- Axis Rapid II microdiffractometer.')
      if f.code == 'instr_class'])),
 ("instr_class: '...polar axis rapid...' must NOT match R-AXIS (\\b guard)",
  lambda: not [f for f in X.check1_geometry(
      type('S', (), {'instr': {'spacing_instr': 'Other', 'intensity_instr': 'Other'}}),
      'Powder data were collected with the sample on the polar axis rapidly spinning.')
      if f.code == 'instr_class']),
 ("I003745 no instr_class flag (D8 single-crystal only)", lambda: not extras('I003745', 'instr_class')),
 ("I003807 no instr_class flag (no powder instrument; 'expert' != Empyrean)", lambda: not extras('I003807', 'instr_class')),
 ("I003246 no instr_class flag (already Diffractometer)", lambda: not extras('I003246', 'instr_class')),
 # --- 2. cell provenance: powder-refined cells must NOT be flagged 'from single-crystal' ---
 ("I003562 no cell_provenance (powder-refined)", lambda: not extras('I003562', 'cell_provenance')),
 ("I003599 no cell_provenance (ADP, not cell)",  lambda: not extras('I003599', 'cell_provenance')),
 ("I003750 no cell_provenance (Dcalc boilerplate)", lambda: not extras('I003750', 'cell_provenance')),
 # --- cell SOURCE: docx using the SCXRD cell when a same-phase powder cell exists = FLAG;
 #     an SCXRD-looking cell with no powder cell = soft NOTE; a powder cell = nothing ---
 ("I003632 cell_source FLAG (SC cell + powder cell exists)", lambda: bool(extras('I003632', 'cell_source', 'flag'))),
 # the same-phase powder conflict drives the FLAG even without a definitive SC cue in the
 # matched cell's sentence (spaltiite: docx used the SCXRD cell, PXRD cell 15.821 refined)
 ("I003807 cell_source FLAG (SCXRD used, PXRD cell refined)", lambda: bool(extras('I003807', 'cell_source', 'flag'))),
 ("I003657 cell_source NOTE not flag (Julgoldite)",  lambda: bool(extras('I003657', 'cell_source', 'note')) and not extras('I003657', 'cell_source', 'flag')),
 ("I003510 no cell_source flag (powder cell, not SC)", lambda: not extras('I003510', 'cell_source', 'flag')),
 ("I003566 no cell_source flag (GSAS powder cell)",  lambda: not extras('I003566', 'cell_source', 'flag')),
 ("I003636 no cell_source flag (UnitCell powder cell)", lambda: not extras('I003636', 'cell_source', 'flag')),
 ("I003562 no cell_source (powder cell)",            lambda: not extras('I003562', 'cell_source')),
 # --- instrument/geometry lexicon (classify_context fallback when no bare powder/
 #     single word sits near the cell). Derived from DC fields; mode-determining terms
 #     only. Unit-level (no fixture needed) so the contract is locked regardless of
 #     which private entries happen to exercise it. ---
 ("lexicon: Gandolfi geometry -> powder",   lambda: C._instr_mode('gandolfi-like geometry, recording') == 'powder'),
 ("lexicon: pseudo-Gandolfi motion -> powder", lambda: C._instr_mode('collected with pseudo-gandolfi motion') == 'powder'),
 # 'crystal rotation' is the same pseudo-Gandolfi technique under a different name -> powder
 ("lexicon: crystal-rotation method -> powder (pseudo-Gandolfi synonym)", lambda: C._instr_mode('obtained using the crystal rotation method') == 'powder'),
 ("lexicon: Debye-Scherrer -> powder",      lambda: C._instr_mode('in debye-scherrer geometry') == 'powder'),
 ("lexicon: kappa four-circle -> single",   lambda: C._instr_mode('bruker kappa four-circle goniometer') == 'single'),
 ("lexicon: three-circle goniometer -> single", lambda: C._instr_mode('a three-circle diffractometer') == 'single'),
 # X'Celerator (PANalytical 1D powder detector); the X'-prefix keeps it off 'accelerator'
 ("lexicon: X'Celerator -> powder", lambda: C._instr_mode("equipped with an X'celerator silicon-strip detector") == 'powder'),
 ("lexicon: 'accelerator' is not a powder cue", lambda: C._instr_mode('at the synchrotron accelerator facility') is None),
 # D8 Advance/Discover = dedicated powder Bragg-Brentano; D8 Venture (Photon area detector)
 # is dual-use -> must NOT classify as single from the model name alone
 ("lexicon: D8 Advance=powder, D8 Venture undetermined",
                                            lambda: C._instr_mode('bruker d8 advance') == 'powder' and C._instr_mode('bruker d8 venture diffractometer') is None),
 # dual-use area-detector single-crystal instruments run pseudo-Gandolfi/Gandolfi-like to
 # collect POWDER -> their model names must NOT force 'single'; the geometry/motion word wins
 ("lexicon: pseudo-Gandolfi on XtaLAB/Photon -> powder (dual-use models)",
                                            lambda: C._instr_mode('rigaku xtalab synergy, pseudo-gandolfi motion') == 'powder'
                                                    and C._instr_mode('bruker photon iii detector, gandolfi-like scan') == 'powder'),
 # bare single-crystal MODEL with no geometry word -> undetermined (dual-use), not 'single'
 ("lexicon: bare XtaLAB/Apex model -> undetermined", lambda: C._instr_mode('rigaku xtalab synergy diffractometer') is None and C._instr_mode('bruker apex ii detector') is None),
 # dual-use Rigaku R-AXIS Rapid II -> must NOT classify (guards against re-adding it;
 # it mislabelled a single-crystal cell as powder in I002535)
 ("lexicon: dual-use R-AXIS Rapid -> unknown", lambda: C._instr_mode('rigaku r-axis rapid ii curved imaging plate microdiffractometer') is None),
 # both modes named -> one-sided rule returns None rather than guessing
 ("lexicon: both modes present -> None",    lambda: C._instr_mode('gandolfi motion on a kappa four-circle goniometer') is None),
 # refinement-software / method cues (Rietveld = powder by definition; SHELX/OLEX refine a
 # single-crystal STRUCTURE). Derived+validated against the paired PDFs.
 ("lexicon: Rietveld/GSAS software -> powder", lambda: C._instr_mode('refined by the rietveld method using gsas-ii') == 'powder'),
 ("lexicon: TOPAS/FullProf -> powder",      lambda: C._instr_mode('whole-pattern refinement in topas') == 'powder' and C._instr_mode('fullprof suite') == 'powder'),
 ("lexicon: SHELX/OLEX -> single",          lambda: C._instr_mode('structure refined with shelxl-2018') == 'single' and C._instr_mode('olex2 was used') == 'single'),
 # CrysAlisPro + Bruker APEX software suites = single-crystal workup (the version digit
 # keeps 'apex4' off the dual-use 'Apex II' instrument; 'crysalis' is not in 'chrysalis')
 ("lexicon: CrysAlisPro/APEX4 -> single", lambda: C._instr_mode('data reduced with crysalispro') == 'single' and C._instr_mode('processed in the bruker apex4 suite') == 'single'),
 ("lexicon: APEX software + Gandolfi -> None (pseudo-Gandolfi protected)", lambda: C._instr_mode('apex4 then gandolfi powder extraction') is None),
 ("lexicon: 'chrysalis' is not a cue", lambda: C._instr_mode('emerged from its chrysalis') is None),
 # dual-use software (does BOTH) must NOT classify — both Jana2006 and Jana2020
 ("lexicon: JANA (does both) -> undetermined", lambda: C._instr_mode('refined using jana2006') is None and C._instr_mode('refined using jana2020') is None),
 # canon-substring collision guards: these common phrases/minerals must NOT read as a cue
 ("lexicon: 'unit cell' phrase is not a powder cue", lambda: C._instr_mode('the unit cell parameters were') is None),
 ("lexicon: 'jadeite' mineral is not a powder cue",  lambda: C._instr_mode('jadeite and omphacite inclusions') is None),
 # collision-safe rescues of versioned/suffixed names (snippet the collider can't contain)
 ("lexicon: JADE 2010 -> powder (not jadeite)", lambda: C._instr_mode('processed with MDI Jade 2010') == 'powder' and C._instr_mode('jadeite-bearing eclogite') is None),
 ("lexicon: SIR2011 -> single (not bare 'sir')", lambda: C._instr_mode('solved by direct methods in sir2011') == 'single'),
 # full-corpus (438-pair) re-scan additions: profile/whole-pattern fitting + 1D powder
 # detectors (LynxEye/MYTHEN are NOT dual-use area detectors)
 ("lexicon: whole-pattern/profile fit -> powder", lambda: C._instr_mode('whole-pattern profile fit refinement') == 'powder'),
 ("lexicon: LynxEye 1D detector -> powder",  lambda: C._instr_mode('d8 with a lynxeye detector') == 'powder'),
 # 'xpert' was NOT added: its canon form collides with 'expert' -> must stay undetermined
 ("lexicon: 'expert' is not a powder cue (xpert collision avoided)", lambda: C._instr_mode('in the expert opinion of the authors') is None),
 # --- entry-id pairing: both 5-digit (ICDD Task Group) and 6-digit ids; underscore-
 #     prefixed pdf names; a longer digit run must NOT be bitten into a false id ---
 ("id: 6-digit docx",         lambda: C.entry_id('I003559(Selenolaurite).docx') == 'I003559'),
 ("id: 5-digit docx",         lambda: C.entry_id('I10636(Yarzhemskiite).docx') == 'I10636'),
 ("id: underscore-prefixed 5-digit pdf", lambda: C.entry_id('77539_I11149.pdf') == 'I11149'),
 ("id: 7-digit run is not an id", lambda: C.entry_id('scan_I1234567.tif') is None),
 ("id: lowercase prefix normalised", lambda: C.entry_id('i11397(Grimmite).docx') == 'I11397'),
 ("id: lowercase i in a word is not an id", lambda: C.entry_id('doi10665.pdf') is None),
 # pdf range pairing: a hyphen 'A-B' expands ONLY its adjacent pair, never ids[0]..ids[-1]
 # (filenames carry unrelated comma/underscore ids) — guards the 550-id overshoot bug
 ("pdf range: A-B plus extra id does not overshoot",
   lambda: set(C._id_keys('2226_I001146-I001147_I001695.pdf')) == {'I001146','I001147','I001695'}),
 ("pdf range: comma id plus range",
   lambda: set(C._id_keys('76264_I10126,I10499-I10500.pdf')) == {'I10126','I10499','I10500'}),
 ("pdf range: a true consecutive range still expands",
   lambda: set(C._id_keys('-60814_I000738-I000748.pdf')) == {'I%06d' % n for n in range(738, 749)}),
 # --- cif Z-check: reconcile across formula-unit conventions (docx vs CIF formula differ by
 #     a multiple, so Z differs while the cell CONTENTS match) — was an ~89% FP storm ---
 ("formula atoms keep fractional occupancy", lambda: X._formula_atoms('Pb1.50 O4.50') == {'Pb': 1.5, 'O': 4.5}),
 ("cif Z: MoO3·H2O Z=8 reconciles with Mo2O8 Z=4 (no flag)",
   lambda: not X.check_cif(_stub_entry(8, 'H2 Mo O4'), {'Z': 4, 'formula': 'Mo2 O8', 'mineral_name': 'testite'})),
 ("cif Z: fractional-occupancy CIF reconciles (Pb1.5 anchor, no flag)",
   lambda: not X.check_cif(_stub_entry(24, 'O3 Pb Te'), {'Z': 16, 'formula': 'O4.50 Pb1.50 Te1.50', 'mineral_name': 'testite'})),
 # a CIF lacking the mineral's dominant cation is a mis-filed/garbage CIF -> NOTE, not a
 # misleading 'Z mismatch' flag (e.g. I002904's Cd/Se CIF vs the As/Sc mineral)
 ("cif Z: chemistry-mismatched CIF -> note, not flag",
   lambda: [f.sev for f in X.check_cif(_stub_entry(4, 'As H4 O6 Sc'), {'Z': 8, 'formula': 'Cd H4 O6 Se', 'mineral_name': 'testite'})] == ['note']),
 # _cif_name_ok must normalize accents, else a legitimately-paired CIF is silently skipped
 ("cif name: accents normalized (Ríosecoite ~ riosecoite)", lambda: X._cif_name_ok(
     {'mineral_name': 'riosecoite'}, type('S', (), {'name': 'Ríosecoite', 'primary': ''})) is True),
 ("cif name: genuinely different mineral still rejected", lambda: X._cif_name_ok(
     {'mineral_name': 'zincostottite'}, type('S', (), {'name': 'Anorthoyttrialite-(Y)', 'primary': ''})) is False),
 # --- indexing: overlapped reflections are packed per column (h='10',k='01',l='44' =
 #     (1,0,4)+(0,1,4)); split so a matching sub-line isn't a false 'disagrees' flag ---
 ("indexing: overlapped hkl splits per column",
   lambda: {(1, 0, 4), (0, 1, 4)} <= set(X._candidate_hkls('10', '01', '44'))),
 ("indexing: SIGNED overlapped hkl splits ('-41'/'03'/'10' = (-4,0,1)+(1,3,0))",
   lambda: {(-4, 0, 1), (1, 3, 0)} <= set(X._candidate_hkls('-41', '03', '10'))),
 # --- temperature: a non-ambient docx temp the paper doesn't state = likely transcription
 #     slip (PXRD is normally room T); a paper-confirmed non-ambient value is real ---
 ("temperature: non-ambient docx vs room-T pdf -> slip flag",
   lambda: bool(X.check13_temperature(type('S', (), {'comments': {'Temperature': '273 K', 'DC': ''}})(), 'Temperature (K) 293 collected reflections'))),
 ("temperature: paper-confirmed non-ambient -> no flag",
   lambda: not X.check13_temperature(type('S', (), {'comments': {'Temperature': '100 K', 'DC': ''}})(), 'data collected at 100 K')),
 ("temperature: ambient docx -> no flag",
   lambda: not X.check13_temperature(type('S', (), {'comments': {'Temperature': '293 K', 'DC': ''}})(), 'x')),
 ("indexing: genuine multi-digit index not split",
   lambda: X._candidate_hkls('1', '0', '14') == [(1, 0, 14)]),
 ("indexing: signed index falls through to literal",
   lambda: X._candidate_hkls('-2', '2', '4') == [(-2, 2, 4)]),
 # --- _norm_pdf font/glyph fixes (validated on the second reference set) ---
 ("norm: þ -> + (charge mojibake)",   lambda: C._norm_pdf('Fe3þ and [4þ1]') == 'Fe3+ and [4+1]'),
 ("norm: spaced angstrom A ˚ -> Å",   lambda: 'Å' in C._norm_pdf('a = 5.93 A˚')),
 # Osc2tab/Osc2xrd (Britvin) generate a POWDER pattern from single-crystal frames
 ("lexicon: Osc2tab/Osc2xrd -> powder", lambda: C._instr_mode('pattern produced with osc2tab') == 'powder' and C._instr_mode('using osc2xrd software') == 'powder'),
 ("lexicon: STOE WinXPOW -> powder", lambda: C._instr_mode('refined with stoe winxpow software') == 'powder'),
 # find_radiation: a parenthesised source with kV/mA tube settings is the X-ray SOURCE,
 # not a microprobe standard (recovers I002189's 'rotating anode (CoKα, 40 kV, 15 mA)')
 ("radiation: parenthesised (CoKα, 40 kV) is found",
   lambda: any(a == 'co' for a, *_ in C.find_radiation('rotating anode (CoKα, 40 kV, 15 mA), imaging plate'))),
 ("radiation: microprobe standard (FeKα) still skipped",
   lambda: not any(a == 'fe' for a, *_ in C.find_radiation('analysed against albite, diopside (FeKα) and apatite standards'))),
 ("norm: thin/nbsp spaces -> normal", lambda: C._norm_pdf('Cu\u2009K\u00a0radiation') == 'Cu K radiation'),
 # a 'calculated [X-ray] powder' pattern is simulated from the single-crystal structure,
 # so it must NOT make a single-crystal cell read 'powder' (I003398: synchrotron crystallite
 # refinement whose only nearby 'powder' is 'Calculated X-ray powder diffraction data')
 ("calc-powder phrase is NOT powder context",
   lambda: (lambda s: C.classify_context(s, s.find('a =')))('refinement gave a = 3.09(1). calculated X-ray powder diffraction data are listed in Table S1.') != 'powder'),
 ("real 'refined from powder data' IS powder context",
   lambda: (lambda s: C.classify_context(s, s.find('a =')))('the unit-cell parameters refined from powder data are a = 5.24(1) and so on.') == 'powder'),
 # preceding powder-software cue (JADE Pro) outranks a bare 'single-crystal' that opens the
 # NEXT sentence — the I002373 case (figure caption pushed the bare 'powder' out of range)
 ("classify_context: before powder-software cue beats after 'single-crystal'",
   lambda: (lambda s: C.classify_context(s, s.find('a =')))('observed d values by profile fitting using jade pro software. refined unit-cell parameters are a = 5.04 b = 6.0. single-crystal diffraction data were collected at the synchrotron') == 'powder'),
 # a Le Bail / Rietveld / Pawley refined cell is powder even when 'single-crystal' is the
 # NEARER word (it's the starting-point/comparison reference) — the I002960 case
 ("classify_context: Le Bail refinement beats a nearer 'single-crystal' starting ref",
   lambda: (lambda s: C.classify_context(s, s.find('a =')))('powder x-ray diffraction data were collected. unit-cell parameters refined using the le bail profile-fitting method starting from parameters determined from single-crystal techniques are a = 9.20 and b = 12.4') == 'powder'),
 # a 'calculated PXRD' pattern (e.g. exported by a visualizer like Mercury/PLATON) is NOT a
 # powder experiment — same as 'calculated powder' (I003398), now also covering the 'pxrd' word
 ("calc-PXRD (Mercury export) is NOT powder context",
   lambda: (lambda s: C.classify_context(s, s.find('a =')))('refined structure a = 7.21(2). A calculated PXRD pattern was generated in Mercury.') != 'powder'),
 # 'simulated' patterns (CrystalDiffract/Mercury) are calculated too, not measured powder
 ("simulated PXRD (CrystalDiffract) is NOT powder context",
   lambda: (lambda s: C.classify_context(s, s.find('a =')))('single-crystal structure a = 7.21(2). A simulated powder pattern from CrystalDiffract.') != 'powder'),
 # but 'calcined powder' is a REAL powder sample — must NOT be swallowed by the calc guard
 ("'calcined powder' IS powder context",
   lambda: (lambda s: C.classify_context(s, s.find('a =')))('cell refined from calcined powder data: a = 5.24(1) and so on.') == 'powder'),
 # pure visualizers are NOT mode cues (VESTA/Diamond/CrystalMaker/Mercury)
 ("lexicon: visualizers are not mode cues", lambda: C._instr_mode('structure drawn in vesta and mercury') is None),
 # --- SG <-> crystal-system consistency (docx-internal, blind-spot check #1) ---
 ("sg_system: classifier maps HM symbols", lambda: all(X._sg_system(s) == exp for s, exp in
     [('Pbca','o'), ('P21/c','m'), ('P121/c1','m'), ('Fd-3m','c'), ('P213','c'), ('F432','c'),
      ('P63/mmc','h'), ('P-3m1','h'), ('R-3m','r'), ('I4/mmm','t'), ('P-1','a'), ('P212121','o')])),
 ("sg_system: mismatch flags (monoclinic system, ortho SG)", lambda: [f for f in X.check23_sg_system(
     type('S', (), {'crystal_system': 'm', 'space_group': 'Pbca', 'cell': {}})) if f.sev=='flag'] != []),
 ("sg_system: agreement no flag (ortho system, ortho SG)", lambda: X.check23_sg_system(
     type('S', (), {'crystal_system': 'o', 'space_group': 'Pbca', 'cell': {}})) == []),
 ("sg_system: rhombohedral system + hex-setting SG compatible", lambda: X.check23_sg_system(
     type('S', (), {'crystal_system': 'h', 'space_group': 'R3m', 'cell': {}})) == []),
 ("sg_system: corpus clean (no SG/system disagreement)", lambda: not extras('I003510', 'sg_system')
     and not extras('I003807', 'sg_system') and not extras('I003632', 'sg_system')),
 # --- optical 2V / sign vs refractive indices (docx-internal, blind-spot check #3) ---
 # I002959 (sulfatoredmondite): β=1.850 sits next to γ=1.860 (far from α=1.780) -> optically
 # NEGATIVE, and 2Vcalc≈40 matches the docx 2V=40, but the docx says Sign=+ (real sign error)
 ("optical_2v: sign contradicting the indices flags", lambda: [f for f in X.check24_optical_2v(
     type('S', (), {'comments': {'Optical Data': 'A=1.780(5), B=1.850(calc), Q=1.860(calc), Sign=+, 2V=40(3)'}}))
     if f.sev=='flag'] != []),
 ("optical_2v: gross 2V gap flags", lambda: [f for f in X.check24_optical_2v(
     type('S', (), {'comments': {'Optical Data': 'A=1.540, B=1.545, Q=1.600, Sign=+, 2V=80'}})) if f.sev=='flag'] != []),
 ("optical_2v: near-uniaxial (β≈γ) stays silent", lambda: X.check24_optical_2v(
     type('S', (), {'comments': {'Optical Data': 'A=1.795, B=1.820, Q=1.820, Sign=+, 2V=80'}})) == []),
 ("optical_2v: consistent sign+2V no flag", lambda: X.check24_optical_2v(
     type('S', (), {'comments': {'Optical Data': 'A=1.540, B=1.545, Q=1.600, Sign=+, 2V=35'}})) == []),
 # --- reflection geometry vs wavelength (docx-internal, blind-spot check #2) ---
 # I002983: d=0.70 Å is impossible under CuKα (λ/2=0.7703); I003406: d=0.7719 -> 2θ≈173° (a
 # synchrotron λ=0.708 mislabelled as CuKα). A normal d-range stays quiet.
 ("reflection_geom: d < λ/2 is impossible -> flag", lambda: [f for f in X.check25_reflection_geometry(
     type('S', (), {'instr': {'lam': '1.54056', 'anode': 'CuKa1'},
                    'refl': [('0.7000','11','4','1','11'), ('2.5','100','1','1','1')]})) if f.sev=='flag'] != []),
 ("reflection_geom: implausibly high 2θ -> flag", lambda: [f for f in X.check25_reflection_geometry(
     type('S', (), {'instr': {'lam': '1.54056', 'anode': 'CuKa1'},
                    'refl': [('0.7719','14','','',''), ('3.0','100','1','1','1')]})) if f.sev=='flag'] != []),
 ("reflection_geom: ordinary d-range stays quiet", lambda: X.check25_reflection_geometry(
     type('S', (), {'instr': {'lam': '1.54056', 'anode': 'CuKa1'},
                    'refl': [('1.5','100','1','1','1'), ('3.0','50','2','2','2')]})) == []),
 ("reflection_geom: no wavelength -> no flag", lambda: X.check25_reflection_geometry(
     type('S', (), {'instr': {}, 'refl': [('0.7','11','1','1','1')]})) == []),
 # a CALCULATED pattern is exempt — presentation λ (CuKα) + geometric d's + high 2θ are all fine
 ("reflection_geom: calculated pattern exempt", lambda: X.check25_reflection_geometry(
     type('S', (), {'instr': {'lam': '1.54056', 'anode': 'CuKa1', 'spacing_instr': 'Calculated'},
                    'refl': [('0.7000','11','4','1','11'), ('2.5','100','1','1','1')]})) == []),
 # --- document-structure (section) tier: the cell belongs to its subsection's experiment ---
 ("section: powder subsection -> powder", lambda: (lambda s: C._section_mode(s, s.find('a =')))(
     'x-ray powder diffraction data were collected (table 2). the refined unit cell is a = 5.0 and b = 6.0') == 'powder'),
 ("section: single-crystal subsection -> single", lambda: (lambda s: C._section_mode(s, s.find('a =')))(
     'single-crystal x-ray diffraction was carried out. the cell is a = 5.0') == 'single'),
 ("section: umbrella heading abstains (None)", lambda: (lambda s: C._section_mode(s, s.find('a =')))(
     'crystal structure determination was performed. the cell is a = 5.0') is None),
 ("section: incidental 'single-crystal X' doesn't beat a powder subsection", lambda: (lambda s: C._section_mode(s, s.find('a =')))(
     'single-crystal fragments were unavailable. x-ray powder diffraction gave a = 5.0') == 'powder'),
 ("section tier wired into classify_context", lambda: (lambda s: C.classify_context(s, s.find('a =')))(
     'single-crystal fragments were unavailable. x-ray powder diffraction gave a = 5.0') == 'powder'),
 # --- cell parsing (cubic / uniaxial / rounded-table) ---
 ("I003634 cubic cell matches",         lambda: cell_verdict('I003634') == 'match'),
 ("I003751 uniaxial: only c flagged",        lambda: params('I003751') == {'c'}),
 # Z (formula units): a/b/c match but the .pdf explicitly states a different 'Z = N'
 # (grokhovskyite: docx Z=2, paper 'Z = 3'); a docx-Z == paper-Z entry must NOT flag
 ("I003744 Z mismatch flagged (docx 2 vs .pdf Z=3)", lambda: 'Z' in params('I003744')),
 ("I003634 no Z flag (docx Z matches .pdf)",        lambda: 'Z' not in params('I003634')),
 ("I003747 clean (no rounding noise)",  lambda: not params('I003747')),
 ("I003698 clean (full-precision cell)", lambda: not params('I003698')),
 ("I003562 indexing flagged (>3%)",     lambda: bool(extras('I003562', 'indexing', 'flag'))),
 # weak reflections (I≤35) only flag at >5%: the I=16 line 4.1440 [3.2%] is dropped,
 # the strong I=80 line 5.0790 [3.1%] is kept
 ("I003562 indexing keeps strong 5.0790",  lambda: bool(extras('I003562', 'indexing', substr='5.0790'))),
 ("I003562 indexing drops weak 4.1440",     lambda: not extras('I003562', 'indexing', substr='4.1440')),
 # --- optical sign (control-char glyphs must NOT be guessed) ---
 ("I003528 no optical-sign flag",       lambda: not extras('I003528', 'optical')),
 ("I003633 no optical-sign flag",       lambda: not extras('I003633', 'optical')),
 # multi-mineral comparison table (several distinct signs) -> can't attribute -> no flag
 ("optical: multi-mineral table doesn't flag", lambda: X.check10_optical(
     type('S', (), {'comments': {'Optical Data': 'Sign=-'}}),
     'Optical class biaxial (+) biaxial (+) biaxial (-) biaxial (+) biaxial (-) biaxial (-)') == []),
 ("optical: single consistent sign still flags", lambda: X.check10_optical(
     type('S', (), {'comments': {'Optical Data': 'Sign=+'}}),
     'the mineral is optically biaxial (-), 2V = 50') != []),
 # strongest line: use the entry's prose list, not a wrong column of a comparison table
 ("strongest_lines: prose I=100 beats comparison-table column", lambda: X.check15_strongest_lines(
     type('S', (), {'refl': [('2.583', '100', '2', '0', '0'), ('3.20', '20', '1', '1', '0')]}),
     'table dmeas(I) 3.20(20) 3.174(100) 3.00(34). The strongest lines in the powder '
     'diffraction pattern are (d A, I %, hkl): 4.49, 31, (110); 2.583, 100, (200).') == []),
 ("strongest_lines: genuinely missing I=100 line still flags", lambda: X.check15_strongest_lines(
     type('S', (), {'refl': [('3.20', '20', '1', '1', '0')]}),
     'The strongest lines (d A, I %, hkl): 4.49, 31, (110); 2.583, 100, (200).') != []),
 # --- IMA number (new mineral vs reinvestigation/reference) ---
 ("I003633 IMA flag (new mineral)",     lambda: bool(extras('I003633', 'ima'))),
 ("I003688 IMA flag (new mineral)",    lambda: bool(extras('I003688', 'ima'))),
 ("I003687 NO IMA flag (reinvest.)",     lambda: not extras('I003687', 'ima')),
 ("I003511 NO IMA flag (reinvest.)",    lambda: not extras('I003511', 'ima')),
 # --- classification (docx already names the group) ---
 ("I003657 no classification comment",    lambda: not extras('I003657', 'classification', 'info')),
 # --- 3. structure relation: don't restate a docx Structure comment; DO check when the
 #     .pdf asserts a relation and the docx has none ---
 ("I003416 no Structure-comment noise (docx already has it)", lambda: not extras('I003416', 'classification', substr='structure')),
 # fluormacraeite is already classified in the Paulkerrite Group, so 'isostructural with
 # paulkerrite' is redundant (group membership implies it) -> suppress the note
 ("I003246 isostructural-with-own-group note suppressed", lambda: not extras('I003246', 'classification', substr='no Structure')),
 # but an OUT-of-group structural relation must still be surfaced
 ("structure-relation: out-of-group isostructural still noted", lambda: [f for f in X.check3_classification(
     type('S', (), {'comments': {}, 'raw_rows': [['IMA Classifications: Some Group Otherite']], 'name': 'zzznotarealmineral', 'primary': ''}),
     'the new phase is isostructural with stranskiite and shares its topology.') if 'no Structure' in f.msg] != []),
 ("structure-relation: isostructural-with-own-group-namesake suppressed", lambda: [f for f in X.check3_classification(
     type('S', (), {'comments': {}, 'raw_rows': [['IMA Classifications: Paulkerrite Group Paulkerrite']], 'name': 'zzznotarealmineral', 'primary': ''}),
     'the new phase is isostructural with paulkerrite, the group prototype.') if 'no Structure' in f.msg] == []),
 # a mineral can't be 'related to itself' (paper names THIS species as the anchor for others)
 ("structure-relation: self-reference suppressed", lambda: [f for f in X.check3_classification(
     type('S', (), {'comments': {}, 'raw_rows': [], 'name': 'Keutschite', 'primary': 'Keut'}),
     'minerals chemically or structurally related to keutschite, including agmantinite and stannite.') if 'no Structure' in f.msg] == []),
 # --- precision check names the esd to add ---
 ("I003566 names esd to add",      lambda: bool(extras('I003566', 'precision', substr='.pdf gives'))),
 # --- analysis field ---
 ("I003510 misplaced-analysis flag",  lambda: bool(extras('I003510', 'analysis', substr='moved'))),
 # --- density check is deregistered (never fires) ---
 ("No density flags anywhere",               lambda: not any(extras(e, 'density')
                                                   for e in ('I003704','I003448','I003562'))),
 # --- 16. instrumentation designators (corpus-curated) ---
 ("I003246 no geometry nag (Spacing Instr. already Diffractometer)", lambda: not extras('I003246', 'geometry')),
 ("I003747 no instr_vocab flag (clean)",     lambda: not extras('I003747', 'instr_vocab', 'flag')),
 ("I003698 no instr_vocab flag (clean)",     lambda: not extras('I003698', 'instr_vocab', 'flag')),
 # --- 16b. measured-data completeness (blank anode/intensity-type) ---
 ("I003600 blank anode -> derive Sync (synch λ)", lambda: bool(extras('I003600', 'instr_vocab', substr='set the anode to Sync'))),
 ("I003246 no blank-field flag",             lambda: not extras('I003246', 'instr_vocab', substr='blank')),
 # --- 17. PDF monochromator/β-filter -> fill blank Filter (powder-context only) ---
 ("I003747 .pdf graphite mono (powder)",      lambda: bool(extras('I003747', 'instr_filter', substr='graphite'))),
 ("I003745 SC mono NOT attributed",          lambda: not extras('I003745', 'instr_filter')),
 ("I003566 SC mono NOT attributed",          lambda: not extras('I003566', 'instr_filter')),
 # --- 19. Intensity Type follows the detector (area→Integrated, BB→Peak) ---
 ("I003657 Bragg-Brentano -> Peak flag",     lambda: bool(extras('I003657', 'intensity_type'))),
 ("I003563 Gandolfi/area -> Integrated flag", lambda: bool(extras('I003563', 'intensity_type'))),
 ("I003822 calc pattern -> no intensity_type", lambda: not extras('I003822', 'intensity_type')),
 # --- 7. synthetic: the 'Synthetic Rock-forming minerals' subfile is a CATEGORY (a
 #     natural mineral is also filed there) — not a 'this sample is synthetic' flag ---
 ("I003512 no synthetic note (Synthetic Rock-forming category, not a synthetic sample)",
                                              lambda: not extras('I003512', 'synthetic')),
 # --- 20. calculated pattern, λ not stated in the paper ---
 # only a NON-standard calc wavelength is worth flagging; I003511 is calculated at the
 # default CuKα (1.54056), legitimately absent from a paper using another source -> no flag
 ("I003511 no calc_wavelength flag (standard CuKα calc default)", lambda: not extras('I003511', 'calc_wavelength')),
 ("calc_wavelength: non-standard λ still flags",
   lambda: bool(X.check20_calc_wavelength(type('S', (), {'instr': {'spacing_instr': 'Calculated', 'lam': '2.28970', 'anode': 'CrKa'}})(),
                'the powder pattern was calculated from the single-crystal structure'))),
 # --- 21. Primary name normalization: corrected names must NOT flag ---
 ("I003523 primary name OK (no FP)",         lambda: not extras('I003523', 'primary_name')),
 # --- 22. cross-source: synthetic skips Mindat (natural≠synthetic); agreeing entry clean ---
 ("I003599 synthetic -> Mindat cell skipped",  lambda: not extras('I003599', 'mindat_fix')),
 ("I003246 no cross-source flag (agrees)",   lambda: not extras('I003246', 'cell_cif') and not extras('I003246', 'mindat_fix')),
 # --- .dft (DataQuacker) soft cross-check: console/log only, never written ---
 ("I003599 .dft Z verify note",              lambda: bool(extras('I003599', 'dft', substr='Z:'))),
 ("I003599 .dft notes are sev=note (not flag)", lambda: not [f for f in (res_for('I003599')['extra'] if res_for('I003599') else []) if f.code == 'dft' and f.sev == 'flag']),
 ("I003246 no .dft note (agrees)",           lambda: not extras('I003246', 'dft')),
 # --- 18. name vs ideal formula: correctly-named REE species must NOT flag ---
 ("I003511 Allanite-(Y) name OK",            lambda: not extras('I003511', 'name_formula', 'flag')),
 ("I003523 Parisite-(Nd) name OK",           lambda: not extras('I003523', 'name_formula', 'flag')),
 ("I003521 Marsaalamite-(Y) name OK",        lambda: not extras('I003521', 'name_formula', 'flag')),
]

def main():
    if not glob.glob(os.path.join(FOLDER, 'I*.docx')):
        print("!! batch not found at %r — pass the path as an argument" % FOLDER)
        return 2
    fails = 0
    for desc, pred in CASES:
        try:
            ok = bool(pred())
        except Exception as e:
            ok = False; desc += "  (threw: %s)" % e
        print("%s  %s" % ("PASS" if ok else "FAIL", desc))
        fails += not ok
    # policy: no entry in this batch should withhold auto-Accept (none are 'severe')
    severe = [C.entry_id(d) for d in sorted(glob.glob(os.path.join(FOLDER, '*.docx')))
              if '~$' not in d and A._is_severe(A.analyze(d, _idx.get(C.entry_id(d)), _cif.get(C.entry_id(d))))]
    ok = not severe
    print("%s  No entry withheld from auto-Accept (severe=%s)" % ("PASS" if ok else "FAIL", severe))
    fails += not ok
    print("\n%d case(s) FAILED" % fails if fails else "\nAll regression cases pass.")
    return 1 if fails else 0

if __name__ == '__main__':
    sys.exit(main())
