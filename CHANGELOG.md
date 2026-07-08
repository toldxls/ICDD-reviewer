# Changelog

Notable changes to the PXRD review tool. The format loosely follows
[Keep a Changelog](https://keepachangelog.com/); the version is the `pxrd-review`
package version in `pyproject.toml`.

## [0.2.1] — 2026-07-08

Fixes from a full-day code review of the 0.2.0 work (10 confirmed defects + 5
cleanups). Regression 204/204; triage-merge behavior covered by new sanity checks.

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
