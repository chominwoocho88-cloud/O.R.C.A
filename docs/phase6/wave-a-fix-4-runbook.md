# Wave A-fix 4 Runbook: Upload-side Verify + Isolated Promote

작성 시점:
2026-04-24

상태:
runbook

목적:
Wave A bootstrap에서 artifact 내용과 main DB가 섞이는 문제를 줄이기 위해,
upload 전 strict verify와 Mode 1 isolated promote 경로를 정리한다.

## 1. Fix 4가 해결하는 문제

이전 조사에서 확인된 핵심 문제는 두 가지였다.

1. `orca_backtest.yml`은 upload 전에 실제 persisted row count를 검증하지 않았다.
2. `jackal_backtest_learning.yml` Mode 1은 artifact와 checkout DB를 같은 workspace 경로에서 다뤄 혼동 여지가 있었다.

Fix 4는 이 둘을 각각 다른 쪽에서 막는다.

## 2. Fix 4의 구성

### A. Upload-side strict verify

`orca_backtest.yml`에서 ORCA + JACKAL backtest가 끝난 뒤:

1. `PRAGMA wal_checkpoint(TRUNCATE)` 실행
2. `-wal`, `-shm` 제거
3. `candidate_registry(backtest)`, `candidate_outcomes`, `candidate_lessons` 검증
4. ORCA/JACKAL session 존재 확인
5. session/date/family 분포 로그 출력

검증이 실패하면:
- workflow 전체가 fail
- artifact upload 없음
- downstream `policy_eval` / `policy_promote` 자동 skip

### B. Mode 1 isolated promote

`jackal_backtest_learning.yml` Mode 1에서는:

1. artifact를 `_artifact_handoff/`에 download
2. 그 위치에서 checkpoint + strict verify
3. 통과 후에만 `data/orca_state.db`로 promote copy
4. JACKAL backtest는 재실행하지 않음

즉 Mode 1은 promote-only 경로다.

## 3. Mode별 역할

### Mode 1

용도:
- 수동 bootstrap

동작:
- artifact download
- isolated verify
- promote copy
- commit + push

JACKAL 재실행:
- 없음

### Mode 2

용도:
- 월간 full fallback

동작:
- ORCA refresh
- JACKAL full replay
- commit + push

### Mode 3

용도:
- 평일 incremental

동작:
- 기존 main DB 재사용
- JACKAL incremental
- commit + push

## 4. 실행 절차

### Step 1: ORCA Backtest 실행

Actions에서 `orca_backtest.yml`을 `workflow_dispatch`로 실행한다.

입력:
- 없음

기대:
- upload-side strict verify 통과
- `research-state-<run_id>` artifact 생성

### Step 2: run_id 확인

run URL의 마지막 숫자를 기록한다.

예:
- `.../actions/runs/24847623560`
- run_id = `24847623560`

### Step 3: JACKAL Backtest Learning 실행

Actions에서 `jackal_backtest_learning.yml`을 `workflow_dispatch`로 실행한다.

입력:
- `mode=full`
- `artifact_run_id=<Step 2 run_id>`

기대:
- `Mode 1: Artifact handoff (ORCA refresh skipped)`
- isolated verify 통과
- `Promote artifact DB`
- `Run JACKAL backtest learning` step은 skip

### Step 4: 로컬 검증

```powershell
git pull origin main
python verify_wave_a.py
```

기대:
- `candidate_registry(backtest) ~ 1260`
- `candidate_outcomes ~ 2520`
- `candidate_lessons ~ 1260`

## 5. Troubleshooting

### ORCA workflow가 strict verify에서 실패

의미:
- upload 직전 runner DB가 기대 수량에 못 미친다.

우선 확인:
- `candidate_registry(backtest)`
- `candidate_outcomes`
- `candidate_lessons`
- distinct days
- session distribution

### Mode 1 isolated verify에서 실패

의미:
- artifact 자체가 기대 수량이 아니거나
- artifact 경로 탐색이 어긋났거나
- artifact가 이미 잘못 생성됐다.

우선 확인:
- `artifact_run_id`
- `_artifact_handoff/` 내부 파일 목록
- Step 1 ORCA run이 strict verify를 통과했는지

### Policy chain 영향

체인:
- `run-backtest -> policy_eval -> policy_promote`

Fix 4 이후 `run-backtest`가 verify 실패로 fail하면
downstream은 자동 skip된다. 이건 의도된 보호 동작이다.

## 6. Rollback

workflow 변경만 되돌리려면:

```powershell
git revert <wave-a-fix-4 commit hash>
git push
```

DB 상태까지 되돌리려면:
- Fix 2 cleanup/back-up 절차를 사용한다.

## 7. 이후 관계

- Wave A-fix 1:
  artifact handoff 경로 추가
- Wave A-fix 2:
  family bug 수정 + cleanup
- Wave A-fix 3:
  Mode 1 promote-only
- Wave A-fix 4:
  upload-side verify + isolated promote
- Wave A-fix 5:
  ORCA JSON parsing robustness

Wave A-fix 5는 Fix 4를 대체하지 않는다.

- Fix 4: artifact 생성/전달 정합성
- Fix 5: ORCA parsing 실패 때문에 Fix 4 단계까지 도달하지 못하는 문제 완화
