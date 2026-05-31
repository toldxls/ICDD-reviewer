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
Cache: review_tool/.cache/mindat_ima.json

CLI:
    python3 mindat.py --refresh            # (re)build the cache from the API
    python3 mindat.py --lookup "#mineral"  # test a single name against the cache
"""
import os, re, json, time, ssl, datetime, urllib.request, urllib.error

# macOS python.org builds often ship without CA certs; use certifi's bundle when
# present so HTTPS verification works. $MINDAT_INSECURE=1 disables verification
# as a last resort (public API, read-only — but verification is preferred).
def _ssl_ctx():
    if os.environ.get('MINDAT_INSECURE') == '1':
        return ssl._create_unverified_context()
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()

_CTX = _ssl_ctx()

BASE = 'https://api.mindat.org/v1'
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, '.cache', 'mindat_ima.json')
KEYFILE = os.path.join(HERE, '.mindat_key')
FIELDS = 'id,name,groupid,strunz10ed1,strunz10ed2,strunz10ed3,strunz10ed4,ima_status'

# ----------------------------------------------------------------------------- auth
def api_key():
    k = os.environ.get('MINDAT_API_KEY')
    if k:
        return k.strip()
    if os.path.exists(KEYFILE):
        return open(KEYFILE).read().strip()
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
            if e.code < 500:
                raise RuntimeError('Mindat API %d: %s' % (e.code, e.read()[:200]))
        except urllib.error.URLError:
            pass
        time.sleep(2 ** i + 0.3)
    raise RuntimeError('Mindat fetch failed after %d retries: %s' % (max_retries, url))

def _pull(key, **params):
    """Paginate a geomaterials query into one list of result dicts."""
    q = '&'.join('%s=%s' % (k, v) for k, v in params.items())
    url = '%s/geomaterials/?%s&page-size=500&format=json' % (BASE, q)
    rows = []
    while url:
        data = _fetch(url, key)
        rows.extend(data.get('results', []))
        url = data.get('next')
        if url:
            time.sleep(0.5)
    return rows

# ----------------------------------------------------------------------------- structural cache (for the candidate-group scan)
# Heavier pull (cell + space-group code + element list) kept SEPARATE from the
# lightweight group-lookup cache so normal reviews stay fast. spacegroup is a
# Mindat integer code (consistent per space group; 0 = unknown). b/angles == 0
# mean 'uniaxial / symmetry-default' (b = a).
STRUCT_FIELDS = 'id,name,groupid,spacegroup,a,b,c,alpha,beta,gamma,elements,ima_formula,ima_status'
STRUCT_CACHE = os.path.join(HERE, '.cache', 'mindat_struct.json')

def _f(x):
    try:
        v = float(str(x).strip()); return v
    except Exception:
        return 0.0

def refresh_struct(verbose=True):
    key = api_key()
    if not key:
        raise RuntimeError('No API key for struct refresh')
    if verbose: print('pulling IMA structural data (cell/SG/elements)…')
    rows = _pull(key, ima='true', fields=STRUCT_FIELDS)
    recs = []
    for m in rows:
        recs.append({'name': m.get('name', ''), 'norm': _norm(m.get('name', '')),
                     'groupid': m.get('groupid') or 0, 'sg': m.get('spacegroup') or 0,
                     'a': _f(m.get('a')), 'b': _f(m.get('b')), 'c': _f(m.get('c')),
                     'al': _f(m.get('alpha')), 'be': _f(m.get('beta')), 'ga': _f(m.get('gamma')),
                     'elements': m.get('elements') or [], 'formula': m.get('ima_formula', '')})
    out = {'fetched': time.strftime('%Y-%m-%d'), 'recs': recs}
    os.makedirs(os.path.dirname(STRUCT_CACHE), exist_ok=True)
    json.dump(out, open(STRUCT_CACHE, 'w'))
    if verbose: print('cached -> %s  (%d records)' % (STRUCT_CACHE, len(recs)))
    return out

_SDB = None
def struct_db():
    global _SDB
    if _SDB is None:
        _SDB = json.load(open(STRUCT_CACHE)) if os.path.exists(STRUCT_CACHE) else {}
    return _SDB

def struct_available():
    return os.path.exists(STRUCT_CACHE)

def refresh_struct_if_stale(max_age_days=14):
    """Same staleness policy as the group cache, for the structural pull."""
    global _SDB
    if not api_key():
        return
    db = struct_db()
    age = None
    try:
        age = (datetime.date.today() - datetime.date.fromisoformat(db.get('fetched'))).days
    except Exception:
        pass
    if struct_available() and age is not None and age < max_age_days:
        return
    if not _reachable():
        if struct_available():
            print('[mindat] offline — using cached structural data')
        return
    print('[mindat] structural cache %s — refreshing…' % ('missing' if not struct_available() else '%s days old' % age))
    try:
        refresh_struct(verbose=False); _SDB = None
        print('[mindat] structural cache refreshed (%d records)' % len(struct_db().get('recs', [])))
    except Exception as ex:
        print('[mindat] struct refresh failed (%s) — using existing cache' % ex)

# ----------------------------------------------------------------------------- cache build
def _strunz(rec):
    s = [str(rec.get('strunz10ed%d' % i) or '') for i in (1, 2, 3, 4)]
    code = '%s.%s%s.%s' % (s[0], s[1], s[2], s[3])
    # group containers store all-zero / empty Strunz ('0.00.') — treat as none
    return code if re.search(r'[1-9A-Za-z]', ''.join(s)) else ''

def refresh(verbose=True):
    key = api_key()
    if not key:
        raise RuntimeError('No API key. Set $MINDAT_API_KEY or write %s' % KEYFILE)
    if verbose: print('pulling IMA minerals…')
    minerals = _pull(key, ima='true', fields=FIELDS)
    if verbose: print('  %d minerals' % len(minerals))
    # group container entries (a group is a geomaterial flagged GROUP). Resolve
    # their names so a mineral's groupid → readable group name.
    if verbose: print('pulling group entries…')
    try:
        groups_raw = _pull(key, ima_notes='GROUP', fields=FIELDS)
    except Exception as e:
        if verbose: print('  (ima_notes=GROUP query failed: %s — resolving groupids individually)' % e)
        groups_raw = []
    groups = {}
    for g in groups_raw:
        groups[str(g['id'])] = {'name': g.get('name', ''), 'strunz': _strunz(g)}
    # any groupids not covered: fetch individually (cached, usually few)
    need = {str(m['groupid']) for m in minerals if m.get('groupid')} - set(groups)
    need.discard('0'); need.discard('None')
    for gid in sorted(need):
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
    out = {'fetched': time.strftime('%Y-%m-%d'), 'minerals': index, 'groups': groups}
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(out, open(CACHE, 'w'))
    if verbose: print('cached -> %s  (%d minerals, %d groups)' % (CACHE, len(index), len(groups)))
    return out

# ----------------------------------------------------------------------------- staleness-aware auto-refresh
def cache_age_days():
    """Age of the cached pull in days, or None if there is no dated cache."""
    f = (_db() or {}).get('fetched')
    try:
        return (datetime.date.today() - datetime.date.fromisoformat(f)).days
    except Exception:
        return None

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
def refresh_if_stale(max_age_days=14):
    """Refresh the cache when it is missing or older than max_age_days — so the
    review tools always see ~current IMA data without anyone remembering to run
    --refresh. Safe and quiet: no key or no network → keep using the existing
    cache; attempted at most once per process. Prints one line only when it
    actually pulls (the user sees why there's a brief pause)."""
    global _AUTO_TRIED, _DB
    if _AUTO_TRIED:
        return
    _AUTO_TRIED = True
    if not api_key():
        return                                  # can't refresh; use whatever exists
    age = cache_age_days()
    if available() and age is not None and age < max_age_days:
        return                                  # fresh enough
    if not _reachable():
        if available():
            print('[mindat] offline — using cached IMA data (%s days old)' % (age if age is not None else '?'))
        return
    why = 'missing' if not available() else '%d days old' % (age if age is not None else -1)
    print('[mindat] cache %s — refreshing IMA/group data…' % why)
    try:
        out = refresh(verbose=False)
        _DB = None                              # force reload of the fresh cache
        print('[mindat] refreshed: %d minerals, %d groups' % (len(out['minerals']), len(out['groups'])))
    except Exception as ex:
        print('[mindat] refresh failed (%s) — using existing cache' % ex)

# ----------------------------------------------------------------------------- lookup (offline)
_DB = None
def _db():
    global _DB
    if _DB is None:
        _DB = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    return _DB

def available():
    return os.path.exists(CACHE)

def _norm(name):
    """Normalise a mineral name for matching: lowercase, drop the '-syn' tag,
    collapse spaces. Keep Levinson suffixes like '-(Ce)' (they are distinct
    species)."""
    s = (name or '').strip().lower()
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
if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--refresh', action='store_true')
    ap.add_argument('--refresh-struct', action='store_true', help='build the structural cache (candidate-group scan)')
    ap.add_argument('--lookup')
    a = ap.parse_args()
    if a.refresh:
        refresh()
    if getattr(a, 'refresh_struct', False):
        refresh_struct()
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
