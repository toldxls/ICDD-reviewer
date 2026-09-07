# Changelog

Notable changes to the PXRD review tool. The format loosely follows
[Keep a Changelog](https://keepachangelog.com/); the version is the `pxrd-review`
package version in `pyproject.toml`.

| version | | one line |
|---|---|---|
| [0.5.6](#056--2026-09-07) | 7 Sep | Every reading says which oracle vouched for it; recall measured by seeding faults; corpus runs in parallel; seven issues fixed |
| [0.5.5](#055--2026-09-05) | 5 Sep | The powder table checked against the cell — every calculated d recomputed from its own indices |
| [0.5.4](#054--2026-09-03) | 3 Sep | Five papers hand-checked, one rule each; the reader defects behind "column chosen by fit" |
| [0.5.3](#053--2026-09-03) | 3 Sep | The paper checker hardened on ~1,400 corpus papers |
| [0.5.2](#052--2026-09-02) | 2 Sep | A paper checked against itself in Manuscript mode; Fill ▸ from the paper; `pxrd update` |
| [0.5.1](#051--2026-09-02) | 2 Sep | Bond-valence tables corrected across `pxrd bv`, `pxrd tables` and the GUI |
| [0.5.0](#050--2026-08-26) | 26 Aug | `pxrd epma`, `pxrd gd`, `pxrd pxrd`; Tables mode becomes five tabs |
| [0.4.0](#040--2026-08-25) | 25 Aug | `pxrd bv`, `pxrd tables`, `pxrd refs`, and Manuscript mode |
| [0.3.0–0.3.5](#035--2026-07-16) | 13–16 Jul | The review GUI; the reference-title check writes a tracked change; two security passes |
| [0.2.0–0.2.9](#early-releases--2026-07-08-to-07-13) | 8–13 Jul | First packaged release; the docx write path made safe; the early checks |

## [Unreleased]

### Added — the water a structure can account for (issue #10, first increment)
An oxygen receives about 2 v.u. from its cations; one receiving much less is holding a hydrogen the
refinement need not have located, which is the point — H is unlocated in many structures, and this
reads the water content without it. `bv_check.water_from_structure` classifies every oxygen site and
counts the hydroxyls and waters per formula unit, scaling by a Z derived from the .cif's own formula
sum. `paper_extract.water_check` compares that with the paper's formula.

Measured before it was built on, and the numbers set what it may claim. Against 1165 sites whose
label states what they are (a refiner writes OH1, OW1, W1):

| | |
|---|---|
| a hydroxyl or water called ordinary oxygen | 2 of 227 (1 %) |
| an ordinary oxygen called hydrous | 301 of 1115 (27 %) |

The error is one-sided and gating on the structure's own valence index does not improve it, so the
count is a reliable statement that a site holds no hydrogen and only a suggestive one that it does.
Where a refinement did locate its H, that measurement wins over the inference. The threshold scales
with the formula (a difference of one H is noise in a formula carrying forty), and ammonium and
organic hydrogen are skipped since they never sit on an oxygen. **Note-grade**: it speaks on 11 of
115 corpus papers with a .cif, every one a structure whose H were not located, and says to check
what the paper reports about how the sample was treated — the owner's point, that the confirmation
is in prose a person reads rather than anything to code.

**Disordered hydrogen is counted per oxygen, by occupancy** (`_located_h`). Summing H sites is
wrong twice over: a hydrogen split across two alternative positions is two half-occupied sites and
one hydrogen, and hydrogen on ammonium or an organic group belongs to the formula but not to any
oxygen. Counting each oxygen's own H, as the plain sum of the occupancies bonded to it and capped at
two, gets both right. Rounding that sum, or flooring it at one, does not: it credits a genuinely
half-occupied hydroxyl with a whole hydrogen, and measured, that took the partly-occupied structures
from 90 % agreement with their own formula sums to 29 %. Against structures whose formula hydrogen
can only sit on oxygen, the count now matches the .cif's own formula sum for 39 of 45, and 5 of the
7 whose H sites are partly occupied.

**Two defects in that counting, found and fixed.** A hydrogen site sitting ON a symmetry element
stands for more than one atom — `Structure.neighbours` merges its images into one entry carrying
their count, and `_located_h` was dropping that count, so a water molecule whose oxygen lies on a
two-fold axis was credited with one hydrogen instead of two. And the classification recomputed each
oxygen's cation sum from the table cells *without* the cation-site occupancy that `compute` weights
its own anion sums by, so an oxygen bonded to a half-occupied cation looked fully coordinated: a
hydroxyl read as ordinary oxygen, which is the one direction this count is supposed to be reliable
in. Weighting it took hydroxyl- and water-labelled sites recognised as such from 93 % to 99 % (a
hydroxyl called ordinary oxygen: 15 of 227 down to 2), with the plain oxygens unchanged.

Not yet done: the physical arbiters (Gladstone-Dale and density at the ideal water content) and the
comparison against the ideal formula rather than the empirical one.

### Added — bond valence without a .cif, from the distances the paper prints
`bv.params` was the tool's worst number, 10 % verified, and not for want of a reader: 185 of its
215 readings had no oracle because nine papers in ten come with no .cif. `paper_structure`, which
rebuilds the whole structure from the coordinates table, a cell and a space group, reaches very few
of them — over a sample of the papers that cite a parameter set and have no .cif, it built a
structure for none of 60: the coordinates have to be read complete, the symbol has to be one the
operator table knows, and the right cell has to be picked out of the several a paper prints.

A **bond-distance table asks for none of that**. It states the two sites and the distance between
them, which is everything a bond valence needs. `pxrd_review/paper_bonds.py` reads that table off
the page — the multi-column layouts, the cation carried down its continuation rows, `×n` before or
after the distance (including the `×` that several journals' fonts deliver as a `3`), the labels
that carry a hydroxyl or water mark (`O10H`, `O12W`), the symmetry code superscripted onto an anion,
the two minerals a paper prints side by side or stacked — and computes the sums from it.

Nothing is inferred: no cell, no space group, no coordinates. So unlike `paper_structure` this is
not note-grade — **gated on the paper's own bonds adding up to the formal valences** (root-mean-
square deviation ≤ 0.15 vu), it reproduced 93 of 94 cation sums (98 %) of the corpus papers that do
have a .cif to score against; ungated it is 74 %, which is why the gate is there. Between 0.15 and
0.35 vu the reading is worth a note and no more. Anion sums are not offered at all: they need the
site multiplicities, which a bond table does not print.

Everything downstream is the existing checker — `bv_tables`, `bvs_site_tables`, `check_bvs_table`
and `check_bvs_sites` take the bond table's structure in place of the .cif's. Two rules are relaxed
for it, both because printed distances are rounded and a bond table states no multiplicities: an
anion row's sum is checked for its own arithmetic but never against the structure, and the parameter
set the paper cites has to be *plainly* refuted before it is called wrong (its U6+ sub-choice being
compared only where the paper states one).

Measured on the whole corpus, `bv.params` goes from 13 % verified to 19 % — 13 papers that had no
oracle at all now have a verdict, one of them a real finding (a paper citing Brese & O'Keeffe whose
table is Brown & Altermatt: 1 cell of 26 differs under the latter, 9 under the former), and 11 more
get a note. Validation harness: `tools/corpus_paper_bonds.py`.

### Added — the Gladstone–Dale constants, from the printed table at last
`data/gd_constants.json` held 65 constants, a third of them tagged "check" because they had been
recalled rather than read, and it had none at all for ammonium or for the rare earths beyond La, Ce,
Nd and Y. It now carries all 117 usable entries of **Mandarino (1981), Can. Mineral. 19, 441–450,
Table 7** — the table that paper says "should replace all former constants" — transcribed from the
scan the owner supplied and checked three ways: every row's printed molecular weight against the one
computed from its formula (all 114 agree; Pm2O3's 342 against 338 is the paper's own figure,
promethium having no stable isotope), sixteen values against the paper's own abstract, and the whole
file against the corpus.

Each entry now carries Mandarino's reliability indicator (H/M/L, or `?` for a value he derived by
extrapolation) and, where Table 7 prints one, the alternative value for a named class of minerals —
Al2O3 0.242 for sulfates and selenates and 0.176 for neso- and inosilicates, Fe2O3 0.268 for
silicates, and so on. Nothing chooses between those automatically; `--k` picks one.

**53 constants added** and **23 values corrected.** Two of the corrections were the owner's own
spreadsheet values, and both were settled by measurement rather than by deference:

| | file | Table 7 | papers reproducing their own published index |
|---|---|---|---|
| UO3 | 0.134 | **0.118** | 12 of the 22 corpus papers whose analysis carries UO3, against 5 |
| MgO | 0.225 | **0.200** | one more |

The 0.134 the spreadsheets use for uranyl minerals is not in Table 7, and nine papers reproduce
their own index with 0.118 where they do not with 0.134 (two go the other way, including the owner's
spanoite sheet). Both former values are kept as variants and `--k UO3=0.134` still reaches them —
`tests.test_gd` pins that route so the old sheets stay reproducible. **This one is worth the owner's
eye**: it is a working convention overturned on corpus evidence, not a typo.

Also corrected: Mn2O3 0.153 → 0.301 (0.153 is Bi2O3's value, so the old entry looks like a
transposition), WO3 0.152 → 0.171 and P2O5, SeO2, TeO2, TeO3 — the five revisions Mandarino's
abstract names explicitly — and Fe2O3, Cr2O3, NiO, CoO, Nb2O5, As2O3, Sb2O3, CO2, F, Cl, Br and the
rest of the 1976 values Table 7 supersedes.

With the constants in, `optics.n` goes from 45 % verified to **57 %** (110 → 146 of the 255 papers
that read an index): the whole of what was left of "no Gladstone–Dale constant for …" is gone but
three papers, and those three tabulate their analysis in elements for a sulfide or an organic.

### Fixed — Gladstone–Dale said "unverified" where it meant "could not read the analysis"
94 papers read a refractive index, a density and an analytical table and still would not verify, and
the fault was in K_C, not in the papers. K_C is a weighted mean over the WHOLE analysis, so a set of
constituents short of it gives a K_C short in the same proportion: 32 of those papers were computing
it from wt% summing to less than 95 % (a missed H2O row, a table given in elements), and 38 had a
constituent with no constant in `gd_constants.json`, silently worth k = 0, which is the same fault.

Every wt% set the paper offers is now tried — what the composition check reduced, each analytical
table the reader kept, and either of those converted from elements to oxides — and **the paper's own
stated compatibility index arbitrates**: a set that reproduces it has proved itself. Only when none
does is the completeness of the reading weighed, and then it decides whether to say `nooracle` with
the reason ("the analysis as read totals 80 % against the 99.7 % the table itself prints"; "no
Gladstone-Dale constant for Pr2O3, Sm2O3") or `unverified`, a real disagreement with the paper.

On the corpus: `optics.n` 43 % → 45 %, `D_meas` 58 % → 71 %, `D_calc` 62 % → 70 %, and 61 doubts
about papers become statements about this tool's own limits. The largest of those limits was data,
not code — and the constants above supply it, taking `optics.n` the rest of the way to 57 %.

## [0.5.6] — 2026-09-07
Every reading now says which oracle vouched for it, the tool's recall is measured for the first
time, and the corpus harness runs in parallel (21 min → 5). Seven reported issues fixed.

### Added
- **A record behind every reading.** `extract()` returns `fields`: value, where it was read, which
  reader read it, and what vouched for it. The oracles: the composition re-derived from the paper's
  own table (`check_composition`), the powder table against the cell (`cell_check`), the
  bond-valence table against the .cif (`bv_check_paper`), Gladstone–Dale for the optics (`gd_check`,
  reading the paper's own compatibility statement), the cell against its printed volume and its
  density from Z and the formula (`cell_consistency`), and Mindat for the name (`species_check`).
  A field is `agrees` / `disagrees` when an oracle adjudicated it, `unverified` with doubts,
  `nooracle` when nothing could check it. `check_paper` prints a `readers:` line and the two new
  sections. An n outside 1.3–3.0 or a density outside 1–25 is unverified before any oracle sees it.
  The compatibility index is never red: a strict comparison flagged fifty corpus papers, K_C at
  fault in most.
- **Recall, measured — the first time (`tools/seed_faults.py`).** Every threshold here was tuned by
  mining the corrected corpus for false positives, so every number was a precision number. The
  seeder injects a fault of known size into papers the tool passes and records whether the check
  fires. Corpus of 1092 papers, share that would reach a reviewer:

  | fault | 2 % | 5 % | 10 % | 20 % |
  |---|---|---|---|---|
  | a coefficient of the published formula | 0 % | 6 % | 69 % | 67 % |
  | one constituent's wt% | 0 % | 6 % | 31 % | 16 % |

  A powder d is caught 11 % at 2 %, 75 % at 3 %, 82 % at 5 %. A wrong stated basis is caught in 1 %
  of 280 papers, so that flag is dead as written (issue #10).
- **A structure from a paper that prints one** (`paper_structure.py`), for the ~50 % of papers whose
  coordinates are printed rather than deposited: coordinates as typeset, operators from the
  space-group symbol (new `symops` table, harvested from corpus .cif files), site elements from the
  occupancy column, charges from the paper's formula, and the cell chosen by lowest instability
  index. Gated on GII ≤ 0.15 and composition closure. **Note-grade throughout**: of 176 papers with
  both a printed structure and a .cif, 17 pass the gate and 49 of 54 cation sites (91 %) reproduce
  the .cif within 0.05 vu, so every line is `[unverified]` and the record never reads `agrees`.
  Papers with a bond-valence check: 48 → 60.
- **The corpus harness** (`tools/corpus_paper_extract.py`) reports a per-reader verified rate
  (`paper_checks_readers.csv`) and writes a per-paper record; `--baseline <json>` diffs a run against
  an earlier one, reader by reader, which is the A/B for a reader change with no worktree or module
  copy. `--jobs` runs the papers in worker processes: 214 s → 53 s on 183 papers, output folded in
  job order and byte-identical to serial, which is the acceptance test. A dead worker stops the run
  rather than marking some paper an error, since an OOM kill and a MuPDF segfault look alike.
- **Fill ▸ runs the checks.** Tables mode fills from `check_paper`: each input carries ✓ / ? / ✗ with
  the reason as its tooltip. It now leaves out, and says so: a name whose Mindat species lacks the
  paper's elements, a table totalling outside 85–112 wt%, an n or density out of range.
- `paper_extract.set_pages_reader(fn)` — a hook to swap the pdf page reader.

### Changed — the readers
- **Composition.** The analysis printed in prose before the formula is read whole, from the 1,400
  characters before it and in either order (218 corpus papers do this; only the last 200 characters
  were searched). Five more reader classes: an oxide block beside an apfu block, a value with its
  unit glued (`7.84%`), a site label whose bracket was lost, the anhydrous basis (stated − H/2), the
  tourmaline O + OH + F convention, and `10 cations excluding Si and P`. A Σ printed as `6=` is
  read; `4319 observed reflections` is no longer a basis. **The paper's own apfu column** is kept and
  used: where the wt% miss the formula but that column reproduces it, the reading is named as the
  tool's shortfall. Corpus: 587 → 605 of 713 reproduce exactly, 108 → 95 unverified.
- **The doubts yield when the reading proves itself.** A doubt says the tool may have misread the
  table; the reduction answers that itself. Reproducing every coefficient but one, over four or more
  elements, drops the doubts about the reading — hard doubts (parse failure, totals, a missing
  element, a circular basis, averaged analyses) still block. H and traces are filtered *before* the
  doubts are weighed, not after: counting a hydrogen the tool itself calls informational as one of
  the "two or more elements deviating" was suppressing single-element findings by itself. Recall on
  a mistyped coefficient 59 % → 69 %; corpus flags 12 → 13.
- **Powder.** An observed line with no calculated partner is looked for among every reflection the
  cell allows, so a table that leaves lines unindexed is no longer penalised (the median such table
  leaves 29 %): `pxrd.obs` verified 35 % → 62 %. A cell statement that lost its angles gets them
  back — a Symbol-font β reaches the text as a plain `b` — and 39 more tables follow their cell, 49
  remain of 88. Lines fitting another cell the paper states are that phase's; more than five
  outliers is a doubt. **A calculated d is flagged only 2 % or more off its cell** (`_CELL_RED`);
  below that it is a note.
- **Densities and the cell.** A powder cell quoted without Z borrows the one the paper states
  elsewhere or the .cif's (200 corpus papers printed a Z the reader had not attached).
  `optics.D_calc` verified 20 % → 62 %, `D_meas` 31 % → 58 %, cell 72 % → 74 %. The D_calc red line
  is **retired to a note**: every one drawn dissolved on inspection. Mindat's cell vouches
  note-grade where nothing in the paper can.
- **Basis.** An inferred basis that reproduces every coefficient is verified. A stated basis that
  fails where another reproduces cleanly is a finding — guarded, and after all fourteen corpus cases
  proved to be the tool's own conventions, those are now rules (water/OH, `9 O` less the water,
  element tables, `O + S`, ammonium, within tolerance, both bases stated). It fires nowhere on the
  corpus; the record goes 41 % → 74 % verified.
- **Bond valence.** BVS columns and transposed grids are read (`bvs_site_tables`,
  `_site_rows_from_grid`, `_maybe_transpose`) and checked site by site (`check_bvs_sites`). A
  paper's own site names map onto the .cif **by coordinates**, or by its printed bond lengths where
  it gives no coordinates table. A .cif that states no oxidation numbers takes them from the paper's
  formula, per element and per site for a mixed-valence one. In a two-mineral paper only the .cif's
  own mineral's table is compared. A table that differs throughout is summarised by column with
  direction and size rather than dismissed. Subsets: tables checked 30 → 46, clean 7 → 15, none lost.
  Reader details fixed on the way: `O8(OH)` row labels, space-separated two-value cells, a Σ that
  includes the hydroxyl's own H, and a tie going to the row above.
- **PyMuPDF is imported by its own name**; the deprecated `fitz` alias is gone, floor `>=1.24.3`.
- **The bond-valence parameter file is parsed once**, not six times per paper. A tidy-up, not a
  speed-up: 214 s → 211 s on 183 papers, inside the noise.

### Fixed
- **#1** a stale verdict could overturn the dismissal a reviewer had just made, and the comment they
  dismissed was written back into the docx on every launch.
- **#2** the old two-column template's instrument fields parsed as the next field's label, so 644 of
  662 entries silently abstained from every instrument check and reported clean. The radiation block
  matched only the new template's spelling, leaving the anode blank.
- **#3** a page scan that timed out was cached as an answer of zero pages: a blank pane behind a
  `pdf ✓` badge, permanently. **#4** the entries endpoint read shared state unlocked, so a folder
  switch mid-poll stranded the dashboard on the old folder. **#7** an in-place run locked only the
  first folder while discovery is recursive. **#8** Windows papercuts. **#9** documented what a Word
  Reject does not persist. **#5**, **#6** verified already fixed.
- **Two reader faults the recall work exposed**, both wrong before and merely hidden: tourmaline's
  boron site was counted as an element, putting every tourmaline paper's boron 1.0 apfu high; and
  nothing checked that a constituent's mean lies inside its own printed range, which it does not in
  5 papers of 109.
- **Six defects from a cross-file review**: Mindat's HTML ideal formula was mass-read by a token scan
  that dropped every subscript (abelsonite 86 instead of 519); a two-origin space group is noted as
  such; Fill ▸ kept a .cif chosen by a name Mindat had rejected; the paper's own structure was shown
  under whichever .cif was selected; the `readers:` line was anchored to a page; a failed
  paper-structure build left its temp directory behind.

### Not shipped
- **A layout model (docling)** was built behind an extra and measured: as a replacement it loses
  more than it gains (cell-consistent calculated rows 89.6 % → 85.3 %, the largest tables truncated),
  as a fallback it adds lines to four papers and takes none away, it read the coordinates tables
  worse, and a 6-page supplement took 16 minutes. Removed; `set_pages_reader` stays as the hook.
- **A hosted-model reader** was built, measured against the same oracles, and removed: a paper under
  review is unpublished work and a public tool must not offer to upload one. Every reader is local.

### Known limits
- 923 corpus papers have no .cif at all; of the 40 whose .cif shares no I-number, matching by cell
  finds three. The bond-valence gap is in the files, not the reader.
- Manuscript mode's ground truth is the .cif, Mindat and the paper's own arithmetic: a manuscript
  with an internally consistent error and no .cif still passes.

## [0.5.5] — 2026-09-05

### Fixed — three things the owner hit testing 0.5.4
- **"? look" on a calculation finding did nothing.** The composition and bond-valence findings of a
  paper have no paragraph in a docx to jump to, so the button returned silently. It now opens the
  paper's page (the analytical table's page, or the bond-valence table's) rendered with the
  finding's labels highlighted, in an overlay; the button says which page. A finding with no page
  says so in the status line instead of staying mute.
- **A manuscript .docx is now a paper for the Tables mode.** "from paper" lists the folder's
  .docx files with the pdfs, and Fill ▸ reads a manuscript the way it reads a paper: its tables
  become pages of words (caption paragraph first, one line per row, cells at their column) so the
  analytical-table reader, the powder-table reader and the transposed-table reader run unchanged;
  its text feeds the formula, basis, optics and parameter-set readers. The manuscript's bond-
  valence table is checked against the same mineral's .cif as part of Fill ▸ (shown on the Bond
  valence tab, `pxrd bv --table` in the GUI at last), and the Manuscript mode runs the composition
  and bond-valence self-checks on a .docx as it does on a .pdf.
- **Browse took 3–4 s to show the folder dialog.** The AppleScript activated osascript itself as a
  foreground app on every click (2 s alone, measured). The dialog is now Finder's: activating
  Finder takes 0.1 s and the panel still comes up frontmost with keyboard focus.

### Changed — the powder-table header, rethought on the corpus
- **The header of a powder table is read through a vocabulary layer** instead of one regular
  expression. Labels with footnote marks or letters (`dcalc*`, `Icalca`), `dcal`/`Ical`, `Dclac`,
  `Imeass`, `Iest` (estimated by eye), `I/I0`, `I/Imax`, `100·I/Imax`, `Irel`, `dhkl`, a label split
  from its nature (`dhkl calc`, `I (calc.)` — the column sits between the two words), `Dobs`/`Dcalc`
  with a capital D (a bare `D` stays a difference column), and units as their own words are all read.
  A bare `d` or `I` is calculated when the caption says the table is ("Table 4. Cont." inherits
  Table 4's caption), observed otherwise. 2θ columns are skipped.
- **`h k l` merge by sequence, however far apart the columns are set** (`h k i l` for a hexagonal
  table, the redundant i dropped); the old 30 pt limit left wide headers as three columns and the
  table to the token-order fallback, which pairs intensities into index triples like (0, 22, 8) for
  every layout that puts the indices first. A block now begins at each `h k l` when the indices lead
  and ends at each when they trail, so a row's d is never paired with the block beside it.
- **An index column owns the index-like tokens out to the midpoints with its neighbours** (the three
  digits under one `hkl` word spread wider than the word); rows are confined to the header's width,
  so the prose of the other column of a two-column page no longer ends a table after three rows; a
  header line with two foreign words, or a first row with them, is a sentence and not a table;
  `001`, `2.1.10` and `01 1` index forms are read; a d value that landed in an intensity slot (the
  header names the columns in the other order than the numbers stand) is swapped back.
- Validated on 1006 corpus pdfs against the previous reader: observed lines 15.7k → 19.8k,
  calculated 13.9k → 24.9k, entries with an index beyond ±30, an intensity above 1000 or a d outside
  0.5–40 Å 1017 → 442; twelve papers lose lines, ten of them garbage the fallback made up; papers with
  no powder table read at all 379 → 238. Still unread: two-line headers (`h k l` on one line, the
  d/I labels on another), 2θ-only tables, and which sample of a multi-sample table is the holotype.

- **A second reader types the columns by what they hold**, for the pages where no header line is
  recognised (a two-line header with `h k l` on one line and the d and I labels on another, a
  table with no header, a spelling the vocabulary does not know): a column of floats between
  0.5 and 40 Å that falls down the rows is d, one bounded by 100 is an intensity, three
  neighbouring columns of small integers are `h k l` (four with |h + k| = |i| are `h k i l`; three
  digits set so close they cluster as one column; `001` and `2.1.10` as one word), floats that
  rise are 2θ and are skipped; the header words above, when any, say which d and I are observed
  and which calculated, else two d columns are told apart by their decimals and a lone one by
  the caption. A block without indices needs a header word for its d (a bond-length or chemical
  table also has a falling float column); a second sample's columns beside the first are left
  out. Glued signed indices (`0-1`, `-1-3`) are split for both readers. It replaces the
  token-order fallback, which made up index triples. Against the header reader alone, on the
  694 distinct corpus pdfs: observed lines 14.1k → 15.2k, calculated 17.9k → 18.4k, suspect
  entries 316 → 30, and — the check that matters — for the 4,900 calculated rows of papers whose
  .cif is in the corpus, d recomputed from the cell and the parsed h k l agrees with the parsed
  d within 0.5 % for 78 % of rows, as before (the rest are largely cells in another setting).
  Three papers lose lines, one of them a table whose rows the pdf splits across baselines.

### Added — the powder table against the cell
- **Every calculated line of a paper's powder table is a statement about the cell**: d follows
  from h k l and the cell parameters exactly. `check_paper` (the Manuscript mode's findings,
  `pxrd paper --check`) now recomputes it for every indexed line — against the .cif's cell when
  the folder has one and it reproduces the table, else against the cell the paper states (the
  powder one first; `a` and `c` alone are tried as tetragonal and as hexagonal) — and names the
  isolated lines that do not follow within 0.5 % (up to 15 %): a mis-indexed or mistyped line,
  red in the Manuscript mode, its d the `? look` term. A table whose lines sit 0.5–1.5 % off
  throughout was computed with a slightly different cell, and one that follows no cell the paper
  gives is one grey note, not fifty red lines; a line off by more than 15 % is the reader's own
  pairing, counted and left out; a .cif whose cell reproduces the table worse than the paper's own is reported as another
  setting or determination (the table is then checked against the paper's cell). An observed
  line with no calculated line within 0.5 % is noted, unverified (a typo, or a line the table
  leaves unindexed). A sign the pdf extraction lost (an overbar) is tried before a line is
  blamed. Works the same for a manuscript .docx. `pxrd_table` can return the pages its lines came
  from; the token-order fallback that used to make up index triples is gone.

### Fixed — what the review of the above found (ten findings, each reproduced)
- The toolbar **Fill ▸** button never worked: it passed its click event as the paper key, which
  reset the select, so it always answered "pick a paper first" (the Manuscript mode's → Tables
  button was the only working route). Pre-existing; fixed.
- `pxrd paper manuscript.docx` (without `--check`) crashed formatting the table's page, which a
  manuscript does not have.
- A **signed two-digit index** (`−10`) in a manuscript's powder table pushed the `h` and `k`
  header words apart and silently dropped every calculated line. The synthetic columns are
  tighter, and the digits under any of the three `h k l` header words now count as indices
  rather than going to the nearest column centre — which also reads the calculated lines of
  nine corpus papers whose wide `h k l` block lost them the same way (observed lines unchanged
  on all 1006).
- Text inserted under **Track Changes** was invisible to the formula / basis / optics readers
  (python-docx sees only direct-child runs); tracked insertions are now read, deletions dropped,
  as the citation checker already did.
- A manuscript's data files are named `<stem>_docx_*`, so a revised `X.docx` beside the
  published `X.pdf` no longer overwrites the paper's `X_paper_*` files (or the reverse).
- The Manuscript mode's **bond-valence check** distinguishes four outcomes instead of two: a
  table that names none of the .cif's cation sites is reported as a stranger's (the folder's
  only .cif is no longer scored against it — the membership rule the pdf reader always applied);
  a table whose labels match no bond (Ow/OH vs O) reports that and still checks its row and
  column sums, instead of "no table found"; a .cif that will not load is reported (on Fill ▸
  too, which used to drop it); a manuscript with nothing to check stays silent.
- **? look** on a composition finding highlighted the bare element symbol, which PyMuPDF
  matches case-insensitively inside every word on the page; it now highlights the constituent
  as the table writes it (`SiO2`).
- **Browse**: the Finder dialog is an Apple event, which macOS gates behind an Automation
  consent. Denied, the old route is used instead of reporting a Cancel forever; a real Cancel
  (−128) is told from a failure, and an unanswered consent sheet times out with a message.

## [0.5.4] — 2026-09-03

### Changed — five papers hand-checked with the owner, one rule each
- **Ferriandrosite-(Ce)**: a header with "wt.%" over columns B–D on one line and "Mean" over
  column A on the next put the whole default read on column B; "Mean" now outranks "wt.%" and the
  leftmost wins. And the owner's policy: when the Mean column reproduces the formula it is the
  source and no other column is tried; named columns (domain letters a sentence assigns to the
  headline mineral, sample codes, a holotype locality, the Levinson suffix, a table legend) are
  consulted only when the mean does not reproduce. Domain phrases belong to the nearest mineral
  name in their sentence ("… (domains A–C) and associated vielleaureite-(Ce) (domain D)").
- **Håleniusite-(Ce)**: the abstract's formula swaps Sm and Nd against the body's. Every formula
  sentence is now read; the one the table reproduces is the reference and an abstract that
  disagrees with it is flagged with the differences ("Nd 0.04 vs 0.148; Sm 0.15 vs 0.028 …"). A
  second formula in the body is a note (an alternative normalisation). The basis "O þ F ¼ 2 apfu"
  reads.
- **Calcioancylite-(La)**: "the empirical formula was calculated without Al" is read and Al left
  out with a note; the factor gate holds back only ratios near a clean factor (½, 2, 3, 4, 10) or
  beyond 0.4–2.5, so the paper's Nd0.10 against 0.057 from its own Nd2O3 is reported.
- **Heimaeyite**: "the total composition of the sample results in …" is a formula of its own kind
  and is verified; correction wording (impurity, admixed, subtracted, corrected for) near the final
  formula marks it as not re-derivable from the table, and the report says so.
- **Fluorpyromorphite**: a two-line cell prints the mean of column 1 on the line above the label
  and the range beside it; both lines are folded into the row. A table legend "1, 2, 8 –
  fluorpyromorphite (1 – holotype, …)" supplies column keys, the holotype's first. A formula
  candidate that is a prefix of another (cut by a page break) is dropped, and a formula is
  preferred only when its check is clean and verified.

### Changed — the reader defects behind the "column chosen by fit" verdicts
Ten unverified papers read by hand: in nine the paper does say which column or row is the mean of
the new mineral and the tool failed to read it, for general reasons that are now fixed:
- **Value cells**: an esd on an integer ("Mean 29(3) 67(3)"), a parenthesised value ("SO3 (13.16)"
  = total S as SO3), a footnote mark glued to the value ("11.41c", "3.19*"), an anion label with
  its charge ("S2–", "Cl–"), hydrosulfide ("HS" wt% → the sulfur). A row that reads n.d. in the
  first column but is measured in the others keeps its other columns (as 0 / value, columns
  aligned) for the named-column and by-fit reads; it still has no mean of its own.
- **Transposed tables**: the apfu columns beside the oxides ("CaO MgO MnO … total Ca Mg Mn") are
  not constituents; a duplicated constituent keeps its first column.
- **Which column**: a legend of the form "zoharite (3—aggregate, Figure 3C)" names column 3, and a
  legend number is explicit (before the name-headed span, never averaged); a group's own Mean cell
  ("Madagascar: 5 6 13 Mean (n = 3)") beats averaging its spots; the holotype's words stop at
  "cotype / paratype" in the same sentence; a constituent repeated below the Total is the apfu
  block and never overrides the wt% row (also in the named-column read).
- **Which table**: a trace-element table (µg/g, ppm) is skipped; a bond-valence or coordinates
  table alone is no analytical table (the check says so instead of reading it).
- **Formula sentences**: braces are brackets ("{[(NH4)2.13K0.87]Σ3.00(H2O)}{…}"); a charge
  superscript typeset between the digits ("Fe0. 2+ 20" = Fe2+0.20) is rejoined; a formula the
  sentence cites from the original description ("formula of koragoite (Voloshin et al., 1997) … is")
  goes last; a formula that rests on site scattering / the structure refinement is the structural
  one whatever the sentence calls it; so is one "based on the structure refinement" (seaborgite's
  abstract); a charge whose sign the text layer lost ("S6+ 2.88S2 2.60" = S2− 2.60) is read as the
  charge, not a count (dinilawiite). A run of apfu in prose ("K0.89 Na0.05 …") is not a composition.
- Corpus (975 papers with a table and a formula): 816 reproduce exactly (84 %, from 786 this
  morning), 140 unverified (from 173), 19 flags, every flag vetted by hand.
- **Review of the above (medium effort, eight confirmed findings, all fixed)**: only a bare
  element repeated below the Total is the apfu block (an oxide there is the FeO / Fe2O3 split);
  n.d. cells are 0 in the positional values only, never averaged into a point-column mean or
  taken as an s.d.; a two-line cell's continuation must sit under the row's values (a "Σ" / "Sum"
  totals line is a total, not phantom columns); a transposed header is judged as printed, then
  only a mostly-repeated one is rejected; a figure legend is not a table legend and a legend
  number needs a numbered header; legend numbers keep the legend's order (holotype first);
  "calculated without Al" is applied to every column and candidate table, not only the mean; the
  abstract / body decision searches the same normalised text the formulas were cut from.
  Vetting the corpus after those fixes: a caption like "Bond-valence analysis" is structural (the
  word "analysis" alone does not make a table analytical), a composition given in the text beats such
  a table, and two formulas for two samples ("beraunite (FR)" / "beraunite (NM)", "the original
  sample") are not an abstract disagreeing with the body.

## [0.5.3] — 2026-09-03

### Changed — the paper checker hardened on ~1,400 corpus papers
The composition check (a paper's empirical formula re-derived from its own analytical table and
basis) went from about a third of the checkable papers reproduced exactly to well over half, with
no false flags, by reading more of what papers actually print:
- **The formula sentence.** The formula is now the first formula-shaped run after "empirical …
  formula" (is / = / : / being / as follows / can be written as / a Russian "эмпирическая формула"),
  up to 1,200 characters long. Notation read: `Cu+ 0.99` charges without a digit, bare `Σ1.01` sums
  without a bracket, a Σ printed as `6` before two-digit and integer sums (`)616.15`, `)62`),
  tourmaline-style site labels (`X( Y( Z( T[ V( W[`, also glued: `ZAl6.00[`), sites named after
  their element (`Mg1(Mg1.42…)`), a font that prints decimals as colons and brackets as `ð Þ`,
  and nested `[(…)Σ16.15 Ca4.85]Σ21.01` sums (a Σ group counts its atoms in the enclosing sum).
- **The table.** A footnote letter printed as its own word (`TiO2 a 15.36`), `Sb`/`Sc` no longer
  split into S + footnote, `NaO` / `Fe2O` / `P2O` lost subscripts, a *Mean* that is the first
  column (the S.D. was being taken when the header was centred over a wider cell), `Aver`
  headers, bare-element rows below *Total* and repeated constituents at under half the value
  (the apfu block), and the **transposed layout** (constituents across a header line, analyses
  down the rows, a Mean/Average row or the rows' average).
- **Several minerals or samples in one table.** When the mean column does not reproduce the
  formula, the other numeric columns (or the other Mean / analysis rows of a transposed table)
  are tried; the one that reproduces it is used and named ("column 3 of the table … a normalised
  column, or another sample or mineral").
- **A bracketed group with a stated Σ is a basis candidate** (`(Pb0.93Ce0.43…)Σ2.000` → Pb+REE = 2;
  two sites of the same elements add up).
- **Species evidence from Mindat** (owner's suggestion): the ideal formula in the offline cache
  supplies oxidation states. An oxide the table reports at another charge than the paper's
  formula (or, failing that, the species) is re-reduced in the other form — FeO as Fe2O3 — and
  adopted only when it reproduces the formula better, with the evidence named; a formula that
  writes an element at a charge the species never has is noted; an element essential to the ideal
  formula that neither the table nor the formula carries is noted; and when no formula sentence
  can be read at all, the table is reduced on the stated basis and the derived formula printed
  for the reviewer to hold against the paper's by eye (unverified). All of these are CALC NOTEs,
  never flags.
- **Rows with no value** (2026-09-03): a subscript in `P2O5` or `Fe2O3` deepens the word's box
  so its vertical centre drifts from its numbers and the row came out as a label with no value.
  Words now share a line when their top, centre or bottom agrees — this alone recovered
  bakakinite, koryakite and barronite. Also `Fe2O3(tot)` / `H2O(calc)` qualifiers, `Fe+3 0.23`
  (sign before the digit), the `(ΣMe = 3.97)` suffix, `Ln0.10` / `REE*0.01` grouped lanthanides
  (compared with the table's La–Lu oxides summed), `Cu12(` as a formula start, "crystal chemical
  formula" wording, soft hyphens, nested groups without a Σ counting their atoms, structure tables
  (Site Atom x y z Ueq, or Si Si Si rows, or 0.8641-style values) never taken for the analytical
  table, trace-element rows in ppm dropped, and **every candidate table kept**: when the first
  choice lacks an element of the formula, the table that carries them all is tried and named
  ("the table on page 11 reproduces the formula"). One lost bracket in the pdf text with every
  coefficient agreeing is a note, not a doubt. Later the same morning: a subscript digit set as its
  own glyph (`B2O` + `3`) is glued into its parent and a superscript footnote number dropped; the
  word "total" in the other page column's prose ("A total of 16 scans") no longer passes for the
  Total row and breaks the block (natromolybdite lost its Na2O row that way); a composition given
  in the running text ("MnO 14.78, Ce2O3 34.19, …, total 100.00 wt.%") is read as a table, the
  ideal formula's "requires …" list excluded; `Fe2.5+ 0.25` charges; a formula followed by
  `= (structural form)` is cut there; a vacancy printed as `h` (font). Lines are now built in two
  passes (words on one baseline first, then the top/centre/bottom merge), so a table row's numbers
  are never captured by the other page column's prose line 3 pt away (åsgruvanite's Yb2O3). The
  formula is cut before a capitalised prose word ("Crystal B" gave a spurious Cr); a mineral name
  may start with a non-ASCII capital (Åsgruvanite was being called calcite) and rock names and
  English -ite words are excluded; the overall fit is judged on the major cations (≥ 0.1 apfu) —
  a trace at 60 % off is reported on its own (merelaniite's Mn 0.05 is the wt% copied as apfu).
  **Captions** (owner): a human finds the analytical table by its caption, and it is Table 1 or 2 in
  almost every paper — candidates are now scored by the "Table N. …" line up to eight lines above
  (+ for chemical / composition / analytical / EPMA / microprobe / wt%, − for coordinates, bonds,
  powder, crystal data, refinement, Raman, IR; + for Table 1–2, − for Table 4 and up). Other rules
  of the same batch: an ideal formula (integers and halves only) is never taken for the empirical
  one; a trace below 0.1 apfu is a finding only when off by half or more; a column chosen by fit,
  a fallback table chosen for its elements, a table with two or more samples fitting poorly, or a
  table whose header was not recognised — all unverified, never flags; alternative columns must
  carry a plausible total (an s.d. column is not a sample); a group basis only when its elements
  occur nowhere else in the formula (`Si4(S1.61Si0.32…)`); element-named site labels only when
  numbered from 1 (`Mg1(…)Mg2(…)`, but `Si4(` is a count); a Σ mismatch in a pure anion group is a
  note, the cations are checked regardless; a vacancy printed as `A`; `(OH)3.524.13H2O` with the
  hydrate dot lost; a constituent listed twice tries the other value.
  A second sweep the same afternoon (owner: "so many remain unverified"): `<0.01` bounds, ranges
  inside a formula (`Ge0.91-0.97`), `(Th,U)4+ 0.54`, a vacancy glyph lost before its count, a Σ
  printed as `P` (only where the value is the group's own sum) or as a bare `S` when the table
  has no sulfur, `(PO4)22H2O` = (PO4)2·2H2O, a `(SREF)` tag, `Σ=48.49`, `·nH2O`, `(Sample 1)`
  after the formula, water inside a bracketed group counting toward its Σ, `(SO4)5.01` always a
  multiplier (S1+O4 = 5 made it look like a sum), sulfosalt cells up to 250 apfu, near-ideal
  formulas with two-decimal coefficients (Au3.00Tl1.01Te2.00) accepted, "the chemical formula of
  X is" as a trigger, Cyrillic lookalike letters in constituents (`Na2О`), the point-averaging
  rule never on a table whose first column is the mean (a powder table sharing the lines was
  being averaged in), a group basis only from analysed elements, and the "deviate overall"
  gate only when two or more major cations are off — one genuine slip stays a finding
  (lauraniite computed S from an SO4 column with the SO3 molar mass). Then, from the flags that
  pass produced: an integer after a bracketed group that equals the group's own cation sum is a Σ
  whose glyph was lost (`(As3.99S0.01)4`), the Σ-as-P rule matches brackets properly so it also
  works after a nested group, a basis prefix such as `(O + F)` before the formula is dropped, and
  a major cation off by a factor beyond 0.6–1.6 is a multiplier or notation misread and is
  reported as unverified — a genuine slip in a paper is a modest deviation, never a factor.
  **The headline mineral's column** (owner): a paper's table often holds other phases or several
  samples, and the caption, the header or the text says which analyses the formula rests on.
  The column is now chosen by that evidence before any fitting: the header cell carrying the
  headline mineral's name, a sample or specimen code the formula sentence cites, a domain or
  crystal letter, a locality named next to "holotype" anywhere in the paper, or the number of
  analyses the sentence states (`n = 10`); an IMA code or name centred over Ave | Std | Range
  selects that group's value column. A transposed table is matched by its row labels. A total
  row (Mn2O3 for both localities) followed by the split (MnO2 + Mn2O3 for one of them) is dropped
  per column, only where the split has a value. Footnote numbers on constituents (`V2O31)`) and
  a Total of 8.00 read from the apfu block are handled. Each starting column (the named one and
  the plain mean column) runs through the same chain — best basis, another table carrying every
  element, the other columns, the oxide forms — and the named column wins only when it leaves no
  residual or the mean column does not either; an author's surname next to "holotype" or a
  locality mentioned in passing can otherwise select the wrong column. A caption sharing its line
  with prose ("… Table 1. Composition of wortupaite") is cut from the header cells at the "Table N."
  token. A trace in the paper that reads five times larger is a factor problem, not a finding.
  Later: `(PO4)3.02` flattened to `PO43.02` in the pdf text is re-bracketed; H never counts as
  factor-like (it is informational); the caption score rewards the headline mineral's name and
  penalises another mineral's (a supporting phase's table from other localities was winning);
  the running head at the top of a page is never a column header; a per-analysis table averages
  only the columns of the same phase as column 1 (calcite columns beside fluorpyromorphite were
  being averaged in); more formula wording — "empirical mineral formula", "gives / yielded /
  resulted in the formula", "with an average formula of", a crystal-data table's "Chemical
  formula …" — and round coefficients are accepted after an explicit "empirical formula"
  (uroxite); zero-width spaces inside a formula's glyph runs are stripped (a journal that
  letter-spaces its formulas). More evidence for the column: the headline's Levinson suffix
  labelling the columns (`(Nd)1 (Y)2 (Ce)3`), a wt% list inside the formula sentence itself
  ("Ni 17.09, Fe 9.76 … which corresponds to"), sample codes such as `A-WP1` or `NRM19331765`
  anywhere in the sentence; the averaging span of a named group is bounded by the neighbouring
  labelled columns. Parser: `(N3C2H2)` is not the ICDD `Fe3 C1.01` charge notation; a one-cation
  group with no decimals inside (`(AsO3OH)5.97`) is always a multiplier; a Σ on a one-cation anion
  complex (`((As0.95Sb0.08)O4)Σ2.03`) is the number of such groups; the headline mineral is the
  candidate the paper uses most, read from the first 3,000 characters.
- The wt% total gate is 85–112 (analyses far from 100 are common, the owner notes). Two more
  gates: a column chosen by fit is never flag-grade evidence (its residual disagreement is reported
  as unverified), and a table constituent at 1 wt% or more that the formula read does not carry
  means another (simplified) formula sentence was read — unverified; and a table of several
  samples (two or more mean columns) whose first sample fits the formula only to 2 % or worse is
  unverified (the formula may belong to another sample). A FeO total row followed by its FeO /
  Fe2O3 split is dropped (Fe was being counted twice).

## [0.5.2] — 2026-09-02

### Added — a paper .pdf in Manuscript mode: the paper checked against itself
Manuscript mode now takes a paper `.pdf` beside the `.docx` manuscripts. Besides the citation
check, the paper's own numbers are re-done and reported as findings: **CALCULATION** where a
number does not follow (a coefficient of the empirical formula that the paper's own wt% table and
stated basis do not give; a bond-valence cell or Σ that the `.cif` does not give under any
parameter set) and **CALC NOTE** for what was re-done and how (the basis used, the set the paper's
table agrees best with vs the one it cites). The `.cif` of the same mineral is found in the folder
by name. A **Tables ▸** button carries the paper into the Tables mode (Fill ▸). `pxrd paper x.pdf
--check [--cif x.cif]` prints the same. `pxrd_review/paper_extract.check_paper` is the engine;
`tools/corpus_paper_extract.py` runs it over a corpus into `review_out/paper_checks_*.{txt,tsv}`.
A confidence gate keeps the flags honest: a composition finding is raised only when the formula
parsed cleanly, at least three constituents were read, their wt% add to a plausible total, the
other cations agree, and every element of the formula was found in the table; anything short of
that is reported as *not verifiable, because …* and never as a fault. Extractor hardening from the
corpus: the value under a *Mean* header when a table carries several samples, `n.d.` rows dropped,
apfu rows beside oxides recognised by value not by the mere presence of an oxide (a sulfide table
with an H2O row keeps its element rows), site labels and REE in formulas tolerated.

### Added — Fill from paper, and the calculation workbooks
The Tables mode can now be filled from the paper itself: pick the `.pdf` in the folder and press
**Fill ▸**. `pxrd_review/paper_extract.py` reads the analytical table (mean, range, s.d., standard
per constituent — through two-column layouts and a journal font that prints `=` as `¼`), the basis
the authors normalised on ("on the basis of 7 O apfu", "U + S = 6"), how they treated the
constituents a probe cannot give (H2O by difference / from the structure / for charge balance, the
Fe3+/Fe2+ split), the mean refractive index and the densities, the bond-valence parameter set they
cite, and the powder table. The means become `review_out/<paper>_paper_epma.csv`, the powder lines
`<paper>_paper_obs.txt` / `_calc.txt`, and the tabs' inputs are set from them — basis, additions,
standards, n, D, parameter set — with the paper's own sentences shown in the status line, so the
reduction re-does the paper's calculation the paper's way. `pxrd paper x.pdf` prints the same.
Two workbooks carry the whole calculation as live formulas for checking a paper's procedure:
**`pxrd bv --xlsx`** / the Bond valence tab's *Write .xlsx* (every bond with R0, b and
s = EXP((R0−R)/b), multiplicities and occupancies, the cation and anion sums built from those
cells, the hydrogen bonds with s = (d/2.17)^−8.2 + 0.06, the parameters and the table note), and
the EPMA workbook now ends with a **method** sheet quoting the paper's basis and calculated-
constituent statements next to the basis actually applied.

### Added — the version chip, Update now, and `pxrd update`
Clicking the chip opens a small panel with **Update now**: the server pulls the checkout or
pip-installs the newer version, then restarts itself with the same token and port, and the open
tab reloads on its own; on Windows a helper window waits for the tool to close, runs pip and
reopens it (the running launcher locks its own executable). Failures show pip's output and the
command to run by hand.
The GUI header now shows the installed version. At launch the server asks GitHub once (two
anonymous GETs: the version on `main`, which the recommended install line tracks, and the latest
release) and the chip turns amber — `⬆ v0.5.1 → 0.5.2` — when something newer exists; its tooltip
carries the upgrade command and the release-notes link, and a click copies the command.
`PXRD_NO_UPDATE_CHECK=1` turns the check off; offline, the chip says so and links the releases
page. **`pxrd update`** installs the newer version with pip (`--check` only reports, `--release`
takes the release's hash-pinned wheel instead of `main`, `--force` installs when nothing is newer);
it never installs over a copy that is already current or ahead, and on a git checkout (an editable
install, the developer's case) it runs `git pull --ff-only` there instead of pip, which would replace
the live link with a plain copy; the chip's tooltip names `pxrd update` in every case. On Windows it hands pip to a fresh
console, because the running `pxrd.exe` launcher cannot overwrite itself.

## [0.5.1] — 2026-09-02

### Fixed — bond-valence tables (`pxrd bv`, `pxrd tables`, the GUI's Bond valence tab)
- **Hydrogen bonds from O···O distances.** The tables (and the anion sums) now carry the hydrogen
  bonds the way the mineral descriptions print them: strengths from the donor–acceptor O···O
  distance, s = (d/2.17)^−8.2 + 0.06 (Ferraris & Ivaldi 1988; the relation in the owner's BV
  spreadsheets — reproduces the szilagyiite, cadsulfohite and svornostite tables to 0.01 vu).
  With H atoms the pairs come from the `_geom_hbond` loop (else the H positions); **without H
  atoms** — the case the tool used to ignore entirely, leaving H₂O rows at Σ ≈ 0.3 — the pairs are
  *proposed* from the O···O geometry (donors from the labels or the valence deficits; no
  polyhedral edges; ≥ 80° from the donor's cations; acceptor room; shortest first, each contact
  once, H–O–H geometry, symmetry pairs together; the larger deficit accepts) and marked as a
  proposal: 81 % of the refined hydrogen bonds in the corpus CIFs are recovered blind.
  `--hbonds oo|h|none`, `--hmax`, `--donors OW1=2`, `--hb OW1>O2` (CLI and GUI). Donated O–H
  valences are reported but not deducted (the owner's convention); the text report shows the full
  accounting in `O–H` / `Σall` columns.
- **Footnote named the wrong parameter set.** Brown's `bvparm2020.cif` files a value under the paper
  that derived it, so Brese & O'Keeffe (1991) — which reprints every Brown & Altermatt (1985)
  value — was footnoted as "Brown and Altermatt" for most cations, and the note did not change
  between BO91 and BA85. The note now follows the set asked for and cites every set used per ion
  pair ("… from Gagné and Hawthorne (2015); U6+–O from Burns et al. (1997); Ca2+–F from Brown and
  Altermatt (1985)"), with short citations instead of the file's journal strings; "Multiplicity is
  indicated by ×→↓." leads it, as in the owner's tables.
- `--u6 burns|params` (GUI: "U⁶⁺ from set") — U⁶⁺–O from Burns et al. (1997) stays the default,
  but the owner's recent tables use Gagné & Hawthorne for U too.
- **`pxrd epma --check`** replicates the published empirical formula of an ICDD entry from its
  Analysis field (mean wt% + the formula in the ICDD notation, whose traps — `)S2` multipliers vs
  `Σ` sums vs sulfur, `Fe3 C1.01` charges, `OH1.09`, vacancies, hydrate water — are all read) on the
  basis inferred from the formula, and reports the coefficients that do not follow from the numbers
  and the transcription faults a reader cannot see: a constituent missing from the wt% list (F, most
  often), a dropped value, `Nb205`, `TiO`, duplicates, group sums that do not add up. Corpus:
  87 of 144 reducible entries (178 distinct entries with an Analysis field) reproduce exactly; the
  rest are garbled or incomplete entries, or calculated-constituent conventions.
  Constituent qualifiers (`FeO(Mössbauer)`) and `(NH4)2O` are now read by the reducer.
- A partly occupied anion's own row sum was scaled by its occupancy (a half-occupied O showed half
  its bond valence); the manuscript checker could not map a paper's `Mg` column onto a merged
  `Mg/Mn` site.
- A bare `W1` label read as water even in a tungstate (now: water only when the formula has no W);
  the hydrogen-bond table's computed rows carry proper symmetry codes; the journal choice and the
  "open ↗" button of the GUI's Tables mode survive a reload.

## [0.5.0] — 2026-08-26

### Added — `pxrd epma`, `pxrd gd`, `pxrd pxrd`: the composition, Gladstone–Dale and powder tables
Three standalone tools alongside `pxrd tables`, each printing the table as text, writing
`review_out/<name>_<tool>.txt`, and on request the Word table (`--word`) and/or an `.xlsx` with live
formulas so the arithmetic can be checked (`--xlsx`; openpyxl is a new dependency).
- **`pxrd epma probe.xlsx --basis O=21`** (`pxrd_review/epma.py`) — reads the probe file (xlsx / csv /
  txt: finds the header row naming the oxides, one row per point, tolerates comment rows), reduces the
  wt% to an empirical formula on any basis — anions (`O=21`, the O=F reduction applied; `--raw-anions`
  for the spreadsheet's 21.5 convention), cations (`cations=8`), an element or sum (`U=5`, `Si+Al=4`) —
  with constituents the probe cannot give (`--add H2O=structure:6`, `CO2=wt:14.02`, `H2O=difference`),
  conversions by molecular weight (`--convert UO2=UO3`), charge balance by hydrogen (`--charge H2O
  --anions N`) or by an Fe2+/Fe3+ split, point selection, standards and the ideal formula. Prints the
  reduction (moles, cations, apfu per constituent, factor, charge) and the published table
  (Constituent | Mean | Range | S.D. | Standard | Normalized | Ideal, with the O=F and Total rows and
  the "calculated from the structure / by difference" note). Validated against the owner's
  spreadsheets (szilagyiite, spanoite). The `.xlsx` has raw | reduction (formulas) | table sheets.
- **`pxrd gd --formula "Ca=1,U=2,V=2,H2O=4" --n 1.70 --cif mineral.cif`** (`pxrd_review/gd.py`) —
  Gladstone–Dale compatibility from a formula (atoms per formula unit → the usual oxides; `--oxide
  S=S` etc.) or wt% (`--wt`), the mean refractive index and a measured density and/or the density
  calculated from the .cif and Z. Constants in `data/gd_constants.json` (Mandarino 1976/1981 as
  harvested from the owner's sheets, each tagged with its source; uncertain ones marked "check";
  `--k UO3=0.118` overrides). Categories superior / excellent / good / fair / poor at 0.02 / 0.04 / 0.06 / 0.08.
- **`pxrd pxrd obs.txt calc.txt --dmin 1.45 --word`** (`pxrd_review/pxrd_table.py`) — the combined
  powder table from an observed peak list (a JADE export with its hkl assignments, or any d / I or
  2θ / I list with `--wavelength`) and the calculated pattern: matched by hkl then by d, unobserved
  reflections within `--tol` (1.2 %) attached to the nearest strong observed peak with Iobs / dobs
  repeated, calculated-only rows when nothing was observed, a row kept when Iobs or Icalc ≥ `--min-i`
  (3.5), a peak with only weak reflections kept once, the eight strongest observed lines in bold,
  two column blocks (`--blocks`). Reproduces the owner's spanoite table (all 66 rows; four weak
  extras the author dropped by hand).
- Tests: `tests/test_epma.py`, `tests/test_gd.py`, `tests/test_pxrd_table.py`, `tests/test_gui_tb.py`.

### Changed — the GUI's Tables mode is now five tabs
**Coords & bonds | Bond valence | Gladstone–Dale | EPMA | PXRD** over one folder: the sidebar lists
the `.cif` files, the data files (probe analyses, peak lists — with a guess at what each is) and
what has been written to `review_out`; each tab has the tool's options as a row of inputs, renders
the same table the CLI prints (with the reduction / working underneath), and writes the same
`review_out/<name>_<tab>.docx` / `.xlsx`. The EPMA means can be handed to the Gladstone–Dale tab
(**← EPMA**). Inputs are remembered per folder in `review_out/tables_opts.json`. Routes `/api/tb/*`
(`epma/<file>`, `gd`, `pxrd`, `…/export?fmt=word|xlsx`, `opts/<tab>`, `open?file=` restricted to the
tool's own outputs); the page still sends only file keys and option strings, re-validated on the server.

## [0.4.0] — 2026-08-25

### Added — `pxrd tables` and the GUI's Tables mode: publishable tables from a .cif
`pxrd_review/tables.py`, run as `pxrd tables mineral.cif --word`, and a third **Tables** toggle in
the GUI. Four tables formatted after the journals and the corpus manuscripts: atom coordinates +
displacement parameters (`s.o.` as element-subscript-occupancy, ⅓/⅔/½ for fixed coordinates, values
and esds verbatim), selected bond distances in three column pairs with superscript symmetry codes
and a *Symmetry codes* note (`<M–O>` means; `<U–Oyl>`/`<U–Oeq>` for uranyl; the `.cif`'s own
`_geom_bond` loop when present, computed otherwise), hydrogen bonds (loop or computed from the H
positions), and the bond-valence analysis in the `Σan`/`Σcat` + `Donor | vu` layout. Rich cells
render to text, HTML (the GUI) and Word (italic *x y z U*, superscript indices/codes, subscript
occupancies; table rules). A bond now counts only when worth ≥ 0.025 vu (also in `pxrd bv`).
Routes `/api/tb/*` under the same gate; `tests/test_tables.py`. The table conventions were taken
from a survey of ~220 corpus papers and the owner's manuscripts. **`--journal ammin|minmag|cjmp|ejm`**
(and a selector in the GUI) applies a journal's conventions — caption form, header and sum labels,
symmetry-code phrase, notes, rules, font — from a registry whose rules are tagged as documented
(American Mineralogist checklist, Mineralogical Magazine instructions, the Canadian journal's own
table template) or corpus-inferred (~300 papers by journal).

### Added — Manuscript mode in the review GUI
An **Entries | Manuscript** toggle in the GUI's top bar. Manuscript mode reviews a folder of paper
`.docx` files with `pxrd refs` inside the same shell: sidebar with per-manuscript badges, the
findings pane in four sections with the familiar confirm / dismiss / ? look / note triage, the
docx (annotated copy or source) in the middle with `? look` jumping to the finding's paragraph, the
text report on the right. Companion files (a separate table docx) are toggled as header chips and
re-analysed at once. **Run** writes `review_out/<name>_refs.docx` applying the triage (dismissed
findings are not written; notes are folded into the comments); the source is never edited. Triage
is saved to `review_out/ms_triage.json` under content-stable finding keys; **Export triage** writes
`ms_triage_report.txt`. `pxrd gui` on a folder with manuscripts but no entries opens in this mode
(`--manuscript` forces it). Same token/CSRF gate and no-raw-paths rule as the entry mode; the docx
renderer now numbers paragraphs (`data-p`) and renders content controls. Routes covered by
`tests/test_gui_ms.py`. (`refs_check` gained `finding_key`, `serialize` and triage-aware annotation
for this.)

### Added — `pxrd bv`: bond distances and bond-valence sums from the .cif, with a manuscript-table check
`pxrd_review/bv_check.py`, run as `pxrd bv mineral.cif [--table "My paper.docx"] [--word]`.

- **Own CIF reader** (loops, quoted/text fields, several blocks; no `eval` — symmetry operators go
  through a small term parser), mixed sites merged, `Fe3+` / `Bi+3` / `S-2` type symbols, every
  symmetry-equivalent position generated and checked; neighbours within an element-aware cutoff.
- **Valences** from the type symbol, `_atom_type_oxidation_number`, `--ox`, or the usual mineral
  values (sulfide/sulfosalt defaults without oxygen; ammonium recognised without its H); every
  assumption stated. **Parameters** from I.D. Brown's `bvparm2020.cif` (bundled): Gagné &
  Hawthorne 2015 for cation–O, Burns et al. 1997 for U⁶⁺, `--params bo|ba`; each one named.
  Hydrogen takes its acceptor valences from H···O and the donor 1 − Σ, so each H sums to 1.
  Bonds weighted by the anion's occupancy (split / partial O sites).
- **Output**: per-site bond list with distances, multiplicities, valences, mean and Σ vs expected;
  the anion × cation table with `×n↓` / `×n→` marks and sums; the parameters used; a self-check
  against the `.cif`'s `_geom_bond` loop (≤ 0.003 Å on every fixture CIF that has one).
  `--word` writes both tables as a `.docx`.
- **`--table`**: the manuscript's bond-distance cells (`Cd1–O3² | 2.472(3)`) vs the `.cif`,
  multiplicities, omitted/extra bonds, `<M–O>` arithmetic (subset means allowed); bond-valence
  tables cell by cell under either convention (per-bond or total), marks, blanks, and the Σ
  arithmetic with D/A hydrogen-bond columns; the parameter set is auto-detected from the table.
  On the owner's manuscripts: cadsulfohite 16/16 distances and 14/14 cells agree; szilagyiite 29/29
  distances, and the three BVS disagreements are real (`0.011`, a ×3 total beside a per-bond
  value, a mixed F/OH cell); flatimerite 68/69 cells with BO91 auto-detected — the one left is a
  `039` missing its decimal point.
- Validated over all 57 fixture CIFs (53 run; the 4 refusals are CIFs without a cell or symmetry
  list). `tests/test_bv_check.py` — rutile from first principles, the symop parser, parameter
  choice, the Word writer, a synthetic manuscript table.

### Added — `pxrd refs`: a manuscript's citations vs its own reference list
A new, self-contained check for *manuscript* review (a paper `.docx`, or a `.pdf`), separate from
the ICDD-entry checks: `pxrd_review/refs_check.py`, run as `pxrd refs "My paper.docx"`.

- **Both directions.** *Cited but not listed* (an in-text citation with no reference-list entry),
  *listed but not cited*, and *mismatch* pairs — an orphan citation and an uncited entry that are
  probably the same reference with the year or the surname's spelling differing (`Gurzhyi` vs
  `Gurzhiy`, cited 1985 / listed 1982) — reported as a pair, so a typo is told apart from a
  genuinely missing reference. Orphans with the same surname elsewhere in the list carry a
  `[list has: Schoep (1923), Schoep (1926)]` hint.
- **FORM findings** — a citation that found its entry but disagrees with it: the year's letter
  (`Cooper et al. 2019` vs a `2019a` entry), the author form against the entry's author count
  (`Zhao 2024` for five authors → `Zhao et al.`; `et al.` for one author), and an entry written
  without initials when the list has them elsewhere. The count comes from an author-list grammar
  (`Surname, I.I.` / `Surname AB` / `I.I. Surname`, `O’Keeffe`, `Yu.S.`, `Sen Gupta`, `Jr.`,
  `et al.`; a program/company name ends the list), so year-at-the-end entries are not over-counted
  and the rule is silent where the block does not parse. ~0.4 findings per published paper.
- **Styles.** Author–year in every common form (`Smith (2019)`, `Smith and Jones, 2019`,
  `Smith et al. 2019a,b`, `Čejka (1999 and 2005)`, `van der Waals et al. (1873)`, `Van Gosen and
  Hall 2017`, `in press`) and bracketed / Science-style numeric citations (`[3]`, `[4–7, 12]`,
  `(1–3)`, numeric superscripts) against a numbered list. A `———` entry inherits the authors above.
- **Body = everything outside the list**: tables, figure captions, an appendix, footnotes and
  endnotes; a `.docx` is read with tracked changes *accepted*. Tables or captions kept in a
  separate file fold in with `--with FILE` (repeatable) — their citations count and satisfy entries.
- **Conservative by construction.** A citation is only recognised in a citation-shaped position;
  `December 2024`, `IMA 2024-012`, `SHELXL-2016`, a URL, or `the Meritorious (1981) Service Award`
  never fire. Acronyms, software/company names and multi-word proper names (`Rigaku Oxford
  Diffraction (2018)`) match when the list has them and are silently ignored otherwise. Surnames
  compare Unicode-folded (`Balić-Žunić` = `Balic-Zunic`, `Karup-Møller` = `Karup-Moller`).
- **Output.** Console report + `review_out/<name>_refs_report.txt`; for a `.docx` an annotated
  COPY `review_out/<name>_refs.docx` with a yellow highlight and a Word comment on every orphan
  citation, uncited entry and mismatch pair (the citation's own run is split out so only the
  citation is highlighted; body text is byte-identical afterwards). The source is never modified;
  an output that already carries someone's comments or tracked changes is not overwritten without
  `--force`. `--no-annotate` for the report alone.
- **PDF path.** Text comes back line by line, so the list is split from the lines: numbered
  sequences first, else year-anchored (an entry's boundary is the first *surname + initials* after a
  sentence/DOI/page boundary between two consecutive years — robust to two-column layouts, wrapped
  lines, journal names that look like surnames, and stranded accents). Report-only; no annotation.
- Validated on eight real manuscripts (every finding reviewed) and the 61 fixture papers (published
  papers drop from ~19 to ~3 residual findings each, mostly genuine). `tests/test_refs_check.py`
  (unittest, no corpus needed) covers the citation forms, the noise cases, the annotator's
  text-preservation guarantee and the splitter. The entry checks and their regression suite are
  untouched.

## [0.3.5] — 2026-07-16

### Security — follow-up audit (no high-severity findings)
A second, independent audit re-confirmed the 0.3.4 posture — localhost-only GUI behind a per-launch
token, XXE-guarded XML parsers, capped zip reads, the Mindat key confined to `api.mindat.org`,
escaped rendering throughout, no secrets in git or the wheel — and produced two low-severity fixes,
both applied:

- **The GUI now extracts PDF text in the crash-isolating worker pool**, like every other page
  operation. `get_text()` interprets the page content stream, so a malformed embedded image can
  segfault libmupdf — an *uncatchable* native fault that would take the whole Flask server down.
  Text extraction previously ran in-process (a deliberate speed choice, on the assumption that only
  rendering can crash); a maliciously crafted paper could exploit that to crash or hang the review
  server. It now degrades to the "no text layer" verdict instead. The CLI keeps the faster
  in-process reader — a crash there just fails that one run, with no server to protect. A valid
  PDF's analysis is byte-for-byte unchanged (identical page-join).
- **The auto-exit heartbeat now updates only after a request clears the auth gate.** It was
  refreshed at the top of `before_request`, so a *rejected* probe from another local user could
  reset the "a tab is open" timer and keep the server running under a closed browser. Now only an
  authenticated request counts as activity.

Informational items left as-is by design, with rationale: `/api/browse` directory enumeration is
token-gated and exists for the folder picker (no confinement possible without removing it);
`MINDAT_INSECURE=1` is a warned, opt-in TLS escape hatch; the CSP's `style-src 'unsafe-inline'` is
required for the per-author highlight colours, whose values come from a fixed palette (no injection
vector).

No check behaviour changed. 294/294 regression cases pass (one new: the worker-isolation invariant).

## [0.3.4] — 2026-07-13

### Security — hardening pass from a full code audit (no high-severity findings)
The audit confirmed the existing posture — localhost-only GUI, XXE-guarded XML parsers, escaped
rendering everywhere, verified TLS, no secrets in git history — and produced five low-severity /
defence-in-depth fixes, all applied:

- **The GUI now requires a per-launch auth token.** A browser could never forge the Host/Origin
  checks, but **another OS user on a shared machine can** (curl sets any header): without the
  token they could list directories (`/api/browse`), open files in Word, and trigger reruns
  through `127.0.0.1`. The launch URL carries the token once (`?t=…`); the index route swaps it
  for an `HttpOnly` session cookie and strips it from the address bar. A bookmarked bare
  `http://127.0.0.1:8000/` returns 403 after a fresh launch — use the URL the tool prints/opens.
- **The Mindat API key is confined to `api.mindat.org`.** The client refuses to fetch any URL off
  the API base — including the API-supplied pagination `next` links — and refuses redirects off
  the API host (urllib re-sends the `Authorization` header on redirects, so a redirect elsewhere
  would have handed the key to whatever host it named).
- **Capped docx zip reads.** A decompression-bomb member now raises a clean error instead of
  inflating into memory: 64 MB per member on every read path, plus a 256 MB whole-archive budget
  where the annotator rebuilds a docx. Regression-locked alongside the existing XXE case.
- **Hardening headers on the GUI:** `X-Content-Type-Options: nosniff` on every response and a
  `default-src 'self'` Content-Security-Policy on the page — defence-in-depth for the
  innerHTML-heavy docx view.
- The macOS folder picker refuses a start path containing `\r`/`\n` — a control character cannot
  be escaped into an AppleScript string literal.

No check behaviour changed. 293/293 regression cases pass (one new: the zip-read cap).

## [0.3.3] — 2026-07-13

### Fixed — the stale-cache warning told reviewers to run a command they cannot run
The bundled Mindat snapshot was judged against the **14-day** bar meant for a key-backed cache, so
it read `!! STALE` a fortnight after every release — permanently — and the remedy it offered was
`--refresh`, which **needs an API key and exits without one**. That is the entire population the
snapshot exists for: nagged forever, and handed a command that cannot work.

- The bundled snapshot now has its own bar: **120 days**, not 14. Staleness here costs *coverage*,
  never correctness — an unknown species yields a console note and the cross-checks simply do not
  fire, so it can never invent a false flag. IMA approves ~100 species a year of 6,226.
- The advice now depends on what the user can actually do. **With** a key: `--refresh`. **Without**
  one: install a newer release (`/releases/latest` — every release ships a fresher snapshot), or
  get a free key and the tool refreshes itself. The GUI chip follows suit — it opens the releases
  page for a keyless reviewer instead of copying a command that would fail.
- A **corrupt or truncated** snapshot (present on disk, 0 species) now reports `UNREADABLE …
  cross-checks are INACTIVE` rather than "stale". It was claiming the data was merely a bit old
  while the checks were in fact dead — the one thing this banner exists to prevent.

*(Not doing: auto-cutting a release when the snapshot ages. A Mindat refresh changes what the
checks find, and validating that needs the private fixtures + corpus sweep, which cannot run in CI
— an automated release would ship unverified check behaviour. It would also require the
maintainer's personal Mindat key as a secret in a public repo. Refreshing the snapshot at each
release, which the release procedure already does, covers it.)*

## [0.3.2] — 2026-07-13

**Upgrade from 0.3.0/0.3.1.** The final review found reproduced bugs in the one check that WRITES
into the docx. None could touch a source file, but they could damage a review_out copy.

### Fixed — the docx write path (all reproduced, all now regression-locked)
- **The tool could destroy a row LABEL.** python-docx's `cell.text` does not see runs nested in
  `w:ins`/`w:del`, so a citation the reviewer had replaced *with track-changes on* read as an
  **empty cell** — `_find_value` then fell through to the row's label cell, and the tool struck out
  **"Primary Reference"** and pasted the citation into the label. The human-marks guard could not
  help: it was being asked about the wrong cell. A fix is now written **only** to a cell whose text
  already IS the fix bar its capitalisation; anything else stays a comment.
- **A reviewer's edit could be destroyed with no backup.** Word's default is track-changes OFF, so
  a reviewer tweaking the tool's inserted citation types *inside* the tool's own `w:ins`. No
  foreign author appears, so nothing saw the edit: the strip dropped the whole insertion and the
  rerun rebuilt from source. The tool now compares what its insertions SAY against what it would
  write, keeps one a human has altered, and does not re-apply over it.
- **`--out` could delete source files.** The guard only rejected `--out` == the source folder, but
  `discover()` is recursive and the corpus keeps docx in a subfolder — `--out <folder>/Files` put
  the outputs on top of the sources, and the stale-twin logic then `os.remove()`d them. Outputs may
  no longer share a directory with any source.
- **The accepted citation came out fully italic and highlighted.** The replacement was one run
  cloning run 0's formatting; the template's citation is italic title + plain authors + **bold**
  year (62/62 fixture cells are multi-run). Because the rewrite is case-only it is the same length,
  so it is now sliced back onto the existing runs — every run keeps its own formatting.
- A human tracked change or comment **nested inside** the tool's insertion is no longer swept away
  by the strip; the run carrying the tool's own comment anchor is no longer swept into the deletion
  (accepting the fix used to delete the comment explaining it).

### Fixed — the title-case check (its output is written, so these mattered)
- **A place name was destroyed when no `.pdf` was paired** (25/405 entries, plus any scanned paper
  with no text layer): `New Mexico` → `new Mexico`, `Ore Mountains` → `ore Mountains`. **The paper
  is the oracle for what is a name — with no paper the check now suggests but NEVER writes.**
- **`Utah` → `utah`, with the paper present.** A word the article capitalises in only half its
  sightings (OCR, typos) fell under the 70 % proper-noun bar. Two capitalised sightings now make it
  a name; under-correcting is the safe direction for a check that writes.
- **A citation with no author pattern** had its journal/series/pages case-rewritten (`Physics And
  Chemistry Of Minerals` → `Physics and chemistry of minerals`) because the whole string was taken
  as the title. It now abstains.
- `Ca-(OH)` / `Fe-(III)` were being lowercased as if they were Levinson-suffixed species.

### Fixed — space groups
- **`P4₃2₁2` was classified CUBIC.** The `3` of a 4-fold *screw* was read as a body-diagonal triad,
  so check 23 wrote a false "Crystal System disagrees with the space group" flag into the docx —
  and contradicted itself (`P4₁2₁2` tetragonal, its enantiomorph `P4₃2₁2` cubic). The 36 cubic
  groups are a closed set and are now matched exactly. (A name collision made this subtle: a second
  `_norm_sg` further down the module silently shadowed the helper.)

## [0.3.1] — 2026-07-13

### Added — GUI
- **Mindat type locality** is shown in the Mindat panel (`Beltana Mine, Puttapa, … Australia`),
  straight from the cache. **Reference only** — no check reads it: Mindat is not authority over
  the paper, and a locality mismatch means nothing on its own. It is there because the reviewer
  usually wants to know where the type material came from without leaving the entry.
  Cached for 6,086 of 6,226 species (98 %); it ships in the bundled snapshot, so it works with
  no API key.
  *(Mindat gives a mineral's type locality only as an ID, and its `/localities/` endpoint ignores
  an id filter — an unknown query param silently returns the unfiltered first page, i.e. somebody
  else's locality. The names come from a page-sweep of the locality list instead: ~225 requests
  and ~2 min on `--refresh`, vs several thousand single fetches. `type_localities` must be listed
  in **both** `fields` and `expand`, or the API quietly returns nothing.)*
- **"reviewed" now sits beside the Accept agree/disagree buttons** instead of hiding at the far
  end of the header past the Rerun button — that is the moment the reviewer decides it. It reads
  as a pill and turns green when ticked.

### Docs
- INSTALL.md carries **no version-pinned install command** anywhere: a pasted `v0.2.9…#sha256=…`
  line quietly installs an *old tool*, which cost real time during a Windows setup. It points at
  `/releases/latest`, uses `<version>` placeholders, tells the reader to take the hash-pinned line
  from the release they are installing, and warns against pasting a versioned command from an old
  message. The verify step now says the printed version must match the one marked `Latest`.

## [0.3.0] — 2026-07-13

### Changed — the reference-title check now WRITES its correction into the docx
The first and only exception to the comment-only rule, at the maintainer's request. Every other
check still comments and leaves the fix to the reviewer.

- The corrected citation is written into the `review_out` **copy** as a **Word tracked change**,
  so the reviewer opens the docx, sees exactly what changed, and clicks **Accept** or **Reject**
  in Word. Nothing is rewritten invisibly and nothing is irreversible. The **source docx is
  still never touched.**
- **A cell a person has already edited is never overwritten.** Any human tracked change in the
  Reference cell and the tool stands down, staying a comment (*"fix left to the reviewer
  (already hand-edited)"*).
- The rewrite differs from the docx in **letter case only** — authors, journal, year and pages
  stay byte-identical, and the check refuses to write at all unless it can prove that.
- **Reruns are idempotent**: the strip step now *rejects* the tool's own previous tracked change
  and re-derives it, so edits never stack.
- The console line and `annotation_log.txt` state every fix written (and every one skipped).

Consequences of the tool now making revisions of its own, both fixed here:
- `_has_tracked_changes()` assumed *"tracked changes are always human; the tool never makes
  revisions"*. Left alone, every fixed entry would have looked hand-edited — a backup on every
  rerun, and the tool's own work reported back to the reviewer as theirs. It is now author-aware,
  as are the reviewer-mark summaries in the log and the GUI.
- `output_hand_edited()` compared the output's body text against the source *before* stripping
  the tool's marks, so an applied fix read as a human body-text edit. It now compares after the
  strip, which reverts the tool's own change — so what remains is genuinely a person's.

## Early releases — 2026-07-08 to 07-13
Ten releases in six days, before the tool went to reviewers; superseded by everything above, and
kept here in outline. `git log` has the detail.

- **0.2.9 – 0.2.6** — reference title case became a check that writes (see 0.3.0); a '? look' mark
  and Intensity Type findings landed on the wrong docx cell; INSTALL.md rewritten against how
  reviewers actually install.
- **0.2.5** — the safety pass: hand-edited outputs backed up before a refresh, the GUI's file
  routes confined to the folder, several false positives that were being written into the docx.
- **0.2.4 – 0.2.3** — GUI and Windows fixes.
- **0.2.2** — the first packaged release, and the data-loss pass that made it fit to distribute:
  the reviewer's own edits preserved on rerun, the gates made trustworthy.
- **0.2.1 – 0.2.0** — the first public version: the cell and wavelength comparison, the extra
  checks, the Mindat lookup, and the first security pass.
