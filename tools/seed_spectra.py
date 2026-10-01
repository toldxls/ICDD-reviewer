"""Recall of the spectroscopy checks: how wrong must a stated distance be before the tool says so?

    python3 tools/seed_spectra.py "<pdf folders, comma-separated>" [OUT_DIR] [TAG] [--papers LIST] [--only SUBSTR] [--limit N]

Every distance a paper credits to Bartlett & Cooney or to Libowitzky that the tool REPRODUCES from the paper's own
band is taken, and one fault is put into the sentence — in memory; no paper is touched:
  distance   the stated distance moved by 0.02, 0.03, 0.05 or 0.10 Å (a mistyped digit, a value carried over from
             another mineral)
  band       the stated wavenumber moved by 10, 20, 50 or 100 cm-1 (a transposed digit, another band's position)
and the checks are run again on the changed sentences. An outcome is
  CAUGHT  a finding (' vs ') the review would write,
  NOTED   an information line,
  MISSED  nothing said.
The table is per relation and per the way the sentence ties the distance to its band (pxrd_review.spectro.Claim.paired),
because that is what decides the grade: a pair the sentence makes itself can be a finding, a band taken from the
sentence before cannot. A fault whose number occurs twice in its sentence is not seeded (counted as 'ambiguous').
Output: OUT_DIR/seed_spectra<tag>.txt.
"""
import os, re, sys, argparse, collections

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pxrd_review import paper_extract as PE, spectro as S
import corpus_paper_extract as CPE

D_STEPS = (0.02, 0.03, 0.05, 0.10)
NU_STEPS = (10, 20, 50, 100)


def outcome(raw, sents, k):
    res = [r for r in S.check_claims(None, (raw, sents)) if r['claim'].sentence == sents[k]]
    if any(r['grade'] == 'flag' for r in res):
        return 'CAUGHT'
    if any(r['grade'] == 'info' for r in res):
        return 'NOTED'
    return 'MISSED'


def swap_once(sent, old, new):
    """The sentence with its one occurrence of the number `old` replaced, or None when it has none or several."""
    hits = [m for m in re.finditer(r'(?<![\d.])' + re.escape(old) + r'(?![\d.]\d|\d)', sent)]
    if len(hits) != 1:
        return None
    return sent[:hits[0].start()] + new + sent[hits[0].end():]


def seed_paper(pdf):
    """[(relation, paired, fault kind, size, outcome)] for one paper."""
    text = PE.text_of(pdf)
    if not re.search(r'Bartlett|Libowitzky', text):
        return []
    raw, sents = S.split(text)
    out = []
    for r in S.check_claims(text, (raw, sents)):
        c = r['claim']
        if r['status'] != 'reproduced' or c.paired not in ('band', 'mode', 'list', 'ctx', 'single'):
            continue
        k = sents.index(c.sentence)
        for step in D_STEPS:
            for sign in (1, -1):
                s2 = swap_once(sents[k], c.text, '%.*f' % (c.decimals, c.dist + sign * step))
                if s2 is None:
                    out.append((c.relation, c.paired, 'distance', step, 'ambiguous')); continue
                out.append((c.relation, c.paired, 'distance', step, outcome(raw, sents[:k] + [s2] + sents[k + 1:], k)))
        if c.band is None:
            continue
        j = k if c.paired != 'ctx' else next((i for i in range(k - 1, max(-1, k - 4), -1) if re.search(r'(?<!\d)%g(?!\d)' % c.band, sents[i])), None)
        if j is None:
            continue
        for step in NU_STEPS:
            for sign in (1, -1):
                s2 = swap_once(sents[j], '%g' % c.band, '%g' % (c.band + sign * step))
                if s2 is None:
                    out.append((c.relation, c.paired, 'band', step, 'ambiguous')); continue
                out.append((c.relation, c.paired, 'band', step, outcome(raw, sents[:j] + [s2] + sents[j + 1:], k)))
    return out


def main(pdf_dirs, out_dir, tag, only=None, subset=None, limit=None):
    acc = collections.defaultdict(collections.Counter); n_papers = 0
    for pdf, _cif, base in CPE._jobs(pdf_dirs, only, subset, limit):
        try:
            rows = seed_paper(pdf)
        except Exception as e:
            sys.stderr.write('ERROR %s: %s\n' % (base, e)); continue
        n_papers += bool(rows)
        for rel, paired, kind, step, res in rows:
            acc[(rel[:3], paired, kind, step)][res] += 1
    L = ['SEEDED FAULTS in the stated distances (pxrd_review.spectro) — %d papers with a reproduced pair' % n_papers, '',
         '  %-4s %-7s %-9s %6s   %6s %6s %6s   %s' % ('rel', 'paired', 'fault', 'size', 'CAUGHT', 'NOTED', 'MISSED', '(ambiguous, not seeded)')]
    for key in sorted(acc, key=lambda k: (k[0], k[1], k[2], k[3])):
        c = acc[key]; n = c['CAUGHT'] + c['NOTED'] + c['MISSED']
        L.append('  %-4s %-7s %-9s %6g   %6s %6s %6s   %d' % (key[0], key[1], key[2], key[3],
                 *('%d' % c[x] if not n else '%d %%' % round(100.0 * c[x] / n) for x in ('CAUGHT', 'NOTED', 'MISSED')), c['ambiguous']))
    L.append('')
    for rel in ('bc', 'lib'):
        for kind in ('distance', 'band'):
            tot = collections.Counter()
            for key, c in acc.items():
                if key[0] == rel and key[2] == kind and key[3] >= (0.05 if kind == 'distance' else 50):
                    tot.update(c)
            n = tot['CAUGHT'] + tot['NOTED'] + tot['MISSED']
            if n:
                L.append('  %s, a %s fault of %s or more: caught %d %%, noted %d %%, missed %d %% (n = %d)' % (
                    rel, kind, '0.05 Å' if kind == 'distance' else '50 cm-1', round(100.0 * tot['CAUGHT'] / n), round(100.0 * tot['NOTED'] / n), round(100.0 * tot['MISSED'] / n), n))
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'seed_spectra%s.txt' % tag), 'w', encoding='utf-8') as f:
        f.write('\n'.join(L) + '\n')
    print('\n'.join(L))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('pdf_dirs', help='pdf folders, comma-separated (searched recursively)')
    ap.add_argument('out_dir', nargs='?', default='/Users/travis/Desktop/Minerals_task_group/review_out')
    ap.add_argument('tag', nargs='?', default='')
    ap.add_argument('--papers'); ap.add_argument('--only'); ap.add_argument('--limit', type=int)
    a = ap.parse_args()
    from pxrd_review import paths
    cache = os.environ.get('PXRD_PAGE_CACHE') or os.path.join(paths.cache_dir(), 'pages')
    os.environ['PXRD_PAGE_CACHE'] = cache; PE.set_page_cache(cache)
    subset = None
    if a.papers:
        subset = set(open(a.papers, encoding='utf-8').read().split()) if os.path.exists(a.papers) else set(x.strip() for x in a.papers.split(',') if x.strip())
    main(a.pdf_dirs.split(','), a.out_dir, a.tag, a.only, subset, a.limit)
