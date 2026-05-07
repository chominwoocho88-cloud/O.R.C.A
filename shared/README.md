# shared/

모든 모듈이 의존할 수 있는 공유 인프라.

## 원칙

- 비즈니스 로직 없음. 인프라만.
- 2개 이상 모듈이 실제로 쓰는 것만 여기 둔다.
- "언젠가 쓸 것 같아서" 미리 추가 금지.

## 구조

- llm/         LLM 클라이언트 + prompt 관리 (활성)
- market_data/ 시장 데이터 수집기 (yfinance, FRED 등)
- broker/      증권사 API (KIS, 키움 등)
- db/          SQLite wrapper
- logging/     JSONL, 메트릭
- paths.py     중앙 경로 관리 (활성)
