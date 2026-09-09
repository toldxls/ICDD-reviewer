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
