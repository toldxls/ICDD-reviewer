# Installing & upgrading the PXRD review tool

Step-by-step instructions for ICDD reviewers. Written for **Windows**; macOS/Linux
differences are noted at the end. After installing you get one command, `pxrd`
(e.g. `pxrd gui "C:\path\to\entries"`), available from any Command Prompt.

There are **two ways** to install and upgrade. Both end up in exactly the same place —
pick one and stick with it:

| | **Option A — wheel file** | **Option B — straight from GitHub** |
|---|---|---|
| Extra software needed | none (just Python) | Python **+ Git for Windows** |
| Install / upgrade step | download a file from the Releases page, `pip install` it | one single command does both |
| Best for | anyone; simplest to explain | comfortable-with-terminal users |

---

## One-time setup (both options)

### 1. Accept the GitHub invitation
The repository (`github.com/toldxls/ICDD-reviewer`) is **private**. You'll receive an
e-mail invitation from GitHub — sign in (create a free account if needed) and click
**Accept invitation**. Without this, the download links below give a 404.

### 2. Install Python
1. Go to <https://www.python.org/downloads/> and download the latest Python 3 for Windows.
2. Run the installer. On the very first screen **tick the box "Add python.exe to PATH"**
   — this is the step people miss, and nothing works without it.
3. Verify: open a **new** Command Prompt (Start menu → type `cmd`) and run:
   ```
   python --version
   pip --version
   ```
   Both should print a version, not "'python' is not recognized…". If they don't,
   re-run the installer and tick the PATH box.

### 3. Mindat API key (enables the Mindat cross-checks)
Get a key from your **mindat.org** account page, then in a Command Prompt:
```
setx MINDAT_API_KEY "YOUR_MINDAT_TOKEN"
```
Close and reopen the Command Prompt (the variable only appears in new windows).
This survives reboots and upgrades — set it once and forget it.
*(Already have the key working from an earlier install? It keeps working; skip this.)*

---

## Option A — install / upgrade from a wheel file

**No Git needed.** The wheel (`.whl`) is a single installable file attached to each
release.

1. Go to the releases page (sign in to GitHub first):
   **<https://github.com/toldxls/ICDD-reviewer/releases>**
2. Under the newest release, in **Assets**, download the file that looks like
   `pxrd_review-0.2.2-py3-none-any.whl` (the version number will differ).
3. **Check the file is genuine.** Every release lists the file's `SHA-256`
   fingerprint in its notes. In a Command Prompt:
   ```
   certutil -hashfile "%USERPROFILE%\Downloads\pxrd_review-0.2.2-py3-none-any.whl" SHA256
   ```
   The long hex string it prints must match the one in the release notes exactly
   (any single character different = corrupted or tampered download — stop and
   re-download / ask Travis).
4. Install it — **note the `--upgrade`**:
   ```
   pip install --upgrade "%USERPROFILE%\Downloads\pxrd_review-0.2.2-py3-none-any.whl"
   ```
   Replace the file name with the one you actually downloaded.
   *Tip: type `pip install --upgrade ` (with the trailing space) and then drag the
   downloaded file from Explorer into the Command Prompt window — it pastes the full
   path for you.*

**That's the whole procedure — first install and every upgrade are the same four
steps**, just with a newer file. pip sees the higher version number and replaces the
old one.

---

## Option B — install / upgrade straight from GitHub

**One-time extra:** install **Git for Windows** from <https://git-scm.com/download/win>
(all default options are fine).

Then this **single command is both the first install and every later upgrade**:
```
pip install --upgrade git+https://github.com/toldxls/ICDD-reviewer.git
```
The first time, a GitHub sign-in window pops up in the browser — sign in with the
account that accepted the invitation. Git remembers it afterwards.

If it prints "Requirement already satisfied" but a newer release exists, force it:
```
pip install --upgrade --force-reinstall git+https://github.com/toldxls/ICDD-reviewer.git
```

---

## After any install or upgrade — verify

```
pxrd --version
```
This prints e.g. `pxrd-review 0.2.2`. Compare with the newest release number on the
[Releases page](https://github.com/toldxls/ICDD-reviewer/releases). If the command
prints an older number, the upgrade didn't take — re-run the install command and
watch for error text.

If `pxrd` itself is "not recognized", close and reopen the Command Prompt first;
if it still isn't found, run `pip show pxrd-review` to confirm it installed, and
re-check step 2 (PATH).

---

## Running it

```
pxrd gui "C:\path\to\entries"
```
Point it at the folder holding the entry `.docx` **and** `.pdf` files. The folder is
remembered — from then on a bare `pxrd gui` reopens it. Other sub-commands:
`pxrd review`, `pxrd sweep`, `pxrd refresh`, … (run `pxrd --help` for the list).

**Upgrades never touch your data.** The API key, the Mindat caches
(`%USERPROFILE%\.pxrd_review\`), your entries folders, and every `review_out\`
folder (triage, edited docx) all live outside the installed package and survive
every upgrade untouched.

---

## macOS / Linux differences

Same two options; use `python3` / `pip3` in the commands, set the key with
`export MINDAT_API_KEY="…"` in `~/.zshrc` (macOS) or `~/.bashrc` (Linux) instead of
`setx`, and check the wheel's fingerprint with `shasum -a 256 <file>` instead of
`certutil`. Developers working from a checkout should keep using `pip install -e .`
(see README "Setup") — an editable install keeps its `.cache/` and `.mindat_key`
at the repo root, exactly as before.

---

## Maintainer — cutting a release

1. Bump the version in **both** `pyproject.toml` and `pxrd_review/__init__.py`;
   update `CHANGELOG.md`; commit.
2. Build the wheel (one-time `pip3 install build`):
   ```
   python3 -m build
   ```
   → `dist/pxrd_review-<version>-py3-none-any.whl` (pure Python, small).
3. Publish it as a GitHub release with the wheel attached **and its SHA-256 in the
   notes** (reviewers verify their download against it — step 3 of Option A):
   ```
   gh release create v<version> dist/pxrd_review-<version>-py3-none-any.whl \
       --title "v<version>" \
       --notes "See CHANGELOG.md

   SHA-256: $(shasum -a 256 dist/pxrd_review-<version>-py3-none-any.whl | cut -d' ' -f1)"
   ```
4. Tell the reviewers a new version is up — they upgrade via Option A or B above.
