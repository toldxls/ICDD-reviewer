"""The structure a paper prints, and the contract that whatever it supports is a note.

    python3 -m unittest tests.test_paper_structure -v"""
import os, shutil, tempfile, unittest

from pxrd_review import paper_structure as PS


class Pieces(unittest.TestCase):
    def test_coordinate_values(self):
        self.assertAlmostEqual(PS._val('0.12345(7)'), 0.12345)
        self.assertAlmostEqual(PS._val('-0.0123'), -0.0123)
        self.assertAlmostEqual(PS._val('1/2'), 0.5)
        self.assertAlmostEqual(PS._val('½'), 0.5)          # as papers typeset a special position
        self.assertAlmostEqual(PS._val('¼'), 0.25)
        self.assertIsNone(PS._val('Ueq'))
        # _val parses; the readers enforce the range, and that is what rejects a d spacing or a
        # bond length standing in a neighbouring column
        self.assertGreater(abs(PS._val('12.4')), PS.FRACT_MAX)

    def test_decimals_separate_a_coordinate_from_a_bond_valence(self):
        self.assertEqual(PS._ndec('0.12345'), 5)
        self.assertEqual(PS._ndec('0.199'), 3)             # a bond valence is printed shorter
        self.assertEqual(PS._ndec('0'), 0)

    def test_site_element_comes_from_the_occupancy_column(self):
        # a paper names sites crystallographically and puts the elements in the occupancy column
        self.assertEqual(PS.site_element('A1', 'Ca0.674(11)Mn0.326(11)'), 'Ca')
        self.assertEqual(PS.site_element('A2', 'Y0.303Nd0.469(2)Ca0.228(2)'), 'Nd')   # the dominant one
        self.assertEqual(PS.site_element('T1', 'Si1'), 'Si')
        self.assertEqual(PS.site_element('O3', ''), 'O')                              # else the label
        self.assertIsNone(PS.site_element('Zz9', ''))

    def test_labels(self):
        for good in ('O1', 'Ow1', 'Na1a', 'Si', 'Fe2'):
            self.assertTrue(PS._label_ok(good), good)
        for bad in ('100', 'and', '0.5'):
            self.assertFalse(PS._label_ok(bad), bad)

    def test_gates_are_note_grade(self):
        """0.15 vu is the threshold measured to reproduce 91 % of a .cif's sites — note-grade."""
        self.assertEqual(PS.GII_GATE, 0.15)
        self.assertLessEqual(PS.GII_GATE, 0.25)


class Closure(unittest.TestCase):
    class _Sp:
        def __init__(self, el, occ=1.0):
            self.element = el; self.ox = None; self.occ = occ

    class _Site:
        def __init__(self, el, mult, occ=1.0):
            self.species = [Closure._Sp(el, occ)]; self.mult = mult

    class _St:
        def __init__(self, cations, anions):
            self.cations = cations; self.anions = anions

    def test_a_complete_structure_closes(self):
        st = self._St([self._Site('Si', 4)], [self._Site('O', 8)])
        self.assertLess(PS.closure(st, {'Si': 1.0, 'O': 2.0}), 0.05)

    def test_a_table_read_in_part_does_not(self):
        """Half the oxygens missing: the valences of what was read still come out, the composition
        does not — which is the whole reason this gate exists beside the instability index."""
        st = self._St([self._Site('Si', 4)], [self._Site('O', 4)])
        self.assertGreater(PS.closure(st, {'Si': 1.0, 'O': 2.0}), 0.25)


if __name__ == '__main__':
    unittest.main()
