# Wave G STEP 2-3 Runbook: Hunter + ORCA Backtest Fetch Migration

## 목적

Wave G STEP 2-3 는 JACKAL Hunter 와 ORCA Backtest 의 남은 daily OHLCV fetch 를 `orca.market_fetch` wrapper 로 옮긴다.
목표는 yfinance rate limit 이 걸려도 Alpha Vantage fallback 을 통해 Hunter daily 운영과 ORCA 3년 backtest 확장을 안정화하는 것이다.

## 변경 범위

### Alpha Vantage pacing

`orca/context_market_data.py` 에 `ALPHA_VANTAGE_SLEEP_SECONDS` 환경변수를 추가했다.

권장값:

- Free tier: `12.0` seconds, 기본값
- Standard tier: `0.8` seconds, 75 requests/min 기준
- Premium tier: `0.4` seconds, 150 requests/min 기준

음수 값은 `0.0` 으로 clamp 되고, 잘못된 값은 기본값 `12.0` 으로 돌아간다.

### JACKAL Hunter

`jackal/hunter.py` 의 세 경로가 wrapper 를 사용한다.

- `_fetch_macro_gate()`
  - `^VIX`, `^TNX`, `^IRX`, `HYG`
  - 일부 ticker fetch 실패 시 기존 fail-safe 값을 유지한다.

- `_fetch_etf_returns()`
  - sector ETF 8개를 `fetch_daily_history_batch()` 로 조회한다.
  - 5d return 계산식은 유지한다.

- `_batch_technicals()`
  - Hunter universe 전체를 `fetch_daily_history_batch()` 로 조회한다.
  - `_calc_tech()` 계산 로직은 유지한다.
  - fetch 실패 ticker 는 `None` 으로 남고 Stage 1 에서 skip 된다.

### ORCA Backtest

`orca/backtest.py::_fetch_dynamic_hist()` 가 `fetch_daily_history_batch()` 를 사용한다.

대상 ticker:

- `^GSPC`
- `^IXIC`
- `^VIX`
- `^KS11`
- `USDKRW=X`
- `000660.KS`
- `005930.KS`
- `NVDA`

기존 `_extract_close_series()` 와 `HIST_DATA` merge 로직은 유지한다.

## GitHub Actions 권장 env

Wave F backfill workflow 는 Standard tier 기준으로 다음 env 를 사용한다.

```yaml
ALPHA_VANTAGE_SLEEP_SECONDS: "0.8"
USE_UNIFIED_FETCH: "1"
```

JACKAL / ORCA workflow 에도 단계적으로 같은 env 를 추가할 수 있다.
단, env 를 추가하지 않아도 기본값은 안전한 free-tier pacing 이다.

## 검증

로컬 검증:

```powershell
python -m unittest tests.test_wave_g_step_2_3_migration
python -m unittest discover -s tests
```

예상:

- STEP 2-2 기준 259 tests 유지
- STEP 2-3 신규 15 tests 추가
- 총 274 tests passing

## 운영 영향

Hunter universe 는 보통 80-100 ticker 규모다.
yfinance 가 정상 동작하면 기존과 유사한 속도로 진행된다.
yfinance 가 rate limit 될 경우 Alpha Vantage fallback 으로 넘어가며, Standard tier `0.8s` pacing 기준 대략 1-2분 범위로 수렴한다.

ORCA Backtest dynamic fetch 는 8 ticker batch 이므로 3년 backtest 기간으로 늘려도 요청량이 작다.
`HIST_DATA` 가 coverage cache 역할을 하므로 이미 있는 날짜는 재사용된다.

## Rollback

빠른 rollback:

```powershell
$env:USE_UNIFIED_FETCH = "0"
```

이 값은 wrapper 내부를 yfinance direct path 로 전환한다.

Alpha Vantage pacing 만 보수적으로 되돌리려면 다음 env 를 제거하거나 `12.0` 으로 설정한다.

```powershell
$env:ALPHA_VANTAGE_SLEEP_SECONDS = "12.0"
```

## 다음 단계

STEP 2-4:

- `orca/context_snapshot.py`
- `orca/data.py`

STEP 2-5 후보:

- put/call ratio fetch 경로 별도 설계
