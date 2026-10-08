"""The spectrum window of the review GUI — the /spectra page and the /api/sp/* routes, through Flask's test client.

    python3 -m unittest tests.test_gui_sp -v

A synthetic Raman spectrum (three known bands, a sloping background, three cosmic rays), a synthetic uranyl .cif and a
one-paragraph manuscript in a temp folder; no browser. The page's own script is exercised live, on a scratch folder.
"""
import io, json, os, shutil, tempfile, unittest

from tests.test_spectrum import synth, TRUTH
from tests.test_spectro import URANYL


class SpectrumWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from pxrd_review.gui import review_gui as G
        cls.G = G
        G._ALLOWED_HOSTS = set()
        cls.tmp = tempfile.mkdtemp(prefix='spgui_')
        x, y, _ = synth(21, TRUTH, lo=300, hi=1300, base=lambda v: 400 + 0.3 * v, spikes=3)
        cls.text = ''.join('%.2f\t%.3f\n' % r for r in zip(x, y))
        for name, body in (('testite raman.txt', cls.text), ('uranyl.cif', URANYL), ('empty.jdx', '##TITLE=t\n##XYDATA=(X++(Y..Y))\n##END=\n')):
            with open(os.path.join(cls.tmp, name), 'w', encoding='utf-8') as f:
                f.write(body)
        import docx
        d = docx.Document()
        d.add_paragraph('The ν1 (UO2)2+ symmetric stretching vibration is present as a very strong band at 832 cm–1 with a shoulder at 846 cm–1. '
                        'A weak band at 880 cm–1 is assigned to the ν3 (UO2)2+ antisymmetric stretching vibration.')
        d.save(os.path.join(cls.tmp, 'testite.docx'))
        cls.c = G.app.test_client()
        assert G.ms_set_folder(cls.tmp)
        if G.MS['athread']:
            G.MS['athread'].join(60)
        cls.body = {'name': 'testite raman.txt', 'kind': 'raman', 'despike': True, 'baseline': 'als'}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _post(self, url, body, status=200):
        r = self.c.post(url, json=body)
        self.assertEqual(r.status_code, status, r.data[:300])
        return json.loads(r.data)

    def test_page_and_state(self):
        r = self.c.get('/spectra')
        self.assertEqual(r.status_code, 200); self.assertIn(b'/static/sp.js', r.data)
        self.assertIn("script-src 'self'", r.headers.get('Content-Security-Policy', ''))
        self.assertIn('no-cache', r.headers.get('Cache-Control', ''))
        r.close()
        s = json.loads(self.c.get('/api/sp/state').data)
        self.assertEqual([f['name'] for f in s['files']][:2], ['empty.jdx', 'testite raman.txt'])     # an instrument format the Tables mode does not list, and a text file
        self.assertEqual((s['cifs'], s['manuscripts']), (['uranyl'], ['testite']))
        self.assertIn('UO2 ν1', s['windows'])
        self.assertNotIn('empty.jdx', self.G.MS['data'])                                               # … and it stays out of the EPMA / PXRD file lists

    def test_series_and_refusals(self):
        s = json.loads(self.c.get('/api/sp/series?name=testite%20raman.txt').data)['series']
        self.assertEqual((len(s), s[0]['n'], s[0]['x0'], s[0]['x1']), (1, 2001, 300.0, 1300.0))
        self.assertEqual(self.c.get('/api/sp/series?name=../../etc/passwd').status_code, 404)            # a name is a key of the folder, never a path
        self.assertEqual(self.c.get('/api/sp/series').status_code, 400)
        r = self.c.get('/api/sp/series?name=empty.jdx')
        self.assertEqual(r.status_code, 400); self.assertIn('no ##XYDATA', json.loads(r.data)['error'])

    def test_process_with_the_structure_and_the_manuscript_beside(self):
        d = self._post('/api/sp/process', dict(self.body, cif='uranyl', ms='testite'))
        self.assertEqual(len(d['x']), 2001); self.assertEqual(len(d['spikes']), 3)
        self.assertEqual([round(t['pos']) for t in d['ticks']], [841, 920, 3402])                        # ν1 and ν3 of the 1.77 Å uranyl, the O–H of the 2.80 Å bond
        self.assertEqual(sorted(b['pos'] for b in d['stated']), [832.0, 846.0, 880.0])
        self.assertEqual([(b['family'], b['mode']) for b in d['stated'] if b['pos'] == 880.0], [('UO2', 'ν3')])
        self.assertLess(abs(d['noise'] - 4.0), 0.8)
        raw = self._post('/api/sp/process', {'name': 'testite raman.txt'})
        self.assertEqual((raw['spikes'], raw['baseline'][0]), ([], 0.0))
        self._post('/api/sp/process', {}, 400); self._post('/api/sp/process', {'name': 'nosuch.txt'}, 404)
        self._post('/api/sp/process', {'name': 'testite raman.txt', 'series': 4}, 400)

    def test_fit_auto_then_the_page_s_own_bands(self):
        r = self._post('/api/sp/fit', dict(self.body, lo=780, hi=960, ms='testite'))
        f = r['fit']
        self.assertEqual([round(c['pos']) for c in f['comps']], [831, 846, 915])
        self.assertEqual(r['trials'][0]['n'], 3)
        self.assertEqual(len(f['x']), len(f['model'])); self.assertEqual(len(f['x']), len(f['residual']))
        self.assertIn('UO2 ν1', f['comps'][0]['suggest']); self.assertTrue(f['comps'][0]['distance'].startswith('U–O 1.78'))
        self.assertEqual([m[0] for m in f['stated']['matched']], [832.0, 846.0])                       # the manuscript's bands the fit has
        self.assertEqual((f['stated']['not_fitted'], [round(v) for v in f['stated']['not_stated']]), ([880.0], [915]))
        two = self._post('/api/sp/fit', dict(self.body, lo=780, hi=960, comps=f['comps'][:2]))['fit']   # the bands the page sends, refined as they are
        self.assertEqual(len(two['comps']), 2)
        held = dict(f['comps'][0], pos=830.0, fix=['pos'])
        self.assertEqual(self._post('/api/sp/fit', dict(self.body, lo=780, hi=960, comps=[held] + f['comps'][1:]))['fit']['comps'][0]['pos'], 830.0)
        self.assertIn('a region to fit is needed', self._post('/api/sp/fit', self.body, 400)['error'])
        self._post('/api/sp/fit', dict(self.body, lo=5000, hi=5100), 400)
        self._post('/api/sp/fit', {}, 400)

    def test_the_band_library_for_a_chemistry(self):
        r = self._post('/api/sp/bands', {'formula': 'Ca2(UO2)3(SO4)2(OH)6·4H2O', 'kind': 'raman', 'at': [832, 1450, 'x', 2920]})
        self.assertEqual(([g['key'] for g in r['groups']], r['source'], r['formula']), (['UO2', 'SO4', 'H2O', 'OH'], 'typed', 'Ca2(UO2)3(SO4)2(OH)6·4H2O'))
        rows = {x['label']: x for x in r['rows']}
        self.assertEqual((rows['SO4 ν1']['free'], rows['SO4 ν1']['active'], rows['UO2 ν1']['published']['of']), (983, 'Raman', 'raman'))
        self.assertTrue(rows['SO4 ν1']['source'].startswith('Nakamoto')); self.assertTrue(rows['H2O lib']['broad'])
        self.assertEqual(sorted(rows['UO2 ν1']['published']), ['of', 'p5', 'p50', 'p95', 'papers'])
        self.assertEqual(([a['pos'] for a in r['at']], r['at'][0]['own'][0], r['at'][1]['own'], r['at'][2]['shared']), ([832, 1450, 2920], 'UO2 ν1', [], ['ν(C–H)']))
        self.assertIn('CO3 ν3', r['at'][1]['other'])
        # nothing typed: the formula the manuscript beside the spectrum states — this one states none
        none = self._post('/api/sp/bands', {'ms': 'testite'})
        self.assertEqual((none['formula'], none['groups'], none['rows'], none['source']), ('', [], [], ''))
        # a name the snapshot does not know is said, never read as a formula; a known one resolves in any case
        bad = self._post('/api/sp/bands', {'formula': 'Notaspeciesofanysnapshot', 'ms': 'testite'})
        self.assertEqual((bad['source'], bad['name'], bad['formula'], bad['groups'], bad['rows']), ('unresolved', 'Notaspeciesofanysnapshot', '', [], []))
        from pxrd_review import bands as B
        if B.resolve('autunite')[1]:
            self.assertEqual([g['key'] for g in self._post('/api/sp/bands', {'formula': 'Autunite'})['groups']], ['UO2', 'PO4', 'H2O'])
        self.assertEqual(self._post('/api/sp/bands', {'formula': 'PbS'})['groups'][0]['key'], 'sulfide')
        self.assertEqual(self._post('/api/sp/bands', {})['rows'], [])
        # a fit asked with the chemistry: each band is named for what that formula expects there, and the files say which formula
        f = self._post('/api/sp/fit', dict(self.body, lo=780, hi=960, formula='Ca2(UO2)3(SO4)2(OH)6·4H2O'))['fit']
        self.assertEqual(f['comps'][0]['suggest'][0], 'UO2 ν1'); self.assertEqual(f['head'][6], 'expected of the formula')
        g = self._post('/api/sp/fit', dict(self.body, lo=780, hi=960, formula='Ca5(PO4)3F'))['fit']
        self.assertTrue(g['comps'][0]['suggest'][0].startswith('no group of the formula'), g['comps'][0]); self.assertEqual(g['comps'][0]['distance'], '')
        ex = self._post('/api/sp/export', dict(self.body, fmt='txt', formula='Ca2(UO2)3(SO4)2(OH)6·4H2O',
                                               regions=[{'lo': 780, 'hi': 960, 'comps': f['comps'], 'base': f['base'], 'x0': f['x0']}]))
        try:
            text = self.c.get('/api/sp/file?name=' + ex['files']['txt']).data.decode('utf-8')
            self.assertIn('chemistry: Ca2(UO2)3(SO4)2(OH)6·4H2O', text); self.assertIn('expected of the formula', text)
            sess = json.loads(self.c.get('/api/sp/file?as=json&name=' + ex['files']['json']).data)
            self.assertEqual(sess['options']['formula_typed'], 'Ca2(UO2)3(SO4)2(OH)6·4H2O')
        finally:
            for fn in os.listdir(self.G.MS['out_dir']):
                if fn.startswith('testite_raman_sp'):
                    os.remove(os.path.join(self.G.MS['out_dir'], fn))

    def test_refining_a_fit(self):
        body = dict(self.body, lo=780, hi=960)
        one = self._post('/api/sp/fit', dict(body, n=1))['fit']
        self.assertEqual(len(one['comps']), 1)
        self.assertTrue(one['next'] and any(abs(n['pos'] - 846) < 12 or abs(n['pos'] - 831) < 12 for n in one['next']), one['next'])   # where the residual still holds a band
        more = self._post('/api/sp/fit', dict(body, comps=one['comps'], add=True))                      # '+ band'
        self.assertEqual(len(more['fit']['comps']), 2); self.assertEqual([t['n'] for t in more['trials']], [1, 2])
        self.assertLess(more['fit']['bic'], one['bic'])
        full = self._post('/api/sp/fit', body)['fit']
        self.assertIn('holds no further band', self._post('/api/sp/fit', dict(body, comps=full['comps'], add=True), 400)['error'])
        capped = self._post('/api/sp/fit', dict(body, comps=full['comps'], max_fwhm=8))['fit']          # the region's width limit
        self.assertTrue(all(c['fwhm'] <= 8.0001 for c in capped['comps'])); self.assertTrue(any(c['at_limit'] == 'max' for c in capped['comps']))
        self.assertTrue(any('rests on the width limit' in w for w in capped['warnings']))
        own = [dict(full['comps'][0], wmax=9.0)] + full['comps'][1:]                                    # … and one band's own
        self.assertLessEqual(self._post('/api/sp/fit', dict(body, comps=own))['fit']['comps'][0]['fwhm'], 9.0001)
        d2 = self._post('/api/sp/d2', dict(self.body, lo=780, hi=960, width=12))
        self.assertEqual(len(d2['x']), len(d2['d2'])); self.assertAlmostEqual(max(d2['d2']), 1.0, 5)
        self.assertLess(abs(d2['x'][d2['d2'].index(max(d2['d2']))] - 831), 4)                           # the strongest band is the highest bump
        self._post('/api/sp/d2', {}, 400); self._post('/api/sp/d2', dict(self.body, lo=5000, hi=5001), 400)

    def test_export_writes_the_fit_on_the_screen(self):
        body = dict(self.body, lo=780, hi=960)
        full = self._post('/api/sp/fit', body)['fit']
        moved = [dict(full['comps'][0], pos=full['comps'][0]['pos'] + 1.5)] + full['comps'][1:]         # bands as a hand left them: NOT at the minimum
        shown = self._post('/api/sp/fit', dict(body, comps=moved, evaluate=True))['fit']
        self.assertAlmostEqual(shown['comps'][0]['pos'], moved[0]['pos'], 9)                            # evaluated as they stand, no step taken
        self.assertGreater(shown['chi2'], full['chi2'])
        r = self._post('/api/sp/export', dict(self.body, fmt='xlsx', regions=[{'lo': 780, 'hi': 960, 'comps': moved, 'local': 'linear', 'converged': False}]))
        self.assertTrue(r['folder'].endswith('review_out'))
        sess = json.loads(self.c.get('/api/sp/file?as=json&name=' + r['files']['json']).data)
        self.assertAlmostEqual(sess['fits'][0]['components'][0]['pos'], moved[0]['pos'], 9)             # … and written as they stood
        self.assertEqual((sess['pxrd_spectrum_session'], sess['options']['name'], sess['options']['regions'][0]['lo']), (1, 'testite raman.txt', 780))
        self.assertTrue(any('had not converged when it was written' in w for w in sess['fits'][0]['warnings']))
        import openpyxl
        wb = openpyxl.load_workbook(os.path.join(self.tmp, 'review_out', r['files']['xlsx']))
        self.assertEqual(wb.sheetnames, ['bands', 'curves', 'spectrum'])
        head = [c.value for c in wb['curves'][1]]
        self.assertEqual(head[:5], ['wavenumber (cm⁻¹)', 'spectrum', 'fit', 'residual', 'local baseline']); self.assertEqual(len(head), 5 + 3)
        self.assertEqual(wb['spectrum'].max_row, 2002)
        txt = self.c.get('/api/sp/file?name=' + r['files']['txt'])
        self.assertEqual(txt.status_code, 200); self.assertTrue(txt.mimetype.startswith('text/plain'))
        for bad in ('/api/sp/file?name=../testite.docx', '/api/sp/file?name=' + r['files']['xlsx'], '/api/sp/file?name=nothing_sp.txt', '/api/sp/file'):
            self.assertEqual(self.c.get(bad).status_code, 404, bad)
        self.assertEqual(self.c.post('/api/sp/reveal?file=../x_sp.txt').status_code, 404)

    def test_dead_bands_twins_and_one_shape(self):
        body = dict(self.body, lo=780, hi=960)
        full = self._post('/api/sp/fit', body)['fit']
        # a band the data have no use for (on top of another, a point wide) is driven to zero — and taken out, and said
        extra = full['comps'] + [dict(full['comps'][0], pos=880.0, height=0.0, fwhm=1.2, fix=['pos', 'fwhm'])]
        f = self._post('/api/sp/fit', dict(body, comps=extra))['fit']
        if len(f['comps']) == 3:
            self.assertTrue(any('driven to zero height' in w for w in f['warnings']), f['warnings'])
        one = self._post('/api/sp/fit', dict(body, comps=full['comps'], share_eta=True))['fit']
        self.assertEqual(len({round(c['eta'], 9) for c in one['comps']}), 1)                              # one η, three widths
        self.assertEqual(len({round(c['fwhm'], 3) for c in one['comps']}), 3)
        self.assertEqual(one['k'], full['k'] - 2)

    def test_the_file_is_the_fit_on_the_screen(self):
        # no baseline taken off: the region's own sloping baseline is part of the model, and goes wherever the bands go
        body = {'name': 'testite raman.txt', 'kind': 'raman', 'baseline': 'none', 'lo': 780, 'hi': 960}
        f = self._post('/api/sp/fit', body)['fit']
        self.assertGreater(abs(f['base'][1]), 0.1)
        as_fitted = {'lo': 780, 'hi': 960, 'comps': f['comps'], 'local': 'linear', 'base': f['base'], 'x0': f['x0'], 'converged': f['converged']}
        same = self._post('/api/sp/fit', dict(body, **as_fitted, evaluate=True))['fit']
        self.assertAlmostEqual(same['chi2'], f['chi2'], 6)
        self.assertGreater(self._post('/api/sp/fit', dict(body, comps=f['comps'], evaluate=True))['fit']['chi2'], 100 * f['chi2'])
        r = self._post('/api/sp/export', dict(body, fmt='txt', regions=[as_fitted]))
        sess = json.loads(self.c.get('/api/sp/file?as=json&name=' + r['files']['json']).data)
        self.assertAlmostEqual(sess['fits'][0]['chi2'], f['chi2'], 6); self.assertAlmostEqual(sess['fits'][0]['baseline'][1], f['base'][1], 9)
        # heights only: the file says so too (its parameters, its uncertainties), and nothing is clamped to the limits of another region
        h = self._post('/api/sp/fit', dict(body, comps=f['comps'], refine='heights', keep_dead=True))['fit']
        r = self._post('/api/sp/export', dict(body, fmt='txt', regions=[dict(as_fitted, comps=h['comps'], base=h['base'], refine='heights', max_fwhm=5, share_width=True)]))
        sess = json.loads(self.c.get('/api/sp/file?as=json&name=' + r['files']['json']).data)
        self.assertEqual((sess['fits'][0]['parameters'], sess['options']['regions'][0]['refine']), (h['k'], 'heights'))
        self.assertEqual([round(c['fwhm'], 6) for c in sess['fits'][0]['components']], [round(c['fwhm'], 6) for c in h['comps']])
        r = self._post('/api/sp/export', dict(body, fmt='txt', regions=[dict(as_fitted, converged=False)]))
        sess = json.loads(self.c.get('/api/sp/file?as=json&name=' + r['files']['json']).data)
        self.assertFalse(sess['fits'][0]['converged']); self.assertIn('NOT CONVERGED', self.c.get('/api/sp/file?name=' + r['files']['txt']).data.decode())
        self.assertIn('nothing fitted yet', self._post('/api/sp/export', dict(body, regions=[{'lo': 780, 'hi': 960}]), 400)['error'])     # nothing is fitted on the way out

    def test_a_hand_edit_removes_nothing_and_an_envelope_is_offered(self):
        body = dict(self.body, lo=780, hi=960)
        full = self._post('/api/sp/fit', body)['fit']
        self.assertIn('envelope', full)
        extra = full['comps'] + [dict(full['comps'][0], pos=880.0, height=5.0, fwhm=1.2)]              # a band placed where the data have none
        kept = self._post('/api/sp/fit', dict(body, comps=extra, refine='heights', keep_dead=True))['fit']
        self.assertEqual(len(kept['comps']), 4); self.assertEqual(sorted(round(c['pos'], 6) for c in kept['comps'])[2], 880.0)
        self.assertEqual([round(c['fwhm'], 9) for c in kept['comps']], [round(c['fwhm'], 9) for c in sorted(extra, key=lambda c: c['pos'])])
        for bad in ({'refine': [1]}, {'refine': {}}, {'comps': [dict(full['comps'][0], fix=5)] + full['comps'][1:]}):       # junk is not a crash
            self._post('/api/sp/fit', dict(body, **dict({'comps': full['comps']}, **bad)))
        st = json.loads(self.c.get('/api/sp/state').data)
        self.assertEqual([r['key'] for r in st['rulers']], ['oo', 'nu1', 'nu3'])
        d2 = self._post('/api/sp/d2', dict(self.body, baseline='snip', width=150, lo=780, hi=960, d2_width=12))    # the two widths are two things
        self.assertEqual(d2['width'], 12)

    def test_a_file_rewritten_is_read_again_and_each_spectrum_has_its_own_files(self):
        p = os.path.join(self.tmp, 'rewritten.txt')
        def write(at):
            x, y, _ = synth(5, [dict(TRUTH[0], pos=at)], lo=300, hi=1300)
            with open(p, 'w', encoding='utf-8') as fh:
                fh.write(''.join('%.2f\t%.3f\n' % r for r in zip(x, y)))
            os.utime(p, (at, at))
        top = lambda: (lambda d: d['x'][d['y'].index(max(d['y']))])(self._post('/api/sp/process', {'name': 'rewritten.txt'}))
        try:
            write(500.0); self.G.ms_set_folder(self.tmp); a = top()
            write(900.0); b = top()
            self.assertEqual((round(a), round(b)), (500, 900))
            import openpyxl
            wb = openpyxl.Workbook(); ws = wb.active
            x, y, _ = synth(6, TRUTH)
            for u, v in zip(x, y):
                ws.append([u, v, None, u, 2 * v])
            wb.save(os.path.join(self.tmp, 'two.xlsx')); self.G.ms_set_folder(self.tmp)
            names = []
            for k in (0, 1):
                f = self._post('/api/sp/fit', {'name': 'two.xlsx', 'series': k, 'lo': 780, 'hi': 960})['fit']
                names.append(self._post('/api/sp/export', {'name': 'two.xlsx', 'series': k, 'regions': [{'lo': 780, 'hi': 960, 'comps': f['comps'], 'base': f['base'], 'x0': f['x0']}]})['files']['txt'])
            self.assertEqual(names, ['two_1_sp.txt', 'two_2_sp.txt'])
        finally:                                                # the other tests list this folder
            for name in ('rewritten.txt', 'two.xlsx'):
                if os.path.exists(os.path.join(self.tmp, name)):
                    os.remove(os.path.join(self.tmp, name))
            self.G.ms_set_folder(self.tmp)
            if self.G.MS['athread']:
                self.G.MS['athread'].join(60)

    def test_a_spectrum_from_a_figure(self):
        import fitz
        from tests.test_figure_trace import make_pdf, BANDS
        pdf = os.path.join(self.tmp, 'figpaper.pdf')
        try:
            X = make_pdf(pdf, second=False)
            self.G.ms_set_folder(self.tmp)
            st = json.loads(self.c.get('/api/sp/state').data)
            self.assertIn('figpaper.pdf', st['figures']); self.assertIn('testite.docx', st['figures'])
            src = json.loads(self.c.get('/api/sp/fig/sources?name=figpaper.pdf').data)['sources']
            self.assertEqual([(s_['index'], s_['spectrum']) for s_ in src], [(0, True), (1, False)])
            img = self.c.get('/api/sp/fig/image?name=figpaper.pdf&i=0')
            self.assertEqual((img.status_code, img.mimetype, img.data[:4]), (200, 'image/png', b'\x89PNG'))
            det = self._post('/api/sp/fig/detect', {'name': 'figpaper.pdf', 'i': 0})
            self.assertEqual(len(det['frames']), 1); self.assertTrue(det['vector'])
            f = det['frames'][0]
            self.assertEqual([t[1] for t in f['ticks']], [200.0, 1200.0])
            body = {'name': 'figpaper.pdf', 'i': 0, 'box': f['box'], 'x1': f['ticks'][0][0], 'v1': 200, 'x2': f['ticks'][1][0], 'v2': 1200}
            tr = self._post('/api/sp/fig/trace', body)
            self.assertEqual((tr['how'], tr['down']), ('vector', False)); self.assertNotIn('name', tr); self.assertGreater(len(tr['trace']), 500)
            z = det['w'] / 595.0
            col = self._post('/api/sp/fig/colour', {'name': 'figpaper.pdf', 'i': 0, 'x': X(600) * z, 'y': (330 - 0.04 / 1.15 * 210) * z})
            self.assertGreater(col['colour'][2], col['colour'][0] + 60)                                    # the blue curve
            self.assertIn('nothing is drawn there', self._post('/api/sp/fig/colour', {'name': 'figpaper.pdf', 'i': 0, 'x': 30, 'y': 30}, 400)['error'])
            used = self._post('/api/sp/fig/trace', dict(body, use=True))
            name = used['name']
            self.assertIn('(figure)', name)
            self.assertIn({'name': name, 'source': 'upload'}, json.loads(self.c.get('/api/sp/state').data)['files'])
            d = self._post('/api/sp/process', {'name': name, 'ms': 'testite'})                              # … and opens like any spectrum, the manuscript's bands beside it
            self.assertTrue(d['figure']); self.assertIn('read off a figure', d['notes'][0]); self.assertFalse(any('smoothed or interpolated' in n for n in d['notes']))
            self.assertEqual(sorted(p[0] for p in d['on_curve']['found']), [832.0, 846.0]); self.assertEqual(d['on_curve']['none'], [880.0])
            top = d['x'][d['y'].index(max(d['y']))]
            self.assertAlmostEqual(top, 464.0, delta=2.5)
            px = self._post('/api/sp/fig/trace', dict(body, v2=None))                                      # the curve alone, before the axis is scaled: its peaks to drop a mark on
            self.assertTrue(px['pixels_only']); self.assertGreaterEqual(len(px['peaks']), 5); self.assertNotIn('lo', px)
            self.assertAlmostEqual(min(px['peaks'], key=lambda p: abs(p - X(464) * z)), X(464) * z, delta=1.5)
            self.assertIn('axis needs two points', self._post('/api/sp/fig/trace', dict(body, v2=None, use=True), 400)['error'])
            # the server holds a traced curve in memory only: the page keeps its points and gives them back after a restart,
            # and a session written from it carries them too
            fm = d['figure_meta']
            self.assertEqual(len(fm['y']), len(d['x'])); self.assertAlmostEqual(fm['cm_per_px'], used['cm_per_px'], 6)
            fit = self._post('/api/sp/fit', {'name': name, 'lo': 400, 'hi': 540})['fit']
            ex = self._post('/api/sp/export', {'name': name, 'fmt': 'txt', 'regions': [{'lo': 400, 'hi': 540, 'comps': fit['comps'], 'base': fit['base'], 'x0': fit['x0']}]})
            sess = json.loads(self.c.get('/api/sp/file?as=json&name=' + ex['files']['json']).data)
            self.assertEqual((sess['figure']['name'], len(sess['figure']['x'])), (name, len(d['x'])))
            with self.G._SP['lock']:
                self.G._SP['uploads'].clear(); self.G._SP['prep'].clear()                                  # … as a restart leaves it
            self._post('/api/sp/process', {'name': name}, 404)
            back = self._post('/api/sp/fig/restore', {'name': name, 'x': d['x'], 'y': fm['y'], 'cm_per_px': fm['cm_per_px'], 'notes': fm['notes']})
            self.assertEqual(back['name'], name)
            again = self._post('/api/sp/process', {'name': name, 'ms': 'testite'})
            self.assertEqual((again['x'], again['notes'][0], again['on_curve']['none']), (d['x'], d['notes'][0], [880.0]))
            for bad in ({'name': 'a file.txt', 'x': d['x'], 'y': fm['y']}, {'name': name, 'x': d['x'], 'y': fm['y'][:-1]}, {'name': name, 'x': [1, 2], 'y': [1, 2]}, {'name': name}):
                self._post('/api/sp/fig/restore', bad, 400)
            self.assertEqual(len(f['marks']), 6)                                                           # the six ticks of the axis, evenly spaced
            for m_, v_ in zip(f['marks'], range(200, 1300, 200)):
                self.assertAlmostEqual(m_, X(v_) * z, delta=1.0)
            own = self._post('/api/sp/fig/detect', {'name': 'figpaper.pdf', 'i': 0, 'box': [f['box'][0] + 20, f['box'][1] + 30, f['box'][2] - 20, f['box'][3]]})
            self.assertEqual((own['frames'], len(own['own']['marks'])), ([], 6))                          # a frame of the user's own: the ticks on its axis
            self.assertIn('drag a frame', self._post('/api/sp/fig/trace', dict(body, box=None), 400)['error'])
            self._post('/api/sp/fig/detect', {'name': 'nosuch.pdf', 'i': 0}, 404)
            self.assertEqual(self.c.get('/api/sp/fig/image?name=../testite.docx&i=0').status_code, 404)
            # an image opened from the browser: kept in memory, traced by its pixels
            with fitz.open(pdf) as doc:
                png = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes('png')
            before = sorted(os.listdir(self.tmp))
            up = self.c.post('/api/sp/fig/upload', data={'file': (io.BytesIO(png), 'shot.png')}, content_type='multipart/form-data')
            self.assertEqual(json.loads(up.data), {'ok': True, 'name': 'shot.png', 'n': 1}); self.assertEqual(sorted(os.listdir(self.tmp)), before)
            det = self._post('/api/sp/fig/detect', {'name': 'shot.png', 'i': 0})
            self.assertEqual((len(det['frames']), det['frames'][0]['ticks'], det['vector']), (1, [], False))
            tr = self._post('/api/sp/fig/trace', {'name': 'shot.png', 'i': 0, 'box': det['frames'][0]['box'], 'x1': X(200) * 2, 'v1': 200, 'x2': X(1200) * 2, 'v2': 1200})
            self.assertEqual(tr['how'], 'raster'); self.assertGreater(tr['coverage'], 0.95)
            bad = self.c.post('/api/sp/fig/upload', data={'file': (io.BytesIO(b'words'), 'notes.txt')}, content_type='multipart/form-data')
            self.assertEqual(bad.status_code, 400)
            bad = self.c.post('/api/sp/fig/upload', data={'file': (io.BytesIO(b'not a picture'), 'broken.png')}, content_type='multipart/form-data')
            self.assertEqual(bad.status_code, 400)
        finally:
            if os.path.exists(pdf):
                os.remove(pdf)
            self.G.ms_set_folder(self.tmp)
            if self.G.MS['athread']:
                self.G.MS['athread'].join(60)

    def test_an_upload_let_go_is_said_and_a_bad_picture_refused(self):
        self.G._SP['uploads'].clear(); self.G._SP['let_go'].clear()
        for k in range(self.G._SP_KEEP + 1):                                                         # one more than the window keeps
            r = self.c.post('/api/sp/upload', data={'file': (io.BytesIO(self.text.encode()), 'up%d.txt' % k)}, content_type='multipart/form-data')
            self.assertTrue(json.loads(r.data)['ok'])
        gone = self._post('/api/sp/process', {'name': 'up0.txt'}, 404)['error']
        self.assertIn('was opened here and has been let go', gone); self.assertIn('open it again', gone)
        self.assertEqual(self._post('/api/sp/process', {'name': 'up1.txt'})['name'], 'up1.txt')
        self.assertIn('no such spectrum file in the open folder', self._post('/api/sp/process', {'name': 'never.txt'}, 404)['error'])
        r = self.c.post('/api/sp/fig/upload', data={'file': (io.BytesIO(b'not a picture'), 'pic.png')}, content_type='multipart/form-data')
        self.assertEqual(r.status_code, 400); self.assertIn('could not be read as an image', json.loads(r.data)['error'])

    def test_upload_stays_in_memory(self):
        before = sorted(os.listdir(self.tmp))
        r = self.c.post('/api/sp/upload', data={'file': (io.BytesIO(self.text.encode()), '../sneaky name.txt')}, content_type='multipart/form-data')
        self.assertEqual(json.loads(r.data), {'ok': True, 'name': 'sneaky name.txt', 'n': 1})
        self.assertEqual(sorted(os.listdir(self.tmp)), before)                                         # nothing is written into the folder
        self.assertEqual(self._post('/api/sp/process', {'name': 'sneaky name.txt'})['name'], 'sneaky name.txt')
        self.assertIn({'name': 'sneaky name.txt', 'source': 'upload'}, json.loads(self.c.get('/api/sp/state').data)['files'])
        bad = self.c.post('/api/sp/upload', data={'file': (io.BytesIO(b'no numbers here\n'), 'words.txt')}, content_type='multipart/form-data')
        self.assertEqual(bad.status_code, 400); self.assertIn('words.txt', json.loads(bad.data)['error'])
        self.assertEqual(self.c.post('/api/sp/upload', data={}, content_type='multipart/form-data').status_code, 400)

    def test_export_and_open_guard(self):
        f = self._post('/api/sp/fit', dict(self.body, lo=780, hi=960))['fit']
        r = self._post('/api/sp/export', dict(self.body, cif='uranyl', fmt='xlsx', regions=[{'lo': 780, 'hi': 960, 'comps': f['comps'], 'local': 'linear'}]))
        self.assertEqual(r['files'], {'txt': 'testite_raman_sp.txt', 'svg': 'testite_raman_sp.svg', 'json': 'testite_raman_sp.json', 'xlsx': 'testite_raman_sp.xlsx'})
        out = os.path.join(self.tmp, 'review_out')
        self.assertIn('831.', open(os.path.join(out, 'testite_raman_sp.txt'), encoding='utf-8').read())
        sess = json.load(open(os.path.join(out, 'testite_raman_sp.json'), encoding='utf-8'))
        self.assertEqual((sess['options']['baseline'], len(sess['fits'][0]['components'])), ('als', 3))
        self.assertIn('testite_raman_sp.xlsx', json.loads(self.c.get('/api/sp/state').data)['outputs'])
        self.assertIn('nothing fitted yet', self._post('/api/sp/export', self.body, 400)['error'])
        for name in ('../testite.docx', 'testite.docx', 'nothing_sp.txt', ''):                          # only this window's own outputs, and only ones that exist
            self.assertEqual(self.c.post('/api/sp/open?file=' + name).status_code, 404, name)
        keep, self.G.MS['out_dir'] = self.G.MS['out_dir'], None
        try:
            self.assertIn('no folder is open', self._post('/api/sp/export', dict(self.body, regions=[{'lo': 780, 'hi': 960}]), 409)['error'])
        finally:
            self.G.MS['out_dir'] = keep


if __name__ == '__main__':
    unittest.main()
