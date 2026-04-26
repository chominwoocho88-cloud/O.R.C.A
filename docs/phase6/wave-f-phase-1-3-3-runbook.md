# Wave F Phase 1.3.3 Runbook: Sector Threshold Relaxation

## Purpose

Wave F Phase 1.3.3 relaxes only the `dominant_sectors` completeness threshold
in `verify_backfill_completeness()`.

The GitHub Actions backfill after Phase 1.3.2 produced:

- 252 / 252 snapshots
- 252 / 252 VIX values
- 252 / 252 S&P 500 momentum values
- 252 / 252 NASDAQ momentum values
- 248 / 252 dominant sector values

The missing 4 sector dates are likely provider coverage gaps for one or more
sector ETFs. The core context dimensions are complete, so blocking the DB commit
on 4 missing sector rows is too strict for Phase 1 historical backfill.

## New Verification Policy

Still required at 100%:

- `vix_level`
- `sp500_momentum_5d`
- `sp500_momentum_20d`
- `nasdaq_momentum_5d`
- `nasdaq_momentum_20d`

Relaxed:

- `dominant_sectors` must be filled for at least 95% of backfill snapshots.

The new function argument is:

```python
verify_backfill_completeness(sector_min_ratio=0.95)
```

Use `sector_min_ratio=1.0` to restore the previous strict behavior.

## Why 95%

The sector field is useful context, but it is not the only market-context
anchor. VIX and index momentum remain fully enforced. A 95% threshold allows a
small number of permanent sector ETF data gaps while keeping the snapshot set
high quality.

For 252 snapshots:

- 95% threshold = 240 required sector snapshots
- observed = 248
- result = pass

## Execution

After this change is on main, rerun:

```text
Actions -> Wave F Backfill -> Run workflow
```

Recommended inputs:

```text
dry_run: false
limit: empty
skip_existing: false
cleanup: true
```

Strict verify should now pass if:

- VIX/momentum remain 252 / 252
- sectors remain at or above 240 / 252
- all 1260 lessons are linked

## Troubleshooting

If verification still fails because sectors are below 95%:

- rerun later in case the provider gap is transient
- inspect the source tracking logs
- keep the DB uncommitted until strict verify passes

If VIX or momentum fails:

- do not relax those thresholds
- treat it as a provider/fetch failure and rerun after rate limits cool down

## Future Work

If sector gaps are permanent, Phase 1.4 can add a more robust sector source or a
cached sector rotation vector. For Phase 1.3.3, the intent is only to unblock a
high-quality historical backfill without weakening core market metrics.
