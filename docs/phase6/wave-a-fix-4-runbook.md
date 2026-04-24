# Wave A-fix 4 Runbook: Upload-side verify + Isolated promote

작성 시점:
2026-04-24

상태:
runbook

목적:
Wave A-fix 1/2/3 이후에도 남아 있던 artifact 불일치 문제를 줄이기 위해,
upload 쪽에서는 strict verify를 추가하고 consume 쪽에서는 artifact를 isolated path에서 검증한 뒤 promote하도록 구조를 보강한다.

## 1. 왜 Fix 4가 필요했나

이전 조사에서 확인된 핵심은 두 가지다.

1. ORCA Backtest 로그의 `Feed 1260`은 materialization 처리 카운트이지, upload 직전 persisted row count를 직접 증명하는 로그는 아니었다.
2. Mode 1 promote 경로는 artifact와 checkout workspace DB가 같은 위치에서 다뤄져서, artifact 자체와 main workspace 상태를 명확히 분리해 검증하기 어려웠다.

Fix 4는 이 두 가지를 각각 다른 쪽에서 해결한다.

## 2. Fix 4의 두 가지 개선점

### A. Upload-side strict verify (`orca_backtest.yml`)

ORCA + JACKAL backtest가 끝난 뒤:
- `PRAGMA wal_checkpoint(TRUNCATE)` 실행
- `-wal`, `-shm` 제거
- 실제 `candidate_registry(backtest)`, `candidate_outcomes`, `candidate_lessons` 수량 확인
- ORCA/JACKAL session 존재 확인
- session/date/family 분포를 로그에 출력

검증이 실패하면:
- `run-backtest` job이 실패
- artifact upload는 발생하지 않음
- downstream `policy_eval` / `policy_promote`는 자동 skip

이 동작은 의도된 것이다. 검증되지 않은 artifact가 policy 단계로 넘어가면 안 된다.

### B. Isolated consume path (`jackal_backtest_learning.yml` Mode 1)

Mode 1에서는:
- artifact를 `_artifact_handoff/`에 download
- 그 위치에서만 checkpoint + strict verify
- 검증 통과 후에만 `data/orca_state.db`로 promote copy
- JACKAL backtest는 재실행하지 않음

즉 Mode 1은 promote-only 역할에 집중한다.

## 3. Mode별 역할 정리

### Mode 1: artifact promote only

사용 시나리오:
- 수동 bootstrap
- 이미 성공한 `orca_backtest.yml` artifact를 main에 반영할 때

Flow:
- artifact download
- isolated checkpoint
- isolated strict verify
- promote copy
- save learning state

JACKAL 재실행:
- 없음

### Mode 2: self-refresh + full replay

사용 시나리오:
- 월간 full fallback

Flow:
- ORCA refresh
- JACKAL backtest full
- save learning state

### Mode 3: daily incremental

사용 시나리오:
- 평일 daily cron

Flow:
- 기존 main DB 재사용
- JACKAL incremental
- save learning state

## 4. 재실행 절차

### Step 1: ORCA Backtest 실행

Actions에서 `orca_backtest.yml`를 `workflow_dispatch`로 실행한다.

입력:
- 없음

예상 시간:
- 10~95분

결과 해석:
- strict verify 통과
  - artifact 생성됨
  - Step 2로 진행
- strict verify 실패
  - artifact 없음
  - runner 로그의 session/date/family 분포를 보고 원인 분석

### Step 2: ORCA Backtest 결과 확인

run URL에서 `run_id`를 기록한다.

예:
- `.../actions/runs/24847623560`
- `run_id = 24847623560`

### Step 3: JACKAL Backtest Learning 실행

Actions에서 `jackal_backtest_learning.yml`를 `workflow_dispatch`로 실행한다.

입력:
- `mode: full`
- `artifact_run_id: <Step 1 run_id>`

예상 시간:
- 1~3분

기대 로그:
- `Mode 1: Artifact handoff (ORCA refresh skipped)`
- `Found artifact DB: ...`
- `Artifact verified (isolated):`
- `Promoted ... -> data/orca_state.db`

`Run JACKAL backtest learning` step은 skip되어야 한다.

### Step 4: 로컬 검증

```powershell
git pull origin main
python verify_wave_a.py
```

기대값:
- `candidate_registry(backtest): ~1260`
- `candidate_outcomes: ~2520`
- `candidate_lessons: ~1260`
- `source_session_id`: 단일 session
- `signal_family`: 4개 이상

## 5. Troubleshooting

### `orca_backtest.yml` strict verify 실패

의미:
- upload 직전 runner DB 자체가 기대 수량을 만족하지 못했다는 뜻

우선 확인:
- `candidate_registry(backtest)`
- `candidate_outcomes`
- `candidate_lessons`
- distinct days
- session 분포

해석 예시:
- `280` 수준이면
  - `jackal/backtest.py` materialize 경로가 일부 날짜만 처리했을 가능성
- `500~999` 수준이면
  - 일부 날짜 skip이나 dedup 영향 의심

다음 조사 포인트:
- `jackal/backtest.py` per-day loop
- `materialize_backtest_day()` return 값
- `record_backtest_candidate()` 호출 횟수

### Mode 1 isolated verify 실패

의미:
- artifact 자체가 기대 수량을 담고 있지 않거나
- download된 파일이 예상 경로와 다르거나
- artifact가 만료/손상됐을 수 있다

우선 확인:
- `artifact_run_id`가 맞는지
- `_artifact_handoff/` 내부 파일 목록
- Step 1 run이 strict verify를 통과했는지

### Policy chain 영향

체인:
- `run-backtest -> policy_eval -> policy_promote`

Fix 4 이후:
- `run-backtest`가 strict verify 실패로 fail하면
- `policy_eval`은 자동 skip
- `policy_promote`도 자동 skip

이건 의도된 동작이다.

## 6. Rollback

workflow 변경 자체를 되돌려야 하면:

```powershell
git revert <wave-a-fix-4 commit hash>
git push
```

DB 상태를 되돌려야 하면:
- Fix 2 runbook의 backup/restore 절차를 사용한다.

## 7. 이전 fix와의 관계

- Wave A-fix 1:
  - artifact handoff 경로 추가
- Wave A-fix 2:
  - family bug 수정 + cleanup
- Wave A-fix 3:
  - Mode 1 promote-only, recompute 방지
- Wave A-fix 4:
  - upload-side strict verify + isolated consume path
- Wave A-fix 5:
  - 필요 시 `jackal/backtest.py` materialize bug 조사

## 8. 기대 효과

Fix 4 이후에는 두 지점에서 같은 질문을 바로 답할 수 있어야 한다.

1. `orca_backtest.yml` runner 내부에서:
   - 정말 `1000+` backtest candidates가 persisted 되었는가?
2. `jackal_backtest_learning.yml` Mode 1에서:
   - 정말 artifact가 그 persisted DB를 담고 있는가?

둘 다 통과하면, 그 다음 promote는 단순 copy + commit 문제가 된다.
