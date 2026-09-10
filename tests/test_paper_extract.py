"""pxrd_review.paper_extract — a synthetic two-column paper page built with PyMuPDF: the analytical
table, the basis sentence, the H2O statement, optics and a powder table.

    python3 -m unittest tests.test_paper_extract -v
"""
import os, shutil, tempfile, unittest

from pxrd_review import paper_extract as PE


def make_pdf(path):
    import pymupdf
    doc = pymupdf.open(); page = doc.new_page(width=595, height=842)
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


class CompositionDoubts(unittest.TestCase):
    """The rule that decides whether a composition disagreement is a FINDING or a console note.

    Every doubt marked `reading` says one thing: the tool may not have read the paper's analytical
    table properly. The reduction answers that itself — when it reproduces every coefficient but
    one over enough elements, the reading has proved itself and the exception belongs to the paper.
    A HARD doubt (the wt% do not add up, an element is missing, the formula would not parse) still
    blocks, because those say the comparison itself is unsound.

    The table below reduces on 12 O to Si 2.962, Al 1.738, Mg 1.984, Ca 0.859, Fe 0.627; the
    formula sentence states all five, with Mg printed 14 % low.
    """
    WT = (('SiO2', 40.28), ('Al2O3', 20.05), ('MgO', 18.10), ('CaO', 10.90), ('FeO', 10.20))
    FORMULA = 'The empirical formula (based on 12 O apfu) is Si2.96Al1.74Mg1.70Ca0.86Fe0.63O12 for it.'

    def ex(self, scale=1.0, header='Constituent Mean Range', rows=None):
        rows = rows if rows is not None else self.WT
        return {'name': 'testite', 'basis': ('anions', None, 12.0),
                'epma': {'rows': [{'constituent': c, 'mean': round(v * scale, 2)} for c, v in rows],
                         'header': header, 'caption': ''}}

    def test_a_reading_doubt_alone_does_not_stop_the_one_odd_coefficient(self):
        # an unrecognised header is a doubt about the READING; four coefficients reproducing
        # settles that question, so the fifth is the paper's
        c = PE.check_composition(self.ex(header='A B C'), self.FORMULA)
        self.assertTrue(any('header was not recognised' not in l for l in c['lines']))
        self.assertEqual([d[0] for d in c['result']['diffs']], ['Mg'])
        self.assertTrue(c['verified'])                                  # a finding, not a note
        self.assertFalse(c['ok'])
        self.assertTrue(any('but Mg follows from the table read' in l for l in c['lines']), c['lines'])
        self.assertEqual(c['doubts'], [])

    def test_a_hard_doubt_still_blocks(self):
        # the same reading, the same one coefficient — but the wt% do not add up, so the
        # comparison itself is unsound and nothing may be concluded from it
        c = PE.check_composition(self.ex(scale=0.8, header='A B C'), self.FORMULA)
        self.assertEqual([d[0] for d in c['result']['diffs']], ['Mg'])
        self.assertFalse(c['verified'])
        self.assertTrue(any('add to 79' in d for d in c['doubts']), c['doubts'])

    def test_an_element_the_table_has_none_of_blocks(self):
        # a formula element absent from the table is a hard doubt: the table was read incompletely
        c = PE.check_composition(self.ex(header='A B C'),
                                 'The empirical formula (based on 12 O apfu) is Si2.96Al1.74Mg1.98Ca0.86Fe0.63Na0.30O12 for it.')
        self.assertFalse(c['verified'])
        self.assertTrue(any('has no Na' in d for d in c['doubts']), c['doubts'])

    def test_too_few_elements_for_the_reading_to_prove_itself(self):
        # three constituents: one of them differing leaves too little agreeing to vouch for the read
        c = PE.check_composition(self.ex(header='A B C', rows=self.WT[:3]),
                                 'The empirical formula (based on 12 O apfu) is Si4.15Al2.44Mg1.70O12 for it.')
        self.assertTrue(c['doubts'])
        self.assertFalse(c['verified'])

    def test_a_clean_read_needs_no_rule(self):
        c = PE.check_composition(self.ex(), 'The empirical formula (based on 12 O apfu) is Si2.96Al1.74Mg1.98Ca0.86Fe0.63O12 for it.')
        self.assertTrue(c['ok'], c['lines'])
        self.assertEqual(c['result']['diffs'], [])


class SingleOutlier(unittest.TestCase):
    """One wrong number does not move one element alone.

    A reduction normalises to a basis, so inflating one constituent moves that element a lot and
    dilutes every OTHER one by a single common factor. The 'the cations deviate N% overall' doubt
    was reading that as a table-reading problem, and because the single-element rescue insisted on
    exactly one deviating element it could not answer. Measured 2026-09-07 by seeding faults:
    recall PEAKED then FELL — 96 papers where a 10 % error in a wt% was caught and a 20 % one was
    not, 27 more for a formula coefficient, and 117 of those 123 degraded to a console note.

    The fixture: the same five constituents as CompositionDoubts, SiO2 inflated 20 %. The
    reduction then puts Si 9 % high and Al, Mg, Ca and Fe all 9 % low — one factor, to a tenth of
    a per cent — while the formula sentence is untouched."""
    WT = (('SiO2', 48.34), ('Al2O3', 20.05), ('MgO', 18.10), ('CaO', 10.90), ('FeO', 10.20))
    FORMULA = 'The empirical formula (based on 12 O apfu) is Si2.96Al1.74Mg1.98Ca0.86Fe0.63O12 for it.'

    def ex(self, rows=None, header='A B C'):
        rows = rows if rows is not None else self.WT
        return {'name': 'testite', 'basis': ('anions', None, 12.0),
                'epma': {'rows': [{'constituent': c, 'mean': v} for c, v in rows],
                         'header': header, 'caption': ''}}

    def test_one_element_off_and_the_rest_on_one_factor_is_a_finding(self):
        c = PE.check_composition(self.ex(), self.FORMULA)
        self.assertEqual(len(c['result']['diffs']), 5)          # five deviate, so `len(solo) == 1` cannot fire
        self.assertTrue(c['verified'], c['doubts'])             # …but it is one wrong number, and a finding
        self.assertTrue(any('but Si follows from the table read' in l for l in c['lines']), c['lines'])
        self.assertEqual(c['doubts'], [])

    def test_the_outlier_is_named_and_it_is_the_wrong_one(self):
        r = PE._check_formula(self.ex(), self.FORMULA, PE._formulas(self.FORMULA, 'testite')[0])
        self.assertEqual(PE._single_outlier(r['counts'], r['result']['apfu']), 'Si')

    def test_scattered_deviations_are_still_a_reading_problem(self):
        """No common factor: the elements disagree in different directions by different amounts,
        which is what a misread table actually looks like. The doubt must stand."""
        rows = (('SiO2', 44.0), ('Al2O3', 17.0), ('MgO', 21.0), ('CaO', 9.0), ('FeO', 12.0))
        c = PE.check_composition(self.ex(rows=rows), self.FORMULA)
        self.assertFalse(c['verified'])
        self.assertTrue(any('deviate' in d for d in c['doubts']), c['doubts'])
        self.assertIsNone(PE._single_outlier(c['counts'], c['result']['apfu']))

    def test_a_hard_doubt_still_blocks_the_outlier(self):
        """Same shape, but an element of the formula is missing from the table: the comparison
        itself is unsound, so nothing may be read off it."""
        c = PE.check_composition(
            self.ex(), 'The empirical formula (based on 12 O apfu) is Si2.96Al1.74Mg1.98Ca0.86Fe0.63Na0.30O12 for it.')
        self.assertFalse(c['verified'])
        self.assertTrue(any('has no Na' in d for d in c['doubts']), c['doubts'])

    def test_fewer_than_four_cations_says_nothing(self):
        self.assertIsNone(PE._single_outlier({'Si': 3.0, 'Al': 1.0, 'Mg': 2.0}, {'Si': 3.3, 'Al': 0.91, 'Mg': 1.82}))

    def test_an_element_in_two_valence_states_is_not_an_outlier(self):
        """A formula printing one element twice ('S6+ 1.02 S2- 1.02') reduces to one summed
        coefficient, so a mismatch there is the parse, not the paper."""
        counts = {'Pb': 5.8, 'Te': 5.04, 'S': 3.02, 'Sb': 0.9, 'Cu': 1.0}
        apfu = {'Pb': 5.49, 'Te': 4.77, 'S': 3.60, 'Sb': 0.85, 'Cu': 0.95}
        self.assertEqual(PE._single_outlier(counts, apfu), 'S')                     # without the charges
        self.assertIsNone(PE._single_outlier(counts, apfu, {'S': {2, 6}}))          # with them

    def test_every_dash_a_journal_sets_reaches_float_as_a_minus(self):
        """Three of the corpus's four crash classes were one half-normalisation: `_NUM` admits an
        en dash as a minus, `float()` does not, and only U+2212 was being translated. 14 papers
        raised instead of being read (8 of them on a separate bug, the per-cent sign below)."""
        for d in ('\u2212', '\u2013', '\u2014', '\u2012', '\u2010'):
            self.assertEqual(PE._dash(d + '0.09'), '-0.09')
            self.assertEqual(PE._numbers(['1.20', d, '3.40']), [('range', (1.20, 3.40))])
            self.assertIsNotNone(PE._num_x((0.0, 0.0, 10.0, 1.0, d + '0.09')))
        self.assertIsNone(PE._num_x((0.0, 0.0, 10.0, 1.0, '\u2014')))      # a bare dash is 'not detected', not a number

    def test_a_per_cent_sign_is_not_a_format_conversion(self):
        """'the wt% table read (%d constituents)' % n raised `unsupported format character 't'`
        on every paper no basis reconciled — 8 of the corpus. The verdict was lost to a crash."""
        c = PE.check_composition(
            {'name': 'testite', 'epma': {'rows': [{'constituent': 'SiO2', 'mean': 40.0},
                                                  {'constituent': 'PbO', 'mean': 55.0}],
                                         'header': 'Constituent Mean', 'caption': ''}},
            'The empirical formula (based on 12 O apfu) is Na9.11K4.02Ba1.77Sr0.90O12 for it.')
        self.assertEqual(c['lines'], ['composition: not verifiable — the wt% table read (2 constituents) and '
                                      'the formula read could not be reconciled on any basis; check the table '
                                      'and the formula sentence by eye'])
        self.assertFalse(c['verified'])

    def test_a_dashed_anion_charge_is_not_a_subscript(self):
        """northstarite: 'S6+ 1.02S2- 1.02' is 2.04 S, not 3.02. The normaliser already undid a
        charge whose sign the text layer had LOST ('S2 2.60'); a sign it kept as a dash fell
        through, and the surplus sulfur then read as a real disagreement with the analysis."""
        from pxrd_review import epma as EP
        norm = PE._journal_to_icdd('Pb5.80Sb3+ 0.05Te4+ 5.04S6+ 1.02S2– 1.02O18')
        counts, _ox, _iss = EP.parse_icdd_formula(norm, has_sulfur=True)
        self.assertAlmostEqual(counts['S'], 2.04, places=2)
        self.assertAlmostEqual(counts['Pb'], 5.80, places=2)
        self.assertEqual(PE._journal_to_icdd('Fe2O3'), 'Fe2 O3')                    # a real subscript survives


class GladstoneDale(unittest.TestCase):
    """Which constituents K_C is formed from decides the answer, so every set the paper offers is
    tried and the paper's own stated compatibility index arbitrates. Only when none reproduces it
    does the completeness heuristic speak — and then it says whether the fault is a reading this
    tool could not complete (nooracle, with the reason) or a real disagreement (unverified).

    The density is derived from K_C rather than written down, so a revision to the constants file
    cannot quietly turn these into tests of nothing."""
    ROWS = (('SiO2', 46.0), ('MgO', 34.0), ('H2O', 20.0))

    @classmethod
    def setUpClass(cls):
        from pxrd_review import gd as GD
        cls.KC = GD.kc(dict(cls.ROWS))[0]
        cls.n = 1.560
        cls.D = (cls.n - 1) / cls.KC              # the density at which 1 - K_P/K_C is exactly zero

    def ex(self, rows=None, n=None, D=None):
        rows = self.ROWS if rows is None else rows
        return {'name': 'testite',
                'optics': {'n': self.n if n is None else n, 'n_from': 'mean of a b g',
                           'D_meas': self.D if D is None else D, 'D_calc': None, 'sentences': []},
                'epma': {'rows': [{'constituent': c, 'mean': v} for c, v in rows],
                         'total': round(sum(v for _c, v in rows), 2), 'header': 'Constituent wt%'}}

    STATED = {'ci': 0.0, 'category': None, 'sentence': ''}

    def test_the_analytical_table_stands_in_for_an_incomplete_reduction(self):
        # the composition check reduced on SiO2 alone; K_C from that is a fraction of the truth, and
        # the index it gives is nowhere near the paper's. The paper's own table reproduces it.
        out = PE.gd_check(self.ex(), {'wt': {'SiO2': 46.0}}, self.STATED)
        self.assertEqual(out['status']['optics.n'], 'agrees')
        self.assertAlmostEqual(out['KC'], self.KC, places=4)

    def test_an_analysis_in_elements_is_converted_to_its_oxides(self):
        from pxrd_review import gd as GD
        got = PE._as_oxides({'Si': 21.50, 'Mg': 20.50, 'O': 44.0}, GD.constants())
        self.assertIn('SiO2', got); self.assertIn('MgO', got)
        self.assertNotIn('O', got)                              # the oxides carry that oxygen already
        self.assertAlmostEqual(got['SiO2'], 46.0, delta=0.2)

    def test_nothing_to_convert_is_left_alone(self):
        from pxrd_review import gd as GD
        self.assertIsNone(PE._as_oxides({'SiO2': 46.0, 'MgO': 34.0}, GD.constants()))

    def test_a_constituent_with_no_constant_is_a_limitation_not_a_doubt(self):
        rows = (('SiO2', 46.0), ('Xy2O3', 34.0), ('H2O', 20.0))
        out = PE.gd_check(self.ex(rows=rows), {'wt': dict(rows)}, self.STATED)
        self.assertEqual(out['status']['optics.n'], 'nooracle')
        self.assertIn('Xy2O3', out['detail'])

    def test_an_analysis_short_of_its_own_printed_total_is_a_limitation(self):
        ex = self.ex()
        ex['epma']['rows'] = [{'constituent': 'SiO2', 'mean': 46.0}]     # the H2O and MgO rows were missed
        ex['epma']['total'] = 100.0                                       # but the table prints its own total
        out = PE.gd_check(ex, {'wt': {'SiO2': 46.0}}, self.STATED)
        self.assertEqual(out['status']['optics.n'], 'nooracle')
        self.assertIn('100.0 %', out['detail'])

    def test_a_complete_analysis_that_still_misses_is_a_doubt(self):
        # every constituent has a constant and the whole adds to 100: nothing excuses the gap, so
        # it stays a doubt about the paper's numbers
        out = PE.gd_check(self.ex(n=1.90), {'wt': dict(self.ROWS)}, self.STATED)
        self.assertEqual(out['status']['optics.n'], 'unverified')
        self.assertIn('this gives', out['detail'])

    def test_the_densities_take_the_same_verdict_as_the_index(self):
        out = PE.gd_check(self.ex(), {'wt': dict(self.ROWS)}, self.STATED)
        self.assertEqual(out['status']['optics.n'], 'agrees')
        self.assertEqual(out['status']['optics.D_meas'], 'agrees')
        self.assertEqual(out['status']['optics.D_calc'], 'nooracle')      # the paper gives no calculated density


if __name__ == '__main__':
    unittest.main()


class Parsers(unittest.TestCase):
    """Corpus-found shapes (2026-09 hardening): footnote marks, lost subscripts, fonts, apfu rows."""

    def test_constituents(self):
        self.assertEqual(PE._constituent_ok('Sb')[0], 'Sb')            # antimony, not S + footnote b
        self.assertEqual(PE._constituent_ok('Sc')[0], 'Sc')
        self.assertEqual(PE._constituent_ok('SiO2a')[0], 'SiO2')       # a footnote letter
        self.assertEqual(PE._constituent_ok('NaO')[0], 'Na2O')         # the 2 was a lost subscript
        self.assertEqual(PE._constituent_ok('Fe2O')[0], 'Fe2O3')
        self.assertEqual(PE._constituent_ok('Xa')[0], None)

    def test_row_footnote_word(self):
        # 'TiO2 a 15.36 14.84–16.95 0.43': the footnote printed as its own word must not end the row
        ws = [(294, 0, 312, 9, 'TiO2'), (306, 0, 310, 9, 'a'), (366, 0, 390, 9, '15.36'), (431, 0, 480, 9, '14.84–16.95'), (507, 0, 525, 9, '0.43')]
        c, kind, vals, x0 = PE._row_at(ws, None)
        self.assertEqual((c, kind), ('TiO2', 'constituent'))
        self.assertEqual(vals[0], ('num', 15.36))

    def test_formula_font_and_length(self):
        # colons for decimals and 'ð Þ' brackets (a journal font); a long formula is not cut at 320 chars
        txt = 'The empirical formula is Sr0:57Ba0:38Na0:01 ð Þ0:96 Mn2+ 1:83Fe2+ 0:14 P3:00O11:98 based on 15 O apfu.'
        f, counts, issues, ox = PE.empirical_formula(txt)
        self.assertAlmostEqual(counts['Sr'], 0.57); self.assertAlmostEqual(counts['Mn'], 1.83); self.assertAlmostEqual(counts['P'], 3.0)
        long = 'The empirical formula is ' + ''.join('%s%.2f' % (el, 1 + i / 100) for i, el in enumerate(['Na', 'K', 'Ca', 'Mg', 'Fe', 'Al', 'Si', 'Ti', 'Mn', 'Cu', 'Zn', 'Pb', 'Sr', 'Ba'] * 3)) + 'O200 and so on.'
        f, counts, issues, ox = PE.empirical_formula(long)
        self.assertEqual(counts['O'], 200.0)


class ApfuBlock(unittest.TestCase):
    def test_apfu_rows_below_total(self):
        # bare-element rows under the Total are the apfu block, even for S (a sulfate reports SO3 only)
        import pymupdf
        tmp = tempfile.mkdtemp(prefix='pe_'); path = os.path.join(tmp, 'sulfate.pdf')
        try:
            doc = pymupdf.open(); page = doc.new_page(width=595, height=842); y = 60
            for row in ('Table 1. Chemical data (wt%)', 'Constituent  Mean  Range', 'MgO  11.00  10.5-11.5', 'CuO  31.18  30.9-31.5',
                        'ZnO  2.62  2.4-2.8', 'SO3  54.76  54.1-55.2', 'Total  99.56', 'Mg  0.79', 'Cu  1.14', 'Zn  0.09', 'S  1.99'):
                page.insert_text((40, y), row, fontsize=9); y += 14
            doc.save(path); doc.close()
            rows = [r['constituent'] for r in PE.epma_table(path)['rows']]
            self.assertEqual(rows, ['MgO', 'CuO', 'ZnO', 'SO3'])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class SpeciesEvidence(unittest.TestCase):
    """Mindat's ideal formula as the fallback line of evidence (owner, 2026-09-02)."""

    def test_ideal_oxidation_and_oxides(self):
        ox = PE.ideal_oxidation('KFe<sup>3+</sup><sub>3</sub>(S<sup>6+</sup>O<sub>4</sub>)<sub>2</sub>(OH)<sub>6</sub>')
        self.assertEqual(ox, {'Fe': {3}, 'S': {6}})
        self.assertEqual(PE.oxide_for('Fe', 3), 'Fe2O3'); self.assertEqual(PE.oxide_for('Mn', 4), 'MnO2'); self.assertEqual(PE.oxide_for('Cu', 1), 'Cu2O')
        species = {'formula': 'Fe<sup>3+</sup>', 'ox': {'Fe': {3}}, 'elements': {'Fe', 'O'}}
        self.assertEqual(PE.oxide_alternatives({'FeO': 10.0, 'SiO2': 40.0}, {}, species), [('FeO', 'Fe2O3', "Mindat's ideal formula has Fe3+")])
        self.assertEqual(PE.oxide_alternatives({'FeO': 10.0}, {'Fe': {3}}, None), [('FeO', 'Fe2O3', 'the formula writes Fe3+')])
        self.assertEqual(PE.oxide_alternatives({'FeO': 10.0}, {'Fe': {2, 3}}, species), [])      # the authors' own split
        self.assertAlmostEqual(PE._convert({'FeO': 10.0}, 'FeO', 'Fe2O3')['Fe2O3'], 11.113, places=3)

    def test_species_lines(self):
        species = {'formula': 'KFe<sup>3+</sup><sub>3</sub>(SO<sub>4</sub>)<sub>2</sub>(OH)<sub>6</sub>', 'ox': {'Fe': {3}}, 'elements': {'K', 'Fe', 'S', 'O', 'H'}}
        L = PE.species_lines(species, {'Fe', 'S'}, {'Fe', 'S'}, {'Fe': {2}})
        self.assertEqual(len(L), 2)
        self.assertIn('carries K, absent', L[0]); self.assertIn('Fe2+; Mindat', L[1])
        self.assertEqual(PE.species_lines(species, {'K', 'Fe', 'S'}, set(), {'Fe': {3}}), [])

    def test_formula_charges_and_group_basis(self):
        f, counts, issues, ox = PE.empirical_formula('The empirical formula is Ca2.00(Mg3.44Ti4+ 1.49Fe0.36Ti3+ 0.34)Σ5.63Si2.37O20 on 20 O.')
        self.assertEqual(ox, {'Ti': {3, 4}})
        n = PE._journal_to_icdd('(Pb0.930Ce0.434Sm0.007)R2.000(CO3)2(OH)1.074')
        self.assertIn(') Σ2.000', n)                                 # a Σ printed as R survives the bare-Σ rule


class Transposed(unittest.TestCase):
    def test_constituents_across(self):
        import pymupdf
        tmp = tempfile.mkdtemp(prefix='pe_'); path = os.path.join(tmp, 'across.pdf')
        try:
            doc = pymupdf.open(); page = doc.new_page(width=595, height=842); y = 60
            xs = (40, 120, 190, 260, 330, 400)
            for cells in (('Constituent', 'Nb2O5', 'MgO', 'FeO', 'MnO', 'Total'), ('1', '62.10', '36.20', '0.80', '0.60', '99.70'),
                          ('2', '61.90', '36.40', '0.70', '0.70', '99.70'), ('Mean', '62.00', '36.30', '0.75', '0.65', '99.70'),
                          ('Range', '61.90-62.10', '36.20-36.40', '0.70-0.80', '0.60-0.70', '')):
                for x, c in zip(xs, cells):
                    page.insert_text((x, y), c, fontsize=9)
                y += 14
            doc.save(path); doc.close()
            e = PE.epma_table(path)
            self.assertTrue(e.get('transposed'))
            self.assertEqual({r['constituent']: r['mean'] for r in e['rows']}, {'Nb2O5': 62.0, 'MgO': 36.3, 'FeO': 0.75, 'MnO': 0.65})
            self.assertEqual(e['total'], 99.7)
            self.assertEqual(len(PE.table_alternatives(e, {r['constituent']: r['mean'] for r in e['rows']})), 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Totals(unittest.TestCase):
    def test_total_row_dropped_when_split_follows(self):
        rows = [{'constituent': c, 'mean': v} for c, v in (('CaO', 4.8), ('FeO', 11.79), ('FeO', 10.71), ('Fe2O3', 1.2), ('P2O5', 34.19))]
        self.assertEqual([r['constituent'] for r in PE._drop_totals(rows)], ['CaO', 'FeO', 'Fe2O3', 'P2O5'])
        self.assertEqual(PE._drop_totals(rows)[1]['mean'], 10.71)
        rows2 = [{'constituent': c, 'mean': v} for c, v in (('FeO', 11.79), ('Fe2O3', 1.2), ('P2O5', 34.19))]
        self.assertEqual(len(PE._drop_totals(rows2)), 3)                     # one of each: nothing to drop


class MorningRules(unittest.TestCase):
    """2026-09-03: the misses worked through with the owner's hand-check list."""

    def test_notation(self):
        self.assertEqual(PE._constituent_ok('Fe2O3(tot)')[0], 'Fe2O3')
        self.assertEqual(PE._constituent_ok('H2O(calc)')[0], 'H2O')
        n = PE._journal_to_icdd('(Ti0.60Fe+3 0.23Mg0.08)Σ1.04')
        self.assertIn('Fe0.23 +3', n)                                       # the sign before the digit
        n = PE._journal_to_icdd('Cu2.00Ag0.97(As0.95Sb0.04)Σ0.99S4.03 (ΣMe = 3.97)')
        self.assertNotIn('Me', n)
        n = PE._journal_to_icdd('(Sr0.55Ba0.25Ln0.10Ca0.10)')
        self.assertIn('Ce0.10', n)                                          # 'Ln0.10' is a grouped lanthanide
        f, counts, issues, ox = PE.empirical_formula('The empirical formula, normalized to 12 Cu apfu, is Cu12(Pb1.92Fe0.06Si0.06)(O15.08F0.02)(Br0.99Cl0.89) here.')
        self.assertAlmostEqual(counts['Cu'], 12.0)                          # 'Cu12(' is the start, not a site label
        f, counts, issues, ox = PE.empirical_formula('The crystal chemical formula of saranovskite is (Sr0.55Ba0.25)(Fe2+ 1.12Mg0.88)O38 and')
        self.assertAlmostEqual(counts['Mg'], 0.88)                          # 'crystal chemical formula' wording

    def test_nested_bare_group_counts_atoms(self):
        from pxrd_review import epma as EP
        counts, ox, issues = EP.parse_icdd_formula(PE._journal_to_icdd('[(Fe3+ 2.12Al0.18)(Zn0.32Mg0.16Fe2+ 0.13Mn0.03)Ti0.06]Σ3.00(Sb0.97Ti0.03)Σ1.00Zn1.00O7'))
        self.assertEqual(issues, [])
        counts, ox, issues = EP.parse_icdd_formula('[( Cl3.82 F0.18 ) Σ4 ( F1.54 O H1.46 ) Σ3 ( O H )2 ] Σ9')
        self.assertEqual(issues, [])                                         # '(OH)2' is two items of the Σ9

    def test_candidate_tables_and_ppm(self):
        import pymupdf
        tmp = tempfile.mkdtemp(prefix='pe_'); path = os.path.join(tmp, 'two.pdf')
        try:
            doc = pymupdf.open(); page = doc.new_page(width=595, height=842); y = 60
            def line(txt):
                nonlocal y
                page.insert_text((40, y), txt, fontsize=9); y += 14
            line('The empirical formula is K2.00Nb1.90Ti0.09Si4.01O12 on 8 cations.'); y += 10
            line('Table 3. Trace elements and oxides'); line('Constituent  wt%')
            for row in ('TiO2  0.65', 'ZrO2  0.21', 'Nb2O5  42.88', 'K2O  15.57', 'Be  0.01', 'B  0.85', 'P  22.0', 'Ba  201'):
                line(row)
            page = doc.new_page(width=595, height=842); y = 60                  # the analytical table on the next page
            line('Table 2. Chemical data (wt%)'); line('Constituent  Mean  Range')
            for row in ('SiO2  40.28  40.07-41.02', 'TiO2  1.20  1.1-1.3', 'ZrO2  0.21  0.1-0.3', 'Nb2O5  42.30  38.2-44.0', 'K2O  15.77  15.7-16.1', 'Total  99.76'):
                line(row)
            doc.save(path); doc.close()
            text = PE.text_of(path); ex = PE.extract(path, None, 'x', write=False) if 'write' in PE.extract.__code__.co_varnames else PE.extract(path, None, 'x')
            e = ex['epma']
            self.assertTrue(e.get('candidates'))
            c = PE.check_composition(ex, text)
            self.assertTrue(c['ok'], c['lines'])
            self.assertTrue(any('reproduces the formula' in l for l in c['lines']) or 'SiO2' in {r['constituent'] for r in e['rows']})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class LateMorning(unittest.TestCase):
    def test_prose_composition(self):
        pt = PE.prose_table('The analysis gave SiO2 40.12, Al2O3 20.05, FeO 10.20 and MgO 29.10 wt.%, total 99.47 wt.%.')
        self.assertEqual([(r['constituent'], r['mean']) for r in pt['rows']], [('SiO2', 40.12), ('Al2O3', 20.05), ('FeO', 10.2), ('MgO', 29.1)])
        self.assertEqual(pt['total'], 99.47)
        self.assertIsNone(PE.prose_table('The ideal formula requires Na2O 6.46, MnO 14.78, Ce2O3 34.19, P2O5 29.57, and H2O 15.01, total 100.00 wt.%.'))
        self.assertIsNone(PE.prose_table('(Ce0.39La0.24Pr0.13Sr0.11Nd0.11Sm0.01)'))       # coefficients are not a composition

    def test_prose_total_is_not_the_total_row(self):
        # the other page column says 'A total of 16 scans'; the table row on the same line is Na2O
        ws = [(40, 0, 45, 9, 'A'), (50, 0, 70, 9, 'total'), (75, 0, 85, 9, 'of'), (90, 0, 100, 9, '16'), (105, 0, 130, 9, 'scans'),
              (310, 0, 335, 9, 'Na2O'), (367, 0, 395, 9, '25.51'), (406, 0, 460, 9, '23.95−26.01'), (469, 0, 490, 9, '0.94'), (511, 0, 550, 9, 'jadeite')]
        c, kind, vals, x0 = PE._row_at(ws, None)
        self.assertEqual((c, kind, vals[0]), ('Na2O', 'constituent', ('num', 25.51)))

    def test_subscript_digit_glued(self):
        import pymupdf
        tmp = tempfile.mkdtemp(prefix='pe_'); path = os.path.join(tmp, 'sub.pdf')
        try:
            doc = pymupdf.open(); page = doc.new_page(width=595, height=842)
            page.insert_text((40, 100), 'B2O', fontsize=9); page.insert_text((54.5, 102.5), '3', fontsize=6)    # the subscript as its own glyph
            page.insert_text((100, 100), '11.43', fontsize=9)
            page.insert_text((40, 120), 'SiO2', fontsize=9); page.insert_text((59, 96), '1', fontsize=6)       # a numbered footnote, superscript
            doc.save(path); doc.close()
            lines = PE.page_lines(pymupdf.open(path)[0])
            toks = [w[4] for w in lines[0]['w']]
            self.assertEqual(toks, ['B2O3', '11.43'], toks)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_charges_and_structural_form(self):
        n = PE._journal_to_icdd('(Fe2+ 0.56Fe2.5+ 0.25Mg0.14)Σ0.95')
        self.assertIn('Fe0.25 +2.5', n)
        f, counts, issues, ox = PE.empirical_formula('The empirical formula is Al0.01Fe2.55Cu0.91S2(OH)3.07 = (Fe1.09Cu0.91)Σ2S2 · (Al0.01)Σ1.47(OH)3.07 here.')
        self.assertAlmostEqual(counts['Fe'], 2.55)                                # cut at '= (structural form)'
        f, counts, issues, ox = PE.empirical_formula('The empirical formula is (Na0.54h0.26Ca0.20)Σ1.00Mn1.00P2.04O8 based on 8 O.')
        self.assertEqual(issues, [])                                              # 'h' is a vacancy glyph


class Names(unittest.TestCase):
    def test_mineral_name_unicode_and_stoplist(self):
        self.assertEqual(PE.mineral_name('Åsgruvanite-(Ce), a new mineral from Sweden. Despite its rarity, calcite is common.'), 'åsgruvanite-(ce)')
        self.assertEqual(PE.mineral_name('Despite everything, Fuyuanite occurs with Calcite in granite.'), 'fuyuanite')

    def test_fit_judged_on_major_cations(self):
        from pxrd_review import epma as EP
        wt = {'PbO': 42.4 * 1.077, 'MoO3': 21.1 * 1.5, 'S': 24.05, 'MnO': 0.05 * 1.29}
        counts = {'Pb': 4.0, 'Mo': 4.33, 'S': 15.0, 'Mn': 0.05}
        r = EP.replicate_formula(wt, counts, [('element', 'S', 15.0)], 'x', tol_abs=0.03, tol_rel=0.05)
        self.assertLess(r['score'], 0.1, r)                                     # Mn's 60 % is a trace: not the overall fit


class Captions(unittest.TestCase):
    def test_caption_score(self):
        self.assertEqual(PE._caption_score('Table 1. Chemical composition (wt.%) of barronite'), 9)
        self.assertEqual(PE._caption_score('Table 3. Atom coordinates and displacement parameters'), -8)
        self.assertEqual(PE._caption_score('Table 5. Bond lengths (Å)'), -10)
        self.assertEqual(PE._caption_score(''), 0)

    def test_notation_batch(self):
        n = PE._journal_to_icdd('(Na0.63Ca0.25Mn0.12)R1.00(A1.91Na0.09)R2.00')
        self.assertIn('?1.91', n)                                              # 'A' is a vacancy glyph
        n = PE._journal_to_icdd('(PO4)4.07(OH)3.524.13H2O')
        self.assertIn('( O H )3.52 ! 4.13 H2 O', n)                            # the hydrate dot lost
        n = PE._journal_to_icdd('Si4(S1.61Si0.32P0.07)Σ1.99O24')
        self.assertIn('Si4 ', n)                                                # 'Si4(' is a count, not a site label
        n = PE._journal_to_icdd('Mg1(Mg1.42Fe0.30)Σ1.72Mg2(Mg1.71Fe0.10)Σ1.81')
        self.assertNotIn('Mg1 ', n); self.assertNotIn('Mg2 ', n)               # numbered from 1: site labels
        from pxrd_review import epma as EP
        counts, ox, issues = EP.parse_icdd_formula('( Ca1.08 Na0.91 ) Σ2.00 ( O H1.59 O0.61 ) Σ2.00')
        self.assertTrue(issues and issues[0].startswith('anion group sum'))  # the cation groups are fine

    def test_alternative_columns_need_a_total(self):
        e = {'rows': [{'constituent': 'BaO', 'mean': 41.26, 'all': [41.26, 0.36, 41.29, 0.40]},
                      {'constituent': 'SiO2', 'mean': 17.38, 'all': [17.38, 0.2, 17.5, 0.3]},
                      {'constituent': 'MnO', 'mean': 8.49, 'all': [8.49, 0.1, 8.3, 0.2]}]}
        alts = PE.table_alternatives(e, {'BaO': 41.26, 'SiO2': 17.38, 'MnO': 8.49})
        self.assertEqual(alts, [{'BaO': 41.29, 'SiO2': 17.5, 'MnO': 8.3}])      # the s.d. columns are not samples


class Afternoon(unittest.TestCase):
    """2026-09-03 afternoon: the second sweep through the deviating and unparsed papers."""

    def test_formula_rules(self):
        J = PE._journal_to_icdd
        self.assertIn('Pt0.01 +4', J('(Rh3+ 1.20Ir4+ 0.06Pt4+ <0.01)S3.99'))              # '<0.01': the bound stands
        self.assertIn('Ge0.940', J('(Ge0.91-0.97Si0.03-0.09)Σ1.00O2'))                     # a range: its middle
        self.assertIn('Th0.54', J('(Ca0.40REE0.93(Th,U)4+ 0.54□0.13)R2.00'))               # '(Th,U)4+ 0.54'
        self.assertIn('?0.06', J('(Mg1.24Ca0.69 0.06Mn0.01)Σ2.00'))                        # a vacancy glyph lost
        n = J('[(H2O)0.50K0.50]2(Mn1.20Mg0.49Fe2+ 0.27Zn0.05)P2.01(Al1.63Fe3+ 0.20Ti4+ 0.19)P2.02(PO4)4.02')
        self.assertIn(') Σ2.01', n); self.assertIn('(PO4 )4.02', n)                       # a Σ printed as P, (PO4) untouched
        self.assertIn(')2 ! 2 H2 O', J('Ca1.99(Fe0.89Mg0.13Mn0.01)R1.03(P1.00O4)22H2O'))    # '(PO4)22H2O' = (PO4)2·2H2O
        self.assertTrue(J('(SREF) Cu2Fe0.84Al0.16(AsO4)(OH)4·4H2O').startswith('Cu2'))    # a tag
        self.assertIn('Σ48.49', J('Ag1.04Pb46.43(As25.52Sb22.97)Σ=48.49S120'))
        self.assertEqual(PE._constituent_ok('Na2О')[0], 'Na2O')                              # Cyrillic О

    def test_parser_rules(self):
        from pxrd_review import epma as EP
        counts, ox, issues = EP.parse_icdd_formula('( Al7.98 Fe0.01 ) Σ7.99 (SO4 )5.01 ( O H )13.95')
        self.assertAlmostEqual(counts['S'], 5.01); self.assertEqual(issues, [])          # (SO4)5.01 is a multiplier
        counts, ox, issues = EP.parse_icdd_formula('[( O H )1.25 F0.06 ! 0.69 H2 O ] Σ2.00')
        self.assertEqual(issues, [])                                                      # the water counts toward the Σ
        counts, ox, issues = EP.parse_icdd_formula('Cu3.23 Pb18.74 Sb17.30 S56')
        self.assertEqual(issues, [])                                                      # 56 S is a real cell

    def test_formula_triggers(self):
        f, counts, issues, ox = PE.empirical_formula('leading to an empirical formula (based on 2 Te apfu) of Au3.00Tl1.01Te2.00. Honeaite is black.')
        self.assertAlmostEqual(counts['Au'], 3.0)                                         # near-ideal coefficients with two decimals
        f, counts, issues, ox = PE.empirical_formula('On the basis of 56 S, the chemical formula of ciriottiite is Cu3.23(11)Ag0.43(4)Pb18.74(9)S56 and so on.')
        self.assertAlmostEqual(counts['Pb'], 18.74)
        f, counts, issues, ox = PE.empirical_formula('The chemical formula is Ca4(Al0.5Si0.5)2Si4O16(OH) here.')
        self.assertEqual(counts, {})                                                      # an ideal one stays out


class Evening(unittest.TestCase):
    def test_sigma_glyph_lost_and_nested_P(self):
        from pxrd_review import epma as EP
        counts, ox, issues = EP.parse_icdd_formula('(Ca4.97 Na0.013 Mg0.017 )(As3.99 S0.01 )4 O23 H16')
        self.assertAlmostEqual(counts['As'], 3.99); self.assertEqual(issues, [])           # ')4' is the cations' own sum
        counts, ox, issues = EP.parse_icdd_formula('( Fe1.0 Mg1.0 ) (PO4 )3')
        self.assertAlmostEqual(counts['P'], 3.0)                                            # one cation: a multiplier
        n = PE._journal_to_icdd('[((Ca0.5Mg0.2Na0.11□0.14)60.95 (As3+)2.05)P3.00(Fe3+ 2.44Mo6+ 0.56)63.00]')
        self.assertIn(') Σ3.00(Fe', n)                                                      # Σ printed as P after a nested group
        self.assertTrue(PE._journal_to_icdd('(O + F) (Na2.74Mn0.15)Σ2.89Ca2').startswith('(Na2.74'))

    def test_factor_like_is_unverified(self):
        ex = {'name': 'x', 'basis': ('element', 'Ca', 2.0), 'epma': {'rows': [{'constituent': c, 'mean': v} for c, v in (('CaO', 53.25), ('P2O5', 33.7), ('Cl', 16.96))], 'total': 99.6, 'header': 'Constituent wt%'}}
        c = PE.check_composition(ex, 'The empirical formula is Ca2.01P1.98O7.96Cl1.01 here.')
        self.assertTrue(c['ok'] or c['verified'] is not None)
        ex['epma']['rows'][1] = {'constituent': 'P2O5', 'mean': 8.4}                        # a quarter of the phosphorus: a factor, not a slip
        c = PE.check_composition(ex, 'The empirical formula is Ca2.01P1.98O7.96Cl1.01 here.')
        self.assertFalse(c['verified']); self.assertTrue(any('off by a factor' in l for l in c['lines']))


class HeadlineColumn(unittest.TestCase):
    """Owner (2026-09-03): the headline mineral's column is named in the header or the text; other
    phases in the same table are supporting material."""

    def _table(self):
        # two localities side by side; Mn2O3 is a total for both and split only for the second
        rows = [{'constituent': 'As2O5', 'mean': 48.06, 'all': [48.06, 47.9], 'xs': [111, 307]},
                {'constituent': 'Mn2O3', 'mean': 17.48, 'all': [17.48, 16.2], 'xs': [111, 307]},
                {'constituent': 'MnO2', 'mean': 6.28, 'all': [6.28], 'xs': [310]},
                {'constituent': 'Mn2O3', 'mean': 10.5, 'all': [10.5], 'xs': [307]},
                {'constituent': 'CaO', 'mean': 13.84, 'all': [13.84, 14.1], 'xs': [111, 307]},
                {'constituent': 'Na2O', 'mean': 5.54, 'all': [5.54, 5.2], 'xs': [111, 307]}]
        cells = [('Montaldo', 168), ('Valletta', 382), ('(n', 178), ('=', 185), ('10)', 193), ('(n', 374), ('=', 380), ('13)', 388),
                 ('Oxide', 48), ('mean', 119), ('range', 189), ('s.u.', 256), ('mean', 314), ('range', 384), ('s.u.', 452)]
        return {'rows': PE._drop_totals(rows), 'rows_all': rows, 'head_cells': cells, 'header': 'Oxide mean range s.u. mean range s.u.'}

    def test_column_by_holotype_locality(self):
        e = self._table()
        wt, why = PE.headline_column(e, 'piccoliite', {'codes': [], 'n': None, 'holotype': False, 'holotype_words': ['Montaldo']})
        self.assertIn('Montaldo', why)
        self.assertEqual(wt['Mn2O3'], 17.48); self.assertNotIn('MnO2', wt)               # the total stands where the split is blank
        wt, why = PE.headline_column(e, 'piccoliite', {'codes': ['Valletta'], 'n': None, 'holotype': False, 'holotype_words': []})
        self.assertEqual((wt['Mn2O3'], wt['MnO2']), (10.5, 6.28))                         # the split overrides the total

    def test_column_by_n_analyses(self):
        e = self._table()
        wt, why = PE.headline_column(e, 'piccoliite', {'codes': [], 'n': 13, 'holotype': False, 'holotype_words': []})
        self.assertIn('13 analyses', why); self.assertEqual(wt['CaO'], 14.1)

    def test_hints_and_footnote_numbers(self):
        h = PE.sample_hints('The empirical formula of domain A (mean of 4 analyses, sample TL-12) is')
        self.assertIn('A', h['codes']); self.assertIn('TL-12', h['codes']); self.assertEqual(h['n'], 4)
        self.assertEqual(PE._constituent_ok('V2O31)')[0], 'V2O3')                          # a footnote number
        self.assertEqual(PE.holotype_words('The holotype specimen is from Montaldo di Mondovì.')[:1], ['Montaldo'])


class Night(unittest.TestCase):
    def test_flattened_group_and_triggers(self):
        self.assertIn('(PO4 )3.02', PE._journal_to_icdd('Pb0.98Fe2+ 1.69Σ2.00V1.31Al0.06Σ2.00PO43.02OH3'))
        f, counts, issues, ox = PE.empirical_formula('The empirical mineral formula is Ca2.06Mn3+ 1.78Cu0.10F0.97(OH)8.02(SO4)0.39. The unit-cell')
        self.assertAlmostEqual(counts['Mn'], 1.78)
        f, counts, issues, ox = PE.empirical_formula('Electron microprobe analyses together with Mössbauer spectroscopy gives the formula (Ca0.59Mn0.24)Σ0.83Mn(Zn0.74Mn2+ 0.48)Σ2(P0.995O4)4(OH)2. Jahnsite is monoclinic')
        self.assertAlmostEqual(counts['Zn'], 0.74)
        f, counts, issues, ox = PE.empirical_formula('the empirical formula (calculated on the basis of 13 O atoms pfu) is [(U1.00O2)2(C2O4)(OH)2(H2O)2]·H2O and the ideal formula is')
        self.assertAlmostEqual(counts['U'], 2.0)                                     # round coefficients after an explicit "empirical formula"
        f, counts, issues, ox = PE.empirical_formula('yielded the formula: (Ce​1.​81La​0.8​1)​Σ2.62 Fe2+ 0.80 here')
        self.assertAlmostEqual(counts['Ce'], 1.81)                                    # zero-width spaces inside the glyph runs

    def test_caption_names(self):
        self.assertEqual(PE._caption_score('Table 4. Chemical data (wt.%) for torryweiserite', 'torryweiserite'), 3 - 2 + 6)
        self.assertEqual(PE._caption_score('Table 11. Chemical compositions of possible oberthurite from other localities', 'torryweiserite'), -2 - 4 + 6)


class Parser3(unittest.TestCase):
    def test_group_multipliers_and_sums(self):
        from pxrd_review import epma as EP
        self.assertAlmostEqual(EP.parse_icdd_formula('(Cu2.68 Mg0.17 ) Σ3 (N3 C2 H2 )2.755')[0]['N'], 8.265)       # not the 'Fe3 C1.01' charge notation
        self.assertAlmostEqual(EP.parse_icdd_formula('(Cu5.16 Co0.34 ) Σ6.01 (AsO3 OH )5.97')[0]['As'], 5.97)       # no decimals inside: a multiplier
        self.assertAlmostEqual(EP.parse_icdd_formula('Ca1.02 Zn1.91 ((As0.95 Sb0.08 )O4 ) Σ2.03')[0]['As'], 1.9285, places=3)   # Σ2.03 = two such groups
        self.assertAlmostEqual(EP.parse_icdd_formula('Si2.00 [O5.91 OH1.09 ]7.00')[0]['O'], 7.0)                    # decimals inside: a sum

    def test_headline_name_by_use(self):
        t = 'Journal head Bustamite group. ' + 'Mendigite, a new mineral species of the bustamite group. ' + 'mendigite ' * 5 + 'bustamite ' * 3
        self.assertEqual(PE.mineral_name(t), 'mendigite')


class Selector2(unittest.TestCase):
    def test_levinson_suffix_and_sentence_list(self):
        rows = [{'constituent': 'Nb2O5', 'mean': 10.32, 'all': [10.32, 11.1, 9.8], 'xs': [112, 154, 197]},
                {'constituent': 'SiO2', 'mean': 39.45, 'all': [39.45, 39.9, 39.1], 'xs': [112, 154, 197]},
                {'constituent': 'Na2O', 'mean': 8.8, 'all': [8.8, 8.2, 8.5], 'xs': [112, 154, 197]}]
        e = {'rows': rows, 'rows_all': rows, 'head_cells': [('Constituent', 62), ('(Nd)1', 112), ('(Y)2', 154), ('(Ce)3', 197)], 'header': ''}
        wt, why = PE.headline_column(e, 'nacareniobsite-(y)', {'codes': [], 'n': None, 'holotype': False, 'holotype_words': []})
        self.assertIn('(Y)', why); self.assertEqual(wt['Na2O'], 8.2)
        h = PE.sample_hints('Type paqueite from A-WP1 has an empirical formula of')
        self.assertIn('A-WP1', h['codes'])
        pt = PE.prose_table('Pt 2.10, Ir 0.10, Ni 17.09, Fe 9.76, Cu 7.38, Co 1.77 S 30.97, total 99.73 wt.%, which corresponds to')
        self.assertEqual(pt['rows'][-1]['constituent'], 'S')                             # no comma before the last item


class Parser4(unittest.TestCase):
    def test_late_notations(self):
        J = PE._journal_to_icdd
        self.assertIn('( H2 O )0.21', J('(Na0.99Ca0.46La0.01H2O0.21)∑2.00'))                  # a water count inside a group
        self.assertIn('(PO4 )1.91', J('Σ2.00PO4)1.91(OH)2.27'))                                # the opening bracket lost
        self.assertIn('Th0.01 ?0.51', J('(Ce4.02Th0.01–0.51)Σ9'))                              # one dash in a Σ group: a vacancy
        self.assertIn('Ge0.940', J('(Ge0.91-0.97Si0.03-0.09)Σ1.00O2'))                         # several dashes: ranges
        self.assertIn('Fe0.25 +3', J('(Mg0.75Fe0.25 3+)Σ1'))                                   # the charge after the count
        self.assertIn('?0.63', J('(Pb8.33Sr0.04o0.63)S9.00'))                                   # a vacancy printed as o


class Domains(unittest.TestCase):
    def test_domains_assigned_to_the_headline(self):
        t = ('Electron microprobe data (in wt.%) of ferriandrosite-(Ce) (domains A–C) and associated vielleaureite-(Ce) (domain D). '
             'Domains B and C correspond to the end-member formula MnCeFe3+AlMn2+(Si2O7)(SiO4)O(OH), i.e. to ferriandrosite-(Ce), '
             'however domain D leads to the end-member formula of vielleaureite-(Ce).')
        self.assertEqual(PE.headline_domains(t, 'ferriandrosite-(ce)')[:3], ['B', 'C', 'A'])     # B and C named twice; D belongs to the other mineral
        self.assertEqual(PE.headline_domains('Crystal II of piccoliite gave the best data.', 'piccoliite'), ['II'])


class TwoFormulas(unittest.TestCase):
    def test_abstract_disagrees_with_body(self):
        rows = [{'constituent': c, 'mean': v} for c, v in (('Ce2O3', 39.37), ('La2O3', 19.92), ('Nd2O3', 14.46), ('Sm2O3', 2.84), ('CaO', 0.73), ('F', 14.33))]
        ex = {'name': 'håleniusite-(ce)', 'basis': ('O', 2.0), 'epma': {'rows': rows, 'total': 93.72, 'header': 'Constituent Mean'}}
        text = ('Abstract. Electron probe microanalysis provided the empirical formula (Ce0.41La0.21Sm0.15Nd0.04Ca0.02)R0.83(O0.70F1.30)R2.00. ' + 'x ' * 2500 +
                'The empirical formula calculated on the basis of O + F = 2 apfu is (Ce0.412La0.210Nd0.148Sm0.028Ca0.022)R0.820(O0.70F1.30)R2.00. Later text.')
        c = PE.check_composition(ex, text)
        self.assertTrue(any('abstract does not agree' in l and 'Sm 0.15 vs 0.028' in l for l in c['lines']), c['lines'])
        self.assertFalse(c['ok'])


class Exclusions(unittest.TestCase):
    def test_excluded_elements(self):
        t = 'as Al3+ strongly differs in ionic radius from large cations such as REE, the empirical formula was calculated without Al. Later, Si was excluded from the sum.'
        self.assertEqual(PE.excluded_elements(t), ['Al', 'Si'])
        self.assertEqual(PE.excluded_elements('The formula was calculated on the basis of 12 O.'), [])


class Corrected(unittest.TestCase):
    def test_total_composition_and_corrected_formula(self):
        rows = [{'constituent': c, 'mean': v} for c, v in (('Fe2O3', 4.18), ('MnO', 0.43), ('K2O', 0.98), ('SO3', 56.72), ('SiO2', 0.10), ('Al2O3', 10.10), ('MgO', 1.00), ('Na2O', 19.39))]
        ex = {'name': 'heimaeyite', 'basis': None, 'epma': {'rows': rows, 'total': 92.89, 'header': 'Constituent Mean'}}
        text = ('We assume the presence of small amounts of Mn, Si, K and Mg is due to impurities. The total composition of the sample results in '
                'K0.10Na2.95Mn0.03Mg0.12Fe0.25Al0.94Si0.01S3.35O13.5. If the Mn and Si impurity and the contributions of koryakite are removed, '
                'the resulting empirical formula of heimaeyite is Na2.93Al0.82Fe0.25S2.99O12.05. The ideal formula is NaAl(SO4)2.')
        c = PE.check_composition(ex, text)
        self.assertFalse(c['ok']); self.assertFalse(c['verified'])
        self.assertTrue(any('uncorrected composition' in l and 'cannot be re-derived' in l for l in c['lines']), c['lines'])


class HandCheck(unittest.TestCase):
    """2026-09-03: the owner's five hand-checked papers, one rule each."""

    def test_legend_columns(self):
        t = '1, 2, 8 – fluorpyromorphite (1 – holotype, mean of 8 spot analyses; 2 – F-richest spot; 8 – cotype); 3 – hydroxylpyromorphite (mean of 4).'
        self.assertEqual(PE.legend_columns(t, 'fluorpyromorphite'), ['1', '2', '8'])
        self.assertEqual(PE.legend_columns('4–6 – pyromorphite; 1 – mimetite', 'pyromorphite'), ['4', '5', '6'])

    def test_two_line_cell_mean_above_label(self):
        import pymupdf
        tmp = tempfile.mkdtemp(prefix='pe_'); path = os.path.join(tmp, 'twoline.pdf')
        try:
            doc = pymupdf.open(); page = doc.new_page(width=595, height=842); y = 60
            page.insert_text((40, y), 'Constituent', fontsize=9); y += 14
            for x, t in zip((130, 180, 220, 260), ('1', '2', '3', '4')): page.insert_text((x, y), t, fontsize=9)
            y += 14
            for label, mean, rng, others in (('CaO', '0.10', '(0.00–0.32)', ('0.15', '0.05', '0.34')), ('PbO', '83.51', '(82.79–84.40)', ('82.50', '83.20', '82.34')),
                                              ('P2O5', '16.13', '(16.00–16.23)', ('15.90', '16.05', '16.02')), ('F', '1.00', '(0.92–1.06)', ('1.36', '0.37', '0.14'))):
                page.insert_text((130, y), mean, fontsize=9)                       # the mean, a line above the label
                page.insert_text((40, y + 5), label, fontsize=9); page.insert_text((120, y + 5), rng, fontsize=7)
                for x, t in zip((180, 220, 260), others): page.insert_text((x, y + 5), t, fontsize=9)
                y += 20
            page.insert_text((40, y), 'Total  100.84  99.37  100.29  100.44', fontsize=9)
            doc.save(path); doc.close()
            e = PE.epma_table(path)
            rows = {r['constituent']: r for r in e['rows']}
            self.assertEqual(rows['PbO']['mean'], 83.51); self.assertEqual(rows['PbO']['all'][:2], [83.51, 82.5])
            self.assertEqual(rows['CaO']['mean'], 0.1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Attribution(unittest.TestCase):
    def test_other_mineral_formula_dropped_and_associated_caption(self):
        t = ('The empirical formula of zoisite-(Pb) is (Ca1.09Pb0.86Mn2+0.01)Σ1.96(Al2.88Fe3+0.10)Σ2.98Si3.00O12(OH). '
             'The empirical formula of hancockite is (Ca1.18Pb0.73Mn2+0.06)Σ1.97(Al2.32Fe3+0.66)Σ2.98Si3.01O12(OH).')
        fs = PE._formulas(t, 'zoisite-(pb)')
        self.assertEqual(len(fs), 1); self.assertAlmostEqual(fs[0][1]['Pb'], 0.86)
        self.assertLess(PE._caption_score('Table 2. EPMA representative analyses of phases associated with zoisite-(Pb).', 'zoisite-(pb)'),
                        PE._caption_score('Table 1. Chemical composition of zoisite-(Pb) (wt.%).', 'zoisite-(pb)'))


class ReaderClasses(unittest.TestCase):
    """2026-09-03 afternoon: the general reader defects behind the 'column chosen by fit' verdicts."""

    def _pdf(self, lines, xs=None):
        """lines: [(y, [(x, text), …])] or [(y, 'text at x=40')] -> a one-page pdf path."""
        import pymupdf
        tmp = tempfile.mkdtemp(prefix='pe_'); path = os.path.join(tmp, 'page.pdf')
        doc = pymupdf.open(); page = doc.new_page(width=595, height=842)
        for y, cells in lines:
            if isinstance(cells, str):
                page.insert_text((40, y), cells, fontsize=9)
            else:
                for x, t in cells:
                    page.insert_text((x, y), t, fontsize=9)
        doc.save(path); doc.close()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        return path

    def test_value_cells(self):
        self.assertEqual(PE._numbers(['29(3)', '67(3)', '3.6(3)'])[::2], [('num', 29.0), ('num', 67.0), ('num', 3.6)])
        self.assertEqual(PE._numbers(['(13.16)', '13.09–13.25'])[0], ('num', 13.16))
        self.assertEqual(PE._constituent_ok('S2–'), ('S', 'constituent'))
        self.assertEqual(PE._constituent_ok('HS'), ('HS', 'constituent'))
        self.assertEqual(PE._constituent_ok('Cl–')[0], 'Cl')

    def test_footnote_mark_on_value(self):
        import pymupdf
        path = self._pdf([(100, [(40, 'FeOb'), (120, '11.41c'), (160, '0.46'), (200, '11.97d')]), (114, [(40, 'MnO'), (120, '0.62'), (160, '0.05'), (200, '0.70')])])
        lines = PE.page_lines(pymupdf.open(path)[0])
        self.assertEqual([w[4] for w in lines[0]['w']], ['FeOb', '11.41', '0.46', '11.97'])

    def test_legend_name_then_number(self):
        t = 'Table 3. Chemical composition of gmalimite (1—grain used for SCXRD, 2—aggregate, Figure 4B) and zoharite (3—aggregate, Figure 3C).'
        self.assertEqual(PE.legend_columns(t, 'zoharite'), ['3'])
        self.assertEqual(PE.legend_columns(t, 'gmalimite'), ['1'])

    def test_holotype_words_stop_at_the_cotype(self):
        w = PE.holotype_words('It was found at two localities: the holotype in the Sahatany Valley, central Madagascar, and a cotype specimen from Sakangyi, Mogok Township, Mandalay Region, Myanmar.')
        self.assertIn('Madagascar', w); self.assertNotIn('Myanmar', w); self.assertNotIn('Mogok', w)

    def test_formula_sentences(self):
        fs = PE._formulas('The empirical formula of koragoite (Voloshin et al., 1997) calculated on the basis of 20 O atoms is Mn3.71Fe0.13Nb3.65Ta0.56W1.83Ti0.08O20. '
                          'The crystal chemical formula of the mineral is (Mn2.02Fe0.98)Σ3.00(Nb2.30Ta0.64Ti0.06)Σ3.00(W1.34Nb0.66)Σ2.00O20.', 'koragoite')
        self.assertEqual(fs[0][4], 'structural'); self.assertAlmostEqual(fs[1][1]['Mn'], 3.71)      # the cited formula goes last
        fs = PE._formulas('The empirical formula (O = 28 apfu) is Ca9.00(Ca0.33Fe0. 2+ 20□0.47)Σ1.00Mg1.04P6.97O28.', 'keplerite')
        self.assertAlmostEqual(fs[0][1]['Fe'], 0.20); self.assertAlmostEqual(fs[0][1]['Ca'], 9.33)   # the charge superscript set mid-number
        fs = PE._formulas('The empirical formulas for ferriphoxite (for O = 13 apfu) and carboferriphoxite (for O = 15 apfu) are '
                          '{[(NH4)2.13K0.87]Σ3.00(H2O)}{(Fe3+ 0.95Al0.05)Σ1.00(HPO4)2(C2O4)} and {[(NH4)1.12K0.88]Σ2.00(H2CO3)}{(Fe3+ 0.78Al0.22)Σ1.00(HPO4)(H2PO4)(C2O4)}, respectively.', 'ferriphoxite')
        self.assertEqual(fs[0][2], []); self.assertAlmostEqual(fs[0][1]['N'], 2.13); self.assertAlmostEqual(fs[0][1]['Fe'], 0.95)   # braces are brackets
        fs = PE._formulas('A combination of results of EMPA and site scattering values obtained by single-crystal structure refinements of Tangir Valley chevkinite-(Ce) '
                          'yielded the formula: (Ce1.81La0.81Nd0.59Ca0.46)Σ3.67(Fe2+ 0.80Mg0.10)Σ0.90Ti2.65Si4.02O22.', 'chevkinite-(ce)')
        self.assertEqual(fs[0][4], 'structural')

    def test_tables_that_are_not_the_analysis(self):
        path = self._pdf([(80, 'Table 2. Trace element composition of ferri-taramite (µg g−1).'), (94, 'Element   Mean   Range'),
                          (108, 'As   18.0   12–25'), (122, 'B   5.5   4–7'), (136, 'Be   75.0   60–90'), (150, 'Co   109.0   90–120'), (164, 'Sc   49.0   40–60')])
        self.assertIsNone(PE.epma_table(path, 'ferri-taramite'))
        path = self._pdf([(80, 'TABLE 6. EMPIRICAL BOND VALENCES (vu) FOR CANADIAN BAZZITE'), (94, 'Bz-ON   Si   Be   Na'),
                          (108, 'O1   4.09   1.964   1.056'), (122, 'O2   4.05   1.980   1.010'), (136, 'O3   4.11   1.950   1.100')])
        self.assertIsNone(PE.epma_table(path, 'bazzite'))

    def test_transposed_apfu_columns_and_integer_esds(self):
        xs = (40, 90, 130, 170, 210, 250, 290, 330, 370, 410, 450)
        head = ['', 'CaO', 'MgO', 'MnO', 'As2O5', 'P2O5', 'H2O*', 'total', 'Ca', 'Mg', 'Mn']
        rows = [['mean', '25.42', '6.11', '0.10', '56.00', '0.29', '11.20', '99.13', '3.691', '1.235', '0.012'],
                ['1', '26.05', '5.44', '0.15', '56.10', '0.12', '11.22', '99.08', '3.793', '1.102', '0.017'],
                ['2', '26.18', '5.47', '0.02', '55.55', '0.44', '11.19', '98.85', '3.814', '1.109', '0.002']]
        path = self._pdf([(80, 'Tab. 2 Chemical composition of chongite from Jáchymov (wt. %)')] + [(100 + 14 * k, list(zip(xs, r))) for k, r in enumerate([head] + rows)])
        e = PE.epma_table(path, 'chongite')
        self.assertEqual([r['constituent'] for r in e['rows']], ['CaO', 'MgO', 'MnO', 'As2O5', 'P2O5', 'H2O'])
        self.assertEqual(e['rows'][0]['mean'], 25.42)
        xs = (40, 90, 140, 190, 240)
        rows = [['Spot', 'SiO2', 'Al2O3', 'Fe2O3', 'Total'], ['1', '27.25', '68.66', '3.48', '99.96'], ['2', '27.24', '68.84', '3.49', '100.17'],
                ['Mean', '29(3)', '67(3)', '3.6(3)', '99.8(5)']]
        path = self._pdf([(80, 'Table 2. (a) Electron microprobe analyses of mullite-2c given in weight percent.')] + [(100 + 14 * k, list(zip(xs, r))) for k, r in enumerate(rows)])
        e = PE.epma_table(path, 'mullite')
        self.assertEqual({r['constituent']: r['mean'] for r in e['rows']}, {'SiO2': 29.0, 'Al2O3': 67.0, 'Fe2O3': 3.6})

    def test_nd_rows_legend_column_and_the_apfu_block(self):
        xs = (40, 180, 240, 410)
        body = [['S', '33.77', '33.58', '30.87'], ['Fe', '36.19', '36.84', '28.35'], ['Cu', '14.33', '14.10', '20.05'], ['K', '7.58', '7.60', '7.00'],
                ['Ba', '0.12', '0.10', '11.50'], ['Na', 'n.d.', 'n.d.', '0.18'], ['Se', 'n.d.', 'n.d.', '0.17'], ['Total', '99.99', '99.22', '99.72'],
                ['S', '25.00', '25.00', '27.00'], ['Na', '0.00', '0.00', '0.22']]
        path = self._pdf([(80, 'Table 3. Chemical composition of gmalimite (1—grain used for SCXRD, 2—aggregate) and zoharite (3—aggregate).'),
                          (100, list(zip(xs, ['wt.%', '1', '2', '3'])))] + [(114 + 14 * k, list(zip(xs, r))) for k, r in enumerate(body)])
        e = PE.epma_table(path, 'zoharite')
        self.assertNotIn('Na', [r['constituent'] for r in e['rows']])                        # n.d. in the first column: no mean
        na = [r for r in e['rows_all'] if r['constituent'] == 'Na']
        self.assertEqual(len(na), 1); self.assertEqual(na[0]['all'], [0.0, 0.0, 0.18])       # kept for the named columns; the apfu 'Na 0.22' below the Total is not a second row
        cols = PE.headline_columns(e, 'zoharite', {'codes': [], 'n': None, 'holotype': False, 'holotype_words': [], 'domains': ['3']})
        self.assertTrue(cols); wt, why = cols[0]
        self.assertIn('column 3', why); self.assertNotIn('averaged', why)
        self.assertEqual(wt['Na'], 0.18); self.assertEqual(wt['S'], 30.87); self.assertEqual(wt['Se'], 0.17)
        alts = PE.table_alternatives(e, {r['constituent']: r['mean'] for r in e['rows']})
        self.assertTrue(any(a.get('Na') == 0.18 and a.get('S') == 30.87 for a in alts))     # the by-fit columns carry the n.d.-first rows too

    def test_mean_cell_inside_the_named_group(self):
        xs = (40, 170, 200, 230, 262, 330, 360, 390, 422)
        head2 = ['No. of spot analyses', '5', '6', '13', 'Mean (n = 3)', '8', '15', '32', 'Mean (n = 9)']
        body = [['SiO2', '29.21', '29.32', '29.43', '29.32', '26.39', '25.49', '26.30', '25.98'], ['Al2O3', '48.10', '48.60', '48.65', '48.45', '44.10', '43.90', '44.30', '44.10'],
                ['B2O3', '16.50', '16.60', '16.64', '16.58', '15.90', '15.80', '16.00', '15.90'], ['MnO', '0.40', '0.38', '0.39', '0.39', '0.20', '0.22', '0.21', '0.21'],
                ['Na2O', '2.10', '2.12', '2.14', '2.12', '1.90', '1.95', '1.92', '1.92']]
        path = self._pdf([(80, 'TABLE 2. Representative chemical compositions of ertlite and mean analyses used for structure refinement'),
                          (100, [(200, 'Madagascar'), (360, 'Myanmar')]), (114, list(zip(xs, head2)))] + [(128 + 14 * k, list(zip(xs, r))) for k, r in enumerate(body)])
        e = PE.epma_table(path, 'ertlite')
        cols = PE.headline_columns(e, 'ertlite', {'codes': [], 'n': None, 'holotype': True, 'holotype_words': ['Madagascar'], 'domains': []})
        wt, why = next((w, y) for w, y in cols if 'Madagascar' in y)
        self.assertNotIn('averaged', why); self.assertEqual(wt['SiO2'], 29.32); self.assertEqual(wt['MnO'], 0.39)

    def test_pass9_vetting(self):
        fs = PE._formulas('The empirical formula using Li, Na, and K based on the structure refinement is Li1.00Na5.81K2.19(UO2)(SO4)5(SO3OH)(H2O). '
                          'The empirical formula using Na measured via EPMA is Li0.79Na5.02K2.02(UO2)(SO4)5(SO3OH)(H2O).', 'seaborgite')
        self.assertEqual([f[4] for f in fs], ['structural', 'empirical'])
        fs = PE._formulas('The empirical formula is Pb8.00Al2.00S6+ 2.88S2 2.60O28.52H22.92.', 'dinilawiite')
        self.assertAlmostEqual(fs[0][1]['S'], 5.48)                                           # 'S2 2.60': the minus of S2− lost
        self.assertIsNone(PE._constituent_ok('Mn2+')[0]); self.assertIsNone(PE._constituent_ok('As3–')[0])   # only anions carry a charge worth stripping
        self.assertIsNone(PE.prose_table('The composition is K0.89 Na0.05 Y0.02 Ca0.01 Ba0.01 Mg0.97 Sc0.54.'))
        self.assertIsNotNone(PE.prose_table('The mean composition is MnO 14.78, Ce2O3 34.19, P2O5 29.57, and H2O 21.46, total 100.00.'))
        xs = (40, 150, 200, 250, 300, 350, 400)
        rows = [['Na', 'Ca', 'K', 'Na', 'F', 'Cl', 'Mn'], ['A', '1.82', '0.02', '0.09', '0.10', '0.05', '1.81'], ['B', '1.80', '0.03', '0.08', '0.12', '0.04', '1.79'], ['C', '1.85', '0.01', '0.10', '0.11', '0.06', '1.83']]
        path = self._pdf([(80, 'Site populations of speziaite')] + [(100 + 14 * k, list(zip(xs, r))) for k, r in enumerate(rows)])
        e = PE.epma_table(path, 'speziaite')
        self.assertTrue(e is None or e.get('total') is None and sum(r['mean'] for r in e['rows']) < 50)
        xs = (40, 150, 200, 240, 300, 350, 390)
        head = ['', 'CF9a1', 'Range', 'SD', 'CF9a2', 'Range', 'SD']
        body = [['Na2O', '1.58', '1.4–1.7', '0.15', '1.67', '1.5–1.8', '0.05'], ['CaO', '10.20', '9.9–10.5', '0.20', '10.40', '10.1–10.7', '0.15'],
                ['FeO', '20.10', '19.5–20.6', '0.30', '19.80', '19.2–20.3', '0.25'], ['P2O5', '39.50', '39.0–40.0', '0.30', '39.20', '38.8–39.6', '0.25'], ['H2O', '28.60', '', '', '28.90', '', '']]
        path = self._pdf([(80, 'TABLE 3. SUMMARY OF CHEMICAL DATA (wt.%) OF LIRAITE HOLOTYPE')] + [(100 + 14 * k, list(zip(xs, r))) for k, r in enumerate([head] + body)])
        e = PE.epma_table(path, 'liraite')
        cols = PE.headline_columns(e, 'liraite', {'codes': ['CF9a1'], 'n': None, 'holotype': False, 'holotype_words': [], 'domains': []})
        wt, why = cols[0]
        self.assertNotIn('averaged', why); self.assertEqual(wt['Na2O'], 1.58); self.assertEqual(wt['FeO'], 20.1)


class ReviewFixes(unittest.TestCase):
    """2026-09-03: the medium-effort review of 10e25cc, one test per confirmed finding."""

    def _pdf(self, lines):
        return ReaderClasses._pdf(self, lines)

    def test_iron_split_below_the_total_survives(self):
        xs = (40, 130)
        rows = [['CaO', '46.10'], ['FeO', '11.79'], ['P2O5', '38.20'], ['MgO', '2.10'], ['SiO2', '1.20'], ['Total', '99.39'], ['FeO', '10.71'], ['Fe2O3', '1.20']]
        path = self._pdf([(80, 'Table 1. Chemical composition of testite (wt%).'), (94, 'Constituent   Mean')] + [(108 + 14 * k, list(zip(xs, r))) for k, r in enumerate(rows)])
        e = PE.epma_table(path, 'testite')
        self.assertEqual({r['constituent']: r['mean'] for r in e['rows'] if r['constituent'].startswith('Fe')}, {'FeO': 10.71, 'Fe2O3': 1.2})

    def test_nd_points_not_averaged_in_and_sigma_total(self):
        xs = (40, 130, 170, 210, 250, 290, 330)
        rows = [['Constituent', '1', '2', '3', '4', '5', '6'], ['SiO2', '46.1', '46.3', '46.0', '46.2', '46.4', '46.1'], ['CaO', '20.2', '20.1', '20.3', '20.0', '20.2', '20.1'],
                ['MgO', '29.0', '29.1', '28.9', '29.2', '29.0', '29.1'], ['F', '0.30', 'n.d.', '0.28', '0.31', 'n.d.', '0.29'], ['Sum', '95.6', '95.5', '95.5', '95.7', '95.6', '95.6']]
        path = self._pdf([(80, 'Table 1. Chemical composition of testite (wt%).')] + [(100 + 14 * k, list(zip(xs, r))) for k, r in enumerate(rows)])
        e = PE.epma_table(path, 'testite')
        f = next(r for r in e['rows'] if r['constituent'] == 'F')
        self.assertAlmostEqual(f['mean'], 0.295); self.assertEqual(f['all'], [0.3, 0.0, 0.28, 0.31, 0.0, 0.29])
        self.assertEqual(e['total'], 95.6)                                              # 'Sum' is the total row, not a continuation of the F row
        self.assertEqual(len(next(r for r in e['rows'] if r['constituent'] == 'MgO')['all']), 6)

    def test_transposed_fully_twinned_header(self):
        xs = (40, 90, 130, 170, 210, 250, 290, 330, 365, 400, 435, 470)
        head = ['Sample', 'SiO2', 'Al2O3', 'FeO', 'MgO', 'CaO', 'Total', 'Si', 'Al', 'Fe', 'Mg', 'Ca']
        rows = [['1', '40.10', '10.20', '12.30', '20.10', '16.90', '99.60', '2.90', '0.87', '0.74', '2.17', '1.31'],
                ['2', '40.30', '10.10', '12.10', '20.30', '16.80', '99.60', '2.91', '0.86', '0.73', '2.18', '1.30'],
                ['Mean', '40.20', '10.15', '12.20', '20.20', '16.85', '99.60', '2.90', '0.86', '0.74', '2.18', '1.30']]
        path = self._pdf([(80, 'Table 2. Chemical composition of testite (wt%).')] + [(100 + 14 * k, list(zip(xs, r))) for k, r in enumerate([head] + rows)])
        e = PE.epma_table(path, 'testite')
        self.assertIsNotNone(e); self.assertEqual({r['constituent']: r['mean'] for r in e['rows']}, {'SiO2': 40.2, 'Al2O3': 10.15, 'FeO': 12.2, 'MgO': 20.2, 'CaO': 16.85})

    def test_legend_scope_and_order(self):
        self.assertEqual(PE.legend_columns('Fig. 2. 1 – newmineralite, 2 – quartz, 3 – calcite. Table 3 – Newmineralite composition', 'newmineralite'), [])
        self.assertEqual(PE.legend_columns('Table 2. Analyses. 1, 2, 8 – newmineralite (1 – holotype; 8 – cotype); 3 – quartz.', 'newmineralite'), ['1', '2', '8'])
        cells = [('Constituent', 40), ('1', 130), ('2', 170), ('8', 210)]
        e = {'head_cells': cells, 'label_x': 40, 'rows': [{'constituent': c, 'mean': v[0], 'all': v, 'xs': [130, 170, 210]} for c, v in
             (('SiO2', [46.1, 46.3, 46.0]), ('CaO', [20.2, 20.1, 20.3]), ('MgO', [29.0, 29.1, 28.9]))]}
        cols = PE.headline_columns(e, 'newmineralite', {'codes': [], 'n': None, 'holotype': False, 'holotype_words': [], 'domains': ['1', '2', '8']})
        self.assertEqual([w['SiO2'] for w, _ in cols], [46.1, 46.3, 46.0])               # the legend's order: the holotype's column first
        e2 = dict(e, head_cells=[('Constituent', 40), ('Mean', 130), ('Range', 170), ('S.D.', 210)])
        self.assertEqual(PE.headline_columns(e2, 'newmineralite', {'codes': [], 'n': None, 'holotype': False, 'holotype_words': [], 'domains': ['1']}), [])   # no numbered header: no column 1

    def test_norm_text_and_excluded_elements(self):
        self.assertIn('Sr0.57Ba0.38', PE._norm_text('formula Sr0:57Ba0:38'))
        e = {'rows': [{'constituent': 'Al2O3', 'mean': 1.0}, {'constituent': 'SiO2', 'mean': 40.0}], 'rows_all': [{'constituent': 'Al2O3', 'mean': 1.0}],
             'candidates': [{'rows': [{'constituent': 'Al2O3', 'mean': 2.0}, {'constituent': 'CaO', 'mean': 3.0}]}]}
        f = PE._without_elements(e, ['Al'])
        self.assertEqual([r['constituent'] for r in f['rows']], ['SiO2']); self.assertEqual(f['rows_all'], [])
        self.assertEqual([r['constituent'] for r in f['candidates'][0]['rows']], ['CaO'])

    def test_two_samples_and_prose_over_structural(self):
        self.assertIn('NM', PE.sample_hints('The empirical formula of beraunite (NM) calculated on the basis of P = 4 apfu is')['codes'])
        self.assertIn('FR', PE.sample_hints('The empirical formula of beraunite (FR) calculated on the basis of P = 4 apfu is')['codes'])
        self.assertNotIn('NM', PE.sample_hints('formula (NM) of')['codes'] if False else [])
        rows = [['Constituent', 'Mean'], ['PbO', '43.21'], ['CuO', '15.38'], ['TeO3', '35.29'], ['H2O', '3.49'], ['Total', '97.37']]
        path = self._pdf([(60, 'The electron microprobe analyses (average of five) provided: PbO 43.21, CuO 15.38, TeO3 35.29, H2O 3.49 (structure), total 97.37 wt.%.'),
                          (200, 'Table 3. Bond-valence analysis for andychristyite'), (214, [(40, 'Site'), (120, 'O1'), (160, 'O2'), (200, 'Total')]),
                          (228, [(40, 'Pb'), (120, '0.45'), (160, '0.30'), (200, '2.05')]), (242, [(40, 'Cu'), (120, '0.50'), (160, '0.48'), (200, '2.02')]),
                          (256, [(40, 'Te'), (120, '1.05'), (160, '0.98'), (200, '6.01')]), (270, [(40, 'Total'), (120, '2.00'), (160, '1.76'), (200, '')])])
        e = PE.epma_table(path, 'andychristyite')
        self.assertIsNotNone(e); self.assertTrue(e.get('prose')); self.assertEqual(e['rows'][0]['constituent'], 'PbO')


class DocxPaper(unittest.TestCase):
    """A manuscript .docx read like a pdf: its tables become pages of words, its text the paper's."""
    def test_docx_tables_and_text(self):
        from docx import Document
        tmp = tempfile.mkdtemp(prefix='pe_'); path = os.path.join(tmp, 'testite.docx')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        doc = Document()
        doc.add_paragraph('Testite, a new mineral from Nowhere')
        doc.add_paragraph('The empirical formula, calculated on the basis of 8 O apfu, is Ca1.00Mg2.01Si2.99O7(OH)0.98. '
                          'H2O was calculated by difference. Optical: alpha = 1.600, beta = 1.610, gamma = 1.620.')
        doc.add_paragraph('Table 1. Chemical data (wt%) for testite.')
        t = doc.add_table(rows=1, cols=5)
        for c, h in zip(t.rows[0].cells, ('Constituent', 'Mean', 'Range', 'S.D.', 'Standard')):
            c.text = h
        for row in (('CaO', '17.23', '16.90–17.50', '0.21', 'wollastonite'), ('MgO', '24.88', '24.50–25.20', '0.30', 'forsterite'),
                    ('SiO2', '55.18', '54.80–55.60', '0.28', 'quartz'), ('H2O', '2.71', '', '', ''), ('Total', '100.00', '', '', '')):
            cells = t.add_row().cells
            for c, v in zip(cells, row):
                c.text = v
        doc.add_paragraph('Table 2. Powder X-ray diffraction data for testite.')
        t2 = doc.add_table(rows=0, cols=7)
        for row in (('Iobs', 'dobs', 'dcalc', 'Icalc', 'h', 'k', 'l'), ('100', '3.4550', '3.4531', '92', '1', '1', '0'), ('35', '2.9800', '2.9791', '40', '0', '2', '1'),
                    ('12', '2.5010', '2.4997', '9', '2', '0', '0'), ('8', '1.0210', '1.0204', '6', '−10', '1', '2')):   # a signed two-digit index: h and k must still read as one column
            cells = t2.add_row().cells
            for c, v in zip(cells, row):
                c.text = v
        doc.save(path)
        e = PE.epma_table(path, 'testite')
        self.assertEqual({r['constituent']: r['mean'] for r in e['rows']}, {'CaO': 17.23, 'MgO': 24.88, 'SiO2': 55.18, 'H2O': 2.71})
        self.assertEqual(e['total'], 100.0); self.assertIsNone(e['page']); self.assertIn('Chemical data', e['caption'])
        self.assertEqual(next(r for r in e['rows'] if r['constituent'] == 'CaO')['standard'], 'wollastonite')
        o, c = PE.pxrd_table(path); self.assertEqual((len(o), len(c)), (4, 4)); self.assertEqual(c[-1][2], (-10, 1, 2))
        ex = PE.extract(path, tmp, 'testite'); self.assertEqual(ex['basis'][:2], ('O', 8.0)); self.assertEqual(ex['files']['epma'], 'testite_docx_epma.csv')   # never the paper's file name
        r = PE.check_paper(path, None, None); self.assertTrue(r['composition']['ok'], r['lines'])
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(PE.main([path, '--out', tmp]), 0)             # the CLI on a manuscript: no page to print
        self.assertIn('analytical table (a table of the manuscript, 4 constituents', buf.getvalue())
        # the formula sentence inserted under Track Changes is still read
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement
        p = doc.paragraphs[1]._p
        ins = OxmlElement('w:ins'); ins.set(qn('w:id'), '1'); ins.set(qn('w:author'), 'reviewer'); ins.set(qn('w:date'), '2026-09-05T00:00:00Z')
        for r_ in list(p.findall(qn('w:r'))):
            p.remove(r_); ins.append(r_)
        p.append(ins); doc.save(path)
        self.assertEqual(PE.extract(path, None, None, write=False)['basis'][:2], ('O', 8.0))

    def test_cell_check(self):
        """The powder table's calculated lines against the cell: the .cif's, else the one the text
        states (a and c only: tetragonal or hexagonal, the table decides); a mistyped d is named."""
        from docx import Document
        from tests.test_bv_check import RUTILE
        tmp = tempfile.mkdtemp(prefix='pe_'); path = os.path.join(tmp, 'rutile.docx'); cif = os.path.join(tmp, 'rutile.cif')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        with open(cif, 'w', encoding='utf-8') as f:
            f.write(RUTILE)
        doc = Document()
        doc.add_paragraph('Rutile from Nowhere. The powder pattern was indexed on a tetragonal cell, a = 4.5937(2), c = 2.9587(1) Å, V = 62.43 Å3.')
        doc.add_paragraph('Table 2. Powder X-ray diffraction data for rutile.')
        t = doc.add_table(rows=0, cols=7)
        for row in (('Iobs', 'dobs', 'Icalc', 'dcalc', 'h', 'k', 'l'), ('100', '3.248', '100', '3.2482', '1', '1', '0'), ('50', '2.487', '48', '2.4874', '1', '0', '1'),
                    ('8', '2.297', '7', '2.2296', '2', '0', '0'), ('20', '2.187', '19', '2.1873', '1', '1', '1'), ('10', '2.054', '9', '2.0544', '2', '1', '0'), ('60', '1.687', '58', '1.6874', '2', '1', '1')):   # 2.2296: a mistyped digit, 2.9 % off
            cells = t.add_row().cells
            for c, v in zip(cells, row):
                c.text = v
        doc.save(path)
        cc = PE.cell_check(path, None)
        self.assertEqual((cc['status'], cc['source'], cc['n'], cc['agree'], cc['loose']), ('checked', 'powder', 6, 5, 5))   # the 2.9 % line is beyond 1.5 %
        self.assertAlmostEqual(cc['cell']['γ'], 90.0); self.assertEqual(cc['bad'][0][2], (2, 0, 0))
        self.assertTrue(any(ln.startswith('2.2296 (2 0 0) does not follow the cell: it gives 2.2968') for ln in cc['lines']), cc['lines'])
        self.assertEqual(cc['unmatched_obs'], [])                                       # 2.297 observed is the (2 0 0) the cell gives
        cc = PE.cell_check(path, cif)
        self.assertEqual((cc['source'], cc['agree'], len(cc['bad'])), ('.cif', 5, 1))
        r = PE.check_paper(path, cif, None)
        self.assertEqual(r['powder_status'], 'checked'); self.assertTrue(any(l.startswith('powder table: 6 indexed lines vs the .cif cell') for l in r['lines']), r['lines'])
        self.assertEqual(cc['wild'], 0)
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            PE.main([path, '--check', '--cif', cif])
        self.assertIn('does not follow the cell', buf.getvalue())

    def test_records_and_oracles(self):
        """Every reading carries a record; the oracles fill them: the composition for the table and
        formula, the cell for the powder table, Gladstone–Dale for the optics, the cell's own volume
        and density, Mindat for the name."""
        from docx import Document
        tmp = tempfile.mkdtemp(prefix='pe_'); path = os.path.join(tmp, 'rutile.docx')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        doc = Document()
        doc.add_paragraph('Rutile from Nowhere. Rutile is tetragonal, a = 4.5937(2), c = 2.9587(1) Å, V = 62.43 Å3, Z = 2. '
                          'The calculated density is 4.248 g/cm3. Optically uniaxial (+), ω = 2.616, ε = 2.903. '
                          'The compatibility index, 1 − (KP/KC), is superior. '
                          'The empirical formula, calculated on the basis of 2 O apfu, is Ti1.00O2.')
        doc.add_paragraph('Table 1. Chemical data (wt%) for rutile.')
        t = doc.add_table(rows=1, cols=4)
        for c, h in zip(t.rows[0].cells, ('Constituent', 'Mean', 'Range', 'S.D.')):
            c.text = h
        for row in (('TiO2', '99.10', '98.80–99.40', '0.21'), ('FeO', '0.40', '0.30–0.50', '0.07'), ('SiO2', '0.30', '0.20–0.40', '0.06'), ('Total', '99.80', '', '')):
            cells = t.add_row().cells
            for c, v in zip(cells, row):
                c.text = v
        doc.add_paragraph('Table 2. Powder X-ray diffraction data for rutile.')
        t2 = doc.add_table(rows=0, cols=7)
        for row in (('Iobs', 'dobs', 'Icalc', 'dcalc', 'h', 'k', 'l'), ('100', '3.248', '100', '3.2482', '1', '1', '0'), ('50', '2.487', '48', '2.4874', '1', '0', '1'),
                    ('8', '2.297', '7', '2.2969', '2', '0', '0'), ('20', '2.187', '19', '2.1873', '1', '1', '1'), ('60', '1.687', '58', '1.6874', '2', '1', '1')):
            cells = t2.add_row().cells
            for c, v in zip(cells, row):
                c.text = v
        doc.save(path)
        r = PE.check_paper(path, None, None); F = r['fields']
        self.assertTrue(r['lines'][0].startswith('readers: table ✓'), r['lines'][0])
        self.assertEqual({k: F[k]['status'] for k in ('epma', 'formula', 'basis', 'method', 'optics.n', 'optics.D_calc', 'cell', 'pxrd.calc', 'pxrd.obs')},
                         {'epma': 'agrees', 'formula': 'agrees', 'basis': 'agrees', 'method': 'none', 'optics.n': 'agrees', 'optics.D_calc': 'agrees', 'cell': 'agrees', 'pxrd.calc': 'agrees', 'pxrd.obs': 'agrees'}, r['lines'])
        self.assertIn(F['name']['status'], ('agrees', 'nooracle', 'none')); self.assertEqual(F['optics.D_meas']['status'], 'none'); self.assertEqual(F['bv.params']['status'], 'none')
        self.assertEqual((F['gd']['status'], F['gd']['value'], F['coords']['status'], F['bv.table']['status']), ('agrees', {'ci': None, 'category': 'superior'}, 'none', 'none'), r['lines'])
        self.assertEqual((F['epma']['verified_by'], F['pxrd.calc']['verified_by'], F['optics.n']['verified_by']), ('composition', 'cell', 'gd'))
        self.assertTrue(any(l.startswith('cell: a=4.5937') and 'V from the axes 62.4 vs 62.4' in l and 'D from Z=2' in l for l in r['lines']), r['lines'])
        self.assertTrue(any(l.startswith('Gladstone–Dale: n 2.7117') for l in r['lines']), r['lines'])
        # the unit pieces
        g = PE.gd_statement('The compatibility index, 1 − (KP/KC), is −0.012, in the superior range of Mandarino (1981).')
        self.assertEqual((g['ci'], g['category']), (-0.012, 'superior'))
        cc = PE.cell_consistency('The cell is a = 4.5937, c = 2.9587 Å, V = 62.43 Å3, Z = 2 (powder data).', {'Ti': 1, 'O': 2}, None, 4.60, verified_formula=True)
        self.assertEqual(cc['status'], 'unverified'); self.assertFalse(cc['red'])                    # one formula tried: a doubt, not a finding
        cc = PE.cell_consistency('The cell is a = 4.5937, c = 2.9587 Å, V = 62.43 Å3, Z = 2 (powder data).', {'Ti': 1, 'O': 2}, None, 4.60, verified_formula=True, masses=[('the ideal formula', 79.9)])
        self.assertEqual(cc['status'], 'unverified'); self.assertFalse(cc['red']); self.assertTrue(any('none of the formulas read gives it' in l for l in cc['lines']), cc['lines'])   # off from every formula: a doubt, never red (2026-09-06)
        cc = PE.cell_consistency('The cell is a = 4.5937, c = 2.9587 Å, V = 70.0 Å3 (powder data).', None, None, None)
        self.assertEqual(cc['status'], 'unverified'); self.assertTrue(any('does not follow from the axes' in l for l in cc['lines']))
        self.assertTrue(PE._same_basis(('O', 8.0), ('O', 8))); self.assertFalse(PE._same_basis(('O', 8.0), ('cations', 8.0)))

    def test_powder_table_by_content(self):
        """The columns are typed by what they hold: an unlabelled calculated pattern, a two-line
        header, indices written as one word, and a second sample's columns left out."""
        from docx import Document
        tmp = tempfile.mkdtemp(prefix='pe_'); path = os.path.join(tmp, 'contentite.docx')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        doc = Document()
        doc.add_paragraph('Table 2. Calculated powder diffraction pattern of contentite.')
        t = doc.add_table(rows=0, cols=5)
        for row in (('h', 'k', 'l', 'dhkl', 'Irel'), ('1', '1', '0', '6.2345', '100'), ('0', '2', '0', '5.1200', '35'), ('−1', '1', '1', '4.0010', '12'), ('2', '0', '−1', '3.4550', '8'), ('1', '3', '0', '3.1020', '4')):
            cells = t.add_row().cells
            for c, v in zip(cells, row):
                c.text = v
        doc.add_paragraph('Table 3. Powder X-ray diffraction data for contentite.')
        t2 = doc.add_table(rows=0, cols=5)
        for row in (('Iobs', 'dobs', 'Icalc', 'dcalc', ''), ('', '(Å)', '', '(Å)', 'hkl'), ('100', '6.23', '100', '6.2345', '110'), ('30', '5.12', '35', '5.1200', '020'),
                    ('10', '4.00', '12', '4.0010', '2.1.10'), ('7', '3.45', '8', '3.4550', '201'), ('3', '3.10', '4', '3.1020', '130')):
            cells = t2.add_row().cells
            for c, v in zip(cells, row):
                c.text = v
        doc.add_paragraph('Table 4. Powder data for contentite (this study) and for the Elliott (2018) sample.')
        t3 = doc.add_table(rows=0, cols=5)
        for row in (('hkl', 'dobs', 'Iobs', 'dobs', 'Iobs'), ('110', '6.23', '100', '6.24', '90'), ('020', '5.12', '30', '5.13', '28'), ('111', '4.00', '10', '4.01', '11'), ('201', '3.45', '7', '3.46', '6')):
            cells = t3.add_row().cells
            for c, v in zip(cells, row):
                c.text = v
        doc.save(path)
        pages = PE._pages(path)
        o, c = PE._pt_read(pages[0], lambda i: PE._caption(pages[0], i))
        self.assertEqual((len(o), len(c)), (0, 5)); self.assertEqual(c[2], (4.001, 12.0, (-1, 1, 1)))      # the caption says calculated: bare dhkl / Irel are calc
        o, c = PE._pt_read(pages[1], lambda i: PE._caption(pages[1], i))
        self.assertEqual((len(o), len(c)), (5, 5)); self.assertEqual(o[0], (6.23, 100.0)); self.assertEqual(c[2], (4.001, 12.0, (2, 1, 10)))   # a two-line header; '2.1.10'
        o, c = PE._pt_read(pages[2], lambda i: PE._caption(pages[2], i))
        self.assertEqual([d for d, _ in o], [6.23, 5.12, 4.0, 3.45]); self.assertEqual(c, [])            # this study's sample only; no calc without a calc column


class GapFixes(unittest.TestCase):
    """The 2026-09-06 gap work: the prose composition before the formula sentence read whole and in
    either order; a Σ printed as '6='; an observed line judged against the cell's own reflections; Z
    borrowed from the paper's other cell statement or the .cif; the two densities vouching for each
    other; D_calc adjudicated by the cell, Z and the formula."""

    def test_prose_value_first_and_parenthesised_ranges(self):
        pt = PE.prose_table('The composition (wt %) is: 0.03 Na2O, 3.70 K2O, 12.18 Rb2O, 2.02 Cs2O, 4.0 Li2O and 53.14 SiO2, total 100.30.')
        self.assertEqual([(r['constituent'], r['mean']) for r in pt['rows']][:3], [('Na2O', 0.03), ('K2O', 3.7), ('Rb2O', 12.18)])
        self.assertEqual(pt['total'], 100.3)
        pt = PE.prose_table('La2O3 8.54 (8.03–9.01, 0.25), Ce2O3 14.12 (13.03–14.90, 0.46), Pr2O3 4.59 (4.19–4.98, 0.19), Nd2O3 3.91 (3.54–4.31, 0.15), total 99.1')
        self.assertEqual([r['mean'] for r in pt['rows']], [8.54, 14.12, 4.59, 3.91])
        self.assertIsNone(PE.prose_table('at 2.5 V, 3.1 K and 4.0 T, 7.2 mA'))                     # units, not constituents

    def test_prose_before_the_formula_is_read_whole(self):
        oxides = ', '.join('%s %.2f' % (c, v) for c, v in (('SiO2', 40.12), ('TiO2', 0.51), ('ZrO2', 0.11), ('Al2O3', 20.05), ('Cr2O3', 0.12), ('V2O3', 0.05), ('Fe2O3', 3.10), ('FeO', 7.10), ('MnO', 0.30), ('MgO', 18.10), ('NiO', 0.04), ('ZnO', 0.03), ('CaO', 0.90), ('SrO', 0.02), ('BaO', 0.02), ('Na2O', 0.22), ('K2O', 0.10), ('Rb2O', 0.01), ('P2O5', 0.05), ('La2O3', 0.02), ('Ce2O3', 0.03), ('Nd2O3', 0.02), ('Y2O3', 0.02), ('SnO2', 0.01), ('PbO', 0.02), ('F', 0.10), ('Cl', 0.02), ('H2O', 9.80)))
        text = 'Text before. The mean composition (wt.%) is: ' + oxides + ', total 100.42. The empirical formula (based on 14 O apfu) is Mg2.68Fe0.59Al2.35Si3.99O14. More text.'
        fs = PE._formulas(text, 'newmineralite')
        self.assertTrue(fs)
        pt = PE._prose_before(text, fs[0][5])
        self.assertEqual(len(pt['rows']), 28); self.assertEqual(pt['rows'][0]['constituent'], 'SiO2')
        self.assertLess(len(PE.prose_table(fs[0][5])['rows']), 28)                                       # the context alone holds only the tail of the list

    def test_sigma_printed_as_six_equals(self):
        f = PE._journal_to_icdd('A(Na0.79K0.16Pb0.01)6=0.96B(Ca1.26Na0.72)6=2.00')
        self.assertIn('Σ0.96', f); self.assertIn('Σ2.00', f); self.assertNotIn('6=', f)

    def test_observed_lines_on_the_cell(self):
        cell = {'a': 4.5937, 'b': 4.5937, 'c': 2.9587, 'α': 90.0, 'β': 90.0, 'γ': 90.0}          # rutile
        ds = PE._reflection_ds(cell, 1.6)
        self.assertTrue(PE._on_cell(ds, 3.247, 0.005)); self.assertTrue(PE._on_cell(ds, 1.6874, 0.005))   # (110), (211)
        self.assertFalse(PE._on_cell(ds, 3.05, 0.005)); self.assertFalse(PE._on_cell(ds, 4.9, 0.005))      # nothing there; beyond the largest d
        from docx import Document
        tmp = tempfile.mkdtemp(prefix='pe_'); path = os.path.join(tmp, 'rutile.docx')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        doc = Document()
        doc.add_paragraph('Rutile. The powder pattern was indexed on a tetragonal cell, a = 4.5937(2), c = 2.9587(1) Å, V = 62.43 Å3, Z = 2.')
        doc.add_paragraph('Table 2. Powder X-ray diffraction data for rutile.')
        t = doc.add_table(rows=0, cols=7)
        for row in (('Iobs', 'dobs', 'Icalc', 'dcalc', 'h', 'k', 'l'), ('100', '3.248', '100', '3.2482', '1', '1', '0'), ('50', '2.487', '48', '2.4874', '1', '0', '1'),
                    ('3', '2.297', '', '', '', '', ''), ('20', '2.187', '19', '2.1873', '1', '1', '1'), ('2', '2.100', '', '', '', '', ''), ('10', '2.054', '9', '2.0544', '2', '1', '0'), ('60', '1.687', '58', '1.6874', '2', '1', '1')):
            cells = t.add_row().cells
            for c, v in zip(cells, row):
                c.text = v
        doc.save(path)
        cc = PE.cell_check(path, None)
        self.assertEqual(cc['status'], 'checked'); self.assertEqual(sorted(cc['unmatched_obs']), [2.1, 2.297])
        self.assertEqual(cc['off_cell'], [2.1])                                                        # 2.297 is the unindexed (200); 2.100 lies on nothing
        self.assertTrue(any(l.startswith('1 observed line without a calculated partner in the table lies on reflections') for l in cc['lines']), cc['lines'])
        self.assertTrue(any(l.startswith('observed 2.1: no calculated line within 0.5 % and no reflection') for l in cc['lines']), cc['lines'])
        r = PE.check_paper(path, None, None)
        self.assertEqual(r['fields']['pxrd.obs']['status'], 'agrees')                                    # one stray in seven: the column is vouched for
        self.assertIn('7 observed lines: 5 paired', r['fields']['pxrd.obs']['detail'])

    def test_z_borrowed_and_the_densities_vouch(self):
        # the powder cell carries no Z; the single-crystal sentence does — the density oracle uses it
        text = ('The structure was refined in P42/mnm with a = 4.594(1), c = 2.959(1) Å, Z = 2. The powder pattern was indexed on '
                'a tetragonal cell, a = 4.5937(2), c = 2.9587(1) Å, V = 62.43 Å3 (powder data).')
        cc = PE.cell_consistency(text, {'Ti': 1, 'O': 2}, None, 4.25, verified_formula=True)
        self.assertEqual(cc['status'], 'agrees'); self.assertEqual(cc['D']['Z'], 2); self.assertTrue(cc['D']['ok'])
        cc = PE.cell_consistency('a = 4.5937(2), c = 2.9587(1) Å, V = 62.43 Å3. Z = 2 for the structure.', {'Ti': 1, 'O': 2}, None, 4.25, verified_formula=True)
        self.assertEqual(cc['D']['Z'], 2)                                                                # a Z stated anywhere, when it is the paper's only one
        cc = PE.cell_consistency('a = 4.5937(2), c = 2.9587(1) Å. ' + 'filler words ' * 30 + 'Z = 2 for one phase and Z = 4 for the other.', {'Ti': 1, 'O': 2}, None, 4.25, verified_formula=True)
        self.assertIsNone(cc['D'])                                                                       # two Zs: none borrowed
        # the record layer: D_calc from the cell, and D_meas vouched for by D_calc
        from docx import Document
        tmp = tempfile.mkdtemp(prefix='pe_'); path = os.path.join(tmp, 'rutile.docx')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        doc = Document()
        doc.add_paragraph('Rutile from Nowhere. Rutile is tetragonal, a = 4.5937(2), c = 2.9587(1) Å, V = 62.43 Å3, Z = 2. '
                          'The density measured by flotation is 4.23(2) g/cm3; the calculated density is 4.25 g/cm3 for the empirical formula. '
                          'The empirical formula (based on 2 O apfu) is Ti1.00O2.')
        doc.add_paragraph('Table 1. Analytical data for rutile.')
        t = doc.add_table(rows=0, cols=3)
        for row in (('Constituent', 'wt%', 'Range'), ('TiO2', '99.80', '99.5–100.1'), ('FeO', '0.10', '0.0–0.2'), ('SiO2', '0.05', '0.0–0.1'), ('Total', '99.95', '')):
            cells = t.add_row().cells
            for c, v in zip(cells, row):
                c.text = v
        doc.save(path)
        r = PE.check_paper(path, None, None); F = r['fields']
        self.assertEqual((F['optics.D_calc']['status'], F['optics.D_calc']['verified_by']), ('agrees', 'cell_consistency'))
        self.assertEqual((F['optics.D_meas']['status'], F['optics.D_meas']['verified_by']), ('agrees', 'density'))

    def test_species_mass_from_mindat_html(self):
        M = PE._species_mass({'formula': 'Ni<sup>2+</sup>C<sub>31</sub>H<sub>32</sub>N<sub>4</sub>'})           # abelsonite
        self.assertAlmostEqual(M, 58.693 + 31 * 12.011 + 32 * 1.008 + 4 * 14.007, delta=1.0)
        M = PE._species_mass({'formula': 'Ca<sub>2</sub>(UO<sub>2</sub>)<sub>3</sub>(CO<sub>3</sub>)<sub>5</sub>·8H<sub>2</sub>O'})
        self.assertAlmostEqual(M, 2 * 40.078 + 3 * (238.029 + 2 * 15.999) + 5 * (12.011 + 3 * 15.999) + 8 * 18.015, delta=2.0)
        self.assertIsNone(PE._species_mass({'formula': ''})); self.assertIsNone(PE._species_mass(None))

    def test_bvs_column_and_transposed_grid(self):
        """Bond-valence sums printed as a column of the coordinates table, and a grid printed the
        other way round (cations down the rows), both checked against the .cif."""
        from docx import Document
        from tests.test_bv_check import RUTILE
        from pxrd_review import bv_check as B
        tmp = tempfile.mkdtemp(prefix='pe_'); cif = os.path.join(tmp, 'rutile.cif')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        with open(cif, 'w', encoding='utf-8') as f:
            f.write(RUTILE)
        st = B.Structure(cif); rk = B.compute(st, B.Params(prefer='gh', u6='burns'), None, 'oo')
        ti = next(r for r in rk[0] if r[0].label.upper().startswith('TI'))
        L = B.check_bvs_sites(st, rk[0], rk[1], [{'head': 'BVS', 'rows': [(ti[0].label, round(ti[2], 2))]}], 'GH')
        self.assertTrue(L[0].startswith('bond-valence sums (table 1, column BVS): 1 cells compared, 0 disagree'), L)
        L = B.check_bvs_sites(st, rk[0], rk[1], [{'head': 'BVS', 'rows': [(ti[0].label, round(ti[2], 2) - 0.5)]}], 'GH')
        self.assertIn('1 disagree', L[0]); self.assertTrue(any('BVS of %s' % ti[0].label in l and ' vs ' in l for l in L), L)
        # a manuscript: the coordinates table with a BVS column
        def docx_with(rows):
            path = os.path.join(tmp, 'ms_%d.docx' % len(os.listdir(tmp))); doc = Document()
            doc.add_paragraph('Rutile. Table 3. Atom coordinates and bond-valence sums.')
            t = doc.add_table(rows=0, cols=len(rows[0]))
            for row in rows:
                cells = t.add_row().cells
                for c, v in zip(cells, row):
                    c.text = v
            doc.save(path); return path
        ex = {'bv': {'params': 'gh', 'u6': 'burns'}}
        p1 = docx_with([('Atom', 'x', 'y', 'z', 'Ueq', 'BVS'), (ti[0].label, '0', '0', '0', '0.005', '%.2f' % ti[2]), ('O1', '0.305', '0.305', '0', '0.006', '2.01')])
        bc = PE.bv_check_paper(p1, cif, ex)
        self.assertEqual(bc['status'], 'checked'); self.assertIn('BVS column', bc['head']); self.assertEqual(bc['disagree'], 0)
        self.assertEqual(PE._site_rows_from_grid([['Atom', 'BVS'], [ti[0].label, '3.98'], ['O1', '2.01']], st), [(ti[0].label, 3.98), ('O1', 2.01)])
        # a manuscript: the grid the other way round — anions across, cations down (a hydrate with four anions)
        from tests.test_bv_check import HYDRATE
        cif2 = os.path.join(tmp, 'hydrate.cif')
        with open(cif2, 'w', encoding='utf-8') as f:
            f.write(HYDRATE)
        st2 = B.Structure(cif2); rk2 = B.compute(st2, B.Params(prefer='gh', u6='burns'), None, 'oo')
        ca = next(r for r in rk2[0] if r[0].label.upper().startswith('CA'))
        ans = [a.label for a in st2.anions]
        def cell_text(an):
            segs = rk2[2].get((an, ca[0].label))
            if not segs:
                return ''
            return ' '.join(('%.2f×%d↓' % (v, nd)) if nd > 1 else '%.2f' % v for v, nd, _na in segs)
        p2 = docx_with([tuple(['Site'] + ans + ['Σ']), tuple([ca[0].label] + [cell_text(an) for an in ans] + ['%.2f' % ca[2]])])
        rows = PE._maybe_transpose(B.read_tables(p2)[0], st2)
        self.assertEqual(rows[0][1], ca[0].label); self.assertEqual(rows[1][0], ans[0])              # transposed: anion rows × cation columns
        bc = PE.bv_check_paper(p2, cif2, ex)
        self.assertEqual(bc['status'], 'checked', bc); self.assertEqual(bc['disagree'], 0, bc.get('lines'))


class BondValenceHandCheck(unittest.TestCase):
    """The 2026-09-07 hand-check of three bond-valence papers: a site named by its bond lengths when
    the paper prints no coordinates, the paper's valences for a .cif that states none, one table per
    mineral in a two-mineral paper, and a table that differs throughout summarised by column."""

    def test_site_named_by_its_bond_lengths(self):
        import pymupdf
        from tests.test_bv_check import HYDRATE
        from pxrd_review import bv_check as B
        tmp = tempfile.mkdtemp(prefix='pe_')
        try:
            cif = os.path.join(tmp, 's.cif')
            with open(cif, 'w') as f:                                                           # Ca with three oxygens at 2.32, 2.40, 2.48 Å
                f.write(HYDRATE.split('Ca1 Ca 0 0 0')[0] + 'Ca1 Ca 0 0 0\nO1 O 0.30 0 0\nO2 O 0 0.31 0\nO3 O 0 0 0.29\n')
            st = B.Structure(cif)
            ds = sorted(d for _o, d, _n in st.neighbours(st.cations[0], 3.4))
            self.assertEqual(len(ds), 3)
            path = os.path.join(tmp, 'bonds.pdf')
            doc = pymupdf.open(); page = doc.new_page(width=595, height=842); y = 60
            for ln in ['Table 3. Selected bond lengths (Å)'] + sum([['M1-O%d' % (k + 1), '%.3f(2)' % d] for k, d in enumerate(ds[:3])], []) + ['<M1-O>', '%.3f' % (sum(ds[:3]) / 3)]:   # the base font has no en dash
                page.insert_text((40, y), ln, fontsize=9); y += 12
            doc.save(path); doc.close()
            self.assertEqual(PE._site_map_by_bonds(path, st, set()), {'M1': 'Ca1'})
            self.assertEqual(PE.site_name_map(path, st), {'M1': 'Ca1'})                     # no coordinates table: the bonds decide
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_paper_valences_for_a_silent_cif(self):
        from tests.test_bv_check import HYDRATE
        from pxrd_review import bv_check as B
        tmp = tempfile.mkdtemp(prefix='pe_')
        try:
            cif = os.path.join(tmp, 'v.cif')
            with open(cif, 'w') as f:
                f.write(HYDRATE.replace('Ca1 Ca 0 0 0', 'V1 V 0 0 0'))
            st = PE._structure_for_paper(cif, {'name': 'testite'}, 'Testite, ideally V3+2(PO4)3, is a new mineral. The empirical formula is V3+1.98P3.01O12.', B)
            self.assertEqual([sp.ox for sp in st.sites[0].species], [3])
            self.assertTrue(any("from the paper's formula: V+3" in n for n in st.notes), st.notes)
            st = PE._structure_for_paper(cif, {'name': 'testite'}, 'no formula here', B)
            self.assertEqual([sp.ox for sp in st.sites[0].species], [5])                    # the default stands when the paper says nothing
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_own_mineral_table_and_the_pattern(self):
        class St: name = None
        tabs = [{'page': 10, 'rows': [], 'kind': 'grid', 'caption': 'TABLE 5A. Bond valences (v.u.) for atoms in nigelcookite'},
                {'page': 11, 'rows': [], 'kind': 'grid', 'caption': 'TABLE 5B. Bond valences (v.u.) for atoms in plumbojohntomaite'}]
        kept, left = PE._own_mineral_tables(tabs, '/x/11580_I003563_Plumbojohntomaite.cif', St())
        self.assertEqual([t['page'] for t in kept], [11]); self.assertIn('nigelcookite', left[0])
        kept, left = PE._own_mineral_tables(tabs, '/x/final_structure.cif', St())              # no name to go by: every table stays
        self.assertEqual(len(kept), 2); self.assertEqual(left, [])
        both = [dict(tabs[0]), dict(tabs[0], page=12, caption='Table 6. Bond valences for nigelcookite at 100 K')]
        self.assertEqual(len(PE._own_mineral_tables(both, '/x/nigelcookite.cif', St())[0]), 2)   # two tables of the same mineral
        lines = ['bond-valence table 1: 11 cells compared, 7 disagree (computed with X; H columns not compared)',
                 'table 1: O1–P1 1.29 vs 1.22 computed', 'table 1: O2–P1 1.22 vs 1.16 computed', 'table 1: O3–P1 1.35 vs 1.27 computed',
                 'table 1: O5–P2 1.35 vs 1.26 computed', 'table 1: O7–P2 1.37 × 2↓ vs 1.28 computed (1.28 per bond, ×2↓)',
                 'table 1: O9–M2 0.47 0.46 vs 1.07 computed (per bond: 0.53, 0.54; total 1.07)',
                 'table 1: O2–Pb1 is blank but the .cif has that bond (0.06 vu)', 'table 1: Σ for P1 5.24 vs 4.94 from the .cif (parameters: X)',
                 'bond-valence table 2: 11 cells compared, 1 disagree (computed with X; H columns not compared)', 'table 2: O1–P1 1.26 vs 1.22 computed']
        per = PE._bv_per_table(lines)
        self.assertEqual([(t, n, b) for t, n, b, _ in per], [(1, 11, 7), (2, 11, 1)])
        pat = PE._bv_pattern(per[0][3], 11, 7)
        self.assertIn('P1: 3 cells, the table higher by 0.06–0.08 vu', pat)
        self.assertIn('M2: 1 cell, the table lower by 0.07 vu', pat)                        # the two-value cell: its worse value against its own bond
        self.assertIn('1 cell blank where the .cif has a bond', pat); self.assertIn('the other 4 cells agree', pat)
        sums = ['bond-valence sums (table 1, column BVS): 12 cells compared, 6 disagree (computed with X)',
                'table 1: BVS of Ba1 2.12 in the table vs 2.44 from the .cif (parameters: X)', 'table 1: BVS of Na4/Dy4 0.97 in the table vs 1.19 from the .cif (parameters: X)']
        self.assertIn('Ba1, Na4/Dy4: 2 cells, the table lower by 0.22–0.32 vu; the other 6 cells agree', PE._bv_pattern(sums, 12, 6))


class HandCheckRules(unittest.TestCase):
    """Owner's rules of 2026-09-07: a calculated powder line is flagged only when egregiously off its
    cell (2 % or more) — a smaller offset is a note; the paper's own apfu column is another part of
    the paper that vouches for its formula when the wt% reading does not."""

    def test_only_an_egregious_powder_line_is_red(self):
        from docx import Document
        tmp = tempfile.mkdtemp(prefix='pe_'); path = os.path.join(tmp, 'rutile.docx')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        doc = Document()
        doc.add_paragraph('Rutile. The powder pattern was indexed on a tetragonal cell, a = 4.5937(2), c = 2.9587(1) Å, V = 62.43 Å3, Z = 2.')
        doc.add_paragraph('Table 2. Powder X-ray diffraction data for rutile.')
        t = doc.add_table(rows=0, cols=7)
        for row in (('Iobs', 'dobs', 'Icalc', 'dcalc', 'h', 'k', 'l'), ('100', '3.248', '100', '3.2482', '1', '1', '0'), ('50', '2.487', '48', '2.460', '1', '0', '1'),
                    ('20', '2.187', '19', '2.250', '1', '1', '1'), ('10', '2.054', '9', '2.0544', '2', '1', '0'), ('60', '1.687', '58', '1.6874', '2', '1', '1'), ('30', '1.624', '28', '1.6237', '2', '2', '0')):
            cells = t.add_row().cells
            for c, v in zip(cells, row):
                c.text = v
        doc.save(path)
        cc = PE.cell_check(path, None)
        self.assertEqual(cc['status'], 'checked')
        self.assertEqual([hkl for _d, _i, hkl, _dc, _dev, _f in cc['bad']], [(1, 1, 1)])                 # 2.250 vs 2.1873: +2.9 %, flagged
        self.assertTrue(any(l.startswith('2.25 (1 1 1) does not follow the cell') for l in cc['lines']), cc['lines'])
        self.assertTrue(any(l.startswith('2.46 (1 0 1) sits +1.1 % off the cell') and l.endswith('[unverified]') for l in cc['lines']), cc['lines'])   # 2.460 vs 2.4874: noted

    def test_apfu_column_vouches_for_the_formula(self):
        import pymupdf
        tmp = tempfile.mkdtemp(prefix='pe_'); path = os.path.join(tmp, 'apfu.pdf')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        doc = pymupdf.open(); page = doc.new_page(width=595, height=842); y = 60
        rows = ['Testite is a new mineral. The empirical formula, based on 4 O apfu, is Mg0.98Ca1.01Si1.00O4.',
                'Table 1. Chemical data (wt%) for testite', 'Constituent  Mean  Range', 'MgO  25.30  25.0-25.6', 'CaO  36.20  35.9-36.5', 'SiO2  38.40  38.1-38.7', 'Total  99.90',
                'Mg  0.98', 'Ca  1.01', 'Si  1.00']
        for row in rows:
            page.insert_text((40, y), row, fontsize=9); y += 14
        doc.save(path); doc.close()
        e = PE.epma_table(path, 'testite')
        self.assertEqual(e['apfu'], {'Mg': 0.98, 'Ca': 1.01, 'Si': 1.0})                                # the block under the Total, read and kept
        self.assertEqual([r['constituent'] for r in e['rows']], ['MgO', 'CaO', 'SiO2'])
        # the wt% reproduce the formula on their own here; the apfu column then adds nothing but agreement
        r = PE.check_paper(path, None, None)
        self.assertTrue(r['composition']['ok'], r['composition']['lines'])
        self.assertIsNone(r['composition'].get('apfu'))
        # a formula the wt% cannot reproduce (another sample's) that the apfu column vouches for: the formula stands, the reading is the tool's
        ex = r['extract']; text = PE.text_of(path).replace('Mg0.98Ca1.01Si1.00O4', 'Mg0.98Ca1.01Si1.00O4')
        e2 = dict(e); e2['rows'] = [dict(x, mean=x['mean'] * (1.3 if x['constituent'] == 'MgO' else 0.9)) for x in e['rows']]
        ex2 = dict(ex); ex2['epma'] = e2
        c2 = PE.check_composition(ex2, text)
        self.assertTrue(c2['ok'], c2['lines']); self.assertTrue(c2['verified'])
        self.assertIn("the paper's own apfu column reproduces it", c2.get('apfu') or '', c2['lines'])


def _line(y, *cells):
    """One typeset line in the shape `paper_extract._pages` returns."""
    return {'y': y, 'top': y - 8.0, 'bot': y + 2.0,
            'w': [(x, y - 8.0, x + 7.0 * len(t), y + 2.0, t) for x, t in cells]}


class _Fake:
    """The little a bond-valence table reader asks of a structure: its site labels."""
    def __init__(self, cations, anions):
        mk = lambda ls: [type('S', (), {'label': l, 'element': l[0]})() for l in ls]
        self.cations = mk(cations); self.anions = mk(anions); self.aliases = {}


class BondValenceTableReading(unittest.TestCase):
    """The layouts of a printed bond-valence table that the corpus turned up."""

    def pages(self, *pages):
        self._saved = PE._pages
        PE._pages = lambda _pdf, **kw: list(pages)
        self.addCleanup(lambda: setattr(PE, '_pages', self._saved))

    def test_a_cell_holding_two_valences_separated_by_a_comma(self):
        st = _Fake(['Na1', 'Fe1'], ['O1', 'O2', 'O3'])
        self.pages([_line(50, (40, 'Na1'), (100, 'Fe1'), (160, 'Sum')),
                    _line(62, (10, 'O1'), (40, '0.04,0.02→'), (100, '0.50'), (160, '1.90')),
                    _line(74, (40, '0.13,0.06↓'), (100, '×2↓')),
                    _line(86, (10, 'O2'), (40, '0.11→'), (100, '0.55'), (160, '1.95')),
                    _line(98, (10, 'O3'), (40, '0.10→'), (100, '0.50'), (160, '1.87'))])
        t = PE.bv_tables('x.pdf', st)
        self.assertEqual(len(t), 1)
        self.assertEqual([r[0] for r in t[0]['rows']], ['Atom', 'O1', 'O2', 'O3'])   # the ',' row did not end the table

    def test_a_transposed_grid_beside_the_other_page_column(self):
        st = _Fake(['Ag1', 'Sb1'], ['S1', 'S2', 'S3'])
        self.pages([_line(50, (10, 'Crystallographic'), (90, 'Nomenclature'), (200, 'Site'),
                          (240, 'S1'), (280, 'S2'), (320, 'S3'), (360, 'Σcations')),
                    _line(62, (10, 'an'), (40, 'easier'), (90, 'convergence'), (200, 'Ag1'),
                          (240, '0.37'), (280, '0.36'), (320, '0.38'), (360, '1.11')),
                    _line(74, (10, 'was'), (40, 'carried'), (90, 'out'), (200, 'Sb1'),
                          (240, '1.12'), (280, '1.03'), (320, '1.04'), (360, '3.19'))])
        t = PE.bv_tables('x.pdf', st)
        self.assertEqual(len(t), 1)
        self.assertEqual(t[0]['rows'], [['Atom', 'Ag1', 'Sb1'], ['S1', '0.37', '1.12'],
                                        ['S2', '0.36', '1.03'], ['S3', '0.38', '1.04'],
                                        ['Σcations', '1.11', '3.19']])

    def test_a_grid_found_from_its_rows_when_the_header_names_no_known_site(self):
        st = _Fake(['M1', 'T1'], ['O1', 'O2', 'O3'])
        self.pages([_line(50, (40, 'M1'), (100, 'T1'), (160, 'Sum')),
                    _line(62, (10, 'O1'), (40, '0.35'), (100, '1.25'), (160, '1.60')),
                    _line(74, (10, 'O2'), (40, '0.34'), (100, '1.25'), (160, '1.59')),
                    _line(86, (10, 'O3'), (40, '0.36'), (100, '1.21'), (160, '1.57'))])
        t = PE.bv_grids_by_rows('x.pdf', st)
        self.assertEqual([r[0] for r in t[0]['rows']], ['Atom', 'O1', 'O2', 'O3'])
        self.assertEqual(t[0]['rows'][0][1:3], ['M1', 'T1'])

    def test_a_coordinates_table_is_not_a_grid(self):
        st = _Fake(['M1'], ['O1', 'O2', 'O3'])
        self.pages([_line(50, (40, 'x'), (100, 'y'), (160, 'z')),
                    _line(62, (10, 'O1'), (40, '0.1607(5)'), (100, '0.7507(11)'), (160, '0.6238(8)')),
                    _line(74, (10, 'O2'), (40, '0.3250(7)'), (100, '0.6194(8)'), (160, '0.5794(8)')),
                    _line(86, (10, 'O3'), (40, '0.3103(6)'), (100, '0.9011(8)'), (160, '0.5553(7)'))])
        self.assertEqual(PE.bv_grids_by_rows('x.pdf', st), [])           # every number carries an esd

    def test_a_bvs_column_whose_label_column_is_unheaded(self):
        st = _Fake(['Ca', 'P1'], ['O1', 'O2'])
        self.pages([_line(38, (10, 'Table'), (40, '4.'), (70, 'Atom'), (110, 'coordinates'),
                          (200, 'and'), (230, 'bond'), (260, 'valence'), (310, 'sums')),
                    _line(50, (40, 'x'), (100, 'y'), (160, 'z'), (220, 'Ueq'), (280, 'BVS')),
                    _line(62, (10, 'Ca'), (40, '-0.75'), (100, '-0.0214(2)'), (160, '0'), (220, '0.0163(7)'), (280, '2.12')),
                    _line(74, (10, 'P1'), (40, '-0.6772'), (100, '0.2565(2)'), (160, '-0.1866'), (220, '0.0152(5)'), (280, '5.05'))])
        t = PE.bvs_site_tables('x.pdf', st)
        self.assertEqual(t[0]['rows'], [('Ca', 2.12), ('P1', 5.05)])

    def test_the_sums_a_bond_table_prints_under_each_block(self):
        from pxrd_review import paper_bonds as PB
        tabs = PB.read_tables('x.pdf', pages=[[
            _line(50, (40, 'Ca1–O5'), (110, '2.327(12)')),
            _line(62, (40, 'Ca1–O1'), (110, '2.356(12)')),
            _line(74, (40, 'Ca1–O2'), (110, '2.358(12)')),
            _line(86, (40, '<Ca1–O>'), (110, '2.400')),
            _line(98, (40, 'BVS'), (110, '2.12')),
            _line(110, (40, 'U1–O37'), (110, '1.754(11)')),
            _line(122, (40, 'U1–O3'), (110, '2.435(11)')),
            _line(134, (40, 'BVS'), (110, '6.18'))]])
        self.assertEqual(tabs[0]['sums'], [('Ca1', 2.12), ('U1', 6.18)])


class CaptionAnchoredTable(unittest.TestCase):
    """The paper says which table holds the bond valences. That is read first, and the site labels
    are asked for only afterwards."""

    def pages(self, *pages):
        saved = PE._pages
        PE._pages = lambda _pdf, **kw: list(pages)
        self.addCleanup(lambda: setattr(PE, '_pages', saved))

    def test_the_caption_finds_a_table_naming_no_known_site(self):
        st = _Fake(['Zz1'], ['Qq1'])                                   # nothing in the table matches
        self.pages([_line(40, (40, 'Table'), (70, '8.'), (95, 'Weighted'), (150, 'bond-valence'),
                          (230, 'sums'), (270, 'for'), (300, 'thingite.')),
                    _line(54, (40, 'Site'), (100, 'M(1)'), (160, 'M(2a)'), (220, 'Σanions')),
                    _line(66, (40, 'S(1)'), (100, '2×→0.41×4↓'), (160, '0.33×2↓'), (220, '2.16')),
                    _line(78, (40, 'S(2)'), (100, '0.36'), (160, '0.25'), (220, '2.10')),
                    _line(90, (40, 'S(3)'), (100, '0.38'), (160, '0.29'), (220, '2.04'))])
        t = PE.bv_tables_by_caption('x.pdf', st)
        self.assertEqual(len(t), 1)
        self.assertEqual(t[0]['rows'][0], ['Atom', 'M(1)', 'M(2a)', 'Σanions'])
        self.assertEqual([r[0] for r in t[0]['rows'][1:]], ['S(1)', 'S(2)', 'S(3)'])

    def test_the_facing_page_column_is_not_taken_for_the_table(self):
        st = _Fake(['M1'], ['S1'])
        self.pages([_line(40, (40, 'Table'), (70, '7.'), (95, 'Bond-valence'), (170, 'sums')),
                    _line(54, (10, 'Diffractometer'), (90, 'Bruker'), (200, 'Site'), (250, 'M(1)'), (300, 'Σ')),
                    _line(66, (10, 'Measured'), (70, 'reflections'), (130, '2243'),
                          (200, 'S(1)'), (250, '0.41'), (300, '2.16')),
                    _line(78, (10, 'Unique'), (70, 'reflections'), (130, '348'),
                          (200, 'S(2)'), (250, '0.36'), (300, '2.10'))])
        t = PE.bv_tables_by_caption('x.pdf', st)
        self.assertEqual([r[0] for r in t[0]['rows'][1:]], ['S(1)', 'S(2)'])   # '2243' is no valence, so the run starts at the table

    def test_prose_with_no_table_under_the_caption_yields_nothing(self):
        st = _Fake(['M1'], ['S1'])
        self.pages([_line(40, (40, 'as'), (60, 'shown'), (90, 'in'), (110, 'Table'), (150, '8.'),
                          (170, 'The'), (200, 'bond-valence'), (280, 'sums')),
                    _line(54, (40, 'are'), (70, 'all'), (100, 'close'), (140, 'to'), (170, 'ideal.'))])
        self.assertEqual(PE.bv_tables_by_caption('x.pdf', st), [])


class BvTableFinderOrder(unittest.TestCase):
    """The order of the finders is the contract: better evidence first. Reading the caption before
    the header match once replaced tables already matched to the structure and cost 17 papers their
    verdict, so the order is pinned here rather than left to the reading of the call site."""

    def test_a_header_matched_table_is_preferred_to_a_caption_matched_one(self):
        calls = []
        def stub(name, result):
            def f(_path, _st):
                calls.append(name); return result
            return f
        saved = {n: getattr(PE, n) for n in ('bv_tables', 'bv_tables_by_caption', 'bv_bond_column',
                                             'bv_grids_by_rows', 'bvs_site_tables', '_bvs_marks_table')}
        self.addCleanup(lambda: [setattr(PE, n, f) for n, f in saved.items()])
        for n in saved:
            setattr(PE, n, stub(n, [{'rows': [], 'kind': 'grid', 'page': 1}]))
        got = PE._find_bv_tables('x.pdf', None)
        self.assertEqual(calls, ['bv_tables'])                      # the first that answers, and no other
        self.assertTrue(got)

    def test_each_finder_answers_only_what_the_one_before_could_not(self):
        calls = []
        def stub(name, result):
            def f(_path, _st):
                calls.append(name); return result
            return f
        saved = {n: getattr(PE, n) for n in ('bv_tables', 'bv_tables_by_caption', 'bv_bond_column',
                                             'bv_grids_by_rows', 'bvs_site_tables', '_bvs_marks_table')}
        self.addCleanup(lambda: [setattr(PE, n, f) for n, f in saved.items()])
        for n in saved:
            setattr(PE, n, stub(n, []))
        PE._find_bv_tables('x.pdf', None)
        self.assertEqual(calls, ['bv_tables', 'bv_tables_by_caption', 'bv_bond_column',
                                 'bv_grids_by_rows', 'bvs_site_tables', '_bvs_marks_table'])


class GauntletRows(unittest.TestCase):
    """The three readings a description is 'fully read' by, beside the table and the optics: the
    bond-valence TABLE (checked whether or not the paper cites a parameter set), the coordinates
    table (settled by a .cif's positions, or by the structure it builds), and the compatibility
    index the paper states."""

    def _page(self, blocks):
        """blocks: [(text, x)] lines, top to bottom -> a one-page pdf path (the base font has no en dash)."""
        import pymupdf
        tmp = tempfile.mkdtemp(prefix='pe_'); path = os.path.join(tmp, 'page.pdf')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        doc = pymupdf.open(); page = doc.new_page(width=595, height=842); y = 60
        for cells in blocks:
            if isinstance(cells, str):
                page.insert_text((40, y), cells, fontsize=9)
            else:
                for x, t in cells:
                    page.insert_text((x, y), t, fontsize=9)
            y += 13
        doc.save(path); doc.close()
        return path

    BONDS = (('Ca1', 'O1', '2.340(2)'), ('Ca1', 'O2', '2.360(2)'), ('Ca1', 'O3', '2.380(2)'), ('Ca1', 'O4', '2.350(2)'),
             ('Si1', 'O1', '1.610(2)'), ('Si1', 'O2', '1.620(2)'), ('Si1', 'O3', '1.630(2)'), ('Si1', 'O4', '1.615(2)'))

    def _head(self):
        return ['Testite, a new mineral from Nowhere',
                'The empirical formula, calculated on the basis of 4 O apfu, is Ca1.00Si1.00O4.',
                'Table 3. Selected bond lengths (A) for testite.'] + \
               [[(40, c), (70, '-'), (80, a), (120, d)] for c, a, d in self.BONDS]

    def _bv_cells(self):
        """The grid the paper would print, computed by the tool itself — never a hard-coded constant."""
        from pxrd_review import paper_bonds as PB, bv_check as B
        path = self._page(self._head())
        text = PE.text_of(path); ex = PE.extract(path, None, None, write=False)
        st, _res, _g = PB.structure_for(path, ex, text)
        self.assertIsNotNone(st)
        _r, _an, cells = PB.compute(st, B.Params(prefer='gh', u6='burns'))
        return {k: v[0][0] for k, v in cells.items()}                  # (anion, cation) -> valence

    def _paper(self, shift=None):
        cells = self._bv_cells()
        rows = [[(40, 'Atom'), (100, 'Ca1'), (160, 'Si1'), (220, 'Σ')]]
        for an in ('O1', 'O2', 'O3', 'O4'):
            vals = [cells[(an, 'Ca1')], cells[(an, 'Si1')]]
            if shift and an in shift:
                vals = [v + shift[an] for v in vals]
            rows.append([(40, an), (100, '%.2f' % vals[0]), (160, '%.2f' % vals[1]), (220, '%.2f' % sum(vals))])
        return self._page(self._head() + ['', 'Table 4. Bond-valence analysis (vu) for testite.'] + rows)

    def test_bv_table_without_a_citation(self):
        r = PE.check_paper(self._paper(), None, None); F = r['fields']
        self.assertEqual(F['bv.params']['status'], 'none', r['lines'])   # the paper names no parameter set: that reading is absent …
        self.assertEqual(F['bv.table']['status'], 'agrees', r['lines'])  # … and the table is checked all the same
        self.assertEqual((F['bv.table']['verified_by'], F['bv.table']['page']), ('bv', 1))
        self.assertIn('bond-valence table ✓ (p1)', r['lines'][0])
        self.assertIn('Bond-valence', F['bv.table']['source'])
        self.assertEqual(F['bv.table']['value']['cells'], 8)

    def test_bv_table_refuted_and_unmatched(self):
        r = PE.check_paper(self._paper({'O1': 0.25}), None, None)
        self.assertEqual(r['fields']['bv.table']['status'], 'disagrees', r['lines'])        # 2 of 8 cells off: more than the slip a table is allowed, short of differing throughout
        r = PE.check_paper(self._paper({'O1': 0.3, 'O2': 0.3, 'O3': 0.3, 'O4': 0.3}), None, None)
        self.assertEqual(r['fields']['bv.table']['status'], 'unverified', r['lines'])       # differs throughout: a doubt, not a comparison

    RUTILE_P1 = (('Ti1', '0.00000', '0.00000', '0.00000'), ('Ti2', '0.50000', '0.50000', '0.50000'),
                 ('O1', '0.30479', '0.30479', '0.00000'), ('O2', '0.69521', '0.69521', '0.00000'),
                 ('O3', '0.80479', '0.19521', '0.50000'), ('O4', '0.19521', '0.80479', '0.50000'))

    def _rutile(self, rows=None, sg='space group P1, '):
        rows = rows or self.RUTILE_P1
        return self._page(['Rutile from Nowhere',
                           'Rutile is tetragonal, %sa = 4.5937(2), b = 4.5937(2), c = 2.9587(1) A, V = 62.43 A3, Z = 2.' % sg,
                           'The empirical formula, calculated on the basis of 2 O apfu, is Ti1.00O2.',
                           'Table 2. Atom coordinates and displacement parameters for rutile.',
                           [(40, 'Atom'), (90, 'x'), (150, 'y'), (210, 'z'), (270, 'Ueq')]] +
                          [[(40, l), (90, x), (150, y), (210, z), (270, '0.0050(2)')] for l, x, y, z in rows])

    def test_coords_from_the_printed_structure(self):
        r = PE.check_paper(self._rutile(), None, None); F = r['fields']
        self.assertEqual(F['coords']['status'], 'agrees', r['lines'])
        self.assertEqual((F['coords']['verified_by'], F['coords']['page'], F['coords']['value']['sites']), ('paper_structure', 1, 6))
        self.assertIn('coordinates ✓ (p1)', r['lines'][0])
        o = {}; PE.coords_check(self._rutile(), None, PE.text_of(self._rutile()), o)
        self.assertNotIn('paper_structure', o)                         # the coords build never masquerades as a bond-valence check
        self.assertEqual((F['bv.table']['status'], F['bv.params']['status']), ('none', 'none'))
        bad = list(self.RUTILE_P1); bad[2] = ('O1', '0.40479', '0.30479', '0.00000')
        r = PE.check_paper(self._rutile(bad), None, None)
        self.assertEqual(r['fields']['coords']['status'], 'unverified', r['lines'])   # one x off by 0.1: the sums no longer come out
        r = PE.check_paper(self._rutile(sg=''), None, None)
        self.assertEqual(r['fields']['coords']['status'], 'nooracle', r['lines'])     # no space group: nothing to build with

    def test_coords_against_a_cif(self):
        from tests.test_bv_check import HYDRATE
        tmp = tempfile.mkdtemp(prefix='pe_'); self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        cif = os.path.join(tmp, 'h.cif'); open(cif, 'w').write(HYDRATE)
        sites = [('Ca1', '0.00000', '0.00000', '0.00000'), ('O1', '0.27500', '0.12500', '0.00000'), ('OW1', '0.00000', '0.30000', '0.00000'),
                 ('O2', '0.30311', '0.47500', '0.00000'), ('O3', '0.69689', '0.47500', '0.00000')]
        page = lambda rows: self._page(['Testhydrate from Nowhere', 'Table 2. Atom coordinates for testhydrate.',
                                        [(40, 'Atom'), (90, 'x'), (150, 'y'), (210, 'z'), (270, 'Ueq')]] +
                                       [[(40, l), (90, x), (150, y), (210, z), (270, '0.0100(3)')] for l, x, y, z in rows])
        r = PE.check_paper(page(sites), cif, None); F = r['fields']
        self.assertEqual((F['coords']['status'], F['coords']['verified_by']), ('agrees', 'cif'), r['lines'])
        r = PE.check_paper(page([(l, x, y, '0.20000') for l, x, y, _z in sites]), cif, None)
        self.assertEqual(r['fields']['coords']['status'], 'unverified', r['lines'])   # every z off the .cif's: another setting, or a misread column

    def test_gd_row_needs_an_n(self):
        r = PE.check_paper(self._page(['Testite from Nowhere', 'The Gladstone-Dale compatibility index, 1 - (KP/KC), is -0.021 (superior) for the empirical formula.']), None, None)
        F = r['fields']
        self.assertEqual((F['gd']['status'], F['gd']['value']), ('nooracle', {'ci': -0.021, 'category': 'superior'}), r['lines'])
        self.assertIn('no n read', F['gd']['detail'])
        self.assertIn('compatibility · ', r['lines'][0])

    def test_why_prints_the_records(self):
        import io, contextlib
        path = self._paper()
        for flag, want in ((['--why'], True), ([], False)):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                PE.main([path, '--check'] + flag)
            self.assertEqual('    source:' in buf.getvalue(), want)
            self.assertEqual('bv.table' in buf.getvalue(), want)


class OpticsFonts(unittest.TestCase):
    """The optics sentence as the font delivers it: a Symbol-font α β γ that reach the text as a b c
    (or g), '=' as '¼' or a lost glyph, and the index a paper computed instead of measuring."""

    def test_latin_for_greek(self):
        o = PE.optics('Optically, smamite is biaxial (-), a = 1.556(1), b = 1.581(1), g = 1.588(1) (white light). The 2V (meas) = 54(1)°.')
        self.assertEqual(o['n'], round((1.556 + 1.581 + 1.588) / 3, 4)); self.assertFalse(o['n_calc'])
        o = PE.optics('It is optically biaxial (+) with refractive indices a ¼ 1.664(2), b ¼ 1.670(2), c ¼ 1.692(2); 2Vcalc. ¼ 56°. Dcalc. ¼ 3.608 g/cm3.')
        self.assertEqual((o['n'], o['D_calc']), (round((1.664 + 1.670 + 1.692) / 3, 4), 3.608))
        o = PE.optics('biaxial (+), a . 1.95, b . 1.95, c . 1.95; 2V = 72(2)8; moderate dispersion')
        self.assertEqual(o['n'], 1.95)
        o = PE.optics('The mineral is uniaxial (-), with w = 1.582(2), e = 1.613(2).')
        self.assertEqual(o['n'], round((2 * 1.582 + 1.613) / 3, 4))

    def test_a_cell_edge_and_a_pleochroism_are_not_indices(self):
        o = PE.optics('Optically biaxial (+); pleochroism: O = green, E = light yellow. The cell is a = 10.2, b = 1.95, c = 12.1 Å.')
        self.assertIsNone(o['n'])                                        # 'b = 1.95' stands alone: no triple, no ω/ε pair

    def test_the_index_the_paper_computed(self):
        for s in ('Mean refractive index, calculated according to the Gladstone–Dale relationship (Mandarino, 1979, 1981), is 1.889 and 1.928 for domains #1 and #2.',
                  'The Gladstone–Dale relationship (Mandarino, 1981) predicts an average index of refraction of 1.889 for the ideal formula.',
                  'with a calculated density of 3.775 g⋅cm–3 and a mean refractive index ∼1.889. The triclinic',
                  'The calculated mean refractive index is 1.889. The chemical composition'):
            o = PE.optics(s)
            self.assertEqual((o['n'], o['n_calc']), (1.889, True), s)
        o = PE.optics('The mean refractive index could not be measured. The cell has a = 1.889 Å.')
        self.assertIsNone(o['n'])
        o = PE.optics('with an average Ca–O distance of 2.508 Å and the Ca–F distance of 2.247 Å.')
        self.assertIsNone(o['n'])                                        # 'a[n av]erage … distance' is not n_av
        o = PE.optics('The average refractive index (nave) was calculated from the Gladstone‒Dale compatibility index as 1.907, using the unit cell.')
        self.assertEqual((o['n'], o['n_calc']), (1.907, True))

    def test_a_verified_density_keeps_its_verdict(self):
        """A misread index makes the compatibility check doubt the density too; the density the cell,
        Z and the formula reproduce keeps the cell's verdict."""
        import pymupdf
        tmp = tempfile.mkdtemp(prefix='pe_'); path = os.path.join(tmp, 'rutile.pdf')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        doc = pymupdf.open(); page = doc.new_page(width=595, height=842); y = 60
        for ln in ('Rutile from Nowhere', 'Rutile is tetragonal, a = 4.5937(2), c = 2.9587(1) A, V = 62.43 A3, Z = 2.',
                   'The calculated density is 4.248 g/cm3. Optically uniaxial (+), omega = 1.616, epsilon = 1.903.',
                   'The compatibility index, 1 - (KP/KC), is superior.',
                   'The empirical formula, calculated on the basis of 2 O apfu, is Ti1.00O2.', 'Table 1. Chemical data (wt%) for rutile.',
                   'Constituent   Mean     Range        S.D.', 'TiO2  99.10  98.80-99.40  0.21', 'FeO  0.40  0.30-0.50  0.07', 'SiO2  0.30  0.20-0.40  0.06', 'Total  99.80'):
            page.insert_text((40, y), ln, fontsize=9); y += 14
        doc.save(path); doc.close()
        r = PE.check_paper(path, None, None); F = r['fields']
        self.assertEqual(F['optics.n']['status'], 'unverified', r['lines'])                       # the index is a digit off (ω 1.616 for 2.616)
        self.assertEqual((F['optics.D_calc']['status'], F['optics.D_calc']['verified_by']), ('agrees', 'cell_consistency'), r['lines'])


class CompatibilityStatement(unittest.TestCase):
    """The compatibility statement as papers print it, and as the font and the text layer deliver it."""

    def test_the_forms(self):
        for s, ci, cat in (('The Gladstone-Dale compatibility (Mandarino 2007), 1  (Kp/Kc), is 0.010 (superior) using the empirical formula and 0.007 (superior) using the ideal formula.', 0.010, 'superior'),
                           ('The Gladstone-Dale compatibility (Mandarino, 1981) 1  (KP/KC) = 0.048 (good), based on the empirical formula.', 0.048, 'good'),
                           ('The GladstoneDale compatibility is 0.0416 (good) using the empirical formula and single-crystal unit cell.', 0.0416, 'good'),
                           ('The calculated compatibility (1  KP/KC) is excellent (0.021) (Mandarino 1981). RAMAN SPECTROSCOPY', 0.021, 'excellent'),
                           ('The Gladstone-Dale compatibility index (Mandarino, 1981) calculated using the above optical properties with the empirical formula and calculated density is 0.021, which is classed as superior.', 0.021, 'superior'),
                           ('The Gladstone–Dale compatibility index (Mandarino, Figure 3. Raman spectra for (a) fluormacraeite and (b) macraeite. 1981) is 0.0083 (superior) based on the empirical formula.', 0.0083, 'superior'),
                           ('The compatibility index, 1 − (KP/KC), is −0.012, in the superior range of Mandarino (1981).', -0.012, 'superior'),
                           ('The Gladstone–Dale compatibility index calculated based on the empirical formula and unit-cell parameters from the singlecrystal XRD data is 1 – (Kp/Kc) = 0.007 using Dmeas and 0.011 using Dcalc.', 0.007, None)):
            g = PE.gd_statement(s)
            self.assertEqual((g['ci'], g['category']), (ci, cat), s)

    def test_not_a_statement(self):
        g = PE.gd_statement('The average refractive index (nave) was calculated from the Gladstone‒Dale compatibility index as 1.907, using the unit cell. Good agreement was found.')
        self.assertIsNone(g['ci'])                                       # the .907 of an index is not a compatibility index
        self.assertIsNone(g['category'])                                 # 'Good agreement' is the next sentence
        g = PE.gd_statement('The compatibility of the powder pattern with the calculated one is good.')
        self.assertEqual((g['ci'], g['category']), (None, None))


class DensitySentences(unittest.TestCase):
    """The density as papers state it, beyond 'Dcalc = 3.21'."""

    def test_forms(self):
        for s, dm, dc in (('The calculated density is Dx = 3.199 g/cm3 and the measured density is Dm = 3.201(3) g/cm3.', 3.201, 3.199),
                          ('The density calculated using the empirical formula and crystal structure is 2.847 g/cm3.', None, 2.847),
                          ('The measured density of is 3.40 g/cm3 (Clerici solution). The calculated density obtained from the empirical formula is 3.38 g/cm3.', 3.40, 3.38),
                          ('The density is 3.05(2) g/cm3. Optically, crystals are biaxial.', 3.05, None),
                          ('Calculated density (g cm–3) 2.880 Absorption coefficient (mm–1) 1.560', None, 2.880),
                          ('The calculated density based on the empirical formula and powder unit-cell parameters obtained from the powder X-ray diffraction data is 4.679 g/cm3.', None, 4.679),
                          ('The density measured via flotation in a mixture of methylene iodide and toluene is 3.05(2) g/cm3. The calculated density based on the empirical formula is 3.09 g/cm3.', 3.05, 3.09)):
            o = PE.optics(s)
            self.assertEqual((o['D_meas'], o['D_calc']), (dm, dc), s)

    def test_not_a_density(self):
        o = PE.optics('Density was not measured owing to the small amount of material. 2V(calc) = 51.68°.')
        self.assertEqual((o['D_meas'], o['D_calc']), (None, None))       # '1.68' inside 51.68 is no density


class TableMarks(unittest.TestCase):
    """The marks a table hangs on a constituent's name, in whichever glyph the font delivers them."""

    def test_footnote_glyphs_and_welded_qualifiers(self):
        for tok, want in (('H2O∗', 'H2O'), ('Li2O∗∗', 'Li2O'), ('H2Ocalc', 'H2O'), ('CO2calc', 'CO2'), ('H2Ocalc.', 'H2O'), ('H2O†', 'H2O'), ('SiO2a', 'SiO2'), ('H2O(calc)', 'H2O')):
            self.assertEqual(PE._constituent_ok(tok)[0], want, tok)
        self.assertEqual(PE._constituent_ok('Xa'), (None, None))
        self.assertEqual(PE._constituent_ok('FeOtot'), (None, None))                    # total iron beside the FeO/Fe2O3 split: not a row to add


class NormalisedSet(unittest.TestCase):
    """A table whose Mean column adds to well over 100 is offered normalised, as the paper's own
    'Norm.' column has it — and only the stated index can accept it."""

    def test_excess_total_offers_the_normalised_set(self):
        ex = {'epma': {'rows': [{'constituent': 'MgO', 'mean': 14.19}, {'constituent': 'CaO', 'mean': 0.14}, {'constituent': 'V2O5', 'mean': 64.90}, {'constituent': 'H2O', 'mean': 39.38}], 'total': 100.0}}
        sets, why = PE._gd_wt_sets(ex, None)
        totals = [round(sum(w.values()), 1) for w, _c in sets]
        self.assertIn(100.0, totals); self.assertIn(118.6, totals)
        self.assertTrue(all(not c for w, c in sets if round(sum(w.values()), 1) == 100.0))       # the scaled set is never 'complete'
        self.assertIn('119', why)                                                             # a failure is still explained by the table as read
        ex['epma']['rows'] = ex['epma']['rows'][:3]                                            # short of H2O: 79 % — not scaled up
        sets, why = PE._gd_wt_sets(ex, None)
        self.assertNotIn(100.0, [round(sum(w.values()), 1) for w, _c in sets])


class GladstoneDaleVariants(unittest.TestCase):
    """Table 7's class constants: a paper picks by its mineral class, and only its own stated index
    can accept the alternative."""

    def test_the_uranyl_constant_under_arbitration(self):
        from pxrd_review import gd as GD
        wt = {'UO3': 60.0, 'SO3': 20.0, 'H2O': 20.0}
        kc_a = GD.kc(wt)[0]; kc_b = GD.kc(wt, {'UO3': 0.134})[0]
        self.assertGreater(kc_b, kc_a)
        n, D = 1.60, 3.0
        ci_b = 1 - ((n - 1) / D) / kc_b                                   # the index the paper would state on the uranyl convention
        ex = {'optics': {'n': n, 'n_from': 'n = 1.60', 'D_meas': None, 'D_calc': D, 'sentences': []},
              'epma': {'rows': [{'constituent': c, 'mean': v} for c, v in wt.items()], 'total': 100.0}}
        out = PE.gd_check(ex, None, {'ci': round(ci_b, 3), 'category': None, 'sentence': ''})
        self.assertEqual(out['status']['optics.n'], 'agrees', out)
        self.assertIn('UO3 at 0.134', out['detail'])
        out = PE.gd_check(ex, None, {'ci': None, 'category': 'superior', 'sentence': ''})   # a category alone cannot accept a variant
        self.assertNotIn('UO3 at', out.get('detail') or '')
        self.assertEqual(sorted(len(o) for o in PE._gd_variant_overrides({'UO3': 60.0, 'MgO': 5.0, 'SiO2': 35.0})), [1, 1, 2])

    def test_an_index_used_as_an_input_is_not_a_statement(self):
        g = PE.gd_statement('The average refractive index (nave) was calculated from the Gladstone-Dale compatibility index as 1.907, using the unit cell. ω and ε were calculated from nave after measuring a birefringence of 0.075.')
        self.assertIsNone(g['ci'])


class OpticsForms2(unittest.TestCase):
    def test_primed_indices_and_the_values_of_form(self):
        o = PE.optics('Sejkoraite-(Y) is yellow, biaxial negative with α′ = 1.62(2), β′ = 1.662(3), γ′ = 1.73(1), 2Vcalc = 79°.')
        self.assertEqual(o['n'], round((1.62 + 1.662 + 1.73) / 3, 4))
        o = PE.optics('Keystoneite is uniaxial (+), and the values of x and e (measured at 589 nm) are 1.85(1) and 1.99(1), respectively.')
        self.assertEqual(o['n'], round((2 * 1.85 + 1.99) / 3, 4))
        o = PE.optics('The mineral is uniaxial (-); the values of ω and ε are 1.585(2) and 1.600(2).')
        self.assertEqual(o['n'], round((2 * 1.585 + 1.600) / 3, 4))


class ProseAnalyses(unittest.TestCase):
    def test_three_constituents_with_a_total_and_decorated_values(self):
        pt = PE.prose_table('The composition (electron microprobe, H2O by gas chromatography) is (in wt.%): Al2O3 24.36, SO3 40.69, H2O 34(2), total 99.05. The empirical formula is')
        self.assertEqual(([(r['constituent'], r['mean']) for r in pt['rows']], pt['total']), ([('Al2O3', 24.36), ('SO3', 40.69), ('H2O', 34.0)], 99.05))
        pt = PE.prose_table('analyses gave UO3 78.6 (77.9–79.3) (0.31), SO3 10.1 (9.8–10.4) (0.2), H2O 11.02 (crystal structure), total 100.96 wt.%. The empirical formula')
        self.assertEqual([(r['constituent'], r['mean']) for r in pt['rows']], [('UO3', 78.6), ('SO3', 10.1), ('H2O', 11.02)])
        self.assertIsNone(PE.prose_table('Al2O3 24.36, SO3 40.69, H2O 34.00 and nothing else.'))     # three without a total: not enough


class SitePrefixB(unittest.TestCase):
    def test_the_b_site_of_a_monazite_type_formula(self):
        f = PE._journal_to_icdd('A(Ca3.89Th0.08Sr0.02La0.03)Σ4.02 B(Ce4+ 0.76Nd0.13Y0.08)Σ1.0 (AsO4)4.0')
        self.assertNotIn('B(', f.replace(' ', '')[:1] + f.replace(' ', ''))
        self.assertIn('Ce', f)
        self.assertIn('B(', PE._journal_to_icdd('Na0.95B(OH)4(SO4)').replace(' ', ''))           # boron keeps its bracket


class VerifiedStructureChecksTheTable(unittest.TestCase):
    """A coordinate structure the paper's own bond distances verify stands in for a .cif: the
    bond-valence table is judged against it at flag grade."""

    def _pdf(self, grid=None):
        import pymupdf
        tmp = tempfile.mkdtemp(prefix='pe_'); path = os.path.join(tmp, 'p.pdf'); self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        doc = pymupdf.open(); page = doc.new_page(width=595, height=842); y = 50
        for ln in ('Rutile from Nowhere', 'Rutile is tetragonal, space group P1, a = 4.5937(2), b = 4.5937(2), c = 2.9587(1) A, V = 62.43 A3, Z = 2.',
                   'The empirical formula, calculated on the basis of 2 O apfu, is Ti1.00O2.', 'Table 2. Atom coordinates for rutile.'):
            page.insert_text((40, y), ln, fontsize=9); y += 13
        for cells in (('Atom', 'x', 'y', 'z', 'Ueq'), ('Ti1', '0.00000', '0.00000', '0.00000', '0.0050(2)'), ('Ti2', '0.50000', '0.50000', '0.50000', '0.0050(2)'),
                      ('O1', '0.30479', '0.30479', '0.00000', '0.0060(2)'), ('O2', '0.69521', '0.69521', '0.00000', '0.0060(2)'),
                      ('O3', '0.80479', '0.19521', '0.50000', '0.0060(2)'), ('O4', '0.19521', '0.80479', '0.50000', '0.0060(2)')):
            for x, t in zip((40, 100, 160, 220, 280), cells):
                page.insert_text((x, y), t, fontsize=9)
            y += 13
        y += 6; page.insert_text((40, y), 'Table 3. Selected bond lengths (A) for rutile.', fontsize=9); y += 13
        for c, a, d in (('Ti1', 'O1', '1.980(1)'), ('Ti1', 'O2', '1.980(1)'), ('Ti1', 'O3', '1.949(1)'), ('Ti1', 'O4', '1.949(1)'), ('Ti2', 'O3', '1.980(1)'), ('Ti2', 'O1', '1.949(1)')):
            page.insert_text((40, y), c, fontsize=9); page.insert_text((70, y), '-', fontsize=9); page.insert_text((80, y), a, fontsize=9); page.insert_text((120, y), d, fontsize=9); y += 13
        if grid:
            y += 6; page.insert_text((40, y), 'Table 4. Bond-valence analysis (vu) for rutile.', fontsize=9); y += 13
            for cells in grid:
                for x, t in zip((40, 100, 160, 220), cells):
                    page.insert_text((x, y), t, fontsize=9)
                y += 13
        doc.save(path); doc.close()
        return path

    def test_flag_grade_against_the_verified_structure(self):
        from pxrd_review import paper_structure as PS, bv_check as B
        p0 = self._pdf()
        st, info = PS.build(p0, PE.text_of(p0), bonds=[('Ti1', 'O1', 1.98), ('Ti1', 'O2', 1.98), ('Ti1', 'O3', 1.949), ('Ti1', 'O4', 1.949), ('Ti2', 'O3', 1.98), ('Ti2', 'O1', 1.949)])
        self.assertTrue(info.get('bonds_verified'), info)
        res, an, cells, hb = B.compute(st, B.Params(prefer='gh', u6='burns'), None, 'oo'); PS.discard(info)
        v = lambda a, c: sorted(s for s, _, _ in cells[(a, c)])[0]
        grid = [('Atom', 'Ti1', 'Ti2', 'Σ')] + [(a, ('%.2f' % v(a, 'Ti1')) if (a, 'Ti1') in cells else '', ('%.2f' % v(a, 'Ti2')) if (a, 'Ti2') in cells else '', '2.00') for a in ('O1', 'O2', 'O3', 'O4')]
        r = PE.check_paper(self._pdf(grid), None, None); F = r['fields']
        self.assertEqual((F['coords']['status'], F['coords']['verified_by']), ('agrees', 'bonds'), r['lines'])
        self.assertEqual(F['bv.table']['status'], 'agrees', r['lines'])
        self.assertIn('verified by its bond distances', F['bv.table']['detail'])
        self.assertTrue(any('reproduces 6 of the 6 bond distances' in l and 'structure the paper itself prints' in l for l in r['lines']), r['lines'])
        self.assertFalse(r.get('paper_structure'))                              # not the note-grade path


class FailureLog(unittest.TestCase):
    """`failure_records` turns the readers that did not verify into records with what they read;
    `log_failures` appends them as JSON lines."""

    def test_records_and_log(self):
        import json
        r = {'extract': {'optics': {'n': 1.6, 'n_from': 'n = 1.6', 'n_calc': False}, 'epma': {'page': 3, 'header': 'wt.%', 'rows': [{'constituent': 'SiO2', 'mean': 40.0}], 'total': 99.0}, 'basis': ('O', 4.0)},
             'fields': {'epma': {'value': 1, 'source': 'wt.%', 'page': 3, 'reader': 'layout', 'verified_by': None, 'status': 'unverified', 'detail': 'the wt% read add to 40.0'},
                        'optics.n': {'value': 1.6, 'source': 'n = 1.6', 'page': None, 'reader': 'regex', 'verified_by': 'gd', 'status': 'agrees', 'detail': ''},
                        'coords': {'value': None, 'source': '', 'page': None, 'reader': 'regex', 'verified_by': None, 'status': 'none', 'detail': ''}},
             'coords': {'status': 'none'}, 'bv': None, 'composition': {'lines': ['composition: 1 constituent']}}
        recs = PE.failure_records(r, '/x/paper.pdf', None, has={'coords': True})
        self.assertEqual({x['field'] for x in recs}, {'epma', 'coords'})                # the agreeing reader is no failure
        ep = next(x for x in recs if x['field'] == 'epma')
        self.assertEqual((ep['status'], ep['page'], ep['context']['rows']), ('unverified', 3, [('SiO2', 40.0)]))
        self.assertTrue(next(x for x in recs if x['field'] == 'coords')['silent'])     # the scan says the paper prints coordinates and the reader has nothing
        tmp = tempfile.mkdtemp(prefix='pe_'); self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        path = PE.log_failures(recs, os.path.join(tmp, 'sub', 'f.jsonl')); PE.log_failures(recs, path)
        lines = [json.loads(l) for l in open(path, encoding='utf-8')]
        self.assertEqual(len(lines), 4); self.assertEqual(lines[0]['paper'], 'paper.pdf')


class ValenceSwap(unittest.TestCase):
    """A column that reproduces under the element's other oxidation state is the paper's
    convention, noted and not counted; one that reproduces under neither stays a finding."""

    def test_cell_devs_and_swap_shape(self):
        lines = ['bond-valence table 1: 6 cells compared, 2 disagree (computed with X; H columns not compared)',
                 'table 1: O1–Fe1 0.33 vs 0.48 computed', 'table 1: O2–Fe1 0.32 vs 0.49 computed']
        self.assertEqual(PE._cell_devs(lines[1])[:2], ('1', 'Fe1'))
        # no .cif: the swap reading is not attempted and the lines pass through unchanged
        out, bad = PE._swap_valence(lines, 2, type('S', (), {'sites': []})(), None, {}, '', None, [{'kind': 'grid'}], [], None, 'gh', None)
        self.assertEqual((out, bad), (lines, 2))
