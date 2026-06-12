"""'타점 없음' 요약의 이유 줄 — 24점의 사연이 보여야 한다 (2026-06-12)."""
from __future__ import annotations

import unittest

from apps.jackal.hunter import _build_summary, _summary_reason_line


def _item(**kw):
    base = {
        "ticker": "GOOGL", "name": "알파벳", "currency": "$",
        "tech": {"rsi": 28.0, "change_5d": -8.2, "bullish_div": False,
                 "price": 150.0, "change_1d": -1.0, "bb_pos": 10.0, "vol_ratio": 1.2},
        "analyst": {"swing_setup": "중립", "day1_score": 68, "swing_score": 76,
                    "main_risk": "거시 역풍"},
        "devil": {"verdict": "반대", "devil_score": 80, "main_risk": "추세 미확인, 거시 역풍"},
        "final": {"final_score": 25.0, "label": "❌ Devil 강반대", "mode": "차단",
                  "day1_score": 25, "swing_score": 25},
    }
    base.update(kw)
    return base


class SummaryReasonTestCase(unittest.TestCase):
    def test_blocked_item_shows_block_label_and_risk(self):
        line = _summary_reason_line(_item())

        self.assertIn("Devil 강반대", line)
        self.assertIn("추세 미확인", line)

    def test_normal_item_shows_score_breakdown_and_verdict(self):
        item = _item(final={"final_score": 58.0, "label": "관망", "mode": "일반",
                            "day1_score": 52, "swing_score": 62},
                     devil={"verdict": "부분동의", "main_risk": "수급 약세"})

        line = _summary_reason_line(item)

        self.assertIn("1일 52점·스윙 62점", line)
        self.assertIn("Devil 부분동의", line)
        self.assertIn("수급 약세", line)

    def test_build_summary_includes_reason_per_item(self):
        aria = {"regime": "위험회피 (테스트)"}

        text = _build_summary([_item()], aria)

        self.assertIn("25점", text)
        self.assertIn("└", text)
        self.assertIn("Devil 강반대", text)

    def test_missing_fields_do_not_crash(self):
        line = _summary_reason_line({"final": {}, "devil": {}, "analyst": {}})

        self.assertIn("1일 ?점", line)


if __name__ == "__main__":
    unittest.main()
