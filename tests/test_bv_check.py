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
        self.assertEqual([round(c.value, 4) if isinstance(c.value, float) else c.value for c in ws[2]][:6], ['Ti1', 'Ti+4', 'O1', 1.9485, 1.815, 0.37])
        # the sums the workbook derives are the tool's (held over every corpus .cif when the writer changed: mixed anions, split waters)
        from tests.xl_eval import Book
        b = Book(os.path.join(out, 'rutile_bv.xlsx'))
        st, result, anion_sum, cells, text = B.run(self.cif, params='bo', out_dir=out, quiet=True)
        wt = b.wb['BV table']                                   # the table as a paper prints it, every cell a formula of the bonds sheet
        self.assertEqual([c.value for c in wt[1]], ['(vu)', 'Ti1', 'Σan'])
        self.assertEqual([c.value for c in wt['A']][1:4], ['O1', 'Σ', 'expected'])
        self.assertEqual(b.value('BV table', 'B2'), ', '.join('%.2f%s' % (s_, B._mark(nd, na)) for s_, nd, na in cells[('O1', 'Ti1')]))
        self.assertIn('↓', b.value('BV table', 'B2'))
        self.assertAlmostEqual(b.value('BV table', 'B3'), result[0][2], places=9)          # Σ of the Ti column
        self.assertAlmostEqual(b.value('BV table', 'C2'), anion_sum['O1'], places=9)       # Σan of the O row

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
            # the table follows another set than the one asked for: the CLI report moves to it and says so; the GUI's export
            # (follow_table=False) scores the sets just the same and stays on the pane's
            from unittest import mock
            out = os.path.join(tmp, 'o'); real = B.check_bvs_table
            def scored(st_, res_, cells_, an_, tabs_, label='?', **kw):      # the asked-for set made to disagree with the table
                return ['table 1: 1 cells compared, 1 disagree'] if label.startswith('Gagn') else real(st_, res_, cells_, an_, tabs_, label, **kw)
            with mock.patch.object(B, 'check_bvs_table', side_effect=scored):
                moved = B.run(cif, table=path, params='gh', out_dir=out, quiet=True)[4]
                kept = B.run(cif, table=path, params='gh', out_dir=out, quiet=True, follow_table=False)[4]
            self.assertIn('the report below uses them', moved); self.assertNotIn('Gagné', moved.split('MANUSCRIPT TABLE CHECK')[0])
            self.assertIn('this report keeps Gagné & Hawthorne 2015, the set asked for', kept)
            self.assertIn('Gagné', kept.split('MANUSCRIPT TABLE CHECK')[0])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class CheckSheet(unittest.TestCase):
    """The workbook's check sheet: a paper's table written from the tool's own cells, then spoiled in known ways."""

    def _grid(self, st, result, cells, anion_sum, spoil=None, scale=None):
        cats = [r[0].label for r in result if r[0].element != 'H']
        rows = [['Atom'] + cats + ['Σ']]
        for an in st.anions:
            if not any((an.label, c) in cells for c in cats):
                continue
            row = [an.label]; tot = 0.0
            for c in cats:
                segs = cells.get((an.label, c))
                if not segs:
                    row.append(''); continue
                k = (scale or {}).get(c, 1.0)
                vals = [(s_ * k + (spoil or {}).get((an.label, c), 0.0), nd, na) for s_, nd, na in segs]
                row.append(', '.join('%.2f%s' % (v, B._mark(nd, na)) for v, nd, na in vals))
                tot += sum(v * (na if isinstance(na, int) else 1) for v, nd, na in vals)
            rows.append(row + ['%.2f' % tot])
        return rows

    def _book(self, tmp, cif, grid, name):
        from tests.xl_eval import Book
        st = B.Structure(cif); P = B.Params(prefer='gh')
        result, anion_sum, cells, hbonds = B.compute(st, P, hbond='none')
        out = os.path.join(tmp, name)
        B.write_xlsx(st, P, result, anion_sum, cells, hbonds, out, tables=[grid], params_label='Gagné & Hawthorne 2015')
        b = Book(out); wc = b.wb['check']
        cell_rows = {(wc.cell(r, 2).value, wc.cell(r, 3).value): r for r in range(4, wc.max_row + 1) if wc.cell(r, 9).value in ('agrees', 'differs', 'blank', 'not compared') and wc.cell(r, 2).value}
        return b, wc, cell_rows

    def test_a_bvs_column_takes_the_table_checks_verdicts_and_one_table(self):
        import openpyxl
        tmp = tempfile.mkdtemp(prefix='bvchk_')
        try:
            cif = _write(tmp, 'hydrate.cif', HYDRATE)
            st = B.Structure(cif); P = B.Params(prefer='gh')
            result, anion_sum, cells, hbonds = B.compute(st, P, hbond='none')
            cats = [r for r in result if r[0].element != 'H']
            # the paper's column, each sum a little off but inside check_bvs_sites' tolerance (0.05 vu + 3 %), beside a column of
            # the same labels that is not valences at all (occupancies) — the pdf reader returns every candidate it finds
            real = [(r[0].label, round(r[2] + 0.05, 2)) for r in cats]
            junk = [(r[0].label, 0.979) for r in cats]
            lines, rec = B.best_site_table(st, result, anion_sum, [junk, real])
            self.assertTrue(rec and all(d['status'] == 'agrees' for d in rec), rec)
            out = os.path.join(tmp, 's.xlsx')
            B.write_xlsx(st, P, result, anion_sum, cells, hbonds, out, site_tables=[junk, real], params_label='Gagné & Hawthorne 2015')
            wc = openpyxl.load_workbook(out)['check']
            verdicts = [wc.cell(r, 8).value for r in range(1, wc.max_row + 1) if wc.cell(r, 2).value in ('cation', 'anion') and isinstance(wc.cell(r, 1).value, int)]
            self.assertEqual(verdicts, ['agrees'] * len(cats))              # one table, the table check's verdicts, no live 0.08 rule
            self.assertTrue(any(str(wc.cell(r, 1).value).startswith('bond-valence sums (table 1') for r in range(1, wc.max_row + 1)))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_the_paper_checks_verdict_is_the_sheets(self):
        import openpyxl
        tmp = tempfile.mkdtemp(prefix='bvchk_')
        try:
            cif = _write(tmp, 'hydrate.cif', HYDRATE)
            st = B.Structure(cif); P = B.Params(prefer='gh')
            result, anion_sum, cells, hbonds = B.compute(st, P, hbond='none')
            (an, cat) = next((a, c) for (a, c), segs in cells.items() if len(segs) == 1 and next(r[0] for r in result if r[0].label == c).element != 'H')
            grid = self._grid(st, result, cells, anion_sum, spoil={(an, cat): 0.30})
            out = os.path.join(tmp, 'k.xlsx')
            verdicts = lambda: [c.value for c in openpyxl.load_workbook(out)['check']['I'] if c.value in ('agrees', 'differs', 'not compared', 'blank')]
            B.write_xlsx(st, P, result, anion_sum, cells, hbonds, out, tables=[grid], params_label='GH')
            self.assertIn('differs', verdicts())
            # the paper check holds that cell (its line is among those kept): still red
            B.write_xlsx(st, P, result, anion_sum, cells, hbonds, out, tables=[grid], params_label='GH', keep=['table 1: %s–%s 0.55 vs 0.25 computed' % (an, cat)])
            self.assertIn('differs', verdicts())
            # it does not (the column excused, the table doubted): shown, not red
            B.write_xlsx(st, P, result, anion_sum, cells, hbonds, out, tables=[grid], params_label='GH', keep=['table 1: doubted as read'])
            self.assertNotIn('differs', verdicts()); self.assertIn('not compared', verdicts())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_a_mistyped_valence_a_shifted_column_and_bad_arithmetic(self):
        tmp = tempfile.mkdtemp(prefix='bvchk_')
        try:
            cif = _write(tmp, 'hydrate.cif', HYDRATE)
            st = B.Structure(cif); P = B.Params(prefer='gh')
            result, anion_sum, cells, hbonds = B.compute(st, P, hbond='none')
            single = [(a, c) for (a, c), segs in cells.items() if len(segs) == 1 and next(r[0] for r in result if r[0].label == c).element != 'H']
            self.assertTrue(single)
            # the table as the tool would print it: every cell agrees, every ΔR is nothing
            b, wc, rows = self._book(tmp, cif, self._grid(st, result, cells, anion_sum), 'ok.xlsx')
            self.assertEqual(b.wb.sheetnames[:3], ['bonds', 'check', 'BV table'])
            self.assertEqual({wc.cell(r, 9).value for r in rows.values()}, {'agrees'})
            for (a, c) in single:
                self.assertAlmostEqual(b.value('check', 'M%d' % rows[(a, c)]), 0.0, delta=0.01)    # the rounding of a printed 0.xx
            # one valence mistyped by +0.20: that cell differs, its column reads 'a cell', and the R it would need is not the structure's
            bad = single[0]
            b, wc, rows = self._book(tmp, cif, self._grid(st, result, cells, anion_sum, spoil={bad: 0.20}), 'typo.xlsx')
            self.assertEqual(wc.cell(rows[bad], 9).value, 'differs')
            self.assertEqual([k for k, r in rows.items() if wc.cell(r, 9).value == 'differs'], [bad])
            self.assertAlmostEqual(b.value('check', 'H%d' % rows[bad]), 0.20, delta=0.011)
            self.assertLess(b.value('check', 'M%d' % rows[bad]), -0.03)                             # a larger valence needs a shorter bond
            lab = {wc.cell(r, 1).value: r for r in range(1, wc.max_row + 1) if isinstance(wc.cell(r, 1).value, str)}
            r_col = next(r for r in range(lab['cation column'] + 1, wc.max_row + 1) if wc.cell(r, 1).value == bad[1])
            self.assertIn('a distance, a ×n multiplicity or a mistyped valence', b.value('check', 'E%d' % r_col))
            # a whole column printed 15 % high: the column, not its cells — R0 and b
            col = max({c for a, c in cells if next(r[0] for r in result if r[0].label == c).element != 'H'}, key=lambda c: sum(1 for a, c2 in cells if c2 == c))
            b, wc, rows = self._book(tmp, cif, self._grid(st, result, cells, anion_sum, scale={col: 1.15}), 'col.xlsx')
            lab = {wc.cell(r, 1).value: r for r in range(1, wc.max_row + 1) if isinstance(wc.cell(r, 1).value, str)}
            r_col = next(r for r in range(lab['cation column'] + 1, wc.max_row + 1) if wc.cell(r, 1).value == col)
            if b.value('check', 'B%d' % r_col) >= 3:
                self.assertIn('the whole column differs', b.value('check', 'E%d' % r_col))
            # the paper's own Σ does not add up: said as arithmetic, before any comparison with the structure
            grid = self._grid(st, result, cells, anion_sum)
            grid[1][-1] = '%.2f' % (float(grid[1][-1]) + 0.30)
            b, wc, rows = self._book(tmp, cif, grid, 'sum.xlsx')
            why = [wc.cell(r, 9).value for r in range(4, wc.max_row + 1) if wc.cell(r, 2).value == 'anion' and wc.cell(r, 8).value == 'differs']
            self.assertTrue(why and why[0].startswith('ARITHMETIC'), why)
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
        # the count before its sign, with no arrow ('2×0.41', and '2× 0.22' as a line break delivers
        # it): the '0' that begins the value is not the count — read so, the cell had no value at all
        self.assertEqual(B._bv_cell('2×0.41'), [(0.41, 2, 1)])
        self.assertEqual(B._bv_cell('2× 0.22'), [(0.22, 2, 1)])
        self.assertEqual(B._bv_cell('12×0.05'), [(0.05, 12, 1)])
        self.assertEqual(B._bv_cell('↓×40.07→×2'), [(0.07, 4, 2)])                     # the welded forms still read
        self.assertEqual(B._bv_cell('2×→0.41×4↓'), [(0.41, 4, 2)])

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

    def test_a_blank_cell_is_a_difference_only_for_a_bond_a_table_would_print(self):
        """A blank cell where the .cif has a bond: a finding when the bond is one a table prints, and
        information — said so in the line's own wording, 'not a difference' — when it is a contact
        under BLANK_INFO (agujaite's O8–Na2 at 0.03 vu). The checker decides, once; the GUI's
        red/grey rule and the record layer read the wording, so neither re-parses the number."""
        tmp = tempfile.mkdtemp(prefix='bv_'); self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        cif = os.path.join(tmp, 'h.cif'); open(cif, 'w').write(HYDRATE)
        st = B.Structure(cif); P = B.Params(prefer='gh', u6='burns')
        res, an, cells, hb = B.compute(st, P, None, 'oo')
        self.assertIn(('OW1', 'Ca1'), cells)
        rows = [['Atom', 'Ca1'], ['O1', '%.2f' % sorted(s for s, _, _ in cells[('O1', 'Ca1')])[0]], ['OW1', '']]
        weak = dict(cells); weak[('OW1', 'Ca1')] = [(0.03, 1, 1)]                          # the bond is a 0.03 vu contact
        lines = B.check_bvs_table(st, res, weak, an, [rows], 'GH')
        blank = [ln for ln in lines if 'OW1–Ca1 is blank' in ln]
        self.assertEqual(len(blank), 1, lines)
        self.assertIn('not a difference', blank[0]); self.assertNotIn('blank but', blank[0])
        self.assertTrue(any(', 0 disagree' in ln for ln in lines), lines)
        lines = B.check_bvs_table(st, res, cells, an, [rows], 'GH')                         # the real bond, 0.30 vu: a missing cell
        blank = [ln for ln in lines if 'OW1–Ca1 is blank' in ln]
        self.assertEqual(len(blank), 1, lines)
        self.assertIn('blank but the .cif has that bond (0.30 vu)', blank[0]); self.assertNotIn('not a difference', blank[0])
        self.assertLess(B.BLANK_INFO, 0.30)


class ColumnMappedOff(unittest.TestCase):
    """A sparse grid under a wide header (boscardinite's seventeen cation columns on two lines): a
    cell that fits the NEIGHBOURING column's bond is a cell mapped one column off, a doubt about
    the read — noted in its own words, not counted as a difference."""

    def test_a_cell_that_fits_the_next_column_is_not_a_difference(self):
        tmp = tempfile.mkdtemp(prefix='bv_'); self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        cif = os.path.join(tmp, 'h.cif'); open(cif, 'w').write(HYDRATE + "Mg1 Mg 0.52 0.12 0\n")   # 1.96 Å from O1, which Ca1 bonds too
        st = B.Structure(cif); P = B.Params(prefer='gh', u6='burns')
        res, an, cells, hb = B.compute(st, P, None, 'oo')
        ca = {a: sorted(s for s, _, _ in v)[0] for (a, c), v in cells.items() if c == 'Ca1'}
        mg = {a: sorted(s for s, _, _ in v)[0] for (a, c), v in cells.items() if c == 'Mg1'}
        both = sorted(set(ca) & set(mg))
        self.assertTrue(both, (ca, mg))
        anions = sorted(set(ca) | set(mg), key=lambda a: (a not in both, a))
        rows = [['Atom', 'Ca1', 'Mg1', 'Σ']] + [[a, ('%.2f' % ca[a]) if a in ca else '', ('%.2f' % mg[a]) if a in mg else '', ''] for a in anions]
        rows[1][2] = '%.2f' % ca[both[0]]                                                       # the Ca1 value printed under Mg1, and nothing under Ca1
        rows[1][1] = ''
        rows.append([both[0] + 'x', '%.2f' % (ca[both[0]] + 0.3), '', ''])                       # a row of no anion: ignored
        lines = B.check_bvs_table(st, res, cells, an, [rows], 'GH')
        self.assertTrue(any('mapped one column off' in ln and 'Ca1' in ln for ln in lines), lines)
        self.assertTrue(any('0 disagree' in ln for ln in lines), lines)
        rows[1][1] = '%.2f' % (ca[both[0]] + 0.3)                                               # the neighbour has its own value: the cell is a difference
        lines = B.check_bvs_table(st, res, cells, an, [rows], 'GH')
        self.assertFalse(any('mapped one column off' in ln for ln in lines), lines)
        self.assertTrue(any('2 disagree' in ln for ln in lines), lines)


# A synthetic P2/m hydrate for the symmetry-code checks (orthogonal cell 7 × 8 × 6 Å). The water OW1
# sits on the mirror (y = 0); its H1 points 0.96 Å towards the image of O2 under −x+1, y, −z+1 (2.775 Å
# away) — so the right code carries a lattice translation, and the same operator without it (−x, y, −z)
# puts O2 far away. H1's mirror image (x, −y, z) is bonded to the same OW1: the same hydrogen bond again.
_OW1 = (0.10, 0.0, 0.10)
_DA = (1.6 / 7, 1.5 / 8, 1.7 / 6)                           # the D⋯A vector, fractional (2.775 Å)
_PA = tuple(_OW1[i] + _DA[i] for i in range(3))
_O2 = (1 - _PA[0], _PA[1], 1 - _PA[2])                       # O2 = (−x+1, y, −z+1) of the acceptor position
_H1 = tuple(_OW1[i] + _DA[i] * 0.96 / 2.775 for i in range(3))
WATER = """data_water
_chemical_name_mineral testwater
_cell_length_a 7
_cell_length_b 8
_cell_length_c 6
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_space_group_name_H-M_alt 'P 2/m'
loop_
_space_group_symop_operation_xyz
'x, y, z'
'-x, y, -z'
'-x, -y, -z'
'x, -y, z'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Mg1 Mg 0.5 0.5 0.5
O1 O 0.5 0.25 0.5
OW1 O %.6f %.6f %.6f
O2 O %.6f %.6f %.6f
H1 H %.6f %.6f %.6f
""" % (_OW1 + _O2 + _H1)


def _ms_docx(path, blocks, paras=()):
    """A manuscript: each block (caption, rows, footnote) as a caption paragraph, a Word table and a
    footnote paragraph; '^c^' in a cell or footnote is written as a superscript run."""
    import re as _re
    from docx import Document
    doc = Document()
    def put(par, text):
        for k, part in enumerate(_re.split(r'\^([^^]*)\^', text)):
            if part:
                par.add_run(part).font.superscript = bool(k % 2)
    for p in paras:
        put(doc.add_paragraph(), p)
    for cap, rows, foot in blocks:
        put(doc.add_paragraph(), cap)
        t = doc.add_table(rows=0, cols=max(len(r) for r in rows))
        for row in rows:
            cells = t.add_row().cells
            for i, x in enumerate(row):
                cells[i].paragraphs[0].text = ''
                put(cells[i].paragraphs[0], x)
        if foot:
            put(doc.add_paragraph(), foot)
    doc.save(path)
    return path


class CodeNotes(unittest.TestCase):
    def test_label_and_fraction_forms(self):
        c = B.parse_code_notes("Symmetry transformations used to generate equivalent atoms: (1) ‘x, y, z–1’; "
                               "(3B) ‘x−½, −y+½, z+1’; (i) −x+1/2, y, −z; #2 -x+1,y,-z+1; iv = x, y−1, z; ′ = x, −y, z+¼")
        self.assertEqual(list(c), ['1', '3B', 'i', '2', 'iv', "'"])
        self.assertEqual(c['1'][:2], B.parse_symop('x,y,z-1'))
        self.assertEqual(c['3B'][:2], B.parse_symop('x-1/2,-y+1/2,z+1'))
        self.assertEqual(c['i'][:2], B.parse_symop('-x+1/2,y,-z'))
        self.assertEqual(c['2'][:2], B.parse_symop('-x+1,y,-z+1'))
        self.assertEqual(c['iv'][:2], B.parse_symop('x,y-1,z'))
        self.assertEqual(c["'"][:2], B.parse_symop('x,-y,z+1/4'))
        self.assertEqual(B.parse_code_notes('Bond valences are from Gagné and Hawthorne (2015).'), {})

    def test_per_table_codes_and_same_as(self):
        tmp = tempfile.mkdtemp(prefix='bv_')
        try:
            path = _ms_docx(os.path.join(tmp, 'ms.docx'), [
                ('Table 5. Bond distances.', [['Mg1–O1^1^', '2.000(1)']], 'Symmetry codes: (1) x, y, z+1.'),
                ('Table 6. Hydrogen bonds.', [['OW1–H1⋯O2^1^', '0.96', '1.8', '2.775']], 'Symmetry codes: (1) −x+1, y, −z+1.'),
                ('Table 7. Bond valences.', [['O1', '0.33']], 'Symmetry codes are the same as in Table 6.')])
            notes, paras = B.read_table_notes(path)
            self.assertEqual([notes[i]['caption'] for i in range(3)], [5, 6, 7])
            self.assertEqual(notes[0]['codes']['1'][:2], B.parse_symop('x,y,z+1'))
            self.assertEqual(notes[1]['codes']['1'][:2], B.parse_symop('-x+1,y,-z+1'))
            self.assertEqual(notes[2]['codes'], notes[1]['codes'])
            self.assertIn('Table 6. Hydrogen bonds.', paras)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class SymmetryCodes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='bv_')
        self.cif = _write(self.tmp, 'water.cif', WATER)
        self.st = B.Structure(self.cif)
        ow1, h1, o2 = (self.st.site(x) for x in ('OW1', 'H1', 'O2'))
        pa = B._apply(B.parse_symop('-x+1,y,-z+1'), o2.frac)
        self.da = '%.3f(3)' % self.st.dist(ow1.frac, pa)
        self.ha = '%.2f(3)' % self.st.dist(h1.frac, pa)
        self.dh = '%.2f(3)' % self.st.dist(ow1.frac, h1.frac)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_check(self, blocks, paras=()):
        path = _ms_docx(os.path.join(self.tmp, 'ms.docx'), blocks, paras)
        notes, ps = B.read_table_notes(path)
        return B.check_symmetry_codes(self.st, B.read_tables(path), notes, ps)

    def hb(self, label):
        return [label, self.dh, self.ha, self.da, '160(3)']

    def test_right_codes_are_silent(self):
        recs = self.run_check([('Table 6. Hydrogen bonds.', [['D–H⋯A', 'D–H', 'H⋯A', 'D⋯A', '∠DHA'], self.hb('OW1–H1⋯O2^1^')],
                                'Symmetry codes: (1) –x+1, y, –z+1.')])
        self.assertEqual([r for r in recs if r['severity'] != 'info'], [], recs)
        self.assertIn('1 coded distances reproduce', recs[0]['text'])

    def test_code_without_its_translation_and_duplicate_row(self):
        recs = self.run_check([('Table 6. Hydrogen bonds.', [self.hb('OW1–H1⋯O2^1^'), self.hb('OW1–H1^2^⋯O2^3^'), self.hb('OW1–H1⋯O2^4^')],
                                "Symmetry codes: (1) ‘–x+1, y, –z+1’; (2) ‘x, –y, z’; (3) ‘–x+1, –y, –z+1’; (4) ‘–x, y, –z’.")],
                              paras=['The three hydrogen bonds in Table 6 link the waters.'])
        flags = [r for r in recs if r['severity'] == 'flag']
        self.assertEqual(len(flags), 1, recs)
        self.assertEqual((flags[0]['kind'], flags[0]['row'], flags[0]['fix']), ('translation', 2, '−x+1, y, −z+1'))
        self.assertIn("code (4) '−x, y, −z' lacks its lattice translation", flags[0]['text'])
        dup = [r for r in recs if r['kind'] == 'duplicate']
        self.assertEqual(len(dup), 1, recs)
        self.assertIn('rows 1 and 2', dup[0]['text'])
        self.assertIn("image under 'x, −y, z'", dup[0]['text'])
        self.assertIn("the text counts 'three hydrogen bonds'", dup[0]['text'])

    def test_wrong_donor_label(self):
        recs = self.run_check([('Table 6. Hydrogen bonds.', [self.hb('O1–H1⋯O2^1^'), self.hb('OW1–H1^2^⋯O2^3^')],
                                'Symmetry codes: (1) –x+1, y, –z+1; (2) x, –y, z; (3) –x+1, –y, –z+1.')])
        donor = [r for r in recs if r['kind'] == 'donor']
        self.assertEqual(len(donor), 1, recs)
        self.assertEqual((donor[0]['row'], donor[0]['severity'], donor[0]['fix']), (0, 'flag', 'OW1'))
        self.assertIn('H1 is bonded to OW1', donor[0]['text'])
        self.assertFalse(any(r['kind'] in ('translation', 'operator') for r in recs), recs)   # the distance holds from the true donor

    def test_a_table_that_omits_every_translation_is_one_record(self):
        recs = self.run_check([('Table 6. Hydrogen bonds.', [self.hb('OW1–H1⋯O2^1^'), self.hb('OW1–H1^2^⋯O2^3^')],
                                'Symmetry codes: (1) –x, y, –z; (2) x, –y, z; (3) –x, –y, –z.')])
        codes = [r for r in recs if r['kind'] == 'translation']
        self.assertEqual(len(codes), 1, recs)
        self.assertEqual((codes[0]['severity'], codes[0]['row']), ('flag', None))
        self.assertIn('printed without their lattice translations — 2 of the 2 coded distances', codes[0]['text'])

    def test_one_number_per_table(self):
        recs = self.run_check([('Table 5. Hydrogen bonds.', [self.hb('OW1–H1⋯O2^1^')], 'Symmetry codes: (1) –x+1, y, –z+1.'),
                               ('Table 6. Hydrogen bonds again.', [self.hb('OW1–H1^2^⋯O2^1^')], 'Symmetry codes: (1) –x+1, –y, –z+1; (2) x, –y, z.')])
        self.assertEqual([r for r in recs if r['severity'] != 'info'], [], recs)

    def test_undefined_code(self):
        recs = self.run_check([('Table 6. Hydrogen bonds.', [self.hb('OW1–H1⋯O2^1^'), self.hb('OW1–H1⋯O2^9^')],
                                'Symmetry codes: (1) –x+1, y, –z+1.')])
        und = [r for r in recs if r['kind'] == 'undefined']
        self.assertEqual(len(und), 1, recs)
        self.assertEqual((und[0]['row'], und[0]['severity']), (1, 'note'))

    def test_wrong_operator_is_flagged_row_by_row(self):
        # the mirror (x, −y, z) where the twofold with its translation is meant: another operator, always a row flag
        recs = self.run_check([('Table 6. Hydrogen bonds.', [self.hb('OW1–H1⋯O2^1^'), self.hb('OW1–H1^2^⋯O2^3^'), self.hb('OW1–H1⋯O2^2^')],
                                'Symmetry codes: (1) –x+1, y, –z+1; (2) x, –y, z; (3) –x+1, –y, –z+1.')])
        op = [r for r in recs if r['kind'] == 'operator']
        self.assertEqual(len(op), 1, recs)
        self.assertEqual((op[0]['row'], op[0]['severity'], op[0]['fix']), (2, 'flag', '−x+1, y, −z+1'))
        self.assertIn('is the wrong operator', op[0]['text'])

    def test_an_operator_the_group_does_not_have(self):
        # Mg1–O1 2.000 twice: as listed, and across the mirror; the code printed is no operator of P2/m
        recs = self.run_check([('Table 5. Bond distances.', [['Mg1–O1', '2.000(1)'], ['Mg1–O1^5^', '2.000(1)'],
                                                             ['OW1–H1⋯O2^1^'] + self.hb('')[1:], ['OW1–H1^2^⋯O2^3^'] + self.hb('')[1:]],
                                'Symmetry codes: (1) –x+1, y, –z+1; (2) x, –y, z; (3) –x+1, –y, –z+1; (5) –x+½, y, –z.')])
        op = [r for r in recs if r['kind'] == 'operator']
        self.assertEqual(len(op), 1, recs)
        self.assertEqual(op[0]['row'], 1)
        self.assertIn(op[0]['fix'], ('x, −y+1, z', '−x+1, −y+1, −z+1'))               # the image across Mg1 (mirror = inversion there), not O1 as listed
        self.assertIn('not an operator of P 2/m', op[0]['text'])

    def test_a_distance_that_needs_a_code_and_has_none(self):
        recs = self.run_check([('Table 6. Hydrogen bonds.', [self.hb('OW1–H1⋯O2^1^'), self.hb('OW1–H1^2^⋯O2^3^'), self.hb('OW1–H1⋯O2')],
                                'Symmetry codes: (1) –x+1, y, –z+1; (2) x, –y, z; (3) –x+1, –y, –z+1.')])
        nc = [r for r in recs if r['kind'] == 'nocode']
        self.assertEqual(len(nc), 1, recs)
        self.assertEqual((nc[0]['row'], nc[0]['severity'], nc[0]['fix']), (2, 'flag', '−x+1, y, −z+1'))
        self.assertIn('has no symmetry code, but O2 as listed is', nc[0]['text'])

    def test_a_table_with_no_codes_at_all_is_one_line(self):
        recs = self.run_check([('Table 6. Hydrogen bonds.', [self.hb('OW1–H1⋯O2'), self.hb('OW1⋯O2')], '')])
        nc = [r for r in recs if r['kind'] == 'nocode']
        self.assertEqual(len(nc), 1, recs)
        self.assertEqual((nc[0]['row'], nc[0]['severity']), (None, 'flag'))
        self.assertIn('prints no symmetry codes, but 2 of its distances', nc[0]['text'])

    def test_codes_follow_the_coordinates_the_manuscript_prints(self):
        # the manuscript prints O2 one cell over (x − 1): its code '−x, y, −z+1' is right in ITS frame (the .cif's
        # coordinates want '−x+1, y, −z+1')
        o2 = self.st.site('O2').frac
        coords = [['Atom', 'x', 'y', 'z']] + [[s.label] + ['%.6f' % v for v in s.frac] for s in self.st.sites if s.label != 'O2'] + \
                 [['O2', '%.6f' % (o2[0] - 1), '%.6f' % o2[1], '%.6f' % o2[2]]]
        recs = self.run_check([('Table 4. Atom coordinates.', coords, ''),
                               ('Table 6. Hydrogen bonds.', [self.hb('OW1–H1⋯O2^1^'), self.hb('OW1–H1^2^⋯O2^3^')],
                                'Symmetry codes: (1) –x, y, –z+1; (2) x, –y, z; (3) –x, –y, –z+1.')])
        self.assertEqual([r['kind'] for r in recs if r['severity'] != 'info'], ['duplicate'], recs)   # rows 1, 2: one bond
        frame, n, diff = B.manuscript_frame(self.st, B.read_tables(os.path.join(self.tmp, 'ms.docx')))
        self.assertEqual((n, diff), (5, 0))
        self.assertAlmostEqual(frame['O2'][0], o2[0] - 1)

    def test_run_reports_them(self):
        path = _ms_docx(os.path.join(self.tmp, 'ms.docx'), [
            ('Table 6. Hydrogen bonds.', [self.hb('OW1–H1⋯O2^1^'), self.hb('OW1–H1^2^⋯O2^3^'), self.hb('OW1–H1⋯O2^4^')],
             'Symmetry codes: (1) –x+1, y, –z+1; (2) x, –y, z; (3) –x+1, –y, –z+1; (4) –x, y, –z.')])
        text = B.run(self.cif, table=path, out_dir=os.path.join(self.tmp, 'o'), quiet=True)[4]
        self.assertIn("code (4) '−x, y, −z' lacks its lattice translation: it puts O2", text)
        self.assertIn('note: table 1 (Table 6) row 2: rows 1 and 2', text)


# A PO4 tetrahedron in a P1 cube with a fifth O 2.9 Å from P (a contact ~0.03 vu, past the first shell).
_T = 1.54 / math.sqrt(3) / 10
PHOSPHATE = """data_phosphate
_chemical_name_mineral testphosphate
_cell_length_a 10
_cell_length_b 10
_cell_length_c 10
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
P1 P5+ 0.5 0.5 0.5
O1 O2- %(p).6f %(p).6f %(p).6f
O2 O2- %(p).6f %(m).6f %(m).6f
O3 O2- %(m).6f %(p).6f %(m).6f
O4 O2- %(m).6f %(m).6f %(p).6f
O5 O2- 0.5 0.5 0.79
""" % {'p': 0.5 + _T, 'm': 0.5 - _T}


class FirstShell(unittest.TestCase):
    def test_contact_past_the_tetrahedron_is_no_bond(self):
        tmp = tempfile.mkdtemp(prefix='bv_')
        try:
            st = B.Structure(_write(tmp, 'po4.cif', PHOSPHATE))
            res = B.compute(st, B.Params())[0]
            p = [r for r in res if r[0].label == 'P1'][0]
            self.assertEqual(sorted(b.anion.label for b in p[1]), ['O1', 'O2', 'O3', 'O4'])
            self.assertAlmostEqual(p[4], 1.54, places=3)
            doc = [['P1–O1', '1.540(2)'], ['P1–O2', '1.540(2)'], ['P1–O3', '1.540(2)'], ['P1–O4', '1.540(2)'], ['<P1–O>', '1.540']]
            lines = B.check_bond_table(st, res, [doc])
            self.assertIn('4 bond distances agree with the .cif, 0 do not', lines[0])
            self.assertFalse(any('different bond set' in x or 'not in the table' in x for x in lines), lines)
            # an explicit cutoff still means everything within it
            p5 = [r for r in B.compute(st, B.Params(), cutoff=3.0)[0] if r[0].label == 'P1'][0]
            self.assertIn('O5', [b.anion.label for b in p5[1]])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_shells_that_stay_whole(self):
        keep = lambda rows: len(B.first_shell([(d, n, s, k) for k, (d, n, s) in enumerate(rows)]))
        self.assertEqual(keep([(2.10, 6, 0.33)]), 1)                                   # an octahedron
        self.assertEqual(keep([(1.90, 3, 1.2), (2.80, 2, 0.09)]), 2)                   # Te4+: the long bonds are worth 0.09 vu
        self.assertEqual(keep([(1.78, 2, 1.6), (2.35, 5, 0.6)]), 2)                    # uranyl: the gap comes after two bonds
        self.assertEqual(keep([(1.47, 3, 1.5), (1.99, 1, 1.25)]), 2)                   # a split sulfate O: strong
        self.assertEqual(keep([(1.69, 3, 1.25), (1.73, 1, 1.1), (2.95, 1, 0.035)]), 2) # a tetrahedral anion and a contact


class FootnoteRepair(unittest.TestCase):
    """A code footnote as a pdf's text layer delivers it: the lost sign is the one the footnote never shows."""
    def ops(self, text):
        return {k: v[2].replace(' ', '') for k, v in B.parse_code_notes(text).items()}

    def test_lost_minus_lost_plus_and_undecidable(self):
        self.assertEqual(self.ops('(ii) x+2, y+2, z+1; (iii) x, y, z1; (iv) x, y 1/2, z+1'),
                         {'ii': 'x+2,y+2,z+1', 'iii': 'x,y,z-1', 'iv': 'x,y-1/2,z+1'})      # '+' printed: the minus was lost
        self.assertEqual(self.ops('(i) x, −y\x043/2, z; (v) x, y, z\x041; (vii) x, y, z–1'),
                         {'i': 'x,-y+3/2,z', 'v': 'x,y,z+1', 'vii': 'x,y,z-1'})             # '−' printed: the plus was lost
        self.assertEqual(self.ops('(x) x, yþ1, z; (xii) \x03xþ1, \x03yþ1, z'), {'x': 'x,y+1,z', 'xii': '-x+1,-y+1,z'})
        self.assertEqual(self.ops('(i) x1, y, z; (ii) x, y, z'), {'ii': 'x,y,z'})           # no sign printed anywhere: unread, not guessed

    def test_stacked_fractions_line_breaks_and_the_sentence_after(self):
        self.assertEqual(self.ops('(ii) x + 1 2, y + 1, z  1 2'), {'ii': 'x+1/2,y+1,z-1/2'})
        self.assertEqual(self.ops('a: x, y–1,\nz; b: x+½, y\n+½, z + 1'), {'a': 'x,y-1,z', 'b': 'x+1/2,y+1/2,z+1'})
        self.assertEqual(self.ops('e: x+1, y+1, z; f: x+1, y, z. 1 Supplementary data are available'), {'e': 'x+1,y+1,z', 'f': 'x+1,y,z'})
        self.assertEqual(self.ops('Symmetry codes: 1 x, y, z; 2 x, y−1, z'), {'1': 'x,y,z', '2': 'x,y-1,z'})


class PrintedBondCodes(unittest.TestCase):
    """A paper's printed bond table against the .cif: the synthetic P2/m hydrate, Mg1 on the inversion centre
    with O1 2.000 Å away along b, its mirror image (x, −y+1, z) the second bond."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='bv_')
        self.st = B.Structure(_write(self.tmp, 'water.cif', WATER))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def check(self, rows, codes='', frame=None):
        return B.printed_bond_codes(self.st, rows, B.parse_code_notes(codes), frame)

    def test_each_outcome(self):
        ident = {s.label: list(s.frac) for s in self.st.sites}                 # the paper prints the .cif's coordinates
        r = self.check([('Mg1', 'O1', 2.000, None), ('Mg1', 'O1', 2.000, 'i')], '(i) x, −y+1, z')
        self.assertEqual((r['n'], r['coded'], r['ok']), (2, 1, 2))
        rutile = B.Structure(_write(self.tmp, 'rutile.cif', RUTILE))           # Ti–O1 1.980 is the listed O1; 1.949 only a 4₂ image
        r = B.printed_bond_codes(rutile, [('Ti1', 'O1', 1.980, None), ('Ti1', 'O1', 1.949, None)], {}, None)
        self.assertEqual((r['ok'], len(r['image'])), (1, 1), r)              # an image under another operator, printed without a code
        r = self.check([('Mg1', 'O1', 2.000, 'i')], '(i) −x+½, y, −z')
        self.assertEqual(len(r['wrong']), 1); self.assertIn('no operator of P 2/m', r['wrong'][0][1])
        r = self.check([('Mg1', 'O1', 2.000, 'i')], '(i) x, −y+2, z', frame=ident)
        self.assertEqual(len(r['translation']), 1)                             # the mirror, a cell too far
        r = self.check([('Mg1', 'O1', 2.000, 'i')], '(i) x, −y, z')
        self.assertEqual(r['ok'], 1)                                           # no frame: the operator is judged, not the translation
        r = self.check([('Mg1', 'O1', 2.000, 'ii')], '(i) x, −y+1, z')
        self.assertEqual(len(r['undefined']), 1)
        r = self.check([('Mg1', 'O1', 2.000, 'ii')])
        self.assertEqual(len(r['unread']), 1)
        self.assertEqual(self.check([('Mg1', 'Mg1', 2.000, None)])['n'], 0)    # no cation–cation 'bonds' (prose distances)
        lines = B.printed_bond_code_lines(self.check([('Mg1', 'O1', 2.000, 'i')], '(i) −x+½, y, −z'), None)
        self.assertTrue(lines[0].startswith('symmetry codes: 1 printed bonds'), lines)
        from pxrd_review.gui.review_gui import _calc_kind
        self.assertEqual({_calc_kind(ln.strip()) for ln in lines}, {'calcinfo'})   # information, never a red line


class ReaderKeepsTheCode(unittest.TestCase):
    def test_suffix(self):
        from pxrd_review import paper_bonds as PB
        self.assertEqual([PB._code(t) for t in ('O1vi', '–O3ii', 'O(2)′', 'Al1-O10Hiv', 'O12W', 'O4(×3)')],
                         ['vi', 'ii', '′', 'iv', None, None])
