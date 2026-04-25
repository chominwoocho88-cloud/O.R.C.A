"""Context snapshot helpers for Wave F Phase 1."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

try:
    import yfinance as yf
except Exception:  # pragma: no cover - degraded runtime fallback
    yf = None

from .paths import BASELINE_FILE
from . import state


VALID_SOURCE_EVENT_TYPES = {"live", "backtest", "walk_forward", "scan", "hunt", "shadow"}

SECTOR_ETFS = {
    "XLK": "Technology",
    "XLV": "Healthcare",
    "XLE": "Energy",
    "XLF": "Financials",
    "XLI": "Industrials",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLB": "Materials",
    "XLC": "Communication Services",
}

_LOOKBACK_BUFFER_DAYS = 90


def get_existing_snapshot(
    trading_date: str,
    source_event_type: str,
    *,
    conn: sqlite3.Connection | None = None,
) -> dict[str, Any] | None:
    return state.find_lesson_context_snapshot(
        trading_date,
        source_event_type,
        conn=conn,
    )


def get_or_create_context_snapshot(
    trading_date: str,
    source_event_type: str,
    source_session_id: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> str:
    """Return an existing context snapshot for the date or create a new one."""
    own_conn = conn is None
    if own_conn:
        state.init_state_db()
        conn = state._connect_orca()
    try:
        existing = get_existing_snapshot(
            trading_date,
            source_event_type,
            conn=conn,
        )
        if existing:
            return str(existing["snapshot_id"])

        snapshot_data = _build_snapshot_data(trading_date, conn)
        snapshot_id = state.record_lesson_context_snapshot(
            {
                "snapshot_id": f"ctx_{uuid4().hex}",
                "created_at": datetime.now().isoformat(),
                "trading_date": trading_date,
                "regime": snapshot_data.get("regime"),
                "regime_confidence": snapshot_data.get("regime_confidence"),
                "vix_level": snapshot_data.get("vix_level"),
                "vix_delta_7d": snapshot_data.get("vix_delta_7d"),
                "sp500_momentum_5d": snapshot_data.get("sp500_momentum_5d"),
                "sp500_momentum_20d": snapshot_data.get("sp500_momentum_20d"),
                "nasdaq_momentum_5d": snapshot_data.get("nasdaq_momentum_5d"),
                "nasdaq_momentum_20d": snapshot_data.get("nasdaq_momentum_20d"),
                "dominant_sectors": snapshot_data.get("dominant_sectors", []),
                "source_event_type": source_event_type,
                "source_session_id": source_session_id,
            },
            conn=conn,
        )
        if own_conn:
            conn.commit()
        return snapshot_id
    finally:
        if own_conn and conn is not None:
            conn.close()


def _build_snapshot_data(trading_date: str, conn: sqlite3.Connection) -> dict[str, Any]:
    """Build the minimum viable Wave F context snapshot for one trading date."""
    market_data = _fetch_market_data_for_date(trading_date)
    regime, confidence = _fetch_regime_for_date(trading_date, conn, market_data=market_data)
    return {
        "regime": regime,
        "regime_confidence": confidence,
        **market_data,
        "dominant_sectors": _compute_dominant_sectors(trading_date),
    }


def _normalize_regime_value(regime: str | None) -> str | None:
    if not regime:
        return None
    try:
        from .backtest import _normalize_regime

        normalized = _normalize_regime(str(regime))
    except Exception:
        normalized = str(regime).strip()
    return normalized or None


def _map_confidence_to_score(confidence: str | None) -> float | None:
    value = str(confidence or "").strip().lower()
    if not value:
        return None
    mapping = {
        "낮음": 0.33,
        "low": 0.33,
        "보통": 0.67,
        "medium": 0.67,
        "med": 0.67,
        "높음": 1.0,
        "high": 1.0,
    }
    return mapping.get(value)


def _load_json_file(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _fetch_regime_for_date(
    trading_date: str,
    conn: sqlite3.Connection,
    *,
    market_data: dict[str, Any] | None = None,
) -> tuple[str | None, float | None]:
    regime, confidence = _fetch_regime_from_orca_report(trading_date, conn)
    if regime:
        return regime, confidence

    regime, confidence = _fetch_regime_from_baseline(trading_date)
    if regime:
        return regime, confidence

    regime, confidence = _heuristic_regime(market_data or _fetch_market_data_for_date(trading_date))
    return regime, confidence


def _fetch_regime_from_orca_report(
    trading_date: str,
    conn: sqlite3.Connection,
) -> tuple[str | None, float | None]:
    row = conn.execute(
        """
        SELECT d.analysis_json
          FROM backtest_daily_results d
          JOIN backtest_sessions s
            ON s.session_id = d.session_id
         WHERE s.system = 'orca'
           AND s.status = 'completed'
           AND d.analysis_date = ?
         ORDER BY s.started_at DESC,
                  CASE
                      WHEN d.phase_label = 'Final Pass' THEN 0
                      WHEN d.phase_label = 'Final' THEN 1
                      ELSE 2
                  END,
                  d.created_at DESC
         LIMIT 1
        """,
        (trading_date,),
    ).fetchone()
    if not row or not row["analysis_json"]:
        return None, None
    try:
        analysis = json.loads(row["analysis_json"])
    except Exception:
        return None, None
    regime = _normalize_regime_value(analysis.get("market_regime"))
    confidence = _map_confidence_to_score(analysis.get("confidence_overall"))
    return regime, confidence


def _fetch_regime_from_baseline(trading_date: str) -> tuple[str | None, float | None]:
    baseline = _load_json_file(BASELINE_FILE)
    if not isinstance(baseline, dict):
        return None, None
    if str(baseline.get("date", "")) != trading_date:
        return None, None
    regime = _normalize_regime_value(baseline.get("market_regime"))
    confidence = _map_confidence_to_score(
        baseline.get("confidence") or baseline.get("confidence_overall")
    )
    return regime, confidence


def _heuristic_regime(market_data: dict[str, Any]) -> tuple[str | None, float | None]:
    vix = market_data.get("vix_level")
    sp20 = market_data.get("sp500_momentum_20d")
    nq20 = market_data.get("nasdaq_momentum_20d")
    if vix is None and sp20 is None and nq20 is None:
        return None, None
    if vix is not None and vix >= 25:
        return "위험회피", 0.45
    if vix is not None and vix >= 20:
        return "전환중", 0.4
    if (sp20 or 0.0) > 0 and (nq20 or 0.0) > 0:
        return "위험선호", 0.4
    return "혼조", 0.35


def _fetch_market_data_for_date(trading_date: str) -> dict[str, Any]:
    """Fetch historical market context for ``trading_date``.

    ``orca.data.fetch_yahoo_data`` is current-only, so Phase 1.1 uses the same
    Yahoo source directly for historical lookbacks.
    """
    vix_points = _fetch_history_points("^VIX", trading_date, lookback_days=30)
    sp_points = _fetch_history_points("^GSPC", trading_date, lookback_days=40)
    nq_points = _fetch_history_points("^IXIC", trading_date, lookback_days=40)
    return {
        "vix_level": _latest_close(vix_points),
        "vix_delta_7d": _absolute_delta(vix_points, 7),
        "sp500_momentum_5d": _percent_change(sp_points, 5),
        "sp500_momentum_20d": _percent_change(sp_points, 20),
        "nasdaq_momentum_5d": _percent_change(nq_points, 5),
        "nasdaq_momentum_20d": _percent_change(nq_points, 20),
    }


def _compute_dominant_sectors(trading_date: str, top_n: int = 3) -> list[str]:
    scored: list[tuple[str, float]] = []
    for ticker, label in SECTOR_ETFS.items():
        points = _fetch_history_points(ticker, trading_date, lookback_days=15)
        change = _percent_change(points, 5)
        if change is None or change <= 0:
            continue
        scored.append((label, change))
    scored.sort(key=lambda item: item[1], reverse=True)
    return [label for label, _score in scored[:top_n]]


def _fetch_history_points(
    ticker: str,
    trading_date: str,
    *,
    lookback_days: int,
) -> list[tuple[str, float]]:
    if yf is None:
        return []
    try:
        end_date = datetime.fromisoformat(trading_date) + timedelta(days=1)
    except ValueError:
        return []
    start_date = end_date - timedelta(days=max(_LOOKBACK_BUFFER_DAYS, lookback_days * 4))
    try:
        history = yf.Ticker(ticker).history(
            start=start_date.date().isoformat(),
            end=end_date.date().isoformat(),
            interval="1d",
            auto_adjust=False,
        )
    except Exception:
        return []
    if history is None:
        return []
    columns = getattr(history, "columns", [])
    close_column = None
    if "Adj Close" in columns:
        close_column = "Adj Close"
    elif "Close" in columns:
        close_column = "Close"
    if not close_column:
        return []

    points: list[tuple[str, float]] = []
    try:
        iterator = history.iterrows()
    except Exception:
        return []
    for idx, row in iterator:
        try:
            close_value = row.get(close_column)
        except Exception:
            close_value = None
        if close_value is None:
            continue
        try:
            close_float = float(close_value)
        except Exception:
            continue
        if close_float != close_float:
            continue
        date_str = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
        points.append((date_str, close_float))
    return points


def _latest_close(points: list[tuple[str, float]]) -> float | None:
    if not points:
        return None
    return round(points[-1][1], 4)


def _absolute_delta(points: list[tuple[str, float]], offset: int) -> float | None:
    if len(points) <= offset:
        return None
    current = points[-1][1]
    prior = points[-(offset + 1)][1]
    return round(current - prior, 4)


def _percent_change(points: list[tuple[str, float]], offset: int) -> float | None:
    if len(points) <= offset:
        return None
    current = points[-1][1]
    prior = points[-(offset + 1)][1]
    if prior == 0:
        return None
    return round(((current - prior) / prior) * 100.0, 4)
