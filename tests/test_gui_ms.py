"""Manuscript mode of the review GUI — the /api/ms/* routes, through Flask's test client.

    python3 -m unittest tests.test_gui_ms -v

Builds a small manuscript + companion in a temp folder; no browser, no corpus."""
import json, os, re, shutil, tempfile, unittest, zipfile

from docx import Document


def _docx(path, paras):
    d = Document()
    for p in paras:
        d.add_paragraph(p)
    d.save(path)
    return path


class ManuscriptMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pxrd_review.gui import review_gui as G
        cls.G = G
        G._ALLOWED_HOSTS = set()                      # pre-launch: the request gate lets the test client in
        cls.tmp = tempfile.mkdtemp(prefix='msgui_')
        _docx(os.path.join(cls.tmp, 'paper.docx'), [
            'Quartz is common (Smith 2019; Jones 2020). Kampf (1977) reported it.',
            'References',
            'Jones, A. (2020) A title. Journal 1, 1–2.',
            'Smith, J. (2019) A title. Journal 2, 3–4.',
            'Uncited, U. (2001) Never cited. Journal 3, 5–6.'])
        _docx(os.path.join(cls.tmp, 'table.docx'), ['Table 1. Data from Uncited (2001).'])
        with open(os.path.join(cls.tmp, 'x.cif'), 'w') as f:
            f.write('data_x\n')
        cls.c = G.app.test_client()
        assert G.ms_set_folder(cls.tmp)
        G.MS['athread'].join(30)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_state_and_doc(self):
        # order-independent: reset the companions another test may have set, analyse synchronously
        self.c.post('/api/ms/triage/paper', json={'findings': {}, 'companions': []})
        self.G.ms_analysis('paper'); self.G.ms_analysis('table')
        st = json.loads(self.c.get('/api/ms/state').data)
        self.assertEqual(sorted(f['key'] for f in st['files']), ['paper', 'table'])
        self.assertEqual(st['cifs'], ['x'])
        paper = next(f for f in st['files'] if f['key'] == 'paper')
        self.assertEqual(paper['summary'], {'orphan': 1, 'uncited': 1, 'pair': 0, 'form': 0})
        d = json.loads(self.c.get('/api/ms/doc/paper').data)
        kinds = sorted(f['kind'] for f in d['analysis']['findings'])
        self.assertEqual(kinds, ['orphan', 'uncited'])
        self.assertEqual(d['others'], ['table'])
        self.assertEqual(self.c.get('/api/ms/doc/nope').status_code, 404)

    def test_companion_triage_run_and_render(self):
        c = self.c
        # a companion file resolves the uncited entry
        r = json.loads(c.post('/api/ms/triage/paper', json={'findings': {}, 'companions': ['table']}).data)
        self.assertTrue(r['ok'] and r['reanalyse'])
        d = json.loads(c.get('/api/ms/doc/paper').data)
        self.assertEqual([f['kind'] for f in d['analysis']['findings']], ['orphan'])
        orphan = d['analysis']['findings'][0]
        self.assertEqual(orphan['fkey'], 'orphan:kampf:1977')
        # dismiss it with a note -> the run writes no comment for it
        c.post('/api/ms/triage/paper', json={'findings': {orphan['fkey']: {'verdict': 'dismiss', 'label': 'x'}},
                                             'companions': ['table'], 'reviewed': True})
        r = json.loads(c.post('/api/ms/run/paper').data)
        self.assertTrue(r['ok'])
        out = os.path.join(self.tmp, 'review_out', 'paper_refs.docx')
        self.assertTrue(os.path.exists(out))
        self.assertNotIn('word/comments.xml', zipfile.ZipFile(out).namelist())   # nothing left to write
        # un-dismiss with a note -> one comment carrying the note
        c.post('/api/ms/triage/paper', json={'findings': {orphan['fkey']: {'verdict': 'confirm', 'note': 'ask author', 'label': 'x'}},
                                             'companions': ['table']})
        self.assertTrue(json.loads(c.post('/api/ms/run/paper').data)['ok'])
        cx = zipfile.ZipFile(out).read('word/comments.xml').decode()
        self.assertEqual(len(re.findall(r'<w:comment ', cx)), 1)
        self.assertIn('reviewer: ask author', cx)
        # rendered copy: paragraph anchors, the tool's comment chip, the finding's paragraph index resolves
        h = json.loads(c.get('/api/ms/docx/paper.html?which=annotated').data)
        self.assertEqual(h['which'], 'annotated')
        self.assertIn('data-p="%d"' % orphan['para'], h['html'])
        self.assertIn('class="cmt"', h['html'])
        src = json.loads(c.get('/api/ms/docx/paper.html?which=source').data)
        self.assertNotIn('class="cmt"', src['html'])
        self.assertTrue(json.loads(c.get('/api/ms/report/paper').data)['text'].startswith('Reference check'))
        self.assertTrue(json.loads(c.post('/api/ms/export').data)['ok'])
        rep = open(os.path.join(self.tmp, 'review_out', 'ms_triage_report.txt'), encoding='utf-8').read()
        self.assertIn('paper.docx', rep)
        # the source docx is untouched
        self.assertNotIn('word/comments.xml', zipfile.ZipFile(os.path.join(self.tmp, 'paper.docx')).namelist())

    def test_default_companions_by_name(self):
        from pxrd_review.gui import review_gui as G
        old = dict(G.MS['triage'])
        try:
            G.MS['triage'].pop('paper', None)                       # nothing saved yet
            self.assertEqual(G._ms_companions('paper'), ['table'])  # 'table.docx' is pre-ticked by name
            self.assertEqual(G._ms_companions('table'), [])         # a table file has no companions of its own
            G.MS['triage']['paper'] = {'companions': []}            # the reviewer un-ticked it: respected
            self.assertEqual(G._ms_companions('paper'), [])
        finally:
            G.MS['triage'] = old

    def test_folder_validation(self):
        r = self.c.post('/api/ms/folder', json={'folder': '/nonexistent/x'})
        self.assertEqual(r.status_code, 400)
        empty = tempfile.mkdtemp(prefix='msgui_empty_')
        try:
            r = self.c.post('/api/ms/folder', json={'folder': empty})
            self.assertEqual(r.status_code, 400)
        finally:
            shutil.rmtree(empty, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
