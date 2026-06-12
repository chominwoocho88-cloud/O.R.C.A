"""설계 §7 질적 성질 고정 — 시드 고정 시뮬 회귀 (값이 아닌 성질을 본다)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.backfill_signal_rewards import replay
from scripts.sim_reward_vs_legacy import PROFILES, simulate


class SimulationPropertiesTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = {p.name: simulate(p, events=200, seed=42) for p in PROFILES}

    def test_strong_calm_signal_grows(self):
        self.assertGreater(self.out["strong_calm"]["reward"], 2.0)
        self.assertGreater(self.out["strong_calm"]["ema_r"], 0.5)

    def test_lottery_discounted_below_strong(self):
        self.assertLess(self.out["lottery"]["reward"],
                        self.out["strong_calm"]["reward"] * 0.6)

    def test_regime_collapse_decays_faster_than_legacy(self):
        flip = self.out["regime_flip"]
        self.assertLess(flip["reward"], flip["legacy"])
        self.assertLess(flip["ema_r"], 0)

    def test_weights_stay_in_bounds(self):
        for out in self.out.values():
            self.assertGreaterEqual(out["reward"], 0.3)
            self.assertLessEqual(out["reward"], 2.5)


class BackfillReplayTestCase(unittest.TestCase):
    def test_replay_normalizes_and_gates_shadow(self):
        entries = [
            {"outcome_checked": True, "timestamp": "2026-06-01T09:00:00",
             "outcome_swing_hit": True, "peak_pct": 3.0, "outcome_pct": 1.0,
             "peak_day": 2, "alerted": True,
             "signals_fired": ["rsi_oversold_boundary(42.1_접근)"]},
            {"outcome_checked": True, "timestamp": "2026-06-02T09:00:00",
             "outcome_swing_hit": False, "peak_pct": 0.5, "outcome_pct": -2.0,
             "peak_day": 1, "alerted": False,  # 미발송 — 통계만
             "signals_fired": ["rsi_oversold"]},
            {"outcome_checked": False, "signals_fired": ["rsi_oversold"]},  # 미확정 제외
        ]

        stats, shadow, devil_stats = replay(entries, {"rsi_oversold": 1.0})

        self.assertEqual(set(stats), {"rsi_oversold"})  # canonical 합산
        self.assertEqual(stats["rsi_oversold"]["n"], 2)
        self.assertIn("rsi_oversold", shadow)  # alerted 1건만 가중치 반영
        self.assertGreater(shadow["rsi_oversold"], 1.0)
        self.assertEqual(devil_stats, {})  # verdict 없는 entry — devil 통계 없음


if __name__ == "__main__":
    unittest.main()
