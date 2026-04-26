"""ORCA Daily historical context helpers.

This module is intentionally separate from JACKAL's historical context helper.
ORCA uses historical retrieval for report context only: no score adjustment and
no write path.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

from . import state
from .lesson_retrieval import retrieve_similar_lessons_for_features


NUMERIC_FEATURES = (
    "vix_level",
    "sp500_momentum_5d",
    "sp500_momentum_20d",
    "nasdaq_momentum_5d",
    "nasdaq_momentum_20d",
)


def historical_context_enabled() -> bool:
    """Return whether ORCA Daily should attach historical context."""
    return str(os.getenv("USE_HISTORICAL_CONTEXT", "1")).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def build_market_features(source: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Resolve snapshot-like market features for retrieval.

    ORCA reports do not always carry 5d/20d momentum fields. When a report or
    market-data payload lacks the full feature set, use the latest existing
    context snapshot as a read-only fallback.
    """
    source = source or {}
    for key in ("historical_context_features", "market_features", "context_features", "context_snapshot"):
        nested = source.get(key)
        if _is_complete_features(nested):
            return _normalize_features(nested)

    if _is_complete_features(source):
        return _normalize_features(source)

    return _latest_snapshot_features()


def get_market_historical_context(
    market_features: dict[str, Any] | None = None,
    top_k: int = 20,
    quality_filter: str = "high",
    recency_decay_days: float | None = 365,
    as_of_date: str | None = None,
    log_retrieval: bool = False,
    source_system: str = "orca_pipeline",
    source_event_type: str | None = "live",
    source_event_id: str | None = None,
    backtest_run_id: str | None = None,
) -> dict[str, Any] | None:
    """Get read-only historical context for ORCA Daily reporting."""
    if not historical_context_enabled():
        return None

    features = build_market_features(market_features)
    if not features:
        return None

    try:
        lessons = retrieve_similar_lessons_for_features(
            features=features,
            top_k=top_k,
            quality_filter=quality_filter,
            as_of_date=as_of_date,
            recency_decay_days=recency_decay_days,
            log_retrieval=log_retrieval,
            source_system=source_system,
            source_event_type=source_event_type,
            source_event_id=source_event_id,
            trading_date=as_of_date,
            mode="observe",
            backtest_run_id=backtest_run_id,
        )
        if not lessons:
            return None

        values = [float(lesson.get("lesson_value") or 0.0) for lesson in lessons]
        win_rate = sum(1 for value in values if value > 0) / len(values)
        avg_value = sum(values) / len(values)
        high_quality_count = sum(1 for lesson in lessons if lesson.get("quality_tier") == "high")
        cluster_id = lessons[0].get("cluster_id")

        return {
            "cluster_id": cluster_id,
            "cluster_label": lessons[0].get("cluster_label"),
            "cluster_size": _cluster_size(cluster_id, fallback=len(lessons)),
            "top_lessons": [_compact_lesson(lesson) for lesson in lessons],
            "win_rate": win_rate,
            "avg_value": avg_value,
            "high_quality_count": high_quality_count,
        }
    except Exception as exc:
        sys.stderr.write(f"WARN: ORCA historical context failed: {exc}\n")
        return None


def _compact_lesson(lesson: dict[str, Any]) -> dict[str, Any]:
    return {
        "lesson_id": lesson.get("lesson_id"),
        "ticker": lesson.get("ticker"),
        "analysis_date": lesson.get("analysis_date"),
        "signal_family": lesson.get("signal_family"),
        "lesson_value": lesson.get("lesson_value"),
        "peak_pct": lesson.get("peak_pct"),
        "peak_day": lesson.get("peak_day"),
        "quality_tier": lesson.get("quality_tier"),
        "relevance_score": lesson.get("relevance_score"),
        "cluster_id": lesson.get("cluster_id"),
        "cluster_label": lesson.get("cluster_label"),
    }


def _cluster_size(cluster_id: Any, fallback: int = 0) -> int:
    if not cluster_id:
        return fallback
    try:
        state.init_state_db()
        with state._connect_orca() as conn:
            cluster = state.get_cluster_by_id(conn, str(cluster_id)) or {}
        return int(cluster.get("sample_count") or cluster.get("size") or fallback)
    except Exception:
        return fallback


def _is_complete_features(value: Any) -> bool:
    return isinstance(value, dict) and all(_float_or_none(value.get(name)) is not None for name in NUMERIC_FEATURES)


def _normalize_features(features: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(features)
    for name in NUMERIC_FEATURES:
        normalized[name] = _float_or_none(normalized.get(name)) or 0.0
    normalized["regime"] = _normalize_regime(
        normalized.get("regime") or normalized.get("market_regime")
    )
    normalized["dominant_sectors"] = _normalize_sectors(
        normalized.get("dominant_sectors")
        or normalized.get("top_sectors")
        or normalized.get("sectors")
        or _sectors_from_inflows(normalized.get("inflows"))
    )
    return normalized


def _normalize_regime(regime: Any) -> str:
    text = str(regime or "").strip().lower()
    if "회피" in text or "risk-off" in text or "riskoff" in text:
        return "위험회피"
    if "선호" in text or "risk-on" in text or "riskon" in text:
        return "위험선호"
    if "전환" in text or "transition" in text:
        return "전환중"
    return "전환중"


def _normalize_sectors(sectors: Any) -> list[str]:
    if isinstance(sectors, str):
        try:
            decoded = json.loads(sectors)
            sectors = decoded if isinstance(decoded, list) else [sectors]
        except Exception:
            sectors = [sectors]
    return [str(sector) for sector in (sectors or []) if str(sector).strip()]


def _sectors_from_inflows(inflows: Any) -> list[str]:
    if not isinstance(inflows, list):
        return []
    sectors = []
    for item in inflows[:3]:
        if isinstance(item, dict) and item.get("zone"):
            sectors.append(str(item["zone"]))
    return sectors


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        text = str(value).replace("%", "").replace("+", "").replace(",", "").strip()
        if text in {"", "N/A", "nan", "None"}:
            return None
        return float(text)
    except Exception:
        return None


def _latest_snapshot_features() -> dict[str, Any] | None:
    try:
        state.init_state_db()
        with state._connect_orca() as conn:
            row = conn.execute(
                """
                SELECT regime, vix_level, sp500_momentum_5d, sp500_momentum_20d,
                       nasdaq_momentum_5d, nasdaq_momentum_20d, dominant_sectors
                  FROM lesson_context_snapshot
                 WHERE vix_level IS NOT NULL
                   AND sp500_momentum_5d IS NOT NULL
                   AND sp500_momentum_20d IS NOT NULL
                   AND nasdaq_momentum_5d IS NOT NULL
                   AND nasdaq_momentum_20d IS NOT NULL
                 ORDER BY trading_date DESC, created_at DESC
                 LIMIT 1
                """
            ).fetchone()
        if not row:
            return None
        return _normalize_features(
            {
                "regime": row["regime"],
                "vix_level": row["vix_level"],
                "sp500_momentum_5d": row["sp500_momentum_5d"],
                "sp500_momentum_20d": row["sp500_momentum_20d"],
                "nasdaq_momentum_5d": row["nasdaq_momentum_5d"],
                "nasdaq_momentum_20d": row["nasdaq_momentum_20d"],
                "dominant_sectors": row["dominant_sectors"],
            }
        )
    except Exception:
        return None
