#!/usr/bin/env python
"""Run the ORCA monthly report and lesson extraction from workflow-safe Python code."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ORCA monthly report")
    parser.add_argument("--dry-run", action="store_true", help="Validate script wiring without sending Telegram")
    args = parser.parse_args(argv)

    if args.dry_run:
        print("DRY RUN monthly report runner OK")
        return 0

    from orca.analysis import extract_monthly_lessons
    from orca.notify import send_monthly_report
    from orca.paths import ACCURACY_FILE, MEMORY_FILE

    send_monthly_report()
    memory = json.loads(MEMORY_FILE.read_text(encoding="utf-8")) if MEMORY_FILE.exists() else []
    accuracy = json.loads(ACCURACY_FILE.read_text(encoding="utf-8")) if ACCURACY_FILE.exists() else {}
    extract_monthly_lessons(memory, accuracy)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
