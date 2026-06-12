"""L2-1 — 신호 라벨 정규화 + 재집계 (실측 파편 사례 기반)."""
from __future__ import annotations

import unittest

from scripts.migrate_signal_accuracy import merge_signal_accuracy
from shared.contracts.signals import CANONICAL_SIGNALS, normalize_signal_label


class NormalizeLabelTestCase(unittest.TestCase):
    def test_real_world_fragments_collapse(self):
        # jackal_weights.json에서 실제 관찰된 파편들
        cases = {
            "bb_touch(-8%_밴드하단)": "bb_touch",
            "bb_touch_lower": "bb_touch",
            "bb_oversold_zone": "bb_touch",
            "rsi_oversold_boundary(42.1_접근)": "rsi_oversold",
            "rsi_oversold_boundary": "rsi_oversold",
            "ma_support(50MA_+3.2%_근처)": "ma_support",
            "ma_support_test": "ma_support",
            "sector_inflow_hbm": "sector_inflow",
            "sector_inflow_감지(ARIA_미반영)": "sector_inflow",
            "volume_climax(1.8x_정도_중립)": "volume_climax",
            "bullish_div": "rsi_divergence",
            "bullish_div_absence_neutral": "rsi_divergence",
        }
        for raw, expected in cases.items():
            self.assertEqual(normalize_signal_label(raw), expected, raw)

    def test_canonical_passthrough(self):
        for canon in CANONICAL_SIGNALS:
            self.assertEqual(normalize_signal_label(canon), canon)

    def test_unknown_and_empty_become_other_only(self):
        for raw in ("fundamental_strength_mismatch", "regime_headwind",
                    "volume_recovery_signal", "", None, "완전 새로운 신호"):
            self.assertEqual(normalize_signal_label(raw), "other")


class MergeAccuracyTestCase(unittest.TestCase):
    def test_counts_sum_and_accuracy_recomputed(self):
        sig_acc = {
            "bb_touch": {"accuracy": 50.0, "correct": 3, "total": 6},
            "bb_touch(-8%_밴드하단)": {"accuracy": 100.0, "correct": 1, "total": 1},
            "bb_touch_lower": {"accuracy": 0.0, "correct": 0, "total": 1},
        }

        merged, mapping = merge_signal_accuracy(sig_acc)

        self.assertEqual(set(merged), {"bb_touch"})
        self.assertEqual(merged["bb_touch"]["total"], 8)
        self.assertEqual(merged["bb_touch"]["correct"], 4)
        self.assertEqual(merged["bb_touch"]["accuracy"], 50.0)
        self.assertEqual(len(mapping), 2)

    def test_sample_total_is_preserved(self):
        sig_acc = {
            "rsi_oversold": {"correct": 4, "total": 7},
            "rsi_oversold_boundary": {"correct": 0, "total": 1},
            "fundamental_strength_mismatch": {"correct": 0, "total": 1},
        }

        merged, _ = merge_signal_accuracy(sig_acc)

        self.assertEqual(sum(r["total"] for r in merged.values()), 9)
        self.assertIn("other", merged)

    def test_new_schema_keys_supported(self):
        sig_acc = {
            "ma_support": {"total": 3, "swing_correct": 1, "d1_correct": 2,
                           "swing_accuracy": 33.3, "d1_accuracy": 66.7},
            "ma_support_test": {"total": 1, "swing_correct": 1, "d1_correct": 0},
        }

        merged, _ = merge_signal_accuracy(sig_acc)

        rec = merged["ma_support"]
        self.assertEqual(rec["total"], 4)
        self.assertEqual(rec["swing_accuracy"], 50.0)
        self.assertEqual(rec["d1_accuracy"], 50.0)


if __name__ == "__main__":
    unittest.main()


class RegimeNormalizationTestCase(unittest.TestCase):
    def test_strips_parenthetical_modifiers(self):
        from shared.contracts.signals import normalize_regime_label

        cases = {
            "위험선호 (급반전 취약 구간 내재)": "위험선호",
            "위험선호(전환 경계)": "위험선호",
            "혼조 (미국 위험선호 표면 / 한국 위험회피 심화)": "혼조",
            "위험회피": "위험회피",
            "": "",
        }
        for raw, expected in cases.items():
            self.assertEqual(normalize_regime_label(raw), expected, raw)

    def test_merge_regime_accuracy_preserves_meta_of_bigger_bucket(self):
        from scripts.migrate_signal_accuracy import merge_regime_accuracy

        reg = {
            "위험선호": {"accuracy": 69.7, "correct": 1550, "total": 2225,
                       "generated_at": "2026-04-29", "metric": "swing_accuracy"},
            "위험선호 (급반전 취약 구간 내재)": {"accuracy": 50.0, "correct": 1, "total": 2},
        }

        merged, mapping = merge_regime_accuracy(reg)

        self.assertEqual(set(merged), {"위험선호"})
        self.assertEqual(merged["위험선호"]["total"], 2227)
        self.assertEqual(merged["위험선호"]["correct"], 1551)
        self.assertEqual(merged["위험선호"]["generated_at"], "2026-04-29")
        self.assertAlmostEqual(merged["위험선호"]["accuracy"], 69.6, places=1)
        self.assertEqual(len(mapping), 1)
