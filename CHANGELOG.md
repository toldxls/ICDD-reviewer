# Changelog

Notable changes to the PXRD review tool. The format loosely follows
[Keep a Changelog](https://keepachangelog.com/); the version is the `pxrd-review`
package version in `pyproject.toml`.

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

## [0.2.9] — 2026-07-13

### Fixed — '? look' on the docx pane landed on the wrong cell
Reported by an ICDD reviewer: most flags navigated to the `MoKa` cell in the Radiation row
whatever they were about, and the cell/esd findings didn't navigate at all. Three separate
causes, all fixed:
- **Instrument fields are not row headers.** `Spacing Instr. :` is cell 4 of a row whose FIRST
  cell is `Camera Diameter =`, so matching on the row header could never find it and fell back
  to the only instrument row that did match — `Radiation =`. Hence "everything lands on MoKa".
  The docx renderer now tags each anchor's target cell (`data-anchor`) by **label cell → next
  cell**, the same way the annotator finds the cell it highlights, so the two always agree.
- **The CELL / per-parameter / RADIATION findings are synthesised in the UI** and are not in the
  findings list the server sends, so looking them up by key returned nothing and their anchors
  were lost — `? look` had nothing to aim at (e.g. Amurselite's esd/value flag on *b*). Their
  anchors are now recorded when the rows are built.
- **The CELL summary's anchor carried the verdict, not a column** (`cell:match`), which resolves
  to no axis; it now lands on the Author's Cell row.

### Fixed — Intensity Type findings pointed at the wrong field
An Intensity Type flag used the generic `instr` anchor, so the tool **highlighted the Spacing
Instr. cell** and `? look` sent the reviewer to the Radiation row. It now anchors on
`intensity_type`, and both the highlight and `? look` land on the Intensity Type value.

### Docs
- INSTALL.md step 2 points at the **Releases page**
  (<https://github.com/toldxls/ICDD-reviewer/releases>) — the newest build is marked `Latest`,
  so it is the fewest clicks to the current version. The one-line `pip install` from the repo
  and the source-folder route are kept as alternatives.

## [0.2.8] — 2026-07-13

### Docs — INSTALL.md rewritten against how reviewers actually install it
Checked against the "Visual Instructions for PXRD_REVIEW_TOOL" walkthrough ICDD wrote for
themselves. It worked, but it diverged from our instructions at almost every step — so the
instructions were the problem, not the reviewers:
- They installed from a **source folder with `pip install -e .`**; INSTALL.md documented only
  the wheel bundle. Both paths are now written out.
- They ran **`python -m pxrd_review.gui.review_gui "<folder>"`**, not `pxrd gui` — the `pxrd`
  command isn't on PATH for every Windows Python. The long form is now given for every command,
  with a troubleshooting row for `'pxrd' is not recognized`.
- **`python3` does not exist on Windows.** The README's commands are all `python3 -m …`, which
  simply fails there. Called out in both files.
- They installed Python from the Microsoft Store's **Python Install Manager** (answer **Y** to
  the PATH prompts); we only documented python.org. Both are now covered.
- Their Mindat workaround was *"GET the .json files I can email them to you … put them in
  `.cache`"*, and their note on setting the key was an open TODO. **Both are obsolete as of
  0.2.7**: the snapshot ships inside the package, so no key and no hand-copied JSON is needed.
  INSTALL.md now says this at the top.
- Clarified that **`Rerun entry/all` writes the docx** while **`Export triage` writes a text
  report** — their walkthrough treated the two as one step.
- The bundle's checksum file is `SHA256SUMS.txt`, as the docs have always said.

### Changed — reference title case (check 26)
- **A formal place name now keeps all of its words.** The rule previously let the paper decide
  every word, which lowercased the head-noun of a name the paper happens to write lowercase
  elsewhere: `Elba Island` → `Elba island`, `Ingul Gold Placer` → `Ingul gold placer`. The
  papers disagree with each other on this, so it is the one thing the paper does *not* decide.
  A capitalized word directly adjacent to a paper-attested name is now part of that name, on
  **either** side — `New Mexico`, `La Sal`, `Vanadium Queen` before it; `Elba Island`,
  `Tolbachik Volcano`, `Quadeville Rose Quartz Quarry` after it.
- **`mine` remains the exception** (*the Burro mine*, *the Redmond mine*), per the reviewer.
- **A species inside a name is kept** (`Rose Quartz Quarry`) while a species with an ordinary
  neighbour still lowercases (`isotypic with jamesite`, `the dongchuanite group`) — adjacency
  to an attested name is the discriminator.
- **An unattested word is left alone but does not anchor a name.** Letting it anchor turned
  `a New Layered …` back into the Title Case the check exists to remove.
- Fire rate drops 6 % → 5 % (21 of 466): the titles that stopped firing are ones whose place
  names were already correct — i.e. they were false positives under the old rule. Still 0 titles
  with altered letters.

## [0.2.7] — 2026-07-13

### Added
- **'? look' now works on the docx pane.** It answered "what does the paper say?" and did
  nothing for the transcription; it now follows whichever pane is open and lands on the exact
  cell the finding is about (scrolls to it, outlines it, flashes once). Findings carry an
  anchor (`reference`, `cell:a`, `instr`, …), and the rendered docx table now carries
  `tr[data-h]` / `td[data-c]`, so the anchor resolves to a row and column; anything without a
  usable anchor falls back to searching the cells for the finding's own evidence terms. With
  no `.pdf` paired, the docx is where '? look' goes.
- **A Mindat snapshot ships inside the wheel** (`pxrd_review/data/*.json.gz`, ~385 KB gzipped).
  Without an API key the group / chemistry / cell cross-checks previously found nothing at all —
  which reads exactly like a clean batch — so the tool now works fully offline out of the box.
  A key only buys fresher data. The cache banner says `[bundled with this release]` when the
  seed is doing the work. Maintainer step before a release:
  `python3 -m pxrd_review.mindat --refresh --bundle`, then commit `pxrd_review/data/`.
  Also adds `python3 -m pxrd_review.mindat --status`.

## [0.2.6] — 2026-07-13

### Added — reference title case (check 26)
- **New check: the Primary Reference title should be sentence case, not the machine Title
  Case the entry arrives in** (`a New Mineral From the Burro Mine`; the title-caser even
  wrecks acronyms, `USA` → `Usa`). Requested by an ICDD reviewer. The direction was mined,
  not assumed: of 165 reviewer-corrected reference cells in the corpus, 53 were case-only
  title fixes and **all 53 went Title Case → sentence case, none the other way**.
- **The paper decides what is a name.** A word the article writes lowercase mid-sentence
  (`volcano`, `deposit`) is an ordinary word; one it capitalizes (`Tolbachik`) is a name;
  one it writes in caps (`USA`) is an acronym to restore. Wholly upper-case lines are
  discarded as evidence — running heads, and the *Canadian Journal of Mineralogy and
  Petrology* sets titles in caps/small-caps. `mine` is preferred lowercase regardless.
- **Never re-cases chemistry** (`Pb2(Fe3+6Zn)O2(PO4)4(OH)8`), an element-prefixed compound
  (`Al-bearing`), a Levinson suffix (`-(Ce)`, never `-(ce)`), a Roman numeral (`IV.`), or a
  site variable (the `A` in `analogs (A = K, Rb, Cs)` is not the article). A capitalized word
  the paper gives no evidence for is left alone rather than lowercased on a guess.
- Comment-only, like every other check: the corrected title is **suggested** in the comment
  and the Reference cell is highlighted. The tool never rewrites the cell.
- Validated across the corpus: fires on 6 % of entries (26 of 466 with a reference), 94 %
  recall against the reviewer's own known corrections, and **0 titles with altered letters**.

## [0.2.5] — 2026-07-13

Full code review ahead of the repository going public. Nothing here changes what the
checks *mean*; the fixes are data-safety, one XSS, and false positives that were being
written into reviewers' docx.

### Fixed — data safety
- **`--out` pointed at the source folder no longer deletes source `.docx` files.** The
  output names are derived from the source name, so an `--out` resolving to the source
  folder made the stale-twin bookkeeping treat a SOURCE docx as a previous run's output
  and `os.remove()` it. It is now refused outright (`--inplace` remains the deliberate
  way to edit originals).
- **Every docx write is atomic** (temp + `os.replace`). `doc.save()` streams a zip; a
  crash or full disk part-way through truncated the target — which under `--inplace`, or
  when refreshing onto a hand-edited output, is the reviewer's only copy.
- **Single-writer lock per output folder.** Clicking "Rerun all" in the GUI while a
  terminal run was going interleaved writes to the same docx and could corrupt it
  silently. A second run now stops with a message. Locks left by a crashed run are
  reclaimed automatically.
- **`--id` matches the entry id exactly.** Substring matching meant `--id I10126` also
  selected (and rewrote the output of) a 6-digit `I101261…`.

### Fixed — security (GUI)
- **XSS via the paper.** `esc()` was `String(s)` — a no-op that only looked like an HTML
  escape — and the matched-cell snippet (raw `get_text()` from the `.pdf`) went into
  `innerHTML`. A crafted paper could run script in the localhost origin and drive the
  local `/api/*` endpoints. `esc()` now escapes; text-node sites use `str()` instead, so
  nothing double-escapes.
- State-changing requests carrying **neither `Origin` nor `Referer`** are now refused.
- `MINDAT_INSECURE=1` warns that it exposes the API key (it disables TLS verification
  while still sending the `Authorization` header).

### Fixed — false positives (were being written into the docx)
- **Blank Crystal System no longer flags.** The guard was `cs not in 'amothrc'` on a
  possibly-empty string — and `''` is a substring of every string — so a blank field
  sailed through and wrote a bogus *"Crystal System () disagrees with…"* comment.
- **"Triclinic" and "Trigonal" are no longer read as *tetragonal*.** The classifier took
  the first letter, and all three start with `t`. Triclinic entries had `a=b` and
  `α=β=γ=90` imposed on them, producing a storm of false symmetry flags. Crystal systems
  are now matched as whole words (ICDD's "Anorthic" *and* the IUCr words), and an
  unrecognised word abstains.
- **`D8` / `SMART` instrument patterns** required only a bare token — but `d8` is the
  electron configuration and `smart` is an English word. They now need the maker's name
  or a real model qualifier.
- **Near-cubic rhombohedral cells** (α=β=γ≈90°) are no longer forced into the hexagonal
  setting and told their γ must be 120.
- **Anode detection** is token-anchored: `CoKα (Fe filter)` read as an *iron* anode (the
  filter metal), and "Copper" matched `co`. A string naming two metals now resolves to
  the one carrying the K-line label, or abstains.
- **Correctly-rounded values** no longer report as value mismatches: comparison at the
  common precision now rounds half-UP on the decimal value, not half-even on a binary
  float (pdf `2.675` vs docx `2.68`).

### Fixed — robustness
- **One unreadable file no longer aborts the batch.** A `.docx` that is really an HTML
  error page, a docx with no `word/document.xml`, or a truncated `.pdf` killed the run
  and left every later entry unchecked. Such entries are now skipped and counted.
- **python-docx pinned to `>=1.2`** — `add_comment()` does not exist before 1.2.0. With
  1.1.x installed, every flagged entry raised `AttributeError`, was swallowed per-entry,
  and the run "succeeded" having written **no findings at all**.
- Mindat: HTTP **429 now backs off and retries** (honouring `Retry-After`) instead of
  failing the refresh; truncated-JSON / dropped-connection reads retry instead of
  escaping as a traceback; pagination is capped so a repeating `next` link can't spin
  forever.
- A missing **PyMuPDF** now says so, once, instead of failing every entry with an opaque
  error.
- The sweep snapshot is written atomically, and an unreadable existing snapshot now says
  the drift comparison was dropped instead of silently restarting the baseline.
- Console output is forced to UTF-8 on Windows, so a direct `python -m pxrd_review.…`
  run no longer dies with `UnicodeEncodeError` on `λ`/`α`/`Å` when redirected.
- `pxrd review I003448` (a bare entry id) now works for `review`/`lambda`/`candidates`,
  which take `--id` — the launcher advertised the shorthand but only `extras` accepted it.

### Docs
- README: the GUI runs on **port 8000**, not 5000; the regression command needed its
  fixtures argument; install step 4 pointed public readers at a private ICDD batch;
  `--refresh` rebuilds both caches (`--refresh-struct` is just an alias); dropped a
  reference to a LaunchAgent that is not in the repo.
- NOTICE now names the two files that actually import PyMuPDF (the AGPL-isolation claim
  pointed at paths that no longer exist).
- INSTALL uses a `<version>` placeholder instead of a wheel filename two releases stale.

## [0.2.4] — 2026-07-12

Follow-up to the Windows-compatibility pass, from the first Windows reviewer's
feedback.

### Fixed — GUI
- **The "open ↗" button now opens whichever file the middle pane is showing** —
  it always opened the entry docx in Word, so on the `.pdf` view clicking it
  (expecting the paper) surfaced the docx instead. It now opens the `.pdf` in the
  default PDF viewer on the `.pdf` view and the docx in Word on the `docx` view;
  the tooltip tracks the toggle. The route (`/api/open/<key>`) grew a
  `?kind=pdf|docx` selector (default `docx`, so nothing else changes) and still
  opens only a file the GUI has indexed. Not noticed on macOS, where the inline
  PDF render made the button unnecessary.

## [0.2.3] — 2026-07-10

Windows-compatibility pass ahead of the first Windows user (ICDD reviewer). A
static sweep of the codebase found two blockers, fixed below; the rest checked
out clean (spawn-safe PDF workers, explicit UTF-8 on all text file IO,
`os.startfile`/PowerShell branches for the native integrations, colon-free
backup timestamps, per-entry containment of Word file locks).

### Fixed — Windows
- **`pxrd` mangled folder paths containing spaces** — Windows `exec*` spawns a
  child while joining argv *without quoting*, so `pxrd gui "C:\…\ICDD entries"`
  arrived split in two (and the prompt returned while the child still printed).
  The launcher now uses `subprocess.run` on Windows (correct quoting, waits,
  propagates the exit code, Ctrl-C → 130); POSIX keeps the true exec.
- **Every GUI rerun failed on Windows** — a piped child interpreter encodes
  stdout as cp1252, and the first `λ`/`α`/`→` the checks print raised
  `UnicodeEncodeError`. The rerun env now sets `PYTHONUTF8=1` and the GUI
  decodes with `encoding='utf-8', errors='replace'` (no child output can crash
  either side); `pxrd` also sets `PYTHONUTF8=1` on Windows so redirected
  console output (`pxrd review > log.txt`) is safe too.

## [0.2.2] — 2026-07-10

Full-codebase review (five parallel reviewers + adversarial verification): 1
critical, 10 major, ~24 minor defects found and fixed. Regression 230/230 (25 new
cases); validated by an analyze()-level A/B diff over the full corpus (1612 docx —
fixtures + all training/ICDD trees): 39 entries changed, every change an intended
fix (31 false `calculated` flags removed, 2 scanned .pdfs now report `notext`
instead of a false anode flag, 1 entry's cell match improved), zero new findings.

### Fixed — data loss / reviewer-work safety
- **Formatting-only manual edits survive reruns** — `output_hand_edited` now does a
  formatting-level compare (highlight/bold/italic/…, via a stripped temp copy), so a
  reviewer highlight with no text change is refreshed-in-place with a backup instead
  of silently rebuilt from source; a corrupt output reads as hand-edited (preserved),
  and a stale twin is never deleted on formatting evidence alone.
- **Backup failures abort, loudly** — when `.edit_backup/` can't be written, the
  entry is left untouched with a `!!` warning instead of proceeding after a false
  "your edits were saved" message.
- **Filtered runs keep batch logs** — `--id`/`--limit` no longer rewrite
  `annotation_log.txt` scoped to the subset or delete `mindat_discrepancies.txt`.
- **Triage can't land on the wrong entry/finding** — content-stable finding keys
  (`f:<hash>`, was positional `f0/f1…` that drifted when the list changed) shared by
  the GUI and `--triage`, with unambiguous-only migration of old keys; the GUI's
  `openEntry` is race-guarded (a failed/out-of-order load can no longer save entry
  A's triage under entry B's key); `triage.json` writes are atomic (tmp+rename) with
  corrupt-file quarantine; rerun endpoints are mutually excluded (409) so two
  `annotate_review` subprocesses can't interleave writes to the same docx.
- **Mindat caches are crash-safe** — atomic writes, unreadable caches self-heal via
  re-fetch instead of crashing every run, and `refresh()` refuses to overwrite a
  populated cache with a drastically smaller pull.

### Fixed — false positives / missed catches (checks)
- **check4 (calculated) is species-scoped** — another species' "could not be
  collected / was calculated" sentences no longer flag a measured entry (removed 31
  corpus false flags, e.g. the camanchacaite-paper quintet, grguricite, dienerite).
- **Scanned .pdf (no text layer) → `notext`** — reported as "no extractable text"
  instead of a written "docx anode NOT found in .pdf" false flag.
- **Cell parsing hardening** — vertical-table label rows cluster per table block and
  the inline grab window truncates at a second `a =` (no more chimeric candidates
  mixing two species' axes — also upgraded one real match, I002381); EPMA rows
  (`Point Ca 3.45 …`) no longer mint phantom cells; esd rejoin can't fuse a
  footnote `(3)` across a newline but still recovers a line-wrapped esd with a unit;
  a docx angle mistyped 90↔120 is now compared instead of skipped; `best_match`
  never zips unequal axis lists; a merged/short Author's-Cell row pads instead of
  crashing the batch; `.PDF` (uppercase) articles pair.
- **λ capture** — nm-quoted wavelengths convert to Å; nearby cell parameters and
  out-of-band numbers are never read as λ.
- **check8/check10/check18 misfires** — esd suggestions can't match inside a longer
  number (112.219(5) vs c=12.219); a prose dash after "biaxial" is not an optic
  sign; a flattened charge digit (Ce3+) is not a REE coefficient (no more wrong
  Levinson rename suggestions).
- **candidate_groups** — axis ratios compare sorted lengths (a setting-swapped cell
  is "similar", not a phantom super-cell); volumes carry the angle term (γ=0
  uniaxial reads as 90°), fixing inverted cation-size verdicts.
- **Accept override works on refresh** — triage `disagree` now clears a previously
  stamped 'x'; repeated `--inplace` runs strip the tool's own annotations first
  instead of duplicating every comment.

### Added — distribution (first packaged release)
- **INSTALL.md** — step-by-step install & upgrade instructions for ICDD reviewers
  (Windows-first): Option A = wheel from the GitHub Releases page, Option B =
  `pip install --upgrade git+…` straight from the private repo; README links to it.
- **`pxrd --version`** (also `-V` / `version`) prints the installed version;
  `pxrd_review.__version__` synced with `pyproject.toml` (was stuck at 0.1.0).
- **Wheel installs keep state out of site-packages** — `paths.py` now detects a
  checkout by marker (`pyproject.toml`) instead of writability, so a pip-installed
  copy puts `.mindat_key`/`.cache/` in `~/.pxrd_review` even on per-user Pythons
  whose site-packages is writable (state there would vanish on reinstall). Dev
  checkouts keep their repo-root state, unchanged.

### Changed — GUI
- **Folder control is discoverable** — the top-bar path is now a bordered chip
  (📁 icon + current folder + an explicit "Change…" button) instead of muted text
  you had to know to click; the picker panel drops down under the chip (was
  anchored to the far right of the window).

### Fixed — trustworthy gates & tooling
- **Regression suite can't vacuously pass** — a missing fixture docx is a loud FAIL
  (was: every negative assertion silently passed); errored checks file under their
  real code and a corpus-wide case asserts none exist; fixture discovery is
  recursive and skips `review_out/`.
- **sweep** — digit-bearing codes aggregate in the fire table; an explicit
  `--baseline` that can't be read exits with an error instead of silently reporting
  "no previous snapshot".
- **CLI** — `pxrd extras I003448` passes the id through instead of remembering it as
  a folder; a stray docx in the cwd can't hijack folder resolution; `pxrd check`
  honors `$PXRD_REGRESSION_DIR`.
- **GUI robustness** — triage export survives a corrupt entry (per-entry error line,
  atomic write, visible JS failure status); the analysis-cache fingerprint includes
  mindat.py + both Mindat caches (a cache refresh invalidates stale panes); label-only
  records are no longer created on render (no `[?]` noise in `triage_report.txt`);
  wedged PDF-worker processes are hard-killed and failed page images retry once;
  stale async PDF-pane continuations are generation-guarded.

## [0.2.1] — 2026-07-08

Fixes from a full-day code review of the 0.2.0 work (10 confirmed defects + 5
cleanups). Regression 204/204; triage-merge behavior covered by new sanity checks.

### Added
- **Entry-list sort options** — a dropdown beside the filter box orders the list by
  ICDD id (↑/↓), mineral name (A→Z / Z→A), most fixes first, or cleanest first.
  Applies within every view (Fixes/Attention/Clean/All); the ‹ › prev/next entry
  navigation follows the displayed order.

### Fixed
- **Triage can no longer be silently lost or corrupted** — a duplicate `flushTriage`
  declaration shadowed the keepalive flush (a confirm/dismiss inside the 350 ms
  debounce was dropped on tab close); the self-heal merge now recognises lowercase
  entry ids via the shared `ID_RE` (they previously pooled together and cross-merged
  verdicts between unrelated entries) and carries **every** saved field (entry notes,
  per-finding labels, timestamps) instead of stripping them.
- **Folder switch is race-free** — `/api/folder` rebuilds the index under the state
  lock, so an in-flight analysis can neither crash an entry request nor write a stale
  foreign row into the new folder's `gui_cache.json`.
- **Server lifecycle** — auto-exit grace default is now 90 s (Chrome throttles a
  backgrounded tab's heartbeat to once per minute, so closing one tab could kill the
  server under another still-open tab), and the watchdog never exits while a request
  (e.g. a long rerun) is still being served.
- **Dashboard rows that go stale later re-analyze** — editing a docx in Word (or
  touching a paired source) no longer leaves the row on "analyzing…" forever.
- **Folder picker** — the native macOS dialog now opens frontmost **with keyboard
  focus** and starts in the current entries folder. Going up is ⌘↑ (the prompt
  carries the hint), ⌘⇧G to type a path, or the sidebar — those keys used to land
  in the browser because the dialog opened unfocused, leaving mouse-only
  drill-down. The in-app browser starts from the real path (not the decorated
  tooltip text, which had opened one level up); the path box gets its own
  full-width row in a wider panel;
  the ancestor `.pdf`-pool probe is bounded (no more minutes-long disk walk when no
  papers exist nearby); a failed docx render is no longer cached for the session.
- **Output-folder guards** — `annotate_review` and `sweep` refuse to run on a
  `review_out` / `.edit_backup` root (discover() can index one since 0.2.0 for the
  GUI's resume feature; annotating one would double-comment the outputs).

### Changed
- **discover() tiebreak counts only human marks** — the tool's own comments no
  longer count as review activity, and on a tie the clean `(Name).docx` beats an
  `_edited` name. A stray copy of a tool output can no longer outrank the true
  source; reviewer copies whose only content is tool comments now resolve to the
  clean copy (Part1: 3 of 37 entries — checks are unaffected, comments never
  change field cells).

## [0.2.0] — 2026-07-08

Review-mode GUI overhaul: inspect the tool's findings **and** reviewers' edits side
by side, and re-point the tool without restarting. GUI-only unless noted — the check
engine and the regression suite are unchanged (204/204 passing).

### Added
- **In-app docx view** — a `.pdf | docx` toggle in the middle pane renders the entry
  transcription in the browser with tracked changes inline (insertions underlined,
  deletions struck through) and comments as chips. An **open ↗** button opens the
  actual docx in Word when you want the full document.
- **Per-author colouring + legend** — each reviewer's marks get a distinct colour
  (the tool itself is muted grey); a colour legend pins to the top of the docx view.
  The legend entries are **toggle buttons** — click an author to show/hide their
  marks. Click a comment to **pin its full text** (no more hover-only tooltip).
- **Reviewer-edit surfacing** — the reviewer's own tracked changes / comments are
  read from the entry docx (or its `review_out` copy) and listed, **filterable by
  author** — so you can review a folder of one reviewer's copies.
- **Auto `.pdf` source pool** — pointing at a folder that holds only docx now
  auto-finds the papers / `.cif` / `.dft` from the nearest ancestor that has them, so
  the evidence panes still populate. `--pdf-root` overrides the auto-detected pool.
- **Dashboard "Log" button** — opens the tool's change log
  (`review_out/annotation_log.txt`) inline in a new browser tab; falls back to the
  other `review_out` logs when present (whitelisted filenames only).
- **In-app folder picker** — click the folder path in the header to re-point the tool
  at a different entries folder **without restarting**: choose with the native
  **Finder** dialog (macOS; zenity on Linux), browse in-app, or type/paste a path.
  Each folder shows a live `docx / .pdf` content hint.

### Fixed
- **discover() picks the reviewed copy** — when a folder holds both a clean
  `(Name).docx` and a reviewer's `(Name)_edited.docx`, the most-reviewed copy now
  wins. Previously the clean copy did, so the GUI/sweep opened the un-edited one.
- **"Hide author" keeps deletions readable** — hiding an author in the docx view now
  keeps a deletion's original text (un-struck) rather than removing it, which had read
  as though the deletion were accepted.
- **PDF parsing moved off the Flask threads** — `analyze()`'s PDF text read now runs
  in the MuPDF worker subprocess, so a live folder switch can no longer segfault the
  server (MuPDF / `fitz` is not thread-safe). The docx renderer is also guarded so a
  pathological file returns empty instead of a 500.

### Security
- The docx renderer HTML-escapes every document-derived string; the new log / docx /
  folder endpoints serve only whitelisted or already-indexed files — no arbitrary
  path or directory traversal.
