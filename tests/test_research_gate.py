import unittest

from orca import research_gate


class ResearchGateSampleQualityTests(unittest.TestCase):
    def test_evaluate_report_warns_on_insufficient_samples_and_empty_projection(self) -> None:
        report = {
            "generated_at": "2026-04-29T00:00:00+09:00",
            "orca": {
                "summary": {"final_accuracy": 55.0, "judged_count": 10},
                "deltas": {"final_accuracy": 0.0},
                "latest": {"session_id": "orca"},
            },
            "jackal_backtest": {
                "summary": {"swing_accuracy": None, "d1_accuracy": None, "total_tracked": 0},
                "deltas": {"swing_accuracy": None, "d1_accuracy": None},
                "latest": None,
                "latest_raw_evaluation_issue": "total_tracked_zero",
                "using_latest_raw_as_representative": False,
            },
            "jackal_shadow": {
                "rolling_10": {"rate": 0.0, "batch_count": 0},
            },
            "jackal_accuracy_view": {
                "meta": {
                    "total_current_rows": 0,
                    "available_rows": {},
                },
            },
            "warnings": [],
        }

        gate = research_gate.evaluate_report(report)
        checks = {item["name"]: item for item in gate["checks"]}

        self.assertEqual(gate["status"], "warn")
        self.assertEqual(checks["orca_judged_count_minimum"]["reason"], "insufficient_sample")
        self.assertEqual(checks["jackal_total_tracked_minimum"]["reason"], "insufficient_sample")
        self.assertEqual(checks["jackal_shadow_rolling_10_batch_count"]["reason"], "insufficient_sample")
        self.assertEqual(checks["jackal_projection_rows_available"]["reason"], "insufficient_sample")
        self.assertEqual(checks["jackal_latest_raw_evaluable"]["reason"], "total_tracked_zero")


if __name__ == "__main__":
    unittest.main()
