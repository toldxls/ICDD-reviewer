"""Private regression of `pxrd proposal`: run it on the fixture folder $PXRD_PROPOSAL_FIXTURES and check the
report against `proposal_expected.json` kept THERE (never in this repo — the fixture is an unpublished
manuscript). The JSON: {"present": [substrings the report must contain], "absent": [substrings it must not],
"comments_min": n}. Each entry is a plain substring of the report text.

    PXRD_PROPOSAL_FIXTURES=/path/to/folder python3 tools/proposal_regression.py
"""
import os, sys, json, tempfile, shutil, glob

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pxrd_review import proposal as PR


def main():
    folder = os.environ.get('PXRD_PROPOSAL_FIXTURES')
    if not folder or not os.path.isdir(folder):
        print('set PXRD_PROPOSAL_FIXTURES to the fixture folder'); return 2
    exp_path = os.path.join(folder, 'proposal_expected.json')
    if not os.path.exists(exp_path):
        print('no proposal_expected.json in the fixture folder'); return 2
    exp = json.load(open(exp_path, encoding='utf-8'))
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
        print('%s: %d checks, %d failed; %d comments written, %d flags unplaced' % (os.path.basename(res['docx']), len(exp.get('present', [])) + len(exp.get('absent', [])), len(fails), res['comments'], len(res['unplaced'])))
        return 1 if fails else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
