"""tools/rruff_windows.py — the OMNIC library reader, the mode assignment by geometry and free-ion ratios, the windows."""
import os, sys, struct, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from tools import rruff_windows as RW
from pxrd_review import bands as BD


class StorePath(unittest.TestCase):
  def test_read_any_reads_a_store_with_x_ids(self):
    import json, os, sys, tempfile, shutil, struct
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
    import rruff_windows as W
    d = tempfile.mkdtemp(prefix='rrw_')
    try:
        x = [150.0 + k for k in range(300)]; y = gauss_any(x, [464], [100])
        data = struct.pack('<%df' % 600, *(x + y))
        with open(os.path.join(d, 'spectra.f32'), 'wb') as f:
            f.write(data * 3)
        sp = [{'name': 'Quartz', 'id': 'R040031', 'kind': 'processed', 'laser': '532.0', 'quality': 'excellent', 'orient': 'unoriented', 'technique': 'raman', 'off': 0, 'npts': 300},
              {'name': 'Magnesio-riebeckite', 'id': 'X050031', 'kind': 'processed', 'laser': '785', 'quality': 'poor', 'orient': 'unoriented', 'technique': 'raman', 'off': len(data), 'npts': 300},
              {'name': 'Quartz', 'id': 'R040031', 'kind': 'processed', 'laser': '532', 'quality': 'broad', 'orient': 'unoriented', 'technique': 'raman', 'off': 2 * len(data), 'npts': 300}]
        json.dump({'spectra': sp}, open(os.path.join(d, 'index.json'), 'w'))
        rows = W.read_any(d)
        names = [n for n, _x, _y in rows]
        assert names == ['QuartzR040031_532processed', 'Magnesio-riebeckiteX050031_785processed'], names     # the broad scan left out, '532.0' → 532
        from pxrd_review.omnic_lib import split_name
        assert split_name(names[1]) == ('Magnesio-riebeckite', 'X050031', 'processed'), split_name(names[1])
    finally:
        shutil.rmtree(d, ignore_errors=True)


def gauss_any(x, centres, heights, w=6.0):
    import math
    return [sum(h * math.exp(-4 * math.log(2) * ((v - c) / w) ** 2) for c, h in zip(centres, heights)) for v in x]


def write_library(folder, spectra):
    """A small OMNIC-style pair: `spectra` = [(name, kind, [y...])] on the tool's grid; kind 'field' writes the
    256-character name field, 'pascal' the length-prefixed name of the older records."""
    npts = 759
    x0, x1 = 32.783936, 1494.56176
    lbt = bytearray(b'1024  \r\n' + b' ' * 1016)
    ptrs = []
    for name, kind, _y in spectra:
        ptrs.append(len(lbt))
        if kind == 'field':
            lbt += b'\x8b\x01\xff' + name.encode('latin-1').ljust(255) + b'\x17' + b'0\t3367940656\t0\t0.00000\t'
        else:
            lbt += b'\x00\x00' + bytes([len(name)]) + name.encode('latin-1') + b' 3043070433\t0\t'
        lbt += b'\xea\x00\x0a\x00'
    toks = ['2794', 'Company name goes here', 'RRUFFLib', '6.0 U', '000', str(len(spectra)), '3048', '0', '0', '1', '31', '32', '4', str(npts),
            '%f' % x0, '%f' % x1, '0.000000', '1.928467', '1.928467', '5', ' 400', 'Spectrum']
    head = ('\r\n'.join(toks) + '\r\n').encode('latin-1').ljust(2794, b'\x00')
    lbd = bytearray(head)
    for (name, kind, y), ptr in zip(spectra, ptrs):
        b0, b1, b2 = ptr & 0xff, (ptr >> 16) & 0xff, (ptr >> 8) & 0xff
        lbd += struct.pack('<%df' % npts, *y) + bytes([b0, b1, b2, 0]) + b'\x00' * 8
    open(os.path.join(folder, 'RRUFFLib.lbd'), 'wb').write(lbd)
    open(os.path.join(folder, 'RRUFFLib.lbt'), 'wb').write(lbt)


def gauss(centres, heights, width=8.0):
    import math
    x = [32.783936 + k * 1.928467 for k in range(759)]
    return [sum(h * math.exp(-((v - c) / width) ** 2) for c, h in zip(centres, heights)) + 2.0 for v in x]


class Reader(unittest.TestCase):
    def test_names_by_pointer_and_both_record_kinds(self):
        with tempfile.TemporaryDirectory() as d:
            write_library(d, [('AbhuriteR060227_clean', 'field', gauss([300], [10])), ('Sanbornite R050001_processed', 'pascal', gauss([400], [10])),
                              ('Whiteite-(CaFeMg)R060912_785processed', 'field', gauss([500], [10]))])
            got = RW.read_omnic(d)
            self.assertEqual([n for n, _x, _y in got], ['AbhuriteR060227_clean', 'Sanbornite R050001_processed', 'Whiteite-(CaFeMg)R060912_785processed'])
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
