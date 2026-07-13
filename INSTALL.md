# Installing & running the PXRD review tool

Step-by-step for ICDD reviewers, written for **Windows** (macOS/Linux notes at the end).
No programming needed — you type a few commands into the black Command Prompt window.

**You do NOT need a Mindat API key.** A Mindat snapshot ships inside the tool, so the
classification / chemistry / cell cross-checks work as soon as it is installed. (Older
instructions told you to ask for `mindat_ima.json` / `mindat_struct.json` and copy them into a
`.cache` folder by hand — **that is no longer necessary**; skip it.)

---

## 1. Install Python (once)

Either of these works. **Whichever you use, Python must be added to your PATH** — that is the
step people miss, and nothing works without it.

**Option A — Python Install Manager (Microsoft Store).** Get it from
<https://apps.microsoft.com/detail/9nq7512cxl7t>, run it, and when it asks
**"Allow longer names"**, **"Configure directory / add PATHs"** and **"Add Python runtime"**,
answer **Y** and press Enter each time.

**Option B — python.org.** Download the latest Python 3 from
<https://www.python.org/downloads/>, run the installer, and on the very first screen
**tick "Add python.exe to PATH"**.

**Check it worked.** Open a **new** Command Prompt (Start menu → type `cmd`) and run:
```
python --version
pip --version
```
Both should print a version. If you get `'python' is not recognized…`, PATH wasn't set — redo
the step above and open a **new** Command Prompt.

> On Windows the command is **`python`**. (`python3` is a macOS/Linux name; it usually does not
> exist on Windows.)

---

## 2. Install the tool

You will have received **either** a bundle zip **or** a source zip. Both end with the same
working `pxrd` command — use whichever you were sent.

### A — from the bundle zip (`pxrd-review-<version>-bundle.zip`)

1. **Unzip it** (right-click → *Extract All…*). Inside:

   | file | what it is |
   |---|---|
   | `pxrd_review-<version>-py3-none-any.whl` | the tool (this is what gets installed) |
   | `SHA256SUMS.txt` | the wheel's fingerprint (integrity check) |
   | `INSTALL.md` | this file |

2. **Check the download is genuine.** The message announcing the upload contains the wheel's
   SHA-256 fingerprint. In a Command Prompt type `certutil -hashfile ` (with the trailing
   space), **drag the `.whl` file** into the window, type ` SHA256`, press Enter:
   ```
   certutil -hashfile "C:\...\pxrd_review-<version>-py3-none-any.whl" SHA256
   ```
   The long hex string must match the announced one exactly. Any difference = corrupted
   download; re-download, or ask Travis.

3. **Install.** Type `pip install --upgrade ` (trailing space), drag the same `.whl` in,
   press Enter:
   ```
   pip install --upgrade "C:\...\pxrd_review-<version>-py3-none-any.whl"
   ```
   The first install needs internet (pip fetches the libraries it depends on); later upgrades
   normally don't.

### B — from a source zip / a folder called `pxrd-review-tool`

1. **Unzip it** somewhere you can find, e.g. your Desktop.
2. **Go into that folder** in the Command Prompt with `cd`, then install with `.` (a dot —
   it means "the folder I am in"):
   ```
   cd Desktop\pxrd-review-tool
   pip install -e .
   ```
   *(Tip: type `cd ` then drag the folder into the window to fill in the path.)*

To **upgrade** later, replace the folder with the new one and run `pip install -e .` again.

### Check it installed

```
pxrd --version
```
It should print e.g. `pxrd-review 0.2.8`.

**If it says `'pxrd' is not recognized`:** first close and reopen the Command Prompt. If it
still isn't found, Python's Scripts folder isn't on your PATH — you don't need to fix that,
just use the longer form everywhere below:

| short (preferred) | longer form that always works |
|---|---|
| `pxrd gui "C:\path\to\entries"` | `python -m pxrd_review.gui.review_gui "C:\path\to\entries"` |
| `pxrd review "C:\path\to\entries"` | `python -m pxrd_review.annotate_review "C:\path\to\entries"` |

---

## 3. Run it

```
pxrd gui "C:\Users\You\Desktop\2028_PART1"
```
Point it at the folder holding the entry `.docx` **and** the paper `.pdf` files. **Keep the
quotes** — paths with spaces break without them. It opens the review window in your browser.
The folder is remembered, so afterwards a bare `pxrd gui` reopens it.

Longer form if `pxrd` isn't recognized:
```
python -m pxrd_review.gui.review_gui "C:\Users\You\Desktop\2028_PART1"
```

### Using the review window

- **Left** — the entry list. Click an entry to open it.
- **Middle** — the paper (`.pdf`) or the transcription (`docx`); use the toggle to switch.
- **Right** — what the docx, the `.cif`/`.dft` and Mindat say, side by side.
- **Findings** — each one has **`? look`**, which jumps to the evidence: on the `.pdf` it
  scrolls to the passage; on the `docx` it lands on the exact cell. Then **`✓ confirm`** or
  **`✗ dismiss`**, and add a note if you want.
- **`Rerun entry ▸`** writes the corrected docx for that entry into the `review_out` subfolder,
  applying your triage. **`Rerun all ▸`** does the whole batch when you're finished.
- **`Export triage`** is separate and optional: it writes a plain-text summary of your
  decisions (`review_out\triage_report.txt`). It does **not** write the docx — the Rerun
  buttons do that.

**Your source files are never modified.** Everything the tool writes goes into a `review_out`
subfolder, as *copies* with Word comments and yellow highlights. Your own manual edits to those
copies are preserved across reruns (a timestamped backup is kept in `review_out\.edit_backup`).

---

## 4. Mindat API key — optional

**Skip this unless you want fresher Mindat data.** The tool ships with a Mindat snapshot and
works fully offline without a key; the header tells you how old that snapshot is. A key only
lets the tool refresh it automatically.

Get a key from your **mindat.org** account page, then in a Command Prompt:
```
setx MINDAT_API_KEY "YOUR_MINDAT_TOKEN"
```
Close and reopen the Command Prompt (the variable only exists in new windows). This survives
reboots and upgrades — set it once.

Check it and see what data you have:
```
python -m pxrd_review.mindat --status
```

---

## Troubleshooting

| what you see | what to do |
|---|---|
| `'python' is not recognized` | Python isn't on PATH — redo step 1, then open a **new** Command Prompt. |
| `'pxrd' is not recognized` | Reopen the Command Prompt; if it persists, use the `python -m …` long forms above. |
| `'python3' is not recognized` | On Windows the command is `python`, not `python3`. |
| The path has spaces and it fails | Put **double quotes** around the whole path. |
| A docx won't open / "locked" | Close the file in Word (and the Explorer preview pane), then rerun. |
| `mindat cache: MISSING` in the header | Reinstall — the snapshot ships inside the package. |

**Upgrades never touch your data.** The API key, the caches, your entries folders and every
`review_out\` folder (triage, edited docx) live outside the installed package and survive every
upgrade untouched.

---

## macOS / Linux differences

Same steps, but use `python3` / `pip3` in the commands, check the fingerprint with
`shasum -a 256 <file>` instead of `certutil`, and set the key with
`export MINDAT_API_KEY="…"` in `~/.zshrc` (macOS) or `~/.bashrc` (Linux) instead of `setx`.
Developers working from a git checkout should use `pip install -e .` (see README "Setup") — an
editable install keeps its `.cache/` and `.mindat_key` at the repo root.

---

## Maintainer — cutting a release

1. **Refresh the bundled Mindat snapshot** (so reviewers without a key get current data):
   ```
   python3 -m pxrd_review.mindat --refresh --bundle
   ```
   Commit `pxrd_review/data/`.
2. Bump the version in **both** `pyproject.toml` and `pxrd_review/__init__.py`; update
   `CHANGELOG.md`; run the regression suite (`pxrd check "<fixtures>"`); commit.
3. Build the wheel (one-time `pip3 install build`):
   ```
   python3 -m build --wheel
   ```
4. Build the bundle:
   ```
   cd dist
   shasum -a 256 pxrd_review-<version>-py3-none-any.whl > SHA256SUMS.txt
   cp ../INSTALL.md .
   zip pxrd-review-<version>-bundle.zip pxrd_review-<version>-py3-none-any.whl SHA256SUMS.txt INSTALL.md
   rm INSTALL.md
   ```
5. Upload the bundle zip to the shared files site, and put the wheel's SHA-256 fingerprint
   **in the announcement message itself** (the copy inside the zip can only catch corruption,
   not tampering — the message is the independent channel).
6. Optional, for the archive: attach the wheel to a GitHub release
   (`gh release create v<version> dist/*.whl --notes "…SHA-256: …"`).
