"""The band library — pxrd_review.bands, data/band_library.json beside data/band_windows.json.

    python3 -m unittest tests.test_bands -v

Formulas are invented or textbook ones; nothing of a paper is here.
"""
import io, contextlib, unittest

from pxrd_review import bands as B


class Groups(unittest.TestCase):
    def test_a_formula_s_groups(self):
        for formula, want in (('Ca(UO2)2(PO4)2·11H2O', ['UO2', 'PO4', 'H2O']),
                              ('Cu4(SO4)(OH)6', ['SO4', 'OH']),
                              ('Cu<sub>4</sub>(SO<sub>4</sub>)(OH)<sub>6</sub> · 2H<sub>2</sub>O', ['SO4', 'H2O', 'OH']),
                              ('Mn2+Cu2+2(As5+O4)2(OH)4(H2O)4', ['AsO4', 'H2O', 'OH']),       # valence superscripts are not part of a group
                              ('(N3-H4)2Mn2+[(U6+O2)4O4(S6+O4)2](H2O)4', ['UO2', 'SO4', 'NH4', 'H2O']),
                              ('Mn(PO3OH)(H2O)3', ['PO4', 'P-OH', 'H2O', 'OH']),              # an acid phosphate is a phosphate with a P–OH, and an O–H
                              ('Pb(As3+O3)Cl', ['AsO3']), ('Ca(As5+O3OH)·2H2O', ['AsO4', 'As-OH', 'H2O', 'OH']),
                              ('Pb5(VO4)3Cl', ['VO4']), ('Ca(VO)Si4O10·4H2O', ['V-O', 'Si-O', 'H2O']),
                              ('Mg2SiO4', ['SiO4']), ('NaAlSi3O8', ['Si-O']),
                              ('CaCO3', ['CO3']), ('Ca(C2O4)·H2O', ['C2O4', 'H2O']), ('NaNO3', ['NO3']),
                              ('Mg3(BO3)2', ['BO3']), ('CaB(OH)4', ['BO4', 'OH']), ('Ca3[B5O6(OH)6]FCl2·8H2O', ['BO3', 'BO4', 'H2O', 'OH']),
                              ('PbMoO4', ['MoO4']), ('MoO3·H2O', ['Mo-O', 'H2O']), ('CaWO4', ['WO4']), ('PbCrO4', ['CrO4']),
                              ('Pb4(TeO3)2(SO4)', ['SO4', 'TeO3']), ('Cu(SeO3)·2H2O', ['SeO3', 'H2O']), ('(H3O)Fe3(SO4)2(OH)6', ['SO4', 'H3O', 'OH']),
                              ('PbS', ['sulfide']), ('Ag3AsS3', ['sulfide']), ('NaCl', []), ('', [])):
            self.assertEqual(B.groups_of(formula), want, formula)

    def test_what_is_no_group(self):
        self.assertEqual(B.groups_of('UO2'), [])                                         # uraninite is no uranyl mineral
        self.assertEqual(B.groups_of('Mg(H2O)6·H2OH2O'), ['H2O'])                         # two waters side by side spell no hydroxyl
        self.assertNotIn('Si-O', B.groups_of('TiSi2'))                                    # a silicide has no Si–O
        self.assertEqual(B.groups_of('BaSO4'), ['SO4'])                                   # Ba is no boron

    def test_an_empirical_formula(self):
        # a mixed site before its oxygens is its dominant atom's group; a substituent under a quarter is no group of the mineral
        self.assertEqual(B.groups_of('PbCu[(Se0.8S0.2)Σ1.0O4](OH)2'), ['SeO4', 'OH'])
        self.assertEqual(B.groups_of('Cu3Al2(SO4)0.95(SiO4)0.04(AsO4)0.01(OH)12·3H2O'), ['SO4', 'H2O', 'OH'])
        self.assertEqual(B.groups_of('Ca2(SO4)0.39(OH)8'), ['SO4', 'OH'])
        self.assertEqual(B.groups_of('[Mg4Al2(OH)12](CO3)[Na(H2O)6]0.05[Si(OH)6]0.10·3H2O'), ['CO3', 'H2O', 'OH'])       # … nor is one inside a minor bracket
        self.assertEqual(B.display('Mn2+Cu2+2(As5+O4)2 (OH)4'), 'MnCu2(AsO4)2(OH)4')


class Library(unittest.TestCase):
    def test_the_table_is_whole(self):
        lib = B.library()
        keys = [g['key'] for g in lib['groups']]
        self.assertEqual(len(keys), len(set(keys)))
        for g in lib['groups']:
            for m in g['modes']:
                lo, hi = m['range']
                self.assertLess(lo, hi, (g['key'], m['mode']))
                self.assertIn(m['source'], lib['sources']); self.assertIn(m['active'], lib['activity'])
                if m.get('free') is not None:
                    self.assertTrue(lo <= m['free'] <= hi, (g['key'], m['mode']))          # a free-ion value outside its own range is a typing slip
        for a in lib['always']:
            self.assertLess(a['range'][0], a['range'][1])

    def test_each_numbered_mode_is_what_its_geometry_makes_it(self):
        # the free ion's geometry fixes what ν1 … ν4 ARE and where each is active: a row that calls ν2 of a carbonate an
        # in-plane bend, or lists ν1 of a sulfate as infrared-active, is wrong whatever its numbers
        rules = {'tetrahedral': {'ν1': ('symmetric stretch', 'R'), 'ν2': ('symmetric bend', 'R'), 'ν3': ('antisymmetric stretch', 'R+IR'), 'ν4': ('antisymmetric bend', 'R+IR')},
                 'planar': {'ν1': ('symmetric stretch', 'R'), 'ν2': ('out-of-plane bend', 'IR'), 'ν3': ('antisymmetric stretch', 'R+IR'), 'ν4': ('in-plane bend', 'R+IR')},
                 'pyramidal': {'ν1': ('symmetric stretch', 'R+IR'), 'ν2': ('symmetric', 'R+IR'), 'ν3': ('antisymmetric stretch', 'R+IR'), 'ν4': ('antisymmetric bend', 'R+IR')},
                 'linear': {'ν1': ('symmetric stretch', 'R'), 'ν2': ('bend', 'IR'), 'ν3': ('antisymmetric stretch', 'IR')}}
        seen = 0
        for g in B.library()['groups']:
            rule = rules.get(g.get('shape'))
            if not rule:
                continue
            for m in g['modes']:
                if m['mode'] in rule:
                    what, active = rule[m['mode']]
                    self.assertTrue(m['what'].replace('N–H ', '').startswith(what), (g['key'], m['mode'], m['what']))
                    self.assertEqual(m['active'], active, (g['key'], m['mode']))
                    seen += 1
            free = {m['mode']: m.get('free') for m in g['modes']}
            if g['shape'] in ('tetrahedral', 'pyramidal') and all(free.get(k) for k in ('ν1', 'ν2', 'ν3', 'ν4')):
                self.assertGreater(min(free['ν1'], free['ν3']), max(free['ν2'], free['ν4']), g['key'])      # stretches above bends
            if g['shape'] == 'planar' and all(free.get(k) for k in ('ν1', 'ν2', 'ν3', 'ν4')):
                self.assertTrue(free['ν3'] > free['ν1'] > free['ν2'] > free['ν4'], g['key'])               # CO3, NO3: 1415 > 1063 > 879 > 680
        self.assertGreaterEqual(seen, 60)
        shapes = {g['key']: g.get('shape') for g in B.library()['groups']}
        self.assertEqual((shapes['SO4'], shapes['CO3'], shapes['SeO3'], shapes['UO2'], shapes['NH4'], shapes['H3O'], shapes['BO3'], shapes['BO4']),
                         ('tetrahedral', 'planar', 'pyramidal', 'linear', 'tetrahedral', 'pyramidal', 'planar', 'tetrahedral'))

    def test_every_measured_window_belongs_to_a_mode(self):
        modes = {'%s %s' % (g['key'], m['mode']) for g in B.library()['groups'] for m in g['modes']}
        for name in B._windows():
            self.assertIn(name, modes, name)                                               # else the window is shipped and never shown

    def test_the_fundamentals_the_literature_agrees_on(self):
        free = {(g['key'], m['mode']): m.get('free') for g in B.library()['groups'] for m in g['modes']}
        for key, want in ((('SO4', 'ν1'), 983), (('SO4', 'ν3'), 1105), (('PO4', 'ν1'), 938), (('PO4', 'ν3'), 1017), (('AsO4', 'ν1'), 837), (('AsO4', 'ν3'), 878),
                          (('VO4', 'ν1'), 826), (('NH4', 'ν4'), 1400), (('H2O', 'bend'), 1595), (('CO3', 'ν1'), 1063)):
            self.assertEqual(free[key], want, key)

    def test_expected(self):
        rows = B.expected('Ca(UO2)2(PO4)2·11H2O')
        names = [B.label(r) for r in rows]
        self.assertEqual(names[0], 'H2O stretch'); self.assertEqual(names[-1], 'UO2 ν2')    # highest wavenumber first
        self.assertEqual(set(r['group'] for r in rows), {'UO2', 'PO4', 'H2O'})
        nu1 = next(r for r in rows if B.label(r) == 'UO2 ν1')
        self.assertTrue(nu1['published'] and 780 < nu1['published']['p5'] < nu1['published']['p95'] < 900)
        self.assertEqual(nu1['published_for'], 'any')
        self.assertEqual(next(r for r in B.expected('Ca(UO2)2(PO4)2·11H2O', 'raman') if B.label(r) == 'UO2 ν1')['published_for'], 'raman')
        self.assertIsNone(next(r for r in rows if B.label(r) == 'PO4 ν2')['published'])    # too few papers: the literature's range alone
        self.assertEqual(B.expected('NaCl'), [])
        self.assertEqual([B.label(r) for r in B.expected(groups=['CO3'])], ['CO3 ν3', 'CO3 ν1', 'CO3 ν2', 'CO3 ν4'])

    def test_identify_with_the_chemistry(self):
        f = 'Ca2(UO2)3(SO4)2(OH)6·4H2O'
        got = B.identify(832, f)
        own = [B.label(c) for c in got if c['in_formula']]
        self.assertEqual(own[0], 'UO2 ν1')
        self.assertEqual(own[1:], ['OH bend', 'H2O lib'])                                   # the broad regions after the mode that stands on its own
        self.assertIn('AsO4 ν1', [B.label(c) for c in got if c['in_formula'] is False])     # stands there too — in another chemistry
        self.assertEqual([B.label(c) for c in B.identify(1010, f) if c['in_formula']][0], 'SO4 ν1')
        self.assertEqual([B.label(c) for c in B.identify(1630, f) if c['in_formula']], ['H2O bend'])
        self.assertEqual([c for c in B.identify(1450, f) if c['in_formula']], [])           # nothing of this formula stands at 1450
        self.assertIn('CO3 ν3', [B.label(c) for c in B.identify(1450, f) if c['in_formula'] is False])
        self.assertEqual([c['group'] for c in B.identify(2920, 'NaCl') if c['in_formula'] is not False], ['C-H'])           # organic matter, whatever the mineral
        self.assertEqual(B.identify(300, 'NaCl')[-1]['group'], 'M-O')

    def test_identify_blind(self):
        got = B.identify(832)
        self.assertTrue(all(c['in_formula'] is None for c in got))
        names = [B.label(c) for c in got]
        self.assertIn('UO2 ν1', names); self.assertIn('AsO4 ν1', names); self.assertNotIn('ν(M–S)', names)
        self.assertIn('ν(M–S)', [B.label(c) for c in B.identify(350, 'PbS')])

    def test_command_line(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(B.main(['Cu4(SO4)(OH)6', '--at', '985,1450']), 0)
        text = out.getvalue()
        self.assertIn('groups: SO4 (sulfate), OH (hydroxyl)', text)
        self.assertIn('985 cm⁻¹: SO4 ν1', text); self.assertIn('1450 cm⁻¹: no group of this formula is expected here', text)
        self.assertIn('of another chemistry: ', text)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(B.main(['--at', '1630']), 0); self.assertEqual(B.main(['--groups']), 0)
        self.assertIn('1630 cm⁻¹: ', out.getvalue()); self.assertIn('H2O bend', out.getvalue()); self.assertIn('uranyl', out.getvalue())
        self.assertEqual(B.resolve('Ca(UO2)2(PO4)2'), ('Ca(UO2)2(PO4)2', ''))
        self.assertEqual(B.resolve('notamineralofanysnapshot'), ('notamineralofanysnapshot', ''))


class FittedBands(unittest.TestCase):
    def test_a_fitted_band_against_the_formula(self):
        from pxrd_review import spectrum as M
        comps = [{'pos': 832.0}, {'pos': 1010.0}, {'pos': 1450.0}, {'pos': 2920.0}, {'pos': 3400.0}, {'pos': 250.0}]
        blind = M.inferred(comps, 'raman')
        self.assertIn('UO2 ν1', blind[0]['suggest'])
        got = M.inferred(comps, 'raman', 'Ca2(UO2)3(SO4)2(OH)6·4H2O')
        self.assertEqual(got[0]['suggest'][0], 'UO2 ν1'); self.assertTrue(got[0]['distance'].startswith('U–O 1.7'))
        self.assertEqual(got[1]['suggest'][0], 'SO4 ν1')
        self.assertTrue(got[2]['suggest'][0].startswith('no group of the formula (elsewhere: '), got[2])
        self.assertTrue(got[3]['suggest'][0].startswith('C–H window'))
        self.assertEqual(got[4]['suggest'], ['OH stretch']); self.assertTrue(got[4]['distance'].startswith('O···O 2.'))
        self.assertEqual(got[5]['suggest'][0], 'UO2 ν2')
        # a phosphate has no uranyl: no U–O distance is read off a band at 832
        self.assertEqual(M.inferred([{'pos': 832.0}], 'raman', 'Ca5(PO4)3F')[0]['distance'], '')


if __name__ == '__main__':
    unittest.main()
