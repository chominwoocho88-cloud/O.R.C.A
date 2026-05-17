"""Tests for the extracted JACKAL deterministic quality engine.

Includes regression coverage for the family ordering hazard that was
fixed after P2-3 extraction. The quality core now computes signal family
before micro-gate and high-uncertainty branches read it.
"""

from __future__ import annotations

import importlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXPECTED_REGISTRY = {
    "hunter": {
        "analyze_final": 5,
        "cooldown_hours": 6,
        "macro_gate": {
            "vix_extreme": 50,
            "vix_fear": 35,
            "vix_watch": 28,
            "vix_penalty_extreme": 20,
            "vix_penalty_fear": 10,
            "vix_penalty_watch": 5,
            "yield_curve_deep_inversion": -0.5,
            "yield_curve_inversion": 0,
            "yield_curve_penalty_deep": 8,
            "yield_curve_penalty_shallow": 3,
            "hy_chg5_stress": -2.0,
            "hy_chg5_watch": -1.0,
            "hy_penalty_stress": 7,
            "hy_penalty_watch": 3,
            "risk_off_regime_penalty": 5,
            "risk_level_extreme_cutoff": 25,
            "risk_level_elevated_cutoff": 10,
        },
        "technical_scoring": {
            "rsi": {
                "bonus_25": {"cutoff": 25, "score": 35},
                "bonus_30": {"cutoff": 30, "score": 28},
                "bonus_35": {"cutoff": 35, "score": 18},
                "bonus_40": {"cutoff": 40, "score": 9},
                "bonus_50": {"cutoff": 50, "score": 3},
                "penalty_75": {"cutoff": 75, "score": -18},
                "penalty_65": {"cutoff": 65, "score": -8},
            },
            "bb": {
                "bonus_5": {"cutoff": 5, "score": 30},
                "bonus_10": {"cutoff": 10, "score": 24},
                "bonus_20": {"cutoff": 20, "score": 15},
                "bonus_30": {"cutoff": 30, "score": 7},
                "penalty_90": {"cutoff": 90, "score": -13},
                "penalty_80": {"cutoff": 80, "score": -6},
            },
            "combo": {
                "rsi_30_bb_15": {"rsi": 30, "bb": 15, "score": 25},
                "rsi_35_bb_25": {"rsi": 35, "bb": 25, "score": 15},
                "rsi_40_bb_35": {"rsi": 40, "bb": 35, "score": 8},
            },
            "change_5d": {
                "bonus_10": {"cutoff": -10, "score": 20},
                "bonus_7": {"cutoff": -7, "score": 14},
                "bonus_5": {"cutoff": -5, "score": 9},
                "bonus_3": {"cutoff": -3, "score": 4},
                "penalty_15": {"cutoff": 15, "score": -14},
                "penalty_10": {"cutoff": 10, "score": -7},
            },
            "volume": {
                "bonus_drop_3x": {"vol_ratio": 3.0, "change_1d_max": 0, "score": 15},
                "bonus_drop_2x": {"vol_ratio": 2.0, "change_1d_max": 0, "score": 10},
                "bonus_3x": {"vol_ratio": 3.0, "score": 7},
                "bonus_2x": {"vol_ratio": 2.0, "score": 5},
                "bonus_1_5x": {"vol_ratio": 1.5, "score": 2},
            },
            "ma_support": {
                "distance": 0.03,
                "rsi_oversold": 40,
                "bb_oversold": 30,
                "chg5_oversold": -3,
                "bonus_with_oversold": 5,
                "bonus_solo": 1,
            },
            "bullish_divergence_bonus": 15,
            "bullish_candle_bonus": 5,
            "bullish_candle_chg5_max": -3,
            "sector_relative": {
                "bonus_5": {"cutoff": -5, "score": 12},
                "bonus_3": {"cutoff": -3, "score": 8},
                "bonus_1": {"cutoff": -1, "score": 4},
            },
        },
        "reason_generation": {
            "chg5_hard_drop": -7,
            "chg5_drop": -4,
            "rsi_extreme": 30,
            "rsi_oversold": 40,
        },
        "context_boosts": {
            "regime_preferred": 8,
            "regime_risk_off": -5,
            "regime_mixed": 2,
            "sector_inflow": 10,
            "sector_outflow": -8,
            "kr_risk_off_penalty": -5,
        },
        "swing_type": {
            "sector_rotation": {"rsi_max": 50, "chg5_max": -2},
            "panic_rebound": {"rsi_max": 35, "chg5_max": -5, "vol_ratio_min": 1.5},
            "panic_rebound_risk_off": {"rsi_max": 40, "chg5_max": -4},
            "momentum_dip": {"chg5_max": -5, "rsi_max": 45},
            "ma_support": {"distance": 0.03, "rsi_max": 45},
        },
        "volume_interpretation": {
            "high_volume": 2.0,
            "high_volume_down_change": -1,
            "low_volume": 0.7,
        },
        "entry_decision": {
            "alert_threshold": 55,
            "devil_block_score": 70,
            "default_day1_score": 50,
            "default_swing_score": 50,
            "default_devil_score": 30,
            "swing_weights": {
                "sector_rotation": {"day1": 0.3, "swing": 0.7},
                "panic_rebound": {"day1": 0.5, "swing": 0.5},
                "momentum_dip": {"day1": 0.35, "swing": 0.65},
                "bullish_divergence": {"day1": 0.4, "swing": 0.6},
                "ma_support": {"day1": 0.6, "swing": 0.4},
                "technical_oversold": {"day1": 0.55, "swing": 0.45},
                "default": {"day1": 0.4, "swing": 0.6},
            },
            "devil_penalty_baseline": 30,
            "devil_penalty_multiplier": 0.25,
            "entry_thresholds": {
                "sector_rotation": 48,
                "panic_rebound": 50,
                "momentum_dip": 50,
                "bullish_divergence": 50,
                "technical_oversold": 55,
                "ma_support": 60,
                "default": 55,
                "additional_decline_override": 99,
            },
            "mode_thresholds": {
                "strong": {"day1_min": 65, "swing_min": 65},
                "scalp": {"day1_min": 60, "swing_max": 50},
                "scale_in": {"day1_max": 50, "swing_min": 65},
            },
        },
    },
    "quality": {
        "alert_threshold": 65,
        "strong_threshold": 78,
        "pre_rule": {
            "rsi_oversold": 32,
            "bb_touch": 15,
            "volume_climax_ratio": 1.8,
            "volume_climax_change_1d": -1.0,
            "momentum_dip_change_5d": -4.0,
            "sector_rebound_rsi": 40,
            "sector_rebound_change": -2.0,
            "rsi_divergence_rsi": 35,
            "52w_low_zone": 15,
            "ma_support_distance": 0.025,
        },
        "core_scores": {
            "sector_rebound": 20,
            "volume_climax": 15,
            "bb_touch_with_rsi_oversold": 16,
            "bb_touch": 12,
            "rsi_oversold": 9,
            "momentum_dip_multi_signal": 5,
            "rsi_divergence_solo_penalty": -20,
            "rsi_divergence_momentum_penalty": -12,
            "rsi_divergence_vol_accumulation": 3,
            "52w_low_zone": 12,
            "vol_accumulation": 12,
            "vol_accumulation_sector_rebound_combo": 8,
            "52w_low_zone_rsi_oversold_combo": 6,
            "vol_accumulation_momentum_combo": 5,
            "bb_sector_rsi_combo": 15,
            "ma_support_solo_penalty": -12,
            "ma_support_weak_penalty": -5,
            "rebound_cap": 12,
        },
        "pcr": {
            "extreme": 1.3,
            "elevated": 1.1,
            "crowded_long": 0.8,
            "extreme_bonus": 10,
            "elevated_bonus": 5,
            "crowded_long_penalty": -8,
        },
        "macro_rebound": {
            "vix_extreme": 35,
            "vix_high": 25,
            "real_panic_vix": 30,
            "real_panic_hy_spread": 4.0,
            "credit_stress_hy_spread": 3.5,
            "real_panic_bonus": 10,
            "vix_extreme_bonus": 6,
            "credit_stress_bonus": 4,
            "chg5_extreme_drop": -8,
            "chg5_drop": -5,
            "chg5_extreme_bonus": 10,
            "chg5_multi_signal_bonus": 5,
            "multi_signal_count_min": 2,
        },
        "regime_veto": {
            "mixed_penalty": -15,
            "risk_off_sector_rebound_bonus": 5,
            "overheat_change_5d": 15,
            "overheat_penalty": -8,
        },
        "fear_greed": {
            "default_score": 50,
            "fear_gate": 15,
            "vix_only_hard": 40,
            "vix_fg_hard": 32,
            "keyword_vix_soft": 28,
            "micro_gate_vix": 22,
            "hard_penalty": 15,
            "soft_penalty": 8,
            "micro_penalty": 5,
        },
        "ticker_accuracy": {
            "strong_sample_min": 8,
            "strong_slope": 0.20,
            "strong_floor": -10,
            "strong_cap": 0,
            "strong_reason_min_abs": 1,
            "light_sample_min": 3,
            "light_slope": 0.10,
            "light_floor": -5,
            "light_cap": 0,
            "light_reason_min_abs": 0.5,
        },
        "family_skip": {
            "crash_rebound": 35,
            "general": 45,
            "ma_support_weak": 47,
            "ma_support_solo": 46,
            "crash_rebound_high_vix": 30,
            "crash_rebound_high_vix_floor": 33,
            "crash_rebound_high_vix_delta": -5,
            "crash_rebound_low_vix": 18,
            "crash_rebound_low_vix_cap": 46,
            "crash_rebound_low_vix_delta": 3,
            "general_low_vix": 18,
            "general_low_vix_cap": 50,
            "general_low_vix_delta": 5,
        },
        "labels": {
            "strong": 80,
            "good": 65,
            "fair": 50,
            "analyst_bonus_cutoff": 75,
            "final_bonus_cutoff": 75,
        },
        "final_judgment": {
            "thesis_killer_score": 20,
            "verdict_weights": {
                "agree": 1.0,
                "partial": 0.75,
                "oppose": 0.5,
            },
            "devil_penalty_baseline": 30,
            "devil_penalty_multiplier": 0.2,
            "watch_cutoff": 40,
            "sell_cutoff": 30,
        },
    },
    "scanner": {
        "cooldown": {
            "hours": 4,
            "family_hours": 48,
            "quality_surge": 15,
            "volume_spike": 2.5,
            "declining_change_max": 0,
            "override_limit_hours": 120,
        },
        "schd_regime": {
            "period_days": 10,
            "min_rows": 5,
            "lookback_index": 5,
            "drop_threshold": -3.0,
            "confidence_penalty": -5.0,
        },
        "analyst_hint": {
            "min_accuracy_samples": 3,
        },
        "signal_relabel": {
            "watch_cutoff": 40,
            "sell_cutoff": 30,
        },
    },
    "evolution": {
        "core": {
            "outcome_hours": 4,
            "success_pct": 0.5,
            "weight_adjust_up": 0.04,
            "weight_adjust_down": 0.03,
            "weight_min": 0.3,
            "weight_max": 2.5,
        },
        "outcomes": {
            "cutoff_hours": 28,
            "d1_correct_pct": 0.3,
            "swing_hit_pct": 1.0,
            "swing_min_rows": 3,
            "d1_bonus": 0.01,
            "change_log_min_delta": 0.001,
        },
        "recommendations": {
            "cutoff_hours": 24,
            "success_pct": 0.5,
        },
    },
    "tracker": {
        "outcomes": {
            "min_elapsed_hours": 26,
            "swing_days": 7,
            "swing_hit_pct": 1.0,
            "d1_hit_pct": 0.5,
            "min_swing_rows": 3,
            "yfinance_delay": 0.4,
        },
        "weights": {
            "adjust_up": 0.04,
            "adjust_down": 0.03,
            "min": 0.3,
            "max": 2.5,
            "min_samples_adjust": 5,
            "high_accuracy_cutoff": 0.70,
            "low_accuracy_cutoff": 0.40,
            "change_log_min_delta": 0.001,
        },
    },
}


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
    for name in ("apps.jackal.scanner", "jackal.quality_engine"):
        sys.modules.pop(name, None)
    quality_engine = importlib.import_module("jackal.quality_engine")
    scanner = importlib.import_module("apps.jackal.scanner")
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


class TestMicroGateRegressionHazards(unittest.TestCase):
    """Regression coverage for the former family ordering hazard."""

    def test_bearish_regime_high_vix_does_not_crash(self):
        from jackal.quality_engine import _calc_signal_quality_core

        result = _calc_signal_quality_core(
            ["ma_support"],
            {
                "price": 100.0,
                "ma50": 100.0,
                "rsi": 45,
                "bb_pos": 50,
                "vol_ratio": 1.0,
                "change_1d": 0.0,
                "change_5d": -1.0,
                "vix_level": 25,
            },
            {
                "regime": "위험회피",
                "thesis_killers": [],
                "note": "",
                "trend": "",
                "fear_greed": "40",
            },
            weights={},
            pcr_avg=0.0,
            cached_vix=25.0,
            hy_spread=3.0,
        )

        self.assertEqual(result["signal_family"], "ma_support_solo")
        self.assertTrue(
            any("레짐microgate" in reason for reason in result["reasons"]),
            "Expected regime_micro path to execute without NameError.",
        )

    def test_high_uncertainty_path_does_not_crash(self):
        from jackal.quality_engine import _calc_signal_quality_core

        result = _calc_signal_quality_core(
            ["bb_touch"],
            {
                "price": 100.0,
                "ma50": 99.0,
                "rsi": 40,
                "bb_pos": 10,
                "vol_ratio": 1.0,
                "change_1d": -1.0,
                "change_5d": -2.0,
                "vix_level": 32,
            },
            {
                "regime": "중립",
                "thesis_killers": [],
                "note": "",
                "trend": "",
                "fear_greed": "50",
            },
            weights={},
            pcr_avg=0.0,
            cached_vix=32.0,
            hy_spread=3.0,
        )

        self.assertEqual(result["signal_family"], "general")
        self.assertTrue(
            any("불확실게이트[" in reason for reason in result["reasons"]),
            "Expected high uncertainty branch to execute without NameError.",
        )


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
    def test_registry_values_match(self):
        from jackal.thresholds import THRESHOLDS

        self.assertEqual(THRESHOLDS, EXPECTED_REGISTRY)

    def test_quality_thresholds_accessible(self):
        from jackal.quality_engine import ALERT_THRESHOLD, STRONG_THRESHOLD

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
