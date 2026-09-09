"""Unit tests for pxrd_review.bv_check — bond distances, bond-valence sums, manuscript tables.

    python3 -m unittest tests.test_bv_check -v

Rutile (TiO2, P42/mnm) is the reference structure: Ti–O 1.949 ×4 and 1.980 ×2, and the Ti sum is
known (≈ 4.0 vu with Brese & O'Keeffe 1991). A synthetic manuscript table exercises the checker."""
import os, math, shutil, tempfile, unittest

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


# A synthetic P1 hydrate (8 Å cube): Ca at the origin with a sulfate-like O1 (2.42 Å) and a water
# OW1 (2.40 Å); O2 and O3 sit 2.80 Å from OW1 at 120° to the Ca–OW1 bond, 120° apart — the two
# acceptors a water molecule wants; O1 is 2.61 Å from OW1 but on the Ca polyhedron (an edge, not
# a hydrogen bond). H1 (0.96 Å from OW1 towards O2) is appended for the H-located tests.
HYDRATE = """data_hydrate
_chemical_name_mineral testhydrate
_cell_length_a 8
_cell_length_b 8
_cell_length_c 8
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_space_group_name_H-M_alt 'P 1'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Ca1 Ca 0 0 0
O1 O 0.275 0.125 0
OW1 O 0 0.3 0
O2 O 0.30311 0.475 0
O3 O 0.69689 0.475 0
"""
HYDRATE_H = HYDRATE + "H1 H 0.10392 0.36 0\n"


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
        result, anion_sum, cells, hbonds = B.compute(self.st, P)
        self.assertEqual(hbonds, [])                         # no hydrogen anywhere
        site, bonds, bvs, expected, mean_d = result[0]
        self.assertAlmostEqual(bvs, 4.07, places=2)          # Ti4+–O R0 1.815, b 0.37
        self.assertAlmostEqual(anion_sum['O1'], bvs / 2, places=6)  # 2 Ti per 4 O: each O gets half a Ti's sum
        # a half-occupied O: the Ti column sees it half the time, its own row still gets the whole bond
        half = _write(self.tmp, 'half.cif', RUTILE.replace('O1 O2- 0.30479 0.30479 0 1', 'O1 O2- 0.30479 0.30479 0 0.5'))
        r2, a2, c2, _ = B.compute(B.Structure(half), P)
        self.assertAlmostEqual(r2[0][2], bvs / 2, places=6)
        self.assertAlmostEqual(a2['O1'], anion_sum['O1'], places=6)
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
        B.run(self.cif, params='bo', out_dir=out, quiet=True, xlsx=True)
        import openpyxl
        ws = openpyxl.load_workbook(os.path.join(out, 'rutile_bv.xlsx'))['bonds']
        self.assertEqual([c.value for c in ws[2]][:6], ['Ti1', 'Ti+4', 'O1', 1.9485, 1.815, 0.37])


class HydrogenBonds(unittest.TestCase):
    def test_ferraris_ivaldi_and_labels(self):
        self.assertAlmostEqual(B.fi_valence(2.55), 0.33, places=2)      # the paper's own anchor
        self.assertAlmostEqual(B.fi_valence(2.926), 0.146, places=3)    # szilagyiite O1 ← OW1: 0.15 in the owner's table
        self.assertAlmostEqual(B.fi_valence(2.657), 0.250, places=3)    # O6 ← OW1: 0.25
        for lab, n in (('OH1', 1), ('Oh2', 1), ('OW1', 2), ('Ow3', 2), ('W4', 2), ('Wat1', 2), ('O6H', 1), ('O7W', 2), ('F1/OH1', 1), ('O5', 0), ('OH', 1)):
            self.assertEqual(B.label_h(lab), n, lab)

    def test_reference_names_and_note(self):
        P = B.Params(prefer='bo')
        self.assertEqual(P.short_ref('a'), "Brese and O'Keeffe (1991)")   # BO91 reprints every BA85 value
        self.assertEqual(B.Params(prefer='ba').short_ref('a'), 'Brown and Altermatt (1985)')
        self.assertEqual(P.short_ref('s'), 'García-Rodríguez et al. (2000)')
        self.assertEqual(P.short_ref('bo'), 'Nyman et al. (2010)')       # derived from the file's citation
        P = B.Params()
        P.get('Ti', 4, 'O', -2); P.get('U', 6, 'O', -2); P.get('NH', 1, 'O', -2)
        self.assertEqual(P.note(), 'Bond-valence parameters from Gagné and Hawthorne (2015); U6+–O from Burns et al. (1997); '
                                   'NH4+–O from García-Rodríguez et al. (2000)')
        self.assertEqual(B.Params(u6='params').get('U', 6, 'O', -2)[2], 'bs')

    def test_blind_proposal_from_oo_geometry(self):
        tmp = tempfile.mkdtemp(prefix='bv_')
        try:
            cif = _write(tmp, 'h.cif', HYDRATE)
            st = B.Structure(cif); P = B.Params()
            result, anion_sum, cells, hb = B.compute(st, P)
            pairs = sorted((x.donor.label, x.acceptor.label, round(x.d, 2), round(x.s, 3), x.via) for x in hb)
            s = round(B.fi_valence(2.8), 3)
            self.assertEqual(pairs, [('OW1', 'O2', 2.8, s, 'OO'), ('OW1', 'O3', 2.8, s, 'OO')])   # not O1: a Ca polyhedron edge
            self.assertAlmostEqual(anion_sum['O2'], s, places=3)                 # Σan = cations + accepted
            self.assertAlmostEqual(B.donated(hb)['OW1'], 2 * (1 - B.fi_valence(2.8)), places=3)   # the O–H part, reported apart
            self.assertFalse([n for n in st.notes if 'deficit' in n])            # donors came from the label
            # overrides: one H only; a pair forced across the polyhedron edge
            st = B.Structure(cif)
            _, _, _, hb1 = B.compute(st, P, donors={'OW1': 1})
            self.assertEqual(len(hb1), 1)
            st = B.Structure(cif)
            _, _, _, hb2 = B.compute(st, P, force=[('OW1', 'O1')])
            self.assertIn(('OW1', 'O1'), [(x.donor.label, x.acceptor.label) for x in hb2])
            # no labels: the valence deficit decides, and says so
            cif2 = _write(tmp, 'h2.cif', HYDRATE.replace('OW1 O', 'O4 O'))
            st = B.Structure(cif2)
            _, _, _, hb3 = B.compute(st, P)
            self.assertIn('O4', {x.donor.label for x in hb3})               # (O2/O3 have no cation at all: 'water' too)
            self.assertTrue(any('deficit' in n and 'O4' in n for n in st.notes))
            self.assertEqual(B.compute(B.Structure(cif), P, hbond='none')[3], [])
            text = B.report_text(st, P, *B.compute(st, P)[:3], hbonds=hb3)
            self.assertIn('HYDROGEN BONDS', text); self.assertIn('Ferraris', text); self.assertIn('table note:', text)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_with_located_h(self):
        tmp = tempfile.mkdtemp(prefix='bv_')
        try:
            cif = _write(tmp, 'hh.cif', HYDRATE_H)
            st = B.Structure(cif); P = B.Params()
            geo = B.hbond_geometry(st)                       # computed: OW1–H1⋯O2, 180°
            self.assertEqual([(g['labels'], g['ang']) for g in geo], [(('OW1', 'H1', 'O2'), '180')])
            result, anion_sum, cells, hb = B.compute(st, P)  # 'oo': strengths from D⋯A, H not a column
            self.assertEqual([(x.donor.label, x.acceptor.label, x.via) for x in hb], [('OW1', 'O2', 'H')])
            self.assertAlmostEqual(hb[0].s, B.fi_valence(2.8), places=3)
            self.assertNotIn('H1', [r[0].label for r in result])
            result, anion_sum, cells, hb = B.compute(st, P, hbond='h')   # the older convention: H as a cation
            self.assertIn('H1', [r[0].label for r in result])
            got = {(x.donor.label, x.acceptor.label, x.via): x.s for x in hb}
            self.assertIn(('OW1', 'O2', 'H···A'), got)     # (the older mode takes every O within 2.4 Å of the H, O1 included)
            self.assertAlmostEqual(got[('OW1', 'O2', 'H···A')], math.exp((0.990 - 1.84) / 0.59), places=2)   # Brown 2002, H⋯O 1.84 Å
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


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
            result, anion_sum, cells, _ = B.compute(st, P)
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


class PaperTableConventions(unittest.TestCase):
    """The 2026-09-07 hand-check of three papers: a hydroxyl tagged in its row label ('O8(OH)'), two
    values in one cell read off a page with a space between them, a printed Σ that includes the
    hydroxyl's own H, and a site's valence given per label."""

    def test_row_label_tags_and_space_separated_values(self):
        self.assertEqual(B._norm_label('O8(OH)'), 'O8')
        self.assertEqual(B._norm_label('O3(H2O)'), 'O3')
        self.assertEqual(B._norm_label('Fe(1)'), 'FE1')
        self.assertEqual(B._norm_label('OW1'), 'OW1')
        self.assertEqual(B._bv_cell('0.06 0.05×2↓'), [(0.06, 1, 1), (0.05, 2, 1)])       # the mark belongs to the value it follows
        self.assertEqual(B._bv_cell('0.36×2↓ 0.23×2↓'), [(0.36, 2, 1), (0.23, 2, 1)])
        self.assertEqual(B._bv_cell('0.70 ×2↓'), [(0.7, 2, 1)])                        # a space before the mark is still one value
        self.assertEqual(B._bv_cell('0.70×4↓×2→, 0.64×2↓'), [(0.7, 4, 2), (0.64, 2, 1)])

    def test_a_charge_resolves_to_the_lone_site_but_a_second_site_does_not(self):
        # 'Fe3+' in a paper's header, or 'Fe3' with the sign lost in the text layer, is the .cif's one
        # Fe site; 'Fe2' beside an 'Fe1' is a second site the .cif does not have and must not be
        # compared with the first one's valences
        table = {'TI1': 'Ti1', 'TI': 'Ti1'}
        self.assertEqual(B._resolve_sites(['Atom', 'Ti4+', 'Σ'], table), {1: 'Ti1'})
        self.assertEqual(B._resolve_sites(['Atom', 'Ti4', 'Σ'], table), {1: 'Ti1'})
        self.assertEqual(B._resolve_sites(['Atom', 'Ti1', 'Ti2'], table), {1: 'Ti1'})
        self.assertEqual(B._resolve_sites(['Atom', 'Ti2', 'Ti3'], table), {})
        tmp = tempfile.mkdtemp(prefix='bv_')
        try:
            st = B.Structure(_write(tmp, 'rutile.cif', RUTILE)); P = B.Params(prefer='bo')
            result, anion_sum, cells, _ = B.compute(st, P)
            grid = [['Atom', 'Ti1', 'Ti2'], ['O1', '0.70×4↓×2→, 0.64×2↓', '0.50×6↓'], ['Σ', '4.07', '3.00']]
            bvs = B.check_bvs_table(st, result, cells, anion_sum, [grid], 'test')
            self.assertIn('1 cells compared, 0 disagree', bvs[0])
            self.assertFalse(any('Ti2' in x for x in bvs), bvs)
            sites = B.check_bvs_sites(st, result, anion_sum, [{'rows': [('Ti1', 4.07), ('Ti2', 3.00)], 'head': 'BVS'}], 'test', compare_anions=False)
            self.assertIn('1 cells compared, 0 disagree', sites[0]); self.assertFalse(any('Ti2' in x for x in sites), sites)
            sites = B.check_bvs_sites(st, result, anion_sum, [{'rows': [('Ti4+', 4.07)], 'head': 'BVS'}], 'test', compare_anions=False)
            self.assertIn('1 cells compared, 0 disagree', sites[0])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_sum_may_include_the_hydroxyl_hydrogen(self):
        tmp = tempfile.mkdtemp(prefix='bv_')
        try:
            cif = _write(tmp, 'hydrate.cif', HYDRATE_H)
            st = B.Structure(cif); P = B.Params(prefer='bo')
            self.assertEqual(B._h_donor_anions(st), {'OW1'})
            result, anion_sum, cells, _ = B.compute(st, P)
            ca_ow = next(s for (an, cat), lst in cells.items() if an == 'OW1' and cat == 'Ca1' for s, _, _ in lst)
            with_h = [['Atom', 'Ca1', 'Σ'], ['OW1', '%.2f' % ca_ow, '%.2f' % (ca_ow + 0.80)]]        # Σ 'includes 0.80 vu from H1'
            lines = B.check_bvs_table(st, result, cells, anion_sum, [with_h + [['Σ', '%.2f' % ca_ow, '']]], 'test')
            self.assertFalse(any('but its row adds to' in x for x in lines), lines)
            too_much = [['Atom', 'Ca1', 'Σ'], ['OW1', '%.2f' % ca_ow, '%.2f' % (ca_ow + 1.40)], ['Σ', '%.2f' % ca_ow, '']]
            lines = B.check_bvs_table(st, result, cells, anion_sum, [too_much], 'test')
            self.assertTrue(any('but its row adds to' in x for x in lines), lines)   # 1.40 is no hydrogen
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_valence_override_by_site_label(self):
        tmp = tempfile.mkdtemp(prefix='bv_')
        try:
            cif = _write(tmp, 'two_fe.cif', HYDRATE.replace('Ca1 Ca 0 0 0', 'Fe1 Fe 0 0 0'))
            by_el = B.Structure(cif, ox_override={'Fe': 2}); by_lab = B.Structure(cif, ox_override={'Fe1': 3, 'Fe': 2})
            self.assertEqual([sp.ox for sp in by_el.sites[0].species], [2])
            self.assertEqual([sp.ox for sp in by_lab.sites[0].species], [3])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class WaterFromStructure(unittest.TestCase):
    """An oxygen's bond-valence sum says whether it holds hydrogen, whether or not the refinement
    located any — the count issue #10's check rests on."""

    def test_counts_hydroxyl_and_water_from_the_valences(self):
        tmp = tempfile.mkdtemp(prefix='bv_')
        try:
            # the formula sum is what scales the cell's sites to one formula unit (Z)
            cif = _write(tmp, 'hydrate.cif', HYDRATE.replace('_chemical_name_mineral testhydrate',
                         '_chemical_name_mineral testhydrate\n_chemical_formula_sum "Ca O4"'))
            st = B.Structure(cif)
            result, anion_sum, cells, _ = B.compute(st, B.Params(), None, 'none')
            w = B.water_from_structure(st, result, cells)
            self.assertIsNotNone(w)
            kinds = {lab: kind for lab, _v, kind in w['sites']}
            self.assertEqual(kinds['OW1'], 'H2O')              # 0.3 v.u. from one Ca: a water molecule
            self.assertIn(kinds['O2'], ('H2O', 'OH'))          # bonded to nothing at all
            self.assertEqual(w['H'], w['OH'] + 2 * w['H2O'])   # hydrogen is the two counts together

        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_an_oxygen_with_its_full_valence_holds_no_hydrogen(self):
        tmp = tempfile.mkdtemp(prefix='bv_')
        try:
            cif = _write(tmp, 'rutile.cif', RUTILE.replace('loop_\n_space_group_symop_operation_xyz',
                         '_chemical_formula_sum "Ti O2"\nloop_\n_space_group_symop_operation_xyz', 1))
            st = B.Structure(cif)
            result, anion_sum, cells, _ = B.compute(st, B.Params(), None, 'none')
            w = B.water_from_structure(st, result, cells)
            self.assertEqual([k for _l, _v, k in w['sites']], ['O'])
            self.assertEqual((w['OH'], w['H2O'], w['H']), (0.0, 0.0, 0.0))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# A water molecule whose oxygen sits ON a two-fold axis: ONE hydrogen site, TWO hydrogens. The
# formula says H2, so the counter has a right answer to be measured against.
ON_AXIS = """data_axis
_cell_length_a 8.0
_cell_length_b 8.0
_cell_length_c 8.0
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_space_group_name_H-M_alt 'P 2'
_chemical_formula_sum 'Mg1 O1 H2'
loop_
_space_group_symop_operation_xyz
'x, y, z'
'-x, y, -z'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
_atom_site_occupancy
Mg1 Mg2+ 0.0 0.600 0.0 1.0
Ow1 O2-  0.0 0.200 0.0 1.0
Hw1 H    0.075 0.280 0.05 %s
"""


class LocatedHydrogen(unittest.TestCase):
    """The hydrogen a refinement actually placed on oxygen, per formula unit. Counted per OXYGEN,
    by occupancy, because a hydrogen written as two half-occupied alternatives is one hydrogen —
    and because a hydrogen site on a symmetry element stands for more than one atom."""

    def _st(self, occ='1.0'):
        tmp = tempfile.mkdtemp(prefix='bv_')
        self.addCleanup(shutil.rmtree, tmp, True)
        return B.Structure(_write(tmp, 'axis.cif', ON_AXIS % occ))

    def test_a_hydrogen_site_on_a_symmetry_element_stands_for_every_image(self):
        st = self._st()
        self.assertEqual(B._z_from_formula(st), 1)
        # one H site, two images of it 0.96 A from the same oxygen
        o = next(a for a in st.anions if a.label == 'Ow1')
        self.assertEqual([(x.label, n) for x, d, n in st.neighbours(o, 1.3)], [('Hw1', 2)])
        self.assertEqual(B._located_h(st, 1), 2.0)             # the formula says H2, and so does this

    def test_a_half_occupied_site_counts_by_its_occupancy(self):
        # the same oxygen with a half-occupied hydrogen: half a hydrogen per image
        self.assertEqual(B._located_h(self._st('0.5'), 1), 1.0)

    def test_a_structure_that_located_no_hydrogen_says_so(self):
        tmp = tempfile.mkdtemp(prefix='bv_')
        self.addCleanup(shutil.rmtree, tmp, True)
        st = B.Structure(_write(tmp, 'noh.cif', (ON_AXIS % '1.0').replace('Hw1 H    0.075 0.280 0.05 1.0\n', '')))
        self.assertIsNone(B._located_h(st, 1))                 # None, not zero: nothing was placed


    def test_a_half_occupied_cation_gives_its_oxygen_half_the_valence(self):
        """`compute` weights an anion's sum by the cation site's occupancy, and the water count has
        to weight it the same way: a hydroxyl bonded to a half-occupied cation otherwise reads as an
        ordinary oxygen — the one direction this count is meant to be reliable in."""
        tmp = tempfile.mkdtemp(prefix='bv_')
        self.addCleanup(shutil.rmtree, tmp, True)
        full = B.Structure(_write(tmp, 'full.cif', (ON_AXIS % '1.0').replace(
            'Hw1 H    0.075 0.280 0.05 1.0\n', '')))
        half = B.Structure(_write(tmp, 'half.cif', (ON_AXIS % '1.0').replace(
            'Hw1 H    0.075 0.280 0.05 1.0\n', '').replace('Mg1 Mg2+ 0.0 0.600 0.0 1.0', 'Mg1 Mg2+ 0.0 0.600 0.0 0.5')
            .replace("'Mg1 O1 H2'", "'Mg0.5 O1 H2'")))
        got = []
        for st in (full, half):
            result, _an, cells, _hb = B.compute(st, B.Params(), None, 'none')
            w = B.water_from_structure(st, result, cells)
            got.append(dict((lab, v) for lab, v, _k in w['sites'])['Ow1'])
        self.assertAlmostEqual(got[1], got[0] / 2, places=2)

    def test_an_oxygen_holds_at_most_two_hydrogens(self):
        st = self._st()
        # both images plus a third contact would still be a water molecule, never H3O in the count
        self.assertLessEqual(B._located_h(st, 1), 2.0)


if __name__ == '__main__':
    unittest.main()


class WeightedColumns(unittest.TestCase):
    """A bond-valence column printed occupancy-weighted — 'Na1×0.20→' in the header, or a site the
    structure knows to be partly occupied — is read so throughout the column, never cell by cell."""

    def test_header_weight_and_column_mode(self):
        self.assertEqual(B._header_weights(['Atom', 'Na1×0.20→', 'Al1', 'Σ']), {1: 0.2})
        self.assertEqual(B._resolve_sites(['Atom', 'Na1×0.20→', 'Al1'], {'NA1': 'Na1', 'AL1': 'Al1'}), {1: 'Na1', 2: 'Al1'})
        tmp = tempfile.mkdtemp(prefix='bv_'); self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        cif = os.path.join(tmp, 'h.cif'); open(cif, 'w').write(HYDRATE)
        st = B.Structure(cif); P = B.Params(prefer='gh', u6='burns')
        res, an, cells, hb = B.compute(st, P, None, 'oo')
        vals = {a: sorted(s for s, _, _ in v)[0] for (a, c), v in cells.items() if c == 'Ca1'}
        rows = [['Atom', 'Ca1×0.50→', 'Σ']] + [[a, '%.2f' % (v * 0.5), '%.2f' % (v * 0.5)] for a, v in sorted(vals.items())]
        lines = B.check_bvs_table(st, res, cells, an, [rows], 'GH')
        hits = [ln for ln in lines if 'cells compared' in ln]
        self.assertTrue(hits and hits[0].endswith('0 disagree (computed with GH; H columns not compared)') or ', 0 disagree' in hits[0], lines)
        rows[1][1] = '%.2f' % (vals[rows[1][0]] * 0.5 + 0.2)                                   # one of two cells off: the column can no longer be called weighted (two matches are needed), so both cells are findings — conservative
        lines = B.check_bvs_table(st, res, cells, an, [rows], 'GH')
        self.assertTrue(any('2 disagree' in ln for ln in lines), lines)
