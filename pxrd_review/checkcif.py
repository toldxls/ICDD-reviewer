"""checkCIF / PLATON report re-tiered by REVIEW significance (`pxrd checkcif <report.pdf|.txt> …`).

checkCIF's A/B/C/G tiers are written for journal submission. For a structure review some G- and
C-level alerts matter far more than their tier (a weighting scheme that did not converge, an estimated
twin fraction, a large variance K), while the A-level PUBL* alerts are missing journal metadata and
mean nothing for a proposal's .cif. This reads the report, re-tiers both ways, and prints a
review-ordered list with the reason each elevated alert matters and what it asks for. Residual
density peaks 0.6–1.0 Å from an O atom (PLAT975/976) are pointed out as possible unmodelled H.

    python3 -m pxrd_review.checkcif "<report.pdf>" [more reports]
"""
import os, re, sys

# checkCIF code -> (review severity, why it outranks its tier, what to do)
ELEVATE = {
    'PLAT965': ('CRITICAL',
                'SHELXL weighting did NOT converge: the refinement is not at a least-squares minimum and every reported esd is unreliable.',
                'Iterate WGHT to convergence, or say why it cannot (severe disorder) and treat every esd as a lower bound.'),
    'PLAT083': ('FLAG',
                'Large 2nd WGHT parameter: least squares had to down-weight reflections it cannot fit — the classic sign of an unmodelled twin or a systematic error.',
                'Explain the large b; test for an unmodelled (pseudo)merohedral twin.'),
    'PLAT906': ('FLAG',
                'Large K = <Fo²>/<Fc²> in a variance bin: a SYSTEMATIC Fo²/Fc² discrepancy (twin overlap, diffuse disorder, omitted strong reflections), not noise.',
                'Identify the bin; check twinning and whether strong low-angle reflections were omitted.'),
    'PLAT931': ('FLAG',
                'checkCIF estimates an unmodelled TWIN component (BASF) from the FCF.',
                'Cross-check the .cif TWIN/BASF; if the law is absent from the refinement, refine it and report the volume fraction.'),
    'PLAT969': ('FLAG',
                'Henn R-gap: wR2 far exceeds the value predicted from the measured σ(I) — a systematic, not random, misfit.',
                'Resolve the systematic error before trusting wR2.'),
    'PLAT933': ('SURFACE',
                'HKL-OMIT records: reflections were excluded from the refinement.',
                'Justify each omission (beam stop, overload, outlier); unjustified omission of strong low-angle data biases the scale and the ADPs and inflates K.'),
    'PLAT913': ('SURFACE',
                'Very strong reflections missing from the FCF (often beam stop or overload).',
                'Confirm these were not silently dropped.'),
    'PLAT077': ('NOTE',
                'The unit cell holds a non-integer atom count: partial occupancy or a vacancy.',
                'Confirm the ideal-formula idealisation of the vacancy (Hatert & Burke 2008).'),
    'PLAT034': ('NOTE',
                'No Flack parameter on an acentric structure.',
                'Report Flack, or the inversion-twin BASF as the absolute-structure measure.'),
    'PLAT794': ('BVS',
                "checkCIF's tentative bond-valence per cation site.",
                'Run pxrd bv: verify the oxidation states; flag under/over-bonded sites (OH/H2O candidates at under-bonded O).'),
    'DIFMN03': ('NOTE',
                'Deep negative residual density; checkCIF asks for the atom site to be identified.',
                'Report which atom the hole sits next to (usually a heavy atom: absorption or a twin).'),
}
DEMOTE = {c: 'journal-submission metadata absent from the .cif — ignorable for a proposal .cif'
          for c in ('PUBL001', 'PUBL003', 'PUBL004', 'PUBL005', 'PUBL006', 'PUBL008',
                    'PUBL009', 'PUBL010', 'PUBL011', 'PUBL012', 'PUBL017')}
RANK = {'CRITICAL': 0, 'FLAG': 1, 'SURFACE': 2, 'BVS': 3, 'NOTE': 4}

ALERT_RE = re.compile(r'\b([A-Z][A-Z0-9]{2,7})_ALERT_(\d)_([ABCG])\b[ .]*(.*)')
NUM_RE = re.compile(r'-?\d+\.\d+|\b\d{2,}\b')
# 'Check Calcd Resid. Dens.  0.61Ang From Ow4     .       0.41 eA-3'
RESID_RE = re.compile(r'Resid\.?\s*Dens\.?\s+(\d+\.\d+)\s*Ang\s+From\s+([A-Za-z]{1,3}\d{0,2}[A-Za-z]?)', re.I)
H_NEAR = (0.6, 1.05)          # an O–H distance as X-ray difference maps place it


def read_text(path):
    """The report's text: a pdf through PyMuPDF (the tool's one pdf reader), else the file as text."""
    if path.lower().endswith('.pdf'):
        import pymupdf
        with pymupdf.open(path) as doc:
            return '\n'.join(pg.get_text() for pg in doc)
    with open(path, encoding='utf-8', errors='ignore') as f:
        return f.read()


def parse(text):
    """[{'code', 'type', 'level', 'desc', 'val'}] — each alert once (the report repeats its summary)."""
    alerts, seen = [], set()
    for m in ALERT_RE.finditer(text):
        code, atype, level, rest = m.group(1), int(m.group(2)), m.group(3), m.group(4).strip()
        key = (code, rest[:40])
        if key in seen:
            continue
        seen.add(key)
        nums = NUM_RE.findall(rest)
        alerts.append(dict(code=code, type=atype, level=level, desc=rest, val=(nums[-1] if nums else None)))
    return alerts


def audit(alerts):
    """{'tally', 'elevated': [(severity, alert, why, action)], 'demoted': n, 'h_peaks': [(d, atom, alert)]}."""
    elevated, demoted, tally, h_peaks = [], 0, {'A': 0, 'B': 0, 'C': 0, 'G': 0}, []
    for a in alerts:
        tally[a['level']] = tally.get(a['level'], 0) + 1
        if a['code'] in ELEVATE:
            sev, why, act = ELEVATE[a['code']]
            elevated.append((sev, a, why, act))
        if a['code'] in DEMOTE:
            demoted += 1
        if a['code'] == 'PLAT975':                              # a residual PEAK (976 is a hole)
            m = RESID_RE.search(a['desc'])
            if m and H_NEAR[0] <= float(m.group(1)) <= H_NEAR[1] and m.group(2)[:1].upper() == 'O':
                h_peaks.append((float(m.group(1)), m.group(2), a))
    elevated.sort(key=lambda e: RANK[e[0]])
    return {'tally': tally, 'elevated': elevated, 'demoted': demoted, 'h_peaks': h_peaks}


def lines(name, res):
    t = res['tally']
    L = ['%s   (checkCIF tally  A=%d B=%d C=%d G=%d)' % (name, t['A'], t['B'], t['C'], t['G'])]
    if not res['elevated']:
        L.append('  (no review-elevated alerts)')
    for sev, a, why, act in res['elevated']:
        v = (' = %s' % a['val']) if a['val'] else ''
        L.append('  %-8s %-9s [checkCIF %s%d]%s' % (sev, a['code'], a['level'], a['type'], v))
        L.append('           why : %s' % why)
        L.append('           do  : %s' % act)
    for d, atom, a in res['h_peaks']:
        L.append('  H?       %-9s residual density %.2f Å from %s (%s e/Å³): an O–H distance — a possible unmodelled H, or a split water site'
                 % (a['code'], d, atom, a['val'] or '?'))
    if res['demoted']:
        L.append("  [demoted] %d PUBL* A-level publication-metadata alerts — ignorable for a proposal .cif" % res['demoted'])
    return L


def run(path):
    return lines(os.path.basename(path), audit(parse(read_text(path))))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__); return 0
    for p in argv:
        try:
            print('\n'.join(run(p)))
        except Exception as ex:
            print('%s: could not read (%s)' % (p, ex))
    return 0


if __name__ == '__main__':
    sys.exit(main())
