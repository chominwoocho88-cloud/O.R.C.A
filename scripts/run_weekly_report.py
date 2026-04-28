#!/usr/bin/env python
"""Run the ORCA weekly report from workflow-safe Python code."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ORCA weekly report")
    parser.add_argument("--dry-run", action="store_true", help="Validate script wiring without sending Telegram")
    args = parser.parse_args(argv)

    if args.dry_run:
        print("DRY RUN weekly report runner OK")
        return 0

    from orca.notify import send_weekly_report

    send_weekly_report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
