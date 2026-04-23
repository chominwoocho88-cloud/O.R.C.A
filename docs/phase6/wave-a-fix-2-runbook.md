# Wave A-fix 2 Runbook

작성 시점:
2026-04-24

상태:
runbook

목적:
Wave A bootstrap 이후 main DB 정합성이 bootstrap artifact와 어긋난 상태를 복구하고,
backtest family 분포 bug를 수정한 뒤 252 trading day bootstrap을 다시 생성한다.

범위:
- JACKAL backtest learning state cleanup
- artifact handoff 기반 bootstrap 재실행
- family 분포 검증

범위 밖:
- ORCA walk-forward session 자체 삭제
- workflow_run chaining
- probability % 사용자 노출

## 1. 왜 Fix 2가 필요한가

현재 확인된 anomaly는 두 가지다.

1. DB/session mismatch
   bootstrap 성공 로그는 `1260` rows와 session `bt_d76cc1...`를 보여주지만,
   현재 main/local DB에는 `bt_ab55...` session과 `275` rows만 남아 있다.

2. Family bug
   backtest materialization이 `signal_family="general"`을 하드코딩해서
   canonicalization이 `{momentum_pullback, divergence, oversold_rebound}`로만
   수렴하고, `rotation`, `panic_rebound`, `ma_reclaim`, `general_rebound`
   coverage가 사실상 막혀 있었다.

Wave D 설계 전에 필요한 것은 아래 두 가지다.

- authoritative 252-day sample 복구
- 7 family가 모두 도달 가능한 backtest materialization 확보

## 2. 사전 조건

- 최근 코드가 pull 되어 있어야 한다.
- `jackal_backtest_learning.yml`은 artifact handoff를 지원해야 한다.
- `scripts/cleanup_backtest_state.sql`이 워크스페이스에 존재해야 한다.

권장:
- cleanup과 bootstrap 재실행은 같은 날 연속으로 수행한다.
- Step 2에서 `artifact_run_id`를 비우지 않는다.

## 3. Step 1: 로컬 DB 백업

cleanup 전에 현재 DB를 반드시 백업한다.

PowerShell:

```powershell
Copy-Item data\orca_state.db data\orca_state.pre-wave-a-fix-2.db
```

검증:

```powershell
Get-Item data\orca_state.pre-wave-a-fix-2.db
```

정상 확인 후 다음 단계로 진행한다.

## 4. Step 2: JACKAL backtest state cleanup

cleanup은 JACKAL-owned backtest state만 삭제한다.
ORCA walk-forward session과 ORCA backtest session은 보존한다.

실행:

```powershell
sqlite3 data/orca_state.db < scripts/cleanup_backtest_state.sql
```

주의:
- 이 스크립트는 destructive 하다.
- preview-only로 보고 싶다면 SQL 파일의 마지막 `COMMIT;`를 `ROLLBACK;`로
  바꾼 뒤 실행한다.

cleanup 대상:
- `candidate_registry`
  - `source_event_type='backtest'`
  - `source_system='jackal'`
- `candidate_outcomes`
  - 위 candidate에 연결된 rows
- `candidate_lessons`
  - 위 candidate에 연결된 rows
- `backtest_sessions`
  - `system='jackal'`
- `backtest_pick_results`
  - 위 JACKAL session에 연결된 rows
- `backtest_daily_results`
  - 위 JACKAL session에 연결된 rows
- `backtest_state`
  - 위 JACKAL session에 연결된 rows

ORCA 보존 항목:
- ORCA `backtest_sessions`
- ORCA `backtest_daily_results`
- ORCA `backtest_state`
- 기존 ORCA walk-forward research session

### Cleanup 후 확인 SQL

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

## 5. Step 3: ORCA research preflight 재실행

Actions에서 `orca_backtest.yml`을 수동 실행한다.

예상 시간:
- 빠르면 10~20분
- 실제 데이터 상황에 따라 60~95분 근접 가능

완료 후 확인:
- 성공 status
- artifact 생성
- run URL 마지막 숫자에서 `run_id` 확보

예:
- URL: `.../actions/runs/24828017570`
- `run_id = 24828017570`

이 `run_id`를 메모한다.

## 6. Step 4: JACKAL persisted bootstrap 재실행

Actions에서 `jackal_backtest_learning.yml`을 수동 실행한다.

Inputs:

- `mode: full`
- `artifact_run_id: <Step 3 run_id>`

중요:
- `artifact_run_id`를 절대 비우지 않는다.
- 비워두면 Mode 2로 떨어져 ORCA refresh를 다시 호출한다.
- 그러면 yfinance rate limit로 같은 실패가 재발할 수 있다.

기대 로그:

```text
Mode 1: Artifact handoff (ORCA refresh skipped)
```

예상 시간:
- 1~3분

성공 경로:
- artifact download
- verify artifact
- JACKAL materialization
- save learning state

## 7. Step 5: main DB 검증

workflow 성공 후 로컬에서 최신 main을 가져온다.

```powershell
git pull
```

그 뒤 아래 SQL 4종을 확인한다.

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
- 현재 schema 기준 `candidate 1개당 d1 + swing 2 horizons`

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
- 특히 아래 중 최소 1개 이상은 새로 보여야 한다.
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
- 새 bootstrap session 하나만 남아야 한다.

## 8. 실패 시 대응

### 케이스 A: artifact download 실패

확인:
- `artifact_run_id` 입력값 오타
- Step 3 run이 실제 성공했는지
- artifact가 보존 기간 내인지

조치:
- Step 3을 다시 실행해 새 run_id를 사용한다.

### 케이스 B: materialization row 수가 1260보다 크게 작다

확인:
- `source_session_id`가 1개인지
- `backtest_days`가 252인지
- ORCA preflight artifact가 13개월 coverage인지

조치:
- 현재 DB를 버리지 말고 backup 유지
- workflow logs와 session summary를 먼저 확인한다.

### 케이스 C: family가 여전히 3개만 나온다

확인:
- fix-2 코드가 실제로 배포됐는지
- `signal_family_raw`가 여전히 `general`인지

조치:
- local test 재실행
- deployed workflow commit SHA 확인

## 9. Rollback

cleanup 이후 문제가 생기면 backup으로 복원한다.

PowerShell:

```powershell
Copy-Item data\orca_state.pre-wave-a-fix-2.db data\orca_state.db -Force
```

복원 후 확인:

```sql
SELECT COUNT(*), source_event_type
FROM candidate_registry
GROUP BY source_event_type;
```

정상 복원 확인 후, 원인 분석을 마치기 전까지는 bootstrap을 재실행하지 않는다.

## 10. 완료 기준

Wave A-fix 2는 아래를 모두 만족하면 완료로 본다.

1. cleanup 후 JACKAL backtest rows가 `0`
2. artifact handoff bootstrap이 성공
3. `candidate_registry(backtest)`가 대략 `1260`
4. `candidate_outcomes`가 대략 `2520`
5. `candidate_lessons`가 대략 `1260`
6. `source_session_id`가 새 bootstrap session 하나로 정리
7. backtest family 분포가 3개 이상, 가능하면 4개 이상으로 확장
