# modules/jackal/

종목 발굴 모듈 (자기 완결).

## 책임
- 신규 후보 발굴 (Hunter)
- watchlist/recommendation 재평가 (Scanner)
- outcome 추적과 learning (Tracker, Evolution)
- 분 단위 fresh 데이터로 시장 변동성 판단 (Stage 2)

## 입력
- data/morning_baseline.json: ORCA baseline
- data/memory.json: ORCA fallback context
- shared.market_data: 정적 시장 데이터
- shared.broker.kis: KIS API 실시간 데이터 (Stage 2)
- data/jackal_state.db: 학습 상태

## 출력
- data/jackal_watchlist.json
- data/jackal_news.json (ORCA 사이드와 공유)
- data/jackal_state.db: 후보/결과/가중치

## 현재 상태 (Day 5)
- 빈 폴더. 실제 코드는 jackal/ 에 있음.
- Day 9에 코드 이동 예정.

## 마이그레이션 순서 (계획)
1. modules/jackal/pipeline/ - core, hunter, scanner, compact, evolution, tracker (Day 9)
2. modules/jackal/realtime/ - 분 단위 KIS fetch (Stage 2, Day 14)
3. modules/jackal/flows/ - 수급 분석 (Stage 3)
