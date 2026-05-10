"""JACKAL watchlist loaders for Phase 8g."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shared.paths import STATE_DB_FILE


def _market_for_ticker(ticker: str, fallback: str = "") -> str:
    value = str(ticker or "").strip().upper()
    if fallback:
        return fallback
    if value.endswith(".KS") or value.endswith(".KQ") or (value.isdigit() and len(value) == 6):
        return "KR"
    return "US"


def _currency_for_market(market: str) -> str:
    return "KRW" if str(market or "").upper() == "KR" else "$"


def _kis_to_watchlist_ticker(ticker: str) -> str:
    value = str(ticker or "").strip()
    if value.isdigit() and len(value) == 6:
        return value + ".KS"
    return value


def _load_candidate_registry_watchlist(
    *,
    statuses: tuple[str, ...] = ("open", "tracking"),
    days_lookback: int = 90,
) -> dict[str, dict]:
    """Load candidate tickers from the ORCA candidate_registry DB."""
    if not statuses:
        return {}

    db_path = Path(STATE_DB_FILE)
    if not db_path.exists():
        return {}

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        placeholders = ",".join("?" for _ in statuses)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days_lookback)).isoformat()
        cursor = conn.execute(
            f"""
            SELECT ticker, name, market, status, source_system, source_event_type,
                   detected_at, candidate_id, signal_family, quality_label, quality_score
            FROM candidate_registry
            WHERE status IN ({placeholders})
              AND detected_at >= ?
            ORDER BY detected_at DESC
            """,
            (*statuses, cutoff),
        )

        watchlist: dict[str, dict] = {}
        for row in cursor:
            ticker = str(row["ticker"] or "").strip()
            if not ticker or ticker in watchlist:
                continue
            market = _market_for_ticker(ticker, str(row["market"] or ""))
            watchlist[ticker] = {
                "ticker": ticker,
                "name": row["name"] or ticker,
                "market": market,
                "currency": _currency_for_market(market),
                "portfolio": False,
                "asset_type": "stock",
                "source": "candidate_registry",
                "status": row["status"],
                "detected_at": row["detected_at"],
                "candidate_id": row["candidate_id"],
                "source_system": row["source_system"],
                "source_event_type": row["source_event_type"],
                "signal_family": row["signal_family"],
                "quality_label": row["quality_label"],
                "quality_score": row["quality_score"],
            }
        return watchlist
    except Exception:
        return {}
    finally:
        if conn is not None:
            conn.close()


def _load_kis_holdings_watchlist() -> dict[str, dict]:
    """Load realtime KIS holdings into the JACKAL watchlist contract."""
    try:
        from shared.broker import get_shared_kis_client

        client = get_shared_kis_client()
        if not client.is_configured():
            return {}

        balance = client.get_account_balance()
        if not balance:
            return {}

        watchlist: dict[str, dict] = {}
        for item in balance.get("holdings", []) or []:
            ticker = _kis_to_watchlist_ticker(str(item.get("ticker", "") or ""))
            if not ticker:
                continue
            market = _market_for_ticker(ticker)
            watchlist[ticker] = {
                "ticker": ticker,
                "source": "kis_holdings",
                "name": item.get("name", "") or ticker,
                "quantity": item.get("quantity", 0),
                "avg_cost": item.get("avg_price", 0),
                "current_price": item.get("current_price", 0),
                "valuation": item.get("valuation", 0),
                "market": market,
                "currency": _currency_for_market(market),
                "portfolio": True,
                "asset_type": "stock",
            }
        return watchlist
    except Exception:
        return {}


def _load_kis_movers_watchlist() -> dict[str, dict]:
    """Load KIS volume and price movers into the JACKAL watchlist contract."""
    try:
        from shared.broker import get_shared_kis_client

        client = get_shared_kis_client()
        if not client.is_configured():
            return {}

        watchlist: dict[str, dict] = {}

        for item in client.get_volume_rank(market="KOSPI", limit=10):
            ticker = _kis_to_watchlist_ticker(str(item.get("ticker", "") or ""))
            if not ticker:
                continue
            market = _market_for_ticker(ticker)
            watchlist[ticker] = {
                "ticker": ticker,
                "source": "kis_volume_surge",
                "signal_type": "volume_surge",
                "name": item.get("name", "") or ticker,
                "volume_rank": item.get("volume_rank"),
                "current_price": item.get("current_price", 0),
                "volume": item.get("volume", 0),
                "change_rate": item.get("change_rate", 0),
                "market": market,
                "currency": _currency_for_market(market),
                "portfolio": False,
                "asset_type": "stock",
            }

        for item in client.get_fluctuation(market="KOSPI", limit=10, direction="up"):
            ticker = _kis_to_watchlist_ticker(str(item.get("ticker", "") or ""))
            if not ticker or ticker in watchlist:
                continue
            market = _market_for_ticker(ticker)
            watchlist[ticker] = {
                "ticker": ticker,
                "source": "kis_price_surge",
                "signal_type": "price_surge",
                "name": item.get("name", "") or ticker,
                "fluctuation_rank": item.get("fluctuation_rank"),
                "current_price": item.get("current_price", 0),
                "volume": item.get("volume", 0),
                "change_rate": item.get("change_rate", 0),
                "market": market,
                "currency": _currency_for_market(market),
                "portfolio": False,
                "asset_type": "stock",
            }

        for item in client.get_fluctuation(market="KOSPI", limit=10, direction="down"):
            ticker = _kis_to_watchlist_ticker(str(item.get("ticker", "") or ""))
            if not ticker or ticker in watchlist:
                continue
            market = _market_for_ticker(ticker)
            watchlist[ticker] = {
                "ticker": ticker,
                "source": "kis_price_crash",
                "signal_type": "price_crash",
                "name": item.get("name", "") or ticker,
                "fluctuation_rank": item.get("fluctuation_rank"),
                "current_price": item.get("current_price", 0),
                "volume": item.get("volume", 0),
                "change_rate": item.get("change_rate", 0),
                "market": market,
                "currency": _currency_for_market(market),
                "portfolio": False,
                "asset_type": "stock",
            }

        return watchlist
    except Exception:
        return {}


def load_jackal_watchlist() -> dict[str, dict]:
    """Load JACKAL watchlist from KIS holdings, KIS movers, and candidate_registry."""
    watchlist = _load_kis_holdings_watchlist()
    movers = _load_kis_movers_watchlist()
    for ticker, info in movers.items():
        if ticker not in watchlist:
            watchlist[ticker] = info
    registry = _load_candidate_registry_watchlist()
    for ticker, info in registry.items():
        if ticker not in watchlist:
            watchlist[ticker] = info
    return watchlist
