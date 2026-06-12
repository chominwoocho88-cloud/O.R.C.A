"""R0 — tracker 보상 shadow: 실가중치 무간섭 + 통계/shadow 누적 (통합)."""
from __future__ import annotations

import copy
import unittest

import pandas as pd

from apps.jackal import tracker


def _entry(**kw):
    base = {
        "ticker": "TEST", "price_at_hunt": 100.0, "alerted": True,
        "signals_fired": ["rsi_oversold"], "outcome_correct": True,
        "outcome_1d_hit": True, "peak_pct": 3.0, "peak_day": 2,
        "outcome_pct": 1.5, "reward": 0.6, "swing_type": "기술적과매도",
        "orca_regime": "위험선호", "devil_verdict": "부분동의",
    }
    base.update(kw)
    return base


def _weights():
    return {
        "signal_weights": {"rsi_oversold": 1.0},
        "signal_accuracy": {},
    }


class CalcOutcomesRewardFieldsTestCase(unittest.TestCase):
    def test_confirmed_entry_carries_reward_fields(self):
        closes = pd.Series([101.0, 103.0, 99.0, 100.5, 102.0])

        result = tracker._calc_outcomes({"price_at_hunt": 100.0}, closes)

        self.assertTrue(result["confirmed"])
        self.assertIn("reward", result)
        self.assertIn("trough_pct", result)
        self.assertGreaterEqual(result["realized_vol_d"], 0.5)  # floor
        self.assertEqual(result["trough_pct"], -1.0)  # 최저 99.0
        self.assertGreater(result["reward"], 0)  # peak +3% 적중

    def test_short_series_has_no_reward_fields(self):
        result = tracker._calc_outcomes({"price_at_hunt": 100.0}, pd.Series([101.0]))

        self.assertFalse(result["confirmed"])
        self.assertNotIn("reward", result)


class RewardShadowTestCase(unittest.TestCase):
    def test_disabled_keeps_real_weights_on_legacy_rule(self):
        weights = _weights()
        before = copy.deepcopy(weights["signal_weights"])

        # 표본 부족(n<5) — 기존 규칙으로는 무조정이어야 한다
        tracker._update_weights(weights, _entry())

        self.assertEqual(weights["signal_weights"], before)  # 실가중치 무간섭
        stats = weights["signal_reward"]["rsi_oversold"]
        self.assertEqual(stats["n"], 1)
        self.assertEqual(stats["ema_r"], 0.6)
        self.assertIn("rsi_oversold", weights["shadow_weights"])
        self.assertNotEqual(weights["shadow_weights"]["rsi_oversold"], 1.0)

    def test_shadow_label_is_canonical(self):
        weights = _weights()
        weights["signal_weights"]["bb_touch"] = 1.0

        tracker._update_weights(
            weights, _entry(signals_fired=["bb_touch(-8%_밴드하단)"]))

        self.assertIn("bb_touch", weights["signal_reward"])
        self.assertNotIn("bb_touch(-8%_밴드하단)", weights["signal_reward"])

    def test_not_alerted_records_stats_but_not_shadow_weight(self):
        weights = _weights()

        tracker._update_weights(weights, _entry(alerted=False))

        self.assertEqual(weights["signal_reward"]["rsi_oversold"]["n"], 1)
        self.assertNotIn("shadow_weights", weights)

    def test_entry_without_reward_is_noop_for_shadow(self):
        weights = _weights()
        entry = _entry()
        del entry["reward"]

        tracker._update_weights(weights, entry)

        self.assertNotIn("signal_reward", weights)

    def test_enabled_flag_still_observation_only_in_this_repo(self):
        # 구레포 계약: 보상 학습은 항상 관측 전용 — enabled=True여도
        # 실가중치 조정은 기존 규칙만 따른다 (전환 판단은 J.A.C.K.A.L에서)
        weights = _weights()
        params = dict(tracker.reward_math.REWARD_PARAMS, enabled=True)
        with unittest.mock.patch.object(
            tracker.reward_math, "REWARD_PARAMS", params
        ):
            tracker._update_weights(weights, _entry(reward=1.0))

        self.assertEqual(weights["signal_weights"]["rsi_oversold"], 1.0)
        self.assertIn("rsi_oversold", weights["shadow_weights"])


import unittest.mock  # noqa: E402


if __name__ == "__main__":
    unittest.main()
