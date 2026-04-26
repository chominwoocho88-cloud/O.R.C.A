from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jackal import probability
from orca import state


class ProbabilityStateIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.state_db = Path(self.tmpdir) / "orca_state.db"
        self.jackal_db = Path(self.tmpdir) / "jackal_state.db"
        self.patchers = [
            patch.object(state, "STATE_DB_FILE", self.state_db),
            patch.object(state, "JACKAL_DB_FILE", self.jackal_db),
        ]
        for patcher in self.patchers:
            patcher.start()
        state.init_state_db()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _record_candidate_with_lesson(
        self,
        *,
        analysis_date: str,
        ticker: str,
        source_event_type: str,
        lesson_type: str,
        lesson_value: float,
        signals_fired: list[str],
    ) -> str:
        candidate_id = state.record_candidate(
            {
                "ticker": ticker,
                "analysis_date": analysis_date,
                "timestamp": f"{analysis_date}T09:00:00+09:00",
                "alerted": True,
                "is_entry": True,
                "signal_family": "general",
                "signals_fired": signals_fired,
                "quality_score": 70.0,
                "price_at_scan": 100.0,
            },
            source_system="jackal",
            source_event_type=source_event_type,
            source_external_key=f"{source_event_type}:{analysis_date}:{ticker}",
        )
        state.record_candidate_lesson(
            candidate_id,
            lesson_type=lesson_type,
            label=lesson_type,
            lesson_value=lesson_value,
            lesson={"origin": source_event_type},
            auto_context_snapshot=False,
        )
        return candidate_id

    def test_summarize_candidate_probabilities_filters_backtest_origin(self):
        self._record_candidate_with_lesson(
            analysis_date="2026-04-01",
            ticker="NVDA",
            source_event_type="backtest",
            lesson_type="backtest_win",
            lesson_value=4.5,
            signals_fired=["rsi_oversold"],
        )
        self._record_candidate_with_lesson(
            analysis_date="2026-04-01",
            ticker="AAPL",
            source_event_type="live",
            lesson_type="aligned_win",
            lesson_value=2.0,
            signals_fired=["sector_rebound"],
        )

        summary = state.summarize_candidate_probabilities(days=400, source_event_types=("backtest",))

        self.assertEqual(summary["raw_rows"], 1)
        self.assertEqual(summary["overall"]["total"], 1)
        self.assertEqual(summary["source_event_types"], ["backtest"])

    def test_summarize_candidate_probabilities_keeps_live_rows_when_unfiltered(self):
        self._record_candidate_with_lesson(
            analysis_date="2026-04-01",
            ticker="NVDA",
            source_event_type="backtest",
            lesson_type="backtest_win",
            lesson_value=4.5,
            signals_fired=["rsi_oversold"],
        )
        self._record_candidate_with_lesson(
            analysis_date="2026-04-02",
            ticker="AAPL",
            source_event_type="live",
            lesson_type="aligned_loss",
            lesson_value=-1.0,
            signals_fired=["sector_rebound"],
        )

        summary = state.summarize_candidate_probabilities(days=400)

        self.assertEqual(summary["raw_rows"], 2)
        self.assertEqual(summary["overall"]["total"], 2)

    def test_summarize_candidate_probabilities_uses_analysis_date_window(self):
        candidate_id = self._record_candidate_with_lesson(
            analysis_date="2025-01-01",
            ticker="OLD1",
            source_event_type="backtest",
            lesson_type="backtest_win",
            lesson_value=3.0,
            signals_fired=["rsi_oversold"],
        )
        with state._connect_orca() as conn:
            conn.execute(
                "UPDATE candidate_lessons SET lesson_timestamp = ? WHERE candidate_id = ?",
                ("2026-04-23T09:00:00+09:00", candidate_id),
            )

        summary = state.summarize_candidate_probabilities(days=30, source_event_types=("backtest",))

        self.assertEqual(summary["raw_rows"], 0)
        self.assertEqual(summary["overall"]["total"], 0)

    def test_summarize_candidate_probabilities_dedupes_duplicate_lessons(self):
        candidate_id = self._record_candidate_with_lesson(
            analysis_date="2026-04-01",
            ticker="NVDA",
            source_event_type="backtest",
            lesson_type="backtest_win",
            lesson_value=4.5,
            signals_fired=["rsi_oversold"],
        )
        state.record_candidate_lesson(
            candidate_id,
            lesson_type="backtest_win",
            label="duplicate",
            lesson_value=4.5,
            lesson={"origin": "backtest"},
            auto_context_snapshot=False,
        )

        summary = state.summarize_candidate_probabilities(days=400, source_event_types=("backtest",))

        self.assertEqual(summary["raw_rows"], 2)
        self.assertEqual(summary["deduped_rows"], 1)
        self.assertEqual(summary["overall"]["total"], 1)

    def test_backtest_family_summary_is_qualified_after_threshold(self):
        for idx in range(5):
            self._record_candidate_with_lesson(
                analysis_date=f"2026-04-0{idx + 1}",
                ticker=f"NVDA{idx}",
                source_event_type="backtest",
                lesson_type="backtest_win",
                lesson_value=2.0 + idx,
                signals_fired=["rsi_oversold"],
            )

        summary = state.summarize_candidate_probabilities(days=400, source_event_types=("backtest",))
        family = summary["by_signal_family"]["oversold_rebound"]

        self.assertTrue(family["qualified"])
        self.assertEqual(family["total"], 5)


class ProbabilityHelperTests(unittest.TestCase):
    def test_load_probability_summary_defaults_to_backtest_only(self):
        with patch.object(probability, "summarize_candidate_probabilities", return_value={"ok": True}) as mocked:
            summary = probability.load_probability_summary()

        self.assertEqual(summary, {"ok": True})
        mocked.assert_called_once_with(
            days=probability.BACKTEST_PROBABILITY_WINDOW_DAYS,
            min_samples=5,
            source_event_types=probability.BACKTEST_PROBABILITY_SOURCE_EVENT_TYPES,
        )

    def test_load_probability_summary_can_override_source_filter(self):
        with patch.object(probability, "summarize_candidate_probabilities", return_value={"ok": True}) as mocked:
            probability.load_probability_summary(days=120, source_event_types=("live",))

        mocked.assert_called_once_with(days=120, min_samples=5, source_event_types=("live",))

    def test_apply_probability_adjustment_uses_qualified_backtest_sample(self):
        final = {"final_score": 70.0, "verdict": "부분동의", "mode": "standard"}
        lesson_summary = {
            "by_signal_family": {
                "oversold_rebound": {
                    "qualified": True,
                    "wins": 6,
                    "total": 8,
                    "win_rate": 75.0,
                    "effective_win_rate": 70.0,
                }
            }
        }

        updated = probability.apply_probability_adjustment(
            final,
            "oversold_rebound",
            lesson_summary,
            entry_threshold=72.0,
        )

        self.assertGreater(updated["probability_adjustment"], 0)
        self.assertEqual(updated["probability_samples"], 8)
        self.assertTrue(updated["is_entry"])

    def test_apply_probability_adjustment_handles_negative_signal_history(self):
        final = {"final_score": 74.0, "verdict": "부분동의", "mode": "standard"}
        lesson_summary = {
            "by_signal_family": {
                "rotation": {
                    "qualified": True,
                    "wins": 2,
                    "total": 8,
                    "win_rate": 25.0,
                    "effective_win_rate": 41.7,
                }
            }
        }

        updated = probability.apply_probability_adjustment(
            final,
            "rotation",
            lesson_summary,
            entry_threshold=72.0,
        )

        self.assertLess(updated["probability_adjustment"], 0)
        self.assertFalse(updated["is_entry"])

    def test_apply_probability_adjustment_skips_unqualified_family(self):
        final = {"final_score": 70.0, "verdict": "부분동의", "mode": "standard"}
        lesson_summary = {
            "by_signal_family": {
                "rotation": {
                    "qualified": False,
                    "wins": 2,
                    "total": 4,
                    "win_rate": 50.0,
                    "effective_win_rate": 50.0,
                }
            }
        }

        updated = probability.apply_probability_adjustment(
            final,
            "rotation",
            lesson_summary,
            entry_threshold=72.0,
        )

        self.assertEqual(updated["probability_adjustment"], 0.0)
        self.assertEqual(updated["probability_samples"], 0)


if __name__ == "__main__":
    unittest.main()
