# ORCA + JACKAL

`ORCA` stands for `Omnidirectional Risk & Context Analyzer`.

`JACKAL` stands for `Just-in-time Alert for Candidates & Key Asset Leverage`.

## Structure

```text
.
├─ .github/workflows/   # Scheduled runs, reset, backtest, policy gates
├─ data/                # Runtime state and tracked JSON/SQLite data
├─ docs/                # Architecture and design notes
├─ jackal/              # JACKAL package
├─ orca/                # ORCA package
├─ reports/             # Generated reports and dashboard output
└─ requirements.txt     # Python dependencies
```

## Main Entry Points

- `python -m pip install -r requirements.txt`

- `python -m orca`
- `python -m orca.main`
- `python -m orca.backtest --months 6 --walk-forward`
- `python -m orca.reset --orca`
- `python -m jackal`
- `python -m jackal.core`
- `python -m jackal.backtest`
- `python -m jackal.tracker`

## ORCA Package Map

- `orca/main.py`: live orchestration
- `orca/analysis.py`: verification, lessons, weights, baseline logic
- `orca/agents.py`: Hunter -> Analyst -> Devil -> Reporter
- `orca/data.py`: market-data collection and cost tracking
- `orca/notify.py`: Telegram and scheduled notifications
- `orca/state.py`: SQLite state spine
- `orca/research_report.py`: research comparison report
- `orca/research_gate.py`: regression gate evaluation
- `orca/policy_promote.py`: promotion decision builder
- `orca/dashboard.py`: dashboard renderer
- `orca/paths.py`: canonical paths

## JACKAL Package Map

- `jackal/core.py`: live opportunity-engine entrypoint
- `jackal/hunter.py`: candidate discovery pipeline
- `jackal/scanner.py`: Analyst -> Devil -> Final evaluation
- `jackal/tracker.py`: outcome tracking and weight refresh
- `jackal/evolution.py`: learning and weight evolution
- `jackal/shield.py`: budget and secret checks
- `jackal/compact.py`: context compaction
- `jackal/market_data.py`: market-data collection
- `jackal/adapter.py`: ORCA context bridge

## Notes

- Runtime and research state are separated.
- Generated files should land in `reports/` instead of the repo root.
- JACKAL is now a Python package and can run with `python -m jackal...`.
- JACKAL reads ORCA state through `orca.state`.
