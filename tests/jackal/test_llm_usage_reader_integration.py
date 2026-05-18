from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.jackal import compact
from apps.jackal.pipeline import shield


class JackalUsageReaderIntegrationTests(unittest.TestCase):
    def test_shield_budget_uses_llm_log_tokens(self):
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
                        "cache_read_tokens": 1,
                        "cache_creation_tokens": 2,
                    },
                    {
                        "ts": "2026-05-18T08:01:00+09:00",
                        "type": "success",
                        "call_site": "orca.hunter",
                        "input_tokens": 100,
                        "output_tokens": 200,
                    },
                ],
            )
            instance = shield.JackalShield(scan_root=Path(tmpdir))
            with patch.object(shield, "read_jackal_today_tokens", return_value=33):
                result = instance._check_budget()

        self.assertEqual(result["today_tokens"], 33)
        self.assertEqual(result["source"], "llm_log")
        self.assertFalse(result["exceeded"])

    def test_shield_budget_falls_back_to_compact_log_without_llm_entries(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            instance = shield.JackalShield(scan_root=Path(tmpdir))
            instance.compact_log = Path(tmpdir) / "compact_log.json"
            instance.compact_log.write_text(
                json.dumps(
                    [
                        {"timestamp": "2026-05-18T08:00:00", "tokens_before": 12},
                        {"timestamp": "2026-05-17T08:00:00", "tokens_before": 99},
                    ]
                ),
                encoding="utf-8",
            )
            with patch.object(shield, "read_jackal_today_tokens", return_value=0), patch.object(
                shield, "datetime", _fake_datetime("2026-05-18")
            ):
                result = instance._check_budget()

        self.assertEqual(result["today_tokens"], 12)
        self.assertEqual(result["source"], "compact_log(fallback)")

    def test_shield_spike_uses_llm_log_grouping(self):
        instance = shield.JackalShield()
        with patch.object(
            shield,
            "read_jackal_tokens_by_date",
            return_value={"2026-05-17": 100, "2026-05-18": 350},
        ), patch.object(shield, "datetime", _fake_datetime("2026-05-18")):
            result = instance._detect_spike()

        self.assertTrue(result["detected"])
        self.assertEqual(result["ratio"], 3.5)

    def test_compact_today_tokens_prefers_llm_log(self):
        instance = compact.JackalCompact()
        with patch.object(compact, "read_jackal_today_tokens", return_value=44):
            self.assertEqual(instance._get_today_tokens(), 44)

    def test_compact_today_tokens_returns_zero_without_llm_entries(self):
        instance = compact.JackalCompact()
        with patch.object(compact, "read_jackal_today_tokens", return_value=0):
            self.assertEqual(instance._get_today_tokens(), 0)

    @staticmethod
    def _write_jsonl(path: Path, entries: list[dict]) -> None:
        path.write_text(
            "\n".join(json.dumps(entry, separators=(",", ":")) for entry in entries),
            encoding="utf-8",
        )


def _fake_datetime(iso_date: str):
    class _FakeDateTime:
        @staticmethod
        def now():
            return _FakeNow(iso_date)

    return _FakeDateTime


def _fake_date_class(iso_date: str):
    class _FakeDateClass:
        @staticmethod
        def today():
            return _FakeDate(iso_date)

    return _FakeDateClass


class _FakeNow:
    def __init__(self, iso_date: str) -> None:
        self._iso_date = iso_date

    def date(self):
        return _FakeDate(self._iso_date)


class _FakeDate:
    def __init__(self, iso_date: str) -> None:
        self._iso_date = iso_date

    def isoformat(self) -> str:
        return self._iso_date

    def __sub__(self, _delta):
        return _FakeDate("2026-05-17")


if __name__ == "__main__":
    unittest.main()
