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
python analyze.py 2026-01              # Analyze a specific month
python analyze.py 2026-01 --reprocess  # Reprocess all (clears existing)
python analyze.py --stats              # Show stats from audit.db
python analyze.py --sample 10          # Sample 10 random tickets

# Review web app
python review_app.py                   # Starts on http://localhost:5050

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
- **`src/local_scanner.py`** - Scans `YYYY-MM/` folders for PNG files matching pattern `{ticket_number}{variant}.png` (e.g., `583239a.png`). The `tickets` symlink points to the actual ticket images.
- **`src/ticket_analyzer.py`** - Core analysis engine. Extracts tech names from a specific image region (~78-82% down, left half) using Tesseract OCR (`--psm 7`). Detects signatures via ink density in a separate region (~82-94% down, left 45%). Returns `TicketAnalysis` dataclass.
- **`src/database.py`** - SQLite wrapper (`audit.db`). `AuditRecord` dataclass. Uses `INSERT OR REPLACE` keyed on `file_path`. Has reporting queries for stats by technician, month, and cross-tabulated.
- **`src/tech_names.py`** - Name normalization. `KNOWN_TECHS` list + `OCR_CORRECTIONS` dict for manual fixes + fuzzy matching (65% threshold via `SequenceMatcher`).
- **`review_app.py`** - Flask app (port 5050) with inline HTML templates. Two modes: detection review (balanced random sample, correct/incorrect voting) and signature gallery by technician (fraud detection). Signature region constants (`SIG_TOP`, `SIG_BOTTOM`, etc.) must stay in sync with `ticket_analyzer.py`.

### Google Cloud pipeline (original design, in `src/`)
`cli.py` → `AuditService` → `DriveClient` + `VisionAnalyzer` → `SheetsWriter`

- Requires a Google service account (`service_account.json`) with Drive, Vision, and Sheets APIs.
- `config.py` uses `pydantic-settings` to load `.env` configuration.
- Not actively used for local analysis; the local pipeline replaced it.

## Key Detection Parameters

Signature detection thresholds in `src/ticket_analyzer.py` (`_detect_signature_universal`):
- Dark pixel threshold: 170 (grayscale)
- Ink density < 2%: no signature
- Ink density 2-10%: signature detected (confidence 0.72-0.88)
- Ink density > 12%: signature detected but lower confidence (0.55)

Image regions (as percentage of image dimensions):
- Tech name: y=78-82%, x=0-50%
- Signature: y=82-94%, x=0-45%

These same region percentages are duplicated in `review_app.py` as `SIG_LEFT/RIGHT/TOP/BOTTOM` constants.

## Data Layout

- Ticket images: `tickets/` symlink → Google Drive folder containing `YYYY-MM/*.png`
- Local months also appear as `2026-02/` directories in the project root (extracted from zip exports)
- Database: `audit.db` in project root
- Credentials: `.env` (never committed), `service_account.json` (gitignored)
