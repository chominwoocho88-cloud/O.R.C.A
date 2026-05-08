import os
import unittest
from pathlib import Path


class PhaseB4JackalPathsTests(unittest.TestCase):
    def test_evolution_imports(self):
        """jackal.evolution import"""
        import jackal.evolution

        self.assertTrue(hasattr(jackal.evolution, "__name__"))

    def test_tracker_imports(self):
        """jackal.tracker import"""
        import jackal.tracker

        self.assertTrue(hasattr(jackal.tracker, "__name__"))

    def test_scanner_imports(self):
        """jackal.scanner import"""
        import jackal.scanner

        self.assertTrue(hasattr(jackal.scanner, "__name__"))

    def test_hunter_imports(self):
        """jackal.hunter import"""
        import jackal.hunter

        self.assertTrue(hasattr(jackal.hunter, "__name__"))

    def test_no_path_file_in_4_files(self):
        """4 files no longer use the Path(__file__) migration blocker."""
        files = [
            "jackal/evolution.py",
            "jackal/tracker.py",
            "jackal/scanner.py",
            "jackal/hunter.py",
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
        from jackal.scanner import _append_build_info

        result = _append_build_info("test")
        self.assertIn("build:", result)


if __name__ == "__main__":
    unittest.main()
