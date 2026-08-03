# Valencia_Waitinglist

Track your Valencia Marathon waiting-list position once per day, keep the full history, and estimate when you may be offered a bib.

## What this project does

- Fetches your current waitlist position from your private tracking link
- Stores one snapshot per day in `data/waitlist_history.csv`
- Generates:
  - `reports/waitlist_report.md` (current position + trend + estimated bib date)
  - `reports/position_over_time.svg` (position-over-time chart image)

## Quick start

1. Set your tracking URL in an environment variable:

```bash
export TRACKING_URL='https://...your-private-link...'
```

2. Log today's position:

```bash
python tracker.py log --marathon-date 2026-12-07
```

3. Rebuild report from existing history only:

```bash
python tracker.py report --marathon-date 2026-12-07
```

## Daily automation (GitHub Actions)

A workflow is included at `.github/workflows/waitlist-tracker.yml`.

- Runs once per day (07:15 UTC)
- Reads `TRACKING_URL` from repository secret
- Updates CSV history + report files
- Commits the updated files automatically

### One-time setup

1. In GitHub repo settings, add secret: `TRACKING_URL`
2. Keep workflow enabled

## Seed data included

Based on your note, initial history includes:

- 2026-01-04: 33000
- 2026-08-03: 13000

These values are in `data/waitlist_history.csv` and can be replaced anytime.
