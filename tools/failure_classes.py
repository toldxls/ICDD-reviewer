"""The reader failures a run logged (paper_checks_failures<tag>.jsonl from tools/corpus_paper_extract.py,
or review_out/reader_failures.jsonl from `pxrd paper --check --log-failures`), grouped into CLASSES —
the worklist for refining a reader: which reader, which status, which detail, how many papers, and
the records of one class with everything they carry (page, sentence, the table read, the oracle's lines).

    python3 tools/failure_classes.py FILE.jsonl                       # every reader: status counts, then the classes
    python3 tools/failure_classes.py FILE.jsonl --field bv.table      # one reader's classes
    python3 tools/failure_classes.py FILE.jsonl --field coords --status unverified --show 5   # the records of that class, in full
    python3 tools/failure_classes.py FILE.jsonl --silent              # only the silent failures (the paper prints the thing, the reader has nothing)
    python3 tools/failure_classes.py FILE.jsonl --paper 12988         # every record of one paper

A class is (field, status, the detail with its numbers replaced by N). A dev tool, never shipped
in the reviewer's install path; it reads what the tool wrote and writes nothing.
"""
import sys, re, json, argparse, collections


def load(path):
    out = []
    with open(path, encoding='utf-8') as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                out.append(json.loads(ln))
    return out


def klass(rec):
    d = re.sub(r'\d+(\.\d+)?', 'N', rec.get('detail') or '')
    d = re.sub(r'\b[A-Z][a-z]?\d*(?:/[A-Z][a-z]?\d*)*\b', 'X', d)          # site and element names: one class for 'Fe1 column' and 'Cu2 column'
    return (rec['field'], rec['status'], d[:90])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('file'); ap.add_argument('--field'); ap.add_argument('--status'); ap.add_argument('--paper')
    ap.add_argument('--silent', action='store_true'); ap.add_argument('--show', type=int, default=0, help='print this many records of the selected class(es) in full')
    a = ap.parse_args(argv)
    recs = load(a.file)
    if a.paper:
        recs = [r for r in recs if a.paper in r['paper']]
    if a.field:
        recs = [r for r in recs if r['field'] == a.field]
    if a.status:
        recs = [r for r in recs if r['status'] == a.status]
    if a.silent:
        recs = [r for r in recs if r.get('silent')]
    if not recs:
        print('no records'); return 0
    by_field = collections.defaultdict(collections.Counter)
    for r in recs:
        by_field[r['field']][r['status']] += 1
    print('%d records, %d papers' % (len(recs), len({r['paper'] for r in recs})))
    for fld, c in sorted(by_field.items(), key=lambda kv: -sum(kv[1].values())):
        print('  %-14s %s' % (fld, ', '.join('%s %d' % (k, v) for k, v in c.most_common())))
    groups = collections.defaultdict(list)
    for r in recs:
        groups[klass(r)].append(r)
    print('\nCLASSES (field | status | detail, numbers as N, names as X):')
    for k, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        papers = sorted({r['paper'] for r in rs})
        print('  %3d  %-12s %-11s %s' % (len(rs), k[0], k[1], k[2]))
        print('       ' + ', '.join(p[:28] for p in papers[:8]) + (' …' if len(papers) > 8 else ''))
    if a.show:
        print('\nRECORDS:')
        for r in recs[:a.show]:
            print('==== %s | %s | %s | %s' % (r['paper'], r['field'], r['status'], (r.get('detail') or '')[:120]))
            for k in ('value', 'page', 'source', 'reader', 'verified_by', 'silent', 'cif', 'when', 'version'):
                if r.get(k) not in (None, '', False):
                    print('   %-12s %s' % (k, str(r[k])[:200]))
            for k, v in (r.get('context') or {}).items():
                if v in (None, '', [], {}):
                    continue
                if isinstance(v, list):
                    print('   %-12s' % k)
                    for x in v[:16]:
                        print('       %s' % (str(x)[:180]))
                else:
                    print('   %-12s %s' % (k, str(v)[:200]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
