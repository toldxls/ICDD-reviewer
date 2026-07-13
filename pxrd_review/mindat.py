#!/usr/bin/env python3
"""
Mindat.org lookup for authoritative mineral classification / group membership.

A Python port of my Apps Script (same Token auth, page-size 500,
exponential backoff). It pulls every IMA-approved geomaterial once with its
group pointer and Nickel-Strunz code, plus the group container entries, and
caches them to a local JSON. Checks then resolve a mineral's GROUP offline —
no per-entry API calls, no rate-limit exposure during a review run.

Why the API and not PDF prose: a paper saying 'X group' may just be COMPARING
the mineral to a group, not asserting membership. Mindat encodes the real
relationship (a mineral's `groupid` points to its group; a group is itself a
geomaterial flagged `ima_notes=GROUP`, and a group needs ~3 isostructural
members). So `groupid → name` is ground truth.

Key: read from $MINDAT_API_KEY or review_tool/.mindat_key (untracked).
Caches (separate files, both built from ONE pull): review_tool/.cache/mindat_ima.json
(group lookup) + mindat_struct.json (cell/SG/elements).

CLI:
    python3 -m pxrd_review.mindat --refresh            # (re)build both caches from the API
    python3 -m pxrd_review.mindat --lookup "#mineral"  # test a single name against the cache
"""
import os, re, sys, json, time, ssl, datetime, unicodedata, urllib.request, urllib.error, http.client

# macOS python.org builds often ship without CA certs; use certifi's bundle when
# present so HTTPS verification works. $MINDAT_INSECURE=1 disables verification as a
# last resort. NOTE the cost: every request carries the API key in an Authorization
# header, so with verification off that KEY is exposed to anyone able to intercept the
# connection (an SSL-inspecting proxy, a hostile network). The data being read is public;
# the credential is not. Prefer fixing the CA bundle (pip install certifi).
def _ssl_ctx():
    if os.environ.get('MINDAT_INSECURE') == '1':
        print('mindat: WARNING — MINDAT_INSECURE=1: TLS certificate verification is OFF, and the '
              'API key is sent on every request. Anyone intercepting the connection can read it. '
              'Prefer `pip install certifi`; rotate the key if this network is not trusted.',
              file=sys.stderr)
        return ssl._create_unverified_context()
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()

_CTX = _ssl_ctx()

BASE = 'https://api.mindat.org/v1'
from pxrd_review import paths as _paths
CACHE = os.path.join(_paths.cache_dir(), 'mindat_ima.json')
KEYFILE = _paths.keyfile()
FIELDS = 'id,name,groupid,strunz10ed1,strunz10ed2,strunz10ed3,strunz10ed4,ima_status'

# ----------------------------------------------------------------------------- bundled seed cache
# A gzipped snapshot of BOTH caches ships inside the package (pxrd_review/data/*.json.gz,
# refreshed at release time by `--bundle`). Without it, a user with no Mindat API key gets no
# group/chemistry/cell cross-checks at all — and, worse, that looks exactly like a clean batch.
# With it, the tool works fully offline out of the box; a key only buys fresher data, and the
# usual staleness auto-refresh still overwrites the seed into the real cache when one exists.
SEED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

def _seed_path(path):
    return os.path.join(SEED_DIR, os.path.basename(path) + '.gz')

def _read_seed(path):
    """The packaged snapshot for this cache, or {} when it isn't there."""
    sp = _seed_path(path)
    if not os.path.exists(sp):
        return {}
    try:
        import gzip
        with gzip.open(sp, 'rt', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        print('mindat: bundled cache unreadable (%s)' % sp, file=sys.stderr)
        return {}

def _has(path):
    """This cache is usable — from the user's own copy, or from the packaged seed."""
    return os.path.exists(path) or os.path.exists(_seed_path(path))

# ----------------------------------------------------------------------------- cache io
def _read_cache(path):
    """Guarded cache read: a corrupt/truncated file is treated as ABSENT (one-line
    stderr warning) so the staleness logic self-heals by re-fetching, instead of
    every consumer crashing on json.load. Falls back to the packaged seed, so a user with
    no API key still gets the Mindat-backed checks."""
    if not os.path.exists(path):
        return _read_seed(path)
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        print('mindat: cache file unreadable — falling back to the bundled copy (%s)' % path,
              file=sys.stderr)
        return _read_seed(path)

def _write_cache(path, obj):
    """Atomic JSON write (same-dir temp + os.replace) so a Ctrl-C / disk-full
    mid-write can never leave a truncated cache behind."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(obj, f)
    os.replace(tmp, path)

# ----------------------------------------------------------------------------- auth
def api_key():
    k = os.environ.get('MINDAT_API_KEY')
    if k:
        return k.strip()
    if os.path.exists(KEYFILE):
        with open(KEYFILE, encoding='utf-8') as f:
            return f.read().strip()
    return None

# ----------------------------------------------------------------------------- fetch (mirrors the Apps Script backoff)
def _fetch(url, key, max_retries=4):
    req = urllib.request.Request(url, headers={'Authorization': 'Token ' + key})
    for i in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=60, context=_CTX) as r:
                if r.status == 200:
                    return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            # 429 (rate-limited) is the one status backoff EXISTS for — a full refresh is
            # several back-to-back pages — so retry it rather than treating it as fatal.
            # Honour Retry-After when the server sends one. Other 4xx are real client
            # errors (bad/absent key, bad query) and stay fatal.
            if e.code == 429:
                try:
                    wait = float(e.headers.get('Retry-After') or 0)
                except (TypeError, ValueError):
                    wait = 0
                time.sleep(max(wait, 2 ** i + 0.3))
                continue
            if e.code < 500:
                raise RuntimeError('Mindat API %d: %s' % (e.code, e.read()[:200]))
        except urllib.error.URLError:
            pass
        except (json.JSONDecodeError, http.client.HTTPException, OSError):
            # a 200 with truncated/invalid JSON (JSONDecodeError), a connection dropped
            # mid-body (IncompleteRead), or a read-phase timeout (OSError) — all retryable,
            # and left uncaught they escape this loop as a raw traceback instead.
            pass
        time.sleep(2 ** i + 0.3)
    raise RuntimeError('Mindat fetch failed after %d retries: %s' % (max_retries, url))

def _pull(key, page_size=2000, **params):
    """Paginate a geomaterials query into one list of result dicts. page-size is
    well under any server cap (2000 rows ≈ 0.8 s, same as 500) so the whole IMA
    corpus is ~4 pages, not ~13 — fewer round-trips is gentler on the API too."""
    q = '&'.join('%s=%s' % (k, v) for k, v in params.items())
    url = '%s/geomaterials/?%s&page-size=%d&format=json' % (BASE, q, page_size)
    rows = []
    seen = set()
    for _ in range(200):        # hard cap: the full IMA corpus is ~4 pages at 2000/page
        data = _fetch(url, key)
        rows.extend(data.get('results', []))
        nxt = data.get('next')
        if not nxt or nxt in seen:   # a 'next' that repeats itself would otherwise spin forever
            return rows
        seen.add(nxt)
        url = nxt
        time.sleep(0.2)
    print('mindat: stopped paginating after 200 pages (%d rows) — the API returned an unexpectedly '
          'long "next" chain; the pull may be incomplete.' % len(rows), file=sys.stderr)
    return rows

# ----------------------------------------------------------------------------- structural cache (for the candidate-group scan)
# Heavier pull (cell + space-group code + element list) kept SEPARATE from the
# lightweight group-lookup cache so normal reviews stay fast. spacegroup is a
# Mindat integer code (consistent per space group; 0 = unknown). b/angles == 0
# mean 'uniaxial / symmetry-default' (b = a).
STRUCT_FIELDS = 'id,name,groupid,spacegroup,a,b,c,alpha,beta,gamma,elements,ima_formula,ima_status'
STRUCT_CACHE = os.path.join(_paths.cache_dir(), 'mindat_struct.json')

# One pull feeds BOTH caches: the struct fields already carry groupid/ima_status,
# so adding the four Strunz codes is everything the group cache needs too. The two
# caches stay SEPARATE files (a normal review only loads the small group cache) but
# share a single network pass — no second walk over the same 6224 IMA minerals.
COMBINED_FIELDS = STRUCT_FIELDS + ',strunz10ed1,strunz10ed2,strunz10ed3,strunz10ed4'

def _f(x):
    try:
        v = float(str(x).strip()); return v
    except Exception:
        return 0.0

def _struct_out(rows):
    """Build the structural cache dict from already-pulled mineral rows."""
    recs = []
    for m in rows:
        recs.append({'name': m.get('name', ''), 'norm': _norm(m.get('name', '')),
                     'groupid': m.get('groupid') or 0, 'sg': m.get('spacegroup') or 0,
                     'a': _f(m.get('a')), 'b': _f(m.get('b')), 'c': _f(m.get('c')),
                     'al': _f(m.get('alpha')), 'be': _f(m.get('beta')), 'ga': _f(m.get('gamma')),
                     'elements': m.get('elements') or [], 'formula': m.get('ima_formula', '')})
    return {'fetched': time.strftime('%Y-%m-%d'), 'recs': recs}

def refresh_struct(verbose=True):
    """The structural cache is now built as part of the single unified pull, so
    this just delegates to refresh() (kept for the --refresh-struct CLI entry)."""
    refresh(verbose=verbose)
    return struct_db()

_SDB = None
def struct_db():
    global _SDB
    if _SDB is None:
        _SDB = _read_cache(STRUCT_CACHE)
    return _SDB

def struct_available():
    return _has(STRUCT_CACHE)

def _struct_age_days():
    """Age of the structural cache in days, or None if undated/missing."""
    try:
        return (datetime.date.today() - datetime.date.fromisoformat(struct_db().get('fetched'))).days
    except Exception:
        return None

def refresh_struct_if_stale(max_age_days=14):
    """Both caches share one staleness check + one network pull now, so this just
    routes to the unified auto-refresh (see _auto_refresh)."""
    _auto_refresh(max_age_days)

# ----------------------------------------------------------------------------- cache build
def _strunz(rec):
    s = [str(rec.get('strunz10ed%d' % i) or '') for i in (1, 2, 3, 4)]
    code = '%s.%s%s.%s' % (s[0], s[1], s[2], s[3])
    # group containers store all-zero / empty Strunz ('0.00.') — treat as none
    return code if re.search(r'[1-9A-Za-z]', ''.join(s)) else ''

def _group_names(key, referenced, verbose=False):
    """Resolve {groupid -> {name, strunz}} for the referenced group ids with a
    couple of BULK queries instead of one request per id. Mindat files group
    containers two ways: most as entrytype=5 ('grouplist'); ~120 older ones as a
    plain mineral (entrytype=0) named '… Group/Subgroup'. The old ima_notes=GROUP
    query returned only ~150, leaving ~470 ids to fetch one-by-one — that serial
    loop was the real bottleneck (~110 s). We pull the two slices once and keep
    only the referenced ids, so the cache stays lean and the per-id fallback in
    refresh() almost never fires."""
    lut = {}
    for g in _pull(key, entrytype=5, fields=FIELDS):                  # grouplists (one query)
        lut[str(g['id'])] = g
    if referenced - set(lut):                                         # only if some are still unresolved
        if verbose: print('  pulling entrytype=0 group parents…')
        for g in _pull(key, entrytype=0, name__icontains='group', fields=FIELDS):
            gid = str(g['id'])
            if gid in referenced and gid not in lut:
                lut[gid] = g
    return {gid: {'name': lut[gid].get('name', ''), 'strunz': _strunz(lut[gid])}
            for gid in referenced if gid in lut}

def refresh(verbose=True):
    """Single network pull of all IMA minerals → writes BOTH the group cache
    (mindat_ima.json) and the structural cache (mindat_struct.json). One pass over
    the corpus feeds both; the files stay separate on disk so a normal review still
    loads only the small group cache."""
    global _DB, _SDB
    key = api_key()
    if not key:
        raise RuntimeError('No API key. Set $MINDAT_API_KEY or write %s' % KEYFILE)
    if verbose: print('pulling IMA minerals (cell + group + Strunz, one pass)…')
    minerals = _pull(key, ima='true', fields=COMBINED_FIELDS)
    if verbose: print('  %d minerals' % len(minerals))
    # sanity guard: a partial/failed pull must never clobber a good cache. The IMA
    # corpus is ~6200 species, so refuse an implausibly small pull (under 1000 rows,
    # or under half of what the existing cache already holds). A corrupt/absent
    # existing cache reads as 0 minerals, so a fresh install still refreshes.
    have = len(_read_cache(CACHE).get('minerals') or {})
    if len(minerals) < max(1000, have // 2):
        raise RuntimeError('Mindat pull returned only %d minerals (existing cache has %d) '
                           '— refusing to overwrite the caches' % (len(minerals), have))
    # resolve every referenced group container's name (bulk; a geomaterial is a
    # group when it is a grouplist or a '… Group'-named parent).
    referenced = {str(m['groupid']) for m in minerals if m.get('groupid')}
    referenced.discard('0'); referenced.discard('None')
    if verbose: print('resolving %d group containers…' % len(referenced))
    groups = _group_names(key, referenced, verbose)
    # rare straggler a referenced id neither slice returned: one-off fallback
    for gid in sorted(referenced - set(groups)):
        try:
            d = _fetch('%s/geomaterials/%s/?fields=id,name,strunz10ed1,strunz10ed2,strunz10ed3,strunz10ed4'
                       % (BASE, gid), key)
            groups[gid] = {'name': d.get('name', ''), 'strunz': _strunz(d)}
        except Exception:
            groups[gid] = {'name': '', 'strunz': ''}
    index = {}
    for m in minerals:
        index[_norm(m.get('name', ''))] = {
            'name': m.get('name', ''), 'groupid': m.get('groupid'),
            'strunz': _strunz(m), 'ima_status': m.get('ima_status'),
        }
    grp = {'fetched': time.strftime('%Y-%m-%d'), 'minerals': index, 'groups': groups}
    _write_cache(CACHE, grp)
    # structural cache — built from the SAME rows, written to its own file
    st = _struct_out(minerals)
    _write_cache(STRUCT_CACHE, st)
    _DB = None; _SDB = None                  # force reload of both fresh caches
    if verbose:
        print('cached -> %s (%d minerals, %d groups) + %s (%d records)'
              % (CACHE, len(index), len(groups), STRUCT_CACHE, len(st['recs'])))
    return grp

# ----------------------------------------------------------------------------- staleness-aware auto-refresh
def cache_age_days():
    """Age of the cached pull in days, or None if there is no dated cache."""
    f = (_db() or {}).get('fetched')
    try:
        return (datetime.date.today() - datetime.date.fromisoformat(f)).days
    except Exception:
        return None

STALE_DAYS = 14                 # the auto-refresh threshold; the banner reports against the same line

def cache_status(max_age_days=STALE_DAYS):
    """(state, one_line) describing the offline Mindat caches.

    state is 'missing' | 'stale' | 'ok'. Worth printing at the top of every run: the
    Mindat-backed checks (group/classification, chemistry, the cell cross-check) go SILENT
    when the cache is absent — they simply find nothing — so a missing cache looks exactly
    like a clean corpus unless the tool says otherwise."""
    gage, sage = cache_age_days(), _struct_age_days()
    have_g, have_s = available(), struct_available()
    if not have_g and not have_s:
        return 'missing', ('mindat cache: MISSING — group/chemistry/cell cross-checks are '
                           'INACTIVE. Run: python3 -m pxrd_review.mindat --refresh')
    n = len((_db() or {}).get('minerals') or {})
    fetched = (_db() or {}).get('fetched') or '?'
    ages = [x for x in (gage, sage) if x is not None]
    age = max(ages) if ages else None
    partial = '' if (have_g and have_s) else \
              ('  [%s cache missing]' % ('structural' if have_g else 'group'))
    if age is None:
        return 'stale', ('mindat cache: undated — age unknown. Run: '
                         'python3 -m pxrd_review.mindat --refresh' + partial)
    when = 'today' if age == 0 else ('1 day old' if age == 1 else '%d days old' % age)
    # Say WHERE the data came from. On a machine with no API key the seed shipped in the wheel
    # is doing the work, and the reviewer should know that: it explains why the checks run at
    # all, and why the date is the release date rather than today.
    src = '' if os.path.exists(CACHE) else ' [bundled with this release]'
    line = 'mindat cache: %s species, fetched %s (%s)%s%s' % (f'{n:,}', fetched, when, src, partial)
    if age >= max_age_days or partial:
        tail = ' — STALE; it auto-refreshes when online' + (
            ' (needs a Mindat API key)' if not api_key() else '') + \
            ', or run: python3 -m pxrd_review.mindat --refresh'
        return 'stale', line + tail
    return 'ok', line

def print_cache_banner(max_age_days=STALE_DAYS, file=None):
    """One-line cache header for the console tools. Never raises — a broken cache must not
    take a review down, and the banner is exactly what tells the reviewer it IS broken."""
    try:
        state, line = cache_status(max_age_days)
    except Exception as ex:
        state, line = 'missing', 'mindat cache: unreadable (%s)' % ex
    mark = {'ok': '', 'stale': '!! ', 'missing': '!! '}[state]
    print('[mindat] %s%s' % (mark, line), file=file or sys.stdout)
    return state

def _reachable():
    """Quick preflight so an offline machine pays ~6 s, not the full retry budget."""
    try:
        req = urllib.request.Request(BASE + '/geomaterials/?page-size=1&format=json',
                                     headers={'Authorization': 'Token ' + (api_key() or '')})
        urllib.request.urlopen(req, timeout=6, context=_CTX).read(1)
        return True
    except Exception:
        return False

_AUTO_TRIED = False
def _auto_refresh(max_age_days=14):
    """Unified staleness-aware auto-refresh for BOTH caches. They are now built from
    one pull, so a single staleness check + single network pass keeps them current —
    review tools always see ~current IMA data without anyone running --refresh. Safe
    and quiet: no key or no network → keep using whatever exists; attempted at most
    once per process; prints only when it actually pulls (so the user sees why there
    is a brief pause). Both refresh_if_stale and refresh_struct_if_stale route here,
    so whichever the run touches first does the single pull and the other is a no-op."""
    global _AUTO_TRIED
    if _AUTO_TRIED:
        return
    _AUTO_TRIED = True
    if not api_key():
        return                                  # can't refresh; use whatever exists
    gage, sage = cache_age_days(), _struct_age_days()
    group_ok  = available() and gage is not None and gage < max_age_days
    struct_ok = struct_available() and sage is not None and sage < max_age_days
    if group_ok and struct_ok:
        return                                  # both fresh enough
    if not _reachable():
        if available() or struct_available():
            print('[mindat] offline — using cached IMA data (%s days old)' % (gage if gage is not None else '?'))
        return
    stale = []
    if not group_ok:  stale.append('group %s'  % ('missing' if not available()        else '%dd' % (gage if gage is not None else -1)))
    if not struct_ok: stale.append('struct %s' % ('missing' if not struct_available() else '%dd' % (sage if sage is not None else -1)))
    print('[mindat] cache %s — refreshing IMA group + structural data (single pull)…' % ', '.join(stale))
    try:
        grp = refresh(verbose=False)
        print('[mindat] refreshed: %d minerals, %d groups, %d structural records'
              % (len(grp['minerals']), len(grp['groups']), len(struct_db().get('recs', []))))
    except Exception as ex:
        print('[mindat] refresh failed (%s) — using existing cache' % ex)

def refresh_if_stale(max_age_days=14):
    """Back-compat entry (called from the checks); routes to the unified refresh."""
    _auto_refresh(max_age_days)

# ----------------------------------------------------------------------------- lookup (offline)
_DB = None
def _db():
    global _DB
    if _DB is None:
        _DB = _read_cache(CACHE)
        # re-key the minerals through the CURRENT _norm, so a cache built by an older
        # normaliser (e.g. one that didn't fold diacritics) still resolves today's
        # queries — no network refresh needed ('Åsgruvanite-(Ce)' -> 'asgruvanite-(ce)').
        mins = _DB.get('minerals')
        if mins:
            _DB['minerals'] = {_norm(v.get('name') or k): v for k, v in mins.items()}
    return _DB

def available():
    return _has(CACHE)

def _norm(name):
    """Normalise a mineral name for matching: FOLD DIACRITICS (Å→A, ö→o), lowercase,
    drop the '-syn' tag, collapse spaces. Keep Levinson suffixes like '-(Ce)' (they are
    distinct species). Diacritic folding is essential because Mindat keeps the accented
    name (e.g. 'Åsgruvanite-(Ce)') while the docx uses the ASCII form ('Asgruvanite-(Ce)')."""
    s = unicodedata.normalize('NFKD', name or '')
    s = ''.join(c for c in s if not unicodedata.combining(c))   # Åsgruvanite -> Asgruvanite
    s = s.strip().lower()
    s = re.sub(r'[\s,\-]*\bsyn\b\.?', '', s)      # synthetic tag: '-syn' or ', syn'
    s = re.sub(r'\s+', ' ', s).strip()
    return s.strip(' ,-')

# polytype / variety suffixes to try stripping on a miss (Mindat keys the base
# species): '-2T', '-IIb-4', '-2c', '-1A', and variety adjectives 'Gypsum-strontian'.
def _candidates(name):
    n = _norm(name)
    yield n
    m = re.sub(r'-[0-9ivxabcmht]+(-[0-9]+)?$', '', n, flags=re.I)   # polytype tail
    if m != n: yield m
    # base species before a variety adjective / suffix: 'gypsum, strontian',
    # 'gypsum-strontian' -> 'gypsum'
    base = re.split(r'[,\-]', n)[0].strip()
    if base and base != n:
        yield base

def lookup(name):
    db = _db()
    mins = db.get('minerals', {})
    for cand in _candidates(name):
        if cand in mins:
            return mins[cand]
    return None

def group_of(name):
    """Return (group_name, species_strunz, matched_species, ima_status) or None.
    Strunz is the SPECIES' code (group containers don't carry one)."""
    rec = lookup(name)
    if not rec:
        return None
    gid = rec.get('groupid')
    gname = _db().get('groups', {}).get(str(gid), {}).get('name', '') if gid else ''
    return (gname, rec.get('strunz', ''), rec['name'], rec.get('ima_status'))

# ----------------------------------------------------------------------------- cli
def bundle_seed():
    """MAINTAINER step, run before cutting a release: freeze the current caches into the
    package as gzipped seeds, so a user with no Mindat API key still gets the group /
    chemistry / cell cross-checks straight out of the wheel. Refresh first, then bundle."""
    import gzip, shutil
    os.makedirs(SEED_DIR, exist_ok=True)
    out = []
    for path in (CACHE, STRUCT_CACHE):
        if not os.path.exists(path):
            raise SystemExit('no cache at %s — run --refresh first' % path)
        db = _read_cache(path)
        n = len(db.get('minerals') or db.get('recs') or {})
        if n < 1000:                       # same sanity floor the refresh uses
            raise SystemExit('%s holds only %d records — refusing to bundle a partial cache'
                             % (os.path.basename(path), n))
        sp = _seed_path(path)
        with open(path, 'rb') as fi, gzip.open(sp, 'wb', compresslevel=9) as fo:
            shutil.copyfileobj(fi, fo)
        out.append((sp, n, db.get('fetched'), os.path.getsize(sp)))
    for sp, n, fetched, size in out:
        print('bundled %-28s %5d records  fetched %s  (%.0f KB)'
              % (os.path.basename(sp), n, fetched, size / 1024))
    print('\nCommit pxrd_review/data/ — the wheel now works with no API key.')

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--refresh', action='store_true', help='(re)build both caches (group + structural) from one API pull')
    ap.add_argument('--refresh-struct', action='store_true', help='alias for --refresh (both caches are built from one pull now)')
    ap.add_argument('--bundle', action='store_true',
                    help='maintainer: freeze the current caches into pxrd_review/data/ so the '
                         'wheel works with no API key (run --refresh first)')
    ap.add_argument('--status', action='store_true', help='report the cache age and where it came from')
    ap.add_argument('--lookup')
    a = ap.parse_args()
    if a.refresh or getattr(a, 'refresh_struct', False):
        refresh()
    if a.bundle:
        bundle_seed()
    if a.status:
        print_cache_banner()
    if a.lookup:
        if not available():
            print('no cache — run --refresh first'); raise SystemExit(1)
        r = group_of(a.lookup)
        if not r:
            print('%-24s : not found in IMA cache' % a.lookup)
        else:
            gname, gstrunz, sp, status = r
            print('%-24s -> species %r [%s]' % (a.lookup, sp, status))
            print('    group: %s  (Strunz %s)' % (gname or '(none / ungrouped)', gstrunz or '?'))
