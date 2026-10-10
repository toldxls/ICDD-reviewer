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


RRUFF_FILE = os.path.join(_HERE, 'data', 'band_windows_rruff.json')
RRUFF_MIN = 8                   # minerals: a RRUFF window stands in for a missing paper window from this many


@functools.lru_cache(maxsize=1)
def _rruff():
    """The windows measured on a RRUFF Raman library (tools/rruff_windows.py; single-group minerals, modes by the
    ion's geometry and free-ion ratios): {'GROUP mode': {'p5' … 'p95', 'n', 'minerals'}}."""
    try:
        with open(RRUFF_FILE, encoding='utf-8') as f:
            return json.load(f).get('windows') or {}
    except (OSError, ValueError):
        return {}


def rruff_window(key, mode):
    return _rruff().get('%s %s' % (key, mode))


def _published(key, mode, technique=None, windows=None):
    """The measured window of a mode — (window, 'raman' | 'ir' | 'any' | 'rruff') — or (None, None). The papers'
    stated positions first; where no paper window exists, the RRUFF spectra's (RRUFF_MIN minerals or more)."""
    w = (_windows() if windows is None else windows)
    name = '%s %s' % ('OH' if (key, mode) == ('H2O', 'stretch') else key, mode)
    entry = w.get(name)
    if entry:
        if technique and entry.get(technique):
            return entry[technique], technique
        if entry.get('any'):
            return entry['any'], 'any'
    r = rruff_window(key, mode) if windows is None else None
    if r and r.get('minerals', 0) >= RRUFF_MIN:
        return dict(r, papers=r['minerals']), 'rruff'
    return None, None


def _rows(keys, technique=None, windows=None):
    lib = library()
    for g in lib['groups']:
        if keys is not None and g['key'] not in keys:
            continue
        for m in g['modes']:
            pub, tech = _published(g['key'], m['mode'], technique, windows)
            yield {'group': g['key'], 'name': g['name'], 'writes': g['writes'], 'mode': m['mode'], 'what': m['what'], 'free': m.get('free'),
                   'lo': m['range'][0], 'hi': m['range'][1], 'active': m['active'], 'source': m['source'], 'check': bool(m.get('check')), 'broad': bool(m.get('broad')),
                   'published': pub, 'published_for': tech, 'rruff': rruff_window(g['key'], m['mode'])}


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


_ELEMENT_OF = {'OH': 'H', 'H2O': 'H', 'H3O': 'H', 'NH4': 'N', 'sulfide': 'S'}


def element_of(key):
    """The element a group is picked by — 'P' for PO4 and P-OH, 'S' for sulfate, sulfite and the sulfides, 'H' for
    water, hydroxyl and hydronium, 'N' for ammonium and nitrate."""
    return _ELEMENT_OF.get(key) or _ELEMENT.match(key).group(0)


def catalogue():
    """Every group the library knows, for picking: [{'key', 'name', 'writes', 'element', 'modes': [{'mode', 'label',
    'what', 'active', 'lo', 'hi', 'broad'}]}] in the library's order."""
    lib = library()
    out = []
    for g in lib['groups']:
        out.append({'key': g['key'], 'name': g['name'], 'writes': g['writes'], 'element': element_of(g['key']),
                    'modes': [{'mode': m['mode'], 'label': label({'group': g['key'], 'mode': m['mode']}), 'what': m['what'], 'active': lib['activity'][m['active']],
                               'lo': m['range'][0], 'hi': m['range'][1], 'broad': bool(m.get('broad'))} for m in g['modes']]})
    return out


_CHEM_TOKEN = re.compile(r'(?<=[A-Za-z)\]])(\d*[+−]|\d+-(?![A-Za-z]))|(?<=[A-Za-z)\]])(\d+(?:\.\d+)?)')


def chem_tokens(text):
    """A plain formula, oxide or ion as runs: [(kind, text)] with kind '' | 'sub' | 'sup' — a number after a Latin letter,
    ')' or ']' is a subscript, a charge (digits and + / −) after one a superscript; a number after '·', Σ or a Greek letter
    (the water count, ν3) stays. The rule the page's chem.js mirrors; for formula fields only, never prose ('R1')."""
    out, last = [], 0
    text = '' if text is None else str(text)
    for m in _CHEM_TOKEN.finditer(text):
        if m.start() > last:
            out.append(('', text[last:m.start()]))
        out.append(('sup' if m.group(1) is not None else 'sub', m.group(0)))
        last = m.end()
    if last < len(text):
        out.append(('', text[last:]))
    return out


_SUBSUP = re.compile(r'(</?su[bp]>)')


def formula_html(raw):
    """The formula with Mindat's own <sub> / <sup> kept and every other character escaped — safe to set as HTML."""
    import html as _h
    txt = re.sub(r'<(?!/?su[bp]>)[^>]+>', '', (raw or '').translate(_SUBS))
    txt = re.sub(r'[\s\x00-\x1f□◻]', '', _h.unescape(txt))                   # an entity (&#9723; = the vacancy sign) read, then dropped as `clean` drops the sign
    txt = re.sub(r'<sup>\d*[+\-−]</sup>|(?<=[A-Za-z])\d[+\-−](?!</sup>)', '', txt)   # valences dropped, as `display` drops them (Fe<sup>3+</sup>, Fe3+)
    return ''.join(part if _SUBSUP.fullmatch(part) else _h.escape(part, quote=False) for part in _SUBSUP.split(txt))


_SPECIES = None


def species_index():
    """Every species of the local Mindat snapshot with the groups its IMA formula holds: [(name, formula, frozenset of
    keys, formula as HTML)], by name. Read once (a quarter of a second for 6,000 species); nothing leaves the machine."""
    global _SPECIES
    if _SPECIES is None:
        rows = []
        try:
            from pxrd_review import mindat as M
            recs = M.struct_db().get('recs', [])
        except Exception:
            recs = []
        for r in recs:
            f = r.get('formula') or ''
            if r.get('name') and f:
                rows.append((r['name'], display(f), frozenset(groups_of(f)), formula_html(f)))
        rows.sort(key=lambda t: t[0].lower())
        _SPECIES = rows
    return _SPECIES


def species_with(keys):
    """The species whose formula holds EVERY one of `keys`: [(name, formula, formula as HTML)] by name — the minerals a
    picked chemistry stands for ('PO4' + 'UO2': the autunite and phosphuranylite groups and their kin)."""
    want = frozenset(keys)
    if not want:
        return []
    return [(n, f, h) for n, f, g, h in species_index() if want <= g]


def species_counts():
    """{group key: how many species of the snapshot hold it}."""
    out = {}
    for _n, _f, g, _h in species_index():
        for k in g:
            out[k] = out.get(k, 0) + 1
    return out


def label(r):
    """'SO4 ν1', 'H2O bend', 'ν(Si–O)' — a row's short name."""
    return r['mode'] if r['mode'][:2] in ('ν(', 'δ(', 'νs', 'νa') else '%s %s' % (r['group'], r['mode'])


def _window_text(r):
    p = r['published']
    if not p:
        return ''
    if r['published_for'] == 'rruff':
        return ''                                                # shown in its own column
    return '%d–%d, median %d (%d papers%s)' % (p['p5'], p['p95'], p['p50'], p['papers'], '' if r['published_for'] == 'any' else ', ' + {'raman': 'Raman', 'ir': 'infrared'}[r['published_for']])


def _rruff_text(r):
    w = r.get('rruff')
    return '%d–%d, median %d (%d minerals)' % (w['p5'], w['p95'], w['p50'], w['minerals']) if w else ''


_NAME = re.compile(r'^[A-Za-zÀ-ÿ\-]+(?:-?\([A-Za-z]+\))?$')


def looks_like_name(text):
    """Is the text the shape of a mineral name (letters, a hyphen, a Levinson suffix) rather than a formula? The first
    letter's case is no test ('Autunite', 'monazite-(Ce)' are names); a capital AFTER the first letter, outside the
    suffix, is a second element symbol ('PbS', 'NaCl', 'FeAsS' are formulas) — unless the whole word is typed in
    capitals ('AUTUNITE')."""
    text = (text or '').strip()
    if not text or re.search(r'\d', text) or not _NAME.match(text):
        return False
    core = re.sub(r'-?\([A-Za-z]+\)$', '', text)
    return len(core) > 2 and (not re.search(r'[A-Z]', core[1:]) or (core.isupper() and len(core) > 3))


def resolve(arg):
    """(formula, mineral name or '') — a mineral name looked up in the local Mindat snapshot (any case), else the text
    as a formula; `looks_like_name` tells a name that did not resolve from a formula."""
    arg = (arg or '').strip()
    if looks_like_name(arg):
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
    head = ('band', 'what', 'active', 'free ion', 'range in minerals', 'published positions', 'RRUFF spectra')
    body = [(label(r), r['what'], lib['activity'][r['active']], '' if r['free'] is None else '%d' % r['free'],
             '%d–%d%s' % (r['lo'], r['hi'], ' *' if r['check'] else ''), _window_text(r), _rruff_text(r)) for r in rows]
    if not any(x[6] for x in body):
        head = head[:6]; body = [x[:6] for x in body]
    w = [max(len(x[i]) for x in [head] + body) for i in range(len(head))]
    for x in [head] + body:
        L.append('  ' + '  '.join(c.ljust(w[i]) for i, c in enumerate(x)).rstrip())
    L.append('')
    if any(r['check'] for r in rows):
        L.append('  * entered from memory of the source, not yet compared with it line by line (data/band_library.json)')
    L.append('  sources: ' + '; '.join(lib['sources'][s].split(' — ')[0] for s in sorted({r['source'] for r in rows})))
    L.append('  published positions: the 5th–95th percentile of what published mineral descriptions assign to that mode')
    if len(head) > 6:
        L.append('  RRUFF spectra: the same percentiles of the band in the Raman spectra of minerals whose formula holds this group alone (data/band_windows_rruff.json)')
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
    if formula is not None and not name and looks_like_name(formula):
        print('no species named ‘%s’ in the local Mindat snapshot — give its formula' % formula)
        formula = None
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
