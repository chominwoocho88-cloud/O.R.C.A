"""Tests for the extracted JACKAL deterministic quality engine.

Deferred bug note:
- `jackal/quality_engine.py:252` still reads `family` inside the micro-gate
  branch before `family = _get_signal_family(signals)` at line 300.
- Repro: call `_calc_signal_quality_core(...)` with a risk-off regime string
  (`"위험회피"`, `"하락추세"`, or `"bearish"`), `vix >= 22`, and without a
  higher-uncertainty gate activating first.
- This refactor intentionally preserves that ordering for behavior parity.
- Fix deferred to a separate bug-fix PR.
"""

from __future__ import annotations

import ast
import importlib
import json
import sys
import tempfile
import types
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


QUALITY_ENGINE_FILE = ROOT / "jackal" / "quality_engine.py"

PRE_RULE_LITERAL_SNAPSHOT = Counter(
    {
        15: 2,
        32: 1,
        -4.0: 1,
        1.8: 1,
        -1.0: 1,
        4.0: 1,
        40: 1,
        -2.0: 1,
        35: 1,
        50: 1,
        0.025: 1,
        1.0: 1,
        2.0: 1,
        0: 1,
    }
)
QUALITY_CORE_LITERAL_SNAPSHOT = Counter(
    {
        0.0: 18,
        5: 14,
        50: 8,
        8: 8,
        15: 7,
        12: 6,
        10: 4,
        6: 3,
        3: 3,
        20: 2,
        35: 2,
        40: 2,
        45: 2,
        46: 2,
        1: 2,
        30: 2,
        4.0: 2,
        2: 2,
        75: 2,
        -5: 2,
        32: 2,
        18: 2,
        16: 1,
        9: 1,
        25: 1,
        3.5: 1,
        47: 1,
        -8: 1,
        100: 1,
        80: 1,
        1.3: 1,
        22: 1,
        0.2: 1,
        -10: 1,
        33: 1,
        65: 1,
        1.1: 1,
        0.1: 1,
        0.5: 1,
        0.8: 1,
        28: 1,
    }
)
FINAL_JUDGMENT_LITERAL_SNAPSHOT = Counter(
    {
        30: 4,
        1.0: 2,
        0.75: 2,
        0: 2,
        40: 2,
        50: 1,
        0.5: 1,
        0.2: 1,
        20: 1,
        100: 1,
        80: 1,
    }
)


def _numeric_literals(path: Path, function_name: str) -> Counter:
    source = path.read_text(encoding="utf-8-sig")
    module = ast.parse(source, filename=str(path))
    for node in module.body:
        if not isinstance(node, ast.FunctionDef) or node.name != function_name:
            continue
        counter: Counter = Counter()
        for child in ast.walk(node):
            if isinstance(child, ast.Constant) and isinstance(child.value, (int, float)):
                if not isinstance(child.value, bool):
                    counter[child.value] += 1
            elif (
                isinstance(child, ast.UnaryOp)
                and isinstance(child.op, ast.USub)
                and isinstance(child.operand, ast.Constant)
                and isinstance(child.operand.value, (int, float))
            ):
                counter[-child.operand.value] += 1
        return counter
    raise AssertionError(f"{function_name} not found in {path}")


def _install_scanner_stubs() -> None:
    anthropic = types.ModuleType("anthropic")

    class DummyAnthropic:
        def __init__(self, api_key=None):
            self.api_key = api_key

    anthropic.Anthropic = DummyAnthropic

    httpx = types.ModuleType("httpx")
    httpx.post = lambda *args, **kwargs: None
    httpx.get = lambda *args, **kwargs: None

    sys.modules["anthropic"] = anthropic
    sys.modules["httpx"] = httpx


def _load_modules():
    _install_scanner_stubs()
    for name in ("jackal.scanner", "jackal.quality_engine"):
        sys.modules.pop(name, None)
    quality_engine = importlib.import_module("jackal.quality_engine")
    scanner = importlib.import_module("jackal.scanner")
    return scanner, quality_engine


class TestPreRuleDetection(unittest.TestCase):
    def test_ma_support_solo_is_filtered_out(self):
        from jackal.quality_engine import detect_pre_rule_signals

        tech = {
            "rsi": 50,
            "bb_pos": 50,
            "vol_ratio": 1.0,
            "change_1d": 0.0,
            "change_5d": 0.0,
            "price": 100.0,
            "ma50": 99.0,
        }
        self.assertEqual(detect_pre_rule_signals(tech), [])

    def test_ma_support_is_kept_with_strong_signal(self):
        from jackal.quality_engine import detect_pre_rule_signals

        tech = {
            "rsi": 28,
            "bb_pos": 10,
            "vol_ratio": 1.0,
            "change_1d": -0.5,
            "change_5d": 0.0,
            "change_3d": 0.0,
            "price": 100.0,
            "ma50": 99.0,
        }
        self.assertEqual(
            detect_pre_rule_signals(tech),
            ["rsi_oversold", "bb_touch", "ma_support"],
        )


class TestSignalFamily(unittest.TestCase):
    def test_crash_rebound_family_has_priority(self):
        from jackal.quality_engine import _get_signal_family

        self.assertEqual(
            _get_signal_family(["bb_touch", "sector_rebound"]),
            "crash_rebound",
        )

    def test_ma_support_weak_family(self):
        from jackal.quality_engine import _get_signal_family

        self.assertEqual(
            _get_signal_family(["ma_support", "momentum_dip"]),
            "ma_support_weak",
        )


class TestFinalJudgment(unittest.TestCase):
    def test_thesis_killer_blocks_entry(self):
        from jackal.quality_engine import _final_judgment

        result = _final_judgment(
            {"analyst_score": 82},
            {"thesis_killer_hit": True, "killer_detail": "liquidity break"},
        )
        self.assertEqual(result["final_score"], 20)
        self.assertFalse(result["is_entry"])
        self.assertEqual(result["signal_type"], "매도주의")

    def test_partial_agreement_uses_existing_weighting(self):
        from jackal.quality_engine import _final_judgment

        result = _final_judgment(
            {
                "analyst_score": 80,
                "bull_case": "rebound setup",
                "entry_price": 100,
                "stop_loss": 92,
            },
            {
                "devil_score": 40,
                "verdict": "부분동의",
                "thesis_killer_hit": False,
                "objections": ["earnings soon"],
            },
        )
        self.assertEqual(result["final_score"], 58.0)
        self.assertFalse(result["is_entry"])
        self.assertEqual(result["signal_type"], "관망")
        self.assertEqual(result["entry_price"], 100)
        self.assertEqual(result["stop_loss"], 92)


class TestQualityCore(unittest.TestCase):
    def test_quality_core_matches_expected_snapshot(self):
        from jackal.quality_engine import _calc_signal_quality_core

        result = _calc_signal_quality_core(
            ["bb_touch", "rsi_oversold"],
            {
                "price": 100.0,
                "ma50": 100.0,
                "rsi": 28,
                "bb_pos": 10,
                "vol_ratio": 2.0,
                "change_1d": -1.5,
                "change_5d": -6.0,
                "vix_level": 18,
            },
            {
                "regime": "중립",
                "thesis_killers": [],
                "note": "",
                "trend": "",
                "fear_greed": "40",
            },
            ticker="AAA",
            weights={"ticker_accuracy": {"AAA": {"accuracy": 40, "total": 10}}},
            pcr_avg=1.15,
            cached_vix=19.0,
            hy_spread=3.0,
        )

        self.assertEqual(result["quality_score"], 83.0)
        self.assertEqual(result["quality_label"], "최강")
        self.assertFalse(result["skip"])
        self.assertEqual(result["skip_threshold"], 45)
        self.assertEqual(result["signal_family"], "general")
        self.assertEqual(result["analyst_adj"], 5)
        self.assertEqual(result["final_adj"], 5)
        self.assertEqual(result["vix_used"], 18.0)
        self.assertFalse(result["vix_extreme"])
        self.assertEqual(result["rebound_bonus"], 5)
        self.assertEqual(result["rebound_raw"], 5)
        self.assertFalse(result["negative_veto"])
        self.assertEqual(result["negative_reasons"], [])


class TestThresholdFreeze(unittest.TestCase):
    def test_numeric_literal_snapshots_match(self):
        from jackal.quality_engine import ALERT_THRESHOLD, STRONG_THRESHOLD

        self.assertEqual(
            _numeric_literals(QUALITY_ENGINE_FILE, "detect_pre_rule_signals"),
            PRE_RULE_LITERAL_SNAPSHOT,
        )
        self.assertEqual(
            _numeric_literals(QUALITY_ENGINE_FILE, "_calc_signal_quality_core"),
            QUALITY_CORE_LITERAL_SNAPSHOT,
        )
        self.assertEqual(
            _numeric_literals(QUALITY_ENGINE_FILE, "_final_judgment"),
            FINAL_JUDGMENT_LITERAL_SNAPSHOT,
        )
        self.assertEqual(ALERT_THRESHOLD, 65)
        self.assertEqual(STRONG_THRESHOLD, 78)


class TestScannerEquivalence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scanner, cls.quality_engine = _load_modules()

    def test_imported_helpers_preserve_identity(self):
        self.assertIs(self.scanner._get_signal_family, self.quality_engine._get_signal_family)
        self.assertIs(self.scanner._get_signal_family_key, self.quality_engine._get_signal_family_key)
        self.assertIs(self.scanner._final_judgment, self.quality_engine._final_judgment)

    def test_calc_signal_quality_wrapper_matches_pure_core(self):
        signals = ["bb_touch", "rsi_oversold"]
        tech = {
            "price": 100.0,
            "ma50": 100.0,
            "rsi": 28,
            "bb_pos": 10,
            "vol_ratio": 2.0,
            "change_1d": -1.5,
            "change_5d": -6.0,
            "vix_level": 18,
        }
        aria = {
            "regime": "중립",
            "thesis_killers": [],
            "note": "",
            "trend": "",
            "fear_greed": "40",
        }
        weights = {"ticker_accuracy": {"AAA": {"accuracy": 40, "total": 10}}}

        with tempfile.TemporaryDirectory() as tmpdir:
            data_file = Path(tmpdir) / "market_data.json"
            data_file.write_text(
                json.dumps(
                    {
                        "fred": {"bamlh0a0hym2": 3.0, "vixcls": 19.0},
                        "prices": {"pcr_avg": 1.15},
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(self.scanner, "DATA_FILE", data_file):
                actual = self.scanner._calc_signal_quality(
                    signals,
                    tech,
                    aria,
                    ticker="AAA",
                    weights=weights,
                )

        expected = self.quality_engine._calc_signal_quality_core(
            signals,
            tech,
            aria,
            ticker="AAA",
            weights=weights,
            pcr_avg=1.15,
            cached_vix=19.0,
            hy_spread=3.0,
        )
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
