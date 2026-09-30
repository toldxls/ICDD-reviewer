"""Note-grade lints over a manuscript's text (`pxrd lint <manuscript.docx|.pdf>`): spectroscopy and notation.

Every rule is a curated table or a text pattern, and every finding is information for a reviewer to
weigh — none is a verdict:
  spectro   a vibrational band assigned to O–H / H2O / a mineral mode that lies in the C–H stretching
            window (2850–2960 cm⁻¹: grease, epoxy, a mounting medium) or on an atmospheric / cell band
            (CO2 2349 and 667, diamond 1900–2300); a Raman laser line the named instrument does not
            carry (a curated list of systems and their excitation lines);
  notation  cleavage, parting or twinning given with a zone symbol [uvw] where a form {hkl} or plane
            (hkl) is meant; a table caption printed twice under one number; one symmetry-code number
            defined as two operators in two tables.
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


def lint(path):
    """Both lint families over a .docx or .pdf: {'findings': [(message, anchor)], 'lines': [...]}."""
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
        from pxrd_review import paper_extract as PE
        text = PE.text_of(path); paras = re.split(r'\n\s*\n|\n(?=\s*(?:Table|Figure|Fig\.)\s+\d)', text); notes = None
    found = spectro(text) + notation(paras, notes)
    head = 'Lints — %s' % os.path.basename(path)
    return {'findings': found, 'lines': [head] + (['  note: ' + m for m, _a in found] or ['  nothing to report'])}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('manuscript')
    a = ap.parse_args(argv)
    print('\n'.join(lint(a.manuscript)['lines']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
