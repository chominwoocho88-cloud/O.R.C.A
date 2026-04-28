from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _install_stub_modules() -> None:
    anthropic = types.ModuleType("anthropic")

    class DummyBlock:
        def __init__(self, text: str):
            self.text = text

    class DummyResponse:
        def __init__(self, text: str = "{}"):
            self.content = [DummyBlock(text)]

    class DummyMessages:
        def create(self, *args, **kwargs):
            return DummyResponse("{}")

    class DummyAnthropic:
        def __init__(self, api_key=None, **kwargs):
            self.api_key = api_key
            self.kwargs = kwargs
            self.messages = DummyMessages()

    anthropic.Anthropic = DummyAnthropic

    httpx = types.ModuleType("httpx")

    class DummyHttpxResponse:
        def json(self):
            return {"ok": True}

        def raise_for_status(self):
            return None

    def _httpx_post(*args, **kwargs):
        return DummyHttpxResponse()

    def _httpx_get(*args, **kwargs):
        return DummyHttpxResponse()

    httpx.post = _httpx_post
    httpx.get = _httpx_get

    yfinance = types.ModuleType("yfinance")

    class DummyTicker:
        def __init__(self, ticker: str):
            self.ticker = ticker

        def history(self, *args, **kwargs):
            return {}

    yfinance.Ticker = DummyTicker
    yfinance.download = lambda *args, **kwargs: {}

    pandas = types.ModuleType("pandas")
    pandas.DataFrame = object
    pandas.Series = object
    pandas.isna = lambda value: False

    sys.modules["anthropic"] = anthropic
    sys.modules["httpx"] = httpx
    sys.modules["yfinance"] = yfinance
    sys.modules["pandas"] = pandas


def _import_target(module_name: str):
    _install_stub_modules()
    if module_name == "jackal.scanner":
        sys.modules.pop("jackal.market_data", None)
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def _make_anthropic_class(*, text: str = "{}", exception: Exception | None = None):
    class DummyBlock:
        def __init__(self, payload: str):
            self.text = payload

    class DummyResponse:
        def __init__(self, payload: str):
            self.content = [DummyBlock(payload)]

    class DummyMessages:
        def create(self, *args, **kwargs):
            if exception is not None:
                raise exception
            return DummyResponse(text)

    class DummyAnthropic:
        def __init__(self, api_key=None, **kwargs):
            self.api_key = api_key
            self.kwargs = kwargs
            self.messages = DummyMessages()

    return DummyAnthropic


def _hunter_tech() -> dict:
    return {
        "price": 101.25,
        "rsi": 29,
        "bb_pos": 14.0,
        "vol_ratio": 1.4,
        "change_1d": 1.8,
        "change_5d": -3.2,
    }


def _hunter_analyst() -> dict:
    return {
        "analyst_score": 76,
        "bull_case": "거래량 회복과 과매도 반등 시도",
        "signals_fired": ["bb_touch", "rsi_oversold"],
        "swing_setup": "반등가능",
        "swing_type": "기술적과매도",
        "day1_score": 71,
        "swing_score": 74,
        "entry_zone": "$100-$102",
        "target_5d": "$108",
        "stop_loss": "$97",
        "expected_days": 4,
    }


def _hunter_aria() -> dict:
    return {
        "regime": "risk-on",
        "thesis_killers": [],
        "key_outflows": [],
        "key_inflows": ["반도체/AI"],
        "jackal_news": {},
        "all_headlines": [],
    }


def _scanner_info() -> dict:
    return {
        "name": "테스트종목",
        "market": "US",
        "currency": "$",
        "avg_cost": None,
        "portfolio": True,
        "reason": "테스트 이유",
    }


def _scanner_tech() -> dict:
    return {
        "price": 210.5,
        "rsi": 34,
        "bb_pos": 28,
        "vol_ratio": 1.6,
        "change_1d": 2.1,
        "change_5d": -1.7,
    }


def _scanner_macro() -> dict:
    return {"fred": {"vix": 19.0, "hy_spread": 3.2, "yield_curve": -0.1}}


def _scanner_aria() -> dict:
    return {
        "regime": "risk-on",
        "sentiment_score": 62,
        "trend": "상승추세",
        "key_outflows": [],
        "key_inflows": ["반도체/AI"],
        "thesis_killers": [],
    }


def _scanner_analyst() -> dict:
    return {
        "analyst_score": 78,
        "confidence": "보통",
        "bull_case": "눌림 이후 거래량 회복",
        "signals_fired": ["bb_touch"],
    }


def _scanner_quality() -> dict:
    return {
        "quality_score": 73,
        "quality_label": "양호",
        "reasons": ["과매도 신호 조합"],
        "skip_threshold": 55,
        "signal_family": "crash_rebound",
        "rebound_bonus": 3,
        "vix_used": 18,
    }


def _scanner_final() -> dict:
    return {
        "final_score": 74,
        "signal_type": "매수검토",
        "is_entry": True,
        "reason": "Analyst 우세",
        "probability_adjustment": 0,
        "probability_samples": 0,
        "probability_win_rate": None,
        "signals_fired": ["bb_touch"],
        "entry_price": None,
        "stop_loss": None,
    }


class HunterDevilStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hunter = _import_target("jackal.hunter")

    def test_hunter_status_ok_with_objection(self):
        response = (
            '{"devil_score": 61, "verdict": "부분동의", '
            '"main_risk": "거래량이 아직 약하고 재차 눌릴 수 있음", '
            '"thesis_killer_hit": false, "is_dead_cat": false, '
            '"structural_decline": false, "volume_concern": "정상"}'
        )
        with patch.object(self.hunter, "Anthropic", _make_anthropic_class(text=response)):
            devil = self.hunter._devil_swing("TSM", _hunter_tech(), _hunter_analyst(), _hunter_aria(), "$")
        self.assertEqual(devil["devil_status"], "ok_with_objection")
        self.assertTrue(devil["devil_called"])
        self.assertTrue(devil["devil_parse_ok"])
        self.assertEqual(devil["devil_render_mode"], "full")
        self.assertIsNone(devil["devil_raw_excerpt"])

    def test_hunter_status_no_material_objection(self):
        response = (
            '{"devil_score": 38, "verdict": "동의", "main_risk": "", '
            '"thesis_killer_hit": false, "is_dead_cat": false, '
            '"structural_decline": false, "volume_concern": "정상"}'
        )
        with patch.object(self.hunter, "Anthropic", _make_anthropic_class(text=response)):
            devil = self.hunter._devil_swing("TSM", _hunter_tech(), _hunter_analyst(), _hunter_aria(), "$")
        self.assertEqual(devil["devil_status"], "no_material_objection")
        self.assertTrue(devil["devil_parse_ok"])
        self.assertEqual(devil["devil_render_mode"], "label_only")
        self.assertEqual(devil["main_risk"], "")

    def test_hunter_status_parse_failed_on_non_json_response(self):
        with patch.object(self.hunter, "Anthropic", _make_anthropic_class(text="not-json-response")):
            devil = self.hunter._devil_swing("TSM", _hunter_tech(), _hunter_analyst(), _hunter_aria(), "$")
        self.assertEqual(devil["devil_status"], "parse_failed")
        self.assertFalse(devil["devil_parse_ok"])
        self.assertEqual(devil["devil_render_mode"], "label_only")
        self.assertEqual(devil["devil_score"], self.hunter._HUNTER_ENTRY["default_devil_score"])
        self.assertEqual(devil["verdict"], "부분동의")
        self.assertEqual(devil["devil_raw_excerpt"], "not-json-response")

    def test_hunter_status_api_error_uses_fallback_values(self):
        with patch.object(
            self.hunter,
            "Anthropic",
            _make_anthropic_class(exception=RuntimeError("boom")),
        ):
            devil = self.hunter._devil_swing("TSM", _hunter_tech(), _hunter_analyst(), _hunter_aria(), "$")
        self.assertEqual(devil["devil_status"], "api_error")
        self.assertFalse(devil["devil_parse_ok"])
        self.assertEqual(devil["devil_render_mode"], "label_only")
        self.assertEqual(devil["devil_score"], self.hunter._HUNTER_ENTRY["default_devil_score"])
        self.assertEqual(devil["verdict"], "부분동의")

    def test_hunter_alert_line_ok_with_objection(self):
        line = self.hunter._build_hunter_devil_line(
            {"devil_status": "ok_with_objection", "verdict": "반대", "main_risk": "추세 재확인 전까지 위험"}
        )
        self.assertEqual(line, "🔴 Devil ⚠️ 반대: 추세 재확인 전까지 위험")

    def test_hunter_alert_line_no_material_objection(self):
        line = self.hunter._build_hunter_devil_line({"devil_status": "no_material_objection"})
        self.assertEqual(line, "🔴 Devil: 반박 없음")

    def test_hunter_alert_line_api_error(self):
        line = self.hunter._build_hunter_devil_line({"devil_status": "api_error"})
        self.assertEqual(line, "🔴 Devil: 응답 실패")

    def test_hunter_alert_line_parse_failed(self):
        line = self.hunter._build_hunter_devil_line({"devil_status": "parse_failed"})
        self.assertEqual(line, "🔴 Devil: 응답 파싱 실패")

    def test_hunter_raw_excerpt_trims_to_200_chars(self):
        excerpt = self.hunter._trim_devil_raw_excerpt("x" * 260)
        self.assertEqual(len(excerpt), 200)
        self.assertEqual(excerpt, "x" * 200)

    def test_hunter_log_entry_backfills_missing_status_fields(self):
        item = {
            "ticker": "TSM",
            "name": "테스트종목",
            "tech": _hunter_tech(),
            "analyst": _hunter_analyst(),
            "devil": {
                "devil_score": 30,
                "verdict": "부분동의",
                "main_risk": "",
                "thesis_killer_hit": False,
            },
            "final": {"final_score": 72, "is_entry": True, "mode": "일반"},
            "signal_family": "technical_oversold",
            "raw_signal_family": "기술적과매도",
            "s1_score": 12,
            "s2_score": 8,
        }
        entry = self.hunter._build_hunt_log_entry(item, _hunter_aria())
        self.assertIn("devil_status", entry)
        self.assertIn("devil_render_mode", entry)
        self.assertIn("devil_called", entry)
        self.assertIn("devil_parse_ok", entry)
        self.assertEqual(entry["devil_status"], "no_material_objection")
        self.assertEqual(entry["devil_render_mode"], "label_only")
        self.assertTrue(entry["devil_called"])
        self.assertFalse(entry["devil_parse_ok"])


class ScannerDevilStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scanner = _import_target("jackal.scanner")
        cls.scanner.weights = {}

    def test_scanner_status_ok_with_objection(self):
        response = (
            '{"devil_score": 64, "verdict": "부분동의", '
            '"objections": ["거래량이 아직 부족함"], '
            '"thesis_killer_hit": false, "killer_detail": "", "bear_case": ""}'
        )
        with patch.object(self.scanner, "Anthropic", _make_anthropic_class(text=response)):
            devil = self.scanner.agent_devil(
                "NVDA",
                _scanner_info(),
                _scanner_tech(),
                _scanner_macro(),
                _scanner_aria(),
                _scanner_analyst(),
            )
        self.assertEqual(devil["devil_status"], "ok_with_objection")
        self.assertTrue(devil["devil_called"])
        self.assertTrue(devil["devil_parse_ok"])
        self.assertEqual(devil["devil_render_mode"], "full")
        self.assertEqual(devil["devil_raw_excerpt"], None)

    def test_scanner_status_no_material_objection(self):
        response = (
            '{"devil_score": 25, "verdict": "동의", '
            '"objections": [], "thesis_killer_hit": false, '
            '"killer_detail": "", "bear_case": ""}'
        )
        with patch.object(self.scanner, "Anthropic", _make_anthropic_class(text=response)):
            devil = self.scanner.agent_devil(
                "NVDA",
                _scanner_info(),
                _scanner_tech(),
                _scanner_macro(),
                _scanner_aria(),
                _scanner_analyst(),
            )
        self.assertEqual(devil["devil_status"], "no_material_objection")
        self.assertTrue(devil["devil_parse_ok"])
        self.assertEqual(devil["devil_render_mode"], "label_only")

    def test_scanner_status_parse_failed_when_regex_missing(self):
        with patch.object(self.scanner, "Anthropic", _make_anthropic_class(text="plain text")):
            devil = self.scanner.agent_devil(
                "NVDA",
                _scanner_info(),
                _scanner_tech(),
                _scanner_macro(),
                _scanner_aria(),
                _scanner_analyst(),
            )
        self.assertEqual(devil["devil_status"], "parse_failed")
        self.assertFalse(devil["devil_parse_ok"])
        self.assertEqual(devil["devil_render_mode"], "label_only")
        self.assertEqual(devil["devil_raw_excerpt"], "plain text")

    def test_scanner_status_parse_failed_when_json_invalid(self):
        with patch.object(self.scanner, "Anthropic", _make_anthropic_class(text='{"devil_score": 40,}')):
            devil = self.scanner.agent_devil(
                "NVDA",
                _scanner_info(),
                _scanner_tech(),
                _scanner_macro(),
                _scanner_aria(),
                _scanner_analyst(),
            )
        self.assertEqual(devil["devil_status"], "parse_failed")
        self.assertFalse(devil["devil_parse_ok"])
        self.assertEqual(devil["devil_score"], 30)
        self.assertEqual(devil["verdict"], "부분동의")

    def test_scanner_status_api_error_uses_fallback_values(self):
        with patch.object(
            self.scanner,
            "Anthropic",
            _make_anthropic_class(exception=RuntimeError("network down")),
        ):
            devil = self.scanner.agent_devil(
                "NVDA",
                _scanner_info(),
                _scanner_tech(),
                _scanner_macro(),
                _scanner_aria(),
                _scanner_analyst(),
            )
        self.assertEqual(devil["devil_status"], "api_error")
        self.assertFalse(devil["devil_parse_ok"])
        self.assertEqual(devil["devil_render_mode"], "label_only")
        self.assertEqual(devil["devil_score"], 30)
        self.assertEqual(devil["verdict"], "부분동의")

    def test_scanner_alert_line_ok_with_objection(self):
        line = self.scanner._build_scanner_devil_line(
            {
                "devil_status": "ok_with_objection",
                "verdict": "부분동의",
                "objections": ["재료 확인 전까지 변동성 위험"],
            }
        )
        self.assertEqual(line, "🔴 Devil ⚠️ 부분동의: 재료 확인 전까지 변동성 위험")

    def test_scanner_alert_line_no_material_objection(self):
        line = self.scanner._build_scanner_devil_line({"devil_status": "no_material_objection"})
        self.assertEqual(line, "🔴 Devil: 반박 없음")

    def test_scanner_alert_line_api_error(self):
        line = self.scanner._build_scanner_devil_line({"devil_status": "api_error"})
        self.assertEqual(line, "🔴 Devil: 응답 실패")

    def test_scanner_alert_line_parse_failed(self):
        line = self.scanner._build_scanner_devil_line({"devil_status": "parse_failed"})
        self.assertEqual(line, "🔴 Devil: 응답 파싱 실패")

    def test_scanner_raw_excerpt_trims_to_200_chars(self):
        excerpt = self.scanner._trim_devil_raw_excerpt("y" * 275)
        self.assertEqual(len(excerpt), 200)
        self.assertEqual(excerpt, "y" * 200)

    def test_scanner_shadow_log_entry_marks_skipped_quality_gate_hidden(self):
        entry = self.scanner._build_shadow_log_entry(
            now_kst=self.scanner.datetime.now(self.scanner.KST),
            ticker="NVDA",
            info=_scanner_info(),
            tech=_scanner_tech(),
            macro=_scanner_macro(),
            aria=_scanner_aria(),
            signals_fired_pre=["bb_touch"],
            quality=_scanner_quality(),
        )
        self.assertEqual(entry["devil_status"], "skipped_quality_gate")
        self.assertFalse(entry["devil_called"])
        self.assertFalse(entry["devil_parse_ok"])
        self.assertEqual(entry["devil_render_mode"], "hidden")
        self.assertIsNone(entry["devil_raw_excerpt"])

    def test_scanner_scan_log_entry_backfills_missing_status_fields(self):
        if hasattr(self.scanner, "weights"):
            delattr(self.scanner, "weights")
        entry = self.scanner._build_scan_log_entry(
            now_kst=self.scanner.datetime.now(self.scanner.KST),
            ticker="NVDA",
            market="US",
            info=_scanner_info(),
            tech=_scanner_tech(),
            macro=_scanner_macro(),
            aria=_scanner_aria(),
            quality=_scanner_quality(),
            analyst=_scanner_analyst(),
            devil={
                "devil_score": 30,
                "verdict": "부분동의",
                "objections": [],
                "thesis_killer_hit": False,
            },
            final=_scanner_final(),
            canonical_signal_family="crash_rebound",
        )
        self.assertIn("devil_status", entry)
        self.assertIn("devil_render_mode", entry)
        self.assertIn("devil_called", entry)
        self.assertIn("devil_parse_ok", entry)
        self.assertEqual(entry["devil_status"], "no_material_objection")
        self.assertEqual(entry["devil_render_mode"], "label_only")
        self.assertTrue(entry["devil_called"])
        self.assertFalse(entry["devil_parse_ok"])

    def test_scanner_scan_log_entry_loads_weights_without_global_variable(self):
        if hasattr(self.scanner, "weights"):
            delattr(self.scanner, "weights")
        with patch.object(self.scanner, "_load_weights", return_value={}) as loader:
            entry = self.scanner._build_scan_log_entry(
                now_kst=self.scanner.datetime.now(self.scanner.KST),
                ticker="NVDA",
                market="US",
                info=_scanner_info(),
                tech=_scanner_tech(),
                macro=_scanner_macro(),
                aria=_scanner_aria(),
                quality=_scanner_quality(),
                analyst=_scanner_analyst(),
                devil={
                    "devil_score": 30,
                    "verdict": "neutral",
                    "objections": [],
                    "thesis_killer_hit": False,
                },
                final=_scanner_final(),
                canonical_signal_family="crash_rebound",
            )

        loader.assert_called_once()
        self.assertIn("reason_detail", entry)

    def test_build_alert_message_with_failed_analyst(self):
        if hasattr(self.scanner, "weights"):
            delattr(self.scanner, "weights")
        analyst = {
            "analyst_score": 0,
            "confidence": "parse_failed",
            "bull_case": "",
            "signals_fired": [],
        }
        with patch.object(self.scanner, "_load_weights", return_value={}) as loader:
            alert = self.scanner._build_alert_message(
                "NVDA",
                _scanner_info(),
                _scanner_tech(),
                analyst,
                {
                    "devil_score": 30,
                    "devil_status": "parse_failed",
                    "verdict": "neutral",
                    "objections": [],
                    "thesis_killer_hit": False,
                },
                _scanner_final(),
                _scanner_quality(),
                "crash_rebound",
                _scanner_aria(),
            )

        loader.assert_called_once()
        self.assertIn("NVDA", alert)
        self.assertIn("parse_failed", alert)

    def test_scanner_no_nameerror_on_fallback(self):
        if hasattr(self.scanner, "weights"):
            delattr(self.scanner, "weights")
        with patch.object(self.scanner, "_load_weights", return_value={}):
            try:
                self.scanner._build_alert_message(
                    "NVDA",
                    _scanner_info(),
                    _scanner_tech(),
                    _scanner_analyst(),
                    {
                        "devil_score": 30,
                        "devil_status": "parse_failed",
                        "verdict": "neutral",
                        "objections": [],
                        "thesis_killer_hit": False,
                    },
                    _scanner_final(),
                    _scanner_quality(),
                    "crash_rebound",
                    _scanner_aria(),
                )
            except NameError as exc:
                self.fail(f"_build_alert_message raised NameError: {exc}")

    def test_run_scan_exposes_wrapped_for_workflow_probe(self):
        self.assertIs(self.scanner.run_scan.__wrapped__, self.scanner.run_scan)


if __name__ == "__main__":
    unittest.main()
