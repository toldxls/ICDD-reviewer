"""The .pdf pane's name layer (`mineral_names`): which words are IMA species, which look like a misspelt
one, and what the hover card carries. Every word below was seen in the corpus; the spelling rules were
set by a whole-corpus run (1264 papers), where the false positives were rocks built on a species name,
chemistry words, and transliterations of a name that is spelt right."""
import unittest

from pxrd_review import mineral_names as M


def _words(*texts):
    return [[0, 0, 1, 1, t] for t in texts]


class Lookup(unittest.TestCase):
    def test_exact_species_through_punctuation_and_diacritics(self):
        for w, key in (('quartz,', 'quartz'), ('(Åsgruvanite-(Ce))', 'asgruvanite-(ce)'),
                       ('nybøite', 'nybøite'), ('Kozłowskiite.', 'kozłowskiite'),
                       ('tobermorite-type', 'tobermorite')):
            self.assertEqual(M.lookup(M._clean(w)), ('exact', [key]), w)

    def test_ima_spelling_hyphens_and_transliteration(self):
        for w, key in (('magnesiohastingsite', 'magnesio-hastingsite'), ('metaautunite', 'meta-autunite'),
                       ('bastnaesite-(Ce)', 'bastnasite-(ce)'), ('boehmite', 'bohmite')):
            self.assertEqual(M.lookup(M._clean(w)), ('spelling', [key]), w)

    def test_root_of_suffixed_species(self):
        how, keys = M.lookup('davidite')
        self.assertEqual(how, 'root')
        self.assertEqual(sorted(keys), ['davidite-(ce)', 'davidite-(la)'])


class Spelling(unittest.TestCase):
    def test_near_misses_are_offered_the_species(self):
        for w, key in (('rhodocrosite', 'rhodochrosite'), ('flourapatite', 'fluorapatite'),
                       ('brackenbuschite', 'brackebuschite'), ('zinckenite', 'zinkenite'),
                       ('celestite', 'celestine')):
            self.assertIn(key, M.suggest(w), w)

    def test_no_suggestion_for_the_corpus_false_positives(self):
        for w in ('chromitite', 'sanidinite', 'phlogopitite', 'titanomagnetite', 'chalcogenide',
                  'lanthanide', 'antisite', 'granite', 'determine', 'composite', 'hornblende',
                  'tourmaline', 'calcites', 'quartz', 'monazite', 'site'):
            self.assertEqual(M.suggest(M._clean(w)), [], w)

    def test_short_or_shapeless_words_are_left_alone(self):
        self.assertEqual(M.suggest('pyrit'), [])           # too short to call
        self.assertEqual(M.suggest('quartzz'), [])         # not a species-name ending


class Page(unittest.TestCase):
    def test_classify_joins_a_line_end_hyphenation(self):
        hits = M.classify(_words('the', 'tobermo-', 'rite', 'structure'))
        self.assertEqual([(h['i'], h['keys']) for h in hits], [([1, 2], ['tobermorite'])])

    def test_classify_splits_dashed_pairs_and_skips_prose_species(self):
        hits = M.classify(_words('jarosite–alunite', 'ice', 'Ice'))
        toks = [h['token'] for h in hits]
        self.assertEqual(toks, ['jarosite', 'alunite', 'ice'])    # lowercase 'ice' is prose; 'Ice' a name
        self.assertEqual(hits[-1]['i'], [2])

    def test_page_carries_a_card_for_every_key(self):
        out = M.page(_words('Zinckenite', 'and', 'bastnaesite-(Ce)'))
        self.assertEqual([h['kind'] for h in out['hits']], ['spell', 'species'])
        self.assertEqual(set(out['species']), {'zinkenite', 'bastnasite-(ce)'})
        c = out['species']['bastnasite-(ce)']
        self.assertEqual(c['name'], 'Bastnäsite-(Ce)')
        self.assertIn('<sub>3</sub>', c['formula'])
        self.assertTrue(c['elements'])


if __name__ == '__main__':
    unittest.main()
