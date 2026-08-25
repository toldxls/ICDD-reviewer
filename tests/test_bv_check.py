"""Unit tests for pxrd_review.bv_check — bond distances, bond-valence sums, manuscript tables.

    python3 -m unittest tests.test_bv_check -v

Rutile (TiO2, P42/mnm) is the reference structure: Ti–O 1.949 ×4 and 1.980 ×2, and the Ti sum is
known (≈ 4.0 vu with Brese & O'Keeffe 1991). A synthetic manuscript table exercises the checker."""
import os, shutil, tempfile, unittest

from pxrd_review import bv_check as B

RUTILE = """data_rutile
_chemical_name_mineral rutile
_cell_length_a 4.5937
_cell_length_b 4.5937
_cell_length_c 2.9587
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_space_group_name_H-M_alt 'P 42/m n m'
loop_
_space_group_symop_operation_xyz
'x, y, z'
'-x, -y, z'
'-y+1/2, x+1/2, z+1/2'
'y+1/2, -x+1/2, z+1/2'
'-x+1/2, y+1/2, -z+1/2'
'x+1/2, -y+1/2, -z+1/2'
'y, x, -z'
'-y, -x, -z'
'-x, -y, -z'
'x, y, -z'
'y+1/2, -x+1/2, -z+1/2'
'-y+1/2, x+1/2, -z+1/2'
'x+1/2, -y+1/2, z+1/2'
'-x+1/2, y+1/2, z+1/2'
'-y, -x, z'
'y, x, z'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
_atom_site_occupancy
Ti1 Ti4+ 0 0 0 1
O1 O2- 0.30479 0.30479 0 1
loop_
_geom_bond_atom_site_label_1
_geom_bond_atom_site_label_2
_geom_bond_distance
_geom_bond_site_symmetry_2
Ti1 O1 1.9485(5) .
Ti1 O1 1.9800(5) 3_555
"""


def _write(tmp, name, text):
    p = os.path.join(tmp, name)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(text)
    return p


class Symmetry(unittest.TestCase):
    def test_parse_symop(self):
        rot, tr = B.parse_symop('-y+1/2, x-y, z+0.25')
        self.assertEqual(rot, [[0, -1, 0], [1, -1, 0], [0, 0, 1]])
        self.assertEqual(tr, [0.5, 0, 0.25])
        rot, tr = B.parse_symop('x, y, z')
        self.assertEqual(rot, [[1, 0, 0], [0, 1, 0], [0, 0, 1]])
        with self.assertRaises(ValueError):
            B.parse_symop('x, y')
        with self.assertRaises(ValueError):
            B.parse_symop('x, y, __import__')

    def test_element_and_charge(self):
        for sym, want in (('Fe3+', ('Fe', 3)), ('Bi+3', ('Bi', 3)), ('S-2', ('S', -2)), ('Cl-', ('Cl', -1)),
                          ('O2-', ('O', -2)), ('Al', ('Al', None))):
            self.assertEqual(B._element_of('X1', sym), want, sym)
        self.assertEqual(B._element_of('OH1', '')[0], 'O')
        self.assertEqual(B._element_of('OW2', '')[0], 'O')
        self.assertEqual(B._element_of('LiY', '')[0], 'Li')


class Rutile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='bv_')
        cls.cif = _write(cls.tmp, 'rutile.cif', RUTILE)
        cls.st = B.Structure(cls.cif)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_sites_and_multiplicity(self):
        st = self.st
        self.assertEqual(st.n_ops, 16)
        ti = next(s for s in st.sites if s.label == 'Ti1'); o = next(s for s in st.sites if s.label == 'O1')
        self.assertEqual((ti.mult, o.mult), (2, 4))
        self.assertEqual([sp.ox for sp in ti.species], [4])
        self.assertAlmostEqual(st.volume, 62.43, places=1)

    def test_distances(self):
        ti = next(s for s in self.st.sites if s.label == 'Ti1')
        nb = [(round(d, 4), n) for o, d, n in self.st.neighbours(ti, 2.5) if o.label == 'O1']
        self.assertEqual(nb, [(1.9485, 4), (1.9801, 2)])

    def test_bvs_and_selfcheck(self):
        P = B.Params(prefer='bo')
        result, anion_sum, cells = B.compute(self.st, P)
        site, bonds, bvs, expected, mean_d = result[0]
        self.assertAlmostEqual(bvs, 4.07, places=2)          # Ti4+–O R0 1.815, b 0.37
        self.assertAlmostEqual(anion_sum['O1'], bvs / 2, places=6)  # 2 Ti per 4 O: each O gets half a Ti's sum
        self.assertEqual(cells[('O1', 'Ti1')][0][1:], (4, 2))  # 1.9485 ×4 into Ti, ×2 into O
        self.assertIn('consistent', B.geom_self_check(self.st, result))
        text = B.report_text(self.st, P, result, anion_sum, cells)
        self.assertIn("R0 1.815  b 0.370", text)
        self.assertIn('0.70×4↓×2→', text)

    def test_gh_default_and_override(self):
        P = B.Params()                                       # gh
        self.assertEqual(P.get('Ti', 4, 'O', -2)[2], 'bs')
        self.assertEqual(P.get('U', 6, 'O', -2)[2], 'r')     # Burns et al. 1997 for uranyl
        st = B.Structure(self.cif, ox_override={'Ti': 3})
        self.assertEqual(st.cations[0].species[0].ox, 4)     # the .cif's own 'Ti4+' wins over the default
        cif2 = _write(self.tmp, 'rutile2.cif', RUTILE.replace('Ti4+', 'Ti').replace('O2-', 'O'))
        st2 = B.Structure(cif2, ox_override={'Ti': 3})
        self.assertEqual(st2.cations[0].species[0].ox, 3)    # --ox applies when the .cif says nothing

    def test_run_writes_report_and_word(self):
        out = os.path.join(self.tmp, 'out')
        st, result, anion_sum, cells, text = B.run(self.cif, params='bo', word=True, out_dir=out, quiet=True)
        self.assertTrue(os.path.exists(os.path.join(out, 'rutile_bv.txt')))
        from docx import Document
        d = Document(os.path.join(out, 'rutile_bv.docx'))
        self.assertEqual(len(d.tables), 2)
        self.assertEqual(d.tables[1].rows[1].cells[0].text, 'O1')


class ManuscriptTable(unittest.TestCase):
    def test_bond_and_bvs_tables(self):
        from docx import Document
        tmp = tempfile.mkdtemp(prefix='bv_')
        try:
            cif = _write(tmp, 'rutile.cif', RUTILE)
            doc = Document()
            t = doc.add_table(rows=0, cols=2)
            for a, b in (('Ti1–O1 ×4', '1.949(1)'), ('Ti1–O1 ×2', '1.985(1)'), ('<Ti1–O>', '1.965')):
                r = t.add_row().cells; r[0].text = a; r[1].text = b
            t2 = doc.add_table(rows=0, cols=3)
            for row in (('Atom', 'Ti1', 'Σ'), ('O1', '0.70×4↓×2→, 0.64×2↓', '2.03'), ('Σ', '4.07', '')):
                r = t2.add_row().cells
                for i, x in enumerate(row):
                    r[i].text = x
            path = os.path.join(tmp, 'ms.docx'); doc.save(path)
            st = B.Structure(cif); P = B.Params(prefer='bo')
            result, anion_sum, cells = B.compute(st, P)
            tables = B.read_tables(path)
            bonds = B.check_bond_table(st, result, tables)
            self.assertIn('1 bond distances agree with the .cif, 1 do not', bonds[0])
            self.assertTrue(any('1.985 but the .cif gives 1.980' in x for x in bonds), bonds)
            self.assertTrue(any('<Ti1–O> given as 1.965' in x and 'average 1.961' in x for x in bonds), bonds)
            bvs = B.check_bvs_table(st, result, cells, anion_sum, tables, 'test')
            self.assertIn('1 cells compared, 0 disagree', bvs[0])
            self.assertEqual([x for x in bvs[1:] if 'Σ' in x], [], bvs)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
