"""An entry whose .pdf scan failed must not spin the background pass (0.5.6 follow-up).

The first fix for the cached zero-page scan (issue #3) left such an entry OUT of the cache so that
reopening it would retry. But the dashboard counts every un-cached entry as pending and re-kicks
an idle analysis pass every 30 s while anything is, and each pass re-ran the failed scan (a 40 s
worker timeout): one bad .pdf kept a worker busy for as long as the GUI was open, and the folder
never reached pending 0. The rule now: the failure is cached and flagged; the background pass is
served from the cache; only the OPEN (retry=True) runs the scan again.
"""
import unittest

from pxrd_review.gui import review_gui as G


class UnreadablePdf(unittest.TestCase):
    def run_with(self, results):
        """get_analysis over a fake entry whose _serialize returns `results` in turn -> the calls made."""
        calls = []
        saved = (G._serialize, G._fingerprint, G.STATE.get('docx'), G.STATE.get('cache'))
        it = iter(results)
        try:
            G._serialize = lambda key: calls.append(key) or next(it)
            G._fingerprint = lambda key: [1]
            G.STATE['docx'] = {'k': '/nowhere/k.docx'}; G.STATE['cache'] = {}
            yield calls
        finally:
            G._serialize, G._fingerprint, G.STATE['docx'], G.STATE['cache'] = saved

    def test_a_failed_scan_is_cached_flagged_and_retried_only_by_the_open(self):
        bad = {'pdf': {'unreadable': True, 'pages': 0}}
        for calls in self.run_with([bad, bad, {'pdf': {'pages': 3}}]):
            G.get_analysis('k')                              # the background pass: runs the scan once
            self.assertEqual(calls, ['k']); self.assertTrue(G.STATE['cache']['k']['unreadable'])
            G.get_analysis('k')                              # the next pass: served from the cache, no re-scan
            self.assertEqual(calls, ['k'])
            G.get_analysis('k', retry=True)                  # the open: tried again
            self.assertEqual(calls, ['k', 'k'])
            G.get_analysis('k', retry=True)                  # and again, since it still failed
            self.assertEqual(calls, ['k', 'k', 'k']); self.assertFalse(G.STATE['cache']['k']['unreadable'])
            G.get_analysis('k', retry=True)                  # readable now: the open is served from the cache too
            self.assertEqual(calls, ['k', 'k', 'k'])

    def test_the_row_carries_a_badge_for_it(self):
        s = {'fixes': 0, 'cell': {'status': 'notext'}, 'files': {'pdf': True}, 'parse_error': None, 'lam': None,
             'mindat': {}, 'synthetic': False, 'findings': [], 'params': [], 'preview': {'severe': False, 'clean': False},
             'pdf': {'unreadable': True, 'pages': 0}}
        self.assertIn('.pdf unreadable', [b['label'] for b in G._badges(s)])
        s['pdf'] = {'pages': 3}
        self.assertNotIn('.pdf unreadable', [b['label'] for b in G._badges(s)])


if __name__ == '__main__':
    unittest.main()
