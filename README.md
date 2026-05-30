# 🔐 Bitmerger

> **Intelligent, safe deduplication for Bitwarden vaults.**  
> Auto-merge duplicate entries with confidence scoring. One command. Zero data loss.
> **Now with a cross-platform GUI and batch rename tools.**

---

## Table of Contents
- [What It Does](#what-it-does)
- [Quick Start](#quick-start)
- [GUI Mode](#gui-mode)
- [Batch Rename](#batch-rename)
- [Safety Guarantees](#safety-guarantees)
- [Usage & Options](#usage--options)
- [How It Works](#how-it-works)
- [Testing](#testing)
- [Security & Privacy](#security--privacy)

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

### 1. Install

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

### 3. Run the Tool

```bash
python3 bw_dedup.py vault.json
```

**That's it!** The tool will:
- Analyze and find all duplicate clusters
- Auto-merge everything safely
- Create a **backup** (`vault.original.YYYYMMDD_HHMMSS.json`)
- Write a **clean export** (`vault.dedup.json`)
- Write a **merge log** (`vault.dedup.json.merge-log.json`)
- Generate an **HTML report** (`vault.report.html`)

---

## 🖥️ GUI Mode

Launch the polished desktop GUI:

```bash
python3 -m bitmerger --gui
# or
python3 bw_dedup.py --gui
```

**Features:**
- **Vault Overview** — Browse all items in a sortable table
- **Deduplicate** — Point-and-click settings, analyze, preview, then execute
- **Batch Rename** — Search and standardize item names with mouse clicks
- **Progress bars** and **confirmation dialogs** for every destructive action
- **Cross-platform** — Works on macOS, Windows, and Linux

---

## 🏷️ Batch Rename

Standardize messy vault names (e.g., `google.com`, `mail.google.com`, `accounts.google.com` → `Google`):

```bash
python3 bw_dedup.py batch-rename vault.json --search "google+mail.google" --replace "Google" --yes
```

| Option | Description |
|--------|-------------|
| `--search` | Query with `+` for OR: `microsoft+live.com` |
| `--replace` | New name for all matched items |
| `--types` | Limit to item types (e.g., `1` for logins only) |
| `--dry-run` | Preview matches without writing |
| `--yes` | Skip confirmation |
| `--no-backup` | Skip backup creation |

Every merge is safe. Nothing is ever deleted.

| Feature | What It Means |
|---|---|
| **Automatic Backup** | Original export saved as `vault.original.YYYYMMDD_HHMMSS.json` |
| **Merge Log** | Every merge recorded in `vault.dedup.json.merge-log.json` — reviewable and auditable |
| **HTML Report** | Visual report of all clusters. Review before importing |
| **Confidence Scoring** | Each cluster scored 0–100%. High scores = safe auto-merge |
| **Conflict Absorption** | If entries differ (e.g., different usernames), the secondary is recorded in notes — **nothing is lost** |
| **Passkey Preservation** | Multiple passkeys with different IDs are all kept; one entry can hold many |
| **TOTP Backfill** | Missing TOTP in primary? Merged from duplicate |
| **Collection & Folder Merge** | All collection IDs and folder metadata are unioned |
| **Zero Network Calls** | Everything processed locally. Your data never leaves your machine |

---

## 📖 Usage Modes

### Default: Auto-Merge

```bash
python3 bw_dedup.py vault.json
```

**Does:** Analyzes, merges, creates outputs all in one go.

**Output:**
- `vault.dedup.json` — Clean export
- `vault.original.YYYYMMDD_HHMMSS.json` — Backup
- `vault.dedup.json.merge-log.json` — Merge log
- `vault.report.html` — Visual report

---

### Review Mode: Step Through Each Merge

```bash
python3 bw_dedup.py vault.json --review
```

**Does:** Interactive mode. You approve each duplicate cluster before merging.

---

### Report Only: Analyze Without Merging

```bash
python3 bw_dedup.py vault.json --report-only
```

**Does:** Generate the HTML report and console summary without writing any files. Perfect for previewing.

---

### Dry Run: Preview Mode

```bash
python3 bw_dedup.py vault.json --dry-run
```

**Does:** Same as `--report-only` but also shows console preview of what would be merged.

---

## 🎛️ All CLI Options

```bash
python3 bw_dedup.py INPUT_FILE [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `-o, --output PATH` | Auto-generated | Output JSON path |
| `-t, --threshold FLOAT` | `0.85` | Similarity threshold (0.0–1.0) |
| `--review` | — | Interactive review mode |
| `--dry-run` | — | Preview without writing |
| `--report-only` | — | Generate report only |
| `--fast` | — | Skip expensive fuzzy matching |
| `--types TEXT` | All | Comma-separated: `1=Login, 2=Note, 3=Card, 4=Identity, 5=SSH` |
| `--no-backup` | — | Skip creating backup |
| `--confidence FLOAT` | `0.0` | Only auto-merge clusters above this confidence |
| `--help` | — | Show help message |

**Examples:**

```bash
# Only analyze logins (type 1)
python3 bw_dedup.py vault.json --types 1

# Only merge high-confidence clusters
python3 bw_dedup.py vault.json --confidence 0.95

# Save output to custom location
python3 bw_dedup.py vault.json -o /path/to/output.json

# Fast mode (skip fuzzy matching)
python3 bw_dedup.py vault.json --fast
```

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

Each cluster receives a score based on match quality:

| Score | Meaning | Action |
|-------|---------|--------|
| **100%** | Exact domain + username + password match | Auto-merge |
| **≥95%** | Very similar items | Auto-merge |
| **85–95%** | Good match | Review recommended |
| **<85%** | Loose match | Review strongly recommended |

You control the threshold with `--confidence`.

---

## 📈 Performance

Small vaults are instant. Larger vaults are still fast.

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
- Batch rename query parsing and matching
- Rename log generation
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

## 📁 Project Structure

```
bitmerger/
├── bw_dedup.py              # Backward-compatible entry point
├── bitmerger/
│   ├── __init__.py
│   ├── __main__.py          # python -m bitmerger
│   ├── core.py              # Engine: models, similarity, merging
│   ├── cli.py               # CLI commands (dedup, batch-rename)
│   ├── gui.py               # PySide6 desktop GUI
│   └── templates/
│       └── report.jinja2    # HTML report template
├── requirements.txt         # Python dependencies
├── .gitignore
├── README.md
├── tests/
│   ├── test_engine.py       # 35 core engine tests
│   └── test_batch_rename.py # 20 batch-rename tests
└── stress_test.py           # Synthetic vault generator
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

### ModuleNotFoundError: No module named 'click'
**Fix:** 
```bash
pip install -r requirements.txt
```

---

## 📦 Dependencies

- **Click** — CLI framework
- **Rich** — Terminal formatting and output
- **Jinja2** — HTML report templating
- **thefuzz** — Fuzzy string matching
- **tldextract** — Domain extraction
- **PySide6** — Cross-platform GUI (Qt for Python)

All specified in `requirements.txt`. Install with:
```bash
pip install -r requirements.txt
```

**GUI only:** If you only need the CLI, you can skip PySide6:
```bash
pip install click rich jinja2 thefuzz tldextract python-Levenshtein
```

---

## 📜 License

MIT License. Use at your own risk.

---

## 🙏 Credits

Built with amazing open-source libraries:
- [Click](https://click.palletsprojects.com/)
- [Rich](https://rich.readthedocs.io/)
- [Jinja2](https://jinja.palletsprojects.com/)
- [thefuzz](https://github.com/seatgeek/thefuzz)
- [tldextract](https://github.com/john-kurkowski/tldextract)

---

<div align="center">

**Nothing is ever deleted. Everything is safely merged.** ✨

</div>
