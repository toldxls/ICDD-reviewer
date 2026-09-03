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

**The latest version is always on the Releases page:**

### **<https://github.com/toldxls/ICDD-reviewer/releases/latest>**

That link always resolves to the newest release. Nothing gets emailed, and there is no files
site to check. You do **not** need a GitHub account.

> ⚠️ **Never paste an install command that names a version** (`v0.2.9`, `…-0.3.0.whl`, a
> `#sha256=…`) out of an old message, an old copy of this file, or a chat history — it will
> quietly install **that old version**. Always take the command from the release page above, or
> use the version-less one-liner in **B**, which is always current.

### A — one line, nothing to download (recommended)

This always fetches the **current** version — there is nothing to download by hand, and
nothing to keep up to date:
```
pip install --upgrade "https://github.com/toldxls/ICDD-reviewer/archive/refs/heads/main.zip"
```
Run that same line again to upgrade. You do **not** need `git` installed.

> **What this does and does not check.** The download is over HTTPS, so it is encrypted and the
> server is authenticated as `github.com` — nobody on the network can alter it in transit. But
> pip does **not** verify a fingerprint here: it installs whatever the branch currently holds.
>
> To have pip *verify* the download, use the **hash-pinned line printed in the release notes**
> (every release ends with a ready-to-paste `pip install …#sha256=…` line). pip then refuses the
> install if a single byte differs. Do not copy such a line out of this file or an old message —
> it pins a specific version, and an old one will quietly install an **old tool**. Take it from
> the release you are installing:
> **<https://github.com/toldxls/ICDD-reviewer/releases/latest>**
>
> (Option **A**'s `.whl` + `certutil` gives the same assurance, checked by hand.)

### B — download the wheel from the release (if you prefer to see the file)

On the Releases page, under **Assets**, download the file ending in **`.whl`**. Then in a
Command Prompt type `pip install --upgrade ` (with the trailing space), **drag the `.whl` file**
into the window, and press Enter:
```
pip install --upgrade "C:\Users\You\Downloads\pxrd_review-<version>-py3-none-any.whl"
```
That is also how you upgrade: download the newer `.whl` and run the same command.

*Optional integrity check:* the release also lists `SHA256SUMS.txt`. To confirm the download
isn't corrupted, run `certutil -hashfile "<the .whl file>" SHA256` and compare the long hex
string with the one in that file (or in the release notes).

### C — install from the source folder

Prefer to see the files? On the Releases page (or the repository page → green **`Code`** button)
choose **Source code (zip)**, unzip it (right-click → *Extract All…*), then in a Command Prompt
go into the unzipped folder and install with `.` (a dot — it means "the folder I am in"):
```
cd Desktop\ICDD-reviewer-<version>
pip install -e .
```
*(Tip: type `cd ` then drag the folder into the window to fill in the path.)*

The first install needs internet — pip fetches the libraries the tool depends on.

### Upgrading

Two ways, both fine:

- In a Command Prompt: **`pxrd update`**. It looks at GitHub, says whether there is a newer
  version, and installs it (a second window runs pip; close it when it says *Done*). When nothing
  is newer it installs nothing. `pxrd update --check` only looks.
- Or run install line **A** again — it always fetches the current version.

You do not have to remember to look: the tool's header shows its version (top right), and the chip
turns **amber** with an arrow — `⬆ v0.5.1 → 0.5.2` — when GitHub has something newer. Click it and
press **Update now**: a small window installs the new version after the tool closes, the tool
reopens by itself, and the page you had open reloads. No typing needed.

### Check it installed

```
pxrd --version
```
It should print `pxrd-review <version>` — and that version should match the one marked
**`Latest`** on the [Releases page](https://github.com/toldxls/ICDD-reviewer/releases). If it
is older, the upgrade didn't take: re-run the install command and reopen the Command Prompt.

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

**One correction is written for you — as a tracked change.** If a reference title is in Title
Case (`a New Mineral From the Burro Mine`) where ICDD style is sentence case, the tool corrects it
in the **copy** as a **Word tracked change**. Open the docx in Word and you will see it marked in
the Reference cell: click **Accept** to keep it or **Reject** to put the original back — exactly
as you would with another reviewer's edit. It never overwrites a cell **you** have already edited,
and it never changes anything but the capitalisation. Every other finding is a comment for you to
act on; this is the only one the tool writes.

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

> Every step matters. Reviewers install from **`/releases/latest`** and from **`main`**, so a
> release that is not pushed, or that carries the wrong `.whl`, silently serves an **old tool**.

1. **Refresh the bundled Mindat snapshot** (so reviewers with no API key get current data — and
   the type localities the GUI shows):
   ```
   python3 -m pxrd_review.mindat --refresh --bundle
   ```
   Commit `pxrd_review/data/`.

2. Bump the version in **both** `pyproject.toml` and `pxrd_review/__init__.py`; update
   `CHANGELOG.md`; run the regression suite (`pxrd check "<fixtures>"` — every case must PASS).

3. **Commit and push `main`.** This is what ships: the one-line install in §2B and the
   `Download ZIP` route both take whatever `main` currently holds.
   ```
   git commit -am "…"
   git push origin main
   ```

4. **Build the wheel into a CLEAN `dist/`.** `python3 -m build` does *not* empty `dist/`, so a
   stale wheel from an earlier release survives there — and step 6's `dist/*.whl` would then
   upload **that** as the new release's asset. Reviewers are told to download "the `.whl`", so
   they would install the old tool. Delete it first:
   ```
   rm -rf dist                       # Windows: rmdir /s /q dist
   python3 -m build --wheel          # one-time: pip3 install build
   ls dist                           # sanity: exactly ONE .whl, and it is the new version
   ```

5. **Checksum it** (both hashes go in the release notes):
   ```
   cd dist && shasum -a 256 pxrd_review-<version>-py3-none-any.whl > SHA256SUMS.txt && cd ..
   git tag -a v<version> -m "v<version> — <headline>" && git push origin --tags
   ```

6. **Publish the release**, attaching the wheel **and** `SHA256SUMS.txt`, and put BOTH hashes in
   the notes — INSTALL.md tells reviewers to verify against them:
   ```
   gh release create v<version> \
       dist/pxrd_review-<version>-py3-none-any.whl \
       dist/SHA256SUMS.txt \
       --latest --title "v<version> — <headline>" --notes "…"
   ```
   The notes **must** end with a ready-to-paste, hash-pinned install line — §2B sends reviewers
   here for it, and it is the only install path pip actually verifies:
   ```
   Source archive SHA-256 (v<version>.zip):
   pip install --upgrade "https://github.com/toldxls/ICDD-reviewer/archive/refs/tags/v<version>.zip#sha256=<hash>"
   ```
   Get that hash *after* pushing the tag:
   ```
   curl -sL -o /tmp/src.zip https://github.com/toldxls/ICDD-reviewer/archive/refs/tags/v<version>.zip
   shasum -a 256 /tmp/src.zip
   ```

7. **Verify what you actually published** — the check that catches every mistake above at once:
   ```
   gh release view v<version> --json assets -q '.assets[].name'    # the NEW wheel + SHA256SUMS.txt
   pip install --upgrade "https://github.com/toldxls/ICDD-reviewer/archive/refs/heads/main.zip"
   pxrd --version                                                  # must print the new version
   ```
