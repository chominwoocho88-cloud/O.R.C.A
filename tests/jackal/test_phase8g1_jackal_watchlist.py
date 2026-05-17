import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from jackal import watchlist


def _create_candidate_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE candidate_registry (
            candidate_id TEXT PRIMARY KEY,
            external_key TEXT NOT NULL UNIQUE,
            source_system TEXT NOT NULL,
            source_event_type TEXT NOT NULL,
            source_event_id TEXT,
            source_run_id TEXT,
            source_session_id TEXT,
            ticker TEXT NOT NULL,
            name TEXT,
            market TEXT,
            detected_at TEXT NOT NULL,
            analysis_date TEXT NOT NULL,
            signal_family TEXT,
            quality_label TEXT,
            quality_score REAL,
            orca_alignment TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            payload_json TEXT NOT NULL,
            latest_outcome_horizon TEXT,
            latest_outcome_at TEXT,
            latest_outcome_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def _insert_candidate(
    path: Path,
    *,
    candidate_id: str,
    ticker: str,
    status: str,
    detected_at: str,
    name: str | None = None,
    market: str | None = None,
    quality_score: float = 70.0,
) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        INSERT INTO candidate_registry (
            candidate_id, external_key, source_system, source_event_type,
            ticker, name, market, detected_at, analysis_date, signal_family,
            quality_label, quality_score, status, payload_json, created_at, updated_at
        ) VALUES (?, ?, 'jackal', 'scan', ?, ?, ?, ?, '2026-05-10',
                  'momentum', 'strong', ?, ?, '{}', ?, ?)
        """,
        (
            candidate_id,
            "key-" + candidate_id,
            ticker,
            name,
            market,
            detected_at,
            quality_score,
            status,
            detected_at,
            detected_at,
        ),
    )
    conn.commit()
    conn.close()


class Phase8g1CandidateRegistryWatchlistTests(unittest.TestCase):
    def test_empty_db_path_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(watchlist, "STATE_DB_FILE", Path(tmp) / "missing.db"):
                result = watchlist._load_candidate_registry_watchlist()

        self.assertEqual(result, {})

    def test_status_filter_excludes_resolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state.db"
            _create_candidate_db(db)
            now = datetime.now(timezone.utc).isoformat()
            _insert_candidate(db, candidate_id="open1", ticker="NVDA", status="open", detected_at=now)
            _insert_candidate(db, candidate_id="resolved1", ticker="AVGO", status="resolved", detected_at=now)
            _insert_candidate(db, candidate_id="tracking1", ticker="005930.KS", status="tracking", detected_at=now)

            with patch.object(watchlist, "STATE_DB_FILE", db):
                result = watchlist._load_candidate_registry_watchlist()

        self.assertIn("NVDA", result)
        self.assertIn("005930.KS", result)
        self.assertNotIn("AVGO", result)
        self.assertEqual(result["NVDA"]["source"], "candidate_registry")

    def test_days_lookback_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state.db"
            _create_candidate_db(db)
            recent = datetime.now(timezone.utc).isoformat()
            old = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
            _insert_candidate(db, candidate_id="recent1", ticker="NVDA", status="open", detected_at=recent)
            _insert_candidate(db, candidate_id="old1", ticker="AVGO", status="open", detected_at=old)

            with patch.object(watchlist, "STATE_DB_FILE", db):
                result = watchlist._load_candidate_registry_watchlist(days_lookback=90)

        self.assertIn("NVDA", result)
        self.assertNotIn("AVGO", result)


class Phase8g1KisHoldingsWatchlistTests(unittest.TestCase):
    def test_empty_holdings_returns_empty(self):
        client = MagicMock()
        client.is_configured.return_value = True
        client.get_account_balance.return_value = None

        with patch("shared.broker.get_shared_kis_client", return_value=client):
            result = watchlist._load_kis_holdings_watchlist()

        self.assertEqual(result, {})

    def test_korean_ticker_suffix(self):
        client = MagicMock()
        client.is_configured.return_value = True
        client.get_account_balance.return_value = {
            "holdings": [
                {
                    "ticker": "005930",
                    "name": "Samsung Electronics",
                    "quantity": 3,
                    "avg_price": 65000,
                    "current_price": 67000,
                    "valuation": 201000,
                }
            ]
        }

        with patch("shared.broker.get_shared_kis_client", return_value=client):
            result = watchlist._load_kis_holdings_watchlist()

        self.assertIn("005930.KS", result)
        self.assertEqual(result["005930.KS"]["source"], "kis_holdings")
        self.assertEqual(result["005930.KS"]["portfolio"], True)
        self.assertEqual(result["005930.KS"]["currency"], "KRW")

    def test_us_ticker_no_suffix(self):
        client = MagicMock()
        client.is_configured.return_value = True
        client.get_account_balance.return_value = {
            "holdings": [{"ticker": "NVDA", "name": "NVIDIA"}]
        }

        with patch("shared.broker.get_shared_kis_client", return_value=client):
            result = watchlist._load_kis_holdings_watchlist()

        self.assertIn("NVDA", result)
        self.assertNotIn("NVDA.KS", result)


class Phase8g1LoadJackalWatchlistTests(unittest.TestCase):
    def test_kis_priority_over_registry(self):
        kis = {
            "005930.KS": {"ticker": "005930.KS", "source": "kis_holdings", "name": "Samsung Electronics"}
        }
        registry = {
            "005930.KS": {"ticker": "005930.KS", "source": "candidate_registry", "name": "old"},
            "NVDA": {"ticker": "NVDA", "source": "candidate_registry"},
        }

        with patch.object(watchlist, "_load_kis_holdings_watchlist", return_value=kis):
            with patch.object(watchlist, "_load_candidate_registry_watchlist", return_value=registry):
                result = watchlist.load_jackal_watchlist()

        self.assertEqual(result["005930.KS"]["source"], "kis_holdings")
        self.assertIn("NVDA", result)

    def test_registry_supplements_kis(self):
        with patch.object(watchlist, "_load_kis_holdings_watchlist", return_value={}):
            with patch.object(
                watchlist,
                "_load_candidate_registry_watchlist",
                return_value={"NVDA": {"ticker": "NVDA", "source": "candidate_registry"}},
            ):
                result = watchlist.load_jackal_watchlist()

        self.assertEqual(result["NVDA"]["source"], "candidate_registry")

    def test_both_empty_returns_empty(self):
        with patch.object(watchlist, "_load_kis_holdings_watchlist", return_value={}):
            with patch.object(watchlist, "_load_candidate_registry_watchlist", return_value={}):
                result = watchlist.load_jackal_watchlist()

        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
