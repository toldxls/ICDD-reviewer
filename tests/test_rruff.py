"""The RRUFF spectra fetched from rruff.net (pxrd_review.rruff): the member files read, the store built and read back, the
union with a Thermo OMNIC copy, the order a mineral's spectra are offered in, and the window's routes — the download
served from files (SOURCE pointed at a file:// folder); nothing is fetched from the network here.

    python3 -m unittest tests.test_rruff -v
"""
import os, io, json, shutil, tempfile, time, unittest, zipfile

from pxrd_review import rruff as R


def member(name, rid, laser, kind, x, y, chem='SiO_2_', tech='Raman'):
    head = ['##NAMES=%s' % name, '##RRUFFID=%s' % rid, '##IDEAL CHEMISTRY=%s' % chem, '##LOCALITY=Somewhere', '##OWNER=RRUFF', '##SOURCE=a museum',
            '##DESCRIPTION=d', '##STATUS=s', '##URL=https://www.rruff.net/odr/rruff_sample/%s' % rid, '##FILETYPE=%s %s' % (tech, 'RAW' if kind == 'raw' else 'Processed')]
    if tech == 'Raman':
        head.append('##RAMAN WAVELENGTH=%s' % laser)
    body = ['%.4f, %.6g' % (a, b) for a, b in zip(x, y)]
    fname = '%s__%s__%s__%s______%s_Data_%s__%s.txt' % (name, rid, tech, laser, tech, 'RAW' if kind == 'raw' else 'Processed', 'ab' * 14)
    return fname, '\n'.join(head + [''] + body + ['##END=', '']).encode('utf-8')


def gauss(x, centres, heights, w=6.0):
    import math
    return [sum(h * math.exp(-4 * math.log(2) * ((v - c) / w) ** 2) for c, h in zip(centres, heights)) for v in x]


class Fetch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix='rruff_')
        src = os.path.join(cls.tmp, 'src'); os.makedirs(os.path.join(src, 'raman')); os.makedirs(os.path.join(src, 'infrared'))
        x = [150.0 + 0.5 * k for k in range(2400)]
        xb = [100.0 + 2.0 * k for k in range(1950)]
        def zipped(path, members):
            with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
                for fname, data in members:
                    z.writestr(fname, data)
        zipped(os.path.join(src, 'raman', 'poor_unoriented.zip'), [
            member('Quartz', 'R040031', '780', 'processed', x, gauss(x, [464, 206], [100, 30])),
            member('Quartz', 'R040031', '780', 'raw', x, gauss(x, [464, 206], [100, 30])),
            member('Quartz', 'R050125', '532', 'processed', x, gauss(x, [464, 206], [100, 30])),
            member('Calcite', 'R040070', '532', 'processed', list(reversed(x)), list(reversed(gauss(x, [1086, 712, 281], [100, 10, 20]))), chem='CaCO_3_'),
            ('notes/readme.txt', b'not a spectrum\n'),
            member('Broken', 'R000001', '532', 'processed', x[:3], [1, 2, 3])])
        zipped(os.path.join(src, 'raman', 'excellent_unoriented.zip'), [
            member('Quartz', 'R040031', '532', 'processed', x, gauss(x, [464, 206], [100, 30]))])
        zipped(os.path.join(src, 'raman', 'LR-Raman.zip'), [
            member('Gypsum', 'R040029', '532', 'processed', xb, gauss(xb, [1008, 3400], [100, 20]), chem='CaSO_4_·2H_2_O')])
        zipped(os.path.join(src, 'infrared', 'RAW.zip'), [
            member('Calcite', 'R040070', '', 'raw', xb, gauss(xb, [1420, 875], [1, 0.3]), chem='CaCO_3_', tech='Infrared')])
        cls.keep = (R.SOURCE, os.environ.get('PXRD_RRUFF_STORE'))
        R.SOURCE = 'file://' + src + '/'
        cls.store = os.path.join(cls.tmp, 'store'); os.environ['PXRD_RRUFF_STORE'] = cls.store
        R._STORE.clear(); R.PROGRESS.clear()

    @classmethod
    def tearDownClass(cls):
        R.SOURCE = cls.keep[0]
        if cls.keep[1] is None:
            os.environ.pop('PXRD_RRUFF_STORE', None)
        else:
            os.environ['PXRD_RRUFF_STORE'] = cls.keep[1]
        R._STORE.clear(); R.PROGRESS.clear()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_a_member_file(self):
        fname, data = member('Abramovite', 'R070037', '532', 'processed', [150.1822, 150.6643, 151.1], [0, 34.88, 2], chem='Pb_2_SnInBiS_7_')
        head, x, y = R.parse_member(data.decode('utf-8'))
        self.assertEqual((head['NAMES'], head['RRUFFID'], head['FILETYPE'], x, y[:2]), ('Abramovite', 'R070037', 'Raman Processed', [150.1822, 150.6643, 151.1], [0.0, 34.88]))
        m = R.member_meta(fname, head, 'poor_unoriented')
        self.assertEqual((m['name'], m['id'], m['kind'], m['laser'], m['quality'], m['orient'], m['technique'], m['chem']),
                         ('Abramovite', 'R070037', 'processed', '532', 'poor', 'unoriented', 'raman', 'Pb2SnInBiS7'))
        self.assertEqual(R.plain_chem('[box]Ca_2_(Mg_4.5-2.5_Fe^2+^_0.5-2.5_)Si_8_O_22_(OH)_2_'), '□Ca2(Mg4.5-2.5Fe2+0.5-2.5)Si8O22(OH)2')
        self.assertEqual(R.member_meta('Quartz__R040031__Raman__532______Raman_Data_RAW__x.txt', {}, 'LR-Raman')['kind'], 'processed')   # no FILETYPE: processed
        self.assertEqual(R.member_meta('x', {'FILETYPE': 'Raman RAW'}, 'LR-Raman')['quality'], 'broad')

    def test_fetch_store_union_and_routes(self):
        self.assertIsNone(R.status())
        with self.assertRaises(ValueError) as cm:
            R.fetch(sets=['nosuchset'], out_dir=self.store, log=None)
        self.assertIn('no such RRUFF set', str(cm.exception))
        self.assertEqual((R.PROGRESS['stage'], R.PROGRESS['finished']), ('failed', True))   # said in PROGRESS even when the sets are wrong
        # a set rruff.net answers 404 for is skipped and named; the core set's 404 is a failure; a kept zip is not fetched twice
        import urllib.error, urllib.request
        real = R._urlopen
        def fake(req, timeout=60):
            url = req.full_url if hasattr(req, 'full_url') else req
            if 'fair_oriented' in url or 'excellent_unoriented' in url:
                raise urllib.error.HTTPError(url, 404, 'Not Found', {}, None)
            return real(req, timeout)
        R._urlopen = fake
        try:
            n0 = R.fetch(sets=['poor_unoriented', 'fair_oriented'], out_dir=self.store, keep_zips=True, log=None)
            self.assertEqual((n0, R.PROGRESS['missing']), (3, ['fair_oriented']))
            self.assertTrue(os.path.isfile(os.path.join(self.store, 'zips', 'poor_unoriented.zip')))
            with self.assertRaises(ValueError) as cm:
                R.fetch(sets=['excellent_unoriented'], out_dir=self.store, log=None)
            self.assertIn('HTTP 404', str(cm.exception))
            R._urlopen = lambda req, timeout=60: (_ for _ in ()).throw(AssertionError('downloaded although the zip was kept'))
            self.assertEqual(R.fetch(sets=['poor_unoriented'], out_dir=self.store, keep_zips=True, log=None), 3)   # 'already here'
        finally:
            R._urlopen = real
        self.assertEqual(R.status(self.store)['n'], 3)                                 # status of a named folder
        self.assertFalse([f for f in os.listdir(self.store) if f.endswith('.part')])
        st0 = R.open_store(self.store); self.assertFalse(st0._f.closed)
        R.close_stores(); self.assertTrue(st0._f.closed)
        with self.assertRaises(ValueError):
            st0.xy(0)                                                                  # a closed store says so, never garbage
        with self.assertRaises(ValueError) as cm:
            R.fetch(sets=['fair_oriented'], out_dir=self.store, log=None)          # not served (a file:// 404 is an URLError): said with its url
        self.assertIn('fair_oriented.zip could not be downloaded', str(cm.exception))
        self.assertEqual((R.PROGRESS['stage'], R.PROGRESS['finished']), ('failed', True))
        self.assertNotIn('poor_oriented', R.SETS)                                   # RRUFF publishes no such set
        n = R.fetch(sets=['poor_unoriented', 'excellent_unoriented', 'LR-Raman'], ir=True, out_dir=self.store, log=None)
        self.assertEqual(n, 6)
        self.assertEqual([f for f in os.listdir(self.store) if f.endswith('.f32')].__len__(), 1)   # one array file: the earlier builds' removed
        self.assertTrue(st0._f.closed)                                                       # the Raman raw and the three-point member left out; the IR one (RAW only) in
        self.assertEqual((R.PROGRESS['stage'], R.PROGRESS['spectra'], R.PROGRESS['finished']), ('done', 6, True))
        zd = os.path.join(self.store, 'zips')                                       # only THIS run's zips are removed: the one kept earlier stays
        self.assertEqual(sorted(os.listdir(zd)) if os.path.isdir(zd) else [], ['poor_unoriented.zip'])
        st = R.open_store(self.store)
        self.assertEqual((st.n, sorted(st.minerals())), (6, ['Calcite', 'Gypsum', 'Quartz']))
        q = st.minerals()['Quartz']                                                 # best first: excellent before poor, 532 before 780
        self.assertEqual([(st.meta(i)['quality'], st.meta(i)['laser']) for i, _r, _k, _l in q], [('excellent', '532'), ('poor', '532'), ('poor', '780')])
        c = st.minerals()['Calcite']
        self.assertEqual([st.meta(i)['technique'] for i, _r, _k, _l in c], ['raman', 'infrared'])     # Raman before infrared
        x, y = st.xy(c[0][0])
        self.assertEqual((len(x), round(x[0], 1), round(x[-1], 1)), (2400, 150.0, 1349.5))               # a descending file stored ascending
        self.assertAlmostEqual(max(y), 100.0, places=2); self.assertAlmostEqual(x[y.index(max(y))], 1086.0, delta=0.6)
        self.assertEqual(st.meta(c[0][0])['chem'], 'CaCO3')
        s = R.status()
        self.assertEqual((s['n'], s['minerals'], s['sets'], s['raw']), (6, 3, ['poor_unoriented', 'excellent_unoriented', 'LR-Raman', 'infrared'], False))
        self.assertGreater(s['bytes'], 5 * 2400 * 4)
        # raw kept when asked
        n2 = R.fetch(sets=['poor_unoriented'], raw=True, out_dir=os.path.join(self.tmp, 'store2'), log=None)
        self.assertEqual(n2, 4)
        # the union with a Thermo OMNIC copy: one list, the store first, indices running on
        from tests.test_rruff_windows import write_library, gauss as og
        from pxrd_review import omnic_lib as OL
        om = os.path.join(self.tmp, 'RRUFF'); os.makedirs(om, exist_ok=True)                  # the name the finder looks for beside a folder
        write_library(om, [('QuartzR040031_processed', 'field', og([464, 206], [100, 30])), ('AnhydriteR040061_processed', 'field', og([1017, 500], [100, 30]))])
        keep = (OL.REMEMBER, OL.SEARCH_ROOTS, os.environ.pop('PXRD_RRUFF_DIR', None))
        OL.REMEMBER, OL.SEARCH_ROOTS = os.path.join(self.tmp, 'mem.txt'), ()
        OL._OPEN.clear()
        try:
            u = R.libraries(os.path.join(self.tmp))                                 # OMNIC beside this folder
            self.assertEqual((u.n, len(u.libs)), (8, 2))
            self.assertEqual(sorted(u.minerals()), ['Anhydrite', 'Calcite', 'Gypsum', 'Quartz'])
            self.assertEqual(len(u.minerals()['Quartz']), 4)
            self.assertEqual(u.meta(u.minerals()['Anhydrite'][0][0])['set'], 'omnic')
            self.assertEqual(len(u.xy(6)[0]), 759)                                 # the first OMNIC record, on the OMNIC grid
            with self.assertRaises(ValueError):
                u.xy(8)
            # the window: the list carries quality and the store; the curve its bands; the status the last fetch
            from pxrd_review.gui import review_gui as G
            G._ALLOWED_HOSTS = set()
            c = G.app.test_client()
            folder = os.path.join(self.tmp, 'batch'); os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, 'sample raman.txt'), 'w', encoding='utf-8') as f:
                f.write(''.join('%.1f\t%.2f\n' % (150 + k, 10 + (k == 300) * 500) for k in range(1200)))
            self.assertTrue(G.ms_set_folder(folder), 'the window needs a folder with something in it')
            if G.MS['athread']:
                G.MS['athread'].join(60)
            OL.REMEMBER = os.path.join(self.tmp, 'mem.txt'); OL.set_library(om)      # the OMNIC copy named by hand, as a user would
            l = json.loads(c.get('/api/sp/rruff/list').data)
            self.assertEqual((l['n'], l['store']['n'], sorted(m['name'] for m in l['minerals'])), (8, 6, ['Anhydrite', 'Calcite', 'Gypsum', 'Quartz']))
            qz = next(m for m in l['minerals'] if m['name'] == 'Quartz')['spectra']
            self.assertEqual((qz[0]['quality'], qz[0]['laser'], qz[0]['technique']), ('excellent', '532', 'raman'))
            self.assertIn('Lafuente', l['citation'])
            cv = json.loads(c.get('/api/sp/rruff/curve?key=%d' % qz[0]['key']).data)
            self.assertTrue(any(abs(p - 464) < 2 for p in cv['peaks']), cv['peaks'])
            o = json.loads(c.post('/api/sp/rruff/open', json={'key': qz[0]['key']}).data)
            self.assertEqual(o['name'], 'Quartz R040031 processed 532 nm (RRUFF %d)' % (qz[0]['key'] + 1))
            o_ = json.loads(c.post('/api/sp/rruff/open', json={'key': qz[1]['key']}).data)
            self.assertNotEqual(o['name'], o_['name'])                                 # two spectra of one sample: two names, both held
            self.assertEqual(json.loads(c.post('/api/sp/process', json={'name': o['name']}).data)['name'], o['name'])
            p = json.loads(c.post('/api/sp/process', json={'name': o['name']}).data)
            self.assertEqual(p['kind'], 'raman'); self.assertTrue(any('excellent, unoriented' in n for n in p['notes']) and any('ideal chemistry SiO2' in n for n in p['notes']))
            ir = next(s_ for m in l['minerals'] if m['name'] == 'Calcite' for s_ in m['spectra'] if s_['technique'] == 'infrared')
            o2 = json.loads(c.post('/api/sp/rruff/open', json={'key': ir['key']}).data)
            self.assertEqual(json.loads(c.post('/api/sp/process', json={'name': o2['name']}).data)['kind'], 'ir-absorbance')
            st_ = json.loads(c.get('/api/sp/rruff/status').data)
            self.assertEqual((st_['fetch']['stage'], st_['store']['n']), ('done', 6))     # the status reports THE store (store_dir), not the second folder
            # a fetch from the window: on a thread, followed by /status, the list refilled
            R.PROGRESS.clear()
            f = json.loads(c.post('/api/sp/rruff/fetch', json={'sets': ['excellent_unoriented']}).data)
            self.assertTrue(f['ok'])
            for _ in range(200):
                if R.PROGRESS.get('finished'):
                    break
                time.sleep(0.05)
            self.assertEqual((R.PROGRESS.get('stage'), R.PROGRESS.get('error')), ('done', ''))
            self.assertEqual(json.loads(c.get('/api/sp/rruff/list').data)['store']['n'], 1)
            self.assertEqual(c.post('/api/sp/rruff/fetch', json={'sets': ['nosuchset']}).status_code, 400)    # checked before anything runs
            self.assertEqual(c.post('/api/sp/rruff/fetch', json={'sets': [{'a': 1}]}).status_code, 400)
            self.assertEqual(c.post('/api/sp/rruff/fetch', json={'sets': []}).status_code, 400)
            # the species list filtered on the server, the limit after the filter
            sp2 = json.loads(c.post('/api/sp/species', json={'groups': ['SO4'], 'q': 'zzzzq'}).data)
            self.assertEqual((sp2['species'], sp2['matching'] == 0, sp2['total'] > 0), ([], True, True))
        finally:
            OL.REMEMBER, OL.SEARCH_ROOTS = keep[0], keep[1]
            if keep[2]:
                os.environ['PXRD_RRUFF_DIR'] = keep[2]
            OL._OPEN.clear()
            R.remove(self.store); R.remove(os.path.join(self.tmp, 'store2'))
            self.assertIsNone(R.status())


if __name__ == '__main__':
    unittest.main()
