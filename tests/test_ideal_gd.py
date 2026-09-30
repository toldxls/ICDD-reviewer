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

    def test_an_ideal_formula_with_a_comma_in_its_brackets_is_read_whole(self):
        f, counts = PE.ideal_formula('The ideal formula is Ba3(Mg,Fe)Si2O8, which requires BaO 60.')
        self.assertEqual(f, 'Ba3(Mg,Fe)Si2O8'); self.assertIn('Ba', counts)
        self.assertIsNone(PE.ideal_formula('The ideal formula is Ba3(Mg'))                     # cut short: not read

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


class ChargeBalance(unittest.TestCase):
    EX = {'name': None, 'epma': {'rows': [{'constituent': 'MgO', 'mean': 17.7}, {'constituent': 'As2O5', 'mean': 45.9}, {'constituent': 'H2O', 'mean': 36.0}]}}

    def test_balanced_formula_is_silent(self):
        t = 'The empirical formula, calculated on the basis of Mg = 1, is Mg1.00As1.00O8.00H9.00.'
        self.assertEqual(PE.charge_balance_check(t, self.EX), [])

    def test_an_o_count_one_short_is_a_finding(self):
        t = 'The empirical formula, calculated on the basis of Mg = 1, is Mg1.00As1.00O7.00H9.00.'
        L = PE.charge_balance_check(t, self.EX)
        self.assertEqual(len(L), 2, L)
        self.assertIn('O7.00 printed vs O8.00 from the charges', L[1]); self.assertIn('As+5 from the analysis', L[1])

    def test_a_quarter_o_is_information(self):
        t = 'The empirical formula, calculated on the basis of Mg = 1, is Mg1.00As1.00O7.70H9.00.'
        L = PE.charge_balance_check(t, self.EX)
        self.assertEqual(len(L), 1, L); self.assertIn('information', L[0]); self.assertNotIn(' vs ', L[0])

    def test_a_variable_valence_with_no_source_stops_the_sum(self):
        t = 'The empirical formula is Fe1.00As1.00O5.00.'
        L = PE.charge_balance_check(t, {'name': None, 'epma': {'rows': [{'constituent': 'As2O5', 'mean': 50.0}]}})
        self.assertEqual(L, ['charge balance: not summed — the valence of Fe is stated nowhere the tool reads'])
        # the formula's own superscript decides
        t = 'The empirical formula is Fe3+1.00As1.00O4.00.'
        self.assertEqual(PE.charge_balance_check(t, {'name': None, 'epma': {'rows': [{'constituent': 'As2O5', 'mean': 50.0}]}}), [])


class ParameterSetFit(unittest.TestCase):
    URANYL = """data_u
_cell_length_a 10
_cell_length_b 10
_cell_length_c 10
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_space_group_name_H-M_alt 'P 1'
loop_
_space_group_symop_operation_xyz
'x, y, z'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
U1 U6+ 0 0 0
O1 O 0.18 0 0
O2 O 0 0.235 0
"""

    def test_the_set_behind_printed_valences_is_named_and_a_cited_other_set_is_a_finding(self):
        import math, tempfile, shutil, os
        from pxrd_review import bv_check as B
        tmp = tempfile.mkdtemp(prefix='setfit_')
        try:
            path = os.path.join(tmp, 'u.cif'); open(path, 'w').write(self.URANYL)
            st = B.Structure(path); P = B.Params()
            rows = {rid: (r0, b) for r0, b, rid, det in P.table[('U', 6, 'O', -2)]}
            Rs = (1.78, 1.80, 2.30, 2.45, 2.50)
            burns = [('U1', 'O1', R, round(math.exp((rows['r'][0] - R) / rows['r'][1]), 2)) for R in Rs]
            L = PE.set_fit_lines(burns, st, cited=None)
            self.assertEqual(len(L), 2, L); self.assertIn('Burns et al. (1997)', L[1]); self.assertNotIn(' vs ', L[1])
            L = PE.set_fit_lines(burns, st, cited='gh')                      # the text cites Gagné & Hawthorne; the numbers are Burns'
            self.assertIn('follow Burns et al. (1997)', L[1]); self.assertIn(' vs the Gagné and Hawthorne (2015) the text cites', L[1])
            gh = [('U1', 'O1', R, round(math.exp((rows['bs'][0] - R) / rows['bs'][1]), 2)) for R in Rs]
            L = PE.set_fit_lines(gh, st, cited='gh'); self.assertIn('Gagné and Hawthorne (2015)', L[1]); self.assertNotIn(' vs ', L[1])
            L = PE.set_fit_lines([('U1', 'O1', R, 0.9) for R in (1.8, 2.4)], st, None); self.assertIn('no set the tool carries reproduces', L[1])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class EpmaTableLint(unittest.TestCase):
    def test_range_sd_n_and_beam(self):
        text = ('Chemical analyses (mean of 6 analyses) were made with a 10 μm beam diameter. Crystals are up to 8 μm across. '
                'The composition is given in Table 1.')
        ex = {'epma': {'caption': 'Table 1. Chemical data (wt%) for testite (mean of 6 analyses).',
                       'rows': [{'constituent': 'MgO', 'mean': 21.5, 'sd': 0.25, 'range': (22.1, 23.9)},        # the mean outside its range
                                {'constituent': 'As2O5', 'mean': 50.0, 'sd': 0.20, 'range': (47.0, 53.0)},      # s.d. 0.20 vs at least 3/√5 = 1.34
                                {'constituent': 'CoO', 'mean': 2.0, 'sd': 1.4, 'range': (0.5, 3.6)},           # within the bound
                                {'constituent': 'H2O', 'mean': 30.0, 'sd': None, 'range': None}]}}
        L = PE.epma_table_lint(ex, text)
        self.assertTrue(L and L[0].startswith('analytical table: 4 constituents, n = 6'), L)
        self.assertTrue(any(x.startswith('MgO: mean 21.5 vs its range 22.1–23.9') for x in L), L)
        self.assertTrue(any(x.startswith('As2O5: s.d. 0.2 vs at least 1.34') for x in L), L)
        self.assertFalse(any('CoO' in x for x in L), L)                                                    # scatter alone is not judged: the s.d. column is not read reliably enough
        self.assertTrue(any('beam (10 µm) is as wide as the largest grains named (8 µm)' in x for x in L), L)
        # within Samuelson's bound, no n printed: nothing
        ex2 = {'epma': {'rows': [{'constituent': 'MgO', 'mean': 22.9, 'sd': 0.7, 'range': (22.1, 23.9)}]}}
        self.assertEqual(PE.epma_table_lint(ex2, 'No count here.'), [])
        self.assertEqual(PE.analyses_count('The mean of 12 analyses is given.'), 12); self.assertEqual(PE.analyses_count('nothing'), None)


class Dominance(unittest.TestCase):
    def test_a_leader_inside_the_scatter_is_a_finding(self):
        text = 'The empirical formula, based on 4 O apfu, is (Mn0.524Ca0.476)Σ1.00(Mg0.90Fe2+0.10)Σ1.00Si1.00O4.'
        ex = {'name': None, 'epma': {'rows': [{'constituent': 'MnO', 'mean': 18.1, 'sd': 1.2, 'range': (16.2, 19.8)},
                                              {'constituent': 'CaO', 'mean': 13.0, 'sd': 1.0, 'range': (11.7, 14.5)},
                                              {'constituent': 'MgO', 'mean': 17.7, 'sd': 0.3, 'range': (17.2, 18.1)},
                                              {'constituent': 'FeO', 'mean': 3.5, 'sd': 0.2, 'range': (3.2, 3.8)},
                                              {'constituent': 'SiO2', 'mean': 29.3, 'sd': 0.3, 'range': None}]}}
        L = PE.dominance_check(text, ex)
        self.assertTrue(L and L[0].startswith('dominance within the scatter'), L)
        self.assertTrue(any(x.startswith('(Mn0.524Ca0.476): Mn leads Ca by 0.048 apfu vs the analytical scatter') and 'not established' in x for x in L), L)
        self.assertTrue(any('the ranges cross' in x and 'Mn' in x for x in L), L)
        self.assertFalse(any('Mg' in x for x in L), L)                                          # 0.90 vs 0.10: not in doubt
        # a clear leader: nothing
        self.assertEqual(PE.dominance_check('The empirical formula is (Mn0.80Ca0.20)Σ1.00Si1.00O3.', ex), [])


if __name__ == '__main__':
    unittest.main()
