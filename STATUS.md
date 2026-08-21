# Project Status — Paper Please

_Last updated: 2026-08-21 (project resurrected after ~6 months idle)_

## Where things stand

- **Pipeline works locally**: `analyze.py`, `review_app.py`, OCR via tesseract 5.5.2, Python 3.14 venv.
- **audit.db** has 1,591 tickets analyzed: 2026-01 (1,121) and 2026-02 (470). Overall signature rate 54.8%.
- **Data source is now `dataIn/YYYY-MM/*.png`** (gitignored). The old `tickets/` Google Drive symlink was dead and
  has been removed. Override the root with env `TICKETS_ROOT`. Months on disk: 2026-02 … 2026-08 (~14.5k PNGs).
  Note: `2026-03.zip` extracted as a wrapper folder holding all six months — flattened 2026-08-21.
- `audit.db` stores `file_path` relative to the project dir. 2026-01 rows still point at the old absolute
  `tickets/Tckts/...` path (images not on disk) — stats work, but the review app can't show that month's images.
- Review app `/stats`: % signed per tech (ranked bars) + tech × month heatmap, with a month-range filter. Techs with no tickets in the latest month are hidden by default (`?all=1` shows them). Remote-only techs (`NO_SIGNATURE_CODES` in tech_names.py: DK/Darrin S) are always excluded.
- Review app `/customers`: repeat customers' signatures side by side (cross-tech first) — the one fraud check with
  real discriminating power. Automated passes (look-alike clustering, trivial-mark rate, email-vs-visit-end timing)
  found no tech-level signal; see session notes 2026-08-21. The audit's real finding is non-collection, not forgery.
- Review app takes `?month=YYYY-MM` (defaults to latest month in DB); nav links carry it through.
- `run_batch.sh` — analyzes every month under `dataIn/` that has unprocessed tickets; safe to re-run.
  Batch over 2026-03..08 launched 2026-08-21 (~0.23 s/ticket ≈ 55 min).

## Fixed this session (2026-08-21)

- **Tech identity now comes from ServiceDesk, not OCR.** `resolve_techs.py` maps each ticket image to the tech
  named in SD `work_history` (99.97% resolved). Added `sd_tech_code` + `ocr_name` columns. Findings: OCR was wrong
  on 1,378 tickets and blank on 1,826 — "Derek F" was two people (DR Frenzel + DI Irvin), "Austin L" was two
  (AR Rutenschroer + RL Loncke), Sal Z's tickets were filed under Ali Z, and Addy N / Owen L / Tyke B were missing.
- Batch of 2026-03..08 (14,042 tickets) OCR'd in parallel, counts verified against disk.

- Rebuilt `venv/` (old one pointed at a Homebrew Python 3.14.0 that was upgraded; pip refused with PEP 668).
- Added `pytesseract` and `flask` to `requirements.txt` — they were never listed, only installed by hand.
- Verified: `analyze.py --stats`, single-ticket OCR, review app routes `/`, `/techs`, `/image/...` all 200.

## Known issues / open decisions

1. **Ticket source**: currently zip exports dropped into `dataIn/`. Fine for now; automate later if needed.
2. The review app has no month picker UI yet — only the `?month=` query string.
3. **Near-zero signature techs** (Darrin S/DK 0%, Derek F/DR 0.5%, Derek I/DI 0.7%, Travis M 1.6%) — identity is
   now confirmed from SD, so this is either real non-signing or a layout the detector misses. Eyeball in
   `/techs/Derek%20F?month=2026-07` before reporting.
4. `DK` (Darrin S) and `TB` (Tyke B) aren't in rossware-sync's `tech_commission.json` — names taken from ticket text.
5. `audit.db` is untracked — decide whether to commit it (it's the only record of the 2026-01 analysis) or gitignore.
   Zips and `dataIn/` are gitignored now.

## Commands

```bash
source venv/bin/activate
python analyze.py --stats
python analyze.py 2026-03          # scan dataIn/2026-03 (skips already-processed)
./run_batch.sh                     # scan every month under dataIn/
python review_app.py               # http://localhost:5050
```
