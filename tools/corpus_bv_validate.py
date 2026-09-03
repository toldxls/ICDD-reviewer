"""Corpus validation of the bond-valence + hydrogen-bond tables: the tool's table from the .cif vs
the paper's published table (extracted from the .pdf text by word positions)."""
import os, re, sys, glob, json, math
import fitz
from pxrd_review import bv_check as B

ANION_LAB = re.compile(r'^(O|OH|OW|Ow|W|Wat|F|Cl|OD|Oh|Hw|H2O)\d*[A-Za-z]?\d*$')

def pdf_lines(page, x_lo=None, x_hi=None):
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

def norm(t):
    return B._norm_label(t.replace('−', '-').replace('–', '-'))

def _clusters(xs, gap=9.0):
    """Split sorted x-centres into columns wherever the gap exceeds `gap` pt."""
    xs = sorted(xs); out = []
    for x in xs:
        if out and x - out[-1][-1] <= gap:
            out[-1].append(x)
        else:
            out.append([x])
    return [sum(c) / len(c) for c in out]

def find_tables(pdf, st):
    """[{'page', 'rows': [[cells]], 'context': str}] — bond-valence tables of this structure.
    Columns come from the data tokens' x-positions (clustered), labelled by the nearest header
    token of the header block (one or two lines above the first anion row)."""
    cats = {norm(x) for r in st.cations for x in r.label.split('/')} | {norm(r.label) for r in st.cations}
    cats = {c for c in cats if not c.startswith('H')}
    anions = {norm(x) for a in st.anions for x in a.label.split('/')} | {norm(a.label) for a in st.anions}
    out = []
    doc = fitz.open(pdf)
    for pno, page in enumerate(doc):
        lines = pdf_lines(page)
        i = 0
        while i < len(lines):
            toks = [w[4] for w in lines[i]['w']]
            hits = [k for k, t in enumerate(toks) if norm(t) in cats]
            if not (len(hits) >= 2 and len(set(norm(toks[k]) for k in hits)) >= 2):
                i += 1; continue
            x_lo = min(w[0] for w in lines[i]['w']) - 150; x_hi = max(w[2] for w in lines[i]['w']) + 100
            # header block: this line and up to two more non-data lines (sub-headers)
            head = list(lines[i]['w']); j = i + 1
            while j < len(lines) and j <= i + 2:
                lw = [w for w in lines[j]['w'] if w[0] >= x_lo and w[2] <= x_hi]
                if not lw or norm(lw[0][4]) in anions or ANION_LAB.match(lw[0][4]) or re.search(r'\d\.\d\d', ' '.join(w[4] for w in lw)):
                    break
                head += lw; j += 1
            # data rows
            raw = []; blank = 0
            while j < len(lines) and j < i + 90:
                lw = [w for w in lines[j]['w'] if w[0] >= x_lo and w[2] <= x_hi]
                if not lw:
                    blank += 1; j += 1
                    if blank > 3: break
                    continue
                first = lw[0][4]
                if norm(first) in anions or ANION_LAB.match(first) or re.match(r'^(Σ|Sum|Total|Σcat|Σanion|Σan)', first):
                    blank = 0; raw.append((first, lw[1:]))
                    if re.match(r'^(Σ|Sum|Total)', first) and not re.match(r'^Σan', first):
                        j += 1; break
                elif raw and all(re.fullmatch(r'[×x]?\d*[↓→]?|[↓→]+|[×x]\d+[↓→]?|\(\d+\)', w[4]) for w in lw):
                    raw[-1] = (raw[-1][0], raw[-1][1] + [w for w in lw])       # superscript marks / esds on their own line
                elif raw:
                    break
                j += 1
            if len(raw) < 2:
                i += 1; continue
            # columns from the data tokens
            xs = [(w[0] + w[2]) / 2 for _, ws in raw for w in ws]
            cols = _clusters(xs)
            if not cols:
                i += 1; continue
            labels = []
            hw = [((w[0] + w[2]) / 2, w[4]) for w in head]
            for cx in cols:
                near = sorted(hw, key=lambda h: abs(h[0] - cx))
                lab = next((t for x, t in near if abs(x - cx) < 28), '?')
                labels.append(lab)
            rows = []
            for first, ws in raw:
                cells = [[] for _ in cols]
                for w in sorted(ws, key=lambda w: w[0]):
                    xc = (w[0] + w[2]) / 2
                    k = min(range(len(cols)), key=lambda c: abs(cols[c] - xc))
                    cells[k].append(w[4])
                rows.append([first] + [' '.join(c) for c in cells])
            txt = page.get_text()
            ctx = ' '.join(m.group(0).replace('\n', ' ') for m in re.finditer(
                r'[^.]{0,120}(Ferraris|hydrogen[- –]bond|Brown|Gagn|Brese|Burns|valence units|Multiplicity)[^.]{0,160}\.', txt, re.I))
            out.append({'page': pno + 1, 'rows': [['Atom'] + labels] + rows, 'context': ctx[:1200]})
            i = j
    return out

HB_HEAD = re.compile(r'^(H|H-?bonds?|Hbond|Hydrogen|hydrogen|Accepted|Donated|Donor|Acceptor|A|D|vu|O[DA]|H\d+|OH\d*|OW\d*|W\d+)$')

def _nums(x):
    return [float(v) for v in re.findall(r'(?<![\d.])\d\.\d\d(?![\d.])', x.replace('−', '-').replace('–', '-'))]

def run(cif, pdfs, verbose=True):
    st = B.Structure(cif)
    tables = []
    for pdf in pdfs:
        try:
            tables += find_tables(pdf, st)
        except Exception as e:
            print('   pdf error', os.path.basename(pdf), e)
    if not tables:
        return None
    best = None
    for ti, t in enumerate(tables):
        for key in ('gh', 'bo', 'ba'):
            for u6 in ('burns', 'params'):
                Pk = B.Params(prefer=key, u6=u6); notes = list(st.notes)
                rk = B.compute(st, Pk, None); st.notes[:] = notes
                lines = B.check_bvs_table(st, rk[0], rk[2], rk[1], [t['rows']], key)
                m = next((re.search(r'(\d+) cells compared, (\d+) disagree', ln) for ln in lines if 'cells compared' in ln), None)
                if not m:
                    continue
                n, bad = int(m.group(1)), int(m.group(2))
                score = n - 2 * bad
                if n and (best is None or score > best[0]):
                    best = (score, n, bad, key, u6, Pk, rk, lines, t)
    if best is None:
        return {'tables': len(tables), 'compared': 0}
    score, n, bad, key, u6, Pk, rk, lines, t = best
    result, anion_sum, cells, hbonds = rk
    don = B.donated(hbonds)
    cat_sum = {}
    for (an, ct), lst in cells.items():
        occ = min(next(r[0] for r in result if r[0].label == ct).occ_total, 1.0)
        cat_sum[an] = cat_sum.get(an, 0.0) + sum(s_ * (na if isinstance(na, (int, float)) else 1) * occ for s_, nd, na in lst)
    acc_tool = {}
    for hb in hbonds:
        acc_tool.setdefault(hb.acceptor.label, []).append(round(hb.s, 2))
    header = t['rows'][0]
    cat_labels = {norm(x) for r in result for x in r[0].label.split('/')}
    cat_cols = {ci for ci, x in enumerate(header) if norm(x) in cat_labels}
    sum_col = next((ci for ci, x in enumerate(header) if re.match(r'^(Σ|Sum|Total|Σan|Σanion)', x)), None)
    hb_cols = [ci for ci, x in enumerate(header) if ci not in cat_cols and ci != sum_col and ci > 0 and (HB_HEAD.match(x.strip()) or x == '?')]
    sig_rows = []; hb_rows = []
    for row in t['rows'][1:]:
        lab = row[0]
        site = st.site(lab) or st.site(norm(lab))
        if site is None or re.match(r'^(Σ|Sum|Total)', lab):
            continue
        an = site.label
        ded = sum(hb.s * hb.n_donor for hb in hbonds if hb.donor.label == an)     # the 'Donated' column, deducted
        tool = {'Σan': anion_sum.get(an, 0.0), 'Σall': anion_sum.get(an, 0.0) + don.get(an, 0.0), 'Σan−donated': anion_sum.get(an, 0.0) - ded, 'Σcat': cat_sum.get(an, 0.0)}
        paper_sum = _nums(row[sum_col]) if sum_col is not None and sum_col < len(row) else []
        if paper_sum:
            ps = paper_sum[-1]
            fit = min(tool.items(), key=lambda kv: abs(kv[1] - ps))
            sig_rows.append((an, ps, fit[0], round(fit[1], 2), round(tool['Σan'], 2), an in don))
        paper_hb = [v for ci in hb_cols if ci < len(row) for v in _nums(row[ci])]
        tool_hb = sorted(acc_tool.get(an, []))
        if paper_hb or tool_hb:
            hb_rows.append((an, sorted(paper_hb), tool_hb))
    return {'tables': len(tables), 'compared': n, 'disagree': bad, 'params': key, 'u6': u6, 'lines': lines, 'sig_rows': sig_rows,
            'hb_rows': hb_rows, 'hb_cols': [header[ci] for ci in hb_cols], 'header': header, 'rows': t['rows'][1:],
            'context': t['context'][:900], 'notes': [x for x in st.notes if 'assumed' not in x],
            'hbonds': [(h.donor.label, h.acceptor.label, round(h.d, 3), round(h.s, 2), h.via) for h in hbonds],
            'has_h': any(x.element == 'H' for x in st.sites), 'page': t['page']}

def pairs(folder):
    cifs = glob.glob(os.path.join(folder, '*.cif')); pdfs = glob.glob(os.path.join(folder, '*.pdf'))
    out = []
    for c in sorted(cifs):
        ids = set(re.findall(r'I\d{6}', os.path.basename(c))) | set(re.findall(r'^\d{4,5}', os.path.basename(c)))
        m = [p for p in pdfs if any(i in os.path.basename(p) for i in ids)]
        if m:
            out.append((c, sorted(m)))
    return out

if __name__ == '__main__':
    folders = sys.argv[1:]
    summary = []
    for folder in folders:
        for cif, pdfs in pairs(folder):
            try:
                r = run(cif, pdfs)
            except Exception as e:
                print('==== %s: ERROR %s' % (os.path.basename(cif), e)); continue
            name = os.path.basename(cif)[:44]
            if r is None:
                print('==== %-44s no bond-valence table found in %s' % (name, ', '.join(os.path.basename(p) for p in pdfs))); continue
            if not r.get('compared'):
                print('==== %-44s table found (%d) but no cells matched' % (name, r['tables'])); continue
            sig = r['sig_rows']
            ok = sum(1 for a, ps, conv, tv, san, isd in sig if abs(ps - tv) <= 0.05)
            print('==== %-44s cells %d/%d disagree (%s, U6 %s); Σ rows within 0.05: %d/%d; H in cif: %s; page %d' % (name, r['disagree'], r['compared'], r['params'], r['u6'], ok, len(sig), r['has_h'], r['page']))
            print('     header:', ' | '.join(r['header']))
            for row in r['rows'][:40]:
                print('       ', ' | '.join(row))
            for ln in r['lines'][1:]:
                print('     .', ln[:150])
            for a, ps, conv, tv, san, isd in sig:
                flag = '' if abs(ps - tv) <= 0.05 else '   <-- off by %+.2f' % (ps - tv)
                print('     Σ %-7s paper %.2f  nearest tool %s %.2f (Σan %.2f)%s%s' % (a, ps, conv, tv, san, ' [donor]' if isd else '', flag))
            if r['hb_cols']:
                print('     H-bond columns in the paper:', r['hb_cols'])
                for a, pv, tv in r['hb_rows']:
                    same = len(pv) == len(tv) and all(abs(x - y) <= 0.02 for x, y in zip(pv, tv))
                    print('     H %-7s paper %s  tool %s%s' % (a, pv, tv, '' if same else '   <--'))
            print('     tool H bonds:', r['hbonds'])
            for x in r['notes']:
                print('     note:', x[:200])
            if r['context']:
                print('     paper:', r['context'][:900])
            summary.append((name, r['disagree'], r['compared'], ok, len(sig)))
    print()
    print('SUMMARY: %d entries; cells %d/%d disagree; Σ rows within 0.05: %d/%d' % (len(summary), sum(s[1] for s in summary), sum(s[2] for s in summary), sum(s[3] for s in summary), sum(s[4] for s in summary)))
