"""Unit tests for pxrd_review.figure_trace — figures drawn here from a spectrum whose bands are known.

    python3 -m unittest tests.test_figure_trace -v

A page is made with PyMuPDF: axes (a closed box or two open axes), tick marks, axis numbers as text, the curve as a drawn
path, a second curve in another colour, numbers set over the peaks in the curve's own colour. The same page rendered to
an image has no words and no paths: the pixels alone. What the tracer returns is set against the bands the curve was
drawn from.
"""
import io, math, os, shutil, tempfile, unittest

import fitz

from pxrd_review import figure_trace as FT, spectrum as SM

BANDS = [(210, 0.35, 14), (464, 1.0, 10), (832, 0.8, 12), (846, 0.45, 9), (1010, 0.25, 16), (1105, 0.55, 20)]
LO, HI = 100.0, 1300.0
X0, X1, Y0, Y1 = 90.0, 500.0, 120.0, 330.0                 # the frame on the page, in points


def spec(v):
    return 0.04 + sum(h * SM.profile('pvoigt', v, p, 1.0, w, 0.5) for p, h, w in BANDS)


def make_pdf(path, colour=(0, 0, 0.8), second=True, labels=True, clutter=True, box=True, flip=False, down=False):
    doc = fitz.open(); page = doc.new_page(width=595, height=842)
    X = (lambda v: X1 - (v - LO) / (HI - LO) * (X1 - X0)) if flip else (lambda v: X0 + (v - LO) / (HI - LO) * (X1 - X0))
    Y = (lambda u: Y0 + 12 + u / 1.15 * (Y1 - Y0 - 12)) if down else (lambda u: Y1 - u / 1.15 * (Y1 - Y0))
    sh = page.new_shape()
    sh.draw_line((X0, Y1), (X1, Y1)); sh.draw_line((X0, Y1), (X0, Y0))
    if box:
        sh.draw_line((X0, Y0), (X1, Y0)); sh.draw_line((X1, Y0), (X1, Y1))
    for v in range(200, 1300, 200):
        sh.draw_line((X(v), Y1), (X(v), Y1 + 4))
    sh.finish(color=(0, 0, 0), width=0.8); sh.commit()
    pts = [(X(LO + k * (HI - LO) / 900.0), Y(spec(LO + k * (HI - LO) / 900.0))) for k in range(901)]
    sh = page.new_shape(); sh.draw_polyline(pts); sh.finish(color=colour, width=0.9, closePath=False); sh.commit()
    if second:                                             # another spectrum in the same frame, set off upward, in another colour
        sh = page.new_shape(); sh.draw_polyline([(x, y - 60 + 14 * math.sin(x / 9.0)) for x, y in pts]); sh.finish(color=(0.8, 0, 0), width=0.9, closePath=False); sh.commit()
    if labels:
        for v in range(200, 1300, 200):
            page.insert_text((X(v) - 8, Y1 + 15), str(v), fontsize=8)
        page.insert_text((250, Y1 + 30), 'Raman shift (cm-1)', fontsize=8)
    if clutter:                                            # the bands' numbers set over them, in the curve's own colour
        for p, h, w in BANDS[1:4]:
            page.insert_text((X(p) - 6, Y(spec(p)) - 6), str(p), fontsize=7, color=colour)
    page.insert_text((90, 360), 'Figure 3. Raman spectrum of testite.', fontsize=9)
    page2 = doc.new_page(width=595, height=842); page2.insert_text((90, 100), 'A page of text.', fontsize=9)
    doc.save(path); doc.close()
    return X


def offsets(r):
    feats = FT.features(r['x'], r['y'], r['cm_per_px'], r['down'])
    return [min(abs(f - p) for f in feats) for p, _h, _w in BANDS]


class Trace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.pdf = os.path.join(cls.tmp, 'paper.pdf')
        cls.X = staticmethod(make_pdf(cls.pdf))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _image(self, dpi, **kw):
        p = os.path.join(self.tmp, 'other.pdf'); X = make_pdf(p, **kw)
        with fitz.open(p) as d:
            png = d[0].get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0)).tobytes('png')
        return FT.figure('figure.png', data=png), (lambda v, X=X, z=dpi / 72.0: X(v) * z)

    def test_sources(self):
        s = FT.sources(self.pdf)
        self.assertEqual([(x['index'], x['spectrum']) for x in s], [(0, True), (1, False)]); self.assertIn('Raman spectrum', s[0]['label'])
        with self.assertRaises(ValueError):
            FT.sources(os.path.join(self.tmp, 'notes.txt'))
        with self.assertRaises(ValueError):
            FT.figure(self.pdf, 7)

    def test_a_page_with_its_words_and_its_drawing(self):
        fig = FT.figure(self.pdf, 0)
        frames = FT.frames(fig)
        self.assertEqual(len(frames), 1)
        z = fig.w / 595.0                                               # a drawn plot is rendered finer than a page of pictures
        self.assertGreater(z, FT.DPI / 72.0)
        box = frames[0]
        self.assertAlmostEqual(box[0], X0 * z, delta=3); self.assertAlmostEqual(box[2], X1 * z, delta=3); self.assertAlmostEqual(box[3], Y1 * z, delta=3)
        self.assertLess(box[1], Y0 * z)                                   # the second curve runs over the box: the frame grows over it
        tk = FT.ticks(fig, box)                                           # the axis numbers, scaled by the line through all of them
        self.assertEqual([v for _x, v in tk], [200.0, 1200.0])
        for px, v in tk:
            self.assertAlmostEqual(px, self.X(v) * z, delta=1.5)
        r = FT.digitize(fig, box, tk[0][0], tk[0][1], tk[-1][0], tk[-1][1], seed=(self.X(464) * z, (Y1 - spec(464) / 1.15 * (Y1 - Y0)) * z))
        self.assertEqual((r['how'], r['down']), ('vector', False)); self.assertGreater(r['coverage'], 0.98)
        self.assertLess(max(offsets(r)), 2.0)                             # the drawing's own curve: every band within 2 cm-1, the shoulder at 846 among them
        self.assertAlmostEqual(max(r['y']), (spec(464)) / 1.15 * (Y1 - Y0) * z / (box[3] - box[1]), delta=0.02)
        r2 = FT.digitize(fig, box, tk[0][0], tk[0][1], tk[-1][0], tk[-1][1], vector=False, colour=(0, 0, 204))
        self.assertEqual(r2['how'], 'raster'); self.assertLess(max(offsets(r2)), 3.0)

    def test_pixels_alone(self):
        for dpi, worst in ((150, 3.0), (300, 2.0)):
            img, X = self._image(dpi)
            self.assertEqual((img.words, img.paths), ([], []))
            box = FT.frames(img)[0]
            self.assertEqual(FT.ticks(img, box), [])                      # a picture keeps no numbers: the two marks are the user's
            r = FT.digitize(img, box, X(200), 200, X(1200), 1200, colour=(0, 0, 204))
            self.assertEqual(r['how'], 'raster'); self.assertGreater(r['coverage'], 0.97)
            self.assertLess(max(offsets(r)), worst, dpi)                  # the numbers over the peaks, in the curve's colour, are not followed
            red = FT.digitize(img, box, X(200), 200, X(1200), 1200, colour=(204, 0, 0))
            self.assertGreater(min(red['y']), min(r['y']) + 0.1)          # the other curve, by its colour

    def test_colour_and_orientation_found(self):
        img, X = self._image(200, colour=(0, 0, 0), second=False, box=False, flip=True)      # one black curve, open axes, high wavenumber on the left
        box = FT.frames(img)[0]
        r = FT.digitize(img, box, X(200), 200, X(1200), 1200)
        self.assertLess(sum(r['colour']), 200); self.assertFalse(r['down']); self.assertLess(max(offsets(r)), 2.5)
        self.assertLess(r['x'][0], r['x'][-1])                            # ascending, whichever way the figure runs
        img, X = self._image(200, colour=(0, 0, 0), second=False, clutter=False, down=True)  # a transmittance figure: the bands point down
        box = FT.frames(img)[0]
        r = FT.digitize(img, box, X(200), 200, X(1200), 1200)
        self.assertTrue(r['down']); self.assertLess(max(offsets(r)), 2.5)

    def test_the_axis_from_its_ticks(self):
        # a picture keeps no numbers, but its ticks are there: the evenly spaced strokes on the axis, each at its fitted
        # place — a curve touching the axis, a frame line and a number's stem are not among them
        img, X = self._image(150)
        box = FT.frames(img)[0]
        marks = FT.tick_marks(img, box)
        self.assertEqual(len(marks), 6)
        for m, v in zip(marks, range(200, 1300, 200)):
            self.assertAlmostEqual(m, X(v), delta=0.6)
        reg = FT._regular([10.0, 52.4, 95.1, 137.5, 180.0, 222.6, 265.0, 300.0, 307.4])       # a pitch of 42.5: read as 42 it loses the scale after four ticks
        self.assertEqual(len(reg), 8); self.assertAlmostEqual((reg[-1] - reg[0]) / 7, 42.5, delta=0.1)
        self.assertEqual(FT._regular([5.0, 40.0]), [])
        # scaled on the two outer ticks, every band is within half a wavenumber at 150 dpi
        r = FT.digitize(img, box, marks[0], 200, marks[-1], 1200, colour=(0, 0, 204))
        self.assertLess(max(offsets(r)), 1.0)
        # … and on any number of points: the line through them
        many = FT.digitize(img, box, colour=(0, 0, 204), calib=list(zip(marks, range(200, 1300, 200))))
        self.assertAlmostEqual(many['cm_per_px'], r['cm_per_px'], 3)
        self.assertEqual(FT.scale([(100.0, 200.0), (300.0, 600.0)]), (0.0, 2.0))
        with self.assertRaises(ValueError):
            FT.scale([(100.0, 200.0), (100.0, 600.0)])

    def test_the_curve_before_the_axis(self):
        img, X = self._image(200, second=False)
        box = FT.frames(img)[0]
        t = FT.trace_pixels(img, box, colour=(0, 0, 204))
        self.assertEqual((t['how'], t['down']), ('raster', False)); self.assertGreater(t['coverage'], 0.97)
        peaks = FT.apexes(t['pts'], t['down'])
        for p, _h, _w in BANDS[:3] + BANDS[4:]:                             # every separate band's top, to a fraction of a pixel (846 is a shoulder)
            self.assertAlmostEqual(min(peaks, key=lambda q: abs(q - X(p))), X(p), delta=0.8, msg=p)

    def test_a_thick_line_is_not_a_broader_band(self):
        # the middle of a thick stroke on a steep flank lies half its SLANTED thickness under its upper edge
        p = os.path.join(self.tmp, 'thick.pdf')
        doc = fitz.open(); page = doc.new_page(width=595, height=842)
        X = lambda v: X0 + (v - LO) / (HI - LO) * (X1 - X0); Y = lambda u: Y1 - u / 1.15 * (Y1 - Y0)
        sh = page.new_shape(); sh.draw_line((X0, Y1), (X1, Y1)); sh.draw_line((X0, Y1), (X0, Y0)); sh.finish(color=(0, 0, 0), width=0.8); sh.commit()
        xs = [LO + k * (HI - LO) / 1800.0 for k in range(1801)]
        sh = page.new_shape(); sh.draw_polyline([(X(v), Y(spec(v))) for v in xs]); sh.finish(color=(0, 0, 0.8), width=2.5, closePath=False); sh.commit()
        png = page.get_pixmap(matrix=fitz.Matrix(200 / 72.0, 200 / 72.0)).tobytes('png'); doc.close()
        img = FT.figure('thick.png', data=png); box = FT.frames(img)[0]; z = 200 / 72.0
        r = FT.digitize(img, box, X(200) * z, 200, X(1200) * z, 1200, colour=(0, 0, 204))
        want = [spec(v) for v in r['x']]
        n = len(want); mx = sum(want) / n; my = sum(r['y']) / n
        r2 = sum((a - mx) * (b - my) for a, b in zip(want, r['y'])) ** 2 / (sum((a - mx) ** 2 for a in want) * sum((b - my) ** 2 for b in r['y']))
        self.assertGreater(r2, 0.985)                                       # under 0.96 with half the FLAT thickness taken everywhere

    def test_a_curve_drawn_in_pieces_and_a_baseline_in_the_axis(self):
        # the page draws the curve as two hundred separate strokes: joined by their colour and their ends, still the drawing's own curve
        p = os.path.join(self.tmp, 'pieces.pdf')
        doc = fitz.open(); page = doc.new_page(width=595, height=842)
        X = lambda v: X0 + (v - LO) / (HI - LO) * (X1 - X0); Y = lambda u: Y1 - u / 1.15 * (Y1 - Y0)
        sh = page.new_shape(); sh.draw_line((X0, Y1), (X1, Y1)); sh.draw_line((X0, Y1), (X0, Y0))
        for v in range(200, 1300, 200):
            sh.draw_line((X(v), Y1), (X(v), Y1 + 4))
        sh.finish(color=(0, 0, 0), width=0.8); sh.commit()
        zero = lambda v: max(0.0, spec(v) - 0.06)                           # a spectrum on its baseline: between its bands it runs along the axis
        pts = [(X(LO + k * (HI - LO) / 1000.0), Y(zero(LO + k * (HI - LO) / 1000.0))) for k in range(1001)]
        for k in range(0, 1000, 5):
            sh = page.new_shape(); sh.draw_polyline(pts[k: k + 6]); sh.finish(color=(0.8, 0, 0), width=0.9, closePath=False); sh.commit()
        for v in range(200, 1300, 200):
            page.insert_text((X(v) - 8, Y1 + 15), str(v), fontsize=8)
        doc.save(p); doc.close()
        fig = FT.figure(p, 0); box = FT.frames(fig)[0]; tk = FT.ticks(fig, box)
        r = FT.digitize(fig, box, tk[0][0], tk[0][1], tk[-1][0], tk[-1][1])
        self.assertEqual(r['how'], 'vector'); self.assertGreater(r['coverage'], 0.98)
        self.assertLess(max(offsets(r)[1:]), 1.0)
        with fitz.open(p) as d:
            png = d[0].get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes('png')
        img = FT.figure('pieces.png', data=png); box = FT.frames(img)[0]; marks = FT.tick_marks(img, box)
        r = FT.digitize(img, box, marks[0], 200, marks[-1], 1200, colour=(204, 0, 0))
        self.assertGreater(r['filled'], 50)                                 # where the curve is hidden in the axis line it is at zero, not missing
        self.assertGreater(len(r['x']), 0.97 * (box[2] - box[0])); self.assertLess(max(offsets(r)[1:]), 1.5)

    def test_the_picture_s_own_border_is_no_plot(self):
        img, _X = self._image(150, second=False)
        import fitz as _f
        page = _f.open().new_page(width=img.w, height=img.h); page.insert_image(page.rect, pixmap=img.pix)
        sh = page.new_shape(); sh.draw_rect(_f.Rect(1, 1, img.w - 1, img.h - 1)); sh.finish(color=(0, 0, 0), width=2); sh.commit()
        framed = FT.figure('framed.png', data=page.get_pixmap().tobytes('png'))
        fr = FT.frames(framed)
        self.assertGreaterEqual(len(fr), 2); self.assertGreater(fr[0][0], 0.05 * framed.w)       # the plot first, the border after it

    def test_a_closed_box_under_another_panel_keeps_to_its_box(self):
        # panels stacked: the lower plot's box has a line along its top, and the upper panel's axis title sits just above
        # it — the frame used to grow up through the title to the upper panel's axis, and the trace climbed the title
        import fitz as _f
        page = _f.open().new_page(width=400, height=420)
        sh = page.new_shape()
        sh.draw_rect(_f.Rect(40, 20, 380, 180)); sh.draw_rect(_f.Rect(40, 230, 380, 400))
        sh.finish(color=(0, 0, 0), width=1); sh.commit()
        page.insert_text((150, 196), 'Raman shift [cm-1]', fontsize=12)
        for x in (60, 160, 260, 360):
            page.insert_text((x, 212), str(x), fontsize=11); page.insert_text((x, 226), str(x), fontsize=11)
        sh = page.new_shape(); sh.draw_polyline([(40 + k, 392 - 0.08 * k - 120 * math.exp(-((k - 170) / 12.0) ** 2)) for k in range(341)]); sh.finish(color=(0, 0, 0), width=1, closePath=False); sh.commit()
        fig = FT.figure('panels.png', data=page.get_pixmap(dpi=144).tobytes('png'))
        z = 2.0
        lower = [b for b in FT.frames(fig) if abs(b[3] - 400 * z) < 6]
        self.assertEqual(len(lower), 1)
        self.assertGreater(lower[0][1], 222 * z)                          # its top is its own line at 230, not the title above it
        r = FT.trace_pixels(fig, lower[0])
        self.assertGreater(min(y for _x, y in r['pts']), 230 * z)        # the trace never left the box
        # a frame drawn by hand past the plot's sides and below its axis: the box's own sides are no curve at its ends
        x0, y0, x1, y1 = lower[0]
        r = FT.trace_pixels(fig, (x0 - 8, y0 + 4, x1 + 8, y1 + 70))
        ends = [y for _x, y in r['pts'][:6] + r['pts'][-6:]]
        self.assertGreater(min(ends), 355 * z)                         # the baseline ends at 365 pt; the sides run up to 230
        self.assertFalse([x for x, _y in r['pts'] if x < x0 or x > x1 + 1])   # nothing outside the plot's own sides

    def test_an_open_plot_under_a_running_head_with_a_ticked_y_axis(self):
        # no box: an x axis overhanging the y axis, the y axis ticked out and in, a running head of the page above the plot,
        # long ticks every second one on the x axis — the frame stopped at the head, the trace started on the curve
        import fitz as _f
        page = _f.open().new_page(width=400, height=420)
        page.insert_text((150, 40), 'RUNNING HEAD', fontsize=14)
        sh = page.new_shape()
        sh.draw_line((40, 380), (380, 380)); sh.draw_line((46, 380), (46, 70))
        for k in range(0, 7):
            y = 380 - 50 * k; sh.draw_line((42, y), (46, y)); sh.draw_line((46, y), (49, y))      # y ticks, out and in
        for k in range(0, 13):
            x = 60 + 25 * k; sh.draw_line((x, 380), (x, 386 if k % 2 == 0 else 383))            # x ticks, long and short
        sh.finish(color=(0, 0, 0), width=1); sh.commit()
        sh = page.new_shape(); sh.draw_polyline([(80 + k, 330 - 0.05 * k - 200 * math.exp(-((k - 150) / 10.0) ** 2)) for k in range(281)]); sh.finish(color=(0, 0, 0), width=1, closePath=False); sh.commit()
        fig = FT.figure('open.png', data=page.get_pixmap(dpi=144).tobytes('png')); z = 2.0
        box = FT.frames(fig)[0]
        self.assertGreater(box[1], 50 * z)                                 # under the running head
        r = FT.trace_pixels(fig, box)
        self.assertGreater(r['pts'][0][0], 78 * z)                         # the curve starts at 80, the y ticks stand at 42–49
        self.assertGreater(min(y for _x, y in r['pts']), 120 * z)          # the peak tops out at 130: nothing of the head
        marks = FT.tick_marks(fig, box)
        majors = FT.tick_majors(fig, box, marks)
        self.assertEqual([round(m / z) for m in majors], [60 + 50 * k for k in range(7)])

    def test_refusals(self):
        img, X = self._image(150)
        box = FT.frames(img)[0]
        for bad, word in (((10, 10, 20, 20), 'too small'), (box, None)):
            with self.assertRaises(ValueError) as e:
                FT.digitize(img, bad, X(200), 200, X(1200), 1200 if word else 200, colour=(0, 0, 204))
            self.assertIn(word or 'two different points', str(e.exception))
        with self.assertRaises(ValueError) as e:
            FT.digitize(img, box, X(200), 200, X(1200), 1200, colour=(0, 200, 0), tol=20)
        self.assertIn('no curve of that colour', str(e.exception))

    def test_files_that_cannot_be_opened_and_images_too_large(self):
        import tempfile, zipfile
        with tempfile.TemporaryDirectory() as d:
            bad_docx = os.path.join(d, 'bad.docx'); open(bad_docx, 'wb').write(b'PK not a zip')
            bad_pdf = os.path.join(d, 'bad.pdf'); open(bad_pdf, 'wb').write(b'%PDF-1.4 garbage')
            for path, word in ((bad_docx, 'is not a .docx'), (bad_pdf, 'is not a .pdf')):
                for fn in (FT.sources, FT.figure):
                    with self.assertRaises(ValueError) as e:
                        fn(path)
                    self.assertIn(word, str(e.exception))
            self.assertIn('is not a .pdf', FT.sources_data(bad_pdf)['error'])
            # an image is measured from its header before it is decoded; over the limit it is refused there
            img, _X = self._image(150)
            png = img.pix.tobytes('png')
            self.assertEqual(FT.image_size(png, 'x.png'), (img.w, img.h))
            self.assertEqual(FT.probe_data('x.png', png), {'w': img.w, 'h': img.h})
            self.assertIn('could not be read as an image', FT.probe_data('x.png', b'not an image')['error'])
            keep = FT.IMAGE_PIXELS_MAX
            try:
                FT.IMAGE_PIXELS_MAX = img.w * img.h - 1
                self.assertIn('too large to trace', FT.probe_data('x.png', png)['error'])
                with self.assertRaises(ValueError) as e:
                    FT.figure('x.png', data=png)
                self.assertIn('too large to trace', str(e.exception))
                docx = os.path.join(d, 'pic.docx')
                with zipfile.ZipFile(docx, 'w') as z:
                    z.writestr('word/media/image1.png', png)
                with self.assertRaises(ValueError) as e:
                    FT.figure(docx, 0)
                self.assertIn('too large to trace', str(e.exception))
            finally:
                FT.IMAGE_PIXELS_MAX = keep

    def test_the_stated_bands_beside_the_curve(self):
        fig = FT.figure(self.pdf, 0); box = FT.frames(fig)[0]; tk = FT.ticks(fig, box)
        r = FT.digitize(fig, box, tk[0][0], tk[0][1], tk[-1][0], tk[-1][1], seed=(self.X(464) * fig.w / 595.0, (Y1 - spec(464) / 1.15 * (Y1 - Y0)) * fig.w / 595.0))
        got = FT.stated_on_curve(r['x'], r['y'], [210, 464, 832, 846, 700, 1010, 1105, 3400], r['cm_per_px'])
        self.assertEqual(([s for s, _f in got['found']], got['none'], got['outside']), ([210, 464, 832, 846, 1010, 1105], [700], [3400]))
        self.assertEqual(got['tol'], 8.0)

    def test_a_worker_s_plain_values(self):
        d = FT.page_data(self.pdf, 0)
        fig = FT.Figure.from_data(d)
        self.assertEqual((fig.w, fig.h, len(fig.paths)), (d['w'], d['h'], 2)); self.assertEqual(len(FT.frames(fig)), 1)
        self.assertIn('no page 9', FT.page_data(self.pdf, 8)['error'])
        self.assertEqual(len(FT.sources_data(self.pdf)['sources']), 2)

    def test_an_image_of_a_docx(self):
        import docx
        img, _X = self._image(100)
        p = os.path.join(self.tmp, 'ms.docx'); d = docx.Document(); d.add_paragraph('Figure 1. Raman spectrum.'); d.add_picture(io.BytesIO(img.png())); d.save(p)
        self.assertEqual(len(FT.sources(p)), 1)
        fig = FT.figure(p, 0)
        self.assertEqual((fig.w, fig.h), (img.w, img.h)); self.assertEqual(len(FT.frames(fig)), 1)


if __name__ == '__main__':
    unittest.main()
