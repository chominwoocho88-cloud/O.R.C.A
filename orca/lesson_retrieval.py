"""Wave F Phase 3: read-only historical lesson retrieval."""
from __future__ import annotations

import bisect
import math
import sqlite3
from datetime import datetime
from typing import Any

from . import lesson_clustering
from . import state


RELEVANCE_WEIGHTS = {
    "quality": 0.45,
    "context": 0.25,
    "signal": 0.20,
    "recency": 0.10,
}
VALID_QUALITY_TIERS = {"high", "medium", "low"}


def retrieve_similar_lessons(
    candidate_id: str | None = None,
    analysis_date: str | None = None,
    snapshot_id: str | None = None,
    features: dict[str, Any] | None = None,
    top_k: int = 10,
    quality_filter: str | None = None,
    signal_family: str | None = None,
    as_of_date: str | None = None,
    recency_decay_days: float | None = None,
    allow_create_snapshot: bool = False,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Retrieve historical lessons from the most similar market context cluster."""
    if not any([candidate_id, analysis_date, snapshot_id, features]):
        raise ValueError("candidate_id, analysis_date, snapshot_id, or features is required")

    own_conn = conn is None
    if own_conn:
        state.init_state_db()
        conn = state._connect_orca()
    assert conn is not None
    try:
        context = _resolve_context(
            conn,
            candidate_id=candidate_id,
            analysis_date=analysis_date,
            snapshot_id=snapshot_id,
            features=features,
            allow_create_snapshot=allow_create_snapshot,
        )
        target_signal_family = signal_family or context.get("signal_family")
        target_cluster_id, target_distance = _find_target_cluster(
            conn,
            context.get("snapshot_id"),
            context.get("features"),
        )
        if not target_cluster_id:
            return []
        lessons = _fetch_candidate_lessons(conn, target_cluster_id, as_of_date=as_of_date)
        archive_by_lesson = _archive_lookup_for_lessons(
            conn,
            [lesson.get("lesson_id") for lesson in lessons],
        )
        return _rank_lessons(
            lessons,
            target_cluster_id=target_cluster_id,
            target_distance=target_distance,
            top_k=top_k,
            quality_filter=quality_filter,
            target_signal_family=target_signal_family,
            signal_filter=signal_family,
            as_of_date=as_of_date,
            recency_decay_days=recency_decay_days,
            archive_by_lesson=archive_by_lesson,
        )
    finally:
        if own_conn and conn is not None:
            conn.close()


def retrieve_similar_lessons_for_features(
    features: dict[str, Any],
    top_k: int = 10,
    quality_filter: str | None = None,
    signal_family: str | None = None,
    as_of_date: str | None = None,
    recency_decay_days: float | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Retrieve similar historical lessons for a direct feature dictionary."""
    return retrieve_similar_lessons(
        features=features,
        top_k=top_k,
        quality_filter=quality_filter,
        signal_family=signal_family,
        as_of_date=as_of_date,
        recency_decay_days=recency_decay_days,
        allow_create_snapshot=False,
        conn=conn,
    )


def _resolve_context(
    conn: sqlite3.Connection,
    candidate_id: str | None,
    analysis_date: str | None,
    snapshot_id: str | None,
    features: dict[str, Any] | None,
    allow_create_snapshot: bool,
) -> dict[str, Any]:
    """Resolve retrieval input into a snapshot id and/or feature dictionary."""
    if snapshot_id:
        snapshot = _get_snapshot_features(conn, snapshot_id)
        if not snapshot:
            raise LookupError(f"context snapshot not found: {snapshot_id}")
        return {"snapshot_id": snapshot_id, "features": snapshot}

    if candidate_id:
        candidate = _get_candidate_context(conn, candidate_id)
        if not candidate:
            raise LookupError(f"candidate not found: {candidate_id}")
        resolved_date = analysis_date or candidate.get("analysis_date")
        resolved = _resolve_snapshot_for_date(
            conn,
            resolved_date,
            allow_create_snapshot=allow_create_snapshot,
            source_event_type=_snapshot_source_for_candidate(candidate.get("source_event_type")),
            source_session_id=candidate.get("source_session_id"),
        )
        resolved["candidate"] = candidate
        resolved["signal_family"] = candidate.get("signal_family")
        return resolved

    if analysis_date:
        return _resolve_snapshot_for_date(
            conn,
            analysis_date,
            allow_create_snapshot=allow_create_snapshot,
            source_event_type="live",
            source_session_id=None,
        )

    if features:
        return {"snapshot_id": None, "features": features}

    raise ValueError("candidate_id, analysis_date, snapshot_id, or features is required")


def _find_target_cluster(
    conn: sqlite3.Connection,
    snapshot_id: str | None,
    features: dict[str, Any] | None,
) -> tuple[str | None, float | None]:
    """Find target cluster from cached snapshot assignment or feature distance."""
    if snapshot_id:
        snapshot = _get_snapshot_features(conn, snapshot_id)
        if snapshot and snapshot.get("context_cluster_id"):
            distance = _distance_for_snapshot(conn, snapshot_id, snapshot["context_cluster_id"])
            return snapshot["context_cluster_id"], distance
        features = features or snapshot

    if features:
        cluster_id, distance = lesson_clustering.find_nearest_cluster(features, conn=conn)
        return cluster_id, distance

    return None, None


def _fetch_candidate_lessons(
    conn: sqlite3.Connection,
    cluster_id: str,
    as_of_date: str | None = None,
) -> list[dict[str, Any]]:
    """Get lessons in one cluster and apply optional look-ahead filter."""
    lessons = lesson_clustering.get_lessons_in_cluster(cluster_id, conn=conn)
    cluster = state.get_cluster_by_id(conn, cluster_id) or {}
    distances = _snapshot_distances(conn, cluster_id)

    enriched = []
    for lesson in lessons:
        lesson_date = _lesson_analysis_date(lesson)
        if as_of_date and lesson_date and not (lesson_date < as_of_date[:10]):
            continue
        payload = lesson.get("lesson") or {}
        snapshot_id = lesson.get("context_snapshot_id")
        item = dict(lesson)
        item.update(
            {
                "analysis_date": lesson_date,
                "cluster_id": cluster_id,
                "cluster_label": cluster.get("cluster_label"),
                "distance_to_centroid": distances.get(snapshot_id),
                "signals_fired": payload.get("signals_fired") or [],
                "peak_pct": payload.get("peak_pct"),
                "peak_day": payload.get("peak_day"),
            }
        )
        enriched.append(item)
    return enriched


def _calculate_quality_score(lesson_value: float | None, all_values: list[float]) -> float:
    """Return percentile rank, avoiding raw-value outlier dominance."""
    sorted_vals = sorted(float(value) for value in all_values if value is not None)
    if not sorted_vals:
        return 0.5
    if lesson_value is None:
        return 0.5
    if len(sorted_vals) == 1:
        return 1.0
    rank = bisect.bisect_right(sorted_vals, float(lesson_value))
    return max(0.0, min(1.0, rank / len(sorted_vals)))


def _calculate_context_score(
    lesson_cluster_id: str,
    target_cluster_id: str,
    distance_to_centroid: float | None,
) -> float:
    """Score cluster match and centroid proximity."""
    if lesson_cluster_id != target_cluster_id:
        return 0.0
    base = 0.7
    if distance_to_centroid is None:
        return base + 0.15
    distance_factor = max(0.0, 1.0 - (float(distance_to_centroid) / 3.0))
    return base + (0.3 * distance_factor)


def _calculate_signal_score(
    lesson_signal_family: str | None,
    target_signal_family: str | None,
) -> float:
    """Score signal-family match."""
    if not target_signal_family or not lesson_signal_family:
        return 0.5
    return 1.0 if lesson_signal_family == target_signal_family else 0.0


def _calculate_recency_score(
    lesson_date: str | None,
    as_of_date: str | None,
    decay_days: float | None,
) -> float:
    """Score recency with optional exponential decay."""
    if decay_days is None:
        return 1.0
    try:
        reference = datetime.fromisoformat((as_of_date or datetime.now().date().isoformat())[:10])
        lesson_dt = datetime.fromisoformat(str(lesson_date)[:10])
        days_old = max(0, (reference - lesson_dt).days)
        return math.exp(-days_old / float(decay_days))
    except Exception:
        return 1.0


def _calculate_relevance_score(
    quality_score: float,
    context_score: float,
    signal_score: float,
    recency_score: float,
) -> float:
    """Weighted relevance score used for top-K ranking."""
    return (
        RELEVANCE_WEIGHTS["quality"] * quality_score
        + RELEVANCE_WEIGHTS["context"] * context_score
        + RELEVANCE_WEIGHTS["signal"] * signal_score
        + RELEVANCE_WEIGHTS["recency"] * recency_score
    )


def _classify_quality_tier(percentile: float) -> str:
    if percentile > 0.67:
        return "high"
    if percentile > 0.33:
        return "medium"
    return "low"


def _filter_by_quality(lessons: list[dict[str, Any]], filter_tier: str | None) -> list[dict[str, Any]]:
    if not filter_tier:
        return lessons
    tier = filter_tier.lower().strip()
    if tier not in VALID_QUALITY_TIERS:
        raise ValueError(f"quality_filter must be one of {sorted(VALID_QUALITY_TIERS)}")
    return [lesson for lesson in lessons if lesson.get("quality_tier") == tier]


def _filter_by_signal(lessons: list[dict[str, Any]], target_family: str | None) -> list[dict[str, Any]]:
    if not target_family:
        return lessons
    return [lesson for lesson in lessons if lesson.get("signal_family") == target_family]


def _archive_lookup_for_lessons(
    conn: sqlite3.Connection,
    lesson_ids: list[Any],
) -> dict[str, dict[str, Any]]:
    """Load latest archive scores for candidate lessons when an archive exists."""
    clean_ids = sorted({str(lesson_id) for lesson_id in lesson_ids if lesson_id})
    if not clean_ids:
        return {}
    run_id = state.get_latest_archive_run_id(conn)
    if not run_id:
        return {}
    placeholders = ", ".join("?" for _ in clean_ids)
    rows = conn.execute(
        f"""
        SELECT lesson_id, run_id, quality_tier, quality_score,
               outcome_percentile, win_score, speed_score, signal_score,
               cluster_fit_score
          FROM lesson_archive
         WHERE run_id = ?
           AND lesson_id IN ({placeholders})
        """,
        (run_id, *clean_ids),
    ).fetchall()
    archive_by_lesson: dict[str, dict[str, Any]] = {}
    for row in rows:
        lesson_id = str(_row_value(row, "lesson_id", 0))
        archive_by_lesson[lesson_id] = {
            "lesson_id": lesson_id,
            "archive_run_id": _row_value(row, "run_id", 1),
            "quality_tier": _row_value(row, "quality_tier", 2),
            "quality_score": _row_value(row, "quality_score", 3),
            "outcome_percentile": _row_value(row, "outcome_percentile", 4),
            "win_score": _row_value(row, "win_score", 5),
            "speed_score": _row_value(row, "speed_score", 6),
            "archive_signal_score": _row_value(row, "signal_score", 7),
            "cluster_fit_score": _row_value(row, "cluster_fit_score", 8),
        }
    return archive_by_lesson


def _rank_lessons(
    lessons: list[dict[str, Any]],
    *,
    target_cluster_id: str,
    target_distance: float | None,
    top_k: int,
    quality_filter: str | None,
    target_signal_family: str | None,
    signal_filter: str | None,
    as_of_date: str | None,
    recency_decay_days: float | None,
    archive_by_lesson: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    all_values = [float(item["lesson_value"]) for item in lessons if item.get("lesson_value") is not None]
    ranked = []
    for item in lessons:
        archive = (archive_by_lesson or {}).get(str(item.get("lesson_id")))
        if archive:
            quality_score = float(archive.get("quality_score") or 0.5)
            quality_tier = str(archive.get("quality_tier") or _classify_quality_tier(quality_score))
        else:
            quality_score = _calculate_quality_score(item.get("lesson_value"), all_values)
            quality_tier = _classify_quality_tier(quality_score)
        context_score = _calculate_context_score(
            item.get("cluster_id") or "",
            target_cluster_id,
            item.get("distance_to_centroid"),
        )
        signal_score = _calculate_signal_score(item.get("signal_family"), target_signal_family)
        recency_score = _calculate_recency_score(
            item.get("analysis_date"),
            as_of_date,
            recency_decay_days,
        )
        relevance_score = _calculate_relevance_score(
            quality_score,
            context_score,
            signal_score,
            recency_score,
        )
        payload = item.get("lesson") or {}
        ranked.append(
            {
                "lesson_id": item.get("lesson_id"),
                "ticker": payload.get("ticker") or item.get("ticker"),
                "signal_family": item.get("signal_family") or payload.get("signal_family"),
                "lesson_value": item.get("lesson_value"),
                "quality_tier": quality_tier,
                "relevance_score": relevance_score,
                "quality_score": quality_score,
                "context_score": context_score,
                "signal_score": signal_score,
                "recency_score": recency_score,
                "archive_run_id": archive.get("archive_run_id") if archive else None,
                "outcome_percentile": archive.get("outcome_percentile") if archive else None,
                "win_score": archive.get("win_score") if archive else None,
                "speed_score": archive.get("speed_score") if archive else None,
                "archive_signal_score": archive.get("archive_signal_score") if archive else None,
                "cluster_fit_score": archive.get("cluster_fit_score") if archive else None,
                "cluster_id": item.get("cluster_id"),
                "cluster_label": item.get("cluster_label"),
                "analysis_date": item.get("analysis_date"),
                "signals_fired": item.get("signals_fired") or [],
                "peak_pct": item.get("peak_pct"),
                "peak_day": item.get("peak_day"),
                "distance_to_centroid": item.get("distance_to_centroid"),
                "target_distance_to_cluster": target_distance,
            }
        )
    ranked = _filter_by_quality(ranked, quality_filter)
    ranked = _filter_by_signal(ranked, signal_filter)
    ranked.sort(
        key=lambda item: (
            item["relevance_score"],
            item["quality_score"],
            float(item["lesson_value"] or 0.0),
            str(item["analysis_date"] or ""),
        ),
        reverse=True,
    )
    if top_k <= 0:
        return []
    return ranked[:top_k]


def _resolve_snapshot_for_date(
    conn: sqlite3.Connection,
    analysis_date: str | None,
    *,
    allow_create_snapshot: bool,
    source_event_type: str,
    source_session_id: str | None,
) -> dict[str, Any]:
    if not analysis_date:
        raise LookupError("analysis_date is required to resolve context snapshot")
    snapshot = _find_snapshot_for_date(conn, analysis_date)
    if snapshot:
        return {"snapshot_id": snapshot["snapshot_id"], "features": snapshot}
    if not allow_create_snapshot:
        raise LookupError(f"context snapshot not found for analysis_date={analysis_date}")

    from .context_snapshot import get_or_create_context_snapshot

    snapshot_id = get_or_create_context_snapshot(
        analysis_date[:10],
        source_event_type,
        source_session_id=source_session_id,
        conn=conn,
    )
    snapshot = _get_snapshot_features(conn, snapshot_id)
    if not snapshot:
        raise LookupError(f"context snapshot creation failed for analysis_date={analysis_date}")
    return {"snapshot_id": snapshot_id, "features": snapshot}


def _get_candidate_context(conn: sqlite3.Connection, candidate_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT candidate_id, analysis_date, source_event_type, source_session_id, signal_family
          FROM candidate_registry
         WHERE candidate_id = ?
        """,
        (candidate_id,),
    ).fetchone()
    if not row:
        return None
    return {
        "candidate_id": _row_value(row, "candidate_id", 0),
        "analysis_date": _row_value(row, "analysis_date", 1),
        "source_event_type": _row_value(row, "source_event_type", 2),
        "source_session_id": _row_value(row, "source_session_id", 3),
        "signal_family": _row_value(row, "signal_family", 4),
    }


def _find_snapshot_for_date(conn: sqlite3.Connection, analysis_date: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT snapshot_id, created_at, trading_date, regime, regime_confidence,
               vix_level, vix_delta_7d, sp500_momentum_5d, sp500_momentum_20d,
               nasdaq_momentum_5d, nasdaq_momentum_20d, dominant_sectors,
               context_cluster_id, source_event_type, source_session_id
          FROM lesson_context_snapshot
         WHERE trading_date = ?
         ORDER BY
               CASE source_event_type
                   WHEN 'live' THEN 0
                   WHEN 'backtest' THEN 1
                   WHEN 'backtest_backfill' THEN 2
                   ELSE 3
               END,
               created_at ASC
         LIMIT 1
        """,
        (analysis_date[:10],),
    ).fetchone()
    return _snapshot_row_to_features(row) if row else None


def _get_snapshot_features(conn: sqlite3.Connection, snapshot_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT snapshot_id, created_at, trading_date, regime, regime_confidence,
               vix_level, vix_delta_7d, sp500_momentum_5d, sp500_momentum_20d,
               nasdaq_momentum_5d, nasdaq_momentum_20d, dominant_sectors,
               context_cluster_id, source_event_type, source_session_id
          FROM lesson_context_snapshot
         WHERE snapshot_id = ?
        """,
        (snapshot_id,),
    ).fetchone()
    return _snapshot_row_to_features(row) if row else None


def _snapshot_row_to_features(row: Any) -> dict[str, Any]:
    sectors = state._decode_json_text(_row_value(row, "dominant_sectors", 11), [])
    return {
        "snapshot_id": _row_value(row, "snapshot_id", 0),
        "created_at": _row_value(row, "created_at", 1),
        "trading_date": _row_value(row, "trading_date", 2),
        "regime": _row_value(row, "regime", 3),
        "regime_confidence": _row_value(row, "regime_confidence", 4),
        "vix_level": _row_value(row, "vix_level", 5),
        "vix_delta_7d": _row_value(row, "vix_delta_7d", 6),
        "sp500_momentum_5d": _row_value(row, "sp500_momentum_5d", 7),
        "sp500_momentum_20d": _row_value(row, "sp500_momentum_20d", 8),
        "nasdaq_momentum_5d": _row_value(row, "nasdaq_momentum_5d", 9),
        "nasdaq_momentum_20d": _row_value(row, "nasdaq_momentum_20d", 10),
        "dominant_sectors": sectors,
        "context_cluster_id": _row_value(row, "context_cluster_id", 12),
        "source_event_type": _row_value(row, "source_event_type", 13),
        "source_session_id": _row_value(row, "source_session_id", 14),
    }


def _snapshot_distances(conn: sqlite3.Connection, cluster_id: str) -> dict[str, float | None]:
    rows = conn.execute(
        """
        SELECT snapshot_id, distance_to_centroid
          FROM snapshot_cluster_mapping
         WHERE cluster_id = ?
        """,
        (cluster_id,),
    ).fetchall()
    return {
        _row_value(row, "snapshot_id", 0): _row_value(row, "distance_to_centroid", 1)
        for row in rows
    }


def _distance_for_snapshot(conn: sqlite3.Connection, snapshot_id: str, cluster_id: str) -> float | None:
    row = conn.execute(
        """
        SELECT distance_to_centroid
          FROM snapshot_cluster_mapping
         WHERE snapshot_id = ?
           AND cluster_id = ?
         ORDER BY run_id DESC
         LIMIT 1
        """,
        (snapshot_id, cluster_id),
    ).fetchone()
    return _row_value(row, "distance_to_centroid", 0) if row else None


def _lesson_analysis_date(lesson: dict[str, Any]) -> str | None:
    payload = lesson.get("lesson") or {}
    return str(
        lesson.get("analysis_date")
        or payload.get("analysis_date")
        or str(lesson.get("lesson_timestamp") or "")[:10]
        or ""
    )[:10] or None


def _snapshot_source_for_candidate(source_event_type: str | None) -> str:
    source = str(source_event_type or "").strip().lower()
    if source in {"hunt", "scan", "shadow"}:
        return "live"
    if source == "backtest":
        return "backtest"
    return source or "live"


def _row_value(row: Any, key: str, index: int, default: Any = None) -> Any:
    if row is None:
        return default
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        try:
            return row[index]
        except (TypeError, KeyError, IndexError):
            return default
