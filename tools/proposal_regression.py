"""Private regression of `pxrd proposal`: run it on the fixture folder $PXRD_PROPOSAL_FIXTURES and check the
report against `proposal_expected.json` kept THERE (never in this repo — the fixtures are unpublished
manuscripts). Two shapes:
  one case   {"manuscript": "x.docx", "cif": "x.cif", "checkcif": "x.pdf", "present": [...], "absent": [...], "comments_min": n}
  several    {"cases": [ {the same keys, plus "name"}, ... ]}   — one line of results per case
Each "present" / "absent" entry is a plain substring of the report text. A .pdf manuscript gets a report and no copy.
A second file, `memo_expected.json`, is read the same way when it exists (the folder's review memo as the answer key).

    PXRD_PROPOSAL_FIXTURES=/path/to/folder python3 tools/proposal_regression.py
"""
import os, sys, json, tempfile, shutil, glob

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pxrd_review import proposal as PR


def run_case(folder, exp):
    tmp = tempfile.mkdtemp(prefix='proposal_reg_')
    try:
        target = exp.get('manuscript')
        docx = os.path.join(folder, target) if target else None
        res = PR.review(docx or folder, os.path.join(folder, exp['cif']) if exp.get('cif') else None,
                        os.path.join(folder, exp['checkcif']) if exp.get('checkcif') else None, out_dir=tmp, annotate_copy=True, quiet=True)
        text = open(res['report'], encoding='utf-8').read()
        fails = []
        for s in exp.get('present', []):
            if s not in text:
                fails.append('MISSING  ' + s)
        for s in exp.get('absent', []):
            if s in text:
                fails.append('PRESENT  ' + s)
        if res['comments'] < exp.get('comments_min', 0):
            fails.append('COMMENTS %d < %d' % (res['comments'], exp['comments_min']))
        for f in fails:
            print('FAIL  ' + f)
        print('%s: %d checks, %d failed; %d comments written, %d flags unplaced' % (exp.get('name') or os.path.basename(res['docx']), len(exp.get('present', [])) + len(exp.get('absent', [])), len(fails), res['comments'], len(res['unplaced'])))
        return len(fails)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    folder = os.environ.get('PXRD_PROPOSAL_FIXTURES')
    if not folder or not os.path.isdir(folder):
        print('set PXRD_PROPOSAL_FIXTURES to the fixture folder'); return 2
    n_fail = 0; ran = 0
    for name in ('proposal_expected.json', 'memo_expected.json'):
        exp_path = os.path.join(folder, name)
        if not os.path.exists(exp_path):
            continue
        exp = json.load(open(exp_path, encoding='utf-8'))
        for case in (exp.get('cases') or [exp]):
            n_fail += run_case(folder, case); ran += 1
    if not ran:
        print('no proposal_expected.json / memo_expected.json in the fixture folder'); return 2
    return 1 if n_fail else 0


if __name__ == '__main__':
    sys.exit(main())
