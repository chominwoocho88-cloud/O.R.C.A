"""Unified daily market-data fetch wrapper for ORCA/JACKAL.

Wave G introduces this module as the public entry point for daily OHLCV
fetches. Existing callers can migrate here gradually while keeping a rollback
switch through USE_UNIFIED_FETCH.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

try:
    import yfinance as yf
except Exception:  # pragma: no cover - runtime degraded path
    yf = None

from .context_market_data import _fetch_with_fallback


_GLOBAL_FETCH_STATS: dict[str, int] = {
    "yfinance_batch_success": 0,
    "yfinance_ticker_success": 0,
    "alpha_vantage_success": 0,
    "failed": 0,
    "total": 0,
}
_LAST_FETCH_SOURCE: dict[str, str] = {}


def fetch_daily_history(
    ticker: str,
    start: str,
    end: str,
    use_fallback: bool | None = None,
) -> pd.DataFrame | None:
    """Fetch daily OHLCV for one ticker.

    Args:
        ticker: yfinance-style ticker such as ``^VIX`` or ``AAPL``.
        start: Inclusive ISO date (YYYY-MM-DD).
        end: Exclusive-ish ISO date as accepted by data providers.
        use_fallback: ``True`` for yfinance->Alpha Vantage cascade,
            ``False`` for direct yfinance rollback, ``None`` to use
            USE_UNIFIED_FETCH (default enabled).

    Returns:
        A normalized DataFrame with at least ``Close`` when available, or
        ``None`` if all providers fail.
    """
    if not str(ticker or "").strip():
        _record_fetch_source(str(ticker or ""), None)
        return None

    if _resolve_use_fallback(use_fallback):
        av_api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
        try:
            data, source = _fetch_with_fallback(ticker, start, end, av_api_key=av_api_key)
            frame = _normalize_history_frame(data)
            if frame is not None and not frame.empty:
                _record_fetch_source(ticker, source)
                return frame
            _record_fetch_source(ticker, None)
            return None
        except Exception as exc:
            _record_fetch_source(ticker, None)
            sys.stderr.write(f"WARN: market_fetch failed for {ticker}: {exc}\n")
            return None

    try:
        data = _download_direct(ticker, start, end)
        frame = _normalize_history_frame(data)
        if frame is not None and not frame.empty:
            _record_fetch_source(ticker, "yfinance_ticker")
            return frame
    except Exception as exc:
        sys.stderr.write(f"WARN: yfinance direct failed for {ticker}: {exc}\n")

    _record_fetch_source(ticker, None)
    return None


def fetch_daily_history_batch(
    tickers: list[str] | tuple[str, ...],
    start: str,
    end: str,
    use_fallback: bool | None = None,
) -> dict[str, pd.DataFrame]:
    """Fetch daily OHLCV for multiple tickers.

    Failed tickers are omitted from the returned dict. In unified mode this
    intentionally loops through ``fetch_daily_history`` so each ticker can fall
    through to Alpha Vantage independently.
    """
    normalized_tickers = [str(ticker).strip() for ticker in tickers if str(ticker).strip()]
    if not normalized_tickers:
        return {}

    if _resolve_use_fallback(use_fallback):
        result: dict[str, pd.DataFrame] = {}
        for ticker in normalized_tickers:
            frame = fetch_daily_history(ticker, start, end, use_fallback=True)
            if frame is not None and not frame.empty:
                result[ticker] = frame
        return result

    try:
        if yf is None:
            raise RuntimeError("yfinance is not available")
        raw = yf.download(
            tickers=normalized_tickers if len(normalized_tickers) > 1 else normalized_tickers[0],
            start=start,
            end=end,
            interval="1d",
            auto_adjust=False,
            group_by="ticker",
            progress=False,
            threads=False,
        )
    except Exception as exc:
        sys.stderr.write(f"WARN: yfinance batch failed: {exc}\n")
        for ticker in normalized_tickers:
            _record_fetch_source(ticker, None)
        return {}

    result = {}
    for ticker in normalized_tickers:
        frame = _extract_batch_ticker_frame(raw, ticker, len(normalized_tickers))
        if frame is not None and not frame.empty:
            result[ticker] = frame
            _record_fetch_source(ticker, "yfinance_batch")
        else:
            _record_fetch_source(ticker, None)
    return result


def fetch_latest_close(
    ticker: str,
    lookback_days: int = 7,
    use_fallback: bool | None = None,
) -> tuple[float, float, str] | None:
    """Fetch latest close, previous-close change percent, and source label."""
    now = datetime.now()
    end = now.date().isoformat()
    start = (now - timedelta(days=max(lookback_days, 1) * 2)).date().isoformat()
    frame = fetch_daily_history(ticker, start, end, use_fallback=use_fallback)
    if frame is None or frame.empty or "Close" not in frame.columns:
        return None

    close = pd.to_numeric(frame["Close"], errors="coerce").dropna()
    if len(close) < 2:
        return None
    latest = float(close.iloc[-1])
    previous = float(close.iloc[-2])
    change_pct = ((latest - previous) / previous * 100) if previous > 0 else 0.0
    return latest, change_pct, _last_fetch_source(ticker) or "unknown"


def fetch_put_call_ratio(
    ticker: str,
    expiry: str | None = None,
    use_yfinance: bool = True,
) -> dict[str, Any] | None:
    """Fetch put/call ratio for one ticker via yfinance options data.

    This is intentionally options-only and isolated from daily OHLCV fallback.
    Alpha Vantage standard market-data endpoints do not replace option chains;
    a future Polygon Options path can be added behind this wrapper.
    """
    if not use_yfinance:
        return None
    if yf is None:
        sys.stderr.write("WARN: fetch_put_call_ratio skipped because yfinance is unavailable\n")
        return None

    try:
        ticker_obj = yf.Ticker(ticker)
        expiries = list(getattr(ticker_obj, "options", []) or [])
        if not expiries:
            return None

        target_expiry = expiry or expiries[0]
        if expiry and expiry not in expiries:
            return None

        chain = ticker_obj.option_chain(target_expiry)
        puts = getattr(chain, "puts", None)
        calls = getattr(chain, "calls", None)
        if puts is None or calls is None or getattr(puts, "empty", True) or getattr(calls, "empty", True):
            return None

        put_volume = _sum_option_column(puts, "volume")
        call_volume = _sum_option_column(calls, "volume")
        put_oi = _sum_option_column(puts, "openInterest")
        call_oi = _sum_option_column(calls, "openInterest")

        return {
            "ticker": str(ticker),
            "expiry": target_expiry,
            "put_volume": put_volume,
            "call_volume": call_volume,
            "put_oi": put_oi,
            "call_oi": call_oi,
            "pcr_volume": round(put_volume / call_volume, 6) if call_volume > 0 else 0.0,
            "pcr_oi": round(put_oi / call_oi, 6) if call_oi > 0 else 0.0,
            "source": "yfinance",
        }
    except Exception as exc:
        sys.stderr.write(f"WARN: fetch_put_call_ratio failed for {ticker}: {exc}\n")
        return None


def fetch_put_call_ratio_summary(
    tickers: tuple[str, ...] = ("SPY", "QQQ"),
    expiries: int = 2,
    sleep_seconds: float = 1.0,
    use_yfinance: bool = True,
) -> dict[str, Any]:
    """Return the legacy ORCA PCR summary while keeping yfinance isolated here."""
    result: dict[str, Any] = {"pcr_spy": None, "pcr_qqq": None, "pcr_avg": None, "pcr_signal": "N/A"}
    pcrs: list[float] = []

    for ticker in tickers:
        pcr_values: list[float] = []
        try:
            available_expiries = _option_expiries(ticker, use_yfinance=use_yfinance)
            for expiry in available_expiries[: max(1, expiries)]:
                detail = fetch_put_call_ratio(ticker, expiry=expiry, use_yfinance=use_yfinance)
                if detail and detail.get("call_volume", 0) > 0:
                    pcr_values.append(float(detail["pcr_volume"]))
            if pcr_values:
                pcr = round(sum(pcr_values) / len(pcr_values), 3)
                pcrs.append(pcr)
                result["pcr_" + ticker.lower()] = pcr
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)
            else:
                sys.stderr.write(f"WARN: PCR {ticker} has no usable option volume\n")
        except Exception as exc:
            sys.stderr.write(f"WARN: PCR {ticker} failed: {exc}\n")

    if pcrs:
        avg = round(sum(pcrs) / len(pcrs), 3)
        result["pcr_avg"] = avg
        result["pcr_signal"] = _pcr_signal(avg)
    return result


def get_fetch_stats() -> dict[str, int]:
    """Return session-level source counters."""
    return dict(_GLOBAL_FETCH_STATS)


def reset_fetch_stats() -> None:
    """Clear session-level source counters and last-source map."""
    _GLOBAL_FETCH_STATS.clear()
    _GLOBAL_FETCH_STATS.update(
        {
            "yfinance_batch_success": 0,
            "yfinance_ticker_success": 0,
            "alpha_vantage_success": 0,
            "failed": 0,
            "total": 0,
        }
    )
    _LAST_FETCH_SOURCE.clear()


def _resolve_use_fallback(use_fallback: bool | None) -> bool:
    """Resolve explicit flag or USE_UNIFIED_FETCH, defaulting to enabled."""
    if use_fallback is not None:
        return bool(use_fallback)
    value = os.getenv("USE_UNIFIED_FETCH", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _record_fetch_source(ticker: str, source: str | None) -> None:
    """Update global counters and per-ticker last-source tracking."""
    _GLOBAL_FETCH_STATS["total"] += 1
    normalized_source = str(source or "").strip() or "failed"
    if normalized_source == "yfinance_batch":
        key = "yfinance_batch_success"
    elif normalized_source == "yfinance_ticker":
        key = "yfinance_ticker_success"
    elif normalized_source == "alpha_vantage":
        key = "alpha_vantage_success"
    else:
        key = "failed"
        normalized_source = "failed"
    _GLOBAL_FETCH_STATS[key] = _GLOBAL_FETCH_STATS.get(key, 0) + 1
    _LAST_FETCH_SOURCE[str(ticker)] = normalized_source


def _last_fetch_source(ticker: str) -> str | None:
    return _LAST_FETCH_SOURCE.get(str(ticker))


def _option_expiries(ticker: str, use_yfinance: bool = True) -> list[str]:
    if not use_yfinance or yf is None:
        return []
    ticker_obj = yf.Ticker(ticker)
    return list(getattr(ticker_obj, "options", []) or [])


def _sum_option_column(frame: Any, column: str) -> float:
    if column not in getattr(frame, "columns", []):
        return 0.0
    series = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    return float(series.sum())


def _pcr_signal(avg: float) -> str:
    if avg >= 1.2:
        return "극단공포"
    if avg >= 0.9:
        return "공포"
    if avg >= 0.7:
        return "중립"
    if avg >= 0.5:
        return "탐욕"
    return "극단탐욕"


def _download_direct(ticker: str, start: str, end: str) -> Any:
    if yf is None:
        raise RuntimeError("yfinance is not available")
    return yf.download(
        tickers=ticker,
        start=start,
        end=end,
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )


def _normalize_history_frame(data: Any) -> pd.DataFrame | None:
    if data is None or getattr(data, "empty", False):
        return None
    frame = data.copy() if hasattr(data, "copy") else pd.DataFrame(data)
    if isinstance(frame.columns, pd.MultiIndex):
        if len(frame.columns.levels) > 1:
            frame.columns = frame.columns.get_level_values(-1)
        else:
            frame.columns = frame.columns.get_level_values(0)
    rename = {}
    for column in frame.columns:
        normalized = str(column).strip().lower().replace("_", " ")
        if normalized == "open":
            rename[column] = "Open"
        elif normalized == "high":
            rename[column] = "High"
        elif normalized == "low":
            rename[column] = "Low"
        elif normalized == "close":
            rename[column] = "Close"
        elif normalized == "volume":
            rename[column] = "Volume"
    frame = frame.rename(columns=rename)
    if "Close" not in frame.columns:
        return None
    try:
        frame.index = pd.to_datetime(frame.index)
    except Exception:
        pass
    return frame


def _extract_batch_ticker_frame(raw: Any, ticker: str, ticker_count: int) -> pd.DataFrame | None:
    if raw is None or getattr(raw, "empty", False):
        return None
    try:
        if ticker_count == 1:
            return _normalize_history_frame(raw)
        if isinstance(raw.columns, pd.MultiIndex):
            if ticker in raw.columns.get_level_values(0):
                return _normalize_history_frame(raw[ticker])
            if ticker in raw.columns.get_level_values(-1):
                return _normalize_history_frame(raw.xs(ticker, axis=1, level=-1))
        if ticker in raw:
            return _normalize_history_frame(raw[ticker])
    except Exception:
        return None
    return None
