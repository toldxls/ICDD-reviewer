#!/usr/bin/env python3
"""
Mineral names on a .pdf page: which words name an IMA species, and which look like a misspelt one.

Drives the GUI's name layer (hover a highlighted name in the .pdf pane → its Mindat formula). A
reading AID, not a check: nothing here is written into a docx, a log or a finding.

LOCAL ONLY. The names come from the Mindat snapshot already on disk (the bundled seed or the user's
own pull, via `mindat.struct_db`), and a paper's words are matched against it in memory — a word read
from a paper is never sent to Mindat or anywhere else (see CLAUDE.md, "A paper is parsed locally").

Spelling is conservative by construction: a word is only called a misspelling when it has the shape
of a species name (ends -ite/-ine/-ase/…), is long enough that one slip still leaves it recognisable,
is neither a species, a Mindat group nor a common word of the same shape, and sits one edit (two for
a long name) from a species that shares its first letter. A near-miss storm on every page would
teach the reviewer to ignore the layer.
"""
import html
import re
import unicodedata

from pxrd_review import mindat

# The species whose names are everyday words in a paper's prose. Highlighting every 'ice' or 'lime'
# would bury the real names; they are still looked up when the word is capitalised mid-sentence.
_PROSE_SPECIES = {'ice', 'lime', 'urea'}
# group names that are everyday words in a paper's prose: named as a group only before 'group'
_PROSE_GROUPS = {'iron', 'nickel', 'copper', 'arsenic', 'silica', 'selenium', 'sulphur', 'sulfur', 'alum', 'glycolate',
                 'gold', 'silver', 'lead', 'platinum', 'mercury', 'tin', 'zinc', 'bismuth', 'antimony', 'tellurium'}

# Words of a mineral name's shape that are NOT a misspelt species (seen in the corpus, or common
# enough in a mineralogy paper that a near-miss suggestion would be noise). Varieties and rock or
# series names Mindat does not list as an IMA species belong here too.
COMMON = {
    # English
    'composite', 'definite', 'infinite', 'opposite', 'favorite', 'favourite', 'despite', 'quite',
    'white', 'write', 'site', 'sites', 'suite', 'unite', 'elite', 'polite', 'satellite', 'appetite',
    'website', 'prerequisite', 'requisite', 'exquisite', 'finite', 'indefinite', 'contrite', 'termite',
    'kryptonite', 'dynamite', 'marguerite', 'bauxite', 'granite', 'laterite', 'phosphorite', 'ignite',
    'determine', 'examine', 'combine', 'machine', 'routine', 'medicine', 'discipline', 'baseline',
    'outline', 'underline', 'online', 'decline', 'engine', 'imagine', 'pristine', 'genuine', 'feline',
    'marine', 'submarine', 'doctrine', 'intestine', 'masculine', 'feminine', 'quarantine', 'vaccine',
    'database', 'increase', 'decrease', 'release', 'purchase', 'phrase', 'phase', 'phases', 'crease',
    'provide', 'decide', 'reside', 'inside', 'outside', 'beside', 'aside', 'divide', 'guide', 'override',
    'suicide', 'coincide', 'collide', 'slide', 'glide', 'pride', 'bride', 'stride', 'wide', 'tide',
    # chemistry and mineralogy vocabulary of the same shape
    'sulfide', 'sulphide', 'oxide', 'hydroxide', 'chloride', 'fluoride', 'bromide', 'iodide', 'nitride',
    'carbide', 'hydride', 'selenide', 'telluride', 'arsenide', 'antimonide', 'boride', 'silicide',
    'sulfite', 'sulphite', 'nitrite', 'selenite', 'arsenite', 'antimonite',
    'phosphite', 'hypochlorite', 'chlorine', 'fluorine', 'bromine', 'iodine', 'amine',
    'glycine', 'alanine', 'cysteine', 'purine', 'pyrimidine', 'pyridine', 'imidazole', 'triazine',
    'zeolites', 'hornblende',
    'pyroxene', 'amphibole', 'illite',
    'glauconite', 'limonite', 'wad', 'psilomelane', 'leucoxene', 'sericite', 'saussurite',
    'uralite', 'iddingsite', 'bowlingite', 'palagonite', 'ferrite', 'austenite',
    'martensite', 'pearlite', 'cementite', 'bainite', 'ledeburite', 'anthracite', 'lignite',
    'kimberlite', 'lamproite', 'carbonatite', 'pegmatite', 'aplite', 'rhyolite', 'dacite', 'andesite',
    'trachyte', 'phonolite', 'syenite', 'diorite', 'tonalite', 'granodiorite', 'monzonite', 'dolerite',
    'diabase', 'basanite', 'tephrite', 'foidite', 'peridotite', 'dunite', 'harzburgite', 'lherzolite',
    'wehrlite', 'websterite', 'pyroxenite', 'hornblendite', 'anorthosite', 'norite', 'troctolite',
    'eclogite', 'amphibolite', 'quartzite', 'marble', 'skarn', 'hornfels', 'mylonite', 'cataclasite',
    'breccia', 'tuff', 'ignimbrite', 'obsidian', 'pumice', 'scoria', 'komatiite', 'picrite', 'ankaramite',
    'tachylite', 'sideromelane', 'chondrite', 'achondrite', 'meteorite', 'meteorites', 'micrometeorite',
    'eucrite', 'diogenite', 'howardite', 'ureilite', 'aubrite', 'angrite', 'brachinite', 'pallasite',
    'mesosiderite', 'shergottite', 'nakhlite', 'chassignite', 'tektite', 'fulgurite', 'concretion',
    'stalactite', 'stalagmite', 'speleothem', 'evaporite', 'turbidite', 'tillite', 'diamictite',
    'bentonite', 'laterite', 'ferricrete', 'calcrete', 'silcrete', 'gossan', 'jasperoid', 'greisen',
    'propylite', 'argillite', 'pelite', 'psammite', 'psephite', 'rudite', 'arenite', 'lutite', 'siltite',
    'mudstone', 'kaolin', 'hydroxyapatite',
    'electrolyte', 'electrolytes', 'analyte', 'analytes', 'dendrite', 'dendrites',
    'polyhedra', 'coordinate', 'coordinates', 'crystallite', 'crystallites', 'spherulite', 'spherulites',
    'sphene', 'chalcogenide', 'chalcogenides', 'antisite', 'symplectite', 'metabasite', 'metasomite',
    'metadiorite', 'araldite', 'christine', 'christiane', 'listwanite', 'sylvinite', 'leucogranite',
    'tsavorite', 'morganite', 'phengite', 'francolite', 'hydrosaline', 'agpaite', 'rhodingite', 'tactite',
    'lithionite', 'nephelinite', 'lanthanide', 'lanthanides', 'actinide', 'actinides', 'germanide',
}

# A species name's shape: the endings nearly every IMA name carries. A word without one is not
# offered a spelling suggestion (it is still recognised if it IS a species, e.g. 'quartz').
_SHAPE = re.compile(r'(?:ite|ine|ase|ide|ote|yte|ene|ane|ite-\([a-z]{1,2}\)|ine-\([a-z]{1,2}\))$')
# What a word may carry around a name: a trailing '-group', '-type', a bracketed Levinson suffix …
_AFFIX = re.compile(r'[-‐](?:group|groups|type|like|bearing|rich|poor|structure|structured|related|'
                    r'supergroup|subgroup|series|family|topology)$')
_EDGE = '.,;:!?"\'“”‘’()[]{}*†‡§¶'
_SPLIT = re.compile(r'[–—/×]')          # 'jarosite–alunite', 'calcite/aragonite'

_IDX = None


# letters NFKD does not decompose; a paper's text layer (or its author) writes them plainly
_PLAIN = str.maketrans({'ø': 'o', 'Ø': 'O', 'ł': 'l', 'Ł': 'L', 'æ': 'ae', 'Æ': 'Ae', 'œ': 'oe', 'ß': 'ss',
                        'đ': 'd', 'ı': 'i', '’': "'"})
# the German / Scandinavian transliteration a name is often printed in ('bastnaesite', 'boehmite')
_TRANSLIT = str.maketrans({'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ø': 'oe', 'å': 'aa'})


def _fold(s):
    s = unicodedata.normalize('NFKD', (s or '').translate(_PLAIN))
    return ''.join(c for c in s if not unicodedata.combining(c))


def _squash(n):
    return n.replace('-', '').replace(' ', '').replace("'", '')


# a species name's own suffix: Levinson '-(Ce)' or a longer one ('-(CaMnMg)', '-(Fe2+)'), a letter/number
# variant or polytype ('joséite-B', 'baumhauerite ii', 'ferronigerite-2N1S')
_SUFFIX = re.compile(r"(?:-\([a-z0-9+,]+\)|[- ](?:[a-z]|[0-9][a-z0-9']*|i{1,3}|iv))$")


def _index():
    """(recs, squash, roots, groups, dels): {norm -> struct record}; {name without hyphens -> norms};
    {name without its suffix -> norms} for a root like 'davidite' ('-(La)', '-(Ce)'); the Mindat group
    names; and the one/two-delete neighbourhoods of the names, for spelling."""
    global _IDX
    if _IDX is not None:
        return _IDX
    recs, squash, roots = {}, {}, {}
    for r in (mindat.struct_db() or {}).get('recs', []):
        n = r.get('norm') or mindat._norm(r.get('name', ''))
        if not n or n in recs:
            continue
        recs[n] = r
        for key in {_squash(_fold(n)), _squash(_fold(r.get('name', '').lower().translate(_TRANSLIT)))}:
            squash.setdefault(key, []).append(n)
        root = _SUFFIX.sub('', n)
        if root != n:
            roots.setdefault(root, []).append(n)
    groups = set(_group_index(recs)['byname'])
    # symmetric-delete index (SymSpell-style) over the names' roots: a query within two edits of a
    # name shares at least one 0/1/2-delete variant with it.
    dels = {}
    for n in recs:
        b = _SUFFIX.sub('', n)
        if ' ' in b or len(b) < 6:
            continue
        for d in _deletes(b, 2):
            dels.setdefault(d, set()).add(n)
    _IDX = (recs, squash, roots, groups, dels)
    return _IDX


def _deletes(w, depth):
    out, frontier = {w}, {w}
    for _ in range(depth):
        nxt = set()
        for s in frontier:
            for i in range(len(s)):
                nxt.add(s[:i] + s[i + 1:])
        out |= nxt
        frontier = nxt
    return out


def distance(a, b):
    """Optimal-string-alignment distance (a transposition counts as one edit)."""
    la, lb = len(a), len(b)
    d = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            c = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[la][lb]


def _clean(word):
    """A word box's text → the name it may carry (normalised), or ''. Strips edge punctuation but
    keeps a Levinson suffix's brackets ('bastnäsite-(Ce),' → 'bastnasite-(ce)')."""
    return _clean_affix(word)[0]


def _clean_affix(word):
    """(name, affix): `_clean`, and the affix it stripped ('crichtonite-group' → ('crichtonite', 'group'))."""
    w = _fold(word).strip().replace('’', "'")
    m = re.search(r'-\([A-Za-z0-9+,]+\)', w)            # a suffix's brackets are the name's: '-(Ce)', '-(CaMnMg)', '-(Fe2+)'
    keep = m.end() if m else 0
    while w and w[0] in _EDGE:
        w, keep = w[1:], max(0, keep - 1)
    while len(w) > keep and w[-1] in _EDGE:
        w = w[:-1]
    w = w.replace('’s', '').replace("'s", '').lower()
    m = _AFFIX.search(w)
    affix = m.group(0)[1:] if m else ''
    w = w[:m.start()] if m else w
    # letters, hyphens and an apostrophe ("d'ansite"); digits, '+' and commas only in a suffix — bracketed
    # ('julgoldite-(fe2+)', '-(ce,la)') or a polytype after the last hyphen ('ferronigerite-2n1s'). A digit
    # inside the word is a scan's misreading ('jask6lskiite'), not a name
    return (mindat._norm(w), affix) if _WORD.fullmatch(w or '') else ('', '')


_WORD = re.compile(r"[a-z][a-z'\-]*[a-z]'?(?:-\([a-z0-9+,]+\))?(?:-[0-9a-z']+)*|[a-z]")


def lookup(token):
    """(how, [norms]) for the species a cleaned token names, or (None, []):
    'exact' — the IMA name; 'spelling' — the IMA name written without/with its hyphens
    ('magnesiohastingsite' → Magnesio-hastingsite); 'root' — a name without its suffix
    ('davidite' → Davidite-(La), Davidite-(Ce)); 'polytype' — the species with a polytype suffix the
    snapshot does not list ('dioskouriite-2M')."""
    recs, squash, roots, _g, _d = _index()
    if token in recs:
        return 'exact', [token]
    hit = squash.get(_squash(token), [])
    same = [h for h in hit if _fold(h) == token]            # 'nybøite' printed as it is, ø read as o
    if same:
        return 'exact', same
    if hit:
        return 'spelling', hit
    if token in roots or _squash(token) in roots:            # 'tetrahe-drite': a break hyphen the text kept
        return 'root', roots.get(token) or roots[_squash(token)]
    m = re.fullmatch(r"(.+?)-(?:[0-9][a-z0-9']*|[a-z][0-9])", token)   # a polytype the IMA does not list ('dioskouriite-2m')
    if m and m.group(1) in recs:
        return 'polytype', [m.group(1)]
    return None, []


def _built_on_species(base, recs):
    """A word made FROM a species name — a rock ('chromitite', 'sanidinite'), a compositional
    variety ('titanomagnetite') — is not a misspelling of the species nearest it."""
    for k in range(6, len(base) - 2):
        head, tail = base[:k], base[len(base) - k:]
        if head in recs or head + 'e' in recs or tail in recs:
            return True
    return False


def suggest(token):
    """The species (normalised names) a cleaned token is probably a misspelling of — [] when it names a species, a
    group or a common word, is built on a species, or is not close enough to one."""
    recs, _s, roots, groups, dels = _index()
    if not token or token in groups or token in COMMON or lookup(token)[0]:
        return []
    base = re.sub(r'-\([a-z]{1,2}\)$', '', token)
    if len(base) < 7 or not _SHAPE.search(token) or base in COMMON or base in groups:
        return []
    if base.endswith('s') and (lookup(base[:-1])[0] or base[:-1] in COMMON or base[:-1] in groups):
        return []                                           # a plural: 'calcites'
    if _built_on_species(base, recs):
        return []
    limit = 1 if len(base) < 10 else 2
    cands = set()
    for d in _deletes(base, limit):
        cands |= dels.get(d, set())
    out = {}
    for c in cands:
        cb = _SUFFIX.sub('', c)
        if cb[0] != base[0]:
            continue
        k = distance(base, cb)
        if 0 < k <= limit:
            out.setdefault(cb, (k, c))                      # one root per suggestion
    best = sorted(out.values())
    best = [c for k, c in best if k == best[0][0]] if best else []
    return sorted(best)[:3]


_GROUP_WORDS = {'group', 'groups', 'supergroup', 'subgroup', 'series', 'family'}
_GIDX = None


def _group_base(name):
    """'Crichtonite Group' / 'Apatite Supergroup' / 'Lillianite Homologous Series' / 'Hornblende Root Name' /
    'Tourmaline' → the name a paper writes ('crichtonite', 'apatite', 'lillianite', 'hornblende', 'tourmaline')."""
    n = mindat._norm(name)
    return re.sub(r'(?:\s+(?:(?:super|sub)?group|(?:homologous\s+)?series|family|root\s+name))+$', '', n).strip()


def _group_index(recs=None):
    """{groups, kids, members, byname}: the snapshot's groups (with their parent), each group's
    child groups, its DIRECT member species (normalised names), and base name → group ids."""
    global _GIDX
    if _GIDX is not None:
        return _GIDX
    recs = recs if recs is not None else _index()[0]
    G = (mindat._db() or {}).get('groups', {})
    kids, members, byname = {}, {}, {}
    for gid, g in G.items():
        p = g.get('parent') or ''
        if p in G and p != gid:
            kids.setdefault(p, []).append(gid)
        base = _group_base(g.get('name', ''))
        if base:
            byname.setdefault(base, []).append(gid)
    for n, r in recs.items():
        gid = str(r.get('groupid') or '')
        if gid in G:
            members.setdefault(gid, []).append(n)
    _GIDX = {'groups': G, 'kids': kids, 'members': members, 'byname': byname}
    return _GIDX


def _descendants(gid):
    """gid and every group under it, parents first (a cycle in the data cannot loop)."""
    kids, out, stack = _group_index()['kids'], [], [gid]
    while stack:
        g = stack.pop()
        if g in out:
            continue
        out.append(g)
        stack.extend(sorted(kids.get(g, []), key=lambda k: _group_index()['groups'][k].get('name', ''), reverse=True))
    return out


def group_members(gid):
    """Every species under a group, its subgroups' included (normalised names)."""
    mem = _group_index()['members']
    return [n for g in _descendants(gid) for n in mem.get(g, [])]


def pick_group(base, word=''):
    """The group a paper means by '<base> <word>' ('group', 'supergroup', 'subgroup', 'series', or ''
    for the bare name), or None. With no word, or a word the snapshot does not match, the TOPMOST of
    the groups sharing the name ('apatite' → Apatite Supergroup, which holds the Apatite Group)."""
    gi = _group_index()
    gids = gi['byname'].get(base) or []
    if not gids:
        return None
    word = {'groups': 'group', 'family': 'group'}.get(word, word)
    if word:
        for g in gids:
            nm = gi['groups'][g].get('name', '').lower()
            if (word == 'group' and nm.endswith(' group') and not re.search(r'(super|sub)group$', nm)) or \
                    (word != 'group' and nm.endswith(word)):
                return g
    top = [g for g in gids if gi['groups'][g].get('parent') not in gids]
    return sorted(top or gids, key=lambda g: -len(group_members(g)))[0]


def _pair(tok):
    """The species of a hyphenated series ('bismuthinite-aikinite' → both), or [] — every part a species
    name of its own. An IMA name with a hyphen ('magnesio-hastingsite') never gets here: it is a species."""
    parts = [x for x in tok.split('-') if x]
    if len(parts) > 1 and all(len(x) > 3 and lookup(x)[0] in ('exact', 'root') for x in parts):
        return parts
    return []


def _names_in(text):
    """True when a word's text carries a species or a group name ('crichtonite-group', 'åsgruvanite-(Ce)',
    'bismuthinite-aikinite')."""
    for part in _SPLIT.split(text):
        tok, affix = _clean_affix(part)
        if tok and (lookup(tok)[0] or _pair(tok) or (affix in _GROUP_WORDS and pick_group(tok, affix))):
            return True
    return False


# a hyphen left hanging before one of these is a suspended compound ('sphalerite- and galena-bearing')
_SUSPENDED = {'and', 'or', 'nor', 'to', 'as'}


def classify(words):
    """[{i: [word indices], kind: 'species'|'spell'|'group', token, how, keys | suggest | gid}] for one
    page's words (each [x0, y0, x1, y1, text], in reading order). A name broken across a line is read
    whole and both boxes are marked: split inside the word ('tobermo-' / 'rite'), at the name's own
    hyphen ('crichtonite-' / 'group', 'åsgruvanite-' / '(Ce)'), or before a suspended compound
    ('sphalerite- and galena-bearing'); so are a two-word name ('native copper') and a name with the
    'group' after it ('crichtonite group', 'crichtonite–group'). `keys`/`suggest` are normalised names:
    `card` them; `gid` is a group: `group_card` it."""
    recs, byname = _index()[0], _group_index()['byname']
    out = []
    n = len(words)
    skip = set()
    for i, w in enumerate(words):
        if i in skip:
            continue
        text = w[4]
        idxs = [i]
        if text.endswith('-') and i + 1 < n:                # a hyphen at the line end
            nt = words[i + 1][4]
            joined = _clean(text[:-1] + nt)
            if joined and (lookup(joined)[0] or joined in byname):
                text, idxs = text[:-1] + nt, [i, i + 1]      # a name split inside the word
                skip.add(i + 1)
            elif _names_in(text + nt):
                text, idxs = text + nt, [i, i + 1]           # the name's own hyphen
                skip.add(i + 1)
            elif nt.strip(_EDGE).lower() in _SUSPENDED:
                text = text[:-1]                             # 'sphalerite- and …': the name alone
        parts = _SPLIT.split(text)
        done = set()
        for pi, part in enumerate(parts):
            if pi in done:
                continue
            tok, affix = _clean_affix(part)
            if not tok:
                continue
            last = pi == len(parts) - 1
            nxt_i = idxs[-1] + 1 if last and part[-1:].isalpha() and idxs[-1] + 1 < n else None
            nxt_word = _clean(words[nxt_i][4]) if nxt_i is not None else ''
            # a two-word species ('native copper', 'baumhauerite II')
            if nxt_word and (tok + ' ' + nxt_word) in recs:
                skip.add(nxt_i)
                out.append({'i': idxs + [nxt_i], 'kind': 'species', 'token': tok + ' ' + nxt_word, 'how': 'exact',
                            'keys': [tok + ' ' + nxt_word]})
                continue
            # '<name>-group', '<name>–group' (the next part of this word) or '<name> group' (the next word,
            # no punctuation between): the GROUP, not the species it is named after
            nxt, extra = '', []
            if not affix:
                if not last and parts[pi + 1].strip(_EDGE).lower() in _GROUP_WORDS:
                    nxt = parts[pi + 1].strip(_EDGE).lower()
                elif nxt_i is not None and words[nxt_i][4].strip(_EDGE).lower() in _GROUP_WORDS:
                    nxt, extra = words[nxt_i][4].strip(_EDGE).lower(), [nxt_i]
            gword = affix if affix in _GROUP_WORDS else nxt
            gid = pick_group(tok, gword) if gword else None
            if gid:
                if nxt and not extra:
                    done.add(pi + 1)
                skip.update(extra)
                out.append({'i': idxs + extra, 'kind': 'group', 'token': tok, 'gid': gid})
                continue
            how, hit = lookup(tok)
            if how:
                if tok in _PROSE_SPECIES and not part.strip(_EDGE)[:1].isupper():
                    continue
                out.append({'i': idxs, 'kind': 'species', 'token': tok, 'how': how, 'keys': hit})
                continue
            gid = (pick_group(tok) or pick_group(_squash(tok))) if tok not in _PROSE_GROUPS else None
            if gid:                                         # a bare group name: 'tourmaline', 'garnet'
                out.append({'i': idxs, 'kind': 'group', 'token': tok, 'gid': gid})
                continue
            pair = _pair(tok)
            if pair:                                        # a series written with a hyphen: 'bismuthinite-aikinite'
                for x in pair:
                    how, hit = lookup(x)
                    out.append({'i': idxs, 'kind': 'species', 'token': x, 'how': how, 'keys': hit})
                continue
            sug = suggest(tok)
            if sug:
                out.append({'i': idxs, 'kind': 'spell', 'token': tok, 'suggest': sug})
    return out


def card(key):
    """What the name layer's popup shows for one species (a normalised name), from the local snapshot
    only: name, IMA formula (Mindat's <sub>/<sup> markup — the page sanitises it), elements, group,
    Strunz code, IMA status, cell and type locality. None for an unknown key."""
    r = _index()[0].get(key)
    if not r:
        return None
    m = mindat.lookup(r.get('name', '')) or {}
    gid = r.get('groupid') or m.get('groupid')
    group = ((mindat._db() or {}).get('groups', {}).get(str(gid)) or {}).get('name', '') if gid else ''
    cell = [r.get(k) or 0 for k in ('a', 'b', 'c', 'al', 'be', 'ga')]
    return {'name': r.get('name', ''), 'formula': html.unescape(r.get('formula') or ''),
            'elements': r.get('elements') or [], 'group': group, 'strunz': m.get('strunz', ''),
            'status': ', '.join(m.get('ima_status') or []), 'cell': cell if any(cell) else [],
            'locality': r.get('tl', '')}


# a group listed in full on its hover card; a larger one is listed in the Mindat pane
SMALL_GROUP = 12


def group_card(gid):
    """A group for the name layer: name, the groups above it, its size, and its members by (sub)group —
    [{name, members: [{name, formula}]}], the group's own members first. None for an unknown id."""
    gi = _group_index()
    g = gi['groups'].get(str(gid))
    if not g:
        return None
    recs = _index()[0]
    chain, p, seen = [], g.get('parent'), set()
    while p and p in gi['groups'] and p not in seen:
        seen.add(p)
        chain.append(gi['groups'][p].get('name', ''))
        p = gi['groups'][p].get('parent')
    sections = []
    for d in _descendants(str(gid)):
        mem = sorted(gi['members'].get(d, []), key=lambda k: recs[k].get('name', '').lower())
        if mem:
            sections.append({'name': gi['groups'][d].get('name', ''),
                             'members': [{'name': recs[k].get('name', ''),
                                          'formula': html.unescape(recs[k].get('formula') or '')} for k in mem]})
    return {'id': str(gid), 'name': g.get('name', ''), 'strunz': g.get('strunz', ''), 'above': chain,
            'n': sum(len(s['members']) for s in sections), 'sections': sections}


def page(words):
    """{hits: classify(words), species: {key: card}, groups: {gid: group_card}} — every card the page's
    hits refer to."""
    hits = classify(words)
    keys = {k for h in hits for k in (h.get('keys') or h.get('suggest') or [])}
    gids = {h['gid'] for h in hits if h['kind'] == 'group'}
    return {'hits': hits, 'species': {k: card(k) for k in sorted(keys)},
            'groups': {g: group_card(g) for g in sorted(gids)}}
