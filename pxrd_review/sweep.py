#!/usr/bin/env python3
"""
Corpus sweep — run the review checks (read-only) over every entry in a folder tree,
write a persistent report + a machine snapshot, and DIFF against the last run.

Why this exists: the checks are hardened reactively (mine deviants -> validate against
the corpus -> regression-gate). The regression suite (regression_check.py) is POINTWISE —
it asserts ~80 known cases — so it cannot see AGGREGATE drift: a check edit that starts
firing on 100 un-asserted entries leaves it green. The only thing that catches that is a
full-corpus sweep with a before/after diff, which until now lived in throwaway scratch
scripts re-derived every session. This commits that workflow.

It is NOT a gate (no auto-fail): the human eyeball on the diff is the gate, same as always —
this just makes it one command and a readable log instead of a bespoke script. Reuses
annotate_review.analyze() verbatim (the single source of truth) and never writes a docx.

Usage:
    python3 -m pxrd_review.sweep "<folder>"               # report + snapshot + diff vs last
    python3 -m pxrd_review.sweep "<folder>" --samples     # also show one example per check
    python3 -m pxrd_review.sweep "<folder>" --baseline OLD.json   # diff vs a saved snapshot
    python3 -m pxrd_review.sweep "<folder>" --no-diff --no-save   # just (re)build the report
Outputs (under <folder>/review_out, or --out DIR):
    sweep_report.txt     human-readable: fire table (old/new template split), verdicts, DIFF
    sweep_snapshot.json  machine snapshot; the baseline the NEXT run diffs against
"""
import sys, os, re, glob, json, argparse, datetime
from collections import Counter, defaultdict

from pxrd_review import cell_lambda_check as C
from pxrd_review import extra_checks as X
from pxrd_review import annotate_review as A

SNAP = 'sweep_snapshot.json'
REPORT = 'sweep_report.txt'

# ----------------------------------------------------------------------------- discovery
def discover(folder):
    """Entry docx under `folder` (recursive), deduped by entry id. Skips the tool's own
    outputs (review_out / .edit_backup) and Word lock files, so the entry SET is stable
    run-to-run (a meaningful diff needs a stable set)."""
    out = {}
    for dp in sorted(glob.glob(os.path.join(folder, '**', '*.docx'), recursive=True)):
        base = os.path.basename(dp)
        if base.startswith('~$'):
            continue
        if re.search(r'(?:^|/)(review_out|\.edit_backup)/', dp.replace(os.sep, '/')):
            continue
        eid = C.entry_id(dp)
        if eid and eid not in out:        # first stable-sorted wins
            out[eid] = dp
    return out

# ----------------------------------------------------------------------------- per-entry analysis
def _newtpl(entry):
    """True for the current ICDD template; the old Task-Group template parses to empty
    structure (parse_entry targets the new layout), so any recognised field == new."""
    return bool(entry and (entry.comments or entry.instr or entry.formulas or entry.subfiles))

def _findings(res, errored):
    """The entry's verdict as a flat list of readable tokens — the unit the diff compares.
    Covers the cell verdict, the lambda verdict, each flagged cell parameter, every extra
    finding (code/sev, '*' = written into the docx), and severe/error markers."""
    if errored:
        return ['error']
    toks = ['cell=%s' % res['cell'][0]]
    lam = res.get('lam')
    if lam:
        toks.append('lam=%s' % lam[0])
    for k in (res.get('params') or {}):
        toks.append('param:%s' % k)
    writable = {id(f) for f in A._writable_extras(res)}
    for f in res.get('extra', []):
        toks.append('%s/%s%s' % (f.code, f.sev, '*' if id(f) in writable else ''))
    if A._is_severe(res):
        toks.append('severe')
    return sorted(toks)

def analyze_entry(eid, dp, pdf, cif, dft):
    rec = {'id': eid, 'docx': dp, 'pdf': os.path.basename(pdf) if pdf else None,
           'cif': bool(cif), 'dft': bool(dft), 'newtpl': True, 'error': None,
           'cell': None, 'lam': None, 'findings': [], 'samples': {}}
    try:
        rec['newtpl'] = _newtpl(X.parse_entry(dp))
    except Exception:
        pass
    try:
        res = A.analyze(dp, pdf, cif, dft)
        rec['cell'] = res['cell'][0]
        rec['lam'] = res['lam'][0] if res.get('lam') else None
        rec['findings'] = _findings(res, False)
        # one example message per extra-check code (for --samples)
        for f in res.get('extra', []):
            rec['samples'].setdefault(f.code, (f.msg or '')[:200])
    except Exception as ex:
        rec['error'] = '%s: %s' % (type(ex).__name__, ex)
        rec['findings'] = ['error']
    return rec

# ----------------------------------------------------------------------------- snapshot build
def build(folder, progress=True):
    try:
        from pxrd_review import mindat
        mindat.refresh_struct_if_stale()       # warm the offline caches once (as annotate does)
    except Exception:
        pass
    docs = discover(folder)
    pidx, cidx, didx = C.pdf_index(folder), C.cif_index(folder), C.dft_index(folder)
    recs = {}
    n = len(docs)
    for i, (eid, dp) in enumerate(sorted(docs.items()), 1):
        recs[eid] = analyze_entry(eid, dp, pidx.get(eid), cidx.get(eid), didx.get(eid))
        if progress and (i % 25 == 0 or i == n):
            print('  [%d/%d] swept' % (i, n), end='\r', flush=True)
    if progress:
        print()
    rel = lambda p: os.path.relpath(p, folder)
    for r in recs.values():
        r['docx'] = rel(r['docx'])
    meta = {'folder': os.path.abspath(folder),
            'generated': datetime.datetime.now().isoformat(timespec='seconds'),
            'n_entries': n,
            'n_newtpl': sum(r['newtpl'] for r in recs.values()),
            'n_pdf': sum(r['pdf'] is not None for r in recs.values()),
            'n_cif': sum(r['cif'] for r in recs.values()),
            'n_dft': sum(r['dft'] for r in recs.values()),
            'n_crash': sum(r['error'] is not None for r in recs.values())}
    return {'meta': meta, 'entries': recs}

# ----------------------------------------------------------------------------- report
def _fire_table(recs):
    """Per extra-check fire counts: code -> [total, newtpl, oldtpl, flags]. The token
    list carries 'code/sev[*]'; aggregate back to the bare check code."""
    tab = defaultdict(lambda: [0, 0, 0, 0])
    for r in recs.values():
        for tok in r['findings']:
            m = re.match(r'^([a-z_]+)/(\w+)', tok)
            if not m:
                continue                         # skip cell=/lam=/param:/severe/error
            code, sev = m.group(1), m.group(2)
            row = tab[code]
            row[0] += 1
            row[1 if r['newtpl'] else 2] += 1
            if sev == 'flag':
                row[3] += 1
    return tab

def _dist(recs, key):
    return Counter(r[key] for r in recs.values() if r[key] is not None)

def write_report(path, snap, baseline, samples=False):
    recs = snap['entries']; meta = snap['meta']
    L = []
    L.append('PXRD review — corpus sweep')
    L.append('folder    : %s' % meta['folder'])
    L.append('generated : %s' % meta['generated'])
    L.append('entries   : %d  (%d new-template | %d old-template)'
             % (meta['n_entries'], meta['n_newtpl'], meta['n_entries'] - meta['n_newtpl']))
    L.append('paired    : %d .pdf | %d .cif | %d .dft' % (meta['n_pdf'], meta['n_cif'], meta['n_dft']))
    L.append('crashes   : %d' % meta['n_crash'])
    L.append('=' * 78)

    celld = _dist(recs, 'cell'); lamd = _dist(recs, 'lam')
    L.append('\nCELL verdicts : ' + ', '.join('%s=%d' % (k, v) for k, v in celld.most_common()))
    L.append('λ    verdicts : ' + ', '.join('%s=%d' % (k, v) for k, v in lamd.most_common()))

    tab = _fire_table(recs)
    L.append('\nEXTRA-CHECK FIRE TABLE  (total | new-tpl | old-tpl | flags)')
    L.append('-' * 78)
    L.append('  %-18s %6s %8s %8s %7s' % ('check', 'total', 'new-tpl', 'old-tpl', 'flags'))
    for code, (tot, nt, ot, fl) in sorted(tab.items(), key=lambda kv: -kv[1][0]):
        L.append('  %-18s %6d %8d %8d %7d' % (code, tot, nt, ot, fl))
    if not tab:
        L.append('  (no findings)')

    crashes = [(r['id'], r['error']) for r in recs.values() if r['error']]
    if crashes:
        L.append('\nCRASHES / PARSE FAILURES')
        L.append('-' * 78)
        for eid, err in sorted(crashes):
            L.append('  %-9s %s' % (eid, err))

    if samples:
        ex = {}
        for r in recs.values():
            for code, msg in r['samples'].items():
                ex.setdefault(code, (r['id'], msg))
        L.append('\nSAMPLE PER CHECK (one example message)')
        L.append('-' * 78)
        for code in sorted(ex):
            eid, msg = ex[code]
            L.append('  [%s] %s' % (code, eid))
            L.append('      %s' % msg)

    L.append('\n' + '=' * 78)
    L.append(_diff_block(baseline, snap))

    text = '\n'.join(L) + '\n'
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)
    return text

# ----------------------------------------------------------------------------- diff
def _diff_block(baseline, snap, cap=60):
    if baseline is None:
        return 'DIFF vs previous run : (no previous snapshot — this is the baseline)'
    old, new = baseline.get('entries', {}), snap['entries']
    L = ['DIFF vs previous run  (baseline %s)' % baseline.get('meta', {}).get('generated', '?'),
         '-' * 78]

    # per-check count deltas
    ot, nt = _fire_table(old), _fire_table(new)
    codes = sorted(set(ot) | set(nt))
    deltas = [(c, ot.get(c, [0])[0], nt.get(c, [0])[0]) for c in codes]
    deltas = [(c, a, b) for c, a, b in deltas if a != b]
    if deltas:
        L.append('per-check count changes:')
        for c, a, b in sorted(deltas, key=lambda x: -abs(x[2] - x[1])):
            L.append('  %-18s %d → %d  (%+d)' % (c, a, b, b - a))
    else:
        L.append('per-check counts: unchanged')

    # entries added / removed from the corpus set
    added = sorted(set(new) - set(old)); removed = sorted(set(old) - set(new))
    if added:
        L.append('\nentries ADDED to corpus (%d): %s' % (len(added), ', '.join(added[:30]) + (' …' if len(added) > 30 else '')))
    if removed:
        L.append('entries REMOVED from corpus (%d): %s' % (len(removed), ', '.join(removed[:30]) + (' …' if len(removed) > 30 else '')))

    # per-entry verdict changes (entries present in both whose finding multiset changed)
    changed = []
    for eid in sorted(set(old) & set(new)):
        co, cn = Counter(old[eid].get('findings', [])), Counter(new[eid].get('findings', []))
        if co == cn:
            continue
        plus = cn - co; minus = co - cn
        changed.append((eid, plus, minus))
    L.append('\nentries with CHANGED verdict: %d' % len(changed))
    def _fmt(counter):
        return ' '.join('%s%s' % (t, '×%d' % n if n > 1 else '') for t, n in sorted(counter.items()))
    for eid, plus, minus in changed[:cap]:
        bits = []
        if plus:  bits.append('+[%s]' % _fmt(plus))
        if minus: bits.append('-[%s]' % _fmt(minus))
        L.append('  %-9s %s' % (eid, '  '.join(bits)))
    if len(changed) > cap:
        L.append('  … and %d more (see snapshot)' % (len(changed) - cap))

    # crashes added / resolved
    oc = {e for e, r in old.items() if r.get('error')}
    nc = {e for e, r in new.items() if r.get('error')}
    if nc - oc:
        L.append('\nNEW crashes: %s' % ', '.join(sorted(nc - oc)))
    if oc - nc:
        L.append('resolved crashes: %s' % ', '.join(sorted(oc - nc)))
    return '\n'.join(L)

# ----------------------------------------------------------------------------- io
def _load(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None

# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description='Read-only corpus sweep: report + run-to-run diff.')
    ap.add_argument('folder')
    ap.add_argument('--out', help='output folder for the report/snapshot (default <folder>/review_out)')
    ap.add_argument('--baseline', help='diff against this snapshot JSON instead of the auto one (implies --no-save)')
    ap.add_argument('--no-diff', action='store_true', help='do not diff against the previous snapshot')
    ap.add_argument('--no-save', action='store_true', help='do not overwrite the auto snapshot baseline')
    ap.add_argument('--samples', action='store_true', help='include one example message per check')
    args = ap.parse_args()

    if not os.path.isdir(args.folder):
        sys.exit('not a folder: %s' % args.folder)
    out_dir = args.out or os.path.join(args.folder, 'review_out')
    snap_path = os.path.join(out_dir, SNAP)
    report_path = os.path.join(out_dir, REPORT)

    print('[sweep] analyzing %s …' % os.path.abspath(args.folder))
    snap = build(args.folder)

    baseline = None
    if not args.no_diff:
        baseline = _load(args.baseline) if args.baseline else _load(snap_path)

    text = write_report(report_path, snap, baseline, samples=args.samples)

    if not args.no_save and not args.baseline:
        os.makedirs(out_dir, exist_ok=True)
        with open(snap_path, 'w', encoding='utf-8') as f:
            json.dump(snap, f)

    m = snap['meta']
    # the headline the user wants at a glance
    changed = crash_new = 0
    if baseline is not None:
        oldE, newE = baseline.get('entries', {}), snap['entries']
        changed = sum(Counter(oldE.get(e, {}).get('findings', [])) != Counter(newE[e]['findings'])
                      for e in set(oldE) & set(newE))
        crash_new = len({e for e, r in newE.items() if r.get('error')}
                        - {e for e, r in oldE.items() if r.get('error')})
    print('[sweep] %d entries (%d new-tpl), %d crashes%s'
          % (m['n_entries'], m['n_newtpl'], m['n_crash'],
             '' if baseline is None else ' | %d changed since last run, %d new crashes' % (changed, crash_new)))
    print('[sweep] report   -> %s' % report_path)
    if not args.no_save and not args.baseline:
        print('[sweep] snapshot -> %s  (baseline for next run)' % snap_path)

if __name__ == '__main__':
    main()
