import shutil
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

from apps.jackal import outcome_resolver as resolver
from apps.orca import state


KST = timezone(timedelta(hours=9))


def _history(*prices):
    rows = []
    for idx, price in enumerate(prices, start=1):
        if isinstance(price, tuple):
            high, low, close = price
        else:
            high = low = close = price
        rows.append(
            {
                "date": f"2026-05-{10 + idx:02d}",
                "high": high,
                "low": low,
                "close": close,
            }
        )
    return rows


class TestOutcomeResolver(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp())
        self.state_db = self.tmpdir / "orca_state.db"
        self.jackal_db = self.tmpdir / "jackal_state.db"
        self.audit_log = self.tmpdir / "contract_shadow_audit.log"
        self.patches = [
            patch.object(state, "STATE_DB_FILE", self.state_db),
            patch.object(state, "JACKAL_DB_FILE", self.jackal_db),
            patch("shared.audit.contract_shadow_audit.CONTRACT_SHADOW_AUDIT_LOG", self.audit_log),
        ]
        for item in self.patches:
            item.start()
        state.init_state_db()
        self.as_of = datetime(2026, 5, 16, 12, 0, tzinfo=KST)

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _insert_card(
        self,
        *,
        timestamp: str = "2026-05-10T10:00:00+09:00",
        ticker: str = "AAPL",
        target_price=105.0,
        stop_price=95.0,
        alerted: bool = True,
    ) -> None:
        state.sync_jackal_live_events(
            "scan",
            [
                {
                    "timestamp": timestamp,
                    "ticker": ticker,
                    "name": ticker,
                    "final_score": 80.0,
                    "current_price": 100.0,
                    "target_price": target_price,
                    "stop_price": stop_price,
                    "alerted": alerted,
                    "is_entry": True,
                    "outcome_checked": False,
                }
            ],
        )

    def _card(self):
        with state._connect_jackal() as conn:
            return conn.execute("SELECT * FROM jackal_prediction_cards").fetchone()

    def test_target_hit_returns_win(self):
        card = {"current_price": 100, "target_price": 105, "stop_price": 95}
        result = resolver._calculate_outcome(card, _history((106, 99, 104)), 1)
        self.assertEqual(result["outcome"], "win")

    def test_stop_hit_returns_loss(self):
        card = {"current_price": 100, "target_price": 105, "stop_price": 95}
        result = resolver._calculate_outcome(card, _history((101, 94, 96)), 1)
        self.assertEqual(result["outcome"], "loss")

    def test_neither_returns_neutral(self):
        card = {"current_price": 100, "target_price": 105, "stop_price": 95}
        result = resolver._calculate_outcome(card, _history((103, 97, 101)), 1)
        self.assertEqual(result["outcome"], "neutral")

    def test_default_threshold_without_target_stop(self):
        card = {"current_price": 100, "target_price": None, "stop_price": None}
        result = resolver._calculate_outcome(
            card,
            _history((100.2, 99.8, 100.0), (100.4, 99.9, 100.2), (101.2, 99.8, 100.5)),
            3,
        )
        self.assertEqual(result["outcome"], "win")

    def test_resolve_skips_not_aged(self):
        self._insert_card(timestamp="2026-05-16T09:00:00+09:00")
        result = resolver.resolve_open_prediction_cards(
            as_of=self.as_of,
            price_fetcher=lambda *_: _history((106, 99, 104)),
            include_shadow=False,
        )

        self.assertEqual(result["skipped_not_aged"], 1)
        self.assertEqual(self._card()["status"], "open")

    def test_1d_outcome_first_and_status_remains_open(self):
        self._insert_card(timestamp="2026-05-14T09:00:00+09:00")
        result = resolver.resolve_open_prediction_cards(
            as_of=self.as_of,
            price_fetcher=lambda *_: _history((106, 99, 104), (107, 98, 103)),
            include_shadow=False,
        )
        card = self._card()

        self.assertEqual(result["updated"], 1)
        self.assertEqual(card["outcome_d1"], "win")
        self.assertIsNone(card["outcome_d3"])
        self.assertEqual(card["status"], "open")

    def test_resolve_status_updates_after_5d(self):
        self._insert_card()
        result = resolver.resolve_open_prediction_cards(
            as_of=self.as_of,
            price_fetcher=lambda *_: _history(
                (101, 99, 100),
                (103, 98, 102),
                (106, 99, 105),
                (107, 100, 106),
                (108, 101, 107),
            ),
            include_shadow=False,
        )
        card = self._card()

        self.assertEqual(result["resolved"], 1)
        self.assertEqual(card["status"], "resolved")
        self.assertEqual(card["outcome_d1"], "neutral")
        self.assertEqual(card["outcome_d3"], "win")
        self.assertEqual(card["outcome_d5"], "win")
        self.assertEqual(card["actual_close_d5"], 107.0)

    def test_resolve_handles_fetch_failure(self):
        self._insert_card()

        def _raise(*_):
            raise RuntimeError("provider down")

        result = resolver.resolve_open_prediction_cards(
            as_of=self.as_of,
            price_fetcher=_raise,
            include_shadow=False,
        )

        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(self._card()["status"], "open")

    def test_resolve_is_idempotent(self):
        self._insert_card()
        fetcher = lambda *_: _history(
            (101, 99, 100),
            (103, 98, 102),
            (106, 99, 105),
            (107, 100, 106),
            (108, 101, 107),
        )

        first = resolver.resolve_open_prediction_cards(as_of=self.as_of, price_fetcher=fetcher, include_shadow=False)
        second = resolver.resolve_open_prediction_cards(as_of=self.as_of, price_fetcher=fetcher, include_shadow=False)

        self.assertEqual(first["resolved"], 1)
        self.assertEqual(second["checked"], 0)
        self.assertEqual(self._card()["status"], "resolved")

    def test_resolves_open_shadow_signal(self):
        shadow_id = state.record_jackal_shadow_signal(
            {
                "timestamp": "2026-05-10T10:00:00+09:00",
                "ticker": "MSFT",
                "market": "US",
                "price_at_scan": 100.0,
                "signal_family": "ma_support",
                "quality_score": 38.0,
            }
        )

        result = resolver.resolve_open_prediction_cards(
            as_of=self.as_of,
            price_fetcher=lambda *_: _history(
                (101, 99, 100),
                (102, 99, 101),
                (103, 100, 102),
                (104, 101, 103),
                (105, 102, 104),
            ),
            include_shadow=True,
        )

        with state._connect_jackal() as conn:
            row = conn.execute(
                "SELECT status, outcome_json FROM jackal_shadow_signals WHERE shadow_id = ?",
                (shadow_id,),
            ).fetchone()

        self.assertEqual(result["shadow"]["resolved"], 1)
        self.assertEqual(row["status"], "resolved")
        self.assertIn("outcome_d5", row["outcome_json"])


if __name__ == "__main__":
    unittest.main()
