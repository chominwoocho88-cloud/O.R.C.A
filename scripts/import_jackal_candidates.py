#!/usr/bin/env python
"""Import the JACKAL candidate snapshot into candidate_registry (ORCA-owned DB).

Counterpart of scripts/export_jackal_candidates.py — see its docstring for the
ownership-boundary background. Runs in the ORCA daily job before the cycle so
the MORNING candidate review sees fresh JACKAL candidates. Idempotent:
record_candidate upserts by external key.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_SNAPSHOT = (
    Path(os.environ.get("ORCA_REPO_ROOT") or ROOT) / "data" / "jackal_candidate_export.jsonl"
)


def _registry_count(state_module) -> int:
    db_path = Path(state_module.STATE_DB_FILE)
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM candidate_registry").fetchone()[0]
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import JACKAL candidate snapshot")
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    args = parser.parse_args(argv)

    if not args.snapshot.exists():
        print(f"import_jackal_candidates: no snapshot at {args.snapshot} — skipping")
        return 0

    from apps.orca import state

    before = _registry_count(state)
    imported = 0
    failed = 0
    for line_no, line in enumerate(
        args.snapshot.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            state.record_candidate(
                row["entry"],
                source_system="jackal",
                source_event_type=str(row.get("event_type") or "scan"),
                source_external_key=row.get("external_key"),
                source_event_id=row.get("event_id"),
            )
            imported += 1
        except Exception as exc:  # 행 단위 실패가 MORNING을 막으면 안 된다
            failed += 1
            print(
                f"  line {line_no}: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )

    after = _registry_count(state)
    print(
        "import_jackal_candidates: "
        f"imported={imported} failed={failed} new_rows={after - before}"
    )
    if imported == 0 and failed > 0:
        # 스냅샷이 있는데 전부 실패 — 5/15 사고의 재림이므로 크게 알린다
        print(
            "import_jackal_candidates: WARNING - snapshot present but nothing "
            "imported; candidate pipeline may be broken again",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
