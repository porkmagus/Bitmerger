# Bitmerger

> Local, reviewable cleanup and reconciliation for Bitwarden and 1Password vault exports.

Bitmerger runs entirely on your machine. It never uploads vault data, but it deliberately works with plaintext exports — treat every source and output file as sensitive.

## What it supports

### Bitwarden

Bitwarden has five vault item types, all represented in Bitmerger:

| Type | Overview fields | Merge identity |
|---|---|---|
| Login | username, domain, TOTP, passkey count | domain + username + password |
| Secure note | note indicator | note content fingerprint |
| Card | masked last four, brand, expiry | brand + last four + expiry |
| Identity | email/phone, name | email + last name + SSN when present |
| SSH key | fingerprint, public-key availability | SSH fingerprint |

The overview intentionally does not display passwords, TOTP secrets, or SSH private keys in the table.

### 1Password

- 1Password Unencrypted Export (`.1pux`) is the primary full-vault source.
- 1Password CSV is an optional login/TOTP enrichment source.
- CSV `OTPAuth` values are only treated as TOTP when they are valid `otpauth://totp/` URIs. Other values are retained as concealed custom fields and reported.
- Direct counterparts become Bitwarden Login, Card, Identity, or Secure Note items.
- Unsupported 1Password categories are retained as secure notes with category metadata rather than silently dropped.
- 1Password vault provenance, tags, archived state, and password history are preserved through the normalized model.
- Attachment and document payloads cannot be imported into Bitwarden JSON. Their metadata is written to the output audit report as an attachment manifest.

Important: Bitwarden documents JSON as an import format. 1Password documents 1PUX as an unencrypted export/archive format, not as a guaranteed re-import mechanism. Treat generated 1PUX files as portable cleaned archives and use 1Password’s currently supported import/migration path where applicable.

## Quick start

### Windows PowerShell

```powershell
cd $HOME\MyGithubRepos

# First time only
git clone https://github.com/porkmagus/Bitmerger.git bitmerger
cd bitmerger
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# Launch
python bw_dedup.py
```

For later launches:

```powershell
cd $HOME\MyGithubRepos\bitmerger
git pull --ff-only
.\.venv\Scripts\Activate.ps1
python bw_dedup.py
```

If PowerShell blocks activation for the current shell:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### macOS and Linux

```bash
git clone https://github.com/porkmagus/Bitmerger.git
cd Bitmerger
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python bw_dedup.py
```

## GUI workflows

### Vault Overview

Open a Bitwarden JSON, 1Password 1PUX, or 1Password CSV export. The sortable overview uses type-aware **Primary** and **Details** columns so cards, identities, secure notes, and SSH keys are useful without exposing secrets in the grid.

### Deduplicate

1. Choose a similarity threshold and item types.
2. Analyze candidate clusters.
3. Use the confidence filter to restrict automatic merges.
4. Run a dry report or execute a merge.

The engine preserves non-conflicting URI entries, including query strings and Bitwarden URI match modes. Custom fields, password history, passkeys, TOTP, collections, folders, and notes are merged without duplicate copies where supported.

### Batch Editor

Search with ordinary terms or field filters such as:

```text
favorite:true
username:alice
domain:github.com
folder:Personal
notes:backup
id:abc
```

Batch-edit name, username, notes, favorite, reprompt, folder, and domain-related fields. Outputs retain the active vault format where possible.

### Merge Vaults

1. Select a Bitwarden JSON export.
2. Select a 1Password 1PUX export.
3. Optionally select a 1Password CSV export for TOTP enrichment.
4. Select **Preview Safety & Duplicates**.
5. Review strict candidates, ambiguous candidates, passkeys, attachment manifests, source-vault metadata, and migration warnings.
6. For ambiguous groups, choose **Merge Selected**, **Keep Separate**, or **Never Suggest**.
7. Create the outputs.

By default, Bitmerger creates a unique timestamped run folder so plaintext artifacts from separate runs never collide. The generated run contains:

```text
bitmerger-run-YYYYMMDD-HHMMSS-xxxxxx/
├── bitmerger-merged.bitwarden.json
├── bitmerger-merged.1password.1pux
└── bitmerger-merged.report.json
```

The audit report contains warnings, attachment metadata, source-output paths, and manual review decisions.

### Persistent review decisions

**Never Suggest** is stored locally in `~/.bitmerger/merge-decisions.json` (or the path supplied in `BITMERGER_DECISION_STORE`). It stores only hashes of source fingerprints and item IDs — never vault content or secrets. A source-file change naturally invalidates an old decision.

## Command line

```bash
python -m bitmerger.cli merge-vaults bitwarden.json onepassword.1pux \
  --onepassword-csv onepassword.csv \
  --output-dir ./bitmerger-output \
  --threshold 0.95
```

The CLI leaves inputs untouched. It rejects source/output path collisions and refuses to overwrite existing outputs unless explicitly authorized by the calling API.

## Security model

- All vault processing is local.
- Source exports, outputs, temporary artifacts, and reports may contain secrets.
- Bitmerger creates new outputs with owner-only permissions where the platform supports them.
- Output creation is staged and validated before artifacts are published.
- 1PUX archives are checked for unsafe paths, duplicate members, excessive member counts, excessive size, and suspicious compression ratios before parsing.
- Do not commit vault exports, generated reports, or attachment bundles to Git.

## Local release gate

This project intentionally uses local verification rather than GitHub CI.

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
.venv/bin/python -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen .venv/bin/python e2e_test.py
.venv/bin/python -m compileall -q bitmerger tests
git diff --check
```

For a macOS packaged-app smoke check:

```bash
.venv/bin/python -m pip install pyinstaller
.venv/bin/python build.py
QT_QPA_PLATFORM=offscreen dist/Bitmerger.app/Contents/MacOS/Bitmerger
```

## Building

```bash
python -m pip install pyinstaller
python build.py
```

PyInstaller output is placed under `dist/`. Build on the target operating system for that operating system’s native package.

## Project layout

```text
bitmerger/
├── bw_dedup.py                 # GUI entry point
├── build.py                    # PyInstaller build
├── bitmerger/
│   ├── core.py                 # Bitwarden models, duplicate engine, merges
│   ├── vault_formats.py        # Bitwarden / 1PUX / CSV adapters and merge safety
│   ├── gui.py                  # PySide6 desktop app
│   ├── item_editor.py          # Item editing component
│   ├── theme.py                # Shared Qt stylesheet and theme support
│   ├── fluidity.py             # Safe visual feedback helpers
│   └── templates/report.jinja2
├── tests/                      # Core, formats, GUI, CSV, and workflow tests
└── requirements.txt
```

## Known boundaries

- Bitwarden JSON exports do not provide a portable attachment-import representation.
- 1Password desktop CSV and 1PUX exports do not carry 1Password passkeys. Bitmerger preserves Bitwarden passkeys; use 1Password Credential Exchange on iOS/Android for 1Password passkey migration.
- Generated 1PUX archives are validated against the public export structure but are not promised as a direct 1Password import replacement.
