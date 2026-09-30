"""A structure .cif against itself and against the manuscript that describes it (`pxrd cifaudit`).

    python3 -m pxrd_review.cif_audit <structure.cif> [--manuscript paper.docx] [--checkcif report.pdf]

Four checks, each a list of records {'kind', 'severity', 'text'} and printed as lines:
  riding   — an H whose Uiso rides (SHELXL's negative Uiso, −1.2 / −1.5) on the atom BEFORE it in the
             embedded .res, compared with the atom it is bonded to in the structure: a riding H listed
             after the wrong atom takes that atom's Ueq (flag, with both Ueq values);
  numbers  — the refinement numbers the manuscript prints (R1, wR2, Rint, GoF, reflections, parameters,
             restraints, μ, F(000), θ, cell, V, Z) against the .cif's own values: a table value that
             differs is a flag; a prose value is a flag when its sentence names the .cif's own reflection
             count or says 'final' (the same refinement, another number) and a note when it merely lies
             near the .cif's (an earlier stage of the refinement reads that way — the corpus: 8 of 97
             papers state such a value, half of them refinement history);
  density  — the density the manuscript states for its ideal formula against Z × M / V from the formula it
             prints, the .cif's cell and Z (never the .cif's own _exptl_crystal_density_diffrn, which is
             what SHELXL made of an unrefined H count): flag over 0.01 g/cm³;
  labels   — a site label the prose names ('Mg2') that the .cif has no site for: flag.
Nothing here writes into any file; the .cif is read only.
"""
import os, re, sys, argparse

from pxrd_review import bv_check as B

TOL_RIDE = 1.25            # an H is bonded to the non-H atom nearest it within this (Å)
D_TOL = 0.01               # g/cm³: a stated density this far from Z·M/V is another formula or another cell
R_NEAR = 0.004             # a prose R1 within this of the .cif's is the same refinement typed differently
R_SAME = 0.0006            # … and within this it is the same number, rounded

# ----------------------------------------------------------------------------- the .res

def res_atoms(st):
    """The atoms of the embedded .res in order: [(label, element, [x, y, z], first U)] — None without one."""
    res = st.block['items'].get('_shelx_res_file')
    if not res:
        return None
    sfac = []
    lines = res.replace('=\n', ' ').split('\n')                    # a continued atom line rejoined
    out = []
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith(('REM', 'TITL')):
            continue
        toks = s.split()
        key = toks[0].upper()
        if key == 'SFAC':
            sfac += [t for t in toks[1:] if re.match(r'^[A-Z][a-z]?$', t)]
            continue
        if key in ('HKLF', 'END'):
            break
        m = re.match(r'^([A-Za-z]{1,2}[A-Za-z0-9\'\"]*)$', toks[0])
        if not m or len(toks) < 6 or key in _RES_CMDS or key.startswith('Q') and re.match(r'^Q\d+$', key):
            continue
        try:
            sf = int(toks[1]); x, y, z = (float(v) for v in toks[2:5]); u = float(toks[6]) if len(toks) > 6 else None
        except ValueError:
            continue
        el = sfac[sf - 1] if 0 < sf <= len(sfac) else None
        out.append((toks[0], el, [x, y, z], u))
    return out

_RES_CMDS = {'CELL', 'ZERR', 'LATT', 'SYMM', 'UNIT', 'TEMP', 'SIZE', 'L.S.', 'BOND', 'ACTA', 'FMAP', 'PLAN', 'WGHT', 'FVAR', 'AFIX', 'HFIX',
             'DFIX', 'DANG', 'SADI', 'SIMU', 'DELU', 'ISOR', 'RIGU', 'EADP', 'EXYZ', 'PART', 'ANIS', 'CONF', 'HTAB', 'EQIV', 'MORE',
             'LIST', 'SHEL', 'OMIT', 'TWIN', 'BASF', 'EXTI', 'SWAT', 'MERG', 'CONN', 'FREE', 'BIND', 'RTAB', 'MPLA', 'GRID', 'SUMP', 'FLAT',
             'CHIV', 'NCSY', 'STIR', 'SPEC', 'RESI', 'MOVE', 'DAMP', 'BLOC', 'XNPD', 'ABIN', 'ANSC', 'ANSR', 'NEUT', 'PRIG', 'LAUE', 'REM'}


def check_riding(st):
    """H atoms riding on the wrong parent: the .res order vs the bonded atom."""
    recs = []
    atoms = res_atoms(st)
    if not atoms:
        return recs
    prev = None
    for lab, el, xyz, u in atoms:
        is_h = (el or '').upper() in ('H', 'D')
        if not is_h:
            prev = (lab, el); continue
        if u is None or u >= 0 or prev is None:
            continue                                            # a refined Uiso: rides on nothing
        site = st.site(lab) or next((s for s in st.sites if s.label.upper() == lab.upper()), None)
        if site is None:
            continue
        near = st.images(site.frac, TOL_RIDE, [s for s in st.sites if s.element not in ('H', 'D')])
        if not near:
            continue
        donor = near[0][0]
        if prev[0].upper() in [x.upper() for x in donor.label.split('/')]:
            continue                                            # 'F1/OH1': a merged site, one of whose labels the .res lists
        parent = st.site(prev[0]) or next((s for s in st.sites if s.label.upper() == prev[0].upper()), None)
        ueq = lambda s: ('%.4f' % s.uiso) if s is not None and s.uiso is not None else '?'
        recs.append({'kind': 'riding', 'severity': 'flag',
                     'text': '%s rides on %s in the .res (Uiso = %g × its Ueq %s), but it is bonded to %s (%.2f Å; Ueq %s): the H is listed after the wrong atom'
                             % (lab, prev[0], abs(u), ueq(parent), donor.label, near[0][1], ueq(donor))})
    return recs

# ----------------------------------------------------------------------------- the manuscript

def docx_lines(path):
    """[(kind, text)] in body order: 'table' for a Word-table row (cells tab-joined) or a tab-separated
    paragraph (a proposal's data table is typed that way), 'p' for prose."""
    from docx import Document
    W = B.W
    body = Document(path).element.body
    out = []
    for el in body.iterchildren():
        if el.tag == W + 'tbl':
            for tr in el.iter(W + 'tr'):
                out.append(('table', '\t'.join(B._cell_text(tc) for tc in tr.findall(W + 'tc'))))
        elif el.tag == W + 'p':
            parts = []
            for x in el.iter():
                if x.tag == W + 't':
                    parts.append(x.text or '')
                elif x.tag == W + 'tab':
                    parts.append('\t')
            t = re.sub(r'\t+', '\t', ''.join(parts)).strip()
            if t:
                out.append(('table' if '\t' in t else 'p', t))
    return out

_NUM = r'(\d+(?:\.\d+)?)(?:\((\d+)\))?'
_D = str.maketrans({'−': '-', '–': '-', '—': '-', ' ': ' '})
# what the manuscript may state, how to read it, and the .cif tag it must equal
STATEMENTS = [
    ('R1 (I > nσ)', re.compile(r'\bR\s*1?\s*(?:\[[^\]]*\]|\((?:obs|F)[^)]*\))?\s*[=:]\s*(0?\.\d{3,4})(?!\d)', re.I), '_refine_ls_r_factor_gt', 'r'),
    ('R1 (all data)', re.compile(r'\bR\s*1?\s*(?:\(all(?: data)?\)|\[all[^\]]*\])\s*[=:]\s*(0?\.\d{3,4})', re.I), '_refine_ls_r_factor_all', 'r'),
    ('wR2 (I > nσ)', re.compile(r'\bwR\s*2?\s*(?:\[[^\]]*\]|\((?:obs|F)[^)]*\))?\s*[=:]\s*(0?\.\d{3,4})(?!\d)', re.I), '_refine_ls_wr_factor_gt', 'r'),
    ('wR2 (all data)', re.compile(r'\bwR\s*2?\s*(?:\(all(?: data)?\)|\[all[^\]]*\])\s*[=:]\s*(0?\.\d{3,4})', re.I), '_refine_ls_wr_factor_ref', 'r'),
    ('Rint', re.compile(r'\bR\s*\(?\s*int\s*\)?\s*[=:]\s*(0?\.\d{3,4})', re.I), '_diffrn_reflns_av_r_equivalents', 'r'),
    ('GoF', re.compile(r'(?:\bGoF|Goodness[- ]of[- ]fit(?: on F2)?|\bS)\s*[=:]\s*(\d\.\d{2,3})', re.I), '_refine_ls_goodness_of_fit_ref', 'gof'),
    ('reflections collected', re.compile(r'\b(\d{3,6})\s*/\s*\d{3,5}\s*;?\s*R\s*\(?int', re.I), '_diffrn_reflns_number', 'int'),
    ('unique reflections', re.compile(r'\b\d{3,6}\s*/\s*(\d{3,5})\s*;?\s*R\s*\(?int', re.I), '_reflns_number_total', 'int'),
    ('parameters', re.compile(r'parameters?\s*/\s*restraints?\s*[=:]?\s*(\d{1,4})\s*/\s*\d{1,3}\b|(?<!/)\bparameters?\s*[=:]?\s*(\d{1,4})\b', re.I), '_refine_ls_number_parameters', 'int'),
    ('restraints', re.compile(r'parameters?\s*/\s*restraints?\s*[=:]?\s*\d{1,4}\s*/\s*(\d{1,3})\b|(?<!/)\brestraints?\s*[=:]?\s*(\d{1,3})\b', re.I), '_refine_ls_number_restraints', 'int'),
    ('μ', re.compile(r'(?:μ|mu|absorption coefficient)\s*(?:\(mm[-−–]1\))?\s*[=:]?\s*(\d+\.\d+)\s*(?:mm)', re.I), '_exptl_absorpt_coefficient_mu', 'f'),
    ('F(000)', re.compile(r'F\s*\(\s*000\s*\)\s*[=:]?\s*(\d{2,6}(?:\.\d+)?)\b'), '_exptl_crystal_f_000', 'f000'),
    ('θmax', re.compile(r'(?:θ|theta)\s*(?:range|max)[^\d\n]{0,30}?(?:\d+\.\d+\s*(?:°|to|–|-)\s*)?(\d+\.\d+)\s*°', re.I), '_diffrn_reflns_theta_max', 'f'),
    ('a', re.compile(r'\ba\s*=\s*' + _NUM + r'\s*Å'), '_cell_length_a', 'cell'),
    ('b', re.compile(r'\bb\s*=\s*' + _NUM + r'\s*Å'), '_cell_length_b', 'cell'),
    ('c', re.compile(r'\bc\s*=\s*' + _NUM + r'\s*Å'), '_cell_length_c', 'cell'),
    ('α', re.compile(r'(?:α|alpha)\s*=\s*' + _NUM + r'\s*°'), '_cell_angle_alpha', 'cell'),
    ('β', re.compile(r'(?:β|beta)\s*=\s*' + _NUM + r'\s*°'), '_cell_angle_beta', 'cell'),
    ('γ', re.compile(r'(?:γ|gamma)\s*=\s*' + _NUM + r'\s*°'), '_cell_angle_gamma', 'cell'),
    ('V', re.compile(r'\bV\s*=\s*' + _NUM + r'\s*Å'), '_cell_volume', 'cell'),
    ('Z', re.compile(r'\bZ\s*=\s*(\d{1,3})\b'), '_cell_formula_units_z', 'int'),
]
_FINAL = re.compile(r'\bfinal\b|Crystal structure\s*:', re.I)
_REFL_ANCHOR = re.compile(r'for\s+(\d{3,6})\s+(?:unique|independent|observed)?\s*reflections', re.I)


def _cif_num(st, tag):
    v = st.block['items'].get(tag)
    return (B._num(v), B._esd(v)) if v not in (None, '', '?', '.') else (None, None)


def check_numbers(st, lines):
    """The manuscript's refinement numbers against the .cif's."""
    recs = []
    seen = set(); compared = set()
    order = [i for i, (k, _t) in enumerate(lines) if k == 'table'] + [i for i, (k, _t) in enumerate(lines) if k != 'table']
    for i in order:                                              # the tables first: a value the abstract repeats must not absorb the table's flag
        kind, raw = lines[i]
        text = raw.translate(_D)
        before = ' '.join(t for _k, t in lines[max(0, i - 4):i])
        # a cell statement is judged whole: a line whose axes are far from the .cif's, or one under a
        # powder heading, is another cell (the powder one, another crystal's, a related mineral's)
        other_cell = re.search(r'powder|PXRD|Gandolfi|Debye', text + ' ' + before, re.I) or any(
            abs(float(m.group(1)) - _cif_num(st, tag)[0]) > 0.02 * _cif_num(st, tag)[0]
            for name, rx, tag, how in STATEMENTS if how == 'cell' and _cif_num(st, tag)[0] for m in rx.finditer(text))
        for name, rx, tag, how in STATEMENTS:
            cif, cif_esd = _cif_num(st, tag)
            if cif is None:
                continue
            for m in rx.finditer(text):
                g = next((x for x in m.groups() if x), None)
                if g is None:
                    continue
                val = float(g)
                esd = None
                if how == 'cell' and m.lastindex and m.lastindex >= 2 and m.group(2):
                    esd = B._esd(g + '(' + m.group(2) + ')')
                if how == 'r' and name.startswith('R1 (I') and re.search(r'all(?: data)?\s*[)\]]?\s*$', text[max(0, m.start() - 25):m.start()], re.I):
                    continue                                    # 'R indices (all data) R1 = …': the all-data row, matched by its own statement
                if how == 'r' and name.startswith('wR2 (I') and re.search(r'\ball(?: data)?\b', text[max(0, m.start() - 60):m.start()], re.I):
                    continue
                key = (name, val)
                if key in seen:
                    continue
                seen.add(key); compared.add(name)
                if how == 'cell':
                    ulp = 10 ** -(len(g.split('.')[1]) if '.' in g else 0) / 2.0
                    tol = max(3 * (esd or 0), 3 * (cif_esd or 0), ulp)
                elif how == 'r':
                    tol = R_SAME
                elif how == 'gof':
                    tol = 0.006
                elif how == 'int':
                    tol = 0.5
                elif how == 'f000':
                    tol = 1.0
                else:
                    tol = max(0.006, 0.002 * abs(cif))
                if abs(val - cif) <= tol:
                    continue
                sent = text.strip()
                if how == 'r' and kind != 'table' and abs(val - cif) > R_NEAR:
                    continue                                    # another structure, another refinement, a comparison
                if how == 'cell' and other_cell:
                    continue
                if kind == 'table':
                    sev, why = 'flag', 'the table'
                elif how == 'cell':
                    sev, why = 'note', 'the text (another determination?)'
                else:
                    anchor = _REFL_ANCHOR.search(text)
                    n_gt = _cif_num(st, '_reflns_number_gt')[0]; n_all = _cif_num(st, '_refine_ls_number_reflns')[0]
                    same = anchor and any(n and abs(float(anchor.group(1)) - n) < 0.5 for n in (n_gt, n_all))
                    if same or _FINAL.search(text):
                        sev, why = 'flag', ('the text, for the .cif\'s own %s reflections' % anchor.group(1)) if same else 'the text (a final value)'
                    else:
                        sev, why = 'note', 'the text (an earlier stage of the refinement, or this one?)'
                recs.append({'kind': 'number', 'severity': sev,
                             'text': '%s: %s gives %s, the .cif %g (%s) — %s' % (name, why, g, cif, tag, _short(sent))})
    if compared:
        recs.insert(0, {'kind': 'summary', 'severity': 'info', 'text': 'numbers: %d kinds read from the manuscript and compared with the .cif (%s); %d differ'
                        % (len(compared), ', '.join(n for n, *_ in STATEMENTS if n in compared), sum(1 for r in recs if r['kind'] == 'number'))})
    return recs


def _short(s, n=110):
    s = re.sub(r'\s+', ' ', s)
    return "'" + (s if len(s) <= n else s[:n] + '…') + "'"

# ----------------------------------------------------------------------------- density

_DENS = re.compile(r'(?:Density\s*\(?\s*calc\.?\s*\)?|D\s*\(?\s*calc\.?\s*\)?|Dcalc|D\s*x|calculated density|Density \(for above formula\)|Density)\s*[=:]?\s*(\d\.\d{2,3})\s*(?:g|Mg)', re.I)
_IDEAL = re.compile(r'(?:ideal(?:ized)?|end-?member|simplified)\s+formula\s*(?:is|of\s+\w+\s+is|[:=])\s*([^\s,;.]{4,80}(?:·\s*\d*\s*H2O)?)', re.I)


def ideal_formula(lines):
    """The ideal formula the manuscript states ('Ideal formula: …', 'The ideal formula is …'): (text, counts) or None."""
    from pxrd_review import paper_extract as PE, epma as EP
    for kind, raw in lines:
        m = _IDEAL.search(raw)
        if not m:
            continue
        f = m.group(1).rstrip(',.;')
        try:
            counts = EP.parse_icdd_formula(PE._journal_to_icdd(f))[0]
        except Exception:
            continue
        if counts and sum(counts.values()) > 1:
            return f, counts
    return None


def check_density(st, lines):
    """Every density the manuscript states for the ideal formula vs Z·M/V from that formula, the .cif's cell and Z."""
    recs = []
    idf = ideal_formula(lines)
    stated = []
    for kind, raw in lines:
        for m in _DENS.finditer(raw.translate(_D)):
            if re.search(r'empirical', raw[m.end():m.end() + 60], re.I):
                continue                                        # for the empirical formula: the composition check's business
            stated.append((float(m.group(1)), raw))
    if not stated:
        return recs
    if idf is None:
        recs.append({'kind': 'density', 'severity': 'note', 'text': 'density: %s stated, but no ideal formula was read to compute it from' % ', '.join('%.3f' % v for v, _ in stated)})
        return recs
    from pxrd_review import gd, epma as EP
    f, counts = idf
    M = sum(EP.ATOMIC_WEIGHTS[el] * n for el, n in counts.items())
    D, Z, V = gd.density_from_cell(st.path, fw=M)
    seen = set()
    cif_d = B._num(st.block['items'].get('_exptl_crystal_density_diffrn') or '')
    for v, raw in stated:
        if v in seen:
            continue
        seen.add(v)
        if abs(v - D) > D_TOL:
            origin = ''
            if cif_d is not None and abs(v - cif_d) <= 0.002:
                origin = " — it is the .cif's own _exptl_crystal_density_diffrn, which the refinement program computed from '%s'" % (st.block['items'].get('_chemical_formula_sum') or '?')
            recs.append({'kind': 'density', 'severity': 'flag',
                         'text': 'density: %.3f stated, but %s (M = %.2f) with Z = %g and V = %.2f Å³ gives %.3f g/cm³%s — %s' % (v, f, M, Z, V, D, origin, _short(raw))})
    vals = sorted(seen)
    if len(vals) > 1 and vals[-1] - vals[0] > 0.004:
        recs.append({'kind': 'density', 'severity': 'flag', 'text': 'density: the manuscript states it as %s in different places' % ' and '.join('%.3f' % v for v in vals)})
    return recs

# ----------------------------------------------------------------------------- site labels

_LABEL = re.compile(r"(?<![A-Za-z0-9/(\[)+½¼¾⅓⅔·])((?:OW|OH|Ow|Oh|W)\d{1,2}[A-Da-d]?|[A-Z][a-z]?\d{1,2}[A-Da-d]?)(?![A-Za-z0-9+/\-−–.(\[·]|\s*[+−–]\s*\d|\)\d)")
_CITATION = re.compile(r'\(\d{4}[a-z]?\)|\b\d{1,4}\s*[–-]\s*\d{1,4}\.\s*$|Crystallogr|Mineral\w*,\s*\d')
_ADP = {'U11', 'U22', 'U33', 'U12', 'U13', 'U23', 'B11', 'B22', 'B33'}
_SG = re.compile(r'space group|setting|\bin\s+[A-Z]-?\d')


def check_labels(st, lines):
    """A site label the prose names that the .cif has no site for."""
    recs = []
    els = {s.element for s in st.sites}
    hits = {}
    for kind, raw in lines:
        if kind != 'p' or _CITATION.search(raw) or '→' in raw:
            continue                                            # a citation's volume number; a reaction equation's O2
        for m in _LABEL.finditer(raw):
            lab = m.group(1)
            if lab in _ADP or lab.upper() in ('H2O', 'CO2', 'SO4', 'PO4'):
                continue
            el = re.match(r'^(OW|OH|Ow|Oh|W|[A-Z][a-z]?)', lab).group(1)
            el = 'O' if el in ('OW', 'OH', 'Ow', 'Oh', 'W') else el
            if el not in els:
                continue                                        # not an element of this structure: a formula, a figure, prose
            if _SG.search(raw[max(0, m.start() - 20):m.start()]) or re.match(r'^[PCIFRAB]\d', lab) and len(lab) <= 3 and re.search(r'/[mcnabd]|\b2[13]\b', raw[m.end():m.end() + 4]):
                continue                                        # a space-group symbol
            if B._find_site(st, lab) is not None:
                continue
            if re.fullmatch(r'[A-Z][a-z]?1', lab) and sum(1 for x in st.sites if x.element == el) == 1:
                continue                                        # 'V1' for the .cif's one V site, labelled 'V'
            ctx = raw[max(0, m.start() - 50):m.end() + 40]
            hits.setdefault(lab, []).append(re.sub(r'\s+', ' ', ctx).strip())
    for lab, ctxs in hits.items():
        recs.append({'kind': 'label', 'severity': 'flag',
                     'text': "site %s is named in the text (%d×) but the .cif has no such site — '…%s…'" % (lab, len(ctxs), ctxs[0])})
    return recs

# ----------------------------------------------------------------------------- run

def audit(cif, manuscript=None, checkcif=None):
    st = B.Structure(cif)
    recs = check_riding(st)
    if manuscript:
        lines = docx_lines(manuscript)
        recs += check_numbers(st, lines) + check_density(st, lines) + check_labels(st, lines)
    out = {'records': recs, 'lines': []}
    L = out['lines']
    L.append('CIF audit — %s%s' % (os.path.basename(cif), (' vs ' + os.path.basename(manuscript)) if manuscript else ''))
    if not recs:
        L.append('  nothing to report')
    for r in recs:
        L.append('  %s%s' % ('note: ' if r['severity'] == 'note' else '', r['text']))
    if checkcif:
        from pxrd_review import checkcif as CC
        L.append('')
        L += CC.run(checkcif)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('cif')
    ap.add_argument('--manuscript', help='the .docx the .cif belongs to')
    ap.add_argument('--checkcif', help='the checkCIF report (.pdf or .txt) to re-tier alongside')
    a = ap.parse_args(argv)
    print('\n'.join(audit(a.cif, a.manuscript, a.checkcif)['lines']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
