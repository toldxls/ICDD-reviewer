"""Note-grade lints over a manuscript's text (`pxrd lint <manuscript.docx|.pdf>`): spectroscopy and notation.

Every rule is a curated table or a text pattern, and every finding is information for a reviewer to
weigh — none is a verdict:
  spectro   a vibrational band assigned to O–H / H2O / a mineral mode that lies in the C–H stretching
            window (2850–2960 cm⁻¹: grease, epoxy, a mounting medium) or on an atmospheric / cell band
            (CO2 2349 and 667, diamond 1900–2300); a Raman laser line the named instrument does not
            carry (a curated list of systems and their excitation lines);
  notation  cleavage, parting or twinning given with a zone symbol [uvw] where a form {hkl} or plane
            (hkl) is meant; a table caption printed twice under one number; one symmetry-code number
            defined as two operators in two tables;
  crossrefs a table or figure the text cites that has no caption (the one lint that is a flag: the
            document's own captions are the oracle), and a caption the text never cites (a note);
  evidence  a valence the formula assigns with no valence-sensitive method named; H2O / OH in the
            formula with no O–H band, thermal analysis or water determination named.
Each finding carries the sentence it comes from and an anchor for a Word comment.
"""
import os, re, sys, argparse

# C–H stretching: aliphatic 2850–2960, aromatic to 3100 — the window an O–H shoulder cannot sit in without a word
CH_WINDOW = (2840.0, 2965.0)
ATMOSPHERIC = [(2349.0, 12.0, 'CO2 (atmospheric, asymmetric stretch)'), (667.0, 6.0, 'CO2 (atmospheric, bend)'),
               (2331.0, 8.0, 'N2 (atmospheric, Raman)'), (1555.0, 8.0, 'O2 (atmospheric, Raman)')]
DIAMOND_CELL = (1900.0, 2300.0)           # the diamond's two-phonon absorption in a compression cell (FTIR)
# Raman systems and the excitation lines they are sold with (the lines a review has met; add, never guess)
LASERS = {
    'xplora': ((532, 638, 785), 'Horiba XploRA / XploRA PLUS'),
    'labram': ((325, 355, 405, 442, 457, 473, 488, 514, 532, 633, 660, 785, 830), 'Horiba LabRAM'),
    'invia': ((325, 405, 442, 457, 488, 514, 532, 633, 785, 830), 'Renishaw inVia'),
    'rm1000': ((514, 633, 785), 'Renishaw RM1000'),
    'dxr': ((455, 532, 633, 780), 'Thermo DXR'),
    'alpha300': ((488, 532, 633, 785), 'WITec alpha300'),
    'senterra': ((532, 633, 785), 'Bruker Senterra'),
    'ntegra': ((473, 532, 633), 'NT-MDT NTEGRA'),
    'confotec': ((532, 633, 785), 'SOL Confotec'),
    'rxn': ((532, 785), 'Kaiser RXN'),
    'thermo almega': ((532, 780), 'Thermo Almega'),
}
_LASER_LINE = re.compile(r'(\d{3}(?:\.\d)?)\s*[- ]?nm\b(?![^.]{0,25}\bgrating)', re.I)
_BAND = re.compile(r'(\d{3,4})(?:\s*\(\s*sh\s*\))?\s*(?:cm|cm[-–−]1|cm\s*[-–−]\s*1)', re.I)
_OH_WORDS = re.compile(r'O[-–—]?H|hydroxyl|water|H2O|hydrogen[- ]bond|ν\s*\(?\s*O', re.I)
_ZONE = re.compile(r'\b(cleavage|parting|twin plane|composition plane|platy|tabular|flattened)\b[^.]{0,80}?(\[\s*[-–−]?\d\s*[-–−]?\d\s*[-–−]?\d\s*\])', re.I)   # a twin AXIS is a direction: 'twin' alone is not linted


def spectro(text):
    """[(message, anchor)] — the spectroscopy lints on the whole text."""
    out = []
    t = text.replace('−', '-').replace('–', '-')
    for m in re.finditer(r'[^.]{0,300}?\b(\d{3,4})(?:\s*(?:and|,)\s*(\d{3,4}))*\s*cm\s*[-]?\s*1[^.]{0,200}', t):
        sent = m.group(0)
        if not _OH_WORDS.search(sent):
            continue
        bands = [float(x) for x in re.findall(r'\b(\d{4}|\d{3})\b(?=\s*(?:,|and|cm|\)))', sent)]
        ch = sorted({b for b in bands if CH_WINDOW[0] <= b <= CH_WINDOW[1]})
        if ch and not re.search(r'C[-–—]?H\b|organic|grease|epoxy|contamin|adhesive|resin|carbon', sent, re.I):
            out.append(('spectroscopy: %s cm⁻¹ %s in the C–H stretching window (%d–%d): an O–H or H2O assignment there is usually a mounting medium, grease or epoxy — '
                        'a C–H band is absent from a Raman spectrum of the same grain if it is not the mineral\'s'
                        % (' and '.join('%g' % b for b in ch), 'lies' if len(ch) == 1 else 'lie', *CH_WINDOW), '%g' % ch[0]))
        for b in bands:
            for c, w, what in ATMOSPHERIC:
                if abs(b - c) <= w and not re.search(r'atmospher|CO2|carbon dioxide|N2|nitrogen', sent, re.I):
                    out.append(('spectroscopy: a band at %g cm⁻¹ coincides with %s' % (b, what), '%g' % b))
        if re.search(r'diamond', t, re.I) and re.search(r'FTIR|infrared|IR\b', sent, re.I):
            for b in bands:
                if DIAMOND_CELL[0] <= b <= DIAMOND_CELL[1]:
                    out.append(('spectroscopy: %g cm⁻¹ lies in the diamond cell\'s two-phonon absorption (%d–%d)' % (b, *DIAMOND_CELL), '%g' % b))
    for key, (lines_, name) in LASERS.items():
        for m in re.finditer(re.escape(key), t, re.I):
            seg = t[m.start(): m.start() + 450]                      # the instrument's sentence and the next: 'using a 248 nm laser' follows the objective
            for lm in _LASER_LINE.finditer(seg):
                lam = float(lm.group(1))
                if not any(abs(lam - x) <= 2 for x in lines_) and 'laser' in seg.lower():
                    out.append(('spectroscopy: a %g nm laser on a %s — that system is supplied with %s nm lines'
                                % (lam, name, '/'.join(str(x) for x in lines_)), lm.group(0)))
    return list(dict.fromkeys(out))


def notation(paragraphs, tables_codes=None):
    """[(message, anchor)] — cleavage/parting/twinning given as a zone symbol, a caption printed twice,
    one code number as two operators. `tables_codes`: {table index: {'caption': n, 'codes': {label: (rot, tr, printed)}}}."""
    out = []
    for p in paragraphs:
        for m in _ZONE.finditer(p):
            sym = re.sub(r'\s', '', m.group(2))
            out.append(("notation: %s given as the zone symbol %s — a cleavage, parting or twin plane is a form {hkl} or a plane (hkl); [uvw] is a direction"
                        % (m.group(1).lower(), sym), m.group(2)))
    caps = {}
    for p in paragraphs:
        m = re.match(r'^\s*(Table|Figure|Fig\.)\s+(\d+)[.:]\s*(.{0,120})', p)
        if m:
            caps.setdefault((m.group(1).rstrip('.'), m.group(2)), []).append(m.group(3).strip())
    for (kind, n), texts in caps.items():
        if len(texts) > 1:
            out.append(("notation: %s %s has %d captions ('%s' / '%s')" % (kind, n, len(texts), texts[0][:60], texts[1][:60]), texts[1][:40]))
    if tables_codes:
        seen = {}; dicts = []
        for ti, v in sorted(tables_codes.items()):
            if any(v.get('codes') is d for d in dicts):
                continue                                            # 'symmetry codes are the same as in Table N': inherited, not defined again
            dicts.append(v.get('codes'))
            for lab, (rot, tr, printed) in (v.get('codes') or {}).items():
                key = tuple(tuple(round(x, 4) for x in r) for r in rot) + (tuple(round(x, 4) for x in tr),)
                if lab in seen and seen[lab][0] != key:
                    out.append(("notation: symmetry code (%s) is '%s' in Table %s and '%s' in Table %s — one number, two operators"
                                % (lab, seen[lab][1], seen[lab][2], printed, v.get('caption') or ti + 1), printed))
                else:
                    seen.setdefault(lab, (key, printed, v.get('caption') or ti + 1))
    return list(dict.fromkeys(out))


# a caption: 'Table 3.' / 'TABLE 3' / 'Fig. 2:' / 'Table 3 Chemical composition' (no stop, a capitalised title) at a line's start
_CAPTION = re.compile(r'^\s*(Supplementary\s+|Suppl\.\s*|Online\s+)?(Table|Figure|Fig\.)\s*(S?\d{1,3})[a-z]?\s*(?:[.:|]|[-–—]\s|(?=\s+(?-i:[A-Z][a-z])))', re.I)   # 'Table 1a.' is Table 1's
_CITE = re.compile(r'\b(Tables?|Figures?|Figs?\.?)\s*(S?\d{1,3}[a-z]?(?:\s*[-–—]\s*S?\d{1,3}[a-z]?)?'
                   r'(?:\s*(?:,|;|and|&)\s*(?!\d{4}\b)S?\d{1,3}[a-z]?(?:\s*[-–—]\s*S?\d{1,3}[a-z]?)?)*)(?!\s*(?:in|of)\s+[A-Z][a-z]+)(?!\s*(?:th|st|nd|rd)\b)')
# a citation that is not of this document's own table: another paper's, a deposited or supplementary one, a book's
_OTHER_DOC = re.compile(r"\btheir\s+(?:Fig|Tab)|\bdeposit|document item|supplement|appendix|\bedition\b|\bin (?:ref|\[)|\bof [A-Z][a-z]+ (?:et al|\()|\bmicrofiche\b", re.I)
_REFS_HEAD = re.compile(r'^\s*(References(?:\s+cited)?|Literature cited|Bibliography)\s*$', re.I)
_CONT = re.compile(r'\(?\b(?:cont(?:inued|\.|d\.)?)\b', re.I)


def _numbers(spec):
    """'3 and 4' / '2–4' / '3a, b' / 'S1' -> the labels named ('3', '4' … ; a letter suffix drops)."""
    out = []
    for part in re.split(r'\s*(?:,|;|and|&)\s*', spec):
        m = re.match(r'(S?)(\d+)[a-z]?(?:\s*[-–—]\s*(S?)(\d+)[a-z]?)?$', part.strip(), re.I)
        if not m:
            continue
        s, a, _s2, b = m.group(1).upper(), int(m.group(2)), m.group(3), m.group(4)
        if b and int(b) >= a and int(b) - a <= 20:
            out += ['%s%d' % (s, n) for n in range(a, int(b) + 1)]
        else:
            out.append('%s%d' % (s, a))
    return out


def crossrefs(paragraphs, docx=True):
    """[(message, anchor, severity)] — a table / figure cited with no caption of that number, and a caption the
    text never cites (note). Captions: 'Table 3.' / 'TABLE 3' / 'Fig. 4:' / 'Table 2 Chemical …' at a paragraph's or a
    line's start, 'Table 1a.' as Table 1's, 'Supplementary Table S1' for the S-numbered set; a '(continued)' caption is
    its first page's. A citation wrapped to a line's start ('given in' ⏎ 'Table 1. The …') is not a caption.
    A cited number with no caption is a FLAG only in a .docx (read cell by cell, every caption in the file), when the
    captions read run 1…n without a gap and the number is past n: a gap says the reader lost captions, a number inside the
    run is such a lost caption, a jump past n+1 whose leading digits are a caption number is a footnote mark or a
    line number glued to the citation ('Table 6¹'), and a year, 'their', 'deposited' or 'of Author (year)' beside the
    citation makes it another document's. In a .pdf the same finding is a note: the text layer loses the last
    table or figure's caption often enough (a rotated table, a caption inside the figure) that on the corpus of
    published papers every such flag was the reader's. The reference list is left out."""
    caps = {'Table': {}, 'Figure': {}}
    cites = {'Table': {}, 'Figure': {}}
    in_refs = False
    for p in paragraphs:
        if _REFS_HEAD.match(p):
            in_refs = True
            continue
        body = p
        prev = ''
        for seg in re.split(r'[\t\n]', p):                    # two captions set side by side share one paragraph, a tab between them; a pdf's caption starts a line
            m = _CAPTION.match(seg)
            # a citation wrapped to a line's start ('are given in' ⏎ 'Table 1. The …') is not a caption: the line before it
            # ends mid-sentence — a caption follows a full stop, a table's last row or a blank line
            if m and prev and re.search(r'[a-z,;(–—-]\s*$', prev):
                m = None
            prev = seg.strip() or prev
            if m:
                kind = 'Table' if m.group(2).lower().startswith('t') else 'Figure'
                label = m.group(3).upper()
                if not _CONT.search(seg[:m.end() + 24]):
                    caps[kind].setdefault(label, seg[:80])
                body = body.replace(seg[:m.end()], ' ', 1)    # the caption's own text may cite another table; its head is not a citation
        if in_refs:
            continue
        for c in _CITE.finditer(body):
            kind = 'Table' if c.group(1).lower().startswith('t') else 'Figure'
            for label in _numbers(c.group(2)):
                cites[kind].setdefault(label, (c.group(0), p))
    whole = ' '.join(paragraphs)
    def runs(nums):
        out, start, prev = [], None, None
        for n in nums + [None]:
            if start is None:
                start = prev = n
            elif n is not None and n == prev + 1:
                prev = n
            else:
                out.append(str(start) if start == prev else '%d–%d' % (start, prev)); start = prev = n
        return ', '.join(out)
    out = []
    for kind in ('Table', 'Figure'):
        if not caps[kind]:
            continue
        word = r'(?:Table|Tab\.)' if kind == 'Table' else r'(?:Figure|Fig\.?)'
        for sup in ('', 'S'):
            have = [k for k in caps[kind] if (k[:1] == 'S') == (sup == 'S')]
            cited = [k for k in cites[kind] if (k[:1] == 'S') == (sup == 'S')]
            missing = [k for k in cited if k not in caps[kind]]
            if not have:
                continue                                      # 'Table S2' cited, no supplementary captions in this file: it travels separately
            nums = sorted(int(re.sub(r'\D', '', k)) for k in have)
            complete = nums[0] == 1 and nums == list(range(1, nums[-1] + 1))
            if missing and len(missing) > max(1, len(cited) // 2):   # most of what is cited has no caption read: the captions are not in this file (or not read), not the citations wrong
                out.append(("cross-reference: %d of the %d %ss the text cites have no caption in this file (%s %s read) — the captions may travel separately"
                            % (len(missing), len(cited), kind.lower(), kind.lower(), sup + runs(nums)), None, 'note'))
                missing = []
            for label in sorted(missing, key=lambda k: int(re.sub(r'\D', '', k) or 0)):
                span, p = cites[kind][label]
                s = p.find(span); sent = p[max(0, s - 50): s + len(span) + 50].strip()
                n = int(re.sub(r'\D', '', label) or 0)
                if _OTHER_DOC.search(sent) or (not docx and re.search(r'\b(?:1[89]|20)\d\d\b', sent)):
                    continue                                  # another document's table, or one deposited elsewhere; in a pdf a year beside the citation is another paper's
                if n > nums[-1] + 1 and any(str(n).startswith(str(k)) and n != k for k in nums):
                    continue                                  # 'Table 6¹' read as Table 61, a line number glued to 'Fig. 2'
                sev = 'flag' if docx and complete and n > nums[-1] else 'note'
                out.append(("cross-reference: %s %s is cited (‘…%s…’) but %s %s %s — its %s captions are %s%s"
                            % (kind, label, sent, 'the manuscript has no' if sev == 'flag' else 'no caption was read for', kind, label,
                               kind.lower(), sup, runs(nums)), span, sev))
            for label in have:
                if label in cites[kind] or not cites[kind]:
                    continue                                  # a file whose text cites no table at all is a supplement or a table file: its captions are cited elsewhere
                n = re.sub(r'\D', '', label)
                mentions = len(re.findall(r'\b%ss?\s*\(?%s%s(?![\d])' % (word, 'S' if sup else '', n), whole))
                if mentions <= 1:                             # the caption is the only place the number occurs (a citation wrapped to a line start still counts)
                    out.append(("cross-reference: %s %s (‘%s’) is never cited in the text" % (kind, label, caps[kind][label][:60]), caps[kind][label][:40], 'note'))
    return out


_VALENCE_IN_FORMULA = re.compile(r'(?<![A-Za-z])(Fe|Mn|Ti|V|Cu|Ce|Eu|Cr|Co|Ni|Sb|As|U|Se|Te|Mo|W|Nb|Sn|Pb|Tl|Bi|S)\s?(\d)\s?[+⁺](?!\s?[a-z])|(?<![A-Za-z])(Fe|Mn|Ti|V|Cu|Ce|Eu|Cr|Co|Ni|Sb|As|U|Se|Te|Mo|W|Nb|Sn|Pb|Tl|Bi)[²³⁴⁵⁶]⁺')   # 'Ca2Fe3+2': no word boundary between the 2 and the Fe
_VALENCE_METHOD = re.compile(r'Mössbauer|Moessbauer|Mossbauer|\bXPS\b|X-ray photoelectron|XANES|XAFS|EXAFS|\bEELS\b|electron energy[- ]loss|wet[- ]chemi|titrat|\bEPR\b|\bESR\b|colorimetr|K ?β|Kβ|flank method|spectrophotometr', re.I)
_VALENCE_ARGUMENT = re.compile(r'bond[- ]valence|charge[- ]balance|electroneutrality|colou?r|pleochro|crystal[- ]chemical|site geometry|bond lengths?|coordination', re.I)
_HYDROUS_FORMULA = re.compile(r'\(OH\)|\bOH\d|H2O|H₂O|\(H3O\)|H3O\b')                      # the formula's own tokens, not the words 'water' / 'hydroxyl' of the prose
_OH_EVIDENCE = re.compile(r'(3[0-7]\d\d)\s*(?:cm|cm[-–−]1|cm\s*[-–−]\s*1)|O[-–—]?H stretch|stretching vibrations? of (?:the )?(?:O[-–—]?H|water|hydroxyl)|thermogravimetr|\bTGA?\b|\bDTA\b|\bDSC\b|weight loss|mass loss|loss on ignition|\bLOI\b|H2O was calculated|calculated (?:from|by|on the basis of)|by difference|Penfield|Karl[- ]Fischer|CHN|hydrogen analys|neutron', re.I)


def evidence(text):
    """[(message, anchor)] — a valence the formula assigns with no valence-sensitive method named (the argument the text
    gives, if any, is quoted); H2O / OH in the formula with no spectroscopic, thermal or analytical evidence named.
    Notes: a valence can rest on bond-valence sums and hydrogen on the structure, and the text may say so in words the
    lint does not read."""
    out = []
    t = text.replace('\xa0', ' ')
    vals = {}
    for m in _VALENCE_IN_FORMULA.finditer(t):
        el = m.group(1) or m.group(3)
        vals.setdefault(el, m.group(0))
    vals = {el: v for el, v in vals.items() if el in ('Fe', 'Mn', 'Ti', 'V', 'Cu', 'Cr', 'Ce', 'Co', 'Eu')}   # the elements whose state a probe cannot give and a mineral takes in more than one
    if vals and not _VALENCE_METHOD.search(t):
        args = sorted({a.lower() for a in _VALENCE_ARGUMENT.findall(t)})
        out.append(('evidence: the formula assigns a valence to %s and the text names no valence-sensitive method (Mössbauer, XPS, XANES, EELS, titration) — %s'
                    % (', '.join('%s (%s)' % (el, v.strip()) for el, v in list(vals.items())[:4]),
                       'the assignment rests on ' + ', '.join(args[:3]) if args else 'no argument for it is read'), next(iter(vals.values())).strip()))
    if _HYDROUS_FORMULA.search(t) and re.search(r'formula', t, re.I) and not _OH_EVIDENCE.search(t):
        out.append(('evidence: the formula carries H2O or OH and the text names no O–H band, thermal analysis, water determination or difference calculation as its evidence', 'H2O'))
    return out


def lint(path):
    """The lint families over a .docx or .pdf: {'findings': [(message, anchor)], 'flags': [(message, anchor)], 'lines': [...]} —
    'findings' is everything (the flags included); a line is prefixed 'note: ' unless it is a flag."""
    from pxrd_review import bv_check as B
    if path.lower().endswith('.docx'):
        from pxrd_review import cif_audit as CA
        lines = CA.docx_lines(path)
        paras = [t for _k, t in lines]
        text = '\n'.join(paras)
        try:
            notes, _ = B.read_table_notes(path)
        except Exception:
            notes = None
    else:
        from pxrd_review import paper_extract as PE, cell_lambda_check as C
        text = PE.text_of(path)                               # one folded line: the band and laser sentences
        raw = C.pdf_text(path) or text                        # the page's lines kept: a caption starts one
        paras = re.split(r'\n\s*\n|\n(?=\s*(?:Table|Figure|Fig\.)\s*S?\d)', raw, flags=re.I); notes = None
    found = [(m, a, 'note') for m, a in spectro(text) + notation(paras, notes) + evidence(text)] + crossrefs(paras, docx=path.lower().endswith('.docx'))
    head = 'Lints — %s' % os.path.basename(path)
    return {'findings': [(m, a) for m, a, _s in found], 'flags': [(m, a) for m, a, s in found if s == 'flag'],
            'lines': [head] + (['  ' + ('' if s == 'flag' else 'note: ') + m for m, _a, s in found] or ['  nothing to report'])}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('manuscript')
    a = ap.parse_args(argv)
    print('\n'.join(lint(a.manuscript)['lines']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
