"""The GUI's page scripts, driven in jsdom against a live test server (tests/js/tb_flows.mjs).

    (cd tests/js && npm install)      # once: jsdom, dev-only, never shipped
    python3 -m unittest tests.test_gui_js -v

Skipped where node or jsdom is missing. Each flow is a state bug a review found in the browser code, which the Flask
test client cannot reach: picks of one probe file carried to the next, the sheet panel left on the last file, a typed
sheet keeping a block number, a folder switch keeping the hidden picks, one save timer for every tab.
"""
import json, os, shutil, subprocess, tempfile, threading, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
JS = os.path.join(HERE, 'js')
PROBE = 'pt,CaO,Al2O3,SiO2\n1,20.16,36.65,43.19\n2,20.20,36.60,43.20\n3,20.10,36.70,43.10\n'


def _node():
    return shutil.which('node')


@unittest.skipUnless(_node() and os.path.isdir(os.path.join(JS, 'node_modules', 'jsdom')), 'node / jsdom not installed (cd tests/js && npm install)')
class TablesFlows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from werkzeug.serving import make_server
        from pxrd_review.gui import review_gui as G
        cls.G = G
        G._ALLOWED_HOSTS = set(); G._AUTH_TOKEN = None
        cls.tmp = tempfile.mkdtemp(prefix='guijs_')
        for name in ('probe.csv', 'probe2.csv'):
            with open(os.path.join(cls.tmp, name), 'w', encoding='utf-8') as f:
                f.write(PROBE)
        assert G.ms_set_folder(cls.tmp)
        if G.MS['athread']:
            G.MS['athread'].join(30)
        cls.srv = make_server('127.0.0.1', 0, G.app, threaded=True)
        cls.th = threading.Thread(target=cls.srv.serve_forever, daemon=True); cls.th.start()
        url = 'http://127.0.0.1:%d' % cls.srv.server_port
        p = subprocess.run([_node(), os.path.join(JS, 'tb_flows.mjs'), url], capture_output=True, text=True, timeout=120, cwd=JS)
        cls.err = p.stderr[-2000:]
        try:
            cls.res = json.loads(p.stdout or '{}')
        except ValueError:
            cls.res = {'_error': {'ok': False, 'detail': (p.stdout or '')[-1500:] + cls.err}}

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_flows(self):
        self.assertNotIn('_error', self.res, self.res.get('_error'))
        want = ('sidebar_file_change_clears_picks', 'same_file_keeps_picks', 'typed_sheet_clears_block_and_range', 'sheet_panel_follows_the_file',
                'late_sheet_reply_ignored', 'folder_switch_clears_hidden_picks', 'per_tab_save_timers')
        for name in want:
            with self.subTest(flow=name):
                self.assertIn(name, self.res, (self.res, self.err))
                self.assertTrue(self.res[name]['ok'], self.res[name]['detail'])


if __name__ == '__main__':
    unittest.main()
