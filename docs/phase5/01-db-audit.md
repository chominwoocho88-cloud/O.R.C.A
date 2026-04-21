# Phase 5-A DB Audit

Purpose: establish a code-backed baseline for Phase 5 before any persistence-boundary or migration work.

Rules for this document:
- Code changes: 0
- Artifact count: 1 document only
- Scope: `data/orca_state.db`, `orca/state.py`, JACKAL runtime callers, and current research reports

## Section 0: Current State Snapshot

Snapshot basis:
- DB: `data/orca_state.db`
- Reports: `reports/orca_research_comparison.json`, `reports/orca_research_gate.json`
- Shell date: `2026-04-21`

### Tier 1 table counts

| Table | Current COUNT | Why it matters |
| --- | ---: | --- |
| `jackal_shadow_signals` | 0 | Shadow sample source. No skipped-signal evaluation can start without rows. |
| `jackal_shadow_batches` | 0 | Shadow scoring batches. `rolling_10` gate has no sample base without rows. |
| `jackal_weight_snapshots` | 0 | JACKAL learning state and accuracy projection source of truth. |
| `jackal_live_events` | 0 | JACKAL hunt/scan/tracker/evolution event history. |
| `jackal_recommendations` | 0 | JACKAL recommendation history and later outcome learning source. |

### Current report warnings

Source: `reports/orca_research_gate.json`

- `No JACKAL shadow batch history recorded yet.`
- `No SQL-projected JACKAL swing signal accuracy snapshot with enough samples yet.`
- `No SQL-projected JACKAL ticker accuracy snapshot with enough samples yet.`
- `No SQL-projected JACKAL recommendation regime accuracy snapshot with enough samples yet.`

### Current ORCA and JACKAL metrics

Source: `reports/orca_research_comparison.json`

| Metric | Value |
| --- | ---: |
| ORCA final accuracy | 58.7 |
| ORCA judged count | 126 |
| JACKAL swing accuracy | 75.6 |
| JACKAL D1 accuracy | 47.8 |
| JACKAL tracked picks | 205 |

### DB file size

- `data/orca_state.db`: `1,880,064` bytes

### Latest `git log -1 data/orca_state.db`

- Unavailable in this shell session because `git` is not installed.
- Additional context: `data/orca_state.db` is gitignored in [.gitignore](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.gitignore:8), while JACKAL workflow comments explicitly state JACKAL SQLite writes may be lost and are not treated as JACKAL-owned artifacts in CI. See [.github/workflows/orca_jackal.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/orca_jackal.yml:104) and [.github/workflows/orca_jackal.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/orca_jackal.yml:130).

### Snapshot interpretation

Confirmed facts:
- All Tier 1 JACKAL persistence tables currently have `COUNT = 0`.
- Research reports already expect shadow history and projected JACKAL accuracy views, but the source tables are empty.
- The scheduled JACKAL workflow runs `jackal.core` and `jackal.scanner`, then resets the checkout to `origin/main`; it does not treat `data/orca_state.db` as a JACKAL-owned persisted artifact. See [.github/workflows/orca_jackal.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/orca_jackal.yml:82), [.github/workflows/orca_jackal.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/orca_jackal.yml:97), [.github/workflows/orca_jackal.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/orca_jackal.yml:165), and [.github/workflows/orca_jackal.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/orca_jackal.yml:166).

Inference to verify in Phase 5-B/C:
- Even when JACKAL runtime code writes to SQLite, CI may discard those rows before they become the next run's baseline.

## Section 1: Tier 1 (최우선) Tables

These 5 tables are the primary Phase 5 investigation targets because they represent JACKAL's learning loop and runtime memory.

### 1. `jackal_shadow_signals`

Schema:
- Created in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:205)
- Pending lookup index in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:222)

State API:
- Write: `record_jackal_shadow_signal()` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1086)
- Read pending rows: `list_pending_jackal_shadow_signals()` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1144)
- Resolve row: `resolve_jackal_shadow_signal()` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1201)

Runtime callers:
- JACKAL scanner writes shadow rows when quality gating skips Claude evaluation. See [jackal/scanner.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/scanner.py:1766), [jackal/scanner.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/scanner.py:1788), and [jackal/scanner.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/scanner.py:1834).

Current finding:
- `COUNT = 0`

Impact:
- No skipped-signal sample pool exists.
- `jackal_shadow_batches` can never populate if this table stays empty.

### 2. `jackal_shadow_batches`

Schema:
- Created in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:225)
- Recorded-at index in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:234)

State API:
- Write: `record_jackal_shadow_accuracy_batch()` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1251)
- Read: `list_jackal_shadow_batches()` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1311)

Runtime callers:
- JACKAL evolution collects pending shadow rows, resolves them, and records batch accuracy. See [jackal/evolution.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/evolution.py:232), [jackal/evolution.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/evolution.py:367), and [jackal/evolution.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/evolution.py:913).

Current finding:
- `COUNT = 0`

Impact:
- `reports/orca_research_gate.json` cannot calculate meaningful `shadow_rolling_10`.
- Research gate stays in warning mode even after ORCA/JACKAL session linkage is fixed.

### 3. `jackal_weight_snapshots`

Schema:
- Created in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:257)
- Latest lookup index in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:264)

State API:
- Write: `record_jackal_weight_snapshot()` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1455)
- Read latest: `load_latest_jackal_weight_snapshot()` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1481)
- Derived write: `sync_jackal_accuracy_projection()` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1938)

Runtime callers:
- Hunter macro gate snapshot write: [jackal/hunter.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/hunter.py:1542)
- Tracker write: [jackal/tracker.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/tracker.py:526)
- Evolution write: [jackal/evolution.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/evolution.py:1006)

Current finding:
- `COUNT = 0`

Impact:
- `jackal_accuracy_projection` also stays empty because it is derived from snapshots.
- Adapter, core, scanner, tracker, and evolution all fall back away from DB-backed learning state. See [jackal/adapter.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/adapter.py:39), [jackal/core.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/core.py:105), [jackal/scanner.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/scanner.py:321), [jackal/tracker.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/tracker.py:383), and [jackal/evolution.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/evolution.py:962).

### 4. `jackal_live_events`

Schema:
- Created in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:237)
- Lookup indexes in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:251) and [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:254)

State API:
- Write: `sync_jackal_live_events()` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1353)
- Read: `list_jackal_live_events()` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1422)

Runtime callers:
- Hunter write: [jackal/hunter.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/hunter.py:1474)
- Scanner write: [jackal/scanner.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/scanner.py:1563)
- Tracker write-back: [jackal/tracker.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/tracker.py:516)
- Evolution write-back: [jackal/evolution.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/evolution.py:365)
- Evolution read: [jackal/evolution.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/evolution.py:206)
- Tracker read: [jackal/tracker.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/tracker.py:348)

Current finding:
- `COUNT = 0`

Impact:
- JACKAL runtime is not retaining event history in the shared DB baseline.
- Candidate registry ingestion through `record_candidate()` has no JACKAL source rows to build on.

### 5. `jackal_recommendations`

Schema:
- Created in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:284)
- Lookup index in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:298)

State API:
- Write: `sync_jackal_recommendations()` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1701)
- Read: `list_jackal_recommendations()` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1761)

Runtime callers:
- Scanner write: [jackal/scanner.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/scanner.py:363)
- Evolution read and write-back: [jackal/evolution.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/evolution.py:451) and [jackal/evolution.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/evolution.py:524)

Current finding:
- `COUNT = 0`

Impact:
- Recommendation learning loop is not preserved in the DB spine.
- Recommendation regime/inflow accuracy views remain empty.

### Tier 1 summary

Confirmed:
- Writer functions exist in code for all five Tier 1 tables.
- Current DB snapshot has zero rows in all five.
- Scheduled workflow comments acknowledge that JACKAL SQLite writes may be lost because `data/orca_state.db` is not treated as a JACKAL-owned artifact. See [.github/workflows/orca_jackal.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/orca_jackal.yml:104).

Implication for Phase 5:
- Phase 5 root fix has to preserve JACKAL state independently of ORCA's DB ownership assumptions.

## Section 2: Tier 2 (일반 조사)

Tier 2 includes all remaining tables. These are important for context, but not the first persistence-boundary target.

### Current counts by table

| Table | COUNT | Notes |
| --- | ---: | --- |
| `backtest_daily_results` | 399 | Research output history exists. |
| `backtest_pick_results` | 205 | JACKAL backtest pick history exists. |
| `backtest_sessions` | 6 | ORCA and JACKAL research sessions exist. |
| `backtest_state` | 18 | Backtest session state exists. |
| `candidate_lessons` | 0 | Candidate follow-up loop not populated. |
| `candidate_outcomes` | 0 | Candidate outcome linkage absent. |
| `candidate_registry` | 0 | No persisted candidate spine rows at snapshot time. |
| `candidate_reviews` | 0 | No persisted candidate review rows. |
| `jackal_accuracy_projection` | 0 | Empty because source snapshots are empty. |
| `jackal_cooldowns` | 0 | No persisted cooldown state. |
| `outcomes` | 0 | ORCA outcome table still empty in this snapshot. |
| `predictions` | 4 | Prediction rows exist, but outcome linkage remains sparse. |
| `runs` | 8 | ORCA run history exists. |

### Tier 2 grouping

Research / backtest spine:
- `backtest_sessions`
- `backtest_state`
- `backtest_daily_results`
- `backtest_pick_results`

ORCA runtime verification spine:
- `runs`
- `predictions`
- `outcomes`

Candidate spine:
- `candidate_registry`
- `candidate_reviews`
- `candidate_lessons`
- `candidate_outcomes`

JACKAL derived / support tables:
- `jackal_accuracy_projection`
- `jackal_cooldowns`

Observation:
- Research tables are populated.
- Runtime learning and candidate tables are mostly empty.
- This split already suggests that research persistence is healthier than production-adjacent JACKAL memory persistence.

## Section 3: Write Path Inventory

This section inventories where writes originate and where payload JSON is parsed back into runtime structures.

### Runtime write paths

JACKAL event and learning writes:
- `sync_jackal_live_events()` -> `jackal_live_events` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1353)
- `record_jackal_shadow_signal()` -> `jackal_shadow_signals` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1086)
- `resolve_jackal_shadow_signal()` -> resolves `jackal_shadow_signals` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1201)
- `record_jackal_shadow_accuracy_batch()` -> `jackal_shadow_batches` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1251)
- `record_jackal_weight_snapshot()` -> `jackal_weight_snapshots` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1455)
- `sync_jackal_recommendations()` -> `jackal_recommendations` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1701)
- `sync_jackal_accuracy_projection()` -> `jackal_accuracy_projection` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1938)

Candidate write side effects from JACKAL-origin rows:
- `record_candidate()` -> `candidate_registry` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:2470)
- `record_candidate_review()` -> `candidate_reviews` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:2995)
- `record_candidate_lesson()` -> `candidate_lessons` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:3078)

Runtime read / parse paths with JSON decode:
- `list_pending_jackal_shadow_signals()` parses `payload_json` and `outcome_json` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1144)
- `resolve_jackal_shadow_signal()` parses `payload_json` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1201)
- `list_jackal_live_events()` parses `payload_json` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1422)
- `load_latest_jackal_weight_snapshot()` parses `weights_json` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1481)
- `list_jackal_recommendations()` parses `payload_json` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1761)
- `list_jackal_accuracy_projection()` parses `metrics_json` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1992)
- `rebuild_latest_jackal_accuracy_projection()` parses `weights_json` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:2044)
- `list_candidates()` parses `candidate_registry.payload_json` on a confirmed normal runtime path in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:2588), called from [orca/analysis.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/analysis.py:679) and [jackal/scanner.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/scanner.py:135)
- `list_candidate_reviews()` parses `candidate_reviews.review_json` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:2724)

### Migration-only functions

Functions found in `orca/state.py` that are not part of the normal per-cycle read/write loop:
- `init_state_db()` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:80)
  - Role: create tables, indexes, and view definitions.
  - Phase 5-C question: keep as a shared bootstrapper or split by DB owner.
- `backfill_candidate_signal_families(*, limit: int | None = None) -> int` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:2923)
  - Role: retrofit `candidate_registry.signal_family` from stored payloads.
  - Repo search result: no normal runtime caller found outside its own definition.
  - Phase 5-C question: migrate once during data move, or retire if the target DB starts clean.

Search result for other migration patterns:
- No `migrate_*` function definitions were found in `orca/state.py` at this snapshot.

### Workflow-level persistence risk

Relevant scheduled path:
- Run `jackal.core`: [.github/workflows/orca_jackal.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/orca_jackal.yml:82)
- Run `jackal.scanner`: [.github/workflows/orca_jackal.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/orca_jackal.yml:97)
- Reset and clean checkout: [.github/workflows/orca_jackal.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/orca_jackal.yml:165) and [.github/workflows/orca_jackal.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/orca_jackal.yml:166)
- Explicit note that `data/orca_state.db` is ORCA-owned and JACKAL SQLite writes may be lost: [.github/workflows/orca_jackal.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/orca_jackal.yml:104) and [.github/workflows/orca_jackal.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/orca_jackal.yml:130)

Operational implication:
- The code has write paths.
- The scheduled persistence contract does not guarantee those writes survive to the next run.
- Phase 5 cannot stop at table creation or caller tracing; it has to fix ownership and retention.

## Section 4: Phase 5-A Conclusions

Confirmed conclusions:
- Tier 1 JACKAL persistence tables are all empty at Phase 5 start.
- Research artifacts exist, but production-adjacent JACKAL memory state does not.
- Current CI comments already acknowledge the persistence boundary problem.
- `backfill_candidate_signal_families()` should be treated as migration-only, not normal runtime.

What Phase 5-B/C should prove after the fix:
- `jackal_live_events` starts accumulating rows across scheduled runs.
- `jackal_weight_snapshots` and `jackal_accuracy_projection` stop resetting to zero.
- `jackal_shadow_signals` and then `jackal_shadow_batches` begin accumulating measurable history.
- Research reports stop warning about missing JACKAL shadow history and missing projected accuracy views.

## Section 3.5: Reference Graph

Purpose: trace explicit FK edges and implicit runtime references before deciding which tables can move in Phase 5-B.

### 3.5.1. Explicit Foreign Keys (PRAGMA)

Recorded exactly from the requested PRAGMA scan:

```text
Foreign Key Relations:

backtest_daily_results:
  column=session_id -> backtest_sessions.session_id  on_delete=NO ACTION

backtest_pick_results:
  column=session_id -> backtest_sessions.session_id  on_delete=NO ACTION

backtest_state:
  column=session_id -> backtest_sessions.session_id  on_delete=NO ACTION

candidate_lessons:
  column=outcome_id -> candidate_outcomes.outcome_id  on_delete=NO ACTION
  column=candidate_id -> candidate_registry.candidate_id  on_delete=NO ACTION

candidate_outcomes:
  column=candidate_id -> candidate_registry.candidate_id  on_delete=NO ACTION

candidate_reviews:
  column=run_id -> runs.run_id  on_delete=NO ACTION
  column=candidate_id -> candidate_registry.candidate_id  on_delete=NO ACTION

outcomes:
  column=prediction_id -> predictions.prediction_id  on_delete=NO ACTION

predictions:
  column=run_id -> runs.run_id  on_delete=NO ACTION
```

Immediate implication:
- There are explicit parent-child edges.
- There are no explicit FK edges from any `jackal_*` table to any other table.
- There is no explicit bidirectional FK pair.

### 3.5.2. Implicit References (grep-based)

Command-equivalent results recorded from code search.

#### A. Tier 1 table names in `orca/` and `jackal/`

Key matches:

```text
orca/research_report.py:18:list_jackal_shadow_batches,
orca/research_report.py:237:shadow_batches = list_jackal_shadow_batches(20)
orca/state.py:205:CREATE TABLE IF NOT EXISTS jackal_shadow_signals (
orca/state.py:225:CREATE TABLE IF NOT EXISTS jackal_shadow_batches (
orca/state.py:237:CREATE TABLE IF NOT EXISTS jackal_live_events (
orca/state.py:257:CREATE TABLE IF NOT EXISTS jackal_weight_snapshots (
orca/state.py:284:CREATE TABLE IF NOT EXISTS jackal_recommendations (
orca/state.py:1113:INSERT INTO jackal_shadow_signals (
orca/state.py:1232:UPDATE jackal_shadow_signals
orca/state.py:1265:INSERT INTO jackal_shadow_batches (
orca/state.py:1380:INSERT INTO jackal_live_events (
orca/state.py:1466:INSERT INTO jackal_weight_snapshots (
orca/state.py:1727:INSERT INTO jackal_recommendations (
jackal/evolution.py:206:self._logs = list(reversed(list_jackal_live_events("hunt", limit=500)))
jackal/evolution.py:232:pending_shadow = list_pending_jackal_shadow_signals(cutoff_1d.isoformat())
jackal/evolution.py:365:sync_jackal_live_events("hunt", self._logs[-500:])
jackal/evolution.py:451:logs = list_jackal_recommendations(limit=200)
jackal/evolution.py:524:sync_jackal_recommendations(logs)
jackal/hunter.py:1474:sync_jackal_live_events("hunt", retained_logs)
jackal/scanner.py:350:logs = list_jackal_recommendations(limit=200)
jackal/scanner.py:363:sync_jackal_recommendations(logs)
jackal/scanner.py:1563:sync_jackal_live_events("scan", logs)
jackal/tracker.py:348:logs = list(reversed(list_jackal_live_events("hunt", limit=500)))
jackal/tracker.py:516:sync_jackal_live_events("hunt", retained_logs)
```

Interpretation:
- Tier 1 table SQL lives only in `orca/state.py`.
- JACKAL modules use those tables through imported state APIs, not direct SQL.
- ORCA research reporting reads Tier 1 state through state APIs, not direct SQL in `research_report.py`.

#### B. ORCA/shared table names in `jackal/`

Exact-name search result:

```text
(no matches)
```

Interpretation:
- JACKAL code does not mention `candidate_registry`, `candidate_reviews`, `candidate_outcomes`, `runs`, `predictions`, or `outcomes` by literal table name.
- JACKAL reaches shared tables through `orca.state` APIs, not by embedding raw table names or SQL.

#### C. `run_id` in `orca/state.py` and `jackal/`

Condensed search result:

```text
orca/analysis.py:667:run_id: str | None = None,
orca/persist.py:89:def record_predictions(*, run_id: str | None, report: dict, health_tracker: Any) -> dict:
orca/run_cycle.py:183:run_id = state_start_run(
orca/state.py:85:run_id TEXT PRIMARY KEY,
orca/state.py:118:FOREIGN KEY(run_id) REFERENCES runs(run_id)
orca/state.py:391:FOREIGN KEY(run_id) REFERENCES runs(run_id)
orca/state.py:580:def record_report_predictions(run_id: str, report: dict) -> dict[str, Any]:
orca/state.py:2999:run_id: str | None = None,
```

Observed fact:
- No `run_id` matches were found in `jackal/*.py`.

Interpretation:
- `run_id` remains an ORCA-side identity convention.
- JACKAL does not currently carry or join on `run_id`.

### 3.5.3. Shared Column Conventions

#### `run_id`

Tables containing `run_id`:
- `runs`
- `predictions`
- `candidate_reviews`

Meaning:
- Explicitly tied to ORCA run tracking.
- Has explicit FK edges `predictions.run_id -> runs.run_id` and `candidate_reviews.run_id -> runs.run_id`.

Actual `JOIN` query in `orca/state.py`:
- No SQL `JOIN` on `run_id` was found.

Conclusion:
- `run_id` behaves like an implicit ORCA identity key plus FK, not an actively joined cross-system dimension.

#### `candidate_id`

Tables containing `candidate_id`:
- `candidate_registry`
- `candidate_reviews`
- `candidate_outcomes`
- `candidate_lessons`

Meaning:
- Primary shared identity for candidate-related tables.
- Explicit parent-child chain:
  - `candidate_reviews.candidate_id -> candidate_registry.candidate_id`
  - `candidate_outcomes.candidate_id -> candidate_registry.candidate_id`
  - `candidate_lessons.candidate_id -> candidate_registry.candidate_id`

Actual `JOIN` query in `orca/state.py`:

```text
orca/state.py:2794:FROM candidate_lessons l
orca/state.py:2795:JOIN candidate_registry c
```

Conclusion:
- `candidate_id` is the one shared column convention that is both explicitly related by FK and actually joined in live code.
- This is the strongest schema-level signal that `candidate_*` forms a table cluster, not isolated tables.

#### `analysis_date`

Tables containing `analysis_date`:
- `runs`
- `predictions`
- `outcomes`
- `backtest_daily_results`
- `backtest_pick_results`
- `jackal_shadow_signals`
- `jackal_live_events`
- `jackal_recommendations`
- `candidate_registry`
- `candidate_reviews`

Meaning:
- Cross-cut partition and filtering dimension across ORCA, JACKAL runtime, and backtest tables.
- Used for lookup indexes and ordering, not as an explicit FK.

Actual `JOIN` query in `orca/state.py`:
- No SQL `JOIN` on `analysis_date` was found.

Conclusion:
- `analysis_date` is a shared partition key, not a relational identity key.
- It is useful for cutover and dual-write validation, but not enough by itself to reconstruct ownership.

### 3.5.4. Reference Graph Conclusion

#### Tier 1 -> other tables

- `jackal_shadow_signals`
  - Explicit FK: none
  - Implicit reference: `record_jackal_shadow_signal()` calls `record_candidate()`, which writes `candidate_registry` and may also upsert `candidate_outcomes` when outcome fields exist. See [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1086) and [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1134).
- `jackal_shadow_batches`
  - Explicit FK: none
  - Implicit reference: none to other tables; acts as aggregate history consumed by reporting only.
- `jackal_weight_snapshots`
  - Explicit FK: none
  - Implicit reference: parent of `jackal_accuracy_projection` via shared `snapshot_id` convention. See [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1455) and [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1938).
- `jackal_live_events`
  - Explicit FK: none
  - Implicit reference: `sync_jackal_live_events()` calls `record_candidate()`, which writes `candidate_registry` and may write `candidate_outcomes`. See [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1353) and [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1412).
- `jackal_recommendations`
  - Explicit FK: none
  - Implicit reference: no table-to-table write side effect; consumed by JACKAL evolution through state APIs.

#### Tier 2 -> Tier 1

- `jackal_accuracy_projection` implicitly references `jackal_weight_snapshots` by `snapshot_id`, but without an explicit FK.
- `candidate_registry` implicitly references JACKAL-origin events through `source_system`, `source_event_type`, `source_event_id`, and `source_external_key`. This is how JACKAL-origin rows are preserved without explicit FK edges.
- `candidate_outcomes` is populated from candidate payloads that originate in JACKAL event/shadow paths.

#### Bidirectional references

Explicit FK result:
- No bidirectional FK pair exists.

Implicit runtime result:
- There is no Tier 1 <-> Tier 1 bidirectional table reference.
- The strongest cross-cluster edge is `Tier 1 JACKAL event tables -> candidate_registry/candidate_outcomes`.

#### Special case: `record_candidate()` -> `candidate_registry`

This relationship is shared, not ORCA-only.

Why:
- JACKAL-origin writes:
  - `sync_jackal_live_events()` writes JACKAL runtime events and then calls `record_candidate()`. See [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1412).
  - `record_jackal_shadow_signal()` calls `record_candidate()`. See [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1134).
  - `resolve_jackal_shadow_signal()` calls `record_candidate()` again with resolved payload/outcome fields. See [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1242).
- ORCA-origin writes:
  - `record_candidate_review()` updates `candidate_registry.orca_alignment`. See [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:3067).
- Reads from both systems:
  - ORCA analysis reads candidates: [orca/analysis.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/analysis.py:679)
  - JACKAL scanner reads candidates: [jackal/scanner.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/scanner.py:135)

Final conclusion:
- `candidate_registry` is a shared table.
- It is not ORCA-only.
- JACKAL writes candidate rows and ORCA reads and enriches them.

## Section 5: Separation Feasibility Classification

Purpose: classify each table before Phase 5-B decides what can move to `jackal_state.db`, what must stay in `orca_state.db`, and what needs explicit shared-table strategy.

### 5.1. Category 1: JACKAL-only (move candidate to `jackal_state.db`)

#### `jackal_shadow_signals` -> Category 1

Reason:
- Runtime writes originate from JACKAL scanner via `record_jackal_shadow_signal()`.
- No explicit FK to ORCA tables.
- ORCA reads it only through state APIs for reporting/evaluation, not via direct SQL in ORCA business logic.

Evidence:
- Write API: [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1086)
- Runtime caller: [jackal/scanner.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/scanner.py:1570)

Migration note:
- The table itself can move.
- The current `record_candidate()` side effect attached to this path would need to stay behind or be re-routed.

#### `jackal_shadow_batches` -> Category 1

Reason:
- Runtime writes originate from JACKAL evolution only.
- No FK edges.
- ORCA consumes only aggregated results through state APIs.

Evidence:
- Write API: [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1251)
- Runtime caller: [jackal/evolution.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/evolution.py:913)

#### `jackal_weight_snapshots` -> Category 1

Reason:
- Runtime writes originate from JACKAL hunter, tracker, and evolution.
- No explicit FK to ORCA tables.
- ORCA modules only consume the latest snapshot through state APIs.

Evidence:
- Write API: [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1455)
- Runtime callers: [jackal/hunter.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/hunter.py:1542), [jackal/tracker.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/tracker.py:526), [jackal/evolution.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/evolution.py:1006)

#### `jackal_live_events` -> Category 1

Reason:
- Runtime writes originate from JACKAL hunter, scanner, tracker, and evolution.
- No explicit FK to ORCA tables.
- ORCA-side use is API-mediated and mostly diagnostic/reporting.

Evidence:
- Write API: [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1353)
- Runtime callers: [jackal/hunter.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/hunter.py:1474), [jackal/scanner.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/scanner.py:1563), [jackal/tracker.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/tracker.py:516), [jackal/evolution.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/evolution.py:365)

Migration note:
- The table can move, but its current candidate side effect means the API boundary has to change at the same time.

#### `jackal_recommendations` -> Category 1

Reason:
- Runtime writes originate from JACKAL scanner and evolution.
- No explicit FK edges.
- ORCA does not directly embed SQL against it.

Evidence:
- Write API: [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1701)
- Runtime callers: [jackal/scanner.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/scanner.py:363), [jackal/evolution.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/evolution.py:524)

#### `jackal_accuracy_projection` -> Category 1

Reason:
- Derived exclusively from JACKAL weight snapshots.
- No explicit FK edges.
- ORCA report reads it through state APIs only.

Evidence:
- Write API: [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1938)
- Rebuild API: [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:2044)
- Consumer: [orca/research_report.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/research_report.py:149)

#### `jackal_cooldowns` -> Category 1

Reason:
- Read/write activity is local to JACKAL scanner through state APIs.
- No explicit FK edges.
- No ORCA module caller was found.

Evidence:
- APIs: [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1500) and [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1537)
- Runtime caller: [jackal/scanner.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/scanner.py:333) and [jackal/scanner.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/scanner.py:346)

### 5.2. Category 2: ORCA-only (keep in `orca_state.db`)

#### `runs` -> Category 2

Reason:
- ORCA-only write path.
- JACKAL code does not use `run_id`.
- Explicit parent table for ORCA verification lifecycle.

Evidence:
- FK parent for `predictions` and `candidate_reviews`
- Runtime caller path begins in [orca/run_cycle.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/run_cycle.py:183)

#### `predictions` -> Category 2

Reason:
- ORCA-only write and resolution flow.
- Explicitly tied to `runs` and `outcomes`.
- No JACKAL caller found.

Evidence:
- Write path: `record_report_predictions()` in [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:580)
- Caller: [orca/persist.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/persist.py:97)

#### `outcomes` -> Category 2

Reason:
- ORCA-only verification result table.
- Explicit FK from `prediction_id`.
- No JACKAL caller found.

Evidence:
- Resolution path: [orca/analysis.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/analysis.py:1205)
- State API: [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:651)

#### `backtest_state` -> Category 2

Reason:
- Only ORCA backtest uses `load_backtest_state()` and `save_backtest_state()`.
- JACKAL backtest does not use session key/value state.
- Explicit FK only to `backtest_sessions`.

Evidence:
- ORCA callers: [orca/backtest.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/backtest.py:745) and [orca/backtest.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/backtest.py:754)
- No JACKAL caller found in code search.

### 5.3. Category 3: Shared (cannot move cleanly without explicit shared strategy)

#### `backtest_sessions` -> Category 3

Reason:
- Both ORCA and JACKAL backtest write sessions.
- Parent table for `backtest_state`, `backtest_daily_results`, and `backtest_pick_results`.

Evidence:
- ORCA writer: [orca/backtest.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/backtest.py:2445)
- JACKAL writer: [jackal/backtest.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/backtest.py:359)

#### `backtest_daily_results` -> Category 3

Reason:
- Both ORCA and JACKAL write daily rows under the shared session model.
- Explicit FK to `backtest_sessions`.

Evidence:
- ORCA writer: [orca/backtest.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/backtest.py:1640)
- JACKAL writer: [jackal/backtest.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/backtest.py:501)

#### `backtest_pick_results` -> Category 3

Reason:
- Both ORCA and JACKAL write pick-level research artifacts.
- Explicit FK to `backtest_sessions`.

Evidence:
- ORCA writer exists in state API and ORCA backtest selection stages.
- JACKAL writer: [jackal/backtest.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/backtest.py:493)

#### `candidate_registry` -> Category 3

Reason:
- JACKAL-origin event paths write it through `record_candidate()`.
- ORCA review path updates it through `record_candidate_review()`.
- Both ORCA and JACKAL read it through `list_candidates()`.

Evidence:
- JACKAL-origin side effects: [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1134), [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1242), [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1412)
- ORCA update: [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:3067)
- ORCA read: [orca/analysis.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/analysis.py:679)
- JACKAL read: [jackal/scanner.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/scanner.py:135)

#### `candidate_outcomes` -> Category 3

Reason:
- Rows are generated from candidate payloads inside `record_candidate()`, which is fed by JACKAL runtime event data.
- Table is part of the shared candidate graph through explicit FK to `candidate_registry`.
- ORCA probability lesson generation consumes it.

Evidence:
- Outcome sync path: [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:2214)
- Candidate writer path: [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:2562)
- Downstream ORCA consumer: [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:2405)

### 5.4. Category 4: Ambiguous

#### `candidate_reviews` -> Category 4

Reason:
- Current writes are ORCA-only.
- Explicitly depends on both `runs` and shared `candidate_registry`.
- No current JACKAL caller exists, but if the candidate cluster is treated as shared, table placement follows higher-level design rather than current call count alone.

Evidence:
- FK edges: `candidate_reviews.run_id -> runs.run_id`, `candidate_reviews.candidate_id -> candidate_registry.candidate_id`
- ORCA writer: [orca/analysis.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/analysis.py:825)
- State API: [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:2995)

Interpretation:
- If the candidate cluster stays with ORCA, this table becomes Category 2.
- If Phase 5-B promotes a separate shared candidate store, this table belongs in that shared cluster.

#### `candidate_lessons` -> Category 4

Reason:
- ORCA writes it through `_sync_candidate_probability_lesson()` and `record_candidate_lesson()`.
- JACKAL reads its aggregated effect indirectly through `jackal/probability.py -> summarize_candidate_probabilities()`.
- Explicit FK edges point to `candidate_registry` and `candidate_outcomes`, both already tied to the shared candidate cluster.

Evidence:
- ORCA lesson sync: [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:2405)
- ORCA summary query with join: [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:2775)
- JACKAL consumer: [jackal/probability.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/probability.py:13)

Interpretation:
- This table is not cleanly JACKAL-only or ORCA-only.
- Its final placement depends on where the candidate probability subsystem lives after Phase 5-B.

### 5.5. Summary Count

- Category 1 (JACKAL-only): `7`
- Category 2 (ORCA-only): `4`
- Category 3 (Shared): `5`
- Category 4 (Ambiguous): `2`

Phase 5-B implication:
- Shared tables: `5`
- Ambiguous tables: `2`
- This falls into the "Shared >= 3 or Blockers >= 2" branch, so Phase 5-B should assume non-trivial shared-table strategy from the start.

## Section 6: Stop Conditions Check

Purpose: validate the four original Phase 5-A stop conditions before Phase 5-B starts.

### 6.1. Stop Condition 1: ORCA module writes `jackal_` prefix tables

Result: `found`

Locations and tables:
- [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1086) `record_jackal_shadow_signal()` -> `jackal_shadow_signals`
- [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1251) `record_jackal_shadow_accuracy_batch()` -> `jackal_shadow_batches`
- [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1353) `sync_jackal_live_events()` -> `jackal_live_events`
- [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1455) `record_jackal_weight_snapshot()` -> `jackal_weight_snapshots`
- [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1537) `sync_jackal_cooldown_state()` -> `jackal_cooldowns`
- [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1701) `sync_jackal_recommendations()` -> `jackal_recommendations`
- [orca/state.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/orca/state.py:1938) `sync_jackal_accuracy_projection()` -> `jackal_accuracy_projection`

Likely design intent:
- `orca/state.py` is acting as a shared persistence adapter for both systems, even though it lives under the ORCA module path.

Impact:
- Physical file location and logical ownership are already mismatched.
- Phase 5-B cannot infer ownership from module path alone.

### 6.2. Stop Condition 2: JACKAL module writes ORCA/shared tables

Result: `found`

Found cases:

#### A. JACKAL writes shared `backtest_*`

- [jackal/backtest.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/backtest.py:359) `start_backtest_session()` -> `backtest_sessions`
- [jackal/backtest.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/backtest.py:501) `record_backtest_day()` -> `backtest_daily_results`
- [jackal/backtest.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/backtest.py:493) `record_backtest_pick_results()` -> `backtest_pick_results`
- [jackal/backtest.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/backtest.py:549) `finish_backtest_session()` -> `backtest_sessions.summary_json`

#### B. JACKAL triggers writes into shared `candidate_*`

- [jackal/hunter.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/hunter.py:1474) calls `sync_jackal_live_events()`
- [jackal/scanner.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/scanner.py:1563) calls `sync_jackal_live_events()`
- [jackal/scanner.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/scanner.py:1570) calls `record_jackal_shadow_signal()`
- [jackal/tracker.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/tracker.py:516) calls `sync_jackal_live_events()`
- [jackal/evolution.py](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/jackal/evolution.py:365) calls `sync_jackal_live_events()`

Why this counts:
- The user explicitly included `candidate_*` in Stop Condition 2.
- JACKAL code is not issuing direct SQL, but it is the runtime origin of writes that land in `candidate_registry` and `candidate_outcomes` through `record_candidate()`.

Judgment:
- Yes, this qualifies as Stop Condition 2.
- Ownership is shared at runtime even if SQL is centralized in `orca/state.py`.

### 6.3. Stop Condition 3: tables with unclear design intent

Result: `found`

Current ambiguous tables:
- `candidate_outcomes`
  - Side-effect table populated from candidate payloads rather than a single explicit domain owner.
- `candidate_lessons`
  - ORCA writes it, JACKAL consumes its aggregate through probability helpers.
- `candidate_reviews`
  - ORCA-owned today, but anchored to shared `candidate_registry`.
- `backtest_state`
  - Generic shared-sounding name, but only ORCA currently uses it.

Interpretation:
- These tables need explicit ownership notes in Phase 5-B design, even if they do not all move.

### 6.4. Stop Condition 4: Foreign Key bidirectional references

Result: `clear`

Basis:
- PRAGMA scan found explicit FK edges, but no table pair references each other in both directions.
- `JOIN` scan in `orca/state.py` also did not reveal any bidirectional relational cycle.

### 6.5. Blockers Summary

Blockers found before Phase 5-B:

1. Shared persistence adapter blocker
- `orca/state.py` currently owns write APIs for both ORCA and JACKAL tables.
- Candidate fix direction:
  - split adapter modules by ownership, or
  - keep one adapter file but add explicit DB routing map per table family.

2. Shared table cluster blocker
- `backtest_*` and `candidate_*` are not cleanly separable with a simple prefix-based move.
- Candidate fix direction:
  - treat them as first-class shared clusters, not leftovers.

3. Candidate cluster ambiguity blocker
- `candidate_registry`, `candidate_outcomes`, `candidate_reviews`, and `candidate_lessons` do not form a clean single-owner set yet.
- Candidate fix direction:
  - decide whether candidate intelligence is ORCA-owned with JACKAL reads, or a separate shared domain.

Non-blocker:
- No explicit bidirectional FK cycle was found, so relational cycle-breaking is not the primary problem.
