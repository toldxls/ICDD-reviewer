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
        import fitz
        tmp = tempfile.mkdtemp(prefix='pe_'); path = os.path.join(tmp, 'sulfate.pdf')
        try:
            doc = fitz.open(); page = doc.new_page(width=595, height=842); y = 60
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
        import fitz
        tmp = tempfile.mkdtemp(prefix='pe_'); path = os.path.join(tmp, 'across.pdf')
        try:
            doc = fitz.open(); page = doc.new_page(width=595, height=842); y = 60
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
        import fitz
        tmp = tempfile.mkdtemp(prefix='pe_'); path = os.path.join(tmp, 'two.pdf')
        try:
            doc = fitz.open(); page = doc.new_page(width=595, height=842); y = 60
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
        import fitz
        tmp = tempfile.mkdtemp(prefix='pe_'); path = os.path.join(tmp, 'sub.pdf')
        try:
            doc = fitz.open(); page = doc.new_page(width=595, height=842)
            page.insert_text((40, 100), 'B2O', fontsize=9); page.insert_text((54.5, 102.5), '3', fontsize=6)    # the subscript as its own glyph
            page.insert_text((100, 100), '11.43', fontsize=9)
            page.insert_text((40, 120), 'SiO2', fontsize=9); page.insert_text((59, 96), '1', fontsize=6)       # a numbered footnote, superscript
            doc.save(path); doc.close()
            lines = PE.page_lines(fitz.open(path)[0])
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
