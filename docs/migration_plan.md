# O.R.C.A modules/ 마이그레이션 계획

## 배경

- 현재 orca/, jackal/ 평평한 구조 (orca/ 18 파일, jackal/ 10 파일)
- Strangler Fig 패턴으로 점진 이동
- modules/ vertical slice 구조로 진화

## 진단 결과 요약 (Day 5 시점)

### 주요 강결합 지점
1. orca/state.py (4,069줄) — ORCA + JACKAL DB 동시 소유
2. orca/market_fetch.py — JACKAL이 직접 import (단방향 의존성 위배)
3. data/*.json 4개 파일 — 모듈 간 인터페이스 (스키마 contract 없음)

### 외부 의존성
- yfinance, FRED, AlphaVantage (정적)
- KRX (한국 시세, 401 에러 만성)
- KIS API (Stage 2에서 추가)

## Stage별 계획

### Stage 1: 기반 구조 (Day 5~10) — 1주

- Day 5: modules/ 빈 골격 + 본 문서 (이번 commit)
- ✅ Day 6: shared/market_data/ 분리 — orca.market_fetch 이동, alias 유지
- ✅ Day 7: modules/orca/pipeline/ 분리 — pipeline.py(46줄)만 이동, alias 유지
  - Day 7 안전 버전: agents.py, run_cycle.py는 별도 sprint에서 이동
- ✅ Day 8: modules/orca/pipeline/agents.py 분리 — 4-agent LLM 정의 이동, alias 유지
  - Day 7-8 학습: alias는 module 객체 wildcard re-export 패턴 필요 (mock.patch 호환성)
- Day 8 후속: modules/orca/lessons/ + state.py 분리 검토 (lessons 먼저)
- Day 9: modules/jackal/pipeline/ 분리
- Day 10: 검증 + 운영 안정성

### Stage 2: KIS + 분 단위 데이터 (Day 11~17) — 1주

- Day 11: shared/broker/kis.py 신규 (KIS_CMW_*_PAPER 사용)
- Day 12: KIS 시세/지수 fetch + yfinance fallback chain
- Day 13: KIS 외인/기관 수급 데이터
- Day 14: modules/jackal/realtime/ 신규 — 분 단위 fetch
- Day 15: JACKAL이 자체 시점 fresh 데이터로 판단
- Day 16-17: 운영 검증 + 안정화

### Stage 3: 신규 기능 (Day 18+) — 2-3주

- 실적발표 추적: modules/orca/events/earnings.py
- 급등락 패턴: modules/orca/events/patterns.py
- 수급 분석: modules/jackal/flows/
- Regime + 심리 강화: modules/orca/regime/, sentiment/
- 다중 계좌: modules/portfolio/accounts/
- Phase 4 self-correction (기존 미완)

## 마이그레이션 원칙

1. **Strangler Fig 패턴**
   - 옛 위치는 alias로 유지
   - 새 위치에 코드 이동
   - 호출부 점진 마이그레이션
   - alias 제거는 모든 호출이 새 위치 사용 후

2. **단방향 의존성**
   - shared <- modules
   - modules 끼리 직접 import 금지
   - 데이터 교환은 JSON contract 또는 integrations/

3. **각 commit 작게**
   - 한 번에 한 모듈/한 레이어만
   - 매 commit 검증 (compile + tests + import + alias)
   - 운영 회귀 발견 시 즉시 stop

4. **운영 우선**
   - 자동 cycle 빨간색 발생 시 다음 작업 보류
   - GitHub Actions 결과로 매 commit 검증

## 주요 위험과 대응

### 위험 1: state.py 4,069줄 분리

대응:
- 한 번에 분리 X
- ORCA-only 함수와 JACKAL-only 함수 grep으로 식별
- shared/db/ 에 두 DB 어댑터 만든 뒤 점진 이동
- 가장 마지막에 처리 (Day 8 또는 Stage 1 종료 후)

### 위험 2: import 경로 대량 변경

대응:
- alias로 옛 경로 유지
- import 경로 변경은 별도 commit으로 분리
- 한 번에 한 모듈만

### 위험 3: GitHub Actions 워크플로 깨짐

대응:
- python -m orca.main 같은 진입점 경로 변경 시 yml도 같이 수정
- yml 변경은 같은 commit에 포함
- 자동 cycle 결과 모니터링 필수

## 검증 체크리스트 (매 commit)

- [ ] python -m compileall -q orca jackal shared modules
- [ ] python -m unittest discover -s tests > t.txt 2>&1; tail -5 t.txt
- [ ] 옛 경로 import 가능 (alias 작동)
- [ ] 새 경로 import 가능
- [ ] 다음 자동 cycle 빨간색 아닌지 (push 후)
- [ ] data/llm_log.jsonl 정상 기록 (push 후)
