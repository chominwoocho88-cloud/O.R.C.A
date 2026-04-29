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

## GitHub Actions Node 20 Warning Response

Use the Tracker and Quality upgrade as the reference pattern for Node.js 20 deprecation warnings:

1. Classify each workflow before changing action versions.
2. Upgrade low-risk read-only/test/dashboard workflows first.
3. Upgrade medium-risk artifact-only or artifact handoff workflows after locking artifact names and paths in `tests/test_workflow_contracts.py`.
4. Leave DB/state commit workflows for a separate session with per-workflow rollback and push-conflict validation.
5. After each batch, run the local contract tests and the basic validation commands from this runbook before starting GitHub Actions verification.

Current risk split:

- Low risk: `quality.yml`, `pages_dashboard.yml`. These are read-only/test/dashboard deploy flows and do not commit repository state.
- Medium risk: `orca_backtest.yml`, `policy_eval.yml`, `policy_promote.yml`. These use artifacts for research DB/report handoff but do not commit or push.
- High risk: `db_vacuum.yml`, `jackal_backtest_learning.yml`, `jackal_scanner.yml`, `jackal_tracker.yml`, `orca_daily.yml`, `orca_jackal.yml`, `orca_reset.yml`, `wave_f_archive.yml`, `wave_f_backfill.yml`, `wave_f_clustering.yml`. These can write DB/JSON state or push commits. `jackal_tracker.yml` has already been upgraded and verified, but the remaining high-risk workflows should be handled individually.

Low/medium manual verification:

- `ORCA Dashboard Pages`: run `workflow_dispatch` with no inputs. Confirm there are no Node.js 20 deprecation warnings from `checkout` or `setup-python`, the dashboard build succeeds, the Pages artifact uploads, and `Deploy to GitHub Pages` returns the page URL.
- `ORCA Backtest`: run `workflow_dispatch` with `months=13`, `walk_forward=true`, `expected_min_candidates=1000`, `expected_min_lessons=1000`, `expected_min_orca_sessions=1`, and `expected_min_jackal_sessions=1` unless a stricter validation target is intended. Confirm the `research-state-${{ github.run_id }}` artifact contains only `data/orca_state.db`, then confirm the reusable `Policy Eval` and `Policy Promote` jobs receive the expected artifact names.
- `Policy Eval`: verify primarily through the `ORCA Backtest` reusable call so the artifact is downloaded from the same workflow run. For direct `workflow_dispatch`, leave `artifact_name` empty unless the artifact exists in that same run context.
- `Policy Promote`: verify primarily through the `Policy Eval` output in the `ORCA Backtest` chain. For direct `workflow_dispatch`, leave `artifact_name` empty unless the policy-eval artifact exists in that same run context.

High-risk follow-up plan:

- Upgrade one DB/state commit workflow at a time.
- Before each change, inspect `permissions`, checkout credential usage, `git pull --rebase`/push retry logic, DB checkpoint steps, and exact `git add` paths.
- Prefer a dry-run or no-op dispatch first when the workflow supports it.
- Confirm the runner version is at least `2.327.1` before relying on Node.js 24 actions on self-hosted runners.
- After GitHub verification, inspect logs for Node warnings, checkout credential persistence behavior, state checkpoint output, commit/no-op behavior, and push retry behavior.

## JACKAL Tracker Run Interpretation

Tracker runs write three quality artifacts after each run:

- `requirements_drift.json` / `.md`
- `jackal_operational_intake.json` / `.md`
- `orca_audit_smoke.json` / `.md`

Use the Actions artifact named `jackal-tracker-quality` to inspect intake and audit state after a Tracker run.

Run log interpretation:

- `Dry-run persistence skipped` with `TRACKER_WILL_SAVE_RESULTS=false`: normal. The run used `dry_run=true`, so state persistence was intentionally skipped.
- `Save Tracker results` success plus `no tracker state changes to commit`: normal when Tracker ran but did not resolve new outcomes or change state files.
- `Save Tracker results` success plus `Commit created` and `Push succeeded`: Tracker persisted outcome/state changes.
- `Save Tracker results` failure: inspect `git status --short`, staged diff output, and push/rebase messages in the step log.

The `Resolve Tracker inputs` step logs `event_name`, raw and normalized `all_entries`, `dry_run`, `notify`, final `TRACKER_ARGS`, and `TRACKER_WILL_SAVE_RESULTS`. This is the first place to check when a workflow_dispatch run behaves differently than expected.
