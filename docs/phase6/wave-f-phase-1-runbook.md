# Wave F Phase 1 Runbook: Context Snapshot Collection

Status: Phase 1.1 implemented

## Purpose

Wave F adds an intelligence layer on top of the Wave A learning spine. Phase 1 starts by storing the market context that surrounded each future lesson, so later phases can answer questions like "when did this signal family work?" instead of only "did this signal family work?"

Phase 1.1 is intentionally small. It creates the schema and minimum viable snapshot builder, but does not attach snapshots to live lessons or backfill historical rows yet.

## Phase 1.1 Scope

Implemented now:

- `lesson_context_snapshot` table in `data/orca_state.db`
- Nullable `candidate_lessons.context_snapshot_id`
- `idx_snapshot_date`, `idx_snapshot_regime`, and `idx_lessons_context`
- `orca/context_snapshot.py`
- Minimum viable snapshot fields:
  - `regime`
  - `regime_confidence`
  - `vix_level`
  - `vix_delta_7d`
  - `sp500_momentum_5d`
  - `sp500_momentum_20d`
  - `nasdaq_momentum_5d`
  - `nasdaq_momentum_20d`
  - `dominant_sectors`
  - `source_event_type`
  - `source_session_id`

Deferred:

- Live lesson hook
- Backfill for the existing Wave A lessons
- Breadth indicators
- Event flags
- Sector rotation vector and divergence score
- Context clustering

## Regime Source Priority

`orca/context_snapshot.py` resolves regime in this order:

1. ORCA backtest report for the same `trading_date`
2. `data/morning_baseline.json` when its `date` matches
3. Heuristic fallback from VIX and 20-day SP500/NASDAQ momentum
4. `NULL` if no useful data exists

`regime_confidence` is best effort. When ORCA provides `confidence_overall`, it is mapped as:

- `낮음` / `low` -> `0.33`
- `보통` / `medium` / `med` -> `0.67`
- `높음` / `high` -> `1.0`

If no confidence source exists, it stays `NULL`.

## Market Data

The historical snapshot builder uses Yahoo Finance through `yfinance` directly because `orca.data.fetch_yahoo_data()` is current-only. It uses the same core market tickers already used elsewhere in ORCA:

- `^VIX`
- `^GSPC`
- `^IXIC`

Dominant sectors are the top positive 5-day returns from this Phase 1.1 ETF set:

- `XLK`: Technology
- `XLV`: Healthcare
- `XLE`: Energy
- `XLF`: Financials
- `XLI`: Industrials
- `XLY`: Consumer Discretionary
- `XLP`: Consumer Staples
- `XLU`: Utilities
- `XLRE`: Real Estate
- `XLB`: Materials
- `XLC`: Communication Services

## Verification SQL

After running `state.init_state_db()`, verify schema:

```sql
SELECT name
FROM sqlite_master
WHERE type='table'
  AND name='lesson_context_snapshot';
```

```sql
PRAGMA table_info(candidate_lessons);
```

Expected: `context_snapshot_id` exists and is nullable.

```sql
SELECT name
FROM sqlite_master
WHERE type='index'
  AND name IN ('idx_snapshot_date', 'idx_snapshot_regime', 'idx_lessons_context');
```

Expected: three rows.

Phase 1.1 does not backfill data, so these counts are expected:

```sql
SELECT COUNT(*) FROM lesson_context_snapshot;
```

Expected immediately after migration: `0`

```sql
SELECT COUNT(*)
FROM candidate_lessons
WHERE context_snapshot_id IS NOT NULL;
```

Expected until Phase 1.2/1.3: `0`

## Manual Smoke Test

Use this only when network access is acceptable:

```powershell
@'
from orca.context_snapshot import get_or_create_context_snapshot

snapshot_id = get_or_create_context_snapshot(
    trading_date="2026-04-24",
    source_event_type="backtest",
    source_session_id="manual_smoke",
)
print(snapshot_id)
'@ | python -
```

If Yahoo Finance is unavailable or rate-limited, the snapshot can still be created with partial `NULL` market metrics.

## Phase 1.2

Add the live hook at the lesson creation layer, not in the Hunter/Scanner alert UI path.

Recommended hook points:

- `orca.state._sync_candidate_probability_lesson()`
- `orca.state.record_candidate_lesson()`
- `orca.state.record_backtest_lesson()`

The hook must be isolated with `try/except`. Snapshot failure must not block candidate, outcome, or lesson writes.

## Phase 1.3

Backfill existing Wave A lessons.

Recommended strategy:

- Read `analysis_date` from backtest lesson payloads.
- Create one shared snapshot per distinct `trading_date` and `source_event_type`.
- Update each lesson's `context_snapshot_id`.
- Cache historical market fetches by ticker/date window to avoid Yahoo Finance rate limits.

The 1260 Wave A lessons should map mostly to about 252 distinct trading-date snapshots.

## Tests

Run:

```powershell
python -m unittest tests.test_context_snapshot
```

Full suite:

```powershell
python -m unittest discover -s tests
```
