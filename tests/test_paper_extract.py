"""pxrd_review.paper_extract — a synthetic two-column paper page built with PyMuPDF: the analytical
table, the basis sentence, the H2O statement, optics and a powder table.

    python3 -m unittest tests.test_paper_extract -v
"""
import os, shutil, tempfile, unittest

from pxrd_review import paper_extract as PE


def make_pdf(path):
    import fitz
    doc = fitz.open(); page = doc.new_page(width=595, height=842)
    y = 60
    def line(txt, x=40, dy=14):
        nonlocal y
        page.insert_text((x, y), txt, fontsize=9); y += dy
    line('Testite, a new mineral from Nowhere', dy=18)
    line('The empirical formula, calculated on the basis of 7 O apfu, is Ca1.00Mg2.01Si2.99O7(OH)0.98.', dy=16)
    line('H2O was calculated by difference; the F content is below detection. Optical: alpha = 1.600, beta = 1.610, gamma = 1.620.')
    line('Density (measured by flotation) = 3.120 g/cm3; calculated density = 3.145 g/cm3.')
    line('Bond-valence parameters are from Gagne and Hawthorne (2015); hydrogen-bond strengths from O-O bond lengths (Ferraris and Ivaldi 1988).', dy=20)
    line('Table 1. Chemical data (wt%) for testite.')
    line('Constituent   Mean     Range        S.D.   Standard')
    # the other page column's text at the same baselines
    for row, side in (('CaO  20.10  19.80-20.40  0.21  wollastonite', 'some body text of the right column, with commas'),
                      ('MgO  29.05  28.70-29.60  0.30  forsterite', 'that must not become a standard name'),
                      ('SiO2  46.30  45.90-46.70  0.28  quartz', ''),
                      ('H2O  3.20', 'and a third line of prose here'),
                      ('Total  98.65', '')):
        page.insert_text((40, y), row, fontsize=9)
        if side:
            page.insert_text((330, y), side, fontsize=9)
        y += 14
    y += 14
    line('Table 2. Powder X-ray diffraction data for testite.')
    xs = (40, 80, 130, 180, 230, 245, 260)                      # the columns line up under the header, as in print
    for cells in (('Iobs', 'dobs', 'dcalc', 'Icalc', 'h', 'k', 'l'), ('100', '3.4550', '3.4531', '92', '1', '1', '0'),
                  ('35', '2.9800', '2.9791', '40', '0', '2', '1'), ('12', '2.5010', '2.4997', '9', '2', '0', '0')):
        for x, c in zip(xs, cells):
            page.insert_text((x, y), c, fontsize=9)
        y += 14
    doc.save(path); doc.close()


class Extract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='pe_')
        cls.pdf = os.path.join(cls.tmp, 'testite.pdf'); make_pdf(cls.pdf)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_table_basis_method_optics_bv(self):
        ex = PE.extract(self.pdf, self.tmp, 'testite')
        self.assertEqual(ex['name'], 'testite')
        rows = {r['constituent']: r for r in ex['epma']['rows']}
        self.assertEqual(sorted(rows), ['CaO', 'H2O', 'MgO', 'SiO2'])
        self.assertEqual((rows['CaO']['mean'], rows['CaO']['range'], rows['CaO']['sd'], rows['CaO']['standard']), (20.1, (19.8, 20.4), 0.21, 'wollastonite'))
        self.assertEqual(rows['MgO']['standard'], 'forsterite')          # the other column's prose is not a standard
        self.assertIsNone(rows['H2O']['range']); self.assertEqual(ex['epma']['total'], 98.65)
        self.assertEqual(ex['basis'], ('O', 7.0)); self.assertIn('basis of 7 O', ex['basis_sentence'])
        self.assertEqual(ex['method']['h2o'], 'difference'); self.assertTrue(any('by difference' in s for s in ex['method']['sentences']))
        self.assertAlmostEqual(ex['optics']['n'], 1.61, places=4); self.assertEqual((ex['optics']['D_meas'], ex['optics']['D_calc']), (3.12, 3.145))
        self.assertEqual((ex['bv']['params'], ex['bv']['hb']), ('gh', 'oo'))
        self.assertEqual((ex['pxrd']['obs'], ex['pxrd']['calc']), (3, 3))
        self.assertEqual(sorted(ex['files']), ['calc', 'epma', 'obs'])
        with open(os.path.join(self.tmp, ex['files']['epma'])) as f:
            head, vals = f.read().splitlines()
        self.assertEqual(head.split(','), ['CaO', 'MgO', 'SiO2', 'H2O']); self.assertEqual(vals.split(',')[0], '20.1')
        with open(os.path.join(self.tmp, ex['files']['calc'])) as f:
            self.assertIn('3.4531 92 1 1 0', f.read())
        self.assertEqual(PE.basis_string(ex['basis']), 'O=7')


if __name__ == '__main__':
    unittest.main()
