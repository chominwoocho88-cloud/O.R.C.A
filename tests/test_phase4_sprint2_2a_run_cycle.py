import os
import unittest
from unittest.mock import patch


class Phase4Sprint22aTests(unittest.TestCase):
    def test_flag_default_false(self):
        with patch.dict(os.environ, {}, clear=True):
            from orca.run_cycle import is_phase4_self_correction_enabled

            self.assertFalse(is_phase4_self_correction_enabled())

    def test_flag_true(self):
        with patch.dict(os.environ, {"WAVE_F_PHASE4_SELF_CORRECTION": "true"}):
            from orca.run_cycle import is_phase4_self_correction_enabled

            self.assertTrue(is_phase4_self_correction_enabled())

    def test_flag_case_insensitive(self):
        from orca.run_cycle import is_phase4_self_correction_enabled

        for value in ["true", "TRUE", "True"]:
            with patch.dict(os.environ, {"WAVE_F_PHASE4_SELF_CORRECTION": value}):
                self.assertTrue(is_phase4_self_correction_enabled())

    def test_run_cycle_imports_detector(self):
        from orca.self_correction import detect_drift

        self.assertTrue(callable(detect_drift))

    def test_run_cycle_module_imports(self):
        from modules.orca.pipeline.run_cycle import run_orca_cycle

        self.assertTrue(callable(run_orca_cycle))

    def test_detector_failure_doesnt_break_cycle(self):
        from modules.orca.pipeline.run_cycle import _run_phase4_drift_check

        with patch("orca.self_correction.detect_drift", side_effect=RuntimeError("boom")):
            with patch("builtins.print") as mock_print:
                _run_phase4_drift_check({"history": []})

        printed = " ".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("drift detector failed", printed)


if __name__ == "__main__":
    unittest.main()
