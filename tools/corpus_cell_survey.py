"""What paper_extract.cell_check says on every paper of a corpus: the powder table's calculated lines
against the .cif cell (matched by the I-number in the file names), else the cell the paper states.
Output: review_out/cell_survey_<tag>.json + .txt — the status × source counts and the red list, to be
read line by line: a red line names a row of the paper, and the row decides whether it is the
paper's error or the reader's pairing.

    python3 tools/corpus_cell_survey.py "<pdf folders, comma-separated>" [--out DIR] [--tag TAG]"""
import os, re, sys, glob, json, time, argparse, collections

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pxrd_review import paper_extract as PE
from tools.corpus_pxrd_ab import find_pdfs_and_cifs, DEFAULT_OUT


def run(folders, out_dir=DEFAULT_OUT, tag=''):
    pdfs, cifs = find_pdfs_and_cifs(folders)
    out = []; t0 = time.time()
    for i, (name, p) in enumerate(sorted(pdfs.items())):
        cif = next((cifs[m] for m in re.findall(r'I\d{5,6}', name) if m in cifs), None)
        try:
            cc = PE.cell_check(p, cif)
        except Exception as ex:
            out.append({'pdf': name, 'status': 'error', 'error': str(ex)[:120]}); continue
        out.append({'pdf': name, 'cif': bool(cif), 'status': cc['status'], 'source': cc.get('source'), 'n': cc.get('n'), 'agree': cc.get('agree'),
                    'loose': cc.get('loose'), 'bad': [(d, hkl, round(dc, 4), round(dev * 100, 1)) for d, I, hkl, dc, dev, _ in (cc.get('bad') or [])],
                    'wild': cc.get('wild'), 'unmatched': len(cc.get('unmatched_obs') or []), 'head': cc.get('head', ''), 'lines': cc.get('lines', [])[:6], 'tried': cc.get('tried')})
        if i % 100 == 0:
            print('%d/%d %.0fs' % (i, len(pdfs), time.time() - t0), flush=True)
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.join(out_dir, 'cell_survey' + ('_' + tag if tag else ''))
    json.dump(out, open(stem + '.json', 'w'), indent=0)
    st = collections.Counter((o.get('cif'), o['status'], o.get('source')) for o in out)
    lines = ['cell_check over %d papers' % len(out), 'count  cif  status     source']
    for k, v in sorted(st.items(), key=lambda kv: -kv[1]):
        lines.append('%5d  %-4s %-10s %s' % (v, 'yes' if k[0] else 'no', k[1], k[2]))
    chk = [o for o in out if o['status'] == 'checked']
    red = [o for o in chk if o['bad']]
    lines.append('checked %d: red lines in %d papers (%d lines); "follows no cell" %d; shifted throughout %d; .cif in another setting %d; unmatched-observed notes %d' % (
        len(chk), len(red), sum(len(o['bad']) for o in red), sum(1 for o in chk if any('follows no cell' in l for l in o['lines'])),
        sum(1 for o in chk if any('off — computed' in l for l in o['lines'])), sum(1 for o in chk if any("the .cif's cell" in l for l in o['lines'])),
        sum(1 for o in chk if o['unmatched'])))
    lines.append('=== RED LINES (paper | cell source | agree/n | the lines)')
    for o in sorted(red, key=lambda o: -len(o['bad'])):
        lines.append('  %-36s %-4s %-8s %3d/%-3d' % (o['pdf'][:36], 'cif' if o['cif'] else 'text', o['source'], o['agree'], o['n']))
        for l in o['lines']:
            if 'does not follow the cell:' in l:
                lines.append('      ' + l[:150])
    with open(stem + '.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print('\n'.join(lines[:len(st) + 3]))
    print('wrote', stem + '.txt')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('folders', help='pdf folders, comma-separated (searched recursively)')
    ap.add_argument('--out', default=DEFAULT_OUT)
    ap.add_argument('--tag', default='')
    a = ap.parse_args()
    run([f.strip() for f in a.folders.split(',') if f.strip()], a.out, a.tag)
