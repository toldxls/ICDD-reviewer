"""Reading a Raman or infrared spectrum from the file an instrument or a spreadsheet wrote — pure Python, read only.

    load(path, sheet=None) -> [Series]        every spectrum in the file (a workbook sheet or a JCAMP file may hold several)

Formats, and how far each is proved:
  text            two or more columns in any delimiter, a decimal comma, header lines skipped (CSV / TSV / .txt / .prn /
                  .asc / .xy; a Horiba LabSpec text export with its '#key=value' header; a RRUFF .txt with its '##KEY=' header)
  .xlsx           every x / y block of numeric columns in a sheet: side-by-side blocks, several y columns under one x, an
                  x that descends; a copy of a column shifted by a constant (a plotting offset) is named as such
  JCAMP-DX        ##XYDATA=(X++(Y..Y)) in plain and in compressed (SQZ / DIF / DUP) form, ##XYPOINTS; the file's own
                  checks are run — the abscissa printed on each line against FIRSTX / LASTX / NPOINTS, the DIF Y-check
  Galactic .spc   the published header layout (new format, either byte order; single or multi-file, even or stored x)
  Thermo .spa     \\
  Bruker OPUS      }  layouts from the readers in open use; NO SAMPLE FILE HAS BEEN THROUGH THESE READERS — a Series they
  (0x4B .spc too) /   return carries meta['unverified'], and the caller must say so: check the axis against the instrument's
                      own display before believing a position
  Horiba .l6s     not read (no public layout): export as text from LabSpec
A reader raises ValueError with a sentence a user can act on; it never guesses silently. Nothing is written, and nothing
leaves the machine.
"""
import os, re, math, struct
from collections import namedtuple

Series = namedtuple('Series', 'name x y meta')
#   x ascending (cm⁻¹ unless meta['x_unit'] says otherwise), y as stored; meta: {'source', 'x_unit', 'y_unit', 'format',
#   'unverified': a sentence when the reader is unproved, 'notes': [...]}

TEXT_EXT = ('.txt', '.csv', '.tsv', '.dat', '.prn', '.asc', '.xy', '.rruff')
JCAMP_EXT = ('.jdx', '.dx', '.jcamp', '.jcm')
SPECTRUM_EXT = TEXT_EXT + JCAMP_EXT + ('.spc', '.spa', '.xlsx', '.xlsm')
_UNVERIFIED = 'the %s reader has not been checked against a file from an instrument: compare the axis and a known band with the instrument\'s own display'


def _series(name, x, y, **meta):
    """A Series with x ascending, the NaN / blank pairs dropped."""
    pts = [(a, b) for a, b in zip(x, y) if a is not None and b is not None and not (math.isnan(a) or math.isnan(b) or math.isinf(b))]
    if len(pts) < 5:
        raise ValueError('%s: fewer than five points' % name)
    if pts[0][0] > pts[-1][0]:
        pts.reverse()
    if any(b[0] < a[0] for a, b in zip(pts, pts[1:])):
        pts.sort(key=lambda p: p[0])
        meta.setdefault('notes', []).append('the x values were not in order and have been sorted')
    meta.setdefault('notes', []); meta.setdefault('x_unit', 'cm-1'); meta.setdefault('y_unit', '')
    return Series(name, [p[0] for p in pts], [p[1] for p in pts], meta)


def load(path, sheet=None):
    """[Series] from a spectrum file, by what the file IS (its first bytes), then by its extension."""
    if not os.path.isfile(path):
        raise ValueError('no such file: %s' % path)
    ext = os.path.splitext(path)[1].lower()
    base = os.path.basename(path)
    if ext in ('.xlsx', '.xlsm'):
        return read_xlsx(path, sheet)
    with open(path, 'rb') as f:
        head = f.read(4096)
    if not head:
        raise ValueError('%s is empty' % base)
    if head[:4] == b'\x0a\x0a\xfe\xfe':
        return read_opus(path)
    if ext == '.spc' or (len(head) > 2 and head[1:2] in (b'\x4b', b'\x4c', b'\x4d') and b'\x00' in head[:64] and ext not in TEXT_EXT + JCAMP_EXT):
        return read_spc(path)
    if ext == '.spa' or head[:18].startswith(b'Spectral Data File'):
        return read_spa(path)
    if ext == '.l6s':
        raise ValueError('%s: a LabSpec .l6s file is not read (its layout is not published) — export the spectrum as text (.txt) from LabSpec' % base)
    if b'\x00' in head[:2048] and ext not in TEXT_EXT + JCAMP_EXT:
        raise ValueError('%s is a binary file of a kind this reader does not know — export the spectrum as text, CSV, JCAMP-DX or .spc' % base)
    with open(path, 'rb') as f:
        text = _decode(f.read())
    if ext in JCAMP_EXT or re.search(r'^\s*##\s*(TITLE|JCAMP)', text[:2000], re.I | re.M) and re.search(r'##\s*(XYDATA|XYPOINTS)\s*=', text, re.I):
        return read_jcamp(text, base)
    return read_text(text, base)


def _decode(raw):
    for enc in ('utf-8-sig', 'utf-16', 'cp1252'):
        try:
            t = raw.decode(enc)
            if enc == 'utf-16' and '\x00' in t:
                continue
            return t
        except UnicodeError:
            continue
    return raw.decode('latin-1')


# ----------------------------------------------------------------------------- text

_NUMBER = re.compile(r'^[+-]?(?:\d+[.,]?\d*|[.,]\d+)(?:[eE][+-]?\d+)?$')


def _cells(line, delim):
    if delim is None:
        return line.split()
    return [c.strip() for c in line.split(delim)]


def _value(c, comma_decimal):
    c = c.strip().strip('"')
    if not c or not _NUMBER.match(c):
        return None
    if comma_decimal:
        c = c.replace(',', '.')
    try:
        return float(c)
    except ValueError:
        return None


def read_text(text, name='spectrum'):
    """Columns of numbers under any header. The delimiter is the one that gives the most rows of two or more numbers; a
    comma is a decimal mark when the delimiter is something else and the numbers carry no point."""
    lines = [ln for ln in text.replace('\r\n', '\n').replace('\r', '\n').split('\n')]
    meta = {'format': 'text', 'source': name, 'notes': []}
    body = []; heading = None
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if not body and not s.startswith('#') and not re.match(r'^[+-]?[\d.,]', s):
            heading = s                                          # the last line of words before the numbers: the column names
        m = re.match(r'^#{1,2}\s*([^=:\t]+?)\s*[=:]\s*(.*)$', s)       # '##NAMES=…' (RRUFF), '#Acq. time (s)=\t10' (LabSpec)
        if m:
            key = m.group(1).strip().lower(); val = m.group(2).strip()
            if key in ('names', 'rruffid', 'title', 'laser', 'laser_wavelength', 'acq. time (s)', 'accumulations', 'grating', 'objective', 'spectro (cm-¹)', 'ideal chemistry'):
                meta[key] = val
                if key in ('names', 'rruffid'):
                    meta['format'] = 'rruff'
                if key.startswith('acq.'):
                    meta['format'] = 'labspec'
            continue
        if s.startswith('#') and not re.match(r'^#\s*[+-]?\d', s):
            if re.match(r'^#\s*wave', s, re.I):
                meta['format'] = 'labspec'
            continue
        body.append(s)
    if not body:
        raise ValueError('%s: no data lines' % name)
    best = None
    for delim in ('\t', ';', ',', None):
        for comma_decimal in ((False, True) if delim != ',' else (False,)):
            rows = []
            for s in body:
                vals = [_value(c, comma_decimal) for c in _cells(s, delim)]
                while vals and vals[-1] is None:
                    vals.pop()
                if len(vals) >= 2 and vals[0] is not None and vals[1] is not None:
                    rows.append(vals)
            score = (len(rows), not comma_decimal)
            if rows and (best is None or score > best[0]):
                best = (score, rows, delim, comma_decimal)
    if best is None or best[0][0] < 5:
        raise ValueError('%s: no two columns of numbers found (%d lines read)' % (name, len(body)))
    _score, rows, _delim, comma_decimal = best
    if comma_decimal:
        meta['notes'].append('a comma is read as the decimal mark')
    ncol = max(set(len(r) for r in rows), key=[len(r) for r in rows].count)
    rows = [r for r in rows if len(r) >= ncol]
    if len(rows) < len(body) * 0.5:
        meta['notes'].append('%d of %d lines did not hold %d numbers and were skipped' % (len(body) - len(rows), len(body), ncol))
    out = []
    heads = [c.strip().strip('"') for c in _cells(heading, _delim)] if heading else []
    for k in range(1, ncol):
        ys = [r[k] for r in rows]
        if any(v is None for v in ys):
            continue
        label = heads[k] if len(heads) == ncol and heads[k] else 'column %d' % (k + 1)
        out.append(_series(name if ncol == 2 else '%s [%s]' % (name, label), [r[0] for r in rows], ys, **dict(meta, notes=list(meta['notes']))))
    if not out:
        raise ValueError('%s: no complete column of intensities' % name)
    return out


# ----------------------------------------------------------------------------- xlsx

def read_xlsx(path, sheet=None):
    """Every x / y block of a workbook's sheets (or of one sheet): a column of 20 or more numbers that runs one way is an
    x, the numeric columns right of it of the same length are its y's, until a blank column or the next x."""
    try:
        import openpyxl, warnings
    except ImportError:
        raise ValueError('reading an .xlsx needs openpyxl')
    base = os.path.basename(path)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        sheets = [ws for ws in wb.worksheets if sheet is None or ws.title == sheet or ws.title.lower() == str(sheet).lower()]
        if not sheets:
            raise ValueError('%s has no sheet %r (it has: %s)' % (base, sheet, ', '.join(ws.title for ws in wb.worksheets)))
        out = []
        for ws in sheets:
            rows = [list(r) for r in ws.iter_rows(values_only=True)]
            out += _blocks(rows, '%s | %s' % (base, ws.title))
        wb.close()
    if not out:
        raise ValueError('%s: no column pair that reads as a spectrum%s' % (base, ' in sheet %s' % sheet if sheet else ''))
    return out


def _numeric_run(col):
    """(first row, last row) of the longest run of numbers in a column, None-tolerant at its ends only."""
    best = (0, -1); start = None
    for i, v in enumerate(col + [None]):
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if start is None:
                start = i
        elif start is not None:
            if i - 1 - start > best[1] - best[0]:
                best = (start, i - 1)
            start = None
    return best


def _blocks(rows, name):
    if not rows:
        return []
    ncol = max(len(r) for r in rows)
    cols = [[(r[c] if c < len(r) else None) for r in rows] for c in range(ncol)]
    runs = [_numeric_run(col) for col in cols]
    def is_x(c):
        a, b = runs[c]
        if b - a + 1 < 20:
            return False
        v = cols[c][a: b + 1]
        up = sum(1 for p, q in zip(v, v[1:]) if q > p); down = sum(1 for p, q in zip(v, v[1:]) if q < p)
        return max(up, down) >= 0.98 * (len(v) - 1) and 0 <= min(v) and max(v) <= 20000 and max(v) - min(v) >= 20
    out = []; c = 0
    while c < ncol:
        if not is_x(c):
            c += 1; continue
        a, b = runs[c]; xs = cols[c][a: b + 1]
        ys = []; k = c + 1
        while k < ncol:
            a2, b2 = runs[k]
            if b2 - a2 + 1 < 0.9 * (b - a + 1) or a2 > a + 2:
                break
            if is_x(k) and ys:                                   # the next block's x: a second column that runs one way, once this x has a y
                break
            ys.append(k); k += 1
        first = None
        for n, yc in enumerate(ys):
            a2, b2 = runs[yc]; lo, hi = max(a, a2), min(b, b2)
            y = cols[yc][lo: hi + 1]; x = cols[c][lo: hi + 1]
            notes = []
            head = cols[yc][a2 - 1] if a2 > 0 and isinstance(cols[yc][a2 - 1], str) else None
            if first is not None and len(first) == len(y):
                d = [q - p for p, q in zip(first, y)]
                if max(d) - min(d) < 1e-6 * max(1.0, abs(d[0])) and abs(d[0]) > 0:
                    notes.append('the column before it shifted by %g (a plotting offset)' % d[0])
            if first is None:
                first = y
            label = '%s [%s]' % (name, head.strip() if head else 'columns %s:%s' % (_col_letter(c), _col_letter(yc)))
            try:
                out.append(_series(label, x, y, format='xlsx', source=name, notes=notes, offset_copy=bool(notes)))
            except ValueError:
                pass
        c = k if ys else c + 1
    return out


def _col_letter(c):
    s = ''
    c += 1
    while c:
        c, r = divmod(c - 1, 26)
        s = chr(65 + r) + s
    return s


# ----------------------------------------------------------------------------- JCAMP-DX

_SQZ = {'@': 0}; _SQZ.update({ch: i + 1 for i, ch in enumerate('ABCDEFGHI')}); _SQZ.update({ch: -(i + 1) for i, ch in enumerate('abcdefghi')})
_DIF = {'%': 0}; _DIF.update({ch: i + 1 for i, ch in enumerate('JKLMNOPQR')}); _DIF.update({ch: -(i + 1) for i, ch in enumerate('jklmnopqr')})
_DUP = {ch: i + 1 for i, ch in enumerate('STUVWXYZs')}
_ASDF_TOKEN = re.compile(r'([@A-Ia-i%J-Rj-rS-Zs])(\d*\.?\d*)|([+-]?(?:\d+\.?\d*|\.\d+)(?:[Ee][+-]?\d+)?)')


def _asdf_line(s):
    """The numbers of one XYDATA line in any of the JCAMP forms (AFFN, PAC, SQZ, DIF, DUP) -> (values, last was a DIF)."""
    vals = []; prev_dif = False; pos = 0
    for m in _ASDF_TOKEN.finditer(s):
        if s[pos: m.start()].strip(' \t,;'):
            raise ValueError('an unexpected %r' % s[pos: m.start()].strip())
        pos = m.end()
        if m.group(3) is not None:
            vals.append(float(m.group(3))); prev_dif = False
            continue
        ch, body = m.group(1), m.group(2)
        if ch in _SQZ:
            vals.append((-1 if _SQZ[ch] < 0 else 1) * float('%d%s' % (abs(_SQZ[ch]), body))); prev_dif = False
        elif ch in _DIF:
            if not vals:
                raise ValueError('a difference with nothing before it')
            vals.append(vals[-1] + (-1 if _DIF[ch] < 0 else 1) * float('%d%s' % (abs(_DIF[ch]), body))); prev_dif = True
        else:
            if not vals:
                raise ValueError('a repeat with nothing before it')
            step = (vals[-1] - vals[-2]) if prev_dif and len(vals) >= 2 else 0.0   # a repeated DIF repeats the difference
            for _ in range(int('%d%s' % (_DUP[ch], body)) - 1):
                vals.append(vals[-1] + step)
    if s[pos:].strip(' \t,;'):
        raise ValueError('an unexpected %r' % s[pos:].strip())
    return vals, prev_dif


def read_jcamp(text, name='spectrum'):
    """Every XYDATA / XYPOINTS block of a JCAMP-DX file. The file checks itself: the x printed at the head of each line
    against the even spacing FIRSTX … LASTX over NPOINTS, and the repeated y that follows a line ending in a difference."""
    blocks = []; cur = None; data = None
    for raw in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        ln = raw.split('$$')[0].rstrip()
        if not ln.strip():
            continue
        m = re.match(r'^\s*##\s*([^=]*)=\s*(.*)$', ln)
        if m:
            key = re.sub(r'[\s\-_/]', '', m.group(1)).upper(); val = m.group(2).strip()
            if key == 'TITLE':
                cur = {'TITLE': val, 'lines': None}; blocks.append(cur)
            elif cur is None:
                cur = {'lines': None}; blocks.append(cur)
            if key in ('XYDATA', 'XYPOINTS'):
                cur['form'] = key; cur['lines'] = []; data = cur['lines']
            elif key in ('END', 'PEAKTABLE', 'PEAKASSIGNMENTS'):
                data = None
            else:
                cur[key] = val; data = None if key != '' else data
            continue
        if data is not None:
            data.append(ln.strip())
    out = []
    for b in blocks:
        if not b.get('lines'):
            continue
        title = b.get('TITLE') or name
        notes = []
        def num(key, default=None):
            try:
                return float(b[key].split()[0].replace(',', '.'))
            except (KeyError, ValueError, IndexError):
                return default
        xf, yf = num('XFACTOR', 1.0), num('YFACTOR', 1.0)
        if b['form'] == 'XYPOINTS':
            xs, ys = [], []
            for ln in b['lines']:
                for pair in re.split(r'[;\s]+(?=[+-]?[\d.])', ln) if ';' in ln else [ln]:
                    v = [float(t) for t in re.split(r'[,\s]+', pair.strip()) if t]
                    for k in range(0, len(v) - 1, 2):
                        xs.append(v[k] * xf); ys.append(v[k + 1] * yf)
        else:
            first, last, npts = num('FIRSTX'), num('LASTX'), num('NPOINTS')
            ys = []; heads = []; carry_dif = False
            for ln in b['lines']:
                try:
                    vals, last_dif = _asdf_line(ln)
                except ValueError as e:
                    raise ValueError('%s: a data line could not be read (%s): %r' % (title, e, ln[:60]))
                if len(vals) < 2:
                    continue
                yv = vals[1:]
                at = len(ys)
                if carry_dif and ys:                             # the Y-check: the first y repeats the last of the line before
                    if abs(yv[0] - ys[-1]) > 1e-6 * max(1.0, abs(ys[-1])):
                        notes.append('a Y-check failed at x = %g (the file\'s own check on its compression)' % (vals[0] * xf))
                    yv = yv[1:]; at -= 1                         # … and the x printed on the line is that repeated point's
                heads.append((at, vals[0] * xf))
                ys += yv; carry_dif = last_dif
            n = len(ys)
            if npts is not None and int(npts) != n:
                notes.append('NPOINTS says %d and the data hold %d' % (int(npts), n))
            if first is None or last is None:
                if len(heads) < 2:
                    raise ValueError('%s: no FIRSTX / LASTX and one data line' % title)
                step = (heads[-1][1] - heads[0][1]) / (heads[-1][0] - heads[0][0])
                first = heads[0][1]; last = first + step * (n - 1)
                notes.append('FIRSTX / LASTX are missing: the axis is taken from the x printed on the data lines')
            step = (last - first) / (n - 1) if n > 1 else 0.0
            xs = [first + step * i for i in range(n)]
            bad = sum(1 for i, hx in heads if abs(hx - xs[i]) > max(abs(step) * 0.6, 1e-6 * abs(hx)))
            if bad:
                notes.append('the x printed on %d of %d data lines departs from the even spacing FIRSTX … LASTX gives' % (bad, len(heads)))
            ys = [v * yf for v in ys]
        xu = (b.get('XUNITS') or '').upper(); yu = (b.get('YUNITS') or '')
        x_unit = 'cm-1' if ('1/CM' in xu or 'CM-1' in xu or 'CM^-1' in xu or 'WAVENUMBER' in xu or 'RAMAN' in xu or not xu) else \
            'nm' if 'NANOMET' in xu else 'um' if 'MICROMET' in xu else xu.lower()
        out.append(_series(title, xs, ys, format='jcamp-dx', source=name, x_unit=x_unit, y_unit=yu, notes=notes, datatype=b.get('DATATYPE', '')))
    if not out:
        raise ValueError('%s: a JCAMP-DX file with no ##XYDATA or ##XYPOINTS block (a peak table alone is not a spectrum)' % name)
    return out


def write_jcamp(series, form='DIF', per_line=8):
    """A Series as JCAMP-DX text (AFFN, or DIF-compressed with its Y-checks) — the tests' round trip, and an export."""
    x, y = series.x, series.y
    n = len(x); yf = max(abs(v) for v in y) / 1e6 or 1.0
    iy = [int(round(v / yf)) for v in y]
    out = ['##TITLE=%s' % series.name, '##JCAMP-DX=4.24', '##DATA TYPE=%s' % (series.meta.get('datatype') or 'INFRARED SPECTRUM'),
           '##XUNITS=1/CM', '##YUNITS=%s' % (series.meta.get('y_unit') or 'ARBITRARY UNITS'), '##XFACTOR=1.0', '##YFACTOR=%r' % yf,
           '##FIRSTX=%r' % x[0], '##LASTX=%r' % x[-1], '##NPOINTS=%d' % n, '##FIRSTY=%r' % y[0], '##XYDATA=(X++(Y..Y))']
    def sqz(v):
        s = str(abs(v)); return ('@ABCDEFGHI'[int(s[0])] if v >= 0 else '@abcdefghi'[int(s[0])]) + s[1:]
    def dif(v):
        s = str(abs(v)); return ('%JKLMNOPQR'[int(s[0])] if v >= 0 else '%jklmnopqr'[int(s[0])]) + s[1:]
    i = 0
    while i < n:
        if form == 'DIF':
            j = min(n, i + per_line)
            line = '%.6f' % x[i] + sqz(iy[i]) + ''.join(dif(iy[k] - iy[k - 1]) for k in range(i + 1, j))
            out.append(line)
            i = j - 1 if j < n else n                            # the next line starts on this line's last y: the Y-check
            if i == n - 1 and j == n:
                break
        else:
            j = min(n, i + per_line)
            out.append('%.6f ' % x[i] + ' '.join(str(v) for v in iy[i:j]))
            i = j
    out.append('##END=')
    return '\n'.join(out) + '\n'


# ----------------------------------------------------------------------------- Galactic SPC

_SPC_X = {0: '', 1: 'cm-1', 2: 'um', 3: 'nm', 13: 'cm-1'}                 # 13 = Raman shift
_SPC_Y = {0: '', 1: 'interferogram', 2: 'absorbance', 3: 'Kubelka-Munk', 4: 'counts', 128: 'transmittance', 129: 'reflectance'}


def read_spc(path):
    """A Galactic / GRAMS .spc file: 512-byte header, an x array when the file stores one, then per sub-file a 32-byte
    subheader and its y values (IEEE float when the exponent byte is 0x80, else integers scaled by 2^exp)."""
    base = os.path.basename(path)
    with open(path, 'rb') as f:
        raw = f.read()
    if len(raw) < 512:
        raise ValueError('%s is too short to be an .spc file' % base)
    flags, version = raw[0], raw[1]
    if version == 0x4d:
        raise ValueError('%s is an old-format (1980s) .spc file, which is not read — open it in the instrument software and save it again, or export text' % base)
    if version not in (0x4b, 0x4c):
        raise ValueError('%s does not carry an .spc version byte (0x4B / 0x4C)' % base)
    e = '<' if version == 0x4b else '>'
    fexper, fexp, fnpts, ffirst, flast, fnsub = struct.unpack(e + 'Bbiddi', raw[2:28])
    fxtype, fytype = raw[28], raw[29]
    cmnt = raw[88:218].split(b'\x00')[0].decode('latin-1').strip()
    multi = bool(flags & 0x04); xyxys = bool(flags & 0x40); xvals = bool(flags & 0x80); y16 = bool(flags & 0x01)
    if xyxys:
        raise ValueError('%s stores a separate x array per sub-file (an XYXY multi-file), which is not read — export the spectra singly' % base)
    if fnpts <= 0 or fnpts > 5000000:
        raise ValueError('%s: the header gives %d points' % (base, fnpts))
    pos = 512
    if xvals:
        x = list(struct.unpack(e + '%df' % fnpts, raw[pos: pos + 4 * fnpts])); pos += 4 * fnpts
    else:
        step = (flast - ffirst) / (fnpts - 1) if fnpts > 1 else 0.0
        x = [ffirst + step * i for i in range(fnpts)]
    out = []
    for k in range(max(1, fnsub)):
        if pos + 32 > len(raw):
            break
        subexp = struct.unpack('b', raw[pos + 1: pos + 2])[0]; pos += 32
        exp = subexp if multi else fexp
        if exp == -128:
            size = 4 * fnpts
            y = list(struct.unpack(e + '%df' % fnpts, raw[pos: pos + size]))
        elif y16:
            size = 2 * fnpts
            y = [v * 2.0 ** (exp - 16) for v in struct.unpack(e + '%dh' % fnpts, raw[pos: pos + size])]
        else:
            size = 4 * fnpts
            y = [v * 2.0 ** (exp - 32) for v in struct.unpack(e + '%di' % fnpts, raw[pos: pos + size])]
        pos += size
        out.append(_series(base if fnsub <= 1 else '%s [%d]' % (base, k + 1), x, y, format='spc', source=base, x_unit=_SPC_X.get(fxtype, 'cm-1'),
                           y_unit=_SPC_Y.get(fytype, ''), comment=cmnt, unverified=_UNVERIFIED % 'Galactic .spc'))
    if not out:
        raise ValueError('%s: no sub-file could be read' % base)
    return out


def write_spc(series, as_float=True):
    """A Series as the bytes of a new-format .spc file with an even x axis — the tests' round trip."""
    n = len(series.x)
    head = bytearray(512)
    head[0] = 0; head[1] = 0x4b
    struct.pack_into('<Bbiddi', head, 2, 0, -128 if as_float else 0, n, series.x[0], series.x[-1], 1)
    head[28] = 1; head[29] = 2
    cm = (series.name or '').encode('latin-1', 'replace')[:129]
    head[88: 88 + len(cm)] = cm
    sub = bytearray(32)
    if as_float:
        body = struct.pack('<%df' % n, *series.y)
    else:
        top = max(abs(v) for v in series.y) or 1.0
        exp = int(math.ceil(math.log(top, 2))) + 1
        struct.pack_into('<Bbiddi', head, 2, 0, exp, n, series.x[0], series.x[-1], 1)
        body = struct.pack('<%di' % n, *[int(round(v / 2.0 ** (exp - 32))) for v in series.y])
    return bytes(head) + bytes(sub) + body


# ----------------------------------------------------------------------------- Thermo SPA, Bruker OPUS (unverified)

def read_spa(path):
    """A Thermo OMNIC .spa file: a directory of 16-byte entries from byte 304 (their count at 294); the entry of type 2
    points at the spectrum header (points at +4, first and last x at +16 / +20), the entry of type 3 at the float32 data."""
    base = os.path.basename(path)
    with open(path, 'rb') as f:
        raw = f.read()
    if len(raw) < 600:
        raise ValueError('%s is too short to be an OMNIC .spa file' % base)
    title = raw[30:285].split(b'\x00')[0].decode('latin-1', 'replace').strip()
    n_entries = struct.unpack('<H', raw[294:296])[0]
    hdr = data = None
    for k in range(min(n_entries, 200)):
        p = 304 + 16 * k
        if p + 16 > len(raw):
            break
        kind = raw[p]
        if kind == 2 and hdr is None:
            hdr = struct.unpack('<I', raw[p + 2: p + 6])[0]
        elif kind == 3 and data is None:
            data = struct.unpack('<II', raw[p + 2: p + 10])
    if hdr is None or data is None or hdr + 24 > len(raw):
        raise ValueError('%s: the spectrum header or data section was not found where an OMNIC .spa keeps them — export the spectrum as CSV, JCAMP-DX or .spc from OMNIC' % base)
    npts = struct.unpack('<I', raw[hdr + 4: hdr + 8])[0]
    first, last = struct.unpack('<ff', raw[hdr + 16: hdr + 24])
    pos, size = data
    if not (5 <= npts <= 5000000) or size < 4 * npts or pos + 4 * npts > len(raw) or not (0 <= min(first, last) and max(first, last) <= 40000 and first != last):
        raise ValueError('%s: the header reads as %d points from %g to %g, which is not a spectrum — export it as CSV, JCAMP-DX or .spc from OMNIC' % (base, npts, first, last))
    y = list(struct.unpack('<%df' % npts, raw[pos: pos + 4 * npts]))
    step = (last - first) / (npts - 1)
    return [_series(title or base, [first + step * i for i in range(npts)], y, format='spa', source=base, unverified=_UNVERIFIED % 'Thermo .spa')]


_OPUS_DATA = {7: 'sample', 11: 'reference', 15: 'spectrum'}                # the low byte of a data block's type; its parameters carry that + 16
_OPUS_KIND = {4: 'single channel', 8: 'interferogram', 12: 'phase', 16: 'absorbance', 20: 'transmittance', 24: 'Kubelka-Munk', 28: 'trace', 40: 'Raman', 44: 'emission', 48: 'reflectance'}


def _opus_params(raw, pos, length):
    out = {}; end = min(len(raw), pos + length)
    while pos + 8 <= end:
        name = raw[pos: pos + 3].decode('latin-1', 'replace')
        kind, size = struct.unpack('<HH', raw[pos + 4: pos + 8])
        pos += 8
        if name == 'END':
            break
        blob = raw[pos: pos + 2 * size]
        try:
            out[name] = struct.unpack('<i', blob[:4])[0] if kind == 0 else struct.unpack('<d', blob[:8])[0] if kind == 1 else blob.split(b'\x00')[0].decode('latin-1', 'replace')
        except struct.error:
            pass
        pos += 2 * size
    return out


def read_opus(path):
    """A Bruker OPUS file: a 24-byte header, a directory of 12-byte entries (type, length in 4-byte words, offset); each
    data block has a parameter block (type + 16) giving NPT, FXV, LXV and the scale CSF."""
    base = os.path.basename(path)
    with open(path, 'rb') as f:
        raw = f.read()
    if len(raw) < 48 or raw[:4] != b'\x0a\x0a\xfe\xfe':
        raise ValueError('%s is not an OPUS file' % base)
    first_dir, _max_e, n_e = struct.unpack('<iii', raw[12:24])
    blocks = []
    for k in range(min(n_e, 500)):
        p = first_dir + 12 * k
        if p + 12 > len(raw):
            break
        btype, length, offset = struct.unpack('<iii', raw[p: p + 12])
        blocks.append((btype & 0xff, (btype >> 8) & 0xff, 4 * length, offset))
    out = []
    for low, kind, length, offset in blocks:
        if low not in _OPUS_DATA or kind in (8, 12):                    # an interferogram or a phase is not a spectrum
            continue
        par = next((_opus_params(raw, o, ln) for lo2, k2, ln, o in blocks if lo2 == low + 16 and k2 == kind), None)
        if not par or 'NPT' not in par or 'FXV' not in par or 'LXV' not in par:
            continue
        npts = par['NPT']
        if not (5 <= npts <= 5000000) or offset + 4 * npts > len(raw):
            continue
        csf = par.get('CSF', 1.0) or 1.0
        y = [v * csf for v in struct.unpack('<%df' % npts, raw[offset: offset + 4 * npts])]
        step = (par['LXV'] - par['FXV']) / (npts - 1)
        label = '%s [%s%s]' % (base, _OPUS_DATA[low] + ' ' if low != 15 else '', _OPUS_KIND.get(kind, 'block %d' % kind))
        out.append(_series(label, [par['FXV'] + step * i for i in range(npts)], y, format='opus', source=base, y_unit=_OPUS_KIND.get(kind, ''),
                           x_unit='cm-1' if str(par.get('DXU', 'WN')).upper().startswith(('WN', 'RS')) else str(par.get('DXU', '')).lower(),
                           unverified=_UNVERIFIED % 'Bruker OPUS'))
    if not out:
        raise ValueError('%s: no spectrum block with its parameters (NPT, FXV, LXV) was found in this OPUS file — export the spectrum as a data point table or JCAMP-DX from OPUS' % base)
    out.sort(key=lambda s: 0 if 'absorbance' in s.name or 'Raman' in s.name or 'transmittance' in s.name else 1)
    return out


# ----------------------------------------------------------------------------- units

def raman_shift(series, laser_nm):
    """A Series recorded against absolute wavelength (nm) as Raman shift (cm⁻¹) from the laser line."""
    if series.meta.get('x_unit') != 'nm':
        return series
    x = [1e7 / laser_nm - 1e7 / v for v in series.x]
    return _series(series.name, x, series.y, **dict(series.meta, x_unit='cm-1', notes=list(series.meta.get('notes', [])) + ['x converted from nm with a %g nm laser' % laser_nm]))


def wavenumber(series):
    """A Series against wavelength in micrometres as wavenumber."""
    if series.meta.get('x_unit') != 'um':
        return series
    return _series(series.name, [1e4 / v for v in series.x], series.y, **dict(series.meta, x_unit='cm-1'))


def guess_kind(series):
    """'ir-transmittance' | 'ir-absorbance' | 'raman' | '' — from the stated y unit, else from the shape: an infrared
    transmittance spectrum sits near its top (100 % or 1) and dips; counts stand on a floor and rise."""
    yu = (series.meta.get('y_unit') or '').lower()
    if 'transmit' in yu:
        return 'ir-transmittance'
    if 'absorb' in yu:
        return 'ir-absorbance'
    if 'raman' in yu or 'count' in yu or 'raman' in (series.meta.get('datatype') or '').lower() or series.meta.get('format') in ('rruff', 'labspec'):
        return 'raman'
    ys = sorted(series.y); n = len(ys)
    lo, med, hi = ys[n // 50], ys[n // 2], ys[-1 - n // 50]
    if hi > lo and (hi - med) < 0.25 * (hi - lo) and (85 <= hi <= 110 or 0.85 <= hi <= 1.1):
        return 'ir-transmittance'
    return ''
