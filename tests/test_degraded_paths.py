"""Degraded and failure-path tests for PR 1, PR 5, and Phase 5.

These tests lock in operationally critical failure branches documented in
docs/analysis/2026-04-22_repository_review.md Section 6 P1-4.
If any test fails, a degraded-path contract has drifted and needs
explicit review before further refactors proceed.
"""

from __future__ import annotations

import contextlib
import gc
import importlib
import io
import json
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _reset_modules(*module_names: str) -> None:
    for module_name in module_names:
        sys.modules.pop(module_name, None)


def _install_stub_modules() -> None:
    anthropic = types.ModuleType("anthropic")

    class DummyAnthropic:
        def __init__(self, api_key=None):
            self.api_key = api_key

    anthropic.Anthropic = DummyAnthropic

    httpx = types.ModuleType("httpx")

    def _unexpected_httpx_call(*args, **kwargs):
        raise AssertionError("Network access is not allowed in degraded-path tests")

    httpx.get = _unexpected_httpx_call
    httpx.post = _unexpected_httpx_call

    rich = types.ModuleType("rich")
    rich.box = types.SimpleNamespace(ROUNDED="rounded", SIMPLE="simple")

    rich_console = types.ModuleType("rich.console")

    class DummyConsole:
        def print(self, *args, **kwargs):
            return None

        def rule(self, *args, **kwargs):
            return None

    rich_console.Console = DummyConsole

    rich_panel = types.ModuleType("rich.panel")

    class DummyPanel:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    rich_panel.Panel = DummyPanel

    rich_table = types.ModuleType("rich.table")

    class DummyTable:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def add_column(self, *args, **kwargs):
            return None

        def add_row(self, *args, **kwargs):
            return None

    rich_table.Table = DummyTable

    sys.modules["anthropic"] = anthropic
    sys.modules["httpx"] = httpx
    sys.modules["rich"] = rich
    sys.modules["rich.console"] = rich_console
    sys.modules["rich.panel"] = rich_panel
    sys.modules["rich.table"] = rich_table


def _import_module(module_name: str):
    _install_stub_modules()
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def _import_run_cycle():
    _reset_modules(
        "orca.run_cycle",
        "orca.persist",
        "orca.present",
        "orca.notify",
        "orca.pipeline",
        "orca.postprocess",
        "orca.data",
        "orca.analysis",
        "orca.agents",
    )
    return _import_module("orca.run_cycle")


def _import_persist():
    _reset_modules("orca.persist", "orca.present", "orca.notify")
    return _import_module("orca.persist")


def _import_state():
    _reset_modules("orca.state")
    return importlib.import_module("orca.state")


def _exercise_market_data(
    *,
    yahoo_quality: str,
    fear_greed: dict | None,
) -> dict:
    """Run fetch_all_market_data with all external dependencies stubbed."""
    notify_stub = types.ModuleType("orca.notify")
    notify_stub.send_message = lambda *args, **kwargs: True

    base_fg = fear_greed or {
        "value": 55,
        "rating": "Neutral",
        "prev_close": 52,
        "source": "fear_greed_chart",
        "confidence": "보통",
    }
    base_pcr = {
        "pcr_spy": 0.9,
        "pcr_qqq": 0.95,
        "pcr_avg": 0.925,
        "pcr_signal": "중립",
    }
    base_krx = {
        "foreign_net": "1000",
        "institution_net": "-200",
        "individual_net": "-800",
        "foreign_buy": "5000",
        "foreign_sell": "4000",
        "source": "krx_api",
        "date": "2026-04-22",
    }
    base_fred = {
        "vix_fred": 21.0,
        "hy_spread": 3.1,
        "yield_curve": -0.2,
        "consumer_sent": 76.0,
        "rrp": 300.0,
        "dxy": 101.5,
        "fred_source": True,
    }
    base_fsc = {
        "samsung_fsc": 1.0,
        "sk_hynix_fsc": 2.0,
        "gold_price": 2300.0,
        "oil_price_diesel": 1600.0,
        "oil_price_gasoline": 1700.0,
        "fsc_source": True,
    }

    _reset_modules("orca.data", "orca.notify")
    _install_stub_modules()
    with patch.dict(sys.modules, {"orca.notify": notify_stub}):
        data = importlib.import_module("orca.data")
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_file = Path(tmpdir) / "orca_market_data.json"
            with patch.object(data, "DATA_FILE", temp_file), patch.object(
                data, "_get_market_status", return_value=("OPEN", "contract-test")
            ), patch.object(
                data, "check_volatility_alert", return_value=False
            ), patch.object(
                data,
                "fetch_yahoo_data",
                return_value={"data_quality": yahoo_quality},
            ), patch.object(
                data,
                "fetch_fear_greed",
                return_value=base_fg,
            ), patch.object(
                data,
                "fetch_put_call_ratio",
                return_value=base_pcr,
            ), patch.object(
                data,
                "fetch_krx_flow",
                return_value=base_krx,
            ), patch.object(
                data,
                "fetch_fred_indicators",
                return_value=base_fred,
            ), patch.object(
                data,
                "fetch_fsc_data",
                return_value=base_fsc,
            ), patch.object(
                data,
                "fetch_korea_news",
                return_value=["headline"],
            ):
                result = data.fetch_all_market_data()

            persisted = json.loads(temp_file.read_text(encoding="utf-8"))
            if result != persisted:
                raise AssertionError("Persisted market-data payload differs from the returned payload")

    _reset_modules("orca.data")
    return result


@contextlib.contextmanager
def _temporary_state_db_pair(state):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        state_db = Path(tmpdir) / "orca_state.db"
        jackal_db = Path(tmpdir) / "jackal_state.db"
        with patch.object(state, "STATE_DB_FILE", state_db), patch.object(state, "JACKAL_DB_FILE", jackal_db):
            state.clear_health_events()
            state.init_state_db()
            try:
                yield state_db, jackal_db
            finally:
                for checkpoint in (state.checkpoint_jackal_db,):
                    try:
                        checkpoint()
                    except Exception:
                        pass
                try:
                    with state._connect_orca() as conn:
                        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except Exception:
                    pass
                state.clear_health_events()
                gc.collect()


class TestMarketDataQualityDegradedPaths(unittest.TestCase):
    """Group 1: data_quality poor/degraded classification."""

    def test_fetch_all_market_data_returns_poor_and_failed_sources(self):
        payload = _exercise_market_data(yahoo_quality="poor", fear_greed=None)

        self.assertEqual(
            payload["data_quality"],
            "poor",
            f"Expected poor data_quality, got {payload['data_quality']!r}",
        )
        self.assertIsInstance(payload["failed_sources"], list, "failed_sources should stay a list")
        self.assertTrue(payload["failed_sources"], "poor payload should preserve non-empty failed_sources")
        self.assertTrue(
            any(item.get("source") == "YAHOO_CORE" for item in payload["failed_sources"]),
            f"Expected YAHOO_CORE in failed_sources, got {payload['failed_sources']!r}",
        )

    def test_fetch_all_market_data_returns_degraded_on_primary_partial_failure(self):
        payload = _exercise_market_data(
            yahoo_quality="ok",
            fear_greed={
                "value": "N/A",
                "rating": "N/A",
                "prev_close": "N/A",
                "source": "unknown",
                "confidence": "낮음",
            },
        )

        self.assertEqual(
            payload["data_quality"],
            "degraded",
            f"Expected degraded data_quality, got {payload['data_quality']!r}",
        )
        self.assertTrue(payload["failed_sources"], "degraded payload should preserve non-empty failed_sources")
        self.assertTrue(
            any(item.get("source") == "FEAR_GREED" for item in payload["failed_sources"]),
            f"Expected FEAR_GREED failure marker, got {payload['failed_sources']!r}",
        )


class TestRunCycleDegradedBranches(unittest.TestCase):
    """Groups 1 and 2: run_orca_cycle poor/degraded handling."""

    def test_run_cycle_poor_data_stops_before_pipeline_and_saves_failed_report(self):
        run_cycle = _import_run_cycle()
        failed_sources = [{"source": "YAHOO_CORE", "error": "core_data_missing", "category": "primary"}]
        captured: dict[str, object] = {}
        pipeline_mock = MagicMock(name="run_agent_pipeline")

        def _capture_failed_report(report: dict):
            captured["report"] = report
            return Path("reports/poor_failed.json")

        with tempfile.TemporaryDirectory() as tmpdir, contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(run_cycle, "REPORTS_DIR", Path(tmpdir)))
            stack.enter_context(patch.object(run_cycle, "state_start_run", return_value=None))
            stack.enter_context(
                patch.object(
                    run_cycle,
                    "fetch_all_market_data",
                    return_value={"data_quality": "poor", "failed_sources": failed_sources},
                )
            )
            stack.enter_context(patch.object(run_cycle, "update_cost", return_value=None))
            stack.enter_context(patch.object(run_cycle, "get_monthly_cost_summary", return_value="$0"))
            stack.enter_context(patch("orca.data.load_cost", return_value={"monthly_runs": {}}))
            stack.enter_context(patch.object(run_cycle.persist, "save_report", side_effect=_capture_failed_report))
            stack.enter_context(patch.object(run_cycle.pipeline, "run_agent_pipeline", pipeline_mock))
            stack.enter_context(patch.object(run_cycle.present, "send_generic_notice", return_value=True))
            stack.enter_context(patch.object(run_cycle.present, "print_health_badge", return_value=None))
            stack.enter_context(patch.object(run_cycle.present.console, "print", return_value=None))
            with self.assertRaises(SystemExit) as exc:
                run_cycle.run_orca_cycle(mode="MORNING", memory=[])

        self.assertEqual(exc.exception.code, 1, "poor data branch should exit with status 1")
        pipeline_mock.assert_not_called()
        report = captured["report"]
        self.assertEqual(report["status"], "failed", f"Expected failed report, got {report!r}")
        self.assertEqual(report["failed_sources"], failed_sources, "poor branch should preserve failed_sources")
        self.assertEqual(
            report["health"]["status"],
            "failed",
            f"Poor branch health should be failed, got {report['health']!r}",
        )
        self.assertIn(
            "external_data_degraded",
            report["health"]["degraded_reasons"],
            f"Poor branch should record external_data_degraded, got {report['health']!r}",
        )

    def test_run_cycle_degraded_data_records_health_and_continues(self):
        run_cycle = _import_run_cycle()
        failed_sources = [{"source": "FEAR_GREED", "error": "unavailable", "category": "primary"}]
        captured: dict[str, object] = {}
        report_payload = {
            "one_line_summary": "degraded-path smoke",
            "market_regime": "중립",
            "confidence_overall": "보통",
            "mode_label": "저녁 마감",
        }
        pipeline_mock = MagicMock(
            name="run_agent_pipeline",
            return_value=({"market_snapshot": {}}, {"analysis": True}, {"risk": True}, dict(report_payload)),
        )

        def _capture_final_report(report: dict, health_tracker, *, failed_sources=None):
            captured["report"] = dict(report)
            captured["failed_sources"] = failed_sources
            captured["health"] = health_tracker.to_report_payload(failed=False)
            return Path("reports/degraded_final.json")

        with tempfile.TemporaryDirectory() as tmpdir, contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(run_cycle, "REPORTS_DIR", Path(tmpdir)))
            stack.enter_context(patch.object(run_cycle, "state_start_run", return_value=None))
            stack.enter_context(
                patch.object(
                    run_cycle,
                    "fetch_all_market_data",
                    return_value={"data_quality": "degraded", "failed_sources": failed_sources},
                )
            )
            stack.enter_context(patch.object(run_cycle, "update_cost", return_value=None))
            stack.enter_context(patch.object(run_cycle, "get_monthly_cost_summary", return_value="$0"))
            stack.enter_context(patch("orca.data.load_cost", return_value={"monthly_runs": {}}))
            stack.enter_context(patch.object(run_cycle, "build_baseline_context", return_value=""))
            stack.enter_context(patch.object(run_cycle, "get_regime_drift", return_value=""))
            stack.enter_context(patch.object(run_cycle.pipeline, "run_agent_pipeline", pipeline_mock))
            stack.enter_context(
                patch.object(
                    run_cycle.postprocess,
                    "sanitize_korea_claims",
                    side_effect=lambda report, market_data: report,
                )
            )
            stack.enter_context(patch.object(run_cycle.postprocess, "run_candidate_review", return_value={}))
            stack.enter_context(
                patch.object(
                    run_cycle.postprocess,
                    "compact_probability_summary",
                    return_value={"overall": {}, "trusted_families": [], "cautious_families": []},
                )
            )
            stack.enter_context(patch.object(run_cycle.postprocess, "maybe_save_baseline", return_value=None))
            stack.enter_context(patch.object(run_cycle.postprocess, "run_secondary_analyses", return_value=None))
            stack.enter_context(patch.object(run_cycle.postprocess, "update_pattern_database", return_value=None))
            stack.enter_context(patch.object(run_cycle.persist, "save_memory", return_value=None))
            stack.enter_context(patch.object(run_cycle.persist, "record_predictions", return_value={"count": 0}))
            stack.enter_context(patch.object(run_cycle.persist, "load_memory", return_value=[]))
            stack.enter_context(
                patch.object(run_cycle.persist, "persist_final_report", side_effect=_capture_final_report)
            )
            stack.enter_context(patch.object(run_cycle.present, "send_start_notice", return_value=None))
            stack.enter_context(patch.object(run_cycle.present, "print_report", return_value=None))
            stack.enter_context(patch.object(run_cycle.present, "print_health_badge", return_value=None))
            stack.enter_context(patch.object(run_cycle.present, "send_final_report", return_value=None))
            stack.enter_context(patch.object(run_cycle.present.console, "print", return_value=None))
            run_cycle.run_orca_cycle(mode="EVENING", memory=[])

        pipeline_mock.assert_called_once()
        self.assertEqual(
            captured["report"]["data_quality"],
            "degraded",
            f"Expected degraded report data_quality, got {captured['report']!r}",
        )
        self.assertEqual(
            captured["failed_sources"],
            failed_sources,
            "degraded path should preserve failed_sources into final report persistence",
        )
        self.assertEqual(
            captured["health"]["status"],
            "degraded",
            f"Expected degraded health payload, got {captured['health']!r}",
        )
        self.assertIn(
            "external_data_degraded",
            captured["health"]["degraded_reasons"],
            f"Expected external_data_degraded in health payload, got {captured['health']!r}",
        )


class TestPersistStateFailurePath(unittest.TestCase):
    """Group 3: persist.record_predictions failure degradation."""

    def test_record_predictions_records_state_db_unavailable_without_raising(self):
        persist = _import_persist()
        run_cycle = _import_run_cycle()
        health_tracker = run_cycle.HealthTracker()

        with patch.object(
            persist,
            "record_report_predictions",
            side_effect=sqlite3.OperationalError("state db unavailable"),
        ), patch.object(
            persist.state_module, "drain_health_events", return_value=[]
        ), patch(
            "orca.present.console.print", return_value=None
        ):
            result = persist.record_predictions(run_id="run_1", report={"mode": "MORNING"}, health_tracker=health_tracker)

        self.assertEqual(result, {"count": 0}, f"Expected degraded zero-count stats, got {result!r}")
        health = health_tracker.to_report_payload(failed=False)
        self.assertEqual(health["status"], "degraded", f"Expected degraded health, got {health!r}")
        self.assertIn(
            "state_db_unavailable",
            health["degraded_reasons"],
            f"Expected state_db_unavailable health code, got {health!r}",
        )


class TestPhase5BestEffortPaths(unittest.TestCase):
    """Group 4: 2-phase write best-effort behavior."""

    def test_record_jackal_shadow_signal_keeps_primary_write_when_secondary_fails(self):
        state = _import_state()
        entry = {
            "timestamp": "2026-04-22T09:00:00+09:00",
            "ticker": "005930.KS",
            "market": "KR",
            "signal_family": "breakout",
            "quality_label": "high",
            "quality_score": 0.87,
        }

        with _temporary_state_db_pair(state), patch.object(
            state, "record_candidate", side_effect=RuntimeError("secondary registry failure")
        ), contextlib.redirect_stderr(io.StringIO()) as stderr:
            shadow_id = state.record_jackal_shadow_signal(entry)

            with state._connect_jackal() as conn:
                row = conn.execute(
                    "SELECT shadow_id, status, ticker FROM jackal_shadow_signals WHERE shadow_id = ?",
                    (shadow_id,),
                ).fetchone()

        self.assertIsNotNone(row, "Primary JACKAL shadow write should persist even when secondary write fails")
        self.assertEqual(row["status"], "open", f"Expected open shadow signal row, got {dict(row)!r}")
        self.assertIn(
            "record_jackal_shadow_signal",
            stderr.getvalue(),
            f"Expected stderr warning for record_jackal_shadow_signal, got {stderr.getvalue()!r}",
        )

    def test_resolve_jackal_shadow_signal_keeps_primary_resolution_when_secondary_fails(self):
        state = _import_state()
        entry = {
            "timestamp": "2026-04-22T09:00:00+09:00",
            "ticker": "005930.KS",
            "market": "KR",
            "signal_family": "breakout",
            "quality_label": "high",
            "quality_score": 0.87,
        }
        outcome = {"worked": True, "outcome_pct": 4.2}

        with _temporary_state_db_pair(state):
            with patch.object(state, "record_candidate", return_value=None):
                shadow_id = state.record_jackal_shadow_signal(entry)

            with patch.object(
                state, "record_candidate", side_effect=RuntimeError("secondary registry failure")
            ), contextlib.redirect_stderr(io.StringIO()) as stderr:
                state.resolve_jackal_shadow_signal(shadow_id, outcome)

            with state._connect_jackal() as conn:
                row = conn.execute(
                    "SELECT status, outcome_json FROM jackal_shadow_signals WHERE shadow_id = ?",
                    (shadow_id,),
                ).fetchone()

        self.assertIsNotNone(row, "Resolved JACKAL shadow signal should remain in primary DB")
        self.assertEqual(row["status"], "resolved", f"Expected resolved status, got {dict(row)!r}")
        self.assertEqual(
            json.loads(row["outcome_json"]),
            outcome,
            f"Expected outcome payload to persist in primary DB, got {row['outcome_json']!r}",
        )
        self.assertIn(
            "resolve_jackal_shadow_signal",
            stderr.getvalue(),
            f"Expected stderr warning for resolve_jackal_shadow_signal, got {stderr.getvalue()!r}",
        )

    def test_sync_jackal_live_events_keeps_primary_events_when_secondary_fails(self):
        state = _import_state()
        entry = {
            "timestamp": "2026-04-22T09:30:00+09:00",
            "ticker": "NVDA",
            "market": "US",
            "final_score": 82.5,
            "alerted": True,
            "is_entry": True,
            "outcome_checked": False,
        }

        with _temporary_state_db_pair(state), patch.object(
            state, "record_candidate", side_effect=RuntimeError("secondary registry failure")
        ), contextlib.redirect_stderr(io.StringIO()) as stderr:
            synced = state.sync_jackal_live_events("scan", [entry])

            with state._connect_jackal() as conn:
                row = conn.execute(
                    "SELECT event_type, ticker, alerted FROM jackal_live_events WHERE ticker = ?",
                    ("NVDA",),
                ).fetchone()

        self.assertEqual(synced, 1, f"Expected 1 synced JACKAL live event, got {synced}")
        self.assertIsNotNone(row, "Primary JACKAL live event write should persist despite secondary failure")
        self.assertEqual(row["event_type"], "scan", f"Unexpected live event row: {dict(row)!r}")
        self.assertIn(
            "sync_jackal_live_events",
            stderr.getvalue(),
            f"Expected stderr warning for sync_jackal_live_events, got {stderr.getvalue()!r}",
        )


class TestNotificationFailurePath(unittest.TestCase):
    """Group 5: notification_failed on error-notice failure."""

    def test_notification_failure_records_notification_failed_health_code(self):
        run_cycle = _import_run_cycle()
        recorded_codes: list[str] = []
        original_record_exception = run_cycle.HealthTracker.record_exception

        def _spy_record_exception(self, code, where, exception, *, message=None):
            recorded_codes.append(code)
            return original_record_exception(self, code, where, exception, message=message)

        with tempfile.TemporaryDirectory() as tmpdir, contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(run_cycle, "REPORTS_DIR", Path(tmpdir)))
            stack.enter_context(patch.object(run_cycle, "state_start_run", return_value=None))
            stack.enter_context(
                patch.object(
                    run_cycle,
                    "fetch_all_market_data",
                    return_value={"data_quality": "ok", "failed_sources": []},
                )
            )
            stack.enter_context(patch.object(run_cycle, "update_cost", return_value=None))
            stack.enter_context(patch.object(run_cycle, "get_monthly_cost_summary", return_value="$0"))
            stack.enter_context(patch("orca.data.load_cost", return_value={"monthly_runs": {}}))
            stack.enter_context(patch.object(run_cycle, "build_baseline_context", return_value=""))
            stack.enter_context(patch.object(run_cycle.present, "send_start_notice", return_value=None))
            stack.enter_context(
                patch.object(run_cycle.pipeline, "run_agent_pipeline", side_effect=RuntimeError("pipeline failed"))
            )
            stack.enter_context(
                patch.object(run_cycle.persist, "save_report", return_value=Path("reports/error_failed.json"))
            )
            stack.enter_context(patch.object(run_cycle.present, "print_health_badge", return_value=None))
            stack.enter_context(
                patch.object(run_cycle.present, "send_error_notice", side_effect=RuntimeError("telegram failed"))
            )
            stack.enter_context(patch.object(run_cycle.present.console, "print", return_value=None))
            stack.enter_context(patch.object(run_cycle.HealthTracker, "record_exception", new=_spy_record_exception))
            stack.enter_context(patch.object(run_cycle.traceback, "print_exc", return_value=None))
            with self.assertRaises(SystemExit) as exc:
                run_cycle.run_orca_cycle(mode="EVENING", memory=[])

        self.assertEqual(exc.exception.code, 1, "notification failure path should still terminate with exit code 1")
        self.assertIn(
            "notification_failed",
            recorded_codes,
            f"Expected notification_failed health code to be recorded, got {recorded_codes!r}",
        )


if __name__ == "__main__":
    unittest.main()
