"""Unit tests for pxrd_review.tables — publishable tables from a .cif (rutile, no corpus needed).

    python3 -m unittest tests.test_tables -v
"""
import os, re, shutil, tempfile, unittest

from pxrd_review import tables as T
from pxrd_review import bv_check as B
from tests.test_bv_check import RUTILE, HYDRATE, HYDRATE_H, _write


class Cells(unittest.TestCase):
    def test_rich_cells(self):
        c = T.C('Ca1–O3', T.R('3', 'sup'))
        self.assertEqual(T.plain(c), 'Ca1–O3³')
        self.assertEqual(T.html(c), 'Ca1–O3<sup>3</sup>')
        self.assertEqual(T.plain(T._elem_occ([B.Species('F', -1, 0.8), B.Species('O', -2, 0.2)])), 'F₀.₈₀O₀.₂₀')
        self.assertEqual(T.html(T.C(T.R('U', 'i'), T.R('eq', 'sub'))), '<i>U</i><sub>eq</sub>')

    def test_coord_and_symop_formatting(self):
        for s, want in (('0.666667', '⅔'), ('0.3333', '⅓'), ('0.5', '½'), ('0.25', '¼'), ('0', '0'), ('0.30479(5)', '0.30479(5)'), ('0.5000(2)', '0.5000(2)')):
            self.assertEqual(T.coord(s), want, s)
        rot, tr = B.parse_symop('-y+1/2, x+1/2, z+1/2')
        self.assertEqual(T.symop_string(rot, tr), '−y+½, x+½, z+½')
        rot, tr = B.parse_symop('x-y, x, -z')
        self.assertEqual(T.symop_string(rot, [tr[0] + 1, tr[1] - 1, tr[2] + 4 / 3]), 'x−y+1, x−1, −z+4/3')


class Rutile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='tbl_')
        cls.cif = _write(cls.tmp, 'rutile.cif', RUTILE)
        cls.st, cls.tabs = T.build(cls.cif, params='bo')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_tables_built(self):
        kinds = [k for k, _ in self.tabs]
        self.assertEqual(kinds, ['coords', 'bonds', 'bvs'])         # no H: no hydrogen-bond table
        coords = dict(self.tabs)['coords']
        self.assertEqual([T.plain(c) for c in coords['head']], ['Atoms', 's.o.', 'x', 'y', 'z', 'Ueq/Uiso'])  # no aniso loop: no U columns
        self.assertEqual([T.plain(c) for c in coords['rows'][0]], ['Ti1', 'Ti₁.₀₀', '0', '0', '0', '-'])
        self.assertEqual([T.plain(c) for c in coords['rows'][1]][2:4], ['0.30479', '0.30479'])
        self.assertIn('rutile', coords['caption'])

    def test_bond_table_from_loop(self):
        bonds = dict(self.tabs)['bonds']
        text = T.render_text([('bonds', bonds)])
        self.assertIn('Ti1–O1', text)
        self.assertIn('1.9485(5)', text)                              # esds from the .cif loop
        self.assertIn('<Ti–O>', text)                                 # one Ti site: mean by element
        self.assertIn('Symmetry codes: (3) −y+½, x+½, z+½', text)   # the .cif's operator number
        self.assertNotIn('no _geom_bond loop', bonds['note'])

    def test_symcode_legend(self):
        # the GUI's cheat sheet: n_klm = operator n, then k−5, l−5, m−5 cells along a, b, c; a pair the
        # table lists twice (Ti1–O1 at 1.9485 and 1.9800) is told apart by its distance
        leg = dict(self.tabs)['bonds']['symcodes']
        self.assertEqual(leg, [{'n': '3', 'code': '3_555', 'op': '−y+½, x+½, z+½', 'used': ['Ti1–O1 (1.9800)'],
                                'base_n': 3, 'base': '−y+½, x+½, z+½', 'shift': [0, 0, 0]}])
        codes = T.SymCodes(self.st)
        codes.begin_table('bonds')
        self.assertIsNone(codes.index('.', 'Ti1–O1', '1.9485(5)'))
        self.assertEqual(codes.index('3_466', 'Ti1–O1', '1.9800(2)'), '3')
        (c,) = codes.legend()
        self.assertEqual((c['op'], c['shift'], c['used']), ('−y−½, x+3/2, z+3/2', [-1, 1, 1], ['Ti1–O1 (1.9800)']))

    def test_symcode_labels_follow_the_cif_operators(self):
        # the superscript is the .cif's operator number; the same operator with another translation takes a prime
        codes = T.SymCodes(self.st)
        codes.begin_table('bonds')
        self.assertEqual([codes.index(c, 'Ti1–O%d' % i) for i, c in enumerate(['6_665', '4_565', '6_656', '1_555', '6_555'])],
                         ['6', '4', '6′', None, '6″'])
        self.assertEqual(codes.note(), 'Symmetry codes: (4) %s; (6) %s; (6′) %s; (6″) %s.'
                         % tuple(codes.codes[c] for c in ('4_565', '6_665', '6_656', '6_555')))
        self.assertEqual([c['n'] for c in codes.legend()], ['4', '6', '6′', '6″'])
        self.assertEqual(T.plain(T.C('O5', T.R('6′', 'sup'))), 'O5⁶′')
        # past three primes the CIF code itself (a P-1 table can need a dozen translations of one operator)
        self.assertEqual([codes.index(c) for c in ('6_556', '6_545', '6_655')], ['6‴', '6_545', '6_655'])
        self.assertTrue(codes.note().endswith('(6‴) %s; (6_545) %s; (6_655) %s.' % tuple(codes.codes[c] for c in ('6_556', '6_545', '6_655'))))
        self.assertEqual(T.plain(T.C('O5', T.R('6_545', 'sup'))), 'O5^(6_545)')

    def test_symcode_legend_keeps_a_non_nklm_code_s_bonds(self):
        codes = T.SymCodes(self.st); codes.begin_table('bonds')
        codes.index('#1', 'Ti1–O1'); codes.index('3_555', 'Ti1–O2'); codes.index('#1', 'Ti1–O3')
        self.assertEqual([(c['code'], c['used']) for c in codes.legend()], [('3_555', ['Ti1–O2']), ('#1', ['Ti1–O1', 'Ti1–O3'])])   # n_klm codes in operator order, others after

    def test_bvs_table(self):
        bvs = dict(self.tabs)['bvs']
        rows = [[T.plain(c) for c in r] for r in bvs['rows']]
        self.assertEqual([T.plain(c) for c in bvs['head']], ['Atom', 'Ti1', 'Σan'])
        self.assertEqual(rows[0][0], 'O1')
        self.assertIn('0.70×4↓×2→', rows[0][1])
        self.assertEqual(rows[-1][:2], ['Σcat', '4.07'])
        self.assertIn("Brese and O'Keeffe (1991)", bvs['note'])       # the set asked for, not the file's ref id
        self.assertIn('Multiplicity is indicated by', bvs['note'])
        self.assertNotIn('Brown and Altermatt', bvs['note'])

    def test_render_and_word(self):
        h = T.render_html(self.tabs)
        self.assertIn('<sup>3</sup>', h); self.assertIn('data-kind="bvs"', h)
        self.assertNotIn('<script', h)
        out = os.path.join(self.tmp, 'out')
        st, tabs, text = T.run(self.cif, word=True, params='bo', out_dir=out, quiet=True)
        self.assertTrue(os.path.exists(os.path.join(out, 'rutile_tables.txt')))
        from docx import Document
        d = Document(os.path.join(out, 'rutile_tables.docx'))
        self.assertEqual(len(d.tables), 3)
        sup = [r for row in d.tables[1].rows for p in row.cells[0].paragraphs for r in p.runs if r.font.superscript]
        self.assertTrue(sup, 'the symmetry code is a superscript run')


class Journals(unittest.TestCase):
    def test_journal_styles(self):
        tmp = tempfile.mkdtemp(prefix='tbl_')
        try:
            cif = _write(tmp, 'rutile.cif', RUTILE)
            st, tabs = T.build(cif, params='bo', journal_key='cjmp')
            coords, bonds, bvs = dict(tabs)['coords'], dict(tabs)['bonds'], dict(tabs)['bvs']
            self.assertEqual(coords['label'], 'TABLE 1.')
            self.assertEqual(coords['caption'], 'ATOM COORDINATES AND DISPLACEMENT PARAMETERS (Å²) FOR RUTILE')
            self.assertTrue(bonds['note'].startswith('Symmetry operators:'))
            self.assertEqual([T.plain(c) for c in bvs['rows'][-1]][:1], ['Sum'])
            self.assertIn('font-family:Arial', T.render_html(tabs))
            st, tabs = T.build(cif, params='bo', journal_key='minmag')
            coords = dict(tabs)['coords']
            self.assertEqual([T.plain(c) for c in coords['head']][:4], ['Site', 's.o.', 'x/a', 'y/b'])
            self.assertEqual(coords['label'], 'Table 1.')
            st, tabs = T.build(cif, params='bo')                     # the default: the owner's style
            self.assertEqual([T.plain(c) for c in dict(tabs)['coords']['head']][:1], ['Atoms'])
            self.assertEqual(T.build(cif, params='bo', journal_key='nope')[1][0][1]['label'], 'Table 1.')   # unknown -> default
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Hydrate(unittest.TestCase):
    def test_hbond_columns_and_proposed_contacts(self):
        tmp = tempfile.mkdtemp(prefix='tbl_')
        try:
            cif = _write(tmp, 'h.cif', HYDRATE)
            st, tabs = T.build(cif)
            d = dict(tabs)
            self.assertEqual([k for k, _ in tabs], ['coords', 'bonds', 'hbonds', 'bvs'])
            self.assertIn('proposed', d['hbonds']['caption'].lower())
            self.assertIn('PROPOSED', d['hbonds']['note'])
            head = [T.plain(c) for c in d['bvs']['head']]
            self.assertEqual(head, ['Atom', 'Ca1', 'Donor', 'vu', 'H bond', 'Σan'])
            rows = {T.plain(r[0]): [T.plain(c) for c in r] for r in d['bvs']['rows']}
            s = B.fi_valence(2.8)
            self.assertEqual(rows['O2'][2:5], ['OW1', '%.2f' % s, '-'])
            self.assertEqual(rows['O2'][-1], '%.2f' % s)                          # Σan = accepted only (no cation)
            self.assertEqual(rows['OW1'][2:5], ['-', '-', '-'])                   # donors: nothing deducted
            self.assertIn('Ferraris and Ivaldi (1988)', d['bvs']['note'])
            self.assertIn('not located', d['bvs']['note'])
            # H located: the geometry table, and no 'proposed' wording
            st, tabs = T.build(_write(tmp, 'hh.cif', HYDRATE_H))
            d = dict(tabs)
            self.assertIn('OW1–H1⋯O2', T.render_text([('hbonds', d['hbonds'])]))
            self.assertNotIn('not located', d['bvs']['note'])
            # no H at all
            st, tabs = T.build(cif, include_h=False)
            self.assertEqual([k for k, _ in tabs], ['coords', 'bonds', 'bvs'])
            st, tabs = T.build(cif, hbond='none')
            self.assertNotIn('Donor', [T.plain(c) for c in dict(tabs)['bvs']['head']])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Computed(unittest.TestCase):
    def test_bonds_without_loop(self):
        tmp = tempfile.mkdtemp(prefix='tbl_')
        try:
            cif = _write(tmp, 'r.cif', RUTILE.split('loop_\n_geom_bond')[0])   # drop the bond loop
            st, tabs = T.build(cif, params='bo')
            bonds = dict(tabs)['bonds']
            text = T.render_text([('bonds', bonds)])
            self.assertIn('no _geom_bond loop', bonds['note'])
            self.assertIn('1.949', text); self.assertIn('1.980', text)
            self.assertEqual(text.count('Ti1–O1'), 6)                 # every symmetry-equivalent bond, each with its code
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()


CAOS = """data_caos
_chemical_name_mineral testite
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
Ca1 Ca 0 1.0 0
O1 O 0.3 1.0 0
S1 S 0 0.65 0
"""


class BondTableFromTheBonds(unittest.TestCase):
    """Table 2 lists exactly the bonds the bond-valence table counts: the loop's distances (with esds) where it lists
    them, computed ones where it does not; a mean per anion; codes measured in the .cif's own frame."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='tbl2_')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_bond_the_loop_lacks_is_computed(self):
        cif = _write(self.tmp, 'r.cif', RUTILE.replace('Ti1 O1 1.9800(5) 3_555\n', ''))   # the loop keeps the 1.9485 only
        st, tabs = T.build(cif, params='bo')
        b = dict(tabs)['bonds']; text = T.render_text([('bonds', b)])
        self.assertIn('1.9485(5)', text)                                            # the loop's, with its esd, as the loop writes it (once)
        self.assertEqual(re.findall(r'Ti1–O1(\S*)\s+1\.980\b', text), ['', '²'], text)   # the ×2 the loop lacked, one row per image, no esd:
                                                                                     # O1 as listed (no code) and its 2_555 image
        self.assertIn('without an esd are computed', b['note'])
        self.assertEqual(T.coord('1.25'), '1¼'); self.assertEqual(T.coord('-1.5'), '-1½'); self.assertEqual(T.coord('0.75'), '¾')

    def test_mean_per_anion_and_the_cif_frame(self):
        cif = _write(self.tmp, 'caos.cif', CAOS)
        st, tabs = T.build(cif)
        text = T.render_text([('bonds', dict(tabs)['bonds'])])
        self.assertIn('<Ca–O>', text); self.assertIn('<Ca–S>', text); self.assertNotIn('O/S', text)
        self.assertIn('Ca1–O1  ', text)                       # O1 as listed (y = 1.0 like Ca1): no code — a wrapped Ca1 had given it one
        self.assertNotIn('Symmetry codes', dict(tabs)['bonds']['note'])

    def test_site_options_move_both_tables(self):
        cif = _write(self.tmp, 'rutile.cif', RUTILE)
        st, tabs = T.build(cif, params='bo', sites='Ti1 max=1.96; O1 comp=O0.9F0.1')
        text = T.render_text([('bonds', dict(tabs)['bonds'])])
        self.assertNotIn('1.9800', text)                                            # past Ti1's longest bond: out of both tables
        bvs = dict(tabs)['bvs']
        self.assertIn('O1 taken as O0.90F0.10', bvs['note']); self.assertIn('Bonds to Ti1 counted up to 1.96 Å', bvs['note'])
        self.assertEqual([T.plain(c) for c in dict(tabs)['coords']['rows'][1]][1], 'O₁.₀₀')   # the coordinates stay the .cif's
        meta = {m['label']: m for m in bvs['sites']}
        self.assertEqual((meta['Ti1']['kind'], meta['Ti1']['max'], meta['O1']['species']), ('cation', 1.96, 'O0.90F0.10'))
        self.assertEqual({(p['cation'], p['anion']) for p in meta['Ti1']['pairs']}, {('Ti', 'O'), ('Ti', 'F')})
