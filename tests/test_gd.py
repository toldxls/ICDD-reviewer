"""Unit tests for pxrd_review.gd — Gladstone–Dale compatibility.

    python3 -m unittest tests.test_gd -v
"""
import os, shutil, tempfile, unittest

from pxrd_review import gd as G
from tests.test_bv_check import RUTILE, _write


SPANOITE = {'Tl2O': 36.05, 'V2O5': 15.43, 'UO3': 48.52}          # the owner's own spreadsheet
OWNER_UO3 = {'UO3': 0.134}      # what those spreadsheets use for a uranyl mineral; see below


class GD(unittest.TestCase):
    def test_constants_and_kc(self):
        K = G.constants()
        self.assertAlmostEqual(K['H2O']['k'], 0.340)
        self.assertAlmostEqual(K['UO3']['k'], 0.118)                   # Mandarino 1981 Table 7
        kc, rows = G.kc(SPANOITE)
        self.assertAlmostEqual(kc, 0.15117, places=4)
        kc2, rows2 = G.kc({'Xy2O3': 50, 'H2O': 50})
        self.assertIsNone(rows2[0][2]); self.assertAlmostEqual(kc2, 0.170, places=3)

    def test_the_owners_uranyl_constant_is_still_reachable(self):
        """The owner's spreadsheets use UO3 = 0.134 for uranyl minerals and their spanoite sheet
        comes out superior on it; Table 7 gives 0.118, and on the 22 corpus papers whose analysis
        carries UO3 that value reproduces the paper's OWN published compatibility index for 12 of
        them against 5 for 0.134, which is why the file follows Table 7. The owner's value is kept
        as a variant, and --k reaches it — this pins that route so the old sheets stay reproducible."""
        self.assertIn(0.134, [v['k'] for v in G.constants()['UO3']['variants']])
        kc, _rows = G.kc(SPANOITE, k_override=OWNER_UO3)
        self.assertAlmostEqual(kc, 0.1589, places=4)
        res = G.evaluate(SPANOITE, 2.062, density=6.69, k_override=OWNER_UO3)
        self.assertEqual(G.category(res['CI_meas']), 'superior')

    def test_ammonium_and_the_rare_earths_are_now_known(self):
        """The two families Table 7 supplied that the file had no constants for at all."""
        K = G.constants()
        self.assertAlmostEqual(K['N2H8O']['k'], 0.483)                 # (NH4)2O, as epma names it
        self.assertAlmostEqual(K['(NH4)2O']['k'], 0.483)               # the alias a person would type
        for ox in ('Pr2O3', 'Sm2O3', 'Eu2O3', 'Gd2O3', 'Tb2O3', 'Dy2O3', 'Ho2O3', 'Er2O3', 'Tm2O3', 'Yb2O3', 'Lu2O3'):
            self.assertIn(ox, K)
        # mascagnite (NH4)2SO4, n 1.527, D 1.77 — the constant reproduces it to a thousandth
        kc, _ = G.kc({'N2H8O': 39.4, 'SO3': 60.6})
        self.assertLess(abs(1 - ((1.527 - 1) / 1.77) / kc), 0.005)

    def test_formula_to_wt(self):
        wt, fw = G.formula_to_wt({'Ca': 1, 'S': 1, 'H2O': 2})                # gypsum
        self.assertAlmostEqual(fw, 172.17, places=1)
        self.assertAlmostEqual(wt['CaO'], 32.57, places=1); self.assertAlmostEqual(wt['SO3'], 46.50, places=1)
        wt, fw = G.formula_to_wt({'Ca': 5, 'P': 3, 'F': 1})                 # fluorapatite: O=F corrected weight
        self.assertAlmostEqual(fw, 504.3, places=0)
        self.assertIn('O=F,Cl', wt)

    def test_evaluate_with_measured_and_calculated_density(self):
        res = G.evaluate(SPANOITE, 2.062, density=6.69, k_override=OWNER_UO3)
        self.assertAlmostEqual(res['CI_meas'], 0.001, places=3)         # the owner's sheet, on its own UO3
        self.assertEqual(G.category(res['CI_meas']), 'superior')
        tmp = tempfile.mkdtemp(prefix='gd_')
        try:
            cif = _write(tmp, 'rutile.cif', RUTILE.replace('_chemical_name_mineral rutile', '_chemical_name_mineral rutile\n_cell_formula_units_Z 2'))
            wt, fw = G.formula_to_wt({'Ti': 1})
            res = G.evaluate(wt, 2.75, cif=cif, fw=fw)                        # rutile: D_calc ≈ 4.25, n ≈ 2.75
            self.assertAlmostEqual(res['D_calc'], 4.25, places=1)
            self.assertAlmostEqual(res['KC'], 0.393, places=3)
            self.assertLess(abs(res['CI_calc']), 0.06)
            out = G.write_xlsx(res, os.path.join(tmp, 'x.xlsx'))
            self.assertTrue(os.path.exists(out))
            self.assertIn('K_P', G.report_text(res))
            # the workbook's formulas give the tool's numbers — from the formula: apfu -> mass -> formula weight -> wt% -> K_C -> D_calc -> index
            from tests.xl_eval import Book
            res = G.prepare(formula='Ca=5,P=3,F=1', n=1.633, density=3.20, cif=cif, z=2)
            b = Book(G.write_xlsx(res, os.path.join(tmp, 'f.xlsx'))); ws = b.wb['GD']
            lab = {}
            for c in ws['A']:
                if isinstance(c.value, str):
                    lab.setdefault(c.value, []).append(c.row)
            val = lambda name, col='B', i=0: b.value('GD', '%s%d' % (col, lab[name][i]))
            self.assertAlmostEqual(val('K_C', 'D'), res['KC'], places=9)
            self.assertAlmostEqual(val('formula weight', 'B'), res['fw'], places=6)
            self.assertAlmostEqual(val('D calculated'), res['D_calc'], places=6)
            self.assertAlmostEqual(val('compatibility', i=0), res['CI_meas'], places=9)
            self.assertAlmostEqual(val('compatibility', i=1), res['CI_calc'], places=9)
            self.assertEqual(val('compatibility', 'D', 0), G.category(res['CI_meas']))
            for key, w, k, c_, src in res['rows']:
                self.assertAlmostEqual(val(key), w, places=9, msg=key)            # wt% from the formula, the O=F correction in the weight
            res = G.evaluate(SPANOITE, 2.062, density=6.69, k_override=OWNER_UO3)   # the wt% route: values in, the rest live
            b = Book(G.write_xlsx(res, os.path.join(tmp, 'w.xlsx')))
            r_kc = next(c.row for c in b.wb['GD']['A'] if c.value == 'K_C')
            self.assertAlmostEqual(b.value('GD', 'D%d' % r_kc), res['KC'], places=9)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class CheckSheet(unittest.TestCase):
    """The workbook's check sheet: the paper's stated index against the tool's, and what would explain a difference."""
    WT = {'MgO': 30.0, 'SiO2': 42.0, 'FeO': 12.0, 'H2O': 8.0}                       # 92.0 %: short of 100

    def _book(self, tmp, paper, name='c.xlsx', **kw):
        from tests.xl_eval import Book
        res = G.evaluate(dict(self.WT), 1.580, density=2.60, **kw)
        b = Book(G.write_xlsx(res, os.path.join(tmp, name), 'testite', paper)); wc = b.wb['check']
        lab = {c.value: c.row for c in wc['A'] if isinstance(c.value, str)}
        return res, b, lab, (lambda key: b.value('check', 'E%d' % next(r for k_, r in lab.items() if k_.startswith(key))))

    def test_what_explains_the_papers_index(self):
        tmp = tempfile.mkdtemp(prefix='gdchk_')
        try:
            res = G.evaluate(dict(self.WT), 1.580, density=2.60)
            ci = res['CI_meas']
            # the paper's index is the tool's: said so, nothing coloured
            res, b, lab, read = self._book(tmp, {'ci': round(ci, 3), 'category': G.category(ci)})
            self.assertTrue(read('1 − K_P/K_C, measured').startswith("ok — reproduces"), read('1 − K_P/K_C, measured'))
            self.assertTrue(read('category').startswith('ok'), read('category'))
            self.assertAlmostEqual(b.value('check', 'B%d' % lab['1 − K_P/K_C, measured density']), ci, places=9)
            # the paper took Mandarino's constant for MgO in sulfates (0.225, not 0.200): amber above, and the line that explains it
            alt = G.evaluate(dict(self.WT), 1.580, density=2.60, k_override={'MgO': 0.225})['CI_meas']
            self.assertGreater(abs(alt - ci), 0.01)
            res, b, lab, read = self._book(tmp, {'ci': round(alt, 4)})
            self.assertFalse(read('1 − K_P/K_C, measured').startswith('ok — reproduces'))
            self.assertIn("EXPLAINS IT — the paper took Mandarino's other constant for MgO", read('MgO with k = 0.225'))
            self.assertEqual(read('the analysis normalised to 100 %'), 'does not reproduce it')
            # the paper normalised its 97 % analysis to 100 before taking K_C
            norm = 1 - res['KP_meas'] / (res['KC'] * 100 / sum(self.WT.values()))
            res, b, lab, read = self._book(tmp, {'ci': round(norm, 4)})
            self.assertIn('EXPLAINS IT — the paper normalised its analysis to 100 %', read('the analysis normalised to 100 %'))
            self.assertTrue(read('Σ wt% of the analysis').startswith('note'), read('Σ wt% of the analysis'))
            # what would give the paper's index: the K_C needed is the normalised one
            self.assertAlmostEqual(b.value('check', 'B%d' % lab['K_C (measured density)']), res['KC'] * 100 / 92.0, places=3)
            # arithmetic is red: a category word that is not the category of the paper's own number
            res, b, lab, read = self._book(tmp, {'ci': 0.075, 'category': 'superior'})
            self.assertTrue(read('category').startswith('PROBLEM') and 'fair' in read('category'), read('category'))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_h_atoms_are_two_to_a_water(self):
        self.assertAlmostEqual(G.formula_to_wt({'Mg': 1, 'H': 2})[1], G.formula_to_wt({'Mg': 1, 'H2O': 1})[1], places=9)   # brucite either way

    def test_a_fluoride_totals_100_and_a_word_needs_no_density(self):
        from tests.xl_eval import Book
        tmp = tempfile.mkdtemp(prefix='gdchk_')
        try:
            # an ideal fluorite: the total carries the O ≡ F deduction (it read 120.49), so no 'normalised to 100 %' explanation is invented
            res = G.prepare(formula='Ca=1,F=2', n=1.434, density=3.18)
            b = Book(G.write_xlsx(res, os.path.join(tmp, 'f.xlsx'), 'fluorite', {'ci': 0.053})); wc = b.wb['check']
            lab = {c.value: c.row for c in wc['A'] if isinstance(c.value, str)}
            r = lab['Σ wt% of the analysis']
            self.assertAlmostEqual(b.value('check', 'B%d' % r), 100.0, places=6); self.assertEqual(b.value('check', 'E%d' % r), 'ok')
            norm = next(v for k_, v in lab.items() if k_.startswith('the analysis normalised to 100 %'))
            self.assertNotIn('EXPLAINS', b.value('check', 'E%d' % norm))
            # a wt% analysis with the deduction a table prints
            res = G.prepare(wt='CaO=55.6,P2O5=42.2,F=3.77,O=F=-1.59', n=1.63, density=3.2)
            b = Book(G.write_xlsx(res, os.path.join(tmp, 'w.xlsx'), 'apatite', {'ci': 0.01}))
            lab = {c.value: c.row for c in b.wb['check']['A'] if isinstance(c.value, str)}
            self.assertAlmostEqual(b.value('check', 'B%d' % lab['Σ wt% of the analysis']), 55.6 + 42.2 + 3.77 - 1.59, places=6)
            # no density at all: the paper's word is still judged against the paper's own number
            res = G.prepare(wt='SiO2=100', n=1.55)
            for word, want in (('superior', 'ok'), ('poor', 'PROBLEM')):
                b = Book(G.write_xlsx(res, os.path.join(tmp, 'n.xlsx'), 'q', {'ci': 0.01, 'category': word}))
                lab = {c.value: c.row for c in b.wb['check']['A'] if isinstance(c.value, str)}
                self.assertTrue(b.value('check', 'E%d' % lab['category']).startswith(want), b.value('check', 'E%d' % lab['category']))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
