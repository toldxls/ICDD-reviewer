"""The Mindat & cross-source pane's lookup box: /api/mn/search answers from the local snapshot.

    python3 -m unittest tests.test_gui_mn -v
"""
import unittest


def _snapshot():
    from pxrd_review import mindat
    return bool((mindat.struct_db() or {}).get('recs'))


class MindatLookup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pxrd_review.gui import review_gui as G
        G._ALLOWED_HOSTS = set(); cls.c = G.app.test_client(); cls.G = G

    @unittest.skipUnless(_snapshot(), 'no Mindat snapshot')
    def test_a_species_and_a_group_from_the_snapshot(self):
        r = self.c.get('/api/mn/search?q=quartz').get_json()
        self.assertEqual(r['hits'][0]['name'], 'Quartz')
        self.assertTrue(r['hits'][0]['formula'] and r['hits'][0]['a'], r['hits'][0])
        self.assertTrue(r['total'] >= 1)
        r = self.c.get('/api/mn/search?q=apatite%20group').get_json()
        self.assertTrue(r['group'] and r['group']['n'] >= 3, r.get('group'))
        r = self.c.get('/api/mn/search?q=Asgruvanite-(Ce)').get_json()          # the ASCII spelling resolves through the usual fallbacks
        self.assertTrue(r['hits'] and 'sgruvanite' in r['hits'][0]['name'], r['hits'][:1])

    @unittest.skipUnless(_snapshot(), 'no Mindat snapshot')
    def test_species_by_element(self):
        r = self.c.get('/api/mn/elements?has=Si,O&only=1').get_json()
        names = [h['name'] for h in r['hits']]
        self.assertIn('Quartz', names)                                           # the simplest chemistries first
        self.assertTrue(all(set(h['elements']) <= {'Si', 'O'} for h in r['hits']), names[:5])
        r = self.c.get('/api/mn/elements?has=Sc&not=Fe').get_json()
        self.assertTrue(r['total'] > 5 and all('Sc' in h['elements'] and 'Fe' not in h['elements'] for h in r['hits']))
        self.assertNotIn('Fe', r['counts']); self.assertEqual(r['counts']['Sc'], r['total'])

    def test_a_short_or_unknown_query_is_empty_not_an_error(self):
        self.assertEqual(self.c.get('/api/mn/search?q=q').get_json()['hits'], [])
        r = self.c.get('/api/mn/search?q=zzqxnosuchmineral').get_json()
        self.assertEqual((r['hits'], r['group']), ([], None))


if __name__ == '__main__':
    unittest.main()
