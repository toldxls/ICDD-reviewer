"""Unit tests for pxrd_review.lints and pxrd_review.proposal — synthetic text and a synthetic manuscript.

    python3 -m unittest tests.test_proposal -v
"""
import os, shutil, tempfile, unittest

from pxrd_review import lints as LI, proposal as PR
from tests.test_bv_check import RUTILE, _write


class Lints(unittest.TestCase):
    def test_spectroscopy(self):
        t = ('Raman spectroscopy was conducted on a Horiba XploRA PLUS with a 100× objective. The spectrum was obtained using a 248 nm laser. '
             'The broad band from 3600 to 2800 cm-1, with shoulders at 3483, 2922 and 2848 cm-1, is the O–H stretching of hydrogen-bonded water. '
             'A weak band at 2349 cm-1 is also assigned to water.')
        f = [m for m, _a in LI.spectro(t)]
        self.assertTrue(any('2848 and 2922' in m and 'C–H' in m for m in f), f)
        self.assertTrue(any('248 nm laser on a Horiba XploRA' in m and '532/638/785' in m for m in f), f)
        self.assertTrue(any('2349' in m and 'CO2' in m for m in f), f)
        self.assertEqual(LI.spectro('A LabRAM HR with a 532 nm laser. Bands at 3400 and 1630 cm-1 are the water modes; the 2920 cm-1 band is C–H of the epoxy.'), [])

    def test_notation(self):
        paras = ['Cleavage is expected on [110] and [010] based on the structure.', 'Twinning by rotation about [110] is common.',
                 'Table 2. Powder data for the mineral.', 'Table 2. Powder data for Mg-arsenate.', 'Figure 1. Crystals.']
        codes = {0: {'caption': 5, 'codes': {'2': ([[-1, 0, 0], [0, 1, 0], [0, 0, -1]], [1, 0, 1], '-x+1, y, -z+1')}},
                 1: {'caption': 6, 'codes': {'2': ([[-1, 0, 0], [0, 1, 0], [0, 0, -1]], [0, 0, 0], '-x, y, -z')}}}
        codes[2] = {'caption': 7, 'codes': codes[1]['codes']}                       # inherited: not a second definition
        f = [m for m, _a in LI.notation(paras, codes)]
        self.assertEqual(sum('zone symbol [110]' in m for m in f), 1, f)             # the cleavage, not the twin axis
        self.assertTrue(any('Table 2 has 2 captions' in m for m in f), f)
        self.assertEqual(sum('symmetry code (2)' in m for m in f), 1, f)


class Proposal(unittest.TestCase):
    def test_review_writes_report_and_copy(self):
        tmp = tempfile.mkdtemp(prefix='prop_')
        try:
            _write(tmp, 'testite.cif', RUTILE)
            from docx import Document
            doc = Document()
            doc.add_paragraph('Testite, ideal formula TiO2, is a new mineral (Smith et al., 2020). Cleavage on [110].')
            doc.add_paragraph('Density (calc.) = 4.250 g·cm–3 for the ideal formula.')
            doc.add_paragraph('The Ti2 site is octahedral.')
            doc.add_paragraph('References')
            doc.add_paragraph('Jones, A. (2019) Another paper. Journal, 1, 1–2.')
            path = os.path.join(tmp, 'testite manuscript.docx'); doc.save(path)
            docx, cif, cc = PR.find_files(tmp)
            self.assertEqual((os.path.basename(docx), os.path.basename(cif), cc), ('testite manuscript.docx', 'testite.cif', None))
            res = PR.review(tmp, quiet=True)
            text = open(res['report'], encoding='utf-8').read()
            self.assertIn('== references', text); self.assertIn('== .cif audit', text); self.assertIn('== lints (notes)', text)
            self.assertIn('site Ti2 is named in the text', text)
            self.assertIn('cleavage given as the zone symbol [110]', text)
            self.assertTrue(os.path.exists(res['copy']))
            self.assertGreaterEqual(res['comments'], 1)
            self.assertEqual(res['unplaced'], [])
            # the copy carries the comments; the source is untouched
            from docx import Document as D
            d2 = D(res['copy']); self.assertTrue(any('comments.xml' in str(p.partname) for p in d2.part.package.parts))
            self.assertEqual(len(Document(path).paragraphs), 5)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
