#!/usr/bin/env python3
"""The RRUFF spectra fetched from rruff.net into a local store — the reference library the spectrum window pulls up
beside a spectrum, found whatever folder is open.

    pxrd rruff --fetch                     the Raman collection (every quality, oriented and unoriented, and the broad
                                           scans that reach the O–H region; about 700 MB downloaded, the processed
                                           spectra kept — some 300 MB on disk)
    pxrd rruff --fetch --raw --ir          … the RAW spectra too, and the infrared collection
    pxrd rruff --fetch --sets excellent_unoriented fair_unoriented      only these sets
    pxrd rruff --status                    what the store holds, and where
    pxrd rruff --remove                    the store deleted

Source: RRUFF's own bulk files (https://www.rruff.net/about/download-data/), read into one index (index.json) and one
array file (spectra.f32: x then y, float32, per spectrum) under <data home>/.cache/rruff/. Nothing of a paper or a
spectrum under review is sent anywhere: the download is the only traffic, and only when asked for. Please cite the
project when its spectra are used: Lafuente, Downs, Yang & Stone (2015), The power of databases: the RRUFF project.

Beside it, a Thermo OMNIC copy of the library (RRUFFLib.lbd + .lbt; omnic_lib) is still read when there is one: the
window sees both as one list (`libraries`).
"""
import os, re, sys, json, zipfile, struct, mmap, time, shutil, threading, urllib.request, urllib.error

from pxrd_review import paths as P

SOURCE = 'https://www.rruff.net/zipped_data_files/'
CITATION = ('Lafuente B., Downs R.T., Yang H., Stone N. (2015) The power of databases: the RRUFF project. In: Highlights in '
            'Mineralogical Crystallography (T. Armbruster, R.M. Danisi, eds), W. De Gruyter, Berlin, 1–30. https://rruff.net')
# set name -> (technique, quality, orientation) as RRUFF files them
SETS = {'excellent_oriented': ('raman', 'excellent', 'oriented'), 'excellent_unoriented': ('raman', 'excellent', 'unoriented'),
        'fair_oriented': ('raman', 'fair', 'oriented'), 'fair_unoriented': ('raman', 'fair', 'unoriented'),
        'poor_unoriented': ('raman', 'poor', 'unoriented'),                                      # RRUFF publishes no poor_oriented set
        'unrated_oriented': ('raman', 'unrated', 'oriented'), 'unrated_unoriented': ('raman', 'unrated', 'unoriented'),
        'LR-Raman': ('raman', 'broad', 'unoriented'), 'infrared': ('infrared', '', '')}      # LR-Raman = RRUFF's broad scans (low resolution, to the O–H region)
REQUIRED = ('excellent_unoriented',)       # a 404 on this one is a failure, not a set to skip: the collection is not where it was
DEFAULT_SETS = ('excellent_oriented', 'excellent_unoriented', 'fair_oriented', 'fair_unoriented', 'poor_unoriented',
                'unrated_oriented', 'unrated_unoriented', 'LR-Raman')
QUALITY_RANK = {'excellent': 0, 'fair': 1, 'unrated': 2, 'poor': 3, 'broad': 4, '': 5}
LASER_RANK = {532: 0, 785: 1, 780: 1, 514: 2, 515: 2, 633: 3, 632: 3, 638: 3, 488: 3, 458: 3, 405: 4}
UA = 'pxrd-review (https://github.com/toldxls/ICDD-reviewer)'
PROGRESS = {}                   # the fetch in hand, for a window that asked for one: stage, set, done, total, spectra, error, finished

def _ssl_context():
    """certifi's bundle where it is installed (a python.org Mac Python trusts nothing without it), else the system's."""
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _urlopen(req, timeout=60):             # a test points SOURCE at file:// urls, which the same opener serves
    opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=_ssl_context()))
    return opener.open(req, timeout=timeout)


def url_of(set_name):
    return SOURCE + ('infrared/RAW.zip' if set_name == 'infrared' else 'raman/%s.zip' % set_name)


def store_dir():
    return os.environ.get('PXRD_RRUFF_STORE') or os.path.join(P.cache_dir(), 'rruff')


# ----------------------------------------------------------------------------- one member of a RRUFF zip

_SUB = re.compile(r'_([\d.\-+x]+)_')
_SUP = re.compile(r'\^([^^]*)\^')


def plain_chem(text):
    """RRUFF's 'Pb_2_SnInBiS_7_' / 'Fe^2+^' / '[box]' markup -> 'Pb2SnInBiS7', 'Fe2+', '□' (the window formats it by the rule)."""
    t = (text or '').replace('[box]', '□')
    t = _SUB.sub(lambda m: m.group(1), t)
    return _SUP.sub(lambda m: m.group(1), t)


def parse_member(text):
    """One RRUFF text file -> (header dict, x, y). Header lines are '##KEY=value'; data lines 'x, y'."""
    head, x, y = {}, [], []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith('##'):
            k, _, v = s[2:].partition('=')
            head[k.strip().upper()] = v.strip()
            continue
        a, sep, b = s.partition(',')
        if not sep:
            continue
        try:
            xv, yv = float(a), float(b)
        except ValueError:
            continue
        if xv != xv or yv != yv or abs(xv) == float('inf') or abs(yv) == float('inf'):
            continue                                            # a NaN / inf row: no point of the curve
        x.append(xv); y.append(yv)
    return head, x, y


_NAME = re.compile(r'^(?P<name>[^_]+)__(?P<id>[RX]\d{6}(?:-\d+)?)__')


def member_meta(member, head, set_name):
    """What the index keeps of one spectrum."""
    tech, quality, orient = SETS.get(set_name, ('raman', '', ''))
    m = _NAME.match(os.path.basename(member))
    name = head.get('NAMES') or (m.group('name') if m else '')
    rid = head.get('RRUFFID') or (m.group('id') if m else '')
    ft = (head.get('FILETYPE') or '').lower()
    kind = 'raw' if 'raw' in ft else 'processed'
    laser = re.sub(r'\s*nm$', '', head.get('RAMAN WAVELENGTH') or head.get('LASER_WAVELENGTH') or '').strip()
    if not re.fullmatch(r'\d+(\.\d+)?', laser):
        fields = os.path.basename(member).split('__')          # 'Quartz__R040031__Raman__532__…': the file name says it too
        laser = fields[3] if len(fields) > 3 and re.fullmatch(r'\d+(\.\d+)?', fields[3]) else ''
    if laser.endswith('.0'):
        laser = laser[:-2]
    return {'name': name.replace('_', ' ').strip(), 'id': rid, 'kind': kind, 'laser': laser, 'quality': quality, 'orient': orient, 'technique': tech,
            'chem': plain_chem(head.get('IDEAL CHEMISTRY', ''))[:120], 'locality': head.get('LOCALITY', '')[:160], 'source': head.get('SOURCE', '')[:80],
            'url': head.get('URL', '')[:120], 'set': set_name}


# ----------------------------------------------------------------------------- the store

class Store(object):
    """The fetched spectra: `n`, `folder`, `entries()`, `minerals()`, `xy(i)`, `meta(i)` — the shape the window reads
    (omnic_lib.Library has the same)."""

    def __init__(self, folder):
        self.folder = folder
        with open(os.path.join(folder, 'index.json'), encoding='utf-8') as f:
            self.index = json.load(f)
        self.spectra = self.index['spectra']
        self.n = len(self.spectra)
        self.array = os.path.join(folder, self.index.get('array') or 'spectra.f32')
        self._f = open(self.array, 'rb')
        self._mm = mmap.mmap(self._f.fileno(), 0, access=mmap.ACCESS_READ) if self.n and os.path.getsize(self.array) else None

    def close(self):
        """The array file and its mapping let go (a rebuild replaces them; Windows cannot replace an open file)."""
        try:
            if self._mm is not None:
                self._mm.close()
        finally:
            try:
                self._f.close()
            except Exception:
                pass

    def meta(self, i):
        return self.spectra[i]

    def xy(self, i):
        s = self.spectra[i]
        off, npts = s['off'], s['npts']
        if self._mm is None or self._mm.closed:
            raise ValueError('the RRUFF store was rebuilt — ask again')
        vals = struct.unpack_from('<%df' % (2 * npts), self._mm, off)
        return list(vals[:npts]), list(vals[npts:])

    def entries(self):
        return [(i, s['name'], s['id'], s['kind'], s['laser']) for i, s in enumerate(self.spectra)]

    def minerals(self):
        """{mineral: [(index, id, kind, laser)]} — each mineral's spectra best first (`rank`), by name."""
        by = {}
        for i, s in enumerate(self.spectra):
            by.setdefault(s['name'], []).append(i)
        return {m: [(i, self.spectra[i]['id'], self.spectra[i]['kind'], self.spectra[i]['laser']) for i in sorted(v, key=lambda i: rank(self.spectra[i]))]
                for m, v in sorted(by.items(), key=lambda kv: kv[0].lower())}


def rank(meta):
    """The order a mineral's spectra are offered in: processed before raw, the better rated first, unoriented before
    oriented (a powder is unoriented), 532 nm first, Raman before infrared; then by id."""
    return (meta.get('technique') != 'raman', meta.get('kind') != 'processed', QUALITY_RANK.get(meta.get('quality', ''), 5),
            meta.get('orient') == 'oriented', _laser_rank(meta.get('laser')), meta.get('id', ''))


def _laser_rank(laser):
    try:
        return LASER_RANK.get(int(round(float(laser))), 4)
    except (TypeError, ValueError):
        return 5


class Union(object):
    """Several libraries as one: the fetched store first, an OMNIC copy after; indices run on from one to the next."""

    def __init__(self, libs):
        self.libs = [l for l in libs if l is not None and l.n]
        self.base = []
        n = 0
        for l in self.libs:
            self.base.append(n); n += l.n
        self.n = n
        self.folder = ' + '.join(l.folder for l in self.libs)

    def _at(self, i):
        if not 0 <= i < self.n:
            raise ValueError('the library holds %d spectra; there is no number %d' % (self.n, i + 1))
        for l, b in reversed(list(zip(self.libs, self.base))):
            if i >= b:
                return l, i - b
        raise ValueError('no spectrum %d' % i)

    def xy(self, i):
        l, j = self._at(i); return l.xy(j)

    def meta(self, i):
        l, j = self._at(i); return l.meta(j)

    def entries(self):
        return [(i + b, name, rid, kind, laser) for l, b in zip(self.libs, self.base) for i, name, rid, kind, laser in l.entries()]

    def minerals(self):
        by = {}
        for l, b in zip(self.libs, self.base):
            for m, v in l.minerals().items():
                by.setdefault(m, []).extend((i + b, rid, kind, laser) for i, rid, kind, laser in v)
        return {m: sorted(v, key=lambda t: rank(self.meta(t[0]))) for m, v in sorted(by.items(), key=lambda kv: kv[0].lower())}


STRONG_SHARE = 0.05             # of the strongest band: a band of a reference spectrum counted at all (one number for the tool, the route, the line)
LATTICE = 150.0                 # cm⁻¹: below this a Raman band is a lattice mode of any mineral


def bands_of(x, y, lattice=LATTICE, share=STRONG_SHARE, n=12):
    """The bands of a reference spectrum -> [(pos, height)] by position: `spectrum.find_peaks` on the floored curve,
    positions at or above `lattice`, heights at or above `share` of the strongest, the strongest `n`. The ONE reading of
    'a strong band' for the windows tool, the window's overlay ticks and the manuscript line."""
    from pxrd_review import spectrum as SPM
    try:
        pk = SPM.find_peaks(x, y)
    except Exception:
        return []
    pk = [(p['pos'], p['height']) for p in pk if p['pos'] >= lattice and p['height'] > 0]
    if not pk:
        return []
    top = max(h for _p, h in pk)
    pk = sorted((t for t in pk if t[1] >= share * top), key=lambda t: -t[1])
    return sorted(pk if n is None else pk[:n])


def by_species(lib):
    """{mindat._norm(mineral): [(index, meta)] best first (`rank`)} over a library or union — the map the species list,
    the manuscript line and the window share. An OMNIC meta has blank quality / orientation: callers tolerate blanks."""
    from pxrd_review import mindat as M
    out = {}
    if lib is None:
        return out
    for m, v in lib.minerals().items():
        out.setdefault(M._norm(m), []).extend((i, lib.meta(i)) for i, _rid, _kind, _laser in v)
    for k in out:
        out[k].sort(key=lambda t: rank(t[1]))
    return out


_STORE = {}


def open_store(folder=None):
    """The store under `folder` (default `store_dir()`), opened once per index stamp; None when there is none."""
    folder = folder or store_dir()
    idx = os.path.join(folder, 'index.json')
    try:
        stamp = os.stat(idx).st_mtime_ns
    except OSError:
        return None
    hit = _STORE.get(folder)
    if hit and hit[0] == stamp:
        return hit[1]
    try:
        st = Store(folder)
    except (OSError, ValueError, KeyError):
        return None
    close_stores(); _STORE[folder] = (stamp, st)
    return st


def close_stores():
    """Every opened store closed and forgotten (before a rebuild or a removal)."""
    for _stamp, st in list(_STORE.values()):
        st.close()
    _STORE.clear()


def libraries(near=None):
    """Everything on this machine as one library: the fetched store, then a Thermo OMNIC copy where one is found;
    None when there is neither."""
    from pxrd_review import omnic_lib as OL
    libs = [open_store()]
    folder = OL.find_library(near)
    if folder:
        try:
            libs.append(OL.open_library(folder))
        except ValueError:
            pass
    u = Union(libs)
    return u if u.n else None


def status(folder=None):
    """What the store holds -> {'folder', 'built', 'n', 'sets', 'raw', 'minerals', 'bytes'} or None."""
    st = open_store(folder)
    if st is None:
        return None
    ix = st.index
    try:
        size = os.path.getsize(st.array)
    except OSError:
        size = 0
    return {'folder': st.folder, 'built': ix.get('built', ''), 'n': st.n, 'sets': ix.get('sets', []), 'raw': bool(ix.get('raw')),
            'minerals': len({s['name'] for s in st.spectra}), 'bytes': size, 'citation': CITATION}


# ----------------------------------------------------------------------------- the fetch

def _progress(**kw):
    PROGRESS.update(kw)


def download(url, path, progress=None):
    """`url` streamed to `path` (a .part file renamed when complete); the response's size reported as it goes."""
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    part = path + '.part'
    with _urlopen(req, timeout=60) as r, open(part, 'wb') as out:
        total = int(r.headers.get('Content-Length') or 0)
        done = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            out.write(chunk); done += len(chunk)
            if progress:
                progress(done=done, total=total)
    os.replace(part, path)
    return path


def build(zips, out_dir, raw=False, progress=None):
    """The zips -> out_dir/index.json + out_dir/spectra.f32. Processed spectra always; RAW with `raw`."""
    os.makedirs(out_dir, exist_ok=True)
    clean_parts(out_dir)
    spectra = []
    stamp = time.strftime('%Y%m%d-%H%M%S')
    array = 'spectra-%s.f32' % stamp                          # a NEW array file each build: the index swap below is then one atomic step
    tmp = os.path.join(out_dir, array + '.part')
    try:
        with open(tmp, 'wb') as out:
            off = 0
            for set_name, zpath in zips:
                try:
                    z = zipfile.ZipFile(zpath)
                except zipfile.BadZipFile as ex:
                    raise ValueError('%s is not a zip file (%s) — fetch again' % (os.path.basename(zpath), ex))
                with z:
                    members = [m for m in z.namelist() if m.lower().endswith('.txt')]
                    for k, member in enumerate(members):
                        head, x, y = parse_member(z.read(member).decode('utf-8', 'replace'))
                        if len(x) < 5:
                            continue
                        meta = member_meta(member, head, set_name)
                        if meta['kind'] == 'raw' and not raw and meta['technique'] == 'raman':
                            continue                           # RRUFF's infrared collection is RAW only: always kept
                        if x[0] > x[-1]:
                            x.reverse(); y.reverse()
                        data = struct.pack('<%df' % (2 * len(x)), *(x + y))
                        out.write(data)
                        meta.update(off=off, npts=len(x), x0=round(x[0], 2), x1=round(x[-1], 2))
                        spectra.append(meta); off += len(data)
                        if progress and k % 200 == 0:
                            progress(stage='reading', set=set_name, spectra=len(spectra), done=k, total=len(members))
        index = {'source': SOURCE, 'citation': CITATION, 'built': time.strftime('%Y-%m-%d %H:%M'), 'sets': [s for s, _ in zips], 'raw': bool(raw),
                 'array': array, 'spectra': spectra}
        with open(os.path.join(out_dir, 'index.json.part'), 'w', encoding='utf-8') as f:
            json.dump(index, f)
        os.replace(tmp, os.path.join(out_dir, array))
        close_stores()                                         # the store in use let go before its index is replaced (Windows: an open file cannot be replaced)
        os.replace(os.path.join(out_dir, 'index.json.part'), os.path.join(out_dir, 'index.json'))
    except BaseException:
        clean_parts(out_dir)
        raise
    for fn in os.listdir(out_dir):                             # the arrays of earlier builds
        if fn.endswith('.f32') and fn != array:
            try:
                os.remove(os.path.join(out_dir, fn))
            except OSError:
                pass
    return len(spectra)


def clean_parts(out_dir):
    """Half-written files of a build that did not finish."""
    try:
        for fn in os.listdir(out_dir):
            if fn.endswith('.part'):
                try:
                    os.remove(os.path.join(out_dir, fn))
                except OSError:
                    pass
    except OSError:
        pass


def fetch(sets=DEFAULT_SETS, raw=False, ir=False, keep_zips=False, out_dir=None, log=print):
    """Download the sets and build the store -> the number of spectra. PROGRESS says where it stands."""
    out_dir = out_dir or store_dir()
    sets = [str(s) for s in sets] + (['infrared'] if ir and 'infrared' not in sets else [])
    PROGRESS.clear(); _progress(stage='downloading', sets=sets, finished=False, error='', missing=[])
    zips, downloaded = [], []
    try:
        bad = [s for s in sets if s not in SETS]
        if bad:
            raise ValueError('no such RRUFF set: %s (one of %s)' % (', '.join(bad), ', '.join(SETS)))
        zdir = os.path.join(out_dir, 'zips'); os.makedirs(zdir, exist_ok=True)
        for s in sets:
            path = os.path.join(zdir, s.replace('/', '_') + '.zip')
            _progress(set=s, done=0, total=0)
            if os.path.isfile(path) and zipfile.is_zipfile(path):             # left by --keep-zips: not downloaded twice
                if log:
                    log('%s already here' % os.path.basename(path))
                zips.append((s, path)); continue
            if log:
                log('downloading %s …' % url_of(s))
            downloaded.append(path)
            try:
                download(url_of(s), path, progress=_progress)
            except urllib.error.HTTPError as ex:
                if ex.code == 404 and s not in REQUIRED:                     # a set RRUFF does not publish (today): said, the rest fetched
                    PROGRESS['missing'].append(s)
                    if log:
                        log('%s: not on rruff.net (404) — skipped' % s)
                    continue
                raise ValueError('%s could not be downloaded (HTTP %d %s)' % (url_of(s), ex.code, ex.reason))
            except (urllib.error.URLError, OSError) as ex:
                raise ValueError('%s could not be downloaded (%s)' % (url_of(s), getattr(ex, 'reason', ex)))
            zips.append((s, path))
        if not zips:
            raise ValueError('none of the sets asked for is on rruff.net: %s' % ', '.join(sets))
        _progress(stage='reading', done=0, total=0)
        n = build(zips, out_dir, raw=raw, progress=_progress)
        _progress(stage='done', spectra=n, finished=True)
        if log:
            log('%d spectra in %s' % (n, out_dir))
        return n
    except Exception as ex:
        _progress(stage='failed', error=str(ex), finished=True)
        raise
    finally:
        if not keep_zips:                                     # only what THIS run downloaded: a zip an earlier --keep-zips run left stays
            for path in downloaded:
                for fn in (path, path + '.part'):
                    try:
                        os.remove(fn)
                    except OSError:
                        pass
            try:
                os.rmdir(os.path.join(out_dir, 'zips'))
            except OSError:
                pass


_LOCK = threading.Lock()


def fetch_in_background(**kw):
    """The fetch on a thread (the window's button); PROGRESS is polled. False when one is already running."""
    with _LOCK:
        if PROGRESS and not PROGRESS.get('finished', True):
            return False
        PROGRESS.clear(); PROGRESS.update(stage='starting', finished=False, error='')     # claimed here, under the lock: a second click sees it
        def run():
            try:
                fetch(log=None, **kw)
            except Exception:
                pass                                           # PROGRESS carries the error
        threading.Thread(target=run, daemon=True).start()
    return True


def remove(out_dir=None):
    out_dir = out_dir or store_dir()
    close_stores()
    shutil.rmtree(out_dir, ignore_errors=True)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog='pxrd rruff', description=__doc__.split('\n\n')[0])
    ap.add_argument('--fetch', action='store_true', help='download the Raman collection from rruff.net and build the store')
    ap.add_argument('--sets', nargs='+', help='the sets to fetch (default: every Raman quality, oriented and unoriented): ' + ', '.join(SETS))
    ap.add_argument('--raw', action='store_true', help='keep the RAW spectra beside the processed ones')
    ap.add_argument('--ir', action='store_true', help='the infrared collection too')
    ap.add_argument('--keep-zips', action='store_true', help='keep the downloaded zips under the store')
    ap.add_argument('--dir', help='the store folder (default: the cache, or $PXRD_RRUFF_STORE)')
    ap.add_argument('--status', action='store_true', help='what the store holds')
    ap.add_argument('--remove', action='store_true', help='delete the store')
    a = ap.parse_args(argv)
    if a.remove:
        remove(a.dir); print('removed'); return 0
    if a.fetch:
        n = fetch(sets=a.sets or DEFAULT_SETS, raw=a.raw, ir=a.ir, keep_zips=a.keep_zips, out_dir=a.dir)
        print('cite: ' + CITATION)
        return 0 if n else 1
    st = status(a.dir)
    if not st:
        print('no RRUFF store (pxrd rruff --fetch builds one; a Thermo OMNIC copy beside a folder is read as well)'); return 1
    print('%d spectra of %d minerals in %s (built %s; sets: %s%s; %.0f MB)' % (st['n'], st['minerals'], st['folder'], st['built'], ', '.join(st['sets']), ' + raw' if st['raw'] else '', st['bytes'] / 1e6))
    print('cite: ' + st['citation'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
