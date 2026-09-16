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


def rows(ds):
    return [(d, '10', '1', '0', '0') for d in ds]


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


class SecondAudit(unittest.TestCase):
    """The edges the second audit found (2026-09-16): forms of the Optical Data field the readers did not
    read, the short-list allowance and the extraction damage of check29, the printed precision and the
    sentence choice of check15."""

    # --- check24 ---
    def test_an_unread_A_or_2V_is_not_a_uniaxial_field(self):
        for od in ('A=n.d., B=1.700(2), Q=1.720(2), Sign=-, 2V=n.d.',
                   'A=n.d., B=1.700(2), Q=1.720(2), Sign=-, 2Vz=60',
                   'A(est)=1.600, B=1.615(5), Q=1.635(5), Sign=-, 2V(calc)=82.7'):
            self.assertEqual(msgs(X.check24_optical_2v(entry(optical=od))), [], od)
        # the field with neither A nor 2V is still uniaxial
        e = entry(optical='B=1.656(3), Q=1.662(3), Sign=-')
        self.assertTrue(any('ω and ε swapped' in x for x in msgs(X.check24_optical_2v(e))))

    def test_qualified_index_and_2v_forms_feed_the_biaxial_computation(self):
        # A(est)/B(calc)/Q(calc) read: 1.500 / 1.510 / 1.540 make an optically positive crystal (2V≈61°)
        e = entry(optical='A(est)=1.500, B(calc)=1.510, Q(calc)=1.540, Sign=-, 2V(calc)=40')
        m = msgs(X.check24_optical_2v(e))
        self.assertEqual(len(m), 1, m)
        self.assertIn('optically positive', m[0])
        # 2Vz= and '2V(calc) 100°' (no '=') read for the gross-gap rule
        for od in ('A=1.500(2), B=1.510(2), Q=1.540(2), Sign=+, 2Vz=100',
                   'A=1.500(2), B=1.510(2), Q=1.540(2), Sign=+, 2V(calc) 100°'):
            m = msgs(X.check24_optical_2v(entry(optical=od)))
            self.assertEqual(len(m), 1, (od, m))
            self.assertIn('2V=100°', m[0])

    def test_a_plus_minus_esd_has_not_collapsed(self):
        e = entry(optical='A=1.695(1), B=1.7012±0.0005, Q=1.712(2), Sign=+, 2V=60')
        self.assertEqual(msgs(X.check24_optical_2v(e)), [])
        e = entry(optical='A=1.6942±0.0005, B=1.6952±0.0005, Q=1.700±0.001, Sign=-, 2V=70')
        self.assertEqual(msgs(X.check24_optical_2v(e)), [])

    def test_em_dash_is_a_minus_and_plus_minus_is_a_note(self):
        self.assertEqual(X.check24_optical_2v(entry(optical='B=1.720(2), Q=1.700(2), Sign=—')), [])
        fs = X.check24_optical_2v(entry(optical='B=1.700(2), Q=1.720(2), Sign=±'))
        self.assertEqual(msgs(fs), [])
        self.assertTrue(any('Sign=±' in x for x in msgs(fs, 'note')), [f.msg for f in fs])

    # --- check29 ---
    TEN = ['7.123', '5.432', '4.321', '3.987', '3.220', '2.988', '2.654', '2.311', '1.987', '1.654']

    def test_short_list_allowance_is_one_line(self):
        ten = self.TEN
        # the abstract names the 8 strongest lines and the table is in a supplement: 2 of 10 unprinted says nothing
        abstract = 'The strongest lines are: ' + ', '.join('%s(%d)' % (d, 100 - i) for i, d in enumerate(ten[:8]))
        self.assertEqual(X.check29_reflections_in_paper(powder(rows(ten)), abstract), [])
        # one of ten unprinted is the case the check is for
        m = msgs(X.check29_reflections_in_paper(powder(rows(ten)), 'Table 3. ' + ' '.join(ten[:9])))
        self.assertEqual(len(m), 1, m)
        self.assertIn('1.654', m[0])
        self.assertIn('verify against', m[0])
        self.assertNotIn('is mistyped', m[0])
        # from 20 lines the allowance is 2
        twenty = ten + ['%.3f' % (1.6 - 0.05 * i) for i in range(10)]
        m = msgs(X.check29_reflections_in_paper(powder(rows(twenty)), 'Table 3. ' + ' '.join(twenty[:18])))
        self.assertEqual(len(m), 1, m)
        self.assertEqual(X.check29_reflections_in_paper(powder(rows(twenty)), 'Table 3. ' + ' '.join(twenty[:17])), [])

    def test_a_d_with_a_tail_or_no_decimal_point(self):
        ten = self.TEN
        table = 'Table 3. dobs ' + ' '.join(ten)
        for tail in ('3.220b', '3.220(1)', '3.220 b'):
            r = rows(ten[:4] + [tail] + ten[5:])
            self.assertEqual(X.check29_reflections_in_paper(powder(r), table), [], tail)
        # a tailed d that IS unprinted is reported as the entry wrote it
        r = rows(ten[:4] + ['3.220b'] + ten[5:])
        m = msgs(X.check29_reflections_in_paper(powder(r), table.replace('3.220', '3.322')))
        self.assertEqual(len(m), 1, m)
        self.assertIn('3.220b', m[0])
        # an integer d neither raises nor is reported (it cannot be among the decimal tokens)
        r = rows(['10'] + ten[1:])
        self.assertEqual(X.check29_reflections_in_paper(powder(r), table), [])

    def test_extraction_damage_on_the_pdf_side_is_printed(self):
        ten = self.TEN
        table = 'Table 3. dobs ' + ' '.join(ten)
        for damaged in ('3,220', '3.2\n20'):
            text = table.replace('3.220', damaged)
            self.assertEqual(X.check29_reflections_in_paper(powder(rows(ten)), text), [], damaged)
        # a digit run that merely ENDS in the entry's digits does not vouch for the line (a longer
        # number such as a 2θ 23.22 would otherwise silence a real miss; the corpus pdfs glue digits
        # only in DOIs and version strings, never in a table)
        for glued in ('1003.220', '13.220'):
            m = msgs(X.check29_reflections_in_paper(powder(rows(ten)), table.replace('3.220', glued)))
            self.assertEqual(len(m), 1, (glued, m))
        # a different number that merely begins with the entry's digits is still unprinted
        m = msgs(X.check29_reflections_in_paper(powder(rows(ten)), table.replace('3.220', '3.2262')))
        self.assertEqual(len(m), 1, m)
        self.assertIn('3.220', m[0])

    # --- check15 ---
    def test_the_printed_precision_sets_the_tolerance(self):
        ds = ['3.3612', '2.9871', '2.1204', '1.5049', '1.4312']
        t = ('The strongest lines in the powder pattern [d, Å (I, %)] are: 3.36(100), 2.99(50), 2.12(40), '
             '1.50(40), 1.43(30). The')
        self.assertEqual(X.check15_strongest_lines(powder(rows(ds)), t), [])
        # at the paper's own precision a transposed d is still a miss
        t = 'The strongest lines in the powder pattern [d, Å (I, %)] are: 3.361(100), 2.987(50), 2.120(40), 1.549(40). The'
        self.assertIn('1.549', msgs(X.check15_strongest_lines(powder(rows(ds)), t))[0])

    def test_every_strongest_lines_sentence_is_scored(self):
        ds = ['3.3612', '2.9871', '2.1204', '1.5049', '1.4312', '1.301']
        other = ('The strongest lines of the powder pattern of otherite [d, Å (I, %)] are: 3.355(100), 2.980(50), '
                 '2.118(40), 1.520(40), 1.445(30), 1.300(20). The')
        own = ('The strongest lines of the powder pattern of testite [d, Å (I, %)] are: 3.361(100), 2.987(50), '
               '2.120(40), 1.505(40), 1.431(30), 1.301(20). The')
        # the isotypic mineral's list first: the entry's own sentence matches, so nothing is reported
        self.assertEqual(X.check15_strongest_lines(powder(rows(ds)), other + ' ' + own), [])
        # no sentence matches fully: the one with the fewest misses is reported
        own2 = own.replace('1.505(40)', '1.550(40)')
        m = msgs(X.check15_strongest_lines(powder(rows(ds)), other + ' ' + own2))
        self.assertEqual(len(m), 1, m)
        self.assertIn('1.550', m[0])
        self.assertNotIn('1.520', m[0])


class AuditEdges2(unittest.TestCase):
    """The second audit (2026-09-16): one finding per fault, prose-suffixed constituents, total-iron
    spellings, ranges, a parenthetical inside the wt% list, the General formula's substituents, a Σ
    over integer coefficients, and the density ratios that tile the 25-30 % band."""

    def test_prose_suffixed_constituent_is_not_recased(self):
        # 1. 'H2Ocalc' is not 'H2OCAlC', 'CO2calc' is not cobalt, 'RE2O3' (rare earths) is not rhenium
        self.assertIsNone(X._recase_species('H2Ocalc'))
        self.assertIsNone(X._recase_species('CO2calc'))
        self.assertIsNone(X._recase_species('RE2O3'))
        e = entry({}, 'Microprobe analysis (wt.%): CaO 30.1, RE2O3 68.1, CO2calc 0.4, H2Ocalc 0.8')
        self.assertEqual(msgs(X.check27_formula_integrity(e)), [])
        # the suffix reads as the '(calc)' tag: the elements are still counted
        items = {sp: els for sp, els, _ in X._wt_items('CO2calc 0.4, H2Ocalc 0.8, RE2O3 68.1, TR2O3 1.0')}
        self.assertEqual(items.get('CO2'), ['C', 'O'])
        self.assertEqual(items.get('H2O'), ['H', 'O'])
        # a rare-earth shorthand groups the REE: the formula's Ce, Nd need no constituent of their own
        e = entry({'Analytical': 'Ca0.98 ( Ce0.60 Nd0.40 ) ( C O3 )2 F'},
                  'Microprobe analysis (wt.%): CaO 30.1, RE2O3 68.1, F 3.2, CO2calc 0.4: Ca0.98 ( Ce0.60 Nd0.40 ) ( C O3 )2 F.')
        self.assertEqual(msgs(X.check27_formula_integrity(e)), [])

    def test_total_iron_spellings(self):
        # 2. every spelling of total iron names Fe
        for sp in ('FeOtot', 'FeOtotal', 'FeOT', 'FeOt', 'FeO*', 'Fe2O3T', 'FeO(tot)'):
            with self.subTest(sp=sp):
                items = X._wt_items('MgO 10.2, %s 25.1, SiO2 40.3' % sp)
                self.assertEqual(len(items), 3, items)
                self.assertIn('Fe', items[1][1])
        e = entry({'Analytical': 'Mg0.5 Fe0.5 Si O3'},
                  'Microprobe analysis (wt.%): MgO 10.2, FeOtot 25.1, SiO2 40.3, CaO 1.0: Mg0.5 Fe0.5 Si O3.')
        self.assertEqual(msgs(X.check27_formula_integrity(e)), [])

    def test_split_symbol_is_one_finding(self):
        # 3a. ferroinnelite: 'N B0.05' is the split; the coefficient comparison must not report B and Nb again
        an = ('( Na1.95 Fe0.64 +2 Mg0.21 Mn0.19 +2 Ca0.02 ) ( Ba3.84 Sr0.13 Na0.03 ) ( Ti2.91 N B0.05 Al0.02 Zr0.01 Mg0.01 ) '
              'Si4.02 S0.94 P0.89 H1.70 O25.89 F0.11')
        a = ('Microprobe analysis (wt.%): SO3 5.47, Nb2O5 0.45, P2O5 4.59, ZrO2 0.13, TiO2 16.91, SiO2 17.55, Al2O3 0.06, '
             'BaO 42.83, SrO 1.01, FeO 3.34, MnO 0.97, CaO 0.09, MgO 0.64, K2O 0.01, Na2O 4.47, H2O(calc) 1.11, F 0.15: '
             '( Na1.95 Fe 0.64 +2 Mg0.21 Mn0.19 +2 Ca0.02 )S3.01 ( Ba3.84 Sr0.13 Na0.03 )S4.00 ( Ti2.91 Nb0.05 Al0.02 Zr0.01 '
             'Mg0.01 )S3.00 Si4.02 S0.94 P0.89 H1.70 O25.89 F0.11.')
        e = entry({'Analytical': an, 'Chemical': 'Ba4 Ti2 Na ( Na Fe +2 ) Ti ( Si2 O7 )2 [ ( S O4 ) ( P O4 ) ] O2 [ O ( O H ) ]'}, a)
        f = X.check27_formula_integrity(e)
        self.assertEqual(len(f), 1, [x.msg for x in f])
        self.assertIn('Nb0.05?', f[0].msg)
        # alicewilsonite-(YCe): 'D Y0.08' — the split, not also 'Dy2O3 absent' and 'Y 0.75 vs 0.67'
        an = ('Na2.11 Ca0.11 Sr1.83 Ba0.08 Y0.67 ( Ce0.51 La0.32 Pr0.03 Nd0.09 Sm0.02 Gd0.04 D Y0.08 Ho0.02 Er0.06 Yb0.03 ) '
              '( C O3 )5.88 ( H2 O )3.00')
        a = ('Microprobe analysis, average of 6 (wt.%): Na2O 7.42, CaO 0.72, SrO 21.49, BaO 1.41, Y2O3 8.52, La2O3 5.93, '
             'Ce2O3 9.52, Pr2O3 0.59, Nd2O3 1.75, Sm2O3 0.46, Gd2O3 0.83, Dy2O3 1.65, Ho2O3 0.34, Er2O3 1.21, Yb2O3 0.64, '
             'CO2 29.33, H2O(calculated) 6.13: Na2.11 Ca0.11 Sr1.83 Ba0.08 Y0.67 ( Ce0.51 La0.32 Pr0.03 Nd0.09 Sm0.02 Gd0.04 '
             'Dy0.08 Ho0.02 Er0.06 Yb0.03 )$SI1.20 ( C O3 )5.88 ( H2 O )3.00.')
        f = X.check27_formula_integrity(entry({'Analytical': an, 'Chemical': 'Na2 Sr2 Y Ce ( C O3 )6 !3 H2 O'}, a))
        self.assertEqual(len(f), 1, [x.msg for x in f])
        self.assertIn('Dy0.08?', f[0].msg)
        # a fault elsewhere on the same row is still its own finding (F in both formulas, not in the wt% list)
        f = X.check27_formula_integrity(entry({'Analytical': an + ' F0.20', 'Chemical': 'Na2 Sr2 Y Ce ( C O3 )6 !3 H2 O'},
                                              a.replace('( H2 O )3.00.', '( H2 O )3.00 F0.20.')))
        self.assertEqual(sorted('Dy0.08?' in x.msg or 'contains F' in x.msg for x in f), [True, True], [x.msg for x in f])

    def test_duplicated_constituent_standing_for_a_missing_one_is_one_finding(self):
        # 3b. airdite: the second CaO is the BaO the formula needs
        an = '( Sr0.46 Ca0.25 Ba0.23 ) ( V1.94 +4 Fe0.03 +3 Cu0.02 ) ( P2.02 O4 ) O10 H8.13'
        a = ('Microprobe analysis, average of 10 (wt.%): SrO 9.78, CaO 2.89, CaO 7.17, VO2 32.81, Fe2O3 0.42, CuO 0.39, '
             'P2O5 29.13, H2O(calc) 14.91: ( Sr0.46 Ca0.25 Ba0.23 )S0.94 ( V1.94 +4 Fe0.03 +3 Cu0.02 )S1.99 ( P2.02 O4 ) O10 H8.13')
        f = X.check27_formula_integrity(entry({'Analytical': an, 'Chemical': 'Sr ( V +4 O )2 ( P O4 )2 !4 H2 O'}, a))
        self.assertEqual(len(f), 1, [x.msg for x in f])
        self.assertIn('CaO twice (2.89 and 7.17)', f[0].msg)
        self.assertIn('probably BaO', f[0].msg)
        # mendozavilite-KCa: the second P2O5 is As2O5
        an = ('[ ( K1.43 Na1.12 Ca0.14 ) ( H2 O )9.02 ( Ca0.94 Cu0.05 +2 Al0.01 ) ( H2 O )6 ] [ Mo8 ( P1.86 As0.06 Si0.01 ) '
              'Fe3.00 +3 O34.48 ( O H )2.52 ]')
        a = ('Microprobe analysis (wt.%): Na2O 1.90, K2O 3.67, CaO3.30, CuO 0.22, Fe2O3 13.09, Al2O3 0.04, SiO2 0.03, '
             'P2O5 7.21, P2O5 0.34, MoO3 62.93, H2O 16.03[ ( K1.43 Na1.12 Ca0.14 )S$I2.69 ( H2 O )9.02 ( Ca0.94 Cu 0.05 +2 '
             'Al 0.01 )$SI1.00 ( H2 O )6 ][ Mo8 ( P1.86 As0.06 Si0.01 )$SI1.93 Fe3.00 +3 O34.48 ( O H )2.52 ]')
        f = X.check27_formula_integrity(entry({'Analytical': an}, a))
        self.assertEqual(len(f), 1, [x.msg for x in f])
        self.assertIn('P2O5 twice', f[0].msg)
        self.assertIn('As2O5', f[0].msg)
        # dacostaite: a duplicated Na2O and a formula whose F the list lacks are TWO faults (F is no Na2O)
        an = '( K0.56 Ca0.04 Na0.03 ) ( Al1.54 Mg1.38 Cu0.03 Zn0.03 ) [ Mg ( H2 O )6 ]2 [ ( As0.99 P0.01 ) O4 ]2 [ F4.46 ( O H )1.46 O0.08 ] !2 H2 O'
        a = ('Microprobe analysis, average of 10 (wt.%): P2O5 0.17, As2O5 35.42, Al2O3 12.23, MgO 21.13, CaO 0.36, '
             'CuO 0.42, ZnO 0.34, Na2O 0.34, Na2O 0.15, K2O 4.13, H2O(calc) 41.40: ' + an + '.')
        m = msgs(X.check27_formula_integrity(entry({'Analytical': an}, a)))
        self.assertEqual(len(m), 2, m)
        self.assertTrue(any('Na2O twice' in x and 'a constituent was probably mistyped' in x for x in m), m)
        self.assertTrue(any('contains F' in x for x in m), m)

    def test_a_list_of_ranges_is_not_a_wt_list(self):
        # 4. selenolaurite: 'Ir 3.28-5.50' is a range, not 3.2 wt%
        wl = 'Ir 3.28-5.50, Te 0.61-1.93, S 0.18'
        self.assertEqual([(sp, v) for sp, _, v in X._wt_items(wl)], [('S', 0.18)])
        self.assertEqual(X._wt_items('Ru 45.1–46.3'), [])
        e = entry({'Analytical': '( Ru0.99 Ir0.05 ) ( Se1.92 Te0.03 S0.01 )', 'Chemical': 'Ru Se2'},
                  'Microprobe analsysis of selenolaurite (wt.%): Ir 3.28-5.50, Te 0.61-1.93, S 0.18: '
                  '( Ru0.99 Ir0.05 )S1.04 ( Se1.92 Te0.03 S0.01 )S1.9.')
        self.assertEqual(msgs(X.check27_formula_integrity(e)), [])

    def test_parenthetical_in_the_list_and_a_sentence_after_the_formula(self):
        # 5a. a bracketed aside with an element and a decimal does not start the formula
        f = 'Na0.97 Ca1.01 Fe0.92 +3 Al1.11 ( P O4 )0.97 F4.85 ( O H )1.32 !0.95 H2 O'
        a = ('Microprobe analysis, average of 12 (wt.%): Na2O 8.32, CaO 15.63, Al2O3 15.59, Fe2O3 20.24, Li2O 1.65 '
             '(Li 0.77 by ICP-OES), P2O5 18.97, F 5.1, H2O(calc) 7.97: ' + f + '.')
        wl, af = X._split_analysis(a)
        self.assertIn('P2O5 18.97', wl)
        self.assertTrue(af.startswith('Na0.97'), af)
        self.assertEqual(msgs(X.check27_formula_integrity(entry({'Analytical': f}, a))), [])
        # the glued formula (no colon) still splits
        wl, af = X._split_analysis('Microprobe analysis (wt.%): Na2O 1.90, H2O 16.03[ ( K1.43 Na1.12 )S$I2.55 ( H2 O )9 ]')
        self.assertEqual(wl.strip(), 'Na2O 1.90, H2O 16.03')
        self.assertTrue(af.startswith('[ ( K1.43'), af)
        # 5b. a sentence after the formula is not part of it
        a = ('Microprobe analysis (wt.%): Na2O 8.32, CaO 15.63, Al2O3 15.59, Fe2O3 20.24, P2O5 18.97, H2O(calc) 7.97: '
             + f + '. F 5.1 wt% by ion chromatography.')
        wl, af = X._split_analysis(a)
        self.assertEqual(af.rstrip('.'), f)
        m = msgs(X.check27_formula_integrity(entry({'Analytical': f}, a)))
        self.assertEqual(m, [], m)

    def test_general_formula_substituents_are_a_note(self):
        # 6. a General formula names a group's substituents by definition
        e = entry({'Chemical': 'Ca Mg Si2 O6', 'General': 'Ca ( Mg , Fe , Mn ) Si2 O6', 'Empirical': 'Ca Mg O6 Si2',
                   'Analytical': 'Ca1.00 Mg0.99 Si2.01 O6'},
                  'Microprobe analysis (wt.%): CaO 25.9, MgO 18.6, SiO2 55.5: Ca1.00 Mg0.99 Si2.01 O6.')
        f = X.check27_formula_integrity(e)
        self.assertEqual([x.sev for x in f], ['note'], [x.msg for x in f])
        self.assertIn('Fe, Mn', f[0].msg)
        # a bare symbol keeps the flag
        e.formulas['General'] = 'Ca ( Mg , Fe ) Si2 O6 U'
        self.assertTrue(any('contains U' in x for x in msgs(X.check27_formula_integrity(e))))

    def test_sigma_over_integer_coefficients_and_a_sigma_off_by_rounding(self):
        # 7. an integer coefficient inside the group is part of its sum
        self.assertNotIn('S4.49', X._strip_sums('( Pb4 Zn0.36 Fe0.13 )S4.49 ( As1.71 Sb0.26 )S1.97 Ge1.92 S12'))
        an = '( Pb4 Zn0.36 Fe0.13 ) ( As1.71 Sb0.26 ) Ge1.92 S12'
        a = ('Microprobe analysis (wt.%): Pb 57.95, S 22.85, Ge 8.29, As 7.60, Sb 1.84, Zn 1.39, Fe 0.44: '
             '( Pb4 Zn0.36 Fe0.13 )S4.49 ( As1.71 Sb0.26 )S1.97 Ge1.92 S11.9.')
        m = msgs(X.check27_formula_integrity(entry({'Analytical': an, 'Chemical': 'Pb4 ( As S3 )2 ( Ge2 S6 )'}, a)))
        self.assertEqual(m, [], m)
        # a Σ typed 0.03 off is not sulfur: no 'S x vs y' phantom
        a = ('Microprobe analysis (wt.%): Pb 57.95, S 22.85, Ge 8.29, As 7.60, Sb 1.84, Zn 1.39, Fe 0.44: '
             '( Pb4.71 Zn0.36 Fe0.13 )S5.23 ( As1.71 Sb0.26 )S1.97 Ge1.92 S12.')
        an = '( Pb4.71 Zn0.36 Fe0.13 ) ( As1.71 Sb0.26 ) Ge1.92 S12'
        m = msgs(X.check27_formula_integrity(entry({'Analytical': an, 'Chemical': 'Pb5 ( As S3 )2 ( Ge2 S6 )'}, a)))
        self.assertEqual(m, [], m)
        # a real sulfur disagreement in a sulfosalt with no Σ is still reported
        a = 'Microprobe analysis (wt.%): Pb 57.81, As 3.53, Sb 20.03, S 19.08: Pb10.336 As1.567 Sb6.088 S23.0.'
        m = msgs(X.check27_formula_integrity(entry({'Analytical': 'Pb10.336 As1.567 Sb6.088 S21.92',
                                                    'Chemical': 'Pb10 Sb6 As2 S22'}, a)))
        self.assertTrue(any('S 21.92 vs 23' in x for x in m), m)

    def test_density_ratios_that_tile_the_band_are_notes(self):
        # 8. 3.00/3.75 is not '5/4×'; 1.25-1.28 is a note; the structural ratios keep their flags
        f = X.check28_density_consistency(entry(density={'Dx': '3.750', 'Xtl Dx': '3.000'}))
        self.assertEqual([x.sev for x in f], ['note'], [x.msg for x in f])
        f = X.check28_density_consistency(entry(density={'Dx': '3.000', 'Xtl Dx': '3.780'}))
        self.assertEqual([x.sev for x in f], ['note'], [x.msg for x in f])
        for dx, xdx, want in (('3.814', '1.944', '1/2×'), ('3.460', '2.280', '2/3×'), ('4.570', '3.418', '3/4×'),
                              ('3.035', '0.771', '1/4×'), ('9.781', '12.901', '4/3×'), ('5.160', '7.910', '3/2×'),
                              ('4.895', '29.181', '6×'), ('4.120', '8.294', '2×'), ('2.160', '3.681', '70%')):
            with self.subTest(dx=dx, xdx=xdx):
                m = msgs(X.check28_density_consistency(entry(density={'Dx': dx, 'Xtl Dx': xdx})))
                self.assertEqual(len(m), 1, m)
                self.assertIn(want, m[0])

    def test_substitute_wording_names_one_element(self):
        # 9. SeO2 stands for Te; F is simply not in the list
        an = 'Pb0.99 Te3.00 +4 O5 ( O H ) Cl2.65 F0.50 ( H1.95 O1.15 )'
        a = 'Microprobe analysis, average of 8 (wt.%): PbO 27.68, SeO2 59.92, Cl 11.74, H2O(calc) 3.33: ' + an + '.'
        m = msgs(X.check27_formula_integrity(entry({'Analytical': an, 'Chemical': 'Pb Te3 +4 O5 ( O H ) Cl3 ( H2 O )'}, a)))
        self.assertEqual(len(m), 1, m)
        self.assertIn('the formula has Te instead', m[0])
        self.assertNotIn('F, Te', m[0])
        self.assertIn('F', m[0].split('instead')[1])


if __name__ == '__main__':
    unittest.main()


class ExtinctionsAndEntryOptics(unittest.TestCase):
    """Checks 30 and 31 (2026-09-16): a reflection the space group forbids, and the entry's own
    indices and Gladstone–Dale arithmetic against the .pdf."""

    def _e(self, sg, refl, optical='', analysis='', density=None):
        e = entry(analysis=analysis, optical=optical, density=density)
        e.space_group = sg; e.refl = refl; e.cell['SG'] = sg
        return e

    def test_a_forbidden_reflection_is_a_flag_and_many_are_a_note(self):
        allowed = [('4.0', '100', '1', '1', '0'), ('3.0', '50', '0', '0', '2'), ('2.5', '40', '2', '0', '0'), ('2.0', '30', '1', '1', '2'), ('1.8', '20', '2', '2', '0'), ('1.5', '10', '3', '1', '0')]
        self.assertEqual(X.check30_extinctions(self._e('C2/c', allowed)), [])
        one_bad = allowed + [('3.5', '15', '1', '0', '0')]                      # h+k odd: absent in a C lattice
        f = X.check30_extinctions(self._e('C2/c', one_bad))
        self.assertEqual([x.sev for x in f], ['flag']); self.assertIn('1 0 0', f[0].msg)
        many_bad = allowed + [('3.5', '15', '1', '0', '0'), ('3.3', '15', '0', '1', '0'), ('3.1', '15', '2', '1', '0'), ('2.9', '15', '0', '0', '1')]
        f = X.check30_extinctions(self._e('C2/c', many_bad))
        self.assertEqual([x.sev for x in f], ['note'])
        self.assertEqual(X.check30_extinctions(self._e('Xyz', one_bad)), [])       # an unknown symbol says nothing
        self.assertEqual(X.check30_extinctions(self._e('P1', one_bad)), [])        # nothing is forbidden in P1

    def test_the_mean_index_of_the_entry(self):
        self.assertAlmostEqual(X._entry_mean_n('A=1.610(3), B=1.620(3), Q=1.644(3), Sign=+, 2V(calc)66.5°'), (1.610 + 1.620 + 1.644) / 3)
        self.assertAlmostEqual(X._entry_mean_n('B=1.716(5), Q=1.668(5), Sign=-'), (2 * 1.716 + 1.668) / 3)   # uniaxial (−): B is ω, the larger
        self.assertIsNone(X._entry_mean_n('B=1.668(5), Q=1.716(5), Sign=-'))                                # the sign contradicts B=ω < Q=ε: check24's finding, not an index
        self.assertAlmostEqual(X._entry_mean_n('A=1.640(3), Q=1.662(3), Sign=+'), (2 * 1.640 + 1.662) / 3)
        self.assertAlmostEqual(X._entry_mean_n('A=1.640(3), Q=1.662(3).'), (2 * 1.640 + 1.662) / 3)         # no sign: the first index is still ω
        self.assertAlmostEqual(X._entry_mean_n('A=1.640(3), B=1.662(3).'), (1.640 + 1.662) / 2)             # no ε at all: the plain mean
        self.assertIsNone(X._entry_mean_n('Sign=+')); self.assertIsNone(X._entry_mean_n(''))

    def test_indices_against_the_paper(self):
        e = self._e('P1', [], optical='A=1.610(3), B=1.620(3), Q=1.644(3), Sign=+')
        same = 'Optically the mineral is biaxial (+), α = 1.610(3), β = 1.620(3), γ = 1.644(3).'
        self.assertEqual([x for x in X.check31_gd_entry(e, same) if x.sev == 'flag'], [])
        other = 'Optically the mineral is biaxial (+), α = 1.588(3), β = 1.600(3), γ = 1.607(3).'
        f = X.check31_gd_entry(e, other)
        self.assertEqual([x.sev for x in f], ['flag']); self.assertIn('mistranscribed', f[0].msg)
        two = other + ' The associated mineral is biaxial (−), α = 1.700, β = 1.710, γ = 1.720.'
        self.assertEqual([x for x in X.check31_gd_entry(e, two) if x.sev == 'flag'], [])           # two sets of indices in the paper: not compared


class EntryOpticsAndSettingsAfterTheAudit(unittest.TestCase):
    """Audit 2026-09-16 pm: a wrong sign is one finding (check24's), the extinction check sees
    P21/c, and check22 recognises Mindat's cell in another setting."""

    def test_a_wrong_sign_is_not_also_a_mistranscribed_index(self):
        e = entry(optical='B=1.600(3), Q=1.660(3), Sign=-')
        text = 'Optically the mineral is uniaxial (+), ω = 1.600(3), ε = 1.660(3). Sample.'
        self.assertEqual(len(msgs(X.check24_optical_2v(e, text))), 1)
        self.assertEqual(msgs(X.check31_gd_entry(e, text)), [])
        e = entry(optical='B=1.660(3), Q=1.600(3), Sign=-')                       # right sign, an index off: the flag stands
        f = msgs(X.check31_gd_entry(e, 'Optically the mineral is uniaxial (−), ω = 1.700(3), ε = 1.640(3). Sample.'))
        self.assertEqual(len(f), 1); self.assertIn('mistranscribed', f[0])

    def test_a_glide_absence_in_p21_c(self):
        allowed = [('4.0', '100', '1', '1', '0'), ('3.0', '50', '0', '0', '2'), ('2.5', '40', '2', '0', '0'), ('2.0', '30', '1', '1', '2'), ('1.8', '20', '0', '2', '0'), ('1.5', '10', '1', '0', '2')]
        e = entry(); e.space_group = 'P21/c'; e.refl = allowed; e.cell['SG'] = 'P21/c'
        self.assertEqual(X.check30_extinctions(e), [])
        e.refl = allowed + [('3.3', '15', '0', '1', '0'), ('2.9', '15', '1', '0', '1')]     # 0k0 k odd, h0l l odd
        f = X.check30_extinctions(e)
        self.assertEqual([x.sev for x in f], ['flag']); self.assertIn('0 1 0', f[0].msg); self.assertIn('1 0 1', f[0].msg)

    def test_mindat_in_another_setting_is_the_same_lattice(self):
        from unittest import mock
        e = type('E', (), {'name': 'testite', 'primary': '', 'subfiles': [], 'space_group': 'C2/c', 'formulas': {}, 'comments': {}, 'instr': {}, 'refl': [],
                           'cell': {'a': '12.0', 'b': '5.0', 'c': '9.0', 'α': '90', 'β': '100', 'γ': '90', 'SG': 'C2/c'}})()
        cif = {'cell': {'a': '12.0', 'b': '5.0', 'c': '9.0', 'α': '90', 'β': '100', 'γ': '90', 'SG': 'C2/c'}}
        # the I-setting of the same lattice (a_I = a_C + c_C), Mindat's symbol an id and its angles as it stores them
        same = {'a': 13.69, 'b': 5.0, 'c': 9.0, 'al': 90.0, 'be': 120.3, 'ga': 90.0, 'sg': 15}
        with mock.patch.object(X, 'mindat_struct', lambda n, exact=False: None if exact else same):
            f = [x for x in X.check22_cross_sources(e, cif, None) if x.code == 'mindat_fix']
        self.assertEqual(len(f), 1); self.assertIn('another setting', f[0].msg)
        other = {'a': 13.69, 'b': 5.0, 'c': 9.6, 'al': 90.0, 'be': 120.3, 'ga': 90.0, 'sg': 15}
        with mock.patch.object(X, 'mindat_struct', lambda n, exact=False: None if exact else other):
            f = [x for x in X.check22_cross_sources(e, cif, None) if x.code == 'mindat_fix']
        self.assertEqual(len(f), 1); self.assertIn('verify which is correct', f[0].msg)
        # a hexagonal cell Mindat stores with b = 0 and γ = 0, against the same lattice on rhombohedral axes in the docx
        e.cell = {'a': '6.36', 'b': '6.36', 'c': '6.36', 'α': '46.3', 'β': '46.3', 'γ': '46.3', 'SG': 'R-3m'}; e.space_group = 'R-3m'
        cif = {'cell': dict(e.cell)}
        hexa = {'a': 5.0, 'b': 0.0, 'c': 17.0, 'al': 0.0, 'be': 0.0, 'ga': 0.0, 'sg': 166}
        with mock.patch.object(X, 'mindat_struct', lambda n, exact=False: None if exact else hexa):
            f = [x for x in X.check22_cross_sources(e, cif, None) if x.code == 'mindat_fix']
        self.assertEqual([('another setting' in x.msg) for x in f], [True])
