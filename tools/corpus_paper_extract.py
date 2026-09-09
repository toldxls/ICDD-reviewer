"""Corpus hardening of the paper checks: every paper .pdf against itself (composition from its own table,
basis and method vs its own formula) and against its .cif (bond-valence table). Output: review_out/paper_checks_*.

    python3 tools/corpus_paper_extract.py "<unused>" "<pdf folders, comma-separated>" [OUT_DIR] [TAG]
                                          [--baseline paper_checks_papers_<tag>.json] [--limit N] [--only SUBSTR] [--papers LIST]

--papers (a file of basenames, or a comma list) runs a subset: the papers a change could touch plus a sample,
diffed against the baseline record — the owner's rule, a full run being half an hour.

--jobs runs the papers in worker processes (default: the machine's cores, capped at 8; --jobs 1 is the serial
path, in-process). The papers are independent, so this is wall-clock only: results are folded in JOB order, so
every output file is byte-identical to a serial run. That equality is the acceptance test for the flag, and it
matters because these files exist to be diffed against each other.

--baseline diffs this run's per-paper record (paper_checks_papers<tag>.json, written every run) against an
earlier run's: the readers whose status changed, paper by paper. That is the A/B for a reader change — the
baseline is the record of the old code, so no worktree or module copy is needed.
"""
import os, re, sys, glob, csv, json, argparse
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # runnable from any cwd — and spawn hands this path to every worker
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pxrd_review import paper_extract as PE
import paper_features as PF

_CTX = mp.get_context('spawn')          # the context the GUI's page worker already uses (pxrd_review/gui/_pdf_worker.py)

READERS = ('epma', 'formula', 'basis', 'method', 'optics.n', 'optics.D_meas', 'optics.D_calc', 'gd', 'cell', 'coords', 'bv.params', 'bv.table', 'pxrd.obs', 'pxrd.calc', 'name')
GAUNTLET = ('epma', 'formula', 'bv.table', 'bv.params', 'coords', 'gd', 'optics.n', 'cell')   # the readers the gauntlet reports on S


def paper_record(r, ex, cif, text, has=None):
    """What one paper's run leaves behind, for the diff: every field's status and detail, the
    composition verdict and its doubts, the bond-valence and powder outcomes, and whether the text
    prints a Z at all (the density oracle needs one). `has` is what the paper PRINTS by the crude
    reader-independent scan (tools/paper_features.py): the gauntlet's denominator."""
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
            'Z_eq': bool(re.search(r'\bZ\s*=\s*\d{1,2}\b', text)), 'Z_any': bool(re.search(r'(?<![A-Za-z])Z\s*[=:]?\s*\d{1,2}\b', text)),
            'coords': {k: (r.get('coords') or {}).get(k) for k in ('status', 'gii', 'closure', 'closure_count', 'matched', 'n', 'sites', 'bonds_ok', 'bonds_n', 'bonds_total')},
            'has': has or {}}


def gauntlet_lines(papers, base=None, limit=8):
    """The gauntlet: on S — the papers whose text prints an EPMA table, a bond-valence table, a
    coordinates table, a compatibility index and optics, by the crude scan — how many of them each
    reader VERIFIES (agrees / |S|), the composite, the worklist, and the diff restricted to S. The
    denominator is the scan's, never the readers': a reader cannot raise its rate by reading less."""
    S = [n for n, r in papers.items() if PF.is_target(r.get('has'))]
    out = ['GAUNTLET: S = %d papers whose text prints an EPMA table, a bond-valence table, a coordinates table, a compatibility index and optics (of %d)'
           % (len(S), len(papers))]
    if not S:
        return out
    stat = lambda n, fld: ((papers[n].get('fields') or {}).get(fld) or {}).get('status', 'none')
    out.append('  %-12s %8s  %-40s %s' % ('reader', 'agrees', 'other statuses', 'first not agreeing'))
    for fld in GAUNTLET:
        c = {}
        for n in S:
            s = stat(n, fld); c[s] = c.get(s, 0) + 1
        a = c.get('agrees', 0)
        others = ', '.join('%s %d' % (k, c[k]) for k in ('disagrees', 'unverified', 'nooracle', 'none') if c.get(k))
        names = [n for n in S if stat(n, fld) != 'agrees'][:limit]
        out.append('  %-12s %3d %3.0f %%  %-40s %s' % (fld, a, 100.0 * a / len(S), others[:40], ', '.join(x[:28] for x in names)))
    def all_agree(n, flds):
        return all(stat(n, f) == 'agrees' for f in flds)
    a3 = sum(1 for n in S if all_agree(n, ('epma', 'bv.params', 'optics.n')))
    a4 = sum(1 for n in S if all_agree(n, ('epma', 'bv.table', 'coords', 'gd')))
    out.append('  composite: table + bond-valence set + n all agree %d/%d; table + bond-valence table + coordinates + compatibility all agree %d/%d' % (a3, len(S), a4, len(S)))
    if base is not None:
        bS = {n: base[n] for n in S if n in base}
        if not bS:
            out.append('  (the baseline carries none of these papers)')
        else:
            out.append('  DIFF on S:')
            out += ['  ' + ln for ln in diff(bS, {n: papers[n] for n in S})[1:]]
    return out


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


def _jobs(pdf_dirs, only=None, subset=None, limit=None):
    """The papers to run, in the order the serial walk visited them -> [(pdf, cif, base)].
    A verbatim transcription of that walk: `seen` is shared across pdf_dirs and the limit is
    tested AFTER the key is added, so `--limit N` yields exactly N papers, drawn from the
    earliest directories; `--limit 0` is falsy and means no limit. The .cif is paired here,
    in the parent, so the unsorted glob that picks it cannot vary from worker to worker."""
    jobs = []; seen = set()
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
            jobs.append((pdf, cif, base))
    return jobs


def _run_one(job):
    """One paper's checks — what the serial loop body did, as a payload the parent folds in:
      {'base', 'record', 'readers': [(field, status)], 'stats': {key: n}, 'lines': [...], 'rows': [[...]]}
      {'base', 'fail': <message>}   when check_paper itself raised
    Only primitives cross the process boundary: check_paper's own return value stays here (it
    carries an epma.Reduction and the whole read of the paper), and nothing in this path writes
    to disk — extract() writes its data files only when it is given an out_dir, and it is not."""
    pdf, cif, base = job
    try:
        r = PE.check_paper(pdf, cif, None)
    except Exception as e:
        return {'base': base, 'fail': str(e)}
    st = {}; readers = []; lines = []; rows = []
    def bump(k):
        st[k] = st.get(k, 0) + 1
    bump('pdfs')
    ex = r['extract']; summary = []
    for fld, rec in (r.get('fields') or {}).items():
        readers.append((fld, rec['status']))
    try:
        has = PF.features(PF.raw_text(pdf))                              # what the paper prints, read independently of every reader above
    except Exception:
        has = {}
    try:
        record = paper_record(r, ex, cif, PE.text_of(pdf), has)
    except Exception as e:
        record = {'fields': {}, 'composition': None, 'error': str(e)[:100], 'has': has}
    if ex['epma']:
        bump('table'); summary.append('table %d' % len(ex['epma']['rows']))
    c = r['composition']
    if c:
        bump('formula'); bump('comp_checked')
        if c['ok']:
            bump('comp_ok'); summary.append('composition OK')
        elif c.get('verified'):
            bump('comp_flag'); summary.append('composition FLAG')
            for ln in c['lines'][1:]:
                rows.append([base, 'composition flag', ln.strip(), ''])
        else:
            bump('comp_unverified'); summary.append('composition unverified')
            for ln in c['lines'][1:]:
                rows.append([base, 'composition unverified', ln.strip(), ''])
    elif ex['epma']:
        summary.append('no formula sentence')
    if ex['basis']: bump('basis')
    if ex['optics']['n']: bump('n')
    if ex['optics']['D_meas'] or ex['optics']['D_calc']: bump('D')
    if ex['bv']['params']: bump('bvset')
    if ex['pxrd']['obs'] or ex['pxrd']['calc']: bump('pxrd'); summary.append('pxrd %d/%d' % (ex['pxrd']['obs'], ex['pxrd']['calc']))
    b = r['bv']
    if b:
        bump('bv_checked')
        if b['disagree'] == 0:
            bump('bv_clean')
        summary.append('bv %d/%d disagree (%s%s)' % (b['disagree'], b['compared'], b['params'], '' if (b['params'], b['u6']) == b['cited'] else ', paper cites ' + b['cited'][0]))
        for ln in b['lines'][1:]:
            rows.append([base, 'bond valence', ln.strip(), ''])
    elif cif:
        summary.append('bv: no table found in the pdf')
    lines.append('==== %-40s %s' % (base, ' | '.join(summary) or 'nothing read'))
    for ln in r['lines']:
        lines.append('     ' + ln[:220])
    return {'base': base, 'record': record, 'readers': readers, 'stats': st, 'lines': lines, 'rows': rows}


def _kill(pool):
    """Tear a pool down hard. shutdown() alone cannot stop a worker wedged inside native MuPDF
    code, so the process would keep the CPU behind the dead pool (pxrd_review/gui/_pdf_worker)."""
    try:
        pool.shutdown(wait=False, cancel_futures=True)
    except Exception:
        pass
    for proc in (getattr(pool, '_processes', None) or {}).values():
        try:
            proc.kill()
        except Exception:
            pass


def _map_ordered(jobs, n_jobs):
    """_run_one over the jobs in worker processes -> [payload], IN JOB ORDER. The order is the
    point: papers[] insertion order is the .json's order and breaks ties in the report's powder
    list, and lines/rows are the report and the TSV, so folding by completion would change three
    of the four output files.

    A worker can die outright — MuPDF segfaults uncatchably on some malformed embedded images,
    which is why the GUI isolates page work at all, and the OS can kill a worker for memory. The
    pool cannot tell those apart, and neither can this: rather than mark some paper an error and
    write a report that a later diff would take at face value, the run says which papers were in
    flight and stops without writing anything. `--jobs 1` then names the culprit."""
    n_jobs = max(1, min(n_jobs, len(jobs)))
    if n_jobs <= 1:
        return [_run_one(j) for j in jobs]
    out = [None] * len(jobs)
    pool = ProcessPoolExecutor(max_workers=n_jobs, mp_context=_CTX)
    try:
        pending = {}; nxt = 0
        for i in range(len(jobs)):
            while nxt < len(jobs) and len(pending) < 4 * n_jobs:          # a bounded window: the parent holds a few results, not the whole corpus
                pending[nxt] = pool.submit(_run_one, jobs[nxt]); nxt += 1
            try:
                out[i] = pending.pop(i).result()
            except BrokenProcessPool:
                stuck = sorted(pending)
                _kill(pool)
                sys.stderr.write('\nA worker process died — a MuPDF fault on a malformed pdf, or the OS killing it for memory.\n'
                                 'Nothing was written: a report that quietly marks a sound paper as an error is worse than no report.\n'
                                 'These papers were in flight, and one of them is the cause:\n')
                for k in stuck[:20]:
                    sys.stderr.write('  %s\n' % jobs[k][2])
                if len(stuck) > 20:
                    sys.stderr.write('  … and %d more\n' % (len(stuck) - 20))
                sys.stderr.write('Re-run with --jobs 1 to find it (it will take the whole run down at that paper).\n')
                raise SystemExit(2)
    finally:
        _kill(pool)
    return out


def main(roots, pdf_dirs, out_dir, tag='', baseline=None, limit=None, only=None, subset=None, n_jobs=1):
    """Every paper .pdf (paired with its .cif when one shares the I-number): what the extractor
    reads, the paper's formula re-derived from its own table and basis, its bond-valence table vs
    the .cif. The verdicts are the tool's, for the owner to check one by one."""
    stats = {'pdfs': 0, 'table': 0, 'formula': 0, 'comp_checked': 0, 'comp_ok': 0, 'comp_flag': 0, 'comp_unverified': 0, 'bv_checked': 0, 'bv_clean': 0, 'basis': 0, 'n': 0, 'D': 0, 'bvset': 0, 'pxrd': 0}
    lines = []; rows = []; papers = {}
    readers = {}                                                          # field -> {status: count}: the per-reader verified rate, the standing metric
    for pay in _map_ordered(_jobs(pdf_dirs, only, subset, limit), n_jobs):
        if 'fail' in pay:
            lines.append('==== %-40s ERROR %s' % (pay['base'], pay['fail'])); rows.append([pay['base'], 'error', pay['fail'][:200], '']); continue
        for k, v in pay['stats'].items():
            stats[k] += v                                                 # += into the dict above: the report prints its repr, so the KEY ORDER is output — never insert one here
        for fld, status in pay['readers']:
            readers.setdefault(fld, {}); readers[fld][status] = readers[fld].get(status, 0) + 1
        papers[pay['base']] = pay['record']                               # insertion order is the .json's order, and breaks ties in the powder list below
        lines += pay['lines']; rows += pay['rows']
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
    base_rec = None
    if baseline:
        with open(baseline, encoding='utf-8') as f:
            base_rec = json.load(f)
    lines += [''] + gauntlet_lines(papers, base_rec)
    if base_rec is not None:
        lines += [''] + diff(base_rec, papers)
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
    ap.add_argument('--jobs', type=int, default=0, help='worker processes: 0 (default) = the cores, capped at 8; 1 = serial, in-process')
    a = ap.parse_args()
    subset = None
    if a.papers:
        subset = set(open(a.papers, encoding='utf-8').read().split()) if os.path.exists(a.papers) else set(x.strip() for x in a.papers.split(',') if x.strip())
    jobs = a.jobs or min(8, os.cpu_count() or 1)                       # capped: each worker holds PyMuPDF and a paper's page model
    main(a.roots.split(','), a.pdf_dirs.split(','), a.out_dir, a.tag, a.baseline, a.limit, a.only, subset, max(1, jobs))
