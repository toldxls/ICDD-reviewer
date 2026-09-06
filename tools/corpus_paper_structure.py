"""Prototype: build a structure from a paper's PRINTED atomic coordinates and check it against the
same mineral's .cif — the validation set being the corpus papers that have both.

What it isolates: whether coordinates as printed (4-5 decimals, no esds, occasionally a fraction)
are good enough to reproduce the .cif's bond-valence sums. Symmetry operators and the site type
symbols are taken FROM THE .CIF on purpose: turning 'Pna21' into operators is a table lookup (a
solved, deterministic problem — no table is bundled yet), and valence assignment is a separate
question. Everything geometric — the cell and every x, y, z — comes from the paper.

    python3 tools/corpus_paper_structure.py "<folder with .cif + .pdf>" [more folders]
    CELL_FROM=cif ...      take the cell from the .cif too, isolating the coordinates alone

Measured 2026-09-06 over 176 pairs: 85 papers yielded a coordinate table, 49 of them complete
enough to use, 47 compared. With the .cif's cell: 28 structures (60 %) reproduce every cation's
bond-valence sum within 0.05 vu, 158/200 sites (79 %), median worst deviation 0.006 vu. End to
end (the paper's cell as well): 19 structures, 109/200 sites. The failures are gross, not
marginal (p25 0.000, median 0.004, p75 0.810 vu), so a gate can refuse them.
"""
import os, re, sys, glob, tempfile, collections

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pxrd_review import bv_check as B, paper_extract as PE, epma as EP

HDR = re.compile(r'(?<![A-Za-z])(x/a|y/b|z/c|x|y|z|U ?eq|U ?iso|B ?iso|Wyck\w*|Site|Atom|occ\.?|s\.o\.f\.?)(?![A-Za-z])', re.I)
AXIS = re.compile(r'^\(?([xyz])(?:/[abc])?\)?$', re.I)      # 'x', 'x/a', '(x)'
VAL = re.compile(r'^([-−]?(?:\d*\.\d+|[01](?:\.0*)?|\d/\d))(?:\((\d+)\))?$')
def _val(t):
    """'0.12345(7)' -> 0.12345; '1/2' -> 0.5; '-0.0123' -> -0.0123; None when not a coordinate."""
    m = VAL.match(t.replace('\u2212', '-').rstrip(','))
    if not m:
        return None
    v = m.group(1)
    if '/' in v:
        a, b = v.split('/'); return float(a) / float(b)
    return float(v)

LABEL = re.compile(r'^([A-Z][a-z]?)([A-Za-z]?\(?\d{0,2}\)?[A-Za-z]?)$')     # O1, Ow1, O1W, M(2), Na1a
WYCK = re.compile(r'^\(?\d{1,2}[a-z]\)?$')                                # a Wyckoff token between label and x
FRACT_MAX = 1.05                                                          # a fractional coordinate, nothing else

def _label_ok(t):
    m = LABEL.match(t.rstrip(',*†‡§'))
    return bool(m) and m.group(1) in EP.ATOMIC_WEIGHTS

def _view(lines, lo, hi):
    """The page restricted to one text column: page_lines merges both columns of a two-column page
    into one line, so filtering the words by x is exactly what reading that column gives."""
    out = []
    for ln in lines:
        ws = [w for w in ln['w'] if lo <= (w[0] + w[2]) / 2 <= hi]
        if ws:
            out.append(dict(ln, w=ws))
    return out

def _scan(lines):
    """The widest atom-site table in one view -> [(label, x, y, z)]."""
    best = []
    for i, ln in enumerate(lines):
        hits = {h.lower()[0] for h in HDR.findall(' '.join(w[4] for w in ln['w']))}
        if not {'x', 'y', 'z'} <= hits:
            continue
        cols = {}
        for w in ln['w']:
            m = AXIS.match(w[4])
            if m and m.group(1).lower() not in cols:
                cols[m.group(1).lower()] = (w[0] + w[2]) / 2
        if len(cols) < 3:
            continue
        rows = []; miss = 0; seen_lab = set()
        for ln2 in lines[i + 1:]:
            ws = ln2['w']
            if not ws:
                continue
            lab = ws[0][4].strip()
            rest = ws[1:]
            if rest and WYCK.match(rest[0][4]):
                rest = rest[1:]
            got = {}
            for w in rest:
                v = _val(w[4])
                if v is None or abs(v) > FRACT_MAX:      # Ueq, occupancy and any prose number are not coordinates
                    continue
                xc = (w[0] + w[2]) / 2
                k = min(cols, key=lambda c: abs(cols[c] - xc))
                if abs(cols[k] - xc) <= 26 and k not in got:
                    got[k] = v
            if _label_ok(lab) and len(got) == 3:
                key = lab.upper().strip('*†‡§,')
                if key in seen_lab:
                    break            # the same site again: the scan has walked into the NEXT table —
                                     # anisotropic displacement parameters carry the same labels and
                                     # values in the same range, and would be read as coordinates
                seen_lab.add(key)
                rows.append((lab, got['x'], got['y'], got['z'])); miss = 0
            else:
                miss += 1
                if rows and miss >= 4:
                    break
        if len(rows) > len(best):
            best = rows
    return best

def paper_sites(pdf):
    """The paper's atom-site table, tried on the whole page and on each text column of it."""
    best = []
    try:
        pages = PE._pages(pdf)
    except Exception:
        return best
    for lines in pages:
        xs = [w[0] for ln in lines for w in ln['w']] + [w[2] for ln in lines for w in ln['w']]
        if not xs:
            continue
        mid = (min(xs) + max(xs)) / 2
        for view in (lines, _view(lines, -1e9, mid + 8), _view(lines, mid - 8, 1e9)):
            r = _scan(view)
            if len(r) > len(best):
                best = r
    return best

def norm(lab):
    return re.sub(r'[^A-Za-z0-9]', '', lab).upper()

def cif_sites(path):
    b = [x for x in B.read_cif(path) if B._loop(x, '_atom_site_fract_x')[1]][0]
    tags, rows = B._loop(b, '_atom_site_fract_x')
    g = lambda t, d=None: B._col(tags, rows, t, d)
    out = []
    for lab, ty, x, y, z in zip(g('_atom_site_label'), g('_atom_site_type_symbol', ''),
                                g('_atom_site_fract_x'), g('_atom_site_fract_y'), g('_atom_site_fract_z')):
        out.append((lab, ty, B._num(x), B._num(y), B._num(z)))
    return out, b

def symop_text(block):
    tags, rows = B._loop(block, '_space_group_symop_operation_xyz')
    tag = '_space_group_symop_operation_xyz'
    if rows is None:
        tags, rows = B._loop(block, '_symmetry_equiv_pos_as_xyz'); tag = '_symmetry_equiv_pos_as_xyz'
    if rows is None:
        return None
    return tag, B._col(tags, rows, tag)

def synth_cif(cell, symtag, ops, sites):
    """A CIF carrying the paper's cell and coordinates, the .cif's operators and type symbols."""
    L = ['data_paper']
    for k, v in zip(('a', 'b', 'c'), cell[:3]):
        L.append('_cell_length_%s %.5f' % (k, v))
    for k, v in zip(('alpha', 'beta', 'gamma'), cell[3:]):
        L.append('_cell_angle_%s %.4f' % (k, v))
    L += ['loop_', symtag]
    L += ["'%s'" % s for s in ops]
    L += ['loop_', '_atom_site_label', '_atom_site_type_symbol',
          '_atom_site_fract_x', '_atom_site_fract_y', '_atom_site_fract_z']
    for lab, ty, x, y, z in sites:
        L.append("%s %s %.5f %.5f %.5f" % (lab, ty or re.match(r'[A-Za-z]{1,2}', lab).group(0), x, y, z))
    return '\n'.join(L) + '\n'

def bvs_map(st):
    P = B.Params(prefer='gh', u6='burns')
    res, anion_sum, cells, hb = B.compute(st, P, None, 'oo')
    return {norm(c.label): bvs for c, bonds, bvs, exp, md in res}

def pairs(folder):
    cifs = glob.glob(os.path.join(folder, '*.cif')); pdfs = glob.glob(os.path.join(folder, '*.pdf'))
    out = []
    for c in sorted(cifs):
        ids = set(re.findall(r'I\d{6}', os.path.basename(c))) | set(re.findall(r'^\d{4,5}', os.path.basename(c)))
        m = [p for p in pdfs if any(i in os.path.basename(p) for i in ids)]
        if m:
            out.append((c, sorted(m)))
    return out

CELL_FROM = os.environ.get('CELL_FROM', 'paper')

def main(folders):
    stat = collections.Counter(); rows = []
    for folder in folders:
        for cif, pdfs in pairs(folder):
            name = os.path.basename(cif)
            stat['pairs'] += 1
            try:
                cs, block = cif_sites(cif)
                sy = symop_text(block)
                cell_cif = B._cell(block)
            except Exception as e:
                stat['cif unusable'] += 1; rows.append((name, 'cif unusable: %s' % e, None)); continue
            if not sy:
                stat['cif has no symop loop'] += 1; rows.append((name, 'cif has no symop loop', None)); continue
            ps = []
            for pdf in pdfs:
                ps = paper_sites(pdf)
                if len(ps) >= 3:
                    break
            if len(ps) < 3:
                stat['no coordinate table read'] += 1; rows.append((name, 'no coordinate table read', None)); continue
            stat['coordinate table read'] += 1
            # the paper's cell, when it states one
            cell, used_paper_cell = cell_cif, False
            if CELL_FROM == 'paper':
                try:
                    pc = PE._paper_cells(PE.text_of(pdf))
                    # the single-crystal cell is the one the coordinates belong to, not the powder one
                    pick = next((c for ctx, c in pc if ctx == 'single'), None) or (pc[0][1] if pc else None)
                    if pick:
                        cell = [pick[k] for k in ('a', 'b', 'c', 'α', 'β', 'γ')]; used_paper_cell = True
                        if any(abs(cell[i] - cell_cif[i]) / cell_cif[i] > 0.02 for i in range(3)):
                            stat['paper cell disagrees with the .cif >2%'] += 1
                except Exception:
                    pass
            bylab = {norm(l): (l, t, x, y, z) for l, t, x, y, z in cs}
            matched = []; dmax = 0.0
            for lab, x, y, z in ps:
                k = norm(lab)
                if k in bylab:
                    L, t, cx, cy, cz = bylab[k]
                    matched.append((L, t, x, y, z))
                    dmax = max(dmax, max(abs(x - cx), abs(y - cy), abs(z - cz)))
            if len(matched) < max(3, 0.6 * len(cs)):
                stat['too few sites matched'] += 1
                rows.append((name, 'matched %d of %d .cif sites' % (len(matched), len(cs)), None)); continue
            stat['sites matched'] += 1
            try:
                tmp = tempfile.NamedTemporaryFile('w', suffix='.cif', delete=False)
                tmp.write(synth_cif(cell, sy[0], sy[1], matched)); tmp.close()
                a = bvs_map(B.Structure(cif)); b = bvs_map(B.Structure(tmp.name))
                os.unlink(tmp.name)
            except Exception as e:
                stat['compute failed'] += 1; rows.append((name, 'compute failed: %s' % e, None)); continue
            common = sorted(set(a) & set(b))
            if not common:
                stat['no common cation site'] += 1; rows.append((name, 'no common cation site', None)); continue
            diffs = [abs(a[k] - b[k]) for k in common]
            worst = max(diffs); ok = sum(1 for d in diffs if d <= 0.05)
            stat['compared'] += 1
            stat['all sites within 0.05 vu'] += (ok == len(common))
            rows.append((name, 'sites %d/%d, coord dmax %.4f, cell %s | BVS %d/%d within 0.05 vu, worst %.3f'
                         % (len(matched), len(cs), dmax, 'paper' if used_paper_cell else '.cif', ok, len(common), worst),
                         (ok, len(common), worst)))
    print('=== per pair')
    for n, msg, _ in rows:
        print('  %-34s %s' % (n[:34], msg))
    print('\n=== totals')
    for k in ('pairs', 'cif unusable', 'cif has no symop loop', 'no coordinate table read', 'coordinate table read',
              'too few sites matched', 'sites matched', 'compute failed', 'no common cation site', 'compared',
              'all sites within 0.05 vu'):
        if stat[k]:
            print('  %4d  %s' % (stat[k], k))
    good = [r[2] for r in rows if r[2]]
    if good:
        tot = sum(g[1] for g in good); okk = sum(g[0] for g in good)
        print('\n  cation sites compared: %d; within 0.05 vu: %d (%.0f %%)' % (tot, okk, 100.0 * okk / tot))
        print('  worst deviation per structure: median %.3f vu, max %.3f vu'
              % (sorted(g[2] for g in good)[len(good) // 2], max(g[2] for g in good)))

if __name__ == '__main__':
    main(sys.argv[1:])
