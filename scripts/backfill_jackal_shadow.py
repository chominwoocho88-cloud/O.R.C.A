"""Backfill JACKAL shadow accuracy batches from resolved shadow signals."""
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
from orca.jackal_quality import (  # noqa: E402
    backfill_shadow_batches_from_resolved_signals,
    describe_jackal_shadow_state,
)

KST = timezone(timedelta(hours=9))


def _stamp() -> str:
    return datetime.now(KST).strftime("%Y%m%d-%H%M%S")


def backup_jackal_db(backup_dir: Path | None = None) -> Path | None:
    source = state.JACKAL_DB_FILE
    if not source.exists():
        return None
    target_dir = backup_dir or source.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{source.name}.backup-jackal-shadow-{_stamp()}"
    shutil.copy2(source, target)
    return target


def run_backfill(*, dry_run: bool, make_backup: bool, backup_dir: Path | None = None) -> dict[str, Any]:
    backup_path = None
    if make_backup and not dry_run:
        backup_path = backup_jackal_db(backup_dir)
    result = backfill_shadow_batches_from_resolved_signals(dry_run=dry_run)
    result["backup_path"] = str(backup_path) if backup_path else None
    result["shadow_state"] = describe_jackal_shadow_state()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill JACKAL shadow batch rows from resolved shadow signal outcomes."
    )
    parser.add_argument("--dry-run", action="store_true", help="Inspect recoverability without writing.")
    parser.add_argument("--no-backup", action="store_true", help="Do not backup jackal_state.db before writing.")
    parser.add_argument("--backup-dir", help="Directory for the pre-write JACKAL DB backup.")
    parser.add_argument("--json-output", help="Optional result JSON path.")
    args = parser.parse_args()

    result = run_backfill(
        dry_run=args.dry_run,
        make_backup=not args.no_backup,
        backup_dir=Path(args.backup_dir) if args.backup_dir else None,
    )
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.json_output:
        output = Path(args.json_output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
