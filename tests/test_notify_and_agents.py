import importlib
import json
import sys
import types
import unittest
from datetime import datetime
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


def _import_module(module_name: str):
    _install_stub_modules()
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


class NotifyAccuracyDisplayTests(unittest.TestCase):
    def test_format_accuracy_display_returns_na_when_empty(self):
        notify = _import_module("orca.notify")

        display = notify._format_accuracy_display(0, 0)

        self.assertFalse(display["has_data"])
        self.assertEqual(display["pct_text"], "N/A")
        self.assertEqual(display["count_text"], "검증 데이터 없음")

    def test_weekly_report_shows_na_when_no_verified_samples(self):
        notify = _import_module("orca.notify")
        captured = []

        def fake_load(path, default=None):
            if path == notify.MEMORY_FILE:
                return []
            if path == notify.ACCURACY_FILE:
                return {"history": [], "strong_areas": [], "weak_areas": []}
            if path == notify.SENTIMENT_FILE:
                return {"history": []}
            return default if default is not None else {}

        fake_now = datetime(2026, 4, 21, 9, 0, tzinfo=notify.KST)

        with patch.object(notify, "_load", side_effect=fake_load), patch.object(
            notify,
            "send_message",
            side_effect=lambda text, reply_markup=None: captured.append(text) or True,
        ), patch.object(notify, "_now", return_value=fake_now):
            notify.send_weekly_report()

        self.assertEqual(len(captured), 1)
        self.assertIn("정확도: <b>N/A</b>", captured[0])
        self.assertIn("검증 데이터 없음", captured[0])

    def test_monthly_report_shows_na_when_no_verified_samples(self):
        notify = _import_module("orca.notify")
        captured = []

        def fake_load(path, default=None):
            if path == notify.MEMORY_FILE:
                return []
            if path == notify.ACCURACY_FILE:
                return {"history": [], "total": 0, "correct": 0, "strong_areas": [], "weak_areas": []}
            if path == notify.SENTIMENT_FILE:
                return {"history": []}
            if path == notify.ROTATION_FILE:
                return {"ranking": []}
            return default if default is not None else {}

        fake_now = datetime(2026, 4, 21, 9, 0, tzinfo=notify.KST)

        with patch.object(notify, "_load", side_effect=fake_load), patch.object(
            notify,
            "send_message",
            side_effect=lambda text, reply_markup=None: captured.append(text) or True,
        ), patch.object(notify, "_now", return_value=fake_now):
            notify.send_monthly_report()

        self.assertEqual(len(captured), 1)
        self.assertIn("예측 정확도: <b>N/A</b>", captured[0])
        self.assertIn("누적 정확도: N/A", captured[0])
        self.assertIn("검증 데이터 없음", captured[0])


class VerificationReportTests(unittest.TestCase):
    def test_verification_report_uses_na_when_accuracy_is_empty(self):
        analysis = _import_module("orca.analysis")
        captured = []

        fake_today = datetime(2026, 4, 21, 9, 0, tzinfo=analysis.KST)

        with patch.object(analysis, "send_message", side_effect=lambda text: captured.append(text) or True), patch.object(
            analysis, "_today", return_value=fake_today.strftime("%Y-%m-%d")
        ):
            analysis._send_verification_report(
                results=[],
                accuracy={"correct": 0, "total": 0, "dir_correct": 0, "dir_total": 0},
                today_acc=0,
                dir_acc=0,
            )

        self.assertEqual(len(captured), 1)
        self.assertIn("오늘: <b>N/A</b> (검증 데이터 없음)", captured[0])
        self.assertIn("누적 방향: <b>N/A</b> | 종합: <b>N/A</b> (검증 데이터 없음)", captured[0])


class ReporterFallbackTests(unittest.TestCase):
    def test_reporter_keeps_valid_devil_thesis_killers_when_reporter_omits_them(self):
        agents = _import_module("orca.agents")

        devil_tk = {
            "event": "나스닥",
            "timeframe": "1일",
            "confirms_if": "나스닥 +1% 이상 종가",
            "invalidates_if": "나스닥 -1% 이하 종가",
        }
        reporter_payload = {
            "analysis_date": "2026-04-21",
            "analysis_time": "09:00 KST",
            "mode": "MORNING",
            "mode_label": "아침 풀분석",
            "one_line_summary": "테스트용 요약 문장입니다. 충분히 길게 작성합니다.",
            "market_regime": "혼조",
            "trend_phase": "횡보추세",
            "trend_strategy": {"recommended": "", "caution": "", "difficulty": "보통"},
            "confidence_overall": "낮음",
            "consensus_level": "낮음",
            "top_headlines": [],
            "volatility_index": {"vkospi": "", "vix": "", "fear_greed": "", "level": "", "interpretation": ""},
            "retail_reversal_signal": {"retail_behavior": "", "contrarian_implication": "", "reliability": ""},
            "outflows": [],
            "inflows": [],
            "neutral_waiting": [],
            "hidden_signals": [],
            "korea_focus": {"krw_usd": "", "kospi_flow": "", "sk_hynix": "", "samsung": "", "assessment": ""},
            "counterarguments": [],
            "thesis_killers": [],
            "tail_risks": [],
            "agent_consensus": {"agreed": [], "disputed": []},
            "meta_improvement": {"missed_last_time": "", "accuracy_review": "", "reweighting": "", "orca_version": ""},
            "tomorrow_setup": "",
            "actionable_watch": [],
        }

        with patch.object(agents, "call_api", return_value=json.dumps(reporter_payload, ensure_ascii=False)):
            result = agents.agent_reporter(
                hunter={"market_snapshot": {}},
                analyst={},
                devil={"thesis_killers": [devil_tk]},
                memory=[],
                accuracy={},
                mode="MORNING",
            )

        self.assertEqual(len(result["thesis_killers"]), 1)
        self.assertEqual(result["thesis_killers"][0]["event"], "나스닥")
        self.assertEqual(result["thesis_killers"][0]["quality"], "ok")


if __name__ == "__main__":
    unittest.main()
