"""Validation tests for the shared test fixture layer."""

from __future__ import annotations

import importlib
import os
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from tests.fixtures import (  # noqa: E402
    env_overrides,
    freeze_time,
    in_memory_jackal_db,
    in_memory_orca_db,
    isolated_filesystem,
    mock_anthropic,
    mock_telegram,
    mock_yfinance,
)


class TestTimeFixtures(unittest.TestCase):
    def test_freeze_time_patches_time_and_target_datetime(self):
        with freeze_time(
            "2026-04-22T10:00:00+09:00",
            datetime_targets=[f"{__name__}.datetime"],
        ) as frozen:
            self.assertEqual(time.time(), frozen.timestamp())
            self.assertEqual(datetime.now(timezone.utc), frozen.astimezone(timezone.utc))


class TestFilesystemFixtures(unittest.TestCase):
    def test_isolated_filesystem_changes_and_restores_cwd(self):
        original_cwd = Path.cwd()

        with isolated_filesystem() as tmpdir:
            self.assertEqual(Path.cwd(), tmpdir)
            Path("sample.json").write_text("{}", encoding="utf-8")
            self.assertTrue((tmpdir / "sample.json").exists())

        self.assertEqual(Path.cwd(), original_cwd)


class TestEnvironmentFixtures(unittest.TestCase):
    def test_env_overrides_sets_and_restores_values(self):
        os.environ["FIXTURE_TEST_ENV"] = "before"

        with env_overrides(FIXTURE_TEST_ENV="after", FIXTURE_NEW_ENV="new"):
            self.assertEqual(os.environ["FIXTURE_TEST_ENV"], "after")
            self.assertEqual(os.environ["FIXTURE_NEW_ENV"], "new")

        self.assertEqual(os.environ["FIXTURE_TEST_ENV"], "before")
        self.assertNotIn("FIXTURE_NEW_ENV", os.environ)
        os.environ.pop("FIXTURE_TEST_ENV", None)


class TestDatabaseFixtures(unittest.TestCase):
    def test_in_memory_orca_db_has_core_schema(self):
        with in_memory_orca_db() as conn:
            tables = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }

        self.assertTrue({"runs", "predictions", "outcomes"}.issubset(tables))

    def test_in_memory_jackal_db_has_core_schema(self):
        with in_memory_jackal_db() as conn:
            tables = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }

        self.assertTrue(
            {
                "jackal_shadow_signals",
                "jackal_live_events",
                "jackal_shadow_batches",
                "jackal_weight_snapshots",
                "jackal_recommendations",
                "jackal_accuracy_projection",
                "jackal_cooldowns",
            }.issubset(tables)
        )


class TestNetworkFixtures(unittest.TestCase):
    def test_mock_anthropic_intercepts_messages_create(self):
        sys.modules.pop("anthropic", None)

        with mock_anthropic("analysis result") as calls:
            anthropic = importlib.import_module("anthropic")
            response = anthropic.Anthropic(api_key="token").messages.create(
                model="demo",
                messages=[{"role": "user", "content": "hello"}],
            )

        self.assertEqual(response.content[0].text, "analysis result")
        self.assertEqual(calls[0]["kwargs"]["model"], "demo")

    def test_mock_yfinance_intercepts_ticker_and_download(self):
        sys.modules.pop("yfinance", None)

        with mock_yfinance({"AAPL": {"history": [1, 2, 3]}, "__download__": {"ok": True}}) as calls:
            yfinance = importlib.import_module("yfinance")
            history = yfinance.Ticker("AAPL").history(period="5d")
            download = yfinance.download("AAPL", period="5d")

        self.assertEqual(history, [1, 2, 3])
        self.assertEqual(download, {"ok": True})
        self.assertEqual(calls["ticker"][0]["ticker"], "AAPL")
        self.assertEqual(calls["download"][0]["args"][0], "AAPL")

    def test_mock_telegram_intercepts_notify_transport_send_message(self):
        sys.modules.pop("orca.notify_transport", None)

        with env_overrides(TELEGRAM_TOKEN="token", TELEGRAM_CHAT_ID="123"), mock_telegram(success=True) as calls:
            notify_transport = importlib.import_module("orca.notify_transport")
            ok = notify_transport.send_message("fixture hello")

        self.assertTrue(ok)
        self.assertEqual(len(calls), 1)
        self.assertIn("/sendMessage", calls[0]["url"])
        self.assertEqual(calls[0]["kwargs"]["json"]["text"], "fixture hello")


if __name__ == "__main__":
    unittest.main()
