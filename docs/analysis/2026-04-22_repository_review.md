# ARIA/JACKAL Repository Review
이 문서는 `ARIA + JACKAL` 리포지터리의 현재 상태를 정적 코드 분석과 현재 워크스페이스 스냅샷 기준으로 정리한 참고 리포트다.
작성 범위는 사용자 요청에 명시된 읽기 전용 입력 자료와 현재 레포 HEAD 기준 소스/워크플로우/테스트/보고 산출물이다.
투자 전략 경고:
이 문서는 투자 전략 제안 문서가 아니다.
새 signal/factor 제안은 의도적으로 제외했다.
기존 Phase 6 factor 후보는 `docs/orca_v2_backlog.md:86-170`에 이미 있으므로 본 문서에서는 재제안하지 않는다.
---
## Section 0: Meta
- 작성 시점: `2026-04-22 17:15:31 +09:00`. Evidence: 로컬 셸 시간.
- 분석 기준 브랜치: `main`. Evidence: `.git/HEAD:1`.
- 분석 기준 커밋: `272f306f237465c4f6b968ef606589e25a1f8c2a`. Evidence: `.git/refs/heads/main` 직접 조회.
- 작성자 시점: 프로젝트 내부 협업자 관점의 read-only review. Evidence: 로컬 저장소, 문서, 현재 DB 파일까지 접근 가능한 상태에서 작성했고, 독립 외부 리뷰는 이미 `docs/analysis/2026-04-22_external_review.md:1-25`에 별도로 존재한다.
- 이번 문서의 우선 기준: Phase 5 완료 맥락 반영. Evidence: `docs/phase5/02-path-decision.md:12-32`, `docs/phase5/03-design.md`, `docs/phase5/04-workflow-design.md`.
- Phase 5 의사결정 해석:
  `Path B`는 `full separation`이 아니라 `bounded separation`이다.
  7개 JACKAL-only 테이블만 `data/jackal_state.db`로 이동했고, shared/ambiguous candidate cluster는 `Phase 6`로 이월됐다. Evidence: `docs/phase5/02-path-decision.md:23-32`, `docs/phase5/02-path-decision.md:90-97`.
- 이번 문서의 비목표:
  `candidate_registry` 재설계, candidate cluster ownership 재결정, workflow artifact scope 재검토, repo-wide BOM 제거, 새로운 factor 제안은 여기서 새 제안으로 다시 올리지 않는다. Evidence: `docs/phase5/02-path-decision.md:25-27`, `docs/orca_v2_backlog.md:233-300`.
- 이전 외부 리뷰의 위치:
  `docs/analysis/2026-04-22_external_review.md`.
  이 문서는 명시적으로 `NOT authoritative`이며, Phase 5 맥락과 전략 제안 caveat를 함께 적고 있다. Evidence: `docs/analysis/2026-04-22_external_review.md:1-25`.
- 이 보고서의 성격:
  실행 지시서가 아니라 참고 자료다.
  실제 backlog의 기준 문서는 여전히 `docs/orca_v2_backlog.md`다. Evidence: `docs/analysis/2026-04-22_external_review.md:20-25`.
- 분석 방법:
  1. 필수 문서 선독.
  2. `orca/`, `jackal/`, `.github/workflows/`, `tests/` 정적 분석.
  3. 현재 `reports/`, `data/orca_state.db`, `data/jackal_state.db` 스냅샷 확인.
  4. `python -m unittest discover -s tests -v`, `python -m compileall orca jackal tests` 실행.
- 현재 런타임 스냅샷도 참고했다.
  단, 이 문서의 핵심 평가는 정적 코드 구조 기준이며, scheduled run 실환경 검증을 대체하지 않는다.
- 본 문서는 `참고 자료`다.
  사용자는 Section 6의 P1 제안을 검토한 뒤, 실제 PR 단위로 선별해야 한다.
---
## Section 1: 계약 무결성 확인
- PR 1: `OK`. Evidence: `HealthTracker`는 degraded reason / counters / details payload를 만들고(`orca/run_cycle.py:41-138`), 10개 코드가 현재 코드에 모두 남아 있다:
  `state_db_unavailable` (`orca/persist.py:101`, `orca/run_cycle.py:174`, `orca/run_cycle.py:194`),
  `state_payload_invalid` (`orca/state.py:2768`, `orca/state.py:2887`, `orca/state.py:3079`),
  `cost_alert_failed` (`orca/run_cycle.py:242`),
  `weight_update_failed` (`orca/run_cycle.py:316`),
  `candidate_review_unavailable` (`orca/postprocess.py:113`),
  `probability_summary_unavailable` (`orca/run_cycle.py:367`),
  `pattern_db_update_failed` (`orca/postprocess.py:186`),
  `dashboard_generation_failed` (`orca/present.py:204`),
  `external_data_degraded` (`orca/run_cycle.py:254`, `orca/run_cycle.py:279`),
  `notification_failed` (`orca/run_cycle.py:432`).
- PR 2: `OK`. Evidence: `orca/learning_policy.py:6-10`에 `MIN_SAMPLES = 5`, `PRIOR_WINS = 2`, `PRIOR_TOTAL = 4`, `TRUSTED_EFFECTIVE_WIN_RATE = 0.58`, `CAUTIOUS_EFFECTIVE_WIN_RATE = 0.46`가 유지되고, `describe_policy()`가 이를 report payload에 노출한다(`orca/learning_policy.py:68-80`, `reports/2026-04-22_morning.json:160-209`).
- PR 3: `OK`. Evidence: `orca/main.py`는 총 48줄이며, 실제 역할이 CLI entrypoint와 `run_orca_cycle()` 호출에 머문다(`orca/main.py:1-48`).
- PR 4: `OK`. Evidence: candidate review scorecard 6-element weight가 그대로 남아 있다:
  `market_bias=0.15`, `signal_family_history=0.30`, `quality=0.20`, `theme_match=0.15`, `devil_penalty=0.10`, `thesis_killer_penalty=0.10`
  (`orca/analysis.py:428-435`).
  실제 합산도 이 weight map을 그대로 사용한다(`orca/analysis.py:726-748`).
- PR 5: `OK`. Evidence: external data visibility는 현재 `data_quality` 3-tier와 `failed_sources`를 유지한다.
  `orca/data.py:577-612`에서 `ok/degraded/poor`를 계산하고 `failed_sources`를 report payload에 넣는다.
  `orca/run_cycle.py:248-286`은 `poor`와 `degraded`를 각각 다른 처리 경로로 기록한다.
  `orca/persist.py:112-123`은 최종 report에 `failed_sources`를 주입한다.
  실제 최신 report에도 `data_quality`, `health`, `failed_sources`가 존재한다(`reports/2026-04-22_morning.json:117`, `reports/2026-04-22_morning.json:211-240`).
- Phase 5 routing: `OK` with caveat. Evidence: `orca/state.py`는 `JACKAL_DB_FILE`을 import하고(`orca/state.py:21`, `orca/paths.py:34`), `_connect_orca()` (`orca/state.py:93-101`), `_connect_jackal()` (`orca/state.py:104-115`), `checkpoint_jackal_db()` (`orca/state.py:118-132`)를 가진다.
  JACKAL-owned read/write paths는 `_connect_jackal()`을 사용한다(`orca/state.py:1183`, `1266`, `1311`, `1381`, `1432`, `1480`, `1579`, `1599`, `1619`, `1638`, `1790`, `1841`, `1913`, `2088`, `2153`, `2182`).
  Caveat: ORCA/shared 쪽은 `_connect_orca()` 대신 기존 `_connect()` wrapper를 계속 사용한다(`orca/state.py:83-90`, `orca/state.py:519`, `541`, `670`, `754`, `856`, `2637`, `2757`, `3147`, `3225`).
  즉, dual-DB routing 자체는 유지되지만 ORCA-side naming normalization은 아직 끝나지 않았다.
- Phase 5 workflow checkpoint contract: `OK`. Evidence: 4개 stateful workflow가 모두 `checkpoint_jackal_db()`를 호출하고 `data/jackal_state.db`를 add 대상에 포함한다.
  `orca_daily.yml:141-160`,
  `jackal_tracker.yml:80-98`,
  `jackal_scanner.yml:64-74`,
  `orca_jackal.yml:110-127`.
- Phase 5 2-phase write mitigation: `OK`. Evidence: `record_jackal_shadow_signal()` (`orca/state.py:1227-1243`),
  `resolve_jackal_shadow_signal()` (`orca/state.py:1352-1367`),
  `sync_jackal_live_events()` (`orca/state.py:1540-1555`) 모두
  `primary (jackal_state.db) already succeeded`를 주석으로 명시하고,
  secondary candidate write 실패 시 `stderr` 경고만 남기며 재-raise하지 않는다.
  이는 `docs/phase5/03-design.md:566-569`, `docs/orca_v2_backlog.md:241-249`의 현재 정책과 일치한다.
- Phase 5 bounded-fix context retention: `OK`. Evidence: 문서상으로도 `candidate_registry` 재설계와 shared/ambiguous cluster는 `Phase 6` 이월이며(`docs/phase5/02-path-decision.md:24-32`), 현재 코드도 `orca/state.py`를 shared adapter로 유지한다(`docs/phase5/02-path-decision.md:27`, `orca/state.py:104-107`).
판정 요약:
현재 코드에서 PR 1-5와 Phase 5 핵심 계약은 깨지지 않았다.
다만 ORCA-side `_connect()` 잔존, dual-DB provenance 미노출, runtime accumulation 미관측 같은 후속 관리 포인트는 남아 있다.
---
## Section 2: Repository Snapshot
### 2.1. ORCA module inventory
- `orca/__init__.py`: ORCA package marker. Evidence: `orca/__init__.py:1`.
- `orca/__main__.py`: `python -m orca` 실행 시 `orca.main`으로 진입시키는 thin module. Evidence: `orca/__main__.py:1-3`.
- `orca/agents.py`: ORCA 4-agent prompt pipeline과 Anthropic API 호출 wrapper를 담당한다. Evidence: `orca/agents.py:1-29`, `orca/agents.py:235`, `orca/agents.py:325`, `orca/agents.py:411`, `orca/agents.py:475`.
- `orca/analysis.py`: sentiment/trend/portfolio 분석, candidate review scorecard, verification, lesson extraction, pattern DB update를 한곳에 모아 둔 통합 분석 모듈이다. Evidence: `orca/analysis.py:1-19`, `orca/analysis.py:151`, `orca/analysis.py:297`, `orca/analysis.py:664`, `orca/analysis.py:1139`, `orca/analysis.py:1472`, `orca/analysis.py:1667`.
- `orca/backtest.py`: ORCA research backtest runner와 walk-forward research state 생성을 담당한다. Evidence: `orca/backtest.py:1-18`.
- `orca/brand.py`: ORCA/JACKAL 명칭 상수만 담는 branding module이다. Evidence: `orca/brand.py:1-7`.
- `orca/compat.py`: 환경변수 접근 helper만 제공한다. Evidence: `orca/compat.py:1-14`.
- `orca/dashboard.py`: HTML dashboard 생성기다. Evidence: `orca/dashboard.py:1-6`, `orca/dashboard.py:34`.
- `orca/data.py`: 시장 데이터 수집, 외부 API fallback, cost ledger, market-data 저장을 담당한다. Evidence: `orca/data.py:11`, `orca/data.py:25`, `orca/data.py:95`, `orca/data.py:273`, `orca/data.py:287`, `orca/data.py:528`.
- `orca/learning_policy.py`: ORCA/JACKAL 공용 learning policy 상수와 helper를 제공한다. Evidence: `orca/learning_policy.py:1-20`, `orca/learning_policy.py:24`, `orca/learning_policy.py:58`, `orca/learning_policy.py:68`.
- `orca/main.py`: CLI entrypoint와 `run_orca_cycle()` 호출만 수행하는 thin coordinator다. Evidence: `orca/main.py:1-48`.
- `orca/notify.py`: Telegram 전송, 주간/월간/속보 메시지, dashboard URL 조립 등 notification 계층을 담당한다. Evidence: `orca/notify.py:1-38`, `orca/notify.py:109`, `orca/notify.py:127`, `orca/notify.py:161`, `orca/notify.py:474`, `orca/notify.py:563`, `orca/notify.py:651`.
- `orca/paths.py`: 데이터/리포트/DB 경로 상수와 atomic write helper를 제공한다. Evidence: `orca/paths.py:1-38`, `orca/paths.py:44-59`.
- `orca/persist.py`: memory/report 저장과 state prediction persistence를 묶는 glue module이다. Evidence: `orca/persist.py:1-28`, `orca/persist.py:33`, `orca/persist.py:68`, `orca/persist.py:89`, `orca/persist.py:112`.
- `orca/pipeline.py`: ORCA agent pipeline을 얇게 연결한다. Evidence: `orca/pipeline.py:1-17`.
- `orca/policy_promote.py`: 최신 research gate 결과를 promotion decision으로 바꾼다. Evidence: `orca/policy_promote.py:1-16`, `orca/policy_promote.py:38`, `orca/policy_promote.py:78`, `orca/policy_promote.py:106`.
- `orca/postprocess.py`: report sanitization, candidate review, baseline 저장, secondary analyses, JACKAL news 수집을 묶는다. Evidence: `orca/postprocess.py:1-30`, `orca/postprocess.py:38`, `orca/postprocess.py:71`, `orca/postprocess.py:96`, `orca/postprocess.py:158`, `orca/postprocess.py:166`, `orca/postprocess.py:177`, `orca/postprocess.py:194`.
- `orca/present.py`: 콘솔 출력, dashboard build wrapper, Telegram send wrapper를 담당한다. Evidence: `orca/present.py:1-28`, `orca/present.py:33`, `orca/present.py:48`, `orca/present.py:55`, `orca/present.py:195`, `orca/present.py:212`, `orca/present.py:218`.
- `orca/research_gate.py`: 최신 research comparison report를 평가해 pass/warn/fail gate를 만든다. Evidence: `orca/research_gate.py:1-18`, `orca/research_gate.py:127`, `orca/research_gate.py:190`, `orca/research_gate.py:234`.
- `orca/research_report.py`: ORCA/JACKAL cross-system research comparison report를 생성한다. Evidence: `orca/research_report.py:1-24`, `orca/research_report.py:90`, `orca/research_report.py:236`, `orca/research_report.py:329`, `orca/research_report.py:415`.
- `orca/reset.py`: ORCA/JACKAL runtime state reset entrypoint다. Evidence: `orca/reset.py:1-18`, `orca/reset.py:131`, `orca/reset.py:163`, `orca/reset.py:214`.
- `orca/run_cycle.py`: ORCA 일일 실행 orchestration과 `HealthTracker`를 담당한다. Evidence: `orca/run_cycle.py:41-138`, `orca/run_cycle.py:141-438`.
- `orca/state.py`: ORCA core, shared candidate cluster, JACKAL learning state까지 모두 담는 SQLite-backed shared persistence adapter다. Evidence: `orca/state.py:1-21`, `orca/state.py:83-132`, `orca/state.py:505-3244`.
### 2.2. JACKAL module inventory
- `jackal/__init__.py`: JACKAL package marker. Evidence: `jackal/__init__.py:1`.
- `jackal/__main__.py`: `python -m jackal` 실행 시 `jackal.core`로 진입한다. Evidence: `jackal/__main__.py:1-3`.
- `jackal/adapter.py`: ORCA baseline/memory/news를 JACKAL 소비 형식으로 바꾸는 interface layer다. Evidence: `jackal/adapter.py:1-8`, `jackal/adapter.py:97`, `jackal/adapter.py:166`, `jackal/adapter.py:175`.
- `jackal/backtest.py`: JACKAL backtest runner와 signal family별 결과 집계를 담당한다. Evidence: `jackal/backtest.py:1-18`, `jackal/backtest.py:68`, `jackal/backtest.py:349`, `jackal/backtest.py:643`.
- `jackal/compact.py`: JACKAL context compact/summary 관리 모듈이다. Evidence: `jackal/compact.py:1-19`, `jackal/compact.py:35`.
- `jackal/core.py`: Shield -> Hunter -> Compact -> Evolution 순서의 orchestration을 담당한다. Evidence: `jackal/core.py:1-23`, `jackal/core.py:42`, `jackal/core.py:145`.
- `jackal/evolution.py`: live/shadow/recommendation outcome 학습, weight update, Claude adjustment, skill persistence를 담당한다. Evidence: `jackal/evolution.py:1-49`, `jackal/evolution.py:152`, `jackal/evolution.py:204`, `jackal/evolution.py:449`, `jackal/evolution.py:614`, `jackal/evolution.py:748`, `jackal/evolution.py:983`.
- `jackal/families.py`: JACKAL family taxonomy canonicalization helper다. Evidence: `jackal/families.py:1-15`, `jackal/families.py:27`, `jackal/families.py:33`.
- `jackal/hunter.py`: universe 구성, macro gate, multi-stage scoring, alerting, persistence를 한 번에 처리하는 discovery pipeline이다. Evidence: `jackal/hunter.py:1-60`, `jackal/hunter.py:233`, `jackal/hunter.py:358`, `jackal/hunter.py:594`, `jackal/hunter.py:818`, `jackal/hunter.py:1291`, `jackal/hunter.py:1495`.
- `jackal/market_data.py`: JACKAL용 macro/technical helper와 cache를 제공한다. Evidence: `jackal/market_data.py:1-29`, `jackal/market_data.py:52`, `jackal/market_data.py:111`, `jackal/market_data.py:159`, `jackal/market_data.py:431`.
- `jackal/probability.py`: ORCA state의 candidate probability summary를 JACKAL final score adjustment로 연결한다. Evidence: `jackal/probability.py:1-8`, `jackal/probability.py:11`, `jackal/probability.py:18`.
- `jackal/scanner.py`: watchlist 구성, deterministic quality gate, Analyst/Devil 호출, recommendation/log 저장, Telegram alert를 한 번에 수행하는 timing pipeline이다. Evidence: `jackal/scanner.py:1-67`, `jackal/scanner.py:127`, `jackal/scanner.py:515`, `jackal/scanner.py:868`, `jackal/scanner.py:1058`, `jackal/scanner.py:1382`, `jackal/scanner.py:1649`, `jackal/scanner.py:1974`.
- `jackal/shield.py`: usage budget, secret scan, spike detection 등 guardrail을 담당한다. Evidence: `jackal/shield.py:1-35`, `jackal/shield.py:45`, `jackal/shield.py:230`.
- `jackal/tracker.py`: hunt outcome 추적과 weight snapshot 업데이트를 담당한다. Evidence: `jackal/tracker.py:1-60`, `jackal/tracker.py:112`, `jackal/tracker.py:161`, `jackal/tracker.py:222`, `jackal/tracker.py:335`, `jackal/tracker.py:606`.
### 2.3. LOC distribution
방법:
`utf-8-sig` 기준으로 `orca/*.py`, `jackal/*.py`, `tests/*.py`를 정적 line count 했다.
이 방식은 BOM 파일 때문에 PowerShell 기본 `Get-Content`보다 안전하다.
- ORCA Python LOC: `12,781` across `23` files.
- JACKAL Python LOC: `7,540` across `14` files.
- Tests LOC: `506` across `5` files.
- Combined production code LOC (`orca + jackal`): `20,321`.
- Top 5 large modules:
  `orca/state.py 3245`,
  `orca/backtest.py 2614`,
  `jackal/scanner.py 1993`,
  `orca/analysis.py 1720`,
  `jackal/hunter.py 1668`.
- Top 5 concentration:
  상위 5개 파일이 전체 production Python LOC의 `55.3%`를 차지한다.
ORCA per-file LOC:
- `orca/state.py`: `3245`
- `orca/backtest.py`: `2614`
- `orca/analysis.py`: `1720`
- `orca/notify.py`: `748`
- `orca/data.py`: `736`
- `orca/dashboard.py`: `684`
- `orca/agents.py`: `631`
- `orca/run_cycle.py`: `438`
- `orca/research_report.py`: `432`
- `orca/postprocess.py`: `284`
- `orca/research_gate.py`: `242`
- `orca/reset.py`: `214`
- `orca/present.py`: `211`
- `orca/learning_policy.py`: `85`
- `orca/policy_promote.py`: `117`
- `orca/persist.py`: `123`
- `orca/paths.py`: `67`
- `orca/main.py`: `48`
- `orca/pipeline.py`: `17`
- `orca/compat.py`: `14`
- `orca/brand.py`: `7`
- `orca/__main__.py`: `3`
- `orca/__init__.py`: `1`
JACKAL per-file LOC:
- `jackal/scanner.py`: `1993`
- `jackal/hunter.py`: `1668`
- `jackal/evolution.py`: `1021`
- `jackal/backtest.py`: `652`
- `jackal/tracker.py`: `632`
- `jackal/market_data.py`: `494`
- `jackal/shield.py`: `306`
- `jackal/compact.py`: `239`
- `jackal/adapter.py`: `195`
- `jackal/core.py`: `163`
- `jackal/families.py`: `94`
- `jackal/probability.py`: `49`
- `jackal/__main__.py`: `3`
- `jackal/__init__.py`: `1`
Observation:
module size는 `orca/state.py`, `orca/backtest.py`, `orca/analysis.py`, `jackal/hunter.py`, `jackal/scanner.py`, `jackal/evolution.py`에 강하게 집중돼 있다.
이 집중은 Section 3 cohesion과 Section 5 technical debt에 직접 연결된다.
### 2.4. Tests snapshot
현재 자동 검증 실행 결과:
- `python -m unittest discover -s tests -v`: `13 tests`, all `OK`.
- `python -m compileall orca jackal tests`: passed.
- 별도 `pytest`, `coverage`, `actionlint` 실행 흔적은 현재 repo/workflow에서 찾지 못했다. Evidence: `.github/workflows/*.yml` 대상 `unittest|pytest|compileall|coverage|actionlint` 검색 결과 없음.
Test file inventory:
- `tests/test_verification_and_state.py`: verification behavior와 state alias compatibility를 점검한다. Evidence: `tests/test_verification_and_state.py:65`, `tests/test_verification_and_state.py:153`.
- `tests/test_notify_and_agents.py`: accuracy display, verification report formatting, reporter fallback을 점검한다. Evidence: `tests/test_notify_and_agents.py:58`, `tests/test_notify_and_agents.py:124`, `tests/test_notify_and_agents.py:147`.
- `tests/test_research_report.py`: research report sanitization을 점검한다. Evidence: `tests/test_research_report.py:6`.
- `tests/test_backtest_dry_lessons.py`: ORCA backtest dry-run lesson generation을 점검한다. Evidence: `tests/test_backtest_dry_lessons.py:7`.
- `tests/test_jackal_backtest.py`: JACKAL backtest universe exclusion을 점검한다. Evidence: `tests/test_jackal_backtest.py:7`.
Coverage shape:
- strong:
  `verification/state alias`, `notify formatting`, `research report sanitization`, `backtest helper`.
- weak:
  `orca/run_cycle.py`,
  `jackal/hunter.py`,
  `jackal/scanner.py`,
  `jackal/core.py`,
  `jackal/evolution.py`,
  workflow shell steps,
  Pages deploy path.
- direct workflow tests:
  없음.
  현재 workflow들은 state save shell script를 많이 포함하지만, 이를 정적으로 검증하는 테스트가 없다.
- dual-DB routing tests:
  직접적이고 전용인 테스트는 찾지 못했다.
  일부 state/verification alias 테스트는 존재하지만, Phase 5 routing invariant를 포괄하지는 않는다.
### 2.5. Workflow inventory
- `orca_daily.yml`: ORCA 일일 리포트 workflow.
  Trigger: schedule `30 23 * * 0-4`, `0 14 * * 1-5`, `0 22 * * 6`, `0 21 1 * *` + manual `mode`. Evidence: `.github/workflows/orca_daily.yml:1-18`.
  Statefulness: `data/orca_state.db`, `data/jackal_state.db`, reports, multiple JSON files를 commit한다 (`.github/workflows/orca_daily.yml:141-161`).
- `orca_jackal.yml`: JACKAL session workflow.
  Trigger: Korea/US session schedule 4개 + manual `session_mode`, `force_hunt`, `force_scan`, `force_evolve`. Evidence: `.github/workflows/orca_jackal.yml:1-35`.
  Statefulness: hotfix-style backup/reset/restore 후 `data/jackal_state.db` 포함 JACKAL-owned artifacts를 main에 push한다 (`.github/workflows/orca_jackal.yml:103-127`, `.github/workflows/orca_jackal.yml:145-190`).
- `jackal_tracker.yml`: JACKAL outcome tracker workflow.
  Trigger: daily schedule `0 3 * * *`, `0 21 * * *` + manual `all_entries`, `dry_run`, `notify`. Evidence: `.github/workflows/jackal_tracker.yml:1-25`.
  Statefulness: `checkpoint_jackal_db()` 호출 후 `data/orca_state.db`, `data/jackal_state.db`, `jackal/jackal_weights.json`을 add한다 (`.github/workflows/jackal_tracker.yml:70-99`).
- `jackal_scanner.yml`: manual scanner workflow.
  Trigger: `workflow_dispatch` with `force`. Evidence: `.github/workflows/jackal_scanner.yml:1-13`.
  Statefulness: `checkpoint_jackal_db()` 호출 후 `data/orca_state.db`, `data/jackal_state.db`와 JACKAL logs를 add한다 (`.github/workflows/jackal_scanner.yml:54-75`).
- `orca_backtest.yml`: ORCA backtest workflow.
  Trigger: manual only. Evidence: `.github/workflows/orca_backtest.yml:1-8`.
  Statefulness: commit이 아니라 artifact upload 중심이다.
- `orca_reset.yml`: ORCA/JACKAL runtime reset workflow.
  Trigger: manual only with `reset_orca`, `reset_jackal`, `confirm`. Evidence: `.github/workflows/orca_reset.yml:1-20`.
  Statefulness: selected runtime files reset 후 commit/push한다.
- `pages_dashboard.yml`: GitHub Pages deploy workflow.
  Trigger: push to `main` on `reports/**`, `data/**`, `orca/**`, workflow file itself + manual dispatch. Evidence: `.github/workflows/pages_dashboard.yml:1-21`.
  Statefulness: repo push를 받아 dashboard를 publish한다.
- `policy_eval.yml`: policy evaluation workflow.
  Trigger: `workflow_call` + manual dispatch. Evidence: `.github/workflows/policy_eval.yml:1-30`.
  Statefulness: `data/orca_state.db`와 comparison/gate reports를 artifact로 upload한다.
- `policy_promote.yml`: policy promotion workflow.
  Trigger: `workflow_call` + manual dispatch. Evidence: `.github/workflows/policy_promote.yml:1-25`.
  Statefulness: promotion md/json artifact를 upload한다.
Workflow-wide observation:
- `orca-repo-state` concurrency group이 `orca_daily.yml`, `orca_jackal.yml`, `jackal_tracker.yml`, `jackal_scanner.yml`, `orca_reset.yml`에 공통 적용돼 있다. Evidence: `.github/workflows/orca_daily.yml:3-5`, `.github/workflows/orca_jackal.yml:8-10`, `.github/workflows/jackal_tracker.yml:8-10`, `.github/workflows/jackal_scanner.yml:3-5`, `.github/workflows/orca_reset.yml:3-5`.
- test/lint-only workflow는 없다.
  현재 CI의 초점은 scheduled production execution, research report generation, policy artifact evaluation에 있다.
---
## Section 3: 설계 품질 평가
### 3.1. 모듈 응집도
#### `orca/run_cycle.py`
Judgment:
`medium`.
이 모듈의 중심 책임은 ORCA daily cycle orchestration이다.
그 점은 유지되고 있다.
다만 실제 구현은 orchestration 외에 다음을 함께 가진다.
`HealthTracker` 정의,
minimal failed report 생성,
state finish fallback,
degraded data branching,
notification error 처리.
Evidence:
`HealthTracker`는 `orca/run_cycle.py:41-138`,
cycle 전체는 `orca/run_cycle.py:141-438`,
minimal failed report helper는 `orca/run_cycle.py:150-160`,
data degradation branch는 `orca/run_cycle.py:248-286`,
global exception path는 `orca/run_cycle.py:421-438`.
해석:
PR 3의 `main.py thin coordinator` 계약은 지켜졌지만, 실질 orchestration complexity는 `main.py`에서 `run_cycle.py`로 이동했다.
즉, contract는 보존됐고 응집도는 “허용 가능한 coordinator 집중” 상태다.
#### `orca/state.py`
Judgment:
`low`.
Phase 5 문서가 이 모듈을 shared adapter로 인정한 것은 맞다.
그 전제는 지켜진다.
하지만 shared adapter라는 설명만으로 낮은 응집도가 사라지지는 않는다.
현재 이 파일은
DB connect/bootstrap,
ORCA run/prediction/outcome,
ORCA/JACKAL backtest state,
JACKAL learning tables,
candidate registry/review/outcome/lesson,
probability summary,
health event queue를 모두 담는다.
Evidence:
connect/bootstrap `orca/state.py:83-132`,
ORCA run/prediction/outcome `orca/state.py:515-845`,
backtest cluster `orca/state.py:848-1168`,
JACKAL learning cluster `orca/state.py:1171-2202`,
candidate cluster `orca/state.py:2297-3244`.
해석:
Phase 5 맥락상 “존재 자체”는 계약 위반이 아니지만,
현재 repo에서 가장 큰 응집도 리스크는 여전히 `orca/state.py`다.
#### `orca/analysis.py`
Judgment:
`low-medium`.
이 모듈은 ORCA analysis라는 이름 아래 실제로 다섯 책임을 수행한다.
첫째, sentiment/trend/portfolio analysis (`orca/analysis.py:151-361`).
둘째, candidate review scorecard와 alignment verdict (`orca/analysis.py:376-871`).
셋째, verification/outcome resolution helper (`orca/analysis.py:1059-1346`).
넷째, lesson extraction 및 lesson prompt (`orca/analysis.py:1353-1627`).
다섯째, pattern DB update와 compact history (`orca/analysis.py:1667-1717`).
해석:
이 파일은 “analysis”라는 라벨보다 실제 책임 폭이 넓다.
특히 candidate review, verification, lessons는 테스트/의존성이 서로 다르므로 분리 가치가 높다.
#### `jackal/hunter.py`
Judgment:
`low-medium`.
Hunter는 discovery pipeline이라는 큰 축은 분명하다.
그러나 구현은
universe build,
macro gate,
technical scoring,
LLM quick scan,
LLM analyst/devil/final decision,
cooldown,
Telegram,
watchlist snapshot,
log/state persistence까지 한 파일에 포함한다.
Evidence:
universe/snapshot `jackal/hunter.py:233-347`,
macro/technical scoring `jackal/hunter.py:358-739`,
quick scan + analyst/devil/final `jackal/hunter.py:818-1284`,
cooldown/Telegram/logging `jackal/hunter.py:1291-1474`,
orchestration `jackal/hunter.py:1495-1665`.
해석:
지금도 동작은 이해 가능하지만, pure scoring logic과 IO/orchestration이 강하게 결합돼 있어 테스트 비용이 높다.
#### `jackal/scanner.py`
Judgment:
`low`.
Scanner는 repo 전체에서 가장 책임이 넓은 JACKAL module이다.
현재 한 파일 안에
watchlist assembly (`jackal/scanner.py:127-234`),
context loading (`jackal/scanner.py:260-512`),
deterministic quality engine (`jackal/scanner.py:515-865`),
LLM analyst/devil (`jackal/scanner.py:868-1051`),
final judgment/cooldown (`jackal/scanner.py:1058-1222`),
Telegram/recommendation/log save (`jackal/scanner.py:1229-1563`),
extra ticker suggestion (`jackal/scanner.py:1577-1646`),
main orchestration (`jackal/scanner.py:1649-1986`)가 공존한다.
해석:
이 파일은 응집도 문제와 테스트성 문제를 동시에 만든다.
구조 개선의 1순위 후보 중 하나다.
#### `jackal/evolution.py`
Judgment:
`medium-low`.
Evolution class는 “학습”이라는 공통 라벨은 유지하지만,
실제 내부는 세 층으로 나뉜다.
outcome learning (`jackal/evolution.py:204-551`),
Claude context/response handling (`jackal/evolution.py:557-719`, `892-900`),
rule registry/skills/instinct persistence (`jackal/evolution.py:725-805`),
weight save + shadow accuracy sync (`jackal/evolution.py:906-1011`).
해석:
모두 learning loop에 속하므로 `state.py`나 `analysis.py`보다 응집도는 낫다.
하지만 LLM reasoning, rule disable, weight persistence가 모두 한 class에 섞여 있어 클래스 내부 분리가 유효하다.
#### 응집도 종합
- `run_cycle.py`: coordinator로서 허용 가능한 복합성.
- `state.py`: Phase 5 계약상 shared adapter로 인정되지만, 여전히 가장 큰 structural concentration point.
- `analysis.py`, `hunter.py`, `scanner.py`, `evolution.py`: 단일 책임을 “느슨하게”만 지키고 있다.
- 즉시 위험:
  이해 비용 상승,
  테스트 fixture 증가,
  변경시 regression 범위 확대.
### 3.2. 의존성 구조
방법:
AST import graph를 기준으로 `orca.*`, `jackal.*` 간 내부 import edge를 추출했다.
Graph 요약:
- top out-degree:
  `orca.postprocess 7`,
  `orca.analysis 6`,
  `orca.main 6`,
  `jackal.core 5`,
  `jackal.hunter 5`,
  `jackal.scanner 5`,
  `orca.run_cycle 5`.
- top in-degree:
  `orca.paths 18`,
  `orca.state 14`,
  `orca.brand 9`,
  `orca.learning_policy 5`,
  `orca.analysis 4`,
  `orca.compat 4`.
해석:
- `orca.paths`는 경로 상수 허브다.
  이 자체는 나쁜 허브가 아니다.
- `orca.state`는 persistence hub다.
  dual-DB 이후에도 JACKAL에서 지속적으로 의존한다.
- ORCA -> JACKAL 직접 의존은 매우 제한적이다.
  코드 검색상 실질 import는 `orca/state.py:19`의 `jackal.families` canonical taxonomy import가 핵심이다.
- JACKAL -> ORCA 의존은 더 강하다.
  `jackal.adapter.py:8`,
  `jackal.core.py:21`,
  `jackal.hunter.py:31`,
  `jackal.scanner.py:29`,
  `jackal.tracker.py:47`,
  `jackal.evolution.py:24`,
  `jackal.probability.py:8` 등이 `orca.state` 또는 `orca.paths`를 직접 사용한다.
- 방향성 결론:
  현재 구조는 “ORCA core + shared adapter를 JACKAL이 소비”하는 방향이다.
  순수한 `ORCA -> JACKAL` 호출 구조가 아니라,
  JACKAL이 ORCA shared layer를 중심으로 매달리는 구조에 가깝다.
순환 의존 여부:
- ORCA/JACKAL package 간 강한 cycle은 찾지 못했다.
  `orca.state -> jackal.families`는 단방향이고, `jackal.families`는 ORCA를 다시 import하지 않는다.
- 다만 ORCA 내부에는 import cycle 1개가 있다.
  `orca.analysis -> orca.data -> orca.notify -> orca.analysis`.
Evidence:
- `orca/analysis.py:1478`에서 local import로 `load_market_data`.
- `orca/data.py:616-618`에서 local import로 `send_message`.
- `orca/notify.py:351-354`에서 local import로 `load_lessons`.
해석:
- 이 cycle은 top-level import crash를 막기 위해 local import로 완화돼 있다.
- 그러나 구조상으로는 cycle이며, 변경 영향 추적을 어렵게 만든다.
- Phase 5 contract와 직접 충돌하지는 않지만, 설계 품질 점수에는 분명한 감점이다.
### 3.3. 에러 처리 일관성
AST census:
- `orca/state.py`: try handler `30`, re-raise `0`.
- `jackal/scanner.py`: try handler `24`, re-raise `0`.
- `jackal/hunter.py`: try handler `28`, re-raise `0`.
- `orca/run_cycle.py`: try handler `7`, re-raise `0`.
- `jackal/evolution.py`: try handler `17`, re-raise `1`.
핵심 패턴은 네 가지다.
패턴 A: degraded-but-continue with health tracking.
- 대표 위치:
  `orca/run_cycle.py:240-286`,
  `orca/run_cycle.py:314-321`,
  `orca/run_cycle.py:365-373`,
  `orca/persist.py:96-109`,
  `orca/present.py:197-207`.
- 장점:
  일일 운용이 외부 API/부수 기능 실패에 완전히 멈추지 않는다.
- 단점:
  degradation이 누적돼도 테스트나 CI에서 자동으로 잡히지 않으면 수동 확인 의존이 커진다.
패턴 B: fail-open fallback.
- 대표 위치:
  `jackal/adapter.py:112-163`,
  `jackal/market_data.py:434-470`,
  `jackal/hunter.py:1584-1587`,
  `jackal/scanner.py:1696-1698`.
- 특징:
  warning을 남기거나 그냥 빈 값/continue로 진행한다.
- 장점:
  scheduled run 생존성.
- 단점:
  “왜 품질이 떨어졌는가”가 report health에 항상 반영되지는 않는다.
패턴 C: silent pass / drop.
- 대표 위치:
  `jackal/adapter.py:154-162`,
  `orca/data.py:614-618`,
  `orca/persist.py:81-85`,
  `orca/dashboard.py:27`, `84`, `86`, `163`, `168`, `173`, `187`, `197`, `235`.
- 평가:
  현재 repo에서 가장 관측성이 약한 패턴이다.
패턴 D: primary-first, secondary best-effort.
- 대표 위치:
  `orca/state.py:1227-1243`,
  `orca/state.py:1352-1367`,
  `orca/state.py:1540-1555`.
- 평가:
  Phase 5 Path B 계약에는 부합한다.
  하지만 observability는 `stderr`에 머무른다.
일관성 평가:
- ORCA outer cycle은 health-tracked degradation 패턴이 비교적 일관적이다.
- JACKAL runtime은 warning/continue fallback이 많다.
- dashboard/persist/adapter 일부는 silent pass가 남아 있어 일관성이 떨어진다.
- 즉,
  “primary feature는 계속 돌린다”는 운영 철학은 일관적이지만,
  “실패를 어디까지 구조적으로 드러내는가”는 일관적이지 않다.
### 3.4. 설정 분산도
Python 상수 중심 설정:
- learning policy:
  `orca/learning_policy.py:6-19`.
- research gate thresholds:
  `orca/research_gate.py:20-25`.
- review score weights:
  `orca/analysis.py:428-435`.
- JACKAL shield budgets:
  `jackal/shield.py:29-30`.
inline threshold hotspots:
- Hunter macro gate:
  `jackal/hunter.py:406-447`.
- Hunter technical scoring thresholds:
  `jackal/hunter.py:620-692`.
- Hunter entry threshold and mode:
  `jackal/hunter.py:1177-1216`.
- Scanner quality score, veto, gate penalty, family thresholds:
  `jackal/scanner.py:541-865`.
- Evolution outcome windows and weight deltas:
  `jackal/evolution.py:217-285`, `jackal/evolution.py:315-329`, `jackal/evolution.py:460-470`.
env var distribution:
- centralized accessor:
  `orca/compat.py:8-14`.
- ORCA prompt/model env:
  `orca/agents.py:21-29`, `orca/analysis.py:44-45`, `orca/main.py:29`, `orca/notify.py:28-32`, `orca/postprocess.py:41`.
- market-data secrets:
  `orca/data.py:39`, `334`, `393`.
- JACKAL runtime env:
  `jackal/hunter.py:58-60`, `jackal/scanner.py:65-67`, `jackal/evolution.py:49`, `jackal/shield.py:29-30`.
JSON/runtime file distribution:
- ORCA paths:
  `orca/paths.py:28-38`.
- Hunter watchlist snapshot:
  `jackal/hunter.py:307-347`.
- Scanner recommendation/watchlist logs:
  `jackal/scanner.py:1382-1435`.
- Evolution weight save:
  `jackal/evolution.py:983-1011`.
평가:
- core policy constants는 일부 중앙화돼 있다.
- 그러나 실제 deterministic thresholds는 `hunter.py`, `scanner.py`, `evolution.py`, `research_gate.py`에 넓게 흩어져 있다.
- JSON, env, Python constant의 혼합 사용은 “운영 유연성”보다 “감사 난이도”를 더 크게 만든다.
- 특히 JACKAL quality-related constants는 선언형 registry보다 inline rule body로 들어가 있어, 변경 diff는 보여도 “정책 diff”는 잘 안 보인다.
### 3.5. 테스트 가능성
현재 테스트가 바로 검증 가능한 영역:
- learning policy pure math:
  `orca/learning_policy.py:24-80`.
- family taxonomy:
  `jackal/families.py:27-33`.
- candidate review scoring helpers:
  `orca/analysis.py:527-661`.
- verification price check helper:
  `orca/analysis.py:1006-1108`.
- scanner family classifier / final judgment:
  `jackal/scanner.py:441-454`, `1058-1122`.
현재 통합 테스트가 더 적합한 영역:
- `run_orca_cycle()`:
  `orca/run_cycle.py:141-438`.
- ORCA agent pipeline:
  `orca/agents.py:105-475`.
- `run_hunt()`:
  `jackal/hunter.py:1495-1665`.
- `run_scan()`:
  `jackal/scanner.py:1649-1986`.
- `JackalEvolution.evolve()`:
  `jackal/evolution.py:159-195`, `204-1011`.
- workflow shell save steps:
  `.github/workflows/orca_daily.yml:134-161`,
  `.github/workflows/orca_jackal.yml:103-190`,
  `.github/workflows/jackal_tracker.yml:70-99`,
  `.github/workflows/jackal_scanner.yml:54-75`.
monkeypatch / stub 필요 영역:
- Anthropic:
  `orca/agents.py:17-29`,
  `orca/analysis.py:28-46`,
  `jackal/hunter.py:29-60`,
  `jackal/scanner.py:26-67`,
  `jackal/evolution.py:22-49`,
  `jackal/compact.py:19`.
- yfinance:
  `orca/data.py:124`,
  `orca/backtest.py:1721`,
  `jackal/backtest.py:38`,
  `jackal/hunter.py:27`,
  `jackal/market_data.py:22`,
  `jackal/tracker.py:44`,
  `jackal/evolution.py:21`.
- httpx / Telegram:
  `orca/notify.py:10`,
  `jackal/hunter.py:26`,
  `jackal/scanner.py:25`,
  `jackal/market_data.py:21`,
  `jackal/tracker.py:553`.
- filesystem / JSON state:
  `orca/paths.py:16-59`,
  `jackal/hunter.py:307-347`,
  `jackal/scanner.py:1382-1563`,
  `jackal/evolution.py:983-1011`.
- current time:
  `orca/run_cycle.py:142`, `335`,
  `jackal/hunter.py:1496`,
  `jackal/scanner.py:1650`,
  `jackal/evolution.py:217`, `462`,
  `jackal/tracker.py:88`.
총평:
- pure helper가 전혀 없는 레포는 아니다.
- 그러나 중요한 business path의 대부분이
  `time + env + filesystem + network + sqlite + side effects`
  를 동시에 건드린다.
- 그래서 현재 테스트가 적은 이유는 “테스트가 필요 없어서”가 아니라 “fixture 비용이 비싸서”에 가깝다.
---
## Section 4: 관측 인프라 현황
### 4.1. 현재 관측 자산
- HealthTracker 10 codes. Evidence: `orca/run_cycle.py:41-138`, Section 1 contract evidence.
  역할: degraded reason, counters, detail payload를 per-run report에 넣는다 (`reports/2026-04-22_morning.json:211-228`).
- per-run report JSON. Evidence: `orca/persist.py:68-74`, `orca/persist.py:112-123`.
  최신 예시에는 `data_quality`, `learning_policy`, `health`, `failed_sources`가 실제로 들어 있다 (`reports/2026-04-22_morning.json:117`, `160-240`).
- research comparison / gate / promotion artifacts. Evidence: `orca/research_report.py:291-325`, `orca/research_gate.py:127-242`, `orca/policy_promote.py:38-117`.
  실제 파일: `reports/orca_research_comparison.json`, `reports/orca_research_gate.json`, `reports/orca_policy_promotion.json`.
- Phase 5 cross-DB stderr warnings. Evidence: `orca/state.py:1227-1243`, `orca/state.py:1352-1367`, `orca/state.py:1540-1555`.
  역할: secondary candidate propagation failure를 최소한 stderr에 남긴다.
- dashboard HTML + GitHub Pages. Evidence: `orca/present.py:195-207`, `orca/dashboard.py:34-684`, `.github/workflows/pages_dashboard.yml:1-25`.
  역할: repo-push 기반 정적 dashboard publish.
- Telegram notifications. Evidence: `orca/notify.py:109-748`, `jackal/hunter.py:1335-1347`, `jackal/scanner.py:1229-1242`, `jackal/tracker.py:547-579`.
  역할: ORCA daily reports, JACKAL alerts, tracker summary.
- SQLite state. Evidence: `orca/paths.py:33-34`, `orca/state.py:83-132`.
  현재 파일:
  `data/orca_state.db`,
  `data/jackal_state.db`.
- JSON runtime logs. Evidence: `jackal/hunter.py:1410-1474`,
  `jackal/scanner.py:1382-1563`,
  `jackal/evolution.py:983-1011`.
  현재 예시:
  `jackal/hunt_log.json`,
  `jackal/scan_log.json`,
  `jackal/recommendation_log.json`,
  `jackal/jackal_weights.json`,
  `data/jackal_watchlist.json`.
- daily market-data quality signal. Evidence: `orca/data.py:577-612`, `orca/run_cycle.py:248-286`.
  역할: ORCA는 `poor`일 때 분석을 중단하고, `degraded`일 때 경고와 함께 계속 진행한다.
- research warnings for missing JACKAL evidence. Evidence: `orca/research_report.py:253-269`, `reports/orca_research_comparison.json:778-781`.
  역할: shadow batch/history 부족을 구조적으로 드러낸다.
### 4.2. 관측 Blind Spots
#### Blind spot 1: cross-DB secondary candidate propagation
어떤 상황:
`jackal_state.db` primary write는 성공했지만 `candidate_registry` / `candidate_outcomes` secondary write가 실패하는 경우.
현재 어떻게 보이는가:
`stderr` 경고만 남고, HealthTracker나 report `health.details`에는 들어가지 않는다.
영향 추정:
JACKAL learning loop는 유지되지만 ORCA candidate spine은 조용히 비어 있을 수 있다.
Evidence:
`orca/state.py:1227-1243`, `orca/state.py:1352-1367`, `orca/state.py:1540-1555`,
`docs/orca_v2_backlog.md:233-252`.
#### Blind spot 2: research report의 dual-DB provenance 누락
어떤 상황:
Phase 5 이후 repo는 dual-DB인데, comparison report는 여전히 `state_db` 단수 필드만 기록한다.
현재 어떻게 보이는가:
`reports/orca_research_comparison.json`에는 `state_db` 하나만 있고 `jackal_state.db` 경로나 snapshot metadata는 없다.
영향 추정:
research artifact만 보고는 “이 숫자가 어느 DB 스냅샷에서 왔는지”가 완전하게 드러나지 않는다.
Evidence:
`orca/research_report.py:291-325`,
`orca/research_report.py:343-347`,
`reports/orca_research_comparison.json:1-4`.
#### Blind spot 3: `jackal_state.db` 비어 있음이 일일 report에는 직접 surfaced 되지 않음
어떤 상황:
현재 워크스페이스 스냅샷 기준 `data/jackal_state.db` 8 objects가 모두 `COUNT = 0`이다.
현재 어떻게 보이는가:
daily report는 `jackal_probability_summary`, candidate review, health를 보여주지만,
JACKAL DB table counts 자체는 보여주지 않는다.
영향 추정:
scheduled run 후에도 JACKAL accumulation이 안 쌓이는 상태를 operator가 늦게 알아차릴 수 있다.
Evidence:
runtime sqlite query on `data/jackal_state.db`,
`reports/orca_research_comparison.json:778-781`,
`reports/2026-04-22_morning.json:160-240`.
#### Blind spot 4: dashboard 내부 섹션 오류의 silent suppression
어떤 상황:
dashboard sub-block 계산 중 일부 값 파싱/표시가 실패하는 경우.
현재 어떻게 보이는가:
`orca/present.py:195-207`는 dashboard build 실패 자체는 health code로 잡지만,
`orca/dashboard.py` 내부는 여러 `except: pass`를 사용한다.
영향 추정:
dashboard가 “생성은 됐지만 일부 카드가 빈 상태”로 남을 수 있다.
Evidence:
`orca/present.py:195-207`,
`orca/dashboard.py:27`,
`orca/dashboard.py:84`,
`orca/dashboard.py:86`,
`orca/dashboard.py:163`,
`orca/dashboard.py:168`,
`orca/dashboard.py:173`,
`orca/dashboard.py:187`,
`orca/dashboard.py:197`,
`orca/dashboard.py:235`.
#### Blind spot 5: report ingestion corruption skip
어떤 상황:
`reports/YYYY-MM-DD_*.json` 중 하나가 깨지거나 decode 실패하는 경우.
현재 어떻게 보이는가:
`get_todays_analyses()`는 `JSONDecodeError` / `OSError`를 그냥 무시한다.
영향 추정:
lesson extraction이나 duplicate detection이 조용히 불완전해질 수 있다.
Evidence:
`orca/persist.py:77-86`.
#### Blind spot 6: JACKAL news parse failure
어떤 상황:
`data/jackal_news.json`가 깨졌거나 예상 shape가 아닌 경우.
현재 어떻게 보이는가:
`load_orca_context()`는 마지막 `except Exception: pass`로 그냥 빈 `jackal_news`를 반환한다.
영향 추정:
news-enriched context가 빠져도 Hunter는 fallback regime만으로 계속 진행한다.
Evidence:
`jackal/adapter.py:154-162`.
#### Blind spot 7: technical fetch 실패가 health로 승격되지 않음
어떤 상황:
scanner에서 `fetch_technicals()`가 빈 값을 반환하는 경우.
현재 어떻게 보이는가:
그 ticker는 `continue`로 넘기고 health/event/report에 남기지 않는다.
영향 추정:
watchlist가 줄어든 원인이 “시장 조건”인지 “data fetch noise”인지 구분이 어려워진다.
Evidence:
`jackal/scanner.py:1696-1698`.
#### Blind spot 8: workflow drift detection 부재
어떤 상황:
Phase 5 save steps에서 `checkpoint_jackal_db()` 호출이나 `git add -f data/jackal_state.db`가 빠지는 미래 변경이 들어오는 경우.
현재 어떻게 보이는가:
이를 막는 전용 test/lint workflow가 없다.
영향 추정:
contract regression이 코드 리뷰에만 의존한다.
Evidence:
current workflow save steps exist at
`.github/workflows/orca_daily.yml:141-160`,
`.github/workflows/jackal_tracker.yml:80-98`,
`.github/workflows/jackal_scanner.yml:64-74`,
`.github/workflows/orca_jackal.yml:110-127`,
and there is no separate test/lint workflow invoking `unittest|pytest|coverage|actionlint`.
#### Blind spot 9: ORCA poor-data notify 자체가 silent fail 가능
어떤 상황:
시장 데이터가 `poor`일 때 warning telegram을 보내려 하지만 notify send가 실패하는 경우.
현재 어떻게 보이는가:
`orca/data.py`는 bare `except: pass`를 사용한다.
영향 추정:
데이터 품질이 가장 나쁜 시점에 운영자 경고가 누락될 수 있다.
Evidence:
`orca/data.py:614-618`.
#### Blind spot 10: current non-zero accumulation proof 부재
어떤 상황:
Phase 5 설계는 `scheduled run 후 COUNT > 0`을 성공 기준으로 적었지만, 현재 스냅샷에서는 아직 그 증거가 없다.
현재 어떻게 보이는가:
current local `data/orca_state.db`와 `data/jackal_state.db` query 결과에서 JACKAL learning tables가 모두 0 row였고,
research comparison도 동일 경고를 유지한다.
영향 추정:
코드와 workflow는 merge됐지만 운영 성공이 “완전히 입증됨” 단계는 아니다.
Evidence:
runtime sqlite query on both DBs,
`docs/phase5/02-path-decision.md:90-97`,
`reports/orca_research_comparison.json:778-781`.
---
## Section 5: 구조적 위험 (Risks, not proposals)
### 5.1. SPOF 분석
#### Claude API 의존
영향 범위:
ORCA agents, candidate review 일부, JACKAL quick scan/analyst/devil, JACKAL compact, evolution adjustment.
실패 시 모습:
fallback/default payload로 계속 가는 경로가 많지만, 판단 품질과 설명 가능성이 급격히 떨어진다.
Evidence:
`orca/agents.py:17-29`,
`orca/analysis.py:28-46`,
`jackal/hunter.py:269-304`,
`jackal/scanner.py:868-1051`,
`jackal/compact.py:19`,
`jackal/evolution.py:614-669`.
평가:
single external reasoning provider에 집중돼 있다.
코드상 degraded mode는 존재하지만, 전략적 대체 provider나 offline model path는 없다.
#### yfinance rate limit / availability
영향 범위:
market data, ORCA backtest, JACKAL technicals, tracker, evolution outcome scoring.
실패 시 모습:
cached snapshot, continue, warning fallback이 많다.
즉시 hard fail보다 “조용한 coverage 감소”로 나타날 가능성이 더 높다.
Evidence:
`orca/data.py:124`,
`orca/backtest.py:1721`,
`jackal/hunter.py:27`,
`jackal/market_data.py:431-470`,
`jackal/tracker.py:44`,
`jackal/evolution.py:21`.
평가:
실제 운영상 가장 빈번한 SPOF 후보다.
#### GitHub Actions 중단 / push conflict
영향 범위:
scheduled run persistence, daily report delivery, tracker accumulation, JACKAL session save, Pages deploy.
실패 시 모습:
runtime may run, but commit/push 실패면 다음 run baseline continuity가 끊긴다.
Evidence:
schedule-driven workflows:
`.github/workflows/orca_daily.yml:7-18`,
`.github/workflows/orca_jackal.yml:11-35`,
`.github/workflows/jackal_tracker.yml:11-25`.
hotfix save/reset/push retry:
`.github/workflows/orca_jackal.yml:140-207`.
평가:
state continuity가 source control workflow health에 강하게 묶여 있다.
#### SQLite 파일 손상 / lock / WAL sidecar mismatch
영향 범위:
`data/orca_state.db`, `data/jackal_state.db`.
실패 시 모습:
ORCA는 `state_db_unavailable` degradation으로 계속 갈 수 있지만,
JACKAL learning rows와 candidate spine의 일부는 partial inconsistency에 빠질 수 있다.
Evidence:
DB connect/WAL config:
`orca/state.py:83-115`.
workflow checkpoint:
`orca/state.py:118-132`,
`.github/workflows/orca_daily.yml:141-160`,
`.github/workflows/orca_jackal.yml:110-127`.
평가:
single-file SQLite 자체보다 “DB 파일 + git-based persistence + workflow timing” 조합이 실제 SPOF다.
### 5.2. 데이터 파이프라인 gap
gap 1:
`fetch_technicals()` 실패 ticker가 scanner에서 silently dropped 된다.
Evidence: `jackal/scanner.py:1696-1698`.
영향: scan coverage 감소 원인이 report health로 올라오지 않는다.
gap 2:
cross-DB candidate propagation은 secondary write 실패 시 `stderr`만 남긴다.
Evidence: `orca/state.py:1227-1243`, `1352-1367`, `1540-1555`.
영향: JACKAL DB와 candidate spine이 순간적으로 어긋날 수 있다.
gap 3:
`record_candidate()`는 `record_jackal_shadow_signal()`, `resolve_jackal_shadow_signal()`, `sync_jackal_live_events()` 세 경로에서 fan-in 된다.
Evidence: `orca/state.py:1220`, `1345`, `1532`, `2606`.
영향: 중복 upsert surface가 존재하고, logical ownership 추적이 어렵다.
gap 4:
report ingestion failure가 skip된다.
Evidence: `orca/persist.py:81-85`.
영향: lessons/duplicate detection/input history가 부분적으로 사라져도 알기 어렵다.
gap 5:
ORCA/JACKAL mutable state가 DB와 JSON에 동시에 남아 있다.
Evidence: `orca/paths.py:28-38`, `jackal/hunter.py:1410-1474`, `jackal/scanner.py:1382-1563`, runtime `data/` and `jackal/*.json`.
영향: source of truth 인식이 흐려질 수 있다.
gap 6:
workflow save steps가 shell-script로 중복돼 있다.
Evidence: `.github/workflows/orca_daily.yml:146-164`, `.github/workflows/jackal_tracker.yml:85-99`, `.github/workflows/jackal_scanner.yml:69-75`, `.github/workflows/orca_jackal.yml:116-190`.
영향: 한 workflow만 drift해도 persistence behavior가 달라질 수 있다.
### 5.3. Technical debt inventory
debt 1:
shared adapter 문제는 Phase 5 이후에도 남아 있다.
Evidence: `docs/phase5/02-path-decision.md:26-32`, `orca/state.py:1-21`, `orca/state.py:505-3244`.
debt 2:
legacy `_connect()`와 new `_connect_orca()`가 공존한다.
Evidence: `orca/state.py:83-101`, `orca/state.py:519`, `541`, `670`, `754`, `2637`, `3225`.
debt 3:
candidate registry는 여전히 cross-DB fan-in 지점이다.
Evidence: `orca/state.py:1220`, `1345`, `1532`, `2606-2721`.
debt 4:
repo-wide UTF-8 BOM 22 files가 남아 있다.
Evidence: runtime scan on current workspace,
`docs/orca_v2_backlog.md:273-300`.
debt 5:
`analysis -> data -> notify -> analysis` cycle이 존재한다.
Evidence: `orca/analysis.py:1478`, `orca/data.py:616`, `orca/notify.py:353`.
debt 6:
oversized modules가 너무 많다.
Evidence: Section 2 LOC distribution.
debt 7:
workflow hotfix shell complexity가 높다.
Evidence: `.github/workflows/orca_jackal.yml:103-207`.
주석 자체가 `symptom-level hotfix`라고 적고 있다 (`.github/workflows/orca_jackal.yml:103-106`).
debt 8:
daily report와 research report의 dual-DB provenance가 완전하지 않다.
Evidence: `orca/research_report.py:291-325`, `reports/orca_research_comparison.json:1-4`.
debt 9:
workflow-level test/lint automation이 없다.
Evidence: workflow file inventory only; no dedicated test/lint workflow found.
debt 10:
research artifact scope의 `jackal_state.db` 포함 여부는 아직 deferred 상태다.
Evidence: `docs/orca_v2_backlog.md:254-272`.
debt 11:
cross-DB secondary write observability 강화는 의도적으로 deferred 상태다.
Evidence: `docs/orca_v2_backlog.md:233-252`.
debt 12:
BOM cleanup 역시 이미 deferred 상태다.
Evidence: `docs/orca_v2_backlog.md:273-300`.
---
## Section 6: 개선 제안
경고:
아래 제안은 투자 전략, portfolio construction, regime-adaptive threshold, 신규 factor 추가를 포함하지 않는다.
그런 항목은 외부 리뷰에서 제기됐지만 `docs/analysis/2026-04-22_external_review.md:12-22`가 명시적으로 “검증되지 않은 proposal”이라고 경고했고,
현재 backlog/Phase 6 범위에도 이미 separate track으로 존재한다.
또한 아래 제안은
`candidate spine 재설계`,
`shared adapter split`,
`research artifact scope 재검토`,
`repo-wide BOM 제거`,
`cross-DB secondary write observability 신설`
을 “새 제안”으로 다시 올리지 않는다.
이들은 이미 backlog/deferred item이다.
### P1
#### P1-1. PR/Phase invariant regression pack 추가
Proposal:
정적 테스트 하나로 PR 1-5 + Phase 5 계약을 자동 점검한다.
Classification:
`[검증됨]`
기존 Backlog 와의 관계:
`기존 Backlog 확장`.
`docs/orca_v2_backlog.md:56-73`의 `P5. Redesign GitHub Actions`에 붙는 검증 자동화 축이다.
PR 1~5 계약 영향 여부:
계약을 바꾸지 않고, 계약 drift를 막는다.
추정 구현 복잡도:
`low`
긴급도:
`P1`
Why now:
현재 계약은 코드와 문서에 존재하지만, 자동 회귀 체크가 없다.
future refactor에서 가장 먼저 깨질 가능성이 있는 것도 이 invariants다.
Evidence:
`orca/learning_policy.py:6-19`,
`orca/main.py:1-48`,
`orca/analysis.py:428-435`,
`orca/state.py:93-132`,
`.github/workflows/orca_daily.yml:141-160`,
`.github/workflows/orca_jackal.yml:110-127`.
#### P1-2. workflow state-preservation smoke check 추가
Proposal:
4개 stateful workflow의 save step에서
`checkpoint_jackal_db()`,
`git add -f data/jackal_state.db`,
`concurrency group`
이 유지되는지 정적으로 확인하는 smoke check를 만든다.
Classification:
`[검증됨]`
기존 Backlog 와의 관계:
`기존 Backlog 확장`.
`P5. Redesign GitHub Actions`의 하위 검증 항목으로 보는 것이 맞다 (`docs/orca_v2_backlog.md:66-73`).
PR 1~5 계약 영향 여부:
계약 보존용.
특히 Phase 5 workflow contract를 강화한다.
추정 구현 복잡도:
`low`
긴급도:
`P1`
Why now:
현재 네 workflow가 모두 맞게 구성돼 있지만, 이를 보장하는 guardrail이 없다.
Evidence:
`.github/workflows/orca_daily.yml:141-160`,
`.github/workflows/jackal_tracker.yml:80-98`,
`.github/workflows/jackal_scanner.yml:64-74`,
`.github/workflows/orca_jackal.yml:110-127`.
#### P1-3. dual-DB 상태 스냅샷을 report/dashboard에 노출
Proposal:
daily report 또는 research comparison에
`orca_state.db` / `jackal_state.db` 각각의
object count,
핵심 table count,
latest mtime 정도를 read-only snapshot으로 추가한다.
Classification:
`[검증됨]`
기존 Backlog 와의 관계:
`기존 Backlog 확장`.
`P4. Build The Evaluation Spine` 및 week 4+ `dashboard observability 확장`의 구체화다 (`docs/orca_v2_backlog.md:50-64`, `docs/orca_v2_backlog.md:216-220`).
PR 1~5 계약 영향 여부:
새 health code를 추가하지 않는 한 계약 비침해.
기존 `failed_sources` / `data_quality` 구조도 유지 가능하다.
추정 구현 복잡도:
`medium`
긴급도:
`P1`
Why now:
현재 comparison report가 `state_db` 단수 필드만 가지며, dual-DB cutover 이후 provenance가 불완전하다.
Evidence:
`orca/research_report.py:291-325`,
`orca/research_report.py:343-347`,
`reports/orca_research_comparison.json:1-4`,
runtime sqlite query on current `data/orca_state.db` and `data/jackal_state.db`.
#### P1-4. degraded/failure path 전용 테스트 보강
Proposal:
`run_orca_cycle()`의 `poor/degraded` branch,
`persist.record_predictions()` state failure branch,
Phase 5 cross-DB best-effort branch를 전용 테스트로 고정한다.
Classification:
`[검증됨]`
기존 Backlog 와의 관계:
`신규`.
PR 1~5 계약 영향 여부:
계약 보존용.
특히 PR 1, PR 5, Phase 5 best-effort semantics를 안정화한다.
추정 구현 복잡도:
`medium`
긴급도:
`P1`
Why now:
가장 중요한 운영 정책은 정상 happy path보다 degraded path에 있다.
그런데 현재 테스트는 이 경로를 직접 덮지 않는다.
Evidence:
`orca/run_cycle.py:248-286`,
`orca/persist.py:96-109`,
`orca/state.py:1227-1243`,
`orca/state.py:1352-1367`,
`orca/state.py:1540-1555`.
### P2
#### P2-1. ORCA 내부 import cycle 제거
Proposal:
`analysis -> data -> notify -> analysis` cycle을 끊기 위해
notification interface 또는 lessons/data helper를 작은 boundary module로 뽑는다.
Classification:
`[검증됨]`
기존 Backlog 와의 관계:
`신규`.
PR 1~5 계약 영향 여부:
계약 비침해.
기능/threshold/DB ownership을 바꾸지 않아도 된다.
추정 구현 복잡도:
`medium`
긴급도:
`P2`
Why now:
현재 cycle은 local import로 완화돼 있지만, 구조 인지 비용과 테스트 비용을 계속 올린다.
Evidence:
`orca/analysis.py:1478`,
`orca/data.py:616`,
`orca/notify.py:353`.
#### P2-2. `orca/analysis.py`를 기능별 submodule로 분리
Proposal:
`candidate review`,
`verification`,
`lessons/pattern db`
를 분리해 `analysis.py`의 책임 폭을 줄인다.
Classification:
`[검증됨]`
기존 Backlog 와의 관계:
`신규`.
PR 1~5 계약 영향 여부:
review weights, learning policy, verification behavior를 유지하는 방식으로만 수행해야 한다.
즉, behavior-preserving refactor 전제다.
추정 구현 복잡도:
`high`
긴급도:
`P2`
Why now:
현재 `analysis.py`는 설계상 서로 다른 test seam을 가진 기능을 너무 많이 묶고 있다.
Evidence:
`orca/analysis.py:151-361`,
`orca/analysis.py:664-871`,
`orca/analysis.py:1139-1346`,
`orca/analysis.py:1353-1717`.
#### P2-3. `jackal/scanner.py` deterministic quality engine 추출
Proposal:
`_calc_signal_quality()`,
family classifier,
pre-rule signal generation,
final judgment를 pure rule module로 추출하고,
scanner 본체는 watchlist/IO/orchestration 중심으로 줄인다.
Classification:
`[검증됨]`
기존 Backlog 와의 관계:
`신규`.
PR 1~5 계약 영향 여부:
quality score 값과 family threshold가 바뀌지 않는 리팩터링이어야 한다.
즉, threshold freeze를 전제로 한다.
추정 구현 복잡도:
`high`
긴급도:
`P2`
Why now:
현재 scanner는 deterministic rule path와 LLM/IO path가 한 파일에 섞여 있어 테스트가 어렵다.
Evidence:
`jackal/scanner.py:515-865`,
`jackal/scanner.py:1058-1122`,
`jackal/scanner.py:1649-1986`.
#### P2-4. `_connect` / `_connect_orca` naming normalization
Proposal:
`orca/state.py` 내부에서 ORCA/shared path가 `_connect_orca()`를 직접 사용하도록 정리하고,
`_connect()`는 compatibility wrapper 또는 deprecated alias로 명시한다.
Classification:
`[검증됨]`
기존 Backlog 와의 관계:
`신규`.
PR 1~5 계약 영향 여부:
Path B table ownership이나 DB split 결정을 바꾸지 않는 선에서만 가능하다.
즉, adapter split이 아니라 naming/intent cleanup이어야 한다.
추정 구현 복잡도:
`low`
긴급도:
`P2`
Why now:
현재 dual-DB routing은 맞지만 ORCA-side naming이 중간 상태라 코드 읽기가 불필요하게 혼란스럽다.
Evidence:
`orca/state.py:83-101`,
`orca/state.py:519`,
`orca/state.py:541`,
`orca/state.py:670`,
`orca/state.py:2637`,
`orca/state.py:3225`.
### P3
#### P3-1. deterministic threshold registry 도입
Proposal:
Hunter/Scanner의 inline numeric thresholds를 선언형 constant map 또는 registry로 끌어올린다.
값 변경은 하지 않고 위치만 정리한다.
Classification:
`[검증됨]`
기존 Backlog 와의 관계:
`기존 Backlog 확장`.
`P2. Harden Agent Contracts`의 “계약을 코드 형태로 명시”하는 축에 가깝다 (`docs/orca_v2_backlog.md:25-36`).
PR 1~5 계약 영향 여부:
review weights, learning policy, external data visibility와 충돌하지 않는다.
단, threshold 수치 drift가 없다는 테스트가 선행돼야 한다.
추정 구현 복잡도:
`medium`
긴급도:
`P3`
Why now:
현재 threshold는 inline lambda/body 안에 흩어져 있어 audit diff와 tests 작성이 어렵다.
Evidence:
`jackal/hunter.py:406-447`,
`jackal/hunter.py:620-692`,
`jackal/hunter.py:1194-1206`,
`jackal/scanner.py:541-865`,
`orca/research_gate.py:20-25`.
#### P3-2. external dependency test fixture layer 도입
Proposal:
time/env/filesystem/sqlite/network를 공통으로 stub하는 test fixture helper를 도입해
`run_cycle`, `hunter`, `scanner`, `evolution`, workflow smoke tests의 setup 비용을 줄인다.
Classification:
`[검증됨]`
기존 Backlog 와의 관계:
`신규`.
PR 1~5 계약 영향 여부:
계약 비침해.
테스트 기반만 개선한다.
추정 구현 복잡도:
`medium`
긴급도:
`P3`
Why now:
현재 중요한 모듈이 모두 `time + env + filesystem + network`를 동시에 건드려, 테스트 추가 비용이 높다.
Evidence:
`orca/run_cycle.py:141-438`,
`jackal/hunter.py:1495-1665`,
`jackal/scanner.py:1649-1986`,
`jackal/evolution.py:159-1011`,
Section 3.5 monkeypatch surface.
#### P3-3. module size / cycle budget static checker 추가
Proposal:
새 PR이 import cycle을 추가하거나 특정 파일 size budget을 넘길 때 경고/실패시키는 static checker를 둔다.
Classification:
`[검증됨]`
기존 Backlog 와의 관계:
`신규`.
PR 1~5 계약 영향 여부:
계약 비침해.
구조 drift 억제용이다.
추정 구현 복잡도:
`low`
긴급도:
`P3`
Why now:
현재 top 5 파일이 production code의 55.3%를 차지하고, ORCA 내부 cycle도 이미 하나 존재한다.
Evidence:
Section 2 LOC distribution,
Section 3.2 import graph,
`orca/analysis.py:1478`,
`orca/data.py:616`,
`orca/notify.py:353`.
---
## Section 7: Known Limitations of This Review
- 이 문서는 정적 코드 분석 기반이다.
  실제 scheduled run replay, network latency, live API payload variability는 재현하지 않았다.
- 런타임 behavior 검증은 제한적이다.
  수행한 자동 검증은 `unittest`와 `compileall`, 현재 DB/query 스냅샷 정도다.
- 시장 데이터 / 외부 API 응답 실물은 재검증하지 않았다.
  따라서 data provider freshness, rate limit behavior, 실제 fill quality는 본 문서 범위 밖이다.
- Git CLI가 현재 셸에서 사용 불가해, 브랜치/커밋 확인은 `.git/HEAD`와 `.git/refs/heads/main` 직접 조회로 대체했다.
- coverage percentage는 산출하지 않았다.
  `tests/` 디렉터리 구조와 실제 실행 성공 여부만 확인했다.
- current DB snapshot은 다음 scheduled run 이후 달라질 수 있다.
  특히 JACKAL learning tables의 `COUNT = 0` 관측은 “현재 시점 스냅샷”이지 영구 상태 보증이 아니다.
- Phase 5 결과물의 실환경 검증은 아직 미완료다.
  `docs/phase5/02-path-decision.md:90-97`가 요구한 `scheduled run 후 COUNT > 0` 증명은 현재 문서 시점에 완전히 닫히지 않았다.
- Phase 6 진입 후 이 문서는 재검토가 필요하다.
  특히 candidate/shared adapter 경계와 factor backlog가 실제로 움직이기 시작하면 Section 3-6의 우선순위가 달라질 수 있다.
---
## Section 8: Phase 6 Input Summary
- Section 6의 `P1` 제안은 Phase 6 초기의 “안전한 구조/검증” 작업 후보로 적합하다.
  특히
  invariant regression pack,
  workflow smoke check,
  dual-DB state snapshot,
  failure-path tests
  는 현재 contracts를 건드리지 않으면서 즉시 가치가 있다.
- Section 5의 technical debt는 Phase 6 mid-term 설계 입력으로 보는 것이 적절하다.
  특히
  shared adapter concentration,
  candidate registry cross-DB fan-in,
  ORCA internal import cycle,
  workflow shell hotfix complexity,
  dual-DB provenance gap
  이 핵심이다.
- existing backlog와 직접 중복되는 항목은 본 문서에서 재제안하지 않았다.
  유지 대상:
  `docs/orca_v2_backlog.md:95-164`의 Phase 6 factor 후보,
  `docs/orca_v2_backlog.md:233-300`의 deferred improvements.
- 사용자가 backlog에 새로 옮길 수 있는 “비중복 구조 항목” 후보는 아래 정도다.
  `PR/Phase invariant regression pack`,
  `workflow state-preservation smoke check`,
  `dual-DB state snapshot observability`,
  `failure-path tests`,
  `ORCA import cycle break`,
  `scanner quality engine extraction`,
  `_connect/_connect_orca naming normalization`,
  `module size/cycle budget checker`.
- 반대로 backlog에 새로 넣지 말아야 할 항목은 아래다.
  `portfolio construction`,
  `regime-adaptive thresholds`,
  `do not trade layer`,
  신규 factor 제안,
  candidate spine redesign 재제안,
  repo-wide BOM cleanup 재제안.
  이유: 사용자 제약 및 기존 backlog/deferred item과 충돌한다.
- 결론:
  현재 repo는 Phase 5 계약을 보존한 상태로 동작하고 있다.
  다음 단계의 가장 안전한 진입점은
  “계약을 자동으로 지키게 만드는 테스트/관측/구조 정리”
  이지,
  새로운 투자 아이디어를 추가하는 것이 아니다.
