"""The space-group operator table: the symbols it resolves, the group property every entry must
have, and bv_check standing a .cif up without an operator loop.

    python3 -m unittest tests.test_symops -v"""
import os, shutil, tempfile, unittest

from pxrd_review import symops as SO
from pxrd_review import bv_check as B

CIF_NO_OPS = """data_test
_chemical_name_mineral 'testite'
_space_group_name_H-M_alt 'P 21/c'
_cell_length_a 5.0000
_cell_length_b 8.0000
_cell_length_c 7.0000
_cell_angle_alpha 90
_cell_angle_beta 100
_cell_angle_gamma 90
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Si1 Si 0.1000 0.2000 0.3000
O1  O   0.2500 0.3000 0.4000
O2  O   0.0500 0.1000 0.1500
O3  O   0.3500 0.0500 0.2000
O4  O   0.1500 0.4000 0.1000
"""


def _canon(ops):
    return {(tuple(tuple(int(round(v)) for v in r) for r in rot), tuple(int(round(t * 12)) % 12 for t in tr))
            for rot, tr in ops}


class Table(unittest.TestCase):
    def test_loads(self):
        self.assertTrue(SO.available())
        self.assertGreaterEqual(len(SO._table()[0]), 40)

    def test_normalise(self):
        self.assertEqual(SO.normalize(' P 2₁/c '), 'P21/C')          # a subscript is a digit
        self.assertEqual(SO.normalize('R-3m (hexagonal axes)'), 'R-3M')   # a setting note is not part of the symbol
        self.assertEqual(SO.normalize('P̄1'), 'P-1')            # a combining overbar folds to '-'
        self.assertEqual(SO.normalize('R̅3m'), 'R-3M')          # and the overline form too

    def test_symbol_forms_resolve_alike(self):
        for s in ('P21/c', 'P 21/c', 'P 2₁/c', 'P1 21/c 1'):
            self.assertTrue(SO.lookup(s), s)
        self.assertEqual(len(SO.lookup('P21/c')[0]), 4)                   # P21/c is order 4
        self.assertEqual(len(SO.lookup('P-1')[0]), 2)
        self.assertEqual(SO.lookup('Nonsense42'), [])

    def test_every_entry_is_a_group(self):
        """Closure, identity and inverses — the property that needs no outside reference."""
        groups, frac = SO._table()
        for sym in groups:
            ops = _canon(SO.lookup(sym)[0])
            self.assertIn((((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0, 0, 0)), ops, '%s has no identity' % sym)
            for (ra, ta) in ops:
                for (rb, tb) in ops:
                    rot = tuple(tuple(sum(rb[i][k] * ra[k][j] for k in range(3)) for j in range(3)) for i in range(3))
                    tr = tuple(int(round(sum(rb[i][k] * ta[k] for k in range(3)) + tb[i])) % 12 for i in range(3))
                    self.assertIn((rot, tr), ops, '%s is not closed' % sym)

    def test_find_in_text(self):
        sym, phrase = SO.find_in_text('The structure was refined in space group P21/c with a = 5.00 Angstrom.')
        self.assertEqual(sym, 'P21/C')
        self.assertIn('space group', phrase)
        # 'space group and the cell …' must not yield the symbol 'And'
        sym2, _ = SO.find_in_text('The space group and the cell were determined from precession images.')
        self.assertIsNone(sym2)
        self.assertIsNone(SO.find_in_text('In the space group, an inversion twin was implemented in the refinement.')[0])   # 'an' is a word, not the setting An
        self.assertEqual(SO.find_in_text('space group Cc, a = 5.1')[0], 'CC')
        self.assertEqual(SO.find_in_text('space group P\x021, with a = 5.4262(11)')[0], 'P-1')        # the overbar as the font's control code
        self.assertEqual(SO.find_in_text('space group Trigonal, R\x013 Temperature (K) 293')[0], 'R-3')

    def test_a_two_letter_symbol_that_is_a_word_needs_the_space_group_phrase(self):
        # 'An average of 22 analyses' after 'symmetry.' had read the setting An; so had 'Am', 'Pa', 'Cm'
        # at a sentence start. A two-letter symbol is taken right after an explicit 'space group'
        # phrase only, with no sentence end between (audit 2026-09-16)
        self.assertIsNone(SO.find_in_text('symmetry. An average of 22 analyses gave Na2O 3.65 wt.%')[0])
        self.assertIsNone(SO.find_in_text('symmetry and crystal morphology. An average of 15 analyses')[0])
        self.assertIsNone(SO.find_in_text('space group. An average of 22 analyses')[0])
        self.assertIsNone(SO.find_in_text('symmetry of the Pb atoms')[0])
        self.assertEqual(SO.find_in_text('space group Cc, a = 5.1')[0], 'CC')                          # the real thing
        self.assertEqual(SO.find_in_text('monoclinic space group Im (a nonstandard setting of Cm)')[0], 'IM')
        self.assertEqual(SO.find_in_text('Space group: Cm Unit cell a = 5.1')[0], 'CM')
        self.assertEqual(SO.find_in_text('sp. gr. Pa, Z = 4')[0], 'PA')
        self.assertEqual(SO.find_in_text('symmetry. P21/c, a = 5.1')[0], 'P21/C')                        # a symbol with a digit is no word
        self.assertNotIn('AN', SO.find_all_in_text('space group P212121 (No. 19), with a = 6.4690(13). The symmetry. An average of 22 analyses.'))

    def test_the_abstracts_own_statement(self):
        # the first symbol statement of the text, naming the mineral (or 'the mineral is') with its cell
        t = ('Xenophyllite is triclinic, P1 or P-1, a 9.643(6), b 9.633(5), c 17.645(11) Å, Z = 3. ' * 1 +
             'The unit-cell parameters of sarcopside (space group P21/c) are: a 10.554(9), b 4.748(5) Å.')
        self.assertEqual(SO.find_own_in_text(t, 'xenophyllite')[0], 'P1')
        self.assertEqual(SO.find_in_text(t)[0], 'P21/C')                                    # the first explicit phrase is the relative's
        t2 = 'The mineral is trigonal, R3m, with a = 10.7527(7) Å, c = 27.4002(18) Å. The symmetry should be lowered to monoclinic space group Im.'
        self.assertEqual(SO.find_own_in_text(t2, 'proshchenkoite-(y)')[0], 'R3M')
        # not the abstract's: no mineral named, no cell stated, or not the first symbol statement
        self.assertIsNone(SO.find_own_in_text('The minerals are trigonal, R3m, with similar layered structures. Plavnoite is monoclinic, C2/c, a = 8.6254(16) Å.', 'plavnoite')[0])
        self.assertIsNone(SO.find_own_in_text('Guettardite differs from sartorite (space group P1) in its Sb content. It is monoclinic, P21/c, a = 8.5 Å.', 'guettardite')[0])
        self.assertIsNone(SO.find_own_in_text('Sejkoraite-(Y) is triclinic (space group P-1) with the ideal formula Y3[(UO2)8O7OH(SO4)4](OH)2(H2O)24.', 'plavnoite')[0])
        self.assertIsNone(SO.find_own_in_text('', 'plavnoite')[0])

    def test_cell_system_is_the_downward_closure_of_the_metric(self):
        # the metric bounds the symmetry from above: a cell at 90° may belong to a monoclinic or a
        # triclinic crystal (pseudo-orthorhombic, or the angles lost by the text layer and defaulted)
        self.assertEqual(SO.cell_system({'a': 10.1, 'b': 5.2, 'c': 7.3, 'α': 90, 'β': 90, 'γ': 90}), {'orthorhombic', 'monoclinic', 'triclinic'})
        self.assertEqual(SO.cell_system({'a': 6.8, 'b': 6.8, 'c': 18.6, 'α': 90, 'β': 90, 'γ': 90}), {'tetragonal', 'orthorhombic', 'monoclinic', 'triclinic'})
        self.assertEqual(SO.cell_system({'a': 5.4, 'b': 5.4, 'c': 5.4, 'α': 90, 'β': 90, 'γ': 90}), {'cubic', 'tetragonal', 'orthorhombic', 'monoclinic', 'triclinic'})
        self.assertEqual(SO.cell_system({'a': 11.9, 'b': 12.7, 'c': 6.7, 'α': 90, 'β': 113.3, 'γ': 90}), {'monoclinic', 'triclinic'})
        self.assertEqual(SO.cell_system({'a': 23.7, 'b': 8.4, 'c': 23.5, 'α': 89.9, 'β': 102.9, 'γ': 89.8}), {'triclinic'})
        # the hexagonal and rhombohedral metrics are printed by their own systems only
        self.assertEqual(SO.cell_system({'a': 15.7, 'b': 15.7, 'c': 47.8, 'α': 90, 'β': 90, 'γ': 120}), {'trigonal', 'hexagonal'})
        self.assertEqual(SO.cell_system({'a': 5.4, 'b': 5.4, 'c': 5.4, 'α': 55.3, 'β': 55.3, 'γ': 55.3}), {'trigonal'})
        # a cell missing an angle allows every system
        self.assertEqual(SO.cell_system({'a': 10.1, 'b': 5.2, 'c': 7.3}), set(SO.ALL_SYSTEMS))
        # the triclinic symbol a paper prints with a cell whose angles the text lost is allowed
        self.assertIn(SO.crystal_system('P-1'), SO.cell_system({'a': 19.04, 'b': 8.23, 'c': 17.33, 'α': 90.0, 'β': 90.0, 'γ': 90.0}))
        self.assertEqual(SO.normalize('P\x021'), 'P-1')


class Fallback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='symops_')
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_structure_without_an_operator_loop(self):
        """A .cif with no _space_group_symop_operation_xyz used to be refused outright."""
        p = os.path.join(self.tmp, 'noops.cif')
        with open(p, 'w', encoding='utf-8') as f:
            f.write(CIF_NO_OPS)
        st = B.Structure(p)
        self.assertEqual(st.n_ops, 4)
        self.assertTrue(st.cations and st.anions)

    def test_unknown_symbol_still_refused(self):
        p = os.path.join(self.tmp, 'weird.cif')
        with open(p, 'w', encoding='utf-8') as f:
            f.write(CIF_NO_OPS.replace("'P 21/c'", "'Z 99/q'"))
        with self.assertRaises(ValueError):
            B.Structure(p)


if __name__ == '__main__':
    unittest.main()


class SystematicAbsences(unittest.TestCase):
    """`absent` derives the reflection conditions from the operators themselves (2026-09-16)."""

    def test_textbook_conditions(self):
        from pxrd_review import symops as SO
        cases = [('C2/c', (1, 0, 0), True), ('C2/c', (1, 1, 0), False), ('C2/c', (0, 0, 1), True), ('C2/c', (0, 0, 2), False),
                 ('P21/c', (1, 0, 1), True), ('P21/c', (1, 0, 2), False), ('P21/c', (0, 1, 0), True), ('P21/c', (0, 2, 0), False), ('P21/c', (1, 1, 1), False),
                 ('Fd-3m', (1, 0, 0), True), ('Fd-3m', (1, 1, 1), False), ('Fd-3m', (2, 0, 0), True), ('Fd-3m', (2, 2, 0), False),
                 ('Pnma', (1, 0, 0), True), ('Pnma', (2, 0, 0), False), ('Pnma', (0, 1, 0), True), ('Pnma', (0, 1, 1), False), ('Pnma', (1, 0, 1), False),
                 ('P1', (1, 2, 3), False), ('I4/m', (1, 0, 0), True), ('I4/m', (1, 1, 0), False), ('R-3m', (1, 0, 0), True), ('R-3m', (1, 0, 1), False)]
        for sym, hkl, expect in cases:
            self.assertEqual(SO.absent(SO.lookup(sym)[0], hkl), expect, (sym, hkl))
        self.assertEqual(SO.absences('C2/c', [(1, 0, 0), (1, 1, 0), (0, 0, 3), (2, 0, 0)]), [(1, 0, 0), (0, 0, 3)])
        self.assertEqual(SO.absences('Xyz', [(1, 0, 0)]), [])


class SettingVariants(unittest.TestCase):
    """`setting_variants` keeps the operator lists of the setting a symbol NAMES (audit
    2026-09-16 pm): the table keys every setting of a group under one symbol, and a condition
    intersected over all of them forbade nothing in P21/c and only h00/0k0/00l in C2/c."""

    def test_the_setting_the_symbol_names(self):
        from pxrd_review import symops as SO
        self.assertEqual(len(SO.setting_variants('P21/c')), 1); self.assertEqual(len(SO.lookup('P21/c')), 9)
        self.assertEqual(SO.absences('P21/c', [(0, 1, 0), (1, 0, 1), (1, 0, 0), (0, 0, 1), (1, 1, 1)]), [(0, 1, 0), (1, 0, 1), (0, 0, 1)])   # 0k0 k odd, h0l l odd (00l among them)
        self.assertEqual(SO.absences('P21/n', [(1, 0, 1), (1, 0, 2), (0, 1, 0)]), [(1, 0, 2), (0, 1, 0)])
        self.assertEqual(SO.absences('C2/c', [(1, 0, 1), (2, 0, 1), (1, 1, 0), (0, 1, 0), (2, 0, 2)]), [(1, 0, 1), (2, 0, 1), (0, 1, 0)])
        self.assertEqual(SO.absences('I2/a', [(1, 0, 1), (1, 0, 0), (1, 1, 1)]), [(1, 0, 1), (1, 0, 0), (1, 1, 1)])
        self.assertEqual(SO.absences('C2/m', [(1, 0, 0), (2, 1, 0), (1, 1, 0)]), [(1, 0, 0), (2, 1, 0)])
        self.assertEqual(SO.absences('P21', [(0, 1, 0), (0, 2, 0), (1, 0, 0)]), [(0, 1, 0)])
        # 'P21/b' names unique axis a OR c: both readings stay, and only what both forbid is reported
        self.assertEqual(len(SO.setting_variants('P21/b')), 2)
        self.assertEqual(SO.absences('P21/b', [(0, 1, 0), (0, 0, 1), (1, 0, 0)]), [(0, 1, 0)])
        # a symbol with one setting, or one this does not read, is untouched
        self.assertEqual(SO.setting_variants('Pnma'), SO.lookup('Pnma'))
        self.assertEqual(len(SO.setting_variants('Fd-3m')), len(SO.lookup('Fd-3m')))
        self.assertEqual(SO.setting_variants('Xyz'), [])

    def test_the_abstract_names_its_own_symbol_not_a_relatives(self):
        from pxrd_review import symops as SO
        own = SO.find_own_in_text
        self.assertEqual(own("Xenophyllite is triclinic, P1 or P-1, a 9.643(6), b 10.1, c 12.2 Å.", 'Xenophyllite')[0], 'P1')
        self.assertEqual(own("The mineral is trigonal, R3m, with a = 10.7527(7), c = 4.5 Å.", 'Anything')[0], 'R3M')
        self.assertEqual(own("Testite, ideally NaCaPO4, is monoclinic, space group P21/c, a = 5.1, b = 6.2, c = 7.3 Å.", 'Testite')[0], 'P21/C')
        # the mineral named beside a RELATIVE's symbol is not the subject of that symbol
        self.assertIsNone(own("Testite is a member of the alluaudite group, whose members are monoclinic, C2/c, a = 12.0, b = 12.5, c = 6.4 Å. "
                              "Its structure was solved in space group P-1 with a = 9.643(6), b = 10.1, c = 12.2 Å.", 'Testite')[0])
        self.assertIsNone(own("Testite, a new mineral, is related to sarcopside (space group P21/c, a 10.4, b 4.7, c 6.0). "
                              "Testite is triclinic, space group P-1, a 9.643(6), b 10.1, c 12.2.", 'Testite')[0])
        self.assertIsNone(own("The hydroxyl analogue of tobermorite (space group B11m, a 6.7, b 7.4, c 22.7). "
                              "Hydroxylgugiaite is orthorhombic, space group Pnma, a 5.1, b 6.2, c 7.3.", 'Hydroxylgugiaite')[0])
