"""Unit tests for pxrd_review.powder_calc and pxrd_review.pxrd_audit — rutile's pattern is known (PDF 21-1276:
110 = 100, 101 ≈ 50, 111 ≈ 20, 211 ≈ 60, 220 ≈ 20; h00 with h odd absent in P4₂/mnm).

    python3 -m unittest tests.test_powder -v
"""
import os, math, shutil, tempfile, unittest

from pxrd_review import powder_calc as PC, pxrd_audit as PA, bv_check as B
from tests.test_bv_check import RUTILE, _write


def _line(pat, st, hkl):
    for x in pat:
        if hkl in PC.equivalents(st, x['hkl']):
            return x
    return None


class Pattern(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='pc_')
        self.cif = _write(self.tmp, 'rutile.cif', RUTILE)
        self.st = B.Structure(self.cif)
        self.pat = PC.pattern(self.cif, 1.5406, 1.3, structure=self.st)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_rutile(self):
        l110 = _line(self.pat, self.st, (1, 1, 0)); l101 = _line(self.pat, self.st, (1, 0, 1)); l211 = _line(self.pat, self.st, (2, 1, 1))
        self.assertAlmostEqual(l110['d'], 3.248, places=3); self.assertEqual(l110['I'], 100.0); self.assertEqual(l110['m'], 4)
        self.assertTrue(40 <= l101['I'] <= 60, l101); self.assertTrue(45 <= l211['I'] <= 70, l211)
        self.assertEqual(l211['m'], 16)
        self.assertIsNone(_line(self.pat, self.st, (1, 0, 0)))                     # the 4₂ screw / n glide: h00, h odd, absent
        self.assertEqual([x for x in self.pat if x['hkl'] == (1, 1, 0)][0]['tth'], self.pat[0]['tth'])
        self.assertAlmostEqual(self.pat[0]['tth'], 27.44, places=1)

    def test_equivalents_and_form_factors(self):
        self.assertEqual(len(PC.equivalents(self.st, (2, 1, 1))), 16)
        self.assertEqual(len(PC.equivalents(self.st, (1, 1, 0))), 4)
        self.assertAlmostEqual(PC.f_of(PC.form_factor('O'), 0.0), 8.0, places=1)    # f(0) = Z
        self.assertAlmostEqual(PC.f_of(PC.form_factor('Ti', 4, ions=True), 0.0), 18.0, places=1)
        self.assertEqual(PC.wavelength('Mo'), 0.71073); self.assertEqual(PC.wavelength('1.54'), 1.54)

    def test_wavelength_moves_lp_not_the_lines(self):
        mo = PC.pattern(self.cif, 0.71073, 1.3, structure=self.st)
        self.assertEqual([x['hkl'] for x in mo], [x['hkl'] for x in self.pat])
        self.assertGreater(_line(mo, self.st, (2, 1, 1))['I'], _line(self.pat, self.st, (2, 1, 1))['I'])   # Lp falls off less steeply at short λ: the high-angle line gains


def _docx_table(path, rows, groups):
    """A proposal-style powder table: Iobs dobs dcalc Icalc hkl, the Iobs/dobs cells merged down each group."""
    from docx import Document
    doc = Document()
    t = doc.add_table(rows=1, cols=5)
    for i, h in enumerate(('Iobs', 'dobs', 'dcalc', 'Icalc', 'hkl')):
        t.rows[0].cells[i].text = h
    for r in rows:
        c = t.add_row().cells
        c[0].text, c[1].text, c[2].text, c[3].text, c[4].text = r
    for a, b in groups:                                                    # (first row, last row) of a merged group, 1-based data rows
        t.cell(a, 0).merge(t.cell(b, 0)); t.cell(a, 1).merge(t.cell(b, 1))
    doc.add_paragraph('Unit-cell parameters refined from powder data: a = 4.594(2), c = 2.959(1) Å')
    doc.save(path)
    return path


class Audit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='pa_')
        self.cif = _write(self.tmp, 'rutile.cif', RUTILE)
        self.st = B.Structure(self.cif)
        self.pat = [x for x in PC.pattern(self.cif, 1.5406, 1.35, structure=self.st) if x['I'] >= 1]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def table_from(self, pat, cell=None, drop=()):
        """Rows and merged groups from a pattern: each line its own observed line, dcalc from `cell` when given."""
        rows = []
        for x in pat:
            if x['hkl'] in drop:
                continue
            d = PA.d_of(cell, x['hkl']) if cell else x['d']
            rows.append(('%.0f' % max(x['I'], 1), '%.3f' % d, '%.3f' % d, '%.0f' % max(x['I'], 1), ' '.join(str(v) for v in x['hkl'])))
        return rows

    def test_clean_table_reproduces(self):
        path = _docx_table(os.path.join(self.tmp, 'm.docx'), self.table_from(self.pat), [])
        rows, dec = PA.read_docx_powder(path)
        self.assertEqual(len(rows), len(self.pat)); self.assertEqual(dec, 3); self.assertTrue(all(r['group'] for r in rows))
        out = PA.audit(path, self.cif)
        self.assertEqual([r['kind'] for r in out['records']], [], out['lines'])
        self.assertTrue(any('follows from the .cif' in ln for ln in out['lines']), out['lines'])
        self.assertTrue(any('rms 0.' in ln and 'Icalc' in ln for ln in out['lines']), out['lines'])

    def test_fit_cell(self):
        rows = [{'hkl': x['hkl'], 'dcalc': round(x['d'], 4)} for x in self.pat]
        cell, rms, sig = PA.fit_cell(rows, 'tetragonal')
        self.assertAlmostEqual(cell[0], 4.5937, places=3); self.assertAlmostEqual(cell[2], 2.9587, places=3)
        self.assertLess(rms, 0.0002)
        self.assertEqual(PA._system(self.st.cell, 'P 42/m n m'), 'tetragonal')
        self.assertEqual(PA._system((10.0, 10.0, 12.0, 90, 90, 90), 'P b c a'), 'orthorhombic')      # a = b by chance
        self.assertEqual(PA._system((10.0, 15.0, 5.0, 90, 106.9, 90), 'C 2/m'), 'monoclinic-b')
        self.assertEqual(PA._system((5.0, 5.0, 5.0, 90, 90, 90), 'F m -3 m'), 'cubic')

    def test_a_cubic_cell_is_stated_by_its_a_alone(self):
        cells = PA.manuscript_cells(['Unit cell: a = 10.123(2) Å, V = 1037.4 Å3'], 'cubic')
        self.assertEqual([c[1][:3] for c in cells], [(10.123, 10.123, 10.123)])
        self.assertEqual(PA.manuscript_cells(['Unit cell: a = 10.123(2) Å'], 'tetragonal'), [])   # needs its c

    def test_dcalc_from_another_cell_is_a_flag(self):
        other = (4.6100, 4.6100, 2.9587, 90, 90, 90)                                   # a 0.35 % longer
        path = _docx_table(os.path.join(self.tmp, 'm.docx'), self.table_from(self.pat, cell=other), [])
        out = PA.audit(path, self.cif)
        cell = [r for r in out['records'] if r['kind'] == 'cell']
        self.assertEqual(len(cell), 1, out['lines']); self.assertEqual(cell[0]['severity'], 'flag')
        self.assertIn('a = 4.61', cell[0]['text']); self.assertIn('the .cif', cell[0]['text']); self.assertIn('is off by 0.3', cell[0]['text'])

    def test_a_strong_line_left_out_is_a_flag(self):
        # 211 (I ≈ 60) dropped but its observed line kept, explained by a weak line: the table must have it
        rows = self.table_from(self.pat, drop=((2, 1, 1),))
        l211 = [x for x in self.pat if x['hkl'] in PC.equivalents(self.st, (2, 1, 1))][0]
        rows.append(('60', '%.3f' % l211['d'], '%.3f' % (l211['d'] + 0.002), '1', '5 5 5'))
        path = _docx_table(os.path.join(self.tmp, 'm.docx'), rows, [])
        out = PA.audit(path, self.cif)
        om = [r for r in out['records'] if r['kind'] == 'omitted']
        self.assertEqual(len(om), 1, out['lines']); self.assertEqual(om[0]['severity'], 'flag'); self.assertIn('2 1 1', om[0]['text'])

    def test_a_weak_line_left_out_is_a_note(self):
        weak = min(self.pat, key=lambda x: x['I'])                                     # the weakest line ≥ 1 of 100
        rows = self.table_from(self.pat, drop=(weak['hkl'],))
        rows.append(('9', '%.3f' % weak['d'], '%.3f' % weak['d'], '8', '5 5 5'))          # a stronger line listed there: the weak one is information
        out = PA.audit(_docx_table(os.path.join(self.tmp, 'm.docx'), rows, []), self.cif)
        om = [r for r in out['records'] if r['kind'] == 'omitted']
        self.assertTrue(not om or om[0]['severity'] == 'note', out['lines'])

if __name__ == '__main__':
    unittest.main()
