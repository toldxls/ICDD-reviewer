"""The route gauntlet: EVERY route of the GUI, in the states a reviewer can put it in — no folder open, a foreign host —
answers, and answers the right thing. A new route is covered the day it is added (the 0.11.0 review found two routes that
failed with no folder open and one guard that answered before the localhost gate, each by reading the code)."""
import json, unittest
from unittest import mock


class RouteGauntlet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pxrd_review.gui import review_gui as G
        cls.G = G; G._ALLOWED_HOSTS = set(); cls.c = G.app.test_client()

    def _urls(self):
        fill = {'key': 'I000001', 'fkey': 'x', 'tab': 'gd', 'name': 'x.pdf', 'page': '1', 'n': '1', 'filename': 'x', 'eid': 'I000001', 'path': 'x'}
        for rule in self.G.app.url_map.iter_rules():
            if rule.endpoint == 'static':
                continue
            url = rule.rule
            for a in rule.arguments:
                url = url.replace('<%s>' % a, fill.get(a, 'x')).replace('<int:%s>' % a, '1').replace('<path:%s>' % a, 'x')
            for m in sorted(rule.methods - {'HEAD', 'OPTIONS'}):
                yield m, url

    def test_no_route_fails_with_no_folder_open(self):
        G = self.G
        keep = {k: G.STATE.get(k) for k in ('folder', 'out_dir', 'order', 'choose')}; keep_ms = {k: G.MS.get(k) for k in ('folder', 'out_dir')}
        G.STATE.update(folder=None, out_dir=None, order=[], choose={'reason': 'nothing to open', 'folder': None}); G.MS.update(folder=None, out_dir=None)
        bad = []
        try:
            with mock.patch.object(G.subprocess, 'Popen', side_effect=AssertionError('a route launched a process with no folder open')), \
                    mock.patch.object(G.subprocess, 'run', side_effect=OSError('no dialogs in a test')), \
                    mock.patch.object(G.UPD, 'start'), mock.patch.object(G.os, '_exit'):
                for m, url in self._urls():
                    if 'pick-folder' in url or 'update' in url or 'quit' in url or 'shutdown' in url:
                        continue                                                 # an OS dialog, the updater, the exit: not folder state
                    try:
                        r = self.c.open(url, method=m, json={} if m != 'GET' else None)
                        if r.status_code >= 500:
                            bad.append('%s %s -> %d %s' % (m, url, r.status_code, r.data[:80]))
                    except Exception as e:
                        bad.append('%s %s raised %s: %s' % (m, url, type(e).__name__, str(e)[:80]))
        finally:
            G.STATE.update(keep); G.MS.update(keep_ms)
        self.assertEqual(bad, [], '\n'.join(bad))

    def test_a_foreign_host_gets_403_from_every_route(self):
        G = self.G; G._ALLOWED_HOSTS = {'127.0.0.1:8000'}; wrong = []
        try:
            for m, url in self._urls():
                r = self.c.open(url, method=m, json={} if m != 'GET' else None, headers={'Host': 'evil.example'})
                if r.status_code != 403:
                    wrong.append('%s %s -> %d' % (m, url, r.status_code))
        finally:
            G._ALLOWED_HOSTS = set()
        self.assertEqual(wrong, [], '\n'.join(wrong))


if __name__ == '__main__':
    unittest.main()
