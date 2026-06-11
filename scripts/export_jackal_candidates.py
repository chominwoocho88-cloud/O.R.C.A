#!/usr/bin/env python
"""Export recent JACKAL live events as a candidate snapshot for ORCA to import.

Why this exists: since the 2026-05-15 ownership boundary (Phase 0.4-C0),
jackal_session no longer commits data/orca_state.db, so the cross-DB candidate
registration inside sync_jackal_live_events is lost on every session persist.
This script writes a JACKAL-owned snapshot file instead; the ORCA daily job
(scripts/import_jackal_candidates.py) registers the rows into its own DB.
One committer per file — no conflict window.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

KST = timezone(timedelta(hours=9))
DATA_ROOT = Path(os.environ.get("ORCA_REPO_ROOT") or ROOT)
DEFAULT_OUTPUT = DATA_ROOT / "data" / "jackal_candidate_export.jsonl"
JACKAL_DB = DATA_ROOT / "data" / "jackal_state.db"


def _within_window(updated_at: str, cutoff: datetime) -> bool:
    try:
        value = datetime.fromisoformat(updated_at)
    except (TypeError, ValueError):
        return True  # 파싱 불가 행은 버리지 않는다 — import 쪽 upsert가 멱등
    if value.tzinfo is None:
        value = value.replace(tzinfo=KST)
    return value >= cutoff


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export JACKAL candidate snapshot")
    parser.add_argument("--days", type=int, default=45, help="lookback window (days)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    if not JACKAL_DB.exists():
        print(f"export_jackal_candidates: missing {JACKAL_DB} — nothing to export")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("", encoding="utf-8")
        return 0

    cutoff = datetime.now(KST) - timedelta(days=args.days)
    conn = sqlite3.connect(JACKAL_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT event_id, event_type, external_key, updated_at, payload_json
          FROM jackal_live_events
         ORDER BY updated_at
        """
    ).fetchall()
    conn.close()

    exported = 0
    lines: list[str] = []
    for row in rows:
        if not _within_window(str(row["updated_at"]), cutoff):
            continue
        try:
            entry = json.loads(row["payload_json"] or "{}")
        except json.JSONDecodeError:
            print(f"  skip {row['event_id']}: invalid payload_json", file=sys.stderr)
            continue
        lines.append(
            json.dumps(
                {
                    "event_id": row["event_id"],
                    "event_type": row["event_type"],
                    "external_key": row["external_key"],
                    "entry": entry,
                },
                ensure_ascii=False,
            )
        )
        exported += 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    print(f"export_jackal_candidates: {exported} events -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
