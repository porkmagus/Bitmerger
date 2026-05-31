# 🔐 Bitmerger

> **Intelligent, safe deduplication for Bitwarden vaults.**  
> Auto-merge duplicate entries with confidence scoring. One click. Zero data loss.

---

## Table of Contents
- [What It Does](#what-it-does)
- [Quick Start](#quick-start)
- [Features](#features)
- [Health Audit](#health-audit)
- [Safety Guarantees](#safety-guarantees)
- [How It Works](#how-it-works)
- [Testing](#testing)
- [Security & Privacy](#security--privacy)
- [Building](#building)

---

## ✨ What It Does

After years of use, Bitwarden vaults accumulate duplicate entries:

- **Multiple logins** for the same site (different URIs, older entries)
- **Overlapping imports** where the same account appears twice
- **Split accounts** where one entry has the TOTP and another has the passkey
- **Typos and variants** (e.g., `twitter.com` vs `x.com`)

**This tool:**
1. Finds all duplicates using smart domain & credential blocking
2. Scores each cluster with a confidence percentage
3. Auto-merges duplicates into the best primary entry
4. Creates backups, logs, and an HTML report
5. Outputs a clean JSON file ready to re-import

**Supports all 5 Bitwarden item types:**

| Type | How Duplicates Are Found |
|------|--------------------------|
| 🔑 **Logins** | Same domain + username + password (with passkey & TOTP deduplication) |
| 📝 **Notes** | Content fingerprint matching |
| 💳 **Cards** | Brand + last-4 digits + expiry date |
| 🪪 **Identities** | Email + last name + SSN |
| 🔐 **SSH Keys** | Key fingerprint |

---

## 🚀 Quick Start

### Option 1: Download Pre-built Release (No Setup Required)

1. Go to [GitHub Releases](https://github.com/porkmagus/bitmerger/releases)
2. Download the latest release for your platform:
   - **macOS:** `Bitmerger-macos.zip` — unzip and double-click `Bitmerger.app`
   - **Windows:** `Bitmerger-windows.zip` — unzip and run `Bitmerger.exe`
   - **Linux:** `Bitmerger-linux.tar.gz` — extract and run `./Bitmerger/Bitmerger`
3. Export your Bitwarden vault as JSON and open it in Bitmerger

### Option 2: Run from Source

#### 1. Install

```bash
# Clone or download this repo
git clone https://github.com/you/bitmerger.git
cd bitmerger

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate        # macOS/Linux
# OR
.venv\Scripts\activate.ps1        # Windows PowerShell
# OR
.venv\Scripts\activate.bat        # Windows cmd

# Install dependencies
pip install -r requirements.txt
```

### 2. Export Your Vault

1. Open **Bitwarden Web Vault** (or app)
2. Go to **Tools** → **Export Vault** → **JSON**
3. Save as `vault.json`

### 3. Launch Bitmerger

```bash
python3 -m bitmerger
# or
python3 bw_dedup.py
```

**That's it!** The GUI will open:
- Drag your `vault.json` into the window, or click **Open Vault**
- Browse all items in the **Vault Overview** tab
- Click **🔍 Analyze Duplicates** in the **Deduplicate** tab
- Review the **HTML Report** before importing

---

## 🖥️ Features

### Vault Overview
- Browse all items in a sortable table with 🔑 📝 💳 🪪 🔐 type icons
- Double-click any item to edit inline
- Real-time search across name, username, domain, notes, folder
- Right-click context menu: copy password, open URL, find duplicates

### Inline Item Editor
- Edit name, username, password, TOTP, URIs, notes
- Card fields: number, expiry, brand, CVV
- Identity fields: name, address, email, phone, SSN
- SSH keys: public key, private key, fingerprint
- Custom fields: dynamic key/value rows with type selection
- Password generator with length control
- Folder dropdown and collection tags

### Deduplicate
- Adjustable similarity threshold (0.0–1.0)
- Per-item-type toggles (logins, notes, cards, identities, SSH)
- Confidence filter: only auto-merge clusters above a confidence score
- Fast mode for large vaults
- Per-field merge preview before executing
- Execute merge with one click

### Batch Editor
- Search across **all** Bitwarden fields with `field:value` syntax: `favorite:true`, `type:login`, `folder:Personal`, `username:alice`, `domain:github.com`, `notes:backup`, `id:abc`, `org:my-org`, `collection:shared`
- Bulk edit fields: **Name**, **Username**, **Notes**, **Favorite**, **Reprompt**, **Folder**
- Toggle booleans (Favorite, Reprompt) with a checkbox
- Apply to selected rows or all visible matches
- Preview matches before applying
- Undo/redo supported
- Exports `.edited.json` with a `.batch-edit-log.json` audit trail

### Health Audit
- One-click scan for:
  - **Weak passwords** — <8 chars or common patterns
  - **Reused passwords** — Clusters sharing the same password
  - **Missing TOTP** — Logins for known 2FA providers without TOTP
  - **Empty passwords** — Logins with no password
- Export results as CSV

### Dark / Light / Auto Theme
- Toggle via menu or the 🌙 button in the header
- Fully recolored tables, buttons, inputs, and panels
- Persists across restarts

### Drag & Drop
- Drop any `.json` file onto the window to load instantly

### Undo / Redo
- `Ctrl+Z` / `Ctrl+Shift+Z` for every edit, merge, and rename
- Descriptive undo labels in the Edit menu
- 50-step history with deep-copy snapshots

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+O` | Open vault |
| `Ctrl+S` | Save vault |
| `Ctrl+Shift+S` | Export CSV |
| `Ctrl+F` | Focus search |
| `Ctrl+M` | Analyze duplicates |
| `Ctrl+D` | Dry run |
| `Ctrl+Z` | Undo |
| `Ctrl+Shift+Z` | Redo |
| `Ctrl+T` | Toggle theme |
| `Delete` | Delete item |
| `F1` | Keyboard shortcuts overlay |

### Welcome Wizard
- First-run guide with **Open Vault** and **Load Sample** buttons
- Sample vault creates 5 demo items for exploration

---

## 🏥 Health Audit

1. Open the **Health Audit** tab
2. Click **Run Health Audit**
3. Review the report:
   - **Weak passwords** — Items with <8 chars or common patterns (`password123`, `123456`)
   - **Reused passwords** — Clusters of items sharing the same password
   - **Missing TOTP** — Logins for known 2FA providers without a TOTP secret
   - **Empty passwords** — Logins with no password set

Export the results as a CSV from the File menu for spreadsheet review.

---

## 🛡️ Safety Guarantees

Every merge is safe. Nothing is ever deleted.

| Feature | What It Means |
|---|---|
| **Automatic Backup** | Original export saved as `vault.original.YYYYMMDD_HHMMSS.json` |
| **Merge Log** | Every merge recorded in `vault.dedup.json.merge-log.json` — reviewable and auditable |
| **HTML Report** | Visual report of all clusters. Review before importing |
| **Confidence Scoring** | Each cluster scored 0–100%. High scores = safe auto-merge |
| **Conflict Absorption** | If entries differ, the secondary is recorded in notes — **nothing is lost** |
| **Passkey Preservation** | Multiple passkeys with different IDs are all kept |
| **TOTP Backfill** | Missing TOTP in primary? Merged from duplicate |
| **Collection & Folder Merge** | All collection IDs and folder metadata are unioned |
| **Zero Network Calls** | Everything processed locally. Your data never leaves your machine |
| **Undo / Redo** | `Ctrl+Z` reverses any merge, rename, or field edit |

---

## 🧠 How It Works

### The Challenge: Finding Duplicates Efficiently

Comparing every item to every other item is expensive: **5,000 items = 12.5M comparisons.**

**Solution:** Smart blocking — group items before comparing.

### Three-Phase Blocking

1. **Domain Block**  
   Items with the same normalized domain are grouped together
   ```
   example.com, www.example.com, sub.example.com → SAME GROUP
   ```

2. **Credential Block**  
   Items with identical `(username, password)` hash are grouped
   ```
   (alice, secret123) → SAME GROUP regardless of URI
   ```

3. **Orphan Fallback**  
   Items with no domain/credentials are only compared if <500 orphans exist

**Result:** ~300,000 comparisons instead of 12.5M. **5,000 items in ~0.5 seconds.**

---

### Primary Selection Heuristic

For each duplicate cluster, the "best" entry becomes the primary based on:

1. Most URIs
2. Has a folder
3. Has passkeys
4. Has TOTP
5. Has notes
6. Has password history
7. Most custom fields
8. Shortest name

**All secondary data is preserved** — merged into the primary entry's notes if fields differ.

---

### Confidence Scoring

| Score | Meaning | Action |
|-------|---------|--------|
| **100%** | Exact domain + username + password match | Auto-merge |
| **≥95%** | Very similar items | Auto-merge |
| **85–95%** | Good match | Review recommended |
| **<85%** | Loose match | Review strongly recommended |

---

## 📈 Performance

| Vault Size | Duplicates | Time | Comparisons |
|---|---|---|---|
| 10 items | ~5 | 0.02s | 6 |
| 500 items | ~175 | 0.08s | ~12,000 |
| 5,000 items | ~1,170 | **0.48s** | **~297,000** |

---

## 🧪 Testing

Run the comprehensive test suite (55 tests):

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

**Coverage:**
- Normalization and fuzzy matching
- Login, card, identity, SSH, and note similarity scoring
- Cluster confidence calculation
- Primary selection algorithm
- Merge logic (backfill, conflict absorption, deduplication)
- Passkey deduplication
- Collection and folder merging
- Round-trip serialization
- Backup and merge log generation
- HTML report generation
- Batch editor query parsing and matching
- Batch edit log generation
- End-to-end integration tests

All tests pass with **0 type checking errors**.

---

## 🔄 Re-Importing Your Cleaned Vault

Once deduplication is complete:

1. Open **Bitwarden Web Vault** (or desktop/mobile app)
2. Go to **Tools** → **Import Data**
3. Select **Bitwarden (json)**
4. Choose your `vault.dedup.json` file
5. Click **Import**

**⚠️ Heads Up:** Importing creates new items. If you want to **replace** your vault (not add duplicates), either:
- Delete all items from your vault first, OR
- Import into a fresh Bitwarden account for testing

---

## 🔒 Security & Privacy

| Aspect | Guarantee |
|--------|-----------|
| **Network** | No network calls. Everything local. |
| **Data** | Your data never leaves your machine. |
| **Backups** | Automatic backups created on every run. Restore anytime. |
| **Logs** | Human-readable JSON. Fully auditable. |
| **Secrets** | Passwords and TOTPs are masked in reports. |

---

## 📦 Building a Standalone Executable

Package Bitmerger into a single-file `.app` (macOS), `.exe` (Windows), or AppImage (Linux) with no Python installation required.

### Prerequisites

```bash
pip install pyinstaller
```

### Build

```bash
# macOS / Linux / Windows
python build.py

# Single-file executable
python build.py --onefile
```

Output will be in `dist/Bitmerger/`.

### macOS App Bundle

```bash
# After pyinstaller build
mv dist/Bitmerger.app /Applications/Bitmerger.app
```

---

## 📁 Project Structure

```
bitmerger/
├── bw_dedup.py              # Entry point — launches GUI
├── bitmerger/
│   ├── __init__.py
│   ├── __main__.py          # python -m bitmerger
│   ├── core.py              # Engine: models, similarity, merging
│   ├── gui.py               # PySide6 desktop GUI
│   ├── theme.py             # Dark/Light/Auto theme manager
│   ├── icons.py             # Type icons & confidence badges
│   ├── item_editor.py       # Inline item editing panel
│   ├── undo_manager.py      # Undo/redo stack
│   └── templates/
│       └── report.jinja2    # HTML report template
├── requirements.txt         # Python dependencies
├── .gitignore
├── README.md
├── build.py                 # PyInstaller build script
├── generate_large_vault.py  # Synthetic vault generator
├── test_large_vault.py      # Stress test suite
└── tests/
    ├── test_engine.py       # 35 core engine tests
    └── test_batch_editor.py # 20 batch-editor tests
```

---

## 🐛 Troubleshooting

### `tldextract` Deprecation Warning
**Symptom:** `The 'registered_domain' property is deprecated...`  
**Fix:** Harmless. Code handles both old and new APIs automatically.

### No Duplicates Found
**Symptom:** Tool runs but finds 0 duplicates.  
**Check:** Ensure you exported as **Bitwarden JSON** (not CSV). File should contain an `items` array.

### Import Fails in Bitwarden
**Symptom:** "Invalid JSON" error when importing.  
**Fix:** Ensure the `*.dedup.json` file hasn't been corrupted. Check the merge log for details.

### GUI won't launch
**Symptom:** `ImportError: No module named 'PySide6'`  
**Fix:** Install GUI dependencies:
```bash
pip install PySide6
# or
pip install -r requirements.txt
```

---

## 📦 Dependencies

- **Jinja2** — HTML report templating
- **thefuzz** — Fuzzy string matching
- **tldextract** — Domain extraction
- **PySide6** — Cross-platform GUI (Qt for Python)

All specified in `requirements.txt`. Install with:
```bash
pip install -r requirements.txt
```

---


## Security Notes

- CSV export includes passwords in plaintext. Use with caution.
- Reused password detection compares passwords in memory.
- Auto-save writes plaintext JSON to disk. Ensure your vault directory is secure.


## Browser Integration

Bitmerger does not include browser integration or auto-type functionality. It is a vault utility for deduplication, audit, and comparison. Use the official Bitwarden browser extension for form filling and auto-type.

## Attachments

Bitmerger does not support vault attachments. Attachments are not included in standard Bitwarden JSON exports and are not processed by this tool.
