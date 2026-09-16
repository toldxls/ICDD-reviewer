"""pxrd_review.lattice — reduced cells (Niggli), centred cells made primitive, and whether two
conventional cells are one lattice.

    python3 -m unittest tests.test_lattice -v
"""
import unittest

from pxrd_review import lattice as L


def r3(c):
    return tuple(round(v, 3) for v in c)


class ReducedCells(unittest.TestCase):
    def test_centred_cubic_cells_reduce_to_their_primitive_rhombohedra(self):
        self.assertEqual(r3(L.reduced((5.64, 5.64, 5.64, 90, 90, 90), 'F')), (3.988, 3.988, 3.988, 60.0, 60.0, 60.0))         # NaCl
        self.assertEqual(r3(L.reduced((3.0, 3.0, 3.0, 90, 90, 90), 'I')), (2.598, 2.598, 2.598, 109.471, 109.471, 109.471))   # bcc

    def test_idempotent(self):
        c = L.reduced((10, 5, 7, 90, 110, 90))
        self.assertEqual(r3(L.niggli(*c)), r3(c))


class SameLattice(unittest.TestCase):
    def test_monoclinic_settings(self):
        self.assertTrue(L.same_lattice((10, 5, 7, 90, 110, 90), (7, 5, 10, 90, 110, 90)))           # a and c swapped
        self.assertTrue(L.same_lattice((10, 5, 7, 90, 110, 90), (10, 5, 7, 90, 70, 90)))            # β and its supplement: c reversed, the same lattice
        self.assertFalse(L.same_lattice((9.0, 5.0, 6.0, 90, 100, 90), (9.1, 5.0, 6.0, 90, 100, 90)))
        # C2/c against the I2/a cell of the same lattice: a' = a + c is I-centred in the new basis
        G = L._metric((9.0, 5.0, 6.0, 90, 100, 90))
        cell_i = L._cell_of(L._transform(G, [[1, 0, 1], [0, 1, 0], [0, 0, 1]]))
        self.assertTrue(L.same_lattice((9.0, 5.0, 6.0, 90, 100, 90), cell_i, 'C', 'I'))
        self.assertFalse(L.same_lattice((9.0, 5.0, 6.0, 90, 100, 90), cell_i, 'C', 'C'))

    def test_rhombohedral_against_hexagonal(self):
        self.assertTrue(L.same_lattice((4.99, 4.99, 17.06, 90, 90, 120), (6.375, 6.375, 6.375, 46.08, 46.08, 46.08), 'R', 'P'))   # calcite

    def test_centring_letter(self):
        self.assertEqual([L.centring_of(s) for s in ('C2/c', 'R-3m', 'P21/c', 'Fd-3m', 'I41/a', '')], ['C', 'R', 'P', 'F', 'I', 'P'])
