"""R4 — Devil 상벌: 신호 보상의 관점 변환 (관측 전용)."""
from __future__ import annotations

import unittest

from jackal.reward import devil_reward
from apps.jackal import tracker


class DevilRewardMathTestCase(unittest.TestCase):
    def test_objection_is_sign_flip(self):
        # 종목이 벌 받으면(r=-1.2) 반대한 Devil은 상(+1.2)
        self.assertEqual(devil_reward(-1.2, "반대"), 1.2)
        self.assertEqual(devil_reward(0.8, "반대"), -0.8)

    def test_agreement_shares_fate(self):
        self.assertEqual(devil_reward(0.8, "동의"), 0.8)
        self.assertEqual(devil_reward(0.8, "부분동의"), 0.4)  # 확신 절반

    def test_unknown_verdict_is_none(self):
        self.assertIsNone(devil_reward(0.5, ""))
        self.assertIsNone(devil_reward(0.5, "보류"))


class TrackerDevilRewardTestCase(unittest.TestCase):
    def _entry(self, verdict, reward):
        return {"ticker": "T", "price_at_hunt": 100.0, "alerted": True,
                "signals_fired": [], "outcome_correct": True,
                "outcome_1d_hit": True, "peak_pct": 3.0, "peak_day": 2,
                "outcome_pct": 1.0, "reward": reward, "devil_verdict": verdict,
                "swing_type": "기술적과매도", "orca_regime": ""}

    def test_overblocking_devil_accumulates_negative_ema(self):
        weights = {"signal_weights": {}, "signal_accuracy": {}}
        # 반대했는데 종목이 계속 상 받음(r>0) = Devil 벌점 누적
        for _ in range(3):
            tracker._update_weights(weights, self._entry("반대", 0.6))

        stats = weights["devil_reward"]["반대"]
        self.assertEqual(stats["n"], 3)
        self.assertLess(stats["ema_r"], 0)

    def test_entry_without_reward_keeps_accuracy_only(self):
        weights = {"signal_weights": {}, "signal_accuracy": {}}
        entry = self._entry("반대", None)
        del entry["reward"]

        tracker._update_weights(weights, entry)

        self.assertIn("devil_accuracy", weights)
        self.assertNotIn("devil_reward", weights)


if __name__ == "__main__":
    unittest.main()
