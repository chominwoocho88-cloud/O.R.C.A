# Phase 6 Wave A Bootstrap Plan

작성 시점:
2026-04-23

상태:
Wave A initial bootstrap runbook

목적:
1년 JACKAL backtest sample을 ORCA candidate learning spine으로 채우고,
이후 daily incremental + monthly full cadence로 유지한다.

핵심 원칙:
- `orca_backtest.yml` 는 계속 artifact-only 로 유지한다.
- persisted learning state 는 `jackal_backtest_learning.yml` 이 책임진다.
- JACKAL probability activation 은 Wave A 에서 `backtest only` 로 고정한다.
- live sample 혼합은 이번 Wave 범위 밖이다.

## Section 1: Bootstrap 개요

초기 bootstrap 은 아래 2단계로 진행한다.

Step 1.
`orca_backtest.yml` workflow_dispatch

목적:
- 13개월 ORCA research session 이 정상 생성되는지 preflight 확인
- artifact-only 경로가 깨지지 않았는지 확인

주의:
- 이 step 은 `data/orca_state.db` 를 repo main 에 persist 하지 않는다.
- 운영 기준 authoritative bootstrap 은 Step 2 다.

Step 2.
`jackal_backtest_learning.yml` workflow_dispatch with `mode=full`

목적:
- ORCA 13개월 walk-forward refresh
- JACKAL 252 trading day full materialization
- `candidate_registry / candidate_outcomes / candidate_lessons` 채우기
- 이후 daily incremental 의 기준 cursor 생성

## Section 2: 예상 실행 시간

Step 1.
`orca_backtest.yml`

예상:
- 약 10~20분

Step 2.
`jackal_backtest_learning.yml` with `mode=full`

예상:
- ORCA refresh 포함 약 25~45분

일일 운영:
- `jackal_backtest_learning.yml` daily incremental
- 약 2~6분

월간 운영:
- `jackal_backtest_learning.yml` monthly full
- 약 25~45분

## Section 3: Step 1 상세

실행:
1. GitHub Actions 에서 `ORCA Backtest` workflow 선택
2. `Run workflow`
3. 기본값 사용

성공 기준:
- workflow status = success
- `research-state-<run_id>` artifact 생성
- ORCA research session summary 에 13개월 확장 흔적 존재

실패 시 확인:
- `python -m orca.backtest --months 13 --walk-forward --fail-on-empty-dynamic-fetch`
  가 workflow log 에 실제 찍혔는지
- dynamic fetch zero-day fail 인지
- 외부 API key 누락인지

## Section 4: Step 2 상세

실행:
1. GitHub Actions 에서 `JACKAL Backtest Learning` workflow 선택
2. `Run workflow`
3. input `mode=full`
4. 실행 완료까지 대기

이 workflow 가 수행하는 일:
- full mode 이므로 ORCA 13개월 research refresh 실행
- JACKAL `python -m jackal.backtest --mode full` 실행
- `data/orca_state.db` 와 `data/jackal_state.db` checkpoint
- 변경분 commit / push

성공 기준:
- workflow status = success
- repo main 에 최신 `data/orca_state.db` 반영
- latest JACKAL backtest session summary 에 아래 필드 존재
  - `selection_mode=full`
  - `materialized_candidates > 0`
  - `materialized_outcomes > 0`
  - `materialized_lessons > 0`
  - `last_materialized_analysis_date` 존재

## Section 5: 검증 쿼리

### 5.1 sqlite3 예시

```sql
SELECT COUNT(*)
FROM candidate_registry
WHERE source_event_type = 'backtest';
```

```sql
SELECT COUNT(*)
FROM candidate_outcomes
WHERE candidate_id IN (
  SELECT candidate_id
  FROM candidate_registry
  WHERE source_event_type = 'backtest'
);
```

```sql
SELECT COUNT(*)
FROM candidate_lessons
WHERE candidate_id IN (
  SELECT candidate_id
  FROM candidate_registry
  WHERE source_event_type = 'backtest'
);
```

```sql
SELECT source_event_type, signal_family, COUNT(*)
FROM candidate_registry
GROUP BY source_event_type, signal_family
ORDER BY source_event_type, COUNT(*) DESC;
```

### 5.2 Python fallback

```python
import sqlite3

conn = sqlite3.connect("data/orca_state.db")
cur = conn.cursor()

queries = {
    "candidate_registry_backtest": """
        SELECT COUNT(*)
          FROM candidate_registry
         WHERE source_event_type = 'backtest'
    """,
    "candidate_outcomes_backtest": """
        SELECT COUNT(*)
          FROM candidate_outcomes
         WHERE candidate_id IN (
               SELECT candidate_id
                 FROM candidate_registry
                WHERE source_event_type = 'backtest'
         )
    """,
    "candidate_lessons_backtest": """
        SELECT COUNT(*)
          FROM candidate_lessons
         WHERE candidate_id IN (
               SELECT candidate_id
                 FROM candidate_registry
                WHERE source_event_type = 'backtest'
         )
    """,
}

for name, sql in queries.items():
    print(name, cur.execute(sql).fetchone()[0])

conn.close()
```

### 5.3 기대값

초기 bootstrap 직후 기대:
- `candidate_registry_backtest > 0`
- `candidate_outcomes_backtest > 0`
- `candidate_lessons_backtest > 0`

권장 확인:
- `candidate_registry_backtest` 가 대략 `252 * 5 = 1260` 보다 작더라도
  `0` 이 아니면 feed 경로는 살아있다고 본다.
- 실제 수치는 데이터 누락 종목, 상장일 부족, 추적 불가 날짜 때문에 더 작을 수 있다.

## Section 6: Rollback 절차

원칙:
- Wave A rollback 은 `source_event_type='backtest'` 와
  `source_session_id='<jackal_session_id>'` 기준으로 수행한다.

순서:
1. latest failed / suspect JACKAL backtest session id 확인
2. 아래 순서로 삭제

```sql
DELETE FROM candidate_lessons
WHERE candidate_id IN (
  SELECT candidate_id
  FROM candidate_registry
  WHERE source_event_type = 'backtest'
    AND source_session_id = '<jackal_session_id>'
);
```

```sql
DELETE FROM candidate_outcomes
WHERE candidate_id IN (
  SELECT candidate_id
  FROM candidate_registry
  WHERE source_event_type = 'backtest'
    AND source_session_id = '<jackal_session_id>'
);
```

```sql
DELETE FROM candidate_registry
WHERE source_event_type = 'backtest'
  AND source_session_id = '<jackal_session_id>';
```

3. 필요 시 해당 session 을 기준으로 full bootstrap 재실행

주의:
- live candidate 는 건드리지 않는다.
- `source_event_type='backtest'` filter 없이 bulk delete 하지 않는다.

## Section 7: 운영 전환 후 cadence

Daily incremental:
- workflow: `jackal_backtest_learning.yml`
- mode: `incremental`
- 스케줄: ORCA daily MORNING 이후
- ORCA persisted research session + 최신 `memory.json` 을 합쳐 신규 trading day 만 materialize

Monthly full:
- workflow: `jackal_backtest_learning.yml`
- mode: `full`
- ORCA 13개월 research refresh 포함
- candidate spine full re-materialize

Manual preflight:
- workflow: `orca_backtest.yml`
- artifact-only
- 계약 검증 및 연구 확인용

## Section 8: 운영 중 체크포인트

매일 확인할 항목:
- latest JACKAL backtest session status
- `last_materialized_analysis_date`
- `materialized_candidates / outcomes / lessons`

매월 확인할 항목:
- `summarize_candidate_probabilities(source_event_types=['backtest'])`
  기준 `raw_rows`, `deduped_rows`
- family 별 qualified 여부
- `jackal/probability.py` adjustment 가 실제로 non-zero 인 family 존재 여부

## Section 9: Known Caveats

- Step 1 artifact-only ORCA backtest 는 persisted bootstrap 을 대체하지 않는다.
- daily incremental 은 ORCA daily 가 만든 최신 `memory.json` 을 활용하므로,
  research walk-forward session 자체를 매일 full rebuild 하지는 않는다.
- Wave A 는 backtest-only probability activation 이다.
  live sample 혼합 정책은 이후 Wave 에서 재검토한다.
