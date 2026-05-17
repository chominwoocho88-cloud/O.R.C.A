import os
import unittest
from pathlib import Path


class PhaseB4JackalPathsTests(unittest.TestCase):
    def test_evolution_imports(self):
        """jackal.evolution import"""
        import apps.jackal.evolution

        self.assertTrue(hasattr(apps.jackal.evolution, "__name__"))

    def test_tracker_imports(self):
        """jackal.tracker import"""
        import apps.jackal.tracker

        self.assertTrue(hasattr(apps.jackal.tracker, "__name__"))

    def test_scanner_imports(self):
        """apps.jackal.scanner import"""
        import apps.jackal.scanner

        self.assertTrue(hasattr(apps.jackal.scanner, "__name__"))

    def test_hunter_imports(self):
        """apps.jackal.hunter import"""
        import apps.jackal.hunter

        self.assertTrue(hasattr(apps.jackal.hunter, "__name__"))

    def test_no_path_file_in_4_files(self):
        """4 files no longer use the Path(__file__) migration blocker."""
        files = [
            "apps/jackal/evolution.py",
            "apps/jackal/tracker.py",
            "apps/jackal/scanner.py",
            "apps/jackal/hunter.py",
        ]
        for file_path in files:
            content = Path(file_path).read_text(encoding="utf-8")
            self.assertNotIn(
                "Path(__file__)",
                content,
                f"{file_path} still uses Path(__file__)",
            )

    def test_b35b_build_info_intact(self):
        """Phase B-3.5b build_info behavior remains intact."""
        os.environ["GITHUB_SHA"] = "abc1234567890"
        from apps.jackal.scanner import _append_build_info

        result = _append_build_info("test")
        self.assertIn("build:", result)


if __name__ == "__main__":
    unittest.main()
