"""The hint oracle: every flag the entry checks raise, scored against what a HUMAN reviewer changed.

    python3 tools/hint_oracle.py "<corpus root>" OUT_DIR [TAG] [--limit N] [--jobs N] [--old-template]

A reviewer's marked-up copy of an entry carries Word tracked changes, so one file holds two states of
every cell: BEFORE (insertions dropped, deleted text kept — the entry as it was submitted) and AFTER
(what the reviewer left). The checks run on BEFORE; each flag is then read against the reviewer's
edits — a review made independently of the tool, most of them before the tool existed:

  RESOLVED   the same flag is gone on AFTER: the reviewer changed what the flag pointed at
  PERSISTS   the flag stands on AFTER — the reviewer did not act on it. NOT a false positive by
             itself: most of these reviews predate the rule (IMA numbers, Dx, hkl groups …).
             The per-code PERSISTS samples in the .txt are the worklist to read by hand.
  and for a flag that PRINTS a value ("add it (IMA 2019-036)", "should be 'Diffractometer'",
  "enter it (Dx = 3.30)", "add Filter = Beta-Filter, FilterType = Ni"):
  CONFIRMED  the reviewer wrote that value into a cell they changed
  OTHER      the flag went away, but the reviewer wrote something else — a hint to read by hand
  LEFT       the cell was not changed

Copies of one document (the same document.xml) are read once; the old two-column template (label and
value in one cell, which `parse_entry` reads as blank fields) is left out unless --old-template. An
entry with no changed cell is skipped (nothing to score against). Read-only; nothing leaves the
machine; no docx is opened for writing. Output OUT_DIR/hint_oracle<TAG>.{txt,json}.
"""
import os, re, sys, json, zipfile, hashlib, argparse, collections
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault('PXRD_NO_UPDATE_CHECK', '1')
from pxrd_review import cell_lambda_check as C, extra_checks as X
from pxrd_review.annotate_review import AUTHOR as TOOL_AUTHOR

_CTX = mp.get_context('spawn')
SKIP_DIRS = ('review_tool', 'pxrd-review', '.cache', '.edit_backup', 'EPMA training')

# the value a flag's message offers, by the forms the checks print
_HINT_PATS = (r"should be '([^']+)'", r'should be ([A-Z][\w-]+(?:-\([A-Za-z]+\))?)(?:[,.]|$)',
              r'\(IMA ([\d]{4}-\d{2,3}[a-z]?)\)', r'densit(?:y|ies) of ([\d.]+(?:, [\d.]+)*(?: and [\d.]+)?)',
              r"add Filter = ([^.;]+)", r"suggest '([^']+)'", r'WITH an esd[^\d]*([\d.]+\(\d+\))',
              r'\.pdf (?:reports|gives|states|prints) ([\d.]+\(\d+\))')


def hints(msg):
    """The values a message offers, each split into the tokens a cell would carry ('Beta-Filter,
    FilterType = Ni' -> ['Beta-Filter', 'Ni']; '5.16, 5.41 and 4.84' -> one hint per density)."""
    out = []
    for pat in _HINT_PATS:
        for m in re.finditer(pat, msg):
            v = next((g for g in m.groups() if g), None)
            if not v or len(v) > 80:
                continue
            if re.fullmatch(r'[\d., and]+', v):
                out += [[x] for x in re.findall(r'\d+\.\d+', v)]
            else:
                toks = [t.split('=')[-1].strip() for t in re.split(r',\s*', v)]
                out.append([t for t in toks if t])
    return out


def _norm(s):
    return re.sub(r'[\s  ]+', '', (s or '')).lower()


def _findings(e, text, pdf):
    return [{'code': f.code, 'sev': f.sev, 'msg': f.msg, 'anchor': f.anchor}
            for f in X.run_all(e, text, None, None, pdf_path=pdf) if f.sev in ('flag', 'note')]


def _old_template(rows):
    """The older ICDD template: the label and its value share a cell ('Radiation : MoKa …'), or the
    entry head is one cell ('CodeNamePrimary …') — `parse_entry` reads such fields as blank."""
    for r in rows[:40]:
        c0 = (r[0] if r else '') or ''
        if c0.startswith('CodeName') or re.match(r'^\s*Radiation\s*:', c0):
            return True
    return False


def run_one(job):
    docx, pdf = job
    base = os.path.basename(docx)
    try:
        rb, ra = X._rows(docx, before=True), X._rows(docx)
        if _old_template(rb):
            return {'docx': docx, 'skip': 'old template'}
        changed = []
        for i, (b, a) in enumerate(zip(rb, ra)):
            for j, (cb, ca) in enumerate(zip(b, a)):
                if X._sq(cb) != X._sq(ca):
                    changed.append({'row': i, 'col': j, 'label': X._sq(b[0])[:40] if b else '',
                                    'before': X._sq(cb)[:300], 'after': X._sq(ca)[:300]})
        if not changed:
            return {'docx': docx, 'skip': 'no cell changed'}
        eb, ea = X.parse_entry(docx, before=True), X.parse_entry(docx)
        text = C.pdf_text(pdf) if pdf else ''
        content = hashlib.md5(json.dumps([rb, ra]).encode('utf-8')).hexdigest()   # the same reviewed entry filed twice (two folders) is one answer
        return {'docx': docx, 'pdf': os.path.basename(pdf) if pdf else None, 'changed': changed, 'content': content,
                'before': _findings(eb, text, pdf), 'after': _findings(ea, text, pdf)}
    except Exception as ex:
        return {'docx': docx, 'fail': '%s: %s' % (base, str(ex)[:160])}


def _human_marked(path):
    """True when the document carries a tracked change by someone other than the tool."""
    try:
        d = zipfile.ZipFile(path).read('word/document.xml').decode('utf-8', 'ignore')
    except Exception:
        return False
    return any(a != TOOL_AUTHOR for a in re.findall(r'<w:(?:ins|del) [^>]*w:author="([^"]*)"', d))


def _jobs(root, old_template):
    """(docx, pdf) for every human-marked docx under root, one per distinct document."""
    pdfs = {}
    docs = []
    for dp, dns, fns in os.walk(root):
        if any(s in dp for s in SKIP_DIRS) or (not old_template and 'ICDD Task Group' in dp):
            dns[:] = []
            continue
        for f in fns:
            p = os.path.join(dp, f)
            if f.lower().endswith('.pdf'):
                for k in C._id_keys(f):
                    pdfs.setdefault(k, p)
            elif f.lower().endswith('.docx') and not f.startswith('~$') and _human_marked(p):
                docs.append(p)
    jobs, seen = [], set()
    for p in sorted(docs):
        try:
            h = hashlib.md5(zipfile.ZipFile(p).read('word/document.xml')).hexdigest()
        except Exception:
            continue
        if h in seen:
            continue
        seen.add(h)
        pdf = next((pdfs[k] for k in C._id_keys(os.path.basename(p)) if k in pdfs), None)
        jobs.append((p, pdf))
    return jobs


def score(recs):
    """Per code: flags on BEFORE, resolved / persists, hinted / confirmed / other / left; and the
    samples to read (the OTHER cases in full, three PERSISTS per code)."""
    per = collections.defaultdict(collections.Counter)
    other, persist = [], collections.defaultdict(list)
    seen = set()
    for r in recs:
        if r.get('content') in seen:
            continue
        seen.add(r.get('content'))
        after = {(f['code'], f['msg']) for f in r['after']}
        chg = [(c['label'], c['before'], c['after']) for c in r['changed'] if c['label'] != 'Accept']
        for f in r['before']:
            if f['sev'] != 'flag':
                continue
            c = f['code']
            per[c]['flags'] += 1
            gone = (c, f['msg']) not in after
            per[c]['resolved' if gone else 'persists'] += 1
            if not gone and len(persist[c]) < 3:
                persist[c].append((r['docx'], f['msg']))
            hv = hints(f['msg'])
            if not hv:
                continue
            per[c]['hinted'] += 1
            hit = any(all(any(_norm(t) and _norm(t) in _norm(a) and _norm(t) not in _norm(b) for _l, b, a in chg) for t in toks) for toks in hv if toks)
            if hit:
                per[c]['confirmed'] += 1
            elif gone:
                per[c]['other'] += 1
                other.append((r['docx'], f['msg'], hv, [(l, b, a) for l, b, a in chg][:6]))
            else:
                per[c]['left'] += 1
    return per, other, persist


def report(recs, skipped, fails, tag, njobs):
    per, other, persist = score(recs)
    L = ['HINT ORACLE%s — %d human-marked entries scored (of %d documents; %d skipped: %s; %d failed)'
         % ((' ' + tag) if tag else '', len({r.get('content') for r in recs}), njobs, len(skipped),
            ', '.join('%s %d' % kv for kv in collections.Counter(skipped).most_common()), len(fails)),
         'BEFORE = the submission (tracked insertions dropped, deletions kept); AFTER = what the reviewer left.',
         'RESOLVED = the flag is gone on AFTER. PERSISTS = not acted on (most reviews predate the rule: a worklist, not a verdict).',
         'CONFIRMED = the value the flag printed is in a cell the reviewer changed to it; OTHER = the flag went away, the reviewer wrote something else.',
         '',
         '  %-18s %5s %8s %8s | %6s %9s %5s %5s' % ('code', 'flags', 'resolved', 'persists', 'hinted', 'confirmed', 'other', 'left')]
    for c, k in sorted(per.items(), key=lambda kv: -kv[1]['flags']):
        L.append('  %-18s %5d %7d%% %8d | %6d %9d %5d %5d'
                 % (c, k['flags'], 100 * k['resolved'] / k['flags'], k['persists'], k['hinted'], k['confirmed'], k['other'], k['left']))
    L += ['', 'OTHER — the reviewer resolved the flag with another value (read each: is the hint wrong?)']
    for docx, msg, hv, chg in other:
        L += ['', '  %s' % os.path.basename(docx), '    %s' % msg[:220], '    hint: %s' % hv]
        L += ['      %s | %s -> %s' % (l[:22], b[:40], a[:40]) for l, b, a in chg]
    L += ['', 'PERSISTS — three per code, the flags no reviewer acted on']
    for c in sorted(persist):
        L += ['', '  ## %s' % c] + ['    %s: %s' % (os.path.basename(d), m[:200]) for d, m in persist[c]]
    L += ['', 'failed: %d' % len(fails)] + ['  %s' % f for f in fails[:8]]
    return '\n'.join(L) + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('root'); ap.add_argument('out_dir'); ap.add_argument('tag', nargs='?', default='')
    ap.add_argument('--limit', type=int); ap.add_argument('--jobs', type=int, default=0)
    ap.add_argument('--old-template', action='store_true', help='include the older template (its fields parse as blank: mostly noise)')
    ap.add_argument('--report', metavar='JSON', help="re-render the report from an earlier run's hint_oracle<TAG>.json (no checks run)")
    a = ap.parse_args(argv)
    if a.report:
        out = json.load(open(a.report)); jobs = out
    else:
        jobs = _jobs(a.root, a.old_template)[:a.limit]
        print('%d human-marked documents (%d with a .pdf)' % (len(jobs), sum(1 for j in jobs if j[1])), flush=True)
        with ProcessPoolExecutor(max_workers=a.jobs or os.cpu_count() or 4, mp_context=_CTX) as pool:
            out = list(pool.map(run_one, jobs, chunksize=2))
    recs = [r for r in out if 'before' in r]
    skipped = [r['skip'] for r in out if 'skip' in r]
    fails = [r['fail'] for r in out if 'fail' in r]
    os.makedirs(a.out_dir, exist_ok=True)
    txt = report(recs, skipped, fails, a.tag, len(jobs))
    json.dump(out, open(os.path.join(a.out_dir, 'hint_oracle%s.json' % a.tag), 'w'), default=str)
    open(os.path.join(a.out_dir, 'hint_oracle%s.txt' % a.tag), 'w', encoding='utf-8').write(txt)
    print(txt)


if __name__ == '__main__':
    main()
