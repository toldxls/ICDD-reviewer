#!/usr/bin/env python3
"""The band library: for a chemistry, the vibrational bands expected of it — and for a band, what it is expected
to be in that chemistry.

    pxrd bands "Ca(UO2)2(PO4)2·11H2O"                 the groups the formula holds, each mode, where its band stands
    pxrd bands autunite                               the same from a mineral name (the local Mindat snapshot)
    pxrd bands "Cu4(SO4)(OH)6" --at 985,3400,1630     what each band is expected to be in that chemistry
    pxrd bands --at 830 [--raman | --ir]              with no chemistry: every group whose band stands there
    pxrd bands --groups                               the groups the library knows

Two sources side by side, never merged into one number:
  * `data/band_library.json` — hand-maintained: per group and mode the free-ion fundamental and the range the band
    takes in minerals, each with its source; an entry tagged `check` was entered from memory of that source.
  * `data/band_windows.json` — measured: the percentiles of the positions published mineral descriptions assign to
    that mode (built by tools/corpus_spectra.py; a window needs 8 papers).
A reference to read a spectrum against, never a finding: windows of different groups overlap wherever their bands
do (ν1 of uranyl and ν1 of arsenate, ν3 of phosphate and ν3 of sulfate), and the formula says which of them a band
can belong to — not which it does.
"""
import os, re, sys, json, functools

_HERE = os.path.dirname(os.path.abspath(__file__))
LIBRARY_FILE = os.path.join(_HERE, 'data', 'band_library.json')
WINDOWS_FILE = os.path.join(_HERE, 'data', 'band_windows.json')

_SUBS = str.maketrans('₀₁₂₃₄₅₆₇₈₉', '0123456789')
_ELEMENT = re.compile(r'[A-Z][a-z]?')
_NO_GROUP = ('S', 'Se', 'Te', 'As', 'Sb', 'Bi')              # with no oxygen in the formula: a sulfide, a sulfosalt


@functools.lru_cache(maxsize=1)
def library():
    """The hand-maintained table (data/band_library.json): {'groups': [...], 'always': [...], 'sources': {...}}."""
    with open(LIBRARY_FILE, encoding='utf-8') as f:
        return json.load(f)


@functools.lru_cache(maxsize=1)
def _windows():
    try:
        with open(WINDOWS_FILE, encoding='utf-8') as f:
            return json.load(f).get('windows') or {}
    except (OSError, ValueError):
        return {}


_MIXED = re.compile(r'\(([^()]*)\)(?:Σ[\d.]+)?\)?O([34])')        # a mixed site before its oxygens: (Se0.8S0.2)Σ1.0O4
_SITE_ATOM = re.compile(r'([A-Z][a-z]?)(\d+(?:\.\d+)?)?')


def clean(formula):
    """(formula with its valence superscripts, markup and spaces removed; the same with the valences kept).
    A mixed site written before its oxygens — '(Se0.8S0.2)O4' of an empirical formula — is read as its dominant
    atom's group ('SeO4')."""
    raw = re.sub(r'<[^>]+>|&#?\w+;|[\s\x00-\x1f□◻]', '', (formula or '').translate(_SUBS))
    f = re.sub(r'(?<=[A-Za-z])\d[+\-−]', '', raw)
    def dominant(m):
        atoms = [(float(n) if n else 1.0, el) for el, n in _SITE_ATOM.findall(m.group(1))]
        return '(%sO%s)' % (max(atoms)[1], m.group(2)) if len(atoms) > 1 else m.group(0)
    return _MIXED.sub(dominant, f), raw


def display(formula):
    """The formula as it is shown: markup, spaces and valence superscripts removed, nothing else rewritten."""
    return re.sub(r'(?<=[A-Za-z])\d[+\-−]', '', clean(formula)[1])


def elements(formula):
    return set(_ELEMENT.findall(clean(formula)[0]))


MINOR = 0.25                    # a group or an atom an empirical formula writes with a coefficient under this is a substituent,
                                # not a group of the mineral: '(SiO4)0.04' beside '(SO4)0.96'


_OPEN, _CLOSE = '([{', ')]}'
_COEFF = re.compile(r'(\d*\.\d+)')


def _minor(f, start, end):
    """Is what stands at f[start:end] written with a coefficient under `MINOR` — its own ('Si0.04'), or that of a
    bracket around it ('(SiO4)0.04', '[Si(OH)6]0.10')?"""
    n = _COEFF.match(f, end)
    if n and float(n.group(1)) < MINOR:
        return True
    depth = 0
    for k in range(end, len(f)):                                 # each bracket that closes around it, and the number after it
        c = f[k]
        if c in _OPEN:
            depth += 1
        elif c in _CLOSE:
            if depth:
                depth -= 1
                continue
            n = _COEFF.match(f, k + 1)
            if n and float(n.group(1)) < MINOR:
                return True
    return False


def _major(pattern, f):
    """Does the formula hold what `pattern` names as more than a minor substituent?"""
    return any(not _minor(f, m.start(), m.end()) for m in re.finditer(pattern, f))


def groups_of(formula):
    """The library groups a formula holds, in the library's order: ['UO2', 'PO4', 'H2O'] for an autunite."""
    f, raw = clean(formula)
    if not f:
        return []
    el = set(_ELEMENT.findall(f))
    out = []
    for g in library()['groups']:
        key = g['key']
        if key == 'OH':
            hit = 'OH' in f.replace('H2O', '').replace('H3O', '')
        elif key == 'sulfide':
            hit = 'O' not in el and bool(el & set(_NO_GROUP))
        elif key == 'UO2':
            hit = 'UO2' in f and f != 'UO2'                      # uraninite is no uranyl mineral
        else:
            hit = any(_major(p, f) for p in g.get('in', ())) or any(re.search(p, raw) for p in g.get('raw', ()))
        if hit and g.get('with_o') and 'O' not in el:
            hit = False
        if hit and (any(re.search(p, f) for p in g.get('not', ())) or any(re.search(p, raw) for p in g.get('not_raw', ()))):
            hit = False
        if hit:
            out.append(key)
    return out


def _published(key, mode, technique=None, windows=None):
    """The measured window of a mode — (window, 'raman' | 'ir' | 'any') — or (None, None)."""
    w = (_windows() if windows is None else windows)
    name = '%s %s' % ('OH' if (key, mode) == ('H2O', 'stretch') else key, mode)
    entry = w.get(name)
    if not entry:
        return None, None
    if technique and entry.get(technique):
        return entry[technique], technique
    return (entry['any'], 'any') if entry.get('any') else (None, None)


def _rows(keys, technique=None, windows=None):
    lib = library()
    for g in lib['groups']:
        if keys is not None and g['key'] not in keys:
            continue
        for m in g['modes']:
            pub, tech = _published(g['key'], m['mode'], technique, windows)
            yield {'group': g['key'], 'name': g['name'], 'writes': g['writes'], 'mode': m['mode'], 'what': m['what'], 'free': m.get('free'),
                   'lo': m['range'][0], 'hi': m['range'][1], 'active': m['active'], 'source': m['source'], 'check': bool(m.get('check')), 'broad': bool(m.get('broad')),
                   'published': pub, 'published_for': tech}


def expected(formula=None, technique=None, groups=None, windows=None):
    """The bands expected of a chemistry: one row per group and mode, highest wavenumber first —
    {'group', 'name', 'mode', 'what', 'free', 'lo', 'hi', 'active', 'source', 'check', 'published', 'published_for'}.
    `lo`–`hi` is the range in minerals from the literature; `published` the measured window ({'p5' … 'p95', 'papers'})
    where the papers give one. `groups` instead of a formula takes the group keys as they are."""
    keys = list(groups) if groups is not None else groups_of(formula)
    rows = list(_rows(set(keys), technique, windows))
    rows.sort(key=lambda r: -(r['published']['p50'] if r['published'] else (r['lo'] + r['hi']) / 2.0))
    return rows


def _score(pos, r):
    """How far a band stands from where a mode is expected, in widths of that expectation (0 = on its centre)."""
    p = r['published']
    if p:
        return abs(pos - p['p50']) / max(10.0, float(p['p75'] - p['p25']))
    mid = r['free'] if r['free'] is not None and r['lo'] <= r['free'] <= r['hi'] else (r['lo'] + r['hi']) / 2.0
    return abs(pos - mid) / max(10.0, (r['hi'] - r['lo']) / 2.4)


def _inside(pos, r):
    p = r['published']
    return r['lo'] <= pos <= r['hi'] or bool(p and p['p5'] <= pos <= p['p95'])


def identify(pos, formula=None, technique=None, groups=None, windows=None):
    """What a band at `pos` is expected to be: the modes whose range (or measured window) holds it —
    [{… the row of `expected` …, 'in_formula': True | False | None, 'score'}] — those of the chemistry first, the
    nearest to its usual position first (a 'broad' mode — librations, M–O–H bends — after the others); `in_formula` is None when no chemistry was given. The two entries every
    chemistry shares (C–H of organic matter, metal–oxygen and lattice modes) come last, 'in_formula' None."""
    keys = None if formula is None and groups is None else set(groups if groups is not None else groups_of(formula))
    out = []
    for r in _rows(None, technique, windows):
        if r['group'] == 'sulfide' and (keys is None or 'sulfide' not in keys):
            continue
        if _inside(pos, r):
            out.append(dict(r, in_formula=None if keys is None else r['group'] in keys, score=round(_score(pos, r), 2)))
    out.sort(key=lambda r: (not r['in_formula'] if keys is not None else False, r['broad'], r['score'], r['group'], r['mode']))
    for a in library()['always']:
        if a['range'][0] <= pos <= a['range'][1]:
            out.append({'group': a['key'], 'name': a['name'], 'writes': a['key'], 'mode': a['mode'], 'what': a['what'], 'free': None, 'lo': a['range'][0],
                        'hi': a['range'][1], 'active': a['active'], 'source': a['source'], 'check': False, 'broad': True, 'published': None, 'published_for': None,
                        'in_formula': None, 'score': None})
    return out


def label(r):
    """'SO4 ν1', 'H2O bend', 'ν(Si–O)' — a row's short name."""
    return r['mode'] if r['mode'][:2] in ('ν(', 'δ(', 'νs', 'νa') else '%s %s' % (r['group'], r['mode'])


def _window_text(r):
    p = r['published']
    if not p:
        return ''
    return '%d–%d, median %d (%d papers%s)' % (p['p5'], p['p95'], p['p50'], p['papers'], '' if r['published_for'] == 'any' else ', ' + {'raman': 'Raman', 'ir': 'infrared'}[r['published_for']])


def resolve(arg):
    """(formula, mineral name or '') — a mineral name looked up in the local Mindat snapshot, else the text as a formula."""
    arg = (arg or '').strip()
    if arg and not re.search(r'\d', arg) and re.match(r'^[A-Za-zÀ-ÿ\-]+(?:-?\([A-Za-z]+\))?$', arg) and arg.lower() == arg:
        try:
            from pxrd_review import paper_extract as PE
            rec = PE.species_record(arg)
            if rec and rec.get('formula'):
                return re.sub(r'<[^>]+>', '', rec['formula']), arg
        except Exception:
            pass
    return arg, ''


def table(formula, technique=None, name=''):
    """The expected bands of a chemistry as text lines."""
    keys = groups_of(formula)
    lib = library()
    names = {g['key']: g['name'] for g in lib['groups']}
    L = ['%s%s' % (name + ': ' if name else '', display(formula))]
    if not keys:
        L.append('  no group of the library in this formula — its bands are metal–anion and lattice modes, below about 600 cm⁻¹')
        return L
    L.append('  groups: ' + ', '.join('%s (%s)' % (k, names[k]) for k in keys))
    L.append('')
    rows = expected(formula, technique)
    head = ('band', 'what', 'active', 'free ion', 'range in minerals', 'published positions')
    body = [(label(r), r['what'], lib['activity'][r['active']], '' if r['free'] is None else '%d' % r['free'],
             '%d–%d%s' % (r['lo'], r['hi'], ' *' if r['check'] else ''), _window_text(r)) for r in rows]
    w = [max(len(x[i]) for x in [head] + body) for i in range(len(head))]
    for x in [head] + body:
        L.append('  ' + '  '.join(c.ljust(w[i]) for i, c in enumerate(x)).rstrip())
    L.append('')
    if any(r['check'] for r in rows):
        L.append('  * entered from memory of the source, not yet compared with it line by line (data/band_library.json)')
    L.append('  sources: ' + '; '.join(lib['sources'][s].split(' — ')[0] for s in sorted({r['source'] for r in rows})))
    L.append('  published positions: the 5th–95th percentile of what published mineral descriptions assign to that mode')
    return L


def at_lines(positions, formula=None, technique=None):
    """What each band is expected to be, as text lines."""
    L = []
    for pos in positions:
        cands = identify(pos, formula, technique)
        own = [c for c in cands if c['in_formula'] is True]
        other = [c for c in cands if c['in_formula'] is False]
        blind = [c for c in cands if c['in_formula'] is None and c['score'] is not None]
        shared = [c for c in cands if c['score'] is None]
        say = lambda c: '%s (%s; %d–%d)' % (label(c), c['what'].split(' (')[0], *((c['published']['p5'], c['published']['p95']) if c['published'] else (c['lo'], c['hi'])))
        if formula is None:
            L.append('%g cm⁻¹: %s' % (pos, '; '.join(say(c) for c in blind + shared) or 'no group of the library has a band here'))
            continue
        if own:
            L.append('%g cm⁻¹: %s' % (pos, '; '.join(say(c) for c in own)))
        else:
            L.append('%g cm⁻¹: no group of this formula is expected here' % pos + ('' if not shared else ' — ' + '; '.join(say(c) for c in shared)))
        if other:
            L.append('      of another chemistry: ' + ', '.join(label(c) for c in other[:6]))
        elif own and shared and not any(c['group'] == 'M-O' for c in shared):
            L.append('      or: ' + '; '.join(say(c) for c in shared))
    return L


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog='pxrd bands', description=__doc__.split('\n\n')[0])
    ap.add_argument('chemistry', nargs='?', help='a formula ("Ca(UO2)2(PO4)2·11H2O") or a mineral name (looked up in the local Mindat snapshot)')
    ap.add_argument('--at', help='band positions (cm⁻¹, comma-separated): what each is expected to be')
    ap.add_argument('--raman', action='store_true', help='the published positions measured by Raman, where there are enough')
    ap.add_argument('--ir', action='store_true', help='the published positions measured by infrared, where there are enough')
    ap.add_argument('--groups', action='store_true', help='list the groups the library knows')
    a = ap.parse_args(argv)
    tech = 'raman' if a.raman else 'ir' if a.ir else None
    if a.groups:
        for g in library()['groups']:
            print('%-8s %-34s %s' % (g['key'], g['name'], ', '.join(m['mode'] for m in g['modes'])))
        return 0
    if not a.chemistry and not a.at:
        ap.print_usage(); return 2
    formula, name = resolve(a.chemistry) if a.chemistry else (None, '')
    if formula is not None:
        print('\n'.join(table(formula, tech, name)))
    if a.at:
        try:
            positions = [float(x) for x in re.split(r'[,\s]+', a.at.strip()) if x]
        except ValueError:
            print('--at takes wavenumbers: 985,3400,1630'); return 2
        if formula is not None:
            print()
        print('\n'.join(at_lines(positions, formula, tech)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
