# Phase 6 Design: candidate_registry Redesign
Date: `2026-04-23`
Authoring mode: `design analysis only`
Implementation status: `not started`
Decision state: `deferred to next session`
Primary scope: `candidate_registry / candidate_outcomes / candidate_reviews / candidate_lessons`
Primary code surface: `orca/state.py`
Primary runtime origins: `jackal/hunter.py`, `jackal/scanner.py`, `orca/analysis_review.py`
---
## Section 0: Meta
### 0.1 Purpose
This document is a Phase 6 input document.
It is not an implementation document.
It is not a migration execution checklist.
It does not choose a final design.
It exists so that a later implementation session can start from a stable inventory instead of re-discovering the current state.
The immediate design problem is the `candidate_*` cluster that Phase 5 explicitly deferred.
The cluster currently lives inside a shared persistence adapter in `orca/state.py`.
That arrangement was accepted as a bounded fix in Phase 5.
It was not accepted as the long-term architecture.
Evidence:
- `docs/phase5/02-path-decision.md:24-32`
- `docs/phase5/02-path-decision.md:90-97`
- `docs/analysis/2026-04-22_repository_review.md:805-812`
### 0.2 Non-goals
This document does not:
- apply a schema migration
- rename tables
- move data between databases
- change caller behavior
- remove the Phase 5 best-effort secondary write mitigation
- decide whether Option A, B, C, or D is final
- define downtime windows
- define production cutover dates
- change PR 1 to PR 5 contracts
- change workflow behavior
### 0.3 Why this is Phase 6 work
Phase 5 was intentionally scoped as bounded separation.
Only Category 1 JACKAL-only tables moved into `data/jackal_state.db`.
Category 3 shared tables and Category 4 ambiguous tables stayed in `data/orca_state.db`.
`candidate_registry` redesign and candidate cluster ownership were deferred.
`orca/state.py` was explicitly tolerated as a shared persistence adapter until a later phase.
Evidence:
- `docs/phase5/02-path-decision.md:24-27`
- `docs/phase5/02-path-decision.md:30-32`
- `docs/phase5/02-path-decision.md:93-94`
### 0.4 What changed after Phase 5
Phase 5 made the cross-database situation more observable but did not remove it.
Three JACKAL write paths now treat candidate propagation as a secondary write.
Those secondary writes are best-effort only.
If `jackal_state.db` succeeds and candidate propagation fails, the system keeps the JACKAL state and only logs a warning to `stderr`.
That means the persistence strategy is operationally stable but structurally incomplete.
Evidence:
- `docs/phase5/03-design.md:563-574`
- `orca/state.py:1227-1243`
- `orca/state.py:1352-1367`
- `orca/state.py:1540-1555`
- `docs/analysis/2026-04-22_repository_review.md:601-611`
### 0.5 Reader expectations
A later implementation session should be able to read this document and then:
- identify current owners and callers
- identify the specific cross-DB fan-in points
- compare restructuring options
- choose one option explicitly
- draft a migration plan without repeating the current-state audit
### 0.6 Required preconditions for the next session
Before implementing any redesign, the next session should confirm:
- current code still matches the inventory below
- P1 contract tests still pass
- P2 structure work has not reintroduced cycles or ownership ambiguity
- no additional candidate write entry points were added after `2026-04-23`
- the Phase 6 sibling design for shared adapter split either exists or is intentionally still absent
As of this writing, `docs/phase6/shared-adapter-split-design.md` does not exist in the repository.
Therefore any dependency statements involving that document are provisional.
### 0.7 Phase 6 question statement
The core Phase 6 question is:
Who should own the candidate spine after Phase 5, and how should runtime writes cross ORCA/JACKAL boundaries without relying on best-effort secondary propagation?
### 0.8 Terminology used in this document
`candidate spine`
- shorthand for `candidate_registry`, `candidate_outcomes`, `candidate_reviews`, `candidate_lessons`
`shared adapter`
- the current reality that `orca/state.py` exposes both ORCA-facing and JACKAL-facing persistence APIs
`fan-in`
- multiple runtime origins feeding the same write surface
`secondary propagation`
- a candidate write that happens after a primary JACKAL write already succeeded
`ownership`
- the logical domain that should be authoritative for a table family
`bounded separation`
- Phase 5 approach: move only the learning-state tables and defer ambiguous/shared clusters
### 0.9 Constraints that survive into Phase 6
Any redesign must preserve or explicitly accommodate:
- PR 1 health code contract
- PR 2 learning policy constants
- PR 3 thin `orca/main.py`
- PR 4 candidate review scorecard semantics
- PR 5 external-data visibility fields
- Phase 5 routing helpers and 2-phase write guarantees until redesign is complete
This matters most for PR 4 because candidate review scoring reads from the candidate cluster today.
Evidence:
- `orca/analysis_review.py:85`
- `orca/analysis_review.py:330-333`
- `orca/analysis_review.py:396-401`
- `orca/analysis_review.py:479`
### 0.10 Document output shape
This document provides:
- a current-state inventory
- a problem analysis
- four design options
- a side-by-side comparison
- an implementation outline for each option
- dependency sequencing notes
- explicit decisions left open
- measurable success criteria
It does not provide runnable migration SQL.
It does not provide a final ADR.
---
## Section 1: 현재 상태 전수 조사
### 1.1 Current candidate tables in the schema
Current schema location:
- `orca/state.py:268-353`
Tables:
- `candidate_registry`
- `candidate_reviews`
- `candidate_outcomes`
- `candidate_lessons`
Current physical database:
- `data/orca_state.db`
Reason:
- These tables were left in ORCA state under Phase 5 Path B.
Evidence:
- `docs/phase5/02-path-decision.md:24-27`
- `orca/state.py:268-353`
### 1.2 Table-by-table inventory
#### 1.2.1 `candidate_registry`
Schema block:
- `orca/state.py:268-299`
Role:
- canonical candidate row
- current aggregate status row
- stores source metadata, family metadata, outcome summary metadata, review alignment metadata
Notable columns visible in schema and upsert logic:
- `candidate_id`
- `source_system`
- `source_run_id`
- `external_key`
- `ticker`
- `status`
- `signal_family`
- `raw_signal_family`
- `signals_fired`
- `quality_score`
- `reference_price`
- `latest_outcome_status`
- `latest_outcome_return_pct`
- `latest_outcome_horizon_days`
- `latest_outcome_at`
- `orca_alignment`
- `reviewed_at`
- timestamps
Writers:
- `record_candidate()` in `orca/state.py:2609-2724`
- `record_candidate_review()` updates alignment fields in `orca/state.py:3134-3214`
Readers:
- `list_candidates()` in `orca/state.py:2727-2818`
- `summarize_candidate_probabilities()` joins registry in `orca/state.py:2914-3059`
- `list_candidate_reviews()` joins registry in `orca/state.py:2863-2911`
- ORCA review flow via `orca/analysis_review.py:330-333`
- JACKAL scanner candidate context via `jackal/scanner.py:151`
Observations:
- This is not a passive lookup table.
- It is both a write target and a denormalized aggregate row.
- It already mixes raw candidate identity with derived state.
#### 1.2.2 `candidate_reviews`
Schema block:
- `orca/state.py:300-320`
Role:
- stores ORCA-side review judgments over candidate rows
- stores review score, confidence label, action, alignment, comments, run linkage
Primary writer:
- `record_candidate_review()` in `orca/state.py:3134-3214`
Runtime origin:
- `orca/analysis_review.py:479`
Readers:
- `list_candidate_reviews()` in `orca/state.py:2863-2911`
- any later ORCA reporting that reads review history
Relationship to PR 4:
- `review_recent_candidates()` computes the PR 4 scorecard and then persists review results through `record_candidate_review()`
- score weights live in `orca/analysis_review.py:85`
- weighted score composition is at `orca/analysis_review.py:396-401`
Observations:
- This table is ORCA-owned in practice today.
- But it anchors to the shared `candidate_registry`.
#### 1.2.3 `candidate_outcomes`
Schema block:
- `orca/state.py:321-338`
Role:
- persists derived outcome rows for candidates
- records horizon, status, return, timestamps derived from live or shadow candidate payloads
Writer surface:
- private helper `_upsert_candidate_outcome()` in `orca/state.py:2300-2350`
- private sync path `_sync_candidate_outcomes()` in `orca/state.py:2353-2463`
- indirect public trigger `record_candidate()` in `orca/state.py:2609-2724`
Readers:
- `_latest_candidate_outcome()` in `orca/state.py:2502-2541`
- `list_candidate_outcomes()` in `orca/state.py:2821-2860`
- `record_candidate_review()` indirectly depends on latest-outcome sync side effects through probability lesson sync
- `summarize_candidate_probabilities()` depends on lesson records partly built from outcome sync
Observations:
- There is no public `record_candidate_outcome()` API in the current code.
- Outcome persistence is a side effect of candidate ingestion.
- That makes ownership less explicit than the table name suggests.
#### 1.2.4 `candidate_lessons`
Schema block:
- `orca/state.py:339-353`
Role:
- stores probability-oriented lesson rows derived from candidate reviews and outcomes
- acts as long-tail evidence for signal-family probability summaries
Writer surfaces:
- private helper `_sync_candidate_probability_lesson()` in `orca/state.py:2544-2606`
- public helper `record_candidate_lesson()` in `orca/state.py:3217-3247`
Actual current write origin:
- `_sync_candidate_probability_lesson()` is triggered by both `record_candidate()` and `record_candidate_review()`
Readers:
- `summarize_candidate_probabilities()` in `orca/state.py:2914-3059`
- ORCA review flow via `orca/analysis_review.py:330`
- ORCA postprocess summary via `orca/postprocess.py:72`
- JACKAL probability helper via `jackal/probability.py:13`
Observations:
- This table is conceptually analytical.
- It is written from ORCA review and candidate sync logic.
- It is read by both ORCA and JACKAL probability paths.
### 1.3 Foreign-key and identity relationships
The candidate cluster is not a loose table set.
It is a connected graph.
Documented FK relationships:
- `candidate_outcomes.candidate_id -> candidate_registry.candidate_id`
- `candidate_lessons.candidate_id -> candidate_registry.candidate_id`
- `candidate_lessons.outcome_id -> candidate_outcomes.outcome_id`
- `candidate_reviews.candidate_id -> candidate_registry.candidate_id`
- `candidate_reviews.run_id -> runs.run_id`
Evidence:
- `docs/phase5/01-db-audit.md:333-342`
The design implication is important:
- `candidate_registry` is the shared identity anchor
- `candidate_outcomes` is subordinate to that identity
- `candidate_lessons` spans both registry and outcomes
- `candidate_reviews` connects candidate identity to ORCA runs
This means ownership cannot be decided table-by-table without checking the graph.
Evidence:
- `docs/phase5/01-db-audit.md:451-462`
### 1.4 Candidate-related helper functions in `orca/state.py`
Current helper inventory:
| Function | Lines | Purpose | Notes |
|---|---:|---|---|
| `_candidate_systems` | `87-93` | normalizes source-system aliases | used to map `jackal` / `hunt` / `scan` families |
| `_candidate_external_key` | `2223-2238` | derives external identity key | depends on system + ticker + event shape |
| `_candidate_status` | `2241-2250` | derives candidate status | used inside `record_candidate()` |
| `_candidate_quality_score` | `2253-2258` | extracts quality score from event | bridge from JACKAL payload to ORCA row |
| `_candidate_signal_family` | `2261-2273` | extracts canonical family | bridge from JACKAL payload to ORCA row |
| `_candidate_raw_signal_family` | `2276-2281` | extracts raw family value | keeps original family form |
| `_candidate_signals_fired` | `2284-2289` | normalizes signal list | serializes into registry row |
| `_candidate_reference_price` | `2292-2297` | normalizes reference price | outcome sync input |
| `_upsert_candidate_outcome` | `2300-2350` | single-row outcome write | private |
| `_sync_candidate_outcomes` | `2353-2463` | derive many outcomes from event | private side-effect engine |
| `_latest_candidate_review` | `2466-2499` | latest review lookup | used by lesson sync |
| `_latest_candidate_outcome` | `2502-2541` | latest outcome lookup | used by lesson sync and registry aggregate |
| `_sync_candidate_probability_lesson` | `2544-2606` | write lesson if review/outcome pair exists | private side effect |
Observations:
- Almost all candidate intelligence is concentrated in `orca/state.py`.
- The file is not just persistence plumbing.
- It contains domain derivation logic for outcomes, family extraction, and lesson synthesis.
This matters for redesign.
A future migration is not only a table move.
It is also a relocation of domain logic.
### 1.5 Public candidate APIs in `orca/state.py`
Current public API surface:
| Function | Lines | Current role | Current DB |
|---|---:|---|---|
| `record_candidate` | `2609-2724` | upsert registry and trigger derived outcome/lesson sync | `orca_state.db` |
| `list_candidates` | `2727-2818` | read registry rows with filters | `orca_state.db` |
| `list_candidate_outcomes` | `2821-2860` | read outcomes | `orca_state.db` |
| `list_candidate_reviews` | `2863-2911` | read reviews joined with registry | `orca_state.db` |
| `summarize_candidate_probabilities` | `2914-3059` | aggregate lessons by family | `orca_state.db` |
| `backfill_candidate_signal_families` | `3062-3131` | one-time repair utility | `orca_state.db` |
| `record_candidate_review` | `3134-3214` | persist ORCA review row and update registry alignment | `orca_state.db` |
| `record_candidate_lesson` | `3217-3247` | direct lesson insert helper | `orca_state.db` |
Important nuance:
- There is no public `record_candidate_outcome()`.
- Outcome persistence is encapsulated under `record_candidate()`.
That means the candidate API is asymmetrical.
Registry and review have public entry points.
Outcome is hidden behind candidate fan-in.
Lesson is both public and side-effect driven.
### 1.6 Runtime callers: actual current fan-in
The repository-wide grep equivalent on `2026-04-23` shows the following runtime callers.
#### 1.6.1 `record_candidate(...)`
Current direct call sites:
- `orca/state.py:1223`
- `orca/state.py:1348`
- `orca/state.py:1535`
Meaning:
- `record_candidate()` is currently fed only by three state-adapter bridge paths.
- It is not directly called from `orca/postprocess.py`.
- It is not directly called from `jackal/hunter.py` or `jackal/scanner.py`.
- JACKAL runtime origins reach it through ORCA state adapter functions.
This is slightly narrower than the original Phase 5 intuition.
The fan-in is real, but it is mediated through adapter APIs, not direct public use from all callers.
#### 1.6.2 `record_candidate_review(...)`
Current direct call site:
- `orca/analysis_review.py:479`
Meaning:
- ORCA review logic is the public writer for `candidate_reviews`.
#### 1.6.3 `list_candidates(...)`
Current direct call sites:
- `orca/analysis_review.py:333`
- `jackal/scanner.py:151`
Meaning:
- candidate registry is read by both ORCA and JACKAL code paths today.
#### 1.6.4 `summarize_candidate_probabilities(...)`
Current direct call sites:
- `orca/analysis_review.py:330`
- `orca/postprocess.py:72`
- `jackal/probability.py:13`
Meaning:
- `candidate_lessons` aggregate outputs are already cross-domain inputs.
#### 1.6.5 `record_candidate_lesson(...)`
Current direct call sites:
- no current repository-wide runtime caller found outside `orca/state.py`
Meaning:
- public exposure exists, but the observed active path is private side-effect synchronization.
#### 1.6.6 `backfill_candidate_signal_families(...)`
Current direct call sites:
- no current runtime caller found
Meaning:
- utility/maintenance API
### 1.7 Cross-DB fan-in entry points from JACKAL runtime
There are three Phase 5 bridge paths.
These are the places where JACKAL-primary writes can trigger candidate secondary writes.
#### 1.7.1 `record_jackal_shadow_signal(entry)`
Definition:
- `orca/state.py:1174-1303`
Primary write:
- `jackal_shadow_signals` in `jackal_state.db`
Secondary candidate propagation:
- `record_candidate(...)` call at `orca/state.py:1223`
Failure policy:
- if primary succeeds and candidate propagation fails, log warning only
- do not roll back primary
- do not raise new exception after primary commit
Evidence:
- `orca/state.py:1227-1243`
- `docs/phase5/03-design.md:568-574`
#### 1.7.2 `resolve_jackal_shadow_signal(...)`
Definition:
- `orca/state.py:1306-1472`
Primary write:
- shadow resolution in `jackal_state.db`
Secondary candidate propagation:
- `record_candidate(...)` call at `orca/state.py:1348`
Failure policy:
- same best-effort model
Evidence:
- `orca/state.py:1352-1367`
#### 1.7.3 `sync_jackal_live_events(system, events)`
Definition:
- `orca/state.py:1475-1657`
Primary write:
- live event sync in `jackal_state.db`
Secondary candidate propagation:
- `record_candidate(...)` call at `orca/state.py:1535`
Failure policy:
- same best-effort model
Evidence:
- `orca/state.py:1540-1555`
### 1.8 Runtime origins behind those bridge paths
These are the code paths that actually trigger the three adapter functions.
| Runtime origin | Call site | Adapter entry | Candidate impact |
|---|---:|---|---|
| `jackal/hunter.py` | `1596` | `sync_jackal_live_events("hunt", retained_logs)` | may create/update registry row and derived outcomes |
| `jackal/scanner.py` | `1165` | `sync_jackal_live_events("scan", logs)` | same |
| `jackal/scanner.py` | `1172` | `record_jackal_shadow_signal(entry)` | same |
| `jackal/evolution.py` | `373` | `sync_jackal_live_events("hunt", self._logs[-500:])` | same |
| `jackal/tracker.py` | `527` | `sync_jackal_live_events("hunt", retained_logs)` | same |
Meaning:
- candidate fan-in is not limited to one JACKAL module
- it is the shared sink for multiple JACKAL subsystems
### 1.9 ORCA-side review and probability flows
#### 1.9.1 ORCA review flow
Main entry:
- `orca/analysis_review.py:318-505`
Key calls:
- `summarize_candidate_probabilities(days=90, min_samples=MIN_SAMPLES)` at `330`
- `list_candidates(source_system="jackal", unresolved_only=True, ...)` at `333`
- PR 4 weighted score composition at `396-401`
- `record_candidate_review(...)` at `479`
Meaning:
- ORCA review logic depends on candidate registry being populated
- ORCA review logic also depends on lesson-derived probability summaries
- review persistence writes back into the same candidate cluster
#### 1.9.2 ORCA postprocess flow
Current entry:
- `orca/postprocess.py:72-106`
Key calls:
- `summarize_candidate_probabilities(...)` at `72`
- `review_recent_candidates(...)` at `106`
Meaning:
- ORCA postprocess is not a direct `record_candidate()` caller today
- but it is still logically dependent on the candidate cluster
- it consumes aggregate probability outputs and triggers reviews
#### 1.9.3 JACKAL probability consumer
Current entry:
- `jackal/probability.py:13`
Key call:
- `summarize_candidate_probabilities(...)`
Meaning:
- JACKAL also consumes the ORCA-resident lesson aggregate
This is one of the strongest signals that candidate ownership is not a simple prefix-based routing problem anymore.
### 1.10 Candidate outcomes dependency graph
The current write/read graph for outcomes is:
1. JACKAL event or shadow signal reaches a Phase 5 bridge function.
2. Bridge function writes JACKAL primary state to `jackal_state.db`.
3. Bridge function then calls `record_candidate(...)` as secondary propagation.
4. `record_candidate(...)` writes or updates `candidate_registry`.
5. `record_candidate(...)` invokes `_sync_candidate_outcomes(...)`.
6. `_sync_candidate_outcomes(...)` writes one or more `candidate_outcomes` rows.
7. `record_candidate(...)` queries `_latest_candidate_outcome(...)`.
8. `record_candidate(...)` pushes latest outcome summary fields back into `candidate_registry`.
9. `record_candidate(...)` invokes `_sync_candidate_probability_lesson(...)`.
10. `_sync_candidate_probability_lesson(...)` may write a lesson row if a qualifying review and outcome pair exists.
11. `summarize_candidate_probabilities(...)` later reads those lessons by signal family.
This graph matters because:
- outcomes are not independent
- outcomes are a bridge table between runtime candidate events and later ORCA probability scoring
- moving only `candidate_registry` without its derived side effects would be incomplete
Evidence:
- `orca/state.py:2300-2606`
- `orca/state.py:2609-2724`
- `orca/state.py:2914-3059`
### 1.11 `candidate_reviews` and `candidate_lessons` in relation to PR 4
PR 4 contract lives in `orca/analysis_review.py`.
Weights:
- `market_bias = 0.15`
- `signal_family_history = 0.30`
- `quality = 0.20`
- `theme_match = 0.15`
- `devil_penalty = 0.10`
- `thesis_killer_penalty = 0.10`
Evidence:
- `orca/analysis_review.py:85-92`
How the candidate cluster participates:
- `list_candidates(...)` supplies unresolved JACKAL candidates to review
- `summarize_candidate_probabilities(...)` supplies signal-family history context
- `record_candidate_review(...)` writes review outputs back to `candidate_reviews` and updates `candidate_registry.orca_alignment`
So PR 4 is not only adjacent to the candidate cluster.
It is materially coupled to it.
If candidate ownership changes, PR 4 read paths and write-back paths must still function unchanged from the outside.
Evidence:
- `orca/analysis_review.py:330-333`
- `orca/analysis_review.py:396-401`
- `orca/analysis_review.py:479`
- `orca/state.py:3134-3214`
### 1.12 Why `candidate_outcomes` is especially ambiguous
`candidate_outcomes` appears ORCA-resident today.
But it is not clearly ORCA-origin.
It is generated from JACKAL-origin event payloads during secondary propagation.
At the same time, it is later used by ORCA-side review/lesson logic.
That makes it neither a clean JACKAL learning table nor a clean ORCA-only review table.
Evidence:
- `docs/phase5/01-db-audit.md:852-858`
- `orca/state.py:2353-2463`
- `orca/state.py:2544-2606`
### 1.13 Current ownership signals by table
This is the best current reading, not a final Phase 6 decision.
| Table | Physical DB now | Write origin now | Read origin now | Ownership signal |
|---|---|---|---|---|
| `candidate_registry` | ORCA | secondary writes from JACKAL bridge, review alignment from ORCA | ORCA + JACKAL | shared/ambiguous |
| `candidate_outcomes` | ORCA | secondary writes from JACKAL bridge via `record_candidate()` | mostly ORCA-side derived reads | ambiguous |
| `candidate_reviews` | ORCA | ORCA review flow | ORCA | ORCA-leaning |
| `candidate_lessons` | ORCA | ORCA sync helper triggered by review/outcome availability | ORCA + JACKAL probability consumer | shared/ambiguous |
### 1.14 Important asymmetry in current APIs
There is a structural mismatch today:
- `candidate_reviews` has a public explicit write API
- `candidate_registry` has a public explicit write API
- `candidate_lessons` has both a public API and a side-effect sync path
- `candidate_outcomes` has only a side-effect sync path
This asymmetry matters for redesign because:
- explicit ownership is harder when one table is only updated as a hidden consequence
- migration steps become harder to reason about
- instrumentation is weaker for the hidden path
### 1.15 Current observability of candidate propagation failures
Current behavior:
- JACKAL primary writes succeed
- candidate propagation failure is logged to `stderr`
- no new PR 1 health code is emitted
- no report field is updated by default
Evidence:
- `orca/state.py:1227-1243`
- `orca/state.py:1352-1367`
- `orca/state.py:1540-1555`
- `docs/orca_v2_backlog.md:241-249`
Implication:
- candidate spine divergence can exist without first-class health visibility
- this is why the redesign and observability question are linked
### 1.16 Current conclusion from inventory
The candidate cluster is physically in ORCA, partially written from JACKAL runtime events, partially written from ORCA review logic, read by both ORCA and JACKAL, and still buffered by Phase 5 best-effort propagation rules.
That combination is exactly why Phase 5 deferred it.
## Section 2: 현재 문제점 분석
### 2.1 Why Path B deferred this cluster
Phase 5 did not fail to notice the candidate cluster.
It explicitly chose not to resolve it.
Documented reasons:
- preserve JACKAL learning-state first
- do not widen scope into candidate spine redesign
- accept `orca/state.py` as a shared adapter temporarily
Evidence:
- `docs/phase5/02-path-decision.md:26-27`
- `docs/phase5/02-path-decision.md:30-32`
- `docs/phase5/02-path-decision.md:91-94`
This is important for Phase 6.
The redesign is not a reaction to an overlooked bug.
It is the next planned architectural step after a bounded operational fix.
### 2.2 Problem 1: cross-DB fan-in remains real
Repository review identifies:
- `record_candidate()` fan-in through the three bridge functions
- cross-DB secondary propagation
Evidence:
- `docs/analysis/2026-04-22_repository_review.md:784-790`
- `docs/analysis/2026-04-22_repository_review.md:810-812`
Why that matters:
- multiple runtime origins feed one shared sink
- ownership is hard to reason about
- write semantics are not local to either ORCA or JACKAL
### 2.3 Problem 2: silent divergence is possible
Blind spot 1 from the review is specific:
- JACKAL primary write may succeed
- candidate secondary write may fail
- only `stderr` warning is recorded
Evidence:
- `docs/analysis/2026-04-22_repository_review.md:601-611`
Operational meaning:
- JACKAL learning loop can appear healthy
- ORCA candidate spine can be empty or stale
- downstream reviews and probability summaries may degrade quietly
### 2.4 Problem 3: ownership is blurred at both schema and code level
Schema ambiguity:
- audit marked `candidate_outcomes`, `candidate_lessons`, and `candidate_reviews` as unclear-design tables
Evidence:
- `docs/phase5/01-db-audit.md:852-863`
- `docs/phase5/01-db-audit.md:888-891`
Code ambiguity:
- `orca/state.py` contains both persistence plumbing and candidate-domain derivation logic
- bridge functions route JACKAL writes into ORCA candidate tables
- ORCA review writes back into the same cluster
Evidence:
- `orca/state.py:1174-1657`
- `orca/state.py:2223-3247`
- `orca/analysis_review.py:318-505`
### 2.5 Problem 4: `candidate_outcomes` is hidden inside another API
Because `candidate_outcomes` only writes as a side effect of `record_candidate()`, the system lacks:
- an explicit single outcome owner
- a clear migration seam
- a first-class write contract for outcomes
This hidden coupling makes any ownership decision harder.
Evidence:
- `orca/state.py:2300-2463`
- `orca/state.py:2609-2724`
### 2.6 Problem 5: candidate lessons bridge domains
`candidate_lessons` looks like an ORCA analytical artifact at first glance.
But it is also consumed by JACKAL probability helpers.
That means even a seemingly ORCA-owned table has cross-domain read significance.
Evidence:
- `orca/state.py:2544-2606`
- `orca/state.py:2914-3059`
- `jackal/probability.py:13`
### 2.7 Problem 6: PR 4 uses the cluster as live input
PR 4 scorecard is contract-sensitive.
Its `signal_family_history` component depends on `summarize_candidate_probabilities(...)`.
Its review target set depends on `list_candidates(...)`.
Its write-back path uses `record_candidate_review(...)`.
Therefore a candidate redesign can indirectly damage a contract the repository now tests.
Evidence:
- `orca/analysis_review.py:330-333`
- `orca/analysis_review.py:396-401`
- `orca/analysis_review.py:479`
### 2.8 Problem 7: `orca/state.py` remains oversized partly because of this cluster
Current line count is not the point by itself.
The structural point is that the candidate cluster keeps a large shared adapter alive.
Repository review lists this explicitly as debt.
Evidence:
- `docs/analysis/2026-04-22_repository_review.md:805-812`
This means candidate redesign is not isolated cleanup.
It is also a prerequisite for removing or shrinking the shared adapter later.
### 2.9 Problem 8: migration complexity increases over time
Every additional read or write path that touches candidate tables will make a later move more expensive.
Today the active surfaces are still bounded:
- three JACKAL bridge paths
- ORCA review write path
- ORCA/JACKAL read paths
That is manageable.
It may not remain manageable if more features accumulate on the current cluster.
### 2.10 Why this is not just a naming problem
The issue is not solved by renaming:
- `candidate_registry`
- `candidate_outcomes`
- `candidate_reviews`
- `candidate_lessons`
The problem is:
- ownership
- direction of writes
- propagation semantics
- hidden side effects
- review-path dependency
### 2.11 Operational risk if nothing changes
If Phase 6 does nothing, the likely future state is:
- more candidate logic remains in shared adapter
- best-effort secondary propagation remains permanent
- candidate divergence remains difficult to observe
- review logic continues to depend on a cluster with mixed write origins
- later redesign becomes costlier
This is tolerable for bounded Phase 5.
It is not a good permanent equilibrium.
### 2.12 Why the problem is still safe to address incrementally
There is also good news.
The candidate cluster is already behind a fairly small set of public functions.
That means Phase 6 can still attack it through staged refactoring rather than a big-bang rewrite.
Important available seams:
- `record_candidate`
- `record_candidate_review`
- `list_candidates`
- `summarize_candidate_probabilities`
The redesign question is hard, but not unbounded.
## Section 3: 재설계 선택지
### 3.1 Option A: Move candidate registry domain toward JACKAL ownership
#### 3.1.1 Description
Under Option A:
- candidate cluster, or most of it, moves to `data/jackal_state.db`
- JACKAL-origin writes become local writes
- ORCA review logic becomes a cross-domain reader/writer into JACKAL-owned candidate data
#### 3.1.2 Why this option exists
Current runtime fan-in begins from JACKAL event production.
`record_candidate()` is effectively fed by JACKAL runtime events.
That suggests JACKAL ownership could simplify write locality.
Evidence:
- `jackal/hunter.py:1596`
- `jackal/scanner.py:1165`
- `jackal/scanner.py:1172`
- `jackal/evolution.py:373`
- `jackal/tracker.py:527`
#### 3.1.3 Potential advantages
- Primary write and candidate write could become the same transaction domain for JACKAL-origin data.
- Phase 5 secondary propagation could disappear for the JACKAL-origin portion.
- `record_jackal_shadow_signal`, `resolve_jackal_shadow_signal`, and `sync_jackal_live_events` would become architecturally simpler.
- Candidate divergence between JACKAL DB and candidate spine would be reduced or removed.
#### 3.1.4 Potential disadvantages
- ORCA review would now depend on JACKAL-owned storage for PR 4 inputs and outputs.
- `candidate_reviews` feels ORCA-owned in practice today, so moving it under JACKAL would invert the review ownership story.
- `candidate_reviews.run_id -> runs.run_id` ties reviews to ORCA run tracking.
- `candidate_lessons` and probability summaries are currently closer to ORCA analytics.
Evidence:
- `docs/phase5/01-db-audit.md:340-342`
- `orca/analysis_review.py:318-505`
- `orca/postprocess.py:72-106`
#### 3.1.5 PR 1 to PR 5 impact
PR 1:
- no direct semantic change required
- but failure reporting paths would change because current best-effort candidate secondary propagation might disappear
PR 2:
- no material impact
PR 3:
- no direct impact
PR 4:
- medium to high impact
- review inputs and write-backs would cross from ORCA into JACKAL-owned domain
PR 5:
- no direct data-quality contract change, but report-side observability of candidate propagation could improve or shift
#### 3.1.6 Migration risk
High.
Reason:
- the table graph is not purely JACKAL-owned
- ORCA review writes and `runs.run_id` foreign-key relationship complicate a clean move
#### 3.1.7 Observability implications
Positive for JACKAL-origin writes.
Mixed for ORCA review writes.
Candidate review failures might become cross-DB instead of candidate ingest failures becoming cross-DB.
#### 3.1.8 Summary judgment
Option A is attractive if the core question is "where do most candidate rows originate?"
It is less attractive if the core question is "who owns review and analytical interpretation of candidates?"
### 3.2 Option B: Keep candidate cluster ORCA-owned, but make cross-domain writes explicit
#### 3.2.1 Description
Under Option B:
- candidate cluster stays in `data/orca_state.db`
- ORCA is declared the owner of candidate intelligence tables
- JACKAL no longer treats candidate propagation as an incidental secondary side effect
- instead, JACKAL-origin writes call an explicit ORCA-owned intake boundary
- the cross-domain hop becomes deliberate, typed, and observable
#### 3.2.2 Why this option exists
Current table graph already leans ORCA in several places:
- physical location is ORCA
- review writes are ORCA
- `candidate_reviews.run_id -> runs.run_id`
- lessons feed ORCA postprocess and review logic
Evidence:
- `orca/state.py:268-353`
- `docs/phase5/01-db-audit.md:340-342`
- `orca/analysis_review.py:318-505`
- `orca/postprocess.py:72-106`
#### 3.2.3 Potential advantages
- Minimal conceptual disruption to PR 4 review flow.
- Existing ORCA review ownership becomes explicit instead of accidental.
- `candidate_reviews` and review-alignment fields do not need to cross into JACKAL ownership.
- Phase 5 Path B remains compatible because candidate tables stay where they are.
- The redesign can focus on API boundaries instead of database relocation first.
#### 3.2.4 Potential disadvantages
- JACKAL-origin candidate ingestion remains cross-domain by design.
- If not designed carefully, the system could still look like "secondary propagation with better naming."
- It does not automatically collapse everything into one transaction.
#### 3.2.5 PR 1 to PR 5 impact
PR 1:
- compatible
- redesign could introduce richer observability later without changing the existing 10-code contract immediately
PR 2:
- no direct impact
PR 3:
- no direct impact
PR 4:
- lowest impact of the four options
- review paths can stay logically ORCA-owned
PR 5:
- compatible
- report visibility work can remain additive
#### 3.2.6 Migration risk
Medium.
Reason:
- fewer table moves
- more API and ownership clarification work
- less FK upheaval than Option A or D
#### 3.2.7 Observability implications
Strong.
Because the design can explicitly instrument the domain boundary between JACKAL event generation and ORCA candidate intelligence.
#### 3.2.8 Summary judgment
Option B is the most conservative architectural cleanup.
It resolves ambiguity by clarifying ownership without requiring an immediate new database boundary.
### 3.3 Option C: Split the candidate cluster by ownership across both databases
#### 3.3.1 Description
Under Option C:
- some candidate tables move to JACKAL
- some remain in ORCA
- likely split patterns:
  - registry + outcomes to JACKAL
  - reviews + lessons to ORCA
  - or another variation
#### 3.3.2 Why this option exists
The current cluster is mixed.
A split may sound like the most accurate reflection of reality.
JACKAL originates many candidate events.
ORCA owns reviews.
Lessons and outcomes sit in between.
#### 3.3.3 Potential advantages
- Ownership can be fine-grained.
- Each subtable can go where its dominant logic lives.
- Cross-domain access can be narrower if done well.
#### 3.3.4 Potential disadvantages
- This is the most subtle option to get wrong.
- The FK graph currently ties the tables tightly together.
- `candidate_lessons` references both `candidate_registry` and `candidate_outcomes`.
- `candidate_reviews` also points back to `candidate_registry`.
- Split ownership would introduce join boundaries across DBs or require denormalization.
Evidence:
- `docs/phase5/01-db-audit.md:333-342`
- `docs/phase5/01-db-audit.md:451-462`
#### 3.3.5 PR 1 to PR 5 impact
PR 1:
- no direct contract change, but more boundary failures become possible
PR 2:
- no direct impact
PR 3:
- no direct impact
PR 4:
- medium to high risk
- history summaries and review write-backs might cross different stores
PR 5:
- no direct impact, but reporting complexity increases
#### 3.3.6 Migration risk
Highest among the practical options.
Reason:
- requires defining ownership per table and possibly per derived artifact
- likely forces cross-DB join replacement patterns
- easiest option to produce partial consistency issues
#### 3.3.7 Observability implications
Potentially good if fully instrumented.
But there would be more edges to observe.
#### 3.3.8 Summary judgment
Option C is the most theoretically precise and the most operationally complex.
It should only be chosen if a strong ownership split emerges from future analysis.
### 3.4 Option D: Create a separate `candidate_state.db`
#### 3.4.1 Description
Under Option D:
- candidate cluster becomes its own database
- ORCA and JACKAL both become clients of a candidate domain
- candidate tables stop living inside either ORCA or JACKAL state DB
#### 3.4.2 Why this option exists
The candidate cluster already behaves like a third domain:
- shared identity
- shared reads
- mixed writes
- derived analytical content
A third DB is the purest way to acknowledge that.
#### 3.4.3 Potential advantages
- Cleanest ownership story if candidate intelligence is truly a separate domain.
- Makes the candidate cluster explicit instead of treating it as a leftover inside ORCA.
- Could reduce conceptual overload in both `orca_state.db` and `jackal_state.db`.
#### 3.4.4 Potential disadvantages
- Introduces a new database family, new workflow save rules, new checkpoint logic, and new operational surface.
- Phase 5 workflows and routing assumptions would need another round of redesign.
- The repository is only just stabilizing around dual-DB observability.
- Jumping directly to triple-DB architecture may be too much change at once.
#### 3.4.5 PR 1 to PR 5 impact
PR 1:
- likely requires new failure surfaces, though contract can still be preserved if handled carefully
PR 2:
- no direct impact
PR 3:
- no direct impact
PR 4:
- medium impact because review inputs/outputs become third-domain calls
PR 5:
- observability work would need extension to a third state snapshot if later exposed
#### 3.4.6 Migration risk
High.
Not because the model is unclear.
Because the operations surface expands materially.
#### 3.4.7 Observability implications
Potentially excellent long term.
Expensive short term.
#### 3.4.8 Summary judgment
Option D is architecturally appealing but likely too large for the first Phase 6 move unless the team explicitly wants a new domain boundary now.
### 3.5 Comparison table
| Category | Option A: move to JACKAL | Option B: keep ORCA-owned, explicit crossing | Option C: split across both DBs | Option D: third DB |
|---|---|---|---|---|
| Implementation complexity | high | medium | very high | high |
| Migration complexity | high | medium | very high | high |
| Phase 5 compatibility | medium | high | medium-low | low-medium |
| PR 4 impact | high | low-medium | high | medium |
| Fit with current physical layout | low | high | medium | low |
| Reduction of current secondary propagation | high for JACKAL-origin rows | medium, if crossing is redesigned explicitly | mixed | high, but via new domain |
| Operational surface increase | low-medium | low | medium-high | high |
| Observability opportunity | medium | high | high | high |
| Risk of silent divergence during transition | medium | medium | high | medium-high |
| Long-term extensibility | medium | high | medium | high |
### 3.6 What each option says about ownership
Option A says:
- candidate intelligence is primarily JACKAL runtime state
Option B says:
- candidate intelligence is primarily ORCA analytical/review state, with JACKAL as producer
Option C says:
- there is no single owner; ownership must be partitioned by subtable
Option D says:
- candidate intelligence is its own domain and neither ORCA nor JACKAL should own it
### 3.7 Tentative recommendation
Tentative recommendation:
- **Option B**
This is not a final decision.
It is the best current recommendation based on the code and Phase 5 constraints.
#### 3.7.1 Why Option B is tentatively preferred
Reason 1:
- it preserves the current ORCA-centered review semantics that PR 4 already depends on
Reason 2:
- it aligns with current physical placement, reducing migration shock
Reason 3:
- it is compatible with Phase 5 Path B rather than undoing it
Reason 4:
- it addresses the real issue, which is ambiguous ownership and hidden secondary propagation, not necessarily the physical DB location itself
Reason 5:
- it leaves room for a later candidate-domain split if usage grows further
#### 3.7.2 Why the recommendation stays tentative
Because this document does not answer:
- how much of `candidate_outcomes` should stay derived versus become explicit
- whether future JACKAL workflows will need lower-latency candidate reads than ORCA ownership can comfortably provide
- whether the later shared-adapter split will expose a cleaner domain boundary than we can currently see
### 3.8 What would change the recommendation
Option A could become preferable if:
- candidate review semantics move closer to JACKAL runtime
- ORCA review becomes read-only against candidate rows
- future features require JACKAL-local candidate transactions
Option C could become preferable if:
- a precise table-by-table ownership split emerges with low coupling cost
Option D could become preferable if:
- candidate intelligence is deliberately elevated into its own operational domain
- the team is ready to support a third state DB
## Section 4: 각 선택지별 구현 단계 개요
### 4.1 Common migration principles for any option
Regardless of option, the first safe migration principles should be:
- introduce the new storage or API boundary before deleting the old one
- prefer dual-read or dual-write transition steps over big-bang cutover
- preserve existing public caller signatures until the new path is validated
- extend tests before removing compatibility paths
- do not remove Phase 5 best-effort mitigation until the replacement path is proven
### 4.2 Option A implementation outline
If Option A is chosen, a plausible sequence is:
#### 4.2.1 Step A1: define JACKAL-owned candidate schema
- create candidate schema in `jackal_state.db`
- decide whether all four candidate tables move together
- re-evaluate FK strategy because `candidate_reviews.run_id -> runs.run_id` is ORCA-linked today
Deliverables:
- schema draft
- ownership notes
- migration compatibility matrix
#### 4.2.2 Step A2: add dual-write compatibility layer
- `record_candidate()` or a replacement API writes both old ORCA tables and new JACKAL tables
- ORCA review write path keeps old behavior first
- write comparison logging is added
Goal:
- prove data parity before read cutover
#### 4.2.3 Step A3: add read compatibility
- `list_candidates()` and related readers support reading from new JACKAL candidate tables
- PR 4 review path is validated against new reads
- probability summaries are checked for parity
#### 4.2.4 Step A4: move ORCA review write path or bridge it explicitly
- decide whether ORCA review writes directly into JACKAL-owned candidate domain
- or writes through an intermediate adapter
This is the hardest step in Option A.
#### 4.2.5 Step A5: retire ORCA candidate tables
- switch reads to new source only
- remove old dual-write
- archive or migrate historic ORCA candidate rows
#### 4.2.6 Testing focus for Option A
- review path parity
- outcome sync parity
- candidate lesson parity
- regression against PR 4 contract behavior
- no break in `list_candidates()` for JACKAL scanner
### 4.3 Option B implementation outline
If Option B is chosen, a plausible sequence is:
#### 4.3.1 Step B1: declare explicit ORCA ownership and formal intake boundary
- document that candidate cluster is ORCA-owned
- create an explicit ORCA intake API for JACKAL-origin candidate payloads
- stop treating candidate writes as incidental secondary side effects
This can still initially call existing functions under the hood.
The value is in boundary clarity.
#### 4.3.2 Step B2: separate candidate domain logic from generic state adapter
- move candidate-domain functions out of monolithic shared adapter
- keep behavior the same initially
- make ORCA-owned candidate service explicit
Likely future code direction:
- `orca/candidate_state.py` or similar
- `orca/state.py` delegates or becomes thinner
#### 4.3.3 Step B3: make JACKAL-to-ORCA candidate propagation explicit and observable
- replace hidden secondary propagation inside bridge functions with named domain calls
- add structured result handling
- later decide whether to surface candidate propagation health via report or other observability
This is where Blind spot 1 can be addressed together with redesign.
#### 4.3.4 Step B4: make outcome ownership explicit
- decide whether `candidate_outcomes` remains derived from candidate intake
- or gets its own public write API
This step removes the current hidden ownership problem.
#### 4.3.5 Step B5: preserve ORCA review and probability read APIs
- `list_candidates()`
- `summarize_candidate_probabilities()`
- `record_candidate_review()`
These should remain stable from the perspective of ORCA review code and JACKAL probability consumers.
#### 4.3.6 Step B6: remove Phase 5-style incidental candidate propagation
- after explicit boundary and tests exist
- remove best-effort secondary candidate writes from bridge internals
- keep Phase 5 mitigation only for truly shared transitional surfaces if any remain
#### 4.3.7 Testing focus for Option B
- PR 4 review path unchanged
- JACKAL-origin candidate intake parity
- no silent candidate divergence in explicit intake path
- parity of probability summaries
- contract tests unchanged unless observability is intentionally extended
### 4.4 Option C implementation outline
If Option C is chosen, a plausible sequence is:
#### 4.4.1 Step C1: choose table-by-table owners
- decide exact owner for each of the four candidate tables
- write an explicit ownership table
- confirm how FK relationships survive the split
#### 4.4.2 Step C2: redesign cross-table joins
- candidate lessons and probability summaries currently rely on registry join patterns
- split ownership may require duplication, snapshots, or API-level joins instead of DB-local joins
#### 4.4.3 Step C3: dual-write transition by table family
- move one subtable family at a time
- validate reads after each move
#### 4.4.4 Step C4: refactor callers by owned read path
- ORCA review readers
- JACKAL scanner readers
- probability helper readers
#### 4.4.5 Step C5: retire transitional compatibility
- remove dual-write or dual-read once each table family is stable
#### 4.4.6 Testing focus for Option C
- cross-DB join replacement correctness
- family probability summary parity
- review output parity
- no partial candidate object reconstruction bugs
### 4.5 Option D implementation outline
If Option D is chosen, a plausible sequence is:
#### 4.5.1 Step D1: define `candidate_state.db`
- schema
- ownership
- workflow save/checkpoint requirements
- backup and restore expectations
#### 4.5.2 Step D2: create candidate-domain API
- new persistence module
- old ORCA and JACKAL callers redirected to domain API
#### 4.5.3 Step D3: dual-write from current ORCA tables
- populate new DB while old tables still exist
- compare parity
#### 4.5.4 Step D4: cut over readers
- ORCA review
- JACKAL scanner
- probability summary consumers
#### 4.5.5 Step D5: remove old tables from ORCA
- archive/migrate historic rows
- update workflow persistence rules
#### 4.5.6 Testing focus for Option D
- third-DB workflow persistence
- snapshot/report observability if later exposed
- domain API parity for all readers and writers
### 4.6 Shared migration cautions
For all options, avoid changing candidate meaning and migration shape in one PR, moving tables before identifying all callers, combining candidate redesign with unrelated feature additions, or removing compatibility helpers before parity tests exist.
Useful transitional modes are likely to be some subset of: old write / old read, dual write / old read, dual write / dual read validation, new write / dual read validation, new write / new read, and cleanup.
Preferred migration style is explicit staging with reversible intermediate steps and parity checks before cutover, not a one-shot table move without a compatibility window.
Implementation detail stays brief here because the exact migration plan should be refreshed against then-current code and tests.
## Section 5: 의존 및 순서
### 5.1 Relation to shared adapter split
The candidate redesign and shared-adapter split are tightly related.
Current fact:
- `orca/state.py` is still the shared adapter
- candidate logic is one of the main reasons it remains shared
Evidence:
- `docs/phase5/02-path-decision.md:27`
- `docs/analysis/2026-04-22_repository_review.md:805-812`
- `orca/state.py:1174-1657`
- `orca/state.py:2223-3247`
As of `2026-04-23`, `docs/phase6/shared-adapter-split-design.md` is not present.
Therefore the dependency can only be described conceptually here.
#### 5.1.1 Candidate redesign first
Pros:
- removes one of the biggest ambiguous clusters before adapter split
- makes later adapter decomposition cleaner
Cons:
- requires touching the shared adapter while it still exists
#### 5.1.2 Shared adapter split first
Pros:
- may create clearer ownership seams before candidate migration
Cons:
- likely forces temporary duplication of candidate logic across adapters
- may move ambiguity around without resolving it
#### 5.1.3 Provisional recommendation
Candidate redesign should come before the final shared-adapter split.
Reason:
- the candidate cluster is itself one of the defining pieces of shared-adapter ambiguity
- splitting the adapter first risks encoding the ambiguity into two files instead of one
### 5.2 Relation to P2-2 verification extraction
P2-2 wave 2 moved verification logic out of the main analysis module while preserving patch seams.
That work is conceptually separate from candidate redesign.
However both touch the broader question of:
- what remains in shared adapter style modules
- what gets explicit domain ownership
Current verification surface:
- `orca/analysis.py`
- `orca/analysis_verification.py`
- `orca/run_cycle.py:30`
- `orca/run_cycle.py:307`
There is no direct candidate-cluster ownership overlap with verification logic.
The practical relationship is sequencing:
- do not combine candidate redesign with verification seam redesign in one migration PR
### 5.3 Relation to PR 4 review logic
This is the strongest functional dependency in the repository.
Any candidate redesign must preserve:
- `list_candidates(...)`
- `summarize_candidate_probabilities(...)`
- `record_candidate_review(...)`
At minimum, from the perspective of `orca/analysis_review.py`.
Evidence:
- `orca/analysis_review.py:330-333`
- `orca/analysis_review.py:396-401`
- `orca/analysis_review.py:479`
This means candidate redesign should happen before any PR 4 redesign only if it can preserve those surfaces.
Otherwise the review contract becomes collateral damage.
### 5.4 Relation to JACKAL workflow stability
The recent JACKAL fixes restored runtime writes and candidate propagation paths.
That stability is valuable.
Phase 6 candidate redesign should not be attempted in the same change set as workflow repair or runtime bug fixes because it would blur whether failures come from migration design or workflow/runtime instability.
### 5.5 Relation to future feature expansion
Feature work such as correlation/relative strength/squeeze does not need to block candidate redesign.
But candidate redesign should ideally finish before new candidate-facing analytical features attach to the current cluster.
Reason: every new dependency makes redesign more expensive.
### 5.6 Provisional Phase 6 dependency graph
Recommended order:
1. Choose candidate option explicitly.
2. Implement candidate redesign.
3. Revisit shared-adapter split using the new candidate ownership boundary.
4. Only then expand new candidate-adjacent features or additional observability if desired.
### 5.7 Sequencing note for observability
Blind spot 1 and candidate redesign are linked.
But they do not need to be solved in the same commit.
A safe order is to choose ownership first and then add observability at the explicit domain boundary.
### 5.8 Why `research_gate.py` is separate
Although related Phase 6 design work may exist, `orca/research_gate.py` is a separate threshold/configuration concern.
It should not be mixed into candidate redesign.
Its domain is gating research/promotion decisions, not candidate spine ownership.
## Section 6: 결정 보류 항목
### 6.1 Decisions intentionally not made here
This document does not decide:
- Option A, B, C, or D as final
- exact cutover ordering
- whether dual-write or dual-read is mandatory
- whether `candidate_outcomes` becomes a public API
- whether lessons remain ORCA-owned or become domain-owned
- how long backward compatibility should remain
- whether new health visibility belongs in the same PR
### 6.2 Questions for the next session
The next session should answer:
- Is candidate intelligence fundamentally ORCA-owned, JACKAL-owned, split, or third-domain?
- Is `candidate_outcomes` a hidden implementation detail or a first-class domain artifact?
- Should `candidate_lessons` be treated as review-derived analytics or shared model evidence?
- Is the first Phase 6 step physical migration, API extraction, or both?
### 6.3 Why deferral is explicit
This document is designed to support a decision.
It is not itself the decision.
That distinction matters because the repository now has tests and contracts that should not be changed implicitly by a design memo.
## Section 7: 성공 기준
### 7.1 Architectural success criteria
A Phase 6 candidate redesign should be considered complete only if:
- cross-DB candidate fan-in is resolved structurally
- best-effort secondary candidate propagation is no longer the long-term mechanism
- candidate ownership is explicit in code and docs
- `orca/state.py` no longer carries ambiguous candidate-domain logic as a shared leftover
### 7.2 Functional success criteria
The redesign should preserve:
- ORCA review behavior
- candidate probability summaries
- JACKAL candidate consumption where currently used
- current public caller expectations for candidate-related APIs, or provide a deliberate compatibility layer
### 7.3 Contract success criteria
The redesign must preserve:
- PR 1 contract unless explicitly extended in a separate approved change
- PR 2 learning policy constants
- PR 3 thin coordinator
- PR 4 scorecard semantics and weighting
- PR 5 data-quality visibility contract
- Phase 5 routing guarantees until replacement path is proven
### 7.4 Operational success criteria
The redesign should eliminate or materially reduce:
- silent candidate divergence
- hidden side-effect writes as the only ownership mechanism
- ambiguous table-family ownership
### 7.5 Migration success criteria
The migration should provide:
- a reversible or staged path
- parity validation between old and new path during transition
- explicit cleanup point when transitional compatibility can be removed
### 7.6 Testing success criteria
A completed redesign should include:
- candidate ownership regression tests
- explicit candidate propagation path tests
- review-path compatibility tests
- observability or divergence-detection tests if new boundary reporting is introduced
### 7.7 Documentation and failure criteria
The final implementation should leave behind updated ownership notes, updated persistence architecture documentation, and updated workflow notes if any new DB or save path exists.
The redesign should be considered incomplete if candidate writes still depend on hidden secondary propagation with no explicit domain boundary, if PR 4 review behavior becomes implicit or broken, if ownership remains arguable after the migration, or if the shared adapter is still required specifically because candidate logic stayed ambiguous.
## Section 8: 참고 자료
### 8.1 Phase 5 source documents
- `docs/phase5/01-db-audit.md`
- `docs/phase5/02-path-decision.md`
- `docs/phase5/03-design.md`
- `docs/phase5/04-workflow-design.md`
### 8.2 Repository review references
- `docs/analysis/2026-04-22_repository_review.md:601-611`
- `docs/analysis/2026-04-22_repository_review.md:784-790`
- `docs/analysis/2026-04-22_repository_review.md:805-812`
### 8.3 Backlog reference
- `docs/orca_v2_backlog.md:241-249`
### 8.4 Core code references
- `orca/state.py:87-93`
- `orca/state.py:1174-1657`
- `orca/state.py:2223-3247`
- `orca/analysis_review.py:85`
- `orca/analysis_review.py:318-505`
- `orca/postprocess.py:72-106`
- `jackal/hunter.py:1596`
- `jackal/scanner.py:151`
- `jackal/scanner.py:1165-1172`
- `jackal/evolution.py:373`
- `jackal/tracker.py:527`
- `jackal/probability.py:13`
### 8.5 Suggested next-session checklist
When implementation starts later, begin with:
1. Reconfirm all candidate call sites and line numbers in current HEAD.
2. Reconfirm whether `docs/phase6/shared-adapter-split-design.md` has been added in the meantime.
3. Choose one option explicitly.
4. Decide whether `candidate_outcomes` becomes an explicit public API.
5. Define parity tests before changing write behavior.
6. Only then draft the actual migration steps.
### 8.6 Final note
Phase 5 solved the immediate JACKAL persistence problem by bounded separation.
It did not solve candidate ownership.
Phase 6 should solve that ownership question deliberately, not by incremental drift.
