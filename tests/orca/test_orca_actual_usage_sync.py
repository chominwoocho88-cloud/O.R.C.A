from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from orca.data import sync_actual_usage


class OrcaActualUsageSyncTests(unittest.TestCase):
    def test_sync_actual_usage_preserves_estimates_and_overwrites_snapshot(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            tmp = Path(tmpdir)
            cost_path = tmp / "orca_cost.json"
            log_path = tmp / "llm_log.jsonl"
            cost_path.write_text(
                json.dumps(
                    {
                        "total_runs": 7,
                        "monthly_runs": {"2026-05": {"runs": 3, "estimated_usd": 3.6}},
                        "estimated_cost_usd": 9.9,
                        "last_run": "2026-05-18 07:00 KST",
                        "monthly_actual_usage": {"2026-04": {"call_count": 99}},
                    }
                ),
                encoding="utf-8",
            )
            self._write_jsonl(
                log_path,
                [
                    {
                        "ts": "2026-05-18T07:00:00+09:00",
                        "type": "success",
                        "call_site": "orca.hunter",
                        "input_tokens": 10,
                        "output_tokens": 20,
                        "cache_read_tokens": 1,
                        "cache_creation_tokens": 2,
                        "web_search_requests": 3,
                    },
                    {
                        "ts": "2026-05-18T07:01:00+09:00",
                        "type": "success",
                        "call_site": "jackal.hunter",
                        "input_tokens": 999,
                        "output_tokens": 999,
                    },
                ],
            )

            first = sync_actual_usage(cost_path=cost_path, log_path=log_path)
            second = sync_actual_usage(cost_path=cost_path, log_path=log_path)

        self.assertEqual(first, second)
        self.assertEqual(second["total_runs"], 7)
        self.assertEqual(second["monthly_runs"], {"2026-05": {"runs": 3, "estimated_usd": 3.6}})
        self.assertEqual(second["estimated_cost_usd"], 9.9)
        self.assertEqual(second["last_run"], "2026-05-18 07:00 KST")
        self.assertEqual(
            second["monthly_actual_usage"],
            {
                "2026-05": {
                    "call_count": 1,
                    "input_tokens": 10,
                    "output_tokens": 20,
                    "cache_read_tokens": 1,
                    "cache_creation_tokens": 2,
                    "web_search_requests": 3,
                }
            },
        )

    def test_sync_actual_usage_empty_log_sets_empty_snapshot(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            tmp = Path(tmpdir)
            cost_path = tmp / "orca_cost.json"
            log_path = tmp / "missing.jsonl"

            result = sync_actual_usage(cost_path=cost_path, log_path=log_path)

        self.assertEqual(result["monthly_actual_usage"], {})
        self.assertEqual(result["total_runs"], 0)
        self.assertEqual(result["monthly_runs"], {})
        self.assertEqual(result["estimated_cost_usd"], 0.0)

    @staticmethod
    def _write_jsonl(path: Path, entries: list[dict]) -> None:
        path.write_text(
            "\n".join(json.dumps(entry, separators=(",", ":")) for entry in entries),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
