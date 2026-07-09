"""Isolate MuPDF (PyMuPDF / fitz) page operations in worker subprocesses.

A malformed embedded image — e.g. a JPEG-2000 (JPX) image that segfaults libmupdf's
decoder — crashes the whole interpreter with an *uncatchable* SIGSEGV, taking the Flask
GUI server down with it (a `try/except` cannot catch a native fault). Every operation
that interprets a page's content stream (`get_text`, `search_for`, `get_pixmap`) can hit
such an image, so they all run here, in a pooled subprocess. If a worker segfaults, the
future reports it, the request degrades gracefully, and the server keeps running. Workers
persist (one `fitz` import each), so page navigation stays responsive.
"""
import threading
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, TimeoutError as _Timeout
from concurrent.futures.process import BrokenProcessPool

_ctx = mp.get_context('spawn')          # spawn is the safe context on macOS (no fork-in-threads)
_pool = None
_lock = threading.Lock()


def _pool_get():
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(max_workers=2, mp_context=_ctx)
    return _pool


def _kill_pool(pool):
    """Tear a pool down HARD. shutdown() alone cannot stop a worker wedged inside
    native MuPDF code (it only stops feeding the queue), so the stuck process would
    leak — and keep the CPU — behind the rebuilt pool. Kill the workers outright."""
    try:
        pool.shutdown(wait=False, cancel_futures=True)
    except Exception:
        pass
    try:
        for p in (getattr(pool, '_processes', None) or {}).values():
            try:
                p.kill()
            except Exception:
                pass
    except Exception:
        pass


def run(fn, *args, default=None, timeout=40):
    """Run `fn(*args)` in the worker pool; return its result, or `default` if the worker
    crashed (native segfault), timed out, or raised. A crash poisons the pool, so it is
    torn down and rebuilt on the next call."""
    global _pool
    with _lock:
        pool = _pool_get()
    try:
        return pool.submit(fn, *args).result(timeout=timeout)
    except (BrokenProcessPool, _Timeout):
        with _lock:                     # worker died / hung -> the pool is unusable; rebuild
            if _pool is not None:
                _kill_pool(_pool)
            _pool = None
        return default
    except Exception:
        return default                  # ordinary fitz error -> graceful, pool still healthy


def shutdown():
    global _pool
    with _lock:
        if _pool is not None:
            _kill_pool(_pool)
            _pool = None


# --- the isolated operations (each (re)imports fitz inside the worker) -----------------
def words(pdf, n):
    """{w, h, words:[[x0,y0,x1,y1,text], …]} for page n, or None for an out-of-range page."""
    import fitz
    with fitz.open(pdf) as doc:
        if not (0 <= n < doc.page_count):
            return None
        page = doc[n]
        r = page.rect
        return {'w': r.width, 'h': r.height,
                'words': [[round(w[0], 1), round(w[1], 1), round(w[2], 1), round(w[3], 1), w[4]]
                          for w in page.get_text('words')]}


def page_png(pdf, n, terms):
    """Full page n rendered at 2x with `terms` highlighted; PNG bytes, or None if out of range."""
    import fitz
    with fitz.open(pdf) as doc:
        if not (0 <= n < doc.page_count):
            return None
        page = doc[n]
        for t in (terms or []):
            for rect in page.search_for(t):
                page.add_highlight_annot(rect)
        return page.get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes('png')


def region_png(pdf, n, terms):
    """A 3x zoomed crop of page n framing the `terms` hits (a quarter-ish of the page); PNG
    bytes, or None if out of range. Mirrors the original api_pdf_region geometry."""
    import fitz
    with fitz.open(pdf) as doc:
        if not (0 <= n < doc.page_count):
            return None
        page = doc[n]
        rects = []
        for t in (terms or []):
            rects += list(page.search_for(t))
        pr = page.rect
        fw, fh = pr.width * 0.52, pr.height * 0.26
        if rects:
            x0 = min(r.x0 for r in rects); y0 = min(r.y0 for r in rects)
            x1 = max(r.x1 for r in rects); y1 = max(r.y1 for r in rects)
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            halfw = max(fw / 2, (x1 - x0) / 2 + 12)
            halfh = max(fh / 2, (y1 - y0) / 2 + 12)
        else:
            cx, cy, halfw, halfh = pr.width / 2, pr.height * 0.28, fw / 2, fh / 2
        cx = min(max(cx, pr.x0 + halfw), pr.x1 - halfw)
        cy = min(max(cy, pr.y0 + halfh), pr.y1 - halfh)
        clip = fitz.Rect(cx - halfw, cy - halfh, cx + halfw, cy + halfh) & pr
        for t in (terms or []):
            for r in page.search_for(t):
                page.add_highlight_annot(r)
        return page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=clip).tobytes('png')


def scan(pdf, terms):
    """[n_pages, best_evidence_page] — the page with the most hits for `terms`."""
    import fitz
    best_pg, best_hits, n = 0, -1, 0
    with fitz.open(pdf) as doc:
        n = doc.page_count
        if terms:
            for i in range(n):
                hits = sum(len(doc[i].search_for(t)) for t in terms)
                if hits > best_hits:
                    best_hits, best_pg = hits, i
    return [n, (best_pg if best_hits > 0 else 0)]


def sizes(pdf):
    """[[w, h], …] point size of every page — lets the UI reserve each page slot's true height
    so lazy-loaded images cause no layout shift (accurate scroll-to-hit). No rendering."""
    import fitz
    with fitz.open(pdf) as doc:
        return [[round(p.rect.width, 1), round(p.rect.height, 1)] for p in doc]


def _selftest_segfault(*_):
    """Deliberately segfault a worker (null deref) — used only to verify crash isolation.
    Never called in normal operation."""
    import ctypes
    ctypes.string_at(0)


def search(pdf, q):
    """Locate query string q across all pages. Returns
        {'pages': [{page, count}, …],            # per-page tally (legacy shape, for the search box)
         'hits':  [{page, rect:[x0,y0,x1,y1]}…], # every individual hit, in reading order
         'sizes': {page: [w, h], …}}             # point size of each page that has a hit
    so the UI can step hit-to-hit and place a flash box in page-% coordinates."""
    import fitz
    pages, hits, sizes = [], [], {}
    with fitz.open(pdf) as doc:
        for i in range(doc.page_count):
            rects = doc[i].search_for(q)
            if rects:
                pages.append({'page': i, 'count': len(rects)})
                r = doc[i].rect
                sizes[i] = [round(r.width, 1), round(r.height, 1)]
                for q_ in sorted(rects, key=lambda b: (round(b.y0, 1), b.x0)):
                    hits.append({'page': i, 'rect': [round(q_.x0, 1), round(q_.y0, 1),
                                                     round(q_.x1, 1), round(q_.y1, 1)]})
    return {'pages': pages, 'hits': hits, 'sizes': sizes}
