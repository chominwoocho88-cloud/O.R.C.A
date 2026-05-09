import unittest

from orca.analysis_review import (
    _quality_component,
    _signal_family_history_component,
)
from orca.notify import REASON_DESCRIPTIONS


class Phase52bInsufficientDataSplitTests(unittest.TestCase):
    def test_no_signal_family(self):
        """signal_family 없음 -> no_signal_family."""
        result = _signal_family_history_component(
            signal_family=None,
            family_history={},
        )
        self.assertEqual(result[1], ["no_signal_family"])

    def test_no_history_stats(self):
        """family_history에 signal_family 없음 -> no_history_stats."""
        result = _signal_family_history_component(
            signal_family="momentum",
            family_history={},
        )
        self.assertEqual(result[1], ["no_history_stats"])

    def test_unqualified_history(self):
        """qualified=False -> unqualified_history."""
        result = _signal_family_history_component(
            signal_family="momentum",
            family_history={"momentum": {"qualified": False, "win_rate": 0.5}},
        )
        self.assertEqual(result[1], ["unqualified_history"])

    def test_missing_quality_none(self):
        """quality None -> missing_quality."""
        result = _quality_component(None)
        self.assertEqual(result[1], ["missing_quality"])

    def test_missing_quality_invalid(self):
        """quality non-numeric -> missing_quality."""
        result = _quality_component("invalid")
        self.assertEqual(result[1], ["missing_quality"])

    def test_mapping_no_signal_family(self):
        self.assertEqual(REASON_DESCRIPTIONS.get("no_signal_family"), "패밀리없음")

    def test_mapping_no_history_stats(self):
        self.assertEqual(REASON_DESCRIPTIONS.get("no_history_stats"), "통계없음")

    def test_mapping_unqualified_history(self):
        self.assertEqual(REASON_DESCRIPTIONS.get("unqualified_history"), "통계부족")

    def test_mapping_missing_quality(self):
        self.assertEqual(REASON_DESCRIPTIONS.get("missing_quality"), "품질불명")

    def test_legacy_insufficient_data_kept(self):
        """legacy back-compat: insufficient_data mapping remains."""
        self.assertEqual(REASON_DESCRIPTIONS.get("insufficient_data"), "데이터부족")


if __name__ == "__main__":
    unittest.main()
