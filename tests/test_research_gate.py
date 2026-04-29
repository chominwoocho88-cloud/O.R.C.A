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
                    "total_projection_rows": 0,
                    "max_sample_count": 0,
                    "available_rows": {},
                    "missing_reasons": ["missing_projection_rows", "missing_accuracy_current"],
                },
            },
            "jackal_recommendation_accuracy": {"projection_rows": 0},
            "market_provider_quality": {"latest_backtest": {"failure_rate": 0.0, "fetch_stats": {"total": 8}}},
            "warnings": [],
        }

        gate = research_gate.evaluate_report(report)
        checks = {item["name"]: item for item in gate["checks"]}

        self.assertEqual(gate["status"], "warn")
        self.assertEqual(checks["orca_judged_count_minimum"]["reason"], "insufficient_sample")
        self.assertEqual(checks["jackal_total_tracked_minimum"]["reason"], "insufficient_sample")
        self.assertEqual(checks["jackal_shadow_rolling_10_batch_count"]["reason"], "insufficient_sample")
        self.assertEqual(checks["jackal_projection_rows_available"]["reason"], "missing_projection_rows")
        self.assertEqual(checks["jackal_accuracy_current_rows_available"]["reason"], "missing_accuracy_current")
        self.assertEqual(checks["jackal_projection_sample_count_minimum"]["reason"], "insufficient_sample")
        self.assertEqual(checks["jackal_recommendation_projection_rows_available"]["reason"], "missing_recommendation_samples")
        self.assertEqual(checks["jackal_latest_raw_evaluable"]["reason"], "total_tracked_zero")

    def test_evaluate_report_checks_projection_sample_count(self) -> None:
        report = {
            "generated_at": "2026-04-29T00:00:00+09:00",
            "orca": {
                "summary": {"final_accuracy": 55.0, "judged_count": 120},
                "deltas": {"final_accuracy": 0.0},
                "latest": {"session_id": "orca"},
            },
            "jackal_backtest": {
                "summary": {"swing_accuracy": 70.0, "d1_accuracy": 47.0, "total_tracked": 120},
                "deltas": {"swing_accuracy": 0.0, "d1_accuracy": 0.0},
                "latest": {"session_id": "jackal", "summary": {}},
                "linked_to_latest_orca": True,
                "latest_evaluable_age_hours": 12,
            },
            "jackal_shadow": {
                "rolling_10": {"rate": 50.0, "batch_count": 10},
            },
            "jackal_accuracy_view": {
                "meta": {
                    "total_current_rows": 2,
                    "total_projection_rows": 2,
                    "max_sample_count": 120,
                    "missing_reasons": [],
                },
            },
            "jackal_recommendation_accuracy": {"projection_rows": 1},
            "market_provider_quality": {"latest_backtest": {"failure_rate": 0.0, "fetch_stats": {"total": 8}}},
            "warnings": [],
        }

        gate = research_gate.evaluate_report(report)
        checks = {item["name"]: item for item in gate["checks"]}

        self.assertEqual(checks["jackal_projection_rows_available"]["status"], "pass")
        self.assertEqual(checks["jackal_accuracy_current_rows_available"]["status"], "pass")
        self.assertEqual(checks["jackal_projection_sample_count_minimum"]["status"], "pass")
        self.assertEqual(checks["jackal_recommendation_projection_rows_available"]["status"], "pass")
        self.assertEqual(checks["market_provider_failure_rate"]["status"], "pass")

    def test_latest_raw_incremental_noop_is_not_a_gate_warning(self) -> None:
        report = {
            "generated_at": "2026-04-29T00:00:00+09:00",
            "orca": {"summary": {"final_accuracy": 55.0, "judged_count": 120}, "deltas": {"final_accuracy": 0.0}, "latest": {"session_id": "orca"}},
            "jackal_backtest": {
                "summary": {"swing_accuracy": 70.0, "d1_accuracy": 47.0, "total_tracked": 120},
                "deltas": {"swing_accuracy": 0.0, "d1_accuracy": 0.0},
                "latest": {"session_id": "jackal"},
                "linked_to_latest_orca": True,
                "latest_evaluable_age_hours": 12,
                "latest_raw_evaluation_issue": "total_tracked_zero",
                "latest_raw_issue_classification": {"severity": "info", "reason": "incremental_no_new_data"},
                "using_latest_raw_as_representative": False,
            },
            "jackal_shadow": {"rolling_10": {"rate": 50.0, "batch_count": 10}},
            "jackal_accuracy_view": {"meta": {"total_current_rows": 1, "total_projection_rows": 1, "max_sample_count": 120, "missing_reasons": []}},
            "jackal_recommendation_accuracy": {"projection_rows": 1},
            "market_provider_quality": {"latest_backtest": {"failure_rate": 0.0, "fetch_stats": {"total": 8}}},
            "warnings": [],
        }

        gate = research_gate.evaluate_report(report)
        raw_check = {item["name"]: item for item in gate["checks"]}["jackal_latest_raw_evaluable"]

        self.assertEqual(raw_check["status"], "pass")
        self.assertEqual(raw_check["reason"], "incremental_no_new_data")

    def test_recommendation_projection_reason_distinguishes_missing_outcomes(self) -> None:
        report = {
            "generated_at": "2026-04-29T00:00:00+09:00",
            "orca": {"summary": {"final_accuracy": 55.0, "judged_count": 120}, "deltas": {"final_accuracy": 0.0}, "latest": {"session_id": "orca"}},
            "jackal_backtest": {
                "summary": {"swing_accuracy": 70.0, "d1_accuracy": 47.0, "total_tracked": 120},
                "deltas": {"swing_accuracy": 0.0, "d1_accuracy": 0.0},
                "latest": {"session_id": "jackal"},
                "linked_to_latest_orca": True,
                "latest_evaluable_age_hours": 12,
            },
            "jackal_shadow": {"rolling_10": {"rate": 50.0, "batch_count": 10}},
            "jackal_accuracy_view": {"meta": {"total_current_rows": 1, "total_projection_rows": 1, "max_sample_count": 120, "missing_reasons": []}},
            "jackal_recommendation_accuracy": {
                "recommendation_rows": 1,
                "checked_rows": 0,
                "projection_rows": 0,
                "current_rows": 0,
                "missing_reasons": [
                    "missing_recommendation_outcomes",
                    "missing_recommendation_projection_rows",
                    "missing_recommendation_current_rows",
                ],
            },
            "market_provider_quality": {"latest_backtest": {"failure_rate": 0.0, "fetch_stats": {"total": 8}}},
            "warnings": [],
        }

        gate = research_gate.evaluate_report(report)
        checks = {item["name"]: item for item in gate["checks"]}

        self.assertEqual(checks["jackal_recommendation_projection_rows_available"]["reason"], "missing_recommendation_outcomes")
        self.assertEqual(
            checks["jackal_recommendation_state_missing_recommendation_current_rows"]["reason"],
            "missing_recommendation_current_rows",
        )


if __name__ == "__main__":
    unittest.main()
