"""Turn an exception into a line the reviewer can act on.

The tool's failures are nearly always environmental, not mysterious: the docx is open in
Word, the download is an HTML error page with a .docx name, PyMuPDF isn't installed, the
Mindat key is missing. A bare `BadZipFile: File is not a zip file` tells a reviewer none of
that. `explain()` maps the handful of failures that actually happen onto a cause and the
command (or action) that fixes them, so an error names its own remedy.

Contract: never raise, never guess wildly. An exception we don't recognise comes back as
'<ExceptionType>: <message>' — no worse than before, and the caller can print it uniformly.
"""
import os

# (predicate, cause, what to do). First match wins, so the specific ones come first.
def _rules(exc, path):
    name = type(exc).__name__
    msg = str(exc)
    f = os.path.basename(path) if path else 'the file'

    if isinstance(exc, PermissionError):
        yield (True,
               '%s is locked by another program — on Windows this is almost always Word '
               'holding it open.' % f,
               'Close the document in Word (and any Explorer preview pane), then run it again.')

    if isinstance(exc, FileNotFoundError):
        yield (True, '%s no longer exists at that path.' % f,
               'It may have been moved or renamed mid-run — re-check the folder and re-run.')

    if name == 'BadZipFile' or 'not a zip file' in msg.lower():
        yield (True,
               '%s is not a real .docx. A .docx IS a zip; this one is not — most often the '
               '"download" is actually an HTML error/login page saved under a .docx name.' % f,
               'Open it in Word to confirm, then re-download it from the source.')

    if isinstance(exc, KeyError) and 'document.xml' in msg:
        yield (True,
               '%s is a zip, but has no word/document.xml — so it is not a Word document '
               '(a renamed .odt/.pages file will do this).' % f,
               'Re-save it from Word as .docx.')

    if name in ('FileDataError', 'EmptyFileError') or 'cannot open' in msg.lower():
        yield (True, '%s could not be opened as a .pdf — it is truncated or corrupt.' % f,
               'Re-download the paper.')

    if isinstance(exc, ImportError):
        mod = getattr(exc, 'name', '') or ''
        pkg = {'fitz': 'PyMuPDF', 'docx': 'python-docx', 'flask': 'Flask',
               'lxml': 'lxml'}.get(mod, mod or 'a required package')
        yield (True, '%s is not installed.' % pkg,
               'Run: pip3 install -r requirements.txt   (or: pip3 install %s)' % pkg)

    if isinstance(exc, AttributeError) and 'add_comment' in msg:
        yield (True,
               'the installed python-docx is too old — Document.add_comment() arrived in 1.2.0, '
               'so no comment can be written and every flagged entry would be skipped.',
               'Run: pip3 install -U "python-docx>=1.2"')

    if isinstance(exc, UnicodeEncodeError):
        yield (True,
               'the console cannot encode the output (λ / α / Å). This is cp1252 on Windows.',
               'Use the launcher (`pxrd …`), which forces UTF-8, or set PYTHONUTF8=1.')

    if 'mindat' in msg.lower() and ('key' in msg.lower() or '401' in msg or '403' in msg):
        yield (True, 'the Mindat API rejected the key (missing, expired, or wrong).',
               'Put a valid key in .mindat_key or $MINDAT_API_KEY, then: '
               'python3 -m pxrd_review.mindat --refresh')


def explain(exc, path=None):
    """One line: what went wrong and what to do. Falls back to the raw exception text."""
    try:
        for ok, cause, fix in _rules(exc, path):
            if ok:
                return '%s  →  %s' % (cause, fix)
    except Exception:
        pass
    return '%s: %s' % (type(exc).__name__, exc)


def note(exc, path=None, prefix='  !!'):
    """Printable, indented failure note — the standard shape for a per-entry skip."""
    return '%s %s' % (prefix, explain(exc, path))
