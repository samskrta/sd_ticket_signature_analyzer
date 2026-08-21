# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Paper Please is a service ticket signature auditor for appliance repair companies. It scans PNG images of service tickets, extracts technician names via OCR, detects handwritten signatures via ink density analysis, and reports signature compliance rates per technician.

## Commands

```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
brew install tesseract  # macOS - required for local OCR

# Analyze tickets (primary workflow)
python analyze.py 2026-01              # Analyze a specific month (from dataIn/2026-01/)
python analyze.py 2026-01 --reprocess  # Re-OCR + re-detect; INSERT OR REPLACE wipes sd_tech_code/customer — run resolve_techs.py after (run_batch.sh does)
python analyze.py --stats              # Show stats from audit.db
python analyze.py --sample 10          # Sample 10 random tickets
python resolve_techs.py                # Assign the authoritative tech from ServiceDesk (run after analyze)
./run_batch.sh                         # analyze every month under dataIn/ then resolve techs

# Review web app
python review_app.py                   # http://localhost:5050 — /stats (compliance charts), /techs (galleries), /customers (repeat customers), / (detection review)

# CLI (Google Cloud mode - requires service account)
python cli.py audit --from 2026-01-01
python cli.py report summary
python cli.py stats --all

# Scheduler daemon
python scheduler.py
```

## Architecture

The system has two independent processing pipelines:

### Local pipeline (primary, actively used)
`analyze.py` → `LocalScanner` → `TicketAnalyzer` → `AuditDatabase` (SQLite)

- **`analyze.py`** - Entry point for local analysis. Uses argparse. Reads tickets from the filesystem, runs OCR + signature detection, stores results in `audit.db`.
- **`src/local_scanner.py`** - Scans `YYYY-MM/` folders for PNG files matching pattern `{ticket_number}{variant}.png` (e.g., `583239a.png`).
- **`src/ticket_analyzer.py`** - Core analysis engine. Extracts tech names from a specific image region (~78-82% down, left half) using Tesseract OCR (`--psm 7`). Detects signatures via masked ink density (see Key Detection Parameters). Returns `TicketAnalysis` dataclass.
- **`src/database.py`** - SQLite wrapper (`audit.db`). `AuditRecord` dataclass. Uses `INSERT OR REPLACE` keyed on `file_path`. Has reporting queries for stats by technician, month, and cross-tabulated.
- **`resolve_techs.py`** - Sets `technician_name` / `sd_tech_code` and `customer` ("NAME · STREET", location else payer) from ServiceDesk (Supabase mirror, `SD_DATABASE_URL` in `.env`). Parses `jobs.work_history` lines like `SZ there ... [Tckts\605070a.png]` to map each ticket *variant* to the tech who emailed it; falls back to appointment order. The OCR'd name is preserved in `ocr_name`. This is the authoritative identity — OCR alone mis-attributed ~9% and missed ~12% (two Dereks, two Austins, Sal Z → Ali Z).
- **`src/tech_names.py`** - `TECH_CODES` (SD 2-letter code → "First L" display name — add new hires here) + OCR fallback: `KNOWN_TECHS` list, `OCR_CORRECTIONS` dict, fuzzy matching (65% threshold via `SequenceMatcher`).
- **`review_app.py`** - Flask app (port 5050) with inline HTML templates. Routes: `/` detection review (vote correct/incorrect), `/techs` galleries, `/stats` compliance charts (latest-month techs only; `NO_SIGNATURE_CODES` excluded), `/customers` repeat-customer comparison. Signature region constants (`SIG_TOP`, `SIG_BOTTOM`, etc.) must stay in sync with `ticket_analyzer.py`.

### Google Cloud pipeline (original design, in `src/`)
`cli.py` → `AuditService` → `DriveClient` + `VisionAnalyzer` → `SheetsWriter`

- Requires a Google service account (`service_account.json`) with Drive, Vision, and Sheets APIs.
- `config.py` uses `pydantic-settings` to load `.env` configuration.
- Not actively used for local analysis; the local pipeline replaced it.

## Key Detection Parameters

Signature detection in `src/ticket_analyzer.py` (`_detect_signature_universal`), constants at the top of the module:
- Region: y=77–94%, x=1–68% of the page (the form's signature area: "by [Tech]" rule at 78.5–79.1%, baseline at 93.5–94.3%, "Total Ticket" box from ~70% width). Horizontal form rules (rows >50% dark) and the printed "by Name Role" block (y=78.5–81.5%, x<30%) are masked before measuring ink.
- Dark pixel threshold: 170 (grayscale)
- Ink density < 0.6%: no signature; 0.6–6%: signature (confidence 0.88 in 1.2–4%, else 0.72); > 6%: signature, confidence 0.55
- Calibrated 2026-08-21 on 2,000 tickets (unsigned p95 0.68%, signed p5 1.19%). The previous 82–94% × 0–45% region missed ~1.6% of tickets whose signature rode above the name line.
- Tech name OCR region: y=78–82%, x=0–50% (OCR is only a fallback — `resolve_techs.py` is authoritative).

`review_app.py` duplicates the display crop as `SIG_LEFT/RIGHT/TOP/BOTTOM` — keep them in sync.

## Data Layout

- Ticket images: `dataIn/YYYY-MM/*.png` (gitignored; drop zip exports here and extract so each month is a direct child of `dataIn/`). Override with env `TICKETS_ROOT`.
- Database: `audit.db` in project root; `file_path` is relative to the project dir (e.g. `dataIn/2026-03/590897a.png`)
- Months can be analyzed in parallel (one `analyze.py` per month) — each month writes once in a single transaction, no SQLite contention.
- Credentials: `.env` (never committed), `service_account.json` (gitignored)
