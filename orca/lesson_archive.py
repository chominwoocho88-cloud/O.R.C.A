"""Wave F Phase 3: lesson archive quality scoring."""
from __future__ import annotations

import bisect
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any
from uuid import uuid4

from . import state


QUALITY_WEIGHTS = {
    "outcome": 0.40,
    "win": 0.25,
    "speed": 0.15,
    "signal": 0.10,
    "cluster_fit": 0.10,
}
VALID_TIERS = {"high", "medium", "low"}


def build_lesson_archive(
    cluster_run_id: str | None = None,
    random_seed: int = 42,
    conn: sqlite3.Connection | None = None,
    dry_run: bool = True,
    verbose: bool = False,
) -> dict[str, Any]:
    """Build denormalized lesson archive rows with multi-dimensional quality."""
    own_conn = conn is None
    if own_conn:
        state.init_state_db()
        conn = state._connect_orca()
    assert conn is not None

    try:
        cluster_run_id = cluster_run_id or state.get_latest_run_id(conn)
        if not cluster_run_id:
            raise LookupError("no clustering run found; build clusters before archiving")

        archive_run_id = (
            f"archive_run_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"
        )
        lessons = _load_clustered_lessons(conn, cluster_run_id)
        all_values = [
            float(item["lesson_value"])
            for item in lessons
            if item.get("lesson_value") is not None
        ]
        signal_scores = _signal_family_reliability(lessons)

        archive_rows: list[dict[str, Any]] = []
        for item in lessons:
            payload = _decode_lesson_payload(item.get("lesson_json"))
            lesson_value = _to_float(item.get("lesson_value"))
            signal_family = str(
                item.get("signal_family") or payload.get("signal_family") or ""
            )
            ticker = str(item.get("ticker") or payload.get("ticker") or "")
            peak_pct = _to_float(payload.get("peak_pct"))
            if peak_pct is None:
                peak_pct = lesson_value
            peak_day = _to_int(payload.get("peak_day"))
            distance = _to_float(item.get("distance_to_centroid"))

            outcome_percentile = _calculate_outcome_percentile(lesson_value, all_values)
            win_score = _calculate_win_score(lesson_value, signal_family)
            speed_score = _calculate_speed_score(peak_day, peak_pct)
            signal_score = signal_scores.get(signal_family, 0.5)
            cluster_fit_score = _calculate_cluster_fit_score(distance)
            quality_score = _composite_quality_score(
                outcome_percentile,
                win_score,
                speed_score,
                signal_score,
                cluster_fit_score,
            )
            quality_tier = _classify_tier(quality_score)
            lesson_id = str(item["lesson_id"])
            archive_id = f"{archive_run_id}_{lesson_id}"

            archive_rows.append(
                {
                    "archive_id": archive_id,
                    "lesson_id": lesson_id,
                    "cluster_id": item["cluster_id"],
                    "run_id": archive_run_id,
                    "cluster_run_id": cluster_run_id,
                    "quality_tier": quality_tier,
                    "quality_score": quality_score,
                    "outcome_percentile": outcome_percentile,
                    "win_score": win_score,
                    "speed_score": speed_score,
                    "signal_score": signal_score,
                    "cluster_fit_score": cluster_fit_score,
                    "lesson_value": lesson_value,
                    "peak_pct": peak_pct,
                    "peak_day": peak_day,
                    "signal_family": signal_family,
                    "ticker": ticker,
                    "analysis_date": item.get("analysis_date"),
                }
            )

        if not dry_run:
            for row in archive_rows:
                state.record_lesson_archive(
                    conn,
                    row["archive_id"],
                    row["lesson_id"],
                    row["cluster_id"],
                    row["run_id"],
                    row["quality_tier"],
                    row["quality_score"],
                    row["outcome_percentile"],
                    row["win_score"],
                    row["speed_score"],
                    row["signal_score"],
                    row["cluster_fit_score"],
                    row["lesson_value"],
                    row["peak_pct"],
                    row["peak_day"],
                    row["signal_family"],
                    row["ticker"],
                    row["analysis_date"],
                )
            conn.commit()

        result = _summarize_archive(
            archive_run_id=archive_run_id,
            cluster_run_id=cluster_run_id,
            rows=archive_rows,
            dry_run=dry_run,
            random_seed=random_seed,
        )
        if verbose:
            print(
                "Wave F archive dry_run={dry_run} cluster_run_id={cluster_run_id} "
                "archive_run_id={archive_run_id}".format(
                    dry_run=dry_run,
                    cluster_run_id=cluster_run_id,
                    archive_run_id=archive_run_id,
                )
            )
            print(
                "  archive_count={count} avg_quality={avg:.4f}".format(
                    count=result["archive_count"],
                    avg=result["avg_quality_score"],
                )
            )
            print("  tiers=" + str(result["tier_distribution"]))
        return result
    finally:
        if own_conn and conn is not None:
            conn.close()


def _calculate_outcome_percentile(
    lesson_value: float | None,
    all_values: list[float],
) -> float:
    """Return percentile rank for the lesson outcome."""
    values = sorted(float(value) for value in all_values if value is not None)
    if not values:
        return 0.5
    if lesson_value is None:
        return 0.5
    if len(values) == 1:
        return 1.0
    rank = bisect.bisect_right(values, float(lesson_value))
    return _clamp(rank / len(values))


def _calculate_win_score(lesson_value: float | None, signal_family: str | None) -> float:
    """Score whether the lesson reflects a positive historical outcome."""
    if lesson_value is None:
        return 0.5
    return 1.0 if float(lesson_value) > 0 else 0.0


def _calculate_speed_score(peak_day: int | None, peak_pct: float | None) -> float:
    """Score how efficiently the lesson reached its peak."""
    if peak_pct is None or float(peak_pct) <= 0:
        return 0.0
    if peak_day is None:
        return 0.5
    if peak_day <= 3:
        return 1.0
    if peak_day <= 7:
        return 0.7
    if peak_day <= 15:
        return 0.4
    return 0.2


def _calculate_signal_score(signal_family: str | None, conn: sqlite3.Connection | None = None) -> float:
    """Return signal-family reliability from historical candidate lessons."""
    if not signal_family:
        return 0.5
    own_conn = conn is None
    if own_conn:
        state.init_state_db()
        conn = state._connect_orca()
    assert conn is not None
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN l.lesson_value > 0 THEN 1 ELSE 0 END) AS wins
              FROM candidate_lessons l
              JOIN candidate_registry c
                ON c.candidate_id = l.candidate_id
             WHERE c.signal_family = ?
            """,
            (signal_family,),
        ).fetchone()
        total = int(_row_value(row, "total", 0, 0) or 0)
        if total <= 0:
            return 0.5
        wins = int(_row_value(row, "wins", 1, 0) or 0)
        return _clamp(wins / total)
    finally:
        if own_conn and conn is not None:
            conn.close()


def _calculate_cluster_fit_score(distance_to_centroid: float | None) -> float:
    """Score how close the snapshot is to the cluster centroid."""
    if distance_to_centroid is None:
        return 0.5
    return _clamp(1.0 - (max(0.0, float(distance_to_centroid)) / 3.0))


def _composite_quality_score(
    outcome_percentile: float,
    win_score: float,
    speed_score: float,
    signal_score: float,
    cluster_fit_score: float,
) -> float:
    """Weighted composite quality score."""
    return _clamp(
        QUALITY_WEIGHTS["outcome"] * outcome_percentile
        + QUALITY_WEIGHTS["win"] * win_score
        + QUALITY_WEIGHTS["speed"] * speed_score
        + QUALITY_WEIGHTS["signal"] * signal_score
        + QUALITY_WEIGHTS["cluster_fit"] * cluster_fit_score
    )


def _classify_tier(quality_score: float) -> str:
    """Classify a composite quality score."""
    if quality_score > 0.67:
        return "high"
    if quality_score > 0.33:
        return "medium"
    return "low"


def _load_clustered_lessons(conn: sqlite3.Connection, cluster_run_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT l.lesson_id, l.lesson_type, l.label, l.lesson_value, l.lesson_json,
               c.ticker, c.analysis_date, c.signal_family,
               m.cluster_id, m.distance_to_centroid
          FROM candidate_lessons l
          JOIN candidate_registry c
            ON c.candidate_id = l.candidate_id
          JOIN snapshot_cluster_mapping m
            ON m.snapshot_id = l.context_snapshot_id
           AND m.run_id = ?
         WHERE l.context_snapshot_id IS NOT NULL
         ORDER BY c.analysis_date, c.ticker, l.lesson_timestamp
        """,
        (cluster_run_id,),
    ).fetchall()
    return [
        {
            "lesson_id": _row_value(row, "lesson_id", 0),
            "lesson_type": _row_value(row, "lesson_type", 1),
            "label": _row_value(row, "label", 2),
            "lesson_value": _row_value(row, "lesson_value", 3),
            "lesson_json": _row_value(row, "lesson_json", 4),
            "ticker": _row_value(row, "ticker", 5),
            "analysis_date": _row_value(row, "analysis_date", 6),
            "signal_family": _row_value(row, "signal_family", 7),
            "cluster_id": _row_value(row, "cluster_id", 8),
            "distance_to_centroid": _row_value(row, "distance_to_centroid", 9),
        }
        for row in rows
    ]


def _signal_family_reliability(lessons: list[dict[str, Any]]) -> dict[str, float]:
    totals: Counter[str] = Counter()
    wins: Counter[str] = Counter()
    for item in lessons:
        payload = _decode_lesson_payload(item.get("lesson_json"))
        family = str(item.get("signal_family") or payload.get("signal_family") or "")
        if not family:
            continue
        totals[family] += 1
        value = _to_float(item.get("lesson_value"))
        if value is not None and value > 0:
            wins[family] += 1
    return {family: _clamp(wins[family] / total) for family, total in totals.items() if total}


def _summarize_archive(
    *,
    archive_run_id: str,
    cluster_run_id: str,
    rows: list[dict[str, Any]],
    dry_run: bool,
    random_seed: int,
) -> dict[str, Any]:
    tiers = Counter(row["quality_tier"] for row in rows)
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        clusters[row["cluster_id"]].append(row)

    cluster_summary = []
    for cluster_id, cluster_rows in sorted(clusters.items()):
        values = [row["quality_score"] for row in cluster_rows]
        tier_counts = Counter(row["quality_tier"] for row in cluster_rows)
        cluster_summary.append(
            {
                "cluster_id": cluster_id,
                "archive_count": len(cluster_rows),
                "avg_quality_score": _safe_average(values),
                "tier_distribution": dict(tier_counts),
                "top_lesson_id": max(
                    cluster_rows,
                    key=lambda row: (
                        row["quality_score"],
                        row["lesson_value"] if row["lesson_value"] is not None else 0.0,
                    ),
                )["lesson_id"]
                if cluster_rows
                else None,
            }
        )

    quality_values = [row["quality_score"] for row in rows]
    return {
        "archive_run_id": archive_run_id,
        "cluster_run_id": cluster_run_id,
        "archive_count": len(rows),
        "tier_distribution": {
            "high": tiers.get("high", 0),
            "medium": tiers.get("medium", 0),
            "low": tiers.get("low", 0),
        },
        "cluster_summary": cluster_summary,
        "avg_quality_score": _safe_average(quality_values),
        "dry_run": dry_run,
        "random_seed": random_seed,
    }


def _decode_lesson_payload(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        decoded = json.loads(value)
        return decoded if isinstance(decoded, dict) else {}
    except Exception:
        return {}


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _safe_average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


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
