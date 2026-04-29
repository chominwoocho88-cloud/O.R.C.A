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
- High risk: `db_vacuum.yml`, `jackal_backtest_learning.yml`, `jackal_scanner.yml`, `jackal_tracker.yml`, `orca_daily.yml`, `orca_jackal.yml`, `orca_reset.yml`, `wave_f_archive.yml`, `wave_f_backfill.yml`, `wave_f_clustering.yml`. These can write DB/JSON state or push commits. They require per-workflow manual verification after action upgrades.

Low/medium manual verification:

- `ORCA Dashboard Pages`: run `workflow_dispatch` with no inputs. Confirm there are no Node.js 20 deprecation warnings from `checkout` or `setup-python`, the dashboard build succeeds, the Pages artifact uploads, and `Deploy to GitHub Pages` returns the page URL.
- `ORCA Backtest`: run `workflow_dispatch` with `months=13`, `walk_forward=true`, `expected_min_candidates=1000`, `expected_min_lessons=1000`, `expected_min_orca_sessions=1`, and `expected_min_jackal_sessions=1` unless a stricter validation target is intended. Confirm the `research-state-${{ github.run_id }}` artifact contains only `data/orca_state.db`, then confirm the reusable `Policy Eval` and `Policy Promote` jobs receive the expected artifact names.
- `Policy Eval`: verify primarily through the `ORCA Backtest` reusable call so the artifact is downloaded from the same workflow run. For direct `workflow_dispatch`, leave `artifact_name` empty unless the artifact exists in that same run context. Confirm `Install dependencies` runs before `Build Research Comparison Report`; a `ModuleNotFoundError` for `pandas` or another dependency means the clean runner did not install `requirements.txt`.
- `Policy Promote`: verify primarily through the `Policy Eval` output in the `ORCA Backtest` chain. For direct `workflow_dispatch`, leave `artifact_name` empty unless the policy-eval artifact exists in that same run context. Confirm `Install dependencies` runs before `Build policy promotion decision`.

High-risk verification plan:

- Verify one DB/state commit workflow at a time.
- Before each run, inspect `permissions`, checkout credential usage, `git pull --rebase`/push retry logic, DB checkpoint steps, and exact `git add` paths.
- Prefer a dry-run or no-op dispatch first when the workflow supports it. Do not use live LLM, paid API, trading, reset, or state-changing backfill runs just to validate action versions.
- Confirm the runner version is at least `2.327.1` before relying on Node.js 24 actions on self-hosted runners.
- After GitHub verification, inspect logs for Node warnings, checkout credential persistence behavior, state checkpoint output, commit/no-op behavior, and push retry behavior.

High-risk workflow settings:

| Workflow | State path | Safe first validation |
| --- | --- | --- |
| `db_vacuum.yml` | VACUUM and cold archive DB commit | No no-op mode exists. Do not manually dispatch without separate approval; validate next scheduled or approved maintenance run logs. |
| `jackal_backtest_learning.yml` | ORCA/JACKAL DB commit and optional artifact handoff | Prefer an approved run with `mode=incremental` first. For handoff, use `mode=full` plus an `artifact_run_id` from a successful `ORCA Backtest` run. |
| `jackal_scanner.yml` | scanner logs, watchlist, ORCA/JACKAL DB commit | No dry-run mode exists. Use `force=false` only after approval because this can use external provider and notification secrets. |
| `orca_daily.yml` | ORCA reports, JSON state, ORCA/JACKAL DB commit | No dry-run mode exists. Validate on the next approved scheduled run; use `expected_min_reports=0` unless checking a specific report count. |
| `orca_jackal.yml` | JACKAL-owned JSON/DB state replay to `main` | Use only after approval. Lower blast radius dispatch is `session_mode=scanner_only`, `force_hunt=false`, `force_scan=false`, `force_evolve=false`, but it can still use external secrets. |
| `orca_reset.yml` | destructive JSON state reset commit | Do not run with `confirm=RESET` without separate approval. For action smoke only, dispatch with `confirm=DO_NOT_RESET`, `reset_orca=false`, `reset_jackal=false` and expect the validation step to fail before reset. |
| `wave_f_backfill.yml` | ORCA DB context backfill commit | Dispatch only with `dry_run=true`, `cleanup=false`, `skip_existing=true`, `expected_snapshots=756`, `expected_linked_lessons=3869` until a separate non-dry approval exists. |
| `wave_f_clustering.yml` | ORCA DB clustering commit | Dispatch only with `dry_run=true`, `force_rebuild=false`, `append_mode=false`, `source_event_type=backtest_backfill`, `expected_snapshots=756`, `expected_linked_lessons=3864`, `min_silhouette=0.11` until a separate non-dry approval exists. |
| `wave_f_archive.yml` | ORCA DB/archive DB commit | Dispatch only with `dry_run=true`, `force_rebuild=false`, `append_mode=false`, `expected_archive_count=3864` until a separate non-dry approval exists. |

State persistence log interpretation:

- `no state changes to commit`: normal no-op. The workflow reached staging, found no relevant DB/JSON/report changes, and exited without a commit.
- `Commit created: <sha>` followed by `Push succeeded`: state changes were persisted.
- `Initial push failed; rebasing once and retrying` followed by `Push succeeded after rebase retry`: first push lost a race, then the workflow rebased on `origin/main` and pushed.
- `Git status before staging`, `Staged state diff`, and `Git status after push` should be present in every DB/state commit run log.
- `orca_jackal.yml` is special: it backs up JACKAL-owned outputs, aligns with `origin/main`, reapplies only those files, and pushes `HEAD:main`. Treat `No JACKAL-owned changes to save` or `no state changes to commit` as a normal no-op.

Artifact handoff checks:

- `jackal_backtest_learning.yml` Mode 1 downloads `research-state-${artifact_run_id}` into `_artifact_handoff/` using the same `run-id`, `repository`, and `github-token` inputs. Confirm the log prints `PASS Artifact verified in isolated dir`.
- The accepted DB path is `_artifact_handoff/data/orca_state.db` or `_artifact_handoff/orca_state.db`.
- `orca_jackal.yml` uploads `jackal-session-quality` with requirements drift, JACKAL intake, and dry-run quality audit files. Use this artifact to interpret a session before trusting persisted state.

Reset/backfill guardrail:

- `orca_reset.yml` must not be executed with `confirm=RESET` for action-version validation.
- `wave_f_backfill.yml`, `wave_f_clustering.yml`, and `wave_f_archive.yml` must not be executed with `dry_run=false` until the intended DB mutation has a separate approval and rollback plan.
- `db_vacuum.yml` has no dry-run switch; treat manual dispatch as a state-changing maintenance operation.
- Current 3-year Wave F inventory baseline is `756` backfill snapshots, `3869` linked backtest lessons, `756` clustered snapshots, and `3864` archived lessons. The archive is `5` lessons behind the latest linked lesson date because the current archive run stops at `2026-04-18`. The current 8-cluster dry-run silhouette is about `0.1200`, so the action smoke threshold is `0.11`.

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
