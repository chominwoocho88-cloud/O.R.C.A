import contextlib
import importlib
import io
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _install_stub_modules() -> None:
    anthropic = types.ModuleType("anthropic")

    class DummyAnthropic:
        def __init__(self, api_key=None):
            self.api_key = api_key

    anthropic.Anthropic = DummyAnthropic

    httpx = types.ModuleType("httpx")

    class DummyResponse:
        def raise_for_status(self):
            return None

    def post(*args, **kwargs):
        return DummyResponse()

    httpx.post = post

    rich = types.ModuleType("rich")
    rich_console = types.ModuleType("rich.console")

    class DummyConsole:
        def print(self, *args, **kwargs):
            return None

    rich_console.Console = DummyConsole
    rich.console = rich_console

    sys.modules["anthropic"] = anthropic
    sys.modules["httpx"] = httpx
    sys.modules["rich"] = rich
    sys.modules["rich.console"] = rich_console


def _import_analysis():
    _install_stub_modules()
    sys.modules.pop("orca.analysis", None)
    return importlib.import_module("orca.analysis")


def _import_state():
    sys.modules.pop("orca.state", None)
    return importlib.import_module("orca.state")


class VerificationBehaviorTests(unittest.TestCase):
    def test_verify_price_handles_index_level_targets(self):
        analysis = _import_analysis()

        results = analysis._verify_price(
            [
                {
                    "event": "나스닥",
                    "confirms_if": "나스닥 24,200pt 이상 종가 유지",
                    "invalidates_if": "나스닥 23,500pt 이하 종가",
                    "quality": "ok",
                }
            ],
            {"nasdaq": "24,377", "nasdaq_change": "+0.72%"},
        )

        self.assertEqual(results[0]["verdict"], "confirmed")
        self.assertIn("레벨 충족", results[0]["evidence"])
        self.assertEqual(results[0]["category"], "ok")

    def test_verify_price_handles_stock_percent_targets(self):
        analysis = _import_analysis()

        results = analysis._verify_price(
            [
                {
                    "event": "SK하이닉스",
                    "confirms_if": "SK하이닉스 +2% 이상",
                    "invalidates_if": "SK하이닉스 -3% 이하",
                }
            ],
            {"sk_hynix_change": "+2.34%"},
        )

        self.assertEqual(results[0]["verdict"], "confirmed")
        self.assertIn("SK하이닉스", results[0]["evidence"])

    def test_run_verification_logs_na_when_nothing_is_judged(self):
        analysis = _import_analysis()
        memory = [
            {
                "analysis_date": "2026-04-21",
                "thesis_killers": [
                    {
                        "event": "나스닥",
                        "confirms_if": "나스닥 24,200pt 이상 종가 유지",
                        "invalidates_if": "나스닥 23,500pt 이하 종가",
                    }
                ],
            }
        ]
        accuracy = {
            "total": 0,
            "correct": 0,
            "by_category": {},
            "history": [],
            "history_by_category": [],
            "weak_areas": [],
            "strong_areas": [],
            "dir_total": 0,
            "dir_correct": 0,
        }
        stdout = io.StringIO()

        with patch.dict(sys.modules, {"orca.data": types.SimpleNamespace(load_market_data=lambda: {})}), patch.object(
            analysis, "_load", side_effect=[memory, accuracy]
        ), patch.object(
            analysis,
            "_verify_price",
            return_value=[{"event": "나스닥", "verdict": "unclear", "evidence": "", "category": "기타"}],
        ), patch.object(analysis, "_ai_verify", return_value=[]), patch.object(
            analysis, "update_weights_from_accuracy", return_value=[]
        ), patch.object(
            analysis, "resolve_verification_outcomes", return_value={"matched": 0, "updated": 0, "unmatched": []}
        ), patch.object(
            analysis, "_save", return_value=None
        ), patch.object(
            analysis, "_send_verification_report", return_value=None
        ), patch.object(
            analysis, "_today", return_value="2026-04-22"
        ), patch.object(
            analysis, "get_orca_flag", return_value=False
        ), contextlib.redirect_stdout(stdout):
            analysis.run_verification()

        self.assertIn("Done. Today accuracy: N/A", stdout.getvalue())


class StateAliasTests(unittest.TestCase):
    def test_resolve_verification_outcomes_matches_legacy_aria_rows(self):
        state = _import_state()
        tmpdir = tempfile.mkdtemp()
        try:
            state_db = Path(tmpdir) / "orca_state.db"
            jackal_db = Path(tmpdir) / "jackal_state.db"

            with patch.object(state, "STATE_DB_FILE", state_db), patch.object(state, "JACKAL_DB_FILE", jackal_db):
                state.init_state_db()

                with state._connect_orca() as conn:
                    conn.execute(
                        """
                        INSERT INTO runs (run_id, system, analysis_date, started_at, status)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        ("run_1", "aria", "2026-04-21", "2026-04-21T09:00:00+09:00", "completed"),
                    )
                    conn.execute(
                        """
                        INSERT INTO predictions (
                            prediction_id, external_key, run_id, system, analysis_date,
                            prediction_kind, event_name, created_at, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            "pred_1",
                            "aria:2026-04-21:morning:thesis:나스닥",
                            "run_1",
                            "aria",
                            "2026-04-21",
                            "thesis_killer",
                            "나스닥",
                            "2026-04-21T09:00:00+09:00",
                            "open",
                        ),
                    )

                resolution = state.resolve_verification_outcomes(
                    "2026-04-21",
                    [
                        {
                            "event": "나스닥",
                            "verdict": "confirmed",
                            "evidence": "나스닥 24,377.00 (레벨 충족)",
                            "category": "ok",
                        }
                    ],
                    resolved_analysis_date="2026-04-22",
                    metadata={"verification_date": "2026-04-22"},
                )

                self.assertEqual(resolution["matched"], 1)
                self.assertEqual(resolution["updated"], 0)

                with state._connect_orca() as conn:
                    row = conn.execute(
                        "SELECT verdict FROM outcomes WHERE prediction_id = ?",
                        ("pred_1",),
                    ).fetchone()
                    self.assertIsNotNone(row)
                    self.assertEqual(row["verdict"], "confirmed")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
