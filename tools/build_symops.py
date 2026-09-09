"""Build the space-group operator table from the corpus's own .cif files.

A .cif that lists `_space_group_symop_operation_xyz` states, for its Hermann-Mauguin symbol, the
operators that symbol means in the setting the authors used. Harvesting those pairs over the corpus
gives a symbol -> operators table for exactly the space groups minerals occupy, taken from refined,
published structures rather than typed in by hand. The operators themselves are mathematics (the
International Tables), not the authors' data.

Nothing is trusted on its word. Every harvested set must be a GROUP: closed under composition
(modulo a lattice translation), containing the identity, and containing an inverse for each of its
members. A set that fails is dropped, not shipped. Where two .cif files give different operators for
the same symbol -- a different origin choice or cell setting -- both are kept as variants, and the
consumer picks the one that reproduces the structure.

    python3 tools/build_symops.py "<corpus root>" [--out pxrd_review/data/symops.json.gz] [--report]

The table is what `bv_check` falls back on when a .cif carries no operator loop (today it refuses
anything but P1/P-1) and what lets a paper's printed coordinates become a structure at all.
"""
import os, re, sys, glob, gzip, json, argparse, collections

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pxrd_review import bv_check as B, symops as SO

FRAC = 12                                   # translations are twelfths: 1/2, 1/3, 1/4, 1/6 all land exactly


def norm_symbol(s):
    """The same normalisation the lookup uses — build and lookup must not drift apart, or a symbol
    is stored under a key nothing will ever ask for ('R -3 2/m (hexagonal axes)')."""
    return SO.normalize(s)


def canon(op):
    """(rot, tr) -> a hashable canonical form, translations reduced into [0, 1)."""
    rot, tr = op
    r = tuple(tuple(int(round(v)) for v in row) for row in rot)
    t = tuple(int(round(v * FRAC)) % FRAC for v in tr)
    return (r, t)


def compose(a, b):
    """a then b, as matrices: (Rb·Ra, Rb·ta + tb)."""
    (ra, ta), (rb, tb) = a, b
    rot = tuple(tuple(sum(rb[i][k] * ra[k][j] for k in range(3)) for j in range(3)) for i in range(3))
    tr = tuple((sum(rb[i][k] * ta[k] for k in range(3)) + tb[i] * 1) % (FRAC) for i in range(3))
    return (rot, tuple(int(round(v)) % FRAC for v in tr))


IDENTITY = (((1, 0, 0), (0, 1, 0), (0, 0, 1)), (0, 0, 0))


def is_group(ops):
    """Closed under composition, with the identity and an inverse for every member. The one check
    that needs no outside reference: a set of operators that is not a group is not a space group."""
    S = set(ops)
    if IDENTITY not in S:
        return False, 'no identity'
    for a in ops:
        for b in ops:
            if compose(a, b) not in S:
                return False, 'not closed'
    for a in ops:
        if not any(compose(a, b) == IDENTITY for b in ops):
            return False, 'no inverse'
    return True, 'group of order %d' % len(ops)


def harvest(roots):
    """{symbol: {frozenset(ops): [files]}} from every .cif that states both a symbol and its operators."""
    found = collections.defaultdict(lambda: collections.defaultdict(list))
    stats = collections.Counter()
    seen = set()
    for root in roots:
        for path in sorted(glob.glob(os.path.join(root, '**', '*.cif'), recursive=True)):
            if 'review_out' in path or os.path.basename(path) in seen:
                continue
            seen.add(os.path.basename(path))
            stats['cif'] += 1
            try:
                blocks = B.read_cif(path)
            except Exception:
                stats['unreadable'] += 1
                continue
            for b in blocks:
                it = b['items']
                sym = norm_symbol(it.get('_space_group_name_h-m_alt') or it.get('_symmetry_space_group_name_h-m')
                                  or it.get('_space_group_name_h-m') or '')
                tags, rows = B._loop(b, '_space_group_symop_operation_xyz')
                tag = '_space_group_symop_operation_xyz'
                if rows is None:
                    tags, rows = B._loop(b, '_symmetry_equiv_pos_as_xyz')
                    tag = '_symmetry_equiv_pos_as_xyz'
                if not sym or rows is None:
                    stats['no symbol or no operators'] += 1
                    continue
                try:
                    ops = frozenset(canon(B.parse_symop(s)) for s in B._col(tags, rows, tag))
                except Exception:
                    stats['unparsable operator'] += 1
                    continue
                if len(ops) < 1:
                    continue
                found[sym][ops].append(os.path.basename(path))
                stats['harvested'] += 1
                break
    return found, stats


def build(found, report=False):
    table = {}
    kept = dropped = variants = 0
    lines = []
    for sym in sorted(found):
        good = []
        for ops, files in sorted(found[sym].items(), key=lambda kv: -len(kv[1])):
            ok, why = is_group(sorted(ops))
            if not ok:
                dropped += 1
                lines.append('  DROPPED %-14s %-14s (%d file%s: %s)' % (sym, why, len(files), '' if len(files) == 1 else 's', files[0]))
                continue
            good.append({'order': len(ops), 'files': len(files),
                         'ops': sorted([list(map(list, r)), list(t)] for r, t in ops)})
        if not good:
            continue
        kept += 1
        variants += len(good) - 1
        table[sym] = good
        lines.append('  %-16s order %-4d %s' % (sym, good[0]['order'],
                                                ('%d variants (different origin or setting)' % len(good)) if len(good) > 1 else ''))
    if report:
        print('\n'.join(lines))
    return table, kept, dropped, variants


def harvest_spglib(found):
    """Every setting of every space group from spglib's database (the International Tables, as a
    library; a dev-time dependency only — the shipped file is what the tool reads), added to `found`
    under the same normalised keys the corpus harvest uses: the short symbol ('P21/c'), the full one
    ('P 1 21/c 1' -> 'P121/C1'), and for the rhombohedral groups the ':H'/':R' forms. A setting the
    corpus already gave is kept as the corpus gave it (proven on a refined structure); the standard
    setting of each group is put first among what spglib adds. -> (found, stats, checks) where checks
    lists the corpus keys spglib disagrees with — there must be none."""
    import spglib
    stats = collections.Counter(); checks = []
    by_key = collections.defaultdict(list)                      # key -> [(rank, ops, label)]
    numbers = harvest_spglib.numbers = {}                        # key -> International Tables number, for the crystal system
    for h in range(1, 531):
        t = spglib.get_spacegroup_type(h)
        d = spglib.get_symmetry_from_database(h)
        ops = frozenset(canon((r.tolist(), tr.tolist())) for r, tr in zip(d['rotations'], d['translations']))
        ok, why = is_group(sorted(ops))
        if not ok:
            stats['not a group'] += 1; continue
        short = norm_symbol(t.international_short.replace('_', ''))
        full = norm_symbol(t.international_full.replace('_', ''))
        choice = (t.choice or '').strip()
        rank = 0 if choice in ('', '1', 'b', 'b1', 'H', '2') else 1   # the standard setting first; origin choice 2 keeps its own place after
        keys = {short, full}
        # a non-standard monoclinic cell choice is written short in a paper — 'I2/m', 'P21/a' — while
        # spglib's short symbol is the standard one ('C2/m', 'P21/c'): the short form of the FULL symbol
        m1 = re.match(r'^([A-Z])1(.+)1$', full) or re.match(r'^([A-Z])11(.+)$', full) or re.match(r'^([A-Z])(.+)11$', full)
        if m1:
            keys.add(m1.group(1) + m1.group(2))
        if short.startswith('R') and choice == 'H':
            keys |= {short + ':H', full + ':H'}
        elif short.startswith('R') and choice == 'R':
            keys = {short + ':R', full + ':R'}
        label = 'spglib #%d %s %s' % (t.number, t.international_full, choice)
        for k in keys:
            by_key[k].append((rank, ops, label)); numbers.setdefault(k, t.number)
        stats['settings'] += 1
    for k, entries in by_key.items():
        if k in found:
            have = set(found[k])
            if not any(ops in have for _r, ops, _l in entries):
                checks.append(k)                                # the corpus's operators for this key match no spglib setting
        for rank, ops, label in sorted(entries, key=lambda e: e[0]):
            if ops not in found[k]:
                found[k][ops].append(label)
                stats['added'] += 1
    return found, stats, checks


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('roots', nargs='+', help='corpus folders to harvest .cif files from')
    ap.add_argument('--out', default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                  'pxrd_review', 'data', 'symops.json.gz'))
    ap.add_argument('--report', action='store_true')
    ap.add_argument('--from-spglib', action='store_true', help='add every setting of all 230 groups from spglib (dev-time dependency), after the corpus harvest')
    a = ap.parse_args(argv)
    found, stats = harvest(a.roots)
    if a.from_spglib:
        found, sstats, checks = harvest_spglib(found)
        print('spglib: %s' % ', '.join('%s %d' % kv for kv in sstats.most_common()))
        if checks:
            print('CORPUS KEYS WHOSE OPERATORS MATCH NO SPGLIB SETTING (look at these): %s' % ', '.join(sorted(checks)))
    table, kept, dropped, variants = build(found, a.report)
    payload = {'note': 'space-group operators harvested from corpus .cif files; every set verified to be a '
                       'closed group with identity and inverses (tools/build_symops.py)',
               'frac': FRAC, 'groups': table, 'numbers': {k: n for k, n in getattr(harvest_spglib, 'numbers', {}).items() if k in table}}
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with gzip.open(a.out, 'wt', encoding='utf-8') as f:
        json.dump(payload, f, separators=(',', ':'), sort_keys=True)
    print('\ncif files read: %d (%s)' % (stats['cif'], ', '.join('%s %d' % (k, v) for k, v in stats.most_common() if k != 'cif')))
    print('symbols kept: %d (%d extra settings), operator sets dropped as not-a-group: %d' % (kept, variants, dropped))
    print('written: %s (%.1f kB)' % (a.out, os.path.getsize(a.out) / 1024.0))
    return 0


if __name__ == '__main__':
    sys.exit(main())
