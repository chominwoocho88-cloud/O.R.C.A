# JACKAL Quality Runbook

This runbook is for system quality checks only. It is not investment advice and does not trigger live LLM calls, paid API calls, or trading/order actions.

## Check Shadow And Recommendation Rows

Run the current quality audit in dry-run mode:

```powershell
python scripts\audit_quality.py --dry-run
```

For a faster post-session intake check:

```powershell
python scripts\check_jackal_operational_intake.py
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
- `waiting_for_operational_samples`: no shadow/recommendation operational rows have arrived yet. This is not a failure.
- `waiting_for_outcomes`: rows exist, but outcome evidence is not mature enough for accuracy backfill.
- `ready_for_backfill_dry_run`: resolved shadow or checked recommendation evidence exists; run dry-run backfill first.

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

## Phase 7 Post-Run Procedure

After a scheduled JACKAL session:

```powershell
python scripts\check_jackal_operational_intake.py --output-json "$env:TEMP\jackal_intake.json" --output-md "$env:TEMP\jackal_intake.md"
```

If the status is `waiting_for_operational_samples`, wait for scanner/recommendation paths to produce real rows. Do not backfill.

If the status is `waiting_for_outcomes`, wait for `JackalEvolution` to resolve shadow or recommendation outcomes. Do not create accuracy rows.

If the status is `ready_for_backfill_dry_run`, run:

```powershell
python scripts\backfill_jackal_shadow.py --dry-run
python scripts\backfill_jackal_accuracy.py --dry-run --include-recommendations
```

Only when the relevant dry-run returns `planned`, run the non-dry command. By default both backfill scripts create a timestamped copy of `data/jackal_state.db` next to the DB before writing:

```powershell
python scripts\backfill_jackal_shadow.py
python scripts\backfill_jackal_accuracy.py --include-recommendations
```

After a non-dry run, re-run:

```powershell
python scripts\check_jackal_operational_intake.py
python scripts\audit_quality.py --dry-run
```

Confirm that row counts, `latest_source`, and `missing_reasons` match the expected evidence. If they do not, restore from the backup file before attempting another write.

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
- Requirements drift should normally be `pass`. Current dependency policy uses tested compatibility ranges in `requirements.txt`; intentional warnings should be documented before release hardening.

## CI Quality Smoke

The lightweight quality workflow runs compile checks, JSON parse, SQLite integrity when DB files exist, requirements drift, operational intake, and `audit_quality.py --dry-run`. It uploads JSON/Markdown artifacts for every run.

Full unittest and full audit remain local/manual checks:

```powershell
python -m unittest discover -s tests
python scripts\audit_quality.py --output-json "$env:TEMP\orca_audit_full.json" --output-md "$env:TEMP\orca_audit_full.md"
```
