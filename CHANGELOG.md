# Changelog

Notable changes to the PXRD review tool. The format loosely follows
[Keep a Changelog](https://keepachangelog.com/); the version is the `pxrd-review`
package version in `pyproject.toml`.

## [0.2.2] — 2026-07-09

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
