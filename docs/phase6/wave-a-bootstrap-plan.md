# Phase 6 Wave A Bootstrap Plan

작성 시점:
2026-04-24

상태:
Wave A bootstrap rerun plan after artifact handoff fix

목적:
1. ORCA 13개월 research preflight 결과를 artifact로 확보한다.
2. JACKAL persisted learning workflow가 그 artifact를 재사용해
   ORCA refresh를 다시 호출하지 않도록 한다.
3. `candidate_registry`, `candidate_outcomes`,
   `candidate_lessons`가 main branch 기준 DB에 실제 반영됐는지
   검증한다.

핵심 원칙:
- `orca_backtest.yml`은 artifact-only로 유지한다.
- persisted bootstrap은 `jackal_backtest_learning.yml`이 담당한다.
- bootstrap 수동 재실행에서는 artifact handoff를 우선 사용한다.
- daily incremental은 기존 persisted DB를 재사용한다.
- monthly full은 artifact 없이도 동작하지만 rate limit 위험이 있다.

## Section 1: 실행 모드 요약

Mode 1.
수동 bootstrap handoff

조건:
- `mode=full`
- `artifact_run_id` 제공

동작:
- `research-state-<run_id>` artifact 다운로드
- ORCA refresh skip
- JACKAL full materialization 실행
- learning state commit / push

장점:
- 외부 fetch 재호출 없음
- yfinance rate limit 위험 제거
- bootstrap 재현성 높음

Mode 2.
월간 full self-refresh

조건:
- `mode=full`
- `artifact_run_id` 비어 있음

동작:
- ORCA refresh 자체 실행
- JACKAL full materialization 실행
- learning state commit / push

주의:
- 외부 fetch를 다시 수행하므로 rate limit 위험이 있다.
- 실패 시 Mode 1 수동 2-step bootstrap으로 대체한다.

Mode 3.
일일 incremental

조건:
- `mode=incremental`

동작:
- ORCA refresh skip
- 기존 main branch DB의 최신 ORCA session 재사용
- delta 기반 learning materialization 실행

## Section 2: 재실행 절차

### Step 1: ORCA Research Preflight

실행:
1. GitHub Actions에서 `ORCA Backtest` workflow를 선택한다.
2. `Run workflow`를 눌러 수동 실행한다.
3. 완료까지 기다린다.

예상 시간:
- 10~95분

성공 기준:
- workflow status = success
- artifact `research-state-<run_id>` 생성
- ORCA 13개월 walk-forward summary 생성
- log에 `python -m orca.backtest --months 13 --walk-forward --fail-on-empty-dynamic-fetch`
  실행 흔적 존재

run_id 추출:
- Actions URL 마지막 숫자를 사용한다.
- 예:
  `/actions/runs/24828017570`
- 이 경우 `run_id = 24828017570`

메모:
- 이 Step은 artifact만 만든다.
- main branch DB를 직접 갱신하지 않는다.

### Step 2: JACKAL Persisted Bootstrap

실행:
1. GitHub Actions에서 `JACKAL Backtest Learning` workflow를 선택한다.
2. `Run workflow`를 누른다.
3. 입력값을 아래처럼 넣는다.

입력값:
- `mode: full`
- `artifact_run_id: <Step 1의 run_id>`

예시:
- `mode: full`
- `artifact_run_id: 24828017570`

예상 시간:
- 1~3분

예상 동작:
- artifact download
- `data/orca_state.db` 검증
- ORCA refresh skip
- `python -m jackal.backtest --mode full`
- `data/orca_state.db`, `data/jackal_state.db` checkpoint
- commit / push

성공 기준:
- workflow status = success
- `Run JACKAL backtest learning` step 실행됨
- `Save learning state` step 실행됨
- main branch 최신 commit에 DB checkpoint 반영

중요:
- 이 Step은 ORCA refresh를 다시 실행하지 않는다.
- artifact handoff 경로에서는 외부 fetch가 없어야 한다.

### Step 3: Main DB 검증

로컬에서:
1. `git pull`
2. 아래 SQL 3개를 실행한다.

검증 SQL 1.
```sql
SELECT COUNT(*), source_event_type
FROM candidate_registry
GROUP BY source_event_type;
```

검증 SQL 2.
```sql
SELECT COUNT(*)
FROM candidate_outcomes;
```

검증 SQL 3.
```sql
SELECT COUNT(*)
FROM candidate_lessons;
```

권장 추가 검증:
```sql
SELECT COUNT(*)
FROM candidate_registry
WHERE source_event_type = 'backtest';
```

성공 기준:
- `candidate_registry`에 `backtest` row 존재
- `candidate_outcomes > 0`
- `candidate_lessons > 0`

이 세 조건이 모두 만족되면:
- Wave A bootstrap COMPLETE

## Section 3: 실패 시 대응

Case 1.
artifact download 실패

확인:
- `artifact_run_id`가 맞는지
- Step 1 workflow가 실제로 success였는지
- artifact 이름이 `research-state-<run_id>`인지
- artifact가 90일 보존 기간 내인지

Case 2.
artifact verify 실패

확인:
- `data/orca_state.db`가 artifact 안에 포함됐는지
- 파일 크기가 1KB 이상인지
- sqlite open이 되는지
- `backtest_sessions` 테이블이 존재하는지

Case 3.
JACKAL materialization 실패

확인:
- `python -m jackal.backtest --mode full` step 로그
- incremental cursor 관련 로그
- candidate materialization summary 로그

Case 4.
main DB 반영 안 됨

확인:
- `Save learning state` step에서 commit/push가 성공했는지
- `git diff --cached --quiet && exit 0`로 조용히 빠진 것은 아닌지
- push 이후 branch state가 최신인지

## Section 4: 운영 전환 후 cadence

일일 운영:
- `jackal_backtest_learning.yml`
- `mode=incremental`
- ORCA refresh 없음
- persisted DB 기준 delta materialization

월간 운영:
- `jackal_backtest_learning.yml`
- `mode=full`
- `artifact_run_id` 없이 실행 시 self-refresh

권장 운영:
- 정기 월간 full이 실패하면
- 같은 날 수동 2-step bootstrap으로 대체한다.

## Section 5: 참고 로그 체크포인트

Mode 1에서 기대하는 로그:
- `Mode 1: Artifact handoff (ORCA refresh skipped)`
- `Download preflight ORCA artifact`
- `Verify ORCA artifact`
- `Artifact verified: ... tables`
- `Run JACKAL backtest learning`
- `Save learning state`

Mode 2에서 기대하는 로그:
- `Mode 2: Full rebuild with self-refresh`
- `Refresh ORCA research session`

Mode 3에서 기대하는 로그:
- `Mode 3: Daily incremental`
- `Run JACKAL backtest learning`
- ORCA refresh step은 skip

## Section 6: Rollback 기준

rollback이 필요하면 아래 순서로 진행한다.

1. 문제 run의 `source_session_id`를 찾는다.
2. `source_event_type = 'backtest'` 기준으로 영향 row를 확인한다.
3. 필요 시 `candidate_lessons` → `candidate_outcomes` →
   `candidate_registry` 순서로 삭제한다.
4. Step 1부터 bootstrap을 다시 실행한다.

주의:
- live sample과 backtest sample은 혼합하지 않는다.
- rollback 쿼리는 반드시 `source_event_type='backtest'`와
  `source_session_id`를 함께 사용한다.

## Section 7: 빠른 체크리스트

실행 전:
- Step 1 success 확인
- `run_id` 확인
- artifact 이름 확인

실행 중:
- Mode 1 로그 확인
- artifact verify 통과 확인
- JACKAL learning step 실행 확인

실행 후:
- main branch pull
- SQL 3개 검증
- `source_event_type='backtest'` row 확인
