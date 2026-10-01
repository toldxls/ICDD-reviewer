"""A spectrum read off a FIGURE: the curve of a plot in a paper's .pdf page, an image of a manuscript .docx, or an
image file, turned back into wavenumber / intensity pairs.

Most papers give no data — at best a figure. What can be had from one is the SHAPE of the curve: where it has a maximum,
a shoulder, nothing. That is enough to set the bands a text states beside the spectrum they were read from, and it is
all this is for: a traced curve is the tool's reading of a picture, to about a pixel (a figure 900 pixels wide over
100-4000 cm-1 is 4 cm-1 a pixel), its intensities relative, its widths not to be fitted. Nothing here is a finding.

    figure(path, index)            a page of a .pdf (rendered), an image of a .docx, an image file  -> Figure
    frames(fig)                    the plot frames on it (the axes of each plot), largest first
    ticks(fig, box)                the numbers printed under a frame, where the .pdf keeps them as text -> [(pixel x, value)]
    tick_marks(fig, box)           the evenly spaced tick strokes of its x axis -> [pixel x], each at its fitted place
    trace_pixels(fig, box, ...)    the curve inside a frame, in pixels (no axis needed yet)
    digitize(fig, box, x1, v1, x2, v2, ...)   … as a spectrum -> {'x', 'y', 'trace', 'how', 'cm_per_px', 'coverage', 'peaks'}

Where the accuracy is (measured on figures set against the data they were drawn from): the trace itself is good to about
half a pixel; what costs more is the AXIS — a mark put on a tick by hand, two pixels off, doubles to quadruples the
error. Hence the ticks are found (the evenly spaced strokes on the axis) and a mark snaps to them.
    features(x, y) / stated_on_curve(...)     where the traced curve has a band, and which stated bands it has none for

Two ways to the curve, the better one first:
  vector   the .pdf draws the curve as a path: its own coordinates are taken (exact to the drawing);
  raster   the pixels of the curve's colour are followed column by column — the one continuous line through the plot
           (text set inside the plot, tick marks and other curves are not continuous with it).
Pure Python but for PyMuPDF, which decodes and renders (already the tool's .pdf reader). Local: nothing leaves the machine.
"""
import os, re, math, zipfile

DPI = 200                      # a .pdf page is rendered at this, at the least
DPI_MAX = 600                  # … and at the resolution of the finest picture set on it, or 400 for a drawn (vector) plot, up to this
PIXELS_MAX = 30e6              # … as long as the page stays under this many pixels
CAPTION = re.compile(r'(?:Fig(?:ure|\.)?)\s*\d+[a-z]?[.:]?[^\n]{0,200}?(?:Raman|infrared|\bIR\b|FTIR|FT-IR)[^\n]{0,80}?spectr', re.I | re.S)
IMAGE_EXT = ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.gif')


class Figure(object):
    """An image to trace: `w`, `h`, `rgb` (3 bytes a pixel, rows top to bottom), and — for a .pdf page — the page's
    words and drawn paths in the image's pixel coordinates."""

    def __init__(self, pix, words=(), paths=(), label='', strokes=()):
        import fitz
        if pix.alpha or pix.colorspace is None or pix.colorspace.n != 3:
            pix = fitz.Pixmap(fitz.csRGB, pix)
            if pix.alpha:
                pix = fitz.Pixmap(pix, 0)
        self.pix = pix; self.w = pix.width; self.h = pix.height; self.rgb = pix.samples
        self.words = list(words); self.paths = list(paths); self.label = label
        self.strokes = list(strokes)                            # [((r, g, b), [(x, y) …])] — every stroked path of the page, with its colour
        self._gray = None

    def png(self):
        return self.pix.tobytes('png')

    def data(self):
        """The figure as plain values (what a worker process can hand back): see `from_data`."""
        return {'w': self.w, 'h': self.h, 'rgb': bytes(self.rgb), 'words': self.words, 'paths': self.paths, 'label': self.label, 'strokes': self.strokes}

    @classmethod
    def from_data(cls, d):
        import fitz
        return cls(fitz.Pixmap(fitz.csRGB, d['w'], d['h'], d['rgb'], False), d.get('words') or (), d.get('paths') or (), d.get('label') or '', d.get('strokes') or ())

    def gray(self):
        """One byte a pixel: 1 where the pixel is ink (not near-white), 0 elsewhere."""
        if self._gray is None:
            import fitz
            g = fitz.Pixmap(fitz.csGRAY, self.pix).samples
            self._gray = g.translate(bytes(1 if v < 200 else 0 for v in range(256)))
        return self._gray

    def at(self, x, y):
        i = 3 * (int(y) * self.w + int(x))
        return tuple(self.rgb[i: i + 3])


def _pdf(path, data=None):
    import fitz
    return fitz.open(stream=data, filetype='pdf') if data is not None else fitz.open(path)


def sources(path, data=None):
    """What a file offers to trace: [{'index', 'label', 'spectrum': a caption on it names a Raman / infrared spectrum}]
    — the pages of a .pdf, the images of a .docx, the one image of an image file. `data`: the file's bytes, for one
    that is held in memory (a .pdf or an image)."""
    low = path.lower()
    if low.endswith('.pdf'):
        out = []
        with _pdf(path, data) as doc:
            for n, page in enumerate(doc):
                text = page.get_text()
                m = CAPTION.search(text)
                cap = re.sub(r'\s+', ' ', text[m.start(): m.start() + 90]).strip() if m else ''
                out.append({'index': n, 'label': 'page %d%s' % (n + 1, ' — ' + cap[:70] if cap else ''), 'spectrum': bool(m)})
        return out
    if low.endswith('.docx'):
        return [{'index': k, 'label': 'image %d (%s)' % (k + 1, os.path.basename(n)), 'spectrum': False} for k, n in enumerate(_docx_images(path))]
    if low.endswith(IMAGE_EXT):
        return [{'index': 0, 'label': os.path.basename(path), 'spectrum': False}]
    raise ValueError('%s is not a .pdf, a .docx or an image' % os.path.basename(path))


def _docx_images(path):
    with zipfile.ZipFile(path) as z:
        return sorted(n for n in z.namelist() if n.startswith('word/media/') and n.lower().endswith(IMAGE_EXT + ('.emf', '.wmf')) and not n.lower().endswith(('.emf', '.wmf')))


def figure(path, index=0, dpi=None, data=None):
    """The Figure of a source: page `index` of a .pdf rendered (with its words and drawn paths), image `index` of a
    .docx, or an image file (or its bytes in `data`). A page is rendered at the resolution of the finest picture set on
    it — a figure embedded at 600 dpi was being read at 200 — and a drawn plot at 400 dpi; `dpi` fixes it."""
    import fitz
    low = (path or '').lower()
    if low.endswith(IMAGE_EXT) or (data is not None and not low.endswith('.pdf')):
        try:
            pix = fitz.Pixmap(data) if data is not None else fitz.Pixmap(path)
        except Exception:
            raise ValueError('%s could not be read as an image' % os.path.basename(path or 'the file'))
        return Figure(pix, label=os.path.basename(path or 'image'))
    if low.endswith('.docx'):
        names = _docx_images(path)
        if not 0 <= index < len(names):
            raise ValueError('%s holds %d images; there is no number %d' % (os.path.basename(path), len(names), index + 1))
        with zipfile.ZipFile(path) as z:
            blob = z.read(names[index])
        try:
            return Figure(fitz.Pixmap(blob), label='%s, image %d' % (os.path.basename(path), index + 1))
        except Exception:
            raise ValueError('image %d of %s could not be read' % (index + 1, os.path.basename(path)))
    if low.endswith('.pdf'):
        with _pdf(path, data) as doc:
            if not 0 <= index < len(doc):
                raise ValueError('%s has %d pages; there is no page %d' % (os.path.basename(path), len(doc), index + 1))
            page = doc[index]
            try:
                drawings = page.get_drawings()
            except Exception:
                drawings = []
            if dpi is None:
                dpi = DPI
                try:
                    for im in page.get_image_info():
                        bb = im.get('bbox') or (0, 0, 0, 0)
                        if bb[2] - bb[0] > 100 and im.get('width'):
                            dpi = max(dpi, 72.0 * im['width'] / (bb[2] - bb[0]))
                except Exception:
                    pass
                if sum(len(d.get('items') or []) for d in drawings) > 400:
                    dpi = max(dpi, 400)
                dpi = min(dpi, DPI_MAX, 72.0 * math.sqrt(PIXELS_MAX / max(1.0, page.rect.width * page.rect.height)))
            z = dpi / 72.0
            pix = page.get_pixmap(matrix=fitz.Matrix(z, z), alpha=False)
            words = []; paths = []; strokes = []
            if not page.rotation:                               # the words and paths of an unrotated page map onto its picture by the zoom alone
                for w in page.get_text('words'):
                    words.append((w[0] * z, w[1] * z, w[2] * z, w[3] * z, w[4]))
                try:
                    for d in drawings:
                        pts = []
                        for it in d.get('items') or []:
                            if it[0] == 'l':
                                pts += [(it[1].x * z, it[1].y * z), (it[2].x * z, it[2].y * z)]
                            elif it[0] == 'c':
                                pts += _bezier([(p.x * z, p.y * z) for p in it[1:5]])
                        if len(pts) >= 40:
                            paths.append(pts)
                        col = d.get('color')
                        if len(pts) >= 2 and col is not None:    # a stroked path: a curve may be drawn as many of them
                            strokes.append((tuple(int(round(255 * c)) for c in col[:3]), pts))
                except Exception:
                    paths = []; strokes = []
            return Figure(pix, words, paths, '%s, page %d' % (os.path.basename(path), index + 1), strokes)
    raise ValueError('%s is not a .pdf, a .docx or an image' % os.path.basename(path or ''))


def page_data(path, index=0, dpi=None, data=None):
    """`figure` for a caller that runs it in another process (the GUI keeps every MuPDF decode out of its server: a
    malformed image can take the interpreter down): Figure.data(), or {'error': message}."""
    try:
        return figure(path, index, dpi, data).data()
    except ValueError as e:
        return {'error': str(e)}


def sources_data(path, data=None):
    try:
        return {'sources': sources(path, data)}
    except ValueError as e:
        return {'error': str(e)}


def _bezier(p, n=6):
    out = []
    for k in range(n + 1):
        t = k / float(n); u = 1.0 - t
        out.append((u ** 3 * p[0][0] + 3 * u * u * t * p[1][0] + 3 * u * t * t * p[2][0] + t ** 3 * p[3][0],
                    u ** 3 * p[0][1] + 3 * u * u * t * p[1][1] + 3 * u * t * t * p[2][1] + t ** 3 * p[3][1]))
    return out


# ----------------------------------------------------------------------------- the plot's frame

def _runs(row):
    """[(start, end)] of the runs of 1 in a bytes row (gaps of up to two pixels closed)."""
    out = []; i = row.find(1)
    while i >= 0:
        j = i
        while True:
            k = row.find(0, j)
            if k < 0:
                j = len(row); break
            nxt = row.find(1, k)
            if nxt < 0 or nxt - k > 2:
                j = k; break
            j = nxt
        out.append((i, j))
        i = row.find(1, j)
    return out


def frames(fig, min_frac=0.18):
    """The plot frames of a figure, largest first: [(x0, y0, x1, y1)] in pixels — for each long horizontal line (an x
    axis) the vertical line that meets its end (the y axis) gives the height; with no vertical line the frame runs up
    to the highest ink above the axis."""
    g = fig.gray(); w, h = fig.w, fig.h
    need = max(60, int(min_frac * w))
    axes = []
    y = 0
    while y < h:
        row = g[y * w: (y + 1) * w]
        if row.count(1) >= need:
            best = max(_runs(row), key=lambda r: r[1] - r[0], default=None)
            if best and best[1] - best[0] >= need:
                # the same line a few rows thick is one axis: keep its lowest row
                if axes and y - axes[-1][0] <= 3 and abs(axes[-1][1] - best[0]) < 6 and abs(axes[-1][2] - best[1]) < 6:
                    axes[-1] = (y, best[0], best[1])
                else:
                    axes.append((y, best[0], best[1]))
        y += 1
    out = []
    for ya, xa, xb in axes:
        # a vertical line standing on either end of the axis
        top = None
        for xc in (xa, xb - 1):
            for dx in (0, 1, -1, 2, -2):
                x = xc + dx
                if not 0 <= x < w:
                    continue
                col = g[x::w][:ya + 1]
                yy = ya
                gap = 0
                while yy > 0 and (col[yy] or gap < 2):
                    gap = 0 if col[yy] else gap + 1
                    yy -= 1
                if ya - yy >= max(40, 0.08 * h) and (top is None or yy < top):
                    top = yy + gap
        if top is None:                                          # no y axis: up to the highest ink over the axis
            top = ya
            for yy in range(ya - 3, max(0, ya - int(0.9 * h)), -1):
                if g[yy * w + xa + 4: yy * w + xb - 4].count(1):
                    top = yy
                elif ya - yy > 0.05 * h and top - yy > 0.04 * h:
                    break
            if ya - top < 40:
                continue
        out.append((xa, top, xb, ya))
    # the top line of a closed box is an 'axis' too: a frame whose bottom is another frame's top is that line
    out = [b for b in out if not any(o is not b and abs(o[1] - b[3]) < 6 and abs(o[0] - b[0]) < 8 and abs(o[2] - b[2]) < 8 for o in out)]
    grown = []
    for xa, top, xb, ya in out:
        # a peak that runs above the end of the y axis (or of the box) is still of this plot: the frame grows upward
        # while there is ink over it, and stops at a blank band or at another plot's line
        blank = 0; yy = top - 4; limit = max(0, top - int(0.6 * (ya - top)) - 40)
        while yy > limit and blank < 14:
            if g[yy * w + xa + 4: yy * w + xb - 4].count(1):
                if g[yy * w + xa: yy * w + xb].count(1) > 0.5 * (xb - xa):
                    break
                top = yy; blank = 0
            else:
                blank += 1
            yy -= 1
        box = (xa, top, xb, ya)
        if not any(abs(box[0] - o[0]) < 8 and abs(box[2] - o[2]) < 8 and abs(box[3] - o[3]) < 8 for o in grown):
            grown.append(box)
    border = lambda b: b[0] <= 0.02 * w and b[2] >= 0.98 * w and b[1] <= 0.03 * h and b[3] >= 0.97 * h      # the line drawn round the whole picture
    grown.sort(key=lambda b: (border(b), -(b[2] - b[0]) * (b[3] - b[1])))
    return grown[:8]


def ticks(fig, box):
    """The axis numbers printed under a frame, where the page keeps them as text: [(pixel x of the label's centre,
    value)] — only when three or more lie on one line and run evenly with their positions (a caption's numbers, a
    figure's letters and a year do not)."""
    x0, y0, x1, y1 = box
    cand = []
    for a, b, c, d, t in fig.words:
        t = t.replace('−', '-').replace(',', '')
        if y1 - 2 <= b and d <= y1 + 0.16 * (y1 - y0) + 60 and x0 - 30 <= 0.5 * (a + c) <= x1 + 30 and re.fullmatch(r'-?\d{1,4}(?:\.\d)?', t):
            cand.append((0.5 * (a + c), float(t), 0.5 * (b + d)))
    best = []
    for _x, _v, yc in cand:
        row = sorted((x, v) for x, v, y in cand if abs(y - yc) < 6)
        if len(row) > len(best):
            best = row
    if len(best) < 3:
        return []
    fit = _line(best)
    if fit is None:
        return []
    a, b = fit
    span = max(v for _x, v in best) - min(v for _x, v in best)
    if not span or max(abs(a + b * x - v) for x, v in best) > 0.03 * span:
        return []
    # a number is centred on its tick only roughly (a '0' at the frame's edge is pushed inward): each is moved onto the
    # tick mark drawn at the axis nearest it, and the scale is the line through all of them
    marks = tick_marks(fig, box)
    if len(marks) >= 2:
        pitch = abs(best[-1][0] - best[0][0]) / (len(best) - 1)
        snapped = []
        for x, v in best:
            near = min(marks, key=lambda m: abs(m - x))
            snapped.append((near if abs(near - x) <= 0.3 * pitch else x, v))
        refit = _line(snapped)
        if refit and max(abs(refit[0] + refit[1] * x - v) for x, v in snapped) <= max(abs(a + b * x - v) for x, v in best) + 1e-9:
            best, (a, b) = snapped, refit
    if b:                                                        # the fitted scale, given at the first and the last number's place
        best = [((v - a) / b, v) for _x, v in (best[0], best[-1])] if len(best) > 2 else best
    return best


def tick_marks(fig, box):
    """The pixel x of the tick marks of a frame's x axis -> [x] of the EVENLY SPACED ones: short vertical strokes
    standing on the axis line, outside it or inside. Strokes are found by how far the ink runs from the axis in each
    column (three pixels or more, and not a frame line); what is evenly spaced among them is the scale's ticks — a
    curve that touches the axis, a label's leader and a number's stem are not."""
    x0, y0, x1, y1 = box
    g = fig.gray(); w, h = fig.w, fig.h
    best = []
    for step in (1, -1):                                         # below the axis (ticks outside), above it (ticks inside)
        start = y1
        while 0 < start < h - 1 and g[start * w + x0: start * w + x1 + 1].count(1) > 0.5 * (x1 - x0):
            start += step                                        # off the axis line itself
        runs = []
        for x in range(max(0, x0 - 2), min(w, x1 + 3)):
            n = 0; y = start
            while 0 <= y < h and n < 45 and g[y * w + x]:
                n += 1; y += step
            runs.append(n)
        marks = []; i = 0
        while i < len(runs):
            if 3 <= runs[i] < 45:
                j = i
                while j + 1 < len(runs) and 3 <= runs[j + 1] < 45:
                    j += 1
                if j - i < 9:
                    marks.append(max(0, x0 - 2) + 0.5 * (i + j) + 0.5)       # the middle of the stroke, a pixel's centre being at its index + ½
                i = j + 1
            else:
                i += 1
        reg = _regular(marks)
        if len(reg) > len(best):
            best = reg
    return best


def _regular(marks, slack=1.6):
    """The largest evenly spaced subset of some positions (three or more); [] when there is none. The spacing is taken
    from the commonest step between neighbours and then REFITTED to the marks it explains, again and again — a pitch of
    42.5 pixels read as 42 loses the scale after four ticks."""
    if len(marks) < 3:
        return []
    marks = sorted(marks)
    diffs = sorted(b - a for a, b in zip(marks, marks[1:]) if b - a > 3)
    if not diffs:
        return []
    best = []; line = None
    for d0 in sorted({round(v) for v in diffs}, key=lambda v: -sum(1 for q in diffs if abs(q - v) <= 1.0))[:4]:
        for origin in marks[:8]:
            o, d = origin, float(d0)
            sub = []
            for _ in range(4):
                sub = [m for m in marks if abs(m - (o + d * round((m - o) / d))) <= slack]
                if len(sub) < 3:
                    break
                fit = _line([(round((m - o) / d), m) for m in sub])
                if fit is None or fit[1] <= 0:
                    break
                o, d = fit[0], fit[1]
            idx = sorted({int(round((m - o) / d)) for m in sub})
            if len(sub) >= 3 and len(idx) >= 0.7 * (idx[-1] - idx[0] + 1) and len(sub) > len(best):     # evenly spaced means consecutive steps, most of them there
                best = sub; line = (o, d, idx)
    if not best:
        return []
    o, d, idx = line
    return [o + d * k for k in idx]                              # each tick at its place on the fitted scale: forty strokes two pixels wide give the pitch to a tenth of a pixel


def _line(pts):
    n = len(pts); sx = sum(p[0] for p in pts); sy = sum(p[1] for p in pts)
    sxx = sum(p[0] * p[0] for p in pts); sxy = sum(p[0] * p[1] for p in pts)
    den = n * sxx - sx * sx
    if not den:
        return None
    b = (n * sxy - sx * sy) / den
    return (sy - b * sx) / n, b


# ----------------------------------------------------------------------------- the curve

def _vector_curve(fig, box, seed=None):
    """The curve of a frame from the page's own drawing -> {pixel column: (top y, bottom y)}, or None.
    A plot's curve is drawn as one path or as many: the stroked paths inside the frame are taken by COLOUR (the colour
    whose strokes cross the most columns — or that of the stroke nearest `seed`), and among those of one colour the
    pieces that join end to end into the widest chain (or the chain nearest `seed`). Long straight strokes along the
    frame — axes, grid — are not a curve."""
    x0, y0, x1, y1 = box
    wd, ht = x1 - x0, y1 - y0
    units = []
    for col, pts in (fig.strokes or [((0, 0, 0), p) for p in fig.paths]):
        inside = sum(1 for x, y in pts if x0 - 2 <= x <= x1 + 2 and y0 - 2 <= y <= y1 + 2)
        if inside < 0.9 * len(pts):
            continue
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        if len(pts) <= 5 and (max(ys) - min(ys) < 1.5 or max(xs) - min(xs) < 1.5):
            continue                                             # a straight stroke along an axis: a frame line, a tick, a grid line
        units.append((col, pts))
    if not units:
        return None
    def columns(group):
        c = set()
        for _col, pts in group:
            c.update(range(int(min(p[0] for p in pts)), int(max(p[0] for p in pts)) + 1))
        return c
    by = {}
    for u in units:
        by.setdefault(u[0], []).append(u)
    if seed is not None:
        near = min(units, key=lambda u: min((x - seed[0]) ** 2 + (y - seed[1]) ** 2 for x, y in u[1]))
        group = by[near[0]]
    else:
        group = max(by.values(), key=lambda g: len(columns(g)))
    # the pieces of one colour that join end to end: chains
    ends = [(u[1][0], u[1][-1]) for u in group]
    parent = list(range(len(group)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    grid = {}
    for i, (a_, b_) in enumerate(ends):
        for p in (a_, b_):
            grid.setdefault((int(p[0] // 3), int(p[1] // 3)), []).append((i, p))
    for (gx, gy), items in list(grid.items()):
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j, q in grid.get((gx + dx, gy + dy), []):
                    for i, p in items:
                        if i != j and abs(p[0] - q[0]) <= 2.0 and abs(p[1] - q[1]) <= 2.0:
                            parent[find(i)] = find(j)
    chains = {}
    for i, u in enumerate(group):
        chains.setdefault(find(i), []).append(u)
    if seed is not None:
        chain = min(chains.values(), key=lambda g: min((x - seed[0]) ** 2 + (y - seed[1]) ** 2 for _c, pts in g for x, y in pts))
    else:
        chain = max(chains.values(), key=lambda g: len(columns(g)))
    col = {}
    for _c, pts in chain:
        for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
            a_, b_ = ((xa, ya), (xb, yb)) if xa <= xb else ((xb, yb), (xa, ya))
            for x in range(int(math.ceil(a_[0])), int(math.floor(b_[0])) + 1):
                t = (x - a_[0]) / (b_[0] - a_[0]) if b_[0] != a_[0] else 0.0
                col.setdefault(x, []).append(a_[1] + t * (b_[1] - a_[1]))
            if int(a_[0]) == int(b_[0]):
                col.setdefault(int(a_[0]), []).extend([a_[1], b_[1]])
    return {x: (min(v), max(v)) for x, v in col.items() if x0 <= x <= x1}


def curve_colour(fig, box):
    """The colour the curve of a frame is drawn in -> (r, g, b): the ink colour found in the MOST COLUMNS of the frame.
    A curve crosses the whole plot; the numbers and names set over its peaks, however much ink they are, stand in a
    few columns each (counting pixels picked the lettering's colour on a figure with many labels). The long straight
    lines — axes, grid — are left out."""
    x0, y0, x1, y1 = box
    g = fig.gray(); w = fig.w
    cols = {}; count = {}
    step = max(1, (y1 - y0) // 260)
    for y in range(y0 + 3, y1 - 2, step):
        row = g[y * w + x0 + 3: y * w + x1 - 2]
        if row.count(1) > 0.5 * len(row):
            continue                                             # a grid line or the frame
        i = row.find(1)
        while i >= 0:
            c = fig.at(x0 + 3 + i, y)
            key = (c[0] >> 5, c[1] >> 5, c[2] >> 5)
            cols.setdefault(key, set()).add(i >> 1)
            count[key] = count.get(key, 0) + 1
            i = row.find(1, i + 1)
    if not cols:
        raise ValueError('nothing is drawn inside that frame')
    k = max(cols, key=lambda q: (len(cols[q]), count[q]))
    return (k[0] * 32 + 16, k[1] * 32 + 16, k[2] * 32 + 16)


def _mask(fig, xa, xb, ya, yb, colour, tol):
    """The pixels of the curve's colour in a rectangle, one byte each (1 = within `tol` of the colour on every
    channel), rows top to bottom -> (bytes, width). Done a row at a time on whole byte strings: a frame of six million
    pixels is not walked pixel by pixel."""
    w = fig.w; rgb = fig.rgb; W = xb - xa + 1
    t = max(1, int(round(0.8 * tol)))
    tabs = [bytes(1 if abs(v - c) <= t else 0 for v in range(256)) for c in colour]
    rows = []
    for y in range(ya, yb + 1):
        seg = rgb[3 * (y * w + xa): 3 * (y * w + xb + 1)]
        n = int.from_bytes(seg[0::3].translate(tabs[0]), 'big') & int.from_bytes(seg[1::3].translate(tabs[1]), 'big') & int.from_bytes(seg[2::3].translate(tabs[2]), 'big')
        rows.append(n.to_bytes(W, 'big'))
    return b''.join(rows), W


def _raster_curve(fig, box, colour, tol, down, seed):
    """The curve of a frame followed through its pixels -> {column: (top, bottom) of the curve's ink there}."""
    x0, y0, x1, y1 = box
    xa, xb, ya, yb = x0 + 2, x1 - 2, y0 + 2, y1 - 2
    if xb - xa < 20 or yb - ya < 20:
        raise ValueError('that frame is too small to trace')
    m, W = _mask(fig, xa, xb, ya, yb, colour, tol)
    H = yb - ya + 1
    # a row inked along most of the width is a grid line, a frame line or the zero line: its pixels are not the curve
    lines = set(k for k in range(H) if m[k * W: (k + 1) * W].count(1) > 0.7 * W)
    cols = []
    for k in range(W):
        col = m[k::W]
        runs = []; i = col.find(1)
        while i >= 0:
            j = col.find(0, i)
            if j < 0:
                j = H
            if lines:
                s_ = None
                for y in range(i, j):
                    if y in lines:
                        if s_ is not None:
                            runs.append((ya + s_, ya + y - 1)); s_ = None
                    elif s_ is None:
                        s_ = y
                if s_ is not None:
                    runs.append((ya + s_, ya + j - 1))
            else:
                runs.append((ya + i, ya + j - 1))
            i = col.find(1, j) if j < H else -1
        # a column inked over most of the height is a vertical line (a marker, a frame), not the curve
        cols.append([r for r in runs if r[1] - r[0] < 0.9 * H])
    if sum(1 for c in cols if c) < 0.2 * len(cols):
        raise ValueError('no curve of that colour is found in the frame — click on the curve to give its colour')
    # the one continuous line: the cheapest way through one run a column, where stepping to a run that touches the
    # last one costs nothing and a jump costs its height; a column may be skipped at a price
    SKIP = 25.0
    INF = float('inf')
    prev = None                                                  # ([(cost, run, back index)], column) of the last column that had runs
    trail = []
    force = None
    if seed is not None and xa <= seed[0] <= xb:
        force = int(seed[0]) - xa
    for k, runs in enumerate(cols):
        if force is not None and k == force and runs:
            runs = [min(runs, key=lambda r: abs(0.5 * (r[0] + r[1]) - seed[1]))]
        if not runs:
            trail.append(None); continue
        cur = []
        for r in runs:
            if prev is None:
                cur.append((0.0, r, -1))
                continue
            best = INF; bi = -1
            for j, (c, pr, _b) in enumerate(prev[0]):
                gap = max(0, r[0] - pr[1] - 1, pr[0] - r[1] - 1)
                cost = c + gap + SKIP * 0.2 * (k - prev[1] - 1)
                if cost < best:
                    best, bi = cost, j
            cur.append((best, r, bi))
        trail.append(cur); prev = (cur, k)
    out = {}
    k = len(trail) - 1
    while k >= 0 and trail[k] is None:
        k -= 1
    if k < 0:
        return out
    j = min(range(len(trail[k])), key=lambda i: trail[k][i][0])
    while k >= 0:
        cost, r, back = trail[k][j]
        out[xa + k] = r
        k2 = k - 1
        while k2 >= 0 and trail[k2] is None:
            k2 -= 1
        if k2 < 0 or back < 0:
            break
        k, j = k2, back
    return out


def _edge(fig, x, y, colour):
    """How far the curve's ink reaches into the pixel (x, y) next to its run: 0 for paper, 1 for the full colour — the
    anti-aliased edge of a line says where it ends to a fraction of a pixel."""
    if not (0 <= x < fig.w and 0 <= y < fig.h):
        return 0.0
    c = fig.at(x, y)
    full = 765.0 - sum(colour)
    return max(0.0, min(1.0, (765.0 - sum(c)) / full)) if full > 30 else 0.0


def trace_pixels(fig, box, colour=None, tol=70, down=None, seed=None, vector=True):
    """The curve inside a frame, in the figure's own pixels -> {'pts': [(x, y)] one a column (y to a fraction of a
    pixel), 'how': 'vector' | 'raster', 'colour', 'down', 'coverage', 'filled', 'box'}. No axis is needed for this: the
    curve can be followed first and the axis scaled on its peaks afterwards."""
    x0, y0, xe, ye = [int(round(v)) for v in box]
    x0, xe = max(0, min(x0, xe)), min(fig.w - 1, max(x0, xe)); y0, ye = max(0, min(y0, ye)), min(fig.h - 1, max(y0, ye))
    if xe - x0 < 30 or ye - y0 < 30:
        raise ValueError('the frame is too small: drag it around the plot, from one end of the axis to the other')
    box = (x0, y0, xe, ye)
    cols = _vector_curve(fig, box, seed) if vector and (fig.strokes or fig.paths) else None
    if cols and len(cols) < 0.85 * (xe - x0):                   # a curve that could not be put together from its pieces: the pixels are followed instead
        cols = None
    how = 'vector' if cols else 'raster'
    lw = 0.0
    if not cols:
        colour = tuple(int(v) for v in colour) if colour else curve_colour(fig, box)
        for wider in (1.0, 1.4, 1.9):                           # a thin line at a low resolution is blended with the paper: its pixels lie further from its colour
            try:
                cols = _raster_curve(fig, box, colour, tol * wider, down, seed)
            except ValueError:
                if wider == 1.9:
                    raise
                continue
            if len(cols) >= 0.85 * (xe - x0 - 3):
                break
    if len(cols) < 20:
        raise ValueError('no curve could be followed in that frame')
    found = len(cols)
    if down is None:                                             # bands down: the curve keeps to the top of its range and dips from it
        mids = sorted(0.5 * (a + b) for a, b in cols.values())
        lo_, hi_ = mids[len(mids) // 50], mids[-1 - len(mids) // 50]
        down = hi_ > lo_ and (mids[len(mids) // 2] - lo_) < 0.3 * (hi_ - lo_)       # pixel y runs downward: 'near the top' is a small y
    filled = 0
    if how == 'raster':
        # the edges to a fraction of a pixel, and the line's own thickness (a quarter of the columns are no steeper than flat)
        sub = {}
        for x, (top, bot) in cols.items():
            sub[x] = (top - _edge(fig, x, top - 1, colour), bot + _edge(fig, x, bot + 1, colour))
        widths = sorted(b - a + 1 for a, b in sub.values())
        lw = widths[len(widths) // 4] if widths else 1.0
        # a curve at zero runs ALONG the axis and is hidden in it: where it leaves the frame's floor on both sides of a gap,
        # the gap is the floor (a spectrum drawn on its baseline had holes wherever it had no band)
        if not down:
            xs = sorted(sub)
            floor = ye - 0.5 * lw
            near_floor = lambda x: sub[x][1] >= ye - 3 - lw
            for a, b in zip(xs, xs[1:]):
                if b - a > 1 and near_floor(a) and near_floor(b):
                    for x in range(a + 1, b):
                        sub[x] = (floor - 0.5 * lw, floor + 0.5 * lw); filled += 1
            for edge_x, rng in ((xs[0], range(x0 + 2, xs[0])), (xs[-1], range(xs[-1] + 1, xe - 1))):
                if near_floor(edge_x):
                    for x in rng:
                        sub[x] = (floor - 0.5 * lw, floor + 0.5 * lw); filled += 1
        cols = sub
    pts = []
    xs_ = sorted(cols)
    for n_, x in enumerate(xs_):
        top, bot = cols[x]
        if how == 'vector':
            pts.append((float(x), bot if down else top))
            continue
        # The middle of the stroke, from its outer edge: half the line's thickness below the top at a peak — and, on a
        # flank, half the thickness MEASURED ALONG THE COLUMN, which the slope stretches by √(1 + slope²). Taking half the
        # flat thickness everywhere put the curve too high on every steep flank: a thick line made every band broader.
        a_ = xs_[max(0, n_ - 2)]; b_ = xs_[min(len(xs_) - 1, n_ + 2)]
        edge = 1 if down else 0
        slope = (cols[b_][edge] - cols[a_][edge]) / float(b_ - a_) if b_ != a_ else 0.0
        half = min(0.5 * lw * math.sqrt(1.0 + slope * slope), 0.5 * (bot - top + 1))
        pts.append((x + 0.5, (bot - half + 0.5) if down else (top + half + 0.5)))     # the centre of a pixel is at its index + ½
    return {'pts': pts, 'how': how, 'colour': list(colour) if colour else None, 'down': bool(down), 'coverage': found / float(xe - x0 + 1),
            'filled': filled, 'box': box}


def apexes(pts, down=False, share=0.02):
    """The pixel x of the peaks of a traced curve (of its dips, with `down`), to a fraction of a pixel: the maxima that
    stand `share` of the curve's range above their saddle, each put at the top of the parabola through its three
    highest points. What an axis mark snaps to when it is dropped on a peak — the way to scale an axis that has no
    usable ticks. NOT the better way where it has them: the numbers printed over a figure's peaks are rounded, and on
    a figure set against its own data, scaling on them was off by 2–3 cm-1 where scaling on the ticks was off by 0.3."""
    n = len(pts)
    if n < 9:
        return []
    from pxrd_review import spectrum as SM
    ys = [p[1] if down else -p[1] for p in pts]                 # up = larger, whichever way the bands point
    sm = SM.savgol(ys, 5, 2)
    rng = max(sm) - min(sm) or 1.0
    out = []
    for i in range(2, n - 2):
        if not (sm[i] >= sm[i - 1] and sm[i] > sm[i + 1]):
            continue
        l = sm[i]; k = i - 1
        while k >= 0 and sm[k] <= sm[i]:
            l = min(l, sm[k]); k -= 1
        r = sm[i]; k = i + 1
        while k < n and sm[k] <= sm[i]:
            r = min(r, sm[k]); k += 1
        if sm[i] - max(l, r) <= share * rng:
            continue
        a, b, c = sm[i - 1], sm[i], sm[i + 1]; den = a - 2 * b + c
        off = 0.5 * (a - c) / den if den else 0.0
        out.append(pts[i][0] + max(-1.0, min(1.0, off)) * 0.5 * (pts[i + 1][0] - pts[i - 1][0]))
    return out


def scale(calib):
    """(a, b) of value = a + b·pixel through the axis points [(pixel x, value)]: the line through two, the least-squares
    line through more."""
    pts = [(float(p), float(v)) for p, v in calib if p is not None and v is not None]
    if len(pts) < 2 or len({p for p, _v in pts}) < 2 or len({v for _p, v in pts}) < 2:
        raise ValueError('two different points of the axis, with their two values, are needed to scale it')
    fit = _line(pts)
    if fit is None or not fit[1]:
        raise ValueError('two different points of the axis, with their two values, are needed to scale it')
    return fit


def digitize(fig, box, x1=None, v1=None, x2=None, v2=None, colour=None, tol=70, down=None, seed=None, vector=True, calib=None):
    """The curve inside the frame `box` (pixels) as a spectrum. The axis is given by `calib`, [(pixel x, value)] of two
    or more points (the least-squares line through them), or by the two points `x1`, `v1`, `x2`, `v2`. `colour`: the
    curve's (r, g, b) — found when not given; `tol`: how far a pixel's colour may lie from it; `down`: the bands point
    DOWN (a transmittance spectrum) — told from the curve when not given; `seed`: a pixel on the curve wanted, where
    several stand in the frame.
    -> {'x', 'y' (0 at the frame's bottom, 1 at its top), 'trace': [(px, py)] for a preview, 'how', 'cm_per_px',
        'coverage': the share of the frame's columns the curve was found in, 'colour', 'down', 'peaks': [pixel x]}"""
    a_, b_ = scale(calib if calib else [(x1, v1), (x2, v2)])
    t = trace_pixels(fig, box, colour, tol, down, seed, vector)
    x0, y0, xe, ye = t['box']
    xs = [a_ + b_ * px for px, _py in t['pts']]
    ys = [(ye - py) / float(ye - y0) for _px, py in t['pts']]
    if xs[0] > xs[-1]:
        xs.reverse(); ys.reverse()
    return {'x': xs, 'y': ys, 'trace': [(round(px, 1), round(py, 1)) for px, py in t['pts']], 'how': t['how'], 'cm_per_px': abs(b_),
            'coverage': t['coverage'], 'filled': t['filled'], 'colour': t['colour'], 'box': list(t['box']), 'down': t['down'],
            'peaks': [round(p, 2) for p in apexes(t['pts'], t['down'])]}


PROMINENCE = 0.015             # a feature of a traced curve stands this share of the curve's range above the saddle that parts it from a higher one


def features(x, y, cm_per_px=1.0, down=False):
    """The bands a traced curve shows — positions only (cm-1): its maxima that stand PROMINENCE of the curve's range
    above the lower of the two saddles parting them from higher ground (a broad hump counts as much as a sharp peak;
    a ripple of the tracing does not), and the shoulders the second derivative marks at smoothing widths of 4 to 64
    pixels. `down`: the bands point down. The curve is smoothed over five pixels first: a traced line steps by whole
    pixels."""
    from pxrd_review import spectrum as SM
    n = len(x)
    if n < 15:
        return []
    if down:
        top_ = max(y); y = [top_ - v for v in y]
    sm = SM.savgol(y, 5, 2)
    rng = max(sm) - min(sm) or 1.0
    out = []
    for i in range(2, n - 2):
        if not (sm[i] >= sm[i - 1] and sm[i] > sm[i + 1]):
            continue
        lo_l = sm[i]; k = i - 1
        while k >= 0 and sm[k] <= sm[i]:
            lo_l = min(lo_l, sm[k]); k -= 1
        lo_r = sm[i]; k = i + 1
        while k < n and sm[k] <= sm[i]:
            lo_r = min(lo_r, sm[k]); k += 1
        if sm[i] - max(lo_l, lo_r) > PROMINENCE * rng:
            a_, b_, c_ = sm[i - 1], sm[i], sm[i + 1]; den = a_ - 2 * b_ + c_      # the top of the parabola through the three highest points
            off = max(-1.0, min(1.0, 0.5 * (a_ - c_) / den)) if den else 0.0
            out.append(x[i] + off * 0.5 * (x[i + 1] - x[i - 1]))
    try:
        floor = min(sm)
        dx = abs(x[-1] - x[0]) / (n - 1)
        for b in SM.find_bands(x, [v - floor for v in sm], sigma=0.003 * rng, min_share=0.02, scales=tuple(k * dx for k in (4, 8, 16, 32, 64))):
            if not any(abs(b['pos'] - p) < 3.0 * dx for p in out):
                out.append(b['pos'])
    except Exception:
        pass
    return sorted(round(p, 1) for p in out)


def stated_on_curve(x, y, stated, cm_per_px=1.0, tol=None, down=False):
    """The stated band positions beside a traced curve -> {'found': [(stated, feature)], 'none': [stated positions the
    curve shows nothing near], 'outside': [those beyond the curve's ends], 'tol'}. `tol` (cm-1): how near a feature
    must be — three pixels, and never under 8 cm-1 (a position read off a figure is no better than that)."""
    tol = tol or max(8.0, 3.0 * cm_per_px)
    feats = features(x, y, cm_per_px, down)
    lo, hi = min(x), max(x)
    out = {'found': [], 'none': [], 'outside': [], 'tol': tol}
    for s in sorted(set(stated)):
        if not lo <= s <= hi:
            out['outside'].append(s); continue
        near = min(feats, key=lambda f: abs(f - s), default=None)
        if near is not None and abs(near - s) <= tol:
            out['found'].append((s, near))
        else:
            out['none'].append(s)
    return out
