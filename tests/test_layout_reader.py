"""The layout reader without docling: a fake document with two tables on two pages -> the grids ->
the pages the table readers consume -> the powder and analytical readers read them.

    python3 -m unittest tests.test_layout_reader -v"""
import unittest
from types import SimpleNamespace as NS

from pxrd_review import layout_reader as LR
from pxrd_review import paper_extract as PE


def cell(r, c, text, rs=1, cs=1):
    return NS(text=text, start_row_offset_idx=r, end_row_offset_idx=r + rs, start_col_offset_idx=c, end_col_offset_idx=c + cs, row_span=rs, col_span=cs, column_header=(r == 0))


class FakeTable:
    def __init__(self, page, caption, rows):
        self.prov = [NS(page_no=page)]; self._cap = caption
        cells = []
        for r, row in enumerate(rows):
            for c, t in enumerate(row):
                if t is not None:
                    cells.append(cell(r, c, t))
        self.data = NS(table_cells=cells, num_rows=len(rows), num_cols=max(len(r) for r in rows))
    def caption_text(self, doc):
        return self._cap


class LayoutReader(unittest.TestCase):
    def setUp(self):
        self.doc = NS(tables=[
            FakeTable(2, 'Table 1. Chemical data (wt%) for testite.', [['Constituent', 'Mean', 'Range', 'S.D.'], ['CaO', '17.23', '16.90–17.50', '0.21'], ['MgO', '24.88', '24.50–25.20', '0.30'],
                                                                     ['SiO2', '55.18', '54.80–55.60', '0.28'], ['H2O', '2.71', None, None], ['Total', '100.00', None, None]]),
            FakeTable(2, 'Table 2. Powder X-ray diffraction data for testite.', [['Iobs', 'dobs', 'dcalc', 'Icalc', 'h', 'k', 'l'], ['100', '3.4550', '3.4531', '92', '1', '1', '0'],
                                                                              ['35', '2.9800', '2.9791', '40', '0', '2', '1'], ['12', '2.5010', '2.4997', '9', '2', '0', '0'], ['8', '1.0210', '1.0204', '6', '−10', '1', '2']]),
        ])

    def test_grid_and_pages(self):
        tabs = LR.grid_from_document(self.doc)
        self.assertEqual(sorted(tabs), [2]); self.assertEqual(len(tabs[2]), 2)
        cap, grid = tabs[2][1]
        self.assertEqual(cap, 'Table 2. Powder X-ray diffraction data for testite.'); self.assertEqual(grid[0], [(0, 'Iobs'), (1, 'dobs'), (2, 'dcalc'), (3, 'Icalc'), (4, 'h'), (5, 'k'), (6, 'l')])
        self.assertEqual(tabs[2][0][1][4], [(0, 'H2O'), (1, '2.71')])                     # a missing cell is simply absent
        calls = []
        pages = LR.assemble(tabs, 3, lambda i: calls.append(i) or [PE._empty_line(70.0)])
        self.assertEqual((len(pages), calls), (3, [0, 2]))                                 # only the pages without a table are read by fitz
        lines = pages[1]
        empties = [k for k, ln in enumerate(lines) if not ln['w']]
        self.assertEqual(len(empties), 3)                                                  # the gap that ends a table region between the two tables
        # the readers consume the page as they would a pdf page
        hdr = next(k for k, ln in enumerate(lines) if [w[4] for w in ln['w']][:2] == ['Iobs', 'dobs'])
        cols = PE._powder_columns(lines[hdr]['w'], PE._caption(lines, hdr))
        self.assertEqual([c[1] for c in cols], ['Iobs', 'dobs', 'dcalc', 'Icalc', 'hkl'])
        o, c = PE._powder_rows_by_columns(lines, hdr + 1, cols)
        self.assertEqual((len(o), len(c)), (4, 4)); self.assertEqual(c[-1][2], (-10, 1, 2))
        o2, c2 = PE._pt_read(lines, lambda i: PE._caption(lines, i))
        self.assertEqual((len(o2), len(c2)), (4, 4))

    def test_cell_text(self):
        self.assertEqual(LR._cell_text('(NH 4 ) 2 O*'), '(NH4)2O*'); self.assertEqual(LR._cell_text('Å 2'), 'Å2')
        self.assertEqual(LR._cell_text('h k l'), 'h k l'); self.assertEqual(LR._cell_text('U eq'), 'U eq'); self.assertEqual(LR._cell_text('I obs'), 'I obs')

    def test_available_is_a_bool(self):
        self.assertIn(LR.available(), (True, False))


if __name__ == '__main__':
    unittest.main()
