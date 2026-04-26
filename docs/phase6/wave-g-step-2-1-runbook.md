# Wave G STEP 2-1 Runbook: Unified Market Fetch Wrapper

## Purpose

Wave G migrates ORCA/JACKAL market data access away from direct yfinance calls
and toward a unified fallback chain.

STEP 2-1 only adds the shared wrapper module. It does not migrate existing
callers yet.

## New Module

`orca/market_fetch.py` is the public entry point for daily OHLCV access.

Public API:

- `fetch_daily_history(ticker, start, end, use_fallback=None)`
- `fetch_daily_history_batch(tickers, start, end, use_fallback=None)`
- `fetch_latest_close(ticker, lookback_days=7, use_fallback=None)`
- `get_fetch_stats()`
- `reset_fetch_stats()`

## Feature Flag

`USE_UNIFIED_FETCH` controls the default path when `use_fallback=None`.

- unset or `1`: unified fallback enabled
- `0`, `false`, `no`, `off`: direct yfinance rollback mode

Explicit function arguments override the environment.

```python
from orca.market_fetch import fetch_daily_history

# Uses USE_UNIFIED_FETCH
df = fetch_daily_history("AAPL", "2026-04-01", "2026-04-20")

# Force unified fallback
df = fetch_daily_history("AAPL", "2026-04-01", "2026-04-20", use_fallback=True)

# Force direct yfinance rollback path
df = fetch_daily_history("AAPL", "2026-04-01", "2026-04-20", use_fallback=False)
```

## Provider Cascade

Unified mode delegates to the existing Wave F provider chain:

```text
yfinance ticker retry -> Alpha Vantage fallback -> failed
```

Batch wrapper behavior:

- Unified mode loops per ticker so each ticker can fall back independently.
- Direct mode uses yfinance batch download.

## Source Tracking

The wrapper tracks in-process source counts:

```python
from orca.market_fetch import get_fetch_stats, reset_fetch_stats

reset_fetch_stats()
# run fetches
print(get_fetch_stats())
```

Example:

```python
{
    "yfinance_batch_success": 10,
    "yfinance_ticker_success": 2,
    "alpha_vantage_success": 3,
    "failed": 1,
    "total": 16,
}
```

## Rollback

Set:

```bash
USE_UNIFIED_FETCH=0
```

This keeps migrated callers on direct yfinance behavior without reverting code.

## STEP 2-1 Scope

Added:

- `orca/market_fetch.py`
- `tests/test_market_fetch.py`
- this runbook

Not changed:

- `orca/data.py`
- `orca/backtest.py`
- `orca/context_snapshot.py`
- `jackal/backtest.py`
- `jackal/tracker.py`
- `jackal/hunter.py`
- `jackal/market_data.py`
- `jackal/scanner.py`
- `jackal/evolution.py`

## Next Steps

STEP 2-2 should migrate the lowest-risk daily OHLCV consumers first:

- `jackal/backtest.py`
- `jackal/tracker.py`
- `jackal/market_data.py`

STEP 2-3 can then migrate heavier scan/backtest paths:

- `jackal/hunter.py`
- `orca/backtest.py`
- `orca/context_snapshot.py`

STEP 2-4 should handle quote/options-specific paths:

- `orca/data.py`
- put/call ratio collection

## Troubleshooting

If yfinance is rate-limited:

- In unified mode, Alpha Vantage should be attempted automatically.
- Check `get_fetch_stats()` for `alpha_vantage_success`.

If Alpha Vantage fails:

- Confirm `ALPHA_VANTAGE_API_KEY` is configured in the runtime environment.
- Confirm the ticker is supported by Alpha Vantage.
- Use `USE_UNIFIED_FETCH=0` for temporary direct-yfinance rollback.

If both providers fail:

- The wrapper returns `None` or omits that ticker from batch results.
- Callers should treat missing data as a degraded but non-crashing path.
