# Handoff — 2026-08-21

## State
Project resurrected. 15,633 tickets (2026-01→08) in audit.db; tech identity from ServiceDesk
(99.97%), detector region fixed and recalibrated, review app has /stats and /customers.
Re-detection batch with the new region was launched at end of session — verify it completed
(`python analyze.py --stats`; counts per month must match `ls dataIn/<month>/*.png | wc -l`).

## Next up
- Confirm the re-detection landed and resolve_techs ran after it (technician_name should be
  SD names, not OCR; `select count(*) from audit_records where sd_tech_code is null` ≈ 4).
- Eyeball /customers "Different techs" tab (143 customers) — the only fraud check with teeth.
- Near-zero collectors are real, not detector noise: Derek F (DR), Derek I (DI), Travis M, Mike F,
  Shannon G. Ali Z drifted 67% → 0% Feb→Jul; Chuck D 94% → 50%.
- New months: drop zip into dataIn/, extract so YYYY-MM is a direct child, `./run_batch.sh`.

## Standing threads
- [carried 1×, since 2026-08-21] DK (Darrin S) and TB (Tyke B) aren't in rossware-sync
  tech_commission.json; names taken from ticket text — confirm with Todd.
- [carried 1×, since 2026-08-21] 2026-01 rows point at images no longer on disk; stats work,
  galleries/customers skip them. Re-export Jan if ever needed.

## Decisions deferred
- [carried 1×] Track audit.db in git? — commit (~5 MB, sole record of Jan) vs gitignore (regenerable 02–08).

## Dead ends (fraud detection) — don't repeat
- Pixel-similarity clustering within tech: no tech above cross-tech baseline.
- "Trivial mark" via PCA straightness: flags wide genuine signatures; useless.
- Email-time minus visit-end: median 3 min, p90 6; signature rate independent of gap per tech.
- OCR name-region tuning: wider band lets signature ink corrupt text; use SD, not OCR.

## Resolved
- 2026-08-21: dead tickets/ symlink, broken venv, missing requirements, OCR mis-attribution.
