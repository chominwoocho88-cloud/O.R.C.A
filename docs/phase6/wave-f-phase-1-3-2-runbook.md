# Wave F Phase 1.3.2 Runbook: yfinance Retry + Alpha Vantage Fallback

## Purpose

Wave F Phase 1.3.2 hardens the historical context backfill against market-data
provider throttling.

The first GitHub Actions backfill correctly found 1260 lessons, but yfinance
returned HTTP 429 for all 14 market tickers. The strict verifier blocked the DB
commit, which was the correct behavior. This fix keeps that verifier in place
and improves the fetch path.

## What Changed

The backfill market-data path now uses three layers:

1. yfinance batch fetch with exponential backoff.
2. yfinance per-ticker retry.
3. Alpha Vantage fallback when `ALPHA_VANTAGE_API_KEY` is available.

Only the Wave F backfill batch path is changed. The Phase 1.1 live/manual helper
`_fetch_history_points()` is intentionally unchanged.

## Fetch Cascade

### Layer 1: yfinance Batch

The workflow first tries all 14 tickers in one yfinance batch:

- `^VIX`
- `^GSPC`
- `^IXIC`
- `XLK`, `XLV`, `XLE`, `XLF`, `XLI`, `XLY`, `XLP`, `XLU`, `XLRE`, `XLB`, `XLC`

Retry policy:

- 3 attempts
- backoff: 2s, 8s, 18s
- `threads=False` to reduce pressure on Yahoo endpoints

### Layer 2: yfinance Per-Ticker

Any ticker missing from the batch result is retried individually.

Retry policy:

- 3 attempts per ticker
- 1s sleep before each ticker request
- backoff: 2s, 8s, 18s

### Layer 3: Alpha Vantage

If a ticker still fails and `ALPHA_VANTAGE_API_KEY` is set, the workflow uses
Alpha Vantage `TIME_SERIES_DAILY` with CSV output.

Rate-limit policy:

- 12s sleep before each Alpha Vantage call
- retry once after 15s if the first call fails

The code tries `outputsize=full` first. If Alpha Vantage returns an information,
premium, or rate-limit response, it falls back to `outputsize=compact`.

## Alpha Vantage Mapping

Alpha Vantage equity and ETF symbols are used directly for sector ETFs:

- `XLK`, `XLV`, `XLE`, `XLF`, `XLI`, `XLY`, `XLP`, `XLU`, `XLRE`, `XLB`, `XLC`

The market indexes use ETF proxies:

- `^VIX` -> `VIXY`
- `^GSPC` -> `SPY`
- `^IXIC` -> `QQQ`

Important: `VIXY` is not the VIX index. It is a VIX futures ETF proxy. This
means `vix_level` from Alpha Vantage fallback should be interpreted as a proxy
risk-volatility measure, not as the literal `^VIX` index level.

## GitHub Secret

The workflow expects this repository secret:

```text
ALPHA_VANTAGE_API_KEY
```

If the secret is missing, the backfill still runs in yfinance-only mode. Alpha
Vantage is optional and only used as fallback.

## Workflow Execution

Use:

```text
Actions -> Wave F Backfill -> Run workflow
```

Recommended recovery run after the failed 429 attempt:

```text
dry_run: false
limit: empty
skip_existing: false
cleanup: true
```

Why:

- `cleanup=true` removes the previous metric-empty `backtest_backfill` snapshots.
- `skip_existing=false` ensures the workflow can relink regenerated snapshots.
- strict verify blocks commit unless 252 snapshots and 1260 lesson links are
  complete.

## Source Tracking

The backfill logs a summary:

```text
Backfill market data sources:
  yfinance_batch_success=N
  yfinance_ticker_success=N
  alpha_vantage_success=N
  failed=N
```

Interpretation:

- `yfinance_batch_success`: tickers filled by the initial batch.
- `yfinance_ticker_success`: tickers filled by per-ticker yfinance retry.
- `alpha_vantage_success`: tickers filled by Alpha Vantage fallback.
- `failed`: tickers still empty after all fallbacks.

For strict verify to pass, `failed` should normally be 0 and all required
metrics should be non-null.

## Expected Result

After a successful run:

- `lesson_context_snapshot` has 252 `backtest_backfill` rows.
- 1260 backtest lessons have `context_snapshot_id`.
- `vix_level`, S&P momentum, NASDAQ momentum, and dominant sectors are filled.
- The workflow commits `data/orca_state.db` to main.

## Troubleshooting

If yfinance returns 429 but Alpha Vantage succeeds:

- The run should pass after the fallback completes.
- Expect several minutes of extra runtime from the 12s Alpha Vantage pacing.

If Alpha Vantage returns premium or rate-limit messages:

- The code tries compact output after full output.
- Compact output may be insufficient for the full 252-day historical range.
- Strict verify may fail, which is expected protection.

If both yfinance and Alpha Vantage fail:

- Wait 1-6 hours and retry.
- Keep `cleanup=true` if any partial backfill data was created.
- Do not manually commit DB changes that failed strict verify.

If only old dates are missing:

- Alpha Vantage compact fallback likely did not provide enough history.
- Rerun later when yfinance batch is no longer throttled.

## Rollback

If a bad backfill commit somehow lands, use either:

```text
Wave F Backfill with cleanup=true, dry_run=false
```

or:

```powershell
git revert <backfill_commit_hash>
git push origin main
```

Cleanup mode removes only `source_event_type='backtest_backfill'` snapshots and
preserves future live snapshots.
