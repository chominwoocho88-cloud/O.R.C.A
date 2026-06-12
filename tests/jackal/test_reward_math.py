"""R0 보상 수학 — 설계 §3~4 성질 고정 (docs/REWARD_SYSTEM_ROADMAP.md)."""
from __future__ import annotations

import unittest

from jackal.reward import (REWARD_PARAMS, compute_reward, next_weight,
                           realized_volatility, update_ema)


def _r(**kw):
    base = dict(swing_hit=True, peak_pct=3.0, outcome_pct=0.0, vol_d=1.0, peak_day=2)
    base.update(kw)
    return compute_reward(**base)


class ComputeRewardTestCase(unittest.TestCase):
    def test_bounded_open_interval(self):
        # 치역은 (-1.5, 1)이지만 round(4)가 극한을 1.0으로 만들 수 있다
        self.assertLessEqual(_r(peak_pct=500.0, vol_d=0.5, peak_day=1), 1.0)
        self.assertGreaterEqual(
            _r(swing_hit=False, outcome_pct=-500.0, vol_d=0.5, peak_day=1), -1.5)

    def test_loss_aversion_asymmetry(self):
        gain = _r(peak_pct=3.0)
        loss = _r(swing_hit=False, outcome_pct=-3.0)
        self.assertAlmostEqual(loss, -gain * REWARD_PARAMS["loss_aversion"], places=3)

    def test_miss_uses_outcome_not_zero(self):
        # 이진이 아니라 "얼마나 틀렸는지"가 벌의 크기
        small = _r(swing_hit=False, outcome_pct=-0.2)
        big = _r(swing_hit=False, outcome_pct=-9.0)
        self.assertLess(big, small)

    def test_faster_peak_earns_more(self):
        self.assertGreater(_r(peak_day=1), _r(peak_day=7))

    def test_volatility_discounts_lottery(self):
        calm = _r(peak_pct=2.5, vol_d=1.0)
        lottery = _r(peak_pct=5.0, vol_d=4.0)
        self.assertGreater(calm, lottery)

    def test_vol_floor_prevents_blowup(self):
        self.assertEqual(_r(vol_d=0.0), _r(vol_d=REWARD_PARAMS["vol_floor"]))


class NextWeightTestCase(unittest.TestCase):
    def test_mean_reversion_pulls_to_one(self):
        # 보상 0이어도 1.0 방향으로 끌림 — 고착 방지 + 용서
        self.assertGreater(next_weight(0.35, 0.0, 10), 0.35)
        self.assertLess(next_weight(2.5, 0.0, 10), 2.5)

    def test_floor_recovery_path_exists(self):
        # 바닥(0.3) 신호가 양 보상으로 부활 가능
        w = 0.3
        for _ in range(20):
            w = next_weight(w, 0.5, 10)
        self.assertGreater(w, 0.5)

    def test_clip_bounds(self):
        self.assertEqual(next_weight(2.49, 1.0, 10), 2.5)
        self.assertEqual(next_weight(0.31, -1.5, 10), 0.3)

    def test_warmup_damps_early_samples(self):
        early = next_weight(1.0, 1.0, 1)
        warmed = next_weight(1.0, 1.0, 5)
        self.assertLess(early - 1.0, warmed - 1.0)


class EmaAndVolTestCase(unittest.TestCase):
    def test_ema_first_sample_initializes(self):
        self.assertEqual(update_ema(None, 0.62), 0.62)

    def test_ema_forgets_old(self):
        value = 1.0
        for _ in range(30):  # 0 보상 연속 — 과거 영광은 잊혀진다
            value = update_ema(value, 0.0)
        self.assertLess(value, 0.01)

    def test_volatility_floor_on_short_series(self):
        self.assertEqual(realized_volatility([100.0]), REWARD_PARAMS["vol_floor"])

    def test_volatility_of_flat_series_is_floor(self):
        self.assertEqual(realized_volatility([100, 100, 100, 100]),
                         REWARD_PARAMS["vol_floor"])

    def test_volatility_computes_pct_std(self):
        vol = realized_volatility([100, 102, 99, 103, 100])
        self.assertGreater(vol, 1.0)


if __name__ == "__main__":
    unittest.main()


class DrawdownPenaltyTestCase(unittest.TestCase):
    """R4 선행 — 계수 0.0이면 동작 불변, 켜면 깊은 트로프가 보상을 깎는다."""

    def test_default_zero_changes_nothing(self):
        self.assertEqual(_r(trough_pct=-8.0), _r(trough_pct=None))

    def test_enabled_discounts_painful_wins(self):
        params = dict(REWARD_PARAMS, drawdown_penalty=0.5)
        smooth = compute_reward(swing_hit=True, peak_pct=3.0, outcome_pct=0,
                                vol_d=1.0, peak_day=2, trough_pct=-0.5, params=params)
        painful = compute_reward(swing_hit=True, peak_pct=3.0, outcome_pct=0,
                                 vol_d=1.0, peak_day=2, trough_pct=-8.0, params=params)
        self.assertLess(painful, smooth)
        self.assertGreaterEqual(painful, -1.5)
