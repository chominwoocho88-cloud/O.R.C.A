# Wave A-fix 5 Runbook: ORCA JSON Parsing Robustness

작성 시점:
2026-04-24

상태:
runbook

목적:
Final Pass에서 간헐적으로 발생한 Claude malformed JSON 응답 때문에
`orca.backtest` 전체 run이 중단되던 문제를 줄이고, 실패 원인을
로그에서 바로 추적할 수 있게 만든다.

## 1. 배경

ORCA Backtest #12에서 다음 현상이 확인됐다.

1. Final Pass 중 특정 날짜에서 Claude 응답이 malformed JSON으로 돌아왔다.
2. 기존 parser는 3단계 fallback만 있었고, 모두 실패하면 즉시 `ValueError`를 raise했다.
3. `_run_phase_dates()`가 이 예외를 잡지 않아 `Run ORCA Backtest` step 자체가 `exit 1`로 끝났다.
4. 그 결과 Wave A-fix 4에서 추가한 upload-side verify와 artifact promote 단계까지 도달하지 못했다.

중요:
- `ALL UNCLEAR`는 정상 케이스다.
- 이번 fix는 ORCA #11의 280 vs 1260 문제와는 별개의 안정성 문제를 다룬다.

## 2. Fix 5의 세 가지 개선

### A. Parser diagnostics

`generate_analysis()`는 이제 내부 helper `_parse_analysis_json()`을 통해 다음 정보를 함께 추적한다.

- `raw_preview`
- `extracted_preview`
- `failed_stage`
- `exception_message`

strict mode가 아니면 이 정보를 `_parse_failed` marker와 함께 caller에 돌려준다.

### B. Per-day graceful degradation

`_run_phase_dates()`는 이제 날짜 단위로 parse failure를 처리한다.

- 해당 날짜를 `parse_failed`로 기록
- diagnostics를 로그에 출력
- 실패율이 임계값 이하이면 다음 날짜로 계속 진행
- 실패율이 임계값을 넘으면 그때만 전체 run 실패

기본 동작:
- graceful mode
- `--max-parse-failures 0.10`

즉, 1~2건의 malformed response 때문에 1시간 이상 돌린 ORCA run 전체를 버리지 않게 된다.

### C. Prompt 강화

system prompt에 다음 요구를 추가했다.

- 반드시 단일 JSON 객체만 반환
- 설명 문장/사족/후기 금지
- 모든 key를 빠짐없이 채우기
- 값이 없으면 빈 문자열 사용

이건 parser fallback을 대체하는 것이 아니라, malformed response 자체를 줄이기 위한 방어선이다.

## 3. 새 CLI 옵션

### `--max-parse-failures`

기본값:
`0.10`

의미:
- 누적 parse failure rate가 이 값을 초과하면 run 실패

### `--strict-json`

기본값:
`False`

의미:
- 켜면 기존 동작처럼 첫 parse failure에서 즉시 실패
- 기존 "즉시 fail" 동작 재현용

### `--verbose-parse-errors`

기본값:
`False`

의미:
- parse failure 시 raw/extracted response 전체를 로그에 더 많이 남김
- 기본은 preview 중심 로그

## 4. 재실행 절차

### Step 1: 코드 반영 후 push

Wave A-fix 5 commit을 `main`에 push한다.

### Step 2: ORCA Backtest 재실행

Actions에서 `orca_backtest.yml`을 `workflow_dispatch`로 실행한다.

입력:
- 없음

기대 동작:
- 특정 날짜 parse failure가 1건 정도 발생해도 run이 계속 진행
- 마지막에 parse failure summary가 출력됨
- Wave A-fix 4의 upload-side verify까지 도달

### Step 3: runner 로그 확인

`Run ORCA Backtest` 로그에서 아래를 확인한다.

- `JSON parse failed (stage X): ...`
- `raw preview: ...`
- `extracted: ...`
- `Parse failures: X / Y (Z%)`
- `Failed dates: ...`

### Step 4: verify 통과 시 artifact promote

ORCA run이 strict verify까지 통과하면:

1. `run_id` 기록
2. `jackal_backtest_learning.yml` 수동 실행
3. 입력:
   - `mode=full`
   - `artifact_run_id=<Step 2 run_id>`

## 5. Troubleshooting

### parse failure가 1~2건이고 run은 완료됨

정상 범주일 수 있다.

다음만 확인한다.
- 최종 `parse_fail_rate`
- upload-side verify 통과 여부
- artifact promote 후 main DB sample 수량

### parse failure rate가 threshold 초과로 실패

의미:
- malformed JSON이 간헐 문제가 아니라 run 품질 전체를 흔드는 수준

우선 조사:
1. 실패 날짜가 Final Pass에 집중되는가
2. 특정 이벤트/긴 prompt에서만 재현되는가
3. raw preview가 prose/truncation/quote corruption 중 어떤 형태인가

다음 선택지:
- `--strict-json` 대신 graceful 유지
- prompt를 더 짧게 재구성
- structured response/tool mode 검토

### `--strict-json`를 언제 쓰나

추천 시나리오:
- parser regression 재현
- CI에서 parser 자체를 강하게 검증하고 싶을 때
- malformed response를 절대 허용하지 않는 진단 run

운영 기본값으로는 권장하지 않는다.

### `--verbose-parse-errors`를 언제 쓰나

추천 시나리오:
- 특정 날짜의 raw Claude 응답을 더 많이 보고 싶을 때
- regex/balanced extractor가 왜 실패했는지 보고 싶을 때

주의:
- 로그가 길어진다
- 민감한 응답 내용이 더 많이 남을 수 있다

## 6. 이전 fix와의 관계

- Wave A-fix 1:
  artifact handoff 경로 추가
- Wave A-fix 2:
  family bug 수정 + cleanup
- Wave A-fix 3:
  Mode 1 promote-only
- Wave A-fix 4:
  upload-side verify + isolated promote
- Wave A-fix 5:
  ORCA JSON parsing robustness + graceful degradation

## 7. 기대 결과

Fix 5 이후에는 아래가 가능해진다.

1. malformed JSON 1건 때문에 ORCA run 전체가 즉시 죽지 않는다.
2. runner 로그만으로 어느 stage에서 parser가 실패했는지 알 수 있다.
3. parse failure가 일정 수준 이하이면 Wave A-fix 4의 strict verify와 artifact upload까지 도달한다.
4. 이후 Mode 1 promote로 JACKAL main DB 반영까지 자연스럽게 이어진다.
