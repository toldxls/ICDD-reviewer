#!/usr/bin/env python3
"""
pxrd — one launcher for the PXRD review tools, so you don't type folder prefixes,
long module paths, or ports.

    pxrd gui [folder] [extra…]     open the review-mode GUI (auto-port, auto-browser)
    pxrd review [folder] [extra…]  write comments/highlights -> <folder>/review_out
    pxrd lambda [folder] [extra…]  cell/λ console report
    pxrd extras [folder] [extra…]  the extra checks, console
    pxrd candidates [folder] […]   candidate-group scan, console
    pxrd sweep [folder] [extra…]   read-only corpus report + diff vs last run -> review_out/
    pxrd check [fixtures]          run the regression suite
    pxrd refresh [--refresh-struct] refresh the Mindat cache
    pxrd mindat [args…]            call mindat.py directly (e.g. --lookup Quartz)
    pxrd refs <manuscript.docx|.pdf|folder> [--with FILE] [--no-annotate]
                                   manuscript citations vs its reference list (both directions + form)
                                   -> console + <dir>/review_out/<name>_refs_report.txt, and for a
                                   .docx an annotated copy <name>_refs.docx
    pxrd bv <structure.cif> [--table manuscript.docx] [--params gh|bo|ba] [--ox Fe=2] [--word]
                                   bond distances + bond-valence sums from the .cif (formatted
                                   table), self-checked against the .cif's own bond loop; --table
                                   checks the manuscript's bond-distance and bond-valence tables
    pxrd tables <structure.cif> [--word] [--params gh|bo|ba] [--ox Fe=2]
                                   publishable tables from the .cif: coordinates + displacement
                                   parameters, selected bond distances (symmetry codes, means),
                                   hydrogen bonds, bond-valence analysis; --word writes a .docx
    pxrd epma <probe.xlsx|.csv> --basis O=21 [--add H2O=structure:6 …] [--charge H2O --anions N] [--xlsx]
                                   microprobe reduction: mean/range/s.d. table, empirical formula on a
                                   basis, xlsx with live formulas
    pxrd epma <entry.docx> --check | pxrd epma --check "Microprobe analysis … : formula"
                                   replicate an ICDD entry's published formula from its Analysis field
                                   and report the coefficients / constituents that do not follow
    pxrd gd --wt "UO3=63.9,…" --n 2.06 [--density D | --cif X.cif] [--xlsx]
                                   Gladstone–Dale compatibility (K_P, K_C, 1 − K_P/K_C)
    pxrd pxrd <obs list> <calc list> [--word --xlsx]   the powder-diffraction table (obs/calc combined
                                   lines, eight strongest in bold)

Folder resolution for the data sub-commands: an explicit folder argument wins; a
leading entry id (e.g. `pxrd extras I003448`) is passed through to the module, not
taken as a folder; otherwise the current directory is used when it contains entry
.docx files (so a bare `pxrd gui` from inside a data folder just works); otherwise
the folder you last passed for that sub-command is reused. Extra flags pass straight
through. (`check` ignores the cwd default — explicit arg > $PXRD_REGRESSION_DIR >
the fixtures folder you last passed.)
"""
import os, re, sys, json, glob
from pxrd_review import paths as P

MODULE = {
    'gui':        'pxrd_review.gui.review_gui',
    'review':     'pxrd_review.annotate_review',
    'lambda':     'pxrd_review.cell_lambda_check',
    'extras':     'pxrd_review.extra_checks',
    'candidates': 'pxrd_review.candidate_groups',
    'sweep':      'pxrd_review.sweep',
    'check':      'pxrd_review.regression_check',
    'refresh':    'pxrd_review.mindat',
    'mindat':     'pxrd_review.mindat',
    'refs':       'pxrd_review.refs_check',   # takes a FILE (or folder) — not folder-resolved
    'bv':         'pxrd_review.bv_check',     # takes a .cif — not folder-resolved
    'tables':     'pxrd_review.tables',       # takes a .cif — not folder-resolved
    'epma':       'pxrd_review.epma',         # takes a probe export — not folder-resolved
    'gd':         'pxrd_review.gd',           # options only
    'pxrd':       'pxrd_review.pxrd_table',   # takes obs + calc lists — not folder-resolved
}
NEEDS_FOLDER = {'gui', 'review', 'lambda', 'extras', 'candidates', 'sweep', 'check'}
MEM = os.path.join(P.cache_dir(), 'pxrd_last.json')   # remembered folder per sub-command

def _load():
    try:
        with open(MEM, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def _save(sub, folder):
    d = _load(); d[sub] = os.path.abspath(folder)
    try:
        os.makedirs(os.path.dirname(MEM), exist_ok=True)
        with open(MEM, 'w', encoding='utf-8') as f:
            json.dump(d, f, indent=1)
    except Exception:
        pass

def _has_entry_docx(folder):
    # entry docx only (I*/O*) — a random .docx in the cwd must not hijack resolution
    return any(glob.glob(os.path.join(folder, pat)) for pat in ('I*.docx', 'O*.docx'))

ENTRY_ID = re.compile(r'[A-Za-z]\d{4,6}')      # e.g. I003448 / O12345 — an id, not a folder

def _resolve_folder(sub, rest):
    """explicit arg > cwd-with-docx (not for `check`) > remembered
    (`check` slots $PXRD_REGRESSION_DIR between the explicit arg and the memory)."""
    if rest and not rest[0].startswith('-'):
        if os.path.isdir(rest[0]):
            _save(sub, rest[0]); return rest[0], rest[1:]
        if not ENTRY_ID.fullmatch(rest[0]):
            raise SystemExit("pxrd %s: not a folder: %s" % (sub, rest[0]))
        # an entry id: leave it in rest (passes through to the module) and resolve
        # the folder as usual below
    cwd = os.getcwd()
    if sub != 'check' and _has_entry_docx(cwd):
        _save(sub, cwd); return cwd, rest
    if sub == 'check':
        env = os.environ.get('PXRD_REGRESSION_DIR')
        if env:
            if not os.path.isdir(env):
                raise SystemExit("pxrd check: $PXRD_REGRESSION_DIR is not a folder: %s" % env)
            return env, rest                    # env-derived: use, but never remember
    folder = _load().get(sub)
    if not folder:
        raise SystemExit("pxrd %s: no folder given and none remembered — pass the entries "
                         "folder once, e.g.  pxrd %s \"/path/to/Part 1\"" % (sub, sub))
    if not os.path.isdir(folder):
        raise SystemExit("pxrd %s: remembered folder no longer exists: %s" % (sub, folder))
    return folder, rest

# How each sub-command wants a single entry id. The launcher advertises a bare trailing id
# ('pxrd review I003448'), but the modules disagree on how to take one: most expose --id,
# extra_checks takes it positionally, and sweep/check/gui have no per-entry mode at all.
# Translate here, so the documented shorthand works everywhere instead of only for `extras`
# (the others used to forward the id as a stray positional and die on 'unrecognized arguments').
_ID_STYLE = {'review': '--id', 'lambda': '--id', 'candidates': '--id',
             'extras': 'positional', 'sweep': None, 'check': None, 'gui': None}

def _fix_entry_id(sub, passthru):
    if not passthru or not ENTRY_ID.fullmatch(passthru[0]):
        return passthru
    eid, tail = passthru[0], passthru[1:]
    style = _ID_STYLE.get(sub)
    if style == '--id':
        return ['--id', eid] + tail
    if style == 'positional':
        return [eid] + tail
    raise SystemExit("pxrd %s: does not take a single entry id (%s) — it runs over the whole "
                     "folder. Use 'pxrd %s' without the id%s."
                     % (sub, eid, sub,
                        ", or 'pxrd review %s' / 'pxrd lambda %s' for one entry" % (eid, eid)
                        if sub in ('sweep', 'check') else ''))

def _usage(code=0):
    print(__doc__.strip()); raise SystemExit(code)

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help', 'help'):
        _usage()
    if sys.argv[1] in ('-V', '--version', 'version'):
        from pxrd_review import __version__
        print('pxrd-review %s' % __version__); raise SystemExit(0)
    sub, rest = sys.argv[1], sys.argv[2:]
    if sub not in MODULE:
        print("pxrd: unknown command %r\n" % sub); _usage(2)

    if sub in NEEDS_FOLDER:
        folder, passthru = _resolve_folder(sub, rest)
        args = [folder] + _fix_entry_id(sub, passthru)
    elif sub == 'refresh':
        args = rest or ['--refresh']        # bare `refresh` -> --refresh
    else:                                   # mindat / refs passthrough
        args = rest
        if sub == 'refs' and not rest:
            raise SystemExit("pxrd refs: give a manuscript .docx (or .pdf, or a folder of them), "
                             "e.g.  pxrd refs \"My paper.docx\"")
        if sub == 'bv' and not rest:
            raise SystemExit("pxrd bv: give a structure .cif, e.g.  pxrd bv mineral.cif --table \"My paper.docx\"")
        if sub == 'tables' and not rest:
            raise SystemExit("pxrd tables: give a structure .cif, e.g.  pxrd tables mineral.cif --word")
        if sub == 'epma' and not rest:
            raise SystemExit("pxrd epma: give the probe export, e.g.  pxrd epma probe.xlsx --basis O=21 --xlsx")
        if sub == 'pxrd' and not rest:
            raise SystemExit("pxrd pxrd: give the observed and calculated peak lists, e.g.  pxrd pxrd obs.txt calc.txt --word")

    # the child is a fresh interpreter: ensure the package is importable even when
    # not pip-installed (running via the repo's ./pxrd dev shim)
    os.environ['PYTHONPATH'] = P.repo_root() + os.pathsep + os.environ.get('PYTHONPATH', '')
    argv = [sys.executable, '-m', MODULE[sub]] + args
    if os.name == 'nt':
        # Windows exec* doesn't replace the process: it spawns a child while joining
        # argv WITHOUT quoting — a folder containing a space arrives split in two —
        # and hands the prompt back while the child still prints. subprocess quotes
        # list args correctly and waits. PYTHONUTF8 keeps the child's stdout UTF-8
        # even when piped/redirected (cp1252 otherwise crashes on λ/α/→ in output).
        import subprocess
        os.environ['PYTHONUTF8'] = '1'
        try:
            rc = subprocess.run(argv).returncode
        except KeyboardInterrupt:
            rc = 130
        raise SystemExit(rc)
    os.execv(sys.executable, argv)      # POSIX: true exec — keeps Ctrl-C wired

if __name__ == '__main__':
    main()
