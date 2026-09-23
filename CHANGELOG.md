# Changelog

Notable changes to the PXRD review tool. The format loosely follows
[Keep a Changelog](https://keepachangelog.com/); the version is the `pxrd-review`
package version in `pyproject.toml`.

| version | | one line |
|---|---|---|
| [0.12.0](#0120--2026-09-23) | 23 Sep | Mineral names on the .pdf page: every IMA species the paper names is tinted and a hover opens its Mindat formula, group, Strunz code, cell and type locality; a word one slip from a species name is underlined with the name it is nearest; the entry's own mineral tinted once a page; matched against the local Mindat snapshot, so a paper's words never leave the machine — a reading aid, no new check |
| [0.11.4](#0114--2026-09-23) | 23 Sep | Three reader rounds from the plan's block 1, each gated on the whole corpus: the powder-table reader rebuilt from the entry-recall worklist (printed-list recall of a dropped line 78 → 92 %, an intensity slip 66 → 88 %; checks 34/37 pair lines one-to-one), the bond-valence readers' first batch (tables no finder read, parameter sets cited by number), the optics and density readers (27 papers' densities read for the first time, a reason where no index is read), and an adversarial read of all three that found five density misreads — no new check |
| [0.11.3](#0113--2026-09-22) | 22 Sep | A deep-dive bug check over the whole corpus: no crash, no errored check, every A/B explained — the defects were in what the flags SAID: check11 hinted the OTHER mineral's IMA number on multi-mineral papers (21 of 22), now the number beside the entry's own name, and a number the entry carries is compared (two real slips on the corpus); a comment label typed in another case read as blank; an isotropic entry's index under 'Refraction Index' never checked; `pxrd paper` on an empty .pdf; the GUI's 'no .pdf' badge on an entry that has one |
| [0.11.2](#0112--2026-09-22) | 22 Sep | The statements gauntlet: what the workbooks SAY, measured against the checks and against seeded faults — contradictions 63 → 0 on the whole corpus, a 10 % wt% slip named 68 → 93 %, the tool's own bond-valence table no longer failing its own check, a bond-valence workbook for papers with no .cif (97 → 340), the colours tested, the paper's GD index one cell; the first recall numbers for the entry checks and check37 (a reflection's intensity is not the paper's); every GUI route walked |
| [0.11.1](#0111--2026-09-21) | 21 Sep | An adversarial review of the day's three releases, every finding reproduced before it was fixed: the arithmetic held, what the tool SAID did not — check33 offered another mineral's density as "enter it"; the EPMA workbook wrote PROBLEM where the composition check flags nothing; a BVS column was judged by a bare ±0.08; the GD total left out O ≡ F,Cl; the folder guard's holes; ten GUI error paths that were a NameError; the sheet and the reduction brought into line on the edge inputs |
| [0.11.0](#0110--2026-09-21) | 21 Sep | Workbooks that show their working: a paper's EPMA re-reduced on its stated basis, the bond-valence table as a paper prints it, and Gladstone–Dale from apfu to index — every number a live formula, each with a `check` sheet that colours what differs from the paper and says where the fault lies; a stated cation basis counts the measured cations; `pxrd gui` asks before opening a folder that is not a batch and starts on its chooser; `? look` crosses between the .pdf and the entry |
| [0.10.1](#0101--2026-09-21) | 21 Sep | Three reflection-list checks (a paper line the list lacks, a blank hkl in a multiply-indexed group, one d with two intensities); an audit of the day's commits; `? look` finds a reflection line and lands on it; a microprobe line list no longer reads as a second radiation, and a calculated pattern has no powder radiation to verify; intensities all multiples of 5 are a note; every log says which version wrote it |
| [0.10.0](#0100--2026-09-21) | 21 Sep | A re-run of the 2028 Part 2 batch in the GUI: two entry checks (a blank Final Quality Mark; Dx left blank although the .pdf states a calculated density), reflection findings on their own line, the paper's own misprint told from the entry's, upright pages for a pdf with a wrong /Rotate, output pages that hold their tables, the launcher opening the folder it is typed in |
| [0.9.0](#090--2026-09-16) | 16 Sep | Three entry checks from the operators and the lattice: a reflection the space group forbids (`symops.absent`, the condition derived from the operators of the setting the symbol names), the same lattice in another setting is no discrepancy (Niggli reduction, `lattice.py`), the entry's own indices against the .pdf and its own Gladstone–Dale; gauntlet rounds 7–8; the recall inversion; a third adversarial audit — five defects fixed, one of them a half-read coordinates table verified at flag grade |
| [0.8.2](#082--2026-09-16) | 16 Sep | Recall re-measured (unchanged since 0.6.0); coordinates round 6 on the whole corpus — displacement tables no longer read as sites, a bond table's name for a split site found; the composition reds hand-checked against the papers: three of thirteen were the tool's, fixed, the other nine now say which oxide form the arithmetic used; '? look' lands on the paper for every finding; corpus runs a third cheaper |
| [0.8.1](#081--2026-09-16) | 16 Sep | A second adversarial audit, of the 0.7.2 fixes and the 0.8.0 checks, over the whole corpus: eight defects and fifteen edge classes fixed — a biaxial (−) entry flagged as uniaxial, a bond table lost to its page's font, the manuscript '? look' landing in the wrong table, two findings for one fault |
| [0.8.0](#080--2026-09-14) | 14 Sep | Entry checks that read the entry against itself and against the paper, from a human review of 2028 Part 2: formula and analysis fields, Xtl Dx vs Dx, the optics field, every strongest line, a reflection d the .pdf never prints — every corpus flag a real defect; case alone no longer a vocabulary fault |
| [0.7.2](#072--2026-09-10) | 10 Sep | An adversarial audit of the 0.6.0–0.7.1 commits: seven defects fixed — a continued coordinates table walked into another mineral's, a "powder was obtained" sentence silenced the calculated-pattern flag, a β = 90.00 monoclinic cell lost its symbol, an arrowless ×n mark lost its value; nothing changed on the corpus A/B |
| [0.7.1](#071--2026-09-10) | 10 Sep | The silent classes: every reader that could not verify now says why (parameter sets, one-site tables, unusable .cif); coordinates 59 → 62 %, parameter sets 60 → 64 %, bond-valence reds 6 → 5; two-mineral papers judged by their own bond table |
| [0.7.0](#070--2026-09-10) | 10 Sep | The gauntlet on the whole 1,130-paper corpus: bond-valence tables 51 → 69 % verified (52 reds → 6), parameter sets 31 → 60 %, coordinates 55 → 59 %, optics 60 → 66 %; a reader failure log; a 50× faster neighbour search |
| [0.6.0](#060--2026-09-09) | 9 Sep | The gauntlet: paper readers driven to 91/83/86/52 % on the papers that print everything; ICDD's Part 2 review corrects five entry rules; another reviewer's triage report reads back into the GUI |
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

## [0.12.0] — 2026-09-23

**Mineral names on the .pdf page.** The .pdf pane's text layer now knows which of its words name a mineral. Every IMA
species is tinted; hovering one opens a card with its IMA formula (sub- and superscripts), group, Strunz code, IMA status,
Mindat cell and type locality. A word that looks like a misspelt species — the shape of a name, one edit from one (two
for a long name), first letter kept — is underlined, and its card names the nearest IMA species with that species' formula,
worded neutrally: a misspelling, an older or non-IMA name, or a scan's misreading of the page (ö read as 'd' or 'ii').
A reading aid only: nothing is written into a docx, a log or a finding.
- Recognised as the species, not flagged: the IMA name written without its hyphens ('magnesiohastingsite' →
  Magnesio-hastingsite) or transliterated ('bastnaesite', 'boehmite', 'nyboite'); a root whose species all carry a suffix
  ('davidite' → Davidite-(La), Davidite-(Ce)); a name broken across a line ('tobermo-' / 'rite'); ligatures ('ﬂuorapatite');
  pairs ('jarosite–alunite'); '-group', '-type' and the like.
- The spelling rules were set on the whole corpus (1,264 papers, 14,034 pages): the first pass underlined 2,152 words;
  rocks and varieties built on a species ('chromitite', 'sanidinite', 'titanomagnetite'), chemistry words ('chalcogenide',
  'lanthanide') and a name spelt right in another script were the false positives, each class now a rule. 1,583 remain —
  about one every nine pages — nearly all older names (zinckenite, celestite, covelline), typos (brackenbuschite,
  rhodocrosite) or scan slips (lindstrdmite). About 159,000 species names recognised, ~14 ms a page.
- The entry's own mineral, named on nearly every line of its paper, is tinted at its first mention on each page only;
  the repeats stay hoverable.
- **Local only.** The words are matched in the GUI's own process against the Mindat snapshot on disk (the bundled seed or
  the user's own pull); no word read from a paper is sent to Mindat or anywhere else.
- On by default; the **minerals** button above the page, or ⚙ → Mineral names, turns it off (remembered).
- `pxrd_review/mineral_names.py` (`classify`, `suggest`, `card`, `page`); `/api/pdf/<key>/words/<n>.json` carries
  `minerals`. Tests: `tests.test_mineral_names`.

## [0.11.4] — 2026-09-23

**The optics and density readers, from the silent classes (2026-09-23; plan block 1, item 3).** Of the 46 papers whose text
prints optics and whose index the reader could not see, most were the crude scan's (a modulation 'γ = 1.8', a physics
paper's refractive index, '2V' in a petrology paper); the readable classes were the DENSITY sentences — 27 corpus papers
printed an index and no density the reader saw, so their index had no Gladstone–Dale oracle — and four multi-column optics
tables. Whole corpus: measured densities verified 180 → 192, calculated 610 → 640 (every record that moved read against its
paper: the ones lost were the literature's, a synthetic analogue's, or a column of a multi-phase table); indices verified
359 → 366, silent 46 → 34; the remainder carries a reason. Entries: one new flag over 1,678 copies (uramphite's blank Dx,
the paper's 3.302 = the entry's Xtl Dx); entry recall unchanged.
- `optics()` reads 'The measured and calculated densities are 3.63(2) and 3.62 g/cm3, respectively' as the pair it is;
  one value per mineral ('3.503 g cm−3 for zadovite and 3.509 for aradite') by the paper's own name, the whole name
  ('lazaraskeite-M2' is not '-M1'); the qualifier after the value ('4.042 (measured) and 4.111 (calculated)',
  '3.68(2)/3.682 g/cm3 (measured/calculated)', 'The density, 4.324 g cm−3, was calculated'); a crystal-data row whose
  unit carries a digit ('Dx (g cm−3) 4.338'); 'was found to be'.
- Guards, each from a corpus record: a density the paper 'reported' from the literature is not its own; a density
  measured on synthetic material is not the mineral's, but one CALCULATED for it is the paper's own; a crystal-data row
  followed by a run of values is a column per phase and is not read unless the run agrees within 3 % (two refinements
  of one structure), because whose the first column is, is not known.
- A cluster of indices in which a symbol repeats ('ω = 1.696(3) ω = 1.703(4) ω = 1.720(5) α = 1.609 …') is a table's row
  of columns and is not read as a sentence: rhabdoborite's index had been its biaxial relative's, and the compatibility
  check called the paper's 'superior' poor.
- No index read, the record says why (`nooracle`, never a value): a multi-column optics table (six new minerals in one
  paper, or a comparison with the literature — no column is picked), an index given by presumption or analogy, an
  opaque mineral with reflectance values only.
- An adversarial read of the round and of the two reader commits before it (the same day): a table's density row
  broken one value per line had escaped the column rule (rathite's five phases); a powder table's 'd(calc)' column
  was a density (proudite) — the symbols are now capital D, a lowercase 'd (calc)' or an old paper's 'dx =' / 'dm ='
  needs its lead word; a cell edge under 'Calculated densities' (cupropavonite); an own density after 'according to'
  in an earlier clause was the literature's (shiranuiite) — the guard reads its own clause; 'density 3.266 obtained
  from SC-XRD unit-cell parameters' is not a measurement. Checks 34 and 37, when the table prints no observed column
  and the calculated pattern stands in, now say so in the finding instead of calling a calculated line observed.

**Bond-valence readers, first batch (2026-09-22 evening; plan block 1, item 2).** The 32 papers whose table the crude scan
sees and no finder read, and the 85 whose parameter set had no oracle, traced one by one. Whole corpus, bond-valence tables
verified 236 → 238 of 332 (the denominator now excludes tables the paper sends to its online materials — those were
never printed to read), parameter sets 214 → 216; three more tables read (zincorinmanite's checks 6 cells, no disagreement;
alicewilsonite's and two others' sums agree for the first time), none lost; workbooks 340 → 344 with contradictions still 0.
- `bvs_site_tables`: a site label the font split from its number ('V 1'), guarded against a site of its own beside its
  s.o.f. ('Fe 1 0.25'); a footnote letter past c ('BVSe'); the asterisk-operator glyph as a mark ('BVS∗∗' — the caption's
  'bond valence sums' two words had been standing in for it); a caption's words are no column head.
- The caption route (`bv_tables_by_caption` / `_value_run` / `_grid_from_runs`): a row labelled site/occupant ('M1/Fe3+',
  'A/Ca1 Ca', 'M2 0.67Fe + 0.33Ti'); a multiplicity written between the arrows ('0.076→2↓'); the header is the line that
  names sites, not a block title ('R block'); grids set anions-across are turned as the checker reads them and their
  labels cleaned of the occupant, as a manuscript's Word table already was.
- `site_name_map`: a multiply-occupied site printed one occupant per line no longer loses its alias to its own constituents.
- `bv_statement`: a numeric citation ('parameters are taken from [11]') resolved through the reference list, two of them
  a mix; 'parameters (vu) are from Brown (1981)' is a source the tool lacks, not 'no set named'.
- `tools/paper_features.py`: a bond-valence table in the online materials is not printed.

**The powder-table reader, from the entry-recall worklist (2026-09-22 pm; plan block 1, item 1).** The 35 entries whose paper
prints the list and whose seeded dropped line or intensity slip went unseen were the reader's: it read nothing (a header with
the indices in the MIDDLE — `Iobs Icalc h k l dobs dcalc`, the commonest journal layout — dropped every row), a few lines (a
two-column page's prose between the rows ended the table; a header on two baselines), or only the calculated column (a
simulated pattern, which is what such an entry was typed from). Fourteen rules in the header path's row walker, each with a
corpus paper and a test (`tests/test_paper_extract.py::PowderTableLayouts`), every one re-run on the whole corpus four ways —
the reader statuses, the red list by hand, the cell metric, the whole-tree entry findings read against the papers:

| | before | after |
|---|---|---|
| a dropped line caught, where the paper prints the list (123 entries) | 78 % | **92 %** |
| the strongest line's intensity slipped, caught | 66 % | **88 %** |
| observed / calculated lines read, whole corpus | 20,896 / 24,923 | 23,286 / 30,572 |
| papers whose table the cell check can judge | 559 | 580 |
| red lines (a line that does not follow the cell) | 35 in 26 papers | 33 in 25 |
| cell metric (`tools/corpus_pxrd_ab.py`): calculated rows whose d follows from their h k l and the .cif cell | 5,400 of 6,041 | **6,494 of 7,065**; no paper less consistent; suspect lines 55 → 35 |

- **One hkl column is one block**, whatever the label order; the first column OWNS a repeated label even on a row where it
  is empty (a second sample's `Iobs dobs` stays out — six-sample tables, comparison columns); several hkl columns cut
  blocks at the indices or at a repeated label. Multi-sample tables are read for their first sample only now (the losers in
  the A/B, each one read: the other samples' lines, and calculated d values that stood in the observed column).
- A header split over two baselines; natures on the line below (`I1meas dmeas I1 d2` over `calc calc`); `{hkl}`, `(Eddavidite)`,
  `hkl1`, `d2`, `I%`, `dcalc**,`; a 2θ column owns the numbers under it; a continuation page reads under the page before's header.
- **A multiply-indexed row pairs value k with triple k** (`dcalc 1.5943, 1.5837, 1.5753` beside `4 4 2, 3 4 5, 2 0 9`): read as
  one row, its first value took a triple made of the leftovers and every such line was a red one. A comma carries a cell.
- Prose between rows is tolerated two lines at a time; a real header ends the rows; a number glued to a word on either side of
  the table is prose (`Nakamoto, 2009;`, `CaO 38.14,`, `94 s frames` — each was a flag or an index); a number left of the
  table is the page's other column; a fourth index token is h k i l only when h + k = −i; a d outside 0.5–40 Å is no line.
- **Checks 34 and 37**: the calculated column stands in where the paper prints no observed one; the two lists are paired
  one-to-one on the entry's unique d values (a dropped 2.965 hid behind the 2.968 beside it; a multiply-indexed d is one line);
  check37 leaves a d the entry writes with two intensities to check36 and a d the paper prints twice alone; check34 counts a
  paper d once, skips the line check15 has named, and a paper line weaker than the entry's weakest is a cut, not a miss.
  New corpus flags after the round, each read: popugaevaite's four lines (kept), argentopearceite's mistyped 1.4282, okruginite's
  1.3076 (I 1) — nothing else moved.
- `tools/entry_recall.py` seeds the intensity slip on every row of a multiply-indexed d (one row slipped is check36's finding).

## [0.11.3] — 2026-09-22

**A deep-dive bug check over the whole corpus (2026-09-22)** — every paper (1,130) through the paper checks against the
last full baseline, every docx copy in the tree (1,727) through `analyze()`, the statements gauntlet, the entry-recall
harness, the unit and regression suites. No crash, no errored check, no reader status moved that the gauntlet log had
not already explained; the workbook contradictions stayed at 0. What the hand-check of the findings turned up:

- **check11 (IMA number) named the wrong number to add.** The hint took the FIRST proposal number in an approval
  sentence, which on a multi-mineral paper is the other mineral's: of the 22 corpus entries whose number "disagreed"
  with the hint, 21 were the tool's misreading (`IMA 2022-050 and IMA 2022-081 for zhenruite and tianhuixinite`;
  `nannoniite (IMA 2024-010) and dacostaite (IMA 2024-015)`; `arsmirandite: IMA2014-081; lehmannite: IMA2017-057a`).
  The number is now read BESIDE THE ENTRY'S OWN NAME (`_ima_numbers_for`: name-then-number, number-then-name, two
  list forms paired by position, an approval sentence naming no other mineral; the Levinson/group suffix is part of
  the name — `tetrahedrite` alone read `Tetrahedrite-(Mn), IMA 2021-098` from a reference list), and the hint is
  omitted when the paper is ambiguous. 23 corpus hints changed, every one read against its paper: 12 wrong numbers
  corrected, 8 hints gained, 3 dropped as unsupported. **A number the entry carries is now compared too** — two
  real slips on the corpus and nothing else: paulrobinsonite carrying maurogemmiite's `2022-098a` (the paper gives
  `2022-099a`), obradovicite-NaCu's `2011-07` truncated from `2011-079`. A letter suffix alone is not a difference.
- **A comment label typed in another case was a blank field.** `comments.get('IMA Number')` on an entry whose row
  reads `IMA number` — dacostaite: the field held `2024-015` and the tool asked for it to be added, with nannoniite's
  number. The labels the checks read are canonicalised on parse (`_COMMENT_LABELS`); the annotator's IMA anchor is
  case-insensitive to match.
- **An isotropic entry's index was never checked.** Sixteen corpus entries write their one index under `Refraction
  Index` (`n=1.6952(5) (589nm).`, `N=1.88.`, a bare `1.737.`), a label check31 did not read — `_entry_iso_n` reads
  it, the index is held to the .pdf's on the biaxial tolerance, a calculated index and a reflectance list are left
  alone. No corpus entry flags; touretite's field now feeds its Gladstone–Dale note.
- **`pxrd paper` on an empty or truncated .pdf** was a MuPDF traceback; it is one line naming the file (the batch
  and the GUI already skipped such a file with the same explanation).
- **The GUI wore a 'no .pdf' badge on an entry that HAS one** when the docx carries no Author's Cell row (the older
  template, a supplementary docx): the badge and the cell line now say what is missing.

Measured, not changed (for the record): the old two-column template is 663 of the 1,727 docx copies and still fires
2.2 flags an entry, most of them "field is empty" on data the parser does not read — the owner's 2026-09-07 call
stands; the corpus holds one zero-byte .pdf and one corrupt .docx, both skipped with a named reason.

## [0.11.2] — 2026-09-22

**The statements gauntlet** — what the workbooks SAY, measured. The reader gauntlet made the numbers right; the 0.11.1 review
found the sentences wrong, and no gate could see a sentence. Two dev tools now can, each against an oracle the sheets do not
share: `tools/corpus_workbooks.py` writes every paper's workbooks (to a scratch folder), evaluates every formula, harvests every
statement and sets it against the record layer — **C**, contradictions, target 0; `tools/seed_statements.py` seeds ONE fault of
a known kind into papers that pass and reads what the check sheet NAMES — **D**, diagnosis accuracy, a confusion matrix per
stratum, counted over the faults that are past the check's own tolerance. Whole corpus, 1,131 papers, ~1 min each:

| | before | after |
|---|---|---|
| C — a sheet that contradicts the check (769 EPMA, 261 GD, 97 BV workbooks) | 63, + 52 bond-valence sheets red where the check agrees | **0** |
| verified papers whose EPMA sheet shows no colour at all | 207 of 661 | **481 of 661** |
| D — a 10 % wt% slip: the element named / read as "the basis" | 68 % / 11 % | **93 % / 0 %** |
| D — the basis one off: named | 50 % | **94 %** |
| D — an oxide reduced in another valence: named | 62 % (0 % with two majors) | **82 %** (79 %) |
| D — two slips at once: said to be several, not one | 72 % | **98 %** |
| GD sheets with an amber line on papers whose index is reproduced | 66 of 217 | **1** |

### Changed — the sheet never says more than the check
- **EPMA**: where the composition check reproduces the formula on another way of counting and holds no basis against the paper,
  the sheet is reduced on THAT count and says which the paper states (45 verified papers had every element red and "the BASIS
  is not the one used"). Where the check holds nothing against the formula — the paper's own apfu column vouches for it, or
  the coefficients are these by one constant factor — what differs is said as a note with that reason, and nothing is red.
  Where the check FLAGS a formula the sheet cannot show (a second formula in the abstract), the sheet says so.
- **EPMA diagnostics**: an element stands alone only where some coefficient does not follow as it stands (a factor of 0.97
  divided out of a formula that follows had named "the slip" on two verified papers) — and the gate is the sheet's, not the
  row's, because the slipped element is often the one still inside the tolerance while its dilution puts every other outside.
  Two majors that AGREE share a factor (a basis, a valence), so a molybdate is told as much as a silicate. The basis row says
  whether the basis that would give the paper's numbers is a WHOLE number — one a paper would state — which is what tells a
  basis from a valence; the valence line says "would explain", not "explains". Amber is for the upper half of the tolerance.
- **Bond valence**: a paper's workbook is written FROM the paper check (`paper_extract.write_bv_xlsx`, `<paper>_paper_bv.xlsx`
  beside the EPMA one) — its structure with the paper's valences and site names, the set that won, the tables it judged — and
  the check sheet holds a cell red only where the check holds that finding (`write_xlsx(keep=)`); a column that follows
  another reference, a table the check doubts as read, is shown, not red. `pxrd bv x.cif --table paper.pdf` reports and
  writes the same (with the defaults; any option asked for keeps the plain path).
- **Gladstone–Dale**: a total outside 98.5–101.5 is a note only where the paper's index is not reproduced.
- `tests/xl_eval.py`: `ROUND`, `TRUE`/`FALSE`, and `MIN`/`MAX` of no numbers = 0, as Excel.

**Second round — the other two sheets, the entries, the GUI's routes.** Three more dev tools: `tools/seed_statements_gd.py` and
`tools/seed_statements_bv.py` (the D matrix for the Gladstone–Dale and bond-valence check sheets — the latter writes the table
the tool itself would print for every corpus .cif, then spoils it in one known way) and `tools/entry_recall.py`, the first
RECALL number the entry checks have had (one transcription slip seeded into each parsed entry, in memory).

| | before | after |
|---|---|---|
| GD sheet: a variant constant / a normalised analysis / a category word one class off / n or D off — named | — | 88 % / 91 % / 100 % / 100 % (the rest: two explanations that both reproduce, both shown) |
| BV: the tool's OWN table, written back, judged wrong by the table check | 35 % of 147 structures | **4 %** |
| BV: a whole column scaled (another R0, another valence) — named as the column | 69 % | **82 %** |
| BV: one cell off by 0.20 vu / one Σ mis-added — named | 95 % / 99 % | 94 % / 99 % |
| entries: the strongest line's d with two digits swapped / left out / Dx blanked — flagged, where the paper prints the list | — | 100 % / 79 % / 81 % (where it does not: 2 % / 0 % / 43 %) |
| entries: the strongest line's intensity 100 typed as 10 — flagged | **0 %** | **47 %** (66 % where the paper prints the list; 0 firings on the 368 paired corpus entries as they stand) |

- **The table check's row arithmetic accepts an occupancy-weighted Σ** — how an anion's sum is formed over a split or partly
  occupied cation site, and how this tool's own table adds its rows: written back, that table failed "its row adds to" on one
  corpus structure in three.
- **A ×n cell's per-bond value is judged on the per-bond tolerance.** The sum of the distinct bonds' values was offered as a
  third "total" even for ONE bond ×n, on the total's tolerance (×n wider): `0.55×2↓` stood for 0.645, and a column scaled by
  0.85 read "ok". Bonds to S, Se, Te and the halides keep the wider reading (the sets differ by that much there). Reader A/B,
  1,130 papers: three bond-valence records moved, each to the conservative side (two `agrees` → `unverified`, one `disagrees` → `agrees`).
- **The column reading**: three or more cells, four in ten, ALL OFF THE SAME WAY is a whole-column difference (a scaled column
  leaves its small cells inside the tolerance, so "six in ten" missed it).
- **check37 (a flag): a reflection's intensity is not the paper's** — compared only where the list plainly came from the
  paper's table and the two intensity scales agree on four lines in five; then a line off by a factor of two and ten units.
- **The colours are tested** (issue #11): `tests/xl_eval.py` evaluates every conditional format row by row (`Book.fills`), the
  statements gauntlet holds every red fill to a red WORD on its row (0 of 1,127 workbooks differ), and the reduction rows are
  coloured through a cell of their own sheet (column P, "does not follow (check sheet)") instead of a rule that names another
  sheet — which Excel 2007 refuses and the later ones keep in an extension block openpyxl does not write. An element row that
  follows as it stands but stands out once the common factor is divided out now SAYS so (the red on those two columns had no word).
  The evaluator's SUMIF / COUNTIFS criteria are Excel's: case-insensitive, `*` and `?` wildcards.
- **A bond-valence workbook for a paper with NO .cif** (issue #18 — nine papers in ten): written from the bond distances the
  paper itself prints (`paper_bonds`), `<paper>_paper_bv.xlsx` beside the EPMA one, every valence a live `EXP((R0−R)/b)` of the
  paper's own distance; the bonds sheet says whose distances they are, and no anion sum is formed or compared (a bond table
  prints no multiplicities). Workbooks on the corpus: 97 → 340. The check sheet's red cells equal the disagreements the paper
  check HOLDS (`bv['held']`, per table — a doubted table's cells are shown, not red), 0 of 340 differ.
- **Gladstone–Dale: the paper's index is ONE cell the rest refer to** (issue #12): it was pasted into every formula as a literal,
  so a reviewer editing it moved nothing; the 'needed' K_C / n / D, the explanations and the category line now follow it, and
  an index of exactly 1 no longer divides by zero.
- **`tests/test_gui_routes.py` — the route gauntlet**: every one of the GUI's 50 routes, with no folder open (no 5xx, no process
  launched) and from a foreign host (403 from each). A new route is covered the day it is added.

## [0.11.1] — 2026-09-21

An adversarial review of the day's three releases (0.10.0, 0.10.1, 0.11.0): eight reviewers, one slice each, every finding
reproduced before it was fixed. The arithmetic held — the bond-valence workbook matched `compute` on every corpus .cif in
both hydrogen-bond conventions, and real Excel agreed with the test evaluator on every formula the writers emit (22,300
cells) — and what was wrong was what the tool SAID. Corpus gates after the fixes: the entries A/B (582 entries: 22 changed,
all intended), the paper checks (1,130 papers: no status changed), 769 EPMA, 62 bond-valence and 256 Gladstone–Dale
workbooks re-swept, the regression suite.

### Fixed — entries
- **check33 offered another mineral's density as "enter it".** A paper on several species states one calculated density per
  species and the reader takes the first: two entries of a three-mineral paper were told to enter the third's. Every other
  calculated density the paper states near Xtl Dx is now offered beside it ("enter the one that applies"); past 8 % of
  Xtl Dx, with no Xtl Dx, or in a sentence about a synthetic analogue or a related mineral, the value is a note. Set on the
  183 corpus entries that carry a Dx, blanked: no other species' value is offered as definite any more (8 were). A sink-float
  measurement beside the word "structure" is no longer read as a calculated density.
- **check29's "the paper's misprint" could swallow the entry's own typo** where the table is set in two blocks side by side:
  a one-keystroke value printed IN ORDER where the line belongs is the original, and vetoes the misprint reading; a value
  that is a line of the entry's own list is not "in its place". Nothing changed on the corpus.
- **check32 (blank Final Quality Mark) is a note on a calculated pattern** — 12 of the 13 corpus blanks, a quarter of the
  calculated entries even after review: a mark that class commonly receives later. Measured patterns still flag.

### Fixed — the workbooks' check sheets
- **EPMA: "PROBLEM: the stated basis does not reproduce the formula" was written wherever the stated and the found basis
  differed** — 74 of 772 corpus workbooks, against 0 basis flags from the composition check, over the tool's own conventions
  (an ammonium count, OH with no water row, a group sum), and "every coefficient follows" of formulas reproduced on no
  basis. PROBLEM is now said only where the composition check flags the basis; otherwise a note that says which case it is.
- **EPMA: fewer than three major elements** (a gypsum: Ca and S) — the median of two ratios is their mean, so one slip read
  as "the basis AND a number" and the right SO3 was "corrected". No common factor is divided out there, and no wt% is
  suggested. The "basis that would give the paper's coefficients" row no longer contradicts "ONE element stands alone".
  A formula none of whose elements is in the table gave an exception (and no workbook); it now gives a sheet that says so.
- **Gladstone–Dale: Σ wt% left out the O ≡ F,Cl deduction** — an ideal fluorite totalled 120.49, fluorapatite 101.59 — which
  raised a false "total" note and could turn "the paper normalised its analysis to 100 %" green for a normalisation that
  never happened. A wt% analysis may now carry the deduction a table prints (`O=F=-1.47`).
- **Gladstone–Dale: reds that were not the paper's arithmetic.** With no density the category line was always red (the word
  is now judged against the paper's own number, density or none); a category word broken at a line end ('excel‑lent') was
  passed over for the next clause's 'poor'; a calculated density that differs from Z·FW/(V·0.602214) for the values typed,
  and a constituent with no constant, are amber.
- **Bond valence: a BVS-column paper was judged by a bare ±0.08 vu on every candidate table the reader returned** — occupancy
  and coordinate columns as red rows, all "table 1" — while the console said "no table found". The sheet and the report now
  carry `check_bvs_sites`' verdicts (its tolerances by site, the mixed-site, sulfosalt and half-occupied rules) for the one
  table that agrees best. "paper − the nearer reading" is the nearest of each bond's valence and the total (an 'agrees' row
  showed −0.39), the column mean is over the cells that differ, a printed 0.00 no longer gives `#NUM!`.

### Fixed — the folder guard, the launcher, crashes
- **"Open it all" outlived its question**: browsing on left it up, and it then opened the HOME folder, confirmed, while the path
  box showed the batch. Browsing withdraws it, and the question names its folder.
- **A console tool typed in the home folder** took all of it as the batch (the morning's one-level-down rule, with an entry in
  a Downloads folder): it no longer does, and says so. A link to the home folder, `/Volumes` and a whole external drive are
  broad paths; a memory file that is valid JSON but not the memory is an empty memory, not a traceback.
- **The guard's holes**: the ancestor "source pool" never climbs into the home folder or a drive (a docx-only batch directly
  under home globbed all of it); a folder of hundreds of papers is asked about before Manuscript mode analyses every one;
  the survey counts what discovery will walk (links followed, only `review_out` left out).
- **Ten error paths of the GUI answered an HTML 500**: `errors` was never imported as `E`. An unreadable paper now costs an
  export its check sheet, not the workbook; the two Tables routes that failed with no folder open answer; the no-folder
  answer comes after the localhost gate (a foreign host got 409 for 403, and the in-flight count ran one short).
- `pxrd paper` no longer dies when the workbook cannot be written (open in Excel on Windows); `pxrd gd --paper` and
  `pxrd bv --table` say which file could not be read.

### Fixed — the edge inputs (the rest of the audit)
- **EPMA: the sheet and the reduction now agree where they did not.** Se and Te as anions beside oxides displace one O each,
  in the total as in the moles (the sheet knew F, Cl and S only: factor 7.72 against 12.67); with `--charge Fe` and S in the
  table the sheet's charge cell is of the cations alone; with a halogen and no true oxide nothing is displaced, so no O apfu
  goes negative. A point is used ONCE and must exist (`1-3,2-4`; a repeated index weighted a point twice, `0` took the last),
  and a selection is written as runs — Excel drops a function of more than 255 arguments, and every wt% then read 0.
- **The paper's workbook**: a coefficient printed as an integer (`Si3`) rounds at ±0.5, not the formula's common ±0.005; the
  printed total and page are given only when the wt% used are the first table's (the check may settle on another column, whose
  Σ was set against the first's total); text that begins with `=` — a note, a bond-valence cell as printed, the method
  sentence — is written as text, and the method sheet is cleaned of control characters.
- **Bond valence, from the GUI**: the export scores the parameter sets against the chosen paper and lists them, but the workbook
  stays on the set the pane shows (`run(follow_table=False)`); a paper left selected no longer moves it to another set unsaid.
- **Gladstone–Dale**: `H=2` in a formula is two H atoms — one water — not two waters (brucite came to 76.33 for 58.32).
- **`? look`**: a second click while the entry's view was still loading no longer resets the page under the later landing
  (one counter for both landers); a formula finding's Analysis stop is counted only where the entry's view has that field.
- **`_fit_page`** leaves alone what it cannot judge: a table sized as a share of the window, the cells of tables nested in the
  first row (the old template is one cell holding the whole entry), a document of several sections.

## [0.11.0] — 2026-09-21

### Added
- **A paper's analysis re-reduced step by step, as one sheet of live formulas** — `review_out/<paper>_paper_epma.xlsx`,
  written by `pxrd paper` and by the Tables mode's **Fill ▸** beside the `.csv` the EPMA tab reads. One row a
  constituent: wt%, the molecular weight as the sum of its atomic weights (`=2*74.922+5*15.999`), moles, the cations
  and anions per formula of the constituent (As2O5: 2 and 5), cation and anion moles, the oxygen a halogen replaces,
  the normalisation factor, apfu and O apfu — every step a formula of the cells before it, so a changed wt%, basis or
  stoichiometric factor re-derives the formula and the number a manuscript got wrong can be found. It is reduced on
  **the basis the paper states**; the coefficients the paper prints stand beside the reduction's with the difference
  and a per-element "does not follow from the table", and what the composition check found is written under it —
  including, where the stated basis does not reproduce the formula, the basis that does.
- **A `check` sheet in the paper's workbook: what differs from the paper is coloured, and the sheet says where the fault
  lies** — live, from the same cells, so it re-reads itself when a wt% or the basis is changed. A reduction normalises,
  so a fault has a shape: *every coefficient off by one factor* with no element left standing is the basis (and the
  basis that would give the paper's coefficients is shown — 8, not the stated 7), or an oxide reduced in another valence
  on an anion basis (`FeO as Fe2O3`: the line that explains the factor says so); *one element left standing* once the
  common factor is divided out is one wrong wt% or one misprinted coefficient — named, with the wt% that would give the
  paper's value, the shift of all the others called what it is (that one value's dilution, not a basis problem); several
  standing out is the table or the formula as read. The wt% read against the printed total is amber, never red (on the
  corpus a total that does not add up is the reading three times in four). H, ammonium and an element printed in two
  valence states are shown and not judged, as the composition check leaves them out. Rows of the reduction whose element
  does not follow are coloured too. Held against the composition check on the whole corpus (769 workbooks): where it
  says every coefficient follows, the sheet shows red on 4 papers — each a real difference between the numbers read.
- **The bond-valence workbook gets the same `check` sheet** when it is given the paper (`pxrd bv x.cif --table paper.pdf|manuscript.docx
  --xlsx`; in the GUI, the paper chosen in Tables mode). Every printed cell and Σ beside the structure's, red where it differs,
  amber where the table leaves a bond blank, grey where it is not compared and why. The verdict is the table check's own — it
  allows for what a formula cannot (a value per bond or the total over the ×n, an occupancy-weighted column, a contact under the
  cutoff) — and the numbers beside it are live: the tool's valence per bond and over the ×n bonds, the difference, and **the
  distance the printed valence would need** (R = R0 − b·ln s) beside the structure's, which tells a mistyped valence (an R no bond
  has) from a bond of another length. Below: the parameter set the table follows, each cation column's pattern (a whole column
  shifted = R0 and b — the set, or the valence state; one cell = a distance, a multiplicity or a typo), the Σ's with the paper's own
  arithmetic said first. On the 62 corpus papers with a .cif and a table the reader finds, the sheet's agree/differ counts equal
  the report's exactly.
- **The Gladstone–Dale workbook too** (`pxrd gd … --xlsx --paper paper.pdf`, or `--paper-ci 0.021`): the index the paper states
  beside the tool's for each density, and what would explain a difference, live — the analysis normalised to 100 %, each of
  Mandarino's variant constants for a constituent that has them, and the K_C, n and D that would give the paper's number. A
  difference is amber, never red (K_C rests on constants and on the whole analysis — the tool's own rule); the line that
  reproduces the paper's index is green; red is kept for arithmetic: a calculated density that is not Z·FW/(V·0.602214), a category
  word that is not the category of the paper's own number. An analysis with no constants at all (an element table) says so instead
  of dividing by zero.
- **`? look` crosses to the other document.** It used to stay in the pane being read — the `.pdf` or the entry — and comparing a
  value meant switching by hand. It is a tour now: the finding's targets in the document being read, then the flagged area in the
  OTHER one, then round again. From the `.pdf`, the second click (the third, for a finding with two places to look in the paper)
  lands on the entry's cell; from the entry, on the paper's line. The hint under the `.pdf` names the next stop ('? look again →
  the entry (docx)'); toggling the pane by hand, or looking at another finding, starts the tour again from what is being read. A
  finding with nothing to show in one of the two documents keeps to the other, as before. (From a reviewer's suggestion.)
- **`pxrd gui` asks before it opens a folder that is not a batch, and starts on its folder chooser when there is nothing to
  open.** Run from a corpus root — or a home folder — it used to index every document beneath and analyse each one: hundreds
  of files, minutes of work, by accident of where the command was typed. A quick bounded look comes first now (a home folder
  or a drive; more than 300 documents; a tree too large to count in a second and a half), and such a folder brings the GUI up
  AT ONCE on the chooser: why, *Pick a batch… / Open it all*, the folders opened lately, the picker. Opening it all is still
  one click (`--open-anyway` on the command line) — it just cannot happen by accident. The same question is asked when a folder
  is switched to from inside the GUI. With no folder given and none remembered, or a remembered folder that is gone, the GUI
  opens on the chooser instead of exiting with an error (the other tools, which have no picker, still stop).
  A look that runs out of time (a slow network drive) says so — "could not be counted in 1.5 s" — and never calls a batch a
  corpus for it; the question is asked before the entries are discovered, that walk being the long one on such a folder; and
  with no folder open, *Rerun all*, *Export triage* and *Import triage* are disabled, and the two that failed answer "choose
  one first" (an adversarial review of the day's changes: five findings, these three and a `#DIV/0!` cell fixed).
- **What the launcher remembers.** A folder is remembered for `pxrd gui` when the GUI OPENS it, not when the command is typed
  — a corpus root it asked about is not the folder to reopen — and a home folder, a drive root or a temp folder is never
  remembered for any tool. The folders opened lately are kept (eight, newest first; the batches the other tools were last
  pointed at seed the list).

### Fixed
- **A stated cation basis is counted over the cations the probe measured.** 'On the basis of 6 cations, excluding H+'
  beside `(CO3)5.88`: C — like B, Li, Be and N — is calculated from the stoichiometry after the measured cations are
  normalised, and the count leaves it out whether or not the sentence says so. The tool counted it, so every coefficient
  of such a carbonate came out at half the paper's and the stated basis read as failing. It is now tried as the stated
  basis written the tool's way, and such equivalents (this one, the anhydrous count, 'N cations excluding X') are tried
  before any group sum read off the formula, which reproduces its own cations by construction. Whole corpus, 1,130
  papers: five `basis` records unverified → agrees, each hand-checked, and no other status changed.
- **The bond-valence workbook (`pxrd bv --xlsx`, the GUI's export) gives the tool's sums.** Evaluated against every
  corpus .cif (208 structures) it did not: a mixed anion site (`O4/F4`) got one R0 where the tool weights each species
  by occupancy, a half-occupied water gave a whole hydrogen bond, two sites sharing a label were summed together, and
  with H as a cation the hydrogen bonds were counted twice. One row per cation species × anion species now, the H-bond
  strength times the occupancy it carries, each site summed over its own rows: no cation or anion sum differs, in
  either hydrogen-bond convention.
  The `cation sums` and `anion sums` sheets are now ONE `BV table` sheet, laid out as a paper prints it — anion rows ×
  cation columns, each cell the valence with its `×n↓` / `×n→` marks, an H bonds column, Σan / O–H / Σall on the right,
  Σ / expected / deviation along the bottom — and every cell is a formula of the `bonds` sheet, so a changed distance,
  R0 or b is seen in the table. Distances and occupancy shares are stored exact (shown to four decimals): the cells
  round as the tool's report does.
- **The Gladstone–Dale workbook (`pxrd gd --xlsx`) carries the whole calculation.** From a formula the wt% were values;
  they are now derived on the sheet — apfu → mass per formula unit → formula weight (less the oxygen F and Cl replace)
  → wt% → k·wt%/100 → K_C — with D_calc from Z, the formula weight and V, K_P, the index and its category as formulas,
  and a constituent without a constant says it adds nothing to K_C.
- **A control character in a paper's sentence no longer stops the workbook.** A pdf's lost minus sign arrives as `\x01`,
  which a worksheet refuses: 25 corpus papers raised, and the Tables mode's Fill ▸ would have failed on them. The notes are
  cleaned, and `check_paper` reports a workbook it could not write instead of failing with it.
- **`pxrd epma --xlsx`: the reduction sheet now derives every number it shows.** The O≡F,Cl correction, the anion
  sum net of the oxygen the halogens displace, the O apfu net of it, an element basis, a conversion (UO2 → UO3) and
  H2O by difference were values or were missing, so a sheet with F or Cl normalised on a different anion sum than the
  tool did; the mean averaged every point when `--points` had chosen some. A test evaluates the written formulas
  (`tests/xl_eval.py`) and holds every derived cell to the Python reduction over each basis kind.

## [0.10.1] — 2026-09-21

### Added — the reflection list against the paper's table, and against itself
- **`check34_lines_missing`: an observed line of the paper's powder table that the list lacks** (flag). Compared
  only where nine in ten of the entry's d values are in that table, and only for a handful of absences (<= 4);
  a row the reader gives no intensity is not counted. On the corpus: 108 comparable entries, 89 complete, six
  with real absences, every one hand-read — three were mistyped d values no other check saw, and the entry
  line of the same intensity beside the gap is named as the mistyped d. A line check 29 has already named is
  not repeated. The table is read through the GUI's isolating worker (`_pdf_worker.powder`).
- **`check35_blank_hkl_in_group`: one row of a multiply-indexed line has no hkl** (flag; 6 of 266 entries).
  The comment and `? look` land on that d's own row.
- **`check36_same_d_two_intensities`: one d entered twice with two intensities on a measured list** (note).

### Fixed
- **The logs head every entry by its mineral name.** A file ICDD returns as '…)_edited.docx' (and the tool's
  copy of one) had its name lost to the suffix, and the log showed the id twice; a Levinson suffix typed
  bare in the file name ('Lepersonnite-Gd') is headed the IMA way, and the suffix keeps the element's own case: 'LEPERSONNITE-(Gd)' — the entry's own
  spelling is still quoted in the finding beneath it.

### Added — from a human review's remarks on the Part 2 batch
- **Intensities that are all multiples of 5: a note** (`check19_intensity_detector`). The all-multiples-of-10 rule
  and the paper's own "visually estimated" were the two signs of a visual estimate; vargite's list (100, 55, 45,
  25, …) passes both, and a human review read it as one. Of the fifteen such corpus entries four are papers that say
  so, one is a Rietveld pattern whose authors rounded, two are scaled past 100 — so it is a note, never a flag.
  Where the paper names a digital area detector the note says what is odd about it: such a pattern is integrated,
  so the rounding is the authors' or an estimate from the converted pattern, and the .pdf does not say which — a
  rounded integration stays Integrated, only an estimate by eye is Peak / Visual. On the corpus: 13 entries gain
  the note, nothing else changed.
- **Every log says which version wrote it.** `annotation_log.txt`, `mindat_discrepancies.txt`, `triage_report.txt`
  and the manuscript triage report carry a `tool version` line — a report that comes back from another machine
  says which rules its findings and verdicts were given on. Import triage reads a report with the line unchanged.

### Fixed — a calculated entry asked to verify its radiation
- **A microprobe line list set off by semicolons read as a second radiation.** 'TiKα (TiO2, LLIF); FeKα (Fe2O3,
  LLIF)' — each line followed by its standard and analysing crystal — passed the skip that knows the bracketed
  and comma lists, so hopmannite's one MoKα source had an 'FeKα' beside it and the single-source rule could not
  fire. A line followed by a bracket naming an analysing crystal (TAP, PET, LIF, PC…) is a microprobe line. A
  broader rule (any line after a comma or semicolon) was tried first and turned two correct verdicts into flags
  on the corpus A/B ('(USMU, FeKα + β radiation', ', CoKα, rotating anode'); both sentences are regression cases.
- **'Verify' on a calculated pattern is settled as the flag already was.** 'No clear powder-context radiation'
  is what a calculated pattern's paper looks like; it now reads as the modelling-wavelength note. `check20` still
  asks whether the paper states the λ. Corpus A/B over 1,678 entries: 18 verify → calc, 3 verify → ok, no flag
  gained or lost; the paper-reader subset: no status changed.

### Fixed — an audit of the day's commits, and the `? look` button replayed over two batches
- **`check33_dx_blank` named numbers that are not densities.** Beside the density it read, the flag offered
  every number within reach that lay within 15 % of it: a calculated density of 1.930 was given the next
  sentence's refractive indices (1.652, 1.66), the measured density, or a cell volume in nm³ as further
  "calculated densities". A neighbour is now part of the same RUN of values — nothing between it and the value
  before but an esd, the unit, a phase label in brackets and a separator — and never the measured density.
  Two phases' values ('6.019 (Hak-Cd), 6.011 (Hak-Fe)'; a crystal-data row '2.198 2.127') are still listed. On
  the corpus: 17 entries flagged, every message read, each value a stated calculated density.
- **The launcher took any folder with a Word file one level down for an entries folder.** `I*.docx` one level
  down matched 'ICDD … statement.docx' in a Desktop subfolder, so `pxrd gui` typed on the Desktop opened the
  Desktop and overwrote the remembered folder. One level down a file must be NAMED as an entry
  ('I003448(…).docx'); the folder itself is judged as before.
- **`? look` on a reflection-list finding stayed on page one.** The entry pads a d with zeros the paper does not
  print ('1.7160' for the table's 1.716), so nothing was found — all six blank-hkl flags of the two batches.
  The d is searched with the padding dropped, then its neighbours BY d VALUE (the list is read across the
  table's two column blocks, so the rows either side of a line are from the other end of the pattern), which
  mark the powder table where the d alone is also a bond length pages on. Applies to every finding anchored on
  the list (checks 15, 29, 34–36).
- **`? look` lands on the term the finding is about.** The terms are ordered most telling first; the pane opened
  the page with the most hits of any term and its first hit in reading order. It now opens, of the pages the
  best term is on, the one where the terms cluster, and lands on that term — a line on a table's second page
  opens that page.
- **`? look` on a finding about the entry alone shows the docx cell.** A blank Final Quality Mark or a misspelt
  vocabulary word has nothing to find in the paper; the pane sat on page one in silence. A .dft Z disagreement
  now looks for the paper's 'Z = N', the Gladstone–Dale note for the paper's stated compatibility index.
  Replayed over the 193 findings of the two batches: 130 → 143 find their place in the .pdf, the rest being
  findings about the entry alone, which land on their cell.
- Whole-corpus run of the entry checks (1,678 entries): no check errored; the paper-reader subset (162 papers)
  against the last baseline: no status changed.

## [0.10.0] — 2026-09-21

### Added
- **`check32_quality_mark`: a blank Final Quality Mark is a flag** (13 of the 266 corpus entries whose
  template has the field). The comment sits on the 'Final Quality Mark' label — the blank value cell has
  nothing to anchor to — and `? look` lands on the value cell. An older template without the field is silent.

- **`check33_dx_blank`: Dx left blank although the .pdf states a calculated density** — a flag carrying the
  paper's value and its sentence (17 of the 43 corpus entries with a blank Dx; every one read as a stated
  calculated density). The value comes from `paper_extract.optics`; a paper that never says "calculated"
  ("the values obtained from the single-crystal structure refinement (3.19 g/cm3)") is read by a clause
  rule that requires Xtl Dx; a value more than 15 % from Xtl Dx is not offered, and a paper printing
  several (two phases, two methods) has them listed for the reviewer to choose.

### Fixed — from a re-run of the 2028 Part 2 batch in the GUI
- **A reflection finding sits on its own line.** The comment and highlight of a d that the .pdf does not
  print went onto the `d(A)` header of the list, and `? look` followed it there; both now land on the cell
  holding that d (the header remains the fallback). Finding keys are unchanged.
- **`? look` on a formula finding alternates** between the formula row and the Analysis field in the docx
  view — a finding such as "contains F, but the wt% list has no constituent for it" is about both.
- **A pdf whose pages carry a `/Rotate 180` their own text contradicts** is rendered upright (in memory —
  the file is never written). The image, the word boxes and the search hits now share one frame: on such a
  paper `? look` had flashed a box at the mirrored spot of an upside-down page.
- **An output copy whose tables overrun the page gets a page that holds them.** ICDD's generated entries
  carry 10 in tables; re-saved by Word onto Letter portrait with 1 in margins (a reviewer's copies of the
  Part 2 batch) the centred tables ran off both edges and the left of every row was cut. `_fit_page`
  turns the page landscape (or widens it) and sets half-inch side margins — page setup only, in the
  review_out copy only, never under `--inplace`; a page that holds its tables is left as it is.
- **`pxrd <cmd>` typed in a batch folder opens that folder.** The launcher took the current folder only
  when the entry docx sat at its top level; with the entries one level down ('2028_Part 2/Part 2/') it
  opened the REMEMBERED folder instead, silently. It now looks one level down (the tool's own output
  folders do not count), and says so on stderr whenever it does fall back to the remembered folder.
- **The one-keystroke hint names table values only.** A candidate must be written with the decimals the
  neighbouring found lines are printed with; a bond-valence sum elsewhere in a paper had been offered
  beside the table's value.
- **The paper's own misprint is a note, not a flag.** When the value the table prints in the line's place
  breaks the table's descending order where the entry's d keeps it — and the entry's hkl gives its d from
  its cell — the entry stands. A hkl re-fitted to a mistyped d cannot pass: the paper's value is then in order.

## [0.9.0] — 2026-09-16

The evening of 0.8.2. Three checks that need no table of conditions: the reflection conditions of a space
group derived from its operators, a lattice reduced to the one cell it has whatever setting a source chose,
and the entry's optics against the paper and its own Gladstone–Dale. Then the day's commits audited a third
time by three auditors with crafted inputs — five defects fixed the same evening, measured against a baseline
snapshotted before any edit. Unit suite 421, entries regression 336 PASS, corpus A/B 1,130 papers: five
records moved, every one a false 'agrees' removed.

### Added
- **Reflections the space group forbids** (`check30_extinctions`, `symops.absent`/`absences`): the
  condition is derived from the operators themselves (h·R = h with a non-integer h·t covers centrings,
  glides and screw axes), under every setting the symbol has, for every reading of a glued index row.
  One or two forbidden lines among many are a flag (a mis-index or a typo); many are a note (the space
  group, its setting or the indexing as a whole). Fires on none of the 657 corpus entries that carry a
  space group and an indexed list — and on 31 of the 64 fixtures when a wrong symbol is substituted.
- **Reduced cells** (`pxrd_review/lattice.py`: Niggli reduction after Křivý & Gruber, centred cells
  made primitive, `same_lattice`): the cross-source cell check (`check22`) no longer calls another
  SETTING of the same lattice a discrepancy — an I-cell against a C-cell, a rhombohedral against a
  hexagonal cell, a monoclinic cell with a and c exchanged or β and its supplement — the Mindat and
  the .cif comparisons say 'the same lattice in another setting' instead.
- **The entry's indices against the .pdf, and its own Gladstone–Dale** (`check31_gd_entry`): the mean
  of the entry's A/B/Q (ω and ε weighted by the sign) against the mean of the paper's indices — a flag
  when they differ by over 0.012 and the paper prints one set of indices (2 of 105 corpus entries, both
  genuinely different numbers); and 1 − K_P/K_C from the entry's own Optical Data, Dx/Dm and Analysis
  wt%, a note when it comes out two Mandarino categories worse than the paper states with the indices
  agreeing (the density or a wt%, or the paper's constants), or 'poor' where the paper states nothing.

### Fixed
- **A third adversarial audit (2026-09-16 pm), of the 0.8.1 and 0.8.2 commits and the checks above**, three
  auditors with crafted inputs; five defects fixed, each with a unit test, measured against a baseline snapshotted
  before any edit (`review_out/paper_checks_papers{aud3base,aud3fix}.json`, 1,130 papers): five records moved, every
  one a false 'agrees' the first fix removes (three coordinates tables read in part or shared with a second
  polytype, and the two bond-valence checks that hung on them); no other reader status changed. Unit suite 421,
  entries regression 336 PASS.
  - **A coordinates table read in PART could be verified 'by bonds' against the sites it never held**, and hand its
    half structure to the bond-valence check at FLAG grade. `paper_structure._loose_keys` gave a numbered bond label
    ('O1') the bare element as a last name, so it reached every O site — a bond table naming O1–O5 scored 5 of 5
    against a table holding only O10–O12; on a corpus paper with every second anion site removed the gate went from
    False to True with all 20 bonds to the missing sites 'reproduced'. The bare key is now the SITE's only (a bond
    table's bare 'Al' still finds Al2); a numbered query that names no site is not compared.
  - **The extinction check was blind for P21/c, C2/m, P21 and most of C2/c.** `symops.absences` intersected the
    condition over every operator list the table keys under a symbol — and the table keys every SETTING of a group
    under it (the P21/n and unique-axis-a operators of .cif files labelled P21/c; the A- and I-centred settings under
    C2/c), so nothing was forbidden in P21/c and only h00/0k0/00l in C2/c. `symops.setting_variants` keeps the
    lists that ARE the setting the symbol names — the pure translations of its lattice letter, and for a short
    monoclinic symbol a two-fold along the unique axis with the screw component written and a mirror across it with
    the glide translation written, origin-free properties of the operators; a genuinely ambiguous short symbol
    ('P21/b': unique axis a or c) keeps both readings and reports what both forbid. Still 0 findings on the 657
    corpus entries with a space group and an indexed list; on the 87 fixture entries with P21/c substituted for
    their symbol the old rule caught none, the new rule 56 (28 flags, 28 notes).
  - **A wrong optic sign drew two flags, the second blaming the indices.** `_entry_mean_n` picked ω by the sign;
    ICDD writes the first index as ω and Q as ε (65 of 66 corpus uniaxial fields), so a wrong sign moved the
    entry's mean by (ε − ω)/3 and check31 called it a mistranscribed index. ω is the first index written; a sign
    that contradicts the order is check24's finding and check31 says nothing.
  - **The abstract's own symbol could be a relative's.** `symops.find_own_in_text` took any sentence naming the
    mineral and a cell: 'Testite is a member of the alluaudite group, whose members are monoclinic, C2/c, a = …'
    and 'is related to sarcopside (space group P21/c, a 10.4 …)' returned the relative's symbol, overriding the
    first-phrase choice that had it right. The mineral must be the subject: named before the symbol, within a
    clause, with no relation word between (member, group, related, analogue, isostructural, similar, cf …).
  - **The reduced-cell compare could not see Mindat's cell in another setting.** `check22` passed the docx
    symbol's centring letter for Mindat's cell (Mindat's symbol is an id the tool has no table for) and read
    Mindat's γ = 0 as 90°, so an I- against a C-setting and a hexagonal against a rhombohedral cell always fell
    back to the old discrepancy note. Mindat's cell is now tried under every centring its metric allows, its lost
    γ is 120° when the entry's symbol is hexagonal or trigonal, its c is a for a cubic cell, and an R symbol on a
    cell already on rhombohedral axes is read as primitive on either side.
- The coordinates reader and the bond reader, rounds 7 and 8 of the gauntlet, and the recall inversion
  (see `review_out/gauntlet_log.md`): coords 356 → 368 of 554 verified on the corpus; a 20 % wt% fault
  caught 23 → 35 % of the time.

## [0.8.2] — 2026-09-16

The afternoon after 0.8.1. Recall re-measured first (`tools/seed_faults.py`, 1,131 papers): identical
to the 2026-09-09 curves, so nothing since 0.6.0 moved it. Then the coordinates reader driven a round
further on the whole corpus, from its failure classes, and the thirteen red composition findings read
one by one against the papers — ten were the papers' (nine distinct), three were the tool's, and each
of those was a class. Measured against a baseline snapshotted before any edit
(`review_out/paper_checks_papers{audit2fix3,it76full}.json`, 1,130 papers): only the intended readings
moved, nothing lost; recall re-run after the composition change, unchanged. Unit suite 393, entries
regression PASS.

### Fixed
- **A displacement-parameter table, or a block of refinement indices, read as the coordinates table.**
  Printed to a coordinates table's decimals (`0.00524(18)`, `R1 = 0.0266`) and, for one paper, under a
  header the reader trusts, four corpus papers had one read as sites — two built into a structure and
  judged (instability 2.5 vu, 'unverified'), two compared to the .cif ('0 of 3 sites fall on a .cif
  site'). Nothing in such a table stands away from 0 the way a coordinate of a third site must
  (`paper_structure._no_adp`, both read paths); and an English word ('Final', 'Peak' — the rows of a
  refinement block) is not a site label, while 'TeA'/'TeB' (a split site) and 'BiI' stay labels — the
  first form of that rule cost hitachiite its verdict. All four are an honest `none` now.
- **The bond table's name for a site the coordinates table prints otherwise.** `bv_check` merges two
  rows at one position into one site 'Ba/Ca', so neither occupant's bonds were compared (11 of 27 and
  9 of 18 'not compared' with every label present); a split member without its letter ('Sb9' for
  'Sb9a'/'Pb9b', and 'O11a' for 'O11'), a hydroxyl or water site by its oxygen number ('O8' for
  'OH8'), a padded number ('O1' for 'O01' — added after the hydroxyl rule alone sent one paper's O1 to
  its OH1 and cost a verified structure) are found when nothing exact is (`bond_hits`, `_loose_keys`;
  exact names always first, so a table printing both O8 and OH8 is matched exactly). Whole corpus
  coordinates 347 → 356 of 554 verified, ten papers to `agrees`.
- **'Av.' as the mean column.** A table of fourteen analyses headed `#009 … #022 Av. St.dev.` had its
  first analysis read as the mean: 'Mean', 'Average' and 'Avg' were the vocabulary, 'Av.' was not, so
  the 'wt%' token over the label column won. One red finding (Ca 0.94 vs 0.865) was this.
- **An element the table prints in two forms was reduced twice.** `MnO(tot) 0.59` beside the
  `Mn2O3(calc) 0.50 / MnO(calc) 0.14` it was apportioned into (and `Fe2O3(tot)`/`(calc)` 1.32, one cell
  read twice); `TiO2 5.54` as analysed beside `Ti2O3 4.48` recalculated. A cell read twice is one row;
  then the printed total arbitrates — rows adding to more than it by over 0.3 wt%, and one row of a
  twice-printed element whose removal lands on it within 0.15, is the recalculated one
  (`_drop_recalculated`; two forms both analysed, FeO and Fe2O3 by Mössbauer, add to the total and are
  untouched). Where the total was not read (one came out 13.81), rows over 101.5 lose a twice-printed
  form only when the formula then follows and did not before (`_overshoot_drops`, in `_resolve`
  beside the oxide alternatives). Two red findings were this (Mn 0.05 vs 0.086, Ti 0.57 vs 1.04); a
  third paper gained its basis, index and compatibility readings because a stray 'H2O 15' in its prose
  analysis is now settled by its total. Composition reds 9 → 6 on the corpus.
- **The deviation line names the oxide form the paper's arithmetic used.** A table printing `SO4 14.58`
  whose S 1.96 follows only from 14.58 read as SO3; a table printing `Mn2O3 4.09` with an Mn3+ formula
  whose Mn 0.95 follows from 4.09 read as MnO. The finding stands (which of the label and the number is
  wrong is the paper's to say) and now reads '— the coefficient would follow from the printed 4.09 wt%
  read as MnO (0.949): the table's Mn2O3 and the formula's arithmetic disagree' (`_other_form`).
- **'? look' on the .pdf found nothing for the commonest flag.** Replaying the button's own term
  builder over the two fixture batches (113 finding rows with a paired .pdf): a formula-integrity
  finding built no search term in 14 of 25 cases (its evidence is the formula string, too long to
  search, and the look-group that reads the Analysis field was keyed on a code that no longer exists),
  a missing-IMA finding never had one, and the density, synthetic, calculated-pattern and provenance
  findings mostly missed. The chemical look-groups now take their wt% values from the docx Analysis
  field (they appear verbatim in the paper's table), a long evidence sentence is searched by two
  windows of its opening words, a density finding falls back to the unit, an anode is tried as
  'CuK' / 'Cu K' / 'Cu-K' with the docx λ as the last resort, and 'IMA' / 'synthetic' are keywords.
  Rows landing on their evidence: 87 → 110 of 113; the three left are papers that never print the
  term. The snippet box now says what was searched, where a second click goes, and when nothing
  was found (a miss used to open the evidence page in silence, indistinguishable from a hit).
- **Manuscript mode, a .pdf manuscript:** a calculation line naming no table (Gladstone–Dale, the
  cell, the species, density) said "there is no place in the docx to jump to"; it now shows the page
  its own words are on, highlighted, as the docx anchors do for a .docx (`_ms_pdf_pages`).
- The docx side was audited the same way — every anchor the checks emit, on 243 docx, against the
  cell the annotator highlights: all resolve; the GUI lands on the value cell where the annotator's
  merged-label lookup lands on the label ('Radiation =', 'Spacing Instr. :'), which is the better of
  the two. No change needed.

### Changed
- **A page-text cache for the corpus runs** (`paper_extract.set_page_cache`, `$PXRD_PAGE_CACHE`;
  `tools/corpus_paper_extract.py` and `tools/seed_faults.py` set it, `--no-cache` is the reference
  path). What MuPDF gives of each page — the text, the word boxes, the layout's line directions, the
  size — is kept on disk keyed on the pdf's content, the PyMuPDF version and the one piece of reader
  code inside it (`_line_dirs`); `page_lines` reads a cached page as it reads a live one. No reader
  code is in the key, so a reader edit never invalidates it: a corpus A/B re-runs every check on
  every paper by design, but a third of its CPU was extracting the same text as the run before. Off
  for the shipped tool, which reads each paper once. Outputs byte-identical cached, cold and
  uncached (the acceptance test); 150 papers at 11 workers: 16.4 s uncached, 11.1 s from the cache
  (CPU 142 s → 103 s), filling it costs nothing extra; 24 MB on disk per 150 papers.
- **The structure geometry pruned, two helpers memoised.** With the page text cached, a third of a
  corpus run's CPU was `bv_check.Structure` asking 27 metric distances of every pair of sites (the
  site merge, the ammonium and sulfide tests, `_equivalents`) — 39 million inner terms over forty
  papers. `Structure.within` answers "some image within cutoff" from the per-axis width bound
  first, the bound `_images_within` already uses, and measures only the images that pass it: an
  exact prune, never a loss. `_bv_norm` (900k calls for a few hundred labels) and `_norm_text` (the
  whole paper, twenty times over) are memoised. 150 papers from the cache: 11.1 s → 7.5 s (CPU
  103 s → 73 s), outputs byte-identical.
- **Corpus runs, measured.** 150 papers on an 11-core machine: 32 s at 5 workers, 24 s at 8, 20 s at
  11 — the harness's default cap of 8 cost 15 % and is gone (every core). The per-paper CPU (~1.2 s)
  is the cost: a third in MuPDF text extraction, a third in the analytical-table reader, a fifth
  building .cif structures. Two pure caches take the cheap part: `text_of` is kept per file like
  `_pages` (a review read the text four times over, each a full extraction), and `_constituent_ok` is
  memoised (half a million calls over forty papers, a few hundred distinct tokens per paper): 14 %
  less CPU on the 150-paper A/B, every output file byte-identical apart from the failure log's timestamps.

## [0.8.1] — 2026-09-16

A second adversarial audit (2026-09-16), of the 0.7.2 fixes and the 0.8.0 commits, run by four
auditors with crafted inputs and read-only scans of the WHOLE corpus — which is where the 0.7.2
regressions showed that the 162-paper gauntlet subset could not (a bond table lost, nineteen space-group
symbols moved). Every finding fixed, each with a unit test and a regression case; the fixes measured
against baselines snapshotted at 0.8.0 before any edit: entries A/B over 619 docx (only the intended
findings changed, no cell verdict moved), paper-reader A/B over 1,130 pdf
(`review_out/paper_checks_papersaudit2{base,fix3}.json`). Unit suite 383, entries regression 336 PASS.

### Fixed
- **A biaxial (−) entry could be flagged "uniaxial … optically positive"** (`check24_optical_2v`): an A
  index written `A=n.d.` or `A(est)=1.600`, a `2V(calc)=82.7`, `2V(calc) 80.9°` or `2Vz=60` was not read,
  so the field looked uniaxial and its sign was judged from ω and ε. The uniaxial reading is taken only
  when the field carries no A and no 2V at all; the qualified forms are read for the biaxial computation
  (21 corpus fields write `2V(calc)=`). A `±` esd is no longer "collapsed into the last digit"; `Sign=—`
  (Word's em dash) is a minus; `Sign=±` is a note.
- **The welded '×2' count lost a whole bond table** (`paper_bonds`, 0.7.2): read only on a page whose font
  prints 'þ'/'¼', it dropped the anhydrite-type table of a page that prints neither (I002526: 'Ca–O1 32
  2.332(13)' on six lines). A column of such counts — three lines of label, bare '3N', distance — is the
  font's own evidence now (`_welded_column`); the seven single noise lines on plain pages stay dropped. One
  paper moves corpus-wide, the one lost.
- **`symops.cell_system` is the downward closure** of the metric's highest symmetry: an all-90° cell
  allows orthorhombic, monoclinic AND triclinic (tetragonal/cubic with equal axes), a cell missing an angle
  every system. 0.7.2 had added monoclinic alone, so three triclinic minerals whose angles the text layer
  lost were disowned for a relative's P21/c, and the English word 'An' at a sentence start read as the
  setting `An` again. A two-letter symbol with no digit or bar is taken only right after a 'space group'
  phrase, and `paper_structure.choose_symbol` prefers the abstract's own statement — the first symbol of
  the text when its sentence names the mineral and states the cell (`symops.find_own_in_text`). Measured
  against Mindat's crystal system over 1,259 papers: 758 → 768 right; the six wrong choices restored, the
  eight 0.7.2 helped kept, no build verdict changed.
- **The check4 measured-pattern guard lost the plural** ('the powder patterns were collected') in 0.7.2 and
  still took a SIMULATED pattern that 'was obtained' as measured (ferriprehnite). `patterns?` /
  `diffractograms?`, and a sentence that says simulated / calculated / theoretical / generated before the
  verb does not vouch. Corpus: the five plural papers regain the guard, six simulated ones lose it, one
  entry moves (ferriprehnite, now flagged).
- **Manuscript '? look' landed in the wrong table** (`review_gui._ms_docx_anchors`): a constituent with a
  superscript footnote (`SiO2ᵃ`) missed its own table (the reader drops the mark, the docx text kept it)
  and the fallback jumped to the same oxide in a Gladstone–Dale or comparison table; a "bond distances and
  bond valences" caption tied with the bond-valence grid and the earlier distance table won, so an
  `O8–Na2` finding scrolled to the `Na1–O8` distance. Cells are normalised as the reader normalises them,
  a table whose CELLS are the labels outranks one that mentions them, the fallback stays within the
  section's tables, `table N` in a finding picks the N-th grid (two minerals), the cell anchor accepts
  `a=16`, the species line anchors, and each table is indexed once (300 findings on a 60-table docx:
  34 s → 0.4 s).
- **Paragraph numbering drifted between the rendered docx and `refs_check.load_docx`** on a content
  control (`w:sdt`) around a row or cell and on a legacy VML text box — every '? look' after it landed
  N paragraphs early. Both sides now walk through content controls and skip every text box; a unit test
  pins the two numberings on eight docx shapes.
- **A blank bond-valence cell under 0.10 vu is classified by `bv_check`**, not by the GUI re-parsing the
  message (`BLANK_INFO`): the line says "under the cutoff most tables print (not a difference)", and
  the CLI and the GUI agree on what is red.
- **One finding per fault, two more shapes** (`check27_formula_integrity`): a split symbol in the
  Analytical row ('N B0.05') no longer also fires the row-vs-formula disagreement and the element notes
  (ferroinnelite, alicewilsonite-(YCe): three findings → one); one duplicated constituent standing for a
  missing one of the same family folds into a single finding ("CaO twice — the second is probably BaO";
  airdite, mendozavilite-KCa), while two unrelated faults stay two (dacostaite).
- **A wt% range list is not a wt% list**: the range guard of the constituent regex was defeated by
  backtracking ('Ir 3.28-5.50' read as 3.2), so selenolaurite's ranges-only field drew a "no constituent"
  flag. Also: 'H2Ocalc', 'CO2calc' and the rare-earth shorthand 'RE2O3' no longer invent an element
  ('H2OCAlC?', rhenium); 'FeOtot', 'FeOT', 'FeO*' count for Fe; a parenthetical inside the list
  ('(Li 0.77 by ICP-OES)') and a sentence after the formula no longer cut the field in the wrong place;
  a General formula's listed substituents ('( Mg , Fe , Mn )') are a note, not a flag; an integer
  coefficient inside a bracket group counts toward its Σ, and a Σ that survives as 'S' is kept out of the
  coefficient comparison; the "formula has X instead" wording pairs each extra constituent with one
  missing element.
- **`check28`'s "simple ratio" is a structural ratio**: p, q ∈ {1, 2, 3, 4, 6, 8}; 5/4 and 6/5 tiled
  the 25–30 % band so every such gap was called a Z error. All thirteen corpus flags stand; kodamaite's
  '5/3×' is now the plain 70 % flag.
- **`check29`'s allowance scales**: one unprinted line below 20 lines (an abstract naming eight of a
  ten-line list is not a misprint), two from 20, 5 % above 40; a d with a tail ('3.220b', '3.220(1)') is
  looked for by its number and an integer d no longer errors; a decimal comma counts as printed; the
  message says "verify against the paper's table" rather than asserting a mistype. The three corpus flags
  stand.
- **`check15`'s tolerance follows the printed precision** (a 2-decimal '1.50' matches 1.5049), and every
  strongest-lines sentence is scored — a paper with an isotypic second mineral's list first no longer
  flags this entry's lines; the fewest-miss sentence is reported only when none matches fully.
- **The first merge of these fixes had lost `build`'s 'other symbols the paper states' fallback** — the
  variable that filters them had moved into `choose_symbol`, the NameError was swallowed by the fallback's
  own try/except, and five papers lost their verified coordinates (hydroxylgugiaite, lesukite,
  uchucchacuaite …), and the cells were filtered by the chosen symbol's system alone, so a two-mineral
  paper whose coordinates table belongs to the OTHER phase (hexathioplumbite: the abstract names P63,
  the table its bonds verify is the cubic phase's) lost its cell before the other symbol was tried. The
  whole-corpus A/B caught both before release; the variable is back and the cells are filtered by every
  symbol tried.
- **`tests/test_triage_import` pins the `.txt` guard by its own message** (the parser's error also
  contained '.txt', so the test passed with the guard removed) and adds the 8 MB case.

## [0.8.0] — 2026-09-14

A human review of the 2028 Part 2 batch and an independent read of the same 37 entries against their papers
turned up about seventy defects neither the tool nor the reviewers had caught. The classes a program can
see became checks, each measured on the 870 new-template entries on disk and every flag read before it
shipped; then an audit of the day's commits. Corpus A/B over 1,707 docx: only the new codes added, the 26
case-only vocabulary flags and the metaheimite false positive removed. Regression suite all PASS, unit
tests OK. Bundled Mindat snapshot refreshed 2026-09-14.

### Added
- **Entry consistency checks that need no .pdf**, from an independent read of the 2028 Part 2 batch against
  the human review of that batch (2026-09-14). Each defect class was listed on the corpus hit by hit before it shipped.
  - `check27_formula_integrity` (codes `formula`, `analysis`) — the syntax of the formula fields and of the
    Analysis field's formula: unbalanced brackets, a lost decimal point (`Al042`), a colon for a point, a split
    symbol (`T B0.01`), a valence superscript read as carbon (`Fe3 C0.20`), a simplified-formula site in the
    Analytical row; malformed or duplicated wt% constituents (`BAO`, `P205`, CaO twice); an element of the
    formula absent from the wt% list or the reverse (fluorine missing, SeO2 standing for TeO2); the Analytical
    row against the Analysis formula; an element in one ideal field only. One finding per fault.
  - `check28_density_consistency` (code `xtl_density`) — Xtl Dx against Dx: a simple ratio (2, 1/2, 3/4 …) is a flag (Z or
    the formula unit is wrong), any other gap of 30 % or more a flag, 12–30 % a note.
  - `check24_optical_2v` also reads the sign (`Sign=1`), a mistyped esd parenthesis, an index whose esd was typed
    as a digit (`1.6142`), and a uniaxial sign that contradicts ω and ε.
  - `check29_reflections_in_paper` (code `reflections`) — a d of a measured reflection list that the .pdf never
    prints although all but a handful of the other lines are, with the printed value one keystroke away.
- **The strongest-lines sentence is checked line by line** (`check15_strongest_lines`), not only its I=100 line —
  a line lost at a table's page break, a transposed d. A sentence about the CALCULATED pattern, and a
  Calculated / Other spacing, are skipped (the metaheimite flag compared dcalc with the measured list).

### Fixed
- **Case alone is no longer an instrument-vocabulary fault** ('Monochromator crystal').
- **Manuscript mode: '? look' on a calculation finding of a .docx now scrolls the docx view to
  the cell the finding names** — a bond-valence line to its row label or column header in the
  bond-valence table, a composition line to its constituent's row in the analytical table, a
  powder line to its d value, a section head to the table's caption, the Gladstone–Dale and cell
  lines to the sentence that states them (`review_gui._ms_docx_anchors`). Before, every such
  finding on a .docx said there was nowhere to jump to, which on a manuscript is nearly every flag.
- **A clean bond-valence table no longer comes up as a flag**: 'N cells compared, 0 disagree' was
  matched by the flag regex looking for '0 disagree' after the word (agujaite2). A blank cell for a
  bond under 0.10 vu — a contact below the cutoff tables print, which the checker itself does not
  count — is information, not a flag (`_calc_kind`).

## [0.7.2] — 2026-09-10

An adversarial audit of the 2026-09-09/10 commits (0.6.0–0.7.1), read diff by diff and probed against
the fixtures; every finding fixed, each with its regression case. Unit suite 322, entries regression
all PASS, corpus A/B on the gauntlet subset (`review_out/paper_checks_papersaudit{0,1}.json`).

### Fixed
- **Continued coordinates tables walked too far back** (`paper_structure.paper_sites`): after the
  widest 'Cont.' part absorbed the headed part before it, the walk went on into any earlier headed
  table with other labels — another mineral's — and merged that too. It stops at the head now.
- **The check4 'pattern was measured' guard read the sample as the pattern** ('Powder for the
  microprobe mounts was obtained by crushing a crystal') and silenced a genuine calculated-pattern
  flag. The guard asks for the pattern, the data or the diffraction between 'powder' and the verb.
- **A monoclinic cell printed at β = 90.00** read as orthorhombic to `symops.cell_system`, so the
  paper's own P21/c could be disowned for a relative's orthorhombic symbol; an all-right-angle cell
  is allowed the monoclinic reading too.
- **A bond-valence cell's count before its sign with no arrow** ('2×0.41', '2× 0.22') lost its
  value: the '0' of the value was read as the count. The count may not be followed by a decimal point.
- **The welded '33' before a distance** is read as ×3 only on a page set in the font that loses its
  symbols, as the same count after the distance already was (both corpus pages that print it are).
- **The per-page coordinates-table cache** is keyed on the file's size and mtime like the page cache,
  so a pdf replaced under a running GUI is read again.
- **The triage import's JSON `{path}` form** opens a `.txt` under 8 MB only, so it cannot be used to
  probe for other files on the machine.

## [0.7.1] — 2026-09-10

Round 5 of the gauntlet, resumed from the failure log of 0.7.0 (`failure_classes.py --silent`): the
readers' silent `none` / `nooracle` on papers that print the thing, class by class, each mechanism
generic and re-run on the whole corpus (`review_out/gauntlet_log.md`, round 5, it67–it70). Silent
`none` fell from 38 to 16 (coordinates), 67 to 0 (parameter sets), 38 to 31 (bond-valence tables);
whole corpus coordinates 59 → 62 %, parameter sets 60 → 64 %, bond-valence tables 69 → 71 % (reds
6 → 5), optics 66 → 68 %; on the 115 papers that print everything, coordinates 89 → 92 % and the
composite 76 → 80.

### Changed
- **The parameter-set record is never a silent blank.** When the paper names no set the tool carries,
  the record says what it does say — a source the tool does not have ('parameters from Brown (2009)',
  Hong et al. 2004, Allmann 1975), a program (ECoN21, JANA2006, VESTA), or no citation in any of its
  bond-valence sentences — as `nooracle` with the reason; the table's own verdict is never written
  onto it. A set named beside 'parameters' without a bond-valence keyword, a table's notes that run on
  without a full stop, a reference-list title through hyphenation or truncated, are read. A paper
  whose parameters come from several sources — a set the tool has for some bonds and one it lacks
  for others (Tl–S from Biagioni et al. 2014, Te–O from Mills & Christy 2013) — is `mixed`, and a
  bond-valence table that differs under it is a doubt, never red; Gagné & Hawthorne for the oxide
  bonds beside Brese & O'Keeffe for the sulfide bonds is the tool's own default, not a mix.
- **Coordinates tables.** Labels the reader refused: 'Fe2_1' (a pseudo-symmetric refinement's twins),
  'M(2a)', "O6'" (a prime is a site of its own — the old reader ended the table at it as a repeated
  label), '(Cu,Hg)', 'T1(Al,Si)' and 'T*1(Al)' (the occupants go to the row's tail), 'A(16c)' and
  'Pb1(≡A)', 'Sb1/Sb1’', 'V 1' set as two tokens; the label nearest x when the facing column's
  sentence heads the line ('As noted above, michalski M3 …'); a split site printed as two rows with the
  same coordinates merges; the Atom column's element with its charge and share ('M1 4c 0.25 Fe3+',
  'T 8i 0.38(1) As5+ 0.12(1) P'); coordinates printed ×10⁴ under a caption that says so of the
  COORDINATES; a site letter's conventional element when nothing names it (T tetrahedral — Si, P, As,
  B —, A/X the large cation, M/Y/Z octahedral; before, T(1) took the formula's leftover cation, Ca in a
  silicate's tetrahedron at 218 vu); the row tail read for occupancy tokens only (the facing column's
  prose read as Si, Y, Li); a table of one or two sites is `nooracle` with its count.
- **Two-mineral papers.** The structure is judged by ITS bond table: when the paper prints two
  coordinates tables the bond tables are split by repeated cations, the best overlap nearest the
  table's page is chosen (the n-th in print order for the n-th table), and only the bonds naming that
  table's own sites count — the union of both minerals' tables had failed a structure that reproduced
  every one of its own 57 bonds for not covering the other's 78. A one-table paper keeps the union.
- **Bond-valence tables found:** the BVS printed under each site's block with the site in the mark
  ('BVS(Ni1) 2.07'), a 'B.V.S.' column head, a sums table set as (site, sum) pairs across each line under
  its caption ('Tl1 1.25 Sb1 2.31 S1 1.76'), a grid whose multiplicity marks are typeset as tokens of
  their own between the cells, a BVS column that ends where its labels repeat (three minerals stacked).
- **Optics and the compatibility index.** 'isotropic, with an index of refraction 1.999(5)', 'the
  refractive index n is 1.65, which is calculated by N = Kd + 1' (read, and marked computed), the
  mean-index sentence at its real length, 'the index of refraction is >1.8' as a bound; a constant
  ('k(UO3) = 0.118 from Mandarino', 'a corrected Kp value of 0.253 for vanadyl') is never the index.
- **The analytical table.** Soft hyphens are stripped from the text and the page's words (every
  constituent of a Springer prose analysis began with one); a bracketed note inside a prose run is not
  part of it; a wt% table set line by line beside a trace-element table is read, not skipped with it.
- **Space-group phrases.** 'triclinic, P1, a = …', 'Monoclinic, C2/m' (a crystal-data block) and
  'spatial group' — looked at only when the paper prints no 'space group' phrase, which comes first.

### Fixed
- The coordinates builder crashed on a label with a full stop ('Pb.' read as an element and the
  number '.'): three papers never built.
- A .cif with no cell or no sites made the paper an error; it is checked as one without a .cif for the
  structure checks, says so, and the cell check keeps the file's cell.

## [0.7.0] — 2026-09-10

The paper readers run against the WHOLE corpus (1,130 papers), reader by reader over the papers whose
crude scan says they print the thing, with a failure log to work from. Every iteration's classes,
mechanisms and numbers are in `review_out/gauntlet_log.md` (round 4, it27–it66).

### Added
- **A reader failure log.** `pxrd paper X.pdf --check --log-failures [FILE]` appends one JSON line per
  reader that did not verify — field, status, detail, page, the sentence it read from, `silent` when the
  paper prints the thing and the reader has nothing, and a per-reader context (the table rows read, the
  build's index, closure, bonds and misses, the bond-valence lines, the optics dict) — to
  `review_out/reader_failures.jsonl`. The corpus tool writes `paper_checks_failures<tag>.jsonl` on every
  run; `tools/failure_classes.py FILE [--field --status --silent --paper --show N]` groups the records
  into classes and prints one class in full. Its first use found a misread the same minute.
- **The valence-state convention** (`_swap_valence`): a cation column, or a site's sum, that reproduces
  under the element's other common oxidation state (Fe2+ against the .cif's Fe3+, Cu+, Mn, V, U …) is
  the valence the paper computed with — noted, not counted. A site-keyed `ox_override` now beats the
  .cif's own statement; the element-keyed `--ox` still yields to it.
- **The corpus tool's GAUNTLET section** ends with a WHOLE CORPUS block: each reader over the papers that
  print its thing, S being the intersection.

### Changed — the readers, each a class found on the corpus and re-run on all of it
- **Bond-valence tables (52 reds → 6, 51 → 69 % verified).** A proportional cell tolerance (0.015 + 2.5 %;
  mixed sites and bonds to S, Se, Cl, I wider); a single value equal to one bond of a multi-bond cell
  (the ×n mark not read), any value of a multi-value cell, the bond distance printed beside its valence,
  a Σ or a distance read into the grid ('O8–As 4.742': not a bond valence, noted); a bond the paper's
  own bond table did not print is the READ's gap, not the paper's; a column printed as one species'
  share of a mixed site; the per-column parameter excuse per site first, then pooled per element, with
  a proportional bound; a site whose element is the paper's own prose assignment and in which no cell
  agrees; a sulfide S, Se or Te in an oxysalt (no O within reach) is the anion, not S6+; no anion sums
  against a structure the paper prints; a table read short, or naming a strong bond the .cif lacks,
  is a doubt where it would otherwise be red; no verdict under eight cells; a bond-distance oracle
  off by a whole valence unit may agree but never convict. The grid finder: a species header
  ('(Zn0.699Fe3+0.301)'), a tourmaline's X Y Z T B letters onto 'AlZ', 'LiY/AlY', a lone '(Cu)', a
  site name set as two words ('T' '1A' — welded at word level, so the coordinates reader gets it too),
  a single renamed site's alias, an esd grid the caption calls bond valence, prose beside a cation
  label rejected as a grid, and the loose header readings kept out of the finder (three of them
  silently broke real tables on two-column pages before the corpus run caught them).
- **Parameter-set citations (31 → 60 %).** 'Gagn´e' with the accent as its own glyph, 'AL- TERMATT',
  a table's notes over 400 characters, BVS / 'BV parameters' keywords, a reference-list fallback when
  exactly one set is there (never a red on its own), either U6+ reading of an unqualified citation.
- **Optics (60 → 66 %).** ε before ω, no equals sign ('α 1.745(5)'), np/nm/ng, a Symbol-font a/b/c,
  ω delivered as x, parenthesised values, 'β = γ', two of three indices, nmin/nmax, an open-e for ε,
  the computed-index sentences, a lone isotropic index (never the oil's, never 'reported by'); 'could not
  be measured' is a `nooracle` with the reason; a comparison table's row is rejected by its loose
  indices; indices only (never 'Δα = 0.005').
- **Coordinates (55 → 59 %).** A table whose sites are all crystallographic names (an amphibole's T1,
  M(1), A2) is judged by its printed bonds; a .cif in another setting falls back to the bonds; a
  structure that passes index and closure and reproduces every bond it can compare agrees; the bonds
  oracle reaches the longest printed bond; the index leaves a lone site off by ≥ 1 vu out (a misread
  row) and says so; every symbol the paper states is tried, the bonds deciding (a relative's Im3̄m
  before the paper's own I213); the overbar lost to the font ('Fd3m'), a macron glyph, a Cyrillic С;
  crystal-data rows and displacement labels ('Cell', 'Ueq', 'U11') are no sites; closure ignores a
  minor substituent the table's labels do not name; a two-mineral paper's bond table nearest the
  coordinates table is that structure's, and a bond table's column head may carry the bonds' dash
  ('Pb1–': the sartorite homologues' tables, unread before).
- **Cells and densities.** 'a 5.600(2) ˚A, b 7.450(3) ˚A' (the ångström as a ring accent), 'a …, b …, and
  c … Å', the unit after each axis, α and γ beside β; a printed volume that lost its last digit in the
  text layer (off by exactly ten); a monoclinic cell read without its β takes it back from V·sin β
  among the βs the text prints; two integer axes are a cell picked out of prose unless the volume
  follows; the cell the .cif's axes vouch for ranks first in a multi-mineral paper; a density off by a
  factor is the Z — another Z that reproduces it to 1.5 % stands, said (D_calc +19 on the corpus).
- **Composition.** 'REEΣ1.99' is the group's count and folds the table's lanthanides; an 'N' row that
  is the number of analyses is not nitrogen; a formula may begin with integer-count elements
  ('Th2F6.7(OH)1.3·3H2O' had lost its Th); a side-by-side analysis table keeps its first block.
- **The mineral's name.** A new-mineral title names it whatever the suffix ('A New Mineral
  Ferrisanidine'), taken when Mindat knows the name or it is an -ite.

### Fixed
- **A full corpus run took 11 minutes on one worker**: `bv_check.Structure.neighbours` scanned a box of
  125 lattice translations for every atom pair (185 million distances on a 700-atom sulfosalt cell).
  An exact per-axis prune (|Δx + i| · perpendicular width ≤ cutoff) leaves ~8; 345 s → 7 s, byte-identical
  on all 224 corpus .cif files. Two papers crashed the analysis-table reader on a constituent row with
  no number. The corpus tool pairs a two-mineral paper's .cif deterministically (the first entry's).

### Also since 0.6.0 (gauntlet it19–26, 2026-09-09 night)

### Fixed
- **The paper readers' cell list had exploded** (a 0.6.0 regression, from the Part 2 rule that reads a
  powder table's 'Unit-cell parameters' row): the row finder matched the prose 'Unit-cell parameters
  refined from the powder data …' and then read every `h k l` triple of the table below it as a cell —
  188 cells on one paper — so the coordinates builder's budget never reached the true cell and 17 of
  the gauntlet's verified structures fell to `unverified`. The finder now takes a table ROW only (the
  label heads the line, decimals in the lengths), and a cell of three integers is never a cell.
- **A sideways table under a figure was read as upright**: the word list numbers text blocks only, the
  layout numbers every block, so below an image every word took another line's direction
  (`_line_dirs`; naalasite's rotated coordinates table, now read).
- **Two-column prose ending in an element symbol** ('Attempts to analyse N (NH4)2O* 7.03 …') became the
  row's constituent; the constituent beside the numbers is the row's.
- **The apfu block below a Total** ('SO4 3.808', 'UO2 8.192', 'H2O 26.0' under sejkoraite's Total) was
  read as three more wt% rows (a 141 % table): once a row below the Total can only be apfu, every row
  after it is.
- **A row with a value in the Normalised column alone** (relianceite's structural C2O3 and H2O) was given
  that value as its mean.
- **A DOI in the page's running foot** ('mgm.2021.99') was read as the stated compatibility index; the
  Σ of a group whose parts include oxygen ('(O1.09F0.92)Σ2.01') was taken for a multiplier (F doubled);
  a footnote letter after a welded qualifier ('H2Ocalcb') hid a constituent.

### Changed — the bond-valence table's conventions (gauntlet it24)
- **The grid reader**: a column takes the header word nearest to it, a site label winning only within
  8 pt ('donated' 4 pt off no longer loses to 'S2' 27 pt off); a column of negative values is the
  hydrogen-bond donor column whatever stands over it, and the checker knows 'donated'/'accepted'
  headers; a bare line of values between two rows belongs to the row ABOVE unless the label below comes
  with no values of its own (a rotated table), decided line by line; anion rows under a symmetry code
  ('O1iii', "O1'") or a coordination number ('[3]O5') are the base anion's row; a grid whose cells carry
  esds is a displacement table, not valences; a header grid its own Σ shows to be short of columns
  yields to the caption route's fuller grid on the same page (strict superset of labels only — the
  finder order stands, and the caption route is not otherwise consulted).
- **The bond reader** accepts a symmetry code on the anion of a welded bond ('Z–O8′' — the tourmaline's
  Z sum was two thirds of the paper's for want of it).
- **Per-cation conventions, noted and not counted**: a cation column that another of the tool's sets
  reproduces, or that sits ≤ 0.08 vu off in one direction over two cells or more, or ≤ 0.08 vu either
  way over three or more (a different R0 AND b), follows a parameter set of its own (S6+ from Brese &
  O'Keeffe under a Gagné & Hawthorne table; Pb2+, Ce3+, Sb3+ from sets the tool does not have); a
  contact of ≤ 0.05 vu the paper lists beyond the tool's cutoff, or that the tool has and the paper
  omits, is a cutoff, not a difference; a split site's sum may be one species' share of it (the K part of
  a K/H2O site); the structure builder writes a mixed-valence element (Fe2+ AND Fe3+ in the formula) bare,
  so the per-site valence fit the .cif path already had applies to the paper's own structure too; a
  site half occupied or less is not compared in a BVS column either; a partly occupied site's column may
  be printed unweighted when the structure is the paper's own bond table; the ammonium N column is
  skipped like H; a table of fewer than four cells with a difference is a doubt, not a finding; the set
  the paper cites is judged by the same excuse as the winner. A 'Bond | valence' header of two words
  places its column under the pair; a digit-suffixed header label ('U1') maps onto a bond table's bare
  site ('U'); a column whose printed Σ is under half the computed sum is a site the paper weighted by an
  occupancy the table does not print (not compared); a header line holding a distance with its esd is a
  bond-table line, never a grid header; a paper citing several parameter sources, one per cation, has
  cited no one set (bv.params `unverified`, said so). Measured on the gauntlet subset — see
  `review_out/gauntlet_log.md` (it24–26).

### Added
- **Import triage** button in the GUI's top bar (beside Export) — the browser's own file chooser; the
  same merge as `pxrd gui <folder> --import-triage <report>`, which was not discoverable. `/api/triage/import`
  takes the upload (`report`) as well as a `{path}` for scripts.
- **Gladstone–Dale from the paper's own columns**: a table's Normalised / Ideal / Theor. / Calculated
  column is offered as a K_C set of its own (`_column_sets`; the header read over the table's own
  x-span, `head_span`, so the other page column's prose cannot hide a header line); a paper that prints
  no density is checked on the density its anchored cell, Z and formula give (`cell_consistency`
  `D_formula`; bimbowrieite); a paper that COMPUTED its n from the compatibility relation is checked
  against an index of zero (`gd_statement` `derived_n`; wortupaite).
- **Constituents the paper says it calculated** ('C2O3, H2O and (NH4)2O were calculated based upon the
  structure determination') leave the composition comparison as calculated by the authors, whatever the
  Mean column holds for them (thebaite-(NH4): a false red retired).
- **A bond-valence table's cells on a site under half occupied** are not compared (noted): how a paper
  weights a 17 %-Na split site is its own choice; the same rule already kept such sites out of the
  structure builder's index.
- **Three more shapes of bond-valence table found**: a BVS column whose rows begin with the other page
  column's prose ('… ther- A(1) ½ 0 0 0.0176(7) 1.150' — the site token nearest the header's label
  column is the row's; a 'Table 4' inside that prose no longer ends the table; a row's continuation
  lines, a second mineral's coordinates under the same site, are neither rows nor misses); valences
  printed beside the distances with the multiplicity between ('Ca–F 2.3029(4) ×2 0.58', and seven
  values over five pairs is a table); and rare-earth group site labels ('REE1', 'Ln2') in the
  coordinates reader. A multi-value cell may hold each distance's own ×n total ('0.50 0.38' for two
  ×2 bonds). A BVS column found with the paper's own site labels but no structure to check it against
  is `nooracle` with the reason, never a silent `none`. The coordinates builder's inferred elements
  (M(1) → the formula's dominant cation) travel with the structure (`st.inferred`) and stay out of the
  sums comparison, as the bond-distance structure's always did — badalovite's M sites carry Fe3+ from
  a site-population table the reader does not have.

## [0.6.0] — 2026-09-09

### Added
- **The gauntlet.** The paper readers driven through 18 measure → fix → re-measure iterations on the
  103 corpus papers that print an EPMA table, a bond-valence table, coordinates, a compatibility index
  and optics. Verified on them: EPMA 84 → 91 %, compatibility 43 → 83 %, n 45 → 84 %, coordinates
  25 → 86 %, bond-valence table 40 → 52 %; recall by seeded faults unchanged. New reader rows
  `bv.table`, `coords`, `gd`; `pxrd paper --check --why`; the reader-independent metric
  (`tools/paper_features.py`, the harness's GAUNTLET section); log and per-iteration patches under
  `review_out/gauntlet_*`.
- **The paper's own bond distances verify its coordinates** (`paper_structure.bond_hits`); a structure so
  verified checks the bond-valence table at flag grade — a deviation from the note-grade rule, listed.
- **All 230 space groups** (702 keys) in `data/symops.json.gz`, harvested from spglib at build time.
- **Bond valence without a .cif** from the distances a paper prints; the table found by its caption; the
  printed layouts; a parameter set must be refuted, not merely beaten; the water a structure can account
  for (issue #10); the Gladstone–Dale constants of Mandarino's Table 7.
- **`pxrd gui <folder> --import-triage <report>`** reads another reviewer's exported triage report back
  in: verdict and note on each finding, decisions on findings no longer raised kept as an entry note,
  local verdicts never overwritten. The GUI has an **Import triage** button for it (beside Export;
  the browser's own file chooser, so nothing to type) — the flag alone was not discoverable.

### Changed — from ICDD's own review of Part 2
- Bragg-Brentano never implies Peak (the processing decides; a Peak on a diffractometer entry is a
  note). Intensity Type is Integrated | Peak; Visual is an Intensity Instrument. A paper that says its
  pattern was measured has a measured pattern. The CIF Z check reconciles on cell contents. A cell value
  written as the .cif writes it is not a sig-figs slip. A table's "Unit-cell parameters" row is a cell.
  A Levinson suffix typed without parentheses is flagged.

### Fixed
- Text-layer classes: Symbol-font Greek arriving as Latin, `¼` for `=`, overbars as control codes,
  sideways tables, coordinates past 1, footnote marks and site names on labels, split and mixed sites.
- Composition: the release valve fires when nothing deviates; a bigger wt% error is caught as often as a
  small one; an anion charge read as a subscript; fourteen papers raised instead of being read.
- GUI: an unreadable .pdf no longer spins the background pass.

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
