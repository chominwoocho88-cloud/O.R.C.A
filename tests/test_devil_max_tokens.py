import os
import unittest
from pathlib import Path


def _llm_call_block(content: str, call_site: str) -> str:
    marker = f'call_site="{call_site}"'
    marker_pos = content.index(marker)
    start = content.rfind("_llm_client.call(", 0, marker_pos)
    end = content.find(")", marker_pos)
    return content[start:end]


class DevilMaxTokensTests(unittest.TestCase):
    def test_scanner_devil_analyst_max_tokens_increased(self):
        """Scanner Devil/Analyst calls no longer use the 400-token limit."""
        content = Path("jackal/scanner.py").read_text(encoding="utf-8")
        self.assertNotIn("max_tokens=400", content)
        self.assertEqual(content.count("max_tokens=1000"), 2)

    def test_hunter_stage4_max_tokens_increased(self):
        """Hunter Stage 4 calls have enough output budget for JSON parsing."""
        content = Path("jackal/hunter.py").read_text(encoding="utf-8")

        self.assertIn(
            "max_tokens=500,",
            _llm_call_block(content, "jackal.hunter.quick_scan"),
        )
        self.assertIn(
            "max_tokens=1500,",
            _llm_call_block(content, "jackal.hunter.analyst"),
        )
        self.assertIn(
            "max_tokens=1000,",
            _llm_call_block(content, "jackal.hunter.devil"),
        )

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
