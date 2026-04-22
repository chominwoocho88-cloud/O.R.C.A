# External Review: 2026-04-22

**Status**: Reference material only. NOT authoritative.

이 문서는 외부 관점의 독립 분석 리포트다.
다음 조건에서 읽어야 한다:

1. Phase 5 맥락이 반영되지 않음
   - PR 1-5 계약, Path B decision, dual-DB design 등 최근 작업 미반영
   - 작성 시점에 이 맥락이 문서에 들어가지 않음

2. Section 6 "Highest-Value Improvements" 의 투자 전략 제안은
   **검증되지 않은 proposal** 이다
   - regime-adaptive thresholds
   - portfolio construction
   - "do not trade" layer 등
   - 적용 전 개별 backtest 필수
   - 즉시 Backlog 로 옮기지 않는다

3. 이 문서는 "할 일 목록" 이 아니라 "참고 자료" 다
   - 기존 docs/orca_v2_backlog.md 가 실제 실행 대상
   - 이 문서 제안을 Backlog 에 넣으려면 개별 판단 필요

실제 진행 중인 작업 맥락은 다음 문서 참조:
- docs/phase5/ 전체 (Phase 5 Path B)
- docs/orca_v2_backlog.md (실행 대상 Backlog)
- docs/jackal/current-signals.md (JACKAL 현재 신호)

이 문서는 이하 원본 그대로 보존한다.

---

# O.R.C.A Repository Analysis Report

- Date: 2026-04-22
- Scope: `ORCA` / `JACKAL` source, workflows, tests, generated research artifacts, runtime state layout
- Goal: repository architecture review plus improvements aimed at better real-world stock-investing performance

## 1. Executive Summary

This repository is not a toy prototype anymore. It already has a meaningful operating loop:

1. `ORCA` builds market context and report artifacts.
2. `JACKAL` hunts/scans candidates and tracks outcomes.
3. SQLite-backed state stores runs, predictions, candidates, outcomes, and backtest sessions.
4. Research comparison, gate, and promotion-decision artifacts exist as a lightweight policy pipeline.

The strongest part of the repository is that it has moved beyond plain prompt output and now records structured research state in SQLite. The weakest part is that return-related validation is still much lighter than the trading logic itself. In other words, the system is already good at generating and scoring ideas, but not yet equally strong at proving that those ideas remain profitable after costs, concentration, and regime shifts.

My high-level conclusion:

- Engineering maturity: medium to high
- Research maturity: medium
- Live-trading readiness: medium-low
- Main blocker to higher real returns: incomplete validation realism, not lack of signal ideas

## 2. Repository Snapshot

- Python files inspected: `41`
- Approximate Python LOC: `17,943`
- Largest modules:
  - `orca/state.py` `2966` lines
  - `orca/backtest.py` `2343` lines
  - `jackal/scanner.py` `1744` lines
  - `jackal/hunter.py` `1446` lines
  - `orca/analysis.py` `1395` lines
- Runtime state currently present:
  - `data/orca_state.db` about `1.8 MB`
  - `data/jackal_state.db` about `118 KB`
  - JSON runtime mirrors still exist beside DB state
- Verification run in this review:
  - `python -m compileall orca jackal tests` passed
  - `python -m unittest discover -s tests -v` passed with `9/9`
  - `pytest` is not installed in the current environment

## 3. What Is Working Well

### 3.1 Architecture has a real backbone now

`orca/run_cycle.py` orchestrates a full run around market-data collection, verification, pipeline execution, candidate review, probability summary, reporting, and state finalization. That is a meaningful production shape, not just a single script.

### 3.2 State management is stronger than a typical side project

`orca/state.py` creates and manages structured tables for:

- runs
- predictions / outcomes
- backtest sessions and day rows
- candidate registry / candidate reviews / candidate outcomes / candidate lessons
- JACKAL shadow, live events, cooldowns, recommendations, and accuracy projection

This is a major strength. It means the project can support auditability, replay, and future policy versioning.

### 3.3 Research governance exists

The repo already generates:

- research comparison
- research gate
- policy promotion decision

The latest saved artifacts show:

- ORCA final accuracy: `58.7%`
- JACKAL swing accuracy: `75.6%`
- JACKAL D1 accuracy: `47.8%`
- Tracked JACKAL picks: `205`
- Current gate result: `warn`

That is good progress because the repository is not pretending every model change should auto-promote.

### 3.4 Outcome tracking is grounded in realized follow-up data

`jackal/tracker.py` records next-day and swing outcomes, then updates weight snapshots. `jackal/probability.py` applies only small, sample-gated probability nudges. That is much safer than fully rewriting policy from sparse outcomes.

## 4. Main Risks and Structural Weaknesses

### 4.1 Too much logic is concentrated in a few giant modules

The biggest operational risk is maintainability. The repository has several "god modules":

- `orca/state.py`
- `orca/backtest.py`
- `jackal/scanner.py`
- `jackal/hunter.py`
- `orca/analysis.py`

This makes regression risk higher because storage logic, business rules, validation rules, reporting, and fallback behavior are often mixed together.

### 4.2 Broad exception handling is still heavily used

Repository-wide search showed many `except Exception` blocks, especially in:

- `orca/state.py`
- `jackal/hunter.py`
- `jackal/scanner.py`
- `orca/analysis.py`
- `orca/backtest.py`

That pattern helps uptime, but it can also hide silent quality degradation. For a trading/research system, silent degradation is dangerous because it creates false confidence rather than explicit failure.

### 4.3 Validation is weaker than the scoring pipeline

This is the most important performance issue.

The current JACKAL backtest mainly summarizes:

- `d1_hit`
- `swing_hit`
- regime/ticker hit rates

The current result flow does **not** visibly model the following as first-class research outputs:

- transaction costs
- slippage
- spread impact
- turnover penalty
- portfolio-level position sizing
- max drawdown
- Sharpe / Sortino / Calmar
- capital utilization

That means "high backtest hit rate" can still overstate deployable return.

### 4.4 Runtime state is still being pushed back into Git

The workflows commit JSON/DB runtime artifacts back into the repository. This gives traceability, but it also mixes source control with mutable production state. That is workable for a solo system, but it creates friction for scaling, debugging, and safe branching.

### 4.5 Evidence gaps remain in the latest research artifacts

The current `research_gate` is `warn`, not `pass`, mainly because the repository itself says key evidence is still missing:

- no shadow batch history
- no SQL-projected swing-signal accuracy snapshot with enough samples
- no SQL-projected ticker-accuracy snapshot with enough samples
- no SQL-projected recommendation-regime accuracy snapshot with enough samples

This matters because the repo is already smart enough to say "do not auto-promote yet."

## 5. Investment Performance Diagnosis

If the goal is to maximize stock-investing returns in practice, the biggest issue is **not** that the repo lacks enough scoring rules. The bigger issue is that the evaluation stack does not yet translate signal quality into portfolio-quality returns.

Right now the system is strongest at:

- finding candidate setups
- scoring technical/reaction signals
- learning small probability nudges from outcomes
- producing daily research narratives

Right now the system is weaker at:

- deciding how much capital to allocate per idea
- deciding how correlated simultaneous ideas are
- proving net return after execution frictions
- rejecting fragile strategies that only look good in backtests

So the best path to higher real returns is:

1. improve execution realism
2. improve capital allocation
3. improve regime-aware validation
4. only then expand signal complexity

## 6. Highest-Value Improvements for Better Real Returns

### Priority 1. Add net-return backtesting, not just hit-rate backtesting

Current JACKAL backtest uses thresholds like:

- 1-day hit over `0.3%`
- swing hit over `1.0%`

That is useful, but it is still a classification-style view. To maximize real returns, the research layer should add:

- per-trade estimated commission
- spread/slippage estimate by ticker liquidity and volatility
- turnover-adjusted net return
- expectancy per trade
- cumulative equity curve
- max drawdown
- Sharpe / Sortino / Calmar

Reason: a strategy with lower hit rate can still outperform if payoff distribution is better, and a high hit-rate strategy can fail after costs.

### Priority 2. Move from signal scoring to portfolio construction

The repo needs a portfolio allocator layer between "candidate approved" and "trade-worthy."

Recommended additions:

- max position size per ticker
- sector concentration cap
- country cap (`US` / `KR`)
- correlated-signal cap
- volatility-scaled sizing
- conviction score to size mapping
- daily risk budget

Reason: raw return maximization without position control usually creates concentration risk rather than robust compounding.

### Priority 3. Make thresholds regime-adaptive, not mostly static

Current scanner thresholds such as alert/strong thresholds and cooldown windows are explicit and understandable, which is good. But fixed thresholds can degrade across volatility regimes.

Recommended upgrade:

- volatility bucket by VIX / realized vol
- separate thresholds for risk-on, mixed, risk-off regimes
- separate thresholds by signal family
- more conservative entry threshold when shadow hit-rate weakens

Reason: a 65-point entry threshold may mean very different things in quiet markets versus panic rebounds.

### Priority 4. Add anti-overfitting metrics to promotion gating

The repo already has a policy gate. The next improvement is to make that gate harder to game.

Add:

- deflated Sharpe ratio or at least trial-count-aware Sharpe adjustment
- walk-forward performance stability by month/regime
- out-of-sample decay check
- parameter sensitivity check
- minimum sample size per signal family and regime cell

Reason: the fastest way to destroy real returns is to promote strategies that only won the search process.

### Priority 5. Separate "idea generation" from "entry execution"

ORCA/JACKAL currently do both discovery and timing-related evaluation. A stronger design would explicitly separate:

- thesis quality
- entry timing quality
- sizing quality
- exit quality

Reason: a good stock can be a bad entry, and a good entry can still be a bad sized position.

### Priority 6. Upgrade exit logic into a research object

The code mentions targets and stop-loss values in the JACKAL path, but exits are not yet the dominant evaluation object in research artifacts.

Recommended experiments:

- trailing stop variants
- partial profit-taking
- time stop
- volatility stop
- ORCA-regime-conditioned exit rules

Reason: improving exits often lifts realized return faster than adding new entry signals.

### Priority 7. Build a "do not trade" layer

To maximize long-run returns, the system should sometimes trade less.

Add hard blockers for:

- low-liquidity names
- event-driven gaps with poor fill quality
- too many same-family signals at once
- low-confidence signals in risk-off regimes
- stale data or degraded-source runs

Reason: removing the worst trades often improves compounding more than finding a few extra winners.

## 7. Recommended 4-Step Roadmap

### Step 1. Validation realism

- Add net PnL accounting to `jackal/backtest.py`
- Add spread/slippage/fee assumptions
- Add equity curve and drawdown report

### Step 2. Capital allocation

- Add a portfolio allocator module
- Implement size caps and risk budget
- Store simulated capital path in SQLite

### Step 3. Promotion discipline

- Extend `orca/research_gate.py` with risk-adjusted metrics
- Require minimum evidence by signal family and regime
- Block promotion when shadow evidence is missing

### Step 4. Module decomposition

- Split giant modules by domain
- Separate storage adapters from scoring logic
- Reduce broad exception swallowing and add structured health counters

## 8. Final Assessment

This repository already has a serious foundation:

- real orchestration
- SQLite state spine
- candidate registry
- backtests
- research comparison
- gate and promotion artifacts

The next 20% of work will likely produce 80% of the real-money improvement if it focuses on:

1. cost-aware validation
2. portfolio sizing
3. anti-overfitting discipline
4. regime-aware gating

If those four areas are strengthened, this repository can move from "interesting signal engine" toward "more credible decision system."

## 9. External References

- SEC, Asset Allocation / Diversification / Rebalancing:
  https://www.sec.gov/about/reports-publications/investorpubsassetallocationhtm
- Bailey & Lopez de Prado, *The Deflated Sharpe Ratio*:
  https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf
- Carr & Lopez de Prado, *Determining Optimal Trading Rules without Backtesting*:
  https://arxiv.org/abs/1408.1159
