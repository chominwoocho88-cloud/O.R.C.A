#!/usr/bin/env python
"""Wave F Phase 3: build lesson archive quality scores."""
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
    backup_path = db_path.with_name(f"{db_path.name}.backup-pre-archive-{int(time.time())}")
    shutil.copy(db_path, backup_path)
    return backup_path


def _print_preflight(conn: sqlite3.Connection) -> dict[str, Any]:
    from orca import state

    clusters = conn.execute("SELECT COUNT(*) FROM lesson_clusters").fetchone()[0]
    mappings = conn.execute("SELECT COUNT(*) FROM snapshot_cluster_mapping").fetchone()[0]
    linked_lessons = conn.execute(
        """
        SELECT COUNT(*)
          FROM candidate_lessons
         WHERE context_snapshot_id IS NOT NULL
        """
    ).fetchone()[0]
    clustered_lessons = conn.execute(
        """
        SELECT COUNT(*)
          FROM candidate_lessons l
          JOIN snapshot_cluster_mapping m
            ON m.snapshot_id = l.context_snapshot_id
        """
    ).fetchone()[0]
    archives = conn.execute("SELECT COUNT(*) FROM lesson_archive").fetchone()[0]
    latest_cluster_run = state.get_latest_run_id(conn)
    latest_archive_run = state.get_latest_archive_run_id(conn)

    status = {
        "clusters": clusters,
        "mappings": mappings,
        "linked_lessons": linked_lessons,
        "clustered_lessons": clustered_lessons,
        "archives": archives,
        "latest_cluster_run": latest_cluster_run,
        "latest_archive_run": latest_archive_run,
    }

    print("Pre-flight:")
    print(f"  clusters: {clusters}")
    print(f"  snapshot mappings: {mappings}")
    print(f"  lessons with context: {linked_lessons}")
    print(f"  clustered lessons: {clustered_lessons}")
    print(f"  existing archive rows: {archives}")
    print(f"  latest cluster run_id: {latest_cluster_run or '(none)'}")
    print(f"  latest archive run_id: {latest_archive_run or '(none)'}")
    return status


def _print_archive_result(result: dict[str, Any]) -> None:
    print()
    print("=" * 60)
    print("Lesson Archive Result")
    print("=" * 60)
    print(f"Archive run ID: {result['archive_run_id']}")
    print(f"Cluster run ID: {result['cluster_run_id']}")
    print(f"Dry run: {result['dry_run']}")
    print(f"Archive rows: {result['archive_count']}")
    print(f"Average quality: {result['avg_quality_score']:.4f}")
    print(f"Tier distribution: {result['tier_distribution']}")

    print()
    print("Cluster summary:")
    for cluster in result["cluster_summary"]:
        print(
            "  "
            f"{cluster['cluster_id']}: "
            f"count={cluster['archive_count']} "
            f"avg_quality={cluster['avg_quality_score']:.4f} "
            f"tiers={cluster['tier_distribution']} "
            f"top={cluster['top_lesson_id']}"
        )


def _verify_result(
    conn: sqlite3.Connection,
    result: dict[str, Any],
    *,
    expected_lessons: int | None,
) -> dict[str, Any]:
    archive_run_id = result["archive_run_id"]
    archive_count = int(result["archive_count"])
    failures: list[str] = []

    rows_in_db = conn.execute(
        "SELECT COUNT(*) FROM lesson_archive WHERE run_id = ?",
        (archive_run_id,),
    ).fetchone()[0]
    high, medium, low = result["tier_distribution"].values()
    tier_total = int(high) + int(medium) + int(low)

    if not result["dry_run"] and rows_in_db != archive_count:
        failures.append(f"archive rows in DB {rows_in_db} != result count {archive_count}")
    if expected_lessons is not None and archive_count != expected_lessons:
        failures.append(f"archive count {archive_count} != expected lessons {expected_lessons}")
    if tier_total != archive_count:
        failures.append(f"tier distribution total {tier_total} != archive count {archive_count}")
    if archive_count <= 0:
        failures.append("archive count is zero")
    if float(result["avg_quality_score"]) <= 0:
        failures.append("avg quality score is not positive")

    return {
        "passed": not failures,
        "failures": failures,
        "rows_in_db": rows_in_db,
        "archive_count": archive_count,
        "tier_total": tier_total,
    }


def _print_verification(verification: dict[str, Any]) -> None:
    print()
    print("=" * 60)
    print("Verification")
    print("=" * 60)
    print(f"rows in DB for run: {verification['rows_in_db']}")
    print(f"archive count: {verification['archive_count']}")
    print(f"tier total: {verification['tier_total']}")
    if verification["passed"]:
        print("PASS archive verification")
        return
    print("FAIL archive verification")
    for failure in verification["failures"]:
        print(f"  - {failure}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build Wave F Phase 3 lesson archive quality scores"
    )
    parser.add_argument(
        "--cluster-run-id",
        default=None,
        help="Optional clustering run_id to archive (default: latest)",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=42,
        help="Random seed recorded for reproducibility (default: 42)",
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
        help="Write archive rows to DB",
    )
    parser.set_defaults(dry_run=True)
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="Clear existing lesson_archive rows before executing",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip automatic DB backup when executing (not recommended)",
    )
    parser.add_argument(
        "--expected-lessons",
        type=int,
        default=None,
        help="Expected number of archive rows",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed archive progress",
    )
    args = parser.parse_args(argv)

    print("=" * 60)
    print("Wave F Phase 3 - Lesson Archive")
    print("=" * 60)
    if args.dry_run:
        print("MODE: DRY RUN (no DB changes)")

    from orca import lesson_archive, state

    state.init_state_db()
    conn = state._connect_orca()
    try:
        preflight = _print_preflight(conn)
        cluster_run_id = args.cluster_run_id or preflight["latest_cluster_run"]
        if not cluster_run_id:
            print()
            print("No clustering run found. Build clusters before archiving.")
            return 1

        if args.dry_run and args.force_rebuild:
            print()
            print("force_rebuild=true requested, but dry_run=true prevents DB changes.")

        if not args.dry_run and preflight["archives"] and not args.force_rebuild:
            print()
            print(
                "Existing lesson_archive rows found. Re-run with --force-rebuild "
                "to replace archive data."
            )
            return 1

        if not args.dry_run and not args.no_backup:
            backup_path = _create_backup()
            print(f"Backup created: {backup_path}")

        if not args.dry_run and args.force_rebuild:
            cleared = state.clear_lesson_archive(conn)
            conn.commit()
            print(f"Cleared existing archive data: {cleared}")

        result = lesson_archive.build_lesson_archive(
            cluster_run_id=cluster_run_id,
            random_seed=args.random_seed,
            conn=conn,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
        _print_archive_result(result)

        verification = _verify_result(
            conn,
            result,
            expected_lessons=args.expected_lessons,
        )
        _print_verification(verification)
        return 0 if verification["passed"] else 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
