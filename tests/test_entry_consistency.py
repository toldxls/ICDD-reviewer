"""Docx-internal consistency checks: formula / analysis fields (check27), Xtl Dx vs Dx (check28) and the
Optical Data field (check24). Every case is a defect class found on the corpus (2026-09-14), written as the
entry wrote it, plus the clean forms the rules must leave alone."""
import unittest
from pxrd_review import extra_checks as X


def entry(formulas=None, analysis='', optical='', density=None, z='4'):
    rows = []
    if density:
        rows.append(['Dx :', density.get('Dx', ''), 'Dm :', '', 'Ds :', '', 'Xtl Dx :', density.get('Xtl Dx', ''),
                     'Approximate Density :', '', ''])
    comments = {}
    if analysis:
        comments['Analysis'] = analysis
    if optical:
        comments['Optical Data'] = optical
    return type('E', (), {'formulas': formulas or {}, 'comments': comments, 'raw_rows': rows,
                          'cell': {'Z': z}, 'name': 'testite', 'instr': {}})()


def msgs(findings, sev='flag'):
    return [f.msg for f in findings if f.sev == sev]


class FormulaSyntax(unittest.TestCase):
    def test_valence_read_as_carbon_reported_once_for_both_fields(self):
        f = '( Pb7.89 Na0.11 Ca0.08 ) ( Al2.19 Si0.31 Fe3 C0.20 Zn0.13 Mn2 C0.11 ) Si8 O27.02 Cl2.98'
        e = entry({'Analytical': f, 'Chemical': 'Pb8 Al3 Si8 O27 Cl3'},
                  'Microprobe analysis, average of 6 (wt.%): Na2O 0.14, Al2O3 4.42, SiO2 19.80, Cl 4.19, CaO 0.19, '
                  'MnO 0.31, Fe2O3 0.63, ZnO 0.42, PbO 69.83: ' + f + '.')
        m = msgs(X.check27_formula_integrity(e))
        self.assertEqual(len(m), 1, m)
        self.assertIn('Fe3+0.20, Mn2+0.11', m[0])
        self.assertIn('and the formula in the Analysis field', m[0])

    def test_decimal_point_lost_colon_space_and_brackets(self):
        cases = [('Pb1.00 ( Fe1.95 +3 Al042 Cu0.09 ) ( As1.66 P0.31 ) O7.97 ( O H )6.03', 'Al0.42'),
                 ('( Mo1:00 O3 )3 ! H2 O', 'Mo1.00'),
                 ('[ ( Na2 .86 K0.67 ) ] Mo8 O33.42', 'space inside a coefficient'),
                 ('Y0.59 Ca0.24 ) Cu6.04 ( P2.96 As0.05 ) O12', 'unbalanced brackets')]
        for f, want in cases:
            with self.subTest(f=f):
                self.assertTrue(any(want in x for x in msgs(X.check27_formula_integrity(entry({'Analytical': f})))))

    def test_split_symbol(self):
        e = entry({'Analytical': 'Na3.10 Sr2.29 ( Ce0.55 La0.19 Eu0.01 T B0.01 Dy0.02 ) Si8 O22'})
        self.assertTrue(any('Tb0.01' in x for x in msgs(X.check27_formula_integrity(e))))
        # spaced ICDD groups are not split symbols: 'C O3' (not Co), 'P O4' (not Po), 'N H4'
        clean = entry({'Analytical': '( N H4 )1.12 K0.88 ( Fe0.78 +3 Al0.22 ) ( P O4 )2 ( C O3 )0.82 ! H2 O'})
        self.assertEqual(msgs(X.check27_formula_integrity(clean)), [])

    def test_sigma_markers_are_not_silicon_or_sulfur(self):
        a = ('Microprobe analysis (wt.%): SiO2 45.36, Al2O3 4.35, MnO 34.92, MgO 1.88, CaO 0.42, Na2O 1.49, '
             'K2O 1.14: ( Na0.91 K0.46 Ca0.14 )$S I1.51 ( Mn9.29 Mg0.89 )$S I10.18 [ ( Si14.28 Al1.61 )$S I15.89 O38 ]')
        e = entry({'Analytical': '( Na0.91 K0.46 Ca0.14 ) ( Mn9.29 +2 Mg0.89 ) [ ( Si14.28 Al1.61 ) O38 ]'}, a)
        self.assertEqual(msgs(X.check27_formula_integrity(e)), [])

    def test_simplified_site_in_analytical_row(self):
        e = entry({'Analytical': '( Na0.52 K0.09 ) ( Na1.81 Ca0.19 ) [ ( Mg2.87 Fe0.77 +2 )4 ( Sc , Fe +3 , Mn +3 ) ] O22'})
        self.assertTrue(any('simplified-formula site' in x for x in msgs(X.check27_formula_integrity(e))))


class AnalysisAgainstFormula(unittest.TestCase):
    def test_fluorine_in_formula_not_in_wt_list(self):
        e = entry({'Analytical': 'Na0.97 Ca1.01 Fe0.92 +3 Al1.11 ( P O4 )0.97 F4.85 ( O H )1.32 !0.95 H2 O'},
                  'Microprobe analysis, average of 12 (wt.%): Na2O 8.32, CaO 15.63, Al2O3 15.59, Fe2O3 20.24, '
                  'P2O5 18.97, H2O(calc) 7.97: Na0.97 Ca1.01 Fe0.92 +3 Al1.11 ( P O4 )0.97 F4.85 ( O H )1.32 !0.95 H2 O.')
        m = msgs(X.check27_formula_integrity(e))
        self.assertTrue(any('contains F' in x for x in m), m)

    def test_one_constituent_standing_for_another_is_one_finding(self):
        e = entry({'Analytical': 'Pb0.99 Te3.00 +4 O5 ( O H ) Cl2.65 ( H1.95 O1.15 )'},
                  'Microprobe analysis, average of 8 (wt.%): PbO 27.68, SeO2 59.92, Cl 11.74, H2O(calc) 3.33: '
                  'Pb0.99 Te3.00 +4 O5 ( O H ) Cl2.65 ( H1.95 O1.15 ).')
        m = msgs(X.check27_formula_integrity(e))
        self.assertEqual(len(m), 1, m)
        self.assertIn('SeO2 59.92', m[0])
        self.assertIn('Te', m[0])

    def test_malformed_and_duplicated_constituents(self):
        e = entry({}, 'Microprobe analysis (wt.%): BAO 24.27, CaO 0.29, P205 13.43, SO3 12.07')
        m = msgs(X.check27_formula_integrity(e))
        self.assertTrue(any('BaO?' in x for x in m) and any('P2O5?' in x for x in m), m)
        e = entry({}, 'Microprobe analysis (wt.%): Na2O 0.31, SiO2 57.07, K2O 7.75, CaO 1.12, Mn2O3 19.65, CaO 0.26')
        self.assertTrue(any('CaO twice' in x for x in msgs(X.check27_formula_integrity(e))))
        # prose and an atom list after the wt% are not duplicated constituents
        e = entry({}, 'Microprobe analysis, average of 6 (wt.%): Ca 20.38. Calculated based on 6 O: Ca21.07, C 25.26')
        self.assertEqual(msgs(X.check27_formula_integrity(e)), [])

    def test_analytical_row_disagrees_with_analysis_formula(self):
        e = entry({'Analytical': 'Pb10.8 Sb6.06 As1.74 S21.92'},
                  'Microprobe analysis, average of 4 (wt.%): Pb 57.81(4), As 3.53(8), Sb 20.03(6), S 19.08(6): '
                  'Pb10.336 As1.567 Sb6.088 S22.')
        m = msgs(X.check27_formula_integrity(e))
        self.assertTrue(any('Pb 10.8 vs 10.336' in x for x in m), m)

    def test_an_analysis_that_matches_is_clean(self):
        f = '( Pb4.71 Zn0.36 Fe0.13 ) ( As1.71 Sb0.26 ) Ge1.92 S12'
        e = entry({'Analytical': f, 'Chemical': 'Pb5 ( As S3 )2 ( Ge2 S6 )', 'Empirical': 'As2 Ge2 Pb5 S12'},
                  'Microprobe analysis, average of 18 (wt.%): Pb 57.95, S 22.85, Ge 8.29, As 7.60, Sb 1.84, Zn 1.39, '
                  'Fe 0.44: ( Pb4.71 Zn0.36 Fe0.13 )S5.20 ( As1.71 Sb0.26 )S1.97 Ge1.92 S12.')
        self.assertEqual(X.check27_formula_integrity(e), [])

    def test_element_in_one_ideal_field_only(self):
        e = entry({'Chemical': '$XS Mn2 Mg5 Si8 O22 ( O H )2',
                   'General': '( ( $XS ) , Ca ) ( Mn , Fe )2 ( Mg , Fe , Mn )5 S8 O22 [ ( O H ) , F ]2',
                   'Empirical': 'H2 Mg5 Mn2 O24 Si8',
                   'Analytical': '( ( $XS )0.91 Ca0.07 Na0.02 ) ( Mn1.64 +2 Fe0.36 +2 ) ( Mg3.56 Fe0.91 +2 Mn0.61 +2 ) '
                                 '( Si7.86 Al0.06 ) O22 [ ( O H )1.92 F0.08 ]'})
        m = msgs(X.check27_formula_integrity(e))
        self.assertEqual(m, [m[0]] if m else ['nothing'])
        self.assertIn('General formula contains S,', m[0])
        # without an analysis the General formula's substituents are not evidence of anything
        del e.formulas['Analytical']
        self.assertEqual(msgs(X.check27_formula_integrity(e)), [])


class DensityRatio(unittest.TestCase):
    def test_whole_number_factor_flags(self):
        m = msgs(X.check28_density_consistency(entry(density={'Dx': '4.120', 'Xtl Dx': '8.294'})))
        self.assertEqual(len(m), 1)
        self.assertIn('2×', m[0])
        self.assertIn('1/4×', msgs(X.check28_density_consistency(entry(density={'Dx': '3.035', 'Xtl Dx': '0.771'}), ))[0])

    def test_chemistry_gap_is_a_note_and_close_values_are_silent(self):
        f = X.check28_density_consistency(entry(density={'Dx': '5.240', 'Xtl Dx': '4.246'}))
        self.assertEqual([x.sev for x in f], ['note'])
        self.assertEqual(X.check28_density_consistency(entry(density={'Dx': '3.283', 'Xtl Dx': '3.093'})), [])
        self.assertEqual(X.check28_density_consistency(entry(density={'Dx': '', 'Xtl Dx': '3.388'})), [])


class OpticalField(unittest.TestCase):
    def test_sign_that_is_not_a_sign(self):
        e = entry(optical='A=1.613(4), B= 1.626(3), Q=1.633(5), Sign=1, 2V(calc)=72°')
        self.assertTrue(any('Sign=1' in x for x in msgs(X.check24_optical_2v(e))))

    def test_mistyped_esd_parenthesis_and_collapsed_esd(self):
        e = entry(optical='A=1.790(7), B=1.800(70, Q=1.815(8), Sign=+, 2V=80(5)°')
        self.assertTrue(any('closing parenthesis' in x for x in msgs(X.check24_optical_2v(e))))
        e = entry(optical='A=1.538(2), B=1.599(2), Q=1.6142, Sign=-, 2V=52(2)°')
        self.assertTrue(any('1.614(2)?' in x for x in msgs(X.check24_optical_2v(e))))
        # a calculated index without an esd is ordinary
        self.assertEqual(msgs(X.check24_optical_2v(entry(optical='A=1.890(5), Q=1.894, Sign=+'))), [])

    def test_uniaxial_sign_against_indices(self):
        e = entry(optical='B=1.656(3), Q=1.662(3), Sign=-')
        self.assertTrue(any('ω and ε swapped' in x for x in msgs(X.check24_optical_2v(e))))
        self.assertEqual(msgs(X.check24_optical_2v(entry(optical='B=1.785(5), Q=1.765(5), Sign=-'))), [])

    def test_reflectance_parked_in_optical_data_is_not_an_esd_fault(self):
        e = entry(optical='R%(air): 30.6-29.8 (470nm); 30.3-29.2 (546nm), 29.7-28.7 (589nm); 28.1-27.4( 650nm).')
        self.assertEqual(msgs(X.check24_optical_2v(e)), [])


def powder(rows, spacing='Diffractometer'):
    return type('E', (), {'refl': rows, 'instr': {'spacing_instr': spacing}, 'name': 'testite'})()


class ReflectionsAgainstPaper(unittest.TestCase):
    ROWS = [('%.4f' % d, '10', '1', '0', '0') for d in (8.123, 6.412, 5.207, 4.388, 3.9021, 3.2200, 2.9714, 2.6532, 2.4105)]

    def table(self, rows):
        return 'Table 3. Powder X-ray diffraction data ' + ' '.join('%s 10 %s' % (d, 'x') for d, *_ in rows)

    def test_one_line_not_printed_is_flagged_with_the_keystroke_neighbour(self):
        printed = [r for r in self.ROWS if r[0] != '3.2200'] + [('3.322',)]
        m = msgs(X.check29_reflections_in_paper(powder(self.ROWS), self.table(printed)))
        self.assertEqual(len(m), 1, m)
        self.assertIn('3.2200', m[0])
        self.assertIn('3.322', m[0])

    def test_a_list_the_paper_does_not_print_says_nothing(self):
        self.assertEqual(X.check29_reflections_in_paper(powder(self.ROWS), 'Table 3. ' + '3.9021 2.9714'), [])
        # nor a calculated pattern, nor a short list
        text = self.table(self.ROWS[:5])
        self.assertEqual(X.check29_reflections_in_paper(powder(self.ROWS, 'Calculated'), text), [])
        self.assertEqual(X.check29_reflections_in_paper(powder(self.ROWS[:7]), self.table(self.ROWS[:6])), [])

    def test_padding_is_not_a_difference(self):
        text = self.table([(d.rstrip('0'),) for d, *_ in self.ROWS])
        self.assertEqual(X.check29_reflections_in_paper(powder(self.ROWS), text), [])

    def test_strongest_lines_every_line_not_only_i100(self):
        rows = [('6.683', '65', '0', '2', '0'), ('3.355', '44', '1', '0', '3'), ('3.144', '100', '1', '2', '1')]
        text = ('The strongest lines of the powder X-ray diffraction pattern [d, Å (I, %) (hkl)] are: '
                '6.683(65)(020), 3.355(44)(103), 3.144(100)(121), 3.120(51)(004).')
        m = msgs(X.check15_strongest_lines(powder(rows), text))
        self.assertEqual(len(m), 1, m)
        self.assertIn('3.120 (I 51)', m[0])
        # a transposed d is a missing line too (kvačekite 1.8632 entered as 1.8362)
        rows = [('3.0458', '11', '2', '0', '0'), ('2.6380', '100', '2', '1', '0'), ('1.8362', '39', '3', '1', '1')]
        text = 'The strongest reflections [d, Å (I)] are: 3.0458(11), 2.6380(100), 1.8632(39).'
        self.assertIn('1.8632', msgs(X.check15_strongest_lines(powder(rows), text))[0])

    def test_strongest_lines_of_calculated_pattern_or_other_spacing_are_silent(self):
        rows = [('7.070', '100', '1', '0', '1'), ('3.536', '40', '2', '0', '2'), ('2.861', '30', '2', '1', '1')]
        calc = 'The strongest lines of the calculated powder pattern [d, Å (I, %)] are: 6.945(100), 3.472(35), 2.832(28).'
        self.assertEqual(X.check15_strongest_lines(powder(rows), calc), [])
        meas = 'The strongest lines of the powder pattern [d, Å (I, %)] are: 6.945(100), 3.472(35), 2.832(28).'
        self.assertEqual(X.check15_strongest_lines(powder(rows, 'Other'), meas), [])
        # within 0.3 %: 7.68 printed, 7.70 entered
        rows = [('7.70', '100', '0', '0', '1'), ('3.536', '40', '2', '0', '2'), ('2.861', '30', '2', '1', '1')]
        text = 'The strongest lines [d, Å (I, %)] are: 7.68(100), 3.536(40), 2.861(30).'
        self.assertEqual(X.check15_strongest_lines(powder(rows), text), [])


class AuditEdges(unittest.TestCase):
    """The edges an audit of the first commit found (2026-09-14)."""

    def test_valence_carbon_is_not_also_a_one_field_element(self):
        e = entry({'Chemical': 'Pb Ga3 ( As O4 )2 ( O H )6', 'Empirical': 'As2 Ga3 H6 O14 Pb',
                   'General': 'Pb ( Ga , Ge , Fe3 C , Al ) [ ( As , S , W ) O4 ]2 ( O H )6',
                   'Analytical': 'Pb0.98 ( Ga2.1 Ge0.4 Fe0.3 Al0.2 ) [ ( As1.6 S0.3 W0.1 ) O4 ]2 ( O H )6'})
        m = msgs(X.check27_formula_integrity(e))
        self.assertEqual(len(m), 1, m)
        self.assertIn('came out as carbon', m[0])

    def test_stray_site_label_is_shown_where_it_stands(self):
        e = entry({'Chemical': 'Na Li1.5 Al7.5 ( Si6 O18 ) ( B O3 )3 ( O H )4',
                   'General': '( Na , $XS ) ( Al , Li )3 Al6 T ( Si , B )6 O18 U ( B O3 )3 ( O H )3',
                   'Empirical': 'Al9 B3 H4 Li1.5 Na O31 Si6',
                   'Analytical': 'Na0.8 ( Al1.4 Li1.3 )3 Al6 ( Si6 O18 ) ( B O3 )3 ( O H )3.4'})
        m = msgs(X.check27_formula_integrity(e))
        self.assertTrue(any("O18 U (" in x and 'stray label' in x for x in m), m)

    def test_strongest_lines_of_another_mineral_are_not_this_list(self):
        rows = [('3.144', '100', '1', '2', '1'), ('6.683', '65', '0', '2', '0'), ('3.355', '44', '1', '0', '3')]
        text = 'The strongest lines of the related mineral foo are: 7.12(100), 5.01(40), 4.12(30), 3.020(25), 2.88(20).'
        self.assertEqual(X.check15_strongest_lines(powder(rows), text), [])

    def test_a_d_broken_over_a_line_of_the_pdf_text_is_printed(self):
        rows = ReflectionsAgainstPaper.ROWS
        text = ' '.join(r[0] for r in rows if r[0] != '3.2200') + ' 3.\n22 '
        self.assertEqual(X.check29_reflections_in_paper(powder(rows), text), [])

    def test_bracketed_sign_and_spaced_esd_are_well_formed(self):
        e = entry(optical='A=1.613(4), B=1.626(3 ), Q=1.633(5), Sign=(-), 2V=72(3)°')
        self.assertEqual(msgs(X.check24_optical_2v(e)), [])


if __name__ == '__main__':
    unittest.main()
