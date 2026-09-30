"""One review of a new-mineral manuscript and its files (`pxrd proposal <folder|manuscript.docx> [--cif X] [--checkcif Y]`).

Runs every check the tool has for a manuscript with a structure beside it, and writes ONE report and ONE
annotated COPY of the manuscript (the source is never touched):
  references     refs_check — citations against the reference list, both ways;
  bond tables    bv_check --table — bond distances, symmetry codes, hydrogen-bond rows, bond-valence table;
  .cif audit     cif_audit — riding H, the refinement numbers, the stated density, site labels; the checkCIF report;
  powder table   pxrd_audit — the cell behind dcalc, omitted lines, Icalc, dobs;
  composition    paper_extract.check_paper — the analysis against the formula, the ideal wt%, Gladstone–Dale, the cell;
  lints          lints — spectroscopy and notation.
Flags are written into the copy as Word comments on the text they concern (a finding with no place in the
text stays in the report); notes go to the report only. Outputs: review_out/<stem>_proposal_report.txt and
review_out/<stem>_proposal.docx. The manuscript is read locally; nothing leaves the machine.
"""
import os, re, sys, glob, argparse, shutil

# a line of the report that is a finding (the GUI's rule for the paper checks, plus this tool's own wordings)
_FLAG = re.compile(r' vs |but the \.cif|but it is bonded|is bonded to .* not|does not|do not|lacks its lattice|is the wrong operator|is not needed|'
                   r'has no symmetry code|no such site|stated, but|in different places|differ|cell the manuscript does not report|not in the table|'
                   r'cited here but has no entry|listed but never cited|reproduced by no combination|(?<!\b0 )disagree', re.I)


def find_files(target, cif=None, checkcif=None):
    """The manuscript .docx, the .cif and the checkCIF report from a folder or a manuscript path."""
    if os.path.isdir(target):
        folder = target
        docs = [p for p in glob.glob(os.path.join(folder, '*.docx')) if not os.path.basename(p).startswith('~$') and 'review_out' not in p
                and not re.search(r'_(refs|proposal|bv|pxrd|tables)\.docx$', p)]
        docs.sort(key=lambda p: -os.path.getsize(p))
        docx = docs[0] if docs else None
    else:
        docx = target; folder = os.path.dirname(os.path.abspath(target))
    stem = os.path.splitext(os.path.basename(docx))[0].lower() if docx else ''
    if not cif:
        cifs = [p for p in glob.glob(os.path.join(folder, '*.cif'))]
        # the .cif whose name shares a word with the manuscript's, else the only one
        named = [p for p in cifs if any(w in os.path.basename(p).lower() for w in re.findall(r'[a-z]{5,}', stem))]
        cif = (named or cifs)[0] if (named or len(cifs) == 1) else None
    if not checkcif:
        reps = [p for p in glob.glob(os.path.join(folder, '*.pdf')) + glob.glob(os.path.join(folder, '*.txt')) if 'checkcif' in os.path.basename(p).lower()]
        named = [p for p in reps if any(w in os.path.basename(p).lower() for w in re.findall(r'[a-z]{5,}', stem))]
        checkcif = (named or reps)[0] if (named or len(reps) == 1) else None
    return docx, cif, checkcif


def _quoted(text):
    """The anchors a report line offers: quoted spans, then a table cell before ' — ', then the numbers it names."""
    out = [q.strip('… ') for q in re.findall(r"[‘']([^’']{6,120})[’']", text)]
    m = re.search(r'site (\w+) is named', text)
    if m:
        out.insert(0, m.group(1))
    m = re.search(r'row \d+: (.{4,60}?) (?:—|\d)', text)
    if m:
        out.append(re.sub(r'\^[^^]*\^', '', m.group(1)).strip())
    m = re.search(r'^(?:\s*)([A-Z][a-z]?\d{0,2}[A-Za-z]?):', text)
    out += re.findall(r'(?<![\d.])(\d+\.\d{2,4})(?![\d.])', text)[:3]
    return [a for a in out if a]


def annotate(docx, findings, out_path, base=None):
    """Word comments for the flags, on the first paragraph or cell that holds one of a finding's anchors.
    `base`: a copy to build on (the refs check's annotated copy, so its comments are kept). -> (n written, unplaced)."""
    from pxrd_review import refs_check as R
    from pxrd_review.annotate_review import AUTHOR, INITIALS, _save_docx
    from docx.text.paragraph import Paragraph
    from docx.text.run import Run
    doc, paras = R.load_docx(base or docx)
    n = 0; unplaced = []
    pieces_by = {}
    for msg, anchors in findings:
        placed = False
        for a in anchors:
            for p in paras:
                if p.elem is None or a not in p.text:
                    continue
                s = p.text.index(a); e = s + len(a)
                pieces = pieces_by.setdefault(p.idx, R._para_pieces(p.elem))
                runs = R._runs_for_span(pieces, s, e)
                if not runs:
                    continue
                R._highlight_runs(runs)
                doc.add_comment([Run(r, Paragraph(p.elem, doc._body)) for r in runs], text=msg, author=AUTHOR, initials=INITIALS)
                n += 1; placed = True
                break
            if placed:
                break
        if not placed:
            unplaced.append(msg)
    _save_docx(doc, out_path)
    return n, unplaced


def review(target, cif=None, checkcif=None, out_dir=None, annotate_copy=True, quiet=False):
    docx, cif, checkcif = find_files(target, cif, checkcif)
    if not docx:
        raise ValueError('no manuscript .docx in %s' % target)
    out_dir = out_dir or os.path.join(os.path.dirname(os.path.abspath(docx)), 'review_out')
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(docx))[0]
    sections = []; flags = []            # (message, anchors)
    def section(title, lines):
        sections.append((title, lines))
    # -- references (its own annotated copy is the base ours builds on)
    refs_copy = None
    try:
        from pxrd_review import refs_check as R
        res = R.check_file(docx, out_dir=out_dir, annotate=annotate_copy, quiet=True)
        _doc, paras = R._load(docx)
        rep = R.report(docx, paras, res).split('\n')
        section('references', rep)
        cand = os.path.join(out_dir, stem + '_refs.docx')
        if annotate_copy and os.path.exists(cand):
            refs_copy = cand
    except Exception as e:
        section('references', ['could not run (%s)' % str(e)[:100]])
    # -- the structure-side checks
    if cif:
        try:
            from pxrd_review import bv_check as B
            text = B.run(cif, table=docx, out_dir=out_dir, quiet=True)[4]
            tab = text.split('MANUSCRIPT TABLE CHECK', 1)
            lines = ['MANUSCRIPT TABLE CHECK' + tab[1]] if len(tab) > 1 else text.split('\n')
            lines = [ln for ln in '\n'.join(lines).split('\n') if ln.strip()]
            section('bond tables (bv_check --table)', lines)
            for ln in lines:
                if not ln.strip().startswith('note:') and _FLAG.search(ln) and 'row' in ln:
                    flags.append((ln.strip(), _quoted(ln)))
        except Exception as e:
            section('bond tables', ['could not run (%s)' % str(e)[:100]])
        try:
            from pxrd_review import cif_audit as CA
            out = CA.audit(cif, docx, checkcif)
            section('.cif audit', out['lines'][1:])
            for r in out['records']:
                if r['severity'] == 'flag':
                    flags.append((r['text'], _quoted(r['text'])))
        except Exception as e:
            section('.cif audit', ['could not run (%s)' % str(e)[:100]])
        try:
            from pxrd_review import pxrd_audit as PA
            out = PA.audit(docx, cif)
            section('powder table', out['lines'][1:])
            for r in out['records']:
                if r['severity'] == 'flag':
                    anchors = ['dcalc', 'Icalc'] if r['kind'] == 'cell' else re.findall(r'under dobs (\d+\.\d+)', r['text'])[:1] + ['dobs']
                    flags.append((r['text'], anchors))
        except Exception as e:
            section('powder table', ['could not run (%s)' % str(e)[:100]])
    else:
        section('.cif', ['no .cif found beside the manuscript — the bond, powder and refinement checks need one (--cif)'])
    # -- the paper against itself
    try:
        from pxrd_review import paper_extract as PE
        chk = PE.check_paper(docx, cif, out_dir=None)
        lines = [ln for ln in chk['lines'] if ln.strip()]
        section('composition, Gladstone–Dale, cell (paper --check)', lines)
        for ln in lines:
            s = ln.strip()
            if ln.startswith('  ') and _FLAG.search(s) and '[unverified]' not in s and 'not a difference' not in s:
                flags.append((s, _quoted(s)))
    except Exception as e:
        section('paper checks', ['could not run (%s)' % str(e)[:100]])
    # -- lints (notes, but a cross-reference to a table or figure the manuscript does not have is a flag)
    try:
        from pxrd_review import lints as LI
        li = LI.lint(docx)
        section('lints', li['lines'][1:])
        for msg, anchor in li['flags']:
            flags.append((msg, [anchor] + _quoted(msg)))
    except Exception as e:
        section('lints', ['could not run (%s)' % str(e)[:100]])
    # -- the annotated copy first, so the report can say how many flags it holds
    n = 0; unplaced = []
    copy = os.path.join(out_dir, stem + '_proposal.docx')
    if annotate_copy:
        n, unplaced = annotate(docx, flags, copy, base=refs_copy)
    # -- the report
    head = ['PROPOSAL REVIEW — %s' % os.path.basename(docx), '  .cif: %s' % (os.path.basename(cif) if cif else 'none'),
            '  checkCIF: %s' % (os.path.basename(checkcif) if checkcif else 'none'),
            '  %d flags: %s; the rest notes' % (len(flags), ('%d written as comments in the copy%s' % (n, ', %d in the report only' % len(unplaced) if unplaced else '')) if annotate_copy else 'report only'), '']
    body = []
    for title, lines in sections:
        body.append('== ' + title)
        body += ['  ' + ln.strip() if not ln.startswith('  ') else ln for ln in lines]
        body.append('')
    report_txt = '\n'.join(head + body)
    rep = os.path.join(out_dir, stem + '_proposal_report.txt')
    with open(rep, 'w', encoding='utf-8') as f:
        f.write(report_txt + '\n')
    if unplaced:
        with open(rep, 'a', encoding='utf-8') as f:
            f.write('\n== flags with no place in the text (report only)\n' + '\n'.join('  ' + u for u in unplaced) + '\n')
    if not quiet:
        print(report_txt)
        print('  report → %s' % rep)
        if annotate_copy:
            print('  annotated copy (%d comments%s) → %s' % (n, ', %d flags unplaced' % len(unplaced) if unplaced else '', copy))
    return {'docx': docx, 'cif': cif, 'checkcif': checkcif, 'report': rep, 'copy': copy if annotate_copy else None, 'flags': flags,
            'sections': sections, 'comments': n, 'unplaced': unplaced}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('target', help='a folder holding the manuscript .docx, .cif and checkCIF report, or the manuscript itself')
    ap.add_argument('--cif'); ap.add_argument('--checkcif'); ap.add_argument('--out')
    ap.add_argument('--no-annotate', action='store_true', help='report only, no annotated copy')
    a = ap.parse_args(argv)
    try:
        review(a.target, a.cif, a.checkcif, a.out, not a.no_annotate)
    except ValueError as e:
        raise SystemExit('pxrd proposal: %s' % e)
    return 0


if __name__ == '__main__':
    sys.exit(main())
