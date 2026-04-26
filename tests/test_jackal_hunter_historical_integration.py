from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from jackal import historical_context
from jackal import hunter


def _features() -> dict:
    return {
        "regime": "risk-on",
        "vix_level": 18.5,
        "sp500_momentum_5d": 1.0,
        "sp500_momentum_20d": 3.0,
        "nasdaq_momentum_5d": 1.2,
        "nasdaq_momentum_20d": 3.5,
        "dominant_sectors": ["Technology", "Communication Services"],
    }


def _lesson(value: float = 8.0, ticker: str = "AAA") -> dict:
    return {
        "lesson_id": f"lesson_{ticker}",
        "ticker": ticker,
        "analysis_date": "2026-04-01",
        "signal_family": "momentum_pullback",
        "lesson_value": value,
        "peak_pct": value,
        "peak_day": 3,
        "quality_tier": "high",
        "relevance_score": 0.91,
        "cluster_id": "cluster_c00",
        "cluster_label": "medium_vix_bullish_riskon_growth",
        "distance_to_centroid": 0.4,
        "target_distance_to_cluster": 0.8,
    }


def _hc(mode: str = "observe", win_rate: float = 0.8, avg_value: float = 8.0) -> dict:
    return {
        "cluster_id": "cluster_c00",
        "cluster_label": "medium_vix_bullish_riskon_growth",
        "cluster_distance": 0.8,
        "lessons": [_lesson(8.0, "AAA"), _lesson(5.0, "BBB")],
        "win_rate": win_rate,
        "avg_value": avg_value,
        "high_quality_count": 5,
        "mode": mode,
    }


def _top_item() -> dict:
    return {
        "ticker": "AAA",
        "name": "Alpha",
        "currency": "$",
        "hunt_reason": "test",
        "s1_score": 80,
        "s2_score": 82,
        "tech": {
            "price": 100.0,
            "change_1d": 1.2,
            "change_5d": -4.0,
            "rsi": 34,
            "bb_pos": 20.0,
            "vol_ratio": 1.4,
            "bullish_div": False,
        },
    }


def _aria() -> dict:
    return {
        "regime": "risk-on",
        "key_inflows": ["Technology"],
        "key_outflows": [],
        "historical_context_features": _features(),
    }


def _analyst() -> dict:
    return {
        "analyst_score": 80,
        "day1_score": 78,
        "swing_score": 82,
        "swing_type": "momentum_pullback",
        "swing_setup": "rebound",
        "signals_fired": ["rsi_oversold"],
        "bull_case": "mean reversion setup",
        "entry_zone": "$99-101",
        "target_5d": "$108",
        "stop_loss": "$95",
        "expected_days": 5,
    }


def _devil() -> dict:
    return {
        "devil_score": 20,
        "verdict": "ok",
        "main_risk": "",
        "thesis_killer_hit": False,
        "devil_status": "no_material_objection",
        "devil_parse_ok": True,
        "devil_called": True,
    }


def _final() -> dict:
    return {
        "final_score": 70.0,
        "is_entry": True,
        "label": "candidate",
        "mode": "standard",
        "day1_score": 78,
        "swing_score": 82,
        "entry_threshold": 65.0,
    }


class HistoricalContextHelperTests(unittest.TestCase):
    def test_use_historical_context_default_on(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(historical_context.historical_context_enabled())

    def test_use_historical_context_disabled(self):
        with patch.dict(os.environ, {"USE_HISTORICAL_CONTEXT": "0"}):
            self.assertFalse(historical_context.historical_context_enabled())

    def test_retrieve_failure_returns_none(self):
        with patch.object(
            historical_context,
            "retrieve_similar_lessons_for_features",
            side_effect=RuntimeError("boom"),
        ):
            result = historical_context.try_retrieve_historical_context(
                _features(),
                "momentum_pullback",
                {"ticker": "AAA"},
            )
        self.assertIsNone(result)

    def test_no_historical_context_when_no_lessons(self):
        with patch.object(historical_context, "retrieve_similar_lessons_for_features", return_value=[]):
            result = historical_context.try_retrieve_historical_context(_features(), "momentum_pullback")
        self.assertIsNone(result)

    def test_try_retrieve_returns_dict_structure(self):
        lessons = [_lesson(8.0, "AAA"), _lesson(4.0, "BBB"), _lesson(-1.0, "CCC")]
        with patch.object(
            historical_context,
            "retrieve_similar_lessons_for_features",
            return_value=lessons,
        ) as mocked:
            result = historical_context.try_retrieve_historical_context(_features(), "momentum_pullback")

        mocked.assert_called_once()
        self.assertEqual(mocked.call_args.kwargs["quality_filter"], "high")
        self.assertEqual(result["cluster_id"], "cluster_c00")
        self.assertEqual(len(result["lessons"]), 3)
        self.assertAlmostEqual(result["win_rate"], 2 / 3)

    def test_market_features_from_aria_normalizes_direct_features(self):
        features = historical_context.market_features_from_aria({"market_features": _features()})

        self.assertEqual(features["regime"], "위험선호")
        self.assertIn("Technology", features["dominant_sectors"])

    def test_calculate_score_adjustment_high_win_rate(self):
        adjustment = historical_context.calculate_score_adjustment(_hc("adjust", 0.9, 10.0))
        self.assertEqual(adjustment, 5.0)

    def test_calculate_score_adjustment_low_win_rate(self):
        adjustment = historical_context.calculate_score_adjustment(_hc("adjust", 0.1, -10.0))
        self.assertEqual(adjustment, -5.0)

    def test_calculate_score_adjustment_neutral_zero(self):
        adjustment = historical_context.calculate_score_adjustment(_hc("adjust", 0.5, 0.0))
        self.assertEqual(adjustment, 0.0)

    def test_calculate_score_adjustment_quality_multiplier(self):
        low_quality = _hc("adjust", 0.7, 5.0)
        high_quality = _hc("adjust", 0.7, 5.0)
        low_quality["high_quality_count"] = 0
        high_quality["high_quality_count"] = 5

        self.assertGreater(
            historical_context.calculate_score_adjustment(high_quality),
            historical_context.calculate_score_adjustment(low_quality),
        )

    def test_observe_mode_no_score_change(self):
        final = historical_context.apply_historical_adjustment(_final(), _hc("observe", 0.9, 10.0))

        self.assertEqual(final["final_score"], 70.0)
        self.assertEqual(final["historical_adjustment"], 0.0)

    def test_adjust_mode_caps_positive_and_negative(self):
        positive = historical_context.apply_historical_adjustment(_final(), _hc("adjust", 0.9, 10.0))
        negative = historical_context.apply_historical_adjustment(_final(), _hc("adjust", 0.1, -10.0))

        self.assertEqual(positive["historical_adjustment"], 5.0)
        self.assertEqual(positive["final_score"], 75.0)
        self.assertEqual(negative["historical_adjustment"], -5.0)
        self.assertEqual(negative["final_score"], 65.0)


class HunterHistoricalIntegrationTests(unittest.TestCase):
    def _run_stage4(self, context: dict | None):
        with (
            patch.object(hunter, "_is_on_cooldown", return_value=False),
            patch.object(hunter, "_analyst_swing", return_value=_analyst()),
            patch.object(hunter, "_devil_swing", return_value=_devil()),
            patch.object(hunter, "_final", return_value=_final()),
            patch.object(hunter, "apply_probability_adjustment", side_effect=lambda final, *_a, **_kw: final),
            patch.object(hunter, "_historical_market_features_from_aria", return_value=_features()),
            patch.object(hunter, "_try_retrieve_historical_context", return_value=context),
        ):
            return hunter._stage4_full_analysis([_top_item()], _aria())

    def test_stage4_observe_mode_adds_historical_context_without_score_change(self):
        result = self._run_stage4(_hc("observe", 0.9, 10.0))[0]

        self.assertEqual(result["final"]["final_score"], 70.0)
        self.assertEqual(result["historical_context"]["cluster_id"], "cluster_c00")
        self.assertEqual(result["historical_adjustment"], 0.0)

    def test_stage4_adjust_mode_changes_score_with_cap(self):
        result = self._run_stage4(_hc("adjust", 0.9, 10.0))[0]

        self.assertEqual(result["final"]["final_score"], 75.0)
        self.assertEqual(result["historical_adjustment"], 5.0)

    def test_stage4_continues_when_no_context(self):
        result = self._run_stage4(None)[0]

        self.assertIsNone(result["historical_context"])
        self.assertEqual(result["final"]["final_score"], 70.0)

    def test_stage4_telegram_alert_includes_historical_context(self):
        item = {
            **_top_item(),
            "analyst": _analyst(),
            "devil": _devil(),
            "final": _final(),
            "signal_family": "momentum_pullback",
            "historical_context": _hc("observe", 0.8, 6.5),
        }
        with patch.object(hunter, "build_hunter_explanation_lines", return_value=[]):
            alert = hunter._build_alert(item, _aria())

        self.assertIn("Historical Context", alert)
        self.assertIn("Similar examples", alert)
        self.assertIn("AAA", alert)

    def test_stage4_hunt_log_includes_historical_context(self):
        item = {
            **_top_item(),
            "analyst": _analyst(),
            "devil": _devil(),
            "final": {**_final(), "historical_adjustment": 2.5},
            "signal_family": "momentum_pullback",
            "raw_signal_family": "momentum_pullback",
            "historical_context": _hc("adjust", 0.8, 6.5),
        }

        entry = hunter._build_hunt_log_entry(item, _aria())

        self.assertEqual(entry["historical_context"]["cluster_id"], "cluster_c00")
        self.assertEqual(entry["historical_adjustment"], 2.5)


if __name__ == "__main__":
    unittest.main()
