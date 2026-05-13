"""Phase 9-3 JACKAL prediction-card outcome resolver."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import pandas as pd

from apps.orca import state
from shared.market_data.fetch import fetch_daily_history


KST = timezone(timedelta(hours=9))
DEFAULT_HORIZONS = (1, 3, 5)
_CLOSE_COLUMNS = {1: "actual_close_d1", 3: "actual_close_d3", 5: "actual_close_d5"}
_OUTCOME_COLUMNS = {1: "outcome_d1", 3: "outcome_d3", 5: "outcome_d5"}


def _now() -> datetime:
    return datetime.now(KST)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def _entry_price(card: dict[str, Any]) -> float | None:
    return _to_float(card.get("current_price") or card.get("entry_price_low"))


def _row_value(row: Any, *names: str) -> Any:
    if isinstance(row, dict):
        for name in names:
            if name in row:
                return row[name]
            lowered = name.lower()
            if lowered in row:
                return row[lowered]
    return None


def _history_rows(frame: Any, *, after: datetime | None = None) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if isinstance(frame, list):
        raw_rows = frame
    elif isinstance(frame, pd.DataFrame):
        data = frame.copy()
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        raw_rows = []
        for idx, row in data.iterrows():
            item = row.to_dict()
            item["date"] = idx
            raw_rows.append(item)
    else:
        return []

    rows: list[dict[str, Any]] = []
    after_date = after.date() if after else None
    for raw in raw_rows:
        raw_date = _row_value(raw, "date", "Date", "timestamp")
        try:
            date = pd.Timestamp(raw_date).date()
        except Exception:
            continue
        if after_date and date <= after_date:
            continue
        close = _to_float(_row_value(raw, "close", "Close"))
        high = _to_float(_row_value(raw, "high", "High"))
        low = _to_float(_row_value(raw, "low", "Low"))
        if close is None:
            continue
        rows.append(
            {
                "date": date.isoformat(),
                "close": close,
                "high": high if high is not None else close,
                "low": low if low is not None else close,
            }
        )
    return sorted(rows, key=lambda row: row["date"])


def _get_price_history(ticker: str, created_at: datetime, as_of: datetime) -> list[dict[str, Any]]:
    """Fetch post-card daily history through the shared KIS/yfinance fetch chain."""
    start = created_at.date().isoformat()
    end = (as_of + timedelta(days=1)).date().isoformat()
    frame = fetch_daily_history(ticker, start, end, use_fallback=True)
    return _history_rows(frame, after=created_at)


def _target_stop(card: dict[str, Any], horizon_day: int) -> tuple[float | None, float | None, bool]:
    target = _to_float(card.get("target_price"))
    stop = _to_float(card.get("stop_price"))
    explicit = target is not None or stop is not None
    if explicit:
        return target, stop, True

    entry = _entry_price(card)
    if entry is None or entry <= 0:
        return None, None, False
    target_pct = 0.005 if horizon_day == 1 else 0.01
    stop_pct = 0.005 if horizon_day == 1 else 0.01
    return entry * (1 + target_pct), entry * (1 - stop_pct), False


def _calculate_outcome(
    card: dict[str, Any],
    price_history: list[dict[str, Any]],
    horizon_day: int,
) -> dict[str, Any] | None:
    """Calculate one horizon outcome for a normalized prediction card."""
    if horizon_day <= 0 or len(price_history) < horizon_day:
        return None

    window = price_history[:horizon_day]
    actual_high = max(float(row["high"]) for row in window)
    actual_low = min(float(row["low"]) for row in window)
    actual_close = float(window[-1]["close"])

    target, stop, explicit = _target_stop(card, horizon_day)
    outcome = "neutral"
    if target is not None and actual_high >= target:
        outcome = "win"
    elif stop is not None and actual_low <= stop:
        outcome = "loss"
    elif not explicit and target is not None and actual_high < target:
        outcome = "neutral"

    return {
        "horizon_day": horizon_day,
        "outcome": outcome,
        "actual_high": actual_high,
        "actual_low": actual_low,
        "actual_close": actual_close,
    }


def _load_open_cards(conn, max_cards: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
          FROM jackal_prediction_cards
         WHERE status = 'open'
         ORDER BY created_at ASC
         LIMIT ?
        """,
        (max_cards,),
    ).fetchall()
    return [dict(row) for row in rows]


def _update_card_outcomes(conn, card: dict[str, Any], outcomes: dict[int, dict[str, Any]], as_of: datetime) -> bool:
    if not outcomes:
        return False

    updates: dict[str, Any] = {
        "actual_high": max(result["actual_high"] for result in outcomes.values()),
        "actual_low": min(result["actual_low"] for result in outcomes.values()),
    }
    for horizon, result in outcomes.items():
        close_col = _CLOSE_COLUMNS.get(horizon)
        outcome_col = _OUTCOME_COLUMNS.get(horizon)
        if close_col and outcome_col:
            updates[close_col] = result["actual_close"]
            updates[outcome_col] = result["outcome"]

    if 5 in outcomes:
        updates["status"] = "resolved"
        updates["resolved_at"] = as_of.isoformat()

    assignments = ", ".join(f"{key} = ?" for key in updates)
    conn.execute(
        f"UPDATE jackal_prediction_cards SET {assignments} WHERE card_id = ?",
        tuple(updates.values()) + (card["card_id"],),
    )
    return True


def _resolve_shadow_signals(
    *,
    as_of: datetime,
    max_signals: int,
    price_fetcher: Callable[[str, datetime, datetime], list[dict[str, Any]]] | None,
) -> dict[str, int]:
    stats = {"resolved": 0, "still_open": 0, "errors": 0}
    with state._connect_jackal() as conn:
        rows = conn.execute(
            """
            SELECT shadow_id, signal_timestamp, ticker, payload_json
              FROM jackal_shadow_signals
             WHERE status = 'open'
             ORDER BY signal_timestamp ASC
             LIMIT ?
            """,
            (max_signals,),
        ).fetchall()

    for row in rows:
        payload = json.loads(row["payload_json"] or "{}")
        created_at = _parse_dt(row["signal_timestamp"])
        if created_at is None or (as_of - created_at).days < 5:
            stats["still_open"] += 1
            continue
        card = {
            "current_price": payload.get("price_at_scan") or payload.get("current_price"),
            "target_price": payload.get("target_price"),
            "stop_price": payload.get("stop_price"),
        }
        try:
            history = (price_fetcher or _get_price_history)(row["ticker"], created_at, as_of)
            result = _calculate_outcome(card, history, 5)
            if not result:
                stats["still_open"] += 1
                continue
            outcome = {
                "outcome_d5": result["outcome"],
                "shadow_swing_ok": result["outcome"] == "win",
                "actual_high": result["actual_high"],
                "actual_low": result["actual_low"],
                "actual_close_d5": result["actual_close"],
                "resolved_by": "phase9_3_outcome_resolver",
                "resolved_at": as_of.isoformat(),
            }
            state.resolve_jackal_shadow_signal(row["shadow_id"], outcome)
            stats["resolved"] += 1
        except Exception:
            stats["errors"] += 1
    return stats


def resolve_open_prediction_cards(
    horizon_days: list[int] | tuple[int, ...] = DEFAULT_HORIZONS,
    *,
    max_cards: int = 50,
    max_shadow_signals: int = 50,
    as_of: datetime | None = None,
    price_fetcher: Callable[[str, datetime, datetime], list[dict[str, Any]]] | None = None,
    include_shadow: bool = True,
) -> dict[str, Any]:
    """Resolve open JACKAL prediction cards across 1D/3D/5D horizons."""
    state.init_state_db()
    as_of = (as_of or _now()).astimezone(KST)
    horizons = tuple(sorted({int(day) for day in horizon_days if int(day) in _OUTCOME_COLUMNS}))
    stats: dict[str, Any] = {
        "checked": 0,
        "updated": 0,
        "resolved": 0,
        "still_open": 0,
        "skipped_not_aged": 0,
        "errors": [],
        "shadow": {"resolved": 0, "still_open": 0, "errors": 0},
    }

    with state._connect_jackal() as conn:
        cards = _load_open_cards(conn, max_cards)
        for card in cards:
            stats["checked"] += 1
            created_at = _parse_dt(card.get("created_at"))
            if created_at is None:
                stats["errors"].append({"card_id": card.get("card_id"), "error": "invalid_created_at"})
                continue

            eligible = [day for day in horizons if (as_of - created_at).days >= day]
            if not eligible:
                stats["skipped_not_aged"] += 1
                stats["still_open"] += 1
                continue

            try:
                history = (price_fetcher or _get_price_history)(card["ticker"], created_at, as_of)
                outcomes = {}
                for day in eligible:
                    result = _calculate_outcome(card, history, day)
                    if result:
                        outcomes[day] = result
                if not _update_card_outcomes(conn, card, outcomes, as_of):
                    stats["still_open"] += 1
                    continue
                stats["updated"] += 1
                if 5 in outcomes:
                    stats["resolved"] += 1
                else:
                    stats["still_open"] += 1
            except Exception as exc:
                stats["errors"].append({"card_id": card.get("card_id"), "error": type(exc).__name__})

    if include_shadow:
        stats["shadow"] = _resolve_shadow_signals(
            as_of=as_of,
            max_signals=max_shadow_signals,
            price_fetcher=price_fetcher,
        )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve JACKAL prediction-card outcomes")
    parser.add_argument("--max-cards", type=int, default=50)
    parser.add_argument("--max-shadow-signals", type=int, default=50)
    parser.add_argument("--no-shadow", action="store_true")
    args = parser.parse_args()
    result = resolve_open_prediction_cards(
        max_cards=args.max_cards,
        max_shadow_signals=args.max_shadow_signals,
        include_shadow=not args.no_shadow,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
