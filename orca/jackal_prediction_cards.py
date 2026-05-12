"""Normalized JACKAL prediction card persistence helpers."""
from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any


KST = timezone(timedelta(hours=9))


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jackal_prediction_cards (
    card_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    event_kind TEXT NOT NULL,
    ticker TEXT NOT NULL,
    name TEXT,
    score REAL NOT NULL,
    day1_score REAL,
    swing_score REAL,
    devil_score REAL,
    devil_verdict TEXT,
    current_price REAL,
    entry_price_low REAL,
    entry_price_high REAL,
    target_price REAL,
    stop_price REAL,
    horizon_days INTEGER,
    pattern_label TEXT,
    main_reasoning TEXT,
    market_regime TEXT,
    fear_greed INTEGER,
    fear_greed_label TEXT,
    inflow_sectors TEXT,
    created_at TEXT NOT NULL,
    build_hash TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    resolved_at TEXT,
    actual_high REAL,
    actual_low REAL,
    actual_close_d1 REAL,
    actual_close_d3 REAL,
    actual_close_d5 REAL,
    outcome_d1 TEXT,
    outcome_d3 TEXT,
    outcome_d5 TEXT,
    FOREIGN KEY(event_id) REFERENCES jackal_live_events(event_id)
);

CREATE INDEX IF NOT EXISTS idx_prediction_cards_status
    ON jackal_prediction_cards(status);

CREATE INDEX IF NOT EXISTS idx_prediction_cards_created
    ON jackal_prediction_cards(created_at);

CREATE INDEX IF NOT EXISTS idx_prediction_cards_ticker
    ON jackal_prediction_cards(ticker);
"""


def migrate_jackal_prediction_cards(conn: sqlite3.Connection) -> None:
    """Create normalized prediction-card tables and indexes."""
    conn.executescript(SCHEMA_SQL)


def _now_iso() -> str:
    return datetime.now(KST).isoformat()


def _json(data: Any) -> str | None:
    if data is None:
        return None
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value is not None and value != "":
            return value
    return None


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def _to_int(value: Any) -> int | None:
    number = _to_float(value)
    if number is None:
        return None
    return int(number)


def _json_or_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, (list, tuple, dict)):
        return _json(value)
    return str(value)


def _reason_text(payload: dict[str, Any]) -> str | None:
    value = _first_present(payload, "reason_detail", "reason", "bull_case", "main_reasoning")
    if value:
        return str(value)
    for key in ("quality_reasons", "signals_fired", "devil_objections"):
        items = payload.get(key)
        if isinstance(items, list) and items:
            return " | ".join(str(item) for item in items)
    return None


def _outcome_label(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"win", "loss", "neutral"}:
            return lowered
        if lowered in {"true", "1", "yes"}:
            return "win"
        if lowered in {"false", "0", "no"}:
            return "loss"
        return "neutral"
    return "win" if bool(value) else "loss"


def _normalize_inflow_sectors(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text[0] in "[{":
            try:
                parsed = json.loads(text)
            except Exception:
                return []
            if isinstance(parsed, list):
                return _normalize_inflow_sectors(parsed)
            return []
        return [text]
    return []


def _alpha_signal_payload_from_prediction_card_values(
    values: dict[str, Any],
    raw_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project normalized prediction-card values into an AlphaSignal payload."""
    raw_payload = raw_payload if isinstance(raw_payload, dict) else {}
    created_at = values.get("created_at")
    raw_inflow_sectors = raw_payload.get("inflow_sectors")
    inflow_source = (
        raw_inflow_sectors
        if isinstance(raw_inflow_sectors, list)
        else values.get("inflow_sectors")
    )

    payload = {
        "event_id": values.get("event_id"),
        "source_system": "jackal",
        "event_type": "alpha_signal",
        "occurred_at": created_at,
        "ticker": values.get("ticker"),
        "score": values.get("score"),
        "name": values.get("name"),
        "day1_score": values.get("day1_score"),
        "swing_score": values.get("swing_score"),
        "devil_score": values.get("devil_score"),
        "devil_verdict": values.get("devil_verdict"),
        "current_price": values.get("current_price"),
        "entry_price_low": values.get("entry_price_low"),
        "entry_price_high": values.get("entry_price_high"),
        "target_price": values.get("target_price"),
        "stop_price": values.get("stop_price"),
        "horizon_days": values.get("horizon_days"),
        "pattern_label": values.get("pattern_label"),
        "main_reasoning": values.get("main_reasoning"),
        "market_regime": values.get("market_regime"),
        "fear_greed": values.get("fear_greed"),
        "fear_greed_label": values.get("fear_greed_label"),
        "inflow_sectors": _normalize_inflow_sectors(inflow_source),
        "alerted": True,
        "build_hash": values.get("build_hash"),
    }
    if created_at:
        payload["analysis_date"] = str(created_at).split("T", 1)[0]
    return payload


def _prediction_card_values(
    event_id: str,
    event_kind: str,
    payload: dict[str, Any],
    *,
    build_hash: str | None = None,
) -> dict[str, Any] | None:
    payload = deepcopy(payload or {})
    if not payload.get("alerted"):
        return None

    ticker = str(payload.get("ticker") or "").strip()
    created_at = str(payload.get("timestamp") or payload.get("created_at") or _now_iso())
    if not ticker or not created_at:
        return None

    outcome_checked = bool(payload.get("outcome_checked"))
    current_price = _to_float(
        _first_present(payload, "current_price", "price_at_hunt", "price_at_scan", "price")
    )
    score = _to_float(_first_present(payload, "final_score", "quality_score", "score")) or 0.0
    resolved_at = str(payload.get("outcome_tracked_at") or _now_iso()) if outcome_checked else None

    return {
        "card_id": f"card_{event_id}",
        "event_id": event_id,
        "event_kind": event_kind,
        "ticker": ticker,
        "name": payload.get("name"),
        "score": score,
        "day1_score": _to_float(payload.get("day1_score")),
        "swing_score": _to_float(payload.get("swing_score")),
        "devil_score": _to_float(payload.get("devil_score")),
        "devil_verdict": payload.get("devil_verdict") or payload.get("verdict"),
        "current_price": current_price,
        "entry_price_low": _to_float(_first_present(payload, "entry_price_low", "entry_low")),
        "entry_price_high": _to_float(_first_present(payload, "entry_price_high", "entry_high")),
        "target_price": _to_float(_first_present(payload, "target_price", "target")),
        "stop_price": _to_float(_first_present(payload, "stop_price", "stop")),
        "horizon_days": _to_int(_first_present(payload, "horizon_days", "horizon")) or 5,
        "pattern_label": _first_present(
            payload,
            "pattern_label",
            "signal_family_label",
            "signal_type",
            "quality_label",
            "entry_mode",
            "swing_setup",
        ),
        "main_reasoning": _reason_text(payload),
        "market_regime": _first_present(payload, "market_regime", "orca_regime", "regime"),
        "fear_greed": _to_int(
            _first_present(payload, "fear_greed", "fear_greed_value", "orca_fear_greed")
        ),
        "fear_greed_label": _first_present(payload, "fear_greed_label", "fear_greed_state"),
        "inflow_sectors": _json_or_text(
            _first_present(payload, "inflow_sectors", "orca_inflows", "key_inflows")
        ),
        "created_at": created_at,
        "build_hash": build_hash or payload.get("build_hash") or payload.get("build"),
        "status": "resolved" if outcome_checked else "open",
        "resolved_at": resolved_at,
        "actual_high": _to_float(payload.get("price_peak")),
        "actual_low": _to_float(payload.get("actual_low")),
        "actual_close_d1": _to_float(payload.get("price_1d_later")),
        "actual_close_d3": _to_float(payload.get("actual_close_d3")),
        "actual_close_d5": _to_float(_first_present(payload, "price_5d_later", "outcome_price")),
        "outcome_d1": _outcome_label(payload.get("outcome_1d_hit")),
        "outcome_d3": _outcome_label(payload.get("outcome_d3")),
        "outcome_d5": _outcome_label(
            _first_present(payload, "outcome_swing_hit", "outcome_correct")
        ),
    }


def record_jackal_prediction_card_conn(
    conn: sqlite3.Connection,
    event_id: str,
    event_kind: str,
    payload: dict[str, Any],
    *,
    build_hash: str | None = None,
) -> str | None:
    """Persist a normalized JACKAL prediction card for alerted live events."""
    values = _prediction_card_values(event_id, event_kind, payload, build_hash=build_hash)
    if not values:
        return None

    columns = list(values.keys())
    placeholders = ", ".join("?" for _ in columns)
    updates = ", ".join(
        f"{column} = excluded.{column}"
        for column in columns
        if column not in {"card_id", "event_id"}
    )
    conn.execute(
        f"""
        INSERT INTO jackal_prediction_cards ({", ".join(columns)})
        VALUES ({placeholders})
        ON CONFLICT(event_id) DO UPDATE SET {updates}
        """,
        tuple(values[column] for column in columns),
    )
    return str(values["card_id"])
