# shared/market_data/

시장 데이터 수집 어댑터.

## 모듈
- fetch.py — yfinance + AlphaVantage fallback chain (Day 6에 이동)
- (미래) macros.py — FRED 등 거시지표
- (미래) korea.py — KIS 한국 시장 (Stage 2)

## 사용

```python
from shared.market_data.fetch import fetch_daily_history

df = fetch_daily_history("AAPL", "2026-04-01", "2026-05-01")
```

## 의존성 방향

shared.market_data <- modules.orca, modules.jackal (둘 다 의존 가능)
