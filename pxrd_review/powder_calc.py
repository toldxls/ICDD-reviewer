"""A powder pattern computed from a structure .cif — pure Python, no runtime dependency.

    python3 -m pxrd_review.powder_calc <structure.cif> [--lambda 1.5406|Cu|Mo|Co] [--dmin 1.0] [--ions] [--no-adp]

F(hkl) = Σ over every atom of the cell of occ · f(s) · T(hkl) · exp(2πi h·r), the atoms generated from the
asymmetric unit by the .cif's operators, f from the International Tables' Cromer–Mann coefficients
(`data/ff_it92.json.gz`, built dev-time from gemmi by tools/build_ff.py: neutral atoms, and the ions with
`--ions`), T the isotropic or anisotropic displacement factor (β' = R β Rᵀ for each equivalent). Reflections
of equal d and |F|² are one line with the multiplicity counted, so systematic absences and the Laue
group fall out of the sum itself. I = m·|F|²·Lp with the Debye–Scherrer Lorentz–polarisation factor
(1 + K cos²2θ)/(sin²θ cosθ), K = 1 without a monochromator (`pol` = cos²2θ_M for one), scaled to 100.
Conventions vary between programs (ions, ADPs, a monochromator term, absorption), so a comparison with
a printed Icalc is information, never a red line on its own.
"""
import os, sys, math, cmath, gzip, json, argparse, functools

from pxrd_review import bv_check as B

WAVELENGTHS = {'cu': 1.5406, 'cuka1': 1.5406, 'cuka': 1.5418, 'mo': 0.71073, 'moka': 0.71073, 'co': 1.7890, 'coka': 1.7890,
               'cr': 2.2897, 'fe': 1.9360, 'ag': 0.5609}


@functools.lru_cache(maxsize=1)
def _table():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'ff_it92.json.gz')
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        return json.load(f)['coefs']


def form_factor(element, ox=None, ions=False):
    """The Cromer–Mann coefficients for an element (or its ion when `ions` and the table has it), or None."""
    t = _table()
    if ions and ox:
        key = '%s%d%s' % (element, abs(int(ox)), '+' if ox > 0 else '-')
        if key in t:
            return t[key]
    return t.get(element)


def f_of(coef, s2):
    """f(s) for s² = (sin θ / λ)²."""
    return sum(a * math.exp(-b * s2) for a, b in zip(coef['a'], coef['b'])) + coef['c']


def wavelength(spec):
    if spec is None:
        return 1.5406
    try:
        return float(spec)
    except (TypeError, ValueError):
        key = str(spec).lower().replace('α', 'a').replace('kα', 'ka').replace(' ', '')
        if key in WAVELENGTHS:
            return WAVELENGTHS[key]
        raise ValueError('unknown wavelength %r' % spec)


def _inv3(m):
    a, b, c = m
    det = (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0]))
    inv = [[(b[1] * c[2] - b[2] * c[1]) / det, (a[2] * c[1] - a[1] * c[2]) / det, (a[1] * b[2] - a[2] * b[1]) / det],
           [(b[2] * c[0] - b[0] * c[2]) / det, (a[0] * c[2] - a[2] * c[0]) / det, (a[2] * b[0] - a[0] * b[2]) / det],
           [(b[0] * c[1] - b[1] * c[0]) / det, (a[1] * c[0] - a[0] * c[1]) / det, (a[0] * b[1] - a[1] * b[0]) / det]]
    return inv


def _aniso(st):
    """{label: [[U11, U12, U13], [U12, U22, U23], [U13, U23, U33]]} from the .cif's aniso loop (B converted)."""
    out = {}
    tags, rows = B._loop(st.block, '_atom_site_aniso_label')
    if not rows:
        return out
    g = lambda t: B._col(tags, rows, t, '')
    isb = '_atom_site_aniso_b_11' in tags
    pre = '_atom_site_aniso_b_' if isb else '_atom_site_aniso_u_'
    for lab, u11, u22, u33, u12, u13, u23 in zip(g('_atom_site_aniso_label'), g(pre + '11'), g(pre + '22'), g(pre + '33'), g(pre + '12'), g(pre + '13'), g(pre + '23')):
        v = [B._num(x) for x in (u11, u22, u33, u12, u13, u23)]
        if None in v:
            continue
        if isb:
            v = [x / (8 * math.pi ** 2) for x in v]
        out[lab] = [[v[0], v[3], v[4]], [v[3], v[1], v[5]], [v[4], v[5], v[2]]]
    return out


class Atom:
    __slots__ = ('frac', 'occ', 'coef', 'beta', 'biso')

    def __init__(self, frac, occ, coef, beta, biso):
        self.frac, self.occ, self.coef, self.beta, self.biso = frac, occ, coef, beta, biso


def atoms_of(st, ions=False, adp=True):
    """Every atom of the unit cell: the asymmetric unit expanded by the operators, with its occupancy,
    scattering coefficients and displacement factor (β = 2π² a*ᵢ a*ⱼ Uᵢⱼ, rotated with each equivalent)."""
    a, b, c, al, be, ga = st.cell
    Gs = _inv3(st.G)
    ast = [math.sqrt(Gs[i][i]) for i in range(3)]
    aniso = _aniso(st) if adp else {}
    out = []
    for site in st.sites:
        species = [(sp.element, sp.ox, sp.occ) for sp in site.species]
        U = None
        for lab in site.label.split('/'):
            if lab in aniso:
                U = aniso[lab]; break
        biso = 8 * math.pi ** 2 * site.uiso if (adp and site.uiso is not None and U is None) else 0.0
        beta0 = None
        if U is not None:
            beta0 = [[2 * math.pi ** 2 * ast[i] * ast[j] * U[i][j] for j in range(3)] for i in range(3)]
        seen = []
        for rot, tr in st.ops:
            p = [v % 1.0 for v in B._apply((rot, tr), site.frac)]
            p = [0.0 if abs(v - 1.0) < 1e-6 else v for v in p]
            if any(all(abs(p[m] - q[m]) < 1e-4 or abs(abs(p[m] - q[m]) - 1) < 1e-4 for m in range(3)) for q in seen):
                continue
            seen.append(p)
            beta = None
            if beta0 is not None:
                # β' = R β Rᵀ with R the operator's rotation in fractional coordinates
                RB = [[sum(rot[i][k] * beta0[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
                beta = [[sum(RB[i][k] * rot[j][k] for k in range(3)) for j in range(3)] for i in range(3)]
            for el, ox, occ in species:
                coef = form_factor(el, ox, ions)
                if coef is None or not occ:
                    continue
                out.append(Atom(p, occ, coef, beta, biso))
    return out, Gs


def pattern(cif, lam=1.5406, dmin=1.0, ions=False, adp=True, pol=1.0, structure=None):
    """[{'hkl', 'd', 'I', 'm', 'F2', 'tth'}] by d descending, I scaled to 100 — the lines of a
    powder pattern of the .cif's structure at wavelength `lam`, down to d = dmin."""
    st = structure or B.Structure(cif)
    atoms, Gs = atoms_of(st, ions, adp)
    rots = []
    for rot, _tr in st.ops:
        r = tuple(tuple(int(round(rot[i][j])) for j in range(3)) for i in range(3))
        if r not in rots:
            rots.append(r)
    a, b, c = st.cell[:3]
    hmax = [int(math.ceil(x / dmin)) + 1 for x in (a, b, c)]
    lines = {}
    for h in range(-hmax[0], hmax[0] + 1):
        for k in range(-hmax[1], hmax[1] + 1):
            for l in range(-hmax[2], hmax[2] + 1):
                if h == 0 and k == 0 and l == 0:
                    continue
                hv = (h, k, l)
                inv_d2 = sum(hv[i] * Gs[i][j] * hv[j] for i in range(3) for j in range(3))
                if inv_d2 <= 0:
                    continue
                d = 1.0 / math.sqrt(inv_d2)
                if d < dmin:
                    continue
                if lam / (2 * d) >= 1.0:
                    continue
                s2 = inv_d2 / 4.0
                F = 0j
                for at in atoms:
                    T = 1.0
                    if at.beta is not None:
                        T = math.exp(-sum(hv[i] * at.beta[i][j] * hv[j] for i in range(3) for j in range(3)))
                    elif at.biso:
                        T = math.exp(-at.biso * s2)
                    F += at.occ * f_of(at.coef, s2) * T * cmath.exp(2j * math.pi * (h * at.frac[0] + k * at.frac[1] + l * at.frac[2]))
                F2 = abs(F) ** 2
                if F2 < 1e-6:
                    continue
                key = _canon(rots, hv)                          # one line per equivalence class of the Laue group
                ln = lines.get(key)
                if ln is None:
                    lines[key] = [d, F2, 1, key]
                else:
                    ln[2] += 1
    out = []
    for d, F2, m, hv in lines.values():
        th = math.asin(lam / (2 * d))
        lp = (1 + pol * math.cos(2 * th) ** 2) / (math.sin(th) ** 2 * math.cos(th))
        out.append({'hkl': hv, 'd': d, 'I': m * F2 * lp, 'm': m, 'F2': F2, 'tth': math.degrees(2 * th)})
    mx = max((x['I'] for x in out), default=0) or 1.0
    for x in out:
        x['I'] = 100.0 * x['I'] / mx
    out.sort(key=lambda x: -x['d'])
    return out


def _canon(rots, hkl):
    """The representative of hkl's equivalence class: the largest tuple among h·R and −h·R."""
    best = None
    for rot in rots:
        r = tuple(sum(hkl[i] * rot[i][j] for i in range(3)) for j in range(3))
        for c in (r, tuple(-v for v in r)):
            if best is None or c > best:
                best = c
    return best


def equivalents(st, hkl):
    """The reflections symmetry-equivalent to hkl under the structure's Laue group (Friedel pairs included)."""
    out = set()
    for rot, _tr in st.ops:
        r = tuple(int(round(sum(hkl[i] * rot[i][j] for i in range(3)))) for j in range(3))     # h' = h R
        out.add(r); out.add(tuple(-v for v in r))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('cif')
    ap.add_argument('--lambda', dest='lam', default='Cu', help='Å, or Cu / Mo / Co / Cr / Fe / Ag (default Cu Kα1 1.5406)')
    ap.add_argument('--dmin', type=float, default=1.0)
    ap.add_argument('--ions', action='store_true', help='ionic scattering factors where the .cif gives a charge')
    ap.add_argument('--no-adp', action='store_true', help='ignore the displacement parameters')
    ap.add_argument('--pol', type=float, default=1.0, help='monochromator polarisation K = cos²2θ_M (default 1: none)')
    ap.add_argument('--min', type=float, default=0.5, help='list lines of I >= this (default 0.5)')
    a = ap.parse_args(argv)
    lam = wavelength(a.lam)
    pat = pattern(a.cif, lam, a.dmin, a.ions, not a.no_adp, a.pol)
    print('%s  λ = %.5f Å  d ≥ %.2f Å  %s ADPs  %s scattering factors' % (os.path.basename(a.cif), lam, a.dmin, 'with' if not a.no_adp else 'no', 'ionic' if a.ions else 'neutral'))
    print('  %7s %6s %8s  %s' % ('d (Å)', 'I', '2θ', 'h k l  (m)'))
    for x in pat:
        if x['I'] >= a.min:
            print('  %7.4f %6.1f %8.3f  %2d %2d %2d  (%d)' % (x['d'], x['I'], x['tth'], *x['hkl'], x['m']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
