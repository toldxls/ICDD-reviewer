"""How well does the figure tracer read a curve? Two answer keys (pxrd_review.figure_trace; dev tool, not shipped).

    python3 tools/figure_oracle.py --synthetic
    python3 tools/figure_oracle.py CASES.json [--jitter PX] [-v]

--synthetic   figures DRAWN HERE from a spectrum whose bands are known, at a ladder of resolutions, line widths and JPEG
              qualities — what resolution alone costs, and what a format costs. No data of anyone's.
CASES.json    figures set against the DATA THEY WERE DRAWN FROM: a private file (default $PXRD_FIGURE_CASES), a list of
                {"name", "figure": image or .pdf, "page": 0, "data": spectrum file, "series": 0,
                 "first_tick": value at the leftmost tick or null, "last_tick": value at the rightmost, "tick_step": cm-1 between ticks,
                 "seed": a wavenumber where the curve wanted has a peak (or null), "range": [lo, hi]}
              For each, the three things a user confirms are given as a user would give them (the frame found; the axis on
              its first and last tick; a click on the curve) and the traced curve is compared with the data: every peak of
              the data against the nearest peak of the trace (cm-1 and pixels), and the shape (R² of trace against data).
              --jitter PX puts the two axis marks up to PX pixels off their ticks, as a hand does without the snap.
Nothing of a case goes into the repo: the file, the figures and the data stay where they are.
"""
import os, sys, json, math, random, argparse, statistics as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pxrd_review import figure_trace as FT, spectrum_formats as F, spectrum as SM


def apexes(x, y, share=0.03):
    """Prominent local maxima, each at the top of the parabola through its three highest points -> [(position, height)]."""
    n = len(x); sm = SM.savgol(y, 5, 2) if n > 20 else list(y)
    rng = max(sm) - min(sm) or 1.0; out = []
    for i in range(2, n - 2):
        if not (sm[i] >= sm[i - 1] and sm[i] > sm[i + 1]):
            continue
        l = sm[i]; k = i - 1
        while k >= 0 and sm[k] <= sm[i]:
            l = min(l, sm[k]); k -= 1
        r = sm[i]; k = i + 1
        while k < n and sm[k] <= sm[i]:
            r = min(r, sm[k]); k += 1
        if sm[i] - max(l, r) <= share * rng:
            continue
        a, b, c = sm[i - 1], sm[i], sm[i + 1]; den = a - 2 * b + c
        out.append((x[i] + (0.5 * (a - c) / den if den else 0.0) * (x[i + 1] - x[i - 1]) / 2.0, sm[i]))
    return out


def compare(r, rx, ry, lo, hi):
    """(peaks in the data, matched, signed errors, R²) of a digitised curve against its data over lo–hi."""
    rx, ry = SM.crop(rx, ry, lo, hi); tx, ty = SM.crop(r['x'], r['y'], lo, hi)
    truth = apexes(rx, ry); got = apexes(tx, ty, 0.02)
    errs = []
    for p, _h in truth:
        near = min(got, key=lambda q: abs(q[0] - p), default=None)
        if near is not None and abs(near[0] - p) <= 4.0 * r['cm_per_px'] + 2.0:
            errs.append(near[0] - p)
    yi = SM._interp(tx, rx, ry); n = len(tx)
    mx, my = sum(yi) / n, sum(ty) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(yi, ty)); sxx = sum((a - mx) ** 2 for a in yi); syy = sum((b - my) ** 2 for b in ty)
    return len(truth), errs, (sxy * sxy / (sxx * syy) if sxx and syy else 0.0)


def line(name, how, n, errs, cm, r2, cov):
    ae = sorted(abs(e) for e in errs) or [0.0]
    return '%-30s %-6s %5d %5d %+7.2f %7.2f %7.2f %7.2f %8.3f %6.2f %7.4f %5.2f' % (
        name[:30], how, n, len(errs), st.mean(errs) if errs else 0.0, st.median(ae), ae[int(0.9 * (len(ae) - 1))], ae[-1], cm, st.median(ae) / cm if cm else 0.0, r2, cov)


HEAD = '%-30s %-6s %5s %5s %7s %7s %7s %7s %8s %6s %7s %5s' % ('case', 'how', 'peaks', 'found', 'bias', 'median', '90th', 'worst', 'cm-1/px', 'med px', 'R2', 'cov')


def cases(path, jitter=0.0, seed=0, verbose=False):
    rng = random.Random(seed)
    print(HEAD)
    for c in json.load(open(path, encoding='utf-8')):
        fig = FT.figure(c['figure'], c.get('page', 0)); box = FT.frames(fig)[0]
        marks = FT.tick_marks(fig, box)
        if len(marks) < 2:
            print('%-30s no ticks found on the axis' % c['name'][:30]); continue
        v_last = c['last_tick']; vf = c['first_tick'] if c.get('first_tick') is not None else v_last + c['tick_step'] * (len(marks) - 1) * (1 if c.get('descending', True) else -1)
        cal = lambda v: marks[0] + (v - vf) / (v_last - vf) * (marks[-1] - marks[0])
        seedpx = colour = None
        if c.get('seed') is not None:                            # a click on the curve wanted: the topmost ink in the column of one of its peaks — and, as the window does, the darkest pixel within two of it
            col = int(round(cal(c['seed'])))
            for y in range(box[1] + 2, box[3] - 2):
                if sum(fig.at(col, y)) < 600:
                    seedpx = min(((col + dx, y + dy) for dx in range(-2, 3) for dy in range(0, 5)), key=lambda q: sum(fig.at(*q))); break
            colour = fig.at(*seedpx) if seedpx else None
        r = FT.digitize(fig, box, marks[0] + rng.uniform(-jitter, jitter), vf, marks[-1] + rng.uniform(-jitter, jitter), v_last, colour=colour, seed=seedpx)
        s = F.load(c['data'])[c.get('series', 0)]
        n, errs, r2 = compare(r, s.x, s.y, *c['range'])
        print(line(c['name'], r['how'], n, errs, r['cm_per_px'], r2, r['coverage']))
        if verbose:
            print('      frame %s, %d ticks, colour %s; errors %s' % (box, len(marks), colour, ' '.join('%+.2f' % e for e in errs)))


BANDS = [(210, 0.35, 14), (464, 1.0, 10), (832, 0.8, 12), (846, 0.45, 9), (1010, 0.25, 16), (1105, 0.55, 20), (318, 0.2, 9), (655, 0.3, 11), (1210, 0.15, 12)]


def synthetic():
    """Known bands drawn as a figure (PyMuPDF), rendered to pixels at each resolution, line width and JPEG quality, traced
    with the axis on its two outer ticks."""
    import fitz
    lo, hi = 100.0, 1300.0
    X0, X1, Y0, Y1 = 90.0, 500.0, 120.0, 330.0
    spec = lambda v: 0.04 + sum(h * SM.profile('pvoigt', v, p, 1.0, w, 0.5) for p, h, w in BANDS)
    X = lambda v: X0 + (v - lo) / (hi - lo) * (X1 - X0)
    xs = [lo + k * (hi - lo) / 2400.0 for k in range(2401)]; ys = [spec(v) for v in xs]
    print(HEAD)
    for width in (0.5, 1.0, 2.0):
        doc = fitz.open(); page = doc.new_page(width=595, height=842)
        sh = page.new_shape(); sh.draw_line((X0, Y1), (X1, Y1)); sh.draw_line((X0, Y1), (X0, Y0))
        for v in range(200, 1300, 100):
            sh.draw_line((X(v), Y1), (X(v), Y1 + 4))
        sh.finish(color=(0, 0, 0), width=0.8); sh.commit()
        sh = page.new_shape(); sh.draw_polyline([(X(v), Y1 - u / 1.15 * (Y1 - Y0)) for v, u in zip(xs, ys)]); sh.finish(color=(0, 0, 0), width=width, closePath=False); sh.commit()
        for dpi in (72, 100, 150, 200, 300, 600):
            pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0))
            for fmt, blob in (('png', pix.tobytes('png')), ('jpeg 60', pix.tobytes('jpeg', jpg_quality=60))):
                if fmt != 'png' and dpi not in (100, 200):
                    continue
                fig = FT.figure('f.%s' % ('png' if fmt == 'png' else 'jpg'), data=blob)
                try:
                    box = FT.frames(fig)[0]; marks = FT.tick_marks(fig, box)
                    r = FT.digitize(fig, box, marks[0], 200.0, marks[-1], 200.0 + 100.0 * (len(marks) - 1))
                    n, errs, r2 = compare(r, xs, ys, 150, 1250)
                    print(line('line %.1f pt, %d dpi, %s' % (width, dpi, fmt), r['how'], n, errs, r['cm_per_px'], r2, r['coverage']))
                except Exception as e:
                    print('%-30s FAILED: %s' % ('line %.1f pt, %d dpi, %s' % (width, dpi, fmt), str(e)[:70]))
        doc.close()


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('cases', nargs='?', default=os.environ.get('PXRD_FIGURE_CASES'), help='the private list of figures with their data (default $PXRD_FIGURE_CASES)')
    ap.add_argument('--synthetic', action='store_true'); ap.add_argument('--jitter', type=float, default=0.0); ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('-v', action='store_true')
    a = ap.parse_args()
    if a.synthetic:
        synthetic()
    if a.cases:
        cases(a.cases, a.jitter, a.seed, a.v)
    if not a.synthetic and not a.cases:
        ap.error('--synthetic, or a CASES.json (or $PXRD_FIGURE_CASES)')
