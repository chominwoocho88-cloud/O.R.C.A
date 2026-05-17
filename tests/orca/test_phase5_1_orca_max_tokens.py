import unittest
from pathlib import Path


class Phase51OrcaMaxTokensTests(unittest.TestCase):
    """ORCA 4 agent max_tokens budget checks."""

    def test_hunter_max_tokens_increased(self):
        """orca.hunter call budget is at least 4000."""
        from apps.orca.pipeline.agents import _TOK

        self.assertGreaterEqual(_TOK["HUNTER"], 4000)

    def test_analyst_max_tokens_increased(self):
        """orca.analyst call budget is at least 2500."""
        from apps.orca.pipeline.agents import _TOK

        self.assertGreaterEqual(_TOK["ANALYST"], 2500)

    def test_devil_max_tokens_increased(self):
        """orca.devil call budget is at least 2500."""
        from apps.orca.pipeline.agents import _TOK

        self.assertGreaterEqual(_TOK["DEVIL"], 2500)

    def test_reporter_max_tokens_increased(self):
        """orca.reporter MORNING call budget is at least 4500."""
        from apps.orca.pipeline.agents import _TOK

        self.assertGreaterEqual(_TOK["REPORTER_FULL"], 4500)

    def test_jackal_devil_hotfix_unchanged(self):
        """JACKAL Devil/Analyst max_tokens hotfix remains intact."""
        content = Path("apps/jackal/scanner.py").read_text(encoding="utf-8")
        self.assertEqual(content.count("max_tokens=1000"), 2)


if __name__ == "__main__":
    unittest.main()
