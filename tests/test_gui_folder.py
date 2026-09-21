"""The GUI and a folder that is not a batch: asked about, never indexed by accident; with nothing to open it starts on the chooser."""
import os, sys, json, shutil, tempfile, unittest
from unittest import mock


class FolderGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pxrd_review.gui import review_gui as G
        from pxrd_review import cli
        cls.G = G; cls.cli = cli
        G._ALLOWED_HOSTS = set()
        cls.tmp = tempfile.mkdtemp(prefix='guifolder_')
        cls._mem = cli.MEM; cli.MEM = os.path.join(cls.tmp, 'last.json')
        cls._tmpf = cli._is_temp; cli._is_temp = lambda f: False                 # these batches live in a temp dir
        cls.batch = os.path.join(cls.tmp, 'Part 1'); os.makedirs(cls.batch)
        cls.root = os.path.join(cls.tmp, 'corpus')
        for i in range(12):                                              # a corpus root: documents in many subfolders
            d = os.path.join(cls.root, 'reviewer %d' % (i % 4)); os.makedirs(d, exist_ok=True)
            open(os.path.join(d, 'I%06d(Testite).docx' % i), 'w').close()
        cls.c = G.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.cli.MEM = cls._mem; cls.cli._is_temp = cls._tmpf
        cls.G.STATE['choose'] = None; cls.G._ALLOWED_HOSTS = set(); cls.G._AUTH_TOKEN = None
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_survey(self):
        G = self.G
        sv = G.folder_survey(self.root)
        self.assertEqual((sv['docx'], sv['dirs'], sv['broad']), (12, 4, False))
        with mock.patch.object(G, 'SURVEY_MAX_DOCX', 10):
            sv = G.folder_survey(self.root)
            self.assertTrue(sv['broad'] and sv['capped']); self.assertIn('more than 10 documents', sv['why'])
        self.assertTrue(G.folder_survey(os.path.expanduser('~'))['broad'])       # a home folder, however few documents it holds — and the look is bounded

    def test_out_of_time_is_not_a_large_tree(self):
        G = self.G
        with mock.patch.object(G, '_SURVEY_SECONDS', 0.0):                   # a slow (network) drive: the look runs out of time on a real batch
            sv = G.folder_survey(self.root)
        self.assertTrue(sv['broad'])                                         # still asked about …
        self.assertIn('could not be counted', sv['why']); self.assertNotIn('not a batch', sv['why'])   # … but never called what it is not

    def test_entry_actions_without_a_folder_say_so(self):
        G = self.G
        folder, G.STATE['out_dir'] = G.STATE['out_dir'], None
        try:
            for url in ('/api/rerun', '/api/rerun/I000001', '/api/triage/export'):
                r = self.c.post(url, json={})
                self.assertEqual(r.status_code, 409, url); self.assertIn('choose one first', json.loads(r.data)['error'])
        finally:
            G.STATE['out_dir'] = folder

    def test_the_folder_route_asks_before_a_folder_that_is_not_a_batch(self):
        G = self.G
        with mock.patch.object(G, 'SURVEY_MAX_DOCX', 10), mock.patch.object(G, 'build_index') as bi, mock.patch.object(G, 'start_analysis'), \
                mock.patch.object(G.C, 'discover', return_value={'I000001': 'x'}):
            r = self.c.post('/api/folder', json={'folder': self.root})
            self.assertEqual(r.status_code, 409); d = json.loads(r.data)
            self.assertTrue(d['broad']); self.assertIn('holds more than 10 documents, in 4 subfolders', d['error']); self.assertIn('Open it all, or pick a batch?', d['error'])
            bi.assert_not_called()                                           # nothing was indexed
            G.C.discover.assert_not_called()                                 # … nor walked: discovery is the long part on such a folder
            r = self.c.post('/api/folder', json={'folder': self.root, 'confirm': True})   # on purpose: opened
            self.assertEqual(r.status_code, 200); bi.assert_called_once()
            self.assertEqual(self.cli._load()['gui'], os.path.abspath(self.root))     # and it is what the launcher reopens

    def test_nothing_to_open_starts_on_the_chooser(self):
        G = self.G
        self.cli._save('gui', self.batch)
        for argv, want in (([], 'Choose the entries folder.'), ([os.path.join(self.tmp, 'gone')], 'no longer exists')):
            G.STATE['choose'] = None
            with mock.patch.object(sys, 'argv', ['review_gui'] + argv + ['--no-browser']), mock.patch.object(G.app, 'run'), \
                    mock.patch.object(G, 'build_index') as bi, mock.patch.object(G.UPD, 'start'), mock.patch.object(G.threading, 'Thread'):
                G.main()
            G._ALLOWED_HOSTS = set(); G._AUTH_TOKEN = None                  # main() arms the host allowlist and the token: the test client has neither
            bi.assert_not_called()
            d = json.loads(self.c.get('/api/entries').data)
            self.assertIn(want, d['choose']['reason']); self.assertEqual(d['choose']['recent'], [os.path.abspath(self.batch)])
            self.assertEqual(d['entries'], [])
        # a corpus root given on the command line: the same screen, saying why, with the folder to open on purpose
        G.STATE['choose'] = None
        with mock.patch.object(G, 'SURVEY_MAX_DOCX', 10), mock.patch.object(sys, 'argv', ['review_gui', self.root, '--no-browser']), \
                mock.patch.object(G.app, 'run'), mock.patch.object(G, 'build_index') as bi, mock.patch.object(G.UPD, 'start'), mock.patch.object(G.threading, 'Thread'):
            G.main()
        G._ALLOWED_HOSTS = set(); G._AUTH_TOKEN = None
        bi.assert_not_called()
        ch = json.loads(self.c.get('/api/entries').data)['choose']
        self.assertTrue(ch['broad']); self.assertEqual(ch['folder'], os.path.abspath(self.root)); self.assertIn('Pick a batch, or open it all', ch['reason'])


if __name__ == '__main__':
    unittest.main()
