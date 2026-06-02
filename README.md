# PXRD review tool — cell & wavelength comparator (prototype)

Compares the **Author's Cell** (a, b, c, α, β, γ, space group, Z) and the
**radiation/wavelength** entered in an ICDD pattern `.docx` against the values
reported in the source `.pdf`, and flags discrepancies for review.

It does **not** check diffractometer/camera type.

## Run
```
python3 cell_lambda_check.py /path/to/entries          # console report, whole folder
python3 cell_lambda_check.py /path/to/entries --id Innnnnn
```
Auto-pairs each `Innnnnn(Name).docx` to its PDF in the folder (or a subfolder),
expanding range-named PDFs like `Innnnnn-Innnnnn.pdf`. Ids may be `I`- or
`O`-prefixed. When several PDFs share an id, the **primary article PDF is
preferred** over `_Supp`/`_TableS1` files (those often omit the cell or hold a
different phase's table) — pairing the wrong file was the main cause of
"no cell found" misses.

Dependencies: PyMuPDF (`fitz`). docx is parsed directly from `word/document.xml`.

## Writing the review into the .docx
`annotate_review.py` runs the same comparison and writes the findings back into
each entry as **Word comments + yellow highlights**, so you see them
in context. It reports **errors only** — a clean entry gets no comment. Every
entry (clean or flagged) also gets an **"x" in the Accept box** unless its cell is
grossly wrong (see "Accept marking" and "Behavioral contract" below), so a clean
entry is opened + re-saved rather than byte-copied. Reruns **preserve hand-edited
outputs** (your tracked changes / comments are kept; tool comments are refreshed).
```
python3 annotate_review.py "/path/to/entries"             # -> <folder>/review_out (copies)
python3 annotate_review.py "/path/to/entries" --id Innnnnn
python3 annotate_review.py "/path/to/entries" --inplace   # edit the originals instead
```
Flagged entries are saved as **`<name>_edited.docx`** (the ones with a comment /
highlight), so you can spot them at a glance in the `review_out/` listing; clean
entries keep the source name. (`--inplace` edits the originals and does not
rename.) A stale opposite-named twin from an earlier run is removed automatically
unless you hand-edited it, in which case it is kept and noted on the console.
What it writes:
- a comment on each flagged Author's-Cell value (value / significant-figures /
  esd mismatch), with that value highlighted;
- a comment on the Radiation cell for an anode hard-flag (only when the cell
  itself matched);
- a single brief **"No matching PDF cell found."** when no cell could be matched.

Comments are authored as **"PXRD Review Tool"** so they filter apart from human
reviewers'. Extra dependency: `python-docx` (≥1.1 for the comment API).

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
using a single-crystal cell is acceptable for many entries — you decide
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
  #mineral). The printed evidence snippet lets you confirm.

## Extra checks (`extra_checks.py`) — my 10 most common review comments
Mined from my own Word comments across past review batches, these are
the recurring notes the cell/λ comparator did **not** cover. They run
automatically at the end of every `cell_lambda_check.py` report (and on the
no-PDF path, since several are docx-internal). They live in a separate module on
purpose: more heuristic, easy to tune or switch off per check as I refine them.

Each finding is graded **⚑ flag** (likely needs an edit/comment), **ℹ info**
(surface for you to confirm — often acceptable), or **· note** (low
confidence). The ten:

1. **geometry / camera method** — surfaces the specific named method in the PDF
   (Bragg-Brentano, Gandolfi, pseudo-Gandolfi, Debye-Scherrer, Guinier, image
   plate, neutron TOF) when the docx `Spacing Instr.` is generic. Keyword must
   share a sentence with a diffraction term. Also names the **specific instrument**
   when recognised (Rigaku R-AXIS RAPID II, XtaLAB Synergy, SuperNova, MiniFlex,
   SmartLab; Bruker D8/APEX; STOE; PANalytical Empyrean) to help confirm the
   designators (ℹ info — the geometry goes in a comment, *not* into `Spacing Instr.`).
2. **cell not powder-refined** — strong phrasings only ("were not refined",
   "from the single-crystal", "cell from SAED").
3. **group / structural classification** — **authoritative via Mindat**
   (`mindat.py`): the mineral's `groupid` → group name, with the species'
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

#### Corpus-curated checks (16, 18) — hardened instrumentation & naming
Reference tables mined from the corrected corpus (ICDD/TAO/Tony's/2028) then
hand-curated as small, editable constants at the bottom of `extra_checks.py`
(`VOCAB_CANON`, `VOCAB_FIX`, `KBETA_FILTER`, `MONO_MATERIALS`, `REE_ELEMENTS`,
`POLYTYPE_SYS`). They **comment/suggest only** — the annotator highlights the cell
and writes the suggested value; it never rewrites a field.

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
21. **Primary (systematic) name normalization** — mechanical nomenclature fixes mined
    from reviewer edits and validated to reproduce them with **zero** false positives:
    remove redundant **"Aqua"**, hyphenate **"Hydrogen-&lt;oxoanion&gt;"**, and put
    oxoanions **before** Hydroxide/Hydrate (⚑, suggests the corrected name). Composition-
    dependent fixes (dropping a non-dominant cation, the acid-salt `Arsenate+Hydroxide
    →Hydrogen-Arsenate`, and `<Metal> Oxide→oxoanion` which needs the formula to tell
    molybdate from molybdite) are left to the reviewer.

Run just the extras: `python3 extra_checks.py <folder> [<id>]`.

#### ICDD `.dft` (DataQuacker) cross-check — a co-equal proxy (console/log only)
ICDD DataQuacker `.dft` files (CIF-like structured records: cell+esd, Z, SG,
density, formulas, geometry, temperature, comments) are paired by entry id
(`cell_lambda_check.dft_index`, `extra_checks.parse_dft`) and compared to the
docx. The `.dft` is a **co-equal proxy, NOT ground truth** (the PDF is the
arbiter), so every `check_dft` finding is **`note` severity — surfaced in the
console and a dedicated "ICDD .dft CROSS-CHECK (verify…)" section of the log,
and NEVER written into the docx.** It is deliberately limited to the reliable
structured signals and stays quiet on agreement (Part 1: 8/62 entries;
training: 18/168):
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

### Mindat lookup (`mindat.py`) — authoritative classification
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
- Build/refresh the group cache: `python3 mindat.py --refresh`
- Build/refresh the structural cache (candidate-group scan): `python3 mindat.py --refresh-struct`
- Test one name: `python3 mindat.py --lookup "#mineral-2T"`
- HTTPS needs CA certs; the client uses `certifi` if importable (macOS
  python.org builds lack system certs). `$MINDAT_INSECURE=1` disables
  verification as a last resort.

Name normalisation handles `-syn` / ", syn" tags, polytype tails (`-2T`,
`-IIb-4`) and variety adjectives (`Gypsum, strontian` → `Gypsum`), then falls
back to the base species. Across one batch: 20 grouped, 17 ungrouped, 3
genuinely not-in-cache new minerals (#mineral1, #mineral2, …) correctly flagged
to verify.

### Candidate-group scan (`candidate_groups.py`) — prototype
Flags where a reviewed phase has an **obvious** structural relative that no group
link records — a group the PDF authors may have missed. Console report only,
**never** written into the docx (this is suggestive, not authoritative).

```
python3 candidate_groups.py <folder> [--id Innnnnn] [--tol 0.04] [--max 4]
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
  guard against Mindat's sometimes loosely-applied group labels — you judge
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
echoes` marker flags my own heuristic — a name usually signals its relations
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

**Staleness-aware auto-refresh — you never run `--refresh` by hand.** The review
tools call `mindat.refresh_if_stale()` on startup: if the cache is missing or
older than 14 days (covering the monthly/bimonthly CNMNC cadence) and a key +
network are present, it pulls fresh data first (one `[mindat] refreshing…` line,
once per run). No key or offline → it quietly keeps using the existing cache, so
a review never breaks. So newly-approved species resolve automatically the next
time you review. Manual `--refresh` and the monthly `LaunchAgent`
(`com.minerals.mindat-refresh.plist`) remain available but are now optional
belt-and-suspenders.

Tuning notes from the first 44-entry pass: #3 PDF-prose and #2
provenance were initially far too loose and were tightened to specific patterns;
#9 had a sign bug (indices read unsigned) now fixed; #1 now requires a diffraction
co-occurrence. Volumes are ~2 findings/entry, mostly info/note with a focused set
of flags.

## Writing the extra checks into the docx
`annotate_review.py` now writes the reliable extra checks into each entry, each
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

Soft `note`/other `info` findings stay console-only (`cell_lambda_check.py`).
Each `Finding` carries an `anchor` (`'cell:a'`…`'cell:Z'`/`'cell:SG'`, `'instr'`,
`'refl'`, `'ima'`, `'analysis'`, `'formula'`, `'name'`) that the annotator maps to a
cell. Comment placement matters to the reviewer, so anchor each finding to the cell
a human would edit. An entry is still
copied **byte-for-byte** when it has no cell/λ issue *and* no writable extra
(verified: clean entries remain identical to source). On a 44-entry batch:
44 entries → 41 edited, 3 untouched, 99 comments.

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
catch that must stay. `regression_check.py` encodes every case as an assertion:

```
python3 regression_check.py            # all cases must PASS after any edit
```

Run it after touching `extra_checks.py`, `cell_lambda_check.py`, or
`annotate_review.py`. If a case fails, you reintroduced a known problem.

### Hard-won rules (do NOT regress)
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
  is a real flag.)*
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
  from an "instrument → canonical profile" table:** corpus mining showed the same
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
  Integrated/Peak distinction from raw data — only the geometry rule. *(I003657 BB→Peak,
  I003563 Gandolfi→Integrated; I003815 real via R-AXIS image-plate.)* **Skip
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

### Accept marking
`annotate_review.py` writes a lowercase **"x"** in the cell after **Accept** for
essentially every entry (my usual convention). It is withheld (all boxes left
blank for a manual decision) ONLY when the cell is grossly wrong — `_is_severe()`:
cell verdict `investigate` with ≥2 axes off tolerance, or one axis >2% off. Minor
cell / sig-fig / esd / Z discrepancies are NOT severe (a new mineral is an Accept
unless the chemistry/cell/SG is completely wrong). It never overwrites a box a
human already marked.

### Preserving manual edits on rerun
The output docx in `review_out/` is your working copy; the source docx is
never edited. A rerun detects a hand edit via tracked changes (`w:ins`/`w:del`), a
non-tool comment, or body text differing from source, then **refreshes in place**:
backs up to `review_out/.edit_backup/<name>.<timestamp>.docx`, strips ONLY the
tool's own comments (author "PXRD Review Tool") + yellow highlights from a temp
copy, and re-annotates onto it — so tracked changes, your comments, text edits, and
your Accept mark survive while the tool's findings are made current. The strip is
atomic (temp copy; `out` is replaced only on success). `--force` rebuilds from
source (discards manual edits). The `_edited` vs clean output name is derived from
the (deterministic) `_is_clean()` verdict, so the path of a given entry is stable
across reruns and refresh-in-place still finds the right file. NOTE for maintainers: python-docx `.text` does NOT
include tracked **insertions** — never rely on it to detect a track-changes edit;
check `w:ins`/`w:del` in `document.xml`.
