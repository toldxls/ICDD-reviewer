"""A Thermo OMNIC spectral library (RRUFFLib.lbd + RRUFFLib.lbt — the RRUFF Raman library as Thermo shipped it)
read in place: the names, one grid, a spectrum decoded on request. Private data: the library is found on this
machine ($PXRD_RRUFF_DIR, a RRUFF folder beside the open folder or above it, ~/RRUFF) and is never copied.

The .lbd: a text header of the length its first token says — tokens (lines end in \\r\\n or \\x00\\n): length, company,
library, version, '000', count, record size, …, points, first x, last x — then fixed records: `points` float32, then
a three-byte pointer into the .lbt (b0 + 256·b2 + 65536·b1), then padding. The .lbt: a 1024-byte header, then one
record per spectrum: a kind byte + \\x01\\xff + the name in a 256-character field (some kinds close it with \\x17
inside the field) and the record's numbers; a few older records write the name as a length-prefixed string instead.
"""
import os, re, struct, functools, collections

_ID = re.compile(r'[RX]\d{6}')
_LASER = re.compile(r'(\d{3})\s?nm|_(\d{3})(?:_|[a-z])')


class Library(object):
    """The library opened: `names` in record order, `x` the one grid, `spectrum(i)` -> [y]."""

    def __init__(self, folder):
        self.folder = folder
        self._lbd = open(os.path.join(folder, 'RRUFFLib.lbd'), 'rb').read()
        lbt = open(os.path.join(folder, 'RRUFFLib.lbt'), 'rb').read()
        toks = [t.strip().decode('latin-1') for t in re.split(rb'[\r\n\x00]+', self._lbd[:4000]) if t.strip()]
        self._hlen = int(toks[0]); self.n = int(toks[5]); self._rec = int(toks[6]); self.npts = int(toks[13])
        x0, x1 = float(toks[14]), float(toks[15])
        if self._hlen + self.n * self._rec != len(self._lbd) or self._rec < 4 * self.npts:
            raise ValueError('the .lbd header (%d records of %d bytes, %d points, header %d) does not add up to its size %d' % (self.n, self._rec, self.npts, self._hlen, len(self._lbd)))
        dx = (x1 - x0) / (self.npts - 1)
        self.x = [x0 + k * dx for k in range(self.npts)]
        found = {m.start(1) - 3: m.group(1) for m in re.finditer(rb'[\x00-\xff]\x01\xff([ -~\x80-\xff\x17]{256})', lbt)}
        spans = sorted((p + 3, p + 259) for p in found)
        for m in re.finditer(rb'([A-Z][A-Za-z\-\(\)\. ]{2,60}?R\d{6}[A-Za-z0-9_]{0,24})', lbt):
            p = m.start()
            if lbt[p - 1] == len(m.group(1)) and not any(a <= p < b for a, b in spans):
                found[p - 3] = m.group(1)
        names = {p: re.sub(r'[\x00-\x1f]', '', v.decode('latin-1')).strip() for p, v in found.items()}
        if len(names) != self.n:
            raise ValueError('the .lbt holds %d names for %d spectra — not the record layout this reader knows' % (len(names), self.n))
        order = sorted(names); self.names = []; self.missed = 0
        for i in range(self.n):
            b = self._lbd[self._hlen + i * self._rec + 4 * self.npts: self._hlen + i * self._rec + 4 * self.npts + 3]
            ptr = b[0] + 256 * b[2] + 65536 * b[1]
            name = names.get(ptr)
            if name is None:
                self.missed += 1; name = names[order[i]]
            self.names.append(name)

    def spectrum(self, i):
        if not 0 <= i < self.n:
            raise ValueError('the library holds %d spectra; there is no number %d' % (self.n, i + 1))
        r = self._lbd[self._hlen + i * self._rec: self._hlen + i * self._rec + 4 * self.npts]
        return list(struct.unpack('<%df' % self.npts, r))

    def xy(self, i):
        """(x, y) of one record — the shape the fetched store (pxrd_review.rruff.Store) has."""
        return self.x, self.spectrum(i)

    def meta(self, i):
        mineral, rid, kind = split_name(self.names[i])
        return {'name': mineral, 'id': rid, 'kind': kind or 'processed', 'laser': laser_of(self.names[i]), 'quality': '', 'orient': '',
                'technique': 'raman', 'chem': '', 'locality': '', 'source': 'a Thermo OMNIC copy of the RRUFF library (2007)', 'url': '', 'set': 'omnic'}

    def entries(self):
        """[(index, mineral, id, kind, laser)] for every record with a RRUFF id."""
        out = []
        for i, name in enumerate(self.names):
            mineral, rid, kind = split_name(name)
            if rid:
                out.append((i, mineral, rid, kind, laser_of(name)))
        return out

    @functools.lru_cache(maxsize=1)
    def minerals(self):
        """{mineral name: [(index, id, kind, laser)]} — processed first, then clean / corrected, raw last — sorted by name."""
        rank = {'processed': 0, 'clean': 1, 'corrected': 2, 'raw': 3}
        by = collections.defaultdict(list)
        for i, mineral, rid, kind, laser in self.entries():
            by[mineral].append((i, rid, kind, laser))
        return {m: sorted(v, key=lambda t: (rank.get(t[2], 9), t[1])) for m, v in sorted(by.items(), key=lambda kv: kv[0].lower())}


def split_name(name):
    """'Whiteite-(CaFeMg)R060912_785processed' -> ('Whiteite-(CaFeMg)', 'R060912', 'processed')."""
    m = _ID.search(name)
    if not m:
        return name.strip(), '', ''
    mineral = name[:m.start()].strip().strip('_').strip()
    tail = name[m.end():].lower()
    kind = next((k for k in ('processed', 'clean', 'corrected', 'raw') if k in tail or (k == 'processed' and 'proc' in tail) or (k == 'raw' and tail.endswith('ra'))), '')
    return mineral, m.group(0), kind


def laser_of(name):
    """The laser wavelength a record's name carries ('…_532processed', '…_785nm_clean'), or ''."""
    m = _LASER.search(name[name.find('R0'):] if 'R0' in name else name)
    return (m.group(1) or m.group(2)) if m else ''


def is_library(folder):
    """Does `folder` hold the OMNIC pair RRUFFLib.lbd + RRUFFLib.lbt?"""
    return bool(folder) and all(os.path.isfile(os.path.join(folder, fn)) for fn in ('RRUFFLib.lbd', 'RRUFFLib.lbt'))


def _remember_file():
    from pxrd_review import paths as P
    return REMEMBER or os.path.join(P.cache_dir(), 'rruff_dir.txt')


REMEMBER = None                 # the file the library's folder is remembered in (None: <cache_dir>/rruff_dir.txt; a test points it elsewhere)
SEARCH_ROOTS = ('~/Desktop', '~/Documents', '~/Downloads', '~')     # looked through two levels deep for a folder named RRUFF
SEARCH_MAX = 400                # folders listed at most in that search: it must stay instant


def remembered():
    """The folder a library was last found in, if it still holds one."""
    try:
        with open(_remember_file(), encoding='utf-8') as f:
            folder = f.read().strip()
    except OSError:
        return None
    return folder if is_library(folder) else None


def _is_temp(folder):
    import tempfile
    t = os.path.realpath(tempfile.gettempdir()); f = os.path.realpath(folder)
    return f == t or f.startswith(t + os.sep)


def remember(folder):
    """Keep the library's folder for every later start, whatever folder is open then (never a temp folder: a test's)."""
    if not folder or (REMEMBER is None and _is_temp(folder)):
        return
    try:
        path = _remember_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(os.path.abspath(folder) + '\n')
    except OSError:
        pass


def _search():
    """A folder named RRUFF holding the pair, up to two levels under the usual places — at most SEARCH_MAX folders listed."""
    seen = 0
    for root in SEARCH_ROOTS:
        root = os.path.expanduser(root)
        try:
            first = sorted(os.listdir(root))
        except OSError:
            continue
        for a in first:
            if a.startswith('.'):
                continue
            pa = os.path.join(root, a)
            if a.lower() == 'rruff' and is_library(pa):
                return pa
            if not os.path.isdir(pa):
                continue
            seen += 1
            if seen > SEARCH_MAX:
                return None
            try:
                second = os.listdir(pa)
            except OSError:
                continue
            for b in second:
                if b.lower() == 'rruff' and is_library(os.path.join(pa, b)):
                    return os.path.join(pa, b)
    return None


def find_library(near=None):
    """The folder holding RRUFFLib.lbd + .lbt: $PXRD_RRUFF_DIR, else the folder it was found in before, else 'RRUFF' beside
    `near` or any of its parents (four levels), else ~/RRUFF, else a RRUFF folder up to two levels under Desktop / Documents /
    Downloads / home. Once found anywhere it is remembered, so it is there whatever folder is opened next. None when there is none."""
    env = os.environ.get('PXRD_RRUFF_DIR')
    if env and is_library(env):
        return env                                               # a folder named that is not a library: the other places are still tried
    hit = remembered()
    if hit:
        return hit
    cands = []
    if near:
        p = os.path.abspath(near)
        for _k in range(5):
            cands.append(os.path.join(p, 'RRUFF'))
            parent = os.path.dirname(p)
            if parent == p:
                break
            p = parent
    cands.append(os.path.join(os.path.expanduser('~'), 'RRUFF'))
    found = next((c for c in cands if is_library(c)), None)
    if not found and _SEARCHED[0] != tuple(SEARCH_ROOTS):        # the two-level walk once per process (per set of roots): not on every request of a window
        found = _search(); _SEARCHED[0] = tuple(SEARCH_ROOTS)
    if found:
        remember(found)
    return found


_SEARCHED = [None]                  # the roots `_search` has walked in this process without finding a library (a found one is remembered instead)


def set_library(folder):
    """A folder named by hand (the window's 'RRUFF library…'): the folder itself, or its RRUFF subfolder -> the folder kept;
    ValueError says what is wrong."""
    typed = (folder or '').strip().strip('"').strip("'")
    if not typed:
        raise ValueError('no such folder: nothing typed')
    folder = os.path.abspath(os.path.expanduser(typed))
    if not os.path.isdir(folder):
        raise ValueError('no such folder: %s' % folder)
    for c in (folder, os.path.join(folder, 'RRUFF')):
        if is_library(c):
            remember(c); _SEARCHED[0] = None
            return c
    raise ValueError('%s holds no RRUFFLib.lbd + RRUFFLib.lbt (the Thermo OMNIC library pair)' % folder)


_OPEN = {}


def open_library(folder):
    """A Library, opened once per folder and file state."""
    try:
        stamp = tuple(os.stat(os.path.join(folder, fn)).st_mtime_ns for fn in ('RRUFFLib.lbd', 'RRUFFLib.lbt'))
    except OSError:
        raise ValueError('no RRUFF library in %s' % folder)
    hit = _OPEN.get(folder)
    if hit and hit[0] == stamp:
        return hit[1]
    lib = Library(folder)
    _OPEN.clear(); _OPEN[folder] = (stamp, lib)
    return lib


def read_omnic(folder):
    """[(name, x, y)] for every record — what tools/rruff_windows.py walks."""
    lib = Library(folder)
    if lib.missed:
        print('note: %d of %d text pointers matched no record; those names were taken by order' % (lib.missed, lib.n))
    return [(name, lib.x, lib.spectrum(i)) for i, name in enumerate(lib.names)]
