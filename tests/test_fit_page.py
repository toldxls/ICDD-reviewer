"""annotate_review._fit_page: an output copy whose tables overrun the page gets a wider page — page
setup only; a page that already holds its tables is left alone."""
import unittest

from docx import Document
from docx.shared import Twips

from pxrd_review import annotate_review as A


def doc_with_table(width):
    d = Document()
    t = d.add_table(rows=1, cols=2)
    t.autofit = False
    tblW = t._tbl.tblPr.find(A._q('tblW'))
    if tblW is None:
        tblW = t._tbl.tblPr.makeelement(A._q('tblW'), {})
        t._tbl.tblPr.append(tblW)
    tblW.set(A._q('w'), str(width)); tblW.set(A._q('type'), 'dxa')
    t.cell(0, 0).text = 'PDFID :'
    return d


class FitPage(unittest.TestCase):
    def test_a_ten_inch_table_on_letter_portrait_turns_the_page(self):
        d = doc_with_table(14400)
        s = d.sections[-1]
        s.page_width, s.page_height = Twips(12240), Twips(15840)
        s.left_margin = s.right_margin = Twips(1440)
        self.assertTrue(A._fit_page(d))
        self.assertEqual((s.page_width.twips, s.page_height.twips), (15840, 12240))
        self.assertGreaterEqual(s.page_width.twips - s.left_margin.twips - s.right_margin.twips, 14400)
        self.assertEqual(d.tables[0].cell(0, 0).text, 'PDFID :')

    def test_a_page_that_holds_its_tables_is_untouched(self):
        d = doc_with_table(8000)
        s = d.sections[-1]
        before = (s.page_width, s.page_height, s.left_margin, s.right_margin)
        self.assertFalse(A._fit_page(d))
        self.assertEqual(before, (s.page_width, s.page_height, s.left_margin, s.right_margin))

    def _letter(self, d):
        s = d.sections[-1]
        s.page_width, s.page_height = Twips(12240), Twips(15840); s.left_margin = s.right_margin = Twips(1440)
        return s

    def test_shapes_that_fit_or_cannot_be_judged_are_left_alone(self):
        from docx.enum.section import WD_SECTION
        # a table that fills its window (pct) fits by definition, whatever widths its cells still carry
        d = doc_with_table(5000); self._letter(d)
        d.tables[0]._tbl.tblPr.find(A._q('tblW')).set(A._q('type'), 'pct')
        for c in d.tables[0].rows[0].cells:
            c.width = Twips(7200)
        self.assertFalse(A._fit_page(d))
        # a table that fits, holding a nested table: the nested cells are not the outer row's
        d = doc_with_table(0); self._letter(d)
        d.tables[0]._tbl.tblPr.find(A._q('tblW')).set(A._q('type'), 'auto')
        for c in d.tables[0].rows[0].cells:
            c.width = Twips(4500)
        inner = d.tables[0].cell(0, 0).add_table(rows=1, cols=2)
        for c in inner.rows[0].cells:
            c.width = Twips(4000)
        self.assertFalse(A._fit_page(d))
        # several sections: which one holds the wide table is not known, so none is turned
        d = doc_with_table(14400); self._letter(d); d.add_section(WD_SECTION.NEW_PAGE)
        self.assertFalse(A._fit_page(d))



class LogName(unittest.TestCase):
    def test_a_returned_edited_file_keeps_its_name_and_a_bare_levinson_suffix_is_written_the_ima_way(self):
        self.assertEqual(A._log_name('I002449(Petersite-(Y))_edited_edited.docx'), 'PETERSITE-(Y)')
        self.assertEqual(A._log_name('I003682(Lepersonnite-Gd)_edited.docx'), 'LEPERSONNITE-(Gd)')
        self.assertEqual(A._log_name('I003896(Anningite-(Ce)).docx'), 'ANNINGITE-(Ce)')
        self.assertEqual(A._log_name('I003743(Avicennite-Sb-rich).docx'), 'AVICENNITE-SB-RICH')


if __name__ == '__main__':
    unittest.main()
