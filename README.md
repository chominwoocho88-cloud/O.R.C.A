# ORCA + JACKAL

`ORCA` means `Omnidirectional Risk & Context Analyzer`.

`JACKAL` means `Just-in-time Alert for Candidates & Key Asset Leverage`.

## Repository Layout

```text
.
|-- .github/workflows/   # Scheduled jobs, backtests, reset, policy gates
|-- data/                # Runtime state and tracked JSON / SQLite data
|-- docs/                # Architecture, v2 design, release-readiness notes
|-- jackal/              # JACKAL package
|-- orca/                # ORCA package
|-- reports/             # Generated reports and dashboard output
|-- .env.example         # Example local environment variables
|-- .gitignore
|-- README.md
`-- requirements.txt
```

## Main Entry Points

```bash
python -m pip install -r requirements.txt

python -m orca
python -m apps.orca.main
python -m apps.orca.backtest --months 6 --walk-forward
python -m orca.reset --orca

python -m jackal
python -m apps.jackal.core
python -m apps.jackal.scanner
python -m jackal.backtest
python -m apps.jackal.tracker
```

## ORCA Package Map

- `apps/orca/main.py`: live orchestration and report assembly
- `apps/orca/analysis.py`: verification, lessons, baseline, candidate review
- `apps/orca/pipeline/agents.py`: Hunter -> Analyst -> Devil -> Reporter
- `orca/data.py`: market-data collection and cost tracking
- `orca/notify.py`: Telegram and scheduled notifications
- `apps/orca/state.py`: SQLite state spine, candidate registry, research history
- `apps/orca/research/research_report.py`: research comparison report
- `apps/orca/research_gate.py`: regression gate evaluation
- `apps/orca/policy_promote.py`: promotion decision builder
- `orca/dashboard.py`: dashboard renderer
- `shared/paths.py`: canonical runtime paths

## JACKAL Package Map

- `apps/jackal/core.py`: live opportunity-engine entrypoint
- `apps/jackal/hunter.py`: candidate discovery pipeline
- `apps/jackal/scanner.py`: watchlist timing evaluation (portfolio + candidate registry + recent recommendations)
- `apps/jackal/tracker.py`: outcome tracking and weight refresh
- `apps/jackal/evolution.py`: learning and weight evolution
- `jackal/probability.py`: candidate lesson probability adjustment
- `jackal/families.py`: canonical signal-family taxonomy
- `apps/jackal/pipeline/shield.py`: budget and secret checks
- `apps/jackal/compact.py`: context compaction
- `jackal/market_data.py`: market-data collection
- `apps/jackal/pipeline/adapter.py`: ORCA context bridge

## Learning Loop

1. `JACKAL` finds candidates from hunt / scan / shadow flows.
2. Candidates are written into `candidate_registry` inside `apps.orca.state`.
3. `ORCA` reviews recent candidates against the current market regime.
4. Tracker and shadow resolution write D1 / swing / follow-up outcomes.
5. Candidate lessons are generated as `aligned_win`, `opposed_loss`, and similar labels.
6. `JACKAL` reads the probability summary and applies a small score adjustment only when recent samples are sufficient.

This means the system learns from candidate quality and market alignment, not just from a fixed portfolio.

## Runtime Roles

- `ORCA Daily`: market regime report, baseline, sentiment, rotation, dashboard render
- `JACKAL Session`: scheduled Hunter -> Scanner flow for discovery plus timing in one run
  - `workflow_dispatch` supports `session_mode=full` / `scanner_only` with optional `force_scan`
  - manual scanner runs now use `session_mode=scanner_only`
- `JACKAL Tracker`: next-day / swing outcome tracking and weight refresh

## Documents

- Candidate-registry v2 design:
  [docs/orca_candidate_registry_v2.md](docs/orca_candidate_registry_v2.md)
- Architecture and migration notes:
  [docs/orca_v2_architecture.md](docs/orca_v2_architecture.md)
- Backlog:
  [docs/orca_v2_backlog.md](docs/orca_v2_backlog.md)
- Release readiness and GitHub handoff:
  [docs/jackal_release_readiness.md](docs/jackal_release_readiness.md)

## Current Caveats

- `ORCA` backtest requires `ANTHROPIC_API_KEY`.
- `yfinance` rate limits can reduce backtest reliability unless cached data or retries are added.
- The current environment does not include `git`, so publishing must be done from a machine with Git installed.
