"""Unit tests for pxrd_review.gd — Gladstone–Dale compatibility.

    python3 -m unittest tests.test_gd -v
"""
import os, shutil, tempfile, unittest

from pxrd_review import gd as G
from tests.test_bv_check import RUTILE, _write


class GD(unittest.TestCase):
    def test_constants_and_kc(self):
        K = G.constants()
        self.assertAlmostEqual(K['H2O']['k'], 0.340); self.assertAlmostEqual(K['UO3']['k'], 0.134)
        kc, rows = G.kc({'Tl2O': 36.05, 'V2O5': 15.43, 'UO3': 48.52})
        self.assertAlmostEqual(kc, 0.1589, places=4)                       # the owner's spanoite sheet
        kc2, rows2 = G.kc({'Xy2O3': 50, 'H2O': 50})
        self.assertIsNone(rows2[0][2]); self.assertAlmostEqual(kc2, 0.170, places=3)

    def test_formula_to_wt(self):
        wt, fw = G.formula_to_wt({'Ca': 1, 'S': 1, 'H2O': 2})                # gypsum
        self.assertAlmostEqual(fw, 172.17, places=1)
        self.assertAlmostEqual(wt['CaO'], 32.57, places=1); self.assertAlmostEqual(wt['SO3'], 46.50, places=1)
        wt, fw = G.formula_to_wt({'Ca': 5, 'P': 3, 'F': 1})                 # fluorapatite: O=F corrected weight
        self.assertAlmostEqual(fw, 504.3, places=0)
        self.assertIn('O=F,Cl', wt)

    def test_evaluate_with_measured_and_calculated_density(self):
        res = G.evaluate({'Tl2O': 36.05, 'V2O5': 15.43, 'UO3': 48.52}, 2.062, density=6.69)
        self.assertAlmostEqual(res['CI_meas'], 0.001, places=3)
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
