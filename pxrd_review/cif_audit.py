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
import os, re, sys, math, argparse

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
            if len(toks) > 2 and re.match(r'^-?\d', toks[2]):
                sfac.append(toks[1].capitalize())                        # the long form: one symbol and its scattering-factor terms
            else:
                sfac += [t.capitalize() for t in toks[1:] if re.match(r'^[A-Za-z][A-Za-z]?$', t)]   # 'SFAC CA MN Y': SHELXL keeps the case it was given
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

def res_model(st):
    """The embedded .res as a model: {'fvar': [values], 'atoms': [{'label', 'element', 'xyz', 'sof', 'u', 'part'}],
    'twin': (3×3 matrix, n) or None, 'basf': [values], 'wght': [values]} — None without a .res."""
    res = st.block['items'].get('_shelx_res_file')
    if not res:
        return None
    m = {'fvar': [], 'atoms': [], 'twin': None, 'basf': [], 'wght': []}
    part = 0; sfac = []
    for ln in res.replace('=\n', ' ').split('\n'):
        toks = ln.strip().split()
        if not toks:
            continue
        key = toks[0].upper()
        try:
            if key == 'FVAR':
                m['fvar'] += [float(v) for v in toks[1:]]
            elif key == 'SFAC':
                if len(toks) > 2 and re.match(r'^-?\d', toks[2]):
                    sfac.append(toks[1].capitalize())
                else:
                    sfac += [t.capitalize() for t in toks[1:] if re.match(r'^[A-Za-z][A-Za-z]?$', t)]
            elif key == 'PART':
                part = int(float(toks[1])) if len(toks) > 1 else 0
            elif key == 'TWIN':
                nums = [float(v) for v in toks[1:]]
                m['twin'] = ([nums[0:3], nums[3:6], nums[6:9]] if len(nums) >= 9 else [[-1, 0, 0], [0, -1, 0], [0, 0, -1]], int(nums[9]) if len(nums) > 9 else 2)
            elif key == 'BASF':
                m['basf'] += [float(v) for v in toks[1:]]
            elif key == 'WGHT':
                m['wght'] = [float(v) for v in toks[1:]]
            elif key in ('HKLF', 'END'):
                break
            elif re.match(r'^[A-Za-z]{1,2}[A-Za-z0-9\'\"]*$', toks[0]) and len(toks) >= 6 and key not in _RES_CMDS and not re.match(r'^Q\d+$', key):
                sf = int(toks[1]); xyz = [float(v) for v in toks[2:5]]; sof = float(toks[5]); u = float(toks[6]) if len(toks) > 6 else None
                m['atoms'].append({'label': toks[0], 'element': sfac[sf - 1] if 0 < sf <= len(sfac) else None, 'xyz': xyz, 'sof': sof, 'u': u, 'part': part})
        except (ValueError, IndexError):
            continue
    return m


def sof_value(code, fvar):
    """A SHELXL parameter code -> (value, kind, k): 10 + q is fixed at q ('fixed'); 10k + q is q·fv(k) ('fv');
    −(10k + q) is q·(1 − fv(k)) ('1-fv'); anything else is refined freely ('free')."""
    k = int(abs(code) // 10); q = round(abs(code) - 10 * k, 5)
    if code >= 0 and k == 1:
        return q, 'fixed', None
    if k >= 2 and len(fvar) >= k:
        fv = fvar[k - 1]
        return (q * fv, 'fv', k) if code > 0 else (q * (1.0 - fv), '1-fv', k)
    return (q if k == 0 else None), 'free', None


OCC_OVER = 1.03            # a site's occupancies adding to more than this: over-occupied (a species standing in for a heavier one, or a slip)
OCC_PARTIAL = (0.02, 0.98) # a chemical occupancy in this range is partial


def check_occupancies(st):
    """The .res occupancies: a site whose species add to more than 1 (flag); partial occupancies fixed rather than
    refined (note — a bond-valence or composition argument resting on them is not independent); a split pair refined
    without a common free variable whose occupancies do not add to 1 (note). The chemical occupancy is the sof over
    the site's symmetry factor (its multiplicity over the general position's)."""
    m = res_model(st)
    if not m or not m['atoms']:
        return []
    general = max(1, len(st.ops))
    def site_of(lab):
        return st.site(lab) or next((x for x in st.sites if lab.upper() in [y.upper() for y in x.label.split('/')]), None)   # 'Fe1/Mg1': a merged site
    rows = []
    for a in m['atoms']:
        if (a['element'] or '').upper() in ('H', 'D'):
            continue
        v, kind, k = sof_value(a['sof'], m['fvar'])
        s = site_of(a['label'])
        if v is None or s is None or not s.mult:
            continue
        sym = s.mult / float(general)
        rows.append({'label': a['label'], 'el': a['element'] or s.element, 'xyz': a['xyz'], 'occ': v / sym if sym else v, 'kind': kind, 'k': k, 'part': a['part']})
    recs = []
    groups = {}                                                  # species sharing one position add up on one site
    for r in rows:
        groups.setdefault(tuple(round(x, 3) for x in r['xyz']), []).append(r)
    for key, rs in groups.items():
        tot = sum(r['occ'] for r in rs)
        if tot > OCC_OVER:
            recs.append({'kind': 'occupancy', 'severity': 'flag',
                         'text': 'site %s: occupancies %s add to %.3f vs 1 — over-occupied (one species standing in for a heavier one, or a slip)' % ('/'.join(r['label'] for r in rs), ' + '.join('%.3f' % r['occ'] for r in rs), tot)})
    fixed = [r for r in rows if r['kind'] == 'fixed' and OCC_PARTIAL[0] < r['occ'] < OCC_PARTIAL[1]]
    if fixed:
        recs.append({'kind': 'occupancy', 'severity': 'note',
                     'text': 'occupancies fixed, not refined: %s — a bond-valence sum or a site composition that rests on them is not independent of what was put in'
                             % ', '.join('%s %.3f' % (r['label'], r['occ']) for r in fixed[:12])})
    seen = set()                                                 # split pairs: two positions within 0.9 Å, both partial, not tied by one free variable
    for i, r in enumerate(rows):
        for r2 in rows[i + 1:]:
            if r['xyz'] == r2['xyz'] or (r['label'], r2['label']) in seen:
                continue
            if not (OCC_PARTIAL[0] < r['occ'] < OCC_PARTIAL[1] and OCC_PARTIAL[0] < r2['occ'] < OCC_PARTIAL[1]):
                continue
            try:
                d = st.dist(r['xyz'], r2['xyz'])
            except Exception:
                continue
            if d > 0.9:
                continue
            seen.add((r['label'], r2['label']))
            tied = r['k'] is not None and r['k'] == r2['k'] and {r['kind'], r2['kind']} == {'fv', '1-fv'}
            tot = r['occ'] + r2['occ']
            if tot > OCC_OVER:
                recs.append({'kind': 'occupancy', 'severity': 'flag',
                             'text': 'split pair %s/%s (%.2f Å apart): occupancies %.3f + %.3f add to %.3f vs 1 — two positions of one atom cannot both be there that often'
                                     % (r['label'], r2['label'], d, r['occ'], r2['occ'], tot)})
            elif not tied and abs(tot - 1.0) > 0.02:
                recs.append({'kind': 'occupancy', 'severity': 'note',
                             'text': 'split pair %s/%s (%.2f Å apart): occupancies %.3f and %.3f refined without a common free variable, adding to %.3f'
                                     % (r['label'], r2['label'], d, r['occ'], r2['occ'], tot)})
    return recs


_NO_TWIN = re.compile(r'no twinning|not twinned|twinning\s*:?\s*(?:was |is )?not (?:observed|detected|found|present)|twinning\s*:\s*none|absence of twinning|untwinned|no evidence (?:of|for) twinning', re.I)   # 'Twinning: not observed' in a data table too
_TWIN_WORD = re.compile(r'\btwin', re.I)
REFINE_RULES = {'R1_vs_Rint': 3.0, 'wR2_over_R1': 3.5, 'wght_a': 0.15, 'completeness': 0.95, 'observed_fraction': 0.5, 'data_per_parameter': 8.0, 'flack': (0.15, 0.85)}


def check_refinement(st, lines=None):
    """Refinement-quality triage from the .cif and its .res, as notes with the numbers: R1 against Rint, wR2/R1, the
    weighting scheme's a term, the completeness, the fraction of observed reflections, data per parameter, a Flack
    parameter between 0.15 and 0.85, and the twin refinement (BASF) against what the manuscript says. Two are flags:
    a manuscript that says the crystal was not twinned while the .res refines a twin fraction, and a transmission
    range wider than μ and the crystal can produce (Tmin/Tmax below exp(−2 μ dmax))."""
    items = st.block['items']
    num = lambda tag: _cif_num(st, tag)[0]
    recs = []
    def note(text, sev='note'):
        recs.append({'kind': 'refinement', 'severity': sev, 'text': text})
    r1, rint, wr2 = num('_refine_ls_r_factor_gt'), num('_diffrn_reflns_av_r_equivalents'), num('_refine_ls_wr_factor_ref')
    if r1 and rint and r1 > max(REFINE_RULES['R1_vs_Rint'] * rint, 0.06):
        note('R1 %.3f against Rint %.3f: the model fits the data %.0f× worse than the equivalents agree with each other' % (r1, rint, r1 / rint))
    if r1 and wr2 and wr2 / r1 > REFINE_RULES['wR2_over_R1']:
        note('wR2 %.3f is %.1f× R1 %.3f: a few strong reflections or the weighting scheme carry the misfit' % (wr2, wr2 / r1, r1))
    w = items.get('_refine_ls_weighting_details') or ''
    mw = re.search(r'\(\s*(\d*\.\d+)\s*P\s*\)\s*\^?2', w)
    m = res_model(st)
    if mw and float(mw.group(1)) > REFINE_RULES['wght_a']:
        note('weighting scheme a = %s: a term this large usually absorbs a systematic misfit (twinning, disorder, absorption)' % mw.group(1))
    elif m and m['wght'] and not mw and m['wght'][0] > REFINE_RULES['wght_a']:
        note('WGHT %g in the .res: a weighting term this large usually absorbs a systematic misfit' % m['wght'][0])
    comp = num('_diffrn_measured_fraction_theta_max')
    if comp is not None and comp < REFINE_RULES['completeness']:
        note('completeness %.3f to θmax' % comp)
    gt, tot, npar = num('_reflns_number_gt'), num('_reflns_number_total'), num('_refine_ls_number_parameters')
    if gt and tot and gt / tot < REFINE_RULES['observed_fraction']:
        note('%d of %d unique reflections observed (%.0f %%)' % (gt, tot, 100.0 * gt / tot))
    if tot and npar and tot / npar < REFINE_RULES['data_per_parameter']:
        note('%d reflections for %d parameters: %.1f data per parameter' % (tot, npar, tot / npar))
    fl, fl_esd = _cif_num(st, '_refine_ls_abs_structure_flack')
    if fl is not None and REFINE_RULES['flack'][0] <= fl <= REFINE_RULES['flack'][1] and (fl_esd is None or fl_esd < 0.15):
        note('Flack parameter %s: an inversion twin not modelled, or the wrong absolute structure' % items.get('_refine_ls_abs_structure_flack'))
    mu, dmax = num('_exptl_absorpt_coefficient_mu'), num('_exptl_crystal_size_max')
    tmin, tmax = num('_exptl_absorpt_correction_t_min'), num('_exptl_absorpt_correction_t_max')
    dmin = num('_exptl_crystal_size_min')
    if mu and dmax and tmin and tmax and tmax > 0:
        floor = math.exp(-2.0 * mu * dmax)
        ctype = (items.get('_exptl_absorpt_correction_type') or '').lower()
        if dmin and tmin / tmax > 0.95 and math.exp(-mu * (dmax - dmin)) < 0.85:
            note('Tmin/Tmax = %.3f for μ %.2f mm⁻¹ on a %.3f × %.3f mm crystal: the paths differ by exp(−μ·Δd) = %.2f, so a correction this flat does not follow the crystal\'s shape (%s)'
                 % (tmin / tmax, mu, dmax, dmin, math.exp(-mu * (dmax - dmin)), ctype or 'correction type unstated'))
        if tmin / tmax < floor * 0.999:
            # a numerical / analytical correction's Tmin and Tmax are transmissions and must fit the crystal; a multi-scan
            # or empirical correction's carry scaling too (SADABS' are not transmissions) — information there
            physical = bool(re.search(r'analyt|numer|integrat|gauss|sphere|cylind', ctype))
            note('Tmin/Tmax = %.3f vs exp(−2 μ dmax) = %.3f for μ %.2f mm⁻¹ and a %.3f mm crystal (%s correction): the range spans more absorption than the crystal can produce%s'
                 % (tmin / tmax, floor, mu, dmax, ctype or 'unstated', '' if physical else ' — or the crystal size is misstated'), 'flag' if physical else 'note')
        elif re.search(r'analyt|numer|integrat|gauss|sphere|cylind', ctype) and tmin < floor * 0.999:
            # a correction that computes transmissions: its Tmin is a transmission along a path the crystal has — no path is longer than
            # twice the longest dimension, so Tmin cannot lie below exp(−2 μ dmax)
            note('Tmin = %.3f vs exp(−2 μ dmax) = %.3f for μ %.2f mm⁻¹ and a %.3f mm crystal (%s correction): the minimum transmission is below what the longest path through the crystal allows (path %.3f mm)'
                 % (tmin, floor, mu, dmax, ctype, -math.log(tmin) / mu), 'flag')
    basf = (m or {}).get('basf') or []
    twinned = bool(basf) or bool((m or {}).get('twin')) or items.get('_twin_individual_mass_fraction_refined') not in (None, '', '?')
    if twinned and lines:
        text = ' '.join(t for _k, t in lines)
        mneg = _NO_TWIN.search(text)
        if mneg:
            s = max(0, mneg.start() - 60)
            sent = text[max(0, text.rfind('.', 0, mneg.start()) + 1): text.find('.', mneg.end()) if text.find('.', mneg.end()) > 0 else mneg.end() + 120]
            try:
                from pxrd_review import paper_extract as PE
                own = (PE.mineral_name(text) or '').lower()
            except Exception:
                own = ''
            others = [w for w in re.findall(r'\b([a-zà-ÿ]{5,}ite)\b', sent.lower()) if w not in ('calcite', 'dolomite', 'granite', 'pegmatite', 'satellite', 'composite') and (not own or w not in own)]
            # a denial in a sentence about another mineral (a comparison paper) is not this structure's: information there
            note('the .res refines a twin (BASF %s) but the manuscript says ‘…%s…’%s' % (', '.join('%.3f' % b for b in basf) or 'set', text[s:mneg.end() + 40].strip(),
                 (' — the sentence names %s, which may be what it is about' % others[0]) if others else ''), 'note' if others else 'flag')
        elif not _TWIN_WORD.search(text):
            note('the .res refines a twin (BASF %s) and the manuscript does not mention twinning' % (', '.join('%.3f' % b for b in basf) or 'set'))
    return recs


# ----------------------------------------------------------------------------- the formula the sites give

_ZNUM = {s: i + 1 for i, s in enumerate(
    'H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe '
    'Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm'.split())}
SITE_APFU_TOL = 0.05       # apfu and 5 %: an element the sites give beyond this of the formula sum, or of the manuscript's structural formula


def site_totals(st):
    """{element: atoms per cell} from the sites (multiplicity × occupancy × species fraction)."""
    have = {}
    for s_ in st.sites:
        for sp in s_.species:
            if sp.element:
                have[sp.element] = have.get(sp.element, 0.0) + s_.mult * sp.occ
    return have


def check_site_formula(st, lines=None):
    """The formula the refined sites give (occupancy × multiplicity, over Z) against the .cif's own formula sum and
    against the structural or empirical formula the manuscript prints. An element out by more than 5 % and 0.05 apfu is
    a flag on the .cif's side (the formula sum is what the program's F(000), μ and density came from) and a flag against
    the manuscript's formula; H is compared only when the refinement located it."""
    from pxrd_review import bv_check as B
    have = site_totals(st)
    z = B._z_from_formula(st)
    recs = []
    if not have or not z:
        return recs
    def rec(text, sev='flag'):
        recs.append({'kind': 'site formula', 'severity': sev, 'text': text})
    want = {}
    for el, num in re.findall(r'([A-Z][a-z]?)\s*(\d*\.?\d*)', st.formula or ''):
        if el in _ZNUM:
            want[el] = want.get(el, 0.0) + (float(num) if num else 1.0)
    have = dict(have); have['N'] = have.get('N', 0.0) + have.pop('NH', 0.0)     # an ammonium modelled as one scatterer
    per_fu = {el: v / z for el, v in have.items()}
    # cations only: a mixed anion site (F/OH) is typed one way in the .cif and split in the formula sum, and H, N follow it
    skip = {'O', 'H', 'F', 'Cl', 'Br', 'I', 'N', 'NH'}
    off, absent = [], []
    for el, w in want.items():
        if el in skip:
            continue
        h = per_fu.get(el, 0.0)
        if h == 0.0 and w > 0:
            absent.append('%s %g' % (el, w))                          # in the formula sum, on no site: not located (Li, Be, B, C of a carbonate the sites hold as O…)
        elif abs(h - w) > max(SITE_APFU_TOL, 0.05 * w):
            off.append('%s %.2f from the sites vs %g in the formula sum' % (el, h, w))
    for el, h in per_fu.items():
        if el not in want and el not in skip and h >= SITE_APFU_TOL:
            off.append('%s %.2f from the sites vs none in the formula sum' % (el, h))
    if off:
        rec('the sites give a formula the .cif\'s formula sum does not match (Z = %d): %s — F(000), μ and the density the program wrote follow the formula sum, not the sites' % (z, '; '.join(off[:6])))
    if absent:
        rec('in the formula sum but on no site: %s (per formula unit, Z = %d) — not located, or left out of the model' % (', '.join(absent[:6]), z), 'note')
    if lines:
        from pxrd_review import paper_extract as PE
        text = ' '.join(t for _k, t in lines)
        pick = next((f for f in PE._formulas(text) if f[4] == 'structural'), None)    # the refinement's own formula; an empirical one need not match the sites
        if pick and pick[1] and not re.search(r'\n|\d\(\d+\)|\b(?:IV|VI|VII|VIII|IX|XII)\b|(?<![A-Za-z(])[A-Z]\s?[\[(]', pick[0]):
            # a formula broken over lines, carrying esds, coordination numerals or site letters is not read whole: no comparison
            ftxt, counts = pick[0], pick[1]
            diffs = []
            for el, c in counts.items():
                if el in skip or el not in _ZNUM:
                    continue
                h = per_fu.get(el, 0.0)
                if abs(h - c) > max(SITE_APFU_TOL, 0.05 * c):
                    diffs.append('%s %.2f from the sites vs %g in the formula' % (el, h, c))
            if diffs and len(diffs) <= max(2, len(counts) // 3):
                rec('the manuscript\'s structural formula %s vs the sites (occupancy × multiplicity / Z = %d): %s' % (ftxt[:90], z, '; '.join(diffs)))
    return recs


def check_f000(st):
    """F(000) recomputed from the sites (Σ multiplicity × occupancy × atomic number over the cell) against the .cif's
    own: a difference beyond 2 % means the formula sum the program used is not what the sites hold (a note — the
    manuscript's printed F(000) is compared with the .cif's by check_numbers)."""
    f_cif = _cif_num(st, '_exptl_crystal_f_000')[0]
    have = site_totals(st)
    if not f_cif or not have:
        return []
    f_sites = sum(n * _ZNUM.get(el, 0) for el, n in have.items())
    if f_sites and abs(f_sites - f_cif) > 0.02 * f_cif:
        return [{'kind': 'F(000)', 'severity': 'note', 'text': 'F(000) %g in the .cif vs %.0f electrons from the sites (%+.1f %%): the formula sum the program used and the sites disagree%s'
                 % (f_cif, f_sites, 100.0 * (f_cif - f_sites) / f_sites, '' if 'H' in have else ' (H not located: a few electrons per formula unit are missing from the sites)')}]
    return []


MU_TOL = 0.10              # μ from the sites against the .cif's, as a fraction: the table is good to a few per cent
_MU_TABLE = None


def _mu_table():
    global _MU_TABLE
    if _MU_TABLE is None:
        import json
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'mu_moka.json'), encoding='utf-8') as f:
            _MU_TABLE = json.load(f)
    return _MU_TABLE


def mu_from_sites(st, lam=None):
    """μ (mm⁻¹) from the sites at Mo Kα — Σ over the cell of atoms × A × (μ/ρ) over N_A V — or None when the wavelength is
    not Mo Kα or an element has no coefficient. -> (mu, missing elements)."""
    from pxrd_review import epma as EP
    T = _mu_table()
    lam = lam if lam is not None else _cif_num(st, '_diffrn_radiation_wavelength')[0]
    if lam is None or abs(lam - T['wavelength']) > 0.002:
        return None, []
    have = site_totals(st)
    missing = [el for el in have if el not in T['mu_rho'] or el not in EP.ATOMIC_WEIGHTS]
    if missing or not have or not st.volume:
        return None, missing
    mu = 0.1 * sum(n * EP.ATOMIC_WEIGHTS[el] * T['mu_rho'][el] for el, n in have.items()) / (6.02214076e23 * st.volume * 1e-24)
    return mu, []


def check_mu(st):
    """μ recomputed from the sites at the .cif's wavelength against the .cif's own μ: beyond 10 % a note — the formula sum
    behind the program's μ is not what the sites hold, or μ was computed for another radiation (Mo Kα data only: the
    table is Mo Kα's)."""
    mu_cif = _cif_num(st, '_exptl_absorpt_coefficient_mu')[0]
    if not mu_cif:
        return []
    mu, missing = mu_from_sites(st)
    if mu is None:
        return []
    if abs(mu - mu_cif) > MU_TOL * mu_cif:
        return [{'kind': 'mu', 'severity': 'note', 'text': 'μ %.3f mm⁻¹ in the .cif vs %.3f from the sites at Mo Kα (%+.0f %%): the formula sum behind the program\'s μ and the sites disagree, or μ was computed for another radiation%s'
                 % (mu_cif, mu, 100.0 * (mu_cif - mu) / mu, '' if 'H' in site_totals(st) else ' (H not located: a fraction of a per cent at most)')}]
    return []


# ----------------------------------------------------------------------------- the twin law

def _mat3(rows):
    return [[float(x) for x in r] for r in rows]

def _mul(A, Bm):
    return [[sum(A[i][k] * Bm[k][j] for k in range(3)) for j in range(3)] for i in range(3)]

def _inv3(A):
    a, b, c = A[0]; d, e, f = A[1]; g, h, i = A[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-12:
        return None
    return [[(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
            [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
            [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]]

def _det3(A):
    a, b, c = A[0]; d, e, f = A[1]; g, h, i = A[2]
    return a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)

def _transpose(A):
    return [[A[j][i] for j in range(3)] for i in range(3)]

def _mv(A, v):
    return [sum(A[i][j] * v[j] for j in range(3)) for i in range(3)]

def _small_ints(v, tol=0.03):
    """A direction as small integers, or None when no multiple up to 12 makes it integral."""
    m = max(abs(x) for x in v) or 1.0
    u = [x / m for x in v]
    for n in range(1, 13):
        w = [x * n for x in u]
        if all(abs(x - round(x)) <= tol for x in w) and any(abs(round(x)) > 0 for x in w):
            ints = [int(round(x)) for x in w]
            g = 0
            for x in ints:
                g = math.gcd(g, abs(x))
            ints = [x // (g or 1) for x in ints]
            if sum(1 for x in ints if x < 0) > sum(1 for x in ints if x > 0):
                ints = [-x for x in ints]
            return ints
    return None

def _fmt_dir(ints, brackets):
    if ints is None:
        return None
    s = ''.join(('%d' % abs(x)) if x >= 0 else ('−%d' % abs(x)) for x in ints) if all(abs(x) < 10 for x in ints) else ' '.join(str(x) for x in ints)
    return brackets[0] + s + brackets[1]


def twin_law(st, M):
    """What a TWIN matrix (acting on hkl) is, in the cell's own geometry: {'det', 'kind' ('identity' | 'inversion' |
    'twofold' | 'threefold' | 'fourfold' | 'sixfold' | 'mirror' | 'rotoinversion' | 'other'), 'axis_direct' [uvw],
    'axis_recip' (hkl)*, 'exact' ('direct' | 'reciprocal' | None), 'symop' (a symmetry operation of the space group,
    ±), 'index' (twin index by the coincidence fraction), 'rational'}."""
    Bd = B.cart_matrix(st)                                        # fractional direct -> Cartesian (columns a, b, c)
    Bi = _inv3(Bd)
    Bs = _transpose(Bi)                                           # reciprocal basis in Cartesian (columns a*, b*, c*)
    Bsi = _inv3(Bs)
    Mc = _mul(_mul(Bs, M), Bsi)                                   # the law as a Cartesian point operation
    det = _det3(Mc); tr = Mc[0][0] + Mc[1][1] + Mc[2][2]
    out = {'det': round(det, 3), 'M': M}
    I = [[1.0 if i == j else 0.0 for j in range(3)] for i in range(3)]
    def close(A, Bm, tol=0.02):
        return all(abs(A[i][j] - Bm[i][j]) <= tol for i in range(3) for j in range(3))
    if close(Mc, I):
        out['kind'] = 'identity'
    elif close(Mc, [[-x for x in r] for r in I]):
        out['kind'] = 'inversion'
    elif abs(det - 1) < 0.05:
        out['kind'] = {-1: 'twofold', 0: 'threefold', 1: 'fourfold', 2: 'sixfold'}.get(int(round(tr)), 'other')
    elif abs(det + 1) < 0.05:
        out['kind'] = {1: 'mirror', 0: 'rotoinversion', -1: 'rotoinversion', -2: 'rotoinversion'}.get(int(round(tr)), 'other')
    else:
        out['kind'] = 'other'
    # the axis (eigenvalue +1 of a rotation; the normal, eigenvalue −1, of a mirror): a null vector of Mc − λI
    lam = -1.0 if out['kind'] in ('mirror', 'rotoinversion') else 1.0
    A = [[Mc[i][j] - (lam if i == j else 0.0) for j in range(3)] for i in range(3)]
    best = None
    for i in range(3):
        for j in range(i + 1, 3):
            r1, r2 = A[i], A[j]
            v = [r1[1] * r2[2] - r1[2] * r2[1], r1[2] * r2[0] - r1[0] * r2[2], r1[0] * r2[1] - r1[1] * r2[0]]
            n = math.sqrt(sum(x * x for x in v))
            if best is None or n > best[0]:
                best = (n, v)
    axis = [x / best[0] for x in best[1]] if best and best[0] > 1e-6 else None
    out['axis_direct'] = out['axis_recip'] = None; out['exact'] = None
    if axis and out['kind'] not in ('identity', 'inversion', 'other'):
        d = _small_ints(_mv(Bi, axis)); r = _small_ints(_mv(_transpose(Bd), axis))
        out['axis_direct'] = d; out['axis_recip'] = r
        out['exact'] = 'direct' if d and _small_ints(_mv(Bi, axis), 0.005) else ('reciprocal' if r and _small_ints(_mv(_transpose(Bd), axis), 0.005) else None)
    # a symmetry operation of the space group, or one composed with the inversion
    out['symop'] = None
    for rot, _tr in st.ops:
        Rc = _mul(_mul(Bd, _mat3(rot)), Bi)
        if close(Mc, Rc):
            out['symop'] = '+'; break
        if close(Mc, [[-x for x in r] for r in Rc]):
            out['symop'] = '-'
    out['centro'] = any(close(_mul(_mul(Bd, _mat3(rot)), Bi), [[-x for x in r] for r in I]) for rot, _tr in st.ops)
    # the twin index: entries within 0.02 of k/2, k/3, k/4 or k/6 are that fraction (a refined or cell-derived matrix carries
    # residues); a matrix rational after that is a lattice law whose index is the order of the coincidence sublattice
    # {v : M v integral}, counted exactly modulo the common denominator; one that is not is an approximate law with no index
    from fractions import Fraction
    snapped = []; rational = True
    for r in M:
        row = []
        for x in r:
            f = None
            for q in (1, 2, 3, 4, 6):
                if abs(x * q - round(x * q)) <= 0.02 * q:
                    f = Fraction(int(round(x * q)), q); break
            if f is None:
                rational = False; row.append(x)
            else:
                row.append(f)
        snapped.append(row)
    out['rational'] = rational; out['index'] = None
    if rational:
        q = 1
        for r in snapped:
            for f in r:
                q = q * f.denominator // math.gcd(q, f.denominator)
        Mi = [[int(f * q) for f in r] for r in snapped]
        count = sum(1 for h in range(q) for k in range(q) for l in range(q)
                    if all((Mi[i][0] * h + Mi[i][1] * k + Mi[i][2] * l) % q == 0 for i in range(3)))
        out['index'] = int(round(q ** 3 / count)) if count else None
    return out


_TWIN_KIND = [('inversion', re.compile(r'\binversion\b|racemic', re.I)),                # within the twin sentences: 'inversion twin', 'related by inversion', 'or inversion'
              ('twofold', re.compile(r'two-?fold|2-fold|180\s*°|rotation twin|twin axis', re.I)),
              ('mirror', re.compile(r'reflection twin|twin plane|mirror', re.I)),
              ('threefold', re.compile(r'three-?fold|3-fold|120\s*°', re.I)), ('fourfold', re.compile(r'four-?fold|4-fold', re.I)), ('sixfold', re.compile(r'six-?fold|6-fold', re.I))]
# the axis or plane the text gives its twin: after the twin word, '[001]' or '(104)', not a viewing direction before it
_TWIN_AXIS = re.compile(r'twin\w*[^.\[(]{0,80}?(?:about|along|around|axis|on|parallel to|by)\s*([\[(])\s*([-−¯‾]?\s?\d)\s*,?\s*([-−¯‾]?\s?\d)\s*,?\s*([-−¯‾]?\s?\d)\s*[\])]', re.I)
# a twin matrix the text prints: 'twin matrix [1 0 0 / 0 1 0 / 0 0 1]', 'twin law ¯101,0¯10,00¯1', '{1 0 0 / 0 1 0 / 0 0 1}'
_PRINTED_TWIN = re.compile(r'twin(?:ning)?\s+(?:matrix|law|operation)[^.\d¯‾−\[({-]{0,40}?[\[({]?\s*((?:[-−¯‾]?\s?\d[\s,/;|]*){9})', re.I)


def printed_twin_matrix(twin_text):
    """The 3×3 matrix a manuscript prints for its twin law, or None: nine signed digits in any separators, an overbar as a minus."""
    m = _PRINTED_TWIN.search(twin_text)
    if not m:
        return None
    body = re.sub(r'[¯‾−]\s?(\d)', r'-\1', m.group(1)); body = re.sub(r'(\d)\u0304', r'-\1', body)
    nums = re.findall(r'-?\d', body)
    if len(nums) != 9:
        return None
    v = [int(x) for x in nums]
    return [v[0:3], v[3:6], v[6:9]]


_R_DROP = re.compile(r'R\s*1?\s*(?:value|factor|index)?\s*(?:dropped|decreased|fell|improved|reduced|lowered|went)\b[^.]{0,80}?twin|twin[^.]{0,120}?R\s*1?\s*(?:value|factor|index)?\s*(?:dropped|decreased|fell|improved|reduced|lowered)', re.I)


def check_twin(st, lines=None):
    """The twin law in the .res (TWIN + BASF) or the .cif's twin loop, judged in the cell's geometry and against the
    manuscript's words. Flags: a law that is the identity or a symmetry operation of the space group (no twin), a law
    that is a symmetry operation composed with the inversion in a centrosymmetric structure (it changes no intensity —
    a BASF against it is meaningless, and an R drop credited to it has another cause), the manuscript's 'inversion
    twin' beside a rotation matrix or its 'twofold' beside the inversion. Notes: the axis the matrix has (direct and
    reciprocal — a twofold about c* is not one about c) against the axis the text names, the twin index of a reticular
    law, a non-rational (approximate) law, a Friedel-only law in a non-centrosymmetric structure, a twin fraction that
    refined to nothing."""
    m = res_model(st)
    recs = []
    def rec(text, sev):
        recs.append({'kind': 'twin', 'severity': sev, 'text': text})
    laws = []
    if m and m['twin']:
        laws.append(('the .res TWIN', m['twin'][0]))
    items = st.block['items']
    for tags, rows in st.block.get('loops') or []:
        tags = [t.lower() for t in tags]
        if '_twin_individual_twin_matrix_11' in tags:
            for row in rows:
                try:
                    Mx = [[float(row[tags.index('_twin_individual_twin_matrix_%d%d' % (i, j))]) for j in (1, 2, 3)] for i in (1, 2, 3)]
                except Exception:
                    continue
                same = lambda A, Bm: all(abs(A[i][j] - Bm[i][j]) <= 0.01 for i in range(3) for j in range(3))
                if not same(Mx, [[1, 0, 0], [0, 1, 0], [0, 0, 1]]) and not any(same(Mx, L) for _w, L in laws):
                    laws.append(("the .cif's twin loop", Mx))
            break
    if not laws:
        return recs
    text = ' '.join(t for _k, t in (lines or []))
    twin_text = ' '.join(mm.group(0) for mm in re.finditer(r'[^.]{0,200}\btwin[^.]{0,200}', text, re.I))   # the sentences about the twin, not the whole paper
    basf = (m or {}).get('basf') or []
    for where, M in laws:
        try:
            tl = twin_law(st, M)
        except Exception:
            continue
        mtxt = '(' + '; '.join(' '.join(('%g' % x) for x in r) for r in M) + ')'
        axis_txt = ''
        if tl.get('axis_direct') or tl.get('axis_recip'):
            d = _fmt_dir(tl['axis_direct'], '[]'); r = _fmt_dir(tl['axis_recip'], '()')
            axis_txt = ' about %s' % (' = '.join(x for x in ((d if tl['exact'] != 'reciprocal' or not r else None), (r + '*' if r else None)) if x)) if tl['kind'] != 'mirror' \
                else ' on %s' % (r if r else d)
        head = '%s %s is %s%s' % (where, mtxt, {'identity': 'the identity', 'inversion': 'the inversion', 'twofold': 'a twofold', 'threefold': 'a threefold', 'fourfold': 'a fourfold',
                                                'sixfold': 'a sixfold', 'mirror': 'a mirror', 'rotoinversion': 'a rotoinversion', 'other': 'not a point operation in this cell'}[tl['kind']], axis_txt)
        if tl['kind'] == 'identity':
            rec('%s: not a twin law — the second component would be the first' % head, 'flag'); continue
        if tl['symop'] == '+':
            rec('%s, a symmetry operation of the space group: not a twin law' % head, 'flag'); continue
        if tl['symop'] == '-' and tl['centro']:
            rec('%s — a symmetry operation composed with the inversion, in a centrosymmetric structure: it changes no intensity, so a twin fraction refined against it means nothing%s'
                % (head, ', and the R drop the text credits to twinning has another cause' if _R_DROP.search(twin_text) else ''), 'flag'); continue
        if tl['symop'] == '-':
            if _R_DROP.search(twin_text):                          # an inversion twin in a non-centrosymmetric structure is the normal use of TWIN −1: nothing to say, unless R1 is credited to it
                rec('%s — the inversion composed with a symmetry operation: it relates Friedel mates only and touches R1 only through anomalous scattering; the R drop the text credits to it needs another cause' % head, 'flag')
        else:
            rec('%s%s' % (head, ', twin index %d (reticular merohedry)' % tl['index'] if tl.get('index') and tl['index'] > 1 else ''), 'note')
            if not tl['rational']:
                rec('%s has non-rational entries: an approximate law (pseudo-merohedry with an obliquity the matrix does not state)' % where, 'note')
        if twin_text:
            stated = [k for k, pat in _TWIN_KIND if pat.search(twin_text)]
            kinds_all = set()
            for _w2, M2 in laws:
                try:
                    t2 = twin_law(st, M2); kinds_all.add('inversion' if t2['kind'] == 'inversion' or t2['symop'] == '-' else t2['kind'])
                except Exception:
                    pass
            if 'inversion' in stated and 'inversion' not in kinds_all and tl['kind'] in ('twofold', 'threefold', 'fourfold', 'sixfold', 'mirror'):
                rec('the manuscript calls it an inversion twin, but %s' % head, 'flag')
            if kinds_all == {'inversion'} and tl['kind'] == 'inversion' and any(k in stated for k in ('twofold', 'threefold', 'fourfold', 'sixfold', 'mirror')) and 'inversion' not in stated:
                rec('the manuscript describes a rotation or reflection twin, but %s' % head, 'flag')
            ma = _TWIN_AXIS.search(twin_text)
            if ma and (tl.get('axis_direct') or tl.get('axis_recip')) and tl['kind'] != 'mirror':
                named = _small_ints([int(re.sub(r'[-−¯‾]\s?', '-', g).replace(' ', '')) for g in ma.groups()[1:]])
                recip_named = ma.group(1) == '('
                same = lambda ax: bool(ax) and named in (ax, [-x for x in ax])
                shown = ('(%s)' if recip_named else '[%s]') % ''.join(str(x) for x in named)
                if named and not same(tl.get('axis_recip') if recip_named else tl.get('axis_direct')):
                    other = same(tl.get('axis_direct') if recip_named else tl.get('axis_recip'))
                    rec('the text puts the twin axis along %s; the matrix is %s%s' % (shown, head.split(' is ', 1)[1],
                        (' — %s is the %s axis, which coincides with the %s one only at 90°' % (shown, 'direct' if recip_named else 'reciprocal', 'reciprocal' if recip_named else 'direct')) if other else ''), 'note')
    if twin_text:
        P = printed_twin_matrix(twin_text)
        if P is not None:
            if P == [[1, 0, 0], [0, 1, 0], [0, 0, 1]]:
                rec('the twin matrix the text prints, (1 0 0; 0 1 0; 0 0 1), is the identity — the law that was refined is (%s)' % '; '.join(' '.join('%g' % x for x in r) for r in laws[0][1]) if laws else
                    'the twin matrix the text prints, (1 0 0; 0 1 0; 0 0 1), is the identity: no twin law', 'flag')
            elif laws:
                try:
                    tp, tr_ = twin_law(st, [[float(x) for x in r] for r in P]), twin_law(st, laws[0][1])
                    if (tp['kind'], tp.get('axis_direct'), tp.get('axis_recip')) != (tr_['kind'], tr_.get('axis_direct'), tr_.get('axis_recip')) and not (tp['kind'] == 'inversion' and tr_['symop'] == '-'):
                        what = 'not a point operation in this cell (another convention, or a misprint)' if tp['kind'] == 'other' else tp['kind']
                        rec('the twin matrix the text prints, (%s), is %s; %s is %s' % ('; '.join(' '.join(str(x) for x in r) for r in P), what, laws[0][0], tr_['kind']), 'note')
                except Exception:
                    pass
    for b in basf:
        if b < 0.02:
            rec('the twin fraction refined to %.3f: the second component is absent, and the twin law can be dropped' % b, 'note')
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
_IDEAL = re.compile(r'(?:ideal(?:ized)?|end-?member|simplified)\s+formula\s*(?:is|of\s+\w+\s+is|[:=])\s*(\S{4,80}(?:·\s*\d*\s*H2O)?)', re.I)   # a comma may sit inside the brackets: 'Ba3(Mg,Fe)…'


def ideal_formula(lines):
    """The ideal formula the manuscript states ('Ideal formula: …', 'The ideal formula is …'): (text, counts) or None."""
    from pxrd_review import paper_extract as PE, epma as EP
    for kind, raw in lines:
        m = _IDEAL.search(raw)
        if not m:
            continue
        f = m.group(1).rstrip(',.;:')
        if f.count('(') != f.count(')') or f.count('[') != f.count(']') or f.endswith(('(', '[')):
            continue                                                 # cut short: not the formula
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
    recs = check_riding(st) + check_occupancies(st)
    lines = None
    if manuscript and manuscript.lower().endswith('.pdf'):
        from pxrd_review import cell_lambda_check as C
        lines = [('p', p) for p in re.split(r'\n\s*\n', C.pdf_text(manuscript) or '') if p.strip()]
        recs += check_numbers(st, lines) + check_density(st, lines)     # a .pdf has no table rows to read cell by cell: its numbers are prose (notes unless anchored), its labels are not judged
    elif manuscript:
        lines = docx_lines(manuscript)
        recs += check_numbers(st, lines) + check_density(st, lines) + check_labels(st, lines)
    recs += check_refinement(st, lines) + check_twin(st, lines) + check_site_formula(st, lines) + check_f000(st) + check_mu(st)
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
