"""Corpus hardening of the paper checks: every paper .pdf against itself (composition from its own table,
basis and method vs its own formula) and against its .cif (bond-valence table). Output: review_out/paper_checks_*.

    python3 tools/corpus_paper_extract.py "<unused>" "<pdf folders, comma-separated>" [OUT_DIR] [TAG]
                                          [--baseline paper_checks_papers_<tag>.json] [--limit N] [--only SUBSTR] [--papers LIST]

--papers (a file of basenames, or a comma list) runs a subset: the papers a change could touch plus a sample,
diffed against the baseline record — the owner's rule, a full run being half an hour.

--baseline diffs this run's per-paper record (paper_checks_papers<tag>.json, written every run) against an
earlier run's: the readers whose status changed, paper by paper. That is the A/B for a reader change — the
baseline is the record of the old code, so no worktree or module copy is needed.
"""
import os, re, sys, glob, csv, json, argparse
from pxrd_review import extra_checks as X, epma as EP, paper_extract as PE

READERS = ('epma', 'formula', 'basis', 'method', 'optics.n', 'optics.D_meas', 'optics.D_calc', 'cell', 'bv.params', 'pxrd.obs', 'pxrd.calc', 'name')


def paper_record(r, ex, cif, text):
    """What one paper's run leaves behind, for the diff: every field's status and detail, the
    composition verdict and its doubts, the bond-valence and powder outcomes, and whether the text
    prints a Z at all (the density oracle needs one)."""
    fields = {k: {'status': v['status'], 'detail': (v.get('detail') or '')[:120], 'value': (str(v['value'])[:40] if v.get('value') not in (None, '') else None)}
              for k, v in (r.get('fields') or {}).items()}
    c = r.get('composition'); p = r.get('powder') or {}; o = ex.get('optics') or {}
    return {'fields': fields,
            'composition': None if not c else 'ok' if c['ok'] else 'flag' if c.get('verified') else 'unverified',
            'doubts': [d[:100] for d in ((c or {}).get('doubts') or [])],
            'bv': {'status': r.get('bv_status'), 'disagree': (r.get('bv') or {}).get('disagree'), 'compared': (r.get('bv') or {}).get('compared'),
                   'from_paper': bool(r.get('paper_structure'))},
            'powder': {'status': p.get('status'), 'n': p.get('n'), 'agree': p.get('agree'), 'loose': p.get('loose'), 'source': p.get('source'),
                       'nobs': ex['pxrd']['obs'], 'ncalc': ex['pxrd']['calc'], 'unmatched': len(p.get('unmatched_obs') or []), 'off_cell': len(p.get('off_cell') or []),
                       'bad': len(p.get('bad') or []), 'wild': p.get('wild'), 'red': [l[:150] for l in (p.get('lines') or []) if 'does not follow the cell:' in l][:6],
                       'notes': [l[:60] for l in (p.get('lines') or []) if 'follows no cell' in l or 'off — computed' in l or "the .cif's cell" in l]},
            'D_calc': o.get('D_calc'), 'D_meas': o.get('D_meas'), 'cif': bool(cif),
            'Z_eq': bool(re.search(r'\bZ\s*=\s*\d{1,2}\b', text)), 'Z_any': bool(re.search(r'(?<![A-Za-z])Z\s*[=:]?\s*\d{1,2}\b', text))}


def diff(base, papers, limit=8):
    """The readers whose status changed between two runs, paper by paper -> lines."""
    lines = ['DIFF vs baseline (%d papers in both):' % len(set(base) & set(papers))]
    for fld in READERS:
        trans = {}
        for name in sorted(set(base) & set(papers)):
            a = (base[name]['fields'].get(fld) or {}).get('status', 'none'); b = (papers[name]['fields'].get(fld) or {}).get('status', 'none')
            if a != b:
                trans.setdefault((a, b), []).append(name)
        for (a, b), names in sorted(trans.items(), key=lambda kv: -len(kv[1])):
            lines.append('  %-14s %-11s -> %-11s %3d  %s%s' % (fld, a, b, len(names), ', '.join(n[:28] for n in names[:limit]), ' …' if len(names) > limit else ''))
    trans = {}
    for name in sorted(set(base) & set(papers)):
        a, b = base[name]['composition'], papers[name]['composition']
        if a != b:
            trans.setdefault((a, b), []).append(name)
    for (a, b), names in sorted(trans.items(), key=lambda kv: -len(kv[1])):
        lines.append('  %-14s %-11s -> %-11s %3d  %s%s' % ('composition', a, b, len(names), ', '.join(n[:28] for n in names[:limit]), ' …' if len(names) > limit else ''))
    if len(lines) == 1:
        lines.append('  no status changed')
    return lines


def main(roots, pdf_dirs, out_dir, tag='', baseline=None, limit=None, only=None, subset=None):
    """Every paper .pdf (paired with its .cif when one shares the I-number): what the extractor
    reads, the paper's formula re-derived from its own table and basis, its bond-valence table vs
    the .cif. The verdicts are the tool's, for the owner to check one by one."""
    stats = {'pdfs': 0, 'table': 0, 'formula': 0, 'comp_checked': 0, 'comp_ok': 0, 'comp_flag': 0, 'comp_unverified': 0, 'bv_checked': 0, 'bv_clean': 0, 'basis': 0, 'n': 0, 'D': 0, 'bvset': 0, 'pxrd': 0}
    lines = []; rows = []; seen = set(); papers = {}
    readers = {}                                                          # field -> {status: count}: the per-reader verified rate, the standing metric
    for pd in pdf_dirs:
        for pdf in sorted(glob.glob(os.path.join(pd, '**', '*.pdf'), recursive=True)):
            if 'review_out' in pdf:
                continue
            base = os.path.basename(pdf)
            if re.search(r'supp|tables?\b', base, re.I):
                continue
            if only and only not in base:
                continue
            if subset is not None and base not in subset:
                continue                                                  # a subset: the papers a change could touch, plus a sample — a full run costs half an hour
            ids = set(re.findall(r'I\d{6}', base)); key = tuple(sorted(ids)) or base
            if key in seen:
                continue
            seen.add(key)
            if limit and len(seen) > limit:
                break
            cif = next((c for c in glob.glob(os.path.join(os.path.dirname(pdf), '*.cif')) if any(i in os.path.basename(c) for i in ids)), None) if ids else None
            try:
                r = PE.check_paper(pdf, cif, None)
            except Exception as e:
                lines.append('==== %-40s ERROR %s' % (base, e)); rows.append([base, 'error', str(e)[:200], '']); continue
            stats['pdfs'] += 1
            ex = r['extract']; summary = []
            for fld, rec in (r.get('fields') or {}).items():
                readers.setdefault(fld, {}); readers[fld][rec['status']] = readers[fld].get(rec['status'], 0) + 1
            try:
                papers[base] = paper_record(r, ex, cif, PE.text_of(pdf))
            except Exception as e:
                papers[base] = {'fields': {}, 'composition': None, 'error': str(e)[:100]}
            if ex['epma']:
                stats['table'] += 1; summary.append('table %d' % len(ex['epma']['rows']))
            c = r['composition']
            if c:
                stats['formula'] += 1; stats['comp_checked'] += 1
                if c['ok']:
                    stats['comp_ok'] += 1; summary.append('composition OK')
                elif c.get('verified'):
                    stats['comp_flag'] += 1; summary.append('composition FLAG')
                    for ln in c['lines'][1:]:
                        rows.append([base, 'composition flag', ln.strip(), ''])
                else:
                    stats['comp_unverified'] += 1; summary.append('composition unverified')
                    for ln in c['lines'][1:]:
                        rows.append([base, 'composition unverified', ln.strip(), ''])
            elif ex['epma']:
                summary.append('no formula sentence')
            if ex['basis']: stats['basis'] += 1
            if ex['optics']['n']: stats['n'] += 1
            if ex['optics']['D_meas'] or ex['optics']['D_calc']: stats['D'] += 1
            if ex['bv']['params']: stats['bvset'] += 1
            if ex['pxrd']['obs'] or ex['pxrd']['calc']: stats['pxrd'] += 1; summary.append('pxrd %d/%d' % (ex['pxrd']['obs'], ex['pxrd']['calc']))
            b = r['bv']
            if b:
                stats['bv_checked'] += 1
                if b['disagree'] == 0:
                    stats['bv_clean'] += 1
                summary.append('bv %d/%d disagree (%s%s)' % (b['disagree'], b['compared'], b['params'], '' if (b['params'], b['u6']) == b['cited'] else ', paper cites ' + b['cited'][0]))
                for ln in b['lines'][1:]:
                    rows.append([base, 'bond valence', ln.strip(), ''])
            elif cif:
                summary.append('bv: no table found in the pdf')
            lines.append('==== %-40s %s' % (base, ' | '.join(summary) or 'nothing read'))
            for ln in r['lines']:
                lines.append('     ' + ln[:220])
    lines.append(''); lines.append('STATS %s' % stats)
    # the powder table against the cell, corpus-wide (what tools/corpus_cell_survey.py used to report):
    # the statuses, and the red list — a red line names a row of the paper, and the row decides whether
    # it is the paper's error or the reader's pairing, so it is read line by line
    pw = [(name, r_['powder']) for name, r_ in papers.items() if r_.get('powder')]
    chk = [(n_, q) for n_, q in pw if q.get('status') == 'checked']
    lines.append('POWDER vs CELL: %s' % ', '.join('%s %d' % (st, sum(1 for _, q in pw if q.get('status') == st)) for st in ('checked', 'unindexed', 'nocell', 'none', 'error') if any(q.get('status') == st for _, q in pw)))
    lines.append('  checked %d: red lines in %d papers (%d lines); follows no cell %d; shifted throughout %d; .cif in another setting %d; observed lines on no reflection in %d papers' % (
        len(chk), sum(1 for _, q in chk if q.get('bad')), sum(q.get('bad') or 0 for _, q in chk), sum(1 for _, q in chk if any('follows no cell' in x for x in q.get('notes') or [])),
        sum(1 for _, q in chk if any('off — computed' in x for x in q.get('notes') or [])), sum(1 for _, q in chk if any(".cif's cell" in x for x in q.get('notes') or [])),
        sum(1 for _, q in chk if q.get('off_cell'))))
    for n_, q in sorted(chk, key=lambda x: -(x[1].get('bad') or 0)):
        if q.get('bad'):
            lines.append('  %-36s %-8s %3s/%-3s' % (n_[:36], q.get('source'), q.get('agree'), q.get('n')))
            lines += ['      ' + x for x in q.get('red') or []]
    os.makedirs(out_dir, exist_ok=True)
    table = [['reader', 'read', 'verified', 'agree', 'disagree', 'unverified', 'nooracle', 'verified rate']]
    for fld in READERS:
        c = readers.get(fld, {}); read = sum(v for k, v in c.items() if k != 'none'); ver = c.get('agrees', 0) + c.get('disagrees', 0)
        table.append([fld, read, ver, c.get('agrees', 0), c.get('disagrees', 0), c.get('unverified', 0), c.get('nooracle', 0), '%.0f %%' % (100.0 * ver / read) if read else '—'])
    lines.append('READERS (what was read, and how much of it an oracle adjudicated):')
    for row in table:
        lines.append('  ' + '  '.join('%-14s' % str(x) for x in row))
    if baseline:
        with open(baseline, encoding='utf-8') as f:
            lines += [''] + diff(json.load(f), papers)
    with open(os.path.join(out_dir, 'paper_checks_readers%s.csv' % tag), 'w', encoding='utf-8', newline='') as f:
        csv.writer(f).writerows(table)
    with open(os.path.join(out_dir, 'paper_checks_papers%s.json' % tag), 'w', encoding='utf-8') as f:
        json.dump(papers, f, indent=0, ensure_ascii=False)
    open(os.path.join(out_dir, 'paper_checks_report%s.txt' % tag), 'w', encoding='utf-8').write(
        'Paper self-checks (pxrd-review 0.5.5+): the composition re-derived from the paper\'s own table, basis and method\n'
        'against its own empirical formula; its bond-valence table (read from the pdf) against the .cif. Rerun:\n'
        '  python3 tools/corpus_paper_extract.py "<unused>" "<pdf+cif folders, comma-separated>" [OUT_DIR] [TAG] [--baseline JSON]\n\n' + '\n'.join(lines) + '\n')
    with open(os.path.join(out_dir, 'paper_checks_faults%s.tsv' % tag), 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, delimiter='\t'); w.writerow(['paper', 'kind', 'detail', 'checked / verdict']); w.writerows(rows)
    tail = next(k for k, ln in enumerate(lines) if ln.startswith('STATS '))
    print('\n'.join(lines[tail:]))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('roots', help='entries roots (unused; kept for the older call form)')
    ap.add_argument('pdf_dirs', help='pdf + cif folders, comma-separated (searched recursively)')
    ap.add_argument('out_dir', nargs='?', default='/Users/travis/Desktop/Minerals_task_group/review_out')
    ap.add_argument('tag', nargs='?', default='')
    ap.add_argument('--baseline', help='an earlier run\'s paper_checks_papers<tag>.json to diff against')
    ap.add_argument('--limit', type=int, help='stop after N papers (a smoke run)')
    ap.add_argument('--only', help='only papers whose file name contains this')
    ap.add_argument('--papers', help='a file with one pdf basename per line (or a comma list): only those papers — a subset run')
    a = ap.parse_args()
    subset = None
    if a.papers:
        subset = set(open(a.papers, encoding='utf-8').read().split()) if os.path.exists(a.papers) else set(x.strip() for x in a.papers.split(',') if x.strip())
    main(a.roots.split(','), a.pdf_dirs.split(','), a.out_dir, a.tag, a.baseline, a.limit, a.only, subset)
