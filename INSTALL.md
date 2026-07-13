# Installing & upgrading the PXRD review tool

Step-by-step instructions for ICDD reviewers, written for **Windows**
(macOS/Linux notes at the end).

Everything arrives as **one file** on the shared files site:
`pxrd-review-<version>-bundle.zip`, which contains

| file | what it is |
|---|---|
| `pxrd_review-<version>-py3-none-any.whl` | the tool (this is what gets installed) |
| `SHA256SUMS.txt` | the wheel's fingerprint (integrity check) |
| `INSTALL.md` | this file |

After installing you get one command, `pxrd` — e.g. `pxrd gui "C:\path\to\entries"` —
available from any Command Prompt.

---

## One-time setup (before your first install)

### 1. Install Python
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

### 2. Mindat API key (enables the Mindat cross-checks)
Get a key from your **mindat.org** account page, then in a Command Prompt:
```
setx MINDAT_API_KEY "YOUR_MINDAT_TOKEN"
```
Close and reopen the Command Prompt (the variable only appears in new windows).
This survives reboots and upgrades — set it once and forget it.
*(Already have the key working from an earlier install? It keeps working; skip this.)*

---

## Install — and every upgrade (same four steps)

1. **Download** the newest `pxrd-review-<version>-bundle.zip` from the shared files
   site and unzip it (right-click → *Extract All…*).

2. **Check the wheel is genuine.** The message announcing the upload includes the
   wheel's SHA-256 fingerprint. In a Command Prompt, type `certutil -hashfile `
   (with the trailing space), **drag the `.whl` file** from the unzipped folder into
   the window, type ` SHA256`, and press Enter:
   ```
   certutil -hashfile "C:\...\pxrd_review-0.2.2-py3-none-any.whl" SHA256
   ```
   The long hex string it prints must match the announced fingerprint exactly.
   Any single character different = corrupted download — stop and re-download,
   or ask the maintainer.

3. **Install.** Type `pip install --upgrade ` (trailing space again), drag the same
   `.whl` file in, press Enter:
   ```
   pip install --upgrade "C:\...\pxrd_review-0.2.2-py3-none-any.whl"
   ```
   The first install needs internet access (pip fetches the tool's libraries from
   pypi.org); upgrades normally don't.

4. **Verify:**
   ```
   pxrd --version
   ```
   It should print the version from the announcement (e.g. `pxrd-review 0.2.2`).
   If `pxrd` is "not recognized", close and reopen the Command Prompt first; if it
   still isn't found, re-check One-time setup step 1 (PATH).

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

Same steps; use `python3` / `pip3` in the commands, check the fingerprint with
`shasum -a 256 <file>` instead of `certutil`, and set the key with
`export MINDAT_API_KEY="…"` in `~/.zshrc` (macOS) or `~/.bashrc` (Linux) instead of
`setx`. Developers working from a checkout should keep using `pip install -e .`
(see README "Setup") — an editable install keeps its `.cache/` and `.mindat_key`
at the repo root, exactly as before.

---

## Maintainer — cutting a release

1. Bump the version in **both** `pyproject.toml` and `pxrd_review/__init__.py`;
   update `CHANGELOG.md`; commit.
2. Build the wheel (one-time `pip3 install build`):
   ```
   python3 -m build --wheel
   ```
3. Build the bundle:
   ```
   cd dist
   shasum -a 256 pxrd_review-<version>-py3-none-any.whl > SHA256SUMS.txt
   cp ../INSTALL.md .
   zip pxrd-review-<version>-bundle.zip pxrd_review-<version>-py3-none-any.whl SHA256SUMS.txt INSTALL.md
   rm INSTALL.md
   ```
4. Upload the bundle zip to the shared files site, and put the wheel's SHA-256
   fingerprint **in the announcement message itself** (the copy inside the zip can
   only catch corruption, not tampering — the message is the independent channel).
5. Optional, for the archive: also attach the wheel to a GitHub release
   (`gh release create v<version> dist/*.whl --notes "…SHA-256: …"`).
