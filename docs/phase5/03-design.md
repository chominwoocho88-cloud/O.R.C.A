# Phase 5-B Design

Purpose: translate the Path B decision into an implementation-ready design without changing code, workflows, or live database files.

Scope guardrails:
- Code changes: 0
- Workflow changes: 0
- DB file creation: 0
- Artifact count: 1 document only

Related documents:
- Audit baseline: [01-db-audit.md](./01-db-audit.md)
- Path decision: [02-path-decision.md](./02-path-decision.md)
- JACKAL signal inventory: [current-signals.md](../jackal/current-signals.md)

## Section 1: Schema Definition

### 1.1. `jackal_state.db` table definitions

Design rule:
- Phase 5-B does not redesign schema.
- The 7 Category 1 tables move as-is from `orca/state.py`.
- Schema parity target: byte-for-byte equivalent SQL for table and index definitions, lifted from the current `init_state_db()` implementation in `orca/state.py`.
- Audit basis: `01-db-audit.md:247-278`, `01-db-audit.md:580-645`, and `01-db-audit.md:803-810`.

#### `jackal_shadow_signals`

Source of truth:
- Code ref: `orca/state.py:205-223`
- Audit refs: `01-db-audit.md:59-88`, `01-db-audit.md:247-250`, `01-db-audit.md:504-506`, `01-db-audit.md:803-804`

Existing SQL:

```sql
CREATE TABLE IF NOT EXISTS jackal_shadow_signals (
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
);

CREATE INDEX IF NOT EXISTS idx_jackal_shadow_pending
    ON jackal_shadow_signals(status, signal_timestamp);
```

Schema parity check:
- Phase 5-C must copy this SQL unchanged into JACKAL bootstrap.
- No explicit foreign key exists.
- Existing schema and target schema are identical by construction because the SQL text is reused verbatim.

#### `jackal_shadow_batches`

Source of truth:
- Code ref: `orca/state.py:225-235`
- Audit refs: `01-db-audit.md:90-111`, `01-db-audit.md:247-251`, `01-db-audit.md:507-509`, `01-db-audit.md:805`

Existing SQL:

```sql
CREATE TABLE IF NOT EXISTS jackal_shadow_batches (
    batch_id TEXT PRIMARY KEY,
    recorded_at TEXT NOT NULL,
    total INTEGER NOT NULL,
    worked INTEGER NOT NULL,
    rate REAL NOT NULL,
    metadata_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_jackal_shadow_batches_recorded_at
    ON jackal_shadow_batches(recorded_at);
```

Schema parity check:
- No explicit foreign key exists.
- SQL is moved without modification.

#### `jackal_live_events`

Source of truth:
- Code ref: `orca/state.py:237-255`
- Audit refs: `01-db-audit.md:135-159`, `01-db-audit.md:247-248`, `01-db-audit.md:513-515`, `01-db-audit.md:600-610`, `01-db-audit.md:806`

Existing SQL:

```sql
CREATE TABLE IF NOT EXISTS jackal_live_events (
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
);

CREATE INDEX IF NOT EXISTS idx_jackal_live_events_lookup
    ON jackal_live_events(event_type, event_timestamp);

CREATE INDEX IF NOT EXISTS idx_jackal_live_events_pending
    ON jackal_live_events(event_type, outcome_checked, alerted, is_entry);
```

Schema parity check:
- No explicit foreign key exists.
- The two indexes move with the table definition.

#### `jackal_weight_snapshots`

Source of truth:
- Code ref: `orca/state.py:257-265`
- Audit refs: `01-db-audit.md:112-133`, `01-db-audit.md:247-252`, `01-db-audit.md:510-512`, `01-db-audit.md:631-633`, `01-db-audit.md:807`

Existing SQL:

```sql
CREATE TABLE IF NOT EXISTS jackal_weight_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    weights_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jackal_weight_snapshots_latest
    ON jackal_weight_snapshots(captured_at DESC);
```

Schema parity check:
- No explicit foreign key exists.
- `captured_at DESC` index must stay unchanged because the current latest-snapshot query orders on that column.

#### `jackal_cooldowns`

Source of truth:
- Code ref: `orca/state.py:267-282`
- Audit refs: `01-db-audit.md:232-234`, `01-db-audit.md:635-644`, `01-db-audit.md:808`

Existing SQL:

```sql
CREATE TABLE IF NOT EXISTS jackal_cooldowns (
    cooldown_key TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    signal_family TEXT,
    cooldown_at TEXT NOT NULL,
    quality_score REAL,
    last_override_at TEXT,
    override_reason TEXT,
    override_quality REAL,
    override_count INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jackal_cooldowns_lookup
    ON jackal_cooldowns(ticker, signal_family, cooldown_at DESC);
```

Schema parity check:
- No explicit foreign key exists.
- This table moves unchanged together with both read and write APIs.

#### `jackal_recommendations`

Source of truth:
- Code ref: `orca/state.py:284-299`
- Audit refs: `01-db-audit.md:160-178`, `01-db-audit.md:247-248`, `01-db-audit.md:516-518`, `01-db-audit.md:612-621`, `01-db-audit.md:809`

Existing SQL:

```sql
CREATE TABLE IF NOT EXISTS jackal_recommendations (
    recommendation_id TEXT PRIMARY KEY,
    external_key TEXT NOT NULL UNIQUE,
    ticker TEXT NOT NULL,
    market TEXT,
    recommended_at TEXT NOT NULL,
    analysis_date TEXT NOT NULL,
    outcome_checked INTEGER NOT NULL DEFAULT 0,
    outcome_pct REAL,
    outcome_correct INTEGER,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jackal_recommendations_lookup
    ON jackal_recommendations(recommended_at DESC, outcome_checked, ticker);
```

Schema parity check:
- No explicit foreign key exists.
- Existing lookup and replay semantics depend on the current composite index order.

#### `jackal_accuracy_projection`

Source of truth:
- Code ref: `orca/state.py:301-318`
- Audit refs: `01-db-audit.md:121-133`, `01-db-audit.md:207-208`, `01-db-audit.md:254-268`, `01-db-audit.md:522`, `01-db-audit.md:623-633`, `01-db-audit.md:810`

Existing SQL:

```sql
CREATE TABLE IF NOT EXISTS jackal_accuracy_projection (
    projection_id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL,
    source TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    family TEXT NOT NULL,
    scope TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    correct REAL,
    total REAL,
    accuracy REAL,
    metrics_json TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE(snapshot_id, family, scope, entity_key)
);

CREATE INDEX IF NOT EXISTS idx_jackal_accuracy_projection_lookup
    ON jackal_accuracy_projection(family, scope, captured_at DESC, entity_key);
```

Companion view requirement:
- `list_jackal_accuracy_projection(current_only=True)` uses `jackal_accuracy_current` by default.
- Code refs: `orca/state.py:320-430` and `orca/state.py:1992-2018`
- Audit refs: `01-db-audit.md:266-268`, `01-db-audit.md:623-633`
- Phase 5-C must create the existing view in `jackal_state.db` together with this table, even though the Path B ownership count still refers to 7 tables.

Schema parity check:
- No explicit foreign key exists.
- The unique constraint and lookup index move unchanged.

### 1.2. `orca_state.db` tables that remain in place

Path B keeps the remaining `11` tables in `orca_state.db`.

Category 2: ORCA-only
- `runs`
- `predictions`
- `outcomes`
- `backtest_state`

Category 3: Shared
- `backtest_sessions`
- `backtest_daily_results`
- `backtest_pick_results`
- `candidate_registry`
- `candidate_outcomes`

Category 4: Ambiguous
- `candidate_reviews`
- `candidate_lessons`

Audit basis:
- Category 2 refs: `01-db-audit.md:646-690`
- Category 3 refs: `01-db-audit.md:692-747`
- Category 4 refs: `01-db-audit.md:749-781`
- Path decision refs: `02-path-decision.md`, Section 3

Phase 5 handling note:
- These tables are explicitly out of the physical move scope.
- Their ownership and redesign questions are deferred to Phase 6.
- Phase 5-C must not alter their schema, file placement, or caller contracts.

### 1.3. Cross-DB FK handling

Confirmed from `01-db-audit.md:317-349`:
- `candidate_reviews.run_id -> runs.run_id`
- `candidate_reviews.candidate_id -> candidate_registry.candidate_id`
- `candidate_outcomes.candidate_id -> candidate_registry.candidate_id`
- `candidate_lessons.outcome_id -> candidate_outcomes.outcome_id`
- `candidate_lessons.candidate_id -> candidate_registry.candidate_id`
- `predictions.run_id -> runs.run_id`
- `outcomes.prediction_id -> predictions.prediction_id`
- `backtest_state.session_id -> backtest_sessions.session_id`
- `backtest_daily_results.session_id -> backtest_sessions.session_id`
- `backtest_pick_results.session_id -> backtest_sessions.session_id`

Category 1 cross-DB FK check:
- `01-db-audit.md:351-355` explicitly states there are no explicit FK edges from any `jackal_*` table.
- No Category 1 table has an FK to ORCA-only, shared, or ambiguous tables.

Design conclusion:
- Path B introduces no explicit cross-database FK problem.
- All existing explicit FK chains remain inside `orca_state.db`.
- The only cross-database coupling in Phase 5 is runtime side effect behavior, not SQLite FK enforcement.

## Section 2: Routing Map

### 2.1. Function -> DB assignment

Design note:
- The full `orca/state.py` function inventory is mapped below.
- Pure helpers are listed as `None (helper)`.
- Public bootstrap/connect helpers are listed separately because they mediate both DBs in the Phase 5 design.
- Audit references are mandatory anchors back to `01-db-audit.md`, even when a helper is only covered indirectly by the shared-adapter blocker.

#### Helper and bootstrap functions

| Function | Target DB | Audit refs | Code refs | Notes |
| --- | --- | --- | --- | --- |
| `_now` | `None (helper)` | `01-db-audit.md:877-881` | `orca/state.py:19` | Timestamp helper only. |
| `_now_iso` | `None (helper)` | `01-db-audit.md:877-881` | `orca/state.py:23` | ISO timestamp helper only. |
| `_single_line_message` | `None (helper)` | `01-db-audit.md:877-881` | `orca/state.py:27` | Health message formatting only. |
| `_record_health_event` | `None (in-memory queue)` | `01-db-audit.md:873-891` | `orca/state.py:34` | Records health events in module memory; no SQLite write. |
| `clear_health_events` | `None (in-memory queue)` | `01-db-audit.md:873-891` | `orca/state.py:50` | Clears in-memory queue only. |
| `drain_health_events` | `None (in-memory queue)` | `01-db-audit.md:873-891` | `orca/state.py:54` | Drains in-memory queue only. |
| `_json` | `None (helper)` | `01-db-audit.md:241-280` | `orca/state.py:60` | JSON serialization helper only. |
| `_candidate_systems` | `None (helper)` | `01-db-audit.md:241-280` | `orca/state.py:66` | Verification/system normalization helper only. |
| `_connect` | `Both (routing helper in Phase 5-C)` | `01-db-audit.md:877-881` | `orca/state.py:70`, `orca/paths.py:13-14` | Current implementation always uses `STATE_DB_FILE`; Phase 5-C replaces this with owner-specific connection helpers. |
| `init_state_db` | `Both` | `01-db-audit.md:272-278`, `01-db-audit.md:877-881` | `orca/state.py:80` | Public bootstrap entrypoint remains, but internally splits by DB owner. |
| `_jackal_event_external_key` | `None (helper)` | `01-db-audit.md:247-268`, `01-db-audit.md:877-881` | `orca/state.py:1344` | Generates deterministic event keys only. |
| `_metric_number` | `None (helper)` | `01-db-audit.md:247-268`, `01-db-audit.md:623-633` | `orca/state.py:1789` | Projection metric normalization only. |
| `_append_accuracy_row` | `None (helper)` | `01-db-audit.md:247-268`, `01-db-audit.md:623-633` | `orca/state.py:1798` | Builds projection rows in memory only. |
| `_build_jackal_accuracy_projection_rows` | `None (row builder)` | `01-db-audit.md:247-268`, `01-db-audit.md:623-633` | `orca/state.py:1832` | Returns rows for later DB sync; no direct DB access. |
| `_to_float` | `None (helper)` | `01-db-audit.md:724-777`, `01-db-audit.md:877-881` | `orca/state.py:2069` | Candidate normalization helper only. |
| `_to_int_flag` | `None (helper)` | `01-db-audit.md:724-777`, `01-db-audit.md:877-881` | `orca/state.py:2078` | Candidate normalization helper only. |
| `_candidate_external_key` | `None (helper)` | `01-db-audit.md:724-747` | `orca/state.py:2084` | Candidate key builder only. |
| `_candidate_status` | `None (helper)` | `01-db-audit.md:724-747` | `orca/state.py:2102` | Candidate status derivation only. |
| `_candidate_quality_score` | `None (helper)` | `01-db-audit.md:724-747` | `orca/state.py:2114` | Candidate payload extraction only. |
| `_candidate_signal_family` | `None (helper)` | `01-db-audit.md:724-777` | `orca/state.py:2122` | Candidate signal-family derivation only. |
| `_candidate_raw_signal_family` | `None (helper)` | `01-db-audit.md:724-777` | `orca/state.py:2137` | Candidate raw family extraction only. |
| `_candidate_signals_fired` | `None (helper)` | `01-db-audit.md:724-777` | `orca/state.py:2145` | Candidate payload extraction only. |
| `_candidate_reference_price` | `None (helper)` | `01-db-audit.md:724-747` | `orca/state.py:2153` | Candidate payload extraction only. |

#### ORCA-only and shared-cluster functions that stay on `orca_state.db`

| Function | Target DB | Audit refs | Code refs | Notes |
| --- | --- | --- | --- | --- |
| `start_run` | `orca_state.db` | `01-db-audit.md:648-658` | `orca/state.py:434`, `orca/run_cycle.py:183` | Writes `runs`. |
| `finish_run` | `orca_state.db` | `01-db-audit.md:648-658` | `orca/state.py:450` | Updates `runs`; not listed separately in the audit, but belongs to the same ORCA-only lifecycle. |
| `_upsert_prediction` | `orca_state.db` | `01-db-audit.md:659-679` | `orca/state.py:497` | Internal helper for `predictions`. |
| `record_report_predictions` | `orca_state.db` | `01-db-audit.md:659-679` | `orca/state.py:580`, `orca/persist.py:97` | Writes `predictions`. |
| `resolve_verification_outcomes` | `orca_state.db` | `01-db-audit.md:670-679` | `orca/state.py:651`, `orca/analysis.py:1205` | Writes `outcomes` and updates `predictions`. |
| `start_backtest_session` | `orca_state.db` | `01-db-audit.md:681-689`, `01-db-audit.md:694-702` | `orca/state.py:763` | Shared backtest table stays in ORCA DB during Path B. |
| `load_backtest_state` | `orca_state.db` | `01-db-audit.md:681-690` | `orca/state.py:783`, `orca/backtest.py:745` | `backtest_state` remains ORCA-only. |
| `save_backtest_state` | `orca_state.db` | `01-db-audit.md:681-690` | `orca/state.py:802`, `orca/backtest.py:754` | `backtest_state` remains ORCA-only. |
| `record_backtest_day` | `orca_state.db` | `01-db-audit.md:704-712` | `orca/state.py:818` | Shared backtest table stays in ORCA DB during Path B. |
| `finish_backtest_session` | `orca_state.db` | `01-db-audit.md:694-722` | `orca/state.py:856` | Session metadata remains in ORCA DB during Path B. |
| `get_latest_backtest_session` | `orca_state.db` | `01-db-audit.md:694-722` | `orca/state.py:889` | Reads shared backtest cluster, still stored in ORCA DB. |
| `list_backtest_sessions` | `orca_state.db` | `01-db-audit.md:694-722` | `orca/state.py:942` | Reads shared backtest cluster, still stored in ORCA DB. |
| `list_backtest_days` | `orca_state.db` | `01-db-audit.md:704-712` | `orca/state.py:998` | Reads shared backtest cluster, still stored in ORCA DB. |
| `record_backtest_pick_results` | `orca_state.db` | `01-db-audit.md:714-722` | `orca/state.py:1039` | Shared backtest table stays in ORCA DB during Path B. |
| `_upsert_candidate_outcome` | `orca_state.db` | `01-db-audit.md:737-747` | `orca/state.py:2161` | Internal helper for shared candidate graph. |
| `_sync_candidate_outcomes` | `orca_state.db` | `01-db-audit.md:737-747` | `orca/state.py:2214` | Shared candidate graph remains in ORCA DB. |
| `_latest_candidate_review` | `orca_state.db` | `01-db-audit.md:751-761` | `orca/state.py:2327` | Reads ambiguous candidate review table that stays in ORCA DB. |
| `_latest_candidate_outcome` | `orca_state.db` | `01-db-audit.md:737-747` | `orca/state.py:2363` | Reads shared candidate outcome table that stays in ORCA DB. |
| `_sync_candidate_probability_lesson` | `orca_state.db` | `01-db-audit.md:767-777` | `orca/state.py:2405`, `jackal/probability.py:13` | Candidate lesson system remains in ORCA DB during Path B. |
| `record_candidate` | `orca_state.db` | `01-db-audit.md:256-259`, `01-db-audit.md:535-550`, `01-db-audit.md:724-747`, `01-db-audit.md:819-833` | `orca/state.py:2470` | Shared candidate spine; called by JACKAL-origin paths. |
| `list_candidates` | `orca_state.db` | `01-db-audit.md:269`, `01-db-audit.md:724-735` | `orca/state.py:2588`, `orca/analysis.py:679`, `jackal/scanner.py:135` | Shared read API used by both systems. |
| `list_candidate_outcomes` | `orca_state.db` | `01-db-audit.md:737-747` | `orca/state.py:2682` | Shared candidate graph remains in ORCA DB. |
| `list_candidate_reviews` | `orca_state.db` | `01-db-audit.md:270`, `01-db-audit.md:751-761` | `orca/state.py:2724` | Ambiguous table still lives in ORCA DB during Path B. |
| `summarize_candidate_probabilities` | `orca_state.db` | `01-db-audit.md:767-777` | `orca/state.py:2775`, `jackal/probability.py:13` | Candidate lesson aggregation stays with ORCA DB during Path B. |
| `backfill_candidate_signal_families` | `orca_state.db` | `01-db-audit.md:272-280` | `orca/state.py:2923` | Migration-only function; not part of the runtime loop. |
| `record_candidate_review` | `orca_state.db` | `01-db-audit.md:258`, `01-db-audit.md:724-735`, `01-db-audit.md:751-761` | `orca/state.py:2995`, `orca/analysis.py:825` | Writes `candidate_reviews` and updates `candidate_registry.orca_alignment`. |
| `record_candidate_lesson` | `orca_state.db` | `01-db-audit.md:259`, `01-db-audit.md:767-777` | `orca/state.py:3078` | Writes `candidate_lessons`. |

#### JACKAL-owned functions that route to `jackal_state.db`

| Function | Target DB | Audit refs | Code refs | Notes |
| --- | --- | --- | --- | --- |
| `record_jackal_shadow_signal` | `jackal_state.db` | `01-db-audit.md:247-250`, `01-db-audit.md:504-506`, `01-db-audit.md:803-804` | `orca/state.py:1086`, `jackal/scanner.py:1570` | Primary write to JACKAL DB, followed by candidate side effect in ORCA DB. |
| `list_pending_jackal_shadow_signals` | `jackal_state.db` | `01-db-audit.md:262`, `01-db-audit.md:378-379` | `orca/state.py:1144`, `jackal/evolution.py:232` | Reads pending shadow rows from JACKAL DB. |
| `resolve_jackal_shadow_signal` | `jackal_state.db` | `01-db-audit.md:250`, `01-db-audit.md:263`, `01-db-audit.md:543` | `orca/state.py:1201`, `jackal/evolution.py:388` | Primary update in JACKAL DB, followed by candidate side effect in ORCA DB. |
| `record_jackal_shadow_accuracy_batch` | `jackal_state.db` | `01-db-audit.md:251`, `01-db-audit.md:507-509`, `01-db-audit.md:805` | `orca/state.py:1251`, `jackal/evolution.py:913` | Writes batch summary only. |
| `list_jackal_shadow_batches` | `jackal_state.db` | `01-db-audit.md:266`, `01-db-audit.md:365-366` | `orca/state.py:1311`, `orca/research_report.py:237` | Reporting read API; still owned by JACKAL DB. |
| `sync_jackal_live_events` | `jackal_state.db` | `01-db-audit.md:248`, `01-db-audit.md:513-515`, `01-db-audit.md:600-610`, `01-db-audit.md:806` | `orca/state.py:1353`, `jackal/hunter.py:1474`, `jackal/scanner.py:1563`, `jackal/tracker.py:516`, `jackal/evolution.py:365` | Primary write to JACKAL DB, followed by candidate side effect in ORCA DB. |
| `list_jackal_live_events` | `jackal_state.db` | `01-db-audit.md:264`, `01-db-audit.md:378`, `01-db-audit.md:387` | `orca/state.py:1422`, `jackal/evolution.py:206`, `jackal/tracker.py:348` | Read API only. |
| `record_jackal_weight_snapshot` | `jackal_state.db` | `01-db-audit.md:119-126`, `01-db-audit.md:252`, `01-db-audit.md:510-512`, `01-db-audit.md:807` | `orca/state.py:1455`, `jackal/hunter.py:1542`, `jackal/tracker.py:526`, `jackal/evolution.py:1006` | Writes JACKAL learning state. |
| `load_latest_jackal_weight_snapshot` | `jackal_state.db` | `01-db-audit.md:120`, `01-db-audit.md:265`, `01-db-audit.md:133` | `orca/state.py:1481`, `jackal/adapter.py:39`, `jackal/core.py:105`, `jackal/scanner.py:321`, `jackal/tracker.py:383`, `jackal/evolution.py:962` | Read API only. |
| `load_jackal_cooldown_state` | `jackal_state.db` | `01-db-audit.md:635-644` | `orca/state.py:1500`, `jackal/scanner.py:333` | Read API for JACKAL-only cooldown support table. |
| `sync_jackal_cooldown_state` | `jackal_state.db` | `01-db-audit.md:635-644`, `01-db-audit.md:808` | `orca/state.py:1537`, `jackal/scanner.py:346` | Writes JACKAL-only cooldown support table. |
| `sync_jackal_recommendations` | `jackal_state.db` | `01-db-audit.md:253`, `01-db-audit.md:516-518`, `01-db-audit.md:612-621`, `01-db-audit.md:809` | `orca/state.py:1701`, `jackal/scanner.py:363`, `jackal/evolution.py:524` | Writes recommendation history only. |
| `list_jackal_recommendations` | `jackal_state.db` | `01-db-audit.md:266`, `01-db-audit.md:381`, `01-db-audit.md:384` | `orca/state.py:1761`, `jackal/evolution.py:451`, `jackal/scanner.py:350` | Read API only. |
| `sync_jackal_accuracy_projection` | `jackal_state.db` | `01-db-audit.md:254`, `01-db-audit.md:522`, `01-db-audit.md:623-633`, `01-db-audit.md:810` | `orca/state.py:1938` | Writes derived rows into JACKAL DB only. |
| `list_jackal_accuracy_projection` | `jackal_state.db` | `01-db-audit.md:267`, `01-db-audit.md:623-633` | `orca/state.py:1992`, `orca/research_report.py:165` | Read API uses `jackal_accuracy_current` view by default. |
| `rebuild_latest_jackal_accuracy_projection` | `jackal_state.db` | `01-db-audit.md:268`, `01-db-audit.md:623-633` | `orca/state.py:2044`, `orca/research_report.py:164` | Reads latest snapshot and rewrites projection rows inside JACKAL DB only. |

### 2.2. Connection management

Current state:
- `orca/state.py:13` imports `STATE_DB_FILE` only.
- `orca/state.py:70-72` hardcodes `_connect()` to `sqlite3.connect(STATE_DB_FILE, timeout=30)`.
- Every persistence function currently goes through `_connect()`.

Design objective for Phase 5-C:
- Keep all public function signatures unchanged.
- Replace the single hardcoded connect path with owner-specific connection helpers.
- Preserve `sqlite3.Row` row factory and current timeout behavior.

Design sketch:

```python
# orca/paths.py
STATE_DB_FILE = DATA_DIR / "orca_state.db"
JACKAL_DB_FILE = DATA_DIR / "jackal_state.db"

# orca/state.py
def _connect_orca() -> sqlite3.Connection:
    STATE_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(STATE_DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def _connect_jackal() -> sqlite3.Connection:
    JACKAL_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(JACKAL_DB_FILE, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
```

Routing rule:
- ORCA-only, shared, and ambiguous tables continue to use `_connect_orca()`.
- Category 1 JACKAL tables use `_connect_jackal()`.
- `init_state_db()` becomes an orchestration wrapper over owner-specific bootstrap helpers.

Caller-impact rule:
- External callers in `jackal/*` and `orca/*` keep importing the same function names.
- No function signature changes are required.
- No caller-side routing logic is introduced.

### 2.3. `paths.py` and bootstrap impact range

Files directly affected in Phase 5-C:
- `orca/paths.py`
- `orca/state.py`

Why:
- `orca/paths.py` currently defines only `STATE_DB_FILE`.
- `orca/state.py` currently centralizes both schema bootstrap and all SQLite connects.

Files intentionally not modified in Phase 5-B:
- `jackal/*.py` callers
- `.github/workflows/*.yml`
- live DB files

## Section 3: 2-Phase Write Analysis

### 3.1. 2-phase write function inventory

These are the only confirmed cross-database side-effect paths found in the current code.

| Function | Primary DB | Side-effect DB | Side effect | Criticality |
| --- | --- | --- | --- | --- |
| `sync_jackal_live_events` | `jackal_state.db` | `orca_state.db` | Calls `record_candidate()` for each synced event | `HIGH` |
| `record_jackal_shadow_signal` | `jackal_state.db` | `orca_state.db` | Calls `record_candidate()` after insert/upsert | `HIGH` |
| `resolve_jackal_shadow_signal` | `jackal_state.db` | `orca_state.db` | Calls `record_candidate()` after resolve update | `HIGH` |

Evidence:
- Audit refs: `01-db-audit.md:504-515`, `01-db-audit.md:535-545`
- Code refs: `orca/state.py:1134`, `orca/state.py:1242`, `orca/state.py:1412`

Stop-condition check:
- Count confirmed: `3`
- This does not exceed the stated stop condition threshold.

### 3.2. Failure mode analysis

#### `sync_jackal_live_events()`

Execution order from code:
1. Build `candidate_jobs` in memory.
2. Upsert each event row into `jackal_live_events`.
3. Exit JACKAL DB transaction scope.
4. Iterate `candidate_jobs` and call `record_candidate()` into `orca_state.db`.

Code refs:
- `orca/state.py:1353-1419`

Failure modes:
- Primary success, secondary failure:
  - `jackal_live_events` row exists in `jackal_state.db`.
  - `candidate_registry` and derived `candidate_outcomes` rows are missing in `orca_state.db`.
  - Current code has no retry queue for missed candidate propagation.
  - Resulting inconsistency:
    - JACKAL event history says the event happened.
    - ORCA candidate spine never sees it.
  - Classification: `critical failure mode`
- Primary failure, secondary not attempted:
  - No live event is stored.
  - No candidate side effect occurs because candidate propagation happens after the JACKAL DB scope.
  - Resulting inconsistency:
    - none across DBs
    - event is simply absent
  - Classification: `non-critical data loss in primary`
- Both fail:
  - No data stored in either DB.
  - Classification: `non-critical cross-DB consistency`, `critical operational loss`

#### `record_jackal_shadow_signal()`

Execution order from code:
1. Insert or reuse `shadow_id` in `jackal_shadow_signals`.
2. Exit JACKAL DB transaction scope.
3. Call `record_candidate()` into `orca_state.db`.

Code refs:
- `orca/state.py:1086-1141`

Failure modes:
- Primary success, secondary failure:
  - `jackal_shadow_signals` row exists.
  - `candidate_registry` row is absent.
  - Later shadow scoring can still proceed because it reads the JACKAL table directly.
  - ORCA candidate-centric follow-up is missing.
  - Classification: `critical failure mode`
- Primary failure, secondary not attempted:
  - No shadow row exists.
  - No candidate row exists.
  - Classification: `non-critical cross-DB consistency`, `critical operational loss`
- Both fail:
  - No stored evidence of the skipped signal.
  - Classification: `non-critical cross-DB consistency`, `critical operational loss`

#### `resolve_jackal_shadow_signal()`

Execution order from code:
1. Read current `payload_json` from `jackal_shadow_signals`.
2. Update `status`, `payload_json`, `outcome_json`, `resolved_at` in `jackal_shadow_signals`.
3. Exit JACKAL DB transaction scope.
4. If `source_external_key` exists, call `record_candidate()` into `orca_state.db`.

Code refs:
- `orca/state.py:1201-1248`

Failure modes:
- Primary success, secondary failure:
  - Resolved shadow outcome exists in `jackal_state.db`.
  - Candidate graph does not receive the resolved payload/outcome snapshot.
  - ORCA-side candidate follow-up remains stale.
  - Classification: `critical failure mode`
- Primary failure, secondary not attempted:
  - Shadow remains unresolved in JACKAL DB.
  - No candidate refresh occurs.
  - Classification: `non-critical cross-DB consistency`, `critical operational loss`
- Both fail:
  - No progress on either side.
  - Classification: `non-critical cross-DB consistency`, `critical operational loss`

Critical failure mode count in this section:
- `3`
- One per 2-phase function, each defined as `primary success + secondary propagation failure`.

### 3.3. Mitigation strategy

Phase 5-C design target:

1. Primary DB write first.
2. If primary write fails:
   - stop immediately
   - do not attempt the secondary write
   - propagate or record the primary failure through the existing caller error path
3. If primary write succeeds:
   - attempt secondary write
4. If secondary write fails:
   - record a health event
   - do not roll back the primary write
   - do not retry inline
   - do not raise a new exception after the primary commit has succeeded

Policy summary:
- Primary DB consistency is strict.
- Secondary propagation is best-effort.
- Cross-file atomic transaction is explicitly out of scope because the write spans two SQLite files.

Why this policy fits Path B:
- Path B is a bounded separation, not a candidate-spine redesign.
- `01-db-audit.md:877-891` already identifies the shared candidate cluster as a blocker deferred to a later phase.
- The chosen policy protects JACKAL learning persistence first, which is the direct Phase 5 objective.

Health event design note for Phase 5-C:
- Secondary propagation failures should emit a health event instead of silently disappearing.
- The event should include:
  - function name
  - source primary record identifier
  - secondary target function
  - exception message

### 3.4. Phase 6 preview

These are reference-only directions, not Phase 5 work items:
- Event-first architecture:
  - JACKAL records only JACKAL-owned events.
  - ORCA consumes those events asynchronously and materializes candidate rows.
- Shared-domain architecture:
  - Candidate graph remains in a shared store.
  - Adapter ownership is split without changing the single-store candidate model.

Why this preview matters now:
- The three 2-phase write functions exist only because the candidate graph is still materialized inline.
- Phase 5 accepts that temporary coupling.
- Phase 6 is where that coupling can be redesigned.

## Section 4: Bootstrap & Initialization

### 4.1. `init_state_db()` split design

Current state:
- `init_state_db()` creates every table, index, and view in a single `STATE_DB_FILE`.
- Code ref: `orca/state.py:80-430`
- Audit refs: `01-db-audit.md:272-278`, `01-db-audit.md:877-881`

Phase 5-C design:

```python
def init_state_db() -> None:
    """Initialize both orca_state.db and jackal_state.db."""
    _init_orca_db()
    _init_jackal_db()

def _init_orca_db() -> None:
    # Create ORCA-only tables.
    # Create shared tables.
    # Create ambiguous tables.

def _init_jackal_db() -> None:
    # Create Category 1 tables.
    # Create jackal_accuracy_current view.
```

Chosen public contract:
- Keep `init_state_db()` as the public compatibility entrypoint.
- Introduce private owner-specific bootstrap helpers.
- Do not change existing external imports.

Chosen bootstrap ordering:
1. `_init_orca_db()`
2. `_init_jackal_db()`

Rationale:
- ORCA-owned and shared tables currently anchor more explicit FK chains.
- Candidate side-effect functions still land in ORCA DB.
- Initializing ORCA first preserves the existing dominant bootstrap dependency order.

### 4.2. First-run behavior

First run after Phase 5-C:
- `data/jackal_state.db` does not exist yet.
- `init_state_db()` creates it lazily on first call.
- Category 1 tables begin empty.

Why empty-start is acceptable:
- `01-db-audit.md:13-17` and `01-db-audit.md:302-310` establish that all 5 Tier 1 core tables are at `COUNT = 0`.
- `01-db-audit.md:207-208` also shows `jackal_accuracy_projection` and `jackal_cooldowns` at `COUNT = 0`.
- Therefore, there is no historical Category 1 payload that must be copied before enabling the new file.

Operational implication:
- The first meaningful proof of success is not migration correctness.
- It is post-deploy accumulation in scheduled runs.

### 4.3. `backfill_candidate_signal_families()` handling

Current classification:
- Migration-only
- ORCA DB only

Evidence:
- Audit refs: `01-db-audit.md:272-280`, `01-db-audit.md:305`
- Code ref: `orca/state.py:2923`

Phase 5 rule:
- No behavior change.
- No relocation.
- No caller change.

Why:
- It operates on `candidate_registry`, which remains in `orca_state.db`.
- It is not part of the scheduled runtime loop.
- It does not unblock Category 1 JACKAL persistence.

## Section 5: Migration Strategy

### 5.1. Data migration necessity

Current counts from Phase 5-A snapshot:
- `jackal_shadow_signals = 0`
- `jackal_shadow_batches = 0`
- `jackal_weight_snapshots = 0`
- `jackal_live_events = 0`
- `jackal_recommendations = 0`
- `jackal_accuracy_projection = 0`
- `jackal_cooldowns = 0`

Evidence:
- Audit refs: `01-db-audit.md:13-17`, `01-db-audit.md:207-208`, `01-db-audit.md:302-310`

Migration conclusion:
- Existing row migration is not required.
- Path B can start from empty Category 1 tables in `jackal_state.db`.
- Phase 5-C therefore needs schema bootstrap and routing changes only.

### 5.2. Existing Category 1 tables inside `orca_state.db`

Path B cleanup rule:
- Do not physically drop the old Category 1 tables from `orca_state.db` during initial rollout.

Why:
- Keeping them preserves rollback optionality.
- The old file remains a fallback reference if Phase 5-C or 5-D must be reverted.
- Physical deletion is not required to prove the new routing path works.

Phase 5-E treatment:
- Mark them as deprecated by routing, not by DDL removal.
- The old tables become inert because all new writes go to `jackal_state.db`.
- Physical drop can be deferred to a later hygiene change after stable observation.

### 5.3. Migration runbook outline

Phase 5-C implementation sequence:
1. Add `JACKAL_DB_FILE` path constant.
2. Add owner-specific connect helpers.
3. Split bootstrap into ORCA and JACKAL schema groups.
4. Repoint Category 1 read/write functions.
5. Leave shared and ORCA-only functions untouched.

Phase 5-D integration sequence:
1. Preserve `data/jackal_state.db` in the relevant workflows.
2. Confirm scheduled runs reuse the same file instead of discarding it.

Phase 5-E cleanup sequence:
1. Verify live accumulation in `jackal_live_events` or `jackal_shadow_signals`.
2. Keep the old Category 1 tables present but deprecated.
3. Postpone physical removal.

## Section 6: Rollback Plan

### 6.1. If Phase 5-C fails

Symptoms:
- Unit tests fail.
- Local bootstrap fails.
- Routing sends data to the wrong file.

Response:
- Revert the Phase 5-C code change.
- Return to the original single-DB code path.

Rollback properties:
- Low risk.
- No historical Category 1 data needs to be preserved because the target tables are empty at baseline.

### 6.2. If Phase 5-D fails

Symptoms:
- Scheduled workflows fail.
- `jackal_state.db` is not preserved across GitHub Actions runs.
- Scheduled accumulation still resets.

Response:
- Revert the workflow change.
- Keep the Python dual-DB support available locally.
- Treat scheduled runs as still unresolved until workflow storage is fixed.

Important nuance:
- Reverting workflow changes alone does not delete dual-DB support from Python.
- It only prevents CI from preserving the new JACKAL-owned file.

Rollback properties:
- Medium risk.
- Local/manual runs may still produce `jackal_state.db`.
- Scheduled retention remains the deciding factor for production-like validation.

### 6.3. If the full Phase 5 rollout fails

Symptoms:
- Path B code lands.
- Workflow retention lands.
- Operational inconsistency or persistent missing data is observed afterward.

Response:
- Revert the Phase 5 commits.
- Ignore or remove `data/jackal_state.db`.
- Return to the pre-Phase 5 persistence model.

Risk:
- Medium to high.

Data-loss note:
- Any Category 1 data accumulated only in `jackal_state.db` during the failed rollout window would be lost after full rollback.
- That is acceptable only because Path B is intended to be validated quickly after rollout.

## Section 7: Phase 5-C work items preview

### 7.1. `paths.py` change

Planned addition:

```python
JACKAL_DB_FILE = DATA_DIR / "jackal_state.db"
```

Impact:
- Single new path constant.
- No existing path constant removal.

### 7.2. `orca/state.py` change

Planned work:
- Add `_connect_orca()`
- Add `_connect_jackal()`
- Split `init_state_db()` internally
- Move Category 1 schema bootstrap into JACKAL bootstrap
- Move `jackal_accuracy_current` view bootstrap with `jackal_accuracy_projection`
- Route Category 1 functions to the JACKAL connect helper
- Keep ORCA/shared/ambiguous functions on the ORCA connect helper
- Add the shared-adapter note from `02-path-decision.md`

Unchanged contracts:
- Public function names
- Public function signatures
- Caller import paths

### 7.3. Test targets

Phase 5-C verification targets:
- `init_state_db()` creates both DB files
- Category 1 tables exist in `jackal_state.db`
- Category 2, 3, and 4 tables still exist in `orca_state.db`
- `record_jackal_shadow_signal()` writes to JACKAL DB and still triggers candidate side effect into ORCA DB
- `sync_jackal_live_events()` writes to JACKAL DB and still triggers candidate side effect into ORCA DB
- `record_report_predictions()` still writes only to ORCA DB
- `summarize_candidate_probabilities()` still reads only from ORCA DB
- `rebuild_latest_jackal_accuracy_projection()` reads and writes only inside JACKAL DB

### 7.4. Workflow design dependency

Phase 5-C alone is not enough.

Reason:
- The code can route correctly and still fail to accumulate useful learning state if scheduled workflows discard `jackal_state.db`.

Evidence:
- Audit refs: `01-db-audit.md:51-57`, `01-db-audit.md:302-311`

Phase link:
- Phase 5-D is the first point where scheduled accumulation can become observable.

## Section 8: Open Questions

### Q1. Connection pooling

Current state:
- Every function uses connect -> execute -> close.

Design options:
- Keep the current pattern.
- Introduce pooling or long-lived connections.

Phase 5-B default:
- Keep the current pattern.

Reason:
- The current code already uses this lifecycle consistently.
- Pooling is a separate performance optimization, not a prerequisite for Path B correctness.

Resolution needed before Phase 5-C:
- `No`
- Default path is already defined: keep current behavior.

### Q2. 2-phase transaction ordering

Decision to make:
- Confirm `primary first, secondary best-effort` as the Path B rule.
- Or require stricter failure semantics.

Phase 5-B default:
- `primary first, secondary best-effort`

Why this still remains open:
- This is the main correctness tradeoff of Path B.
- Owner confirmation is valuable because it determines how much inconsistency risk is accepted in exchange for bounded implementation scope.

Resolution needed before Phase 5-C:
- `Yes`

### Q3. Secondary-write error propagation

Decision to make:
- If secondary propagation fails after a successful primary write, should the function:
  - raise,
  - swallow and log,
  - or log and return a partial-success contract?

Phase 5-B default:
- Log to health tracking and do not raise a new exception after the primary commit succeeds.

Why this still remains open:
- Caller-visible behavior matters for scheduled runs and future monitoring.
- The current code does not yet encode this policy explicitly.

Resolution needed before Phase 5-C:
- `Yes`

### Q4. `init_state_db()` idempotency and call pattern

Decision to make:
- Keep `init_state_db()` as a top-level compatibility wrapper only.
- Decide whether per-owner connect helpers should also ensure owner-specific bootstrap lazily.

Phase 5-B default:
- Keep `init_state_db()` public.
- Split internals by owner.
- Confirm idempotency with tests in Phase 5-C.

Why this still remains open:
- Current code calls `init_state_db()` broadly before many operations.
- The safest exact bootstrap trigger pattern should be confirmed before implementation.

Resolution needed before Phase 5-C:
- `Yes`
