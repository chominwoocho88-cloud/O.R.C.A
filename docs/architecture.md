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

- ✅ shared/ 골격 생성 (이번 commit)
- ✅ docs/architecture.md 비전 명문화 (이번 commit)
- 🔄 LLMClient는 orca/llm_client.py에 있음 (다음 단계에서 shared/llm/로 이동 예정)
- 🔄 KIS API client는 미구현 (KIS 가입 후 shared/broker/kis.py로 신규 생성 예정)
- ⏸️ orca/, jackal/ 코드는 모두 기존 위치 유지
- ⏸️ modules/, integrations/, tools/ 폴더는 미생성 (필요 시점에 만듦)

## 다음 단계 후보

1. JACKAL LLMClient 통합 (5월 1번 작업 마무리)
2. shared/llm/ 실제 분리 (orca/llm_client.py → shared/llm/client.py)
3. shared/broker/kis.py 신규 작성 (KIS API 가입 완료 후)
4. 비용 가시성 대시보드 (data/llm_log.jsonl 분석)
