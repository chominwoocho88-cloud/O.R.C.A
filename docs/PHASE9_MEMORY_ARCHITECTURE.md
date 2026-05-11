# Phase 9 Memory Architecture Audit (2026-05-11)

> Goal: clarify the current Prediction Memory assets before building the full
> "swing prediction -> outcome tracking -> learning cycle" loop.

## 1. Current Memory Systems

### ORCA Prediction DB (`data/orca_state.db`)

#### Table: `predictions`

```sql
CREATE TABLE predictions (
    prediction_id TEXT PRIMARY KEY,
    external_key TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL,
    system TEXT NOT NULL,
    analysis_date TEXT NOT NULL,
    mode TEXT,
    prediction_kind TEXT NOT NULL,
    subject TEXT,
    category TEXT,
    event_name TEXT,
    direction TEXT,
    confidence TEXT,
    market_regime TEXT,
    trend_phase TEXT,
    summary_json TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    last_outcome_id TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    FOREIGN KEY(run_id) REFERENCES runs(run_id)
)
```

Current local data:

| Status | Count | Detail |
|---|---:|---|
| `open` | 68 | `report_summary` 30 + `thesis_killer` 38 |
| `resolved` | 30 | `thesis_killer` 30 |

Write path:

- `orca/state.py:795` `record_report_predictions`
- `orca/state.py:712` `_upsert_prediction`
- `orca/persist.py:91` `record_predictions`

Purpose:

- Tracks ORCA report-level market thesis predictions.
- Tracks `thesis_killer` items that can confirm or invalidate a thesis.
- This is ORCA's report quality memory, not a normalized JACKAL trade-card memory.

#### Table: `outcomes`

```sql
CREATE TABLE outcomes (
    outcome_id TEXT PRIMARY KEY,
    prediction_id TEXT NOT NULL UNIQUE,
    analysis_date TEXT NOT NULL,
    verdict TEXT NOT NULL,
    evidence TEXT,
    category TEXT,
    resolved_at TEXT NOT NULL,
    metadata_json TEXT,
    FOREIGN KEY(prediction_id) REFERENCES predictions(prediction_id)
)
```

Current local data:

| Verdict | Count |
|---|---:|
| `confirmed` | 25 |
| `invalidated` | 4 |
| `unclear` | 1 |

Resolve path:

- `orca/state.py:888` `resolve_outcomes`
- `orca/analysis_verification.py:442` thesis killer verification sync

Important finding:

- `thesis_killer` predictions are resolved.
- `report_summary` predictions are currently not resolved by this path, so they remain open.

### JACKAL Memory DB (`data/jackal_state.db`)

JACKAL stores hunt/scan/shadow memory separately from ORCA predictions.

#### Table: `jackal_live_events`

```sql
CREATE TABLE jackal_live_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    external_key TEXT NOT NULL UNIQUE,
    ticker TEXT NOT NULL,
    event_timestamp TEXT NOT NULL,
    analysis_date TEXT NOT NULL,
    alerted INTEGER NOT NULL DEFAULT 0,
    is_entry INTEGER NOT NULL DEFAULT 0,
    outcome_checked INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
```

Current local data: 21 rows.
Recent operating audit data: 32 rows.

Local breakdown:

| Event | Alerted | Entry | Outcome Checked | Count |
|---|---:|---:|---:|---:|
| `hunt` | 0 | 0 | 1 | 5 |
| `hunt` | 1 | 1 | 1 | 5 |
| `scan` | 0 | 0 | 0 | 10 |
| `scan` | 1 | 1 | 0 | 1 |

Write path:

- `jackal/hunter.py:1841` `sync_jackal_live_events("hunt", retained_logs)`
- `jackal/scanner.py:1387` `sync_jackal_live_events("scan", logs)`
- `jackal/tracker.py:533` syncs tracked hunt outcomes back to the DB
- `orca/state.py:2052` `sync_jackal_live_events`

Purpose:

- Stores JACKAL live hunt and scan events.
- Preserves payload JSON including score, signal context, Devil/Analyst result, and alert status.
- This is the closest existing asset to a JACKAL prediction card.

#### Table: `jackal_shadow_signals`

```sql
CREATE TABLE jackal_shadow_signals (
    shadow_id TEXT PRIMARY KEY,
    external_key TEXT NOT NULL UNIQUE,
    signal_timestamp TEXT NOT NULL,
    analysis_date TEXT NOT NULL,
    ticker TEXT NOT NULL,
    market TEXT,
    signal_family TEXT,
    quality_label TEXT,
    quality_score REAL,
    status TEXT NOT NULL DEFAULT 'open',
    payload_json TEXT NOT NULL,
    outcome_json TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT
)
```

Current local data: 6 rows, all `open`.
Recent operating audit data: 11 rows.

Write/resolve path:

- `jackal/scanner.py:1394` `record_jackal_shadow_signal`
- `jackal/evolution.py:414` `resolve_jackal_shadow_signal`

Purpose:

- Stores lower-quality or skipped scanner signals for shadow learning.
- Lets JACKAL learn from signals that were not sent as live alerts.

#### Accuracy Tables

Current local data:

| Table | Local Rows | Recent Operating Audit |
|---|---:|---:|
| `jackal_accuracy_current` | 89 | 92 |
| `jackal_accuracy_projection` | 89 | 276 |
| `jackal_shadow_batches` | 0 | not fixed in local audit |
| `jackal_recommendations` | 0 | not fixed in local audit |

Purpose:

- Holds aggregated accuracy views by system, ticker, regime, signal, Devil verdict, and related scopes.
- Used by research/reporting gates and future learning policy.

### Candidate Memory (`data/orca_state.db`)

Current local data:

| Table | Rows |
|---|---:|
| `candidate_registry` | 3956 |
| `candidate_outcomes` | 7888 |
| `candidate_lessons` | 3929 |

Purpose:

- This is the broad candidate memory layer.
- JACKAL live and shadow sync paths also write candidate records into ORCA state.
- `candidate_lessons` is already a large accumulated learning asset.

## 2. Outcome Tracking

### JACKAL Tracker

Location: `jackal/tracker.py`

Documented role in the module:

1. Find `hunt_log.json` entries where `outcome_checked=False`.
2. Fetch prices with yfinance.
3. Record 1D, swing, and 5D outcomes.
4. Update `jackal_weights.json` accuracy fields.
5. Sync results back through `sync_jackal_live_events("hunt", retained_logs)`.

Important current state:

- Hunt events are being checked locally.
- Scan events remain mostly unchecked locally.
- Shadow signals are present but currently open locally.

### ORCA Outcome Verification

Location: `orca/analysis_verification.py`

Current scope:

- Verifies ORCA thesis killer predictions.
- Writes results to `outcomes`.
- Updates `predictions.status` to `resolved`.

Current gap:

- This resolver does not handle JACKAL alert prediction cards.
- It also does not resolve `report_summary` predictions.

## 3. Learning System

### Probability Adjustment

Location: `jackal/probability.py`

Key functions:

- `load_probability_summary`
- `apply_probability_adjustment`

Policy source:

- `orca/learning_policy.py`
- `suggest_probability_adjustment`

Current behavior:

- The probability layer can adjust final JACKAL scores, such as the observed `learn +4`.
- It uses historical lesson/probability summaries.
- It is not yet a direct closed loop from every resolved live JACKAL outcome into future Devil/Analyst prompts.

### Evolution

Location: `jackal/evolution.py`

Key functions:

- `evolve`
- `_learn_from_outcomes`
- `_learn_from_recommendations`
- `_ask_claude`
- `_save_skills`
- `_save_instincts`
- `_apply_claude_adjustments`
- `_record_shadow_accuracy`
- `_sync_shadow_accuracy`

Current behavior:

- Evolution reads live and shadow outcomes.
- It can create skills, instincts, and weight adjustments.
- It is a learning engine, but it is not yet a complete Prediction Memory loop for normalized alert cards.

## 4. Big Picture Mapping

### 4.1 "Alert sent -> prediction card saved"

Current status: partial.

What exists:

- JACKAL hunt/scan events are saved to `jackal_live_events`.
- The raw `payload_json` preserves rich context.
- Hunter and Scanner both sync live events.

What is missing:

- No normalized `jackal_prediction_cards` table or view.
- Target, stop, horizon, reasoning, regime, and Fear & Greed are not first-class columns.
- The current memory is event-log shaped, not prediction-card shaped.

### 4.2 "3-5 days later -> outcome tracking"

Current status: partial.

What exists:

- `jackal/tracker.py` tracks hunt outcomes.
- 1D, swing, and 5D fields exist in tracker logic.
- Hunt events can be synced back after outcome tracking.

What is missing:

- Unified 1D/3D/5D resolver for hunt, scan, and shadow.
- Scan events are mostly unchecked locally.
- Shadow signals are mostly open locally.

### 4.3 "Success/failure patterns -> learning"

Current status: partial.

What exists:

- Probability adjustment exists.
- Candidate lessons have accumulated 3929 rows locally.
- Evolution can produce skills, instincts, and weights.

What is missing:

- Resolved live outcome cases are not yet injected into Devil/Analyst prompt memory in a direct, auditable way.
- There is no normalized bridge from JACKAL prediction card -> outcome -> reusable prompt lesson.

### 4.4 "Weekly Telegram report"

Current status: not implemented as a JACKAL Prediction Memory report.

What exists:

- ORCA notify/reporting has prediction and accuracy-related sections.
- JACKAL tracker can send summaries.

What is missing:

- A dedicated weekly "JACKAL prediction memory" report:
  - alert count
  - 1D hit rate
  - swing hit rate
  - best/worst pattern
  - learning changes
  - next-week caution rules

## 5. Current Gaps

| Gap | Priority | Suggested Sprint |
|---|---:|---|
| Normalize JACKAL prediction cards | High | Phase 9-2 |
| First-class target/stop/horizon/reason fields | High | Phase 9-2 |
| Unified 1D/3D/5D outcome resolver | High | Phase 9-3 |
| Resolved outcome -> prompt learning loop | Highest | Phase 9-4 |
| Weekly Telegram memory report | Medium | Phase 9-5 |
| Resolve or archive stale `report_summary` predictions | Medium | Phase 9 hygiene |

## 6. Data Hygiene Findings

### ORCA `report_summary` Predictions

`report_summary` has 30 open rows locally.

Finding:

- They are written by `record_report_predictions`.
- Current resolver focuses on `thesis_killer`.
- Therefore `report_summary` can remain open indefinitely unless a resolver/archive policy is added.

### Local vs Operating DB Differences

JACKAL DB counts differ between local and operating audit.

Known values:

| Metric | Local | Operating Audit |
|---|---:|---:|
| `jackal_live_events` | 21 | 32 |
| `jackal_shadow_signals` | 6 | 11 |
| `jackal_accuracy_current` | 89 | 92 |
| `jackal_accuracy_projection` | 89 | 276 |

Interpretation:

- The operating workflow is the richer source for latest JACKAL state.
- Local DB can lag behind workflow artifacts/committed state.
- Phase 9 should treat source-of-truth selection explicitly.

## 7. Phase 9 Plan

### Phase 9-1: Memory Architecture Audit

Status: this document.

Scope:

- Document current ORCA and JACKAL memory separation.
- Confirm what exists and what is missing.
- Create a stable base for the next implementation sprints.

### Phase 9-2: Normalize JACKAL Prediction Cards

Recommended scope:

- Add a new table or view for `jackal_prediction_cards`.
- Extract from `jackal_live_events.payload_json`.
- Promote important fields:
  - ticker
  - event timestamp
  - source event type
  - final score
  - day1 score
  - swing score
  - Devil score/verdict
  - target/stop/horizon when available
  - regime
  - Fear & Greed
  - signal family
  - alert status

Risk:

- Low if implemented as a new table/view without changing existing event writes.

### Phase 9-3: Unified Outcome Resolver

Recommended scope:

- Track hunt, scan, and shadow outcomes in one resolver.
- Support 1D, 3D, and 5D horizons.
- Preserve tracker behavior for hunt entries.
- Add scan/shadow outcome support.

Risk:

- Medium.
- Needs careful handling of yfinance/KIS source selection and missing price data.

### Phase 9-4: Closed-Loop Learning

Recommended scope:

- Convert resolved prediction cards into reusable lessons.
- Feed high-confidence lessons into Analyst/Devil context.
- Example learning shape:
  - "RSI < 20 + Greed > 60 + sector inflow produced swing success X/Y."
  - "Dead-cat true under risk-on had false-positive rate X%."

Risk:

- High.
- Prompt changes affect operating behavior and need staged rollout.

### Phase 9-5: Weekly Telegram Memory Report

Recommended scope:

- Send a concise weekly report:
  - alerts
  - resolved cards
  - 1D accuracy
  - swing accuracy
  - strongest pattern
  - weakest pattern
  - learning deltas

Risk:

- Low.
- Output-only feature.

## 8. User Vision Progress

Completed from the five JACKAL improvement views:

- Fear & Greed direct connection: complete.
- ORCA regime + human psychology in prompts: complete.
- Crash/surge pattern discovery through KIS movers: complete.

Remaining:

- Earnings-related movement detection.
- News + earnings date awareness.
- Full Prediction Memory System.

Phase 9 focus:

- Turn existing memory assets into one explicit learning loop:
  `prediction card -> outcome -> lesson -> future decision`.

## 9. Reference File Map

ORCA prediction memory:

- `orca/state.py:712` `_upsert_prediction`
- `orca/state.py:795` `record_report_predictions`
- `orca/state.py:888` `resolve_outcomes`
- `orca/persist.py:91` `record_predictions`
- `orca/analysis_verification.py:442` thesis killer outcome sync

JACKAL live/shadow memory:

- `orca/state.py:1751` `record_jackal_shadow_signal`
- `orca/state.py:1883` `resolve_jackal_shadow_signal`
- `orca/state.py:2052` `sync_jackal_live_events`
- `jackal/hunter.py:1841` hunt event sync
- `jackal/scanner.py:1387` scan event sync
- `jackal/scanner.py:1394` shadow signal write
- `jackal/tracker.py:365` tracker entry point
- `jackal/tracker.py:533` tracked hunt sync

Learning:

- `jackal/probability.py:15` `load_probability_summary`
- `jackal/probability.py:31` `apply_probability_adjustment`
- `orca/learning_policy.py:58` `suggest_probability_adjustment`
- `jackal/evolution.py:228` `_learn_from_outcomes`
- `jackal/evolution.py:640` `_ask_claude`
- `jackal/evolution.py:753` `_save_skills`
- `jackal/evolution.py:763` `_save_instincts`
