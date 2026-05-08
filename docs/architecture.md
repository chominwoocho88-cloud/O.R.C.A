# O.R.C.A 아키텍처

## 비전

O.R.C.A는 개인 트레이딩 봇 플랫폼이다. 시장 분석부터 종목 발굴, 포트폴리오 관리까지 전 단계를 다룬다.

## 3단계 파이프라인

```
[ORCA] 시장 분석
   ↓ (시그널)
[JACKAL] 종목 발굴
   ↓ (후보 + 강도)
[PORTFOLIO] 계좌별 포지션/주문 관리
```

## 디렉토리 구조 (목표)

```
O.R.C.A/
├─ shared/              # 공유 인프라 (모든 모듈이 의존 가능)
│  ├─ llm/              # LLM 클라이언트 + prompt 관리
│  ├─ market_data/      # yfinance, FRED, AlphaVantage
│  ├─ broker/           # KIS, 키움 등 증권사 API
│  ├─ db/               # SQLite wrapper
│  └─ logging/          # JSONL, 메트릭
│
├─ modules/             # 비즈니스 모듈 (vertical slices)
│  ├─ orca/             # 시장 분석 (자기 완결)
│  │  ├─ pipeline/
│  │  ├─ regime/
│  │  ├─ sentiment/
│  │  ├─ events/        # 실적발표, 급등락 패턴
│  │  ├─ lessons/
│  │  ├─ state/
│  │  ├─ workflows/
│  │  ├─ tests/
│  │  ├─ docs/
│  │  └─ README.md
│  │
│  ├─ jackal/           # 종목 발굴 (자기 완결)
│  │  ├─ pipeline/
│  │  ├─ scanner/
│  │  ├─ tracker/
│  │  ├─ flows/         # 수급 분석
│  │  ├─ state/
│  │  ├─ workflows/
│  │  ├─ tests/
│  │  ├─ docs/
│  │  └─ README.md
│  │
│  └─ portfolio/        # 포트폴리오 관리 (NEW)
│     ├─ accounts/      # 계좌별 격리
│     ├─ positions/
│     ├─ orders/
│     ├─ workflows/
│     ├─ tests/
│     └─ README.md
│
├─ integrations/        # 모듈 간 연결 (단방향)
├─ tools/               # CLI 진입점
├─ docs/                # repo 전체 문서
├─ data/                # 운영 데이터 (대부분 gitignore)
└─ .github/workflows/   # 통합 워크플로
```

## 핵심 원칙

1. **자기 완결성**: 각 모듈 폴더 안에 그 모듈에 필요한 모든 것 (코드/테스트/문서/워크플로).
2. **단방향 의존성**: shared ← modules ← integrations. 모듈 간 직접 import 금지.
3. **shared 엄격 관리**: 2개 이상 모듈이 실제로 쓰는 것만 shared.
4. **integrations는 얇음**: 데이터 변환 + 호출만. 비즈니스 로직 X.
5. **각 모듈 README.md가 시작점**: 그 모듈 이해의 진입점.

## 마이그레이션 전략

Strangler Fig 패턴을 따른다.

- 기존 orca/, jackal/ 코드는 그대로 유지
- 신규 코드만 새 구조 (shared/, modules/) 에 추가
- 점진적으로 옛 코드를 새 위치로 이동
- 각 이동마다 alias 유지로 import 경로 호환
- 옛 위치 폐기는 모든 import가 새 위치를 가리킬 때

## 현재 상태 (2026-05-07)

- shared/ 골격 생성 (이번 commit)
- docs/architecture.md 비전 명문화 (이번 commit)
- LLMClient는 shared/llm/client.py에 있음 (Day 4에 호출부 마이그레이션 완료). 모든 호출부가 shared.llm.client 직접 사용. orca/llm_client.py alias는 외부 호환성 위해 유지.
- modules/ 빈 골격 생성 (Day 5). 코드 이동은 Day 6~10에 점진적.
- Day 6: shared/market_data/ 분리 완료. orca.market_fetch alias 유지. JACKAL 단방향 의존성 회복.
- Day 7: pipeline.py를 modules/orca/pipeline/로 이동 (alias 유지). 작은 파일로 modules/ 이동 패턴 첫 검증.
- Day 8: agents.py 이동 (modules/orca/pipeline/agents.py). mock.patch 호환성 패턴 적용.
- Day 9: run_cycle.py 이동. Stage 1 핵심 ORCA pipeline 3 파일 (pipeline + agents + run_cycle) 모두 modules/orca/pipeline/ 입주 완료.
- Day 10 안전 게이트 발동: JACKAL Path(__file__) 패턴 발견으로 modules/jackal/pipeline 이동 보류.
- Phase A 진단 완료: 경로 의존성 전수 조사.
- Day 11 Phase B-1: shared/paths.py 신규 작성. 기존 코드 영향 0.
- Day 12 Phase B-2: orca/paths.py가 shared.paths의 alias. 호출부 영향 0.
- Day 13 Phase B-3: jackal 첫 3개 파일(adapter, shield, compact)이 shared.paths 사용. JACKAL legacy 데이터 위치 그대로.
- Phase B-3.5: 텔레그램 메시지 짤림 수정 + build 표시 추가. 운영 가시성 향상.
- Phase B-3.5b: JACKAL 텔레그램에도 build 표시. 운영 가시성 ORCA + JACKAL 통합 완성.
- Phase B-4: jackal/{evolution, tracker, scanner, hunter} 경로 shared.paths 통합 완료. 운영 데이터 위치는 그대로 유지.
- Phase B-5: jackal/{core, backtest} 경로 shared.paths 통합 완료. Stage 1 경로 의존성 제거는 Phase D만 남음.
- 마이그레이션 계획: docs/migration_plan.md 참조
- KIS API client는 미구현 (KIS 가입 완료, 다음 단계에서 shared/broker/kis.py로 신규 생성 예정)
- orca/, jackal/ 코드는 모두 기존 위치 유지
- integrations/, tools/ 폴더는 미생성 (필요 시점에 만듦)

## 다음 단계 후보

1. shared/llm/ 실제 분리 (완료 - Day 3)
2. 호출부 점진 마이그레이션 (완료 - Day 4)
3. modules/ 빈 골격 (완료 - Day 5)
4. shared/market_data/ 분리 (완료 - Day 6)
5. modules/orca/pipeline/pipeline.py 이동 (완료 - Day 7)
6. modules/orca/pipeline/agents.py 이동 (완료 - Day 8)
7. modules/orca/pipeline/run_cycle.py 이동 (완료 - Day 9)
8. shared/paths.py 도입 및 orca/paths.py alias 변환 (완료 - Phase B-1/B-2)
9. JACKAL 경로 상수 교체 (완료 - Phase B-3~B-5)
10. modules/jackal/pipeline/ 분리 재시도 (Phase D)
