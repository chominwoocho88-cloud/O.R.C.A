# JACKAL Quality Runbook

This runbook is for system quality checks only. It is not investment advice and does not trigger live LLM calls, paid API calls, or trading/order actions.

## Check Shadow And Recommendation Rows

Run the current quality audit in dry-run mode:

```powershell
python scripts\audit_quality.py --dry-run
```

Key fields:

- `jackal_shadow_state.signal_rows`: scanner quality-gate skip signals stored in SQLite.
- `jackal_shadow_state.batch_rows`: resolved shadow outcome batches available for rolling rates.
- `jackal_recommendation_accuracy.recommendation_rows`: ARIA extra recommendation rows stored by JACKAL scanner.
- `jackal_recommendation_accuracy.checked_rows`: recommendation rows that have outcome evidence.
- `missing_shadow_signals`: scanner has not produced/persisted quality-skip shadow rows.
- `missing_resolved_shadow_outcomes`: shadow rows exist, but no resolved outcome can support accuracy.
- `missing_recommendation_samples`: no recommendation rows exist.
- `missing_recommendation_outcomes`: recommendation rows exist, but no checked outcomes exist.

## Backfill Dry Runs

Shadow batches:

```powershell
python scripts\backfill_jackal_shadow.py --dry-run
```

Recommendation accuracy projection:

```powershell
python scripts\backfill_jackal_accuracy.py --dry-run --include-recommendations
```

A `planned` result means source evidence exists and a non-dry-run backfill can create rows. A `skipped` result means the script found no valid evidence and should not fabricate accuracy rows.

## Full Audit

```powershell
python scripts\audit_quality.py --output-json "$env:TEMP\orca_audit_full.json" --output-md "$env:TEMP\orca_audit_full.md"
```

The full audit runs compile checks, unit tests, `pip check`, JSON parsing, SQLite integrity, research report, research gate, and policy promotion.

## Gate Warning Interpretation

- `jackal_latest_raw_evaluable` with `incremental_no_new_data` is a normal no-op if the latest evaluable backtest is fresh.
- `jackal_shadow_rolling_10_batch_count` means shadow outcomes are not mature enough for a rolling quality signal.
- `jackal_recommendation_projection_rows_available` with `missing_recommendation_outcomes` means recommendations are being recorded but are not yet outcome-checked.
- `market_provider_failure_rate` means market data provider failures may be contaminating quality evidence.
- Requirements drift in audit is advisory by default; it should be resolved before release hardening but does not fail the smoke gate.
