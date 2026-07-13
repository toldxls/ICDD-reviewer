"""PXRD mineral-review tool — validate an ICDD entry .docx against the source paper
(.pdf), the author .cif, the ICDD .dft, and the Mindat API; write Word comments +
highlights into copies. See README.md for the behavioral contract."""
__version__ = "0.2.6"

# Console output carries λ, α, Å, ⚠, ★. On Windows the default console/pipe encoding is
# cp1252, which cannot encode any of them: a plain `python -m pxrd_review.…` run (i.e. not
# via the `pxrd` launcher, which sets PYTHONUTF8=1) dies with UnicodeEncodeError partway
# through a batch — and redirecting to a file is exactly when it bites. Force UTF-8 on our
# own streams; a no-op everywhere else.
import sys as _sys
if _sys.platform == 'win32':                    # pragma: no cover — POSIX CI never runs this
    for _stream in (_sys.stdout, _sys.stderr):
        try:
            _stream.reconfigure(encoding='utf-8', errors='replace')
        except Exception:                       # detached/replaced stream — nothing to do
            pass
