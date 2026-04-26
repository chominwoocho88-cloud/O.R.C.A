"""Market-data fetch helpers for Wave F context backfill."""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from io import StringIO
from typing import Any

import pandas as pd

try:
    import yfinance as yf
except Exception:  # pragma: no cover - degraded runtime fallback
    yf = None


_YFINANCE_MAX_RETRIES = 3
_ALPHA_VANTAGE_MAX_RETRIES = 2
ALPHA_VANTAGE_SLEEP_DEFAULT = 12.0

ALPHA_VANTAGE_TICKER_MAP = {
    "^VIX": "VIXY",
    "^GSPC": "SPY",
    "^IXIC": "QQQ",
}


def fetch_historical_market_data_range(
    tickers: tuple[str, ...],
    min_date: str,
    max_date: str,
    buffer_days: int = 90,
) -> dict[str, list[tuple[str, float]]]:
    """Fetch and normalize all historical market data needed for backfill."""
    try:
        start = datetime.fromisoformat(min_date) - timedelta(days=buffer_days)
        end = datetime.fromisoformat(max_date) + timedelta(days=1)
    except ValueError:
        return {ticker: [] for ticker in tickers}

    start_iso = start.date().isoformat()
    end_iso = end.date().isoformat()
    av_api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    stats = {
        "yfinance_batch_success": 0,
        "yfinance_ticker_success": 0,
        "alpha_vantage_success": 0,
        "failed": 0,
    }
    result: dict[str, list[tuple[str, float]]] = {ticker: [] for ticker in tickers}

    if yf is not None:
        try:
            batch = _fetch_yfinance_batch_with_retry(tickers, start_iso, end_iso)
            parsed = _split_downloaded_history(batch, tickers)
            for ticker, points in parsed.items():
                if points:
                    result[ticker] = points
                    stats["yfinance_batch_success"] += 1
        except Exception as exc:
            print(f"yfinance batch failed after retries: {type(exc).__name__}: {str(exc)[:120]}")

    for ticker in tickers:
        if result[ticker]:
            continue
        frame, source = _fetch_with_fallback(ticker, start_iso, end_iso, av_api_key=av_api_key)
        if source and frame is not None:
            result[ticker] = _points_from_frame(frame)
            stats[f"{source}_success"] += 1
        else:
            stats["failed"] += 1

    print(
        "Backfill market data sources: "
        f"yfinance_batch_success={stats['yfinance_batch_success']}, "
        f"yfinance_ticker_success={stats['yfinance_ticker_success']}, "
        f"alpha_vantage_success={stats['alpha_vantage_success']}, "
        f"failed={stats['failed']}"
    )
    return result


def _fetch_yfinance_batch_with_retry(
    tickers: tuple[str, ...],
    start: str,
    end: str,
    max_retries: int = _YFINANCE_MAX_RETRIES,
) -> Any:
    """Fetch a yfinance batch with exponential backoff."""
    if yf is None:
        raise RuntimeError("yfinance is not available")
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            data = yf.download(
                tickers=list(tickers),
                start=start,
                end=end,
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
                group_by="ticker",
            )
            if data is not None and not getattr(data, "empty", True):
                return data
        except Exception as exc:
            last_error = exc
        if attempt < max_retries - 1:
            delay = _retry_delay_seconds(attempt)
            print(
                f"Batch retry {attempt + 1}/{max_retries} after {delay}s "
                f"({type(last_error).__name__ if last_error else 'empty'})"
            )
            time.sleep(delay)
    if last_error:
        raise last_error
    return None


def _fetch_yfinance_ticker_with_retry(
    ticker: str,
    start: str,
    end: str,
    max_retries: int = _YFINANCE_MAX_RETRIES,
) -> Any:
    """Fetch one yfinance ticker with retry and ticker-level pacing."""
    if yf is None:
        raise RuntimeError("yfinance is not available")
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            time.sleep(1)
            data = yf.download(
                tickers=ticker,
                start=start,
                end=end,
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
            )
            if data is not None and not getattr(data, "empty", True):
                return data
        except Exception as exc:
            last_error = exc
        if attempt < max_retries - 1:
            delay = _retry_delay_seconds(attempt)
            time.sleep(delay)
    if last_error:
        raise last_error
    return None


def _fetch_with_fallback(
    ticker: str,
    start: str,
    end: str,
    av_api_key: str | None = None,
) -> tuple[Any | None, str | None]:
    """Cascade per-ticker fetch: yfinance first, then Alpha Vantage."""
    errors: list[str] = []
    try:
        data = _fetch_yfinance_ticker_with_retry(ticker, start, end)
        if data is not None and not getattr(data, "empty", True):
            return data, "yfinance_ticker"
    except Exception as exc:
        errors.append(f"yfinance: {type(exc).__name__}: {str(exc)[:100]}")

    if av_api_key:
        try:
            data = _fetch_alpha_vantage_with_retry(ticker, start, end, av_api_key)
            if data is not None and not getattr(data, "empty", True):
                return data, "alpha_vantage"
        except Exception as exc:
            errors.append(f"alpha_vantage: {type(exc).__name__}: {str(exc)[:100]}")

    print(f"  All fetches failed for {ticker}: {errors}")
    return None, None


def _get_alpha_vantage_sleep_seconds() -> float:
    """Return Alpha Vantage pacing seconds from env, defaulting to free-tier safe."""
    try:
        value = float(os.getenv("ALPHA_VANTAGE_SLEEP_SECONDS", ALPHA_VANTAGE_SLEEP_DEFAULT))
        return max(0.0, value)
    except (TypeError, ValueError):
        return ALPHA_VANTAGE_SLEEP_DEFAULT


def _fetch_alpha_vantage_with_retry(
    ticker: str,
    start: str,
    end: str,
    api_key: str | None = None,
    max_retries: int = _ALPHA_VANTAGE_MAX_RETRIES,
) -> pd.DataFrame | None:
    """Fetch Alpha Vantage with free-tier pacing and retry."""
    last_error: Exception | None = None
    sleep_seconds = _get_alpha_vantage_sleep_seconds()
    for attempt in range(max_retries):
        try:
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
            data = _fetch_alpha_vantage_history(ticker, start, end, api_key)
            if data is not None and not data.empty:
                return data
        except Exception as exc:
            last_error = exc
        if attempt < max_retries - 1:
            time.sleep(15)
    if last_error:
        raise last_error
    return None


def _fetch_alpha_vantage_history(
    ticker: str,
    start: str,
    end: str,
    api_key: str | None = None,
) -> pd.DataFrame | None:
    """Fetch daily OHLCV from Alpha Vantage TIME_SERIES_DAILY."""
    import requests

    if not api_key:
        api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        raise ValueError("ALPHA_VANTAGE_API_KEY not available")

    av_ticker = _alpha_vantage_ticker(ticker)
    for outputsize in ("full", "compact"):
        response = requests.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "TIME_SERIES_DAILY",
                "symbol": av_ticker,
                "outputsize": outputsize,
                "apikey": api_key,
                "datatype": "csv",
            },
            timeout=30,
        )
        response.raise_for_status()
        text = response.text.strip()
        if _looks_like_alpha_vantage_error(text):
            if outputsize == "full":
                continue
            raise RuntimeError(f"Alpha Vantage error for {ticker}: {text[:200]}")

        frame = _parse_alpha_vantage_csv(text, start, end)
        if frame is not None and not frame.empty:
            return frame
        if outputsize == "compact":
            raise RuntimeError(f"Alpha Vantage empty response for {ticker}")
    return None


def _alpha_vantage_ticker(yfinance_ticker: str) -> str:
    """Map a yfinance ticker to the Alpha Vantage symbol namespace."""
    return ALPHA_VANTAGE_TICKER_MAP.get(yfinance_ticker, yfinance_ticker)


def _looks_like_alpha_vantage_error(text: str) -> bool:
    lower = text.lower()
    return (
        not text
        or text.startswith("{")
        or "information" in lower
        or "error message" in lower
        or "thank you for using alpha vantage" in lower
        or "premium" in lower
        or "our standard api rate limit" in lower
    )


def _parse_alpha_vantage_csv(text: str, start: str, end: str) -> pd.DataFrame | None:
    try:
        frame = pd.read_csv(StringIO(text))
    except Exception as exc:
        raise RuntimeError(f"Alpha Vantage CSV parse failed: {exc}") from exc
    if frame.empty:
        return frame

    rename: dict[str, str] = {}
    for column in frame.columns:
        normalized = str(column).strip().lower()
        if normalized == "timestamp":
            rename[column] = "Date"
        elif normalized in {"open", "high", "low", "close", "volume"}:
            rename[column] = normalized.capitalize()
    frame = frame.rename(columns=rename)
    if "Date" not in frame.columns or "Close" not in frame.columns:
        raise RuntimeError("Alpha Vantage CSV missing Date/Close columns")

    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame = frame.dropna(subset=["Date"])
    frame = frame.set_index("Date").sort_index()
    start_ts = pd.to_datetime(start)
    end_ts = pd.to_datetime(end)
    frame = frame[(frame.index >= start_ts) & (frame.index <= end_ts)]
    for column in ("Open", "High", "Low", "Close", "Volume"):
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def _split_downloaded_history(
    downloaded: Any,
    tickers: tuple[str, ...],
) -> dict[str, list[tuple[str, float]]]:
    result: dict[str, list[tuple[str, float]]] = {}
    columns = getattr(downloaded, "columns", None)
    for ticker in tickers:
        frame = None
        if columns is not None and getattr(columns, "nlevels", 1) > 1:
            try:
                frame = downloaded[ticker]
            except Exception:
                frame = None
        elif len(tickers) == 1:
            frame = downloaded
        result[ticker] = _points_from_frame(frame)
    return result


def _points_from_frame(frame: Any) -> list[tuple[str, float]]:
    if frame is None:
        return []
    columns = getattr(frame, "columns", [])
    close_column = None
    if "Adj Close" in columns:
        close_column = "Adj Close"
    elif "Close" in columns:
        close_column = "Close"
    if close_column is None:
        return []

    points: list[tuple[str, float]] = []
    try:
        iterator = frame.iterrows()
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


def _retry_delay_seconds(attempt: int) -> int:
    return 2 * ((attempt + 1) ** 2)
