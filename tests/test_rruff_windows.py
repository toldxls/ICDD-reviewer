"""tools/rruff_windows.py — the OMNIC library reader, the mode assignment by geometry and free-ion ratios, the windows."""
import os, sys, struct, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from tools import rruff_windows as RW
from pxrd_review import bands as BD


class StorePath(unittest.TestCase):
    """The readers over a fetched store: which spectra each `which` walks, the metadata carried, the pick per id, the writer's merge."""
    @classmethod
    def setUpClass(cls):
        import json, tempfile
        from tests.rruff_fixture import member, gauss, write_store, GRID, BROAD, IR
        cls.tmp = tempfile.mkdtemp(prefix='rrw_')
        cls.store = os.path.join(cls.tmp, 'store')
        write_store(cls.store, {
            'excellent_oriented': [member('Quartz', 'R040031', '532', 'processed', GRID, gauss(GRID, [464, 206], [100, 30]))],
            'poor_unoriented': [member('Quartz', 'R040031', '780', 'processed', GRID, gauss(GRID, [464, 206], [100, 30])),
                                member('Magnesio-riebeckite', 'X050031', '785', 'processed', GRID, gauss(GRID, [670], [100]), chem='Na_2_(Mg_3_Fe_2_)Si_8_O_22_(OH)_2_')],
            'LR-Raman': [member('Gypsum', 'R040029', '532', 'processed', BROAD, gauss(BROAD, [1008, 3400], [100, 20], w=12), chem='CaSO_4_·2H_2_O')],
            'infrared': [member('Calcite', 'R040070', '', 'raw', IR, gauss(IR, [1420, 875], [1, 0.3], w=20), chem='CaCO_3_', tech='Infrared')]})

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_which_spectra_each_reader_walks(self):
        raman = RW.spectra_of(self.store, 'raman')
        self.assertEqual(sorted((m['name'], m['id'], m['laser']) for m, _x, _y in raman), [('Magnesio-riebeckite', 'X050031', '785'), ('Quartz', 'R040031', '532'), ('Quartz', 'R040031', '780')])
        broad = RW.spectra_of(self.store, 'broad')
        self.assertEqual([(m['name'], m['quality'], round(x[-1])) for m, x, _y in broad], [('Gypsum', 'broad', 4398)])
        ir = RW.spectra_of(self.store, 'ir')
        self.assertEqual([(m['name'], m['technique'], m['kind']) for m, _x, _y in ir], [('Calcite', 'infrared', 'raw')])
        with self.assertRaises(ValueError):
            RW.spectra_of(self.store, 'xrd')
        self.assertEqual(RW.label_of(raman[0][0]).split()[1], raman[0][0]['id'])

    def test_the_pick_per_id_and_the_merging_writer(self):
        import json
        from pxrd_review import rruff as R
        # the best of one id by rruff.rank: 532 nm unoriented before 780 nm, excellent-oriented after unoriented poor? no: quality first
        metas = [m for m, _x, _y in RW.spectra_of(self.store, 'raman') if m['id'] == 'R040031']
        best = min(metas, key=R.rank)
        self.assertEqual((best['quality'], best['laser']), ('excellent', '532'))
        # the writer replaces only the keys a run owns
        path = os.path.join(self.tmp, 'win.json')
        RW.write_windows({'SO4 ν1': {'p50': 990, 'minerals': 9}, 'H2O stretch': {'p50': 3300, 'minerals': 4}}, 'raman', 'run one', path)
        RW.write_windows({'H2O stretch': {'p50': 3450, 'minerals': 12}, 'OH stretch': {'p50': 3600, 'minerals': 5}}, 'broad', 'run two', path)
        doc = json.load(open(path, encoding='utf-8'))
        self.assertEqual({k: v['p50'] for k, v in doc['windows'].items()}, {'H2O stretch': 3450, 'OH stretch': 3600, 'SO4 ν1': 990})   # the Raman run's O–H key was not its to write
        self.assertEqual(sorted(doc['sources']), ['broad', 'raman']); self.assertEqual(doc['technique'], 'raman')
        RW.write_windows({'SO4 ν3': {'p50': 1120, 'minerals': 9}}, 'raman', 'run three', path)
        doc = json.load(open(path, encoding='utf-8'))
        self.assertEqual(sorted(doc['windows']), ['H2O stretch', 'OH stretch', 'SO4 ν3'])                 # the Raman keys replaced, the O–H ones kept
        ir = os.path.join(self.tmp, 'ir.json')
        RW.write_windows({'SO4 ν3': {'p50': 1110, 'minerals': 10}}, 'ir', 'ir run', ir)
        self.assertEqual(json.load(open(ir, encoding='utf-8'))['technique'], 'ir')

    def test_the_runs_on_the_fixture_store(self):
        # the broad-scan run measures the O–H keys of a water-only mineral; the infrared run anchors on ν3; activity and evidence write their reports
        import json, io, contextlib
        from pxrd_review import bands as B
        out = os.path.join(self.tmp, 'out')
        if not B.resolve('gypsum')[1]:
            self.skipTest('no Mindat snapshot for the formula lookup')
        with contextlib.redirect_stdout(io.StringIO()):
            RW.main([self.store, out, '--which', 'broad'])
        recs = [json.loads(l) for l in open(os.path.join(out, 'rruff_windows.jsonl'), encoding='utf-8')]
        self.assertEqual({(r['group'], r['mode'], r['mineral']) for r in recs}, {('H2O', 'stretch', 'Gypsum')})        # gypsum: water, no hydroxyl; its 3400 band
        self.assertAlmostEqual(recs[0]['pos'], 3400, delta=4)
        with contextlib.redirect_stdout(io.StringIO()):
            RW.main([self.store, out, '--which', 'ir'])
        recs = [json.loads(l) for l in open(os.path.join(out, 'rruff_windows.jsonl'), encoding='utf-8')]
        self.assertEqual({(r['group'], r['mode']) for r in recs}, {('CO3', 'ν3'), ('CO3', 'ν2')})                      # calcite's infrared ν3 (anchor) and ν2
        with contextlib.redirect_stdout(io.StringIO()):
            RW.main([self.store, out, '--activity'])
        rep = open(os.path.join(out, 'rruff_activity_report.txt'), encoding='utf-8').read()
        self.assertIn('ACTIVITY', rep)
        win = os.path.join(self.tmp, 'ev_ir.json')
        keep = RW.DATA
        try:                                                                         # the evidence report reads the data folder: a scratch one here
            RW.DATA = self.tmp
            json.dump({'windows': {'CO3 ν2': {'p5': 860, 'p25': 865, 'p50': 872, 'p75': 878, 'p95': 884, 'n': 12, 'minerals': 9, 'dropped': 0}}}, open(os.path.join(self.tmp, 'band_windows_rruff_ir.json'), 'w'))
            with contextlib.redirect_stdout(io.StringIO()):
                RW.main([self.store, out, '--evidence'])
            ev = open(os.path.join(out, 'library_evidence.txt'), encoding='utf-8').read()
            self.assertIn('CO3      ν2', ev); self.assertIn('860–884 (872) 9', ev)                                    # the infrared column from the scratch file; the Raman column from the shipped data
            self.assertIn('check-tagged rows', ev)
        finally:
            RW.DATA = keep

    def test_composites_and_orientation_on_the_fixture_store(self):
        import json, gzip, io, contextlib
        from pxrd_review import bands as B
        if not B.resolve('quartz')[1]:
            self.skipTest('no Mindat snapshot for the formula lookup')
        path = os.path.join(self.tmp, 'comp.json.gz')
        with contextlib.redirect_stdout(io.StringIO()):
            RW.composites(self.store, path)
        comp = json.load(gzip.open(path, 'rt', encoding='utf-8'))['composites']
        self.assertEqual(comp, {})                                                   # three minerals a group: none here has MIN_MINERALS
        self.assertEqual(RW._resample([1.0, 2.0, 3.0], [10.0, 20.0, 30.0], 0.0, 3.0, 1.0), [None, 10.0, 20.0, 30.0])
        opath = os.path.join(self.tmp, 'orient.json')
        with contextlib.redirect_stdout(io.StringIO()):
            RW.orientation(self.store, opath)
        self.assertEqual(json.load(open(opath, encoding='utf-8'))['groups'], {})      # no sample with three orientations in the fixture
        keep = RW.DATA
        try:
            RW.DATA = self.tmp
            with contextlib.redirect_stdout(io.StringIO()):
                RW.main([self.store, os.path.join(self.tmp, 'o2'), '--composites'])  # the flag route; DATA pointed at scratch so the shipped file is untouched
            self.assertTrue(os.path.isfile(os.path.join(self.tmp, 'band_composites.json.gz')))
        finally:
            RW.DATA = keep
    def test_bands_of_and_by_species(self):
        from pxrd_review import rruff as R
        from tests.rruff_fixture import gauss, GRID
        pk = R.bands_of(GRID, gauss(GRID, [464, 206, 900, 120], [100, 30, 3, 50]))
        self.assertEqual([round(p) for p, _h in pk], [206, 464])                                   # the lattice band and the 3 % band left out
        self.assertEqual(len(R.bands_of(GRID, gauss(GRID, [300, 400, 500], [100, 80, 60]), n=2)), 2)
        st = R.open_store(self.store)
        by = R.by_species(st)
        self.assertEqual(sorted(by), ['calcite', 'gypsum', 'magnesio-riebeckite', 'quartz'])
        self.assertEqual([m['laser'] for _i, m in by['quartz']], ['532', '780'])
        self.assertEqual(R.by_species(None), {})
        R.close_stores()


from tests.rruff_fixture import write_library, omnic_gauss as gauss


class Reader(unittest.TestCase):
    def test_names_by_pointer_and_both_record_kinds(self):
        with tempfile.TemporaryDirectory() as d:
            write_library(d, [('AbhuriteR060227_clean', 'field', gauss([300], [10])), ('Sanbornite R050001_processed', 'pascal', gauss([400], [10])),
                              ('Whiteite-(CaFeMg)R060912_785processed', 'field', gauss([500], [10]))])
            got = RW.spectra_of(d, 'raman')
            self.assertEqual([(m['name'], m['id'], m['kind']) for m, _x, _y in got], [('Abhurite', 'R060227', 'clean'), ('Sanbornite', 'R050001', 'processed'), ('Whiteite-(CaFeMg)', 'R060912', 'processed')])
            self.assertEqual(RW.spectra_of(d, 'broad'), [])                                        # an OMNIC copy has Raman only
            x, y = got[1][1], got[1][2]
            self.assertEqual((len(x), len(y), round(x[0], 3), round(x[-1], 2)), (759, 759, 32.784, 1494.56))
            self.assertAlmostEqual(x[max(range(759), key=lambda k: y[k])], 400, delta=2)

    def test_split_name(self):
        self.assertEqual(RW.split_name('Whiteite-(CaFeMg)R060912_785processed'), ('Whiteite-(CaFeMg)', 'R060912', 'processed'))
        self.assertEqual(RW.split_name('Sanbornite R050001_raw'), ('Sanbornite', 'R050001', 'raw'))
        self.assertEqual(RW.split_name('AbhuriteR060227_corrected'), ('Abhurite', 'R060227', 'corrected'))
        self.assertEqual(RW.split_name('QuartzR060604_processe'), ('Quartz', 'R060604', 'processed'))


class Assignment(unittest.TestCase):
    def test_a_sulfate_by_free_ion_ratios(self):
        # barite-like: ν1 988 strongest, ν3 1140 and 1085, ν4 617, ν2 453, a lattice band at 140 and a stray at 760
        pk = [(160, 60), (453, 20), (617, 25), (760, 10), (988, 100), (1085, 15), (1140, 20)]
        free = {'ν1': 983, 'ν3': 1105, 'ν4': 611, 'ν2': 450}
        got = RW.assign('tetrahedral', list(free), pk, free)
        self.assertEqual(got['ν1'], [988]); self.assertEqual(sorted(got['ν3']), [1085, 1140]); self.assertEqual(got['ν4'], [617]); self.assertEqual(got['ν2'], [453])
        self.assertEqual(sorted(got['(unassigned)']), [160, 760])                 # near no mode of the ion: a lattice band, a stray
        # the strongest band far from the free-ion ν1: the spectrum is left out, nothing assigned
        got = RW.assign('tetrahedral', list(free), [(450, 100), (988, 30)], free)
        self.assertEqual(dict(got), {'(ν1 not dominant)': [450]})

    def test_a_combined_bend_row_and_a_planar_ion(self):
        free = {'ν1': 897, 'ν3': 837, 'ν2, ν4': 317}
        got = RW.assign('tetrahedral', list(free), [(318, 20), (340, 10), (820, 30), (897, 100)], free)
        self.assertEqual((got['ν1'], got['ν3'], sorted(got['ν2, ν4'])), ([897], [820], [318, 340]))
        free = {'ν1': 1063, 'ν3': 1415, 'ν2': 879, 'ν4': 680}
        got = RW.assign('planar', list(free), [(155, 50), (283, 40), (712, 15), (1086, 100), (1436, 8)], free)
        self.assertEqual((got['ν1'], got['ν4'], got['ν3']), ([1086], [712], [1436]))

    def test_the_infrared_anchor(self):
        free = {'ν1': 983, 'ν3': 1105, 'ν4': 611, 'ν2': 450}
        # an infrared sulfate: ν3 dominates; the anchor is the strongest band near the free ν3, ν1 is placed by ratio like the rest
        pk = [(450, 10), (600, 30), (640, 25), (985, 20), (1090, 100), (1150, 80), (1500, 5)]
        self.assertEqual(RW.ir_anchor(pk, free), ('ν3', 1090))
        got = RW.assign('tetrahedral', list(free), pk, free, anchor=RW.ir_anchor(pk, free))
        self.assertEqual((got['ν3'], got['ν1'], sorted(got['ν4']), got['ν2']), ([1090], [985], [600, 640], [450]))
        self.assertEqual(got['(unassigned)'], [1150])                                   # 1150 is near no mode once 1090 is ν3; 1500 is under ASSIGN_STRONG
        # no band near ν3 or ν1: left out; a group with no free value: '(no anchor)'
        self.assertIsNone(RW.ir_anchor([(300, 100), (700, 50)], free))
        got = RW.assign('tetrahedral', ['ν1', 'ν3'], [(900, 100)], {}, anchor=('ν3', 900))
        self.assertEqual(dict(got), {'(no anchor)': [900]})

    def test_the_o_h_region_of_a_broad_scan(self):
        from tests.rruff_fixture import gauss, BROAD
        y = gauss(BROAD, [1008, 1620, 3420], [100, 8, 25], w=14)
        got = RW.oh_bands(BROAD, y)
        self.assertAlmostEqual(got['stretch'], 3420, delta=3); self.assertAlmostEqual(got['bend'], 1620, delta=3)
        hump = [v + 40 * __import__('math').exp(-((x - 3100) / 500) ** 2) for x, v in zip(BROAD, gauss(BROAD, [1008], [100], w=14))]
        self.assertIsNone(RW.oh_bands(BROAD, hump)['stretch'])                          # a 1000 cm⁻¹ hump is no stretch
        self.assertEqual(RW.oh_bands(BROAD[:10], y[:10]), {'stretch': None, 'bend': None})

    def test_window_and_verdict(self):
        vals = [(980 + k, 'm%d' % k) for k in range(20)] + [(1300, 'odd')]
        w = RW.window(vals)
        self.assertEqual((w['minerals'], w['dropped'], w['p50']), (20, 1, 990))
        self.assertEqual(RW.verdict(w, 960, 1050), 'agrees')
        self.assertIn('above the range', RW.verdict(w, 900, 960))
        self.assertEqual(RW.verdict(dict(w, minerals=2), 960, 1050), 'too few minerals')


class InTheLibrary(unittest.TestCase):
    def test_a_rruff_window_stands_in_for_a_missing_paper_window(self):
        rows = {BD.label(r): r for r in BD.expected('CaSO4')}
        self.assertTrue(rows['SO4 ν1']['rruff'] and rows['SO4 ν1']['rruff']['minerals'] >= 8)
        self.assertEqual(rows['SO4 ν1']['published_for'], 'any')                     # the papers' window first
        rows = {BD.label(r): r for r in BD.expected('Mg2SiO4')}
        self.assertEqual(rows['SiO4 ν4']['published_for'], 'rruff')                  # no paper window: the spectra's
        self.assertIn('RRUFF spectra', '\n'.join(BD.table('Mg2SiO4')))


if __name__ == '__main__':
    unittest.main()
