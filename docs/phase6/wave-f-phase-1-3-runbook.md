# Wave F Phase 1.3 Runbook: Backfill Lesson Context

Status: implemented

## Purpose

Phase 1.3 links the existing Wave A backtest lessons to historical market context snapshots.

The current Wave A spine has:

- `1260` backtest lessons
- `252` distinct trading dates
- `5` lessons per trading date

Phase 1.3 creates one shared snapshot per trading date and writes that `snapshot_id` into each related lesson's nullable `context_snapshot_id`.

## Why Phase 1.3 Before Phase 1.2

Backfill is a controlled, one-time operation. It does not touch Hunter, Scanner, ORCA daily, or workflow hot paths. Once historical snapshots are validated, Phase 1.2 can attach the same mechanism to live lesson creation with much less uncertainty.

## What The Backfill Does

For each distinct backtest lesson date:

1. Read `analysis_date` and `regime` from `candidate_lessons.lesson_json`.
2. Reuse an existing `backtest_backfill` snapshot if present.
3. Otherwise compute market metrics from cached historical Yahoo Finance data.
4. Insert a `lesson_context_snapshot` row with `source_event_type='backtest_backfill'`.
5. Update all lessons for that date with the shared `context_snapshot_id`.

The backfill unit is a trading date, not an individual lesson.

## Market Data Strategy

The backfill avoids per-date Yahoo Finance calls.

It fetches this ticker set once for the full date range plus a 90-day buffer:

- `^VIX`
- `^GSPC`
- `^IXIC`
- `XLK`, `XLV`, `XLE`, `XLF`, `XLI`, `XLY`, `XLP`, `XLU`, `XLRE`, `XLB`, `XLC`

The primary path uses `yf.download()` batch mode. If batch mode fails, the code falls back to per-ticker download with a short retry delay. Per-date metric calculation then uses only the in-memory cache.

## Safety

The script is designed to be idempotent.

- `--dry-run` performs no DB writes and no network calls.
- Existing linked lessons are skipped by default.
- Existing `backtest_backfill` snapshots are reused.
- A failed date is recorded in the summary and does not block other dates.
- The script creates a timestamped DB backup before a real run unless `--no-backup` is passed.

## Commands

Run from repo root:

```powershell
cd "C:\Users\skyco\OneDrive\문서\GitHub\O.R.C.A"
```

Dry-run first:

```powershell
python scripts/backfill_lesson_context.py --dry-run --verbose
```

Expected dry-run shape:

```text
Lessons total: 1260
Lessons processed: 1260
Lessons skipped: 0
Snapshots created: 252
Snapshots reused: 0
Dates total: 252
Dates processed: 252
```

Actual run:

```powershell
python scripts/backfill_lesson_context.py --verbose
```

Optional smaller run:

```powershell
python scripts/backfill_lesson_context.py --limit 10 --verbose
```

## Verification SQL

```sql
SELECT COUNT(*)
FROM lesson_context_snapshot
WHERE source_event_type = 'backtest_backfill';
```

Expected after full run: about `252`

```sql
SELECT COUNT(*)
FROM candidate_lessons
WHERE context_snapshot_id IS NOT NULL;
```

Expected after full run: `1260`

```sql
SELECT COUNT(*)
FROM candidate_lessons
WHERE context_snapshot_id IS NULL;
```

Expected after full run: `0`

```sql
SELECT s.trading_date, COUNT(l.lesson_id)
FROM lesson_context_snapshot s
JOIN candidate_lessons l
  ON l.context_snapshot_id = s.snapshot_id
WHERE s.source_event_type = 'backtest_backfill'
GROUP BY s.trading_date
ORDER BY s.trading_date
LIMIT 10;
```

Expected: `5` lessons per backfilled trading date.

## Troubleshooting

If the script exits with failed dates:

- Review the printed date and reason.
- Re-run the same command. Already linked dates will be skipped by default.
- If Yahoo Finance is rate-limited, wait and re-run with the same command.

If the output shows fewer than 252 snapshots:

- Check whether `--limit` was used.
- Check whether some snapshots already existed and were reused.
- Query failed dates in the script output.

If the DB needs rollback:

1. Stop running backfill commands.
2. Find the backup printed by the script, for example `data/orca_state.db.backup-pre-backfill-<timestamp>`.
3. Restore it over `data/orca_state.db`.
4. Re-run verification SQL.

## Phase 1.2 Next

Phase 1.2 should add the live hook at lesson creation time:

- `orca.state._sync_candidate_probability_lesson()`
- `orca.state.record_candidate_lesson()`
- `orca.state.record_backtest_lesson()`

Snapshot creation must be isolated with `try/except` so a context fetch failure never blocks candidate, outcome, or lesson writes.

## Tests

Backfill-specific tests:

```powershell
python -m unittest tests.test_backfill_lesson_context
```

Full suite:

```powershell
python -m unittest discover -s tests
```
