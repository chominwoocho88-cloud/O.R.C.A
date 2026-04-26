from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rich.panel import Panel

from orca import dashboard
from orca import historical_context
from orca import notify
from orca import pipeline
from orca import present


def _features() -> dict:
    return {
        "vix_level": 18.5,
        "sp500_momentum_5d": 1.2,
        "sp500_momentum_20d": 3.4,
        "nasdaq_momentum_5d": 1.5,
        "nasdaq_momentum_20d": 4.1,
        "regime": "위험선호",
        "dominant_sectors": ["Technology", "Communication Services"],
    }


def _lesson(ticker: str = "NVDA", value: float = 12.5) -> dict:
    return {
        "lesson_id": f"lesson_{ticker}",
        "ticker": ticker,
        "analysis_date": "2026-04-01",
        "signal_family": "momentum_pullback",
        "lesson_value": value,
        "peak_pct": value + 1.0,
        "peak_day": 5,
        "quality_tier": "high",
        "relevance_score": 0.91,
        "cluster_id": "cluster_c05",
        "cluster_label": "medium_vix_neutral_riskon_growth",
    }


def _context() -> dict:
    return {
        "cluster_id": "cluster_c05",
        "cluster_label": "medium_vix_neutral_riskon_growth",
        "cluster_size": 105,
        "top_lessons": [_lesson("NVDA", 12.5), _lesson("AVGO", 8.4)],
        "win_rate": 1.0,
        "avg_value": 10.45,
        "high_quality_count": 2,
    }


def _report() -> dict:
    return {
        "mode": "MORNING",
        "mode_label": "Morning",
        "analysis_date": "2026-04-27",
        "analysis_time": "09:00 KST",
        "market_regime": "위험선호",
        "confidence_overall": "높음",
        "one_line_summary": "테스트용 ORCA 리포트",
        "outflows": [],
        "inflows": [],
        "trend_strategy": {},
    }


class OrcaHistoricalContextHelperTests(unittest.TestCase):
    def test_get_market_historical_context_success(self):
        lessons = [_lesson("NVDA", 12.5), _lesson("AVGO", 8.4)]
        with (
            patch.object(historical_context, "retrieve_similar_lessons_for_features", return_value=lessons) as mocked,
            patch.object(historical_context, "_cluster_size", return_value=410),
            patch.dict("os.environ", {}, clear=True),
        ):
            result = historical_context.get_market_historical_context(_features())

        self.assertEqual(result["cluster_id"], "cluster_c05")
        self.assertEqual(result["cluster_size"], 410)
        self.assertEqual(result["win_rate"], 1.0)
        self.assertEqual(result["high_quality_count"], 2)
        mocked.assert_called_once()
        self.assertEqual(mocked.call_args.kwargs["top_k"], 20)
        self.assertEqual(mocked.call_args.kwargs["quality_filter"], "high")

    def test_get_market_historical_context_disabled_via_env(self):
        with (
            patch.object(historical_context, "retrieve_similar_lessons_for_features") as mocked,
            patch.dict("os.environ", {"USE_HISTORICAL_CONTEXT": "0"}),
        ):
            result = historical_context.get_market_historical_context(_features())

        self.assertIsNone(result)
        mocked.assert_not_called()

    def test_get_market_historical_context_no_lessons(self):
        with patch.object(historical_context, "retrieve_similar_lessons_for_features", return_value=[]):
            result = historical_context.get_market_historical_context(_features())

        self.assertIsNone(result)

    def test_get_market_historical_context_graceful_fallback(self):
        with patch.object(
            historical_context,
            "retrieve_similar_lessons_for_features",
            side_effect=RuntimeError("boom"),
        ):
            result = historical_context.get_market_historical_context(_features())

        self.assertIsNone(result)

    def test_build_market_features_uses_direct_features(self):
        features = historical_context.build_market_features({"market_features": _features()})

        self.assertEqual(features["regime"], "위험선호")
        self.assertEqual(features["dominant_sectors"][0], "Technology")
        self.assertEqual(features["vix_level"], 18.5)

    def test_build_market_features_falls_back_to_latest_snapshot(self):
        with patch.object(historical_context, "_latest_snapshot_features", return_value=_features()) as mocked:
            features = historical_context.build_market_features({"market_regime": "위험회피"})

        self.assertEqual(features["vix_level"], 18.5)
        mocked.assert_called_once()


class OrcaPipelineHistoricalIntegrationTests(unittest.TestCase):
    def test_pipeline_adds_historical_context(self):
        with (
            patch.object(pipeline, "agent_hunter", return_value={"market_snapshot": {}}),
            patch.object(pipeline, "agent_analyst", return_value={"analyst": True}),
            patch.object(pipeline, "agent_devil", return_value={"devil": True}),
            patch.object(pipeline, "agent_reporter", return_value=_report()),
            patch.object(historical_context, "build_market_features", return_value=_features()),
            patch.object(historical_context, "get_market_historical_context", return_value=_context()),
        ):
            _hunter, _analyst, _devil, report = pipeline.run_agent_pipeline(
                today="2026-04-27",
                mode="MORNING",
                market_data={},
                memory=[],
                lessons_prompt="",
                baseline_context="",
                accuracy={},
            )

        self.assertEqual(report["historical_context"]["cluster_id"], "cluster_c05")

    def test_pipeline_continues_when_retrieve_fails(self):
        with (
            patch.object(pipeline, "agent_hunter", return_value={}),
            patch.object(pipeline, "agent_analyst", return_value={}),
            patch.object(pipeline, "agent_devil", return_value={}),
            patch.object(pipeline, "agent_reporter", return_value=_report()),
            patch.object(historical_context, "build_market_features", return_value=_features()),
            patch.object(historical_context, "get_market_historical_context", side_effect=RuntimeError("boom")),
        ):
            _hunter, _analyst, _devil, report = pipeline.run_agent_pipeline(
                today="2026-04-27",
                mode="MORNING",
                market_data={},
                memory=[],
                lessons_prompt="",
                baseline_context="",
                accuracy={},
            )

        self.assertNotIn("historical_context", report)

    def test_pipeline_without_historical_context_leaves_report_unchanged(self):
        with (
            patch.object(pipeline, "agent_hunter", return_value={}),
            patch.object(pipeline, "agent_analyst", return_value={}),
            patch.object(pipeline, "agent_devil", return_value={}),
            patch.object(pipeline, "agent_reporter", return_value=_report()),
            patch.object(historical_context, "build_market_features", return_value=_features()),
            patch.object(historical_context, "get_market_historical_context", return_value=None),
        ):
            _hunter, _analyst, _devil, report = pipeline.run_agent_pipeline(
                today="2026-04-27",
                mode="MORNING",
                market_data={},
                memory=[],
                lessons_prompt="",
                baseline_context="",
                accuracy={},
            )

        self.assertNotIn("historical_context", report)


class OrcaHistoricalRenderingTests(unittest.TestCase):
    def test_render_report_includes_historical_section(self):
        rendered = present._render_historical_section(_context())

        self.assertIn("medium_vix_neutral_riskon_growth", rendered)
        self.assertIn("Win rate: 100%", rendered)
        self.assertIn("NVDA", rendered)

    def test_print_report_includes_historical_panel(self):
        report = _report()
        report["historical_context"] = _context()
        printed = []

        with (
            patch.object(present.console, "print", side_effect=lambda obj=None, *a, **k: printed.append(obj)),
            patch.object(present.console, "rule", return_value=None),
        ):
            present.print_report(report, 1)

        panels = [obj for obj in printed if isinstance(obj, Panel)]
        self.assertTrue(any("Historical Market Context" in str(panel.title) for panel in panels))

    def test_telegram_alert_includes_historical_context(self):
        report = _report()
        report["historical_context"] = _context()
        lines = notify._build_historical_context_lines(report)

        joined = "\n".join(lines)
        self.assertIn("Historical Context", joined)
        self.assertIn("Win rate: 100%", joined)
        self.assertIn("NVDA", joined)

    def test_send_report_includes_historical_context(self):
        report = _report()
        report["historical_context"] = _context()
        captured = []

        with patch.object(notify, "send_message", side_effect=lambda text, reply_markup=None: captured.append(text) or True):
            self.assertTrue(notify.send_report(report, 1))

        self.assertEqual(len(captured), 1)
        self.assertIn("Historical Context", captured[0])
        self.assertIn("medium_vix_neutral_riskon_growth", captured[0])

    def test_dashboard_historical_block_html(self):
        html = dashboard._render_historical_context_html(_context())

        self.assertIn("Historical Market Context", html)
        self.assertIn("medium_vix_neutral_riskon_growth", html)
        self.assertIn("NVDA", html)

    def test_dashboard_includes_historical_html(self):
        tmpdir = Path(tempfile.mkdtemp())
        try:
            memory_file = tmpdir / "memory.json"
            output_file = tmpdir / "dashboard.html"
            report = _report()
            report["historical_context"] = _context()
            memory_file.write_text(json.dumps([report], ensure_ascii=False), encoding="utf-8")

            patches = [
                patch.object(dashboard, "MEMORY_FILE", memory_file),
                patch.object(dashboard, "OUTPUT_FILE", output_file),
                patch.object(dashboard, "SENTIMENT_FILE", tmpdir / "sentiment.json"),
                patch.object(dashboard, "ACCURACY_FILE", tmpdir / "accuracy.json"),
                patch.object(dashboard, "ROTATION_FILE", tmpdir / "rotation.json"),
                patch.object(dashboard, "COST_FILE", tmpdir / "cost.json"),
                patch.object(dashboard, "PATTERN_DB_FILE", tmpdir / "patterns.json"),
                patch.object(dashboard, "DATA_FILE", tmpdir / "market.json"),
                patch.object(dashboard, "PORTFOLIO_FILE", tmpdir / "portfolio.json"),
                patch.object(dashboard, "HUNT_LOG_FILE", tmpdir / "hunt_log.json"),
                patch.object(dashboard, "JACKAL_WEIGHTS_FILE", tmpdir / "weights.json"),
            ]
            for item in patches:
                item.start()
            try:
                html = dashboard.build_dashboard()
            finally:
                for item in reversed(patches):
                    item.stop()

            self.assertIn("Historical Market Context", html)
            self.assertIn("medium_vix_neutral_riskon_growth", output_file.read_text(encoding="utf-8"))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
