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
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
