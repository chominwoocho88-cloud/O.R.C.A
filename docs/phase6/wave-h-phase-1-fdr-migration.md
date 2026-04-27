# Wave H Phase 1 - FinanceDataReader Main Fetch Buffer

## Purpose

Wave H temporarily promotes FinanceDataReader (FDR) to the primary daily OHLCV
provider for ORCA/JACKAL. The goal is to stabilize Korean and US market fetches
while Korean ISP SSL/yfinance failures are frequent and before KIS Developers API
access is available.

## Provider Priority

With `USE_FDR_MAIN=1`:

1. FinanceDataReader
2. Alpha Vantage for non-Korean tickers
3. yfinance as the final backup

With `USE_FDR_MAIN=0`, ORCA/JACKAL immediately roll back to the previous Wave G
path:

1. yfinance
2. Alpha Vantage fallback

The public caller API is unchanged. Existing calls to
`fetch_daily_history()`, `fetch_daily_history_batch()`, and
`fetch_latest_close()` continue to work.

## Ticker Mapping

| yfinance style | FDR symbol | Notes |
| --- | --- | --- |
| `005930.KS` | `005930` | Korean stock/ETF |
| `005930.KQ` | `005930` | KOSDAQ stock |
| `NVDA` | `NVDA` | US stock |
| `^VIX` | `VIX` | Volatility index |
| `^GSPC` | `US500` | S&P 500 proxy |
| `^IXIC` | `IXIC` | NASDAQ |
| `^KS11` | `KS11` | KOSPI |
| `USDKRW=X` | `USD/KRW` | FX |
| `KRW=X` | `USD/KRW` | FX |
| `^TNX` | unsupported | AV/yfinance fallback |
| `^IRX` | unsupported | AV/yfinance fallback |

## Files

- `orca/fdr_fetch.py`: FDR adapter, ticker conversion, normalization.
- `orca/market_fetch.py`: provider priority orchestration and source stats.
- `requirements.txt`: adds `finance-datareader>=0.9.110`.
- Workflows: `USE_FDR_MAIN=1` enabled for ORCA/JACKAL/Wave F jobs.

## Rollback

Set:

```bash
USE_FDR_MAIN=0
```

No code change is needed. This restores the previous Wave G behavior while
keeping Alpha Vantage and yfinance fallback intact.

## KIS Compatibility

When KIS Developers API is available, add a `kis_fetch.py` adapter and place it
before FDR:

1. KIS
2. FDR
3. Alpha Vantage
4. yfinance

FDR remains the Korean fallback and AV remains the US fallback.

## Validation

Recommended checks:

```bash
python -m unittest tests.test_fdr_integration tests.test_market_fetch
python -m unittest discover tests
```

Optional real FDR smoke tests:

```bash
RUN_REAL_FDR_TESTS=1 python -m unittest tests.test_fdr_integration.RealFDRSmokeTests
```

