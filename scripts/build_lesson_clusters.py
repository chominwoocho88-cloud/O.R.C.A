#!/usr/bin/env python
"""Wave F Phase 2-C: build lesson context clusters."""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _create_backup() -> Path:
    from orca import state

    db_path = state.STATE_DB_FILE
    if not db_path.exists():
        raise FileNotFoundError(f"State DB not found: {db_path}")
    backup_path = db_path.with_name(
        f"{db_path.name}.backup-pre-clustering-{int(time.time())}"
    )
    shutil.copy(db_path, backup_path)
    return backup_path


def _print_preflight(conn: sqlite3.Connection) -> dict[str, Any]:
    from orca import state

    snapshots = conn.execute(
        "SELECT COUNT(*) FROM lesson_context_snapshot"
    ).fetchone()[0]
    usable_snapshots = conn.execute(
        """
        SELECT COUNT(*)
          FROM lesson_context_snapshot
         WHERE vix_level IS NOT NULL
           AND sp500_momentum_5d IS NOT NULL
           AND sp500_momentum_20d IS NOT NULL
           AND nasdaq_momentum_5d IS NOT NULL
           AND nasdaq_momentum_20d IS NOT NULL
        """
    ).fetchone()[0]
    lessons_linked = conn.execute(
        """
        SELECT COUNT(*)
          FROM candidate_lessons
         WHERE context_snapshot_id IS NOT NULL
        """
    ).fetchone()[0]
    clusters = conn.execute("SELECT COUNT(*) FROM lesson_clusters").fetchone()[0]
    mappings = conn.execute("SELECT COUNT(*) FROM snapshot_cluster_mapping").fetchone()[0]
    latest_run_id = state.get_latest_run_id(conn)

    status = {
        "snapshots": snapshots,
        "usable_snapshots": usable_snapshots,
        "lessons_linked": lessons_linked,
        "clusters": clusters,
        "mappings": mappings,
        "latest_run_id": latest_run_id,
    }

    print("Pre-flight:")
    print(f"  snapshots total: {snapshots}")
    print(f"  snapshots usable for clustering: {usable_snapshots}")
    print(f"  lessons linked to context: {lessons_linked}")
    print(f"  existing clusters: {clusters}")
    print(f"  existing mappings: {mappings}")
    print(f"  latest run_id: {latest_run_id or '(none)'}")
    return status


def _print_cluster_result(result: dict[str, Any]) -> None:
    print()
    print("=" * 60)
    print("Clustering Result")
    print("=" * 60)
    print(f"Run ID: {result['run_id']}")
    print(f"Dry run: {result['dry_run']}")
    print(f"Clusters: {result['n_clusters']}")
    print(f"Silhouette score: {result['silhouette_score']:.4f}")
    print(f"Within-cluster variance: {result['within_cluster_variance']:.4f}")
    print(f"Assignments: {len(result['snapshot_assignments'])}")
    print(f"Small clusters: {len(result['small_clusters'])}")

    print()
    print("Cluster summary:")
    for cluster in result["cluster_summary"]:
        sectors = ", ".join(cluster.get("common_sectors") or [])
        print(
            "  "
            f"{cluster['cluster_id']}: "
            f"size={cluster['size']} "
            f"label={cluster['cluster_label']} "
            f"sil={cluster['silhouette_score']:.3f} "
            f"rep={cluster['representative_snapshot_id']} "
            f"regime={cluster.get('dominant_regime')} "
            f"sectors=[{sectors}]"
        )


def _verify_result(
    conn: sqlite3.Connection,
    result: dict[str, Any],
    *,
    expected_snapshots: int | None,
    expected_linked_lessons: int | None,
    min_silhouette: float,
) -> dict[str, Any]:
    run_id = result["run_id"]
    n_clusters = int(result["n_clusters"])
    assignment_count = len(result["snapshot_assignments"])

    clusters = conn.execute(
        "SELECT COUNT(*) FROM lesson_clusters WHERE run_id = ?",
        (run_id,),
    ).fetchone()[0]
    mappings = conn.execute(
        "SELECT COUNT(*) FROM snapshot_cluster_mapping WHERE run_id = ?",
        (run_id,),
    ).fetchone()[0]
    cached = conn.execute(
        """
        SELECT COUNT(*)
          FROM lesson_context_snapshot
         WHERE context_cluster_id IN (
               SELECT cluster_id FROM lesson_clusters WHERE run_id = ?
         )
        """,
        (run_id,),
    ).fetchone()[0]
    clustered_lessons = conn.execute(
        """
        SELECT COUNT(*)
          FROM candidate_lessons l
          JOIN snapshot_cluster_mapping m
            ON m.snapshot_id = l.context_snapshot_id
         WHERE m.run_id = ?
        """,
        (run_id,),
    ).fetchone()[0]

    failures: list[str] = []
    if not result["dry_run"] and clusters != n_clusters:
        failures.append(f"clusters {clusters} != expected {n_clusters}")
    if not result["dry_run"] and mappings != assignment_count:
        failures.append(f"mappings {mappings} != assignments {assignment_count}")
    if not result["dry_run"] and cached != assignment_count:
        failures.append(f"context_cluster_id cache {cached} != assignments {assignment_count}")
    if expected_snapshots is not None and assignment_count < expected_snapshots:
        failures.append(f"assignments {assignment_count} < expected snapshots {expected_snapshots}")
    if (
        not result["dry_run"]
        and expected_linked_lessons is not None
        and clustered_lessons < expected_linked_lessons
    ):
        failures.append(
            f"clustered lessons {clustered_lessons} < expected linked lessons {expected_linked_lessons}"
        )
    if float(result["silhouette_score"]) < min_silhouette:
        failures.append(
            f"silhouette {result['silhouette_score']:.4f} < threshold {min_silhouette:.4f}"
        )

    return {
        "passed": not failures,
        "failures": failures,
        "clusters": clusters,
        "mappings": mappings,
        "cached": cached,
        "clustered_lessons": clustered_lessons,
        "assignments": assignment_count,
    }


def _print_verification(verification: dict[str, Any]) -> None:
    print()
    print("=" * 60)
    print("Verification")
    print("=" * 60)
    for key in ("clusters", "mappings", "cached", "clustered_lessons", "assignments"):
        print(f"{key}: {verification[key]}")

    if verification["passed"]:
        print("PASS clustering verification")
        return

    print("FAIL clustering verification")
    for failure in verification["failures"]:
        print(f"  - {failure}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build Wave F Phase 2 context clusters"
    )
    parser.add_argument(
        "--n-clusters",
        type=int,
        default=8,
        help="Number of context clusters to build (default: 8)",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=42,
        help="Random seed for deterministic K-means (default: 42)",
    )
    parser.add_argument(
        "--max-iter",
        type=int,
        default=100,
        help="Maximum K-means iterations (default: 100)",
    )
    parser.add_argument(
        "--min-cluster-size",
        type=int,
        default=5,
        help="Warn when clusters are smaller than this size (default: 5)",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional explicit clustering run_id",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Simulate without DB writes (default)",
    )
    mode.add_argument(
        "--execute",
        dest="dry_run",
        action="store_false",
        help="Write clustering results to DB",
    )
    parser.set_defaults(dry_run=True)
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Clear existing clustering data before executing",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip automatic DB backup when executing (not recommended)",
    )
    parser.add_argument(
        "--expected-snapshots",
        type=int,
        default=None,
        help="Minimum expected snapshot assignments",
    )
    parser.add_argument(
        "--expected-linked-lessons",
        type=int,
        default=None,
        help="Minimum expected lessons reachable through cluster mappings",
    )
    parser.add_argument(
        "--min-silhouette",
        type=float,
        default=0.15,
        help="Minimum acceptable silhouette score (default: 0.15)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed clustering progress",
    )
    args = parser.parse_args(argv)

    print("=" * 60)
    print("Wave F Phase 2-C - Lesson Context Clustering")
    print("=" * 60)
    if args.dry_run:
        print("MODE: DRY RUN (no DB changes)")

    from orca import lesson_clustering, state

    state.init_state_db()
    conn = state._connect_orca()
    try:
        preflight = _print_preflight(conn)

        if args.dry_run and args.force_rebuild:
            print()
            print("force_rebuild=true requested, but dry_run=true prevents DB changes.")

        if not args.dry_run and preflight["latest_run_id"] and not args.force_rebuild:
            print()
            print(
                "Existing clustering run found. Re-run with --force-rebuild "
                "to replace clustering data."
            )
            return 1

        if not args.dry_run and not args.no_backup:
            backup_path = _create_backup()
            print(f"Backup created: {backup_path}")

        if not args.dry_run and args.force_rebuild:
            cleared = state.clear_clustering_data(conn)
            conn.commit()
            print(f"Cleared existing clustering data: {cleared}")

        result = lesson_clustering.build_clusters(
            n_clusters=args.n_clusters,
            random_seed=args.random_seed,
            max_iter=args.max_iter,
            min_cluster_size=args.min_cluster_size,
            conn=conn,
            run_id=args.run_id,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
        _print_cluster_result(result)

        verification = _verify_result(
            conn,
            result,
            expected_snapshots=args.expected_snapshots,
            expected_linked_lessons=args.expected_linked_lessons,
            min_silhouette=args.min_silhouette,
        )
        _print_verification(verification)
        return 0 if verification["passed"] else 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
