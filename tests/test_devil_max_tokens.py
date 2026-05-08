import os
import unittest
from pathlib import Path


class DevilMaxTokensTests(unittest.TestCase):
    def test_scanner_devil_analyst_max_tokens_increased(self):
        """Scanner Devil/Analyst calls no longer use the 400-token limit."""
        content = Path("jackal/scanner.py").read_text(encoding="utf-8")
        self.assertNotIn("max_tokens=400", content)
        self.assertEqual(content.count("max_tokens=1000"), 2)

    def test_scanner_imports_unchanged(self):
        """jackal.scanner still imports normally."""
        import jackal.scanner

        self.assertTrue(hasattr(jackal.scanner, "__name__"))

    def test_b35b_build_info_intact(self):
        """Phase B-3.5b build footer behavior remains intact."""
        os.environ["GITHUB_SHA"] = "abc1234567890"
        from jackal.scanner import _append_build_info

        result = _append_build_info("test")
        self.assertIn("build:", result)


if __name__ == "__main__":
    unittest.main()
