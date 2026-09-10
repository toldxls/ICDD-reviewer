"""The triage-report importer: another reviewer's triage_report.txt read back into verdicts."""
import unittest
from pxrd_review.gui import review_gui as G

REPORT = """PXRD review — triage report
source folder : C:\\Users\\Rost\\Desktop\\MINERALNEW
generated     : 2026-09-09T11:44:05
entries       : 37 total | 35 marked reviewed
==============================================================================

PETERSITE-(Y)   (I002449)   [REVIEWED]
------------------------------------------------------------------------------
  [CONFIRMED   ] CELL: no exact cell match — closest off by Σ|Δ|=0.0560 Å over 3 axes — INVESTIGATE
↳ p
       note: MR-See table 2.

SUENOITE   (I003638)   [REVIEWED]
------------------------------------------------------------------------------
  [CONFIRMED   ] intensity_type: the powder pattern intensities were visually estimated (per the .pdf), so Intens
       note: MR- Intensity Type can only be I or P, Intensity Instrument is Visual.
  [dismissed   ] CELL: value match to a reported cell — 3/3 axes, direct, Σ|Δ|=0.0000 Å
↳ matches the p
  Accept decision : agree
  entry note: checked against the paper
"""


class ParseReport(unittest.TestCase):
    def test_blocks(self):
        b = G._parse_triage_report(REPORT)
        self.assertEqual([x['eid'] for x in b], ['I002449', 'I003638'])
        self.assertTrue(b[0]['reviewed'])
        self.assertEqual(b[0]['verdicts'][0]['verdict'], 'CONFIRMED')
        self.assertEqual(b[0]['verdicts'][0]['note'], 'MR-See table 2.')
        self.assertTrue(b[0]['verdicts'][0]['label'].startswith('CELL: no exact cell match'))
        self.assertIn('\n↳ p', b[0]['verdicts'][0]['label'])
        self.assertEqual(b[1]['accept'], 'agree')
        self.assertEqual(b[1]['note'], 'checked against the paper')
        self.assertEqual([v['verdict'] for v in b[1]['verdicts']], ['CONFIRMED', 'dismissed'])


class MatchLabels(unittest.TestCase):
    rows = [('cell', 'CELL', 'match'), ('lam', 'RADIATION', 'anode MoKa appears in .pdf but no clear powder-context radiation found'),
            ('f:aaa', 'intensity_type', 'the powder pattern intensities were visually estimated (per the .pdf), so Intensity Instr. should be Visual, not Gandolfi.'),
            ('f:bbb', 'analysis', "Analysis present but no 'average of N' stated — confirm it is an average, not a single point."),
            ('f:ccc', 'classification', 'docx has no Structure comment'), ('f:ddd', 'classification', 'docx names a group Mindat does not')]

    def test_cell_and_radiation_by_code(self):
        self.assertEqual(G._match_report_label('CELL: value match to a reported cell — 3/3 axes\n↳ matches the p', self.rows), 'cell')
        self.assertEqual(G._match_report_label('RADIATION: anode MoKa appears in .pdf but no clear powder-context radiation found', self.rows), 'lam')

    def test_prefix_and_reworded(self):
        # the exact 80-character prefix the GUI labelled it with
        msg = "Analysis present but no 'average of N' stated — confirm it is an average, not a single point."
        self.assertEqual(G._match_report_label('analysis: ' + msg[:80], self.rows), 'f:bbb')
        # a reworded finding of a code the entry raises once still takes the verdict
        self.assertEqual(G._match_report_label('intensity_type: the powder pattern intensities were visually estimated (per the .pdf), so Intens', self.rows), 'f:aaa')
        # two findings of one code and no prefix match: nobody gets it
        self.assertIsNone(G._match_report_label('classification: something else entirely', self.rows))
        self.assertIsNone(G._match_report_label('no colon here', self.rows))


if __name__ == '__main__':
    unittest.main()


class Idempotent(unittest.TestCase):
    def test_import_notes_are_replaced_not_stacked(self):
        n = 'my own note ‖ triage_report.txt decided on findings this version does not raise: [x] docx 3 dp  vs  pdf 2 dp ‖ triage_report.txt entry note: b'
        self.assertEqual(G._without_import_notes(n, 'triage_report.txt'), 'my own note')
        self.assertEqual(G._without_import_notes('', 'triage_report.txt'), '')


class UploadRoute(unittest.TestCase):
    """The Import triage button uploads the report; the route merges it as the CLI flag does."""
    def setUp(self):
        self.saved = {k: G.STATE.get(k) for k in ('docx', 'order', 'triage', 'out_dir')}
        G.STATE['docx'] = {'suenoite': '/nowhere/suenoite.docx'}
        G.STATE['order'] = ['suenoite']
        G.STATE['triage'] = {}
        self.patched = (G.C.entry_id, G.get_analysis, G._save_triage)
        G.C.entry_id = lambda p: 'I003638'
        G.get_analysis = lambda key: {'findings': []}      # truthy: an analysed entry
        G._entry_rows_orig = G._entry_rows
        G._entry_rows = lambda d: [('f:int', 'intensity_type', 'the powder pattern intensities were visually estimated'),
                                   ('cell', 'CELL', 'value match')]
        G._save_triage = lambda: None

    def tearDown(self):
        G.C.entry_id, G.get_analysis, G._save_triage = self.patched
        G._entry_rows = G._entry_rows_orig
        for k, v in self.saved.items():
            G.STATE[k] = v

    def test_upload_merges_and_reports(self):
        import io
        with G.app.test_client() as c:
            r = c.post('/api/triage/import', data={'report': (io.BytesIO(REPORT.encode('utf-8')), 'icdd_report.txt')},
                       content_type='multipart/form-data')
        j = r.get_json()
        self.assertTrue(j['ok'], j)
        self.assertEqual(j['summary']['entries'], 1)               # petersite is not in this folder
        self.assertEqual(j['summary']['unknown_entries'], ['I002449'])
        self.assertEqual(j['summary']['matched'], 2)
        t = G.STATE['triage']['suenoite']
        self.assertEqual(t['findings']['f:int']['verdict'], 'confirm')
        self.assertEqual(t['findings']['f:int']['imported'], 'icdd_report.txt')
        self.assertEqual(t['findings']['cell']['verdict'], 'dismiss')
        self.assertEqual(t['accept'], 'agree')
        self.assertTrue(t['reviewed'])

    def test_the_path_form_takes_a_text_file_only(self):
        # the JSON {path} form names a file on the machine hosting the GUI: only a .txt report is
        # opened, so the endpoint cannot be used to probe for other files (audit 2026-09-10)
        with G.app.test_client() as c:
            r = c.post('/api/triage/import', json={'path': '/etc/passwd'})
            self.assertEqual(r.status_code, 400)
            self.assertIn('.txt', r.get_json()['error'])
            r = c.post('/api/triage/import', json={'path': '/no/such/dir/triage_report.txt'})
            self.assertEqual(r.status_code, 400)
            self.assertIn('no such file', r.get_json()['error'])

    def test_not_a_report_is_a_400(self):
        import io
        with G.app.test_client() as c:
            r = c.post('/api/triage/import', data={'report': (io.BytesIO(b'hello world'), 'notes.txt')},
                       content_type='multipart/form-data')
        self.assertEqual(r.status_code, 400)
        self.assertIn('not a triage report', r.get_json()['error'])
