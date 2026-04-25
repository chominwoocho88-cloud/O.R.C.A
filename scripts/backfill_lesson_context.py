#!/usr/bin/env python
"""Wave F Phase 1.3: Backfill context snapshots for existing lessons."""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _create_backup() -> Path:
    from orca.paths import STATE_DB_FILE

    backup_path = STATE_DB_FILE.with_name(
        f"{STATE_DB_FILE.name}.backup-pre-backfill-{int(time.time())}"
    )
    shutil.copy(STATE_DB_FILE, backup_path)
    return backup_path


def _print_verification_counts() -> None:
    from orca.paths import STATE_DB_FILE

    conn = sqlite3.connect(STATE_DB_FILE)
    try:
        snapshots = conn.execute(
            "SELECT COUNT(*) FROM lesson_context_snapshot"
        ).fetchone()[0]
        linked = conn.execute(
            """
            SELECT COUNT(*)
              FROM candidate_lessons
             WHERE context_snapshot_id IS NOT NULL
            """
        ).fetchone()[0]
        unlinked = conn.execute(
            """
            SELECT COUNT(*)
              FROM candidate_lessons
             WHERE context_snapshot_id IS NULL
            """
        ).fetchone()[0]
        backfill_snapshots = conn.execute(
            """
            SELECT COUNT(*)
              FROM lesson_context_snapshot
             WHERE source_event_type = 'backtest_backfill'
            """
        ).fetchone()[0]
    finally:
        conn.close()

    print()
    print("Verification counts:")
    print(f"  lesson_context_snapshot: {snapshots}")
    print(f"  backtest_backfill snapshots: {backfill_snapshots}")
    print(f"  lessons with context: {linked}")
    print(f"  lessons without context: {unlinked}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill context snapshots for Wave F Phase 1.3"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max distinct trading dates to process (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate without DB writes or network calls",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Log per-date progress",
    )
    parser.add_argument(
        "--skip-existing",
        dest="skip_existing",
        action="store_true",
        default=True,
        help="Skip lessons that already have context (default)",
    )
    parser.add_argument(
        "--include-existing",
        dest="skip_existing",
        action="store_false",
        help="Reprocess existing linked lessons as well",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip automatic DB backup (not recommended)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Wave F Phase 1.3 - Lesson Context Backfill")
    print("=" * 60)
    if args.dry_run:
        print("MODE: DRY RUN (no DB changes, no network calls)")

    if not args.no_backup and not args.dry_run:
        backup_path = _create_backup()
        print(f"Backup created: {backup_path}")

    from orca.context_snapshot import backfill_lessons_context

    result = backfill_lessons_context(
        limit=args.limit,
        skip_existing=args.skip_existing,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    print()
    print("=" * 60)
    print("Backfill Result")
    print("=" * 60)
    print(f"Lessons total: {result['lessons_total']}")
    print(f"Lessons processed: {result['lessons_processed']}")
    print(f"Lessons skipped: {result['lessons_skipped']}")
    print(f"Snapshots created: {result['snapshots_created']}")
    print(f"Snapshots reused: {result['snapshots_reused']}")
    print(f"Dates total: {result.get('dates_total', 0)}")
    print(f"Dates processed: {result.get('dates_processed', 0)}")
    print(f"Duration: {result['duration_seconds']:.1f}s")

    if not args.dry_run:
        _print_verification_counts()

    if result["failed_dates"]:
        print()
        print(f"Failed dates ({len(result['failed_dates'])}):")
        for item in result["failed_dates"]:
            print(f"  {item['date']}: {item['reason']}")
        return 1

    print()
    print("Backfill complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
