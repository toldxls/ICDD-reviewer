"""pxrd_review.update — version comparison, the GitHub check (with a stand-in fetch), the pip line.

    python3 -m unittest tests.test_update -v
"""
import json, unittest

from pxrd_review import update as U, __version__


class Versions(unittest.TestCase):
    def test_vtuple_and_newer(self):
        self.assertEqual(U.vtuple('v0.3.4'), (0, 3, 4))
        self.assertEqual(U.vtuple('0.5.1+dirty'), (0, 5, 1))
        self.assertTrue(U.newer('0.10.0', '0.9.9')); self.assertFalse(U.newer('0.5.1', '0.5.1'))
        self.assertEqual(U.parse_init('# x\n__version__ = "0.5.2"\n'), '0.5.2')
        self.assertIsNone(U.parse_init('nothing here'))

    def test_check_with_a_stand_in_network(self):
        release = {'tag_name': 'v0.3.4', 'html_url': 'https://github.com/x/releases/tag/v0.3.4',
                   'assets': [{'name': 'pxrd_review-0.3.4-py3-none-any.whl', 'browser_download_url': 'https://dl/whl'},
                              {'name': 'SHA256SUMS.txt', 'browser_download_url': 'https://dl/sums'}]}
        def fetch(url, timeout=None):
            if url == U.MAIN_INIT: return '__version__ = "9.9.9"\n'
            if url == U.RELEASE_API: return json.dumps(release)
            if url == 'https://dl/sums': return 'ab' * 32 + '  pxrd_review-0.3.4-py3-none-any.whl\n'
            raise AssertionError(url)
        r = U.check(fetch)
        self.assertEqual((r['installed'], r['main'], r['release'], r['newest'], r['newer']), (__version__, '9.9.9', '0.3.4', '9.9.9', True))
        self.assertEqual((r['wheel'], r['sha256']), ('https://dl/whl', 'ab' * 32))
        self.assertIsNone(r['error'])
        self.assertTrue(U.pip_command('release', r)[-1].endswith('#sha256=' + 'ab' * 32))
        self.assertEqual(U.pip_command()[-1], U.MAIN_ZIP)
        # offline: no exception, the error is stated, nothing is "newer"
        def down(url, timeout=None):
            raise OSError('no network')
        r = U.check(down)
        self.assertFalse(r['newer']); self.assertIn('no network', r['error']); self.assertIsNone(r['newest'])
        # main unreachable but the release answers: still a verdict
        def half(url, timeout=None):
            if url == U.RELEASE_API: return json.dumps({'tag_name': 'v0.0.1', 'assets': []})
            raise OSError('no')
        r = U.check(half)
        self.assertEqual((r['newest'], r['newer'], r['error']), ('0.0.1', False, None))

    def test_cli_never_installs_when_nothing_is_newer(self):
        import io, contextlib
        calls = []
        saved = (U.check, U.subprocess.call)
        try:
            U.check = lambda fetch=None: {'installed': __version__, 'main': '0.0.1', 'release': None, 'release_url': U.RELEASES_URL,
                                          'wheel': None, 'sha256': None, 'newest': '0.0.1', 'newer': False, 'error': None}
            U.subprocess.call = lambda cmd: calls.append(cmd) or 0
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = U.main([])                                   # a bare `pxrd update`: on this checkout, a git pull, never pip
            self.assertEqual(rc, 0)
            self.assertEqual([c[:2] for c in calls], [['git', '-C']])
            self.assertNotIn('pip', ' '.join(' '.join(c) for c in calls))
            calls.clear()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = U.main(['--check'])
            self.assertEqual((rc, calls), (0, []))
        finally:
            U.check, U.subprocess.call = saved

    def test_gui_pull_that_changes_nothing_does_not_restart(self):
        # a checkout already at its upstream: git pull says "Already up to date", HEAD stays put —
        # the server must NOT relaunch itself (it once restarted on every Pull now)
        import types
        popens, exits = [], []
        saved = (U.subprocess.run, U.subprocess.Popen, U.os._exit, U.time.sleep)
        wait = saved[3]                                        # the real sleep, for polling the worker thread
        try:
            def run(cmd, **kw):
                if cmd[-1] == 'HEAD':
                    return types.SimpleNamespace(returncode=0, stdout='abc123\n', stderr='')
                return types.SimpleNamespace(returncode=0, stdout='Already up to date.\n', stderr='')
            U.subprocess.run = run
            U.subprocess.Popen = lambda *a, **k: popens.append(a)
            U.os._exit = lambda rc: exits.append(rc)
            U.time.sleep = lambda s: None
            with U._run_lock:
                U._run.update(state='idle', log='', rc=None, how=None)
            U.gui_update([], {})
            for _ in range(200):
                st = U.run_status()
                if st['state'] not in ('running', 'idle'):
                    break
                wait(0.01)
            self.assertEqual((st['state'], st['how'], st['rc']), ('current', 'git pull', 0))
            self.assertIn('Already up to date', st['log'])
            self.assertEqual((popens, exits), ([], []))
            # and a pull that moves HEAD restarts (the helper is started, the process exits)
            heads = iter(['abc123\n', 'def456\n'])
            def run2(cmd, **kw):
                if cmd[-1] == 'HEAD':
                    return types.SimpleNamespace(returncode=0, stdout=next(heads), stderr='')
                return types.SimpleNamespace(returncode=0, stdout='Updating abc123..def456\n', stderr='')
            U.subprocess.run = run2
            with U._run_lock:
                U._run.update(state='idle', log='', rc=None, how=None)
            U.gui_update([], {})
            for _ in range(200):
                st = U.run_status()
                if st['state'] not in ('running', 'idle'):
                    break
                wait(0.01)
            self.assertEqual(st['state'], 'restarting')
            self.assertEqual((len(popens), exits), (1, [0]))
        finally:
            U.subprocess.run, U.subprocess.Popen, U.os._exit, U.time.sleep = saved
            with U._run_lock:
                U._run.update(state='idle', log='', rc=None, how=None)

    def test_checkout_is_recognised(self):
        # this test runs from the repository: update must point at git pull, not pip
        self.assertTrue(U.checkout() and U.checkout().endswith('review_tool'))
        st = U.status()
        self.assertEqual(st['command'], 'pxrd update'); self.assertIn('git -C', st['pip']); self.assertEqual(st['checkout'], U.checkout())


if __name__ == '__main__':
    unittest.main()
