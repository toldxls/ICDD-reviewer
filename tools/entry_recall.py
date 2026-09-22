"""Recall of the ENTRY checks, by seeding faults — the number the entry review has never had.

    python3 tools/entry_recall.py "<entries roots, comma-separated>" OUT_DIR [TAG] [--limit N] [--jobs N]

Every figure for the entry checks is a precision figure (flags hand-checked on the corrected corpus).
This takes entries with a paired .pdf and a measured reflection list, seeds ONE slip of the kind a
transcription carries into the parsed entry — in memory; no docx is opened for writing, and
annotate_review is never run — and asks whether the review would say so:

  d-swap     two adjacent digits of the strongest line's d transposed (3.843 -> 3.834)
  d-swap-mid the same on a line of middling intensity
  drop       the strongest line left out of the list
  I-slip     the strongest line's intensity 100 -> 10
  dx-blank   Dx blanked where the entry has one

  CAUGHT  a new FLAG (what is written into the docx) that names the seeded value
  VAGUE   a new flag that does not name it        NOTED  a new console note only        MISSED  nothing new

Output OUT_DIR/entry_recall<TAG>.{txt,json}. Read-only; nothing leaves the machine.
"""
import os, re, sys, json, argparse
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('PXRD_NO_UPDATE_CHECK', '1')
from pxrd_review import cell_lambda_check as C, extra_checks as X

_CTX = mp.get_context('spawn')

def _swap(d):
    """3.843 -> 3.834: the last two digits that differ, transposed; None when no swap changes the value."""
    m = re.match(r'^(\d+)\.(\d+)$', d)
    if not m:
        return None
    frac = m.group(2)
    for i in range(len(frac) - 1, 0, -1):
        if frac[i] != frac[i - 1]:
            return m.group(1) + '.' + frac[:i - 1] + frac[i] + frac[i - 1] + frac[i + 1:]
    return None

def _findings(e, text, pdf):
    out = set()
    for f in X.run_all(e, text, None, None, pdf_path=pdf):
        if f.sev in ('flag', 'note'):
            out.add((f.sev, f.code, f.msg))
    return out

def _run_one(job):
    docx, pdf = job
    base = os.path.basename(docx)
    try:
        e = X.parse_entry(docx); text = C.pdf_text(pdf)
        if not text or not text.strip() or not e.refl or len(e.refl) < 8 or not X._measured(e):
            return None
        base0 = _findings(e, text, pdf)
    except Exception as ex:
        return {'base': base, 'fail': str(ex)[:120]}
    rows = [r for r in e.refl if X._val(r[0]) and X._val(r[1]) is not None]
    if len(rows) < 8:
        return None
    by_i = sorted(rows, key=lambda r: -(X._val(r[1]) or 0))
    strong, mid = by_i[0], by_i[len(by_i) // 2]
    runs = []
    def seed(kind, refl=None, raw=None, needle=''):
        try:
            e2 = e._replace(**{k: v for k, v in (('refl', refl), ('raw_rows', raw)) if v is not None})   # a copy: the parsed entry is immutable
            new = _findings(e2, text, pdf) - base0
        except Exception as ex:
            runs.append({'kind': kind, 'class': 'ERROR', 'said': str(ex)[:80]}); return
        flags = [m for s, c, m in new if s == 'flag']; notes = [m for s, c, m in new if s == 'note']
        cls = ('CAUGHT' if any(needle and needle in m for m in flags) else 'VAGUE') if flags else 'NOTED' if notes else 'MISSED'
        runs.append({'kind': kind, 'class': cls, 'said': (flags or notes or [''])[0][:150], 'codes': sorted({c for s, c, m in new})})
    for kind, row in (('d-swap', strong), ('d-swap-mid', mid)):
        d = re.sub(r'\s+', '', row[0]); m = re.match(r'\d+\.\d+', d); sw = _swap(m.group(0)) if m else None
        if sw:
            seed(kind, refl=[((sw + d[len(m.group(0)):],) + tuple(r[1:])) if r is row else r for r in e.refl], needle=sw)
    sd = re.sub(r'\s+', '', strong[0])
    seed('drop', refl=[r for r in e.refl if re.sub(r'\s+', '', r[0] or '') != sd], needle=re.match(r'[\d.]+', re.sub(r'\s+', '', strong[0])).group(0).rstrip('0'))
    if (X._val(strong[1]) or 0) >= 90:
        seed('I-slip', refl=[((r[0], '10') + tuple(r[2:])) if r is strong else r for r in e.refl], needle=re.match(r'[\d.]+', re.sub(r'\s+', '', strong[0])).group(0).rstrip('0'))
    dx = next((i for i, r in enumerate(e.raw_rows or []) if r and re.match(r'^Dx\s*:?\s*$', (r[0] or '').strip()) and len(r) > 1 and (r[1] or '').strip()), None)
    if dx is not None:
        val = (e.raw_rows[dx][1] or '').strip()
        raw = [list(r) for r in e.raw_rows]; raw[dx][1] = ''
        seed('dx-blank', raw=raw, needle=('%g' % X._val(val)) if X._val(val) else val)
    # the stratum that decides what a d-based check CAN see: is the list printed in the paper's text at all?
    toks = set(re.findall(r'\d+\.\d+', text))
    printed = sum(1 for r in rows if X._d_forms(re.match(r'\d+\.\d+', re.sub(r'\s+', '', r[0])).group(0)) & toks) if rows else 0
    return {'base': base, 'runs': runs, 'lines': len(rows), 'printed': round(printed / len(rows), 2), 'shared_pdf': bool(re.search(r'I\d+\s*[-_]\s*I?\d+', os.path.basename(pdf)))}

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('roots'); ap.add_argument('out_dir'); ap.add_argument('tag', nargs='?', default=''); ap.add_argument('--limit', type=int); ap.add_argument('--jobs', type=int, default=0)
    a = ap.parse_args(argv)
    jobs = []; seen = set()
    for root in [r for r in a.roots.split(',') if r]:
        idx = C.pdf_index(root)
        for eid, dp in sorted(C.discover(root).items()):
            b = os.path.basename(dp).replace('_edited', '')
            if '2028_Part 2' in dp or b in seen:
                continue
            pdf = next((idx[k] for k in C._id_keys(os.path.basename(dp)) if k in idx), None)
            if pdf:
                seen.add(b); jobs.append((dp, pdf))
    jobs = jobs[:a.limit]
    with ProcessPoolExecutor(max_workers=a.jobs or os.cpu_count() or 4, mp_context=_CTX) as pool:
        recs = [r for r in pool.map(_run_one, jobs, chunksize=2) if r]
    fails = [r for r in recs if 'fail' in r]; recs = [r for r in recs if 'runs' in r]
    CL = ('CAUGHT', 'VAGUE', 'NOTED', 'MISSED', 'ERROR')
    L = ['ENTRY-CHECK RECALL by seeded slips%s — %d measured entries with a .pdf (of %d paired)' % ((' ' + a.tag) if a.tag else '', len(recs), len(jobs)), '',
         '  %-11s %5s  ' % ('seeded', 'n') + ' '.join('%8s' % c for c in CL)]
    for kind in ('d-swap', 'd-swap-mid', 'drop', 'I-slip', 'dx-blank'):
        xs = [x for r in recs for x in r['runs'] if x['kind'] == kind]
        if xs:
            L.append('  %-11s %5d  ' % (kind, len(xs)) + ' '.join('%7.0f%%' % (100.0 * sum(1 for x in xs if x['class'] == c) / len(xs)) for c in CL))
    from collections import Counter
    for name, f in (('the list is printed in the .pdf (>= 90 % of its d)', lambda r: r['printed'] >= 0.9), ('the list is NOT printed (< 90 %)', lambda r: r['printed'] < 0.9)):
        sub = [r for r in recs if f(r)]
        L += ['', name.upper() + ' — %d entries' % len(sub)]
        for kind in ('d-swap', 'd-swap-mid', 'drop', 'I-slip', 'dx-blank'):
            xs = [x for r in sub for x in r['runs'] if x['kind'] == kind]
            if xs:
                L.append('  %-11s %5d  ' % (kind, len(xs)) + ' '.join('%7.0f%%' % (100.0 * sum(1 for x in xs if x['class'] == c) / len(xs)) for c in CL))
    L += ['', 'which check spoke (new findings, by code)']
    for kind in ('d-swap', 'd-swap-mid', 'drop', 'I-slip', 'dx-blank'):
        c = Counter(code for r in recs for x in r['runs'] if x['kind'] == kind for code in x.get('codes', []))
        L.append('  %-11s %s' % (kind, ', '.join('%s %d' % kv for kv in c.most_common(6))))
    L += ['', 'failed: %d' % len(fails)] + ['  %s %s' % (r['base'], r['fail']) for r in fails[:6]]
    os.makedirs(a.out_dir, exist_ok=True)
    json.dump(recs, open(os.path.join(a.out_dir, 'entry_recall%s.json' % a.tag), 'w'), default=str)
    open(os.path.join(a.out_dir, 'entry_recall%s.txt' % a.tag), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
    print('\n'.join(L))

if __name__ == '__main__':
    main()
