# Wave F Phase 1.2 Runbook: Live Hook for New Lessons

## Purpose

Wave F Phase 1.2 links every newly recorded lesson to a market context snapshot.

Phase 1.1 added the schema and snapshot module. Phase 1.3 backfilled existing
backtest lessons. Phase 1.2 closes the loop for future lessons by attaching a
`context_snapshot_id` at lesson insert time.

## What Changed

Three lesson write paths now attempt to create or reuse a context snapshot:

- `_sync_candidate_probability_lesson()` for review/outcome-derived lessons.
- `record_candidate_lesson()` for general live/manual lessons.
- `record_backtest_lesson()` for new backtest materialization lessons.

The snapshot hook is isolated. If context creation fails, the lesson insert still
continues with `context_snapshot_id = NULL`.

## Hook Flow

1. Read candidate metadata from `candidate_registry`.
2. Determine the trading date.
3. Map candidate source provenance into snapshot provenance.
4. Call `get_or_create_context_snapshot()`.
5. Insert the lesson with `context_snapshot_id`.

The trading date fallback order is:

- `candidate_registry.analysis_date`
- `lesson.analysis_date`
- `lesson_timestamp[:10]`
- current KST date

The source mapping is:

- `hunt`, `scan`, `shadow` -> `live`
- `backtest` -> `backtest`
- anything else -> original source, or `unknown`

Backfilled historical context remains separate under `source_event_type =
'backtest_backfill'`.

## Failure Isolation

Snapshot failures are intentionally non-fatal.

On failure:

- The lesson is still inserted.
- `candidate_lessons.context_snapshot_id` remains `NULL`.
- `_record_health_event("context_snapshot_failed", ...)` records diagnostics.
- A warning is written to stderr.

This keeps Hunter, Scanner, backtest materialization, and probability learning
from being blocked by a temporary market-data provider issue.

## Expected Behavior

For a new live lesson:

```text
candidate_registry(source_event_type='hunt', analysis_date='2026-04-20')
record_candidate_lesson(...)
-> lesson_context_snapshot(trading_date='2026-04-20', source_event_type='live')
-> candidate_lessons.context_snapshot_id = ctx_...
```

For a new backtest lesson:

```text
candidate_registry(source_event_type='backtest', analysis_date='2026-04-20')
record_backtest_lesson(...)
-> lesson_context_snapshot(trading_date='2026-04-20', source_event_type='backtest')
-> candidate_lessons.context_snapshot_id = ctx_...
```

For old or deliberately unlinked lessons:

```text
candidate_lessons.context_snapshot_id IS NULL
```

## Verification

After a run that creates new lessons:

```sql
SELECT source_event_type, COUNT(*)
  FROM lesson_context_snapshot
 GROUP BY source_event_type
 ORDER BY source_event_type;

SELECT COUNT(*)
  FROM candidate_lessons
 WHERE context_snapshot_id IS NOT NULL;

SELECT COUNT(*)
  FROM candidate_lessons
 WHERE context_snapshot_id IS NULL;
```

For Python-level health events during tests or one process:

```python
from orca import state
print(state.drain_health_events())
```

## Performance Notes

The first lesson for a trading date can trigger market-data fetches. Later
lessons for the same `trading_date + source_event_type` reuse the same snapshot.

This means:

- A live day usually pays the context fetch cost once.
- A backtest run pays it once per distinct trading date.
- If fetch fails, the hook records diagnostics and leaves the lesson unlinked.

## Backward Compatibility

`record_candidate_lesson()` and `record_backtest_lesson()` remain backward
compatible. New optional parameters were added:

- `context_snapshot_id`: explicitly attach an existing snapshot.
- `auto_context_snapshot`: default `True`; tests and special maintenance code
  can set it to `False` to intentionally create unlinked lessons.

## Relation To Later Phases

Phase 2 clustering can now consume both:

- historical backfilled lessons (`backtest_backfill`)
- newly created live/backtest lessons (`live`, `backtest`)

Lessons with `context_snapshot_id = NULL` remain valid but will be skipped or
handled as unknown-context samples by the clustering layer.
