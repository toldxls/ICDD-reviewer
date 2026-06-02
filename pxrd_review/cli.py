#!/usr/bin/env python3
"""
pxrd — one launcher for the PXRD review tools, so you don't type folder prefixes,
long module paths, or ports.

    pxrd gui [folder] [extra…]     open the review-mode GUI (auto-port, auto-browser)
    pxrd review [folder] [extra…]  write comments/highlights -> <folder>/review_out
    pxrd lambda [folder] [extra…]  cell/λ console report
    pxrd extras [folder] [extra…]  the extra checks, console
    pxrd candidates [folder] […]   candidate-group scan, console
    pxrd check [fixtures]          run the regression suite
    pxrd refresh [--refresh-struct] refresh the Mindat cache
    pxrd mindat [args…]            call mindat.py directly (e.g. --lookup Quartz)

Folder resolution for the data sub-commands: an explicit folder argument wins;
otherwise the current directory is used when it contains entry .docx files (so a
bare `pxrd gui` from inside a data folder just works); otherwise the folder you
last passed for that sub-command is reused. Extra flags pass straight through.
(`check` ignores the cwd default — it uses the fixtures folder you pass / remember.)
"""
import os, sys, json, glob
from pxrd_review import paths as P

MODULE = {
    'gui':        'pxrd_review.gui.review_gui',
    'review':     'pxrd_review.annotate_review',
    'lambda':     'pxrd_review.cell_lambda_check',
    'extras':     'pxrd_review.extra_checks',
    'candidates': 'pxrd_review.candidate_groups',
    'check':      'pxrd_review.regression_check',
    'refresh':    'pxrd_review.mindat',
    'mindat':     'pxrd_review.mindat',
}
NEEDS_FOLDER = {'gui', 'review', 'lambda', 'extras', 'candidates', 'check'}
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
    return any(glob.glob(os.path.join(folder, pat)) for pat in ('I*.docx', 'O*.docx', '*.docx'))

def _resolve_folder(sub, rest):
    """explicit arg > cwd-with-docx (not for `check`) > remembered."""
    if rest and not rest[0].startswith('-'):
        _save(sub, rest[0]); return rest[0], rest[1:]
    cwd = os.getcwd()
    if sub != 'check' and _has_entry_docx(cwd):
        _save(sub, cwd); return cwd, rest
    folder = _load().get(sub)
    if not folder:
        raise SystemExit("pxrd %s: no folder given and none remembered — pass the entries "
                         "folder once, e.g.  pxrd %s \"/path/to/Part 1\"" % (sub, sub))
    if not os.path.isdir(folder):
        raise SystemExit("pxrd %s: remembered folder no longer exists: %s" % (sub, folder))
    return folder, rest

def _usage(code=0):
    print(__doc__.strip()); raise SystemExit(code)

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help', 'help'):
        _usage()
    sub, rest = sys.argv[1], sys.argv[2:]
    if sub not in MODULE:
        print("pxrd: unknown command %r\n" % sub); _usage(2)

    if sub in NEEDS_FOLDER:
        folder, passthru = _resolve_folder(sub, rest)
        args = [folder] + passthru
    elif sub == 'refresh':
        args = rest or ['--refresh']        # bare `refresh` -> --refresh
    else:                                   # mindat passthrough
        args = rest

    # the child is a fresh interpreter: ensure the package is importable even when
    # not pip-installed (running via the repo's ./pxrd dev shim)
    os.environ['PYTHONPATH'] = P.repo_root() + os.pathsep + os.environ.get('PYTHONPATH', '')
    os.execv(sys.executable, [sys.executable, '-m', MODULE[sub]] + args)  # keeps Ctrl-C wired

if __name__ == '__main__':
    main()
