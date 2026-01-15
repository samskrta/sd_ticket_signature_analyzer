# Paper Please - Service Ticket Signature Auditor

Automated auditing of appliance repair service tickets for signature compliance. Uses local OCR to extract technician names, detects signatures via image analysis, and generates reports to track signature rates by technician.

## Features

- **Local OCR** - Uses Tesseract for technician name extraction (no cloud APIs required)
- **Signature Detection** - Analyzes ink density in signature regions
- **Name Normalization** - Fuzzy matching corrects OCR typos to known technician list
- **Interactive Review** - Web UI for spot-checking detection accuracy
- **Fraud Detection** - Gallery view to compare signatures by technician
- **Reports** - Per-technician and per-month signature compliance stats

## Quick Start

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install Tesseract OCR (macOS)
brew install tesseract

# 4. Create symlink to your tickets folder
ln -s /path/to/your/tickets/folder tickets

# 5. Run analysis
python analyze.py 2026-01
```

## Folder Structure

Tickets should be organized by month:

```
tickets/
└── Tckts/
    ├── 2026-01/
    │   ├── 583239a.png
    │   ├── 583239b.png
    │   └── ...
    ├── 2025-12/
    └── ...
```

## Usage

### Analyze Tickets

```bash
# Analyze specific month(s)
python analyze.py 2026-01

# Analyze multiple months
python analyze.py 2026-01 2025-12

# Reprocess all tickets (clears database)
python analyze.py 2026-01 --reprocess

# Show statistics only
python analyze.py --stats
```

### Review Detection Accuracy

```bash
# Start the review web app
python review_app.py

# Open http://localhost:5050
# - Review random sample of tickets
# - Mark detections as correct/incorrect
# - Track accuracy in real-time
```

### Signature Gallery (Fraud Detection)

Visit `http://localhost:5050/techs` to:

1. See all technicians with signature counts
2. Click a technician to view all their collected signatures
3. Compare signatures visually to identify potential fraud patterns

## Customization

### Adding New Technicians

Edit `src/tech_names.py`:

```python
KNOWN_TECHS = [
    "Ali Z",
    "Anthony B",
    # Add new technicians here
]
```

### Fixing OCR Errors

Add corrections for common OCR mistakes:

```python
OCR_CORRECTIONS = {
    "Dgrtey B": "Darren B",  # Common misreading
    "Koby A": "Koby H",      # Wrong letter
}
```

### Adjusting Detection Regions

In `src/ticket_analyzer.py`, modify these values:

```python
# Technician name region (percentage of image height)
tech_region = img.crop((0, int(height * 0.78), int(width * 0.50), int(height * 0.82)))

# Signature region
sig_top = int(height * 0.82)
sig_bottom = int(height * 0.94)
```

## Output

Results are stored in `audit.db` (SQLite). View with:

```bash
# Quick stats
python analyze.py --stats

# Or query directly
sqlite3 audit.db "SELECT technician_name, COUNT(*) FROM audit_records GROUP BY technician_name"
```

## Sample Output

```
          Signature Rates by Technician           
┏━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━━━┳━━━━━━━━┓
┃ Technician ┃ Total ┃ Signed ┃ Missing ┃   Rate ┃
┡━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━━━╇━━━━━━━━┩
│ Travis M   │    74 │      0 │      74 │    N/A │
│ Shannon G  │    81 │      7 │      74 │   8.6% │
│ Kelvin B   │    55 │     53 │       2 │  96.4% │
└────────────┴───────┴────────┴─────────┴────────┘
```

## Requirements

- Python 3.10+
- Tesseract OCR
- ~50MB disk space for dependencies

## License

Internal use only.
