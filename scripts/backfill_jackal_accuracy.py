"""Backfill JACKAL SQL accuracy projection/current rows from evaluable backtests."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from orca import state  # noqa: E402
from orca.jackal_accuracy_projection import (  # noqa: E402
    backfill_jackal_accuracy_projection_from_backtest,
    describe_jackal_accuracy_projection_state,
)

KST = timezone(timedelta(hours=9))


def _now_stamp() -> str:
    return datetime.now(KST).strftime("%Y%m%d-%H%M%S")


def backup_jackal_db(backup_dir: Path | None = None) -> Path | None:
    source = state.JACKAL_DB_FILE
    if not source.exists():
        return None
    target_dir = backup_dir or source.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{source.name}.backup-jackal-accuracy-{_now_stamp()}"
    shutil.copy2(source, target)
    return target


def run_backfill(
    *,
    session_id: str | None = None,
    dry_run: bool = False,
    make_backup: bool = True,
    backup_dir: Path | None = None,
) -> dict[str, Any]:
    backup_path: Path | None = None
    if make_backup and not dry_run:
        backup_path = backup_jackal_db(backup_dir)

    result = backfill_jackal_accuracy_projection_from_backtest(
        session_id=session_id,
        dry_run=dry_run,
    )
    result["backup_path"] = str(backup_path) if backup_path else None
    result["projection_state"] = describe_jackal_accuracy_projection_state()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill JACKAL accuracy projection/current rows from the latest evaluable backtest."
    )
    parser.add_argument("--session-id", help="Use a specific evaluable JACKAL backtest session.")
    parser.add_argument("--dry-run", action="store_true", help="Plan rows without writing a snapshot/projection.")
    parser.add_argument("--no-backup", action="store_true", help="Do not backup jackal_state.db before writing.")
    parser.add_argument("--backup-dir", help="Directory for the pre-write JACKAL DB backup.")
    parser.add_argument("--json-output", help="Optional path to write machine-readable result JSON.")
    args = parser.parse_args()

    backup_dir = Path(args.backup_dir) if args.backup_dir else None
    result = run_backfill(
        session_id=args.session_id,
        dry_run=args.dry_run,
        make_backup=not args.no_backup,
        backup_dir=backup_dir,
    )

    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.json_output:
        output_path = Path(args.json_output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
