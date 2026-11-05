"""The .pdf pane's rectangles on rotated pages (issue #14): a word box and a search hit must sit on the word's ink in
the page as it is rendered, at /Rotate 0, 90, 180 and 270.

    python3 -m unittest tests.test_pdf_worker -v
"""
import os, shutil, tempfile, unittest

import pymupdf

from pxrd_review.gui import _pdf_worker as W


def _ink(pix, rect):
    """Share of dark pixels inside rect (page points, the pixmap at 1x)."""
    x0, y0 = max(0, int(rect[0])), max(0, int(rect[1]))
    x1, y1 = min(pix.width, int(rect[2]) + 1), min(pix.height, int(rect[3]) + 1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    dark = sum(pix.pixel(x, y)[0] < 128 for y in range(y0, y1) for x in range(x0, x1))
    return dark / ((x1 - x0) * (y1 - y0))


class RotatedPages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.pdf = os.path.join(cls.tmp, 'rot.pdf')
        doc = pymupdf.open()
        for rot in (0, 90, 180, 270):
            pg = doc.new_page(width=595, height=842)
            pg.insert_text((80, 120), 'WOLFRAMITE', fontsize=28)      # one word, far from the centre: a wrong frame misses it
            pg.set_rotation(rot)
        doc.save(cls.pdf)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_word_boxes_and_search_hits_sit_on_the_ink(self):
        hits = W.search(self.pdf, 'WOLFRAMITE')
        self.assertEqual([p['page'] for p in hits['pages']], [0, 1, 2, 3])
        with pymupdf.open(self.pdf) as doc:
            for n in range(4):
                pix = doc[n].get_pixmap(matrix=pymupdf.Matrix(1, 1), colorspace=pymupdf.csGRAY)
                w = W.words(self.pdf, n)
                self.assertEqual((round(w['w']), round(w['h'])), (pix.width, pix.height), n)
                (box,) = [x for x in w['words'] if x[4] == 'WOLFRAMITE']
                self.assertGreater(_ink(pix, box[:4]), 0.08, 'rotation %d: the word box misses its word' % doc[n].rotation)
                (hit,) = [h['rect'] for h in hits['hits'] if h['page'] == n]
                self.assertGreater(_ink(pix, hit), 0.08, 'rotation %d: the search hit misses its word' % doc[n].rotation)


if __name__ == '__main__':
    unittest.main()
