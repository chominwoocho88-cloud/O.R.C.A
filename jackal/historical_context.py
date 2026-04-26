"""Historical context retrieval helpers for JACKAL Hunter."""
from __future__ import annotations

import json
import os
import sys
from typing import Any

from orca import state
from orca.lesson_retrieval import retrieve_similar_lessons_for_features


NUMERIC_FEATURES = (
    "vix_level",
    "sp500_momentum_5d",
    "sp500_momentum_20d",
    "nasdaq_momentum_5d",
    "nasdaq_momentum_20d",
)


def historical_context_enabled() -> bool:
    return str(os.getenv("USE_HISTORICAL_CONTEXT", "1")).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def historical_context_mode() -> str:
    mode = str(os.getenv("HISTORICAL_CONTEXT_MODE", "observe")).strip().lower()
    return "adjust" if mode == "adjust" else "observe"


def market_features_from_aria(aria: dict[str, Any] | None) -> dict[str, Any] | None:
    """Resolve current market features without creating snapshots."""
    aria = aria or {}
    for key in ("historical_context_features", "market_features", "context_features"):
        features = aria.get(key)
        if _is_complete_features(features):
            return _normalize_features(features)
    if _is_complete_features(aria):
        return _normalize_features(aria)
    return _latest_snapshot_features()


def try_retrieve_historical_context(
    market_features: dict[str, Any] | None,
    signal_family: str | None,
    candidate_data: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Retrieve top historical lessons with graceful fallback."""
    if not historical_context_enabled() or not market_features:
        return None
    try:
        lessons = retrieve_similar_lessons_for_features(
            features=market_features,
            top_k=5,
            signal_family=signal_family,
            quality_filter="high",
        )
        if not lessons:
            return None
        values = [float(lesson.get("lesson_value") or 0.0) for lesson in lessons]
        win_rate = sum(1 for value in values if value > 0) / len(values)
        avg_value = sum(values) / len(values)
        high_quality_count = sum(1 for lesson in lessons if lesson.get("quality_tier") == "high")
        cluster_distance = (
            lessons[0].get("target_distance_to_cluster")
            if lessons[0].get("target_distance_to_cluster") is not None
            else lessons[0].get("distance_to_centroid")
        )
        return {
            "cluster_id": lessons[0].get("cluster_id"),
            "cluster_label": lessons[0].get("cluster_label"),
            "cluster_distance": cluster_distance,
            "lessons": [_compact_lesson(lesson) for lesson in lessons],
            "win_rate": win_rate,
            "avg_value": avg_value,
            "high_quality_count": high_quality_count,
            "mode": historical_context_mode(),
        }
    except Exception as exc:
        sys.stderr.write(f"WARN: historical_context retrieve failed: {exc}\n")
        return None


def calculate_score_adjustment(historical_context: dict[str, Any] | None) -> float:
    """Calculate capped Hunter score adjustment for adjust mode."""
    if not historical_context:
        return 0.0
    win_rate = float(historical_context.get("win_rate", 0.5) or 0.5)
    avg_value = float(historical_context.get("avg_value", 0.0) or 0.0)
    high_quality_count = int(historical_context.get("high_quality_count", 0) or 0)
    win_rate_factor = (win_rate - 0.5) * 2.0
    value_factor = max(-1.0, min(1.0, avg_value / 10.0))
    quality_multiplier = 1.0 + (min(5, max(0, high_quality_count)) / 5.0) * 0.5
    adjustment = (win_rate_factor * 2.5 + value_factor * 2.5) * quality_multiplier
    return max(-5.0, min(5.0, adjustment))


def apply_historical_adjustment(final: dict[str, Any], historical_context: dict[str, Any] | None) -> dict[str, Any]:
    """Apply historical context only in adjust mode; observe mode is read-only."""
    if not historical_context:
        return final
    final = dict(final)
    final["historical_context_mode"] = historical_context.get("mode", "observe")
    if historical_context.get("mode") != "adjust":
        final.setdefault("historical_adjustment", 0.0)
        return final
    adjustment = calculate_score_adjustment(historical_context)
    old_score = float(final.get("final_score", 0.0) or 0.0)
    new_score = max(0.0, min(100.0, old_score + adjustment))
    final["final_score"] = round(new_score, 1)
    final["historical_adjustment"] = round(adjustment, 2)
    threshold = float(final.get("entry_threshold", 0.0) or 0.0)
    if threshold:
        final["is_entry"] = final["final_score"] >= threshold and final.get("mode") != "차단"
    return final


def historical_alert_lines(
    historical_context: dict[str, Any] | None,
    final: dict[str, Any] | None = None,
) -> list[str]:
    if not historical_context:
        return []
    lines = [
        "━━━━━━━━━━━━━━━━━━━━",
        "Historical Context",
        f"Cluster: {historical_context.get('cluster_label') or historical_context.get('cluster_id')}",
        f"Win rate (top 5): {float(historical_context.get('win_rate', 0.0)) * 100:.0f}%",
        f"Avg value: {float(historical_context.get('avg_value', 0.0)):+.2f}%",
    ]
    adjustment = (final or {}).get("historical_adjustment")
    if historical_context.get("mode") == "adjust" and adjustment is not None:
        lines.append(f"Score adjustment: {float(adjustment):+.2f}")
    examples = historical_context.get("lessons") or []
    if examples:
        lines.append("Similar examples:")
        for lesson in examples[:3]:
            value = float(lesson.get("lesson_value") or 0.0)
            date = str(lesson.get("analysis_date") or "")[:10]
            lines.append(
                f"  - {lesson.get('ticker')} ({date}): {value:+.2f}% [{lesson.get('quality_tier')}]"
            )
    return lines


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
    }


def _is_complete_features(value: Any) -> bool:
    return isinstance(value, dict) and all(value.get(name) is not None for name in NUMERIC_FEATURES)


def _normalize_features(features: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(features)
    normalized["regime"] = _normalize_regime(normalized.get("regime"))
    normalized["dominant_sectors"] = _normalize_sectors(normalized.get("dominant_sectors"))
    return normalized


def _normalize_regime(regime: Any) -> str:
    text = str(regime or "").strip().lower()
    if "회피" in text or "risk-off" in text or "riskoff" in text:
        return "위험회피"
    if "선호" in text or "risk-on" in text or "riskon" in text:
        return "위험선호"
    return "전환중"


def _normalize_sectors(sectors: Any) -> list[str]:
    if isinstance(sectors, str):
        try:
            decoded = json.loads(sectors)
            sectors = decoded if isinstance(decoded, list) else [sectors]
        except Exception:
            sectors = [sectors]
    return [str(sector) for sector in (sectors or [])]


def _latest_snapshot_features() -> dict[str, Any] | None:
    try:
        state.init_state_db()
        conn = state._connect_orca()
        try:
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
        finally:
            conn.close()
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
