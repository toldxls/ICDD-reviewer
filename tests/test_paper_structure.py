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


class SitesWithPage(unittest.TestCase):
    def test_paper_sites_with_page(self):
        import pymupdf
        tmp = tempfile.mkdtemp(prefix='ps_'); path = os.path.join(tmp, 'p.pdf')
        try:
            doc = pymupdf.open(); doc.new_page(width=595, height=842)          # a blank first page: the table is on page 2
            page = doc.new_page(width=595, height=842); y = 60
            for cells in ([(40, 'Atom'), (90, 'x'), (150, 'y'), (210, 'z'), (270, 'Ueq')],
                          [(40, 'Ti1'), (90, '0.00000'), (150, '0.00000'), (210, '0.00000'), (270, '0.0050(2)')],
                          [(40, 'O1'), (90, '0.30479'), (150, '0.30479'), (210, '0.00000'), (270, '0.0060(2)')],
                          [(40, 'O2'), (90, '0.69521'), (150, '0.69521'), (210, '0.00000'), (270, '0.0060(2)')]):
                for x, t in cells:
                    page.insert_text((x, y), t, fontsize=9)
                y += 13
            doc.save(path); doc.close()
            rows, pno = PS.paper_sites(path, with_page=True)
            self.assertEqual((len(rows), pno), (3, 2))
            self.assertEqual(len(PS.paper_sites(path)), 3)                    # the default return is unchanged
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class ReaderFonts(unittest.TestCase):
    """What the font and the layout do to a coordinates table."""

    def _pdf(self, rows, header=('Atom', 'x', 'y', 'z', 'Ueq'), xs=(40, 90, 150, 210, 270)):
        import pymupdf
        tmp = tempfile.mkdtemp(prefix='ps_'); path = os.path.join(tmp, 'p.pdf')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        doc = pymupdf.open(); page = doc.new_page(width=595, height=842); y = 60
        for cells in [header] + list(rows):
            for x, t in zip(xs, cells):
                page.insert_text((x, y), t, fontsize=9)
            y += 13
        doc.save(path); doc.close()
        return path

    def test_a_dash_typed_negative_coordinate(self):
        for d in ('-', '–', '−', '—'):
            self.assertAlmostEqual(PS._val(d + '0.12647(12)'), -0.12647, msg=repr(d))
            self.assertAlmostEqual(PS._val(d + '½'), -0.5, msg=repr(d))
        # the pdf itself with plain hyphens: the base font has no en dash (it prints a middle dot for one)
        rows = PS.paper_sites(self._pdf([('U1', '-0.12647(12)', '-0.74999(18)', '0.5003(2)', '0.0291(3)'), ('S1', '0.2545(13)', '-0.9989(9)', '0.5974(11)', '0.027(4)'),
                                         ('Al1', '1', '-½', '1', '0.034(7)'), ('O1', '-0.045(4)', '-0.821(2)', '0.6733(7)', '0.0257(9)')]))
        self.assertEqual([(r[0], round(r[1], 5), round(r[2], 5)) for r in rows], [('U1', -0.12647, -0.74999), ('S1', 0.2545, -0.9989), ('Al1', 1.0, -0.5), ('O1', -0.045, -0.821)])

    def test_an_occupancy_column_before_x(self):
        rows = [('Na1', '0.62(3)', '0.7763(8)', '0.0146(16)', '0.3690(9)', '0.050(4)'), ('Na2', '0.60(3)', '0.7226(7)', '0.3510(15)', '0.2409(8)', '0.040(4)'),
                ('As1', '1.0', '0.86189(9)', '0.79611(10)', '0.56879(9)', '0.0121(3)'), ('O1', '1.0', '0.9151(5)', '0.2263(9)', '0.6221(5)', '0.021(2)')]
        # with the header: the header read knows the column; without one: the shorter first number is the occupancy
        for header in (('Atom', 'Occupancy', 'x/a', 'y/b', 'z/c', 'Ueq'), ('', '', '', '', '', '')):
            got = PS.paper_sites(self._pdf(rows, header=header, xs=(40, 85, 150, 215, 280, 345)))
            self.assertEqual([(r[0], round(r[1], 4), round(r[3], 4)) for r in got], [('Na1', 0.7763, 0.369), ('Na2', 0.7226, 0.2409), ('As1', 0.8619, 0.5688), ('O1', 0.9151, 0.6221)], header)

    def test_closure_by_count(self):
        from pxrd_review import bv_check as B
        from tests.test_bv_check import HYDRATE
        tmp = tempfile.mkdtemp(prefix='ps_'); self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        cif = os.path.join(tmp, 'h.cif'); open(cif, 'w').write(HYDRATE)                       # Ca1 + O1, OW1, O2, O3: 1 cation to 4 anions
        st = B.Structure(cif)
        self.assertAlmostEqual(PS.closure_count(st, {'Ca': 1, 'O': 4, 'H': 2}), 0.0)
        self.assertAlmostEqual(PS.closure_count(st, {'Ca': 1, 'Mg': 1, 'O': 4}), 0.5)          # a cation the table does not hold: 50 % off
        self.assertIsNone(PS.closure_count(st, {}))


class SplitSites(unittest.TestCase):
    """'Fe1/Al1 0.84/0.16(2) 0 0.1471(3) 0': a split site is a row of the table, not four misses that end it."""

    def test_label_and_element(self):
        for lab in ('Fe1/Al1', 'Ca/Mg', 'K/O', 'O6/K1', 'M1/M2'):
            self.assertTrue(PS._label_ok(lab), lab)
        self.assertFalse(PS._label_ok('0.84/0.16'))
        self.assertEqual(PS.site_element('Fe1/Al1', '0.0102(7)'), 'Fe')
        self.assertEqual(PS.site_element('Ca/Mg', 'Ca0.62Mg0.38'), 'Ca')

    def test_the_table_reads_through_them(self):
        rows = [('Na1', '0.62(3)', '0.7763(8)', '0.0146(16)', '0.3690(9)', '0.050(4)'), ('Na2', '0.60(3)', '0.7226(7)', '0.3510(15)', '0.2409(8)', '0.040(4)'),
                ('Na3', '0.27(4)', '0', '0.560(4)', '0', '0.038(12)'),
                ('Fe1/Al1', '0.84/0.16(2)', '0', '0.1471(3)', '0', '0.0102(7)'), ('Fe2/Al2', '0.84/0.16(2)', '0', '0.6130(3)', '½', '0.0154(9)'),
                ('Fe3/Al3', '0.843/0.157(17)', '0.76439(10)', '0.1144(2)', '0.58682(13)', '0.0159(6)'), ('Fe4/Al4', '0.904/0.096(17)', '0.73846(9)', '0.14537(19)', '0.91342(12)', '0.0112(5)'),
                ('As1', '1', '0.86189(7)', '0.79611(17)', '0.56879(9)', '0.0197(4)'), ('As2', '1', '0.63805(6)', '0.85448(16)', '0.51559(10)', '0.0192(3)')]
        got = ReaderFonts._pdf(self, rows, header=('Atom', 'Occupancy', 'x/a', 'y/b', 'z/c', 'Ueq'), xs=(40, 85, 150, 215, 280, 345))
        sites = PS.paper_sites(got)
        self.assertEqual([r[0] for r in sites], [r[0] for r in rows])
        self.assertEqual([round(r[1], 5) for r in sites][3:6], [0.0, 0.0, 0.76439])


class ContinuedAndOccupied(unittest.TestCase):
    """A table continued over a page break is one table; an occupancy printed before x is read,
    and a site a third occupied is left out of the instability index."""

    def _two_page(self, cont_word):
        import pymupdf
        tmp = tempfile.mkdtemp(prefix='ps_'); path = os.path.join(tmp, 'p.pdf')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        doc = pymupdf.open()
        for pno, (top, rows) in enumerate((('Table 4. Atom coordinates for testite.', [('Atom', 'x', 'y', 'z', 'Ueq'), ('Sr1', '0.12345(2)', '0.25000(3)', '0.50000(2)', '0.010(1)'),
                                                                                     ('Ca1', '0.62345(2)', '0.75000(3)', '0.00000(2)', '0.011(1)'), ('B1', '0.33333(4)', '0.66667(4)', '0.12500(4)', '0.009(1)')]),
                                           (cont_word, [('B2', '0.83333(4)', '0.16667(4)', '0.62500(4)', '0.009(1)'), ('O1', '0.11111(5)', '0.22222(5)', '0.33333(5)', '0.012(2)'),
                                                        ('O2', '0.44444(5)', '0.55555(5)', '0.66666(5)', '0.012(2)'), ('O3', '0.77777(5)', '0.88888(5)', '0.99999(5)', '0.012(2)')]))):
            page = doc.new_page(width=595, height=842); y = 60
            page.insert_text((40, y), top, fontsize=9); y += 13
            for cells in rows:
                for x, t in zip((40, 90, 150, 210, 270), cells):
                    page.insert_text((x, y), t, fontsize=9)
                y += 13
        doc.save(path); doc.close()
        return path

    def test_continued_over_the_page(self):
        rows, pno = PS.paper_sites(self._two_page('Table 4. Cont.'), with_page=True)
        self.assertEqual(([r[0] for r in rows], pno), (['Sr1', 'Ca1', 'B1', 'B2', 'O1', 'O2', 'O3'], 1))
        rows, _p = PS.paper_sites(self._two_page('Some other prose at the top of the page.'), with_page=True)
        self.assertEqual([r[0] for r in rows], ['Sr1', 'Ca1', 'B1', 'B2', 'O1', 'O2', 'O3'])        # header-less and beginning the page: a continuation too

    def test_occupancy_read_and_the_index_spares_a_disordered_site(self):
        self.assertEqual(PS._occupancy('occ=0.62(3) 0.050(4)'), 0.62); self.assertEqual(PS._occupancy('occ=1 0.0197(4)'), 1.0)
        self.assertIsNone(PS._occupancy('0.0197(4)')); self.assertIsNone(PS._occupancy('0.62(3) 0.050(4)')); self.assertIsNone(PS._occupancy('Ca0.674Mn0.326'))   # untagged: Ueq, or an element-weighted occupancy
        rows = ReaderFonts._pdf(self, [('Na1', '0.27(4)', '0.00000', '0.56000(4)', '0.00000', '0.038(12)'), ('As1', '1', '0.86189(7)', '0.79611(17)', '0.56879(9)', '0.0197(4)')],
                                header=('Atom', 'Occupancy', 'x/a', 'y/b', 'z/c', 'Ueq'), xs=(40, 85, 150, 215, 280, 345))
        got = PS.paper_sites(rows)
        self.assertEqual([(r[0], PS._occupancy(r[4])) for r in got], [('Na1', 0.27), ('As1', 1.0)])
        cif = PS.synth_cif([10, 10, 10, 90, 90, 90], '_space_group_symop_operation_xyz', ['x, y, z'], [('Na1', 'Na', 0, 0.56, 0), ('As1', 'As5+', 0.86, 0.79, 0.57)], occ={'Na1': 0.27})
        self.assertIn('_atom_site_occupancy', cif); self.assertIn('Na1 Na 0.00000 0.56000 0.00000 0.270', cif); self.assertIn('As1 As5+ 0.86000 0.79000 0.57000 1.000', cif)


class SidewaysTable(unittest.TestCase):
    """A landscape table on a portrait page is typeset rotated; its rows run up the page. The page
    model turns such text into its own reading frame, and the table reads as any other."""

    def _pdf(self, rotate):
        import pymupdf
        tmp = tempfile.mkdtemp(prefix='ps_'); path = os.path.join(tmp, 'p.pdf')
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        doc = pymupdf.open(); page = doc.new_page(width=595, height=842)
        page.insert_text((40, 60), 'Prose at the top of the page, upright.', fontsize=9)
        rows = [('Atom', 'x', 'y', 'z', 'Ueq'), ('Ti1', '0.00000', '0.00000', '0.00000', '0.0050(2)'), ('O1', '0.30479(5)', '0.30479(5)', '0.00000', '0.0060(2)'),
                ('O2', '0.69521(5)', '0.69521(5)', '0.00000', '0.0060(2)'), ('Ti2', '0.50000', '0.50000', '0.50000', '0.0050(2)')]
        for i, cells in enumerate(rows):
            for j, t in enumerate(cells):
                if rotate == 90:                                                   # the text reads upward; rows step across the page
                    page.insert_text((80 + i * 14, 700 - j * 60), t, fontsize=9, rotate=90)
                else:
                    page.insert_text((40 + j * 60, 100 + i * 14), t, fontsize=9)
        doc.save(path); doc.close()
        return path

    def test_rotated_rows_read_as_rows(self):
        from pxrd_review import paper_extract as PE
        got = PS.paper_sites(self._pdf(90))
        self.assertEqual([(r[0], round(r[1], 5)) for r in got], [('Ti1', 0.0), ('O1', 0.30479), ('O2', 0.69521), ('Ti2', 0.5)])
        page = PE._pages(self._pdf(90))[0]
        self.assertTrue(any(l.get('rot') for l in page) and any(not l.get('rot') for l in page))
        self.assertTrue(all(w[0] >= PE.ROT_X for l in page if l.get('rot') for w in l['w']))       # the two frames never mix
        self.assertEqual([(r[0], round(r[1], 5)) for r in PS.paper_sites(self._pdf(0))][:2], [('Ti1', 0.0), ('O1', 0.30479)])


class BarredTwinAndOccupancyTag(unittest.TestCase):
    def test_a_placed_coordinate_is_never_the_occupancy(self):
        # the header letter sits RIGHT of the value's centre (values left-aligned under a centred header): x is still x, not 'occ='
        rows = [('Ca1', '0.82421(2)', '0.51657(2)', '0.38114(3)', '0.0078(3)'), ('Na1', '0.49261(5)', '0.16604(5)', '0.24880(9)', '0.0188(5)'), ('O1', '0.11111(5)', '0.22222(5)', '0.33333(5)', '0.012(2)')]
        got = PS.paper_sites(ReaderFonts._pdf(self, rows, header=('Atom', 'x', 'y', 'z', 'Ueq'), xs=(40, 100, 160, 220, 280)))
        self.assertEqual([(r[0], round(r[1], 5), PS._occupancy(r[4])) for r in got], [('Ca1', 0.82421, None), ('Na1', 0.49261, None), ('O1', 0.11111, None)])

    def test_the_barred_twin_is_tried(self):
        from pxrd_review import symops as SO
        self.assertTrue(SO.lookup('P-1') and SO.lookup('P1'))
        # a P1̄ structure whose overbar the text lost: built in P1 its sums come out half; the twin wins
        import pymupdf
        tmp = tempfile.mkdtemp(prefix='ps_'); path = os.path.join(tmp, 'p.pdf'); self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        doc = pymupdf.open(); page = doc.new_page(width=595, height=842); y = 60
        # rutile's atoms in P1 are six; given as the three of a P-1 description they would be read as half a cell —
        # instead a made-up centrosymmetric pair: NaCl-like Na at 0,0,0 and Cl at 1/2,1/2,1/2 in a cubic cell, symbol 'P1' (meaning P-1)
        for ln in ('Halite from Nowhere', 'Halite is cubic, space group P1, a = 5.6402(2), b = 5.6402(2), c = 5.6402(2) A, V = 179.4 A3, Z = 4.',
                   'The empirical formula, calculated on the basis of 1 Cl apfu, is Na1.00Cl1.00.', 'Table 2. Atom coordinates for halite.'):
            page.insert_text((40, y), ln, fontsize=9); y += 13
        for cells in (('Atom', 'x', 'y', 'z', 'Ueq'), ('Na1', '0.00000', '0.00000', '0.00000', '0.0100(2)'), ('Na2', '0.50000', '0.50000', '0.00000', '0.0100(2)'),
                      ('Cl1', '0.50000', '0.00000', '0.00000', '0.0100(2)'), ('Cl2', '0.00000', '0.50000', '0.00000', '0.0100(2)')):
            for x, t in zip((40, 100, 160, 220, 280), cells):
                page.insert_text((x, y), t, fontsize=9)
            y += 13
        doc.save(path); doc.close()
        st, info = PS.build(path)
        self.assertIsNotNone(info.get('gii'))
        if st is not None:
            PS.discard(info)


class SymbolAndCellAgree(unittest.TestCase):
    def test_the_symbol_a_printed_cell_allows_is_the_papers(self):
        from pxrd_review import symops as SO
        self.assertEqual(SO.crystal_system('P-1'), 'triclinic'); self.assertEqual(SO.crystal_system('I-42d'), 'tetragonal'); self.assertEqual(SO.crystal_system('C2/c'), 'monoclinic')
        self.assertEqual(SO.cell_system({'a': 11.9, 'b': 12.7, 'c': 6.7, 'α': 90, 'β': 113.3, 'γ': 90}), {'monoclinic'})
        self.assertEqual(SO.cell_system({'a': 6.8, 'b': 6.8, 'c': 18.6, 'α': 90, 'β': 90, 'γ': 90}), {'tetragonal', 'orthorhombic'})
        self.assertEqual(SO.cell_system({'a': 15.7, 'b': 15.7, 'c': 47.8, 'α': 90, 'β': 90, 'γ': 120}), {'trigonal', 'hexagonal'})


class AnglesAsLatin(unittest.TestCase):
    def test_a_triclinic_cell_whose_angles_arrive_as_a_b_c(self):
        from pxrd_review import paper_extract as PE
        t = ('Pseudodickthomssenite is triclinic, P1, a = 7.3566(6) A, b = 9.4672(9) A, c = 9.5529(9) A, a = 104.205(7)8, b = 100.786(7)8, c = 100.157(7)8, '
             'V = 616.08(10) A3, and Z = 2.')
        cells = [PE._cell_str(c) for _x, c in PE._paper_cells(t)]
        self.assertIn('a=7.3566, b=9.4672, c=9.5529, α=104.205, β=100.786, γ=100.157', cells, cells)
        self.assertFalse(any(c.startswith('a=104') for c in cells), cells)                  # the angles are not a cell


class PrintedBondsDecide(unittest.TestCase):
    """The paper's own bond distances are the direct check of its coordinates, cell and symbol: the
    build picks the cell that reproduces them, and the verdict rests on the count."""

    def _pdf(self, cell_line, bonds=True):
        import pymupdf
        tmp = tempfile.mkdtemp(prefix='ps_'); path = os.path.join(tmp, 'p.pdf'); self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        doc = pymupdf.open(); page = doc.new_page(width=595, height=842); y = 60
        for ln in ('Rutile from Nowhere', cell_line, 'The empirical formula, calculated on the basis of 2 O apfu, is Ti1.00O2.', 'Table 2. Atom coordinates for rutile.'):
            page.insert_text((40, y), ln, fontsize=9); y += 13
        rows = (('Atom', 'x', 'y', 'z', 'Ueq'), ('Ti1', '0.00000', '0.00000', '0.00000', '0.0050(2)'), ('Ti2', '0.50000', '0.50000', '0.50000', '0.0050(2)'),
                ('O1', '0.30479', '0.30479', '0.00000', '0.0060(2)'), ('O2', '0.69521', '0.69521', '0.00000', '0.0060(2)'),
                ('O3', '0.80479', '0.19521', '0.50000', '0.0060(2)'), ('O4', '0.19521', '0.80479', '0.50000', '0.0060(2)'))
        for cells in rows:
            for x, t in zip((40, 100, 160, 220, 280), cells):
                page.insert_text((x, y), t, fontsize=9)
            y += 13
        if bonds:
            y += 8; page.insert_text((40, y), 'Table 3. Selected bond lengths (A) for rutile.', fontsize=9); y += 13
            for c, a, d in (('Ti1', 'O1', '1.980(1)'), ('Ti1', 'O2', '1.980(1)'), ('Ti1', 'O3', '1.949(1)'), ('Ti1', 'O4', '1.949(1)'), ('Ti2', 'O3', '1.980(1)'), ('Ti2', 'O1', '1.949(1)')):
                page.insert_text((40, y), c, fontsize=9); page.insert_text((70, y), '-', fontsize=9); page.insert_text((80, y), a, fontsize=9); page.insert_text((120, y), d, fontsize=9); y += 13
        doc.save(path); doc.close()
        return path

    def test_the_cell_that_reproduces_the_bonds_wins(self):
        from pxrd_review import paper_extract as PE
        # two cells printed: a wrong one first (another phase's), the right one after — the bonds pick the right one
        p = self._pdf('Rutile is tetragonal, space group P1, a = 5.1000(2), b = 5.1000(2), c = 3.2000(1) A; and a = 4.5937(2), b = 4.5937(2), c = 2.9587(1) A, Z = 2.')
        r = PE.check_paper(p, None, None); F = r['fields']
        self.assertEqual((F['coords']['status'], F['coords']['verified_by']), ('agrees', 'bonds'), r['lines'])
        self.assertIn('6 of the 6 bond distances', F['coords']['detail'])
        p = self._pdf('Rutile is tetragonal, space group P1, a = 5.1000(2), b = 5.1000(2), c = 3.2000(1) A, Z = 2.')   # only the wrong cell: the bonds refuse it
        r = PE.check_paper(p, None, None); F = r['fields']
        self.assertEqual((F['coords']['status'], F['coords']['verified_by']), ('unverified', 'bonds'), r['lines'])
        self.assertIn('printed', F['coords']['detail'])


class LabelsAndContinuations(unittest.TestCase):
    def test_footnote_marks_leave_the_label(self):
        got = PS.paper_sites(ReaderFonts._pdf(self, [('Mn*', '0.12345(2)', '0.25000(3)', '0.50000(2)', '0.010(1)'), ('S**', '0.62345(2)', '0.75000(3)', '0.00000(2)', '0.011(1)'), ('O1', '0.33333(4)', '0.66667(4)', '0.12500(4)', '0.009(1)')]))
        self.assertEqual([r[0] for r in got], ['Mn', 'S', 'O1'])

    def test_a_continuation_that_repeats_its_header(self):
        prev = [('K1', 0, 0, 0, ''), ('O1', 0, 0, 0, ''), ('O20', 0, 0, 0, '')]
        self.assertTrue(PS._continues(prev, [('O21', 0, 0, 0, ''), ('O22', 0, 0, 0, ''), ('O46', 0, 0, 0, '')]))
        self.assertFalse(PS._continues(prev, [('O1', 0, 0, 0, ''), ('O2', 0, 0, 0, '')]))              # another mineral's table starts over
        self.assertFalse(PS._continues(prev, [('Si1', 0, 0, 0, ''), ('Al1', 0, 0, 0, '')]))            # new elements: not a continuation

    def test_the_site_name_beside_the_element_stays_on_the_label(self):
        # 'Mn (X)' and 'Mn (M1)' are two sites, not one repeated; 'Cu(M1)*' is a label; 'MH', 'AP' are sites named by two letters
        rows = [('Mn', '(X)', '0.25', '0.96332(11)', '0', '0.0193(2)'), ('Mn', '(M1)', '0.25', '0.46379(10)', '0', '0.0119(2)'),
                ('Al1', '(M3a)', '0', '0', '0', '0.0061(3)'), ('Cu(M1)*', '', '0.5', '0', '0.5', '0.0218(9)'),
                ('MH', '', '0.09453(18)', '0.66029(10)', '0.19328(3)', '0.0074(2)'), ('AP', '', '0.5967(2)', '0.66042(11)', '0.18986(3)', '0.0096(2)'),
                ('O1', '', '0.26524(15)', '0.2062(3)', '0.1480(2)', '0.0260(6)')]
        got = PS.paper_sites(ReaderFonts._pdf(self, rows, header=('Atom', '', 'x', 'y', 'z', 'Ueq'), xs=(40, 62, 100, 160, 220, 280)))
        self.assertEqual([r[0] for r in got], ['Mn(X)', 'Mn(M1)', 'Al1(M3a)', 'Cu(M1)', 'MH', 'AP', 'O1'])

    def test_a_coordinate_printed_past_one_under_its_header(self):
        rows = [('U2', '1.06477(6)', '0.24559(8)', '0.30101(10)', '0.0123(4)'), ('U4', '0.64714(6)', '0.73698(7)', '1.08167(8)', '0.0112(4)'),
                ('O1', '1.0199(11)', '0.5046(15)', '1.1339(18)', '0.037(7)'), ('O2', '0.7190(8)', '0.7491(12)', '0.6794(13)', '0.009(4)')]
        got = PS.paper_sites(ReaderFonts._pdf(self, rows))
        self.assertEqual([(r[0], round(r[1], 5), round(r[3], 5)) for r in got], [('U2', 1.06477, 0.30101), ('U4', 0.64714, 1.08167), ('O1', 1.0199, 1.1339), ('O2', 0.719, 0.6794)])

    def test_the_next_caption_ends_the_table(self):
        import pymupdf
        tmp = tempfile.mkdtemp(prefix='ps_'); path = os.path.join(tmp, 'p.pdf'); self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        doc = pymupdf.open(); page = doc.new_page(width=595, height=842); y = 60
        rows = [('Atom', 'x', 'y', 'z', 'Ueq'), ('K1', '0.12345(2)', '0.25000(3)', '0.50000(2)', '0.010(1)'), ('O1', '0.62345(2)', '0.75000(3)', '0.00000(2)', '0.011(1)'), ('O2', '0.33333(4)', '0.66667(4)', '0.12500(4)', '0.009(1)'),
                ('Table 6. Anisotropic displacement parameters.',), ('Atom', 'U11', 'U22', 'U33', 'U12'), ('K1', '0.0123(2)', '0.0250(3)', '0.0500(2)', '0.0010(1)'), ('O1', '0.0234(2)', '0.0750(3)', '0.0100(2)', '0.0011(1)')]
        for cells in rows:
            for x, t in zip((40, 90, 150, 210, 270), cells):
                page.insert_text((x, y), t, fontsize=9)
            y += 13
        doc.save(path); doc.close()
        self.assertEqual([r[0] for r in PS.paper_sites(path)], ['K1', 'O1', 'O2'])

    def test_a_continuation_page_that_runs_into_the_next_table(self):
        import pymupdf
        tmp = tempfile.mkdtemp(prefix='ps_'); path = os.path.join(tmp, 'p.pdf'); self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        doc = pymupdf.open()
        for rows in ([('Atom', 'x', 'y', 'z', 'Ueq'), ('K1', '0.12345(2)', '0.25000(3)', '0.50000(2)', '0.010(1)'), ('K2', '0.22345(2)', '0.35000(3)', '0.60000(2)', '0.010(1)'), ('O1', '0.62345(2)', '0.75000(3)', '0.00000(2)', '0.011(1)'), ('O2', '0.33333(4)', '0.66667(4)', '0.12500(4)', '0.009(1)')],
                     [('Table 5. (continued).',), ('Atom', 'x', 'y', 'z', 'Ueq'), ('O3', '0.42345(2)', '0.35000(3)', '0.40000(2)', '0.010(1)'), ('O4', '0.52345(2)', '0.45000(3)', '0.30000(2)', '0.011(1)'),
                      ('K1', '0.0123(2)', '0.0250(3)', '0.0500(2)', '0.0010(1)'), ('O1', '0.0234(2)', '0.0750(3)', '0.0100(2)', '0.0011(1)')]):
            page = doc.new_page(width=595, height=842); y = 60
            for cells in rows:
                for x, t in zip((40, 90, 150, 210, 270), cells):
                    page.insert_text((x, y), t, fontsize=9)
                y += 13
        doc.save(path); doc.close()
        self.assertEqual([r[0] for r in PS.paper_sites(path)], ['K1', 'K2', 'O1', 'O2', 'O3', 'O4'])

    def test_bond_labels_answer_to_the_site_name_and_the_element(self):
        self.assertEqual(PS._label_keys('Mn (X)'), ['MNX', 'X', 'MN'])
        self.assertEqual(PS._label_keys('Al1(M3a)'), ['AL1M3A', 'M3A', 'AL1'])
        self.assertEqual(PS._label_keys('O(1)'), ['O1', None, None])
        class Site:
            def __init__(self, label): self.label = label
        class St:
            sites = [Site('Mn(X)'), Site('Mn(M1)'), Site('Al1(M3a)'), Site('Al2(M3b)'), Site('O1'), Site('O5')]
            def neighbours(self, s, r):
                return {'Mn(X)': [(St.sites[4], 2.196, None)], 'Mn(M1)': [(St.sites[5], 2.128, None)], 'Al1(M3a)': [(St.sites[5], 1.882, None)], 'Al2(M3b)': [(St.sites[4], 1.879, None)]}[s.label]
        # the paper numbers the Al sites differently in its two tables: the site name in parentheses is what carries over
        ok, n, miss = PS.bond_hits(St(), [('Mn(X)', 'O1', 2.196), ('Mn(M1)', 'O5', 2.128), ('Al2(M3a)', 'O5', 1.882), ('Al3(M3b)', 'O1', 1.879), ('Mn', 'O5', 2.128)])
        self.assertEqual((ok, n, miss), (5, 5, []))
        ok, n, miss = PS.bond_hits(St(), [('Mn(X)', 'O5', 2.128)])            # the other Mn site's bond is not this site's
        self.assertEqual((ok, n), (0, 1))
