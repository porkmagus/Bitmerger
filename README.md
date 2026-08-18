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

Bitmerger writes an import-shaped 1PUX archive using 1Password’s public `export.attributes` / `export.data` structure and 1Password-style base32 IDs. It also produces a login CSV with native `OTPAuth` columns. Always keep the Bitwarden JSON output: it is the complete portable artifact, including Bitwarden passkeys.

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

1. Select a Bitwarden JSON export and a 1Password 1PUX export.
2. Optionally select a 1Password CSV export for TOTP enrichment.
3. Select **1. Preview Safe Merge**.
4. Read the concise safety summary, then select **2. Create Clean Vaults**.

Only high-confidence duplicates are merged. Ambiguous groups are automatically kept as separate entries—there is no per-item review queue or dropdown. The normal flow is preview, one confirmation, and a completion summary.

By default, Bitmerger creates a unique timestamped run folder so plaintext artifacts from separate runs never collide. The generated run contains:

```text
bitmerger-run-YYYYMMDD-HHMMSS-xxxxxx/
├── bitmerger-merged.bitwarden.json
├── bitmerger-merged.1password.1pux
├── bitmerger-merged.1password-logins.csv
├── bitmerger-passkey-recovery.bitwarden.json
└── bitmerger-merged.report.json
```

The audit report contains warnings, attachment metadata, source-output paths, and explicit preservation counts for TOTP secrets, passkeys, password-bearing login entries, and all login entries. The CSV is intentionally login-only; CSV has no safe native representation for passkeys, cards, identities, or arbitrary custom fields.

### Passkeys: verified preservation, separate transfer

Bitmerger never puts passkeys into desktop 1PUX or CSV because those formats do not transport them. It writes `bitmerger-passkey-recovery.bitwarden.json`, a Bitwarden-compatible subset containing each final passkey-bearing entry, and verifies a SHA-256 fingerprint for every complete passkey credential before publication. The report marks a passkey-bearing run as `manual_passkey_transfer_required`.

Desktop 1Password cannot import passkeys from a file. To finish a migration, use direct Credential Exchange (CXP) in compatible mobile apps **or** use the existing Bitwarden passkey to sign in on each website and create a new passkey saved in 1Password. Then compare the report’s passkey count and test every migrated passkey before deleting the source vault or any recovery artifact. The recovery JSON is a lossless Bitwarden recovery file, **not** an import file for 1Password. See `docs/PASSKEY-MIGRATION.md` for the complete verified procedure.

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
- The generated 1PUX archive and login CSV carry TOTP material, while the Bitwarden JSON remains the authoritative portable output for Bitwarden passkeys.
