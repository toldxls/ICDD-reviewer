"""The spectroscopy reader over the corpus: every band a paper states with its assignment, every distance it
credits to Bartlett & Cooney or to Libowitzky recomputed, and — from all of it — the band windows the tool ships.

    python3 tools/corpus_spectra.py "<pdf folders, comma-separated>" [OUT_DIR] [TAG]
                                    [--baseline spectra_library<tag>.jsonl] [--papers LIST] [--only SUBSTR] [--limit N]
                                    [--build-windows] [--no-cache]

Outputs, in OUT_DIR (the private review_out — nothing here goes into the repo but the windows):
  spectra_library<tag>.jsonl   one line per paper that states a band: its bands (position, technique, shape, group,
                               mode), its stated distances with their verdicts, the lines the review would print
  spectra_report<tag>.txt      the counts; THE PROOF OF THE COEFFICIENTS (every pair a paper prints — a band beside
                               the distance it gave — recomputed, largest difference first); the findings in full,
                               to be read by hand; the reader against a denominator that shares no code with it
                               (tools/paper_features.spectro_features); the windows as they would be built
  --baseline                   the papers whose findings or verdict counts changed since an earlier run: the A/B
                               for a reader change, as tools/corpus_paper_extract.py does it for the other readers
  --build-windows              writes pxrd_review/data/band_windows.json: per group and mode, the percentiles of the
                               positions the papers assign to it. AGGREGATES ONLY — no paper, no mineral — and a bin
                               needs MIN_PAPERS papers behind it. Folders of unpublished work never feed it (EXCLUDE).

The papers are read from the page-text cache the other corpus tools keep (--no-cache reads the pdfs); the run is
serial and takes seconds, and its outputs are a function of the papers and the code alone.
"""
import os, re, sys, json, argparse, collections

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pxrd_review import paper_extract as PE, spectro as S
import paper_features as PF
import corpus_paper_extract as CPE

MIN_PAPERS = 8                                       # a window with fewer papers behind it is not shipped
EXCLUDE = re.compile(r'CNMNC|proposal|review_out|pxrd-review', re.I)     # unpublished work, the tool's own output and its bundles
WINDOW_MODES = {1, 2, 3, 4}                          # the numbered modes of a polyatomic group …
WINDOW_EXTRA = {('OH', 'stretch'), ('H2O', 'bend'), ('H2O', 2)}          # … and the two water / hydroxyl bands every hydrated mineral has
PCTS = (5, 25, 50, 75, 95)
TRIM = 5.0                                           # robust sigmas (1.4826 MAD) from the median beyond which a position is dropped:
                                                     # the reader mispairs a band with a group a few times in a hundred, and those
                                                     # land far from the rest — the percentiles are of what remains


def pct(v, q):
    v = sorted(v); i = (len(v) - 1) * q / 100.0; lo = int(i); hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)


def read_paper(pdf, cif):
    """One paper -> its library record, or None when it states no band."""
    text = PE.text_of(pdf)
    sp = S.split(text)
    if not any('cm-1' in x for x in sp[1]):
        return None, text
    bands = S._bands_of(sp[1])
    claims = S.check_claims(text, sp) if re.search(r'Bartlett|Libowitzky', text) else []
    try:
        lines = S.check_lines(text, None, cif, pdf)
    except Exception as e:
        lines = ['ERROR %s' % str(e)[:120]]
    rec = {'paper': os.path.basename(pdf),
           'bands': [[b.pos, b.technique, b.shape, b.family, b.mode, b.own] for b in bands],
           'claims': [[r['claim'].relation, r['claim'].text, r['claim'].band, r['claim'].mode, r['claim'].paired, r['status'], r['grade'],
                       None if r['calc'] is None else round(r['calc'], 4)] for r in claims],
           'lines': lines}
    return rec, text


def windows(recs):
    """{'group mode': {'technique': {'n', 'papers', 'p5' …}}} from the papers' own (not quoted) assigned bands."""
    acc = collections.defaultdict(lambda: collections.defaultdict(list))
    for rec in recs:
        seen = set()
        for pos, tech, _shape, fam, mode, own in rec['bands']:
            if not own or not fam or not ((mode in WINDOW_MODES and fam not in ('OH', 'M-O', 'CH', 'lattice', 'overtone')) or (fam, mode) in WINDOW_EXTRA):
                continue
            key = ('H2O', 'bend') if (fam, mode) == ('H2O', 2) else (fam, mode)
            for t in ('any', tech):
                if t and (key, t, pos) not in seen:
                    seen.add((key, t, pos)); acc[key][t].append((pos, rec['paper']))
    out = {}
    for key in sorted(acc, key=lambda k: (k[0], str(k[1]))):
        entry = {}
        for t in ('any', 'raman', 'ir'):
            v = acc[key].get(t) or []
            if len({p for _x, p in v}) < MIN_PAPERS:
                continue
            med = pct([x for x, _p in v], 50)
            sigma = max(1.4826 * pct([abs(x - med) for x, _p in v], 50), 5.0)
            kept = [(x, p) for x, p in v if abs(x - med) <= TRIM * sigma]
            papers = len({p for _x, p in kept})
            if papers >= MIN_PAPERS:
                xs = [x for x, _p in kept]
                entry[t] = dict({'n': len(xs), 'papers': papers, 'dropped': len(v) - len(kept)}, **{'p%d' % q: round(pct(xs, q)) for q in PCTS})
        if entry:
            out['%s %s' % (key[0], 'ν%d' % key[1] if isinstance(key[1], int) else key[1])] = entry
    return out


def diff(base, recs):
    """The papers whose findings or verdict counts changed since the baseline run."""
    old = {}
    for ln in open(base, encoding='utf-8'):
        r = json.loads(ln); old[r['paper']] = r
    def sig(r):
        return (sorted(collections.Counter((c[0], c[5], c[6]) for c in r['claims']).items(), key=str), [ln for ln in r['lines'] if ' vs ' in ln])
    lines = ['DIFF vs baseline (%d papers there, %d here):' % (len(old), len(recs))]
    n = 0
    for r in recs:
        o = old.get(r['paper'])
        if o is None:
            lines.append('  + %s (not in the baseline)' % r['paper']); n += 1
        elif sig(o) != sig(r):
            lines.append('  ~ %s' % r['paper']); n += 1
            lines += ['      was  %s' % (sig(o),), '      now  %s' % (sig(r),)]
    gone = sorted(set(old) - {r['paper'] for r in recs})
    lines += ['  - %s (no band read now)' % p for p in gone]
    nb0 = sum(len(o['bands']) for o in old.values()); nb1 = sum(len(r['bands']) for r in recs)
    na0 = sum(1 for o in old.values() for b in o['bands'] if b[3]); na1 = sum(1 for r in recs for b in r['bands'] if b[3])
    lines.append('  bands %d -> %d; assigned %d -> %d' % (nb0, nb1, na0, na1))
    if not n and not gone:
        lines.append('  no verdict changed')
    return lines


def main(pdf_dirs, out_dir, tag, baseline=None, only=None, subset=None, limit=None, build=False):
    jobs = [j for j in CPE._jobs(pdf_dirs, only, subset, limit)]
    recs = []; st = collections.Counter(); has = collections.Counter(); proof = []; windows_recs = []
    for pdf, cif, base in jobs:
        st['papers'] += 1
        try:
            rec, text = read_paper(pdf, cif)
        except Exception as e:
            st['errors'] += 1; sys.stderr.write('ERROR %s: %s\n' % (base, e)); continue
        try:
            f = PF.spectro_features(PF.raw_text(pdf) if PE._page_cache_dir is None else '\n'.join(pt.text for pt in PE._page_texts(pdf)))
        except Exception:
            f = {}
        for k, v in f.items():
            has[k] += bool(v)
        if rec is None:
            continue
        recs.append(rec)
        if not EXCLUDE.search(pdf):
            windows_recs.append(rec)
        st['with bands'] += 1; st['bands'] += len(rec['bands']); st['assigned'] += sum(1 for b in rec['bands'] if b[3])
        rels = {c[0][:3] for c in rec['claims']}
        for k in ('bc', 'lib'):
            if f.get(k):
                has[k + ' read'] += k in rels
                has[k + ' reproduced'] += any(c[0][:3] == k and c[5] == 'reproduced' for c in rec['claims'])
        if f.get('bands'):
            has['bands read'] += len(rec['bands']) >= 3
        for c in rec['claims']:
            st['claims'] += 1; st['%s %s %s' % (c[0], c[4] or '-', c[5])] += 1
            if c[2] is not None and c[7] is not None:
                proof.append((abs(c[7] - float(c[1])), rec['paper'], c[0], c[1], c[2], c[7], c[5]))
        st['flags'] += sum(1 for ln in rec['lines'] if ' vs ' in ln)
    L = ['SPECTROSCOPY over the corpus (pxrd_review.spectro) — %d papers' % st['papers'], '']
    L.append('STATS  papers %d; with bands %d; bands %d, assigned to a group %d (%.0f %%); stated distances %d; findings %d; errors %d' % (
        st['papers'], st['with bands'], st['bands'], st['assigned'], 100.0 * st['assigned'] / max(1, st['bands']), st['claims'], st['flags'], st['errors']))
    L += ['', 'READER vs what the paper prints (the denominator is tools/paper_features.spectro_features, which shares no code with the reader):']
    L.append('  three or more band positions   %4d papers; the reader has three or more on %d (%.0f %%)' % (has['bands'], has['bands read'], 100.0 * has['bands read'] / max(1, has['bands'])))
    for k, name in (('bc', 'Bartlett & Cooney'), ('lib', 'Libowitzky')):
        L.append('  a distance credited to %-18s %3d papers; read on %d (%.0f %%); a stated pair reproduced on %d' % (
            name, has[k], has[k + ' read'], 100.0 * has[k + ' read'] / max(1, has[k]), has[k + ' reproduced']))
    L += ['', 'STATED DISTANCES by relation, pairing and verdict:']
    L += ['  %4d  %s' % (v, k) for k, v in sorted(st.items()) if k.split(' ')[0] in ('bc', 'lib_oo', 'lib_ho')]
    L += ['', 'THE PROOF OF THE COEFFICIENTS — every band a paper prints beside the distance it gave, recomputed (%d pairs; the largest differences):' % len(proof)]
    L.append('  within 0.005 Å: %d; within 0.011: %d; within 0.02: %d; beyond: %d' % (
        sum(1 for p in proof if p[0] <= 0.005), sum(1 for p in proof if p[0] <= 0.011), sum(1 for p in proof if p[0] <= 0.02), sum(1 for p in proof if p[0] > 0.02)))
    for d, paper, rel, txt, band, calc, status in sorted(proof, reverse=True)[:25]:
        L.append('  %.3f  %-34s %-6s stated %s at %g cm-1, recomputed %.3f  [%s]' % (d, paper[:34], rel, txt, band, calc, status))
    L += ['', 'FINDINGS (every one is to be read against its paper):']
    for rec in recs:
        for ln in rec['lines']:
            if ' vs ' in ln:
                L.append('  %-34s %s' % (rec['paper'][:34], ln))
    L += ['', 'INFORMATION lines on stated distances (not findings):']
    for rec in recs:
        for ln in rec['lines'][1:]:
            if ' vs ' not in ln and not ln.startswith(('uranyl:', 'hydrogen bonds:')):
                L.append('  %-34s %s' % (rec['paper'][:34], ln))
    w = windows(windows_recs)
    L += ['', 'BAND WINDOWS (group, mode, technique: bands / papers, 5th–25th–50th–75th–95th percentile; a bin needs %d papers):' % MIN_PAPERS]
    for key, entry in w.items():
        for t, e in entry.items():
            L.append('  %-12s %-6s %4d / %3d   %5d %5d %5d %5d %5d   (%d dropped)' % (key, t, e['n'], e['papers'], e['p5'], e['p25'], e['p50'], e['p75'], e['p95'], e['dropped']))
    if baseline:
        L += [''] + diff(baseline, recs)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'spectra_library%s.jsonl' % tag), 'w', encoding='utf-8') as f:
        for rec in recs:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    with open(os.path.join(out_dir, 'spectra_report%s.txt' % tag), 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')
    if build:
        dest = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'pxrd_review', 'data', 'band_windows.json')
        doc = {'about': 'Where published mineral descriptions place each vibrational band: percentiles of the stated positions (cm-1) per group and mode. '
                        'Aggregates only; rebuilt by tools/corpus_spectra.py --build-windows.',
               'min_papers': MIN_PAPERS, 'percentiles': list(PCTS), 'trim_sigmas': TRIM, 'windows': w}
        with open(dest, 'w', encoding='utf-8') as f:
            json.dump(doc, f, indent=1, ensure_ascii=False, sort_keys=True); f.write('\n')
        L.append(''); L.append('windows written: %s (%d bins)' % (dest, sum(len(e) for e in w.values())))
    stats = next(k for k, ln in enumerate(L) if ln.startswith('STATS'))
    end = next(k for k, ln in enumerate(L) if ln.startswith('THE PROOF'))
    print('\n'.join(L[stats:end + 2]))
    if baseline:
        print('\n'.join(L[next(k for k, ln in enumerate(L) if ln.startswith('DIFF')):]))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('pdf_dirs', help='pdf + cif folders, comma-separated (searched recursively)')
    ap.add_argument('out_dir', nargs='?', default='/Users/travis/Desktop/Minerals_task_group/review_out')
    ap.add_argument('tag', nargs='?', default='')
    ap.add_argument('--baseline', help="an earlier run's spectra_library<tag>.jsonl to diff against")
    ap.add_argument('--papers', help='a file with one pdf basename per line (or a comma list): only those papers')
    ap.add_argument('--only', help='only papers whose file name contains this')
    ap.add_argument('--limit', type=int, help='stop after N papers')
    ap.add_argument('--build-windows', action='store_true', help='write pxrd_review/data/band_windows.json from this run')
    ap.add_argument('--no-cache', action='store_true', help='read every pdf with MuPDF instead of the page-text cache')
    a = ap.parse_args()
    if a.no_cache:
        os.environ.pop('PXRD_PAGE_CACHE', None); PE.set_page_cache(None)
    else:
        from pxrd_review import paths
        cache = os.environ.get('PXRD_PAGE_CACHE') or os.path.join(paths.cache_dir(), 'pages')
        os.environ['PXRD_PAGE_CACHE'] = cache; PE.set_page_cache(cache)
    subset = None
    if a.papers:
        subset = set(open(a.papers, encoding='utf-8').read().split()) if os.path.exists(a.papers) else set(x.strip() for x in a.papers.split(',') if x.strip())
    main(a.pdf_dirs.split(','), a.out_dir, a.tag, a.baseline, a.only, subset, a.limit, a.build_windows)
