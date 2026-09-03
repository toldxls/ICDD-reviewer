"""EPMA corpus replication: the ICDD entry's Analysis field (mean wt% + the published empirical
formula) re-reduced with pxrd_review.epma on the basis the paper states (from the .pdf text) or,
failing that, the basis that best reproduces the formula; every coefficient compared."""
import os, re, sys, glob, math, json
from collections import OrderedDict
import fitz
from pxrd_review import extra_checks as X, epma as EP, gd as GD
USUAL = GD.USUAL_OXIDE

# ----------------------------------------------------------------------------- the Analysis field
WT_RE = re.compile(r'(?<![A-Za-z])(H2O|CO2|SO3|[A-Z][a-z]?\d*O\d*|[A-Z][a-z]?)(?:\s*\([^)]{1,25}\))?[,:]?\s*(\d+\.\d+|\d+)(?![\d.]*[-–])\b')

def parse_analysis(a):
    """(wt {constituent: value}, formula text, n analyses) from the ICDD Analysis string."""
    m = re.search(r'\(wt\.?\s*%\)\s*:?\s*(.*?)(?::|;)\s*([^:;]*(?:[A-Z][a-z]?\d|\)|\]).*)$', a, re.S)
    if not m:
        return None, None, None, []
    wt_txt, formula = m.group(1), m.group(2)
    wt = OrderedDict(); issues = []
    # 'Nb205' (a zero for the O), 'Ti02'
    wt_txt2 = re.sub(r'\b([A-Z][a-z]?\d?)0(\d)\b', lambda m: m.group(1) + 'O' + m.group(2), wt_txt)
    if wt_txt2 != wt_txt:
        issues.append('a zero written for O in the wt%% list (%s)' % ', '.join(set(re.findall(r'\b[A-Z][a-z]?\d?0\d\b', wt_txt))))
        wt_txt = wt_txt2
    for c, v in WT_RE.findall(wt_txt):
        if c in ('O', 'H', 'C', 'N'):
            continue
        if c in wt:
            issues.append('%s listed twice' % c)
        try:
            wt[c] = float(v)
        except ValueError:
            pass
    # constituents named without a value ('ZrO2, TiO2 1.42')
    for m in re.finditer(r'\b([A-Z][a-z]?\d*O\d*|F|Cl)\s*(?:\([^)]*\))?\s*,', wt_txt):
        if m.group(1) not in wt and m.group(1) not in ('O',):
            issues.append('no value for %s' % m.group(1))
    for c in wt:
        try:
            k = EP.parse_constituent(c)
        except ValueError:
            issues.append('unknown constituent %s' % c); continue
        if re.fullmatch(r'[A-Z][a-z]?O', c) and k.element not in ('Mg', 'Ca', 'Sr', 'Ba', 'Be', 'Fe', 'Mn', 'Ni', 'Co', 'Zn', 'Cu', 'Cd', 'Pb', 'Sn', 'Hg', 'Eu', 'Pd', 'Ag', 'Tl'):
            issues.append('unusual constituent %s (a digit missing?)' % c)
    n = re.search(r'average of (\d+)', a)
    return wt, formula.strip(), (int(n.group(1)) if n else None), issues

# ----------------------------------------------------------------------------- the ICDD formula notation
# 'Ca1.00 Pb1.00 Al1.00 [ F6.25 ( O H )0.75 ]S7.00' ; '( Mn1.75 +2 Mg0.25 )sigma2.00' ; '!3.9 H2 O' ; 'O10.02'
TOK = re.compile(r'\(|\)|\[|\]|\{|\}|!|Σ|sigma|Sigma|SIGMA|[A-Z][a-z]?|\d+\.\d+|\d+|[+-]\d+(?:\.\d+)?|\?|□|·|\.|,|\s+')

def parse_icdd_formula(text, has_sulfur=False):
    """{element: count} including H and O; hydrate water after '!' added in. Valence tags
    (+3) are recorded in `ox` per element."""
    t = text.replace('·', ' ! ').replace('•', ' ! ').replace('□', '?')
    t = re.sub(r'([\)\]\}])\s*\$?(?:sigma|Sigma|SIGMA|SS|SI)\s*(?=\d)', r'\1 Σ', t)      # ')$SI0.97', ')SS1.96'
    t = re.sub(r'([\)\]\}])\s*S\s*(?=\d)', r'\1 S?', t)                                    # ')S7.00' — a sum, or sulfur: decided below
    t = re.sub(r'\s+', ' ', t)
    toks = [x for x in re.compile(r'S\?|' + TOK.pattern).findall(t) if x.strip()]
    counts = {}; ox = {}; sums = []; items = [0.0]; stray = []                          # items: per-level item totals
    def add(el, n, mult):
        counts[el] = counts.get(el, 0.0) + n * mult
    i = 0
    def parse_group(i, mult):
        """parse until a closing bracket; returns i after it"""
        while i < len(toks):
            tk = toks[i]
            if tk in ('(', '[', '{'):
                # find the group's own multiplier after its closing bracket
                j = i + 1; depth = 1
                while j < len(toks) and depth:
                    if toks[j] in ('(', '[', '{'): depth += 1
                    elif toks[j] in (')', ']', '}'): depth -= 1
                    j += 1
                # j is after the closing bracket; the multiplier, if numeric, follows (skip sigma sums)
                # the group's own item total first (a dry run at multiplier 1), to tell a sum from a multiplier
                items.append(0.0); saved_counts = dict(counts); saved_ox = dict(ox); saved_sums = list(sums)
                parse_group_inner(i + 1, j - 1, 1.0)
                total = items.pop(); counts.clear(); counts.update(saved_counts); ox.clear(); ox.update(saved_ox); sums[:] = saved_sums
                gm = 1.0; k = j; stated = None
                if k < len(toks) and toks[k] in ('Σ', 'sigma', 'Sigma', 'SIGMA'):
                    k += 1
                    if k < len(toks) and re.match(r'^\d', toks[k]):
                        stated = float(toks[k]); k += 1                          # the stated sum: a self-check
                elif k < len(toks) and toks[k] == 'S?':
                    # ')S13.11': sulfur only when the analysis has sulfur and the number is no sum
                    if k + 1 < len(toks) and re.match(r'^\d', toks[k + 1]) and (not has_sulfur or abs(float(toks[k + 1]) - total) <= max(0.06, 0.1 * total)):
                        stated = float(toks[k + 1]); k += 2
                    else:
                        toks[k] = 'S'                                            # sulfur: parsed as an element below
                elif k < len(toks) and re.match(r'^\d+(\.\d+)?$', toks[k]):
                    v = float(toks[k])
                    if '.' in toks[k] and abs(v - total) <= max(0.06, 0.1 * total):
                        stated = v; k += 1                                       # ']7.00' after O5.91 OH1.09: a sum written without Σ
                    else:
                        gm = v; k += 1
                items.append(0.0)
                parse_group_inner(i + 1, j - 1, mult * gm)
                got = items.pop()
                items[-1] += gm
                if stated is not None:
                    sums.append((stated, got))
                i = k; continue
            if tk in (')', ']', '}'):
                if len(items) == 1:                                              # a stray closer at the top level
                    stray.append(tk); i += 1
                    if i < len(toks) and toks[i] in ('S?', 'Σ') and i + 1 < len(toks) and re.match(r'^\d', toks[i + 1]):
                        i += 2                                                   # … and its sum
                    continue
                return i + 1
            if tk == '!':
                # hydrate water: '!3.9 H2 O' or '! H2 O'
                n = 1.0; i += 1
                if i < len(toks) and re.match(r'^\d+(\.\d+)?$', toks[i]):
                    n = float(toks[i]); i += 1
                # consume 'H2 O' / 'H2O'
                if i + 2 < len(toks) and toks[i] == 'H' and toks[i + 1] == '2' and toks[i + 2] == 'O':
                    add('H', 2, n * mult); add('O', 1, n * mult); i += 3
                elif i + 1 < len(toks) and toks[i] == 'H' and toks[i + 1] == 'O':
                    add('H', 1, n * mult); add('O', 1, n * mult); i += 2
                continue
            if tk in ('?', 'S?'):
                if tk == 'S?':
                    toks[i] = 'S'; continue
                n = 1.0; i += 1                                                  # a vacancy: counts as an item only
                if i < len(toks) and re.match(r'^\d+(\.\d+)?$', toks[i]):
                    n = float(toks[i]); i += 1
                items[-1] += n; continue
            if tk == 'O' and i + 2 < len(toks) and toks[i + 1] == 'H' and re.match(r'^\d+(\.\d+)?$', toks[i + 2]):
                n = float(toks[i + 2]); add('O', n, mult); add('H', n, mult); items[-1] += n; i += 3; continue   # 'OH1.09' = (OH)1.09
            if re.match(r'^[A-Z][a-z]?$', tk):
                el = tk; n = 1.0; i += 1
                if i < len(toks) and re.match(r'^\d+(\.\d+)?$', toks[i]):
                    n = float(toks[i]); i += 1
                    # 'Fe3 C1.01' / 'V5 C0.01': the number was the charge, the count follows the C
                    if i + 1 < len(toks) and toks[i] == 'C' and re.match(r'^\d+(\.\d+)?$', toks[i + 1]) and n in (1, 2, 3, 4, 5, 6, 7) and el != 'C':
                        ox[el] = int(n); n = float(toks[i + 1]); i += 2
                if i < len(toks) and re.match(r'^[+-]\d+(\.\d+)?$', toks[i]):
                    ox[el] = float(toks[i]); i += 1
                add(el, n, mult); items[-1] += n; continue
            i += 1
        return i
    def parse_group_inner(a, b, mult):
        sub = toks[a:b]
        saved = toks[:]
        toks[:] = sub
        parse_group(0, mult)
        toks[:] = saved
    parse_group(0, 1.0)
    if stray:
        sums.append(('unbalanced bracket', 0.0))
    return counts, ox, sums

# ----------------------------------------------------------------------------- the paper's basis
BASIS_PATTERNS = [
    (r'basis of (\d+(?:\.\d+)?) (?:O|oxygen|oxygens)(?: atoms)?(?: per formula unit| apfu| pfu)?', 'O'),
    (r'based on (\d+(?:\.\d+)?) (?:O|oxygen|oxygens)(?: atoms)?', 'O'),
    (r'(?:basis of|based on|normalized to|normalised to) (\d+(?:\.\d+)?) (?:anions?|\(O ?\+ ?(?:F|OH)[^)]*\)|O ?\+ ?F|O ?\+ ?OH)', 'anions'),
    (r'(?:basis of|based on|normalized to|normalised to) (\d+(?:\.\d+)?) (?:total )?cations', 'cations'),
    (r'(?:basis of|based on|normalized to|normalised to) (\d+(?:\.\d+)?) ((?:[A-Z][a-z]? ?\+ ?)*[A-Z][a-z]?)(?: atoms| apfu| pfu| atom)?\b', 'element'),
    (r'(?:basis of|based on|normalized to|normalised to) ((?:[A-Z][a-z]? ?\+ ?)*[A-Z][a-z]?) ?= ?(\d+(?:\.\d+)?)', 'element2'),
]

def paper_basis(pdf_paths):
    """[(kind, N or element spec, phrase)] found in the paper text."""
    out = []
    for p in pdf_paths:
        try:
            doc = fitz.open(p)
        except Exception:
            continue
        txt = ' '.join(page.get_text() for page in doc)
        txt = re.sub(r'-\n', '', txt); txt = re.sub(r'\s+', ' ', txt)
        for pat, kind in BASIS_PATTERNS:
            for m in re.finditer(pat, txt, re.I):
                phrase = txt[max(0, m.start() - 60): m.end() + 40]
                if kind == 'element':
                    spec = m.group(2).replace(' ', ''); n = float(m.group(1))
                    if spec.upper() in ('O', 'OXYGEN', 'ANIONS', 'CATIONS', 'H2O', 'H', 'OH'):
                        continue
                    out.append(('element', spec, n, phrase))
                elif kind == 'element2':
                    spec = m.group(1).replace(' ', '')
                    if spec.upper() == 'O':
                        out.append(('O', None, float(m.group(2)), phrase))
                    else:
                        out.append(('element', spec, float(m.group(2)), phrase))
                else:
                    out.append((kind, None, float(m.group(1)), phrase))
    # dedupe
    seen = set(); uniq = []
    for k in out:
        key = (k[0], k[1], k[2])
        if key not in seen:
            seen.add(key); uniq.append(k)
    return uniq

# ----------------------------------------------------------------------------- replication
def dataset(wt, name):
    cons, vals = [], []
    for c, v in wt.items():
        try:
            cons.append(EP.parse_constituent(c)); vals.append(v)
        except ValueError:
            continue
    return EP.Dataset(cons, [vals], ['mean'], {}, name, None)

def formula_elements(counts):
    """cations (non-H, non-O, non-halogen) of the published formula"""
    return {k: v for k, v in counts.items() if k not in ('H', 'O', 'F', 'Cl', 'Br', 'S', 'Se', 'Te') or k in ('S', 'Se', 'Te') and False}

def basis_candidates(counts):
    """Plausible bases the paper may have used, from the formula itself."""
    cands = []
    o_tot = counts.get('O', 0.0) + counts.get('F', 0.0) + counts.get('Cl', 0.0)   # anions incl. the water O
    h2o = counts.get('H', 0.0) / 2
    for n in {round(o_tot), round(o_tot - h2o), round(o_tot - counts.get('H', 0.0) / 2 - counts.get('F', 0.0))}:
        if n > 0:
            cands.append(('O', float(n)))
    cats = {k: v for k, v in counts.items() if k not in ('H', 'O', 'F', 'Cl', 'Br')}
    tot = sum(cats.values())
    if tot > 0 and abs(tot - round(tot)) < 0.06:
        cands.append(('cations', float(round(tot))))
    for el, v in cats.items():
        if v >= 0.9 and abs(v - round(v)) < 0.02:
            cands.append(('element', el, float(round(v))))
    return cands

def replicate(wt, counts, basis, name):
    ds = dataset(wt, name)
    try:
        red = EP.reduce(ds, basis)
    except Exception as e:
        return None, str(e)
    tool = {}
    for k, r in red.rows.items():
        c = r.c
        if c.kind == 'water':
            tool['H'] = tool.get('H', 0.0) + r.apfu
        elif c.kind == 'element-anion':
            tool[c.element] = tool.get(c.element, 0.0) + r.apfu
        else:
            tool[c.element] = tool.get(c.element, 0.0) + r.apfu
    return tool, red

def score(tool, counts):
    """RMS relative deviation over the cations the paper lists."""
    devs = []
    for el, v in counts.items():
        if el in ('H', 'O') or v < 0.05:
            continue
        t = tool.get(el)
        if t is None:
            continue
        devs.append((t - v) / max(v, 0.05))
    return math.sqrt(sum(d * d for d in devs) / len(devs)) if devs else 9.9, len(devs)

def compare(tool, counts, tol_abs=0.02, tol_rel=0.02):
    out = []
    for el, v in counts.items():
        if el == 'O':
            continue
        t = tool.get(el)
        if t is None:
            if v >= 0.05:
                out.append((el, v, None, 'not in the analysis'))
            continue
        d = t - v
        if abs(d) > max(tol_abs, tol_rel * v):
            out.append((el, v, t, '%+.3f' % d))
    return out

def pdfs_for(docx_path, files_dirs):
    ids = set(re.findall(r'I\d{6}', os.path.basename(docx_path)))
    out = []
    for d in files_dirs:
        for p in glob.glob(os.path.join(d, '*.pdf')):
            if any(i in os.path.basename(p) for i in ids):
                out.append(p)
    return sorted(out)

def main(roots, files_dirs, limit=None):
    docx = []
    for r in roots:
        docx += [p for p in glob.glob(os.path.join(r, '**', '*.docx'), recursive=True) if 'review_out' not in p and not os.path.basename(p).startswith('~')]
    docx = sorted(docx, key=lambda p: ('_edited' in p, p))
    seen_ids = set(); uniq = []
    for d in docx:
        ids = tuple(sorted(set(re.findall(r'I\d{6}', os.path.basename(d)))))
        if ids and ids in seen_ids:
            continue
        seen_ids.add(ids); uniq.append(d)
    docx = uniq[:limit] if limit else uniq
    stats = {'entries': 0, 'parsed': 0, 'replicated': 0, 'ok': 0, 'factor_only': 0, 'basis_from_paper': 0}
    results = []
    for d in docx:
        try:
            e = X.parse_entry(d)
        except Exception:
            continue
        a = (e.comments.get('Analysis') or '').strip()
        if not a:
            continue
        stats['entries'] += 1
        name = os.path.basename(d)[:44]
        wt, ftxt, n, issues = EP.parse_icdd_analysis(a)
        if not wt or len(wt) < 2 or not ftxt:
            continue
        has_s = any(c in ('S', 'SO3', 'SO2') for c in wt)
        counts, ox, f_issues = EP.parse_icdd_formula(ftxt, has_s)
        issues = issues + f_issues
        if not counts or sum(1 for k in counts if k not in ('H', 'O')) < 1:
            continue
        stats['parsed'] += 1
        if not re.search(r'\d\.\d', ftxt):
            results.append((name, 'ideal formula only (no decimals) — cannot replicate' + ('; ' + '; '.join(issues) if issues else ''), None)); continue
        if any('group sums' in x or 'unbalanced' in x for x in issues):
            results.append((name, 'formula notation problem — ' + '; '.join(issues), None)); continue
        pb = paper_basis(pdfs_for(d, files_dirs))
        stated = []
        for k in pb:
            if k[0] in ('O', 'anions'):
                stated.append(('O', k[2]))
            elif k[0] == 'cations':
                stated.append(('cations', k[2]))
            elif k[0] == 'element':
                stated.append(('element', k[1], k[2]))
        r = EP.replicate_formula(wt, counts, stated, name) if stated else None
        alt = None
        if r is None or r['score'] > 0.03 or r.get('factor'):
            alt = EP.replicate_formula(wt, counts, [c for c in EP.basis_candidates(counts) if c not in stated], name)
            if alt is not None and (r is None or alt['score'] < r['score'] - 0.01):
                if r is not None:
                    issues.append('the paper states %s but the formula is reproduced with %s' % (EP._basis_label(r['basis']), EP._basis_label(alt['basis'])))
                r = alt
        if r is None:
            results.append((name, 'no basis reproduces the formula', None)); continue
        stats['replicated'] += 1
        if stated:
            stats['basis_from_paper'] += 1
        diffs = list(r['diffs'])
        for x in issues:
            diffs.append(('*', 0, 0, x))
        if not diffs:
            stats['ok'] += 1
            if r.get('factor'):
                stats['factor_only'] += 1
        results.append((name, r['basis'], {'score': r['score'], 'diffs': diffs, 'stated': stated, 'unanalysed': r['unanalysed'], 'factor': r.get('factor'),
                                           'formula': ftxt[:160], 'wt': dict(wt), 'tool_formula': r['reduction'].formula(), 'total': r['reduction'].total,
                                           'charge': r['reduction'].charge, 'paper_basis_phrases': [k[3] for k in pb][:2]}))
    return stats, results

if __name__ == '__main__':
    roots = sys.argv[1].split(',')
    files_dirs = sys.argv[2].split(',')
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else None
    stats, results = main(roots, files_dirs, limit)
    for name, b, info in results:
        if info is None:
            print('==== %-44s %s' % (name, b)); continue
        flag = 'OK ' if not info['diffs'] else 'DIFF'
        print('==== %-44s %s basis %s (score %.3f)%s%s' % (name, flag, b, info['score'], '' if info['stated'] else '  [basis inferred]', ('  [×%.3f: another basis]' % info['factor']) if info.get('factor') else ''))
        if info['diffs']:
            print('     paper formula:', info['formula'])
            print('     tool  formula:', info['tool_formula'], ' total %.2f charge %+.2f' % (info['total'], info['charge']))
            for el, v, t, note in info['diffs']:
                if el == '*':
                    print('     ! %s' % note)
                else:
                    print('     %-3s paper %.3f  tool %s  %s' % (el, v, ('%.3f' % t) if t is not None else '—', note))
        if info.get('unanalysed'):
            print('     (calculated by the authors, not analysed: %s)' % ', '.join(info['unanalysed']))
            for ph in info['paper_basis_phrases']:
                print('     paper says: …%s…' % ph.replace('\n', ' '))
    print()
    print('STATS', stats)
