# Phase 5 Path Decision

Purpose: record the Phase 5 execution path choice before implementation begins, so the rationale stays traceable after the code changes land.

Related documents:
- Audit baseline: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md)
- JACKAL current-state map: [current-signals.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/jackal/current-signals.md)
- Phase 6 candidate backlog: [orca_v2_backlog.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/orca_v2_backlog.md)

## Section 1: Decision Summary

결정: `Path B (축소 분리)`

날짜:
- `2026-04-21`

근거 문서:
- [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md)

결정권자:
- 프로젝트 오너 `Minwoo`

결정 요약:
- `Category 1 (JACKAL-only)` 로 분류된 `7`개 테이블만 `data/jackal_state.db` 로 이동한다. 근거: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:783)
- `Category 3 (Shared)` `5`개와 `Category 4 (Ambiguous)` `2`개는 `orca_state.db` 에 남긴다. 근거: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:783)
- `candidate_registry` 재설계와 candidate cluster ownership 결정은 이번 Phase 5 범위에서 제외하고 `Phase 6` 로 이월한다. 근거: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:875)
- `orca/state.py` 는 당분간 ORCA 전용 파일이 아니라 shared persistence adapter 로 취급한다. 근거: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:812)

Operational summary:
- 이번 결정의 1차 목표는 `JACKAL 학습 상태 보존` 이다.
- 이번 결정의 비목표는 `candidate spine 재설계` 이다.
- 이번 결정은 `full separation` 이 아니라 `bounded separation` 이다.

## Section 2: Path Options Evaluated

이 섹션은 Phase 5-A 결과를 바탕으로 비교된 경로를 기록한다.

### Path A: Full Separation (전체 DB 분리)

정의:
- `Category 1 (7)` + `Category 3 (5)` + `Category 4 (2)` 를 모두 분리 대상으로 보고 처리
- 사실상 JACKAL, ORCA, candidate cluster 의 경계를 한 번에 재설계하는 경로

범위:
- `jackal_*` 테이블 전체 이동
- `candidate_*` cluster 이동 또는 별도 shared store 설계
- `backtest_*` cluster ownership 재분류
- `orca/state.py` 라우팅 구조 대폭 변경
- workflow, bootstrap, migration, validation 동시 개편

예상 세션:
- `20~30`

리스크:
- `높음`

거부 사유:
- `candidate_registry` 는 단순 보조 테이블이 아니라 `JACKAL -> ORCA` 이벤트 spine 으로 확인됐다. 근거: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:719)
- shared table cluster 는 `5`개, ambiguous table 은 `2`개로 단순 prefix 이동으로 해결되지 않는다. 근거: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:790)
- Phase 5-A blocker `3`개가 모두 shared ownership 설계 문제를 가리킨다. 근거: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:873)
- 개인 프로젝트 기준으로는 “DB 분리 작업”이 아니라 `이벤트 경로 재설계 프로젝트` 에 가까운 범위다.

판정:
- Phase 5 범위로 채택하지 않음

### Path B: Reduced Separation (축소 분리)

상태:
- `SELECTED`

정의:
- `Category 1 (JACKAL-only)` `7`개 테이블만 `jackal_state.db` 로 이동
- shared/ambiguous cluster 는 그대로 두고, ownership 문제를 문서상으로 명시한 뒤 다음 단계로 이월

범위:
- `jackal_shadow_signals`
- `jackal_shadow_batches`
- `jackal_weight_snapshots`
- `jackal_live_events`
- `jackal_recommendations`
- `jackal_accuracy_projection`
- `jackal_cooldowns`

예상 세션:
- `10~15`

리스크:
- `중`

선택 사유:
- Phase 5-A 가 확인한 핵심 운영 문제는 `JACKAL 학습 상태가 scheduled run 이후 유지되지 않는 것` 이었다. 근거: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:59)
- 위 문제는 `Category 1` 테이블 보존만으로도 직접적으로 대응 가능하다. 근거: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:247)
- `candidate_registry` 문제를 “이번에 같이 푼다”가 아니라 “명시적으로 이월한다”는 점이 범위를 실용적으로 만든다.
- `orca/state.py` 가 shared adapter 라는 사실을 문서와 코드 주석으로 인정하면, 이름과 논리적 소유권의 불일치를 관리 가능한 상태로 둘 수 있다. 근거: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:815)

판정:
- Phase 5 실행 경로로 채택

### Path C: Workflow-only Fix (DB 분리 포기)

정의:
- DB 파일은 하나만 유지
- workflow retention 만 보정해서 scheduled run 후 샘플 누적만 복구

범위:
- `.github/workflows` 수정
- checkout reset/clean 전후 보존 경로 조정
- auto-commit 또는 artifact 유지 전략 조정

예상 세션:
- `2~3`

리스크:
- `낮음`

거부 사유:
- 샘플 누적 자체는 개선될 수 있지만 `orca/state.py` 가 shared adapter 라는 구조적 사실은 그대로 남는다. 근거: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:812)
- candidate/shared cluster 에 대한 ownership 문서를 미루는 대신 기술 부채를 고정하는 효과가 있다.
- Phase 5-A blocker `1` 과 `2` 를 해결하지 못한다. 근거: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:877)

판정:
- 단독 경로로 채택하지 않음

### Path D: Shared Adapter Split (DB 유지 + 파일 분리)

정의:
- DB 파일은 유지
- `orca/state.py` 를 ORCA/JACKAL/Shared 3개 파일로 물리 분리

범위:
- adapter code split
- import 경로 정리
- state bootstrap 분리

예상 세션:
- `5~7`

리스크:
- `중`

거부 사유:
- workflow 가 state 를 잃는 문제는 그대로 남으므로 `샘플이 안 쌓이는 운영 문제` 에 직접 대응하지 못한다. 근거: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:294)
- 구조 정리는 가능하지만, Phase 5 의 핵심 증명 조건인 `scheduled run 후 COUNT > 0` 보장과는 직접 연결되지 않는다.
- 물리 분리는 Phase 6 에서도 다시 다룰 수 있으므로 지금 당장 선행 조건이 아니다.

판정:
- Phase 5 단독 경로로 채택하지 않음

### Path E: Managed DB Service (Supabase + PostgreSQL)

정의:
- SQLite 를 버리고 managed PostgreSQL 로 전환
- local file persistence 대신 networked service ownership 체계로 이동

범위:
- schema migration
- connection management
- secrets/workflow/auth 재설계
- rollback plan 재설계

예상 세션:
- `12~21`

리스크:
- `매우 높음`

거부 사유:
- 외부 서비스 의존이 새로 생긴다.
- 운영 비용과 credential 관리 범위가 늘어난다.
- rollout/rollback 모두 SQLite 수준의 단순성이 사라진다.
- 현재 프로젝트 상황에서는 `2~4주` 규모의 집중이 필요한 트랙으로 분류된다.

판정:
- Phase 5 범위로 채택하지 않음

## Section 3: Path B Scope Definition

이 섹션은 `Path B` 가 정확히 무엇을 포함하고 무엇을 제외하는지 기록한다.

### Included (이번 Phase 5 범위)

#### 1. Category 1 table migration

다음 `7`개 테이블을 `data/jackal_state.db` 로 이동:
- `jackal_shadow_signals`
- `jackal_shadow_batches`
- `jackal_weight_snapshots`
- `jackal_live_events`
- `jackal_recommendations`
- `jackal_accuracy_projection`
- `jackal_cooldowns`

근거:
- `Category 1 (JACKAL-only): 7` 확정. Ref: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:785)

#### 2. `orca/state.py` routing change

이번 Phase 5 에서 수행할 라우팅 성격:
- 위 `7`개 테이블 write API 를 `jackal_state.db` 로 라우팅
- 위 `7`개 테이블 read API 도 동일한 owner DB 를 읽도록 정렬
- 나머지 ORCA/shared table 함수는 그대로 유지
- `init_state_db()` 는 dual-DB bootstrap 관점으로 재검토
- `backfill_candidate_signal_families()` 는 migration-only 함수로 별도 취급

관련 근거:
- write path inventory. Ref: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:247)
- migration-only functions. Ref: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:272)

#### 3. Shared adapter note

파일 상단에 아래 취지의 note 를 박는다:

```python
# NOTE (Phase 5 Path B):
# This module is a shared persistence adapter.
# It owns SQL for both orca_state.db (ORCA core)
# and jackal_state.db (JACKAL learning).
# Path B decision: accept this duality.
# Full adapter split deferred to Phase 6.
# See docs/phase5/02-path-decision.md for rationale.
```

의미:
- `orca/state.py` 이름과 논리적 소유권이 다를 수 있음을 코드 내부에서 명시
- Path B 가 “temporary accident” 가 아니라 “문서화된 수용 결정” 임을 고정

#### 4. Workflow update scope

대상 workflow:
- [orca_daily.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/orca_daily.yml)
- [orca_jackal.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/orca_jackal.yml)
- [jackal_tracker.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/jackal_tracker.yml)
- [jackal_scanner.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/jackal_scanner.yml)

이번 Phase 5 범위에서 고정할 원칙:
- `data/orca_state.db` 와 `data/jackal_state.db` 를 둘 다 보존 대상으로 본다.
- 구체 retention/commit/artifact 전략은 `Phase 5-D` 에서 결정한다.

### Excluded (Phase 6 이월)

#### Category 3 shared tables (`5`)

- `backtest_sessions`
- `backtest_daily_results`
- `backtest_pick_results`
- `candidate_registry`
- `candidate_outcomes`

근거:
- `Category 3 (Shared): 5`. Ref: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:787)

#### Category 4 ambiguous tables (`2`)

- `candidate_reviews`
- `candidate_lessons`

근거:
- `Category 4 (Ambiguous): 2`. Ref: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:788)

#### Exclusion rationale

- `candidate_*` cluster 는 ORCA와 JACKAL 사이의 candidate/evidence spine 으로 확인되었다. Ref: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:719)
- 이를 분리하려면 table relocation 이 아니라 이벤트 경로 재설계가 필요하다.
- `backtest_*` cluster 도 이미 shared 로 판정되었기 때문에 이번 범위에 넣으면 Phase 5 가 full separation 으로 팽창한다.

### Deferred to Phase 6

Phase 6 으로 이월되는 구조 과제:
1. `candidate_registry` 재설계
2. `candidate_outcomes` ownership / lifecycle 재설계
3. `candidate_reviews`, `candidate_lessons` category 확정
4. `backtest_*` cluster 분리 전략
5. `orca/state.py` 를 shared adapter 에서 물리적으로 분리할지 여부

Phase 6 prerequisites:
- Phase 5 완료
- JACKAL 학습 루프 안정화
- scheduled run 후 sample 누적 시작
- `candidate_registry` 에 실제 데이터가 쌓이기 시작
  - 현재 스냅샷 `COUNT = 0`. Ref: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:205)

### Phase 6 candidates (JACKAL feature expansion, separate track)

이미 backlog 에 등록된 Phase 6 기능 확장 후보:
- `P1. Cross-stock correlation`
- `P2. Relative strength vs market`
- `P3. Squeeze + breakout direction`

근거 문서:
- backlog: [orca_v2_backlog.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/orca_v2_backlog.md:86)
- current signal map:
  - [current-signals.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/jackal/current-signals.md:1004)
  - [current-signals.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/jackal/current-signals.md:1052)
  - [current-signals.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/jackal/current-signals.md:1090)

의미:
- Phase 6 은 두 개 트랙으로 갈라진다.
- 하나는 `candidate/shared adapter` 재설계 트랙이다.
- 다른 하나는 `JACKAL signal factor expansion` 트랙이다.
- 이 문서에서 결정한 Path B 는 먼저 전자의 전제 조건만 만든다.

## Section 4: Known Accepted Risks for Path B

Path B 는 구조 리스크를 “모른 척” 하는 것이 아니라, 명시적으로 수용하고 다음 단계 범위로 옮기는 결정이다.

### Risk 1: 2-phase write

설명:
- 일부 JACKAL API 는 `jackal_state.db` 와 `orca_state.db` 양쪽에 write 하게 된다.
- 두 파일 DB 사이에는 single transaction 을 걸 수 없다.
- 한쪽 write 성공, 다른 쪽 write 실패가 가능하다.

대표 함수:
- `sync_jackal_live_events()`
  - `jackal_live_events` write
  - side effect 로 `record_candidate()` 경로를 타면 `candidate_registry` write 발생
- `record_jackal_shadow_signal()`
  - `jackal_shadow_signals` write
  - side effect 로 `record_candidate()` write 발생
- `resolve_jackal_shadow_signal()`
  - `jackal_shadow_signals` update
  - resolved payload 를 기반으로 downstream candidate write 가능

근거:
- JACKAL event / learning writes. Ref: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:247)
- candidate write side effects. Ref: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:256)

문제 정의:
- file split 후 cross-DB atomicity 는 보장되지 않음
- scheduled run 중 partial failure 가 나면 candidate/event spine 간 불일치 가능

수용 근거:
- 현재도 각 write 가 별도 `conn.execute + commit` 구조이므로 atomicity 가 강하지 않다.
- Phase 5 의 우선 순위는 `JACKAL 샘플 누적 시작` 이다.
- candidate spine 재설계는 Phase 6 독립 과제로 떼어내는 편이 범위 관리에 맞다.

Phase 5 대응:
- 2-phase write 함수 목록을 `Phase 5-B` 설계 문서에 명시
- 실패 시 health/event log 남김
- `Phase 5-C` 검증에 cross-DB consistency check 포함

### Risk 2: `orca/state.py` 가 여전히 shared

설명:
- Path B 이후에도 `orca/state.py` 는 두 DB 의 SQL adapter 역할을 수행한다.
- 물리 파일 이름과 논리적 소유권이 계속 일치하지 않는다.

근거:
- Stop Condition 1 결과 `found`. Ref: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:799)
- design intent summary. Ref: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:812)

선택한 mitigation:
- 파일 상단에 shared adapter note 삽입
- 이 문서를 공식 rationale 로 연결

### Risk 3: Workflow 복잡도 증가

설명:
- workflow 가 다루는 persisted state artifact 가 `1개` 에서 `2개` 로 늘어난다.

추가 DB:
- `data/orca_state.db`
- `data/jackal_state.db`

영향 workflow:
- [orca_daily.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/orca_daily.yml)
- [orca_jackal.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/orca_jackal.yml)
- [jackal_tracker.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/jackal_tracker.yml)
- [jackal_scanner.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/jackal_scanner.yml)

대응:
- `Phase 5-D` 에서 workflow 별 write path / save path / retention path 설계
- concurrency 및 overwrite 우선순위 검토

## Section 5: Success Criteria for Phase 5 (Path B)

Phase 5 완료 판정 기준:

1. `data/jackal_state.db` 파일 생성

2. `Category 1` 의 `7`개 테이블이 `jackal_state.db` 에 존재
- `jackal_shadow_signals`
- `jackal_shadow_batches`
- `jackal_weight_snapshots`
- `jackal_live_events`
- `jackal_recommendations`
- `jackal_accuracy_projection`
- `jackal_cooldowns`

3. `orca/state.py` 의 `jackal_*` write API 가 `jackal_state.db` 로 라우팅

4. 아래 `4`개 workflow 에서 `jackal_state.db` 보존 동작 확인
- [orca_daily.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/orca_daily.yml)
- [orca_jackal.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/orca_jackal.yml)
- [jackal_tracker.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/jackal_tracker.yml)
- [jackal_scanner.yml](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/.github/workflows/jackal_scanner.yml)

5. scheduled run 후 아래 둘 중 하나 이상 관측
- `jackal_shadow_signals COUNT > 0`
- `jackal_live_events COUNT > 0`

이 항목이 Path B 의 핵심 증명이다. 이유: Phase 5-A baseline 에서는 Tier 1 JACKAL table count 가 모두 `0` 이었다. Ref: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:17)

6. 기존 PR 1-5 계약 유지
- `PR 1`: HealthTracker code 10개 유지
- `PR 2`: `learning_policy v1` schema 유지
- `PR 3`: `main.py` thin coordinator (`<50 lines`) 유지
- `PR 4`: candidate review scorecard 동작
- `PR 5`: external data visibility 동작

이 문서의 관점:
- Path B 는 새로운 DB 경계를 만든다.
- Path B 는 기존 계약을 깨는 리팩터링이 아니다.

## Section 6: Phase 5 Sub-phase Plan

Path B 실행은 `4`개 sub-phase 로 나눈다.

### Phase 5-B: Design

목표:
- `jackal_state.db` schema 정의
- `orca/state.py` dual-DB routing map 정의
- 2-phase write 함수 목록 확정
- `paths.py` / bootstrap 영향 범위 고정

산출물:
- 설계 문서
- function routing table
- risk checklist

예상 세션:
- `1~2`

### Phase 5-C: Implementation

목표:
- `jackal_state.db` 생성 코드 추가
- Category 1 read/write API 라우팅 구현
- `init_state_db()` dual bootstrap 처리
- `backfill_candidate_signal_families()` 의 Phase 5 위치 확정

산출물:
- Python code changes
- migration/bootstrap helpers
- 검증 로그

예상 세션:
- `2~4`

### Phase 5-D: Workflow Integration

목표:
- 4개 workflow 에서 dual DB 보존 전략 구현
- reset/clean/save/commit 순서 재정의
- artifact or commit ownership 정리
- concurrency 검토

산출물:
- workflow changes
- scheduled run persistence check

예상 세션:
- `2~3`

리스크:
- 이번 Path B 전체에서 가장 높은 실행 리스크를 가진다.

### Phase 5-E: Cleanup

목표:
- 기존 `orca_state.db` 에서 Category 1 table 제거 또는 비활성화 전략 적용
- `.gitignore` / save policy 정리
- old data cleanup / one-time migration 정리

산출물:
- cleanup commit
- post-migration 확인 결과

예상 세션:
- `1`

총 예상:
- `6~10` 세션

## Section 7: Lessons from Path Decision Process

이번 경로 결정 과정에서 얻은 교훈:

### Lesson 1. “단순 분리” 가정은 schema 조사 없이 성립하지 않는다

- Phase 5-A 초기에 prefix 기준 이동만 보면 `jackal_*` table relocation 으로 보일 수 있었다.
- 하지만 `Section 3.5 Reference Graph` 와 `Section 5 Category Classification` 을 보면 shared/ambiguous cluster 가 별도 문제로 드러났다.
- 특히 `candidate_registry` 가 shared spine 이라는 점이 경로 선택을 바꿨다. Ref: [01-db-audit.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/phase5/01-db-audit.md:719)

### Lesson 2. 물리적 파일 이름과 논리적 소유권은 다를 수 있다

- `orca/state.py` 는 이름상 ORCA 파일이지만 실제로는 ORCA와 JACKAL 양쪽 SQL adapter 로 동작한다.
- 이름만 보고 ownership 을 추정하면 잘못된 설계 결정을 내리기 쉽다.
- Path B 는 이 불일치를 “숨기지 않고 문서화하는” 선택이다.

### Lesson 3. 개인 프로젝트 규모에서는 bounded fix 가 맞을 때가 있다

- `Path E` 같은 managed DB 전환은 기술적으로 더 근본적인 경로일 수 있다.
- 하지만 이번 프로젝트 상황에서는 시간, 외부 의존성, rollback 부담이 함께 증가한다.
- Path B 는 “근본 해결 완수” 가 아니라 “지금 운영 병목을 끊는 경계” 에 초점을 둔다.

### Lesson 4. 설계 결정은 코드보다 먼저 문서로 고정해야 한다

- Phase 5-A 결과만 있고 path decision 문서가 없으면, 이후 구현 단계에서 다시 Path A/B/C 논쟁이 반복될 수 있다.
- 이 문서는 그 재논쟁을 막기 위한 기준점이다.

### Lesson 5. Phase 6 스코프도 지금 문서화해야 한다

- candidate spine 재설계는 이번에 해결하지 않는다.
- 대신 “무엇을 안 하기로 했는지”와 “왜 안 하는지”를 지금 기록해야 Phase 5 범위가 흔들리지 않는다.
- JACKAL feature expansion 후보도 별도 Phase 6 트랙으로 backlog 에 이미 고정해 두었다. Ref: [orca_v2_backlog.md](/C:/Users/skyco/OneDrive/문서/GitHub/O.R.C.A/docs/orca_v2_backlog.md:86)

Closing statement:
- Path B 는 최종 구조가 아니라 `Phase 5용 경계 결정` 이다.
- 이 문서의 역할은 “왜 지금 이 경계를 택했는가”를 남기는 것이다.
