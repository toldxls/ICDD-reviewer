"""Where the tool's writable state lives — the Mindat caches (.cache/) and the
API key (.mindat_key). Historically these sat at the repo root (one level above the
code). After packaging the code into pxrd_review/, this single resolver keeps them
findable in every install mode, so an existing .mindat_key / .cache keeps working:

  1. $PXRD_REVIEW_HOME, if set (explicit override).
  2. The repo root (parent of this package) when it is an actual checkout (has
     pyproject.toml) and writable — the dev / editable (`pip install -e .`) case:
     preserves the user's current .cache/ + .mindat_key.
  3. ~/.pxrd_review/ — for a wheel install into site-packages. (Checked by marker,
     not writability: per-user Pythons have a WRITABLE site-packages, and state
     scattered there would silently vanish on upgrade/reinstall.)
"""
import os

def repo_root():
    """The directory that contains the pxrd_review package."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def data_home():
    env = os.environ.get('PXRD_REVIEW_HOME')
    if env:
        return os.path.abspath(os.path.expanduser(env))
    root = repo_root()
    if os.path.isfile(os.path.join(root, 'pyproject.toml')) and os.access(root, os.W_OK):
        return root
    return os.path.join(os.path.expanduser('~'), '.pxrd_review')

def cache_dir():
    return os.path.join(data_home(), '.cache')

def keyfile():
    return os.path.join(data_home(), '.mindat_key')
