"""Wave F Phase 2: context snapshot clustering.

This module is intentionally dependency-light. It uses numpy only so the
clustering engine can run in GitHub Actions and local environments without
adding sklearn/scipy.
"""
from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter
from datetime import datetime
from typing import Any
from uuid import uuid4

import numpy as np

from . import state


NUMERICAL_FEATURES = (
    "vix_level",
    "sp500_momentum_5d",
    "sp500_momentum_20d",
    "nasdaq_momentum_5d",
    "nasdaq_momentum_20d",
)
REGIME_ORDER = ("위험회피", "전환중", "위험선호")
SECTOR_ORDER = (
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Financials",
    "Health Care",
    "Healthcare",
    "Industrials",
    "Materials",
    "Real Estate",
    "Technology",
    "Utilities",
)
CANONICAL_SECTOR_ORDER = (
    "Communication Services",
    "Consumer Discretionary",
    "Consumer Staples",
    "Energy",
    "Financials",
    "Healthcare",
    "Industrials",
    "Materials",
    "Real Estate",
    "Technology",
    "Utilities",
)
DEFAULT_CLUSTER_SOURCE_EVENT_TYPE = "backtest_backfill"


def build_clusters(
    n_clusters: int = 8,
    random_seed: int = 42,
    max_iter: int = 100,
    min_cluster_size: int = 5,
    source_event_type: str | None = DEFAULT_CLUSTER_SOURCE_EVENT_TYPE,
    conn: sqlite3.Connection | None = None,
    run_id: str | None = None,
    dry_run: bool = True,
    verbose: bool = False,
) -> dict[str, Any]:
    """Build numpy-only K-means clusters from lesson context snapshots."""
    own_conn = conn is None
    if own_conn:
        state.init_state_db()
        conn = state._connect_orca()
    assert conn is not None
    try:
        run_id = run_id or f"cluster_run_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"
        snapshot_ids, features, metadata = _load_snapshot_features(
            conn,
            source_event_type=source_event_type,
        )
        if len(snapshot_ids) < n_clusters:
            raise ValueError(f"not enough snapshots for {n_clusters} clusters: {len(snapshot_ids)}")

        labels, centroids = _kmeans_numpy(features, n_clusters, random_seed=random_seed, max_iter=max_iter)
        silhouette = calculate_silhouette_score(features, labels)
        within_variance = _cluster_within_variance(features, labels, centroids)
        cluster_summary = _summarize_clusters(
            conn,
            run_id,
            snapshot_ids,
            features,
            labels,
            centroids,
            metadata,
            n_clusters,
            random_seed,
        )
        assignments = {
            snapshot_id: cluster_summary[int(label)]["cluster_id"]
            for snapshot_id, label in zip(snapshot_ids, labels)
        }
        small_clusters = [
            cluster["cluster_id"]
            for cluster in cluster_summary
            if int(cluster["size"]) < min_cluster_size
        ]

        result = {
            "run_id": run_id,
            "n_clusters": n_clusters,
            "silhouette_score": silhouette,
            "within_cluster_variance": within_variance,
            "cluster_summary": cluster_summary,
            "snapshot_assignments": assignments,
            "small_clusters": small_clusters,
            "feature_metadata": metadata,
            "dry_run": dry_run,
        }

        if verbose:
            print(f"Wave F clustering dry_run={dry_run} run_id={run_id}")
            print(f"  source_event_type={metadata.get('source_event_type') or 'all'}")
            print(f"  snapshots={len(snapshot_ids)} clusters={n_clusters}")
            print(f"  silhouette={silhouette:.4f} within_variance={within_variance:.4f}")
            print("  sizes=" + ", ".join(str(c["size"]) for c in cluster_summary))

        if not dry_run:
            _store_clustering_results(conn, run_id, result, assignments, metadata)
            conn.commit()
        return result
    finally:
        if own_conn and conn is not None:
            conn.close()


def get_cluster_for_snapshot(
    snapshot_id: str,
    conn: sqlite3.Connection | None = None,
) -> str | None:
    own_conn = conn is None
    if own_conn:
        state.init_state_db()
        conn = state._connect_orca()
    assert conn is not None
    try:
        row = conn.execute(
            """
            SELECT context_cluster_id
              FROM lesson_context_snapshot
             WHERE snapshot_id = ?
            """,
            (snapshot_id,),
        ).fetchone()
        return row["context_cluster_id"] if row else None
    finally:
        if own_conn and conn is not None:
            conn.close()


def get_lessons_in_cluster(
    cluster_id: str,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    own_conn = conn is None
    if own_conn:
        state.init_state_db()
        conn = state._connect_orca()
    assert conn is not None
    try:
        return state.get_lessons_in_cluster(conn, cluster_id)
    finally:
        if own_conn and conn is not None:
            conn.close()


def find_nearest_cluster(
    snapshot_features: dict[str, Any],
    conn: sqlite3.Connection | None = None,
    run_id: str | None = None,
    source_event_type: str | None = DEFAULT_CLUSTER_SOURCE_EVENT_TYPE,
) -> tuple[str | None, float]:
    """Find the nearest active cluster for a new snapshot-like feature dict."""
    own_conn = conn is None
    if own_conn:
        state.init_state_db()
        conn = state._connect_orca()
    assert conn is not None
    try:
        effective_run_id = run_id or state.get_latest_run_id(conn)
        if not effective_run_id:
            return None, math.inf
        snapshot_ids, features, metadata = _load_snapshot_features(
            conn,
            source_event_type=source_event_type,
        )
        vector = _transform_snapshot_features(snapshot_features, metadata)
        rows = conn.execute(
            """
            SELECT snapshot_id, cluster_id
              FROM snapshot_cluster_mapping
             WHERE run_id = ?
            """,
            (effective_run_id,),
        ).fetchall()
        if not rows:
            return _find_nearest_cluster_from_rows(vector, conn, effective_run_id, metadata)

        index = {snapshot_id: idx for idx, snapshot_id in enumerate(snapshot_ids)}
        grouped: dict[str, list[np.ndarray]] = {}
        for row in rows:
            idx = index.get(row["snapshot_id"])
            if idx is not None:
                grouped.setdefault(row["cluster_id"], []).append(features[idx])
        if not grouped:
            return None, math.inf

        best_cluster = None
        best_distance = math.inf
        for cluster_id, points in grouped.items():
            centroid = np.mean(np.vstack(points), axis=0)
            distance = _euclidean_distance(vector, centroid)
            if distance < best_distance:
                best_cluster = cluster_id
                best_distance = distance
        return best_cluster, best_distance
    finally:
        if own_conn and conn is not None:
            conn.close()


def calculate_silhouette_score(features: np.ndarray, labels: np.ndarray) -> float:
    labels = np.asarray(labels)
    unique_labels = sorted(set(int(label) for label in labels))
    if len(unique_labels) < 2:
        return 0.0
    distances = _pairwise_distances(features)
    scores: list[float] = []
    for idx, label in enumerate(labels):
        same_mask = labels == label
        same_mask[idx] = False
        a_score = float(distances[idx, same_mask].mean()) if same_mask.any() else 0.0
        b_score = math.inf
        for other_label in unique_labels:
            if other_label == int(label):
                continue
            other_mask = labels == other_label
            if other_mask.any():
                b_score = min(b_score, float(distances[idx, other_mask].mean()))
        denom = max(a_score, b_score)
        scores.append((b_score - a_score) / denom if denom and math.isfinite(denom) else 0.0)
    return float(np.mean(scores))


def _load_snapshot_features(
    conn: sqlite3.Connection,
    source_event_type: str | None = DEFAULT_CLUSTER_SOURCE_EVENT_TYPE,
) -> tuple[list[str], np.ndarray, dict[str, Any]]:
    normalized_source = _normalize_source_event_type(source_event_type)
    source_filter = ""
    params: tuple[Any, ...] = ()
    if normalized_source:
        source_filter = "           AND source_event_type = ?\n"
        params = (normalized_source,)
    rows = conn.execute(
        f"""
        SELECT snapshot_id, trading_date, regime, vix_level,
               sp500_momentum_5d, sp500_momentum_20d,
               nasdaq_momentum_5d, nasdaq_momentum_20d, dominant_sectors,
               source_event_type
          FROM lesson_context_snapshot
         WHERE vix_level IS NOT NULL
           AND sp500_momentum_5d IS NOT NULL
           AND sp500_momentum_20d IS NOT NULL
           AND nasdaq_momentum_5d IS NOT NULL
           AND nasdaq_momentum_20d IS NOT NULL
{source_filter.rstrip()}
         ORDER BY trading_date, snapshot_id
        """,
        params,
    ).fetchall()
    snapshot_dicts = [dict(row) for row in rows]
    snapshot_ids = [row["snapshot_id"] for row in snapshot_dicts]
    raw_matrix = np.vstack([_build_feature_vector(row) for row in snapshot_dicts]) if snapshot_dicts else np.empty((0, 19))
    standardized, means, stds = _standardize_numerical(raw_matrix, list(range(len(NUMERICAL_FEATURES))))
    metadata = {
        "feature_names": [
            *NUMERICAL_FEATURES,
            *[f"regime:{name}" for name in REGIME_ORDER],
            *[f"sector:{name}" for name in CANONICAL_SECTOR_ORDER],
        ],
        "numerical_features": list(NUMERICAL_FEATURES),
        "regime_order": list(REGIME_ORDER),
        "sector_order": list(CANONICAL_SECTOR_ORDER),
        "numerical_means": means.tolist(),
        "numerical_stds": stds.tolist(),
        "source_event_type": normalized_source,
        "snapshots": snapshot_dicts,
    }
    return snapshot_ids, standardized, metadata


def _normalize_source_event_type(source_event_type: str | None) -> str | None:
    """Normalize clustering source filter; None/all means no source filter."""
    if source_event_type is None:
        return None
    normalized = str(source_event_type).strip()
    if not normalized or normalized.lower() in {"all", "*", "none"}:
        return None
    return normalized


def _build_feature_vector(snapshot: dict[str, Any]) -> np.ndarray:
    numeric = [float(snapshot.get(name) or 0.0) for name in NUMERICAL_FEATURES]
    regime = _one_hot_regime(str(snapshot.get("regime") or ""))
    sectors = _multi_hot_sectors(snapshot.get("dominant_sectors") or "[]")
    return np.concatenate([np.array(numeric, dtype=float), regime, sectors])


def _transform_snapshot_features(snapshot: dict[str, Any], metadata: dict[str, Any]) -> np.ndarray:
    vector = _build_feature_vector(snapshot).astype(float)
    means = np.array(metadata["numerical_means"], dtype=float)
    stds = np.array(metadata["numerical_stds"], dtype=float)
    stds = np.where(stds == 0, 1.0, stds)
    vector[: len(NUMERICAL_FEATURES)] = (vector[: len(NUMERICAL_FEATURES)] - means) / stds
    return vector


def _standardize_numerical(
    matrix: np.ndarray,
    indices: list[int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    result = matrix.astype(float).copy()
    values = result[:, indices] if len(result) else np.empty((0, len(indices)))
    means = values.mean(axis=0) if len(values) else np.zeros(len(indices))
    stds = values.std(axis=0) if len(values) else np.ones(len(indices))
    safe_stds = np.where(stds == 0, 1.0, stds)
    if len(result):
        result[:, indices] = (values - means) / safe_stds
    return result, means, safe_stds


def _one_hot_regime(regime: str) -> np.ndarray:
    vector = np.zeros(len(REGIME_ORDER), dtype=float)
    normalized = str(regime or "").strip()
    if normalized in REGIME_ORDER:
        vector[REGIME_ORDER.index(normalized)] = 1.0
    return vector


def _multi_hot_sectors(sectors_json: str | list[str]) -> np.ndarray:
    if isinstance(sectors_json, str):
        try:
            sectors = json.loads(sectors_json) if sectors_json else []
        except Exception:
            sectors = []
    else:
        sectors = list(sectors_json or [])
    aliases = {"Health Care": "Healthcare"}
    vector = np.zeros(len(CANONICAL_SECTOR_ORDER), dtype=float)
    for sector in sectors:
        name = aliases.get(str(sector), str(sector))
        if name in CANONICAL_SECTOR_ORDER:
            vector[CANONICAL_SECTOR_ORDER.index(name)] = 1.0
    return vector


def _kmeans_numpy(
    features: np.ndarray,
    n_clusters: int,
    random_seed: int = 42,
    max_iter: int = 100,
) -> tuple[np.ndarray, np.ndarray]:
    if n_clusters <= 0:
        raise ValueError("n_clusters must be positive")
    if len(features) < n_clusters:
        raise ValueError("n_clusters cannot exceed number of points")
    rng = np.random.RandomState(random_seed)
    centroids = _kmeans_plus_plus_init(features, n_clusters, rng)
    labels = np.full(len(features), -1, dtype=int)
    for _ in range(max_iter):
        distances = np.linalg.norm(features[:, None, :] - centroids[None, :, :], axis=2)
        new_labels = np.argmin(distances, axis=1)
        if np.array_equal(labels, new_labels):
            break
        labels = new_labels
        centroids = _cluster_centroids(features, labels, n_clusters)
        for cluster_idx in range(n_clusters):
            if not np.any(labels == cluster_idx):
                farthest = int(np.argmax(np.min(distances, axis=1)))
                centroids[cluster_idx] = features[farthest]
                labels[farthest] = cluster_idx
    return labels, centroids


def _kmeans_plus_plus_init(
    features: np.ndarray,
    n_clusters: int,
    rng: np.random.RandomState,
) -> np.ndarray:
    first_idx = int(rng.randint(len(features)))
    centroids = [features[first_idx]]
    while len(centroids) < n_clusters:
        existing = np.vstack(centroids)
        distances = np.min(np.sum((features[:, None, :] - existing[None, :, :]) ** 2, axis=2), axis=1)
        total = float(distances.sum())
        if total <= 0:
            candidates = [idx for idx in range(len(features)) if not any(np.array_equal(features[idx], c) for c in centroids)]
            centroids.append(features[candidates[0] if candidates else int(rng.randint(len(features)))])
            continue
        probabilities = distances / total
        centroids.append(features[int(rng.choice(len(features), p=probabilities))])
    return np.vstack(centroids)


def _euclidean_distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=float) - np.asarray(b, dtype=float)))


def _pairwise_distances(features: np.ndarray) -> np.ndarray:
    return np.linalg.norm(features[:, None, :] - features[None, :, :], axis=2)


def _cluster_centroids(
    features: np.ndarray,
    labels: np.ndarray,
    n_clusters: int,
) -> np.ndarray:
    centroids = np.zeros((n_clusters, features.shape[1]), dtype=float)
    for cluster_idx in range(n_clusters):
        mask = labels == cluster_idx
        centroids[cluster_idx] = features[mask].mean(axis=0) if mask.any() else features[0]
    return centroids


def _cluster_within_variance(
    features: np.ndarray,
    labels: np.ndarray,
    centroids: np.ndarray,
) -> float:
    variances = []
    for cluster_idx in sorted(set(int(label) for label in labels)):
        points = features[labels == cluster_idx]
        if len(points):
            variances.append(float(np.mean(np.sum((points - centroids[cluster_idx]) ** 2, axis=1))))
    return float(np.mean(variances)) if variances else 0.0


def _select_representative_snapshot(
    cluster_features: np.ndarray,
    cluster_snapshot_ids: list[str],
    centroid: np.ndarray,
) -> str:
    distances = np.linalg.norm(cluster_features - centroid, axis=1)
    return cluster_snapshot_ids[int(np.argmin(distances))]


def _build_cluster_label(cluster_summary: dict[str, Any]) -> str:
    vix = float(cluster_summary.get("raw_centroid_vix") or cluster_summary.get("centroid_vix") or 0.0)
    sp20 = float(cluster_summary.get("raw_centroid_sp500_20d") or 0.0)
    nq20 = float(cluster_summary.get("raw_centroid_nasdaq_20d") or 0.0)
    regime = str(cluster_summary.get("dominant_regime") or "unknown")
    sectors = cluster_summary.get("common_sectors") or []

    vix_label = "low_vix" if vix < 15 else "high_vix" if vix > 22 else "medium_vix"
    avg_momentum = (sp20 + nq20) / 2.0
    momentum_label = "bullish" if avg_momentum > 2 else "bearish" if avg_momentum < -2 else "neutral"
    regime_label = {
        "위험회피": "riskoff",
        "전환중": "transition",
        "위험선호": "riskon",
    }.get(regime, "unknown")
    sector_label = _sector_label(sectors)
    return "_".join(part for part in (vix_label, momentum_label, regime_label, sector_label) if part)


def _sector_label(sectors: list[str]) -> str:
    defensive = {"Utilities", "Consumer Staples", "Healthcare", "Health Care"}
    growth = {"Technology", "Communication Services", "Consumer Discretionary"}
    cyclical = {"Energy", "Materials", "Industrials", "Financials"}
    sector_set = set(sectors or [])
    if sector_set & defensive:
        return "defensive"
    if sector_set & growth:
        return "growth"
    if sector_set & cyclical:
        return "cyclical"
    return "rotation"


def _store_clustering_results(
    conn: sqlite3.Connection,
    run_id: str,
    cluster_data: dict[str, Any],
    snapshot_assignments: dict[str, str],
    feature_metadata: dict[str, Any],
) -> None:
    state.clear_clustering_data(conn, run_id)
    for cluster in cluster_data["cluster_summary"]:
        state.record_lesson_cluster(conn, cluster)
    distances = {
        cluster["cluster_id"]: cluster.get("snapshot_distances", {})
        for cluster in cluster_data["cluster_summary"]
    }
    for snapshot_id, cluster_id in snapshot_assignments.items():
        state.assign_snapshot_to_cluster(
            conn,
            snapshot_id,
            cluster_id,
            distances.get(cluster_id, {}).get(snapshot_id),
            run_id,
        )


def _summarize_clusters(
    conn: sqlite3.Connection,
    run_id: str,
    snapshot_ids: list[str],
    features: np.ndarray,
    labels: np.ndarray,
    centroids: np.ndarray,
    metadata: dict[str, Any],
    n_clusters: int,
    random_seed: int,
) -> list[dict[str, Any]]:
    snapshots = metadata["snapshots"]
    summary: list[dict[str, Any]] = []
    for cluster_idx in range(n_clusters):
        indices = np.where(labels == cluster_idx)[0]
        cluster_snapshot_ids = [snapshot_ids[idx] for idx in indices]
        cluster_features = features[indices]
        centroid = centroids[cluster_idx]
        representative = _select_representative_snapshot(cluster_features, cluster_snapshot_ids, centroid)
        raw_stats = _raw_cluster_stats([snapshots[idx] for idx in indices])
        performance = _cluster_performance(conn, cluster_snapshot_ids)
        distances = {
            snapshot_id: _euclidean_distance(features[idx], centroid)
            for snapshot_id, idx in zip(cluster_snapshot_ids, indices)
        }
        cluster = {
            "cluster_id": f"{run_id}_c{cluster_idx:02d}",
            "cluster_label": "",
            "size": len(indices),
            "representative_snapshot_id": representative,
            "centroid_vix": float(centroid[0]),
            "centroid_sp500_5d": float(centroid[1]),
            "centroid_sp500_20d": float(centroid[2]),
            "centroid_nasdaq_5d": float(centroid[3]),
            "centroid_nasdaq_20d": float(centroid[4]),
            "dominant_regime": raw_stats["dominant_regime"],
            "common_sectors": raw_stats["common_sectors"],
            "silhouette_score": _cluster_silhouette(features, labels, cluster_idx),
            "within_variance": _cluster_within_variance(features[indices], np.zeros(len(indices), dtype=int), centroid.reshape(1, -1)),
            "avg_outcome_score": performance["avg_outcome_score"],
            "win_rate": performance["win_rate"],
            "sample_count": performance["sample_count"],
            "algorithm": "kmeans",
            "n_clusters_total": n_clusters,
            "random_seed": random_seed,
            "run_id": run_id,
            "created_at": datetime.now().astimezone().isoformat(),
            "updated_at": datetime.now().astimezone().isoformat(),
            "raw_centroid_vix": raw_stats["raw_centroid_vix"],
            "raw_centroid_sp500_20d": raw_stats["raw_centroid_sp500_20d"],
            "raw_centroid_nasdaq_20d": raw_stats["raw_centroid_nasdaq_20d"],
            "snapshot_ids": cluster_snapshot_ids,
            "snapshot_distances": distances,
        }
        cluster["cluster_label"] = _build_cluster_label(cluster)
        summary.append(cluster)
    return summary


def _raw_cluster_stats(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    regime_counts = Counter(str(row.get("regime") or "unknown") for row in snapshots)
    sector_counts: Counter[str] = Counter()
    for row in snapshots:
        sectors = row.get("dominant_sectors") or "[]"
        sector_counts.update(np.nonzero(_multi_hot_sectors(sectors))[0].tolist())
    common_sector_indices = [idx for idx, _count in sector_counts.most_common(3)]
    common_sectors = [CANONICAL_SECTOR_ORDER[idx] for idx in common_sector_indices]
    return {
        "dominant_regime": regime_counts.most_common(1)[0][0] if regime_counts else None,
        "common_sectors": common_sectors,
        "raw_centroid_vix": _mean_snapshot_value(snapshots, "vix_level"),
        "raw_centroid_sp500_20d": _mean_snapshot_value(snapshots, "sp500_momentum_20d"),
        "raw_centroid_nasdaq_20d": _mean_snapshot_value(snapshots, "nasdaq_momentum_20d"),
    }


def _mean_snapshot_value(snapshots: list[dict[str, Any]], key: str) -> float:
    values = [float(row[key]) for row in snapshots if row.get(key) is not None]
    return float(np.mean(values)) if values else 0.0


def _cluster_performance(conn: sqlite3.Connection, snapshot_ids: list[str]) -> dict[str, Any]:
    if not snapshot_ids:
        return {"avg_outcome_score": None, "win_rate": None, "sample_count": 0}
    placeholders = ",".join("?" for _ in snapshot_ids)
    rows = conn.execute(
        f"""
        SELECT lesson_value
          FROM candidate_lessons
         WHERE context_snapshot_id IN ({placeholders})
        """,
        tuple(snapshot_ids),
    ).fetchall()
    values = [float(row["lesson_value"]) for row in rows if row["lesson_value"] is not None]
    if not values:
        return {"avg_outcome_score": None, "win_rate": None, "sample_count": 0}
    wins = [value for value in values if value > 0]
    return {
        "avg_outcome_score": float(np.mean(values)),
        "win_rate": len(wins) / len(values),
        "sample_count": len(values),
    }


def _cluster_silhouette(features: np.ndarray, labels: np.ndarray, cluster_idx: int) -> float:
    mask = labels == cluster_idx
    if not mask.any() or len(set(int(label) for label in labels)) < 2:
        return 0.0
    distances = _pairwise_distances(features)
    scores = []
    for idx in np.where(mask)[0]:
        same = labels == cluster_idx
        same[idx] = False
        a_score = float(distances[idx, same].mean()) if same.any() else 0.0
        b_score = math.inf
        for other in sorted(set(int(label) for label in labels)):
            if other == cluster_idx:
                continue
            other_mask = labels == other
            b_score = min(b_score, float(distances[idx, other_mask].mean()))
        denom = max(a_score, b_score)
        scores.append((b_score - a_score) / denom if denom and math.isfinite(denom) else 0.0)
    return float(np.mean(scores))


def _find_nearest_cluster_from_rows(
    vector: np.ndarray,
    conn: sqlite3.Connection,
    run_id: str,
    metadata: dict[str, Any],
) -> tuple[str | None, float]:
    best_cluster = None
    best_distance = math.inf
    for cluster in state.get_active_clusters(conn, run_id):
        centroid = _cluster_row_vector(cluster, metadata)
        distance = _euclidean_distance(vector, centroid)
        if distance < best_distance:
            best_cluster = cluster["cluster_id"]
            best_distance = distance
    return best_cluster, best_distance


def _cluster_row_vector(cluster: dict[str, Any], metadata: dict[str, Any]) -> np.ndarray:
    vector = np.zeros(len(metadata["feature_names"]), dtype=float)
    vector[:5] = [
        cluster.get("centroid_vix") or 0.0,
        cluster.get("centroid_sp500_5d") or 0.0,
        cluster.get("centroid_sp500_20d") or 0.0,
        cluster.get("centroid_nasdaq_5d") or 0.0,
        cluster.get("centroid_nasdaq_20d") or 0.0,
    ]
    vector[5:8] = _one_hot_regime(cluster.get("dominant_regime") or "")
    vector[8:] = _multi_hot_sectors(cluster.get("common_sectors") or [])
    return vector
