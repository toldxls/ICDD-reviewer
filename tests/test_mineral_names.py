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


def _has_parents():
    from pxrd_review import mindat
    return any(g.get('parent') for g in (mindat._db() or {}).get('groups', {}).values())


class LineBreaks(unittest.TestCase):
    """A name the line broke is read whole, whichever hyphen the break fell on (1,270 names on the corpus
    were lost at a line-end hyphen that was the name's own, before 0.12.1)."""
    def test_break_at_the_names_own_hyphen(self):
        for texts, kind, tok in ((('crichtonite-', 'group', 'minerals'), 'group', 'crichtonite'),
                                 (('Åsgruvanite-', '(Ce)'), 'species', 'asgruvanite-(ce)'),
                                 (('jahnsite-', '(CaMnMg)'), 'species', 'jahnsite-(camnmg)'),
                                 (('jarosite-', 'type'), 'species', 'jarosite')):
            hits = M.classify(_words(*texts))
            self.assertEqual([(h['kind'], h['i'], h['token']) for h in hits], [(kind, [0, 1], tok)], texts)

    def test_suspended_hyphen_reads_the_name_alone(self):
        hits = M.classify(_words('sphalerite-', 'and', 'galena-bearing'))
        self.assertEqual([(h['token'], h['i']) for h in hits], [('sphalerite', [0]), ('galena', [2])])

    def test_a_compound_that_names_nothing_stays_unmarked(self):
        self.assertEqual(M.classify(_words('graphite-', 'monochromatized')), [])   # as on one line


class Names(unittest.TestCase):
    def test_every_species_is_found_from_its_own_name(self):
        recs = M._index()[0]
        missed = []
        for key, r in recs.items():
            texts = r['name'].split()
            hits = M.classify(_words(*texts))
            if not any(key in (h.get('keys') or []) for h in hits):
                missed.append(r['name'])
        self.assertLessEqual(len(missed), 2, missed)        # Mindat's own odd records ('Nioboixiolite-([])')

    def test_two_names_in_one_box(self):
        for text in ('jarosite–alunite', 'jarosite-alunite'):
            hits = M.classify(_words(text))
            self.assertEqual([(h['token'], h['i']) for h in hits], [('jarosite', [0]), ('alunite', [0])], text)
        hits = M.classify(_words('bismuthinite-', 'aikinite', 'series'))
        self.assertEqual([(h['token'], h['i']) for h in hits], [('bismuthinite', [0, 1]), ('aikinite', [0, 1])])

    def test_polytype_suffix_is_the_species(self):
        self.assertEqual(M.lookup('dioskouriite-2m'), ('polytype', ['dioskouriite']))
        self.assertEqual(M.lookup('magnesio-hastingsite')[0], 'exact')      # a hyphenated IMA name is no pair


class Groups(unittest.TestCase):
    """A group named in the paper is the group, not the species it is named after; its card lists
    every member, its subgroups' included (the snapshot's groups carry their parent since 0.12.1)."""
    def _one(self, *texts):
        hits = M.classify(_words(*texts))
        self.assertEqual(len(hits), 1, hits)
        return hits[0]

    def test_affix_and_following_word_name_the_group(self):
        for texts, idx in ((('crichtonite-group',), [0]), (('crichtonite', 'group.'), [0, 1]),
                           (('Crichtonite', 'Group'), [0, 1]), (('crichtonite–group',), [0])):
            h = self._one(*texts)
            self.assertEqual((h['kind'], h['i']), ('group', idx), texts)
            self.assertEqual(M.group_card(h['gid'])['name'], 'Crichtonite Group')

    def test_species_stays_a_species(self):
        self.assertEqual(self._one('crichtonite')['kind'], 'species')
        self.assertEqual(self._one('crichtonite,', 'group')['kind'], 'species')   # punctuation between

    def test_bare_group_names_and_prose_words(self):
        self.assertEqual(M.group_card(self._one('tourmaline,')['gid'])['name'], 'Tourmaline')
        self.assertEqual(M.classify(_words('iron', 'oxide')), [])
        self.assertEqual(self._one('iron', 'group')['kind'], 'group')     # named as a group before 'group'

    @unittest.skipUnless(_has_parents(), 'this Mindat cache predates group parents (refresh it)')
    def test_supergroup_lists_its_subgroups_members(self):
        h = self._one('Apatite', 'Supergroup')
        c = M.group_card(h['gid'])
        self.assertEqual(c['name'], 'Apatite Supergroup')
        names = {m['name'] for sec in c['sections'] for m in sec['members']}
        self.assertIn('Fluorapatite', names)                    # a member of the Apatite GROUP below it
        self.assertEqual(c['n'], len(names))

    @unittest.skipUnless(_has_parents(), 'this Mindat cache predates group parents (refresh it)')
    def test_root_name_group(self):
        c = M.group_card(M.pick_group('hornblende'))
        self.assertIn('Magnesio-hornblende', [m['name'] for sec in c['sections'] for m in sec['members']])
        self.assertIn('Amphibole Supergroup', c['above'])


if __name__ == '__main__':
    unittest.main()
