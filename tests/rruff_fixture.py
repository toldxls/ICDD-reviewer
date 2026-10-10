"""Synthetic RRUFF data for the tests — a member file as RRUFF's zips hold them, a store built from such members, and a
Thermo OMNIC library pair on the OMNIC grid. Every name here is made up; nothing of the real collection is in the repo.
Tests that may open a store point `PXRD_RRUFF_STORE` at a temp folder (and `omnic_lib.REMEMBER` / `SEARCH_ROOTS` at
nothing) so the machine's own library stays out, as `tests.test_gui_sp.SpectrumWindow.setUpClass` does."""
import os, math, struct, zipfile


def member(name, rid, laser, kind, x, y, chem='SiO_2_', tech='Raman'):
    """(file name, bytes) of one RRUFF text file: the '##KEY=value' header, then 'x, y' lines."""
    head = ['##NAMES=%s' % name, '##RRUFFID=%s' % rid, '##IDEAL CHEMISTRY=%s' % chem, '##LOCALITY=Somewhere', '##OWNER=RRUFF', '##SOURCE=a museum',
            '##DESCRIPTION=d', '##STATUS=s', '##URL=https://www.rruff.net/odr/rruff_sample/%s' % rid, '##FILETYPE=%s %s' % (tech, 'RAW' if kind == 'raw' else 'Processed')]
    if tech == 'Raman':
        head.append('##RAMAN WAVELENGTH=%s' % laser)
    body = ['%.4f, %.6g' % (a, b) for a, b in zip(x, y)]
    fname = '%s__%s__%s__%s______%s_Data_%s__%s.txt' % (name, rid, tech, laser, tech, 'RAW' if kind == 'raw' else 'Processed', 'ab' * 14)
    return fname, '\n'.join(head + [''] + body + ['##END=', '']).encode('utf-8')


def gauss(x, centres, heights, w=6.0):
    """Gaussian bands of FWHM `w` on the grid `x`."""
    return [sum(h * math.exp(-4 * math.log(2) * ((v - c) / w) ** 2) for c, h in zip(centres, heights)) for v in x]


GRID = [150.0 + 0.5 * k for k in range(2400)]          # a Raman grid 150–1349.5
BROAD = [100.0 + 2.0 * k for k in range(2150)]         # a broad scan 100–4398
IR = [400.0 + 2.0 * k for k in range(1800)]            # an infrared grid 400–3998


def write_store(folder, sets):
    """A store under `folder` from {set name: [(fname, bytes)]} — the zips written to a scratch folder beside it and
    built with `rruff.build` (so the store is exactly what a fetch makes), then removed."""
    from pxrd_review import rruff as R
    src = os.path.join(folder, '_zips'); os.makedirs(src, exist_ok=True)
    zips = []
    for set_name, members in sets.items():
        path = os.path.join(src, set_name + '.zip')
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
            for fname, data in members:
                z.writestr(fname, data)
        zips.append((set_name, path))
    n = R.build(zips, folder, raw=False)
    import shutil
    shutil.rmtree(src, ignore_errors=True)
    return n


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


def omnic_gauss(centres, heights, width=8.0):
    """Bands on the OMNIC grid (759 points, 32.78–1494.56)."""
    x = [32.783936 + k * 1.928467 for k in range(759)]
    return [sum(h * math.exp(-((v - c) / width) ** 2) for c, h in zip(centres, heights)) + 2.0 for v in x]
