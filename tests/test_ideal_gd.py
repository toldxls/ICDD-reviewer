"""Unit tests for the ideal-formula, Gladstone–Dale grid, basis-free ratio and density-statement readers.

    python3 -m unittest tests.test_ideal_gd -v
"""
import os, shutil, tempfile, unittest

from pxrd_review import paper_extract as PE, epma as EP

TEXT = ("The empirical formula, calculated on the basis of Mg = 1, is Mg1.00As0.91O7.75H9. "
        "The ideal formula is Mg(AsO3OH)·4H2O, which requires MgO 17.06, As2O5 48.63, H2O 34.41, total 100.00 wt%. "
        "Biaxial (–), α = 1.502(2), β = 1.512(2), γ = 1.518(2). "
        "Density (calc.) = 2.257 g·cm–3 for the ideal formula. "
        "The Gladstone-Dale compatibility, 1 – (Kp/Kc), is –0.043 (good) for the empirical formula and 0.031 (excellent) for the ideal formula.")


class Readers(unittest.TestCase):
    def test_density_statement_forms(self):
        for t, key, v in (('Density (calc.) = 2.257 g·cm–3 for the ideal formula.', 'D_calc', 2.257),
                          ('Density (for above formula)\t2.261 g cm–3', 'D_calc', 2.261),
                          ('Density (meas.) = 2.25(2) g/cm3 by flotation.', 'D_meas', 2.25)):
            self.assertEqual(PE.optics(t)[key], v, t)

    def test_every_stated_index(self):
        g = PE.gd_statement(TEXT)
        self.assertEqual(g['ci'], -0.043); self.assertEqual(g['category'], 'good')
        self.assertEqual([(x['ci'], x['category'], x['for']) for x in g['all']], [(-0.043, 'good', 'empirical'), (0.031, 'excellent', 'ideal')])

    def test_ideal_formula_and_its_wt(self):
        f, counts = PE.ideal_formula(TEXT)
        self.assertEqual(f, 'Mg(AsO3OH)·4H2O'); self.assertEqual(counts, {'Mg': 1.0, 'As': 1.0, 'O': 8.0, 'H': 9.0})
        wt = PE.ideal_wt(counts)
        self.assertAlmostEqual(wt['MgO'], 17.06, places=1); self.assertAlmostEqual(wt['As2O5'], 48.63, places=1); self.assertAlmostEqual(wt['H2O'], 34.31, places=1)

    def test_ideal_wt_check_finds_the_typo_and_the_total(self):
        L = PE.ideal_wt_check(TEXT, {'epma': {}})
        self.assertTrue(L and L[0].startswith('ideal formula: Mg(AsO3OH)·4H2O gives'), L)
        self.assertTrue(any('H2O 34.41 in the text vs 34.31' in x for x in L), L)
        self.assertTrue(any('add to 100.10 vs the total printed, 100.00' in x for x in L), L)
        self.assertFalse(any('MgO' in x and ' vs ' in x for x in L), L)                       # 17.06 is right
        # the table's Ideal column too
        ex = {'epma': {'head_cells': [('Constituent', 70.0), ('Mean', 120.0), ('Ideal', 400.0)],
                       'rows_all': [{'constituent': 'H2O', 'all': [0.0, 34.61], 'xs': [120.0, 400.0]}]}}
        L = PE.ideal_wt_check(TEXT, ex)
        self.assertTrue(any("H2O 34.61 in the table's Ideal column vs 34.31" in x for x in L), L)
        self.assertEqual(PE.ideal_wt_check('No ideal formula here. Density 3.2.', {'epma': {}}), [])

    def test_basis_free_ratios(self):
        ex = {'epma': {'rows': [{'constituent': 'MgO', 'mean': 21.82, 'sd': 0.65}, {'constituent': 'As2O5', 'mean': 56.74, 'sd': 1.73}]}}
        L = PE.basis_free_ratios(ex, {'Mg': 1.0, 'As': 1.0, 'O': 8.0, 'H': 9.0})
        self.assertEqual(len(L), 2, L); self.assertIn('Mg:As = 1.097', L[1]); self.assertIn('information', L[1])      # 2σ on the s.d. alone
        L = PE.basis_free_ratios(ex, {'Mg': 1.0, 'As': 1.0, 'O': 8.0, 'H': 9.0}, n_points=11)
        self.assertIn('whatever the basis', L[1]); self.assertIn('n = 11', L[1])                                        # 7σ on the s.d. of the means
        self.assertEqual(PE.basis_free_ratios(ex, {'Mg': 1.1, 'As': 1.0, 'O': 8.0}), [])                              # within scatter: nothing

    def test_gd_grid(self):
        ex = {'optics': PE.optics(TEXT), 'epma': {'rows': [{'constituent': 'MgO', 'mean': 17.66}, {'constituent': 'As2O5', 'mean': 45.92}, {'constituent': 'H2O', 'mean': 35.99}], 'total': 99.57}, '_text': TEXT}
        L = PE.gd_grid(ex, {'counts': {'Mg': 1.0, 'As': 0.91, 'O': 7.75, 'H': 9.0}}, PE.gd_statement(TEXT))
        self.assertTrue(L and L[0].startswith('Gladstone–Dale, the statements one by one'), L)
        self.assertEqual(len(L), 3, L)
        self.assertTrue(any('stated +0.031 (excellent) for the ideal formula' in x for x in L), L)
        self.assertTrue(any("not of the ideal formula it is stated for" in x or 'reproduced by no combination' in x or 'slack' in x for x in L), L)


class BasisSensitivity(unittest.TestCase):
    def test_alternatives(self):
        tmp = tempfile.mkdtemp(prefix='ep_')
        try:
            csv = os.path.join(tmp, 'p.csv')
            with open(csv, 'w') as f:
                f.write('MgO,CoO,As2O5\n21.82,0.54,56.74\n22.10,0.50,57.20\n')
            ds, red, table, text = EP.prepare(csv, 'Mg+Co=1', adds=['H2O=structure:4.5'])
            alts = EP.basis_sensitivity(ds, red, adds=[EP._parse_add('H2O=structure:4.5')])
            labels = [a[0] for a in alts]
            self.assertEqual(labels[0], 'Mg+Co = 1.0 apfu')
            self.assertIn('As = 1 apfu', labels); self.assertIn('2 cations apfu', labels)
            self.assertTrue(alts[0][1].startswith('Mg0.99Co0.01As0.9'), alts[0])
            as1 = dict((a[0], a[1]) for a in alts)['As = 1 apfu']
            self.assertTrue(as1.startswith('Mg1.1'), as1)                                    # the Mg:As ratio is the same on every basis
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
