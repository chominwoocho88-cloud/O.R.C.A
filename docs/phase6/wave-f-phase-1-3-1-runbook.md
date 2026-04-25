# Wave F Phase 1.3.1 Runbook: Actions Backfill

## Purpose

Wave F Phase 1.3.1 moves the lesson context backfill from the local Windows
environment to GitHub Actions.

The local run can create snapshots, but the user's network path blocks yfinance
with an SSL certificate error. GitHub-hosted runners avoid that ISP/certificate
path and should fetch VIX, index momentum, and sector ETF data normally.

## What This Adds

Phase 1.3.1 adds a manual workflow:

- `.github/workflows/wave_f_backfill.yml`
- `workflow_dispatch` only, no cron
- `dry_run=true` by default
- optional cleanup mode for recovery
- strict verification before committing `data/orca_state.db`
- automatic commit and push only after verification passes

The workflow does not change live ORCA, Hunter, Scanner, or daily automation.

## Inputs

`dry_run`

Default: `true`

When true, the workflow prints the planned backfill but does not write or commit
the database. Run this first.

`limit`

Default: empty

Optional maximum number of distinct trading dates to process. For the final
production run, leave this empty so all 252 dates are processed.

`skip_existing`

Default: `true`

Reuses existing `backtest_backfill` snapshots where possible. This keeps the
workflow idempotent if a previous run partially completed.

`cleanup`

Default: `false`

When true and `dry_run=false`, removes existing `backtest_backfill` snapshots
and unlinks lessons before running the backfill again. Live snapshots are
preserved.

If `cleanup=true` and `dry_run=true`, the workflow logs a warning and does not
modify the DB.

## Recommended Execution

### Step 1: Dry Run

Open GitHub Actions:

`Actions` -> `Wave F Backfill` -> `Run workflow`

Use:

```text
dry_run: true
limit: empty
skip_existing: true
cleanup: false
```

Expected output:

- 1260 backtest lessons discovered
- 252 distinct trading dates planned
- no DB commit

### Step 2: Real Backfill

Run the same workflow again:

```text
dry_run: false
limit: empty
skip_existing: true
cleanup: false
```

Expected flow:

1. Pre-flight status prints current snapshot/link counts.
2. Backfill fetches market data through GitHub Actions.
3. Strict verify checks completeness.
4. SQLite WAL is checkpointed.
5. `data/orca_state.db` is committed and pushed.

Expected commit message:

```text
chore: Wave F Phase 1.3 - Backfill executed via Actions [skip ci]
```

### Step 3: Local Verification

After the workflow commits:

```powershell
cd "C:\Users\skyco\OneDrive\문서\GitHub\O.R.C.A"
git pull origin main
python - <<'PY'
import sqlite3

conn = sqlite3.connect('data/orca_state.db')
print('Snapshots:', conn.execute(
    "SELECT COUNT(*) FROM lesson_context_snapshot "
    "WHERE source_event_type='backtest_backfill'"
).fetchone()[0])
print('Linked lessons:', conn.execute(
    "SELECT COUNT(*) FROM candidate_lessons "
    "WHERE context_snapshot_id IS NOT NULL"
).fetchone()[0])
print('Unlinked backtest lessons:', conn.execute("""
    SELECT COUNT(*)
    FROM candidate_lessons l
    JOIN candidate_registry c ON c.candidate_id = l.candidate_id
    WHERE c.source_event_type='backtest'
      AND l.context_snapshot_id IS NULL
""").fetchone()[0])
print('VIX filled:', conn.execute(
    "SELECT COUNT(*) FROM lesson_context_snapshot "
    "WHERE source_event_type='backtest_backfill' "
    "AND vix_level IS NOT NULL"
).fetchone()[0])
print('Sectors filled:', conn.execute(
    "SELECT COUNT(*) FROM lesson_context_snapshot "
    "WHERE source_event_type='backtest_backfill' "
    "AND dominant_sectors IS NOT NULL "
    "AND dominant_sectors != '' "
    "AND dominant_sectors != '[]'"
).fetchone()[0])
conn.close()
PY
```

Expected:

- `Snapshots: 252`
- `Linked lessons: 1260`
- `Unlinked backtest lessons: 0`
- `VIX filled: 252`
- `Sectors filled: 252`

## Strict Verify Criteria

The workflow calls `verify_backfill_completeness()` before committing.

It requires:

- `backtest_backfill` snapshots >= 252
- linked backtest lessons >= 1260
- unlinked backtest lessons == 0
- `vix_level` filled for every snapshot
- S&P 500 5d and 20d momentum filled for every snapshot
- NASDAQ 5d and 20d momentum filled for every snapshot
- `dominant_sectors` is not empty for every snapshot

If any check fails, the workflow exits with status 1 and does not commit.

## Cleanup Mode

Use cleanup mode when a previous backfill committed incomplete or suspicious
data and you want to regenerate it.

Inputs:

```text
dry_run: false
limit: empty
skip_existing: true
cleanup: true
```

Cleanup does two things:

1. Sets `candidate_lessons.context_snapshot_id = NULL` for lessons linked to
   `backtest_backfill` snapshots.
2. Deletes only `lesson_context_snapshot` rows where
   `source_event_type='backtest_backfill'`.

Live snapshots and future Phase 1.2 data are preserved.

## Rollback

There are two rollback layers.

First, use cleanup mode and rerun the workflow. This is preferred when only
backfill data is bad.

Second, revert the DB commit:

```powershell
git revert <backfill_commit_hash>
git push origin main
```

Use git revert when the committed database itself should be restored exactly to
the previous state.

## Troubleshooting

If dry-run succeeds but the real run fails during yfinance fetch:

- rerun once with the same inputs
- keep `skip_existing=true`
- if repeated, inspect failed dates in the backfill output

If strict verify fails with missing market metrics:

- do not manually commit the DB
- rerun with `cleanup=true` after checking the failed metric counts
- if failures persist on GitHub Actions, reduce the run with `limit` for
  diagnostics, but do not use `limit` for the production commit

If the workflow says there are no DB changes:

- the backfill may already be complete
- run local verification after `git pull`

## Relationship To Other Wave F Phases

Phase 1.1 created the schema and context snapshot module.

Phase 1.3 created the local backfill code.

Phase 1.3.1 runs that backfill in GitHub Actions to avoid local SSL blocking.

Phase 1.2 can follow after the historical lessons are linked. It will attach
snapshots to newly created live lessons.
