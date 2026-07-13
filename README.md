# PXRD review tool

Validates an ICDD pattern `.docx` (the transcription reviewed by a Task Group & ICDD) against its
sources — the paper `.pdf`, the author `.cif`, the ICDD `.dft`, and the Mindat API — and
flags the recurring problems a reviewer would otherwise comb the files for. It writes Word
comments + highlights into *copies* of each docx and never edits the source.

The core is a **cell + wavelength** comparison: the Author's Cell (a, b, c, α, β, γ, space
group, Z) and the radiation/wavelength vs the values reported in the `.pdf`. On top of that
it runs the two-dozen "extra checks" listed below — including **instrument geometry and
diffractometer/camera type** (Diffractometer / Film / Gandolfi / Calculated; and peak vs
integrated vs visually-estimated intensities), analysis counts, IMA number, name↔formula
consistency, Mindat classification/chemistry, cross-file cell/ESD agreement, and a light
reflection-indexing consistency pass.

## Install / Quick start (`pxrd`)
> **Reviewers (non-developers): see [INSTALL.md](INSTALL.md)** — step-by-step Windows
> install & upgrade instructions for the distributed bundle zip (wheel + checksum +
> instructions). This section is the developer quick start for a checkout.
```
pip install -e .                   # one-time: puts a global `pxrd` command on PATH
cd /path/to/entries && pxrd gui    # open the GUI for the folder you're standing in
pxrd gui "/path/to/entries"        # …or name the folder explicitly
pxrd gui                           # reopens the last folder, on a free port, in the browser
```
`pxrd` is a launcher so you don't type folder prefixes or ports. Sub-commands:
`gui`, `review` (write comments/highlights), `sweep` (corpus fire-rate/drift report),
`lambda`, `extras`, `candidates`, `check` (regression), `refresh` (rebuild Mindat cache),
`mindat` (Mindat passthrough). For a data sub-command the folder is
**resolved as**: an explicit argument, else the current directory when it holds entry
`.docx` files, else the folder **remembered per sub-command** (pass it once, omit
after). The GUI **auto-picks a free port**, and extra flags (`--id`, `--port`, …) pass
through. Without installing, run `./pxrd <sub>` from a checkout (the dev launcher), or
the explicit `python3 -m pxrd_review.<module>` forms shown below.

## Setup — step by step (fresh install)
Requirements: **Python ≥ 3.9** and `pip`. Unzip the archive, then work from inside the
`pxrd-review-tool` folder. Steps **1** and **5** are the minimum to use the tool; **2–4** add the
Mindat cross-checks and the verification pass.

**1 — Install.**
```
cd /path/to/pxrd-review-tool
pip install -e .
```
Installs the dependencies (**PyMuPDF**, **python-docx**, **Flask**) and puts the `pxrd` command on
your PATH. (Libraries only, without the command: `pip install -r requirements.txt`.)

**2 — Add your Mindat API key.** *Optional.* **A Mindat snapshot ships inside the package**
(`pxrd_review/data/*.json.gz`, refreshed at each release), so the classification / chemistry /
cell cross-checks work offline out of the box with **no key at all** — the header says
`[bundled with this release]` when that copy is doing the work. A key only buys **fresher** data:
with one, the tool auto-refreshes when the snapshot goes stale (Mindat adds species continuously,
and its data already lags the CNMNC newsletter). Get a key from your **mindat.org** account, then
use **either** a key file **or** an environment variable:

*Key file* (set once, persists across sessions — recommended):
```
echo "YOUR_MINDAT_TOKEN" > /path/to/pxrd-review-tool/.mindat_key
chmod 600 /path/to/pxrd-review-tool/.mindat_key      # keep the secret private
```

*Environment variable* (takes precedence over the file if both are set):
```
# macOS / Linux — current terminal only:
export MINDAT_API_KEY="YOUR_MINDAT_TOKEN"
# make it permanent: add that exact line to ~/.zshrc (macOS) or ~/.bashrc (Linux), then reopen the terminal

# Windows PowerShell — current session:
$env:MINDAT_API_KEY = "YOUR_MINDAT_TOKEN"
# make it permanent: setx MINDAT_API_KEY "YOUR_MINDAT_TOKEN"   (then reopen the terminal)
```

**3 — Refresh the Mindat cache** *(optional — only if you set a key in step 2)*:
```
pxrd refresh
```
Pulls the current IMA species/group list into a local cache, replacing the snapshot bundled with
the release. Without a key this step is unnecessary: the bundled snapshot already makes the tool
run fully offline. `python3 -m pxrd_review.mindat --status` reports what data is actually in use
and how old it is.

**4 — Verify the install** (optional; **Task Group reviewers only**):
```
pxrd check "/path/to/Part 1"
```
Runs the regression suite against the corrected reference batch — should report **all pass**. Point
it at the folder holding the entry `.docx` files; the exact folder name doesn't matter, and **keep
the quotes** if the path contains spaces.

That batch is ICDD review material and is **not public**, so this step only works if you already
have it. Everyone else: skip to step 5 — `pxrd --version` is enough to confirm the install.

**5 — Run the review GUI on a batch:**
```
pxrd gui "/path/to/entries"
```
Opens the review GUI in your browser — **localhost only**, auto-picks a free port.

**Notes**
- **PyMuPDF licensing:** PyMuPDF (the PDF engine) is **AGPL-3.0 or commercial** (Artifex) — the only
  non-permissive dependency. Local use is unencumbered, but **read `NOTICE` before redistributing the
  tool or hosting the GUI as a shared network service** (the rest of the project is MIT). Prebuilt
  wheels cover macOS/Linux/Windows, so no compiler is needed.
- **Where files land:** in an editable install, `.mindat_key` and `.cache/` sit at the repo root; if
  that folder is read-only, the tool falls back to `~/.pxrd_review/` (or set `$PXRD_REVIEW_HOME`).
- Without a key, the Mindat checks run off the **snapshot bundled in the package** (see step 2).
  If that snapshot is ever missing too, they are skipped cleanly — no errors, no false flags —
  and the header says so, because silently-skipped checks read exactly like a clean batch.

## Run
> **On Windows the command is `python`, not `python3`** (which usually does not exist there):
> `python -m pxrd_review.gui.review_gui "C:\path\to\entries"`. Reviewers should follow
> [INSTALL.md](INSTALL.md) rather than this section.

```
python3 -m pxrd_review.cell_lambda_check /path/to/entries          # console report, whole folder
python3 -m pxrd_review.cell_lambda_check /path/to/entries --id Innnnnn
python3 -m pxrd_review.sweep /path/to/corpus                       # read-only corpus report + diff vs last run
```
**Corpus sweep (`pxrd sweep`).** Read-only: runs `annotate_review.analyze()` over every
entry under a folder tree (recursive, deduped by id, skipping `review_out/`), and writes
`review_out/sweep_report.txt` (per-check fire table split old- vs new-template, cell/λ
verdict distributions, crashes) plus `review_out/sweep_snapshot.json`. Each run **diffs
against the previous snapshot** — which entries changed verdict, per-check count deltas,
new/resolved crashes — so an aggregate false-positive storm or regression is visible *before*
a reviewer hits it (the pointwise `regression_check` can't see aggregate drift). It is a
report, **not a gate**: the eyeball on the diff is the judgement. `--samples` adds one example
message per check; `--baseline OLD.json` diffs against a saved snapshot without overwriting
the auto one.

Auto-pairs each `Innnnnn(Name).docx` to its PDF in the folder (or a subfolder),
expanding range-named PDFs like `Innnnnn-Innnnnn.pdf`. Ids may be `I`- or
`O`-prefixed. When several PDFs share an id, the **primary article PDF is
preferred** over `_Supp`/`_TableS1` files (those often omit the cell or hold a
different phase's table) — pairing the wrong file was the main cause of
"no cell found" misses.

Dependencies: PyMuPDF (`fitz`). docx is parsed directly from `word/document.xml`.

## Writing the review into the .docx
`pxrd_review/annotate_review.py` runs the same comparison and writes the findings back into
each entry as **Word comments + yellow highlights**, so they appear
in context. It reports **errors only** — a clean entry gets no comment. Every
entry (clean or flagged) also gets an **"x" in the Accept box** unless its cell is
grossly wrong (see "Accept marking" and "Behavioral contract" below), so a clean
entry is opened + re-saved rather than byte-copied. Reruns **preserve hand-edited
outputs** (hand-made tracked changes / comments are kept; tool comments are refreshed).
```
python3 -m pxrd_review.annotate_review "/path/to/entries"             # -> <folder>/review_out (copies)
python3 -m pxrd_review.annotate_review "/path/to/entries" --id Innnnnn
python3 -m pxrd_review.annotate_review "/path/to/entries" --inplace   # edit the originals instead
```
Flagged entries are saved as **`<name>_edited.docx`** (the ones with a comment /
highlight), so they stand out at a glance in the `review_out/` listing; clean
entries keep the source name. (`--inplace` edits the originals and does not
rename.) A stale opposite-named twin from an earlier run is removed automatically
unless it was hand-edited, in which case it is kept and noted on the console.
What it writes:
- a comment on each flagged Author's-Cell value (value / significant-figures /
  esd mismatch), with that value highlighted;
- a comment on the Radiation cell for an anode hard-flag (only when the cell
  itself matched);
- a single brief **"No matching PDF cell found."** when no cell could be matched.

Comments are authored as **"PXRD Review Tool"** so they filter apart from human
reviewers'. Extra dependency: `python-docx` **≥1.2** (`Document.add_comment()` arrived in 1.2.0; with 1.1.x every flagged entry raises `AttributeError`, is swallowed per-entry, and the run 'succeeds' having written no findings at all).

## What it reads from the docx
Values reflect **accepted tracked changes**: tracked insertions are applied,
deletions dropped, and inter-run spaces removed (insertions split numbers
across runs). So it validates the *current* state of the entry.

## What it checks (in priority order)
1. **A matching cell exists** in the PDF (powder *or* single-crystal — both fine).
2. **Numbers match** — per-parameter value mismatch = likely transcription error
   (e.g. caught #mineral α=106.1 where the PDF says 106.0).
3. **Significant figures** — docx parameter quoted to more/fewer decimals than
   the PDF (e.g. c=7.08950 vs 7.0895).
4. **Error (esd) values** — the `(n)` uncertainty differs (only compared when
   both docx and PDF have one parsed).
5. **No exact match → "INVESTIGATE"** — noting the absence of an exact match
   is itself enough to trigger a look.

Whether a matched cell is from PXRD or SCXRD is **information, not a flag** —
using a single-crystal cell is acceptable for many entries — the reviewer decides
(it's usually stated explicitly in the PDF; note it as a comment like
"SCXRD cell" / "cell from SCXRD"). The tool surfaces existing
docx comments and, when a matched cell appears in a single-crystal context,
prints an ℹ note plus the PDF evidence snippet.

## How matching works (and why)
- Powder vs single-crystal cells of the same phase differ by only a few mÅ, so
  the tool ranks PDF cells by **closeness** (smallest Σ|Δ|) with a tight 0.004 Å
  tolerance — never "first within a loose window."
- Compares only parameters present in both; handles uniaxial cells where the PDF
  omits `b` (docx sets b = a). Symmetry-fixed angles (90, 120) are skipped.

## How cells are found in the PDF
The PDF is harvested several ways; all candidates are pooled and ranked by closeness.
1. **Inline narrative** — `a = 9.52(1), c = 9.19(2) Å`, the common case.
2. **Chained equality (uniaxial)** — `a = b = 5.1755(9) Å, c = 14.058(5) Å` and
   `a = b = c = 6.09(1) Å` (cubic). The plain inline grab fails here because a
   `=` is followed by `b`, not a number — so these powder cells in hexagonal/
   trigonal/tetragonal/cubic entries were being missed.
3. **Cubic/isometric** — when only `a` is quoted (`a = 6.0901(2) Å`), taken as
   `a = b = c` only when the text says cubic/isometric or the volume matches `a³`.
4. **Space-separated** — `a 23.90(1), b 11.00(1), c 17.05(1) Å` (no `=`), anchored
   on the trailing `Å` so prose like "a 5 mm bar" can't trigger it.
5. **Tables** — *vertical* label/value tables (`a (Å)` then `5.6751(5)`), and
   volume-anchored *grid* rows (`SG a b c V`, `0.55 ≤ V/(a·b·c) ≤ 1.03`).

### Multi-phase papers (one PDF, several minerals)
The hard case: a paper describing several minerals lists each phase's cell, and
the parser must expose **all** of them (and pick the right one), not just the
first. Two layouts are handled, each tagging the cell with its **phase name**:
- **Named grid rows** — `#mineral† P21 8.8593(2) 8.3846(5) 32.655(4) 97.801(8) …`
  (the 4th number is β, not V, so the volume-anchored grid parser skips it; this
  one keys on the *name + space-group* anchor).
- **Multi-column comparison tables** — one parameter per row, one phase per
  column: `a (Å) 8.8955 8.8848 8.9089 8.9245 | b (Å) … | c (Å) …` → one cell per
  column.
When several sibling cells are equally close, the entry's mineral name (from the
docx filename) breaks the tie via the cell's phase tag (`best_match(..., prefer_phase)`).
This took one review batch from 6 "investigate" down to 1 (the lone real
transcription error), fixing the five affected phases — all cases where the
matching cell was present but unparsed.

**Mojibake / extraction:** several journals extract `=` as `¼`, the ångström as
`A˚`, and split an esd off with a space (`8.8593 (2)`); the text is normalised
(`¼`→`=`, `A˚`→`Å`, `8.8593 (2)`→`8.8593(2)`) before parsing. The two multi-phase
parsers also collapse newlines, since PyMuPDF emits table cells one-per-line.

## Reliability
- **Reliable:** does the docx cell match a reported cell; per-parameter value /
  sig-fig / esd checks; "matches nothing — investigate"; anode identification;
  surfacing review comments. Across a 44-entry batch every entry
  now yields a parsed cell to compare — no "CHECK MANUALLY" fall-throughs —
  including all four extraction paths above.
- **Heuristic (info only, never a flag):** the powder-vs-single-crystal *label*
  uses keyword proximity, which can mislabel when a powder-refinement sentence
  references single-crystal seeding ("…refined…starting from…single-crystal
  techniques are a = …" describes the POWDER cell — e.g. 00-XXXXX
  #mineral). The printed evidence snippet supports confirmation.

## Extra checks (`pxrd_review/extra_checks.py`) — the recurring review comments this tool automates
Drawn from the reviewer's own past review notes, these are
the recurring notes the cell/λ comparator did **not** cover. They run
automatically at the end of every `pxrd_review/cell_lambda_check.py` report (and on the
no-PDF path, since several are docx-internal). They live in a separate module on
purpose: more heuristic, easy to tune or switch off per check as they are refined.

Each finding is graded **⚑ flag** (likely needs an edit/comment), **ℹ info**
(surface for the reviewer to confirm — often acceptable), or **· note** (low
confidence). The ten:

1. **geometry / camera method** — surfaces the specific named method in the PDF
   (Bragg-Brentano, Gandolfi, pseudo-Gandolfi / **crystal-rotation method**,
   Debye-Scherrer, Guinier, image plate, neutron TOF) when the docx `Spacing Instr.`
   is generic. Keyword must share a sentence with a diffraction term. Also names the
   **specific instrument** when recognised (Rigaku R-AXIS RAPID II, XtaLAB Synergy,
   SuperNova, MiniFlex, SmartLab; Bruker D8/APEX; STOE; PANalytical Empyrean) to help
   confirm the designators (ℹ info — the geometry goes in a comment, *not* into
   `Spacing Instr.`). When `Spacing/Intensity Instr.` is `Other`/blank and the PDF says
   the powder pattern was *collected on a* diffractometer — whether a recognised model
   in a powder sentence, **or just the bare word "diffractometer"** in a powder-
   collection sentence (the model is often named only once, then referenced
   anaphorically: "obtained using the same diffractometer", a pseudo-Gandolfi setup) —
   it FLAGs `Spacing/Intensity Instr. → Diffractometer`. Whole-word only, so the dual-
   use *micro*diffractometer (R-AXIS Rapid / D8 Discover) is left to the model path. The
   model patterns tolerate a .pdf line-break hyphenation (`R-\nAxis` → "R- Axis": the
   R-AXIS regex allows any hyphen/whitespace between 'r' and 'axis', `\b`-anchored).
2. **cell not powder-refined** — suppressed when the paper says the cell was
   refined from the **powder** data; otherwise a strong phrasing ("not refined",
   "from single-crystal data", "cell from SAED") fires only when its sentence is
   about the **cell** and not boilerplate (not a comparison / calc-pattern note /
   ADP-extinction / Dcalc density sentence). High precision, very low volume.
3. **group / structural classification** — **authoritative via Mindat**
   (`pxrd_review/mindat.py`): the mineral's `groupid` → group name, with the species'
   Nickel-Strunz code, cross-checked against the docx Strunz-mindat field.
   Falls back to the author's Structure/Isomorphism/Polymorphism comment and, only
   for species Mindat doesn't have (new/renamed), to specific PDF prose. PDF
   "isostructural with X" comparisons (which Mindat's groupid does not encode) are
   always surfaced. See the Mindat section below.
4. **PXRD calculated** — `Spacing/Intensity Instr. = Calculated` (a hard docx
   signal), or a PDF sentence pairing a powder term with "calculated from … the
   structure". (Plain "calculated" alone is ignored — too common.)
5. **wavelength** — docx λ vs the canonical Kα1/Kα/Kα2 for the stated anode;
   flags non-standard values and surfaces "Kα2 stripped" from the PDF.
6. **ideal vs empirical formula** — conservative: only when a natural mineral has
   a formula but an **empty Analysis field** (likely the ideal composition); a
   softer note when an analysis lacks an "average of N".
7. **synthetic vs natural** — name `-syn`/`synthetic` vs the SubFile class.
8. **precision / esd / symmetry** *(docx-internal, no PDF)* — symmetry-equal
   axes/angles must share value **and** esd; symmetry-fixed angles (90/120) must
   carry no esd; axes quoted to ≥3 decimals must have an esd. (Reproduces my
   own comments verbatim — e.g. "no error on the cell angles in the
   tetragonal setting", and an a/b esd mismatch.)
9. **hkl indexing** *(docx-internal, no PDF)* — recomputes d for each listed
   reflection from the stated cell via the general (triclinic) reciprocal metric
   and flags any indexed line off by >1 %. Catches transcription/indexing errors
   and doubled axes. Signed indices handled.
10. **IMA number** — flags only when the **PDF carries an IMA proposal id** (e.g.
    `IMA 20XX-XXX`) but the docx IMA Number field is blank, and prints the number
    to add (avoids false-flagging established minerals).

(Checks 11–15 add optical-sign, IMA-section, analysis-total/count, non-ambient
temperature, and strongest-line cross-checks.)

#### Reference title case (check 26)
The Primary Reference arrives **machine-Title-Cased** (`a New Mineral From the Burro
Mine` — it even wrecks acronyms: `USA` → `Usa`). ICDD style is **sentence case**:
ordinary words lowercase, proper nouns and acronyms kept. The direction is not a guess —
mining the 165 reviewer-corrected reference cells in the corpus found 53 case-only title
fixes, and **all 53 went Title Case → sentence case, none the other way**.

**The paper is the oracle for what is a name.** A word the article itself writes lowercase
mid-sentence (`volcano`, `deposit`, `mineral`) is an ordinary word whatever the docx did to
it; one it writes capitalized (`Tolbachik`, `Kamchatka`) is a name; one it writes in caps
(`USA`, `REE`) is an acronym to restore. Wholly upper-case **and Title-Cased** lines are ignored
as evidence — running heads repeat on every page, and the *Canadian Journal of Mineralogy and
Petrology* sets its titles in caps/small-caps, so they say nothing about a word's true case.

**A formal place name keeps all of its words**, on both sides of the attested name: `New Mexico`,
`La Sal`, `Vanadium Queen` (before) and `Elba Island`, `Ingul Gold Placer`, `Tolbachik Volcano`,
`Quadeville Rose Quartz Quarry` (after) — even though the paper writes the bare head-noun
lowercase elsewhere ("the volcano erupted"). The papers disagree with each other here, so this is
the one thing the paper does *not* decide. **`mine` is the exception** and stays lowercase: *the
Burro mine*, *the Redmond mine*. A species is normally lowercase (`jamesite`, `dongchuanite
group`) but is kept when it sits inside a name (`Rose Quartz Quarry`) — adjacency to an attested
name is what separates the two. A word the paper cannot vouch for is left alone, and does **not**
go on to vouch for its neighbours.

Never re-cased: chemistry (`Pb2(Fe3+6Zn)O2(PO4)4(OH)8`), an element-prefixed compound
(`Al-bearing`), a Levinson suffix (`-(Ce)`, never `-(ce)`), a Roman numeral (`IV.`), and a
site variable (the `A` in `analogs (A = K, Rb, Cs)` is not the article). A capitalized word
the paper gives no evidence for is **left alone** — lowercasing a name it cannot verify is
the one harmful mistake this check could make, so it under-corrects instead.

Fires on 5 % of entries; needs ≥2 wrongly-capitalized words, so a single arguable word stays
silent.

**This is the one check that WRITES its correction into the docx** — the single exception to the
comment-only rule, and it is deliberately narrow:
- The corrected citation is written as a **Word tracked change** in the `review_out` **copy**, so
  the reviewer opens it, sees exactly what changed, and clicks **Accept** or **Reject** in Word.
  Nothing is rewritten invisibly, and nothing is irreversible. The **source docx is never
  touched** (that invariant is unchanged).
- **A cell a person has already edited is never overwritten.** If the Reference cell carries any
  human tracked change, the tool leaves it alone and stays a comment (the run reports *"fix left
  to the reviewer (already hand-edited)"*).
- The rewrite differs from the docx in **letter case only** — the authors, journal, year and
  pages stay byte-identical, and the check refuses to write at all if it cannot prove that.
- Reruns are **idempotent**: a rerun rejects the tool's own previous change and re-derives it, so
  edits never stack.
- The comment (with the full suggested title) is still written either way.

Every other check remains comment-only.

#### Reference-table checks (16, 18) — hardened instrumentation & naming
Reference tables encoding standard crystallographic conventions, hand-curated
as small, editable constants at the bottom of `pxrd_review/extra_checks.py`
(`VOCAB_CANON`, `VOCAB_FIX`, `KBETA_FILTER`, `MONO_MATERIALS`, `REE_ELEMENTS`,
`POLYTYPE_SYS`). They **comment/suggest only** — the annotator highlights the cell
and writes the suggested value; it never rewrites a field. (The reference-title check, 26, is
the one exception: it writes its correction as a reviewable tracked change — see above.)

16. **instrumentation designators** — the parser now also reads the **FilterType**
    field. Checks:
    - **controlled-vocabulary** spelling/casing of `Spacing Instr.`, `Intensity
      Instr.`, `Intensity Type`, `Filter` — suggests the canonical value (⚑ flag).
      Catches typos (`Diffractomer`/`Diffractomter` → `Diffractometer`), casing
      (`Monochromator crystal` → `Monochromator Crystal`, `Beta-filter` →
      `Beta-Filter`), and `Visual?` → `Visual`. Unseen typos are caught by
      closeness to a canonical value (never forces a far-off value).
    - **β-filter element vs anode** (textbook Kβ rule): with `Filter = Beta-Filter`,
      `FilterType` is fixed by the anode — Cu→Ni, Co→Fe, Fe→Mn, Cr→V, Mo→Zr, Ag→Pd
      (⚑ flag; caught real CoKα+Ni and FeKα+Ni errors in the corpus).
    - **monochromator material** — `Monochromator Crystal` should carry a crystal
      material (Graph/Ge/Si…), not a β-filter foil (· note).
    - **measured data completeness** — for a genuinely measured method (Spacing
      Instr. ∈ Diffractometer/Film/Camera/Gandolfi/Guinier/Debye-Scherrer/Visual/
      Image plate), a blank **Radiation/anode** or blank **Intensity Type** is
      flagged (⚑). NOT applied to `Calculated`/`Other` (collapsed/derived from
      single-crystal data), where a blank is legitimate. A blank anode is **not
      treated as simply missing when λ is given**: the source is derived from the
      wavelength — λ matching a characteristic line → "set the anode to CuKα/MoKα…";
      λ matching nothing + PDF describes synchrotron/beamline → "set the anode to
      Sync"; otherwise "synchrotron? — specify". Intensity Type is flagged blank
      only — Integrated vs Peak is *not* prescribed (the same instrument uses both).
    - *(Deliberately NOT checked: `Spacing=Calculated` with `Intensity=Other`. That
      is the correct encoding for a pattern calculated from single-crystal/synchrotron
      data — d-spacings from the cell, intensities collapsed/derived from the observed
      structure factors. `Other` is meaningful, not "unknown".)*
17. **PDF monochromator/β-filter → fill a blank Filter** — when the docx `Filter`
    field is blank AND the PDF names the device in an **unambiguous, powder-context
    sentence** (e.g. "graphite-monochromated", "Ni-filtered"; the sentence must
    carry powder/PXRD/Gandolfi/Debye/Guinier), suggest the value as a comment on the
    Filter cell (⚑). The powder-context gate is essential: it skips single-crystal
    monochromator mentions (which would otherwise be mis-attributed to the powder
    Filter — e.g. for calculated-from-SC patterns). High precision, low yield.
18. **name vs ideal formula** — the **Levinson rare-earth suffix** `-(Ce)`/`-(La)`/
    `-(Y)`… must name the dominant REE in the (empirical) formula; flags a mismatch
    with the corrected name (⚑ flag; validated 29/29 on the corpus). Ambiguous
    cases (REE listed without coefficients) are skipped. **Polytype suffix**
    (`-1M`/`-2O`/`-3T`…) letter must be consistent with the crystal system
    (M↔monoclinic, O↔orthorhombic, T↔trigonal, Q↔tetragonal, …).
19. **Intensity Type ↔ detector** *(the reviewers' single most frequent comment)* —
    Intensity Type is set by the detector: **area detectors** (image-plate, Gandolfi/
    pseudo-Gandolfi, Guinier camera, R-AXIS RAPID, curved imaging plate) integrate the
    2D ring → **Integrated**; **Bragg-Brentano** slit optics → **Peak**. Detected in a
    powder-context sentence; flags the mismatch (⚑). "Guinier" is guarded against the
    author surname. **Skips docx-Calculated patterns** (Intensity Type is a modelling
    choice there, not a detector fact); patterns where it matters are recorded as
    measured in the docx and still reach the check. Validated ~90% consistent;
    independently reproduces the reviewer's own I001361 and I002366 comments.
20. **Calculated pattern, λ not stated** — when the docx pattern is Calculated and its
    λ (and anode) appear nowhere in the paper, flag "confirm the wavelength used" (⚑).
    Catches default CuKα λ on synchrotron-derived calcs (Feiite/Liuite/Tschaunerite).
21. **Primary (systematic) name normalization** — mechanical nomenclature fixes derived
    from reviewer edits and validated to reproduce them with **zero** false positives:
    remove redundant **"Aqua"**, hyphenate **"Hydrogen-&lt;oxoanion&gt;"**, and put
    oxoanions **before** Hydroxide/Hydrate (⚑, suggests the corrected name). Composition-
    dependent fixes (dropping a non-dominant cation, the acid-salt `Arsenate+Hydroxide
    →Hydrogen-Arsenate`, and `<Metal> Oxide→oxoanion` which needs the formula to tell
    molybdate from molybdite) are left to the reviewer.

Run just the extras: `python3 -m pxrd_review.extra_checks <folder> [<id>]`.

#### ICDD `.dft` (DataQuacker) cross-check — a co-equal proxy (console/log only)
ICDD DataQuacker `.dft` files (CIF-like structured records: cell+esd, Z, SG,
density, formulas, geometry, temperature, comments) are paired by entry id
(`cell_lambda_check.dft_index`, `extra_checks.parse_dft`) and compared to the
docx. The `.dft` is a **co-equal proxy, NOT ground truth** (the PDF is the
arbiter), so every `check_dft` finding is **`note` severity — surfaced in the
console and a dedicated "ICDD .dft CROSS-CHECK (verify…)" section of the log,
and NEVER written into the docx.** It is deliberately limited to the reliable
structured signals and stays quiet on agreement (Part 1: 8/62 entries;
validation set: 18/168):
- **cell value divergence**, but only when it's the *same cell* with 1–2
  discrepant axes (transcription-level); when most axes differ (axis permutation /
  different setting — common between a powder docx and an SC `.dft`) it stays
  silent, since the docx-vs-PDF cell check is the real validator;
- **Z** (only when the cells otherwise agree — a different cell scales Z
  proportionally and isn't an error; docx-vs-CIF Z is covered separately);
- **geometry** for measured methods (e.g. docx `Film` vs `.dft` `Camera:Gandolfi`).
SG (notation noise), precision/esd (overlaps check 8; the docx is often the more
complete one), temperature (the `.dft` field is ambiguous — sometimes the SC
value) and the comment-loop fields (IMA/optical — garbled in some `.dft`) are
NOT compared.

#### Cross-source cell consensus + Mindat feedback (check 22)
`parse_cif` now also reads the **cell** (a/b/c/α/β/γ), and `extra_checks.mindat_struct`
resolves a species to its Mindat **structural** record (cell, SG=IT number, elements,
formula) — ~93 % of reviewed entries resolve. check 22 compares the cell across
**docx (powder), `.cif`, and Mindat** using **sorted axis lengths** — angle-free (Mindat
stores γ=0 for uniaxial cells, so a *volume* comparison wrongly inflates hexagonal
cells by 1/sin120°≈1.155) and robust to powder↔SCXRD axis relabeling. The `.cif`/Mindat
are usually the **single-crystal** cell, which legitimately differs a little from the
submitted powder cell, so the bar is **high** (only large, non-polytype differences):
- **docx & `.cif` disagree with Mindat** (docx ≈ `.cif`, Mindat differs, not a super/
  sub-cell) → a `mindat_fix` **note** routed to a separate **`mindat_discrepancies.txt`**
  — a list to verify against the paper and follow up; **either side may be the one to
  fix** (Mindat is a co-equal proxy, and is sometimes the correct one — e.g. Feiite,
  where the synchrotron-refined docx/.cif cell deviates from the published cell Mindat
  carries). **Never** written into a docx.
- **the powder cell differs grossly** from the SCXRD structure (docx ≠ `.cif` ≈ Mindat,
  >5 %, non-polytype) → a `cell_cif` ⚑ flag for the reviewer.
- **axis swap** — same cell magnitudes but the axes are in a different *order* than the
  `.cif` (`cell_swap` ⚑) — a likely transcription error (axis permutations shouldn't
  occur for the same phase). Skips near-equal/uniaxial axes.
- **ideal formula** vs Mindat's **IMA formula** (ground truth, from the IMA list; EXACT
  species only — a variety/Levinson suffix differs from the base). Flags only a MAJOR
  discrepancy: a **species-defining element** in one formula **entirely absent** from
  the other — excludes substituents (the dominant cation of a `(A,B,…)` site only),
  traces (<0.5), and is order-independent (so `(Ca,Y)`↔`CaY`, `(Bi Sb)`↔`(Sb Bi)` don't
  flag). → `mindat_chem` note in the cross-check log (Mindat lags the CNMNC newsletter,
  so it cuts both ways). *(Hochleitnerite: Mindat's formula is missing the K.)*
- IMA status `QUESTIONABLE` (from the group cache) → a note.

`mindat_fix`/`mindat_chem`/`ima_status` are written to a separate **`mindat_discrepancies.txt`**
(sectioned Cell / Chemistry / IMA status), never into a docx. `.cif` **density** is NOT
used (H of OH/H₂O/NH₄ is usually unrefined). SG-vs-Mindat is **not** checked — Mindat
often reports nonstandard space groups or cells from old determinations.

### Mindat lookup (`pxrd_review/mindat.py`) — authoritative classification
A Python port of my Apps Script (Token auth, page-size 500,
exponential backoff). It pulls every IMA-approved geomaterial once with its
`groupid`, Nickel-Strunz code and `ima_status`, plus the group container entries
(`ima_notes=GROUP`), and caches them to `.cache/mindat_ima.json`. Check #3 then
resolves a mineral's group **offline** — a review run makes zero API calls.

Why the API and not PDF prose: a paper saying "X group" may merely be *comparing*
the mineral to a group, and bare "X group" prose also catches geological
formations ("Creek group"). Mindat encodes the real relationship — a mineral's
`groupid` points to its group, and a group needs ~3 isostructural members — so
`groupid → name` is ground truth.

Setup:
- API key: `$MINDAT_API_KEY` or `review_tool/.mindat_key` (untracked; in
  `.gitignore`).
- Build/refresh BOTH caches (group lookup + structural) from one API pull:
  `python3 -m pxrd_review.mindat --refresh`. There is no need to run anything else —
  `--refresh-struct` is kept only as an alias for the same command.
- Report what the tool is actually using: `python3 -m pxrd_review.mindat --status`.
- **Releasing (maintainer):** `python3 -m pxrd_review.mindat --refresh --bundle` freezes the
  current caches into `pxrd_review/data/*.json.gz` and the wheel picks them up, so reviewers
  with no API key still get the Mindat-backed checks. Commit `pxrd_review/data/` with the
  release. Without this the checks would simply find nothing on their machines — which looks
  exactly like a clean batch.
- Test one name: `python3 -m pxrd_review.mindat --lookup "#mineral-2T"`
- HTTPS needs CA certs; the client uses `certifi` if importable (macOS
  python.org builds lack system certs). `$MINDAT_INSECURE=1` disables
  verification as a last resort.

Name normalisation handles `-syn` / ", syn" tags, polytype tails (`-2T`,
`-IIb-4`) and variety adjectives (`Gypsum, strontian` → `Gypsum`), then falls
back to the base species. Across one batch: 20 grouped, 17 ungrouped, 3
genuinely not-in-cache new minerals (#mineral1, #mineral2, …) correctly flagged
to verify.

### Candidate-group scan (`pxrd_review/candidate_groups.py`) — prototype
Flags where a reviewed phase has an **obvious** structural relative that no group
link records — a group the PDF authors may have missed. Console report only,
**never** written into the docx (this is suggestive, not authoritative).

```
python3 -m pxrd_review.candidate_groups <folder> [--id Innnnnn] [--tol 0.04] [--max 4]
```
A candidate is reported only when ALL hold against an existing IMA mineral:
- **same space group** (Mindat's consistent integer SG code);
- **cell relation** — similar cell (each axis within `--tol`, default 4 %) *or* a
  rational sub-/super-cell (axis ratios near 1, 2, 3, ½, ⅓ …);
- **one sensible substitution** — identical element set, or a single swap between
  chemically analogous elements (Mg↔Fe, Al↔Sc, Ce↔Nd/REE, Si↔Ge …; a swap across
  chemistries like Si↔Fe does not count).
- **cation-size consistency** (surfaced as evidence, never a silent filter) — each
  swap shows the two Shannon ionic radii and Δr, and checks the **cell change is
  commensurate and in the right direction** (bigger cation → bigger cell). A
  same-size swap with a near-constant cell, or a large-radius swap whose cell
  tracks the size, reads as real; a mismatch gets a ⚠ to verify. This is the key
  guard against Mindat's sometimes loosely-applied group labels — the reviewer judges
  from the radii + metrics, not the group name.

…and only for phases where the relation is **not already identified**: ungrouped
in Mindat *and* no Structure/Isomorphism/Polymorphism group comment in the docx.
If the matched relative is itself in a group, the phase is a candidate **member**
of that existing group; if both are ungrouped, they are a lead to **form** a new
group (needs ≥3 members to be real — reported as a lead, not a conclusion).

Reporting is **member-centric**: it names the specific mineral matched (e.g.
"matches #mineral2"), then notes that mineral's group — and **warns when the group
spans several space groups** (a chemically-defined group, so the strict match is
to the member, not the whole group; this is why #mineral1 matches *#mineral2*,
not *#mineral3*, even though the group is called "#mineral3-#mineral2"). A `★name
echoes` marker flags an independent heuristic — a name usually signals its relations
(it often embeds or echoes a known relative's name, or two analogues share a
root) — as independent corroboration of the structural match.

Uses the structural cache (auto-refreshes like the group cache). On
one batch (default tol) it scans the 14 ungrouped/unidentified phases and
returns 2 clean leads — #mineral1 → matches #mineral2 (Zn↔Cu, Δ1.6 %, in an
existing chemically-named group), and #mineral3 ↔ #mineral4 (Ce↔Nd, Δ1.0 %, both
ungrouped → could form a group) — with no false positives. `--tol 0.08` surfaces
more (e.g. a Ti↔Si lead), trading precision for recall.

Limitations: a **brand-new mineral not yet in Mindat** has no structural record,
so it is skipped (the case where this would be most useful but data is missing —
a batch-vs-batch fallback on docx cell/formula is the next step). Mindat cells are
sparse (b/angles often 0 = uniaxial/default), so matching uses a, b, c only.

**Staleness-aware auto-refresh — no need to run `--refresh` by hand.** The review
tools call `mindat.refresh_if_stale()` on startup: if the cache is missing or
older than 14 days (covering the monthly/bimonthly CNMNC cadence) and a key +
network are present, it pulls fresh data first (one `[mindat] refreshing…` line,
once per run). No key or offline → it quietly keeps using the existing cache, so
a review never breaks. So newly-approved species resolve automatically on the next
review run. A manual `python3 -m pxrd_review.mindat --refresh` remains available but is
now optional belt-and-suspenders. (Scheduling that command — cron, a systemd timer, a
macOS LaunchAgent — is equally optional; nothing in the tool depends on it.)

Tuning notes from the first 44-entry pass: #3 PDF-prose and #2
provenance were initially far too loose and were tightened to specific patterns;
#9 had a sign bug (indices read unsigned) now fixed; #1 now requires a diffraction
co-occurrence. Volumes are ~2 findings/entry, mostly info/note with a focused set
of flags.

## Writing the extra checks into the docx
`pxrd_review/annotate_review.py` now writes the reliable extra checks into each entry, each
anchored on the relevant cell (Word comment by **"PXRD Review Tool"**; flags also
yellow-highlight their anchor):
- **symmetry / precision** → the offending Author's-Cell parameter (a…γ);
- **Calculated pattern / instrumentation vocab** → the Instrumentation row;
- **hkl indexing** → the Reflection List;
- **missing IMA number** → the IMA Number field;
- **analysis** (count missing/mismatch, (calc), wt.% total, empty/misplaced) → the
  **Analysis comment cell** (where the `Microprobe analysis (wt.%): …` data is
  given; the label cell when that field is empty);
- **CIF Z mismatch** → the **Z cell** of the Author's-Cell row (`cell:Z`);
- **ideal formula** → the formula row;
- **name vs formula** (Levinson/polytype) → the mineral name;
- **Mindat group** (informational, not highlighted) → the mineral name.

Soft `note`/other `info` findings stay console-only (`pxrd_review/cell_lambda_check.py`).
Each `Finding` carries an `anchor` (`'cell:a'`…`'cell:Z'`/`'cell:SG'`, `'instr'`,
`'refl'`, `'ima'`, `'analysis'`, `'formula'`, `'name'`) that the annotator maps to a
cell. Comment placement matters to the reviewer, so anchor each finding to the cell
a human would edit. An entry is still
copied **byte-for-byte** when it has no cell/λ issue *and* no writable extra
(verified: clean entries remain identical to source). On a 44-entry batch:
44 entries → 41 edited, 3 untouched, 99 comments.

## Review-mode GUI (`pxrd_review/gui/review_gui.py`) — validate the flags, comments & annotations
The CLI checks write comments/highlights + `annotation_log.txt`, but there is no
way to **see the evidence** behind each finding, so two failure classes are
invisible: **silent failures** (no `.pdf` paired, no cell parsed, `parse_entry`
threw, Mindat didn't resolve, a sibling-phase match) and **close calls** (a cell
match near the 0.004 Å tolerance, a λ "verify", an `info`/`note` that never became
a docx flag). The GUI surfaces both and lets the reviewer triage them.

```
pip3 install -r requirements.txt              # adds Flask (GUI only)
python3 -m pxrd_review.gui.review_gui "/path/to/entries"      # opens http://127.0.0.1:8000
python3 -m pxrd_review.gui.review_gui "/path/to/entries" --port 8000 --no-browser
```
It is a **thin, read-only presentation/triage layer over `annotate_review.analyze()`**
— it reuses the check logic verbatim, never duplicates or changes it, and **never
edits a docx**. Its only writes are sidecars under `<folder>/review_out`:
`gui_cache.json` (analysis cache), `triage.json` (verdicts), `triage_report.txt`
(the exported summary).

- **Dashboard** — one row per entry, the **primary lens being the major
  fixes/annotations the tool writes into the docx** (`N fixes` badge: flagged cell
  parameters, the cell-level comment, an anode-mismatch λ flag, indexing, intensity-
  type, formula/name, Mindat group). Default sort is by fixes; the **Fixes /
  Attention / Clean / All** view selector switches lenses. "Attention" is the
  *secondary* subset — silent failures & close calls (`no .pdf`, `no cell parsed`,
  `cell INVESTIGATE`, `docx parse error`, `cell near tolerance`, `λ unrec`,
  `Mindat: not resolved`). Instrument-wavelength findings (`λ verify`, the
  canonical-λ checks) are low value to ICDD, so they are shown but **muted and
  excluded from the fixes count/sort** (the anode-mismatch λ *flag* — Mo vs Cu — is
  a real error and is **not** demoted).
- **Entry detail** — side-by-side panes: **findings** — the cell-match result, the
  radiation result, and every extra finding, each badged by severity:
  **FLAG** (red, a real problem, written to docx) · **CHECK** (orange, confirm —
  info-level / λ verify) · **NOTE** (gray, low-confidence FYI) · **OK** (green, clean
  cell match), with a coloured left-border, a written-to-docx/console-only tag, its
  docx anchor, low-priority ones muted, and per-finding triage ✓ confirm / ✗ dismiss /
  ? look + note. A **"hide notes"** toggle (persisted) drops the gray NOTE rows so you
  can focus on the actionable FLAG/CHECK items. **.pdf evidence** (the page rendered via PyMuPDF with
  the cell values highlighted, page nav, a search box over the whole paper, and the
  captured snippet beneath); **docx values** (Author's cell grid with the flagged
  axes coloured, radiation, instrumentation, formulas, existing reviewer comments);
  and **Mindat & cross-source** (the Mindat structural record — sorted axes, SG,
  IMA formula, group, status — alongside the `.cif` and `.dft` cells).
- Each entry is **analyzed eagerly at launch** (cached to `gui_cache.json`,
  re-run only when a docx/PDF changes) so the dashboard badges are populated the
  moment it opens. Keyboard: `j`/`k` (or ‹ ›) step entries.
- **Appearance & layout** (⚙ in the top bar, all persisted in `localStorage`):
  four themes — **Clear Dark** (default; translucent frosted panels), **Solid Dark**,
  **Midnight**, **Graphite** — plus panel-opacity and backdrop-blur sliders, a
  compact/comfortable density toggle, and a font-size control. The panes are
  **drag-resizable** (sidebar, findings, the Mindat column, and the docx/Mindat
  split) and each side pane **collapses** from its title bar. (True see-through-to-
  desktop transparency would need a native window; the browser build does a frosted
  in-app translucency instead.)

### Triage → rerun feedback loop
Triage verdicts feed back into the annotator. **Rerun entry** (header) and
**Rerun all** (top bar) re-invoke `pxrd_review/annotate_review.py` with `--triage triage.json`,
which is **comment-only apart from the reference-title fix** (which is written as a
reviewable tracked change; every other correction remains the reviewer's): a
**dismissed** finding is **suppressed** (not written, and its fix is not applied),
a **confirmed / look** note is **folded into the tool's comment**, and the **Accept**
box follows your agree/disagree. The header shows a live preview (`rerun writes N ·
M suppressed`). The single-entry rerun passes `--no-logs` so it regenerates one docx
without clobbering the batch `annotation_log.txt` / `mindat_discrepancies.txt`.
`annotate_review --triage <json>` is also usable from the CLI; without it the output
is byte-for-byte unchanged (the regression suite depends on this).

**Security:** the server **binds to `127.0.0.1` only** (off the network/internet),
Flask **debug is OFF**, and the browser only ever sends an entry **key** that the
server maps to a file it indexed at startup — no raw paths from the page, so no
path traversal. No data leaves the machine. It is a localhost, single-user tool —
the same posture as a local Jupyter server.

The GUI's **written-to-docx** findings mirror `annotate_review` exactly (verified
entry-by-entry against `annotation_log.txt`), so it is a faithful preview of what
the annotator would write — without writing it.

## Known limitations / next steps
- **#3 (Mindat)** is only as current as the cached pull — re-run `--refresh` so
  newly-approved species resolve; until then they show as "not found — verify".
  Group strunz is taken from the species (group containers store none).
- **#10 (IMA)** depends on the proposal id appearing literally as `IMA …` in the
  PDF text; scanned-image PDFs or unusual phrasings will miss it.
- **#6 (ideal formula)** is intentionally conservative (empty-Analysis only); it
  will not catch "ideal formula given but a table of analyses exists elsewhere".
- **Multi-phase PDFs** are now largely handled (named grid rows + multi-column
  tables + phase-name tiebreak; see "Multi-phase papers" above). A residual
  near-degenerate case can still land on a sibling phase → "INVESTIGATE" when the
  matching cell genuinely isn't in the parsed text (e.g. a multi-phase entry pair,
  where the phases differ by < the match tolerance).
- The **grid** parser reads `a b c V` but leaves angles blank (α/β/γ shown as
  `None`); value/sig-fig checks then cover only the axes for those entries.
- Powder/single classification needs labeled examples to move beyond keyword
  proximity (decimal-places and esd-size are candidate secondary signals).

---

## Behavioral contract (regression cases) — read before changing the checks

This is my design memory for whoever maintains the checks (Claude or a human).
The checks were hardened by hand-auditing one review batch;
each rule below corresponds to a real false positive that was removed or a real
catch that must stay. `pxrd_review/regression_check.py` encodes every case as an assertion:

```
python3 -m pxrd_review.regression_check "/path/to/fixtures"   # all cases must PASS after any edit
```

The fixtures are a private corrected batch (not shipped — see NOTICE); set `$PXRD_REGRESSION_DIR`
to point at them once and the path argument becomes optional. Without them the suite exits with a
message rather than running, so this gate is available to Task Group reviewers only.

Run it after touching `pxrd_review/extra_checks.py`, `pxrd_review/cell_lambda_check.py`, or
`pxrd_review/annotate_review.py`. If a case fails, a known problem was reintroduced.

### Hard-won rules (do NOT regress)
- **Check 26 is the ONE check that writes into the docx.** Every other check comments and
  highlights; the reviewer applies the fix. Check 26 (reference title case) additionally sets
  `Finding.fix`, and `annotate_review._apply_tracked_fix` writes it into the **review_out copy**
  as a **Word tracked change**. Five things must stay true, and each has a regression case:
  (1) the **source docx is never touched**; (2) a cell a **human has already tracked-changed is
  never overwritten**; (3) the rewrite differs from the docx in **letter case only** — the check
  refuses to emit a `fix` at all if it cannot prove that; (4) reruns are **idempotent** —
  `_strip_tool_annotations` *rejects* the tool's own `w:ins`/`w:del` and re-derives them, so edits
  never stack; (5) the writer **declines a multi-paragraph cell** (sweeping several paragraphs'
  runs into one `w:del` would lose the paragraph break on Reject). A dismissed finding applies no
  fix. Do not give any other check a `fix` without the owner's say-so.
- **The tool's own tracked changes are not a human edit.** `_has_tracked_changes`,
  `output_hand_edited` and the reviewer-mark summaries are all author-aware. Break that and every
  fixed entry looks hand-edited: a backup on every rerun, and the tool's own work reported back to
  the reviewer as theirs.
- **Calculated pattern.** A docx correctly marked `Spacing=Calculated` is normal,
  not an error → console **note only**, never a docx flag, and it suppresses the
  radiation mismatch (calc wavelength ≠ experimental). The PDF-inferred "calculated
  from the structure" flag fires ONLY for a genuinely calc-only pattern — reject
  sentences containing *observed / experimental / measured / matches / fits /
  theoretical / "calculated from (the) powder"* (those describe a measured pattern
  or a comparison column). *(#mineral1, #mineral2, #mineral3 = measured.)*
  In multi-species papers ("for all species **except &lt;name&gt;** … were
  calculated"), if THIS entry is the excepted species its pattern was measured —
  don't flag it. *(camanchacaite = excepted, no flag; its siblings = flagged.)*
- **`.dft` cross-check is a co-equal proxy, console/log only.** `check_dft` is
  always `note` severity — never written to the docx. Keep it quiet on agreement:
  cell notes ONLY for a same-cell 1–2-axis transcription difference (suppress when
  most axes differ = a different setting/phase); Z notes ONLY when the cells
  otherwise agree (a different cell scales Z). Do NOT compare SG (notation noise),
  temperature (ambiguous `.dft` field), or the `.dft` comment-loop fields
  (IMA/optical are garbled in some files). The PDF stays the arbiter; the `.dft`
  never overrides the docx-vs-PDF or docx-vs-CIF checks.
- **Radiation.** PDF text extraction drops the Kα α-glyph → accept the α-less form
  (`CuK radiation`, `(CuK)`). Skip microprobe **standard** emission lines
  (`hematite (FeKα)`) and pick the powder radiation that carries an explicit λ.
  *(#mineral1 CuK = powder = match; #mineral2 CoKα not CuKα; #mineral3 Mo↔Cu
  is a real flag.)* When the paper names a **single anode** and it **matches** the
  docx, that is unambiguously *the* radiation → `ok`, **not** `verify`, even if the
  only mention sits in a single-crystal sentence (a powder pattern collected via a
  Gandolfi-like / crystal-rotation motion on a single-crystal instrument shares the
  source). Only **two-or-more distinct anodes** with no powder-context stay `verify`.
  *(I003562/I003563 single MoKα = OK; I003521 Cu+Fe = verify.)*
- **Cell provenance (check 2).** A powder cell that the paper says was refined from
  the **powder data** (e.g. "Refined unit-cell parameters from the powder data using
  CHECKCELL") is fine — never flag provenance, regardless of single-crystal prose.
  Otherwise a "from the single-crystal / not refined" phrase fires ONLY when its
  sentence is genuinely about the **cell** AND is not boilerplate: exclude a
  comparison ("…agree with the SC values"), a calculated-pattern table note,
  "…were not refined" about atom displacements / the extinction coefficient, and —
  crucially — the **Dcalc density-calculation** sentence ("calculated density, based
  on the empirical formula and the unit-cell refined from single-crystal data"),
  which is universal new-mineral boilerplate, not an actionable provenance issue (a
  SC cell is acceptable). Validated on a larger reference set: **Part 1 14→0,
  validation set 8→1** (only a genuine non-density "cell determined from single-crystal"
  statement survives). *(I003562/I003599/I003600/I003750 = no flag.)*
- **Cell source — PXRD vs SCXRD (`cell_source`).** ICDD entries carry the **powder**
  cell, so using the single-crystal cell is worth surfacing. A matched cell's source
  is labelled by **powder cues first** (GSAS/EXPGUI/Rietveld/UnitCell/CHEKCELL/μXRD/
  "from the powder data" — these WIN over a stray "single-crystal" word elsewhere in
  the snippet), then **positive** single-crystal cues (single-crystal/SCXRD/centroids/
  "N reflections"), then a hedged "refined unit-cell … space group" guess. A docx
  **FLAG** fires ONLY on a *definitive* single-crystal cell (positive SC cue, no powder
  cue) that ALSO has a same-phase powder cell reported (sorted-axis match within 10 %,
  differing >tol) — "used the SCXRD cell; powder cell a=… exists". Everything else
  SCXRD-looking is a console/GUI **note**, never a docx flag. Validated: Part 1 = 1
  flag (I003632, "centroids of 1089 reflections" + a cubic powder cell), validation set = 2
  (I003155 SCXRD-vs-PXRD-WPF table; I002960 "single-crystal techniques"); the powder/
  Rietveld/UnitCell cells (I003510/I003566/I003636) and Julgoldite (no same-phase
  powder cell) correctly do NOT flag.
- **Cubic cells.** Papers give only `a`. Parse the `a (Å) … V (Å³)` table; accept
  as cubic when "cubic" is near OR V ≈ a³ (tight, 0.5%), and NOT when a differing
  `c (Å)` is present. *(#mineral.)*
- **Uniaxial cells (trigonal/hexagonal/tetragonal).** Only `a, c` are reported
  (b = a). Don't flag a "missing b"; infer b = a when matching. Assign table
  values **by axis label**, not positionally (a `c` value must not land in `b`).
  *(#mineral1 → only the c esd flags; #mineral2/#mineral3 stay clean.)*
- **Cell candidate choice.** Prefer the PDF cell with the SMALLEST deviation
  (full-precision prose) over a rounded summary table; phase-name match only breaks
  near-ties (≤1 mÅ). *(#mineral matches the full-precision cell → clean.)*
- **Optical sign.** The ± glyph often extracts as a control char (`\x02`); never
  guess it. Flag a mismatch only when the PDF sign is a clean +/− or
  positive/negative word. *(#mineral1, #mineral2 = '+', no flag.)*
- **IMA number.** Only flag a missing number when the entry's OWN name sits beside
  a "new mineral"/"approved" cue that is NOT a reference citation (author-year,
  Newsletter, et al., DOI, page range). Structural reinvestigations of old minerals
  have no number. *(#mineral1/#mineral2 = flag; #mineral3/#mineral4 =
  reinvestigations, no flag.)*
- **Classification (group).** Suppress the Mindat group comment when the docx
  already names the group anywhere (IMA Classifications / Group rows), not just the
  Strunz field. Ungrouped status is not worth a comment. *(#mineral.)*
- **Z / CIF.** Compare Z only (cell params and SG are unreliable across polytypes /
  settings / hydration states). Flag only when CIF Z > 1 and the CIF mineral name
  matches the entry. A Z or sig-fig mismatch is NOT "severe". *(a synthetic hydrate,
  docx Z=6 vs the dehydrated phase's CIF Z=2, is a real flag I resolve.)*
- **Missing esd.** When a cell value lacks an esd the PDF supplies, NAME it:
  "PDF gives c=12.219(2); add the (2)". *(#mineral.)*
- **Analysis field.** If empty but the data sits in another field (e.g. Absolute
  Configuration), say "move it"; combine with the empty-field note. Strip the
  `PXRD check [...] — ` boilerplate from logged comments. *(#mineral.)*
- **Density (check14) is DEREGISTERED.** docx Dcalc uses the empirical formula about
  as often as the ideal, so a docx/PDF density gap is not an error. Helpers remain
  for possible future "grossly mistyped density" use. *(No density flags anywhere.)*
- **Instrument designators (check16).** Vocabulary fixes and the β-filter element
  rule (Cu→Ni, Co→Fe, Fe→Mn, Cr→V, Mo→Zr, Ag→Pd) are ⚑ flags — high confidence,
  textbook. **Do NOT add a `Spacing=Calculated` / `Intensity=Other` coherence
  check** — it fired on ~25 % of submissions and was wrong: that pair is the correct
  encoding for a powder pattern calculated from single-crystal/synchrotron data
  (d-spacings from the cell; intensities `Other` = collapsed/derived from the
  observed structure factors). `Other` is a meaningful designator, not "unknown".
  Instruments/geometry are surfaced as ℹ info — never "correct" `Spacing Instr.` to
  a camera name (reviewer keeps it generic and notes geometry in a comment).
  *(I003747/I003698 = no vocab flag; I003246 = R-AXIS recognised.)*
  Blank **anode**/**Intensity Type** are flagged ONLY for measured methods
  (`MEASURED_METHODS`), never for Calculated/Other. Do NOT prescribe Integrated vs
  Peak — the same instrument uses both. **Do NOT auto-fill filter/filtertype/anode
  from an "instrument → canonical profile" table:** the reference set showed the same
  instrument runs different anodes, filter is blank ~67% of the time and accepted,
  PDF "X-filtered" mentions are mostly sample-prep noise, and instrument detection
  is confounded by the single-crystal source named on calculated patterns. Only the
  anode↔λ↔β-filter physics (above) is reliable enough to flag.
- **Name vs formula (check18).** Levinson suffix flags ONLY on a confident dominant
  (≥2 REE with explicit coefficients, unique max ≠ suffix). REE listed without
  coefficients (ambiguous ideal formula) must NOT flag. Polytype letter↔system uses
  the docx system letter (trigonal 'T' maps to h/r, tetragonal is 'Q', not 't').
  *(I003511/I003523/I003521 correctly named = no flag.)*
- **Intensity Type ↔ detector (check19).** Area detector ⇒ Integrated, Bragg-Brentano
  ⇒ Peak; the detector keyword must be in a powder-context sentence. **Guard "Guinier"**
  with camera/method context — it is also the author surname (André Guinier), and a
  "Guinier et al." citation must NOT be read as the method. Do NOT teach the full
  Integrated/Peak distinction from raw data — only the geometry rule. The **crystal-
  rotation method** (`crystal[\s-]?rotation` + method/motion/technique/scan) is the same
  pseudo-Gandolfi area-detector technique under a different name → Integrated. *(I003657
  BB→Peak, I003563 Gandolfi→Integrated, I003548 crystal-rotation→Integrated; I003815 real
  via R-AXIS image-plate.)* **Skip
  docx-Calculated patterns** — Intensity Type is meaningless for most calculated
  patterns; the ones where it matters are docx-marked measured (e.g. I002366 Kiryuite
  is Diffractometer though the paper calculated it). *(I003822/I002983 calc = no flag.)*
- **Calculated wavelength (check20).** Flag only when NEITHER the numeric λ (~3 s.f. or
  2-dec) NOR the anode element (`CuK`…) appears in the paper — a paper that says "CuKα"
  without the number is fine. *(synchrotron calcs with a default CuKα λ = flag.)*
- **Primary name (check21).** STRING-mechanical only: remove "Aqua", hyphenate
  "Hydrogen-&lt;oxoanion&gt;", oxoanions before Hydroxide/Hydrate. Do NOT reorder
  Hydroxide relative to **halides** (accepted names keep "Hydroxide Fluoride/Chloride"),
  and do NOT do `<Metal> Oxide→oxoanion` (needs the formula: molybdate vs molybdite).
  Validated to reproduce real edits with ZERO false positives on accepted names.
- **Cross-source cell (check22).** Compare cells with **sorted axis lengths**, NEVER
  cell volume with defaulted angles — Mindat stores γ=0 for uniaxial cells, so a
  volume comparison inflates hexagonal cells by exactly 1/sin120°≈1.155 (this once
  produced 23 phantom "Mindat discrepancies", all ×1.15). `.cif`/Mindat are usually the
  SCXRD cell, so use a HIGH tolerance vs the powder cell and exclude super/sub-cell
  (polytype) rational relations. Mindat is a co-equal proxy: a `mindat_fix` finding is
  a console NOTE routed to `mindat_discrepancies.txt`, NEVER a docx flag. For a
  **synthetic** phase, skip the Mindat CELL check (a synthetic cell differs from the
  natural species Mindat carries) but KEEP the chemistry check — a synthetic's ideal
  formula should still match the natural IMA formula (unless a redefinition, flagged in
  the text). *(I003246 = agrees, no flag; I003599 Dypingite-syn = cell skipped.)*

### Accept marking
`pxrd_review/annotate_review.py` writes a lowercase **"x"** in the cell after **Accept** for
essentially every entry (the usual convention), **centred** in the box (horizontal +
vertical) so it doesn't sit against the label. It is withheld (all boxes left
blank for a manual decision) ONLY when the cell is grossly wrong — `_is_severe()`:
cell verdict `investigate` with ≥2 axes off tolerance, or one axis >2% off. Minor
cell / sig-fig / esd / Z discrepancies are NOT severe (a new mineral is an Accept
unless the chemistry/cell/SG is completely wrong). It never overwrites a box a
human already marked.

### Preserving manual edits on rerun
The output docx in `review_out/` is the working copy; the source docx is
never edited. A rerun detects a hand edit via tracked changes (`w:ins`/`w:del`), a
non-tool comment, body text differing from source, or a **Reject/Replace box mark**
(the body signature ignores only the Accept value cell, which the tool auto-stamps —
so a reviewer's Reject/Replace decision counts as a hand edit and is preserved, not
overwritten with Accept). It then **refreshes in place**: backs up to
`review_out/.edit_backup/<name>.<timestamp>.docx`, strips ONLY the tool's own comments
(author "PXRD Review Tool") + the tool's own yellow highlights (those inside a tool
comment range — a reviewer's manual yellow highlight is kept) from a temp copy, and
re-annotates onto it — so tracked changes, manual comments, text edits, and the manual
Accept/Reject decision survive while the tool's findings are made current. The strip is
atomic (temp copy; `out` is replaced only on success). `--force` rebuilds from
source (discards manual edits). The `_edited` vs clean output name is derived from
the (deterministic) `_is_clean()` verdict, so the path of a given entry is stable
across reruns and refresh-in-place still finds the right file. NOTE for maintainers: python-docx `.text` does NOT
include tracked **insertions** — never rely on it to detect a track-changes edit;
check `w:ins`/`w:del` in `document.xml`.
