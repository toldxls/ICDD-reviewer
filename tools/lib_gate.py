#!/usr/bin/env python3
"""The band library's gate: `bands.identify()` against each corpus paper's OWN numbered assignments.

    python3 tools/lib_gate.py <spectra_library<tag>.jsonl from tools/corpus_spectra.py> [--technique] [--blind]

For every stated band the paper assigns to a group and a numbered mode (ν1–ν4), the library is asked what the band
is expected to be in that paper's chemistry (the formula the jsonl carries — Mindat's, else the paper's); the top
answer is scored against the paper's own label. Prints top-1 mode, top-1 group and the count, overall and per group.
Run BEFORE and AFTER any change to the ranges, the measured windows, the scoring or `groups_of`; the number must not fall.
Reference 2026-10-10 (spectra_libraryr4.jsonl, 0.17.1): see the rules file. A dev tool: the jsonl is private, never the repo.
"""
import os, sys, json, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from pxrd_review import bands as BD

MODES = {1: 'ν1', 2: 'ν2', 3: 'ν3', 4: 'ν4'}


def score(path, technique=True, blind=False):
    tot = collections.Counter(); hit_mode = collections.Counter(); hit_group = collections.Counter()
    with open(path, encoding='utf-8') as f:
        for line in f:
            rec = json.loads(line)
            formula = None if blind else (rec.get('formula') or None)
            for b in rec.get('bands') or []:
                pos, tech, _shape, group, mode, own = (b + [None] * 6)[:6]
                if not group or not isinstance(mode, int) or mode not in MODES or not own:
                    continue
                want = '%s %s' % (group, MODES[mode])
                cands = BD.identify(float(pos), formula=formula, technique=(tech if technique else None))
                top = BD.label(cands[0]) if cands else ''
                tot[group] += 1
                hit_mode[group] += top == want
                hit_group[group] += bool(cands) and cands[0]['group'] == group
    return tot, hit_mode, hit_group


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('jsonl')
    ap.add_argument('--no-technique', action='store_true', help='ignore the stated technique')
    ap.add_argument('--blind', action='store_true', help='no formula: the windows alone')
    a = ap.parse_args(argv)
    tot, hm, hg = score(a.jsonl, technique=not a.no_technique, blind=a.blind)
    n = sum(tot.values())
    if not n:
        print('no numbered assignment in', a.jsonl); return 1
    print('LIB GATE %s%s: %d numbered bands of %d groups — top-1 mode %.1f %%, top-1 group %.1f %%' % (
        os.path.basename(a.jsonl), ' (blind)' if a.blind else '', n, len(tot), 100.0 * sum(hm.values()) / n, 100.0 * sum(hg.values()) / n))
    for g, t in sorted(tot.items(), key=lambda kv: -kv[1]):
        print('  %-8s %4d bands  mode %5.1f %%  group %5.1f %%' % (g, t, 100.0 * hm[g] / t, 100.0 * hg[g] / t))
    return 0


if __name__ == '__main__':
    sys.exit(main())
