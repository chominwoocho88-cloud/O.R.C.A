# Wave A-fix 3 Runbook

작성 시점:
2026-04-24

상태:
runbook

목적:
Mode 1 artifact handoff를 promote-only 경로로 재설계해서,
이미 성공한 ORCA + JACKAL artifact를 main DB에 그대로 반영한다.

배경:
- Wave A-fix 1은 artifact handoff 경로를 추가했지만,
  Mode 1에서도 `python -m jackal.backtest --mode full`을 다시 실행했다.
- 그 결과 artifact 안의 `1260` rows가 main에 남지 않고,
  오래된 ORCA session 기반 `280` rows가 새 session으로 덮어써졌다.

Fix 3 핵심:
- Mode 1 = artifact promote only
- Mode 2 = self-refresh + full replay
- Mode 3 = daily incremental

## 1. 이전 Fix들과의 관계

Wave A-fix 1:
- artifact handoff 경로 추가
- `artifact_run_id` input 도입

Wave A-fix 2:
- backtest family bug 수정
- JACKAL backtest cleanup SQL + runbook 작성

Wave A-fix 3:
- Mode 1에서 JACKAL 재실행 제거
- WAL checkpoint + strict verify 추가
- artifact를 그대로 commit/push 하도록 정렬

## 2. Mode 정의

### Mode 1: artifact promote only

사용 시나리오:
- 수동 bootstrap
- 이미 `orca_backtest.yml`이 성공했고, 그 artifact를 main에 반영하고 싶을 때

Flow:
1. artifact download
2. WAL checkpoint
3. strict verify
4. JACKAL 재실행 skip
5. save learning state

예상 결과:
- artifact 안의 `candidate_registry(backtest)`가 그대로 main에 반영
- 기대치: `1260 / 2520 / 1260`

### Mode 2: self-refresh + full replay

사용 시나리오:
- 월간 cron fallback
- artifact 없이 full rebuild가 필요할 때

Flow:
1. ORCA refresh
2. JACKAL full replay
3. save learning state

주의:
- 외부 fetch가 발생한다
- rate limit 리스크가 있다

### Mode 3: daily incremental

사용 시나리오:
- 평일 incremental learning

Flow:
1. 기존 main DB 사용
2. JACKAL incremental replay
3. save learning state

## 3. 재실행 절차

### Step 1: ORCA Backtest artifact 준비

성공 artifact:
- run id: `24847623560`
- artifact name: `research-state-24847623560`

같은 날 생성된 artifact이므로 90일 보존 기간 안이다.

### Step 2: JACKAL Learning promote

Actions에서 `jackal_backtest_learning.yml` 수동 실행:

- `mode: full`
- `artifact_run_id: 24847623560`

기대 로그:

```text
Mode 1: Artifact handoff (ORCA refresh skipped)
WAL checkpoint complete
✅ Artifact verified:
```

중요:
- Mode 1에서는 `Run JACKAL backtest learning` step이 실행되면 안 된다.

### Step 3: main DB 검증

로컬에서 최신 main pull 후 SQL 검증:

```sql
SELECT COUNT(*), source_event_type
FROM candidate_registry
GROUP BY source_event_type;
```

Expected:
- `backtest ~1260`

```sql
SELECT COUNT(*)
FROM candidate_outcomes;
```

Expected:
- `~2520`

```sql
SELECT COUNT(*)
FROM candidate_lessons;
```

Expected:
- `~1260`

```sql
SELECT source_session_id, COUNT(*)
FROM candidate_registry
WHERE source_event_type='backtest'
GROUP BY source_session_id;
```

Expected:
- `1 row`
- artifact의 JACKAL session 하나만 보존

## 4. 실패 시 확인 포인트

1. artifact download가 실제 성공했는지
2. WAL checkpoint step이 실행됐는지
3. strict verify가 `candidate_registry(backtest) >= 1000`을 통과했는지
4. Mode 1에서 JACKAL rerun step이 skip됐는지
5. Save learning state가 `data/orca_state.db`를 commit/push했는지

## 5. 완료 기준

Wave A-fix 3 완료 기준:

1. Mode 1이 promote-only로 동작
2. JACKAL rerun 없이 artifact state가 main에 반영
3. main DB에 `candidate_registry(backtest) ~1260`
4. `candidate_outcomes ~2520`
5. `candidate_lessons ~1260`
6. bootstrap artifact session이 실제 main DB에서 관찰됨
