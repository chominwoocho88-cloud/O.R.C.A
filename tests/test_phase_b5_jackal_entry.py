import os
import unittest
from pathlib import Path


class PhaseB5JackalEntryTests(unittest.TestCase):
    def test_core_imports(self):
        """jackal.core import, including the workflow entrypoint module."""
        import jackal.core

        self.assertTrue(hasattr(jackal.core, "__name__"))

    def test_backtest_imports(self):
        """jackal.backtest import."""
        import jackal.backtest

        self.assertTrue(hasattr(jackal.backtest, "__name__"))

    def test_no_path_file_in_2_files(self):
        """core.py and backtest.py no longer use Path(__file__)."""
        files = ["jackal/core.py", "jackal/backtest.py"]
        for file_path in files:
            content = Path(file_path).read_text(encoding="utf-8")
            self.assertNotIn(
                "Path(__file__)",
                content,
                f"{file_path} still uses Path(__file__)",
            )

    def test_phase_b3_b4_intact(self):
        """Phase B-3 and B-4 JACKAL modules still import."""
        from jackal import adapter, shield, compact, evolution, tracker, scanner, hunter

        self.assertTrue(adapter and shield and compact and evolution and tracker and scanner and hunter)

    def test_b35b_build_info_intact(self):
        """Phase B-3.5b build footer behavior remains intact."""
        os.environ["GITHUB_SHA"] = "abc1234567890"
        from jackal.scanner import _append_build_info

        result = _append_build_info("test")
        self.assertIn("build:", result)

    def test_jackal_module_imports_all(self):
        """All JACKAL modules touched during Phase B import together."""
        from jackal import (
            core,
            backtest,
            adapter,
            shield,
            compact,
            evolution,
            tracker,
            scanner,
            hunter,
        )

        self.assertTrue(core and backtest and adapter and shield and compact)
        self.assertTrue(evolution and tracker and scanner and hunter)


if __name__ == "__main__":
    unittest.main()
