from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _install_stub_modules() -> None:
    anthropic = types.ModuleType("anthropic")

    class DummyMessages:
        def create(self, *args, **kwargs):
            block = types.SimpleNamespace(text="{}")
            return types.SimpleNamespace(content=[block])

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

    httpx.post = lambda *args, **kwargs: DummyHttpxResponse()
    httpx.get = lambda *args, **kwargs: DummyHttpxResponse()

    yfinance = types.ModuleType("yfinance")
    yfinance.Ticker = lambda ticker: types.SimpleNamespace(history=lambda *args, **kwargs: {})
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


def _hunter_item() -> dict:
    return {
        "ticker": "SOXL",
        "name": "테스트종목",
        "currency": "$",
        "hunt_reason": (
            "반도체/AI 로테이션 수급과 과매도 반등 후보가 동시에 보이는 구간으로 "
            "최근 낙폭 대비 회복 시도가 빠르게 붙을 수 있는 구조"
        ),
        "tech": {
            "price": 101.25,
            "rsi": 29,
            "bb_pos": 14.0,
            "vol_ratio": 1.4,
            "change_1d": 1.8,
            "change_5d": -3.2,
        },
        "analyst": {
            "analyst_score": 76,
            "bull_case": "거래량 회복과 과매도 반등 시도가 함께 들어오고 있습니다.",
            "signals_fired": ["sector_rebound", "bb_touch", "rsi_oversold"],
            "swing_type": "섹터로테이션",
            "day1_score": 62,
            "swing_score": 79,
            "entry_zone": "$100-$102",
            "target_5d": "$108",
            "stop_loss": "$97",
            "expected_days": 4,
        },
        "devil": {
            "devil_status": "no_material_objection",
            "verdict": "동의",
            "main_risk": "",
        },
        "final": {
            "final_score": 78,
            "label": "매수검토",
            "mode": "일반",
            "day1_score": 62,
            "swing_score": 79,
            "is_entry": True,
        },
        "signal_family": "rotation",
        "raw_signal_family": "섹터로테이션",
    }


def _hunter_aria() -> dict:
    return {
        "regime": "risk-on",
        "key_inflows": [
            "반도체/AI 테마로 이어지는 대형 성장주 수급 유입",
            "전력/인프라 관련 보조 수급",
        ],
        "key_outflows": ["장기채와 방어주 선호"],
    }


def _scanner_info() -> dict:
    return {
        "name": "테스트스캔",
        "market": "US",
        "currency": "$",
        "avg_cost": None,
        "portfolio": True,
        "reason": "테스트 reason",
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


def _scanner_analyst() -> dict:
    return {
        "analyst_score": 78,
        "confidence": "보통",
        "bull_case": "눌림 이후 거래량 회복이 붙는 모습입니다.",
        "signals_fired": ["bb_touch", "rsi_oversold", "sector_rebound"],
    }


def _scanner_quality() -> dict:
    return {
        "quality_score": 73,
        "quality_label": "양호",
        "reasons": [
            "BB+RSI조합(97%+88%)+16",
            "sector_rebound(93%)+20",
            "전환중/혼조레짐-15",
        ],
        "skip_threshold": 55,
        "signal_family": "crash_rebound",
    }


def _scanner_devil() -> dict:
    return {
        "devil_score": 25,
        "verdict": "동의",
        "objections": [],
        "thesis_killer_hit": False,
        "killer_detail": "",
        "devil_status": "no_material_objection",
        "devil_called": True,
        "devil_parse_ok": True,
        "devil_render_mode": "label_only",
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
        "signals_fired": ["bb_touch", "rsi_oversold", "sector_rebound"],
        "entry_price": None,
        "stop_loss": None,
    }


def _scanner_aria() -> dict:
    return {
        "regime": "risk-on",
        "trend": "상승추세",
        "sentiment_score": 62,
        "key_inflows": [
            "반도체/AI 테마로 이어지는 대형 성장주 수급 유입",
            "전력 인프라 테마 동반 강세",
        ],
        "key_outflows": ["장기채와 방어주 선호"],
    }


def _scanner_macro() -> dict:
    return {"fred": {"vix": 19.0, "hy_spread": 3.2, "yield_curve": -0.1}}


class ExplanationHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.explanation = importlib.import_module("jackal.explanation")

    def test_signal_humanize_rsi_oversold(self):
        self.assertEqual(self.explanation.humanize_signal("rsi_oversold"), "RSI 과매도")

    def test_signal_humanize_bb_touch(self):
        self.assertEqual(self.explanation.humanize_signal("bb_touch"), "BB 하단 접근")

    def test_signal_humanize_volume_climax(self):
        self.assertEqual(self.explanation.humanize_signal("volume_climax"), "거래량 급증")

    def test_signal_humanize_momentum_dip(self):
        self.assertEqual(self.explanation.humanize_signal("momentum_dip"), "단기 낙폭")

    def test_signal_humanize_sector_rebound(self):
        self.assertEqual(self.explanation.humanize_signal("sector_rebound"), "섹터 반등")

    def test_signal_humanize_rsi_divergence(self):
        self.assertEqual(self.explanation.humanize_signal("rsi_divergence"), "RSI 다이버전스")

    def test_signal_humanize_52w_low_zone(self):
        self.assertEqual(self.explanation.humanize_signal("52w_low_zone"), "52주 저점권")

    def test_signal_humanize_vol_accumulation(self):
        self.assertEqual(self.explanation.humanize_signal("vol_accumulation"), "매집 거래량")

    def test_signal_humanize_ma_support(self):
        self.assertEqual(self.explanation.humanize_signal("ma_support"), "MA 지지")

    def test_family_narrative_rotation(self):
        line = self.explanation.build_family_narrative_line("rotation")
        self.assertIn("섹터로테이션", line)
        self.assertIn("유입 섹터", line)

    def test_family_narrative_panic_rebound(self):
        line = self.explanation.build_family_narrative_line("panic_rebound")
        self.assertIn("패닉반등", line)
        self.assertIn("스냅백", line)

    def test_family_narrative_momentum_pullback(self):
        line = self.explanation.build_family_narrative_line("momentum_pullback")
        self.assertIn("모멘텀눌림목", line)
        self.assertIn("재진입", line)

    def test_family_narrative_ma_reclaim(self):
        line = self.explanation.build_family_narrative_line("ma_reclaim")
        self.assertIn("MA지지반등", line)
        self.assertIn("이동평균", line)

    def test_family_narrative_divergence(self):
        line = self.explanation.build_family_narrative_line("divergence")
        self.assertIn("강세다이버전스", line)
        self.assertIn("모멘텀", line)

    def test_family_narrative_oversold_rebound(self):
        line = self.explanation.build_family_narrative_line("oversold_rebound")
        self.assertIn("기술적과매도", line)
        self.assertIn("과매도", line)

    def test_family_narrative_general_rebound(self):
        line = self.explanation.build_family_narrative_line("general_rebound")
        self.assertIn("일반반등", line)
        self.assertIn("복수", line)

    def test_hunter_swing_suitability_prefers_swing(self):
        text = self.explanation.describe_hunter_swing_suitability(50, 70)
        self.assertIn("3~7일 회복형", text)

    def test_hunter_swing_suitability_prefers_day1(self):
        text = self.explanation.describe_hunter_swing_suitability(72, 50)
        self.assertIn("당일 반등형", text)

    def test_hunter_swing_suitability_balanced(self):
        text = self.explanation.describe_hunter_swing_suitability(62, 68)
        self.assertIn("혼합형", text)

    def test_scanner_swing_suitability_fast_snapback(self):
        text = self.explanation.describe_scanner_swing_suitability({"peak_day": "D2", "mae_avg": "-2.1%"})
        self.assertIn("빠른 스냅백형", text)

    def test_scanner_swing_suitability_early_recovery(self):
        text = self.explanation.describe_scanner_swing_suitability({"peak_day": "D3", "mae_avg": "-2.1%"})
        self.assertIn("초기 눌림 회복형", text)

    def test_scanner_swing_suitability_mid_recovery(self):
        text = self.explanation.describe_scanner_swing_suitability({"peak_day": "D4~5", "mae_avg": "-3.8%"})
        self.assertIn("3~5일 회복형", text)

    def test_devil_summary_ok_with_objection(self):
        summary = self.explanation.build_devil_summary(
            {"devil_status": "ok_with_objection", "verdict": "부분동의", "objections": ["거래량 확인 필요"]}
        )
        self.assertEqual(summary, "부분동의: 거래량 확인 필요")

    def test_devil_summary_no_material_objection(self):
        summary = self.explanation.build_devil_summary({"devil_status": "no_material_objection"})
        self.assertEqual(summary, "반박 없음")

    def test_devil_summary_api_error(self):
        summary = self.explanation.build_devil_summary({"devil_status": "api_error"})
        self.assertEqual(summary, "응답 실패")

    def test_devil_summary_parse_failed(self):
        summary = self.explanation.build_devil_summary({"devil_status": "parse_failed"})
        self.assertEqual(summary, "응답 파싱 실패")

    def test_quality_reason_humanize_omits_negative_and_percent(self):
        summary = self.explanation.summarize_signal_breakdown(
            signals_fired=["bb_touch"],
            quality_reasons=[
                "BB+RSI조합(97%+88%)+16",
                "sector_rebound(93%)+20",
                "전환중/혼조레짐-15",
            ],
        )
        self.assertIn("BB 하단 + RSI 과매도", summary)
        self.assertIn("섹터 반등", summary)
        self.assertNotIn("%", summary)
        self.assertNotIn("혼조", summary)


class ExplanationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.explanation = importlib.import_module("jackal.explanation")
        cls.hunter = _import_target("jackal.hunter")
        cls.scanner = _import_target("jackal.scanner")
        cls.scanner.weights = {}

    def test_hunter_alert_includes_explanation_block_and_truncates_regime(self):
        alert = self.hunter._build_alert(_hunter_item(), _hunter_aria())
        self.assertIn("🧭 추천 이유", alert)
        self.assertIn("섹터로테이션", alert)
        self.assertIn("🔴 Devil: 반박 없음", alert)

        regime_line = next(line for line in alert.splitlines() if line.startswith("시장 맥락:"))
        self.assertLessEqual(len(regime_line), self.explanation.HUNTER_LINE_BUDGETS["regime"])
        self.assertIn("...", regime_line)

    def test_scanner_alert_and_payload_include_reason_detail_components(self):
        quality = _scanner_quality()
        alert = self.scanner._build_alert_message(
            "NVDA",
            _scanner_info(),
            _scanner_tech(),
            _scanner_analyst(),
            _scanner_devil(),
            _scanner_final(),
            quality,
            "oversold_rebound",
            _scanner_aria(),
        )
        self.assertIn("🧭 추천 이유", alert)
        self.assertIn("기술적과매도", alert)
        self.assertIn("🔴 Devil: 반박 없음", alert)

        swing_line = next(line for line in alert.splitlines() if line.startswith("📈 스윙:"))
        self.assertNotIn("(97%)", swing_line)

        regime_line = next(line for line in alert.splitlines() if line.startswith("시장 맥락:"))
        self.assertLessEqual(len(regime_line), self.explanation.SCANNER_LINE_BUDGETS["regime"])
        self.assertIn("...", regime_line)

        entry = self.scanner._build_scan_log_entry(
            now_kst=self.scanner.datetime.now(self.scanner.KST),
            ticker="NVDA",
            market="US",
            info=_scanner_info(),
            tech=_scanner_tech(),
            macro=_scanner_macro(),
            aria=_scanner_aria(),
            quality=quality,
            analyst=_scanner_analyst(),
            devil=_scanner_devil(),
            final=_scanner_final(),
            canonical_signal_family="oversold_rebound",
        )
        self.assertEqual(entry["reason"], "Analyst 우세")
        self.assertIn("reason_detail", entry)
        self.assertIn("reason_components", entry)
        self.assertIn("quality_score", entry)
        self.assertIn("quality_label", entry)
        self.assertIn("quality_reasons", entry)
        self.assertNotIn("🧭 추천 이유", entry["reason_detail"])
        self.assertIn("기술적과매도", entry["reason_detail"])
        self.assertEqual(entry["reason_components"]["devil_summary"], "반박 없음")


if __name__ == "__main__":
    unittest.main()
