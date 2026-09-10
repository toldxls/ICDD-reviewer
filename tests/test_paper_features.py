"""tools/paper_features — the gauntlet's reader-independent denominator, and the GAUNTLET section
of tools/corpus_paper_extract.py.

    python3 -m unittest tests.test_paper_features -v
"""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
import paper_features as PF
import corpus_paper_extract as CPE


class Features(unittest.TestCase):
    def test_each_feature(self):
        f = PF.features('Electron microprobe analyses (wt.%): SiO2 46.30, MgO 29.05, CaO 20.10, FeO 0.40, H2O 3.20.\n'
                        'Table 4. Bond-valence analysis (vu) for testite.\n'
                        'Table 2. Atom coordinates and displacement parameters.\n'
                        'The Gladstone-Dale compatibility index is superior.\n'
                        'Optically biaxial (+), α = 1.600, β = 1.610, γ = 1.620; 2V = 60°.')
        self.assertEqual(f, {'epma': True, 'bv': True, 'coords': True, 'gd': True, 'optics': True})
        self.assertTrue(PF.is_target(f))
        self.assertEqual(PF.features('A structure refinement of nothing in particular.'), {k: False for k in PF.HAS_KEYS})

    def test_coordinates_by_shape(self):
        self.assertTrue(PF.features('Atom x y z Ueq\n')['coords'])                                   # a header
        self.assertTrue(PF.features('Ti1 0.00000 0.00000 0.00000\nO1 0.3048(2) 0.3048(2) 0.000\nO2 0.69521 0.69521 0.00000\n')['coords'])   # three rows
        self.assertFalse(PF.features('with the Ueq of each H set to 1.5 times that of the donor O atom')['coords'])     # prose about Ueq is not a table
        self.assertFalse(PF.features('Ti1 0.00000 0.00000 0.00000\n')['coords'])

    def test_epma_needs_oxides_and_an_analysis(self):
        self.assertFalse(PF.features('SiO2 46.30 wt%')['epma'])                                     # one oxide
        self.assertFalse(PF.features('SiO2 MgO CaO FeO')['epma'])                                   # no wt%


class Gauntlet(unittest.TestCase):
    def _paper(self, has, **st):
        f = {k: {'status': 'none', 'detail': '', 'value': None} for k in CPE.READERS}
        for k, v in st.items():
            f[k.replace('_', '.')]['status'] = v
        return {'fields': f, 'has': has, 'composition': None}

    def test_subset_rates_and_composites(self):
        full = {k: True for k in PF.HAS_KEYS}; part = dict(full, bv=False)
        papers = {'a.pdf': self._paper(full, epma='agrees', bv_table='agrees', coords='agrees', gd='agrees', bv_params='agrees', optics_n='agrees'),
                  'b.pdf': self._paper(full, epma='agrees', bv_table='unverified', coords='none', gd='nooracle'),
                  'c.pdf': self._paper(part, epma='agrees', bv_table='agrees', coords='agrees', gd='agrees')}
        out = CPE.gauntlet_lines(papers)
        self.assertIn('S = 2 papers', out[0])                                                       # c prints no bond-valence table: not in S
        epma = next(l for l in out if l.strip().startswith('epma')); bvt = next(l for l in out if l.strip().startswith('bv.table'))
        self.assertIn('2 100 %', epma); self.assertIn('1  50 %', bvt); self.assertIn('unverified 1', bvt); self.assertIn('b.pdf', bvt)
        self.assertIn('all agree 1/2; table + bond-valence table + coordinates + compatibility all agree 1/2', '\n'.join(out))
        base = {'a.pdf': self._paper(full, epma='agrees', bv_table='unverified'), 'c.pdf': papers['c.pdf']}
        out = CPE.gauntlet_lines(papers, base)
        self.assertTrue(any('DIFF on S' in l for l in out))
        self.assertTrue(any('bv.table' in l and 'unverified' in l and 'agrees' in l and 'a.pdf' in l for l in out))
        self.assertFalse(any('c.pdf' in l for l in out if 'DIFF' in l or '->' in l))              # the diff is restricted to S

    def test_no_subset(self):
        out = CPE.gauntlet_lines({'a.pdf': self._paper({})})
        self.assertEqual(len(out), 1); self.assertIn('S = 0', out[0])


if __name__ == '__main__':
    unittest.main()
