# Wave G STEP 2-4 Runbook: ORCA Data + Context Snapshot Migration

## 목적

Wave G STEP 2-4 는 ORCA 의 마지막 daily market-data 경로를 unified fallback 체계로 옮긴다.

- `orca/context_snapshot.py::_fetch_history_points()` 는 `orca.market_fetch.fetch_daily_history()` 를 사용한다.
- `orca/data.py::_fetch_one()` 은 Yahoo chart HTTP 를 primary 로 유지하고, 실패 시 `fetch_latest_close()` 로 fallback 한다.
- `orca/data.py::fetch_put_call_ratio()` 는 `orca.market_fetch` 의 options-only wrapper 로 위임한다.
- `orca/context_snapshot.py` 와 `orca/data.py` 에는 `yfinance` import 및 `yf.*` 직접 호출이 남지 않는다.

## Hybrid Quote Policy

`_fetch_one()` 은 ORCA Daily 의 현재가 성격을 최대한 보존하기 위해 Yahoo chart HTTP 를 먼저 호출한다.

1. Yahoo chart 성공: 기존과 동일하게 가격 문자열과 변화율 문자열을 반환한다.
2. Yahoo chart 실패: `USE_UNIFIED_FETCH` 가 켜져 있으면 `market_fetch.fetch_latest_close()` 를 호출한다.
3. fallback 도 실패: 기존처럼 `("N/A", "")` 를 반환한다.

`USE_UNIFIED_FETCH=0` 으로 설정하면 Yahoo chart 실패 후 unified fallback 을 사용하지 않는다.

## Context Snapshot Impact

Phase 1.2 live hook 이 새 lesson 을 기록할 때 `get_or_create_context_snapshot()` 을 호출한다. 이때 VIX, S&P 500, NASDAQ, sector ETF history 는 더 이상 `yf.Ticker().history()` 를 직접 호출하지 않고 `market_fetch.fetch_daily_history()` 로 수집된다.

첫 lesson/date 에서는 market fetch latency 가 있을 수 있지만, 같은 trading date 의 이후 lesson 은 기존 snapshot 을 재사용한다.

## Put/Call Ratio Policy

Put/Call ratio 는 option chain 데이터가 필요하므로 Alpha Vantage daily OHLCV fallback 으로 대체할 수 없다.

- `market_fetch.fetch_put_call_ratio()` 는 단일 ticker/expiry 의 option PCR 을 yfinance 로 가져온다.
- `market_fetch.fetch_put_call_ratio_summary()` 는 기존 ORCA 형식인 `pcr_spy`, `pcr_qqq`, `pcr_avg`, `pcr_signal` 을 반환한다.
- 실패 시 예외를 전파하지 않고 `None` 또는 `N/A` summary 로 degrade 한다.

미래에 Polygon Options 를 도입하면 이 wrapper 내부에 polygon path 만 추가하면 된다.

## Environment

- `USE_UNIFIED_FETCH=1`: 기본값. Yahoo chart 실패 또는 daily history fetch 에 unified fallback 사용.
- `USE_UNIFIED_FETCH=0`: rollback. `data.py` quote fallback 을 비활성화하고 `market_fetch` 는 direct yfinance path 를 사용.
- `ALPHA_VANTAGE_API_KEY`: unified fallback 의 Alpha Vantage key.
- `ALPHA_VANTAGE_SLEEP_SECONDS`: Standard tier 는 `0.8`, free tier 는 기본 `12.0`.

## Verification

권장 검증:

```powershell
python -m py_compile orca\market_fetch.py orca\context_snapshot.py orca\data.py
python -m unittest tests.test_wave_g_step_2_4_migration
python -m unittest discover -s tests
Select-String -Path orca\context_snapshot.py,orca\data.py -Pattern "import yfinance|yf\.|yf ="
```

마지막 명령은 출력이 없어야 한다.

## Rollback

운영 중 문제가 생기면 먼저 환경변수로 rollback 한다.

```powershell
$env:USE_UNIFIED_FETCH="0"
```

이렇게 하면 ORCA quote fallback 은 비활성화되고, `market_fetch` daily path 는 direct yfinance path 로 돌아간다. 코드 수준 rollback 이 필요하면 Wave G STEP 2-4 commit 을 revert 한다.

## Wave G Status

- STEP 2-1: `orca/market_fetch.py` wrapper
- STEP 2-2: JACKAL backtest/tracker/market_data
- STEP 2-3: Hunter + ORCA backtest + Alpha Vantage pacing
- STEP 2-4: ORCA context_snapshot + data + PCR wrapper

이 단계 후 daily OHLCV fetch 는 unified fallback 을 통과한다. PCR 은 options-only wrapper 로 격리되어 있으며, yfinance 의존성이 명시적으로 한 곳에 모인다.
