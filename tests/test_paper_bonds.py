"""Unit tests for pxrd_review.paper_bonds — the bond distances a paper prints, and the bond
valences that follow from them.

    python3 -m unittest tests.test_paper_bonds -v

The reader is fed typeset lines directly (the shape `paper_extract._pages` returns: a list of
pages, each a list of {'y', 'w': [(x0, y0, x1, y1, text), …]}), so every layout the corpus shows
can be written out here without a .pdf.
"""
import unittest

from pxrd_review import paper_bonds as PB
from pxrd_review import bv_check as B


def line(y, *cells):
    """line(100, (40, 'Pb1'), (60, '–'), (70, 'S7'), (100, '2.814(14)')) -> one typeset line."""
    return {'y': y, 'top': y - 8.0, 'bot': y + 2.0,
            'w': [(x, y - 8.0, x + 8.0 * len(t), y + 2.0, t) for x, t in cells]}


def page(*lines):
    return list(lines)


class Cells(unittest.TestCase):
    """One line of a bond table, in each of the ways the corpus typesets it."""

    def cells(self, *cells):
        return PB._cells(line(100, *cells))

    def test_dash_as_its_own_token(self):
        c = self.cells((40, 'Pb1'), (60, '–'), (70, 'S7'), (100, '2.814(14)'))
        self.assertEqual([(x[1], x[2], x[3], x[4], x[5]) for x in c], [('Pb1', 'S7', 2.814, 14, 1)])

    def test_dash_attached_to_the_anion(self):
        c = self.cells((40, 'X'), (60, '–O(2)'), (100, '2.503(4)'))
        self.assertEqual(c[0][1:6], ('X', 'O2', 2.503, 4, 1))

    def test_continuation_row_carries_no_cation(self):
        c = self.cells((60, '–O(5)'), (100, '2.733(4)'))
        self.assertIsNone(c[0][1])
        self.assertEqual(c[0][2], 'O5')

    def test_pair_written_as_one_token(self):
        c = self.cells((40, 'Al1–O10H'), (100, '1.876(5)'))
        self.assertEqual(c[0][1:4], ('Al1', 'O10H', 1.876))          # an UPPERCASE suffix is part of the label

    def test_symmetry_code_is_not_another_site(self):
        c = self.cells((40, 'M1–O1vi'), (100, '2.101(3)'))
        self.assertEqual(c[0][1:3], ('M1', 'O1'))                    # 'vi' names an image, not a site

    def test_multiplier_after_the_distance(self):
        c = self.cells((40, 'X'), (60, '–O(2)'), (100, '2.503(4)'), (130, '×'), (140, '3'))
        self.assertEqual(c[0][5], 3)

    def test_multiplier_between_the_anion_and_the_distance(self):
        c = self.cells((40, 'X'), (60, '−O(2)'), (90, '×'), (100, '3'), (120, '2.474(3)'))
        self.assertEqual(c[0][1:6], ('X', 'O2', 2.474, 3, 3))

    def test_multiplication_sign_that_reaches_the_text_as_a_three(self):
        # several corpus journals set '×' in a font whose glyph arrives as '3' ('0.10 3 0.01 mm')
        c = self.cells((40, 'Si–O6'), (90, '3'), (100, '2'), (120, '1.630(5)'))
        self.assertEqual(c[0][1:6], ('Si', 'O6', 1.630, 5, 2))

    def test_a_mean_row_is_not_a_bond(self):
        self.assertEqual(self.cells((40, 'mean'), (100, '2.671')), [])
        self.assertEqual(self.cells((40, '<Al1–O>'), (100, '1.904')), [])

    def test_a_number_with_no_bond_before_it_is_not_a_bond(self):
        self.assertEqual(self.cells((40, 'a'), (50, '='), (60, '8.0774(10)')), [])
        self.assertEqual(self.cells((40, 'V'), (50, '='), (60, '4.6743(9)')), [])

    def test_distances_outside_the_range_of_a_bond(self):
        self.assertEqual(self.cells((40, 'Pb1–S7'), (100, '0.814(14)')), [])
        self.assertEqual(self.cells((40, 'Pb1–S7'), (100, '5.814(14)')), [])


class ReadTables(unittest.TestCase):
    """Columns, the cation carried down them, and the two ways a page holds two substances."""

    def three_column_page(self):
        # 'Pb1 – S7 2.814' with two more columns beside it, then continuation rows
        return page(
            line(100, (40, 'Pb1'), (60, '–'), (70, 'S7'), (100, '2.814(14)'),
                      (140, 'Pb2'), (160, '–'), (170, 'S17'), (200, '2.911(13)'),
                      (240, 'Pb3'), (260, '–'), (270, 'S5'), (300, '2.902(16)')),
            line(112, (60, '–'), (70, 'S15'), (100, '2.964(10)'),
                      (160, '–'), (170, 'S5'), (200, '2.980(16)'),
                      (260, '–'), (270, 'S19'), (300, '2.908(14)')),
            line(124, (60, '–'), (70, 'S2'), (100, '3.010(16)'),
                      (160, '–'), (170, 'S19'), (200, '2.995(14)'),
                      (260, '–'), (270, 'S15'), (300, '2.912(10)')))

    def test_the_cation_carries_down_its_own_column(self):
        t = PB.read_tables(None, [self.three_column_page()])
        self.assertEqual(len(t), 1)
        got = {}
        for b in t[0]['bonds']:
            got.setdefault(b.cation, []).append(b.anion)
        self.assertEqual(got, {'Pb1': ['S7', 'S15', 'S2'], 'Pb2': ['S17', 'S5', 'S19'],
                               'Pb3': ['S5', 'S19', 'S15']})

    def test_rows_come_back_column_major(self):
        # the order `candidates` needs: a column read to its end before the next is begun
        t = PB.read_tables(None, [self.three_column_page()])
        self.assertEqual([b.cation for b in t[0]['bonds']][:4], ['Pb1', 'Pb1', 'Pb1', 'Pb2'])

    def test_two_substances_side_by_side_become_two_tables(self):
        # 'Rasmussenite | Ca-glycinate trihydrate': the same site label in two columns
        pg = page(
            line(100, (40, 'Ca'), (60, '–O4'), (100, '2.370(5)'), (150, 'Ca'), (170, '–O4'), (200, '2.361(5)')),
            line(112, (60, '–O1'), (100, '2.389(5)'), (170, '–O1'), (200, '2.359(5)')),
            line(124, (60, '–O6'), (100, '2.405(5)'), (170, '–N2'), (200, '2.436(5)')),
            line(136, (60, '–O5'), (100, '2.435(6)'), (170, '–N1'), (200, '2.410(6)')))
        cands = PB.candidates(PB.read_tables(None, [pg]))
        self.assertEqual(len(cands), 2)
        self.assertEqual([b.anion for b in cands[0]], ['O4', 'O1', 'O6', 'O5'])
        self.assertEqual([b.anion for b in cands[1]], ['O4', 'O1', 'N2', 'N1'])

    def test_two_substances_stacked_become_two_tables(self):
        """A two-mineral paper prints the same table twice down the page: a cation that comes back
        after another has intervened opens the second table."""
        rows = []; y = 100
        for _mineral in range(2):
            for cat, bonds in (('P1', (('O1', '1.545(3)'), ('O2', '1.566(3)'), ('O3', '1.529(3)'), ('O4', '1.520(3)'))),
                               ('P2', (('O5', '1.531(4)'), ('O6', '1.550(4)'), ('O7', '1.525(3)')))):
                for i, (an, d) in enumerate(bonds):
                    head = ((40, cat), (60, '–'), (70, an), (100, d))
                    rows.append(line(y, *(head if i == 0 else ((60, '–'), (70, an), (100, d)))))
                    y += 12
        cands = PB.candidates(PB.read_tables(None, [page(*rows)]))
        self.assertEqual(len(cands), 2)
        for c in cands:
            self.assertEqual(sorted({b.cation for b in c}), ['P1', 'P2'])
            self.assertEqual(len(c), 7)

    def test_a_table_continued_on_the_next_page_is_one_table(self):
        p1 = page(line(100, (40, 'Pb1'), (60, '–'), (70, 'S1'), (100, '2.901(4)')),
                  line(112, (60, '–'), (70, 'S2'), (100, '2.912(4)')),
                  line(124, (60, '–'), (70, 'S3'), (100, '2.923(4)')),
                  line(136, (60, '–'), (70, 'S4'), (100, '2.934(4)')))
        p2 = page(line(100, (40, 'As2'), (60, '–'), (70, 'S5'), (100, '2.213(4)')),
                  line(112, (60, '–'), (70, 'S6'), (100, '2.244(4)')),
                  line(124, (60, '–'), (70, 'S7'), (100, '2.371(4)')),
                  line(136, (60, '–'), (70, 'S8'), (100, '2.397(4)')))
        cands = PB.candidates(PB.read_tables(None, [p1, p2]))
        self.assertEqual(len(cands), 1)
        self.assertEqual(sorted({b.cation for b in cands[0]}), ['As2', 'Pb1'])

    def test_prose_is_not_a_table(self):
        pg = page(line(100, (40, 'The'), (60, 'O–H'), (90, 'distance'), (140, 'is'), (160, '0.98(2)')),
                  line(112, (40, 'and'), (60, 'the'), (90, 'H···A'), (140, 'one'), (160, '1.80(4)')))
        self.assertEqual(PB.read_tables(None, [pg]), [])          # fewer than MIN_ROWS bond cells


class Elements(unittest.TestCase):
    """Which element sits on a site — the label, the occupancy column, or nothing."""

    def test_a_label_that_names_an_element(self):
        self.assertEqual(PB.element_of('Pb1'), 'Pb')
        self.assertEqual(PB.element_of('O10H'), 'O')
        self.assertEqual(PB.element_of('Si3'), 'Si')

    def test_a_site_name_needs_the_occupancy_column(self):
        self.assertIsNone(PB.element_of('M1'))
        self.assertEqual(PB.element_of('M1', {'M1': 'Mg'}), 'Mg')
        self.assertIsNone(PB.element_of('T(1)'))

    def test_yttrium_and_tungsten_are_settled_by_the_analysis(self):
        # a tourmaline's Y site is not yttrium, and a W site is usually water
        self.assertIsNone(PB.element_of('Y', known={'Na', 'Fe', 'Al', 'Si', 'B', 'O'}))
        self.assertEqual(PB.element_of('Y', known={'Y', 'O', 'Si'}), 'Y')
        self.assertEqual(PB.element_of('Y', {'Y': 'Fe'}, known={'Na', 'Fe', 'Al'}), 'Fe')
        self.assertEqual(PB.element_of('Y'), 'Y')               # nothing known: the label is all there is

    def test_the_occupancy_column_must_carry_an_occupancy(self):
        rows = [('M1', 0, 0, 0, 'Ca0.674(11)Mn0.326(11)'),
                ('M2', 0, 0, 0, '0.0142(8) 1.00'),
                ('O6', 0, 0, 0, 'Bragg'),                       # a word out of the prose beside the table
                ('O7', 0, 0, 0, '0.0191 parameters')]
        got = PB.site_elements(rows)
        self.assertEqual(got, {'M1': 'Ca'})                     # the dominant one, and nothing else


class Compute(unittest.TestCase):
    """The valences the printed distances give, and the gate on them."""

    def rows(self, *triples):
        return [PB.Row(c, a, d, None, n, 1, i, 0) for i, (c, a, d, n) in enumerate(triples)]

    def test_a_silicate_tetrahedron_sums_to_four(self):
        st = PB.BondStructure(self.rows(('Si1', 'O1', 1.614, 1), ('Si1', 'O2', 1.620, 1),
                                        ('Si1', 'O3', 1.630, 1), ('Si1', 'O4', 1.635, 1)))
        res, _an, _cells = PB.compute(st, B.Params(prefer='gh'))
        self.assertEqual(len(res), 1)
        self.assertAlmostEqual(res[0][2], 4.0, delta=0.1)
        self.assertEqual(res[0][3], 4)
        self.assertLess(PB.gii(res), PB.GII_GATE)

    def test_a_multiplier_counts_the_bond_that_many_times(self):
        one = PB.BondStructure(self.rows(('B1', 'O1', 1.373, 1)))
        two = PB.BondStructure(self.rows(('B1', 'O1', 1.373, 2)))
        r1, _a, _c = PB.compute(one, B.Params(prefer='gh'))
        r2, _a, _c = PB.compute(two, B.Params(prefer='gh'))
        self.assertAlmostEqual(r2[0][2], 2 * r1[0][2], places=6)

    def test_the_two_images_of_one_distance_are_one_bond_of_count_two(self):
        # a paper lists them on their own lines as often as it writes 'x2'; the table it is checked
        # against prints one cell either way
        split = PB.BondStructure(self.rows(('B1', 'O1', 1.373, 1), ('B1', 'O1', 1.373, 1)))
        marked = PB.BondStructure(self.rows(('B1', 'O1', 1.373, 2)))
        rs, _a, cs = PB.compute(split, B.Params(prefer='gh'))
        rm, _a, cm = PB.compute(marked, B.Params(prefer='gh'))
        self.assertAlmostEqual(rs[0][2], rm[0][2], places=6)
        self.assertEqual(len(cs[('O1', 'B1')]), 1)             # one cell, not two
        self.assertEqual(cs[('O1', 'B1')][0][1], 2)
        self.assertNotEqual(PB._merged(self.rows(('B1', 'O1', 1.373, 1), ('B1', 'O2', 1.373, 1))), [])

    def test_bonds_at_different_distances_stay_apart(self):
        rows = self.rows(('B1', 'O1', 1.373, 1), ('B1', 'O1', 1.392, 1))
        self.assertEqual(len(PB._merged(rows)), 2)

    def test_a_site_nothing_can_name_is_left_out(self):
        st = PB.BondStructure(self.rows(('X', 'O1', 2.503, 3), ('B', 'O2', 1.373, 3)))
        self.assertEqual([c.label for c in st.cations], ['B'])

    def test_the_gate_rejects_a_reading_whose_sums_do_not_come_out(self):
        # the same tetrahedron with one distance misread by half an angstrom
        st = PB.BondStructure(self.rows(('Si1', 'O1', 1.614, 1), ('Si1', 'O2', 1.620, 1),
                                        ('Si1', 'O3', 1.630, 1), ('Si1', 'O4', 2.135, 1)))
        res, _an, _cells = PB.compute(st, B.Params(prefer='gh'))
        self.assertGreater(PB.gii(res), PB.GII_GATE)

    def test_anion_sums_are_not_offered(self):
        st = PB.BondStructure(self.rows(('Si1', 'O1', 1.614, 1), ('Si1', 'O2', 1.620, 1),
                                        ('Si1', 'O3', 1.630, 1), ('Si1', 'O4', 1.635, 1)))
        _res, anion_sum, _cells = PB.compute(st, B.Params(prefer='gh'))
        self.assertEqual(anion_sum, {})                        # no multiplicities, so no anion sum

    def test_a_sulfide_takes_the_sulfide_valences(self):
        st = PB.BondStructure(self.rows(('Pb1', 'S1', 2.814, 1), ('Pb1', 'S2', 2.964, 1),
                                        ('Pb1', 'S3', 3.010, 1), ('Pb1', 'S4', 3.066, 1),
                                        ('Pb1', 'S5', 3.160, 1), ('Pb1', 'S6', 3.260, 1),
                                        ('Pb1', 'S7', 3.262, 1), ('Pb1', 'S8', 3.294, 1)))
        res, _a, _c = PB.compute(st, B.Params(prefer='bo'))
        self.assertEqual(res[0][3], 2)                         # Pb2+, not the oxide default
        self.assertAlmostEqual(res[0][2], 2.0, delta=0.25)

    def test_the_paper_s_own_charge_wins(self):
        rows = self.rows(('Fe1', 'O1', 2.00, 6))
        plain = PB.BondStructure(rows)
        stated = PB.BondStructure(rows, charges={'Fe': 2})
        self.assertEqual(plain.cations[0].species[0].ox, B.DEFAULT_OX['Fe'])
        self.assertEqual(stated.cations[0].species[0].ox, 2)


if __name__ == '__main__':
    unittest.main()


class Layouts(unittest.TestCase):
    """The typesetting the corpus turned up once the dashed forms above were already read."""

    def test_multiplier_welded_onto_the_anion_label(self):
        c = PB._cells(line(100, (40, 'Sn-O4(×3)'), (100, '1.998(2)')))
        self.assertEqual(c[0][1:6], ('Sn', 'O4', 1.998, 2, 3))

    def test_multiplier_in_brackets_as_its_own_token(self):
        c = PB._cells(line(100, (40, 'A'), (60, '–O6B'), (90, '(×2)'), (120, '2.645(5)')))
        self.assertEqual(c[0][1:6], ('A', 'O6B', 2.645, 5, 2))

    def test_multiplier_in_brackets_after_the_distance(self):
        c = PB._cells(line(100, (40, 'Ca4'), (60, '–OW19'), (100, '2.18(2)'), (130, '(×2)')))
        self.assertEqual(c[0][5], 2)

    def test_a_bracketed_multiplier_of_the_next_column_is_not_this_cell_s(self):
        c = PB._cells(line(100, (40, 'S2–O8'), (100, '1.469(9)'), (130, 'OW9…O10'), (180, '(×2)'), (210, '3.174(14)')))
        self.assertEqual(c[0][5], 1)                                 # the (×2) belongs to the hydrogen-bond column

    def test_welded_multiplication_sign_before_the_distance(self):
        ws = line(100, (40, 'Cr1–O2'), (90, '33'), (120, '1.677(10)'))
        c = PB._cells(ws, mangled=True)
        self.assertEqual(c[0][1:6], ('Cr1', 'O2', 1.677, 10, 3))       # '33' is '×3' in the font that loses its symbols
        self.assertEqual(PB._cells(ws), [])                             # on an ordinary page '33' is a column of its own: no cell, as `_mult_after` leaves the number

    def test_welded_multiplication_sign_after_the_distance_only_on_such_a_page(self):
        ws = line(100, (40, 'Mn'), (60, '(X)'), (80, 'O1'), (110, '2.196(3)'), (140, '32'))
        self.assertEqual(PB._cells(ws, True, False)[0][5], 1)         # an ordinary page: '32' is the next column
        self.assertEqual(PB._cells(ws, True, True)[0][5], 2)          # the mangled font: it is '×2'

    def test_no_dash_at_all_needs_the_relaxed_pass(self):
        ws = line(100, (40, 'Mn'), (60, '(X)'), (80, 'O1'), (110, '2.196(3)'))
        self.assertEqual(PB._cells(ws), [])                           # strict: a cell of some other table
        self.assertEqual(PB._cells(ws, relaxed=True)[0][1:4], ('Mn', 'O1', 2.196))

    def test_a_dashless_cell_needs_an_anion_and_an_esd(self):
        self.assertEqual(PB._cells(line(100, (40, 'CaO'), (80, '3.03')), relaxed=True), [])
        self.assertEqual(PB._cells(line(100, (40, 'CaO'), (80, '3.03(2)')), relaxed=True), [])   # Ca is no anion
        self.assertEqual(PB._cells(line(100, (40, 'O3'), (80, '1.876')), relaxed=True), [])      # no esd

    def test_a_dashless_water_label_is_an_anion(self):
        c = PB._cells(line(100, (40, 'Al'), (70, 'W2'), (100, '1.875(7)')), relaxed=True)
        self.assertEqual(c[0][1:4], ('Al', 'W2', 1.875))

    def test_water_resolves_to_oxygen_unless_the_analysis_names_tungsten(self):
        self.assertEqual(PB.element_of('W2', {}, {'Al', 'S', 'O'}), 'O')
        self.assertEqual(PB.element_of('W2', {}, {'W', 'O'}), 'W')

    def test_the_dash_typeset_onto_the_cation_with_its_label_split(self):
        c = PB._cells(line(100, (40, 'T'), (50, '1A–'), (80, 'O1A'), (110, '1.630(2)')), relaxed=True)
        self.assertEqual(c[0][1:4], ('T1A', 'O1A', 1.63))

    def test_a_bond_caption_admits_the_page_to_the_relaxed_pass(self):
        self.assertTrue(PB._bond_caption(page(line(50, (40, 'TABLE'), (70, '5.'), (90, 'SELECTED'),
                                                   (140, 'INTERATOMIC'), (200, 'DISTANCES')))))
        self.assertFalse(PB._bond_caption(page(line(50, (40, 'Table'), (70, '1.'), (90, 'Chemical'), (140, 'data')))))

    def test_the_mangled_font_is_recognised_by_its_other_substitutions(self):
        self.assertTrue(PB._mangled(page(line(50, (40, 'R1'), (60, '¼'), (80, '3.96%')),
                                         line(60, (40, 'Mn2þ')))))
        self.assertFalse(PB._mangled(page(line(50, (40, 'R1'), (60, '='), (80, '3.96%')))))


class SitePopulations(unittest.TestCase):
    """'M1', 'T2', 'A' name no element; the paper's own assignment does."""

    def test_the_share_that_wins(self):
        t = '*M1 = 0.37Mn + 0.27Mg + 0.35Fe + 0.03Zn, M2 = 0.59Fe + 0.41Al; M3 = 0.42Fe + 0.58Al.'
        self.assertEqual(PB.sites_from_text(t, {'M1', 'M2', 'M3'}), {'M1': 'Mn', 'M2': 'Fe', 'M3': 'Al'})

    def test_an_assignment_with_no_shares_takes_the_first_element(self):
        t = 'T1 = (CrO4)2–/(SeO4)2–/(SO4)2–; T2 = (SO4)2–'
        self.assertEqual(PB.sites_from_text(t, {'T1', 'T2'}), {'T1': 'Cr', 'T2': 'S'})

    def test_prose_alone_says_nothing_without_an_assignment(self):
        self.assertEqual(PB.sites_from_text('The M1 site is octahedral and rather regular.', {'M1'}), {})

    def test_the_sentence_that_names_the_occupant(self):
        t = 'The M2 site was found to be fully occupied by Cd, whereas M1 exhibited less.'
        self.assertEqual(PB.sites_from_text(t, {'M2'}), {'M2': 'Cd'})

    def test_an_inferred_site_is_kept_out_of_the_instability_index(self):
        rows = [PB.Row('Si1', 'O1', 1.62, 1, 1, 1, 0, 0), PB.Row('M1', 'O1', 2.10, 1, 1, 1, 1, 0)]
        st = PB.BondStructure(rows, {'M1': 'Fe'}, {'Si': 4, 'Fe': 2}, None, '', {'M1'})
        res, _an, _c = PB.compute(st, B.Params(prefer='gh'))
        self.assertIsNotNone(PB.gii(res))
        self.assertNotEqual(PB.gii(res), PB.gii(res, st.inferred))


class ColumnHeads(unittest.TestCase):
    """The cation named once over its column instead of on each row."""

    def test_a_column_headed_by_its_cation(self):
        tabs = PB.read_tables('x.pdf', pages=[page(
            line(50, (40, 'Pb1'), (140, 'Pb2')),
            line(62, (40, '–O4'), (80, '2.27(1)'), (140, '–O5'), (180, '2.38(1)')),
            line(74, (40, '–O2'), (80, '2.37(1)'), (140, '–O4'), (180, '2.529(9)')),
            line(86, (40, '–O1'), (80, '2.39(1)'), (140, '–O2'), (180, '2.53(1)')))])
        got = {(r.cation, r.anion) for r in tabs[0]['bonds']}
        self.assertEqual(got, {('Pb1', 'O4'), ('Pb1', 'O2'), ('Pb1', 'O1'),
                               ('Pb2', 'O5'), ('Pb2', 'O4'), ('Pb2', 'O2')})

    def test_a_column_that_names_its_own_cation_ignores_the_line_above(self):
        tabs = PB.read_tables('x.pdf', pages=[page(
            line(50, (40, 'Zz9')),
            line(62, (40, 'Si1–O1'), (110, '1.62(1)')),
            line(74, (40, '–O2'), (110, '1.63(1)')),
            line(86, (40, '–O3'), (110, '1.61(1)')),
            line(98, (40, '–O4'), (110, '1.60(1)')))])
        self.assertEqual({r.cation for r in tabs[0]['bonds']}, {'Si1'})


class SplitSiteLabels(unittest.TestCase):
    """'M(2a)' and 'M(2b)' are the two halves of a split site — the letter is inside the brackets
    and belongs to the label, unlike the symmetry code outside them."""

    def test_a_letter_inside_the_brackets_is_part_of_the_label(self):
        self.assertEqual(PB._label('M(2a)')[0], 'M2a')
        self.assertEqual(PB._pair_token('M(2a)–S(2)'), ('M2a', 'S2'))

    def test_a_letter_outside_them_is_still_a_symmetry_code(self):
        self.assertEqual(PB._label('O1vi')[0], 'O1')
        self.assertEqual(PB._pair_token('M1–O1vi'), ('M1', 'O1'))

    def test_both_halves_come_back_normalised(self):
        self.assertEqual(PB._pair_token('M(1)–S(1)'), ('M1', 'S1'))     # so a continuation row's '–S(1)' names the same site

    def test_the_split_site_reads_as_a_bond(self):
        c = PB._cells(line(100, (40, 'M(2a)–S(2)'), (110, '2.2145(11)')))
        self.assertEqual(c[0][1:4], ('M2a', 'S2', 2.2145))


class MixedSites(unittest.TestCase):
    """A site the coordinates table populates with two species ('Na0.62Ca0.38') computes as the
    share-weighted sum over both — which is what a paper prints in that column of its table."""

    def test_species_from_the_row_and_the_weighted_cell(self):
        from pxrd_review import paper_structure as PS, bv_check as B
        self.assertEqual(PS.occupancy_species('Na0.62(1)Ca0.38 0.010(1)'), [('Na', 0.62), ('Ca', 0.38)])
        self.assertEqual(PS.occupancy_species('As0.70 0.0123(4)'), [('As', 0.7)])
        self.assertEqual(PS.occupancy_species('0.0197(4)'), [])
        rows = [PB.Row("A1", "O1", 2.40, 1, 1, 1, 0, 0), PB.Row("A1", "O2", 2.45, 1, 1, 1, 1, 0)]
        P = B.Params(prefer='gh', u6='burns')
        plain = PB.BondStructure(rows, {'A1': 'Na'}, {}, None, 't')
        mixed = PB.BondStructure(rows, {'A1': 'Na'}, {}, None, 't', occ={'A1': [('Na', 0.62), ('Ca', 0.38)]})
        cp = PB.compute(plain, P)[2][('O1', 'A1')][0][0]; cm = PB.compute(mixed, P)[2][('O1', 'A1')][0][0]
        sna = P.valence('Na', 1, 'O', -2, 2.40); sca = P.valence('Ca', 2, 'O', -2, 2.40)
        self.assertAlmostEqual(cp, sna, places=4)
        self.assertAlmostEqual(cm, 0.62 * sna + 0.38 * sca, places=4)
        res = PB.compute(mixed, P)[0]
        self.assertAlmostEqual(res[0][3], 0.62 * 1 + 0.38 * 2, places=6)                     # the formal valence, share-weighted
        self.assertEqual(mixed.cations[0].species[0].element, 'Na')


class SiteNames(unittest.TestCase):
    def test_the_site_name_beside_the_element_travels_with_the_row(self):
        c = PB._cells(line(100, (40, 'Mn'), (55, '(X)'), (80, 'O1'), (100, '2.196(3)')), relaxed=True)
        self.assertEqual(c[0][1:7], ('Mn', 'O1', 2.196, 3, 1, 'X'))
        c = PB._cells(line(100, (40, 'Pb1'), (60, '–'), (70, 'S7'), (100, '2.814(14)')))
        self.assertEqual(c[0][6], None)
        self.assertEqual(PB.Row('Mn', 'O1', 2.196, 3, 1, 1, 0, 0).site, None)
