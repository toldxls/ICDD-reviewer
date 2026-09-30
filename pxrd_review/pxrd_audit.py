"""A manuscript's powder-diffraction table against the structure it comes with (`pxrd pxrdaudit`).

    python3 -m pxrd_review.pxrd_audit <manuscript.docx|paper.pdf> --cif structure.cif [--lambda Mo]

What is checked, and how it is graded:
  cell      the cell the dcalc column was computed from, back-fitted from the printed (hkl, dcalc) by
            linear least squares on 1/d² (the crystal system taken from the .cif's cell), compared with
            the .cif's cell and every cell the manuscript prints: when neither reproduces the column
            to within its own rounding, the dcalc came from a cell the manuscript does not report — flag;
  omitted   reflections of the .cif's calculated pattern at least as strong as the weakest line the
            table lists, whose d falls under an observed line or inside a listed group, but which the
            table leaves out — flag (the table says it lists lines down to that intensity);
  icalc     the printed Icalc against the pattern computed from the .cif (`powder_calc`): the rms
            difference on the 100 scale, the corpus median being 4 — a note with the worst lines when
            it is large, since programs differ in scattering factors, displacement parameters and Lp;
  ratio     Iobs / ΣIcalc per observed line — a note where a line is far from the table's own median
            ratio (preferred orientation, a misassigned line, a misprint);
  dobs      an observed d outside the d-range of the calculated lines assigned to it, by more than
            their own spread and 0.2 % — a note.
A .docx table is read cell by cell (Word's vertical merges are the grouping); a .pdf's table through
`paper_extract.pxrd_table`, grouped by the nearest observed line. Nothing is written.
"""
import os, re, sys, math, argparse

from pxrd_review import bv_check as B

CELL_OFF = 0.001           # a printed cell is another cell when a parameter is this far (relative) from the back-fitted one — and beyond 3 esd and the printed rounding; a fourth decimal is not a finding
OMIT_STRONG = 10.0         # an omitted reflection of this intensity (of 100) is a flag; a weaker one, or one stronger than all the table lists under its observed line, a note
GROUP_TOL = 0.002          # 0.2 %: d tolerance for 'under an observed line' and for a dobs outside its group
ICALC_NOTE = 10.0          # rms on the 100 scale above which the Icalc comparison is reported in full
RATIO_FACTOR = 3.0         # an Iobs/ΣIcalc this many times off the table's median is noted

# ----------------------------------------------------------------------------- the table

_HDR = {'iobs': 'iobs', 'i obs': 'iobs', 'i(obs)': 'iobs', 'iobs.': 'iobs', 'imeas': 'iobs', 'i meas': 'iobs',
        'dobs': 'dobs', 'd obs': 'dobs', 'd(obs)': 'dobs', 'dmeas': 'dobs', 'd meas': 'dobs',
        'dcalc': 'dcalc', 'd calc': 'dcalc', 'd(calc)': 'dcalc', 'dcal': 'dcalc',
        'icalc': 'icalc', 'i calc': 'icalc', 'i(calc)': 'icalc', 'ical': 'icalc',
        'hkl': 'hkl', 'h k l': 'hkl', 'h': 'h', 'k': 'k', 'l': 'l'}


def _hdr(cell):
    t = re.sub(r'[\s_*]+', ' ', cell.replace('^', '').strip()).lower()
    t = t.replace('å', '').replace('(å)', '').strip()
    return _HDR.get(t) or _HDR.get(t.replace(' ', ''))


def _num(t):
    t = (t or '').strip().replace('−', '-').replace('–', '-')
    m = re.match(r'^-?\d+(?:\.\d+)?', t)
    return float(m.group(0)) if m else None


def _hkl(t):
    v = re.findall(r'-?\d+', (t or '').replace('−', '-').replace('–', '-').replace('̅', '-'))
    return tuple(int(x) for x in v[:3]) if len(v) >= 3 else None


def read_docx_powder(path):
    """The manuscript's powder table: [{'iobs', 'dobs', 'dcalc', 'icalc', 'hkl', 'group'}] — one entry per
    calculated line, `group` numbering the observed line it is listed under (Word's vertical merges),
    and the number of decimals the d values are printed to."""
    from docx import Document
    W = B.W
    doc = Document(path)
    best = None
    for tbl in doc.tables:
        rows = []
        for tr in tbl._tbl.iter(W + 'tr'):
            cells = []
            for tc in tr.findall(W + 'tc'):
                vm = tc.find(W + 'tcPr/' + W + 'vMerge')
                cells.append((''.join(x.text or '' for x in tc.iter(W + 't')), None if vm is None else (vm.get(W + 'val') or 'continue')))
            rows.append(cells)
        if not rows:
            continue
        hdr_i = next((i for i, r in enumerate(rows[:3]) if sum(1 for c, _ in r if _hdr(c) in ('dobs', 'dcalc', 'hkl')) >= 2), None)
        if hdr_i is None:
            continue
        # column blocks: each run from an Iobs/dobs column to the next hkl (or h k l) column
        hdr = [_hdr(c) for c, _ in rows[hdr_i]]
        blocks = []; cur = {}
        for ci, h in enumerate(hdr):
            if h in ('iobs', 'dobs') and cur.get(h) is not None:
                blocks.append(cur); cur = {}
            if h:
                cur[h] = ci
            if h in ('hkl', 'l'):
                blocks.append(cur); cur = {}
        if cur:
            blocks.append(cur)
        blocks = [b for b in blocks if 'dcalc' in b and ('hkl' in b or all(k in b for k in 'hkl'))]
        if not blocks:
            continue
        out = []; group = 0; decimals = 3
        for b in blocks:
            last = None
            for ri in range(hdr_i + 1, len(rows)):
                r = rows[ri]
                get = lambda k: r[b[k]] if k in b and b[k] < len(r) else ('', None)
                dcalc = _num(get('dcalc')[0])
                hkl = _hkl(get('hkl')[0]) if 'hkl' in b else (lambda h, k, l: (int(h), int(k), int(l)) if all(re.match(r'^-?\d+$', x.strip()) for x in (h, k, l)) else None)(get('h')[0], get('k')[0], get('l')[0])
                if dcalc is None or hkl is None:
                    continue
                dtxt = get('dcalc')[0].strip()
                if '.' in dtxt:
                    decimals = len(dtxt.split('.')[1])
                dobs_c, dobs_m = get('dobs'); iobs_c, _ = get('iobs')
                dobs = _num(dobs_c); iobs = _num(iobs_c)
                if dobs is not None and dobs_m != 'continue':
                    group += 1; last = (dobs, iobs)
                elif dobs_m == 'continue' or (dobs is None and last is not None and False):
                    pass
                elif dobs is None:
                    last = None
                g = group if (dobs is not None or dobs_m == 'continue') and last else None
                out.append({'iobs': last[1] if g else None, 'dobs': last[0] if g else None, 'dcalc': dcalc,
                            'icalc': _num(get('icalc')[0]) if 'icalc' in b else None, 'hkl': hkl, 'group': g})
        if out and (best is None or len(out) > len(best[0])):
            best = (out, decimals)
    return best or ([], 3)


def read_pdf_powder(path):
    """The paper's table through paper_extract, each calculated line grouped with the nearest observed one."""
    from pxrd_review import paper_extract as PE
    obs, calc = PE.pxrd_table(path)
    out = []
    obs = sorted(((d, I) for d, I in obs if d), reverse=True)
    for d, I, hkl in calc:
        h = _hkl(str(hkl)) if not isinstance(hkl, (tuple, list)) else tuple(hkl)
        if not d or h is None:
            continue
        near = min(((abs(od - d) / d, i) for i, (od, oi) in enumerate(obs)), default=None)
        g = near[1] + 1 if near and near[0] <= 0.004 else None
        out.append({'iobs': obs[g - 1][1] if g else None, 'dobs': obs[g - 1][0] if g else None, 'dcalc': float(d),
                    'icalc': float(I) if I is not None else None, 'hkl': h, 'group': g})
    return out, 3

# ----------------------------------------------------------------------------- the cell behind dcalc

def _system(cell, symbol=''):
    """The crystal system for the back-fit: the space-group symbol where it says (a 4 in it is tetragonal,
    a 3 or 6 hexagonal axes, a 3 after a 2/m/4 cubic; an orthorhombic cell may have a ≈ b by chance),
    the metric otherwise."""
    a, b, c, al, be, ga = cell
    eq = lambda x, y: abs(x - y) <= 0.002 * max(x, y)
    right = [abs(x - 90) < 0.05 for x in (al, be, ga)]
    sym = re.sub(r'[\s_()]', '', symbol or '').replace('-', '')
    body = sym[1:] if sym[:1] in 'PABCIFRH' else sym
    if body:
        if re.search(r'^(2|m|4|n|d|a|b|c)[^3]*3', body) or body in ('23', 'm3', 'm3m', '43m', '432', 'a3', 'n3'):
            return 'cubic'
        if re.search(r'4', body):
            return 'tetragonal'
        if re.search(r'[36]', body):
            return 'hexagonal'
        if all(right) and len(re.findall(r'2|m|c|n|a|b|d|e', body)) >= 2 and not re.fullmatch(r'(2|m|c|n|a|b|d|e|21|2/m|2/c|2/n|2/a|21/m|21/c|21/n|21/a|21/b|2/b)', body):
            return 'orthorhombic'
    if all(right):
        if eq(a, b) and eq(b, c):
            return 'cubic'
        if (eq(a, b) or eq(b, c) or eq(a, c)) and not body:
            return 'tetragonal'
        return 'orthorhombic'
    if eq(a, b) and abs(ga - 120) < 0.05 and right[0] and right[1]:
        return 'hexagonal'
    if sum(right) == 2:
        return 'monoclinic-' + 'abc'[right.index(False)]
    return 'triclinic'


def _basis(system, h, k, l):
    """The terms of 1/d² = Σ pᵢ·termᵢ for the system (the reciprocal metric's free components)."""
    if system == 'cubic':
        return [h * h + k * k + l * l]
    if system == 'tetragonal':
        return [h * h + k * k, l * l]
    if system == 'hexagonal':
        return [h * h + h * k + k * k, l * l]
    if system == 'orthorhombic':
        return [h * h, k * k, l * l]
    if system == 'monoclinic-b':
        return [h * h, k * k, l * l, h * l]
    if system == 'monoclinic-a':
        return [h * h, k * k, l * l, k * l]
    if system == 'monoclinic-c':
        return [h * h, k * k, l * l, h * k]
    return [h * h, k * k, l * l, h * k, h * l, k * l]


def _solve(A, y):
    """Least squares by the normal equations (Gauss–Jordan with pivoting): (parameters, their esds
    from the residual variance × (AᵀA)⁻¹), or (None, None)."""
    n = len(A[0]); m = len(A)
    N = [[sum(r[i] * r[j] for r in A) for j in range(n)] for i in range(n)]
    v = [sum(r[i] * yy for r, yy in zip(A, y)) for i in range(n)]
    M = [N[i] + [v[i]] + [1.0 if j == i else 0.0 for j in range(n)] for i in range(n)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(M[r][i]))
        M[i], M[p] = M[p], M[i]
        if abs(M[i][i]) < 1e-14:
            return None, None
        piv = M[i][i]; M[i] = [x / piv for x in M[i]]
        for r in range(n):
            if r != i:
                f = M[r][i]
                M[r] = [x - f * yv for x, yv in zip(M[r], M[i])]
    par = [M[i][n] for i in range(n)]
    inv = [[M[i][n + 1 + j] for j in range(n)] for i in range(n)]
    res = [yy - sum(pi * ai for pi, ai in zip(par, r)) for r, yy in zip(A, y)]
    s2 = sum(x * x for x in res) / max(1, m - n)
    return par, [math.sqrt(max(s2 * inv[i][i], 0.0)) for i in range(n)]


def _gstar(system, p):
    """The reciprocal metric tensor from the fitted parameters."""
    if system == 'cubic':
        A = p[0]; return [[A, 0, 0], [0, A, 0], [0, 0, A]]
    if system == 'tetragonal':
        return [[p[0], 0, 0], [0, p[0], 0], [0, 0, p[1]]]
    if system == 'hexagonal':
        return [[p[0], p[0] / 2, 0], [p[0] / 2, p[0], 0], [0, 0, p[1]]]
    if system == 'orthorhombic':
        return [[p[0], 0, 0], [0, p[1], 0], [0, 0, p[2]]]
    if system == 'monoclinic-b':
        return [[p[0], 0, p[3] / 2], [0, p[1], 0], [p[3] / 2, 0, p[2]]]
    if system == 'monoclinic-a':
        return [[p[0], 0, 0], [0, p[1], p[3] / 2], [0, p[3] / 2, p[2]]]
    if system == 'monoclinic-c':
        return [[p[0], p[3] / 2, 0], [p[3] / 2, p[1], 0], [0, 0, p[2]]]
    return [[p[0], p[3] / 2, p[4] / 2], [p[3] / 2, p[1], p[5] / 2], [p[4] / 2, p[5] / 2, p[2]]]


def _cell_from_gstar(Gs):
    from pxrd_review import powder_calc as PC
    G = PC._inv3(Gs)
    a, b, c = (math.sqrt(G[i][i]) for i in range(3))
    al = math.degrees(math.acos(G[1][2] / (b * c))); be = math.degrees(math.acos(G[0][2] / (a * c))); ga = math.degrees(math.acos(G[0][1] / (a * b)))
    return (a, b, c, al, be, ga)


def d_of(cell, hkl):
    a, b, c, al, be, ga = cell
    G = B.Structure.__new__(B.Structure); G.cell = cell; B.Structure._metric(G)
    from pxrd_review import powder_calc as PC
    Gs = PC._inv3(G.G)
    q = sum(hkl[i] * Gs[i][j] * hkl[j] for i in range(3) for j in range(3))
    return 1.0 / math.sqrt(q) if q > 0 else None


def fit_cell(rows, system):
    """The cell the dcalc column follows from: (cell, rms in Å) or None."""
    data = [(r['hkl'], r['dcalc']) for r in rows if r['dcalc'] and r['hkl']]
    n_par = len(_basis(system, 1, 1, 1))
    if len(data) < n_par + 2:
        return None
    A = [_basis(system, *h) for h, d in data]; y = [1.0 / (d * d) for h, d in data]
    p, sig = _solve(A, y)
    if p is None or any(v <= 0 for v in p[:min(3, len(p))]):
        return None
    try:
        cell = _cell_from_gstar(_gstar(system, p))
        # the cell parameters' esds: each fitted parameter moved by its esd, the shifts added in quadrature
        var = [0.0] * 6
        for j in range(len(p)):
            q = list(p); q[j] += sig[j]
            c2 = _cell_from_gstar(_gstar(system, q))
            for i in range(6):
                var[i] += (c2[i] - cell[i]) ** 2
        cell_sig = [math.sqrt(v) for v in var]
    except (ValueError, ZeroDivisionError):
        return None
    return cell, rms_of(cell, rows), cell_sig


def rms_of(cell, rows):
    ds = [(d_of(cell, r['hkl']), r['dcalc']) for r in rows if r['dcalc'] and r['hkl']]
    ds = [(x, y) for x, y in ds if x]
    return math.sqrt(sum((x - y) ** 2 for x, y in ds) / len(ds)) if ds else None


_CELL_LINE = re.compile(r'\ba\s*=\s*(\d+\.\d+)')


def manuscript_cells(text_lines, system_hint):
    """Every cell the manuscript prints as 'a = … b = … c = … β = …' (over up to five lines):
    [(label, cell, decimals printed)] — None where a value is a default, not printed."""
    out = []
    for i, t in enumerate(text_lines):
        if not _CELL_LINE.search(t):
            continue
        seg = ' '.join(text_lines[i:i + 5]).replace('−', '-').replace('–', '-')
        def g(k):
            m = re.search(r'(?<![A-Za-z])%s\s*=\s*(\d+\.\d+)' % k, seg)
            if not m:
                return None, None
            return float(m.group(1)), len(m.group(1).split('.')[1])
        a, b, c = g('a'), g('b'), g('c')
        al = g('α') if g('α')[0] else g('alpha'); be = g('β') if g('β')[0] else g('beta'); ga = g('γ') if g('γ')[0] else g('gamma')
        need = {'monoclinic-a': [al], 'monoclinic-b': [be], 'monoclinic-c': [ga], 'triclinic': [al, be, ga]}.get(system_hint, [])
        if any(v[0] is None for v in need):
            continue                                        # a cell printed without the angle its system needs: not this one
        if not (a[0] and c[0]):
            continue
        b = b if b[0] else a
        vals = (a, b, c, al if al[0] else (90.0, None), be if be[0] else (90.0, None), ga if ga[0] else ((120.0, None) if system_hint == 'hexagonal' else (90.0, None)))
        cell = tuple(v[0] for v in vals); esd = tuple(v[1] for v in vals)
        if not any(all(abs(x - y) < 1e-6 for x, y in zip(cell, o[1])) for o in out):
            out.append(('the manuscript' + (' (powder)' if re.search(r'powder|PXRD', seg, re.I) else ''), cell, esd))
    return out


def cell_matches(fit, cand, decimals, system, fit_sig=None):
    """Does the printed cell agree with the back-fitted one? A dcalc column is computed from the refined
    value, which rounds to the printed digits — so the tolerance is the printed rounding (with a little
    slack for the fit), not the esd: b = 15.49 cannot have given d values that fit b = 15.438, whatever
    its esd. -> (True/False, the worst relative deviation)."""
    worst = 0.0; ok = True
    for i in range(6):
        if i >= 3 and abs(cand[i] - 90) < 1e-6 and abs(fit[i] - 90) < 0.05:
            continue
        tol = max(1.5 * 0.5 * 10 ** -(decimals[i] if decimals[i] is not None else 3), 3 * (fit_sig[i] if fit_sig else 0.0), CELL_OFF * cand[i])
        dev = abs(fit[i] - cand[i])
        worst = max(worst, dev / cand[i])
        if dev > tol:
            ok = False
    return ok, worst

# ----------------------------------------------------------------------------- the audit

def _fmt_cell(cell, system):
    a, b, c, al, be, ga = cell
    s = 'a = %.4f, b = %.4f, c = %.4f' % (a, b, c)
    if system.startswith('monoclinic'):
        s += ', %s = %.3f' % ({'a': 'α', 'b': 'β', 'c': 'γ'}[system[-1]], {'a': al, 'b': be, 'c': ga}[system[-1]])
    elif system == 'triclinic':
        s += ', α = %.3f, β = %.3f, γ = %.3f' % (al, be, ga)
    return s


def audit(manuscript, cif, lam=None):
    from pxrd_review import powder_calc as PC
    st = B.Structure(cif)
    is_docx = manuscript.lower().endswith('.docx')
    rows, decimals = read_docx_powder(manuscript) if is_docx else read_pdf_powder(manuscript)
    recs = []; L = ['Powder-table audit — %s vs %s' % (os.path.basename(manuscript), os.path.basename(cif))]
    if len(rows) < 8:
        L.append('  no powder table with dcalc and hkl was read'); return {'records': recs, 'lines': L, 'rows': rows}
    if is_docx:
        from pxrd_review import cif_audit as CA
        text_lines = [t for _k, t in CA.docx_lines(manuscript)]
        text = '\n'.join(text_lines)
    else:
        from pxrd_review import paper_extract as PE
        text = PE.text_of(manuscript); text_lines = text.split('\n')
    m = re.search(r'\b(Cu|Mo|Co|Cr|Fe|Ag)\s*K\s*[αa]', text, re.I)
    lam = PC.wavelength(lam or (m.group(1) if m else 'Cu'))
    groups = {}
    for r in rows:
        if r['group']:
            groups.setdefault(r['group'], []).append(r)
    n_calc = len(rows); n_obs = len(groups)
    L.append('  %d calculated lines under %d observed, d to %d decimals, λ %.4f Å' % (n_calc, n_obs, decimals, lam))
    # -- the cell behind dcalc
    system = _system(st.cell, st.sg)
    fit = fit_cell(rows, system)
    if fit:
        fcell, frms, fsig = fit
        rounding = 0.5 * 10 ** -decimals
        def _dec(t):
            v = (st.block['items'].get(t) or '').split('(')[0]
            return len(v.split('.')[1]) if '.' in v else 0
        cif_dec = tuple(_dec(t) for t in ('_cell_length_a', '_cell_length_b', '_cell_length_c', '_cell_angle_alpha', '_cell_angle_beta', '_cell_angle_gamma'))
        cands = [('the .cif', st.cell, cif_dec)] + manuscript_cells(text_lines, system)
        judged = [(lab, cell) + cell_matches(fcell, cell, dec, system, fsig) for lab, cell, dec in cands
                  if all(60 <= v <= 150 for v in cell[3:])]
        ok = [j for j in judged if j[2]]
        if ok:
            L.append('  dcalc: the column follows from %s (within %.2f %%; back-fit %s ± %s, rms %.4f Å)'
                     % (ok[0][0], 100 * ok[0][3], _fmt_cell(fcell, system), '/'.join('%.4f' % x for x in fsig[:3]), frms))
        elif frms <= 3 * rounding:
            recs.append({'kind': 'cell', 'severity': 'flag',
                         'text': 'dcalc: the column follows from %s (± %s; rms %.4f Å), a cell the manuscript does not report — %s'
                                 % (_fmt_cell(fcell, system), '/'.join('%.4f' % x for x in fsig[:3]), frms, '; '.join('%s %s is off by %.2f %%' % (lab, _fmt_cell(cell, system), 100 * worst) for lab, cell, _ok, worst in judged))})
        else:
            L.append('  dcalc: no %s cell reproduces the column (back-fit rms %.4f Å): indices or d values inconsistent' % (system, frms))
    # -- the pattern from the .cif
    dmin = max(0.8, min(r['dcalc'] for r in rows) - 0.02)
    pat = PC.pattern(cif, lam, dmin, structure=st)
    idx = {}
    for x in pat:
        for e in PC.equivalents(st, x['hkl']):
            idx.setdefault(e, x)
    def match(r):
        """The pattern line a table row names — the printed hkl, or, where that line's d is not the printed
        dcalc, the sign variant whose d is (a pdf's text layer drops the overbar of a negative index)."""
        x = idx.get(r['hkl'])
        if x is not None and abs(x['d'] - r['dcalc']) <= 0.0015 * r['dcalc']:
            return x
        h, k, l = r['hkl']
        best = x
        for sh in (1, -1):
            for sk in (1, -1):
                for sl in (1, -1):
                    y = idx.get((sh * h, sk * k, sl * l))
                    if y is not None and abs(y['d'] - r['dcalc']) <= 0.0015 * r['dcalc'] and (best is None or abs(y['d'] - r['dcalc']) < abs(best['d'] - r['dcalc'])):
                        best = y
        return best
    listed = set()
    for r in rows:
        x = match(r)
        listed |= PC.equivalents(st, x['hkl'] if x is not None else r['hkl'])
    # -- Icalc vs the .cif
    pairs = [(r, match(r)) for r in rows if r['icalc'] is not None]
    pairs = [(r, x) for r, x in pairs if x is not None]
    rms = None
    if len(pairs) >= 8:
        mx = max(r['icalc'] for r, _ in pairs) or 1.0
        devs = sorted(((r['icalc'] * 100.0 / mx - x['I'], r, x) for r, x in pairs), key=lambda t: -abs(t[0]))
        rms = math.sqrt(sum(d * d for d, _, _ in devs) / len(devs))
        line = 'Icalc: %d lines vs the pattern computed from the .cif — rms %.1f on the 100 scale (corpus median 4)' % (len(devs), rms)
        if rms > ICALC_NOTE:
            line += '; worst: ' + ', '.join('%s %g vs %.0f' % (' '.join(str(v) for v in r['hkl']), r['icalc'], x['I']) for d, r, x in devs[:5])
            recs.append({'kind': 'icalc', 'severity': 'note', 'text': line})
        else:
            L.append('  ' + line)
    # -- omitted overlaps
    imin = min((r['icalc'] for r in rows if r['icalc'] is not None), default=None)
    if imin is not None and groups:
        floor = max(2 * imin, imin + (rms or 0), 1.0)       # over the table's floor by more than the programs disagree
        scale = 100.0 / (max((r['icalc'] or 0) for r in rows) or 1.0)
        # a program that merges near-coincident lines prints one index with the summed intensity: a
        # listed neighbour whose printed Icalc carries the missing line's intensity has not omitted it
        matched = [(r, match(r)) for r in rows if r['icalc'] is not None]
        matched = [(r, x) for r, x in matched if x is not None]
        def absorbed(x):
            for r, y in matched:
                if abs(y['d'] - x['d']) <= 0.004 * x['d'] and r['icalc'] * scale - y['I'] >= 0.5 * x['I']:
                    return True
            return False
        omitted = []; merged = 0
        for x in pat:
            if x['I'] < floor or x['hkl'] in listed:
                continue
            for g, rs in groups.items():
                lo = min(r['dcalc'] for r in rs); hi = max(r['dcalc'] for r in rs); dobs = rs[0]['dobs']
                if lo * (1 - GROUP_TOL) <= x['d'] <= hi * (1 + GROUP_TOL) or (dobs and abs(x['d'] - dobs) <= GROUP_TOL * dobs):
                    if absorbed(x):
                        merged += 1
                    else:
                        omitted.append((x, dobs, sum(r['icalc'] or 0 for r in rs) * scale))
                    break
        if merged:
            L.append('  %d reflections not listed by index are carried in a neighbouring line\'s Icalc (the program merged near-coincident lines)' % merged)
        if omitted:
            # a table lists weak lines only where one explains an observed peak, so its weakest line is no
            # threshold: a strong reflection left out, or one stronger than everything listed under its
            # observed line, is the finding; the rest is information (corpus: half the papers omit some)
            strong = [(x, u, gs) for x, u, gs in omitted if x['I'] >= OMIT_STRONG or x['I'] > gs]
            text = ('omitted: %d reflections of I ≥ %.1f fall under listed observed lines but are in no line of the table%s — %s'
                    % (len(omitted), floor, ' (%d of them strong, or stronger than all the table lists there)' % len(strong) if strong else '',
                       '; '.join('%s %.3f (I %.1f) under dobs %.3f' % (' '.join(str(v) for v in x['hkl']), x['d'], x['I'], u) for x, u, gs in (strong or omitted)[:10])))
            # a pdf's table is read by a layout reader that can drop a row: information there, a flag for a .docx read cell by cell
            recs.append({'kind': 'omitted', 'severity': 'flag' if (strong and is_docx) else 'note', 'text': text})
    # -- Iobs / ΣIcalc and dobs against the group
    ratios = []
    for g, rs in groups.items():
        s = sum(r['icalc'] or 0 for r in rs); iobs = rs[0]['iobs']
        if s > 0 and iobs:
            ratios.append((iobs / s, rs))
    if len(ratios) >= 5:
        med = sorted(r for r, _ in ratios)[len(ratios) // 2]
        odd = [(r, rs) for r, rs in ratios if r > RATIO_FACTOR * med or r < med / RATIO_FACTOR]
        if odd:
            recs.append({'kind': 'ratio', 'severity': 'note',
                         'text': 'Iobs/ΣIcalc: median %.2f; %d observed lines are %g× off it — %s' % (med, len(odd), RATIO_FACTOR,
                                 '; '.join('dobs %.3f (Iobs %g, ΣIcalc %g: %.2f)' % (rs[0]['dobs'], rs[0]['iobs'], sum(r['icalc'] or 0 for r in rs), ratio) for ratio, rs in odd[:8]))})
    offs = []
    for g, rs in groups.items():
        lo = min(r['dcalc'] for r in rs); hi = max(r['dcalc'] for r in rs); dobs = rs[0]['dobs']
        if dobs:
            offs.append(((dobs - hi) / dobs if dobs > hi else ((dobs - lo) / dobs if dobs < lo else 0.0), dobs, lo, hi))
    if offs:
        med = sorted(o[0] for o in offs)[len(offs) // 2]
        if abs(med) > GROUP_TOL:
            recs.append({'kind': 'dobs', 'severity': 'note',
                         'text': 'dobs run %+.2f %% from the calculated lines over the table (median of %d): the powder cell differs from the cell behind dcalc' % (100 * med, len(offs))})
        off = [o for o in offs if o[0] != 0.0 and abs(o[0] - med) > GROUP_TOL]
        if off:
            recs.append({'kind': 'dobs', 'severity': 'note',
                         'text': 'dobs outside its group%s: %s' % (' (beyond the table\'s own offset)' if abs(med) > GROUP_TOL else '',
                                 '; '.join('%.3f vs %s (%+.2f %%)' % (dobs, ('%.3f–%.3f' % (hi, lo)) if hi != lo else '%.3f' % lo, 100 * o) for o, dobs, lo, hi in off[:10]))})
    for r in recs:
        L.append('  %s%s' % ('note: ' if r['severity'] == 'note' else '', r['text']))
    return {'records': recs, 'lines': L, 'rows': rows, 'pattern': pat}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('manuscript')
    ap.add_argument('--cif', required=True)
    ap.add_argument('--lambda', dest='lam', help='Å or Cu / Mo / Co … (default: the manuscript\'s stated radiation, else Cu)')
    a = ap.parse_args(argv)
    print('\n'.join(audit(a.manuscript, a.cif, a.lam)['lines']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
