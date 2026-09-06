"""The paper's tables through a layout model — docling (IBM, MIT), fully local — for the table
readers of paper_extract: every table on a page comes back with its cell structure (row and column
of each cell, the caption), which no word-position heuristic recovers on a two-column page, a
two-line header or a table without a header line the vocabulary knows.

    pxrd paper --pages docling …            pip install "pxrd-review[layout]"  (Python ≥ 3.10)

`pages(path)` gives the pdf as pages in the shape page_lines gives them: a page with tables becomes
the tables' grids (caption first, one line per row, cells at their column's x — the construction a
manuscript .docx already goes through), a page without one stays as fitz reads it; installed with
`paper_extract.set_pages_reader(pages)`. A pdf is converted once: the grids are cached under
.cache/layout by the file's sha1 and the docling version. Nothing here imports docling at module
level, so the package imports without it; `available()` says whether it is there."""
import os, re, json, time, hashlib

from pxrd_review import paths as P

_converter = None


def available():
    try:
        import docling.document_converter  # noqa: F401
        return True
    except Exception:
        return False


def version():
    try:
        from importlib.metadata import version as _v
        return _v('docling')
    except Exception:
        return '?'


def _conv():
    """One converter per process: table structure on (ACCURATE), no OCR (the corpus pdfs have a
    text layer; a scanned one would need it), models from DOCLING_ARTIFACTS_PATH when set."""
    global _converter
    if _converter is None:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
        opts = PdfPipelineOptions(do_table_structure=True, do_ocr=False)
        art = os.environ.get('DOCLING_ARTIFACTS_PATH')
        if art:
            opts.artifacts_path = art
        opts.table_structure_options.mode = TableFormerMode.ACCURATE
        _converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
    return _converter


def _cell_text(t):
    """A cell's text with the spaces the model puts around sub- and superscripts closed again:
    '(NH 4 ) 2 O*' -> '(NH4)2O*', 'Å 2' -> 'Å2', 'U eq' and 'h k l' left as they are."""
    t = ' '.join((t or '').split())
    t = re.sub(r'(?<=[A-Za-zÅ)\]])\s+(?=\d)', '', t)                   # a digit after a letter or a closing bracket: a subscript or a superscript
    t = re.sub(r'(?<=\d)\s+(?=[)\]])', '', t)                            # a bracket closing after a digit
    t = re.sub(r'(?<=[A-Za-z])\s+(?=[)\]])', '', t)
    t = re.sub(r'(?<=\d)\s+(?=[A-Z][a-z]?(?:\d|\*|[()\]]|$))', '', t)      # '…)2 O*' -> '…)2O*', 'Fe2 O3' -> 'Fe2O3': an element after a subscript
    return t

def grid_from_document(doc):
    """docling's tables -> {page_no (1-based): [(caption, rows)]}, rows = [[(column, text), …], …]
    with a merged cell placed once, at its first row and column."""
    out = {}
    for t in doc.tables:
        pr = t.prov[0] if getattr(t, 'prov', None) else None
        page = int(getattr(pr, 'page_no', 1) or 1)
        rows = {}
        for c in t.data.table_cells:
            txt = _cell_text(c.text)
            if not txt:
                continue
            rows.setdefault(c.start_row_offset_idx, {}).setdefault(c.start_col_offset_idx, txt)
        grid = [sorted(r.items()) for _, r in sorted(rows.items())]
        if not grid:
            continue
        try:
            cap = ' '.join((t.caption_text(doc) or '').split())
        except Exception:
            cap = ''
        out.setdefault(page, []).append((cap, grid))
    return out


def _cache_path(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    d = os.path.join(P.cache_dir(), 'layout')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, h.hexdigest() + '.json')


def tables_of(path):
    """The pdf's tables per page, converted once. -> ({page_no: [(caption, rows)]}, seconds)."""
    cp = _cache_path(path); ver = version()
    try:
        with open(cp, encoding='utf-8') as f:
            c = json.load(f)
        if c.get('docling') == ver:
            return {int(k): [(cap, [[(int(col), txt) for col, txt in row] for row in grid]) for cap, grid in v] for k, v in c['pages'].items()}, c.get('seconds', 0.0)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    t0 = time.time()
    res = _conv().convert(path, raises_on_error=False)
    tabs = grid_from_document(res.document) if getattr(res, 'document', None) is not None else {}
    secs = time.time() - t0
    try:
        with open(cp, 'w', encoding='utf-8') as f:
            json.dump({'docling': ver, 'seconds': secs, 'pages': {str(k): [[cap, [[[col, txt] for col, txt in row] for row in grid]] for cap, grid in v] for k, v in tabs.items()}}, f)
    except OSError:
        pass
    return tabs, secs


def assemble(tabs, n_pages, fitz_page):
    """The pages for the table readers: page i's tables stacked as one pseudo-page (three empty
    lines between tables end a table region), a page without one as fitz_page(i) gives it."""
    from pxrd_review import paper_extract as PE
    out = []
    for i in range(n_pages):
        pt = tabs.get(i + 1)
        if not pt:
            out.append(fitz_page(i)); continue
        lines = []; y = 70.0
        for cap, grid in pt:
            if lines:
                for _ in range(3):
                    lines.append(PE._empty_line(y)); y += 14.0
            block = PE._grid_lines(cap, grid, y0=y)
            lines += block; y = (block[-1]['y'] + 14.0) if block else y
        out.append(lines)
    return out


def pages(path):
    """The pdf as pages for the table readers (see the module docstring). A .docx is never routed
    here; a conversion that fails leaves the page to fitz."""
    import fitz
    from pxrd_review import paper_extract as PE
    try:
        tabs, _ = tables_of(path)
    except Exception:
        tabs = {}
    with fitz.open(path) as doc:
        fitz_pages = [None] * len(doc)
        def fitz_page(i):
            if fitz_pages[i] is None:
                fitz_pages[i] = PE.page_lines(doc[i])
            return fitz_pages[i]
        return assemble(tabs, len(doc), fitz_page)
