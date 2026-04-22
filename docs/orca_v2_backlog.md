# ORCA v2 Execution Backlog

이 문서는 `ORCA v2 Architecture Blueprint`를 실제 작업 단위로 쪼갠 실행용 백로그다.

## P0. Stop The Bleeding

목표: 지금 당장 시스템이 조용히 망가지지 않게 만든다.

- `baseline_context` 인터페이스 불일치 수정
- 월간 워크플로우의 missing import 수정
- `memory.json`, `accuracy.json`, `hunt_log.json`, `jackal_weights.json`에 atomic write 적용
- 핵심 write 경로에 file lock 또는 single-writer 정책 적용
- broad exception 위치에 structured warning log 추가
- GitHub Actions에 `concurrency` 설정 추가
- 운영 상태와 연구 상태를 최소한 파일 레벨로 분리

## P1. Establish A Real State Layer

목표: JSON 파일 중심 운영에서 벗어난다.

- SQLite 도입
- `runs` 테이블 구현
- `predictions` 테이블 구현
- `outcomes` 테이블 구현
- 기존 `memory.json`을 DB-backed projection으로 대체
- 기존 `accuracy.json`을 DB aggregate view로 대체
- 기존 `hunt_log.json`을 DB event log로 대체

## P2. Harden Agent Contracts

목표: 프롬프트 결과를 "느낌"이 아니라 계약으로 다룬다.

- Hunter output schema 고정
- Analyst output schema 고정
- Devil output schema 고정
- Reporter를 narrative-only renderer로 축소
- `evidence`, `source_quality`, `invalidation_rules`, `confidence_basis` 필드 의무화
- schema validation 실패 시 fallback JSON repair 대신 명시적 retry와 error logging 사용

## P3. Separate Research From Production

목표: 백테스트와 운영 판단의 경계를 만든다.

- backtest run과 production run 저장소 분리
- JACKAL shadow 결과를 ORCA accuracy에서 분리
- policy versioning 도입
- challenger policy shadow run 도입
- promotion gate 문서화

## P4. Build The Evaluation Spine

목표: "정확했나"를 넘어서 "왜 정확했나"를 측정한다.

- prediction registry 도입
- candidate registry 도입
- candidate review / candidate outcome / candidate lesson 루프 도입
- calibration metrics 구현
- regime-sliced metrics 구현
- confidence drift monitoring 구현
- outcome resolution lag metric 구현
- policy comparison dashboard 구현

## P5. Redesign GitHub Actions

목표: GitHub Actions를 데이터 저장소 대용으로 쓰지 않는다.

- `aria-run.yml` 분리
- `jackal-run.yml` 분리
- `outcome-resolver.yml` 신설
- `policy-eval.yml` 신설
- `policy-promote.yml` 신설
- mutable state auto-commit 제거
- report artifact upload 기반으로 전환

## P6. Cost And Security

목표: 비용과 비밀정보를 사후 점검이 아니라 1급 운영 제약으로 취급한다.

- 실제 usage 기반 cost ledger 도입
- mode별 budget ceiling 도입
- crisis mode와 cheap mode 분리
- secret scan을 CI fail condition으로 승격
- boot-time env validation 추가
- report export 전 scrub pass 추가

## Phase 6 Candidates (Post-Phase 5)

귀속 그룹: Phase 6 후보 (Phase 5 완료 후)

전제 조건:
- Phase 5 완료 (`JACKAL` 학습 상태 보존 구조 확립)
- scheduled run 에서 shadow batch 누적 시작 확인
- 이후 새 factor 의 효과를 shadow batch 기준으로 확인 가능

### P1. Cross-stock correlation (최우선)

위치:
- `jackal/scanner.py` (새 factor 추가)
- `jackal/market_data.py` (correlation 계산)

내용:
- 같은 섹터 내 `N` 종목의 최근 `5~10일` 수익률 correlation 계산
- 대상 종목과 sector peer 들의 움직임 동조 여부를 signal 에 반영
- peer 들의 동조 움직임을 별도 factor 로 기록

근거:
- 사용자 직접 요청 (`2026-04-21`)
- Cross-sectional momentum factor (`Jegadeesh & Titman 1993` 이후 실증 축)
- Summary Map `☐ Cross-stock correlation matrix`
  - `docs/jackal/current-signals.md`

왜 Phase 5 후인가:
- Phase 5 없으면 scheduled run 에서 새 factor 의 shadow batch 누적이 이어지지 않음
- 보존 구조 없이 추가된 factor 는 검증 이력 누적이 어려움

### P2. Relative strength vs market (2순위)

위치:
- `jackal/market_data.py` (benchmark fetch)
- `jackal/scanner.py` (RS 반영)

내용:
- `KOSPI` / `S&P500` 대비 ticker 의 누적 초과수익률 계산
- `RS percentile >= 80` 구간을 별도 component 로 반영
- 현재 Hunter 에 있는 sector ETF 대비 상대 낙폭과 별도로, 시장 benchmark 기준 relative strength 를 기록

근거:
- `O'Neil CANSLIM` 의 relative strength 축
- `Jegadeesh-Titman` momentum 실증 축
- Summary Map `☐ Market benchmark relative strength line`
  - `docs/jackal/current-signals.md`
- 현재 sector ETF 대비 상대낙폭은 Hunter 에 부분 구현
  - `jackal/hunter.py:678-692`

왜 Phase 5 후인가:
- Phase 5 없으면 scheduled run 에서 새 factor 의 shadow batch 누적이 이어지지 않음
- 보존 구조 없이 추가된 factor 는 검증 이력 누적이 어려움

### P3. Squeeze + breakout direction (3순위)

위치:
- `jackal/market_data.py` (squeeze detection)
- `jackal/scanner.py` (결합)

내용:
- `bb_width` 가 최근 `20일` 중 하위 `10%` 이면 squeeze flag 계산
- squeeze 단독으로 entry 를 결정하지 않고 기존 신호와 AND 조건으로 결합
- 기존 신호 예시:
  - `RSI oversold`
  - `volume surge`
- 수렴 후 방향성 신호를 별도 component 로 기록

근거:
- 사용자 질문 `그래프 수렴 → 터짐`
- Bollinger squeeze 는 breakout 임박 구간 탐지 패턴으로 자주 사용됨
- Summary Map `☐ Squeeze 감지`
  - `docs/jackal/current-signals.md`
- 현재 구현은 `bb_width`, `bb_expanding` 까지 존재
  - `jackal/market_data.py:380-387`
  - `jackal/scanner.py:915-919`

왜 Phase 5 후인가:
- Phase 5 없으면 scheduled run 에서 새 factor 의 shadow batch 누적이 이어지지 않음
- 단독 후보가 아니라 P1 또는 P2 구현 중 보조 feature 로 흡수 가능

### Phase 6 Common Policy

- Phase 5 완료 확인 후 `P1` 부터 순차 진행
- `P3` 는 `P1` 또는 `P2` 구현 과정에서 보조 feature 로 포함 가능
- 각 factor 는 독립 PR 단위로 설계
- 기존 `quality_score` 계산 로직은 유지하고 새 component 추가 방식으로 확장
- `PR 1-5` 운영 원칙 재적용
  - drift `0`
  - Backlog 상시 유지
  - 멈춤 보고

### Duplicate / Conflict Check

중복 확인:
- 이 문서 내에 `Cross-stock correlation`, `Relative strength vs market`, `Squeeze + breakout direction` 항목은 기존에 없음
- 현재 repo 에서 위 세 항목은 backlog 로 등록된 상태가 아니라 조사 문서의 현재 상태 설명으로만 존재
  - `docs/jackal/current-signals.md:1004`
  - `docs/jackal/current-signals.md:1052`
  - `docs/jackal/current-signals.md:1086`
  - `docs/jackal/current-signals.md:1090`
  - `docs/jackal/current-signals.md:1096`

충돌 확인:
- 직접 충돌하는 기존 backlog 항목은 없음
- 관련성이 있는 기존 항목은 아래 두 축
  - `P4. Build The Evaluation Spine`
  - `P5. Redesign GitHub Actions`
- 이번 Phase 6 후보는 `Phase 5` 완료 후 검증 가능한 factor 후보로 기록하며, `P4/P5` 의 선행 조건을 전제로 둠
  - `docs/orca_v2_backlog.md:50-73`

## Suggested Order

### Week 1

- P0 전부
- SQLite 골격 생성
- `runs` 테이블 도입

### Week 2

- `predictions`, `outcomes` 도입
- ORCA/JACKAL 기록 경로 일부 DB 이관
- agent schema validation 추가

### Week 3

- Reporter 축소
- evaluation spine 초안
- shadow/promotion 경계 구현

### Week 4+

- GitHub Actions 재구성
- dashboard observability 확장
- policy versioning 완성

## Done Definition

아래 기준을 만족해야 v2 전환이 의미 있다.

- 운영 run마다 `run_id`가 존재한다.
- 모든 예측은 `prediction_id`를 가진다.
- outcome 없이 accuracy가 계산되지 않는다.
- JACKAL shadow와 ORCA production metric이 섞이지 않는다.
- mutable state를 main branch에 자동 커밋하지 않는다.
- 어떤 결론이든 evidence chain을 역추적할 수 있다.

## Deferred Improvement: cross-DB secondary write observability

위치:
- `orca/state.py`
- `sync_jackal_live_events()`
- `record_jackal_shadow_signal()`
- `resolve_jackal_shadow_signal()`

내용:
- Secondary write 실패 시 현재는 `stderr` 경고만 남기는 정책을 사용한다.
- `candidate_registry` / `candidate_outcomes` 쪽 secondary propagation 실패를 더 구조적으로 관측하는 경로는 아직 없다.
- `HealthTracker` 통합은 `Phase 6` candidate spine 재설계와 함께 처리한다.

왜 지금 말고 나중인지:
- `PR 1` 의 health code `10개 불변` 계약을 유지해야 한다.
- 새 health code 추가는 이번 Phase 5-C 범위를 넘어선다.
- `Phase 6` 에서 candidate spine 재설계와 observability 를 함께 처리하는 편이 경계가 명확하다.

귀속 PR:
- `Phase 6` 또는 별도 observability PR

## Deferred Improvement: research artifact scope 재검토

위치:
- `.github/workflows/orca_backtest.yml:47`
- `.github/workflows/policy_eval.yml:88`

내용:
- 현재 두 workflow 가 `data/orca_state.db` 와 sidecar (`data/orca_state.db-shm`, `data/orca_state.db-wal`) 를 artifact 로 upload 한다.
- `Phase 5-D` 이후 `data/jackal_state.db` 도 연구 / 평가 artifact 범위에 포함할지 별도 판단이 필요하다.
- 연구 / 평가에서 JACKAL 학습 상태가 실제로 필요한 경우 artifact 대상에 추가할 수 있다.
- 필요하지 않다면 현재 범위를 유지한다.

왜 지금 말고 나중인지:
- `Phase 5-D` 범위는 scheduled run 사이의 DB 보존 문제다.
- artifact upload 는 연구 / 평가 snapshot 경계 문제로, scheduled persistence 와 분리된 별도 의사결정이다.
- 실제 `orca_backtest.yml` / `policy_eval.yml` 가 `jackal_state.db` 를 소비하는지 확인한 뒤 결정하는 편이 범위가 명확하다.

귀속 PR:
- `research artifact scope PR` (가칭)
## Deferred Improvement: UTF-8 BOM 제거 (repo-wide)
위치:
- 레포 전체 .py 파일 22개에 BOM 존재
- 대표 예: orca/analysis.py, orca/state.py

내용:
- Python .py 파일에 UTF-8 BOM (EF BB BF) 존재
- py_compile, unittest 등 실행은 정상 (Python 이 BOM 관대 처리)
- 하지만 AST 기반 도구 (linter, code analyzer, formatter) 일부는 실패
- 예: ast.parse(content) 는 BOM 에서 SyntaxError

배경:
- Phase 5 이전부터 존재 (HEAD 도 BOM 포함)
- accuracy debug 트랙과 무관
- Windows 환경 / 과거 에디터가 저장 시 추가한 것으로 추정

기존 repo hygiene 후보와 통합:
- .pyc/__pycache__ ignore 확인
- workflow 문자열 corruption
- ARIA 잔재 정리
- UTF-8 BOM 제거  ← 신규

왜 지금 말고 나중인지:
- 기능적 문제 없음 (Python 실행 OK)
- 22개 파일 일괄 수정은 별도 hygiene PR 영역
- accuracy debug commit 과 분리 유지

귀속 PR: Phase 6 후보 중 "repo hygiene PR"
