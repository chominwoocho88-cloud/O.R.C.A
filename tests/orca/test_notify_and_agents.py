import importlib
import json
import sys
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


def _repo_root() -> Path:
    for path in Path(__file__).resolve().parents:
        if (path / "apps" / "orca").is_dir() and (path / "shared").is_dir():
            return path
    raise RuntimeError("Repository root not found from notify and agents test")


ROOT = _repo_root()
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
    rich_panel = types.ModuleType("rich.panel")
    rich_table = types.ModuleType("rich.table")

    class DummyConsole:
        def print(self, *args, **kwargs):
            return None

    class DummyPanel:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class DummyTable:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def add_column(self, *args, **kwargs):
            return None

        def add_row(self, *args, **kwargs):
            return None

    rich_console.Console = DummyConsole
    rich_panel.Panel = DummyPanel
    rich_table.Table = DummyTable
    rich.console = rich_console
    rich.panel = rich_panel
    rich.table = rich_table
    rich.box = types.SimpleNamespace()

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
        analysis = _import_module("apps.orca.analysis")
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
        agents = _import_module("apps.orca.pipeline.agents")

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


class ReporterEveningKoreaForecastSchemaTests(unittest.TestCase):
    def test_reporter_schema_includes_tomorrow_korea_fields(self):
        agents = _import_module("apps.orca.pipeline.agents")

        for field in (
            "tomorrow_korea_open",
            "tomorrow_korea_levels",
            "us_to_korea_impact",
            "tomorrow_korea_catalysts",
        ):
            self.assertIn(field, agents.REPORTER_SYSTEM)
        self.assertIn('"direction":"갭업/갭다운/보합"', agents.REPORTER_SYSTEM)
        self.assertIn('"kospi_support"', agents.REPORTER_SYSTEM)
        self.assertIn('"directional_trigger"', agents.REPORTER_SYSTEM)

    def test_evening_reporter_prompt_requires_structured_korea_forecast(self):
        agents = _import_module("apps.orca.pipeline.agents")
        captured = {}
        reporter_payload = {
            "analysis_date": "2026-05-21",
            "analysis_time": "20:30 KST",
            "mode": "EVENING",
            "mode_label": "저녁 마감",
            "one_line_summary": "테스트용 저녁 요약 문장입니다. 충분히 길게 작성합니다.",
            "market_regime": "혼조",
            "trend_phase": "횡보추세",
            "trend_strategy": {"recommended": "", "caution": "", "difficulty": "보통"},
            "confidence_overall": "보통",
            "consensus_level": "보통",
            "top_headlines": [],
            "volatility_index": {"vkospi": "", "vix": "", "fear_greed": "", "level": "", "interpretation": ""},
            "retail_reversal_signal": {"retail_behavior": "", "contrarian_implication": "", "reliability": ""},
            "outflows": [],
            "inflows": [],
            "neutral_waiting": [],
            "hidden_signals": [],
            "korea_focus": {"krw_usd": "", "kospi_flow": "", "sk_hynix": "", "samsung": "", "assessment": ""},
            "tomorrow_korea_open": {
                "direction": "갭업",
                "expected_gap_pct": "+0.5~1.0%",
                "kospi_open_range": "7,250~7,320",
                "sk_hynix": "나스닥 대비 1.36x beta 반영",
                "samsung": "대형주 동조",
                "confidence": "보통",
            },
            "tomorrow_korea_levels": {
                "kospi_support": "7,180",
                "kospi_resistance": "7,360",
                "watch_level": "7,250",
                "breakdown_risk": "7,180 이탈",
            },
            "us_to_korea_impact": {
                "us_signal": "나스닥 강세",
                "expected_korea_impact": "반도체 갭업 압력",
                "sk_hynix_beta_note": "1.36x beta",
                "samsung_note": "메모리 동조",
            },
            "tomorrow_korea_catalysts": [
                {
                    "event": "엔비디아 시간외",
                    "time_kst": "06:00 KST",
                    "why_it_matters": "한국 반도체 개장 영향",
                    "directional_trigger": "+5% 이상",
                }
            ],
            "counterarguments": [],
            "thesis_killers": [],
            "tail_risks": [],
            "agent_consensus": {"agreed": [], "disputed": []},
            "meta_improvement": {"missed_last_time": "", "accuracy_review": "", "reweighting": "", "orca_version": ""},
            "tomorrow_setup": "",
            "actionable_watch": [],
        }

        def fake_call_api(system, prompt, **kwargs):
            captured["system"] = system
            captured["prompt"] = prompt
            captured["kwargs"] = kwargs
            return json.dumps(reporter_payload, ensure_ascii=False)

        with patch.object(agents, "call_api", side_effect=fake_call_api):
            result = agents.agent_reporter(
                hunter={"market_snapshot": {}},
                analyst={},
                devil={},
                memory=[],
                accuracy={},
                mode="EVENING",
            )

        self.assertEqual(result["tomorrow_korea_open"]["direction"], "갭업")
        self.assertIn("tomorrow_korea_open", captured["system"])
        self.assertIn("EVENING REQUIRED: 내일 아침 한국 시장 예측 특화", captured["prompt"])
        self.assertIn("반드시 아래 4개 필드를 모두 JSON schema대로 채워라", captured["prompt"])
        self.assertIn("1.36x beta", captured["prompt"])
        self.assertIn("tomorrow_setup은 기존 호환 필드", captured["prompt"])


if __name__ == "__main__":
    unittest.main()
