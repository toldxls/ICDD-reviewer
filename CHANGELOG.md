# Changelog

Notable changes to the PXRD review tool. The format loosely follows
[Keep a Changelog](https://keepachangelog.com/); the version is the `pxrd-review`
package version in `pyproject.toml`.

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
