#!/usr/bin/env python3
"""
Candidate-group scan (prototype) — flag where a reviewed phase has an OBVIOUS
structural relative that no group link records, so the reviewer can consider a
group the PDF authors may have missed.

Deliberately conservative (the reviewer warned this can be dangerously
misleading). A candidate is reported only when ALL of these hold against an
existing IMA mineral:
  * same space group  (Mindat's integer SG code — consistent per space group);
  * cell relation     — either similar cell (each axis within ~4 %) OR a rational
                        sub-/super-cell (axis ratios near 1,2,3,½,⅓,… — a real
                        sub-cell relation, not a chance match);
  * one sensible substitution — identical element set, or a single swap between
                        chemically analogous elements (Mg↔Fe, Al↔Sc, REE↔REE …).

…and only for phases where a relation is NOT already identified:
  * the phase is UNGROUPED in Mindat (no groupid), and
  * its docx entry carries no Structure/Isomorphism/Polymorphism group comment.

If a matched relative is itself in a group, the phase is a candidate MEMBER of
that existing group (authors likely missed it). If the relative is also
ungrouped, the pair are candidates to FORM a new group (needs ≥3 members to be
real — reported as a lead, not a conclusion).

Never writes into the docx. Console report only.

Usage:
    python3 tools/candidate_groups.py <folder> [--id Innnnnn] [--tol 0.04]
"""
import os, re, glob, argparse

# --- repo layout: make the sibling code dirs importable by bare name -----------
import os as _o, sys as _s
_d = _o.path.dirname(_o.path.abspath(__file__))
_r = _o.path.dirname(_d) if _o.path.basename(_d) in ('tools', 'gui', 'mindat') else _d
for _x in ('tools', 'mindat', 'gui'):
    _p = _o.path.join(_r, _x)
    if _o.path.isdir(_p) and _p not in _s.path:
        _s.path.insert(0, _p)
# -------------------------------------------------------------------------------
import mindat
import extra_checks as X
import cell_lambda_check as C

# Chemically analogous cations grouped by typical valence, each with an
# approximate Shannon EFFECTIVE IONIC RADIUS (Å, octahedral VI, the usual
# valence). A swap WITHIN a group reads as a simple substitution; across groups
# it does not (Si↔Fe is not "obvious"). The radii let us check the reviewer's
# key point — that the cell-metric change should be commensurate (and in the
# right direction) with the cation-size change of the substitution.
SIM_GROUPS = [
    {'Mg':0.72,'Fe':0.78,'Mn':0.83,'Ca':1.00,'Zn':0.74,'Co':0.745,'Ni':0.69,
     'Cu':0.73,'Cd':0.95,'Sr':1.18,'Ba':1.35,'Pb':1.19,'Hg':1.02,'Sn':0.93},   # ~divalent
    {'Al':0.535,'Fe':0.645,'Cr':0.615,'Sc':0.745,'Ga':0.62,'In':0.80,'V':0.64,
     'Ti':0.67,'Mn':0.645,'Co':0.61},                                          # ~trivalent
    {'La':1.032,'Ce':1.01,'Pr':0.99,'Nd':0.983,'Pm':0.97,'Sm':0.958,'Eu':0.947,
     'Gd':0.938,'Tb':0.923,'Dy':0.912,'Ho':0.901,'Er':0.89,'Tm':0.88,'Yb':0.868,
     'Lu':0.861,'Y':0.90,'Sc':0.745},                                          # REE 3+
    {'Si':0.40,'Ge':0.53,'Ti':0.605,'Sn':0.69,'Zr':0.72,'Hf':0.71},            # tetrahedral / 4+
    {'P':0.38,'As':0.46,'V':0.54,'Nb':0.64,'Sb':0.60,'Ta':0.64},               # 5+
    {'S':0.12,'Se':0.42,'Te':0.56,'Cr':0.26,'Mo':0.59,'W':0.60},               # 6+ / chalcogen
    {'F':1.33,'Cl':1.81,'Br':1.96,'I':2.20},                                   # halogens
    {'Na':1.02,'K':1.38,'Rb':1.52,'Cs':1.67,'Li':0.76,'Tl':1.50,'Ag':1.15},    # alkali
]
def _sensible(x, y):
    return any(x in g and y in g for g in SIM_GROUPS)

def radius_pair(x, y):
    """(r_x, r_y) from the first analogous group holding both, else None."""
    for g in SIM_GROUPS:
        if x in g and y in g:
            return g[x], g[y]
    return None

SIMPLE_RATIONALS = [1, 2, 3, 4, 1/2, 1/3, 1/4, 2/3, 3/2, 3/4, 4/3]

# ----------------------------------------------------------------------------- relations
def _fillb(r):
    """Mindat stores b=0 for uniaxial cells (b=a); return (a,b,c) usable floats."""
    a, b, c = r['a'], r['b'] or r['a'], r['c']
    return a, b, c

def cell_relation(P, Cc, tol):
    a1, b1, c1 = _fillb(P); a2, b2, c2 = _fillb(Cc)
    if min(a1, c1, a2, c2) <= 0:
        return None
    ra, rb, rc = a2/a1, b2/b1, c2/c1
    if all(abs(r - 1) <= tol for r in (ra, rb, rc)):
        dev = max(abs(r - 1) for r in (ra, rb, rc))
        return ('similar', 'Δ%.1f%%' % (dev*100))
    # rational sub/super-cell: every axis ratio near a simple rational, not all 1
    picks = []
    for r in (ra, rb, rc):
        best = min(SIMPLE_RATIONALS, key=lambda q: abs(r - q))
        if abs(r - best) / best > 0.03:
            return None
        picks.append(best)
    if all(abs(p - 1) < 1e-6 for p in picks):
        return None                       # that's just 'similar', handled above
    def _fmt(p):
        return {0.5: '½', 1/3: '⅓', 0.25: '¼', 2/3: '⅔',
                1.5: '3/2', 0.75: '3/4', 4/3: '4/3'}.get(round(p, 4), str(int(p)) if p == int(p) else '%.2f' % p)
    return ('sub/super-cell', 'a:b:c × %s,%s,%s' % tuple(_fmt(p) for p in picks))

def substitution(P, Cc):
    sp, sc = set(P['elements']), set(Cc['elements'])
    if not sp or not sc:
        return None
    if sp == sc:
        return 'same elements'
    dp, dc = sp - sc, sc - sp
    if len(dp) == 1 and len(dc) == 1:
        x, y = next(iter(dp)), next(iter(dc))
        return '%s↔%s' % (x, y) if _sensible(x, y) else None
    return None

# ----------------------------------------------------------------------------- scan
def _struct_index():
    recs = mindat.struct_db().get('recs', [])
    idx = {}
    for r in recs:
        idx.setdefault(r['norm'], r)
    return recs, idx

def _find(name, idx):
    for cand in mindat._candidates(name):
        if cand in idx:
            return idx[cand]
    return None

def scan_phase(P, recs, tol):
    """Return ranked candidate relatives for phase record P."""
    out = []
    for Cc in recs:
        if Cc is P or Cc['name'] == P['name']:
            continue
        if not (P['sg'] and Cc['sg'] and Cc['sg'] == P['sg']):
            continue                       # same space group required
        sub = substitution(P, Cc)
        if not sub:
            continue
        rel = cell_relation(P, Cc, tol)
        if not rel:
            continue
        # rank: existing group first (join an established group), then closeness
        out.append((Cc, rel, sub))
    def _key(item):
        Cc, rel, _ = item
        grouped = 0 if Cc['groupid'] else 1
        dev = float(re.search(r'[\d.]+', rel[1]).group()) if rel[0] == 'similar' else 50
        return (grouped, dev)
    return sorted(out, key=_key)

def already_identified(entry, P):
    """True if a group relation is already on record for this phase."""
    if P and P['groupid']:
        return True
    for code in ('Structure', 'Isomorphism', 'Polymorphism'):
        v = entry.comments.get(code, '')
        if re.search(r'\bgroup\b|isostructural|isotypic|homeotypic|supergroup|subgroup', v, re.I):
            return True
    return False

def group_name(gid):
    return mindat._db().get('groups', {}).get(str(gid), {}).get('name', 'group %s' % gid)

def group_sgcodes(gid, recs):
    """Set of (nonzero) Mindat SG codes among a group's members. A group that
    spans several is chemically (not strictly isostructurally) defined, so a
    same-SG match is really to the matched member, not the whole group."""
    return {r['sg'] for r in recs if r['groupid'] == gid and r['sg']}

def _vol(r):
    return r['a'] * (r['b'] or r['a']) * r['c']

def size_consistency(P, Cc, sub):
    """Compare the swapped cations' radii against the observed cell change. P
    carries the first element of the swap (`x↔y` is built x=P-only, y=C-only).
    Returns an evidence string (radii, Δr, direction) or '' if not a single swap
    / radii unknown. The reviewer judges — this surfaces the signal, never gates."""
    if '↔' not in sub:
        return ''                                   # 'same elements' — no swap
    x, y = sub.split('↔')
    rp = radius_pair(x, y)
    if not rp:
        return ''
    rx, ry = rp; dr = abs(rx - ry)
    s = '%s %.2f↔%s %.2f Å (Δr %.2f)' % (x, rx, y, ry, dr)
    s += '; near-isodimensional' if dr < 0.10 else '; sizable swap'
    vP, vC = _vol(P), _vol(Cc)
    if dr >= 0.03 and abs(vP - vC) > 1e-6:          # direction is meaningful
        s += ', cell tracks cation size ✓' if (rx > ry) == (vP > vC) \
             else ', ⚠ cell change OPPOSES cation size — verify it is this substitution'
    elif dr < 0.03 and rel_pct(P, Cc) is not None and rel_pct(P, Cc) > 3:
        s += ', ⚠ cell moves more than the tiny Δr implies'
    return s

def rel_pct(P, Cc):
    a1, b1, c1 = (P['a'], P['b'] or P['a'], P['c'])
    a2, b2, c2 = (Cc['a'], Cc['b'] or Cc['a'], Cc['c'])
    if min(a1, c1, a2, c2) <= 0:
        return None
    return max(abs(a2/a1 - 1), abs(b2/b1 - 1), abs(c2/c1 - 1)) * 100

def name_echo(a, b):
    """The reviewer's heuristic: a name usually signals its relations. True if one
    species name contains the other's root (zincochenite ⊃ chenite, chinleite-(Ce)
    ~ chinleite-(Nd)). Independent corroboration of a structural match."""
    ra = re.sub(r'-?\(.*?\)|-[0-9].*$', '', a.lower()).strip('- ')
    rb = re.sub(r'-?\(.*?\)|-[0-9].*$', '', b.lower()).strip('- ')
    if len(ra) < 4 or len(rb) < 4:
        return False
    short, long = sorted((ra, rb), key=len)
    return short[-5:] in long or long.endswith(short)

# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('folder')
    ap.add_argument('--id', help='only this entry id')
    ap.add_argument('--tol', type=float, default=0.04, help='axis similarity tolerance (default 0.04 = 4%%)')
    ap.add_argument('--max', type=int, default=4, help='max candidates listed per phase')
    args = ap.parse_args()

    mindat.refresh_struct_if_stale()
    if not mindat.struct_available():
        print('No structural cache. Run:  python3 mindat/mindat.py --refresh-struct'); return
    recs, idx = _struct_index()

    docs = sorted(f for f in glob.glob(os.path.join(args.folder, '*.docx'))
                  if not os.path.basename(f).startswith('~$'))
    n_scanned = n_hits = 0
    for dp in docs:
        if args.id and args.id not in os.path.basename(dp):
            continue
        e = X.parse_entry(dp)
        name = e.name or e.primary or ''
        P = _find(name, idx)
        if P is None:
            print('%-30s  not in Mindat structural cache — skipped (new mineral?)' % os.path.basename(dp)[:30])
            continue
        if already_identified(e, P):
            continue                       # relation already known — not our job
        n_scanned += 1
        cands = scan_phase(P, recs, args.tol)
        if not cands:
            continue
        n_hits += 1
        sgsym = e.space_group or '?'
        print('=' * 78)
        print('%s   [%s, space group %s, a=%.3f b=%.3f c=%.3f]' %
              (os.path.basename(dp), P['name'], sgsym, P['a'], P['b'] or P['a'], P['c']))
        for Cc, rel, sub in cands[:args.max]:
            echo = ' ★name echoes' if name_echo(P['name'], Cc['name']) else ''
            print('   matches %s%s — same SG, %s, %s' % (Cc['name'], echo, rel[0], sub))
            print('       %s; cell a=%.3f b=%.3f c=%.3f' % (rel[1], Cc['a'], Cc['b'] or Cc['a'], Cc['c']))
            size = size_consistency(P, Cc, sub)
            if size:
                print('       cation size: %s' % size)
            if Cc['groupid']:
                codes = group_sgcodes(Cc['groupid'], recs)
                het = (' — but that group spans %d space groups, so the strict '
                       'match is to %s itself' % (len(codes), Cc['name'])) if len(codes) > 1 else ''
                print('       → %s is in the %s%s; consider that group.'
                      % (Cc['name'], group_name(Cc['groupid']), het))
            else:
                print('       → %s is also ungrouped — together a lead to FORM a group (needs a 3rd member).'
                      % Cc['name'])
    print('=' * 78)
    print('scanned %d ungrouped/unidentified phases; %d had obvious candidate relatives.'
          % (n_scanned, n_hits))

if __name__ == '__main__':
    main()
