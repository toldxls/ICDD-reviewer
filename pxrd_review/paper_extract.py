#!/usr/bin/env python3
"""
paper_extract — read a mineral description .pdf for what the Tables mode needs, so the tabs can be
filled from the paper and its own calculations re-done its own way:

  • the analytical table: mean wt% per constituent, with range, s.d. and standard where printed;
  • the basis the authors normalised the formula on ("on the basis of 21 O apfu", "Si + Al = 4"),
    and how they treated what the probe cannot give (H2O by difference / by stoichiometry / for
    charge balance, Fe3+/Fe2+ by charge balance, CO2 from the structure …) — as the sentences;
  • the optical data: the mean refractive index (n, or the mean of α β γ / ω ε) and the measured
    and calculated densities;
  • the bond-valence parameter set the paper cites (Gagné & Hawthorne / Brese & O'Keeffe / Brown &
    Altermatt, Burns for U6+, Ferraris & Ivaldi for hydrogen bonds);
  • the powder table: observed (Iobs, dobs) and calculated (dcalc, Icalc, hkl) lines.

    python3 -m pxrd_review.paper_extract paper.pdf [--out DIR]     # prints what it found, writes the data files

Everything is best effort and every value carries the line or sentence it was read from, so the
reviewer can see why. Nothing here decides — the EPMA / GD / PXRD tools take these as inputs.
"""
import os, re, sys, json, argparse
from collections import OrderedDict

from pxrd_review import epma as EP

# ----------------------------------------------------------------------------- pdf text and lines

def page_lines(page, x_lo=None, x_hi=None):
    """The page's words grouped into lines (by baseline, ±3 pt), each line's words by x."""
    words = page.get_text('words')
    words = [w for w in words if (x_lo is None or w[0] >= x_lo) and (x_hi is None or w[2] <= x_hi)]
    words.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines = []
    for w in words:
        yc = (w[1] + w[3]) / 2
        if lines and abs(lines[-1]['y'] - yc) <= 3.0:
            lines[-1]['w'].append(w)
        else:
            lines.append({'y': yc, 'w': [w]})
    for ln in lines:
        ln['w'].sort(key=lambda w: w[0])
    return lines

def text_of(pdf):
    import fitz
    doc = fitz.open(pdf)
    t = ' '.join(page.get_text() for page in doc)
    t = re.sub(r'-\n(?=[a-z])', '', t)                     # de-hyphenate line breaks
    t = re.sub(r'(?<=[A-Za-z\)])\s*¼\s*(?=\d)', ' = ', t)   # a journal font that prints '=' as '¼' ("O ¼ 32")
    return re.sub(r'\s+', ' ', t)

# ----------------------------------------------------------------------------- the analytical table

_CONST = re.compile(r'^(\(NH4\)2O|H2O[+\-]?|H2O\+?|CO2|SO3|SO2|[A-Z][a-z]?\d*O\d*|F|Cl|Br|I|S|Se|Te|[A-Z][a-z]?)[*†‡§¹²³a-d]*$')
_TOTAL = re.compile(r'^(Total|Sum|[-–−]?O\s*[=≡]\s*(F|Cl|S|F,Cl|Cl,F)(,Cl)?)$', re.I)
_NUM = re.compile(r'^[-–−]?\d+\.\d+$|^\d+$')
_NUM_ESD = re.compile(r'^(\d+\.\d+)\((\d+(?:\.\d+)?)\)$')
_RANGE1 = re.compile(r'^(\d+\.\d+)\s*[-–—]\s*(\d+\.\d+)$')
_NA = re.compile(r'^(n\.?d\.?|b\.?d\.?l?\.?|[-–—]|bdl|nd|n/a)$', re.I)

def _constituent_ok(tok):
    t = re.sub(r'[*†‡§¹²³]+$', '', tok)
    if _TOTAL.match(t):
        return t, 'total'
    m = _CONST.match(t)
    if not m:
        return None, None
    c = m.group(1)
    m2 = re.fullmatch(r'([A-Z][a-z]?)2O', c)
    if m2 and EP._USUAL_OXIDE.get(m2.group(1), '').startswith(m2.group(1) + '2O'):
        c = EP._USUAL_OXIDE[m2.group(1)]                    # the O count was a lost subscript
    try:
        EP.parse_constituent('N2H8O' if c == '(NH4)2O' else c.rstrip('+-'))
    except ValueError:
        return None, None
    return c, 'constituent'

def _numbers(tokens):
    """Fold 'a – b' triples into ranges; return [(kind, value)] with kind num | range | text."""
    out = []; i = 0
    while i < len(tokens):
        t = tokens[i].replace('−', '-').replace('–', '-').replace('—', '-')
        m = _RANGE1.match(t)
        if m:
            out.append(('range', (float(m.group(1)), float(m.group(2))))); i += 1; continue
        if _NUM.match(t) and i + 2 < len(tokens) and tokens[i + 1] in ('-', '–', '—', '−') and _NUM.match(tokens[i + 2].replace('−', '-')):
            out.append(('range', (float(t), float(tokens[i + 2].replace('−', '-'))))); i += 3; continue
        if _NUM.match(t):
            out.append(('num', float(t))); i += 1; continue
        m = _NUM_ESD.match(t)
        if m:                                               # '38.23(58)': the value, then its s.d. in the last digits
            v, e = m.group(1), m.group(2)
            sd = float(e) if '.' in e else int(e) * 10 ** (-(len(v) - v.index('.') - 1))
            out.append(('num', float(v))); out.append(('esd', round(sd, 4))); i += 1; continue
        if _NA.match(t):
            out.append(('na', None)); i += 1; continue
        out.append(('text', tokens[i])); i += 1
    return out

_STOP = {'with', 'the', 'and', 'of', 'in', 'is', 'are', 'to', 'a', 'an', 'for', 'by', 'on', 'from', 'that', 'this', 'as', 'at', 'was', 'were', 'which', 'it'}

def _row_at(ws, x_col):
    """One table row in a line of words: the first constituent token (at x_col when known) that
    numbers follow. Two-column pages merge body text into the line, so the cells stop at the last
    number or at a short name within 130 pt of it. -> (constituent, kind, values, x0) or None."""
    toks = [w[4] for w in ws]
    for k, w in enumerate(ws):
        c, kind = _constituent_ok(toks[k])
        if c is None and toks[k] in ('O', '-O', '–O', '−O') and k + 2 < len(toks) and toks[k + 1] in ('=', '≡'):
            c, kind = 'O=' + toks[k + 2], 'total'; rest = ws[k + 3:]
        elif c is not None:
            rest = ws[k + 1:]
        else:
            continue
        if x_col is not None and abs(w[0] - x_col) > 30:
            continue
        vals = _numbers([r[4] for r in rest])
        if not any(kk in ('num', 'range') for kk, _ in vals):
            continue
        # cells end at the last number plus a short name (the standard): body text from the other
        # page column — a comma, a stop word, more than three words — is not a cell
        last_num_x = max(r[2] for r, (kk, _) in zip(rest, vals) if kk in ('num', 'range', 'na'))
        keep = []; words = 0
        for r, (kk, v) in zip(rest, vals):
            if kk in ('num', 'range', 'na'):
                keep.append((kk, v)); words = 0; continue
            if kk != 'text':
                keep.append((kk, v)); continue
            if r[0] > last_num_x + 130 or words >= 3 or v.lower() in _STOP or v.endswith((',', '.', ';', ':')):
                break
            keep.append((kk, v)); words += 1
        # a second table block on the same line (side-by-side tables) starts at the next constituent
        cut = len(keep)
        for idx, (kk, v) in enumerate(keep[1:], 1):
            if kk == 'text' and _constituent_ok(v)[0] and idx + 1 < len(keep) and keep[idx + 1][0] in ('num', 'range'):
                cut = idx; break
        return c, kind, keep[:cut], w[0]
    return None

def epma_table(pdf):
    """The analytical table with the most constituent rows: {'rows': [{'constituent', 'mean',
    'range', 'sd', 'standard'}], 'total', 'header', 'page'}; None when no table is found."""
    import fitz
    doc = fitz.open(pdf)
    best = None
    for pno, page in enumerate(doc):
        lines = page_lines(page)
        i = 0
        while i < len(lines):
            block = []; j = i; x_col = None; gap = 0; last_row = i
            while j < len(lines):
                ws = lines[j]['w']; toks = [w[4] for w in ws]
                if not toks:
                    break
                row = _row_at(ws, x_col)
                if row:
                    c, kind, vals, x0 = row
                    if x_col is None:
                        x_col = x0
                    block.append((c, kind, vals)); j += 1; gap = 0; last_row = j
                elif block and gap < 3:
                    gap += 1; j += 1                         # the other page column's lines, a wrapped name
                else:
                    break
            j = last_row
            n_const = sum(1 for c, k, v in block if k == 'constituent')
            if n_const >= 3 and (best is None or n_const > best['n']):
                head = []
                for k in (i - 1, i - 2):
                    if k >= 0:
                        head = [w[4] for w in lines[k]['w']] + head
                rows = []; total = None
                has_std = bool(re.search(r'standard|std|prob', ' '.join(head), re.I))   # names count only under such a column
                oxide_table = any(re.search(r'O\d*$', c) and c not in ('O',) for c, k, v in block if k == 'constituent')
                for c, kind, vals in block:
                    if c == 'O':
                        continue                                                 # an 'O = F' remnant, never a constituent
                    if oxide_table and re.fullmatch(r'[A-Z][a-z]?', c) and c not in ('F', 'Cl', 'Br', 'I', 'S', 'Se', 'Te'):
                        continue                                                 # an apfu row (Si 5.936) beside the oxides
                    nums = [v for k, v in vals if k == 'num']
                    rng = next((v for k, v in vals if k == 'range'), None)
                    texts = [v for k, v in vals if k == 'text' and not re.fullmatch(r'[a-d*†‡§]+', v)] if has_std else []
                    if kind == 'total':
                        if c.lower().startswith('total') and nums:
                            total = nums[0]
                        continue
                    if not nums:
                        continue
                    mean = nums[0]
                    sd = None
                    # s.d. is the number after the range (Mean | Range | S.D.), else the second number when
                    # the header says so
                    esd = next((v for k, v in vals if k == 'esd'), None)
                    if esd is not None:
                        sd = esd
                    elif rng is not None:
                        after = [v for k, v in vals[[k for k, _ in vals].index('range') + 1:] if k == 'num']
                        sd = after[0] if after else None
                    elif len(nums) >= 2 and any(re.match(r'(S\.?D\.?|σ|e\.?s\.?d)', h, re.I) for h in head):
                        sd = nums[1]
                    rows.append({'constituent': 'N2H8O' if c == '(NH4)2O' else c.rstrip('+-'), 'mean': mean, 'range': rng, 'sd': sd,
                                 'standard': ' '.join(texts) if texts else None})
                best = {'rows': rows, 'total': total, 'header': ' '.join(head)[:200], 'page': pno + 1, 'n': n_const}
                i = j; continue
            i += 1
    return best

# ----------------------------------------------------------------------------- the paper's method

_BASIS = [
    (r'(?:basis of|based on|normali[sz]ed (?:to|on(?: the basis of)?)) (\d+(?:\.\d+)?) (?:O|oxygen|oxygens)(?: atoms)?(?: per formula unit| apfu| pfu)?', 'O'),
    (r'(?:basis of|based on|normali[sz]ed (?:to|on(?: the basis of)?)) (\d+(?:\.\d+)?) (?:anions?|\(O ?\+ ?(?:F|OH|Cl)[^)]*\)|O ?\+ ?(?:F|OH|Cl)|total anions?)', 'O'),
    (r'(?:basis of|based on|normali[sz]ed (?:to|on(?: the basis of)?)) (\d+(?:\.\d+)?) (?:total )?cations', 'cations'),
    (r'(?:basis of|based on|normali[sz]ed (?:to|on(?: the basis of)?)) (\d+(?:\.\d+)?) ((?:[A-Z][a-z]? ?\+ ?)*[A-Z][a-z]?)(?: atoms| apfu| pfu| atom)?\b', 'element'),
    (r'(?:basis of|based on|normali[sz]ed (?:to|on(?: the basis of)?)) ((?:[A-Z][a-z]? ?\+ ?)*[A-Z][a-z]?) ?= ?(\d+(?:\.\d+)?)', 'element2'),
]
_SKIP_EL = {'O', 'OXYGEN', 'ANIONS', 'CATIONS', 'H2O', 'H', 'OH', 'APFU', 'PFU'}

def basis_statement(text):
    """The first basis the paper states near its empirical formula: (basis tuple for epma, the
    sentence) — e.g. (('O', 21.0), '… on the basis of 21 O apfu …'); (None, '') when none."""
    hits = []
    for pat, kind in _BASIS:
        for m in re.finditer(pat, text, re.I):
            lo = max(0, m.start() - 160); pre = text[lo:m.start()]
            cut = max(pre.rfind('. '), pre.rfind('; '))
            sent = text[(lo + cut + 2) if cut >= 0 else lo: m.end() + 80].strip()
            sent = sent[:sent.find('. ', len(sent) - 80) + 1] if sent.find('. ', len(sent) - 80) > 0 else sent
            if kind == 'element':
                spec, n = m.group(2).replace(' ', ''), float(m.group(1))
                if spec.upper() in _SKIP_EL:
                    continue
                b = ('element', spec, n)
            elif kind == 'element2':
                spec = m.group(1).replace(' ', '')
                b = ('O', float(m.group(2))) if spec.upper() == 'O' else ('element', spec, float(m.group(2)))
            else:
                b = (kind, float(m.group(1)))
            near = 1 if re.search(r'empirical formula|formula', text[max(0, m.start() - 200): m.end() + 200], re.I) else 0
            hits.append((-near, m.start(), b, sent))
    if not hits:
        return None, ''
    hits.sort(key=lambda h: (h[0], h[1]))
    return hits[0][2], hits[0][3]

def method_statements(text):
    """Sentences on how the unmeasured constituents were handled. -> {'sentences': [...],
    'h2o': 'difference' | 'stoichiometry' | 'structure' | 'charge' | 'measured' | None,
    'charge': 'Fe' | 'H2O' | None, 'calculated': [constituents]}"""
    sents = re.split(r'(?<=[.;])\s+', text)
    out = {'sentences': [], 'h2o': None, 'charge': None, 'calculated': []}
    for s in sents:
        if len(s) > 400 or len(re.findall(r'\d+\.\d+', s)) > 6:
            continue
        if re.search(r'\b(calculated|by difference|stoichiometr|charge[- ]balance|charge balance|by analogy|assuming)\b', s, re.I) and \
                re.search(r'H2O|CO2|B2O3|Li2O|BeO|Fe2O3|FeO|Fe3\+|Fe2\+|Mn3\+|OH|water|hydrogen|carbon|boron|lithium', s, re.I):
            out['sentences'].append(s.strip())
            if re.search(r'H2O|water|hydrogen', s, re.I):
                if re.search(r'by difference', s, re.I): out['h2o'] = 'difference'
                elif re.search(r'charge', s, re.I): out['h2o'] = out['h2o'] or 'charge'; out['charge'] = out['charge'] or 'H2O'
                elif re.search(r'stoichiometr|ideal formula', s, re.I): out['h2o'] = out['h2o'] or 'stoichiometry'
                elif re.search(r'structure|structural|refinement|crystal[- ]structure', s, re.I): out['h2o'] = out['h2o'] or 'structure'
            if re.search(r'Fe2O3|FeO|Fe3\+|Fe2\+', s, re.I) and re.search(r'charge', s, re.I):
                out['charge'] = 'Fe'
            for c in ('H2O', 'CO2', 'B2O3', 'Li2O', 'BeO', 'Fe2O3'):
                if re.search(r'\b' + c + r'\b', s) and re.search(r'calculated|by difference|stoichiometr|charge', s, re.I) and c not in out['calculated']:
                    out['calculated'].append(c)
        if re.search(r'\bH2O\b[^.]{0,60}(TGA|thermogravimetr|Penfield|CHN|measured directly)', s, re.I):
            out['h2o'] = 'measured'; out['sentences'].append(s.strip())
    return out

# ----------------------------------------------------------------------------- optics, density

_F = r'(\d\.\d{2,4})'

def optics(text):
    """{'n': mean refractive index or None, 'n_from': how, 'D_meas', 'D_calc', 'sentences'}"""
    out = {'n': None, 'n_from': '', 'D_meas': None, 'D_calc': None, 'sentences': []}
    t = text.replace('−', '-')
    m = re.search(r'\b(?:n\s*=|n\s*\(?\s*(?:mean|average|calc)\s*\)?\s*=|nmean\s*=|n\s*≈)\s*' + _F, t)
    abg = re.findall(r'\b(?:n?α|nα|alpha)\s*=\s*' + _F + r'.{0,60}?\b(?:n?β|nβ|beta)\s*=\s*' + _F + r'.{0,60}?\b(?:n?γ|nγ|gamma)\s*=\s*' + _F, t)
    we = re.findall(r'\b(?:n?ω|nω|omega)\s*=\s*' + _F + r'.{0,60}?\b(?:n?ε|nε|epsilon)\s*=\s*' + _F, t)
    if abg:
        a, b, g = (float(x) for x in abg[0]); out['n'] = round((a + b + g) / 3, 4); out['n_from'] = 'mean of α %s, β %s, γ %s' % abg[0]
    elif we:
        w, e = (float(x) for x in we[0]); out['n'] = round((2 * w + e) / 3, 4); out['n_from'] = 'mean of ω %s (×2), ε %s' % we[0]
    elif m:
        out['n'] = float(m.group(1)); out['n_from'] = 'n = %s' % m.group(1)
    for key, pat in (('D_meas', r'(?:D\s*meas\.?|Dmeas|measured density|density[^.]{0,50}?(?:measured|floatation|flotation|pycnomet)[^.]{0,40}?)\s*(?:=|is|of|was|:)?\s*' + _F),
                     ('D_calc', r'(?:D\s*calc\.?|Dcalc|calculated density|density[^.]{0,30}?calculated[^.]{0,40}?)\s*(?:=|is|of|was|:)?\s*' + _F)):
        mm = re.search(pat, t, re.I)
        if mm:
            out[key] = float(mm.group(1)); out['sentences'].append(t[max(0, mm.start() - 40): mm.end() + 30].strip())
    if out['n'] and out['n_from']:
        out['sentences'].append(out['n_from'])
    return out

# ----------------------------------------------------------------------------- bond-valence parameters

def bv_statement(text):
    """{'params': 'gh'|'bo'|'ba'|None, 'u6': 'burns'|'params'|None, 'hb': 'oo'|None, 'sentences'}"""
    out = {'params': None, 'u6': None, 'hb': None, 'sentences': []}
    for s in re.split(r'(?<=[.;])\s+', text):
        if len(s) > 400 or not re.search(r'bond[- ]valence|valence units|hydrogen[- ]bond', s, re.I):
            continue
        hit = False
        if re.search(r'Gagn[eé]', s): out['params'] = out['params'] or 'gh'; hit = True
        if re.search(r"Brese", s): out['params'] = out['params'] or 'bo'; hit = True
        if re.search(r'Brown (?:and|&) Altermatt', s): out['params'] = out['params'] or 'ba'; hit = True
        if re.search(r'Burns', s) and re.search(r'U\s*6\s*\+|U6\+|uran', s, re.I): out['u6'] = 'burns'; hit = True
        elif re.search(r'U\s*6\s*\+|U6\+|U6þ', s) and re.search(r'Gagn[eé]', s): out['u6'] = out['u6'] or 'params'; hit = True
        if re.search(r'Ferraris', s): out['hb'] = 'oo'; hit = True
        if hit:
            out['sentences'].append(s.strip())
    if out['params'] == 'gh' and out['u6'] is None and re.search(r'Gagn[eé][^.]{0,120}U6?\+', text):
        out['u6'] = 'params'
    return out

# ----------------------------------------------------------------------------- the powder table

_HKL = re.compile(r'^[-−]?\d{1,2}$')
_PHEAD = re.compile(r'^(I|d|2θ|2theta)_?\(?(obs|calc|meas|c|o)\)?\.?$|^(hkl|h|k|l)$', re.I)

def _powder_columns(ws):
    """The header line of a powder table -> [(x centre, label)] with labels Iobs dobs dcalc Icalc hkl
    (h k l as one column); [] when the line is no such header."""
    cols = []
    for w in ws:
        t = w[4].replace('(', '').replace(')', '')
        m = _PHEAD.match(t)
        if not m:
            continue
        xc = (w[0] + w[2]) / 2
        if m.group(3):
            lab = 'hkl'
            if cols and cols[-1][1] == 'hkl' and xc - cols[-1][0] < 30:
                cols[-1] = ((cols[-1][0] + xc) / 2, 'hkl'); continue
        else:
            lab = m.group(1)[0].upper().replace('2', 'D') + ('obs' if m.group(2).lower() in ('obs', 'meas', 'o') else 'calc')
            lab = lab.replace('Dobs', 'dobs').replace('Dcalc', 'dcalc')
        cols.append((xc, lab))
    labs = [l for _, l in cols]
    return cols if ('dobs' in labs or 'dcalc' in labs) and 'hkl' in labs else []

def _powder_rows_by_columns(lines, start, cols):
    """Rows under a header: tokens go to the nearest column; several blocks per line are handled
    by walking the columns in order."""
    obs, calc = [], []
    order = [c for c in cols]
    n = 0
    for ln in lines[start:]:
        ws = ln['w']
        if not ws:
            continue
        toks = [w[4].replace('−', '-') for w in ws]
        if not any(re.fullmatch(r'\d+\.\d+', t) for t in toks):
            if n > 3:
                break                                            # the table ended
            continue
        cells = {}
        for w in ws:
            xc = (w[0] + w[2]) / 2
            k = min(range(len(order)), key=lambda i: abs(order[i][0] - xc))
            if abs(order[k][0] - xc) > 40:
                continue
            cells.setdefault(k, []).append(w[4].replace('−', '-'))
        # blocks: consecutive columns up to and including each hkl
        block = {}
        for k in range(len(order)):
            lab = order[k][1]
            if k in cells:
                block[lab] = cells[k]
            if lab == 'hkl':
                if block:
                    _powder_emit(block, obs, calc); n += 1
                block = {}
    return obs, calc

def _num1(v):
    try:
        return float(v[0]) if v else None
    except ValueError:
        return None

def _powder_emit(block, obs, calc):
    hk = [t for t in block.get('hkl', []) if _HKL.match(t)]
    hkl = tuple(int(t) for t in hk[-3:]) if len(hk) >= 3 else None
    if hkl is None and len(hk) == 1 and re.fullmatch(r'-?\d{3}', hk[0]):
        hkl = tuple(int(c) for c in hk[0].lstrip('-'))
    d_o, i_o, d_c, i_c = (_num1(block.get(k)) for k in ('dobs', 'Iobs', 'dcalc', 'Icalc'))
    if d_o is not None:
        obs.append((d_o, i_o))
    if d_c is not None and hkl is not None:
        calc.append((d_c, i_c, hkl))

def pxrd_table(pdf):
    """Observed (d, I) and calculated (d, I, hkl) powder lines from the paper's table. The header
    line (Iobs dobs dcalc Icalc h k l, in any order, one or more blocks side by side) fixes the
    columns by position; without one, the tokens' order decides: floats are d, the ints before
    the hkl triple are intensities."""
    import fitz
    doc = fitz.open(pdf)
    obs, calc = [], []
    for page in doc:
        lines = page_lines(page)
        i = 0
        while i < len(lines):
            cols = _powder_columns(lines[i]['w'])
            if cols:
                o, c = _powder_rows_by_columns(lines, i + 1, cols)
                if o or c:
                    obs += o; calc += c
                    i += 1 + max(len(o), len(c)); continue
            i += 1
    if not obs and not calc:
        for page in doc:
            for ln in page_lines(page):
                toks = [w[4].replace('−', '-') for w in ln['w']]
                floats = [k for k, t in enumerate(toks) if re.fullmatch(r'\d+\.\d{2,4}', t)]
                if not floats or not all(re.fullmatch(r'-?\d+(\.\d+)?', t) for t in toks):
                    continue
                lead = floats[0]                                   # ints before the first d: intensities
                k = 0
                while k < len(toks):
                    j = k; fl = []; ints = []
                    seen_hkl = False
                    while j < len(toks):
                        t = toks[j]
                        if '.' in t:
                            if ints and fl and len(ints) >= 3 + lead and False:
                                break
                            fl.append(float(t)); ints_after = 0
                        else:
                            ints.append(int(float(t)))
                        j += 1
                        # a chunk ends after the hkl triple plus the next chunk's leading ints
                        after = [t2 for t2 in toks[j:j + lead + 1]]
                        if fl and len(ints) >= (1 if len(fl) == 2 else 0) + 3 + (lead if len(fl) == 1 and k == 0 else 0) and (j >= len(toks) or (after and '.' in after[-1] if lead else '.' in toks[j])):
                            break
                    if not fl:
                        break
                    body = ints[:len(ints) - (lead if j < len(toks) else 0)] if lead and j < len(toks) else ints
                    if len(body) < 3:
                        break
                    hkl = tuple(body[-3:]); ivals = body[:-3]
                    if len(fl) >= 2:
                        obs.append((fl[0], float(ivals[0]) if ivals else None)); calc.append((fl[1], float(ivals[1]) if len(ivals) > 1 else (float(ivals[0]) if ivals else None), hkl))
                    else:
                        calc.append((fl[0], float(ivals[-1]) if ivals else None, hkl))
                    k = j - (lead if j < len(toks) else 0)
    seen = set(); obs2 = []
    for d, I in obs:
        if (round(d, 3), I) in seen:
            continue
        seen.add((round(d, 3), I)); obs2.append((d, I))
    return obs2, calc

# ----------------------------------------------------------------------------- the paper's empirical formula

def empirical_formula(text):
    """The empirical formula the paper states ("The empirical formula (based on 28 O apfu) is …"):
    (formula text, {element: apfu}, issues). Journal notation is turned into the ICDD form the
    epma parser reads: 'Fe3+1.52' / 'Fe3þ 1.52' charges, Σ sums, '·8H2O', '□' vacancies."""
    t = text.replace('þ', '+').replace('þ', '+')
    for m in re.finditer(r'empirical formula[^.;]{0,140}?\s(?:is|=|:)\s*([\(\[A-Z□][^\s].{0,320})', t, re.I):
        f = m.group(1)
        f = re.split(r'\s(?=[a-z])|, |; |\. ', f)[0]              # the formula ends where prose (or the next clause) starts
        if not re.search(r'\d', f[:20]) and not f.startswith(('(', '[')):
            continue
        norm = _journal_to_icdd(f)
        counts, ox, issues = EP.parse_icdd_formula(norm, has_sulfur='S' in counts_guess(norm))
        if counts and sum(1 for k in counts if k not in ('H', 'O')) >= 1:
            return f.strip(), counts, issues
    return '', {}, []

def counts_guess(norm):
    return set(re.findall(r'[A-Z][a-z]?', norm))

def _journal_to_icdd(f):
    """'(NH4)1.895Na0.065' -> '( N H4 )1.895 Na0.065'; 'Fe3+1.52' -> 'Fe1.52 +3'; 'Σ2.000' kept; '·8H2O' -> '!8 H2 O'."""
    f = f.replace('·', ' ! ').replace('•', ' ! ').replace('□', '?').replace('−', '-').replace('–', '-')
    f = re.sub(r'([)\]])\s*6(\d\.\d+)', r'\1 Σ\2', f)                               # ']60.90': a Σ printed as '6' (font)
    f = re.sub(r'\b[AMXYZT]\d(?:\+[AMXYZT]\d)?(?=[\(\[])', ' ', f)                     # site labels A1[…], M2+M3(…)
    f = re.sub(r'([A-Z][a-z]?)(\d)\+\s*(\d+\.\d+|\d+)', r'\1\3 +\2', f)          # Fe3+1.52  -> Fe1.52 +3
    f = re.sub(r'([A-Z][a-z]?)(\d)\+', r'\1 +\2', f)                                  # Fe3+ (no count)
    f = re.sub(r'\(NH4\)', '( N H4 )', f)
    f = re.sub(r'(?<=!)\s*(\d+(?:\.\d+)?)?\s*H2O', lambda m: ' %s H2 O' % (m.group(1) or ''), f)
    f = re.sub(r'\(OH\)', '( O H )', f)
    f = re.sub(r'H2O', ' H2 O ', f)
    f = re.sub(r'([A-Z][a-z]?)(\d+\.\d+|\d+)', r'\1\2 ', f)                          # a space after every count
    f = re.sub(r'([)\]])\s*Σ\s*', r'\1 Σ', f)
    return re.sub(r'\s+', ' ', f).strip(' .')

# ----------------------------------------------------------------------------- the checks (manuscript tool)

def check_composition(ex, text):
    """Re-do the paper's reduction from its own table, basis and method, against its own empirical
    formula. -> {'ok', 'lines', 'formula', 'basis', 'result'}; None when the paper gives no table
    or no formula."""
    e = ex.get('epma')
    if not e or not e['rows']:
        return None
    ftxt, counts, f_issues = empirical_formula(text)
    if not counts:
        return None
    wt = {r['constituent']: r['mean'] for r in e['rows']}
    bases = [ex['basis']] if ex.get('basis') else []
    has_s = any(c in ('S', 'SO3', 'SO2') for c in wt)
    r = EP.replicate_formula(wt, counts, bases, ex.get('name') or 'paper') if bases else None
    if r is None or r['score'] > 0.03 or r.get('factor'):
        alt = EP.replicate_formula(wt, counts, [b for b in EP.basis_candidates(counts) if b not in bases], ex.get('name') or 'paper')
        if alt is not None and (r is None or alt['score'] < r['score'] - 0.01):
            r = alt
    if r is None:
        return {'ok': False, 'lines': ['the paper\'s wt% table and its empirical formula could not be reconciled on any basis'], 'formula': ftxt, 'basis': None, 'result': None}
    lines = []
    b = r['basis']
    lines.append('composition: %d constituents re-reduced on %s%s → rms deviation of the cations %.1f%%' % (
        len(wt), EP._basis_label(b), '' if ex.get('basis') == b else (' (the paper states %s; that does not reproduce its formula)' % EP._basis_label(ex['basis']) if ex.get('basis') else ' (basis inferred: the paper does not state one)'), 100 * r['score']))
    if r.get('factor'):
        lines.append('the published coefficients are the replicated ones ÷ %.3f — a different basis than the one read' % r['factor'])
    for el, v, t, note in r['diffs']:
        lines.append('  %s: paper %.3f, from the paper\'s own wt%% %s (%s)' % (el, v, ('%.3f' % t) if t is not None else '—', note))
    if r['unanalysed']:
        lines.append('  calculated by the authors, not analysed: %s' % ', '.join(r['unanalysed']))
    for x in f_issues:
        lines.append('  ! formula: ' + x)
    ok = not r['diffs'] and not f_issues
    if ok:
        lines.append('  every coefficient of the published formula follows from the published wt%')
    return {'ok': ok, 'lines': lines, 'formula': ftxt, 'basis': b, 'result': r}

def check_paper(pdf, cif=None, out_dir=None):
    """The paper against itself and its .cif: {'extract', 'composition', 'bv', 'lines'} — the lines
    are what a manuscript review prints under 'Composition' and 'Bond valence'."""
    text = text_of(pdf)
    ex = extract(pdf, out_dir, None, write=bool(out_dir))
    out = {'extract': ex, 'composition': check_composition(ex, text), 'bv': None, 'lines': []}
    if out['composition']:
        out['lines'] += out['composition']['lines']
    elif ex.get('epma'):
        out['lines'].append('composition: an analytical table was read but no empirical formula sentence was found to check it against')
    if cif:
        try:
            from pxrd_review import bv_check as B
            from pxrd_review.tables import journal
            st = B.Structure(cif)
            tabs = bv_tables(pdf, st)
            if tabs:
                cited = (ex['bv'].get('params') or 'gh', ex['bv'].get('u6') or 'burns')
                best = None
                for key in ('gh', 'bo', 'ba'):
                    for u6 in ('burns', 'params'):
                        P = B.Params(prefer=key, u6=u6); notes = list(st.notes)
                        rk = B.compute(st, P, None, 'oo'); st.notes[:] = notes
                        lines = B.check_bvs_table(st, rk[0], rk[2], rk[1], [t['rows'] for t in tabs], B.PARAM_NAMES[key])
                        hits = [re.search(r'(\d+) cells compared, (\d+) disagree', ln) for ln in lines]
                        n = sum(int(m.group(1)) for m in hits if m); bad = sum(int(m.group(2)) for m in hits if m)
                        if n and (best is None or (bad, 0 if (key, u6) == cited else 1) < best[:2]):
                            best = (bad, 0 if (key, u6) == cited else 1, key, u6, P, lines, n)
                if best is not None:
                    bad, _, key, u6, P, lines, n = best
                    out['bv'] = {'tables': len(tabs), 'lines': lines, 'params': key, 'u6': u6, 'cited': cited, 'compared': n, 'disagree': bad}
                    head = 'bond valence: the paper\'s table (p%d) vs the .cif — agrees best with %s%s' % (
                        tabs[0]['page'], P.note(), '' if (key, u6) == cited else ' (the paper cites %s%s)' % (B.PARAM_NAMES.get(cited[0], cited[0]), ', U6+ from Burns' if cited[1] == 'burns' else ''))
                    out['lines'] += [head] + ['  ' + ln for ln in lines]
            else:
                out['lines'].append('bond valence: no bond-valence table found in the pdf (nothing to check against the .cif)')
        except Exception as ex_:
            out['lines'].append('bond valence: could not check (%s)' % ex_)
    return out

def bv_tables(pdf, st):
    """The paper's bond-valence tables (anion rows × cation columns) as row lists, read from the
    pdf by word positions: the header line names ≥2 of the structure's cations; columns are the
    data tokens' x-clusters labelled by the nearest header token."""
    import fitz
    from pxrd_review import bv_check as B
    norm = lambda t: B._norm_label(t.replace('−', '-').replace('–', '-'))
    cats = {norm(x) for r in st.cations for x in r.label.split('/')} | {norm(r.label) for r in st.cations}
    cats = {c for c in cats if not c.startswith('H')}
    anions = {norm(x) for a in st.anions for x in a.label.split('/')} | {norm(a.label) for a in st.anions}
    an_re = re.compile(r'^(O|OH|OW|Ow|W|Wat|F|Cl|OD|Oh|Hw|H2O)\d*[A-Za-z]?\d*$')
    out = []
    doc = fitz.open(pdf)
    for pno, page in enumerate(doc):
        lines = page_lines(page)
        i = 0
        while i < len(lines):
            toks = [w[4] for w in lines[i]['w']]
            hits = [k for k, t in enumerate(toks) if norm(t) in cats]
            if not (len(hits) >= 2 and len({norm(toks[k]) for k in hits}) >= 2):
                i += 1; continue
            x_lo = min(w[0] for w in lines[i]['w']) - 150; x_hi = max(w[2] for w in lines[i]['w']) + 100
            head = list(lines[i]['w']); j = i + 1
            while j < len(lines) and j <= i + 2:
                lw = [w for w in lines[j]['w'] if w[0] >= x_lo and w[2] <= x_hi]
                if not lw or norm(lw[0][4]) in anions or an_re.match(lw[0][4]) or re.search(r'\d\.\d\d', ' '.join(w[4] for w in lw)):
                    break
                head += lw; j += 1
            raw = []; blank = 0
            while j < len(lines) and j < i + 90:
                lw = [w for w in lines[j]['w'] if w[0] >= x_lo and w[2] <= x_hi]
                if not lw:
                    blank += 1; j += 1
                    if blank > 3: break
                    continue
                first = lw[0][4]
                if norm(first) in anions or an_re.match(first) or re.match(r'^(Σ|Sum|Total|Σcat|Σanion|Σan)', first):
                    blank = 0; raw.append((first, lw[1:]))
                    if re.match(r'^(Σ|Sum|Total)', first) and not re.match(r'^Σan', first):
                        j += 1; break
                elif raw and all(re.fullmatch(r'[×x]?\d*[↓→]?|[↓→]+|[×x]\d+[↓→]?|\(\d+\)', w[4]) for w in lw):
                    raw[-1] = (raw[-1][0], raw[-1][1] + [w for w in lw])
                elif raw:
                    break
                j += 1
            if len(raw) < 2:
                i += 1; continue
            xs = sorted((w[0] + w[2]) / 2 for _, ws in raw for w in ws)
            cols = []
            for x in xs:
                if cols and x - cols[-1][-1] <= 9.0:
                    cols[-1].append(x)
                else:
                    cols.append([x])
            cols = [sum(c) / len(c) for c in cols]
            if not cols:
                i += 1; continue
            hw = [((w[0] + w[2]) / 2, w[4]) for w in head]
            labels = [next((t for x, t in sorted(hw, key=lambda h: abs(h[0] - cx)) if abs(x - cx) < 28), '?') for cx in cols]
            rows = []
            for first, ws in raw:
                cells = [[] for _ in cols]
                for w in sorted(ws, key=lambda w: w[0]):
                    k = min(range(len(cols)), key=lambda c: abs(cols[c] - (w[0] + w[2]) / 2))
                    cells[k].append(w[4])
                rows.append([first] + [' '.join(c) for c in cells])
            out.append({'page': pno + 1, 'rows': [['Atom'] + labels] + rows})
            i = j
    return out

# ----------------------------------------------------------------------------- name, the whole

def mineral_name(text):
    head = text[:1500]
    m = re.search(r'\b([A-Z][a-z]{3,}ite(?:-\([A-Za-z]+\))?)\b', head)
    if m:
        return m.group(1).lower()
    names = re.findall(r'\b([a-z]{4,}ite(?:-\([a-z]+\))?)\b', text.lower())
    if names:
        return max(set(names), key=names.count)
    return ''

def extract(pdf, out_dir=None, stem=None, write=True):
    """Everything the tabs can take from the paper: {'name', 'epma': {...}, 'basis', 'basis_sentence',
    'method', 'optics', 'bv', 'pxrd': {'obs': n, 'calc': n}, 'files': {...}, 'notes': [...]}.
    With write=True the data files the EPMA and PXRD tabs read are written to out_dir:
    <stem>_paper_epma.csv (constituents as columns, one row = the means), <stem>_paper_obs.txt and
    <stem>_paper_calc.txt."""
    text = text_of(pdf)
    stem = stem or os.path.splitext(os.path.basename(pdf))[0]
    out = {'name': mineral_name(text), 'epma': epma_table(pdf), 'method': method_statements(text), 'optics': optics(text),
           'bv': bv_statement(text), 'files': {}, 'notes': []}
    out['basis'], out['basis_sentence'] = basis_statement(text)
    o, c = pxrd_table(pdf)
    out['pxrd'] = {'obs': len(o), 'calc': len(c)}
    if write and out_dir:
        os.makedirs(out_dir, exist_ok=True)
        if out['epma'] and out['epma']['rows']:
            p = os.path.join(out_dir, stem + '_paper_epma.csv')
            rows = out['epma']['rows']
            with open(p, 'w', encoding='utf-8') as f:
                f.write(','.join(r['constituent'] for r in rows) + '\n')
                f.write(','.join('%g' % r['mean'] for r in rows) + '\n')
            out['files']['epma'] = os.path.basename(p)
        if o:
            p = os.path.join(out_dir, stem + '_paper_obs.txt')
            with open(p, 'w', encoding='utf-8') as f:
                f.write('d I\n' + ''.join('%.4f %g\n' % (d, I if I is not None else 0) for d, I in o))
            out['files']['obs'] = os.path.basename(p)
        if c:
            p = os.path.join(out_dir, stem + '_paper_calc.txt')
            with open(p, 'w', encoding='utf-8') as f:
                f.write('d I h k l\n' + ''.join('%.4f %g %d %d %d\n' % (d, I if I is not None else 0, h[0], h[1], h[2]) for d, I, h in c))
            out['files']['calc'] = os.path.basename(p)
    if not out['epma']:
        out['notes'].append('no analytical table found in the pdf')
    if not out['basis']:
        out['notes'].append('no normalisation basis stated — the EPMA tab keeps its own')
    return out

def basis_string(b):
    if not b:
        return ''
    if b[0] == 'O':
        return 'O=%g' % b[1]
    if b[0] == 'cations':
        return 'cations=%g' % b[1]
    return '%s=%g' % (b[1], b[2])

def main(argv=None):
    ap = argparse.ArgumentParser(prog='pxrd paper', description=__doc__.split('\n\n')[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('pdf'); ap.add_argument('--out', help='where the data files go (default <pdf dir>/review_out)')
    ap.add_argument('--check', action='store_true', help="check the paper against itself: its formula from its own table and basis, its bond-valence table against the .cif")
    ap.add_argument('--cif', help='the structure .cif, for the bond-valence check')
    a = ap.parse_args(argv)
    if a.check:
        r = check_paper(a.pdf, a.cif, None)
        print('\n'.join(r['lines']) or 'nothing to check: no analytical table or formula sentence found')
        return 0
    out = extract(a.pdf, a.out or os.path.join(os.path.dirname(os.path.abspath(a.pdf)), 'review_out'))
    e = out['epma']
    print('mineral: %s' % (out['name'] or '?'))
    if e:
        print('analytical table (page %d, %d constituents; header: %s):' % (e['page'], len(e['rows']), e['header'][:80]))
        for r in e['rows']:
            print('  %-8s %8.2f  %s  %s  %s' % (r['constituent'], r['mean'], ('%g–%g' % r['range']) if r['range'] else '', ('sd %g' % r['sd']) if r['sd'] is not None else '', r['standard'] or ''))
        if e['total'] is not None:
            print('  total    %8.2f' % e['total'])
    print('basis: %s   %s' % (basis_string(out['basis']) or '?', ('«%s»' % out['basis_sentence']) if out['basis_sentence'] else ''))
    for s in out['method']['sentences'][:6]:
        print('method: %s' % s[:220])
    print('optics: n %s (%s); D meas %s; D calc %s' % (out['optics']['n'], out['optics']['n_from'], out['optics']['D_meas'], out['optics']['D_calc']))
    print('bond valence: params %s, U6+ %s, H bonds %s' % (out['bv']['params'], out['bv']['u6'], out['bv']['hb']))
    print('powder table: %d observed, %d calculated lines' % (out['pxrd']['obs'], out['pxrd']['calc']))
    for k, v in out['files'].items():
        print('  wrote %s' % v)
    for n in out['notes']:
        print('note: %s' % n)
    return 0

if __name__ == '__main__':
    sys.exit(main())
