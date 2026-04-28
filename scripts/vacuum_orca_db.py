from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from orca import state
from orca.lesson_archive_store import COLD_ARCHIVE_DB_FILE, migrate_to_cold, vacuum_sqlite_database
from orca.paths import STATE_DB_FILE


def _mb(path: Path) -> float | None:
    return round(path.stat().st_size / 1024 / 1024, 2) if path.exists() else None


def _counts(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    conn = sqlite3.connect(path)
    try:
        names = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        return {name: conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in names}
    finally:
        conn.close()


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    backup_dir = Path(tempfile.gettempdir()) / "orca_db_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    backup_path = backup_dir / f"{path.stem}.backup-{stamp}{path.suffix}"
    shutil.copy2(path, backup_path)
    return backup_path


def main() -> int:
    parser = argparse.ArgumentParser(description="VACUUM ORCA state DB and move cold rows out of the hot DB.")
    parser.add_argument("--migrate-cold", action="store_true", help="Move cold archive/log/backtest rows first")
    parser.add_argument("--threshold-runs", type=int, default=1, help="Archive runs to keep hot")
    parser.add_argument("--no-backup", action="store_true", help="Skip temp backup before maintenance")
    args = parser.parse_args()

    state.init_state_db()
    before = {
        "main_mb": _mb(STATE_DB_FILE),
        "cold_mb": _mb(COLD_ARCHIVE_DB_FILE),
        "main_counts": _counts(STATE_DB_FILE),
        "cold_counts": _counts(COLD_ARCHIVE_DB_FILE),
    }
    backup_path = None if args.no_backup else _backup(STATE_DB_FILE)

    migration = None
    if args.migrate_cold:
        migration = migrate_to_cold(threshold_runs=args.threshold_runs)

    main_vacuum = vacuum_sqlite_database(STATE_DB_FILE)
    cold_vacuum = vacuum_sqlite_database(COLD_ARCHIVE_DB_FILE) if COLD_ARCHIVE_DB_FILE.exists() else None

    after = {
        "main_mb": _mb(STATE_DB_FILE),
        "cold_mb": _mb(COLD_ARCHIVE_DB_FILE),
        "main_counts": _counts(STATE_DB_FILE),
        "cold_counts": _counts(COLD_ARCHIVE_DB_FILE),
    }
    print(
        json.dumps(
            {
                "backup_path": str(backup_path) if backup_path else None,
                "before": before,
                "migration": migration,
                "main_vacuum": main_vacuum,
                "cold_vacuum": cold_vacuum,
                "after": after,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
