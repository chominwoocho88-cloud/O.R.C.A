# Wave G STEP 2-2 Runbook: JACKAL Market Fetch Migration

## 목적

Wave G STEP 2-2 는 JACKAL 의 daily OHLCV 조회 경로를 `orca.market_fetch` 공용 wrapper 로 이동한다.
직접 `yfinance` 호출을 줄이고, `USE_UNIFIED_FETCH=1` 기본값에서 yfinance retry 와 Alpha Vantage fallback 을 자동으로 활용하는 것이 목표다.

## 변경 범위

이번 단계는 세 함수만 바꾼다.

- `jackal/backtest.py::_fetch_yf_cached()`
  - 기존: `yf.Ticker(ticker).history(period="2y", interval="1d")`
  - 변경: `orca.market_fetch.fetch_daily_history(ticker, start, end)`
  - `functools.lru_cache(maxsize=128)` 는 그대로 유지한다.

- `jackal/tracker.py::_fetch_post_hunt_closes()`
  - 기존: `yf.download(..., auto_adjust=True)`
  - 변경: `fetch_daily_history()` 로 같은 날짜 범위의 daily close 를 가져온다.
  - hunt 당일 제외 후 익일 이후 close 를 추출하는 로직은 그대로 유지한다.

- `jackal/market_data.py::fetch_technicals()`
  - 기존: `yf.Ticker(ticker).history(period="1y", interval="1d")`
  - 변경: 최근 400 calendar days 를 `fetch_daily_history()` 로 조회한다.
  - technical cache fallback 은 유지한다.

## 보존되는 동작

- 기존 public function signature 는 변경하지 않는다.
- JACKAL backtest 의 `lru_cache` 는 그대로 동작한다.
- Scanner technical cache 는 유지된다.
- `USE_UNIFIED_FETCH=0` 을 설정하면 wrapper 내부에서 기존 yfinance direct path 로 rollback 할 수 있다.
- Alpha Vantage key 가 없어도 yfinance path 는 계속 동작한다.

## 날짜 범위

- Backtest: 750 calendar days
  - 기존 `period="2y"` 대체.
  - weekend/holiday buffer 를 포함한다.

- Tracker: hunt timestamp 부터 `max_days * 2 + 5` calendar days
  - 기존 tracker window 를 그대로 유지한다.

- Market data technicals: 400 calendar days
  - 252 trading day 기반 52-week position 계산을 위해 1년보다 넉넉한 buffer 를 둔다.

## auto_adjust 차이

Tracker 의 기존 `yf.download(..., auto_adjust=True)` 는 split/dividend adjusted close 를 사용했다.
현재 `market_fetch.fetch_daily_history()` 는 표준 `Close` 컬럼을 사용한다.

단기 outcome 추적에서는 일반적으로 split 이벤트가 드물어 영향이 작다. 다만 future enhancement 로 wrapper 에 `adjusted=True` 옵션을 추가하면 이 차이를 더 엄밀하게 줄일 수 있다.

## 검증 절차

로컬에서 다음을 실행한다.

```powershell
python -m unittest tests.test_wave_g_step_2_2_migration
python -m unittest discover -s tests
```

예상 결과:

- STEP 2-1 기준 249 tests 유지
- STEP 2-2 신규 10 tests 추가
- 총 259 tests passing

## 운영 확인

JACKAL workflow 실행 후 로그에서 다음을 확인한다.

- Backtest: universe ticker fetch 가 실패 없이 진행되는지
- Tracker: post-hunt close series 가 정상 추출되는지
- Scanner: `fetch_technicals()` 결과가 정상이며, 실패 시 cache fallback 이 사용되는지

`orca.market_fetch.get_fetch_stats()` 를 추가로 출력하면 source 별 사용량을 확인할 수 있다.

## Rollback

가장 빠른 rollback 은 환경변수다.

```powershell
$env:USE_UNIFIED_FETCH = "0"
```

GitHub Actions 에서는 workflow env 에 다음을 추가한다.

```yaml
USE_UNIFIED_FETCH: "0"
```

이 경우 JACKAL 코드의 호출 경로는 wrapper 를 유지하지만, wrapper 내부가 yfinance direct path 로 전환된다.
구조 자체를 되돌려야 할 때만 Wave G STEP 2-2 commit 을 revert 한다.

## 다음 단계

STEP 2-3 에서 다음 경로를 이관한다.

- `jackal/hunter.py`
- `orca/backtest.py`
- `orca/context_snapshot.py`

STEP 2-4 에서 `orca/data.py` 와 put/call ratio 관련 fetch 를 별도 설계한다.
