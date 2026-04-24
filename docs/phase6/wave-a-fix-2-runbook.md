# Wave A-fix 2 Runbook

작성 시점:
2026-04-24

상태:
runbook

목적:
Wave A bootstrap 이후 확인된 두 가지 문제를 정리하고, backtest state를 clean 상태로 되돌린 뒤 artifact handoff 기반 bootstrap을 다시 수행한다.

범위:
- JACKAL backtest learning state cleanup
- family bug 수정 반영 여부 확인
- artifact handoff 기반 bootstrap 재실행

범위 밖:
- ORCA walk-forward session 삭제
- workflow chaining
- probability 퍼센트 노출

## 1. 왜 Fix 2가 필요했나

당시 확인된 문제는 두 가지였다.

1. DB/session mismatch
   - bootstrap 로그는 `1260` rows와 session `bt_d76cc1...`를 보여줬지만
   - main/local DB는 `275` 또는 `280` rows만 남아 있었다.

2. Family bug
   - backtest materialization이 `signal_family="general"`을 하드코딩해서
   - canonical family가 사실상 `momentum_pullback`, `divergence`, `oversold_rebound` 세 family에만 몰렸다.

Fix 2의 목표는:
- JACKAL backtest state만 깨끗하게 비우고
- family bug 수정이 들어간 코드로
- artifact handoff 기반 bootstrap을 다시 돌리는 것이다.

## 2. 사전 조건

- 최신 코드를 pull 해둔다.
- `scripts/cleanup_backtest_state.sql`이 workspace에 있어야 한다.
- backup 없이 cleanup을 진행하지 않는다.

## 3. Step 1: 로컬 DB backup

PowerShell:

```powershell
Copy-Item data\orca_state.db data\orca_state.pre-wave-a-fix-2.db
```

검증:

```powershell
Get-Item data\orca_state.pre-wave-a-fix-2.db
```

## 4. Step 2: JACKAL backtest state cleanup

cleanup 대상은 JACKAL-owned backtest state만이다. ORCA walk-forward session은 보존한다.

실행:

```powershell
sqlite3 data/orca_state.db < scripts/cleanup_backtest_state.sql
```

cleanup 대상:
- `candidate_registry`
  - `source_event_type='backtest'`
  - `source_system='jackal'`
- `candidate_outcomes`
  - 위 candidate와 연결된 rows
- `candidate_lessons`
  - 위 candidate와 연결된 rows
- `backtest_sessions`
  - `system='jackal'`
- `backtest_pick_results`
  - 위 JACKAL session에 연결된 rows
- `backtest_daily_results`
  - 위 JACKAL session에 연결된 rows
- `backtest_state`
  - 위 JACKAL session에 연결된 rows

보존 대상:
- ORCA `backtest_sessions`
- ORCA `backtest_daily_results`
- ORCA `backtest_state`

cleanup 직후 확인:

```sql
SELECT COUNT(*)
FROM candidate_registry
WHERE source_event_type='backtest';
```

Expected:
`0`

```sql
SELECT COUNT(*)
FROM backtest_sessions
WHERE system='jackal';
```

Expected:
`0`

## 5. Step 3: ORCA research preflight

Actions에서 `orca_backtest.yml`를 수동 실행한다.

예상 시간:
- 빠르면 10~20분
- 실제 데이터 상황에 따라 60~95분 근접 가능

완료 후 확인:
- success status
- artifact 생성
- run URL에서 `run_id` 확보

예:
- URL: `.../actions/runs/24847623560`
- `run_id = 24847623560`

## 6. Step 4: JACKAL persisted bootstrap

Actions에서 `jackal_backtest_learning.yml`를 수동 실행한다.

Inputs:
- `mode: full`
- `artifact_run_id: <Step 3 run_id>`

중요:
- `artifact_run_id`를 비우지 않는다
- 비우면 Mode 2로 떨어져 ORCA refresh를 다시 호출하고 rate limit 실패가 재발할 수 있다

Fix 3 이후 Mode 1 기대 동작:
- artifact download
- strict verify
- JACKAL 재실행 없음
- save learning state

예상 시간:
- 1~3분

## 7. Step 5: main DB 검증

workflow 성공 후 로컬에서 최신 main을 pull 한다.

```powershell
git pull
```

아래 SQL 네 가지를 확인한다.

### 7.1 Origin 분포

```sql
SELECT COUNT(*), source_event_type
FROM candidate_registry
GROUP BY source_event_type;
```

Expected:
- `backtest` rows가 대략 `1260`

### 7.2 Outcomes / Lessons

```sql
SELECT COUNT(*)
FROM candidate_outcomes;
```

Expected:
- 대략 `2520`

```sql
SELECT COUNT(*)
FROM candidate_lessons;
```

Expected:
- 대략 `1260`

### 7.3 Family 분포

```sql
SELECT signal_family, COUNT(*)
FROM candidate_registry
WHERE source_event_type='backtest'
GROUP BY signal_family
ORDER BY COUNT(*) DESC;
```

Expected:
- 최소 `4개 이상` family
- 특히 아래 중 최소 하나 이상 새로 보여야 한다
  - `rotation`
  - `panic_rebound`
  - `ma_reclaim`

### 7.4 Session 단일성

```sql
SELECT source_session_id, COUNT(*)
FROM candidate_registry
WHERE source_event_type='backtest'
GROUP BY source_session_id;
```

Expected:
- `1 row`
- 새 bootstrap session 하나로 정리

## 8. 실패 시 대응

### Artifact 다운로드 실패

확인:
- `artifact_run_id`가 맞는지
- Step 3 run이 실제 성공했는지
- artifact가 보존 기간 내인지

### Sample 수량이 예상보다 적은 경우

확인:
- `source_session_id`가 하나인지
- ORCA artifact가 실제 13개월 coverage인지
- family bug 수정 커밋이 workflow에 반영됐는지

### Family가 다시 세 개만 나오는 경우

확인:
- deployed workflow가 fix-2 이후 커밋인지
- `signal_family_raw`가 여전히 `general`로 박혀 있는지

## 9. Rollback

backup으로 복원:

```powershell
Copy-Item data\orca_state.pre-wave-a-fix-2.db data\orca_state.db -Force
```

검증:

```sql
SELECT COUNT(*), source_event_type
FROM candidate_registry
GROUP BY source_event_type;
```

## 10. 완료 기준

아래를 모두 만족하면 Fix 2 목표는 달성된 것으로 본다.

1. cleanup 후 JACKAL backtest rows가 `0`
2. artifact handoff bootstrap 성공
3. `candidate_registry(backtest)`가 대략 `1260`
4. `candidate_outcomes`가 대략 `2520`
5. `candidate_lessons`가 대략 `1260`
6. `source_session_id`가 bootstrap session 하나로 정리
7. backtest family 분포가 4개 이상으로 확장

참고:
- 이후 Mode 1 promote-only / isolated promote 문제는 Fix 3, Fix 4 runbook을 따른다.
