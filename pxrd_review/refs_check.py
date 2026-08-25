#!/usr/bin/env python3
"""
refs_check — cross-check a manuscript's in-text citations against its own reference list.

    python3 -m pxrd_review.refs_check <manuscript.docx | paper.pdf | folder> [--no-annotate] [--out DIR]
    pxrd refs <manuscript.docx>

Both directions are reported:
  * CITED BUT NOT LISTED   — a citation in the body text with no entry in the reference list
                             (shown with the same surname's entries, if any: "[list has: Schoep (1923)]")
  * LISTED BUT NOT CITED   — a reference-list entry the body text never cites
  * MISMATCH               — an orphan citation and an uncited entry that are probably the same
                             reference (same surname, different year; or same year, surname
                             spelt differently), listed as a pair so a typo is told apart from a
                             genuinely missing reference.
  * FORM                   — a citation that found its entry but disagrees with it in form: the
                             year's letter ('Cooper et al. 2019' vs a '2019a' entry), the author
                             form ('Zhao 2024' for a five-author entry: 'Zhao et al.'; 'A and B'
                             for three authors), or an entry written without initials.

Styles handled: author–year in every common form — "Smith (2019)", "Smith and Jones (2019)",
"Smith et al., 2019a,b", "(Smith 2019; Jones and Brown, 2020)", "Smith, Jones and Brown (2019)",
"in press" — and bracketed numeric citations ("[3]", "[4–7, 12]", numeric superscripts) against a
numbered list. Everything outside the reference list counts as body text: tables, figure captions,
footnotes/endnotes and an appendix included, since a citation there still needs an entry.

A .docx is read as Word shows it with all changes accepted (tracked insertions count, deletions do
not). For a .docx the tool also writes an annotated COPY, <dir>/review_out/<name>_refs.docx: every
orphan citation and uncited entry gets a yellow highlight and a Word comment. The source file is
never modified. A .pdf gets the console/text report only. Tables or captions kept in a separate
file are folded in with --with FILE (repeatable): their citations count as body text.

Design notes (same discipline as the entry checks):
  * A citation is only recognised in a citation-shaped position: "Name (year)", "Name et al. year",
    or "Name, year" inside parentheses/brackets. A bare "Word 2019" in prose ("December 2024",
    "IMA 2024-012", "SHELXL-2016") is not a citation and is never reported.
  * All-capitals tokens ("IMA", "USGS", "NIST") are matched when the list has such an entry and
    silently ignored otherwise — corporate authors and acronyms look alike.
  * Surnames are compared after Unicode folding (Balić-Žunić == Balic-Zunic == BalićŽunić), so
    a diacritic never produces a finding; a real spelling difference is reported as a MISMATCH
    pair, not as two unrelated findings.
"""
import os, re, sys, glob, copy, argparse, unicodedata, difflib
from collections import namedtuple

from pxrd_review import errors as E

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
MC_FALLBACK = '{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback'
XML_SPACE = '{http://www.w3.org/XML/1998/namespace}space'

Para = namedtuple('Para', 'idx text elem where')          # elem: lxml w:p (docx body) or None
Entry = namedtuple('Entry', 'idx text names year suffix number para start end nauth', defaults=(None,))
# nauth: the author count when the entry's author block parsed as a proper list of
# 'Surname, I.' authors; None when it did not (no initials, a corporate author, '———').
Cite = namedtuple('Cite', 'names etal year suffix who raw para start end soft alts')
# alts: folded multi-word forms of a name ('Rigaku Oxford Diffraction' -> rigakuoxforddiffraction,
# oxforddiffraction) tried against the joined leading names of an entry.
# soft: a citation-shaped string that is ALSO something else in prose (an acronym, a software
# or company name, 'the Meritorious (1981) award') — counted when the list has it, silently
# dropped otherwise, so it never produces a finding on its own.

# ----------------------------------------------------------------------------- text loading

def _run_text(r):
    """Visible text of one w:r. A numeric superscript run ('12', '3–5') is made visible as
    '[12]' so a superscript-numbered citation style can be checked like a bracketed one."""
    out = []
    for c in r:
        if c.tag == W + 't':
            out.append(c.text or '')
        elif c.tag in (W + 'br', W + 'cr'):
            out.append('\n')
        elif c.tag == W + 'tab':
            out.append(' ')
        elif c.tag in (W + 'noBreakHyphen', W + 'softHyphen'):
            out.append('-' if c.tag == W + 'noBreakHyphen' else '')
    s = ''.join(out)
    rpr = r.find(W + 'rPr')
    if rpr is not None and s.strip():
        va = rpr.find(W + 'vertAlign')
        if (va is not None and va.get(W + 'val') == 'superscript'
                and re.fullmatch(r'[\d,\s–—\-]+', s) and re.search(r'\d', s)):
            s = '[%s]' % s.strip()
    return s

_SKIP = {W + 'del', W + 'moveFrom', MC_FALLBACK, W + 'rPr', W + 'pPr', W + 'commentRangeStart',
         W + 'commentRangeEnd', W + 'footnoteReference', W + 'endnoteReference'}

def _para_pieces(p):
    """[(w:r element, its text)] in document order, tracked changes accepted (w:ins kept,
    w:del dropped). Runs are the unit the annotator later highlights / comments on."""
    pieces = []
    def walk(el):
        for c in el:
            if c.tag in _SKIP:
                continue
            if c.tag == W + 'r':
                pieces.append((c, _run_text(c)))
            else:
                walk(c)
    walk(p)
    return pieces

MC_ALT = '{http://schemas.openxmlformats.org/markup-compatibility/2006}AlternateContent'

def _in_fallback(p):
    """Inside a text box (mc:AlternateContent, Choice or Fallback): skipped, so paragraph indexes
    match the GUI's docx renderer, which does not render text boxes either."""
    return any(a.tag in (MC_FALLBACK, MC_ALT) for a in p.iterancestors())

def load_docx(path):
    """(python-docx Document, [Para]) — body paragraphs (tables included, in document order)
    followed by footnote/endnote paragraphs (report-only: their runs live in another part)."""
    from docx import Document
    from lxml import etree
    doc = Document(path)
    paras = []
    for p in doc.element.body.iter(W + 'p'):
        if _in_fallback(p):
            continue                        # the legacy twin of a text box: same text twice
        text = ''.join(t for _, t in _para_pieces(p))
        paras.append(Para(len(paras), text, p, 'body'))
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False,
                             dtd_validation=False, huge_tree=False)
    for part in doc.part.package.iter_parts():
        name = str(part.partname)
        if name not in ('/word/footnotes.xml', '/word/endnotes.xml'):
            continue
        try:
            root = etree.fromstring(part.blob, parser)
        except Exception:
            continue
        where = 'footnote' if 'footnotes' in name else 'endnote'
        for p in root.iter(W + 'p'):
            text = ''.join(t for _, t in _para_pieces(p))
            if text.strip():
                paras.append(Para(len(paras), text, None, where))
    return doc, paras

def load_pdf(path):
    """[Para] shaped like a docx: one body Para (all text before the reference heading, lines
    joined so a citation wrapped across lines still reads), the heading, one Para per reference
    entry, and a 'tail' Para for whatever follows the list (captions, supplement). A PDF has no
    paragraphs of its own — text comes back line by line — so the list is split here, from the
    lines, rather than by the paragraph rules the docx path uses."""
    from pxrd_review.cell_lambda_check import pdf_text
    raw = pdf_text(path) or ''
    raw = re.sub('[\u02c6\u02c7\u02d8\u02d9\u02da\u02db\u02dc\u02dd\u00b4\u00a8\u00b8]', '', raw)  # 'Petˇríˇcek'
    raw = re.sub('[\u0300-\u036f]', '', raw)                          # 'Bač ́ık': a stranded accent
    raw = re.sub(r'(\w)-[ \t]*\n[ \t]*(?=[a-z])', r'\1', raw)     # re-join "diffrac-\ntometer"
    raw = re.sub(r'(\w)-[ \t]*\n[ \t]*(?=[A-Z])', r'\1-', raw)    # keep "Frank-\nKamenetskaya"
    lines = [ln.strip() for ln in raw.split('\n')]
    def is_head(t):
        if re.fullmatch(r'(?:[A-Za-z]\s){4,}[A-Za-z]', t):
            t = t.replace(' ', '')                          # 'R E F E R E N C E S'
        return bool(HEADING.match(t))
    head = None
    for i, ln in enumerate(lines):
        if is_head(ln) and any(ENTRY_START.match(l) for l in lines[i + 1:i + 8] if l):
            head = i
    if head is None:
        return [Para(0, ' '.join(l for l in lines if l), None, 'body')]
    tail = None; n = 0
    for j in range(head + 1, len(lines)):
        t = lines[j]
        if ENTRY_START.match(t):
            n += 1
        elif n >= 3 and len(t) < 60 and LIST_END.match(t):
            tail = j; break
    paras = [Para(0, ' '.join(l for l in lines[:head] if l), None, 'body'),
             Para(1, 'References', None, 'body')]
    for chunk in split_reference_block('\n'.join(lines[head + 1:tail])):
        paras.append(Para(len(paras), chunk, None, 'body'))
    if tail is not None:
        paras.append(Para(len(paras), ' '.join(l for l in lines[tail:] if l), None, 'tail'))
    return paras

# ----------------------------------------------------------------------------- name handling

def _fold(s):
    """Unicode-fold a surname for comparison: strip accents, case, hyphens, apostrophes, spaces."""
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().translate(_LETTERS)               # ø, ł, ı, đ, ß, æ, œ: no NFKD decomposition
    return re.sub(r'[^a-z]', '', s)

_LETTERS = str.maketrans({'ø': 'o', 'ł': 'l', 'ı': 'i', 'đ': 'd', 'ß': 'ss', 'æ': 'ae', 'œ': 'oe',
                          'þ': 'th', 'ð': 'd', 'ħ': 'h', 'ŧ': 't'})
PARTICLES = {'van', 'von', 'de', 'der', 'den', 'del', 'della', 'di', 'da', 'du', 'dos', 'das',
             'la', 'le', 'ten', 'ter', 'op', 'af', 'av', 'zu', 'el', 'bin', 'ibn', 'st', 'saint'}
_NOT_A_NAME = {'et', 'al', 'and', 'eds', 'ed', 'jr', 'sr', 'ii', 'iii', 'iv', 'in', 'editor',
               'editors', 'the', 'of', 'others', 'anon'}
_WORD = re.compile(r"[^\W\d_][\w'’\-]*")

def surnames(author_block, limit=12):
    """Folded surnames from a reference entry's author block, in order. Initials ('A.', 'AR')
    are skipped; lowercase particles are glued to the name that follows (van der Waals →
    'vanderwaals'); a hyphenated or apostrophe name folds to one token."""
    names, buf = [], []
    # 'G.Yu.', 'Ya.A.': a transliterated digraph initial is followed by its period; the surname
    # Yu never is ('Yu, X.'), so the period is what tells them apart
    author_block = re.sub(r"\b(?:Shch|Yu|Ya|Ye|Yo|Zh|Kh|Ts|Ch|Sh|Th|Ph|Dj|Dz)\.", '', author_block)
    words = [m.group(0).strip("'’-") for m in _WORD.finditer(author_block)]
    words = [w for w in words if w]
    def is_initials(w):
        return len(w.rstrip('.')) <= 3 and w.rstrip('.').isupper()
    for i, w in enumerate(words):
        low = w.lower().rstrip('.')
        nxt = words[i + 1] if i + 1 < len(words) else ''
        if low in PARTICLES and nxt and nxt.lower() not in _NOT_A_NAME and (
                nxt.lower() in PARTICLES or (nxt[0].isupper() and not is_initials(nxt))):
            buf.append(low); continue           # 'van der' Waals / 'Van' Gosen / 'Le' Bail
        if low in _NOT_A_NAME:
            buf = []; continue
        if not w[0].isupper():
            buf = []; continue
        if is_initials(w) or len(w) == 1:
            continue                            # initials: 'A', 'AR', 'JRC'
        names.append(_fold(''.join(buf) + w)); buf = []
        if len(names) >= limit:
            break
    return names

# ----------------------------------------------------------------------------- the reference list

_YEAR = r'(?:1[5-9]\d{2}|20\d{2})'
YEAR_TOKEN = re.compile(r'(?<![\d\-–/])\(?(' + _YEAR + r')([a-h])?\)?(?![\d\-–/])')
PAREN_YEAR = re.compile(r'\(\s*(' + _YEAR + r')([a-h])?\s*\)')
IN_PRESS = re.compile(r'\b(?:in\s+press|in\s+review|forthcoming|submitted|accepted|no\s+date|n\.d\.)\b', re.I)
HEADING = re.compile(r'^\s*(?:\d+\.?\s*)?(references?(?:\s+cited|\s+and\s+notes)?|literature\s+cited|'
                     r'bibliography|works\s+cited|reference\s+list|sources)\s*:?\s*$', re.I)
# Where a reference entry's author block starts: 'Kampf, A.R.', 'Kampf AR', 'Van Cappellen, P.',
# '[3] Kampf', '3. Kampf' — a surname followed by initials. A journal name ('American Mineralogist,
# 108') has no initials and never matches; 'YAO ET AL.' (a running header) is excluded outright.
_PARTS = (r"(?:\b(?:[Vv]an|[Vv]on|[Dd]e|[Dd]er|[Dd]en|[Dd]el|[Dd]ella|[Dd]i|[Dd]a|[Dd]u|[Dd]os|[Dd]as|"
          r"[Ll]a|[Ll]e|[Tt]en|[Tt]er|[Ee]l|d'|D'|Mac|Mc|O'|St\.?)\s?)*")
ENTRY_START = re.compile(_PARTS + r"[A-ZÀ-ÞĀ-ſ][^\W\d_]+(?:[-'’][^\W\d_]+)*"
                         r"(?:,\s*|\s+)(?:[A-Z]\.|(?!ET\b|AND\b|AL\b|IMA\b|USA\b|UK\b|Ed\b|Eds\b)[A-Z]{1,3}(?![A-Za-z0-9]))")   # 'Acta A71': a volume, not an initial
NUMBERED_LINE = re.compile(r'^\s*(?:\[(\d+)\]|(\d+)[.)])(?:\s+|$)')
# An entry's author block as a grammar: 'Kampf, A.R.' | 'Kampf AR' | 'A.R. Kampf' | 'J.-P. Smith',
# joined by ',' / ';' / 'and' / '&' / a space, optionally closed by 'et al.'. It stops at the first
# token that is not an author, so a Vancouver-style entry (year at the end) yields the authors
# alone and not the title — the count is what the FORM check relies on.
_UP = r"[A-ZÀ-ÖØ-ÞĀĂĄĆĈĊČĎĐĒĔĖĘĚĜĞĠĢĤĦĨĪĬĮİĴĶĹĻĽĿŁŃŅŇŌŎŐŒŔŖŘŚŜŞŠŢŤŦŨŪŬŮŰŲŴŶŸŹŻŽ]"
# one surname: 'Kampf', 'O’Keeffe', 'García-Rodríguez', 'Sen Gupta', 'van der Waals'
_ACORE = _PARTS + r"[A-ZÀ-ÞĀ-ſ](?:[^\W\d_]|['’\-](?=[^\W\d_]))+(?:\s[A-ZÀ-ÞĀ-ſ][^\W\d_]+(?=(?:,\s*|\s+)" + _UP + r"))?"
# initials: 'A.', 'A.R.', 'A. R.', 'J.-M.', 'T.J.B', 'Yu.S.', 'É.', 'AR', 'AA.'
_LET = r"(?:Shch|Yu|Ya|Ye|Yo|Zh|Kh|Ts|Ch|Sh|Th|Ph|Dj|Dz|" + _UP + r")"
# a trailing initial may lack its period ('T.J.B and') but must not be the first letter of the
# next surname ('H.A. Wu')
_INIT_DOT = _LET + r"\.(?:\s?-?" + _LET + r"(?:\.|(?![^\W\d_])))*"
_INIT_CAPS = _UP + r"{1,3}\.?(?![A-Za-z0-9])"
_INIT = r"(?:" + _INIT_DOT + r"|" + _INIT_CAPS + r")"
# 'Curienite, A new mineral' (a Vancouver title) is not 'Surname, Initial': a bare single capital
# after the comma must not be followed by a lowercase word
_INIT_AFTER_COMMA = r"(?:" + _INIT_DOT + r"|" + _INIT_CAPS + r"(?!\s+[a-z]))"
_AUTHOR = (r"(?:" + _ACORE + r"(?:,\s*" + _INIT_AFTER_COMMA + r"|\s+" + _INIT + r")(?:,?\s*(?:Jr|Sr|II|III)\.?)?|"
           + _INIT + r"\s+" + _ACORE + r")")
_SEP = r"(?:\s*[,;]\s*(?:and\s+|&\s*)?|\s+(?:and|&)\s+|\s+)"
AUTHOR_LIST = re.compile(r"^\s*(?:\[\d+\]|\d+[.)])?\s*(" + _AUTHOR + r"(?:" + _SEP + _AUTHOR + r")*"
                         r"(?:,?\s*et\s+al\.?)?)")
DASHES = re.compile(r'[—–\-_]{2,}')

def _author_boundary(gap):
    """Offset in `gap` (the text between one entry's year and the next's) where the next entry's
    author block begins: the FIRST surname+initials that follows a sentence/DOI/page boundary
    (a leading '12.' / '[12]' numbering token is kept with the entry), or a '———' standing for
    the previous entry's authors. None when no such start exists (the two years belong to one
    entry). Never the gap start itself: the text right after a year is the entry's own title."""
    for m in ENTRY_START.finditer(gap):
        before = gap[:m.start()]
        if not before.strip():
            continue
        num = re.search(r'(?:^|(?<=\s))(?:\[\d{1,3}\]|\d{1,3}[.)])\s+$', before)
        if num:                             # '… 3–8. 12. Kampf' — '12.' is the entry's number,
            head = before[:num.start()]     # '8.' (no space before it) is a page
            if not head.strip() or re.search(r'[.;:)\d]\s*$', head):
                return num.start()
            continue
        if not re.search(r'[.;:)\d]\s+$', before):
            continue                                            # mid-author-list: 'A.R., Adams'
        if re.search(r'\b[Ii]n:?\s+(?:[A-Z]\.\s*)*$', before):
            continue                                            # 'In: Smith, J. (Ed.)' — an editor
        if re.match(r'.{0,120}?\((?:[Ee]ds?|[Ee]ditors?)\.?\)', gap[m.start():]):
            continue
        return m.start()
    d = DASHES.search(gap)
    if d and d.start() > 0 and re.search(r'[.;:)\d]\s+$', gap[:d.start()]):
        return d.start()
    return None

def split_reference_block(text):
    """Split a block of reference text — a PDF section, or a docx paragraph holding several
    entries — into entries. Three strategies, in order of reliability:
      1. a numbered list: split where a line starts with the NEXT number in sequence;
      2. year-anchored: each entry carries one publication year, so the boundary between two
         entries lies between consecutive years, at the first author-block start after a
         sentence/DOI/page-number boundary (robust to two-column PDFs, wrapped lines, and
         journal names that look like surnames);
      3. line-based: a line that opens like an author block once the running entry has a year."""
    lines = [ln.strip() for ln in text.split('\n') if ln.strip()]
    if not lines:
        return []
    # 1. numbered sequence
    nums = [(i, int(next(g for g in m.groups() if g))) for i, ln in enumerate(lines)
            for m in [NUMBERED_LINE.match(ln)] if m]
    if len(nums) >= 3:
        starts, expect = [], nums[0][1]
        for i, n in nums:
            if n == expect:
                starts.append(i); expect += 1
        if len(starts) >= 3:
            starts = [0] + [i for i in starts if i > 0]
            return [' '.join(lines[a:b]) for a, b in zip(starts, starts[1:] + [len(lines)])]
    # 2. year-anchored
    flat = ' '.join(lines)
    years = list(PAREN_YEAR.finditer(flat))
    if len(years) < 3:
        years = list(YEAR_TOKEN.finditer(flat))
    if len(years) >= 2:
        starts = [0]
        for prev, cur in zip(years, years[1:]):
            gap = flat[prev.end():cur.start()]
            pos = _author_boundary(gap)
            if pos is not None:
                starts.append(prev.end() + pos)
        if len(starts) >= 2:
            return [flat[a:b].strip() for a, b in zip(starts, starts[1:] + [len(flat)])]
    # 3. line-based
    out, cur = [], []
    for ln in lines:
        if cur and ENTRY_START.match(ln) and (YEAR_TOKEN.search(' '.join(cur)) or IN_PRESS.search(' '.join(cur))):
            out.append(' '.join(cur)); cur = [ln]
        else:
            cur.append(ln)
    if cur:
        out.append(' '.join(cur))
    return out
LIST_END = re.compile(r'^\s*(?:\d+\.?\s*)?(figure\s+captions?|figures?|tables?|table\s+\d|appendix|'
                      r'appendices|supplement(?:ary|al)?|supporting|acknowledg|author\s+contributions?|'
                      r'conflicts?\s+of\s+interest|data\s+availability|funding|highlights|'
                      r'graphical\s+abstract)\b', re.I)
NUMBERING = re.compile(r'^\s*(?:\[(\d+)\]|(\d+)\s*[.)]|(\d+)\s+(?=[A-Z]))\s*')

def _entry_like(text):
    t = text.strip()
    if len(t) < 25:
        return False
    if not (YEAR_TOKEN.search(t) or IN_PRESS.search(t)):
        return False
    return bool(re.search(r"\b[A-Z]\.|,|\bet al\b", t))

def _looks_like_heading(text):
    t = text.strip()
    return bool(t) and len(t) < 80 and not YEAR_TOKEN.search(t) and not t.endswith('.') \
        and not _entry_like(t)

def find_reference_list(paras):
    """(heading_index or None, first_entry_index, end_index_exclusive, note).
    The LAST 'References'-style heading followed by entry-like paragraphs wins; without a
    heading, the longest trailing run (>= 5) of entry-like paragraphs is used."""
    nonblank = [p for p in paras if p.text.strip()]
    heads = [p for p in nonblank if HEADING.match(p.text) and p.where == 'body']
    for h in reversed(heads):
        after = [p for p in nonblank if p.idx > h.idx][:6]
        if sum(_entry_like(p.text) for p in after) >= 2:
            start = h.idx + 1
            end = _list_end(paras, start)
            if end > start:
                return h.idx, start, end, ''
    # no usable heading: longest run of entry-like paragraphs
    best = (0, None, None); run_start = None; n = 0
    for p in paras:
        if not p.text.strip():
            continue
        if _entry_like(p.text) and p.where == 'body':
            if run_start is None:
                run_start = p.idx; n = 0
            n += 1
            if n > best[0]:
                best = (n, run_start, p.idx + 1)
        else:
            run_start = None; n = 0
    if best[0] >= 5:
        return None, best[1], best[2], 'no "References" heading found — using the run of %d entry-like paragraphs' % best[0]
    return None, None, None, 'no reference list found'

def _list_end(paras, start):
    """Walk forward from the first entry until a heading-like paragraph closes the list."""
    seen = numbered = 0
    for p in paras[start:]:
        t = p.text.strip()
        if not t or p.where != 'body':
            if p.where != 'body':
                return p.idx
            continue
        if seen >= 3 and numbered >= seen - 1 and not NUMBERING.match(t) and not _entry_like(t):
            return p.idx                    # a numbered list ends where the numbering stops
        if _entry_like(t) or (seen and YEAR_TOKEN.search(t)):
            seen += 1; numbered += bool(NUMBERING.match(t)); continue
        if seen and (LIST_END.match(t) or _looks_like_heading(t)):
            return p.idx
        if seen and len(t) < 25:
            continue                        # a stray short line inside the list
        if seen:
            seen += 1; continue             # long, no year: an old-style entry or a wrapped one
        return p.idx
    return len(paras)

def _find_loose(text, head, pos):
    """Offset of `head` in `text` from `pos`, tolerating whitespace/newline differences."""
    pat = r'\s+'.join(re.escape(w) for w in head.split())
    m = re.compile(pat).search(text, pos)
    return m.start() if m else -1

_DIGRAPH_INIT = re.compile(r"\b(?:Shch|Yu|Ya|Ye|Yo|Zh|Kh|Ts|Ch|Sh|Th|Ph|Dj|Dz)\.")

def _grammar_surnames(block):
    """One folded surname per author the grammar matched: 'Sen Gupta PK' -> 'sengupta',
    'van der Waals, J.D.' -> 'vanderwaals', 'Coveney, R.M. Jr.' -> 'coveney'."""
    out = []
    for m in re.finditer(_AUTHOR, block):
        words = [w for w in _WORD.findall(_DIGRAPH_INIT.sub('', m.group(0)))
                 if not (len(w.rstrip('.')) <= 3 and w.rstrip('.').isupper()) and w.lower().rstrip('.') not in _NOT_A_NAME
                 and len(w) > 1]
        if words:
            out.append(_fold(''.join(words)))
    return out

def _cut_non_authors(block):
    """Truncate an author list at a 'co-author' that is really a program or a company:
    'Sheldrick, G.M. SHELXL-2019' / 'Dolivo-Dobrovolsky D.V., MINAL' — an all-capitals token of
    4+ letters when the first author is not written in capitals, or a name on the soft list."""
    first_caps = None
    for m in re.finditer(_AUTHOR, block):
        w = next((x for x in _WORD.findall(m.group(0)) if len(x.rstrip('.')) > 3 or not x.rstrip('.').isupper()), '')
        caps = w.isupper() and len(w) >= 4
        if first_caps is None:
            first_caps = caps; continue
        if (caps and not first_caps) or _fold(w) in _SOFT:
            return block[:m.start()]
    return block

def parse_entry(text, idx, para, start, end):
    t = text.strip()
    number = None
    m = NUMBERING.match(t)
    if m:
        number = int(next(g for g in m.groups() if g)); t = t[m.end():]
    year = suffix = None
    m = PAREN_YEAR.search(t)
    if m:
        year, suffix, ypos = m.group(1), m.group(2), m.start()
    else:
        m = YEAR_TOKEN.search(t)
        if m:
            year, suffix, ypos = m.group(1), m.group(2), m.start()
        else:
            m = IN_PRESS.search(t)
            year, ypos = ('in press', m.start()) if m else (None, min(len(t), 250))
    m = AUTHOR_LIST.match(t)
    if m and (ypos == 0 or m.end() <= ypos + 2 or ypos == min(len(t), 250)):
        block = _cut_non_authors(m.group(1))   # a proper author list: names AND a reliable count
        names = _grammar_surnames(block)
        nauth = max(len(names), 3) if re.search(r'\bet\s+al\b', block) else len(names)
        return Entry(idx, t, names, year, suffix, number, para, start, end, nauth)
    block = t[:ypos] if ypos > 3 else t
    if len(block) > 300:                    # year at the very end (Vancouver): the author block
        block = block[:300]                 # is the head of the entry; the rest is the title
    return Entry(idx, t, surnames(block), year, suffix, number, para, start, end, None)

def collect_entries(paras, start, end):
    entries = []
    def add(text, para, s, e_):
        if len(text.strip()) < 25 and not NUMBERING.match(text):
            return                              # a stray short line, not an entry
        en = parse_entry(text, len(entries), para, s, e_)
        if re.match(r'\s*[—–\-_]{2,}', en.text) and entries:
            en = en._replace(names=entries[-1].names)   # '———' = same author(s) as above
        if en.names or en.number is not None:
            entries.append(en)
    for p in paras[start:end]:
        if not p.text.strip() or p.where != 'body':
            continue
        if '\n' in p.text.strip() or len(PAREN_YEAR.findall(p.text)) >= 3:
            # several entries in one paragraph (soft line breaks, or a pasted block)
            pos = 0
            for chunk in split_reference_block(p.text):
                head = re.sub(r'\s+', ' ', chunk)[:40]
                s = _find_loose(p.text, head, pos)
                e_ = s + len(chunk) if s >= 0 else pos
                add(chunk, p.idx, max(s, 0), min(max(e_, s + 1), len(p.text)))
                pos = max(e_, pos)
        else:
            add(p.text, p.idx, 0, len(p.text))
    return entries

# ----------------------------------------------------------------------------- citations in the body

_NAME = _PARTS + r"[A-ZÀ-ÞĀ-ſ][^\W\d_]*(?:[-'’][^\W\d_]+)*"
# 'Smith', 'Smith and Jones', 'Smith, Jones and Brown' (a comma list only with a closing 'and'),
# each optionally 'et al.'
_AUTH = (r"(?P<auth>" + _NAME + r"(?:(?:\s*,\s*" + _NAME + r")*\s*,?\s*(?:and|&)\s*" + _NAME + r")?"
         r"(?P<etal>\s+et\s+al\.?)?)")
_YR = r"(?:" + _YEAR + r"[a-h]?|in\s+press)"
_YEARS = r"(?P<years>" + _YR + r"(?:(?:\s*,\s*|\s+and\s+|\s*&\s*)(?:" + _YR + r"|[a-h]\b))*)"
_AFTER = r"(?![\w\-–/])"          # 'IMA 2024-012', 'Xxx2026_data', page ranges: not a year
# "Smith (2019)", "Smith and Jones (2019a, b)", "Smith et al. (2019, 2020)"
NARRATIVE = re.compile(_AUTH + r"\s*\(\s*" + _YEARS + r"\s*\)" + _AFTER)
# "Smith et al. 2019" / "Smith et al., 2019" without parentheses (only with et al.)
NARRATIVE_ETAL = re.compile(_AUTH.replace('(?P<etal>\\s+et\\s+al\\.?)?', '(?P<etal>\\s+et\\s+al\\.?)')
                            + r"(?:\s*,\s*|\s+)" + _YEARS + _AFTER)
# inside a parenthetical chunk: "Smith 2019", "Smith, 2019", "Smith et al., 2019a,b"
IN_PAREN = re.compile(_AUTH + r"(?:\s*,\s*|\s+)" + _YEARS + _AFTER)
PAREN_NUM = re.compile(r'\(\s*([1-9]\d{0,2}(?:\s*[–—\-]\s*[1-9]\d{0,2})?(?:\s*,\s*[1-9]\d{0,2}(?:\s*[–—\-]\s*[1-9]\d{0,2})?)*)\s*\)')
URLISH = re.compile(r'https?:|www\.|doi|\.org|\.com|\.html?', re.I)
ARTICLE_BEFORE = re.compile(r'\b(?:the|a|an|The|A|An)\s+$')
PAREN_GROUP = re.compile(r'\(([^()]*)\)|\[([^\[\]]*)\]')
BRACKET_NUM = re.compile(r'\[\s*(\d+(?:\s*[–—\-]\s*\d+)?(?:\s*,\s*\d+(?:\s*[–—\-]\s*\d+)?)*)\s*\]')

# Never a citing author when it precedes a year: months, prose, journal/agency words, software.
_STOP = set(_fold(w) for w in """
January February March April May June July August September October November December
Jan Feb Mar Apr Jun Jul Aug Sep Sept Oct Nov Dec
In See Since From Recently Earlier Later Before After Until During Between Around About At On By
To For With Than Then When Table Tables Fig Figs Figure Figures Eq Eqs Equation Section Sect Chapter
Vol Volume No Nr Number Issue Part Version Series Ed Eds Edition Page Pages
Ca Circa Early Late Mid Summer Winter Spring Autumn Fall Year Years
Sample Samples Specimen Specimens Type Holotype Cotype Neotype Proposal Proposals Accepted Received
Revised Published Approved Discredited Redefined Renamed
Pers Comm Personal Communication Unpublished Data This Study Work Paper Present Ibid Copyright
Photo Photograph Image Trip Collected Found Discovered However Although Whereas Because
""".split())
# Software, instrument and company names: a real list sometimes cites them ('Bruker (2009)'), so
# they are SOFT — matched when the list has them, ignored otherwise.
_SOFT = set(_fold(w) for w in """
University Universität Université Università Museum Institute Laboratory Company Inc Ltd GmbH Co
Corporation Survey Diffraction Mineral Minerals Mineralogy Mineralogist Mineralogical Petrology
Geology Geological Chemistry Chemical Physics Physical Crystallography Science Sciences Research
Letters Acta Review Reviews Society Association Journal Magazine Bulletin Proceedings Abstracts
Abstract Program Programme Report Reports Newsletter Handbook Encyclopedia Dictionary Glossary
Atlas Lexicon Compendium Canadian American European Russian Chinese Agilent Oxford Stoe Nonius Enraf
SHELXL SHELXS SHELXT SHELX SHELXLE Jana Jana2006 Jana2020 Olex Olex2 WinGX PLATON FullProf GSAS GSASII
TOPAS VESTA Diamond ATOMS Mercury CCDC CRYSTALS Match HighScore PANalytical Malvern Bruker Rigaku
APEX SAINT SADABS TWINABS CrysAlis CrysAlisPro EXPO DICVOL checkCIF publCIF PowderCell FindIt ICSD
ICDD COD AMCSD Mindat RRUFF Origin Excel Matlab Python SPSS Mathematica ImageJ CrystalMaker
SingleCrystal Xtaldraw CELREF UnitCell TREOR McMaille Refine Structure Avaspec Hyperion JASCO
Horiba Renishaw Thermo Nicolet Perkin PerkinElmer Spectrum LabSpec Wire Omnic Opus Spectragryph
Fityk Peakfit PDF Unitcell Powder Powdercell ISODISTORT Bilbao FINDSYM VASP CASTEP Quantum Espresso
Gaussian Materials Studio CrystalExplorer Superflip Charge Flipping
""".split())

def _years_of(s):
    """'2019a, b, 2020' -> [('2019','a'), ('2019','b'), ('2020',None)]; 'in press' -> [('in press',None)]"""
    out, last = [], None
    for tok in re.split(r'\s*,\s*|\s+and\s+|\s*&\s*', s.strip()):
        tok = tok.strip()
        if not tok:
            continue
        if re.fullmatch(r'in\s+press', tok, re.I):
            out.append(('in press', None)); continue
        m = re.fullmatch(r'(' + _YEAR + r')([a-h])?', tok)
        if m:
            last = m.group(1); out.append((last, m.group(2)))
        elif re.fullmatch(r'[a-h]', tok) and last:
            out.append((last, tok))
    return out

def _cite_names(auth):
    """The cited surnames, folded: 'Smith, Jones and Brown' -> [smith, jones, brown]."""
    a = re.sub(r'\s+et\s+al\.?$', '', auth.strip())
    parts = re.split(r'\s*,\s*|\s+(?:and|&)\s+', a)
    return [_fold(p) for p in parts if p.strip()]

def _mk_cites(m, para, offset, out, seen_spans, narrative=False):
    auth = m.group('auth'); etal = bool(m.group('etal'))
    words = re.split(r'\s*,\s*|\s+(?:and|&)\s+', re.sub(r'\s+et\s+al\.?$', '', auth.strip()))
    words = [re.sub(r"[’']s$", '', w.strip()) for w in words if w.strip()]     # "Barton's (1980)"
    while words and _fold(words[0]) in _STOP:
        words.pop(0)                                # 'However, Graeser and Roggiani (1976)'
    if not words:
        return
    names = [_fold(w) for w in words]
    span = (para.idx, offset + m.start(), offset + m.end())
    if span in seen_spans:
        return
    seen_spans.add(span)
    first = words[0].split()[0]
    before = para.text[:offset + m.start()]
    after = para.text[offset + m.end():]
    alts = []
    lead = re.search(r"((?:[A-ZÀ-ÞĀ-ſ][^\W\d_'’\-]*\s+){1,3})$", before) if narrative and len(names) == 1 else None
    # 'Sen Gupta et al. (1992)': a two-word surname reads as 'Gupta' with a leading word
    if lead:                                        # 'Rigaku Oxford Diffraction (2022)'
        lw = lead.group(1).split()
        alts = [_fold(''.join(lw[i:]) + words[0]) for i in range(len(lw))]
    soft = (names[0] in _SOFT
            or (first.isupper() and len(first) <= 8)                     # IMA, USGS, NIST
            or bool(lead)
            or (narrative and len(names) == 1 and not etal              # 'the Meritorious (1981)',
                and (bool(ARTICLE_BEFORE.search(before))                 # '… (1994) Service Awards'
                     or bool(re.match(r'\s+[A-Z]', after)))))
    who = (', '.join(words[:-1]) + ' and ' + words[-1]) if len(words) > 1 else words[0]
    who = re.sub(r'\s+', ' ', who) + (' et al.' if etal else '')
    for year, suffix in _years_of(m.group('years')):
        out.append(Cite(names, etal, year, suffix, who, m.group(0).strip(), para.idx, span[1], span[2], soft, alts))

def find_citations(paras):
    """All author–year citations in the body paragraphs."""
    out, seen = [], set()
    for p in paras:
        text = p.text
        if not text.strip():
            continue
        for m in NARRATIVE.finditer(text):
            _mk_cites(m, p, 0, out, seen, narrative=True)
        for m in NARRATIVE_ETAL.finditer(text):
            _mk_cites(m, p, 0, out, seen)
        for g in PAREN_GROUP.finditer(text):
            inner = g.group(1) if g.group(1) is not None else g.group(2)
            if not (re.search(_YEAR, inner) or IN_PRESS.search(inner)) or URLISH.search(inner):
                continue
            base = g.start() + 1
            pos = 0
            for chunk in inner.split(';'):
                for m in IN_PAREN.finditer(chunk):
                    _mk_cites(m, p, base + pos, out, seen)
                pos += len(chunk) + 1
    return out

def find_numeric_citations(paras, parens=False):
    """[(numbers, para idx, start, end)] for '[3]', '[4–7, 12]' (and numeric superscripts);
    with parens=True also the Science-style '(1–3)', '(4, 5)'."""
    out = []
    for p in paras:
        for m in (PAREN_NUM if parens else BRACKET_NUM).finditer(p.text):
            if re.fullmatch(r'[01]{3}', m.group(1).strip()):
                continue                    # '[100]', '[001]': a crystallographic direction
            nums = []
            for tok in re.split(r'\s*,\s*', m.group(1)):
                r = re.split(r'\s*[–—\-]\s*', tok)
                if len(r) == 2 and r[0].isdigit() and r[1].isdigit():
                    a, b = int(r[0]), int(r[1])
                    if 0 < b - a < 50:
                        nums.extend(range(a, b + 1)); continue
                if tok.strip().isdigit():
                    nums.append(int(tok))
            if nums:
                out.append((nums, p.idx, m.start(), m.end()))
    return out

# ----------------------------------------------------------------------------- matching

def _close(a, b):
    """Two folded surnames that are probably the same name misspelt."""
    if not a or not b:
        return False
    if a == b or a.startswith(b) or b.startswith(a):
        return len(a) >= 3 and len(b) >= 3
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.8 and abs(len(a) - len(b)) <= 2

def _years_near(a, b, window=3):
    try:
        return abs(int(a) - int(b)) <= window
    except (TypeError, ValueError):
        return False

def _joined(e):
    """The entry's leading names joined ('rigaku', 'rigakuoxford', 'rigakuoxforddiffraction')."""
    return {''.join(e.names[:k]) for k in range(1, min(4, len(e.names)) + 1)}

def _pairable(c, e):
    """Score (higher = likelier) that orphan citation c and entry e are the same reference
    with a slip in the year or the spelling; None when they are not."""
    if not e.names:
        return None
    if c.etal and len(e.names) < 2:
        return None                         # 'X et al.' is never a single-author entry
    same_name = e.names[0] == c.names[0]
    if same_name and e.year != c.year:
        if _years_near(c.year, e.year) and all(n in e.names for n in c.names[1:]):
            return 2
        return None
    if e.year == c.year and not same_name and _close(e.names[0], c.names[0]):
        return 3
    return None

def _year_ok(c, e):
    if c.year == e.year:
        return not (c.suffix and e.suffix and c.suffix != e.suffix)
    return False

def match_author_year(cites, entries):
    """-> (orphans, uncited, pairs, matched). An entry is 'used' by any exactly matching
    citation; `matched` maps id(cite) -> (entries, names actually matched) for the form check."""
    used = set(); orphans = []; matched = {}
    def find(names):
        first = names[0]
        cands = [e for e in entries if e.names and _year_ok(c, e)
                 and (e.names[0] == first or any(a in _joined(e) for a in c.alts))]
        if len(names) >= 2:
            strict = [e for e in cands if all(n in e.names for n in names[1:])]
            if strict:
                cands = strict
            elif cands and not any(len(e.names) >= 2 for e in cands):
                pass                        # the list truncates authors; accept the first-author match
            else:
                cands = []
        return cands
    for c in cites:
        names = c.names
        cands = find(names)
        # 'PGMs, Godel and Barnes (2008)': a comma list may have swallowed a preceding noun —
        # retry without the leading name(s) before calling it an orphan
        k = 1
        while not cands and len(c.names) - k >= 2:
            names = c.names[k:]; cands = find(names); k += 1
        if cands:
            used.update(e.idx for e in cands); matched[id(c)] = (cands, names); continue
        orphans.append(c)
    uncited = [e for e in entries if e.idx not in used]
    # near-miss pairing: the same first surname (co-authors agreeing) within a few years, or the
    # same year with the surname spelt differently. Uncited entries are tried first; a USED entry
    # can still pair ("cited 2018 here, 2019 elsewhere; the list says 2019").
    pairs = []; paired_c = set(); paired_e = set()
    for c in orphans:
        best = None
        for pool, penalty in ((uncited, 0), ([e for e in entries if e.idx in used], 1)):
            for e in pool:
                score = _pairable(c, e)
                if score is not None and (best is None or score - penalty > best[0]):
                    best = (score - penalty, e)
            if best:
                break
        if best:
            pairs.append((c, best[1])); paired_c.add(id(c))
            if best[1].idx not in used:
                paired_e.add(best[1].idx)
    orphans = [c for c in orphans if id(c) not in paired_c]
    uncited = [e for e in uncited if e.idx not in paired_e]
    seen = set(); unique = []
    for c, e in pairs:                      # one line per (citation, entry), not per occurrence
        k = (c.names[0], c.year, c.suffix, e.idx)
        if k not in seen:
            seen.add(k); unique.append((c, e))
    return orphans, uncited, unique, matched

def match_numeric(ncites, entries):
    nums = {e.number if e.number is not None else i + 1: e for i, e in enumerate(entries)}
    cited = set()
    orphans = []
    for numbers, para, s, e_ in ncites:
        for n in numbers:
            cited.add(n)
            if n not in nums:
                orphans.append((n, para, s, e_))
    uncited = [e for n, e in sorted(nums.items()) if n not in cited]
    return orphans, uncited

# ----------------------------------------------------------------------------- form: citation vs its entry
# A citation that FOUND its entry can still disagree with it in form. These are the corrections a
# reviewer writes most often, and they are certain once the match is: the entry is right there.
Form = namedtuple('Form', 'kind cite entry msg')       # kind: suffix | authors | initials

_INITIALS = re.compile(r"\b[A-Z]\.|(?<![A-Za-z])[A-Z]{1,3}(?![A-Za-z0-9.])")

def _entry_has_initials(e):
    return e.nauth is not None

def _cite_form(c, names):
    if c.etal:
        return 'et al.'
    return {1: 'single', 2: 'two'}.get(len(names), 'list')

def _expected_form(n):
    return 'single' if n == 1 else 'two' if n == 2 else 'et al.'

def _form_hint(c, e, names):
    """'Zhao et al. (2024)' — how the citation should read for this entry."""
    first = c.who.split(' et al')[0].split(' and ')[0].split(',')[0].strip()
    yr = e.year + (e.suffix or '')
    n = e.nauth or len(e.names)
    if n == 1:
        return '%s (%s)' % (first, yr)
    if n == 2:
        second = _entry_second_name(e)
        return '%s and %s (%s)' % (first, second, yr) if second else '%s and … (%s)' % (first, yr)
    return '%s et al. (%s)' % (first, yr)

def _entry_second_name(e):
    """The second author's surname as written in the entry (for the 'A and B' hint)."""
    block = e.text[:max(e.text.find(e.year), 0)] if e.year and e.year in e.text else e.text[:120]
    words = [m.group(0) for m in _WORD.finditer(block)]
    hits = [w for w in words if _fold(w) == e.names[1]] if len(e.names) > 1 else []
    return hits[0] if hits else ''

def form_findings(cites, entries, matched):
    out = []; seen = set()
    for c in cites:
        if id(c) not in matched:
            continue
        ents, names = matched[id(c)]
        if len(ents) != 1:
            continue                                # ambiguous match: leave it
        e = ents[0]
        key = (names[0], c.year, c.suffix, e.idx)
        if key in seen:
            continue
        seen.add(key)
        # 1. the year's letter: cited 2019, listed 2019a (or the reverse)
        if (c.suffix or '') != (e.suffix or ''):
            twins = [x for x in entries if x.names and x.names[0] == e.names[0] and x.year == e.year]
            if len(twins) > 1 and not c.suffix:
                out.append(Form('suffix', c, e, 'the list has %d %s (%s) entries (%s) — the citation '
                                'needs the letter' % (len(twins), c.who.split(' et al')[0], e.year,
                                                       ', '.join(e.year + (x.suffix or '') for x in twins))))
            else:
                out.append(Form('suffix', c, e, 'cited as %s, listed as %s — make them agree (a letter '
                                'is only needed when the list has two %s %s entries)'
                                % (c.year + (c.suffix or ''), e.year + (e.suffix or ''),
                                   c.who.split(' et al')[0].split(' and ')[0], e.year)))
        # 2. author-count form: 1 author -> 'A'; 2 -> 'A and B'; 3+ -> 'A et al.'
        if e.nauth and e.names:
            have, want = _cite_form(c, names), _expected_form(e.nauth)
            if have != want and have != 'list':
                out.append(Form('authors', c, e, 'the entry has %d author%s — cite it as %s'
                                % (e.nauth, '' if e.nauth == 1 else 's', _form_hint(c, e, names))))
    # 3. an entry with no initials at all, when the list writes initials elsewhere
    with_initials = {e.names[0] for e in entries if e.names and _entry_has_initials(e)}
    for e in entries:
        if not e.names or e.year is None or _entry_has_initials(e) or re.match(r'\s*[—–\-_]{2,}', e.text):
            continue
        block = e.text[:e.text.find(e.year)] if e.year in e.text else ''
        words = [w for w in _WORD.findall(block) if w.lower() not in _NOT_A_NAME]
        if not (1 <= len(words) <= 3) or any(_fold(w) in _SOFT for w in words):
            continue                                # a corporate author, or not an author block
        if e.names[0] in with_initials or len(words) == 1:
            out.append(Form('initials', None, e, 'the entry has no initials%s'
                            % (' (the list writes %s with initials elsewhere)' % words[0]
                               if e.names[0] in with_initials else '')))
    return out

# ----------------------------------------------------------------------------- driver

def _fmt_cite(c):
    return '%s (%s)' % (c.who, c.year + (c.suffix or ''))

def _group_orphans(orphans):
    """[(cite, count)] — one line per distinct citation, first occurrence, with its count."""
    seen = {}
    for c in orphans:
        k = (c.names[0], c.year, c.suffix)
        if k in seen:
            seen[k][1] += 1
        else:
            seen[k] = [c, 1]
    return list(seen.values())

def _list_has(c, entries, n=3):
    """'list has: Schoep (1923), Schoep (1935)' — the same surname's entries, for an orphan."""
    same = sorted({(e.year or '?') + (e.suffix or '') for e in entries
                   if e.names and e.names[0] == c.names[0]})
    if not same:
        return ''
    shown = ', '.join('%s (%s)' % (c.who.split(' et al')[0].split(' and ')[0].split(',')[0], y)
                      for y in same[:n])
    return '   [list has: %s%s]' % (shown, ', …' if len(same) > n else '')

def _fmt_entry(e, n=110):
    t = re.sub(r'\s+', ' ', e.text)
    return (t[:n] + '…') if len(t) > n else t

def _ctx(paras, c, width=70):
    t = paras[c.para].text
    a, b = max(0, c.start - width // 2), min(len(t), c.end + width // 2)
    s = re.sub(r'\s+', ' ', t[a:b])
    return ('…' if a else '') + s + ('…' if b < len(t) else '')

def analyze(paras):
    """The whole check on a paragraph list. Returns a dict the report and annotator consume."""
    res = {'heading': None, 'list': None, 'note': '', 'style': None, 'entries': [],
           'cites': [], 'orphans': [], 'uncited': [], 'pairs': [], 'form': [], 'n_cites': 0, 'ncites': []}
    h, start, end, note = find_reference_list(paras)
    res['note'] = note
    if start is None:
        return res
    res['heading'] = h; res['list'] = (start, end)
    entries = collect_entries(paras, start, end)
    res['entries'] = entries
    body = [p for p in paras if not (start <= p.idx < end) and p.idx != h]
    cites = find_citations(body)
    ncites = find_numeric_citations(body)
    numbered = entries and sum(e.number is not None for e in entries) >= 0.7 * len(entries)
    n_num = sum(len(n) for n, *_ in ncites)
    hard = [c for c in cites if not c.soft]
    if numbered and len(hard) < 3:
        # Science-style '(1–3)' alongside/instead of brackets: only numbers the list actually
        # has can be citations, and only in a manuscript with no author–year citations
        top = max(e.number or 0 for e in entries) + 2
        spans = {(pi, a, b) for _, pi, a, b in ncites}
        ncites = ncites + [(n, pi, a, b) for n, pi, a, b in find_numeric_citations(body, parens=True)
                           if all(x <= top for x in n) and (pi, a, b) not in spans]
        n_num = sum(len(n) for n, *_ in ncites)
    if numbered and n_num >= 3 and n_num >= len(hard):
        res['style'] = 'numeric'; res['ncites'] = ncites; res['n_cites'] = n_num
        o, u = match_numeric(ncites, entries)
        res['orphans'], res['uncited'] = o, u
    else:
        res['style'] = 'author-year'; res['cites'] = cites; res['n_cites'] = len(cites)
        # soft citations (acronyms, software names, 'the X (1981)') count only when the list has them
        firsts = set().union(*[_joined(e) for e in entries if e.names]) if entries else set()
        cites = [c for c in cites if not (c.soft and c.names[0] not in firsts
                                          and not any(a in firsts for a in c.alts))]
        res['cites'] = cites; res['n_cites'] = len(cites)
        o, u, pr, matched = match_author_year(cites, entries)
        res['orphans'], res['uncited'], res['pairs'] = o, u, pr
        res['form'] = form_findings(cites, entries, matched)
    return res

def report(path, paras, res):
    L = []
    name = os.path.basename(path)
    L.append('Reference check — %s' % name)
    if res['list'] is None:
        L.append('  %s — nothing to check.' % (res['note'] or 'no reference list found'))
        return '\n'.join(L)
    s, e = res['list']
    head = ('heading "%s" at ¶%d' % (paras[res['heading']].text.strip(), res['heading'] + 1)
            if res['heading'] is not None else res['note'])
    L.append('  reference list: %d entries (%s; ¶%d–%d); citation style: %s'
             % (len(res['entries']), head, s + 1, e, res['style']))
    if res['style'] == 'numeric':
        L.append('  in-text citations: %d numbers cited' % res['n_cites'])
        o, u = res['orphans'], res['uncited']
        L.append('')
        L.append('CITED BUT NOT LISTED (%d)' % len(o))
        for n, para, a, b in o:
            L.append('  [%d]   ¶%-4d %s' % (n, para + 1, re.sub(r'\s+', ' ', paras[para].text[max(0, a - 35):b + 35])))
        L.append('')
        L.append('LISTED BUT NOT CITED (%d)' % len(u))
        for en in u:
            L.append('  #%-3s %s' % (en.number if en.number is not None else '?', _fmt_entry(en)))
        return '\n'.join(L)
    distinct = {(c.names[0], c.year, c.suffix) for c in res['cites']}
    L.append('  in-text citations: %d (%d distinct)' % (res['n_cites'], len(distinct)))
    o, u, pr = res['orphans'], res['uncited'], res['pairs']
    L.append('')
    grouped = _group_orphans(o)
    L.append('CITED BUT NOT LISTED (%d)' % len(grouped) if len(grouped) == len(o) else
             'CITED BUT NOT LISTED (%d distinct, %d occurrences)' % (len(grouped), len(o)))
    for c, n in grouped:
        L.append('  %-34s ¶%-4d %s%s' % (_fmt_cite(c)[:34] + (' ×%d' % n if n > 1 else ''), c.para + 1,
                                        _ctx(paras, c), _list_has(c, res['entries'])))
    L.append('')
    L.append('LISTED BUT NOT CITED (%d)' % len(u))
    for en in u:
        L.append('  ¶%-4d %s' % (en.para + 1, _fmt_entry(en)))
    L.append('')
    L.append('MISMATCH — probably the same reference; year or spelling differs (%d)' % len(pr))
    for c, en in pr:
        L.append('  cited  %-30s ¶%-4d %s' % (_fmt_cite(c)[:30], c.para + 1, _ctx(paras, c, 50)))
        L.append('  listed ¶%-4d %s' % (en.para + 1, _fmt_entry(en, 100)))
    fm = res.get('form', [])
    L.append('')
    L.append('FORM — the citation and its entry disagree (%d)' % len(fm))
    for f in fm:
        if f.cite is not None:
            L.append('  %-34s ¶%-4d %s' % (_fmt_cite(f.cite)[:34], f.cite.para + 1, f.msg))
        else:
            L.append('  ¶%-4d %s: %s' % (f.entry.para + 1, f.msg, _fmt_entry(f.entry, 80)))
    if not (o or u or pr or fm):
        L.append('')
        L.append('  Every citation has an entry, every entry is cited, and their forms agree.')
    return '\n'.join(L)

# ----------------------------------------------------------------------------- keys + JSON (for the GUI)

def finding_key(kind, obj, entry=None):
    """A content-stable key for a finding, so a reviewer's verdict survives reruns and edits
    elsewhere in the document: orphan:<surname>:<year>, uncited:<entry head>, pair:<surname>:<year>,
    form:<kind>:<surname>:<year> / form:initials:<entry head>."""
    def head(e):
        return re.sub(r'\s+', ' ', e.text)[:50]
    if kind == 'orphan':
        return 'orphan:%s:%s%s' % (obj.names[0], obj.year, obj.suffix or '')
    if kind == 'uncited':
        return 'uncited:%s' % head(obj)
    if kind == 'pair':
        return 'pair:%s:%s%s' % (obj.names[0], obj.year, obj.suffix or '')
    if kind == 'form':
        if obj.cite is not None:
            return 'form:%s:%s:%s%s' % (obj.kind, obj.cite.names[0], obj.cite.year, obj.cite.suffix or '')
        return 'form:%s:%s' % (obj.kind, head(obj.entry))
    return kind

def serialize(paras, res):
    """Plain dicts for the GUI: every finding with its key, label, message, paragraph index and
    character span (so the page can scroll to it), grouped the way the report groups them."""
    out = {'style': res['style'], 'note': res['note'], 'n_entries': len(res['entries']),
           'n_cites': res['n_cites'], 'list': list(res['list']) if res['list'] else None,
           'heading': res['heading'], 'findings': []}
    def add(kind, fkey, label, msg, para, start, end, extra=None):
        d = {'kind': kind, 'fkey': fkey, 'label': label, 'msg': msg, 'para': para,
             'start': start, 'end': end, 'text': re.sub(r'\s+', ' ', paras[para].text)[:160] if para is not None else ''}
        if extra:
            d.update(extra)
        out['findings'].append(d)
    if res['list'] is None:
        return out
    if res['style'] == 'numeric':
        for n, para, s, e in res['orphans']:
            add('orphan', 'orphan:%d' % n, '[%d]' % n, 'cited here but the reference list has no entry %d' % n, para, s, e)
        for en in res['uncited']:
            add('uncited', 'uncited:%d' % (en.number or 0), '#%s' % (en.number or '?'),
                'listed but never cited in the text', en.para, en.start, en.end, {'entry': _fmt_entry(en, 110)})
        return out
    for c, n in _group_orphans(res['orphans']):
        add('orphan', finding_key('orphan', c), _fmt_cite(c),
            'cited but not in the reference list' + (' (×%d)' % n if n > 1 else '') + _list_has(c, res['entries']),
            c.para, c.start, c.end, {'count': n})
    for en in res['uncited']:
        add('uncited', finding_key('uncited', en), _fmt_entry(en, 60), 'listed but never cited in the text',
            en.para, en.start, en.end, {'entry': _fmt_entry(en, 110)})
    for c, en in res['pairs']:
        add('pair', finding_key('pair', c), _fmt_cite(c),
            'probably the same reference as "%s" — the year or spelling differs' % _fmt_entry(en, 90),
            c.para, c.start, c.end, {'entry': _fmt_entry(en, 110), 'entry_para': en.para})
    for f in res.get('form', []):
        if f.cite is not None:
            add('form', finding_key('form', f), _fmt_cite(f.cite), f.msg, f.cite.para, f.cite.start, f.cite.end)
        else:
            add('form', finding_key('form', f), _fmt_entry(f.entry, 60), f.msg, f.entry.para, f.entry.start, f.entry.end,
                {'entry': _fmt_entry(f.entry, 110)})
    return out

# ----------------------------------------------------------------------------- docx annotation

def _set_text(t_el, s):
    t_el.text = s
    if s != s.strip():
        t_el.set(XML_SPACE, 'preserve')

def _split_run(r, t, a, b):
    """Split run r (text t) so that t[a:b] sits in its own run; returns the run holding the
    span. Only a plain single-w:t run is split; anything else is returned whole."""
    ts = r.findall(W + 't')
    if len(ts) != 1 or (ts[0].text or '') != t:
        return r, [(r, t)]
    parent = r.getparent()
    pieces = []
    if a > 0:
        before = copy.deepcopy(r); _set_text(before.find(W + 't'), t[:a])
        parent.insert(parent.index(r), before); pieces.append((before, t[:a]))
    _set_text(ts[0], t[a:b]); pieces.append((r, t[a:b]))
    if b < len(t):
        after = copy.deepcopy(r); _set_text(after.find(W + 't'), t[b:])
        parent.insert(parent.index(r) + 1, after); pieces.append((after, t[b:]))
    return r, pieces

def _runs_for_span(pieces, start, end):
    """Run elements covering [start, end) of the paragraph text; refines `pieces` in place."""
    out, pos, i = [], 0, 0
    while i < len(pieces):
        r, t = pieces[i]
        s0 = pos
        if not t or s0 + len(t) <= start or s0 >= end:
            pos += len(t); i += 1; continue
        a, b = max(start, s0) - s0, min(end, s0 + len(t)) - s0
        if a > 0 or b < len(t):
            mid, new = _split_run(r, t, a, b)
            pieces[i:i + 1] = new
            k = next(j for j, (el, _) in enumerate(new) if el is mid)
            out.append(mid)
            pos = s0 + sum(len(x) for _, x in new[:k + 1]); i += k + 1
        else:
            out.append(r); pos += len(t); i += 1
    return out

def _highlight_runs(runs):
    for r in runs:
        rpr = r.find(W + 'rPr')
        if rpr is None:
            rpr = r.makeelement(W + 'rPr', {}); r.insert(0, rpr)
        hl = rpr.find(W + 'highlight')
        if hl is None:
            hl = rpr.makeelement(W + 'highlight', {}); rpr.append(hl)
        hl.set(W + 'val', 'yellow')

def annotate_docx(doc, paras, res, out_path, triage=None):
    """Write the findings as highlights + comments into a COPY at out_path. Returns the count.
    `triage` (optional, from the GUI): {fkey: {'verdict': 'dismiss'|'confirm'|None, 'note': str}} —
    a dismissed finding is not written, a reviewer note is appended to the comment."""
    from pxrd_review.annotate_review import AUTHOR, INITIALS, _save_docx
    from docx.text.paragraph import Paragraph
    from docx.text.run import Run
    triage = triage or {}
    notes = {}                              # (para, start, end) -> [text]
    def add(para, s, e_, msg, fkey=None):
        t = triage.get(fkey) if fkey else None
        if t and t.get('verdict') == 'dismiss':
            return
        if t and t.get('note'):
            msg += ' — reviewer: %s' % t['note']
        notes.setdefault((para, s, e_), []).append(msg)
    if res['style'] == 'numeric':
        for n, para, s, e_ in res['orphans']:
            add(para, s, e_, 'Reference check: [%d] is cited here but the reference list has no entry %d.' % (n, n),
                'orphan:%d' % n)
        for en in res['uncited']:
            add(en.para, en.start, en.end, 'Reference check: entry %s is listed but never cited in the text.'
                % (en.number if en.number is not None else '?'), 'uncited:%d' % (en.number or 0))
    else:
        for c in res['orphans']:
            add(c.para, c.start, c.end, 'Reference check: %s is cited here but has no entry in the reference list.'
                % _fmt_cite(c), finding_key('orphan', c))
        for en in res['uncited']:
            add(en.para, en.start, en.end, 'Reference check: this entry is listed but never cited in the text.',
                finding_key('uncited', en))
        for c, en in res['pairs']:
            add(c.para, c.start, c.end, 'Reference check: cited as %s, but the reference list has "%s" — '
                'probably the same reference with the year or spelling differing; make them agree.'
                % (_fmt_cite(c), _fmt_entry(en, 90)), finding_key('pair', c))
            add(en.para, en.start, en.end, 'Reference check: listed as "%s", cited in the text as %s (¶%d) — '
                'the year or spelling differs.' % (_fmt_entry(en, 70), _fmt_cite(c), c.para + 1), finding_key('pair', c))
        for f in res.get('form', []):
            if f.cite is not None:
                add(f.cite.para, f.cite.start, f.cite.end, 'Reference check: %s.' % f.msg, finding_key('form', f))
            else:
                add(f.entry.para, f.entry.start, f.entry.end, 'Reference check: %s.' % f.msg, finding_key('form', f))
    pieces_by_para = {}
    n = 0
    for (pi, s, e_), msgs in sorted(notes.items()):
        p = paras[pi]
        if p.elem is None:
            continue                        # footnote/endnote: report only
        pieces = pieces_by_para.setdefault(pi, _para_pieces(p.elem))
        runs = _runs_for_span(pieces, s, e_)
        if not runs:
            continue
        _highlight_runs(runs)
        para = Paragraph(p.elem, doc._body)
        doc.add_comment([Run(r, para) for r in runs], text='\n'.join(dict.fromkeys(msgs)),
                        author=AUTHOR, initials=INITIALS)
        n += 1
    _save_docx(doc, out_path)
    return n

# ----------------------------------------------------------------------------- main

def _load(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == '.docx':
        return load_docx(path)
    if ext == '.pdf':
        return None, load_pdf(path)
    raise SystemExit('refs_check: not a .docx or .pdf: %s' % path)

def check_file(path, out_dir=None, annotate=True, force=False, quiet=False, companions=(), triage=None):
    """companions: extra .docx/.pdf (tables, captions, supplement) whose text counts as BODY —
    a citation there needs an entry in the manuscript's list too, and satisfies one.
    triage: {fkey: {'verdict', 'note'}} from the GUI — dismissed findings are not written."""
    doc, paras = _load(path)
    for extra in companions:
        _, more = _load(extra)
        tag = 'with:' + os.path.basename(extra)
        paras += [Para(len(paras) + i, p.text, None, tag) for i, p in enumerate(more)]
    res = analyze(paras)
    text = report(path, paras, res)
    if not quiet:
        print(text)
    out_dir = out_dir or os.path.join(os.path.dirname(os.path.abspath(path)), 'review_out')
    stem = os.path.splitext(os.path.basename(path))[0]
    if res['list'] is not None:
        os.makedirs(out_dir, exist_ok=True)
        rep = os.path.join(out_dir, stem + '_refs_report.txt')
        with open(rep, 'w', encoding='utf-8') as f:
            f.write(text + '\n')
        if not quiet:
            print('  report → %s' % rep)
    findings = bool(res['orphans'] or res['uncited'] or res['pairs'] or res.get('form'))
    if doc is not None and annotate and res['list'] is not None and findings:
        out_path = os.path.join(out_dir, stem + '_refs.docx')
        if os.path.exists(out_path) and not force:
            from pxrd_review.annotate_review import _has_foreign_comment, _has_tracked_changes
            if _has_foreign_comment(out_path) or _has_tracked_changes(out_path):
                print('  NOT overwriting %s — it carries someone\'s comments or tracked changes '
                      '(pass --force to replace it).' % out_path)
                return res
        n = annotate_docx(doc, paras, res, out_path, triage)
        if not quiet:
            print('  annotated copy (%d comments) → %s' % (n, out_path))
    return res

def main(argv=None):
    ap = argparse.ArgumentParser(prog='pxrd refs', description=__doc__.split('\n\n')[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('path', help='a manuscript .docx, a .pdf, or a folder of them')
    ap.add_argument('--out', help='output folder (default: <file dir>/review_out)')
    ap.add_argument('--no-annotate', action='store_true', help='report only; write no docx copy')
    ap.add_argument('--force', action='store_true', help='overwrite an output copy that carries comments/tracked changes')
    ap.add_argument('--with', dest='companions', action='append', default=[], metavar='FILE',
                    help='a companion .docx/.pdf (tables, figure captions, supplement) whose citations '
                         'count as body text; repeatable')
    a = ap.parse_args(argv)
    if os.path.isdir(a.path):
        files = sorted(f for f in glob.glob(os.path.join(a.path, '*'))
                       if f.lower().endswith(('.docx', '.pdf')) and not os.path.basename(f).startswith('~$'))
        if not files:
            raise SystemExit('refs_check: no .docx / .pdf in %s' % a.path)
    else:
        if not os.path.exists(a.path):
            raise SystemExit('refs_check: no such file: %s' % a.path)
        files = [a.path]
    for i, f in enumerate(files):
        if i:
            print()
        try:
            check_file(f, a.out, annotate=not a.no_annotate, force=a.force, companions=a.companions)
        except SystemExit:
            raise
        except Exception as exc:
            print('Reference check — %s\n  FAILED: %s' % (os.path.basename(f), E.explain(exc, f)))
    return 0

if __name__ == '__main__':
    sys.exit(main())
