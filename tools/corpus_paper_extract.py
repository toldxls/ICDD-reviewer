"""Corpus hardening of the paper checks: every paper .pdf against itself (composition from its own table,
basis and method vs its own formula) and against its .cif (bond-valence table). Output: review_out/paper_checks_*.

    python3 tools/corpus_paper_extract.py "<entries roots, comma-separated>" "<pdf folders, comma-separated>"
"""
import os, re, sys, glob, csv
from pxrd_review import extra_checks as X, epma as EP, paper_extract as PE

def main(roots, pdf_dirs, out_dir, tag=''):
    """Every paper .pdf (paired with its .cif when one shares the I-number): what the extractor
    reads, the paper's formula re-derived from its own table and basis, its bond-valence table vs
    the .cif. The verdicts are the tool's, for the owner to check one by one."""
    stats = {'pdfs': 0, 'table': 0, 'formula': 0, 'comp_checked': 0, 'comp_ok': 0, 'comp_flag': 0, 'comp_unverified': 0, 'bv_checked': 0, 'bv_clean': 0, 'basis': 0, 'n': 0, 'D': 0, 'bvset': 0, 'pxrd': 0}
    lines = []; rows = []; seen = set()
    for pd in pdf_dirs:
        for pdf in sorted(glob.glob(os.path.join(pd, '**', '*.pdf'), recursive=True)):
            if 'review_out' in pdf:
                continue
            base = os.path.basename(pdf)
            if re.search(r'supp|tables?\b', base, re.I):
                continue
            ids = set(re.findall(r'I\d{6}', base)); key = tuple(sorted(ids)) or base
            if key in seen:
                continue
            seen.add(key)
            cif = next((c for c in glob.glob(os.path.join(os.path.dirname(pdf), '*.cif')) if any(i in os.path.basename(c) for i in ids)), None) if ids else None
            try:
                r = PE.check_paper(pdf, cif, None)
            except Exception as e:
                lines.append('==== %-40s ERROR %s' % (base, e)); rows.append([base, 'error', str(e)[:200], '']); continue
            stats['pdfs'] += 1
            ex = r['extract']; summary = []
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
    os.makedirs(out_dir, exist_ok=True)
    open(os.path.join(out_dir, 'paper_checks_report%s.txt' % tag), 'w', encoding='utf-8').write(
        'Paper self-checks (pxrd-review 0.5.4): the composition re-derived from the paper\'s own table, basis and method\n'
        'against its own empirical formula; its bond-valence table (read from the pdf) against the .cif. Rerun:\n'
        '  python3 tools/corpus_paper_extract.py "<unused>" "<pdf+cif folders, comma-separated>"\n\n' + '\n'.join(lines) + '\n')
    with open(os.path.join(out_dir, 'paper_checks_faults%s.tsv' % tag), 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, delimiter='\t'); w.writerow(['paper', 'kind', 'detail', 'checked / verdict']); w.writerows(rows)
    print('\n'.join(lines[-3:]))

if __name__ == '__main__':
    main(sys.argv[1].split(','), sys.argv[2].split(','), sys.argv[3] if len(sys.argv) > 3 else '/Users/travis/Desktop/Minerals_task_group/review_out', sys.argv[4] if len(sys.argv) > 4 else '')
