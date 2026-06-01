#!/usr/bin/env python3
"""Regression check — locks in the false-positive fixes and genuine catches that
were established by hand-auditing one private review batch (see README "Behavioral
contract"). Run after ANY change to the checks; every case must still PASS.

    python3 regression_check.py "/path/to/fixtures"
    PXRD_REGRESSION_DIR="/path/to/fixtures" python3 regression_check.py

The fixtures are a private ICDD review batch (not shipped with this repo);
point the script at your local copy via the argument or $PXRD_REGRESSION_DIR.

Read-only: it runs analyze() and inspects the verdict — it does not write docx.
Exit code 0 = all pass, 1 = a regression.
"""
import sys, os, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cell_lambda_check as C
import annotate_review as A

FOLDER = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('PXRD_REGRESSION_DIR', '')
if not FOLDER:
    sys.exit("Regression fixtures not found. Pass the private review-batch folder as an "
             "argument or set $PXRD_REGRESSION_DIR — it is private ICDD data and is "
             "not included in this repository.")

_idx = C.pdf_index(FOLDER)
_cif = C.cif_index(FOLDER)
_cache = {}
def res_for(eid):
    if eid not in _cache:
        dp = glob.glob(os.path.join(FOLDER, eid + '*.docx'))
        if not dp:
            _cache[eid] = None
        else:
            _cache[eid] = A.analyze(dp[0], _idx.get(eid), _cif.get(eid))
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
def params(eid):
    r = res_for(eid); return set((r.get('params') or {})) if r else set()

# (description, predicate) — predicate returns True when behaviour is correct
CASES = [
 # --- calculated-pattern false positives (measured/comparison, not calculated) ---
 ("I003448 not flagged 'calculated'",        lambda: not extras('I003448', 'calculated', 'flag')),
 ("I003563 not 'calculated'",      lambda: not extras('I003563', 'calculated', 'flag')),
 ("I003815 not 'calculated'",          lambda: not extras('I003815', 'calculated', 'flag')),
 # --- radiation ---
 ("O002127 radiation OK (CuK found)",  lambda: not lam_flag('O002127')),
 ("I003815 radiation NOT flagged",     lambda: not lam_flag('I003815')),
 ("I003699 radiation IS flagged (real)",   lambda: lam_flag('I003699')),
 # --- cell parsing (cubic / uniaxial / rounded-table) ---
 ("I003634 cubic cell matches",         lambda: cell_verdict('I003634') == 'match'),
 ("I003751 uniaxial: only c flagged",        lambda: params('I003751') == {'c'}),
 ("I003747 clean (no rounding noise)",  lambda: not params('I003747')),
 ("I003698 clean (full-precision cell)", lambda: not params('I003698')),
 ("I003562 indexing flagged (>3%)",     lambda: bool(extras('I003562', 'indexing', 'flag'))),
 # --- optical sign (control-char glyphs must NOT be guessed) ---
 ("I003528 no optical-sign flag",       lambda: not extras('I003528', 'optical')),
 ("I003633 no optical-sign flag",       lambda: not extras('I003633', 'optical')),
 # --- IMA number (new mineral vs reinvestigation/reference) ---
 ("I003633 IMA flag (new mineral)",     lambda: bool(extras('I003633', 'ima'))),
 ("I003688 IMA flag (new mineral)",    lambda: bool(extras('I003688', 'ima'))),
 ("I003687 NO IMA flag (reinvest.)",     lambda: not extras('I003687', 'ima')),
 ("I003511 NO IMA flag (reinvest.)",    lambda: not extras('I003511', 'ima')),
 # --- classification (docx already names the group) ---
 ("I003657 no classification comment",    lambda: not extras('I003657', 'classification', 'info')),
 # --- precision check names the esd to add ---
 ("I003566 names esd to add",      lambda: bool(extras('I003566', 'precision', substr='PDF gives'))),
 # --- analysis field ---
 ("I003510 misplaced-analysis flag",  lambda: bool(extras('I003510', 'analysis', substr='moved'))),
 # --- density check is deregistered (never fires) ---
 ("No density flags anywhere",               lambda: not any(extras(e, 'density')
                                                   for e in ('I003704','I003448','I003562'))),
 # --- 16. instrumentation designators (corpus-curated) ---
 ("I003246 instrument recognised (R-AXIS)",  lambda: bool(extras('I003246', 'geometry', substr='R-AXIS'))),
 ("I003747 no instr_vocab flag (clean)",     lambda: not extras('I003747', 'instr_vocab', 'flag')),
 ("I003698 no instr_vocab flag (clean)",     lambda: not extras('I003698', 'instr_vocab', 'flag')),
 # --- 16b. measured-data completeness (blank anode/intensity-type) ---
 ("I003600 blank anode flagged (measured)",  lambda: bool(extras('I003600', 'instr_vocab', substr='Radiation/anode is blank'))),
 ("I003246 no blank-field flag",             lambda: not extras('I003246', 'instr_vocab', substr='blank')),
 # --- 17. PDF monochromator/β-filter -> fill blank Filter (powder-context only) ---
 ("I003747 PDF graphite mono (powder)",      lambda: bool(extras('I003747', 'instr_filter', substr='graphite'))),
 ("I003745 SC mono NOT attributed",          lambda: not extras('I003745', 'instr_filter')),
 ("I003566 SC mono NOT attributed",          lambda: not extras('I003566', 'instr_filter')),
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
