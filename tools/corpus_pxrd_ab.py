"""A/B of the powder-table reader (paper_extract.pxrd_table) over a corpus of papers, with the cell
metric: for a paper whose .cif is beside it (matched by the I-number in the file names), d recomputed
from the .cif cell and the parsed h k l must agree with the parsed d within 0.5 % — the one rigorous
test of whether the indices are paired with the right d. Output: review_out/pxrd_ab_<tag>.json + .txt.

    python3 tools/corpus_pxrd_ab.py "<pdf folders, comma-separated>" [--baseline path/to/paper_extract.py]
                                    [--pages fitz|docling] [--out DIR] [--tag TAG]

--baseline is a copy of an earlier paper_extract.py (e.g. `git show v0.5.5:pxrd_review/paper_extract.py
> /tmp/pe_0.5.5.py`); without it the run reports the current reader alone. --pages docling reads the
tables through the layout reader (pxrd_review.layout_reader) for the B side.

Per paper: [obs, calc, suspect, calc rows with a cell, of which consistent]. Suspect = an index beyond
±30, an intensity above 1000, or a d outside 0.5–40 Å — garbage a reader made up. ALWAYS read the
losers' header lines and first rows before trusting a count: count-level A/B once judged a fallback's
made-up index triples as "lines"."""
import os, re, sys, glob, json, time, math, argparse, importlib.util

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pxrd_review import paper_extract as PE
from pxrd_review import extra_checks as X

DEFAULT_OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'review_out')


def load_module(path, name='paper_extract_baseline'):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def find_pdfs_and_cifs(folders):
    """{basename: pdf path} (the first of duplicate names wins) and {I-number: cif path}."""
    pdfs, cifs = {}, {}
    for root in folders:
        for p in sorted(glob.glob(os.path.join(root, '**', '*.pdf'), recursive=True)):
            if 'review_out' in p:
                continue
            pdfs.setdefault(os.path.basename(p), p)
        for c in glob.glob(os.path.join(root, '**', '*.cif'), recursive=True):
            for m in re.findall(r'I\d{5,6}', os.path.basename(c)):
                cifs.setdefault(m, c)
    return pdfs, cifs


def cell_of(name, cifs):
    for m in re.findall(r'I\d{5,6}', name):
        c = cifs.get(m)
        if not c:
            continue
        cell = PE._cell_floats((X.parse_cif(c) or {}).get('cell') or {})
        if cell:
            return cell
    return None


def consistent(cell, calc):
    """(rows with a computable d, rows within 0.5 %) — a lost overbar is not held against a row."""
    n = ok = 0
    for d, I, hkl in calc:
        if hkl == (0, 0, 0) or not d:
            continue
        ds = PE._d_variants(cell, hkl)
        if not ds:
            continue
        n += 1
        ok += 1 if min(abs(dc - d) / d for dc, _ in ds) <= 0.005 else 0
    return n, ok


def stats(o, c):
    bad = sum(1 for d, I in o if not (0.5 <= d <= 40) or (I is not None and I > 1000))
    bad += sum(1 for d, I, h in c if not (0.5 <= d <= 40) or (I is not None and I > 1000) or any(abs(x) > 30 for x in h))
    return [len(o), len(c), bad]


def run(folders, baseline=None, pages='fitz', out_dir=DEFAULT_OUT, tag='', with_cif=False, limit=0):
    pdfs, cifs = find_pdfs_and_cifs(folders)
    if with_cif:                                                         # only the papers the cell metric can judge
        pdfs = {n: p for n, p in pdfs.items() if cell_of(n, cifs)}
    if limit:
        pdfs = dict(sorted(pdfs.items())[:limit])
    A = load_module(baseline) if baseline else None
    if pages.startswith('docling'):
        from pxrd_review import layout_reader as LR
        if not LR.available():
            sys.exit('--pages docling: the layout reader is not available (pip install "pxrd-review[layout]")')
        PE.set_pages_reader(LR.pages, 'replace' if pages == 'docling-replace' else 'fallback')
    agg = {'A': [0] * 5, 'B': [0] * 5}; cases = []; t0 = time.time(); secs = []
    for i, (name, p) in enumerate(sorted(pdfs.items())):
        cell = cell_of(name, cifs)
        try:
            tb = time.time(); b = PE.pxrd_table(p); secs.append(time.time() - tb)
        except Exception as ex:
            cases.append({'pdf': name, 'error': str(ex)[:120]}); continue
        sb = stats(*b) + list(consistent(cell, b[1]) if cell else (0, 0))
        for k in range(5):
            agg['B'][k] += sb[k]
        rec = {'pdf': name, 'B': sb, 'Bc': b[1][:2], 'Bo': b[0][:1]}
        if A is not None:
            try:
                a = A.pxrd_table(p)
            except Exception as ex:
                a = ([], [])
            sa = stats(*a) + list(consistent(cell, a[1]) if cell else (0, 0))
            for k in range(5):
                agg['A'][k] += sa[k]
            rec.update({'A': sa, 'Ac': a[1][:2], 'Ao': a[0][:1], 'changed': a != b})
        cases.append(rec)
        if i % 100 == 0:
            print('%d/%d %.0fs' % (i, len(pdfs), time.time() - t0), flush=True)
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.join(out_dir, 'pxrd_ab' + ('_' + tag if tag else ''))
    json.dump({'folders': folders, 'baseline': baseline, 'pages': pages, 'agg': agg, 'cases': cases}, open(stem + '.json', 'w'), indent=0)
    lines = ['pxrd_table over %d papers (%d with a .cif cell)%s' % (len(pdfs), sum(1 for c in cases if c.get('B') and c['B'][3]), ' — pages: ' + pages),
             'totals [obs, calc, suspect, calc rows with a cell, consistent]:']
    if A is not None:
        lines.append('  A (baseline %s): %s' % (os.path.basename(baseline), agg['A']))
    lines.append('  B (current):      %s' % agg['B'])
    if secs:
        secs.sort(); lines.append('  B seconds per paper: median %.1f, max %.1f (%d papers)' % (secs[len(secs) // 2], secs[-1], len(secs)))
    if A is not None:
        ch = [c for c in cases if c.get('changed')]
        loss = [c for c in ch if c['B'][0] + c['B'][1] < c['A'][0] + c['A'][1]]
        worse = [c for c in ch if c['B'][2] > c['A'][2]]
        lesscons = [c for c in ch if c['A'][3] and c['B'][3] and c['B'][4] / c['B'][3] < c['A'][4] / c['A'][3] - 0.1]
        lines.append('changed %d, lost lines %d, more suspect %d, less cell-consistent %d' % (len(ch), len(loss), len(worse), len(lesscons)))
        lines.append('=== LOST LINES   A -> B | first calc A | B')
        for c in sorted(loss, key=lambda c: (c['A'][0] + c['A'][1]) - (c['B'][0] + c['B'][1]), reverse=True)[:40]:
            lines.append('  %-40s %s -> %s | %s | %s' % (c['pdf'][:40], c['A'], c['B'], c['Ac'][:1], c['Bc'][:1]))
        lines.append('=== MORE SUSPECT / LESS CONSISTENT')
        for c in worse + [c for c in lesscons if c not in worse]:
            lines.append('  %-40s %s -> %s | %s | %s' % (c['pdf'][:40], c['A'], c['B'], c['Ac'][:1], c['Bc'][:1]))
    with open(stem + '.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('\n'.join(lines[:6]))
    print('wrote', stem + '.txt')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('folders', help='pdf folders, comma-separated (searched recursively)')
    ap.add_argument('--baseline', help='a copy of an earlier paper_extract.py for the A side')
    ap.add_argument('--pages', default='fitz', choices=['fitz', 'docling', 'docling-replace'], help='docling = fitz first, the layout model where fitz reads no table on a page; docling-replace = every page through the layout model')
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--tag', default='')
    ap.add_argument('--with-cif', action='store_true', help='only the papers whose .cif is beside them (the cell metric)')
    ap.add_argument('--limit', type=int, default=0, help='the first N papers (a timing run)')
    a = ap.parse_args()
    run([f.strip() for f in a.folders.split(',') if f.strip()], a.baseline, a.pages, a.out, a.tag, a.with_cif, a.limit)
