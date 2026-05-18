from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from shared.llm.usage_reader import (
    read_jackal_today_tokens,
    read_jackal_tokens_by_date,
    read_orca_today_usage,
    read_orca_usage_by_month,
)


class LLMUsageReaderTests(unittest.TestCase):
    def test_read_jackal_today_tokens_filters_and_sums_actual_tokens(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            log_path = Path(tmpdir) / "llm.jsonl"
            self._write_jsonl(
                log_path,
                [
                    {
                        "ts": "2026-05-18T08:00:00+09:00",
                        "type": "success",
                        "call_site": "jackal.hunter.analyst",
                        "input_tokens": 10,
                        "output_tokens": 20,
                        "cache_read_tokens": 3,
                        "cache_creation_tokens": 4,
                    },
                    {
                        "ts": "2026-05-18T08:01:00+09:00",
                        "type": "success",
                        "call_site": "orca.hunter",
                        "input_tokens": 100,
                        "output_tokens": 200,
                    },
                    {
                        "ts": "2026-05-17T08:00:00+09:00",
                        "type": "success",
                        "call_site": "jackal.scanner.devil",
                        "input_tokens": 7,
                        "output_tokens": 8,
                    },
                    {
                        "ts": "2026-05-18T08:02:00+09:00",
                        "type": "failure",
                        "call_site": "jackal.hunter.devil",
                        "input_tokens": 999,
                        "output_tokens": 999,
                    },
                    "not-json",
                ],
            )

            tokens = read_jackal_today_tokens(today="2026-05-18", log_path=log_path)

        self.assertEqual(tokens, 37)

    def test_read_jackal_tokens_by_date_groups_jackal_success_entries(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            log_path = Path(tmpdir) / "llm.jsonl"
            self._write_jsonl(
                log_path,
                [
                    {
                        "ts": "2026-05-17T08:00:00+09:00",
                        "type": "success",
                        "call_site": "jackal.hunter.suggest",
                        "input_tokens": 1,
                        "output_tokens": 2,
                    },
                    {
                        "ts": "2026-05-17T09:00:00+09:00",
                        "type": "success",
                        "call_site": "jackal.evolution",
                        "input_tokens": 3,
                        "output_tokens": 4,
                    },
                    {
                        "ts": "2026-05-18T08:00:00+09:00",
                        "type": "success",
                        "call_site": "jackal.compact",
                        "input_tokens": "5",
                        "output_tokens": "6",
                    },
                ],
            )

            totals = read_jackal_tokens_by_date(log_path=log_path)

        self.assertEqual(totals, {"2026-05-17": 10, "2026-05-18": 11})

    def test_missing_log_returns_zero_and_empty_grouping(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            missing = Path(tmpdir) / "missing.jsonl"

            self.assertEqual(read_jackal_today_tokens(today="2026-05-18", log_path=missing), 0)
            self.assertEqual(read_jackal_tokens_by_date(log_path=missing), {})
            self.assertEqual(read_orca_usage_by_month(log_path=missing), {})
            self.assertEqual(
                read_orca_today_usage(today="2026-05-18", log_path=missing),
                {
                    "call_count": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_read_tokens": 0,
                    "cache_creation_tokens": 0,
                    "web_search_requests": 0,
                },
            )

    def test_read_orca_usage_by_month_groups_kst_month_and_skips_noise(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            log_path = Path(tmpdir) / "llm.jsonl"
            self._write_jsonl(
                log_path,
                [
                    {
                        "ts": "2026-04-30T23:30:00+00:00",
                        "type": "success",
                        "call_site": "orca.hunter",
                        "input_tokens": 10,
                        "output_tokens": 20,
                        "cache_read_tokens": 3,
                        "cache_creation_tokens": 4,
                        "web_search_requests": 2,
                    },
                    {
                        "ts": "2026-05-18T07:00:00+09:00",
                        "type": "success",
                        "call_site": "orca.reporter",
                        "input_tokens": "5",
                        "output_tokens": "6",
                        "web_search_requests": "1",
                    },
                    {
                        "ts": "2026-05-18T07:01:00+09:00",
                        "type": "success",
                        "call_site": "jackal.hunter",
                        "input_tokens": 999,
                        "output_tokens": 999,
                    },
                    {
                        "ts": "2026-05-18T07:02:00+09:00",
                        "type": "failure",
                        "call_site": "orca.devil",
                        "input_tokens": 999,
                        "output_tokens": 999,
                    },
                    "not-json",
                ],
            )

            totals = read_orca_usage_by_month(log_path=log_path)

        self.assertEqual(
            totals,
            {
                "2026-05": {
                    "call_count": 2,
                    "input_tokens": 15,
                    "output_tokens": 26,
                    "cache_read_tokens": 3,
                    "cache_creation_tokens": 4,
                    "web_search_requests": 3,
                }
            },
        )

    def test_read_orca_today_usage_filters_by_kst_date(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            log_path = Path(tmpdir) / "llm.jsonl"
            self._write_jsonl(
                log_path,
                [
                    {
                        "ts": "2026-05-17T15:30:00+00:00",
                        "type": "success",
                        "call_site": "orca.hunter",
                        "input_tokens": 1,
                        "output_tokens": 2,
                    },
                    {
                        "ts": "2026-05-17T14:59:00+00:00",
                        "type": "success",
                        "call_site": "orca.hunter",
                        "input_tokens": 100,
                        "output_tokens": 200,
                    },
                ],
            )

            usage = read_orca_today_usage(today="2026-05-18", log_path=log_path)

        self.assertEqual(
            usage,
            {
                "call_count": 1,
                "input_tokens": 1,
                "output_tokens": 2,
                "cache_read_tokens": 0,
                "cache_creation_tokens": 0,
                "web_search_requests": 0,
            },
        )

    @staticmethod
    def _write_jsonl(path: Path, entries: list[dict | str]) -> None:
        path.write_text(
            "\n".join(
                entry if isinstance(entry, str) else json.dumps(entry, separators=(",", ":"))
                for entry in entries
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
