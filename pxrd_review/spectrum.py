"""A Raman or infrared spectrum, from the instrument's file to a table of fitted bands
(`pxrd spectrum <file> [--sheet S] [--range LO HI] [--despike] [--baseline als|snip|rubber|none] [--fit auto|N] [--cif X] [--manuscript M]`).

    import       spectrum_formats.load — text, CSV, a workbook sheet, RRUFF, LabSpec text, JCAMP-DX, .spc, .spa, OPUS
    clean        despike (cosmic rays: a jump up and back within a few points, narrower than any band the resolution
                 allows), to_absorbance (an infrared transmittance spectrum)
    baseline     anchor points, SNIP, asymmetric least squares, the rubber band (the lower convex hull)
    find         bands from the smoothed second derivative, kept by prominence over the noise
    fit          Gaussian, Lorentzian or pseudo-Voigt components by Levenberg–Marquardt, with bounds, shared widths,
                 a constant or sloping local baseline, standard uncertainties and the correlations between parameters
    judge        how many components the data support (BIC over 1 … n), and what a fit should not be trusted for:
                 components closer than the resolution or than their own widths, a width under the resolution, an
                 uncertainty as large as a separation, parameters correlated above 0.95, structure left in the residual
    set beside   the structure's own distances turned into expected positions (spectro.bc_nu1_inv, spectro.lib_nu), the
                 bands a manuscript states, and the windows published descriptions place each band in
Everything is pure Python (no numpy at run time): a fit is done region by region, which is also how a spectrum is read.
The numbers the window shows and the table `export` writes come from here, so the two cannot disagree.
"""
import os, re, sys, json, math, argparse, functools
from collections import namedtuple

from pxrd_review import spectrum_formats as F
from pxrd_review.lints import CH_WINDOW

LN2 = math.log(2.0)
G_AREA = math.sqrt(math.pi / (4.0 * LN2))       # area of a unit-height, unit-FWHM Gaussian
L_AREA = math.pi / 2.0                           # … of a Lorentzian
SHAPES = ('pvoigt', 'gauss', 'lorentz')

# ----------------------------------------------------------------------------- small numerics


def _median(v):
    s = sorted(v); n = len(s)
    return 0.0 if not n else s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def noise(y):
    """The standard deviation of the point-to-point noise, from the second differences (which a smooth band and a sloping
    baseline do not enter): 1.4826 MAD / √6."""
    if len(y) < 5:
        return 0.0
    d2 = [y[i - 1] - 2.0 * y[i] + y[i + 1] for i in range(1, len(y) - 1)]
    med = _median(d2)
    return 1.4826 * _median([abs(v - med) for v in d2]) / math.sqrt(6.0)


def crop(x, y, lo=None, hi=None):
    """The points with lo <= x <= hi."""
    pts = [(a, b) for a, b in zip(x, y) if (lo is None or a >= lo) and (hi is None or a <= hi)]
    return [p[0] for p in pts], [p[1] for p in pts]


def _interp(x, xs, ys):
    """Linear interpolation of (xs, ys) at each of x (xs ascending); held flat outside."""
    out = []; j = 0; n = len(xs)
    for v in x:
        while j < n - 2 and xs[j + 1] < v:
            j += 1
        if v <= xs[0]:
            out.append(ys[0])
        elif v >= xs[-1]:
            out.append(ys[-1])
        else:
            a, b = xs[j], xs[j + 1]
            out.append(ys[j] + (ys[j + 1] - ys[j]) * (v - a) / (b - a) if b > a else ys[j])
    return out


def _solve(A, b):
    """x of A x = b for a small dense symmetric positive-definite A, by Cholesky; None when it is not positive definite."""
    n = len(b)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = A[i][j] - sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                if s <= 0.0:
                    return None
                L[i][i] = math.sqrt(s)
            else:
                L[i][j] = s / L[j][j]
    z = [0.0] * n
    for i in range(n):
        z[i] = (b[i] - sum(L[i][k] * z[k] for k in range(i))) / L[i][i]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (z[i] - sum(L[k][i] * x[k] for k in range(i + 1, n))) / L[i][i]
    return x


def _inverse(A):
    """The inverse of a small symmetric positive-definite matrix, column by column; None when it has none."""
    n = len(A); cols = []
    for k in range(n):
        e = [1.0 if i == k else 0.0 for i in range(n)]
        c = _solve(A, e)
        if c is None:
            return None
        cols.append(c)
    return [[cols[j][i] for j in range(n)] for i in range(n)]


@functools.lru_cache(maxsize=256)
def _sg_weights(window, order, deriv, at=0):
    """The weights of a Savitzky–Golay filter on the `window` points round a point: the deriv-th derivative (per point
    spacing) of the least-squares polynomial of `order`, evaluated `at` points from the window's centre."""
    h = window // 2
    A = [[sum(float(t) ** (i + j) for t in range(-h, h + 1)) for j in range(order + 1)] for i in range(order + 1)]
    inv = _inverse(A)
    w = []
    for t in range(-h, h + 1):
        b = [float(t) ** i for i in range(order + 1)]
        c = [sum(inv[i][j] * b[j] for j in range(order + 1)) for i in range(order + 1)]     # the fitted coefficients' weights on y(t)
        w.append(sum(c[i] * math.factorial(i) / math.factorial(i - deriv) * float(at) ** (i - deriv) for i in range(deriv, order + 1)))
    return tuple(w)


def savgol_noise(window, order=2, deriv=0, dx=1.0):
    """What a Savitzky–Golay filter makes of unit white noise: the standard deviation of its output."""
    window = max(order + 1 + (order + 1) % 2, window | 1)
    return math.sqrt(sum(c * c for c in _sg_weights(window, order, deriv))) / dx ** deriv


def savgol(y, window=9, order=2, deriv=0, dx=1.0):
    """Savitzky–Golay smoothing (or the deriv-th derivative): a polynomial of `order` fitted to each `window` of points.
    The ends are held by fitting the first and last full window and evaluating it out to the edge."""
    n = len(y); window = max(order + 1 + (order + 1) % 2, window | 1)
    if n < window:
        return list(y) if deriv == 0 else [0.0] * n
    h = window // 2
    scale = 1.0 / dx ** deriv
    coeffs = lambda at: [c * scale for c in _sg_weights(window, order, deriv, at)]
    mid = coeffs(0)
    out = [0.0] * n
    for i in range(h, n - h):
        out[i] = sum(mid[k] * y[i - h + k] for k in range(window))
    for i in range(h):
        w = coeffs(i - h); out[i] = sum(w[k] * y[k] for k in range(window))
        w = coeffs(h - i); out[n - 1 - i] = sum(w[k] * y[n - window + k] for k in range(window))
    return out


# ----------------------------------------------------------------------------- cleaning

def to_absorbance(y):
    """Absorbance from transmittance, in percent when the values run to 100 and as a fraction when they run to 1."""
    top = sorted(y)[-max(1, len(y) // 50)]
    scale = 100.0 if top > 1.5 else 1.0
    floor = scale * 1e-4
    return [-math.log10(max(v, floor) / scale) for v in y]


def despike(x, y, threshold=8.0, max_width=3, resolution=None):
    """Cosmic-ray events removed -> (cleaned y, [(first index, last index)] of what was replaced).

    A cosmic ray is a jump UP and a jump back DOWN within a few points — narrower than anything the spectrometer's
    resolution lets a real band be. The jumps are found on the first differences by their modified z-score (0.6745 ×
    deviation / MAD, after Whitaker & Hayes 2018), and a run between an up-jump and the next down-jump is replaced by a
    straight line only when it is at most `max_width` points wide (or `resolution` cm⁻¹, when the resolution is given)
    and stands above both neighbours. A sharp real band is wider than that and is left alone."""
    n = len(y)
    if n < 8:
        return list(y), []
    if resolution:
        dx = abs(x[-1] - x[0]) / (n - 1)
        max_width = max(1, int(resolution / dx)) if dx > 0 else max_width
    d = [y[i + 1] - y[i] for i in range(n - 1)]
    med = _median(d); mad = _median([abs(v - med) for v in d]) or 1e-12
    z = [0.6745 * (v - med) / mad for v in d]
    out = list(y); spikes = []
    i = 0
    while i < n - 1:
        if z[i] > threshold:                                    # a jump up between i and i + 1
            j = i + 1
            while j < n - 1 and j - i <= max_width and not z[j] < -threshold:
                j += 1
            if j < n - 1 and z[j] < -threshold and j - i <= max_width:
                a, b = i, j + 1                                  # good points either side of the event i+1 … j
                while a > 0 and z[a - 1] > threshold:            # a two-step rise
                    a -= 1
                while b < n - 1 and z[b] < -threshold:           # a two-step fall
                    b += 1
                if b - a - 1 <= max_width + 2 and min(y[a + 1: b]) > max(y[a], y[b]):
                    for k in range(a + 1, b):
                        out[k] = y[a] + (y[b] - y[a]) * (k - a) / (b - a)
                    spikes.append((a + 1, b - 1)); i = b; continue
        i += 1
    return out, spikes


# ----------------------------------------------------------------------------- baselines

def baseline_anchors(x, y, anchors, half=3):
    """A baseline through anchor points chosen on the x axis: at each, the median of the points around it; straight
    lines between, flat beyond the first and last."""
    if not anchors:
        return [0.0] * len(y)
    pts = []
    for a in sorted(anchors):
        i = min(range(len(x)), key=lambda k: abs(x[k] - a))
        pts.append((x[i], _median(y[max(0, i - half): i + half + 1])))
    return _interp(x, [p[0] for p in pts], [p[1] for p in pts])


def baseline_rubberband(x, y):
    """The rubber band: the lower convex hull of the spectrum, stretched under it from end to end."""
    hull = []
    for p in zip(x, y):
        while len(hull) >= 2 and (hull[-1][0] - hull[-2][0]) * (p[1] - hull[-2][1]) - (hull[-1][1] - hull[-2][1]) * (p[0] - hull[-2][0]) <= 0:
            hull.pop()
        hull.append(p)
    return _interp(x, [p[0] for p in hull], [p[1] for p in hull])


def baseline_snip(y, half_width=40):
    """SNIP (Ryan et al. 1988; Morháč et al. 1997): each point is clipped to the mean of its neighbours p points either
    side, for p from `half_width` down to 1 — what is left is what no band-sized window could lift. `half_width`
    (points) should exceed the half-width of the FOOT of the broadest band to be kept. Done on the intensities as they
    are: the logarithmic scaling the method was given for counting spectra that span decades bends a straight sloping
    background into a sagging one."""
    n = len(y)
    v = list(y)
    for p in range(min(half_width, (n - 1) // 2), 0, -1):
        w = list(v)
        for i in range(p, n - p):
            m = 0.5 * (v[i - p] + v[i + p])
            if m < v[i]:
                w[i] = m
        v = w
    return v


def _solve_penta(d0, d1, d2, rhs):
    """x of a symmetric positive-definite pentadiagonal system (diagonal d0, first off-diagonal d1, second d2) by a
    banded LDLᵀ factorisation — linear in the number of points."""
    n = len(d0)
    D = [0.0] * n; l1 = [0.0] * n; l2 = [0.0] * n            # l1[i] = L[i+1][i], l2[i] = L[i+2][i]
    for i in range(n):
        D[i] = d0[i] - (l1[i - 1] ** 2 * D[i - 1] if i >= 1 else 0.0) - (l2[i - 2] ** 2 * D[i - 2] if i >= 2 else 0.0)
        if i + 1 < n:
            l1[i] = (d1[i] - (l1[i - 1] * l2[i - 1] * D[i - 1] if i >= 1 else 0.0)) / D[i]
        if i + 2 < n:
            l2[i] = d2[i] / D[i]
    z = [0.0] * n
    for i in range(n):
        z[i] = rhs[i] - (l1[i - 1] * z[i - 1] if i >= 1 else 0.0) - (l2[i - 2] * z[i - 2] if i >= 2 else 0.0)
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = z[i] / D[i] - (l1[i] * x[i + 1] if i + 1 < n else 0.0) - (l2[i] * x[i + 2] if i + 2 < n else 0.0)
    return x


def baseline_als(y, lam=1e5, p=0.01, iterations=10):
    """Asymmetric least squares (Eilers & Boelens 2005): the smooth curve z minimising Σ w (y − z)² + λ Σ (Δ²z)², with
    w = p where the spectrum lies above it and 1 − p where it lies below, re-weighted `iterations` times. λ sets the
    stiffness (1e4 follows a curved fluorescence background, 1e7 is nearly a straight line), p how far under the bands
    it stays."""
    n = len(y)
    if n < 5:
        return list(y)
    # DᵀD of the second-difference operator: its three distinct bands
    dd0 = [6.0] * n; dd1 = [-4.0] * (n - 1); dd2 = [1.0] * (n - 2)
    dd0[0] = dd0[-1] = 1.0; dd0[1] = dd0[-2] = 5.0; dd1[0] = dd1[-1] = -2.0
    w = [1.0] * n; z = list(y)
    for _ in range(iterations):
        z = _solve_penta([w[i] + lam * dd0[i] for i in range(n)], [lam * v for v in dd1], [lam * v for v in dd2], [w[i] * y[i] for i in range(n)])
        w2 = [p if y[i] > z[i] else 1.0 - p for i in range(n)]
        if w2 == w:
            break
        w = w2
    return z


BASELINES = ('none', 'als', 'snip', 'rubber', 'anchors')


def baseline(x, y, kind='als', anchors=None, lam=1e7, p=0.01, width=150.0):
    """The baseline of one of the kinds; 'none' is zero.
    `lam` is the stiffness of the asymmetric-least-squares baseline AS FOR A SPACING OF 1 cm⁻¹: the penalty is on second
    differences, so the same curve needs λ/dx⁴ at a spacing dx — scaled here, so that one value means one stiffness on
    any spectrum (about 2π·λ^¼ cm⁻¹ is the width of the narrowest feature the baseline can still follow: 350 cm⁻¹ at 1e7).
    `width` (cm⁻¹) is SNIP's clipping half-width: wider than the foot of the broadest band to be kept."""
    dx = abs(x[-1] - x[0]) / max(1, len(x) - 1) if len(x) > 1 else 1.0
    if kind == 'als':
        return baseline_als(y, lam / dx ** 4 if dx > 0 else lam, p)
    if kind == 'snip':
        return baseline_snip(y, max(2, int(round(width / dx))) if dx > 0 else 40)
    if kind == 'rubber':
        return baseline_rubberband(x, y)
    if kind == 'anchors':
        return baseline_anchors(x, y, anchors or [])
    if kind in ('none', '', None):
        return [0.0] * len(y)
    raise ValueError('no baseline of the kind %r (one of %s)' % (kind, ', '.join(BASELINES)))


# ----------------------------------------------------------------------------- finding bands

SCALES = (6.0, 12.0, 25.0, 50.0, 100.0, 200.0)      # cm⁻¹: the smoothing widths a band is looked for at
RIPPLE = 0.6                                         # shoulders this deep on BOTH sides of a dip: a ripple, not a band
MIN_SHARE = 0.03                                     # a band worth a component carries this share of the curve where it stands


def find_bands(x, y, sigma=None, ref=None, min_snr=4.0, min_share=MIN_SHARE, scales=SCALES):
    """[{'pos', 'height', 'fwhm', 'snr', 'scale'}] — the bands of a baseline-free spectrum, largest area first.

    A band is a minimum of the second derivative — which separates a shoulder from its neighbour where the curve itself
    has no maximum — and a band 100 cm⁻¹ wide has a second derivative ten thousand times weaker than one 10 cm⁻¹ wide of
    the same height. So the derivative is taken at a LADDER of smoothing widths, each with the noise that width lets
    through (savgol_noise): a narrow lattice mode is found at 6 cm⁻¹, the components of an O–H envelope at 25–100.
    Finest first: a wider scale adds a band only where no finer one already stands inside its dip, so an envelope comes
    apart into its components rather than being taken whole.
    Kept when the dip is `min_snr` deviations deep and the band carries `min_share` of the curve where it stands — and
    never less than half that share of the tallest thing in the region (`ref`, the smoothed spectrum itself by default;
    for a residual, the spectrum it is the residual of) — and when its dip is not one swing of a ripple (RIPPLE): the
    lines of atmospheric water on an infrared O–H band are significant, and are no component.
    Width from the dip's zero crossings (1.18 × their distance for a Gaussian), less the smoothing's own widening; height
    from the dip's depth, never above the curve."""
    n = len(y)
    if n < 15:
        return []
    span = abs(x[-1] - x[0]); dx = span / (n - 1)
    sigma = sigma or noise(y) or 1e-12
    rtop = max(max(ref) if ref is not None else max(y), 1e-300)
    kept = []; done = set()
    for s in scales:
        w = max(5, int(round(s / dx)) | 1)
        if w in done or w > max(5, n // 3):
            continue
        done.add(w)
        d2 = savgol(y, w, 3, deriv=2, dx=dx)
        sd2 = sigma * savgol_noise(w, 3, 2, dx)
        sm = savgol(y, w, 2)
        rf = ref if ref is not None else sm
        for i in range(2, n - 2):
            if not (d2[i] < d2[i - 1] and d2[i] <= d2[i + 1] and d2[i] < -min_snr * sd2):
                continue
            a = i
            while a > 0 and d2[a] < 0:
                a -= 1
            b = i
            while b < n - 1 and d2[b] < 0:
                b += 1
            # a band's dip has shallow shoulders (0.45 of its depth for a Gaussian); a ripple's are as deep as the dip
            la = a; lmax = 0.0
            while la > 0 and d2[la] >= 0:
                lmax = max(lmax, d2[la]); la -= 1
            rb = b; rmax = 0.0
            while rb < n - 1 and d2[rb] >= 0:
                rmax = max(rmax, d2[rb]); rb += 1
            fw = 1.2 * (x[b] - x[a])
            fw = math.sqrt(max(fw * fw - (0.6 * w * dx) ** 2, (2 * dx) ** 2))
            h = min(-d2[i] * fw * fw / (8.0 * LN2), max(sm[i], 0.0))
            floor = min_share * max(rf[i], 0.5 * rtop)
            if h < 3.0 * sigma or h < floor:
                continue
            if h < 3.0 * floor and min(lmax, rmax) >= RIPPLE * -d2[i]:
                continue                                         # small AND one swing of a ripple; the components of an envelope, close-set, have deep shoulders too — and are not small
            if any(x[a] <= q['pos'] <= x[b] for q in kept):
                continue
            kept.append({'pos': x[i], 'height': h, 'fwhm': min(fw, 0.5 * span), 'snr': -d2[i] / sd2, 'scale': w * dx})
    kept.sort(key=lambda q: -q['height'] * q['fwhm'])
    return kept


def find_peaks(x, y, min_snr=4.0, min_sep=None, window=None):
    """The bands of a spectrum, strongest first (find_bands; `window` — one smoothing width in points — narrows the
    ladder to that scale)."""
    n = len(y)
    if n < 15:
        return []
    dx = abs(x[-1] - x[0]) / (n - 1)
    out = find_bands(x, y, min_snr=min_snr, scales=(window * dx,) if window else SCALES)
    out.sort(key=lambda p: -p['height'])
    if min_sep is None:
        return out
    kept = []
    for pk in out:
        if all(abs(pk['pos'] - q['pos']) >= min_sep for q in kept):
            kept.append(pk)
    return kept


def second_derivative(x, y, width=12.0):
    """−d²y/dx² smoothed over `width` cm⁻¹ (bands point up, as in the spectrum) — the curve a hidden component shows in."""
    n = len(y)
    if n < 7:
        return [0.0] * n
    dx = abs(x[-1] - x[0]) / (n - 1)
    w = min(max(5, int(round(width / dx)) | 1), (n - 1) | 1 if n % 2 else n - 1)
    return [-v for v in savgol(y, w, 3, deriv=2, dx=dx)]


# ----------------------------------------------------------------------------- the model

def profile(shape, x, pos, height, fwhm, eta=0.5):
    """One band at x: 'gauss', 'lorentz', or the pseudo-Voigt η·Lorentzian + (1 − η)·Gaussian of one width."""
    t = (x - pos) / fwhm
    if shape == 'gauss':
        return height * math.exp(-4.0 * LN2 * t * t) if abs(t) < 6.0 else 0.0
    if shape == 'lorentz':
        return height / (1.0 + 4.0 * t * t)
    g = math.exp(-4.0 * LN2 * t * t) if abs(t) < 6.0 else 0.0
    return height * (eta / (1.0 + 4.0 * t * t) + (1.0 - eta) * g)


def area(shape, height, fwhm, eta=0.5):
    if shape == 'gauss':
        return height * fwhm * G_AREA
    if shape == 'lorentz':
        return height * fwhm * L_AREA
    return height * fwhm * (eta * L_AREA + (1.0 - eta) * G_AREA)


def model(x, comps, base=(0.0, 0.0), x0=0.0):
    """The sum of the components (+ the local baseline base[0] + base[1]·(x − x0)) at each x."""
    b0, b1 = base
    out = [b0 + b1 * (v - x0) for v in x] if (b0 or b1) else [0.0] * len(x)
    k4 = 4.0 * LN2; exp = math.exp
    for c in comps:
        p0, h, w, shape = c['pos'], c['height'], c['fwhm'], c['shape']
        if not h:
            continue
        if shape == 'lorentz':
            for i, v in enumerate(x):
                t = (v - p0) / w
                out[i] += h / (1.0 + 4.0 * t * t)
        elif shape == 'gauss':
            for i, v in enumerate(x):
                t = (v - p0) / w
                if -6.0 < t < 6.0:
                    out[i] += h * exp(-k4 * t * t)
        else:
            eta = c.get('eta', 0.5); hl = h * eta; hg = h * (1.0 - eta)
            for i, v in enumerate(x):
                t = (v - p0) / w; t2 = t * t
                out[i] += hl / (1.0 + 4.0 * t2) + (hg * exp(-k4 * t2) if t2 < 36.0 else 0.0)
    return out


Fit = namedtuple('Fit', 'comps base x0 lo hi n k rss chi2 r2 aic bic sigma iterations converged cov names warnings')
#   comps: [{'shape', 'pos', 'height', 'fwhm', 'eta', 'area', 'esd': {'pos', 'height', 'fwhm', 'eta'}, …}] by position;
#   base: (constant, slope) of the local baseline about x0;  n points, k free parameters;  sigma: the noise used as the
#   unit of χ² (so chi2 = RSS / ((n − k) σ²): about 1 when the model leaves only noise);  cov / names: the covariance
#   matrix of the free parameters and their names ('pos1', 'fwhm2', 'b0' …);  warnings: [str]


def linear_heights(xs, ys, comps, local_baseline='const'):
    """The heights (never negative) that fit best with the positions, widths and shapes as they are — the start a fit of
    overlapping bands needs, since a height guessed band by band counts the neighbours' share twice. Returns the
    components with their heights set; the local baseline is solved with them and dropped."""
    comps = [dict(c) for c in comps]
    if not comps:
        return comps
    x0 = 0.5 * (xs[0] + xs[-1])
    nb = {'none': 0, 'const': 1, 'linear': 2}.get(local_baseline, 1)
    cols = [[profile(c.get('shape', 'pvoigt'), v, c['pos'], 1.0, c['fwhm'], c.get('eta', 0.5)) for v in xs] for c in comps]
    if nb >= 1:
        cols.append([1.0] * len(xs))
    if nb == 2:
        cols.append([v - x0 for v in xs])
    active = list(range(len(comps)))
    for _ in range(len(comps) + 1):
        use = active + list(range(len(comps), len(cols)))
        A = [[sum(p * q for p, q in zip(cols[a], cols[b])) for b in use] for a in use]
        for k in range(len(use)):
            A[k][k] = A[k][k] * (1.0 + 1e-9) + 1e-12
        sol = _solve(A, [sum(p * q for p, q in zip(cols[a], ys)) for a in use])
        if sol is None:
            return comps
        neg = [a for a, v in zip(active, sol) if v < 0]
        if not neg:
            for c in comps:
                c['height'] = 0.0
            for a, v in zip(active, sol):
                comps[a]['height'] = v
            return comps
        active = [a for a in active if a not in neg]             # a band the data want below zero is left at zero
    return comps


def fit(x, y, comps, lo=None, hi=None, local_baseline='const', share_width=False, fix=(), max_iter=120, sigma=None, resolution=None,
        max_fwhm=None, min_fwhm=None, share_eta=False, tol=1e-6):
    """Least-squares fit of the components to the spectrum between lo and hi (Levenberg–Marquardt, analytic derivatives).

    comps           [{'shape': 'pvoigt'|'gauss'|'lorentz', 'pos', 'height', 'fwhm', 'eta'?, 'fix': ['pos', …]?}] — the start
    local_baseline  'none' | 'const' | 'linear': what the region's own baseline may still be after the subtraction
    share_width     every component takes one common width (and one common η) — for a multiplet of one kind
    share_eta       every pseudo-Voigt component takes one common η (the widths stay their own): thirteen overlapping
                    bands do not fix thirteen shapes
    max_iter        0 = no fitting at all: the model, its statistics and uncertainties AS THE COMPONENTS STAND (what an
                    export writes — the fit on the screen, not another one)
    fix             parameter kinds fixed for every component ('eta', 'fwhm', 'pos')
    max_fwhm, min_fwhm   limits on every width (a component's own 'wmax' / 'wmin' override them): what keeps a band of
                    an envelope from widening into the envelope
    Bounds: a position stays inside the region, a height at or above zero, a width between two sampling steps (or
    min_fwhm) and the region's width (or max_fwhm), η between 0 and 1.
    -> Fit. Raises ValueError when there is nothing to fit (no component, or fewer points than parameters)."""
    xs, ys = crop(x, y, lo, hi)
    n = len(xs)
    if not comps:
        raise ValueError('no component to fit')
    if n < 8:
        raise ValueError('fewer than eight points between %s and %s' % (lo, hi))
    lo, hi = xs[0], xs[-1]; x0 = 0.5 * (lo + hi); span = hi - lo
    dx = span / (n - 1)
    comps = [dict(c) for c in comps]
    for c in comps:
        c.setdefault('shape', 'pvoigt'); c.setdefault('eta', 0.5)
        if c['shape'] not in SHAPES:
            raise ValueError('no band shape %r (one of %s)' % (c['shape'], ', '.join(SHAPES)))
        c['_wlo'] = max(2 * dx, float(c.get('wmin') or min_fwhm or 0.0)); c['_whi'] = max(c['_wlo'], min(span, float(c.get('wmax') or max_fwhm or span)))
        c['fwhm'] = min(max(float(c['fwhm']), c['_wlo']), c['_whi']); c['height'] = max(float(c['height']), 0.0); c['pos'] = min(max(float(c['pos']), lo), hi)
    sig = sigma if sigma else (noise(ys) or 1.0)
    # --- the free parameters: (name, getter, setter, lower, upper)
    free = []
    def add(name, get, put, a, b):
        free.append((name, get, put, a, b))
    fixed_all = set(fix)
    one_eta = bool(share_width or share_eta)
    if one_eta:                                                 # one shape for all: they start from one value
        pv = [c for c in comps if c['shape'] == 'pvoigt']
        for c in pv:
            c['eta'] = pv[0]['eta']
    for k, c in enumerate(comps):
        cf = set(c.get('fix') or ()) | fixed_all
        if 'pos' not in cf:
            add('pos%d' % (k + 1), (lambda c=c: c['pos']), (lambda v, c=c: c.__setitem__('pos', v)), lo, hi)
        if 'height' not in cf:
            add('height%d' % (k + 1), (lambda c=c: c['height']), (lambda v, c=c: c.__setitem__('height', v)), 0.0, float('inf'))
        if 'fwhm' not in cf and not (share_width and k > 0):
            if share_width:
                add('fwhm', (lambda: comps[0]['fwhm']), (lambda v: [q.__setitem__('fwhm', v) for q in comps]), max(q['_wlo'] for q in comps), min(q['_whi'] for q in comps))
            else:
                add('fwhm%d' % (k + 1), (lambda c=c: c['fwhm']), (lambda v, c=c: c.__setitem__('fwhm', v)), c['_wlo'], c['_whi'])
        if c['shape'] == 'pvoigt' and 'eta' not in cf and not (one_eta and any(q['shape'] == 'pvoigt' for q in comps[:k])):
            if one_eta:
                add('eta', (lambda c=c: c['eta']), (lambda v: [q.__setitem__('eta', v) for q in comps if q['shape'] == 'pvoigt']), 0.0, 1.0)
            else:
                add('eta%d' % (k + 1), (lambda c=c: c['eta']), (lambda v, c=c: c.__setitem__('eta', v)), 0.0, 1.0)
    base = [0.0, 0.0]
    if local_baseline in ('const', 'linear'):
        add('b0', (lambda: base[0]), (lambda v: base.__setitem__(0, v)), -float('inf'), float('inf'))
    if local_baseline == 'linear':
        add('b1', (lambda: base[1]), (lambda v: base.__setitem__(1, v)), -float('inf'), float('inf'))
    k_free = len(free)
    if k_free == 0:
        raise ValueError('every parameter is fixed')
    if n <= k_free:
        raise ValueError('%d points for %d parameters' % (n, k_free))
    names = [f[0] for f in free]

    def residuals():
        return [b - m for b, m in zip(ys, model(xs, comps, base, x0))]

    def jacobian():
        """Per free parameter, {point index: ∂model/∂p} — only where the band's derivative is not negligible."""
        cols = {nm: {} for nm in names}
        for k, c in enumerate(comps):
            p0, h, w, eta, shape = c['pos'], c['height'], c['fwhm'], c['eta'], c['shape']
            reach = (4.0 if shape == 'gauss' else 30.0) * w
            a = 0
            while a < n and xs[a] < p0 - reach:
                a += 1
            for i in range(a, n):
                v = xs[i]
                if v > p0 + reach:
                    break
                t = (v - p0) / w; t2 = t * t
                g = math.exp(-4.0 * LN2 * t2) if shape != 'lorentz' and t2 < 36.0 else 0.0
                q = 1.0 / (1.0 + 4.0 * t2) if shape != 'gauss' else 0.0
                if shape == 'gauss':
                    f = g; dfdt = -8.0 * LN2 * t * g
                elif shape == 'lorentz':
                    f = q; dfdt = -8.0 * t * q * q
                else:
                    f = eta * q + (1.0 - eta) * g; dfdt = eta * (-8.0 * t * q * q) + (1.0 - eta) * (-8.0 * LN2 * t * g)
                    key = 'eta' if one_eta else 'eta%d' % (k + 1)
                    if key in cols:
                        cols[key][i] = cols[key].get(i, 0.0) + h * (q - g)
                key = 'pos%d' % (k + 1)
                if key in cols:
                    cols[key][i] = h * dfdt * (-1.0 / w)
                key = 'height%d' % (k + 1)
                if key in cols:
                    cols[key][i] = f
                key = 'fwhm' if share_width else 'fwhm%d' % (k + 1)
                if key in cols:
                    cols[key][i] = cols[key].get(i, 0.0) + h * dfdt * (-t / w)
        if 'b0' in cols:
            cols['b0'] = {i: 1.0 for i in range(n)}
        if 'b1' in cols:
            cols['b1'] = {i: xs[i] - x0 for i in range(n)}
        return [cols[nm] for nm in names]

    def normal(J, r):
        A = [[0.0] * k_free for _ in range(k_free)]; g = [0.0] * k_free
        for a in range(k_free):
            Ja = J[a]
            g[a] = sum(v * r[i] for i, v in Ja.items())
            for b in range(a, k_free):
                Jb = J[b]
                small, big = (Ja, Jb) if len(Ja) <= len(Jb) else (Jb, Ja)
                s = 0.0
                for i, v in small.items():
                    w_ = big.get(i)
                    if w_ is not None:
                        s += v * w_
                A[a][b] = A[b][a] = s
        return A, g

    r = residuals(); rss = sum(v * v for v in r)
    lam = 1e-3; converged = max_iter == 0; it = 0
    for it in range(1, max_iter + 1):
        A, g = normal(jacobian(), r)
        stepped = False
        old = [f[1]() for f in free]
        # a parameter resting on a bound that the gradient pushes further out sits this step out: clamping it after the
        # solve would spoil the step of every parameter it is coupled to
        act = [a for a in range(k_free) if not ((old[a] <= free[a][3] and g[a] < 0) or (old[a] >= free[a][4] and g[a] > 0))]
        if not act:
            converged = True
            break
        for _try in range(12):
            M = [[A[a][b] * ((1.0 + lam) if a == b else 1.0) + (1e-12 if a == b else 0.0) for b in act] for a in act]
            d_act = _solve(M, [g[a] for a in act])
            if d_act is None:
                lam *= 10.0; continue
            delta = [0.0] * k_free
            for a, d_ in zip(act, d_act):
                delta[a] = d_
            for (nm, get, put, a_, b_), d_, o in zip(free, delta, old):
                put(min(max(o + d_, a_), b_))
            r2 = residuals(); rss2 = sum(v * v for v in r2)
            if rss2 < rss:
                rel = (rss - rss2) / rss if rss else 0.0
                r, rss = r2, rss2; lam = max(lam / 10.0, 1e-9); stepped = True
                if rel < tol:
                    converged = True
                break
            for (nm, get, put, a_, b_), o in zip(free, old):
                put(o)
            lam *= 10.0
        if not stepped or converged:
            converged = converged or not stepped
            break
    # --- uncertainties from the curvature at the minimum
    A, _g = normal(jacobian(), r)
    dof = max(1, n - k_free)
    s2 = rss / dof
    inv = _inverse([[A[a][b] + (1e-12 if a == b else 0.0) for b in range(k_free)] for a in range(k_free)])
    cov = [[inv[a][b] * s2 for b in range(k_free)] for a in range(k_free)] if inv else None
    esd = {nm: (math.sqrt(cov[a][a]) if cov and cov[a][a] > 0 else None) for a, nm in enumerate(names)}
    mean = sum(ys) / n; tss = sum((v - mean) ** 2 for v in ys) or 1e-300
    for k, c in enumerate(comps):
        c['area'] = area(c['shape'], c['height'], c['fwhm'], c['eta'])
        c['esd'] = {'pos': esd.get('pos%d' % (k + 1)), 'height': esd.get('height%d' % (k + 1)),
                    'fwhm': esd.get('fwhm' if share_width else 'fwhm%d' % (k + 1)), 'eta': esd.get('eta' if one_eta else 'eta%d' % (k + 1))}
        c['index'] = k + 1
        c['at_limit'] = 'max' if c['fwhm'] >= c['_whi'] * 0.999 and c['_whi'] < span else 'min' if c['fwhm'] <= c['_wlo'] * 1.001 and c['_wlo'] > 2 * dx else ''
        del c['_wlo'], c['_whi']
    out = Fit(sorted(comps, key=lambda c: c['pos']), (base[0], base[1]), x0, lo, hi, n, k_free, rss, rss / (dof * sig * sig), 1.0 - rss / tss,
              n * math.log(max(rss, 1e-300) / n) + 2.0 * k_free, n * math.log(max(rss, 1e-300) / n) + k_free * math.log(n), sig, it, converged, cov, names, [])
    out.warnings.extend(diagnose(out, xs, r, resolution))
    return out


def _runs_z(r):
    """The Wald–Wolfowitz runs statistic of the residuals' signs: strongly negative when they come in long runs — a band
    the model does not have, or a shape it cannot take."""
    signs = [v > 0 for v in r if v != 0]
    n1 = sum(signs); n2 = len(signs) - n1
    if n1 < 8 or n2 < 8:
        return 0.0
    runs = 1 + sum(1 for a, b in zip(signs, signs[1:]) if a != b)
    mu = 2.0 * n1 * n2 / (n1 + n2) + 1.0
    var = 2.0 * n1 * n2 * (2.0 * n1 * n2 - n1 - n2) / ((n1 + n2) ** 2 * (n1 + n2 - 1.0))
    return (runs - mu) / math.sqrt(var) if var > 0 else 0.0


CORR_WARN = 0.95
RUNS_WARN = -6.0


def diagnose(f, xs, residual, resolution=None):
    """What a fit should not be trusted for -> [str]."""
    out = []
    dx = (f.hi - f.lo) / max(1, f.n - 1)
    if not f.converged:
        out.append('the fit stopped at its iteration limit without converging')
    cs = f.comps
    for a, b in zip(cs, cs[1:]):
        sep = b['pos'] - a['pos']; wmean = 0.5 * (a['fwhm'] + b['fwhm'])
        if resolution and sep < resolution:
            out.append('the bands at %.1f and %.1f cm⁻¹ are %.1f apart, closer than the resolution (%.1f)' % (a['pos'], b['pos'], sep, resolution))
        elif sep < 0.5 * wmean:
            out.append('the bands at %.1f and %.1f cm⁻¹ are %.1f apart, under half their width (%.1f): one band with another shape fits as well' % (a['pos'], b['pos'], sep, wmean))
        ea, eb = a['esd'].get('pos'), b['esd'].get('pos')
        if ea and eb and math.hypot(ea, eb) > 0.5 * sep:
            out.append('the positions %.1f and %.1f cm⁻¹ are uncertain by ±%.1f and ±%.1f, as much as they are apart' % (a['pos'], b['pos'], ea, eb))
    for c in cs:
        if resolution and c['fwhm'] < resolution:
            out.append('the band at %.1f cm⁻¹ is %.1f wide, narrower than the resolution (%.1f): a cosmic ray or noise, not a band' % (c['pos'], c['fwhm'], resolution))
        elif c['fwhm'] <= 2.5 * dx:
            out.append('the band at %.1f cm⁻¹ is %.1f wide — two or three points' % (c['pos'], c['fwhm']))
        if c['height'] < 3.0 * f.sigma:
            out.append('the band at %.1f cm⁻¹ stands %.1f noise deviations high' % (c['pos'], c['height'] / f.sigma if f.sigma else 0.0))
        if c.get('at_limit') == 'max':
            out.append('the band at %.1f cm⁻¹ rests on the width limit (%.0f cm⁻¹): the data would have it wider — another band may be missing beside it' % (c['pos'], c['fwhm']))
        if c['fwhm'] >= 0.98 * (f.hi - f.lo):
            out.append('the band at %.1f cm⁻¹ is as wide as the region fitted: it is baseline, not a band' % c['pos'])
        if c['pos'] - f.lo < 0.25 * c['fwhm'] or f.hi - c['pos'] < 0.25 * c['fwhm']:
            out.append('the band at %.1f cm⁻¹ sits on the edge of the region fitted' % c['pos'])
    if f.cov:
        for a in range(len(f.names)):
            for b in range(a + 1, len(f.names)):
                va, vb = f.cov[a][a], f.cov[b][b]
                if va > 0 and vb > 0:
                    rho = f.cov[a][b] / math.sqrt(va * vb)
                    na, nb = f.names[a], f.names[b]
                    if abs(rho) > CORR_WARN and re.sub(r'\D', '', na) != re.sub(r'\D', '', nb) and not na.startswith('b') and not nb.startswith('b'):
                        out.append('%s and %s are correlated at %.2f: the data fix a combination of the two, not each' % (na, nb, rho))
    else:
        out.append('the parameters are not all determined (a singular fit): no uncertainties')
    corr = [w for w in out if 'are correlated at' in w]
    if len(corr) > 3:                                            # the three strongest, and how many more
        corr.sort(key=lambda w: -abs(float(re.search(r'correlated at (-?[\d.]+)', w).group(1))))
        out = [w for w in out if w not in corr[3:]] + ['%d more pairs of parameters are correlated above %.2f' % (len(corr) - 3, CORR_WARN)]
    for mark, what in (('as much as they are apart', 'pairs of neighbouring positions are uncertain by as much as they are apart'),
                       ('under half their width', 'pairs of bands are closer than half their width'),
                       ('rests on the width limit', 'bands rest on the width limit')):
        same = [w for w in out if mark in w]                     # a fit of a dozen bands says each thing a dozen times: three, and the count
        if len(same) > 3:
            at = out.index(same[2])
            out = [w for w in out if w not in same[3:]]
            out.insert(at + 1, '%d more %s' % (len(same) - 3, what))
    z = _runs_z(residual)
    if z < RUNS_WARN:
        out.append('the residual runs in long stretches of one sign (runs test z = %.1f): a band is missing or a shape does not fit' % z)
    return out


PRUNE_BIC = 6.0      # a model one band smaller is preferred unless the larger one's BIC is lower by more than this
ADD_BIC = 10.0       # a band is added only when it lowers the BIC by more than this


def _bare(c):
    """A fitted component as the start of the next fit (its limits and holds kept)."""
    out = {'shape': c['shape'], 'pos': c['pos'], 'height': c['height'], 'fwhm': c['fwhm'], 'eta': c['eta']}
    for k in ('fix', 'wmin', 'wmax'):
        if c.get(k):
            out[k] = c[k]
    return out


def residual_bands(xs, ys, f, min_share=MIN_SHARE, sigma=None):
    """Where a fit still leaves a band: [{'pos', 'height', 'fwhm'}] from the residual, largest first — the second
    derivative's dips at every scale, and, where the residual is one smooth swell with no dip of its own, its highest
    smoothed stretch. The share is of the SPECTRUM there, not of the residual."""
    m = model(xs, f.comps, f.base, f.x0)
    r = [a - b for a, b in zip(ys, m)]
    n = len(xs); dx = (xs[-1] - xs[0]) / (n - 1)
    sigma = sigma or f.sigma
    w = min(max(5, int(round(25.0 / dx)) | 1), max(5, (n // 4) | 1))
    ref = [max(v, 0.0) for v in savgol(ys, w, 2)]
    out = find_bands(xs, r, sigma, ref, min_share=min_share)
    rs = savgol(r, w, 2)
    i = max(range(n), key=lambda k: rs[k])
    if rs[i] > 4.0 * sigma * savgol_noise(w, 2) and rs[i] >= min_share * max(ref[i], 0.5 * max(ref)) \
            and not any(abs(q['pos'] - xs[i]) < 0.5 * q['fwhm'] for q in out):
        a = i
        while a > 0 and rs[a] > 0.5 * rs[i]:
            a -= 1
        b = i
        while b < n - 1 and rs[b] > 0.5 * rs[i]:
            b += 1
        out.append({'pos': xs[i], 'height': rs[i], 'fwhm': max(4 * dx, xs[b] - xs[a]), 'snr': rs[i] / (sigma * savgol_noise(w, 2)), 'scale': w * dx})
    out.sort(key=lambda q: -q['height'] * q['fwhm'])
    return out


def auto_fit(x, y, lo=None, hi=None, n=None, max_n=8, shape='pvoigt', local_baseline='const', min_snr=4.0, resolution=None, seeds=None,
             max_fwhm=None, min_fwhm=None, min_share=MIN_SHARE, share_eta=False):
    """A fit that chooses its own components -> (the chosen Fit, [(n, bic, chi2)] for every model tried).

    1. Every band the second derivative shows, at every scale (find_bands), is a component from the start — with the
       seeds (positions a structure or a manuscript expects) first — their heights set together by linear least squares.
    2. While the residual still holds a band (residual_bands) one is added and the whole refitted, as long as the BIC
       falls by more than ADD_BIC.
    3. Each band is then taken out in turn, weakest first, and the smaller model kept whenever it is as good (PRUNE_BIC).
    With `n` given, that many bands are used and steps 2–3 only make up the number. `max_fwhm` keeps a component of an
    envelope from widening into the envelope; `min_share` is how small a share of the curve a band may carry (lower finds
    more)."""
    xs, ys = crop(x, y, lo, hi)
    if len(xs) < 12:
        raise ValueError('fewer than twelve points between %s and %s' % (lo, hi))
    span = xs[-1] - xs[0]; dx = span / (len(xs) - 1)
    sigma = noise(ys) or 1.0
    limit = int(n or max_n)
    kw = dict(local_baseline=local_baseline, resolution=resolution, max_fwhm=max_fwhm, min_fwhm=min_fwhm, sigma=sigma, share_eta=share_eta)
    trial = dict(kw, max_iter=40, tol=1e-5)                    # a model on trial is fitted roughly; the one kept, fully
    cands = find_bands(xs, ys, sigma, min_snr=min_snr, min_share=min_share)
    wcap = max_fwhm or span
    start = []
    for p in seeds or []:
        if not xs[0] <= p <= xs[-1]:
            continue
        near = min(cands, key=lambda q: abs(q['pos'] - p)) if cands else None
        if near is not None and abs(near['pos'] - p) <= max(15.0, 0.5 * near['fwhm']):
            cands.remove(near); start.append(near)
        else:
            i = min(range(len(xs)), key=lambda k: abs(xs[k] - p))
            start.append({'pos': xs[i], 'height': max(ys[i], 0.0), 'fwhm': min(12.0, wcap)})
    start += cands
    if not start:
        i = max(range(len(xs)), key=lambda k: ys[k])
        start = [{'pos': xs[i], 'height': ys[i], 'fwhm': min(max(4 * dx, 0.1 * span), wcap)}]
    comps = [{'shape': shape, 'pos': c['pos'], 'height': max(c['height'], 1e-9), 'fwhm': min(c['fwhm'], wcap), 'eta': 0.5} for c in start[:limit]]
    comps = [c for c in linear_heights(xs, ys, comps, local_baseline) if c['height'] > 0] or comps[:1]
    trials = []
    try:
        f = fit(xs, ys, comps, **trial)
    except ValueError:
        raise ValueError('no band found between %g and %g' % (xs[0], xs[-1]))
    trials.append((len(f.comps), f.bic, f.chi2))
    # 2. what the residual still shows
    while len(f.comps) < limit:
        added = None
        for c in residual_bands(xs, ys, f, min_share, sigma)[:3]:       # the largest first; the next only when that one does not pay
            new = [_bare(q) for q in f.comps] + [{'shape': shape, 'pos': c['pos'], 'height': max(c['height'], 1e-9), 'fwhm': min(c['fwhm'], wcap), 'eta': 0.5}]
            try:
                f2 = fit(xs, ys, new, **trial)
            except ValueError:
                continue
            if added is None or f2.bic < added.bic:
                added = f2
            if f2.bic < f.bic - ADD_BIC:
                break
        if added is None or not (n or added.bic < f.bic - ADD_BIC):
            if added is not None:
                trials.append((len(added.comps), added.bic, added.chi2))
            break
        f = added; trials.append((len(f.comps), f.bic, f.chi2))
    # 3. each band out in turn: the smaller model whenever it is as good
    pruned = not n
    while pruned and len(f.comps) > 1:
        pruned = False
        for c in sorted(f.comps, key=lambda q: q['height'] * q['fwhm'])[:4]:     # the four smallest: a large band is not in doubt
            try:
                f2 = fit(xs, ys, [_bare(q) for q in f.comps if q is not c], **trial)
            except ValueError:
                continue
            if f2.bic <= f.bic + PRUNE_BIC:
                f = f2; trials.append((len(f2.comps), f2.bic, f2.chi2)); pruned = True
                break
    f = without_dead(xs, ys, fit(xs, ys, [_bare(q) for q in f.comps], **kw), **kw)[0]
    if trials:
        trials[-1] = (len(f.comps), f.bic, f.chi2)
    return f, trials


DEAD = 1e-9          # of the tallest band: a height the fit has driven to this is no band


def without_dead(xs, ys, f, **kw):
    """(fit, [positions dropped]) — a fit whose bands the minimiser drove to zero height, fitted again without them. A
    band at zero does nothing in the model and everything to its uncertainties (its position and width are free and
    mean nothing), so it is taken out and said."""
    top = max(c['height'] for c in f.comps) if f.comps else 0.0
    dead = [c for c in f.comps if c['height'] <= DEAD * top and 'height' not in (c.get('fix') or ())]
    if not dead or len(dead) == len(f.comps):
        return f, []
    f2 = fit(xs, ys, [_bare(c) for c in f.comps if c not in dead], **kw)
    f2.warnings.insert(0, '%s driven to zero height by the fit and taken out: %s cm⁻¹' % (
        'a band was' if len(dead) == 1 else '%d bands were' % len(dead), ', '.join('%.0f' % c['pos'] for c in dead)))
    return f2, [c['pos'] for c in dead]


# ----------------------------------------------------------------------------- beside the structure and the text

def expected_bands(structure):
    """[(position, label)] — where the structure's own distances put the uranyl and O–H stretches (spectro's relations
    turned round): 'ν1 U1 (1.762 Å)', 'ν3 U1', 'O–H O3···O7 (2.80 Å)'."""
    from pxrd_review import spectro as SP
    out = []
    for label, _ds, mean in (structure or {}).get('uranyl') or []:
        out.append((SP.bc_nu1_inv(mean), 'ν1 (UO2) %s, U–O %.3f Å' % (label, mean)))
        out.append((SP.bc_nu3_inv(mean), 'ν3 (UO2) %s, U–O %.3f Å' % (label, mean)))
    for D, A, d, _how in (structure or {}).get('hbonds') or []:
        if SP.LIB_MIN_OO <= d <= 3.3:
            out.append((SP.lib_nu(d), 'ν(O–H) %s···%s, %.2f Å' % (D, A, d)))
    return sorted(out)


def compare_stated(comps, stated, tolerance=6.0):
    """The fitted bands against the positions a manuscript states -> {'matched': [(stated, fitted, difference)],
    'not_fitted': [stated positions with no fitted band within `tolerance`], 'not_stated': [fitted positions]}."""
    fitted = sorted(c['pos'] for c in comps); used = set(); matched = []; lost = []
    for s in sorted(set(stated)):
        best = min((k for k in range(len(fitted)) if k not in used), key=lambda k: abs(fitted[k] - s), default=None)
        if best is not None and abs(fitted[best] - s) <= tolerance:
            used.add(best); matched.append((s, fitted[best], fitted[best] - s))
        else:
            lost.append(s)
    return {'matched': matched, 'not_fitted': lost, 'not_stated': [p for k, p in enumerate(fitted) if k not in used]}


def inferred(comps, technique=None):
    """For each fitted band, what it would mean: the windows it falls in (spectro.suggest), and the distance either
    relation gives where one applies -> [{'pos', 'suggest': [names], 'distance': str}]."""
    from pxrd_review import spectro as SP
    out = []
    for c in comps:
        names = [n for n, _w in SP.suggest(c['pos'], technique)]
        dist = ''
        if CH_WINDOW[0] <= c['pos'] <= CH_WINDOW[1]:
            # the C–H stretches of grease, epoxy or a mounting medium stand here: no O···O distance is read off them
            names = ['C–H stretching window (%d–%d)' % CH_WINDOW] + names
            dist = 'no distance: a band here is usually C–H of organic matter (absent from a Raman spectrum of the grain if not the mineral’s)'
        elif 'UO2 ν1' in names:
            dist = 'U–O %.3f Å if ν1 (UO2)' % SP.bc_nu1(c['pos'])
        elif 'UO2 ν3' in names:
            dist = 'U–O %.3f Å if ν3 (UO2)' % SP.bc_nu3(c['pos'])
        elif 'OH stretch' in names:
            d = SP.lib_d(c['pos'])
            dist = 'O···O %.2f Å' % d if d is not None else 'no O···O distance (above %g cm⁻¹: a free O–H)' % SP.LIB_FREE_OO
        out.append({'pos': c['pos'], 'suggest': names, 'distance': dist})
    return out


# ----------------------------------------------------------------------------- one call for the CLI and the window

SMOOTHED_SNR = 5000     # signal over point-to-point noise beyond which a spectrum has been smoothed or interpolated


def prepare(path, sheet=None, series=0, lo=None, hi=None, kind=None, despike_on=False, threshold=8.0, resolution=None,
            baseline_kind='none', anchors=None, lam=1e7, p=0.01, width=150.0, laser=None):
    """The spectrum of a file, cleaned -> {'series', 'all': [names], 'x', 'raw', 'y' (cleaned, baseline taken off),
    'baseline', 'spikes', 'kind', 'noise', 'notes'}. Nothing is fitted here."""
    return prepare_series(F.load(path, sheet), series, lo, hi, kind, despike_on, threshold, resolution, baseline_kind, anchors, lam, p, width, laser)


def prepare_series(every, series=0, lo=None, hi=None, kind=None, despike_on=False, threshold=8.0, resolution=None,
                   baseline_kind='none', anchors=None, lam=1e7, p=0.01, width=150.0, laser=None):
    """`prepare` for spectra already read ([Series]) — what the window calls for a file it was sent."""
    if not 0 <= series < len(every):
        raise ValueError('the file holds %d spectr%s; there is no number %d' % (len(every), 'um' if len(every) == 1 else 'a', series + 1))
    s = every[series]
    if laser:
        s = F.raman_shift(s, laser)
    s = F.wavenumber(s)
    notes = list(s.meta.get('notes') or [])
    if s.meta.get('unverified'):
        notes.insert(0, s.meta['unverified'])
    if s.meta.get('x_unit') not in ('cm-1', ''):
        notes.append('the x axis is in %s, not cm⁻¹%s' % (s.meta['x_unit'], ' — give the laser wavelength to convert it' if s.meta['x_unit'] == 'nm' else ''))
    kind = kind or F.guess_kind(s)
    if len(crop(s.x, s.y, lo, hi)[0]) < 8:
        raise ValueError('fewer than eight points between %s and %s (the spectrum runs %g–%g)' % (lo, hi, s.x[0], s.x[-1]))
    # cleaned and baselined WHOLE, then cut to the range: a baseline fitted to a cut-out has no ends to hold it
    x, raw = list(s.x), list(s.y)
    y = list(raw)
    if kind == 'ir-transmittance':
        y = to_absorbance(y); notes.append('transmittance converted to absorbance')
    spikes = []
    if despike_on:
        y, spikes = despike(x, y, threshold, resolution=resolution)
    base = baseline(x, y, baseline_kind, anchors, lam, p, width)
    sig = noise(y)
    top = sorted(y)[-max(1, len(y) // 100)] - sorted(y)[len(y) // 100]
    if sig and top / sig > SMOOTHED_SNR:
        notes.append('the point-to-point noise is under 1/%d of the signal: a smoothed or interpolated spectrum — χ² is then not on a noise scale, and the '
                     'uncertainties measure the misfit of the model, not the noise of the measurement' % SMOOTHED_SNR)
    keep = [i for i, v in enumerate(x) if (lo is None or v >= lo) and (hi is None or v <= hi)]
    cut = lambda v: [v[i] for i in keep]
    return {'series': s, 'all': [t.name for t in every], 'x': cut(x), 'raw': cut(raw), 'cleaned': cut(y), 'baseline': cut(base),
            'y': [y[i] - base[i] for i in keep], 'spikes': [(x[a], x[b]) for a, b in spikes if (lo is None or x[b] >= lo) and (hi is None or x[a] <= hi)],
            'kind': kind, 'noise': sig, 'notes': notes}


def band_rows(f, technique=None):
    """The table of a fit: one row per band — position, width, height, area, share of the area, shape, what it may be."""
    total = sum(c['area'] for c in f.comps) or 1.0
    extra = {round(i['pos'], 6): i for i in inferred(f.comps, technique)}
    rows = []
    def pm(v, e, fmt):
        return (fmt % v) + (' ± ' + (fmt % e) if e else '')
    for c in f.comps:
        i = extra.get(round(c['pos'], 6), {})
        rows.append([pm(c['pos'], c['esd'].get('pos'), '%.1f'), pm(c['fwhm'], c['esd'].get('fwhm'), '%.1f'), pm(c['height'], c['esd'].get('height'), '%.4g'),
                     '%.4g' % c['area'], '%.0f' % (100.0 * c['area'] / total), c['shape'] + (' η %.2f' % c['eta'] if c['shape'] == 'pvoigt' else ''),
                     ', '.join(i.get('suggest') or []), i.get('distance') or ''])
    return ['position (cm⁻¹)', 'FWHM (cm⁻¹)', 'height', 'area', 'area %', 'shape', 'window', 'distance'], rows


def table_text(f, technique=None, title=''):
    head, rows = band_rows(f, technique)
    w = [max(len(str(r[k])) for r in [head] + rows) for k in range(len(head))]
    L = [title] if title else []
    L.append('  '.join(h.ljust(w[k]) for k, h in enumerate(head)))
    L += ['  '.join(str(v).ljust(w[k]) for k, v in enumerate(r)) for r in rows]
    L.append('%d points %g–%g cm⁻¹, %d parameters; reduced χ² %.2f (noise %.3g), R² %.4f, BIC %.1f%s' % (
        f.n, f.lo, f.hi, f.k, f.chi2, f.sigma, f.r2, f.bic, '' if f.converged else '; NOT CONVERGED'))
    if f.base != (0.0, 0.0):
        L.append('local baseline %.4g%s' % (f.base[0], ' %+.4g·(x − %.0f)' % (f.base[1], f.x0) if f.base[1] else ''))
    L += ['  ! ' + w_ for w_ in f.warnings]
    return '\n'.join(L)


def figure_svg(x, y, f=None, base=None, ticks=None, width=900, height=420, title='', reverse=False):
    """The spectrum, its fit and its residual as an SVG (written by `export`; the window draws its own from the same
    numbers). `reverse`: x runs high to low, as an infrared spectrum is printed."""
    pad_l, pad_r, pad_t, pad_b = 56, 14, 22 if title else 10, 34
    res_h = 60 if f else 0
    ph = height - pad_t - pad_b - res_h
    x0, x1 = x[0], x[-1]
    fit_y = model(x, f.comps, f.base, f.x0) if f else None
    ymin = min(min(y), 0.0); ymax = max(y) * 1.05 or 1.0
    X = lambda v: pad_l + ((x1 - v) if reverse else (v - x0)) / (x1 - x0) * (width - pad_l - pad_r)
    Y = lambda v: pad_t + (ymax - v) / (ymax - ymin) * ph
    step = max(1, len(x) // 1800)
    def path(vals, yf=Y, sel=None):
        pts = [(X(x[i]), yf(vals[i])) for i in range(0, len(x), step) if sel is None or sel(x[i])]
        return 'M' + ' L'.join('%.1f,%.1f' % p for p in pts) if pts else ''
    o = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" font-family="Helvetica,Arial,sans-serif" font-size="11">' % (width, height, width, height),
         '<rect width="100%" height="100%" fill="#fff"/>']
    if title:
        o.append('<text x="%d" y="14" font-size="12">%s</text>' % (pad_l, _esc(title)))
    o.append('<path d="%s" fill="none" stroke="#222" stroke-width="1"/>' % path(y))
    if f:
        inside = lambda v: f.lo <= v <= f.hi
        for c in f.comps:
            vals = [profile(c['shape'], v, c['pos'], c['height'], c['fwhm'], c['eta']) + f.base[0] + f.base[1] * (v - f.x0) for v in x]
            o.append('<path d="%s" fill="none" stroke="#2a78c2" stroke-width="0.8"/>' % path(vals, sel=inside))
        o.append('<path d="%s" fill="none" stroke="#d1492e" stroke-width="1.2"/>' % path(fit_y, sel=inside))
        r = [a - b if inside(v) else 0.0 for v, a, b in zip(x, y, fit_y)]
        rmax = max(abs(v) for v in r) or 1.0
        ry = lambda v: pad_t + ph + 8 + (res_h - 12) * 0.5 * (1.0 - v / rmax)
        o.append('<line x1="%d" x2="%d" y1="%.1f" y2="%.1f" stroke="#bbb"/>' % (pad_l, width - pad_r, ry(0), ry(0)))
        o.append('<path d="%s" fill="none" stroke="#666" stroke-width="0.8"/>' % path(r, ry, inside))
        for c in f.comps:
            o.append('<text x="%.1f" y="%.1f" text-anchor="middle" fill="#2a78c2">%.0f</text>' % (X(c['pos']), max(pad_t + 9, Y(c['height'] + f.base[0]) - 4), c['pos']))
    for pos, label in ticks or []:
        if x0 <= pos <= x1:
            o.append('<line x1="%.1f" x2="%.1f" y1="%d" y2="%d" stroke="#2e9e5b" stroke-dasharray="3,2"><title>%s</title></line>' % (X(pos), X(pos), pad_t, pad_t + ph, _esc(label)))
    yb = pad_t + ph + res_h
    o.append('<line x1="%d" x2="%d" y1="%d" y2="%d" stroke="#222"/>' % (pad_l, width - pad_r, yb, yb))
    span = x1 - x0
    tick = next(t for t in (10, 20, 50, 100, 200, 500, 1000) if span / t <= 10)
    v = math.ceil(x0 / tick) * tick
    while v <= x1:
        o.append('<line x1="%.1f" x2="%.1f" y1="%d" y2="%d" stroke="#222"/><text x="%.1f" y="%d" text-anchor="middle">%g</text>' % (X(v), X(v), yb, yb + 4, X(v), yb + 16, v))
        v += tick
    o.append('<text x="%.1f" y="%d" text-anchor="middle">wavenumber (cm⁻¹)</text>' % (0.5 * (pad_l + width - pad_r), height - 4))
    o.append('</svg>')
    return '\n'.join(o)


def _esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def session(prep, fits, opts):
    """What it takes to do the same again: the file, the options, and every fitted region — the '_sp.json' of an export."""
    def comp(c):
        out = {k: c[k] for k in ('shape', 'pos', 'height', 'fwhm', 'eta', 'area')}
        out['esd'] = c['esd']
        for k in ('fix', 'wmin', 'wmax'):                         # what was held and limited: a session opens as it was left
            if c.get(k):
                out[k] = c[k]
        return out
    return {'pxrd_spectrum_session': 1, 'file': prep['series'].meta.get('source'), 'series': prep['series'].name, 'options': opts, 'noise': prep['noise'], 'spikes': prep['spikes'],
            'fits': [{'lo': f.lo, 'hi': f.hi, 'n': f.n, 'parameters': f.k, 'chi2': f.chi2, 'r2': f.r2, 'bic': f.bic, 'converged': f.converged,
                      'baseline': list(f.base), 'x0': f.x0, 'components': [comp(c) for c in f.comps], 'warnings': list(f.warnings)} for f in fits]}


def export(prep, fits, out_dir, stem, opts=None, word=False, xlsx=False, ticks=None):
    """Write the band table (<stem>_sp.txt, always), the figure (<stem>_sp.svg), the session (<stem>_sp.json) and, when
    asked, the table as Word / Excel -> {kind: path}."""
    os.makedirs(out_dir, exist_ok=True)
    tech = 'raman' if prep['kind'] == 'raman' else 'ir' if prep['kind'].startswith('ir') else None
    out = {}
    text = ['SPECTRUM — %s' % prep['series'].name] + ['  note: ' + n for n in prep['notes']]
    if prep['spikes']:
        text.append('  %d cosmic-ray event%s removed at %s cm⁻¹' % (len(prep['spikes']), '' if len(prep['spikes']) == 1 else 's', ', '.join('%.0f' % a for a, _b in prep['spikes'][:12])))
    for f in fits:
        text += ['', table_text(f, tech, 'Bands %g–%g cm⁻¹' % (f.lo, f.hi))]
    out['txt'] = os.path.join(out_dir, stem + '_sp.txt')
    with open(out['txt'], 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(text) + '\n')
    out['svg'] = os.path.join(out_dir, stem + '_sp.svg')
    with open(out['svg'], 'w', encoding='utf-8') as fh:
        if len(fits) == 1:
            xs, ys = crop(prep['x'], prep['y'], fits[0].lo - 0.15 * (fits[0].hi - fits[0].lo), fits[0].hi + 0.15 * (fits[0].hi - fits[0].lo))
            fh.write(figure_svg(xs, ys, fits[0], ticks=ticks, title=prep['series'].name, reverse=tech == 'ir'))
        else:
            fh.write(figure_svg(prep['x'], prep['y'], None, ticks=ticks, title=prep['series'].name, reverse=tech == 'ir'))
    out['json'] = os.path.join(out_dir, stem + '_sp.json')
    with open(out['json'], 'w', encoding='utf-8') as fh:
        json.dump(session(prep, fits, opts or {}), fh, indent=1, ensure_ascii=False)
    if xlsx and fits:
        import openpyxl
        from openpyxl.styles import Font
        bold = Font(bold=True)
        sig = lambda v, n=4: None if v is None else float('%.*g' % (n, v))
        wb = openpyxl.Workbook(); ws = wb.active; ws.title = 'bands'
        ws.append(['Fitted bands — %s' % prep['series'].name]); ws['A1'].font = bold
        for n_ in prep['notes']:
            ws.append([n_])
        for f in fits:
            _head, rows = band_rows(f, tech)
            ws.append([])
            ws.append(['region %g–%g cm⁻¹: %d points, %d parameters; reduced χ² %.3g, R² %.5f%s' % (f.lo, f.hi, f.n, f.k, f.chi2, f.r2, '' if f.converged else '; NOT CONVERGED')])
            ws.append(['position (cm⁻¹)', '± s.u.', 'FWHM (cm⁻¹)', '± s.u.', 'height', '± s.u.', 'area', 'area %', 'shape', 'η', 'where published descriptions place it', 'distance'])
            for cell in ws[ws.max_row]:
                cell.font = bold
            total = sum(c['area'] for c in f.comps) or 1.0
            for c, r in zip(f.comps, rows):
                ws.append([round(c['pos'], 1), sig(c['esd'].get('pos'), 2), round(c['fwhm'], 1), sig(c['esd'].get('fwhm'), 2), sig(c['height']), sig(c['esd'].get('height'), 2), sig(c['area']),
                           round(100.0 * c['area'] / total, 1), {'pvoigt': 'pseudo-Voigt', 'gauss': 'Gaussian', 'lorentz': 'Lorentzian'}[c['shape']],
                           round(c['eta'], 2) if c['shape'] == 'pvoigt' else None, r[6], r[7]])
            for w_ in f.warnings:
                ws.append(['! ' + w_])
        for col, width in zip('ABCDEFGHIJKL', (16, 9, 13, 9, 11, 9, 11, 8, 13, 6, 34, 30)):
            ws.column_dimensions[col].width = width
        # the curves, to plot: per region the spectrum as fitted, the fit, the residual and each band on the region's points
        for k, f in enumerate(fits):
            cs = wb.create_sheet('curves %g-%g' % (round(f.lo), round(f.hi)) if len(fits) > 1 else 'curves')
            xs, ys = crop(prep['x'], prep['y'], f.lo, f.hi)
            m = model(xs, f.comps, f.base, f.x0)
            per = [model(xs, [c], f.base, f.x0) for c in f.comps]
            cs.append(['wavenumber (cm⁻¹)', 'spectrum', 'fit', 'residual', 'local baseline'] + ['band %.0f' % c['pos'] for c in f.comps])
            for cell in cs[1]:
                cell.font = bold
            for i, v in enumerate(xs):
                cs.append([v, sig(ys[i], 6), sig(m[i], 6), sig(ys[i] - m[i], 4), sig(f.base[0] + f.base[1] * (v - f.x0), 4)] + [sig(col[i], 5) for col in per])
            cs.column_dimensions['A'].width = 18
        sp = wb.create_sheet('spectrum')
        sp.append(['wavenumber (cm⁻¹)', 'as recorded', 'cleaned' + (' (absorbance)' if prep['kind'] == 'ir-transmittance' else ''), 'baseline', 'baseline taken off'])
        for cell in sp[1]:
            cell.font = bold
        for i, v in enumerate(prep['x']):
            sp.append([v, prep['raw'][i], sig(prep['cleaned'][i], 6), sig(prep['baseline'][i], 6), sig(prep['y'][i], 6)])
        sp.column_dimensions['A'].width = 18
        out['xlsx'] = os.path.join(out_dir, stem + '_sp.xlsx'); wb.save(out['xlsx'])
    if word and fits:
        import docx
        doc = docx.Document()
        for f in fits:
            head, rows = band_rows(f, tech)
            doc.add_paragraph('Fitted bands, %g–%g cm⁻¹ (%s)' % (f.lo, f.hi, prep['series'].name))
            t = doc.add_table(rows=1, cols=len(head))
            for k, h in enumerate(head):
                t.rows[0].cells[k].text = h
            for r in rows:
                cells = t.add_row().cells
                for k, v in enumerate(r):
                    cells[k].text = str(v)
            doc.add_paragraph('Reduced χ² %.2f, R² %.4f; %s.' % (f.chi2, f.r2, '; '.join(f.warnings) if f.warnings else 'no warning'))
        out['docx'] = os.path.join(out_dir, stem + '_sp.docx'); doc.save(out['docx'])
    return out


# ----------------------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('path', help='the spectrum: text, CSV, .xlsx, RRUFF, JCAMP-DX, .spc, .spa or an OPUS file')
    ap.add_argument('--sheet', help='the sheet of a workbook'); ap.add_argument('--series', type=int, default=1, help='which spectrum of the file (1 = the first)')
    ap.add_argument('--list', action='store_true', help='list the spectra the file holds and stop')
    ap.add_argument('--range', nargs=2, type=float, metavar=('LO', 'HI'), help='the region to fit (cm-1); cleaning and the baseline use the whole spectrum')
    ap.add_argument('--kind', choices=('raman', 'ir-absorbance', 'ir-transmittance'), help='what the spectrum is (guessed when not given)')
    ap.add_argument('--laser', type=float, help='the laser wavelength (nm), for a Raman spectrum recorded against wavelength')
    ap.add_argument('--despike', action='store_true', help='remove cosmic-ray events'); ap.add_argument('--resolution', type=float, help='the spectral resolution (cm-1)')
    ap.add_argument('--baseline', choices=BASELINES, default='none'); ap.add_argument('--lam', type=float, default=1e7, help='stiffness of the als baseline, as for a 1 cm-1 spacing'); ap.add_argument('--p', type=float, default=0.01)
    ap.add_argument('--anchors', help='anchor positions for --baseline anchors, comma-separated')
    ap.add_argument('--width', type=float, default=150.0, help='the clipping half-width of --baseline snip (cm-1)')
    ap.add_argument('--fit', help="'auto' (as many bands as the data support) or a number of bands")
    ap.add_argument('--max-bands', type=int, default=8, help="the most bands --fit auto may use")
    ap.add_argument('--max-fwhm', type=float, help='the widest a band may be (cm-1): keeps a component of a broad envelope from widening into it')
    ap.add_argument('--min-fwhm', type=float, help='the narrowest a band may be (cm-1)')
    ap.add_argument('--min-share', type=float, default=100 * MIN_SHARE, help='the smallest band --fit auto proposes: its share of the curve where it stands, in %% (lower finds more)')
    ap.add_argument('--shape', choices=SHAPES, default='pvoigt'); ap.add_argument('--local', choices=('none', 'const', 'linear'), default='linear', help='the local baseline of the fit')
    ap.add_argument('--cif', help='the structure: its uranyl and hydrogen-bond distances as expected positions')
    ap.add_argument('--manuscript', help='a manuscript .docx or paper .pdf: its stated bands beside the fitted ones')
    ap.add_argument('--out', help='the folder for the outputs (default: review_out beside the file)'); ap.add_argument('--word', action='store_true'); ap.add_argument('--xlsx', action='store_true')
    a = ap.parse_args(argv)
    try:
        if a.list:
            for k, s in enumerate(F.load(a.path, a.sheet)):
                print('%2d  %-60s %5d points  %g–%g %s%s' % (k + 1, s.name[:60], len(s.x), s.x[0], s.x[-1], s.meta.get('x_unit'), '  [' + '; '.join(s.meta['notes']) + ']' if s.meta.get('notes') else ''))
            return 0
        lo, hi = a.range if a.range else (None, None)
        prep = prepare(a.path, a.sheet, a.series - 1, lo, hi, a.kind, a.despike, resolution=a.resolution, baseline_kind=a.baseline,
                       anchors=[float(v) for v in a.anchors.split(',')] if a.anchors else None, lam=a.lam, p=a.p, width=a.width, laser=a.laser)
    except ValueError as e:
        raise SystemExit('pxrd spectrum: %s' % e)
    print('SPECTRUM — %s: %d points %g–%g cm⁻¹, noise %.3g%s' % (prep['series'].name, len(prep['x']), prep['x'][0], prep['x'][-1], prep['noise'], ', ' + prep['kind'] if prep['kind'] else ''))
    for n in prep['notes']:
        print('  note: ' + n)
    if prep['spikes']:
        print('  %d cosmic-ray event%s removed: %s' % (len(prep['spikes']), '' if len(prep['spikes']) == 1 else 's', ', '.join('%.0f' % s for s, _e in prep['spikes'][:12])))
    ticks = []
    if a.cif:
        from pxrd_review import spectro as SP
        try:
            ticks = expected_bands(SP.structure_distances(a.cif))
        except Exception as e:
            print('  the .cif could not be used (%s)' % str(e)[:100])
        for pos, label in ticks:
            if prep['x'][0] <= pos <= prep['x'][-1]:
                print('  expected %.0f cm⁻¹  %s' % (pos, label))
    fits = []
    if a.fit:
        try:
            f, trials = auto_fit(prep['x'], prep['y'], n=None if a.fit == 'auto' else int(a.fit), max_n=a.max_bands, shape=a.shape, local_baseline=a.local,
                                 resolution=a.resolution, seeds=[p for p, _l in ticks], max_fwhm=a.max_fwhm, min_fwhm=a.min_fwhm, min_share=a.min_share / 100.0)
        except ValueError as e:
            raise SystemExit('pxrd spectrum: %s' % e)
        fits.append(f)
        tech = 'raman' if prep['kind'] == 'raman' else 'ir' if prep['kind'].startswith('ir') else None
        print(table_text(f, tech))
        print('  models tried: ' + ', '.join('%d (BIC %.0f)' % (n, b) for n, b, _c in trials))
        more = residual_bands(crop(prep['x'], prep['y'], f.lo, f.hi)[0], crop(prep['x'], prep['y'], f.lo, f.hi)[1], f, a.min_share / 100.0)
        if more:
            print('  the residual still holds a band near ' + ', '.join('%.0f' % q['pos'] for q in more[:4]) + ' cm⁻¹')
    if a.manuscript:
        from pxrd_review import spectro as SP, paper_extract as PE
        stated = sorted({b.pos for b in SP.bands(PE.text_of(a.manuscript)) if b.own and prep['x'][0] <= b.pos <= prep['x'][-1]})
        if fits:
            c = compare_stated(fits[0].comps, stated)
            print('  stated in the manuscript and fitted: ' + (', '.join('%g (fitted %.1f)' % (s, p) for s, p, _d in c['matched']) or 'none'))
            if c['not_fitted']:
                print('  stated, no fitted band within 6 cm⁻¹: ' + ', '.join('%g' % s for s in c['not_fitted']))
            if c['not_stated']:
                print('  fitted, not stated: ' + ', '.join('%.1f' % p for p in c['not_stated']))
        else:
            print('  stated in the manuscript: ' + ', '.join('%g' % s for s in stated))
    if fits or a.out:
        out_dir = a.out or os.path.join(os.path.dirname(os.path.abspath(a.path)), 'review_out')
        stem = re.sub(r'[^\w.-]+', '_', os.path.splitext(os.path.basename(a.path))[0])
        files = export(prep, fits, out_dir, stem, vars(a), a.word, a.xlsx, ticks)
        print('  written: ' + ', '.join(os.path.basename(p) for p in files.values()) + ' → ' + out_dir)
    return 0


if __name__ == '__main__':
    sys.exit(main())
