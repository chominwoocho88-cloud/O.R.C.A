import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


class Phase51OrcaMaxTokensTests(unittest.TestCase):
    """ORCA 4 agent max_tokens budget checks."""

    def test_hunter_max_tokens_increased(self):
        """orca.hunter call budget is at least 8000."""
        from apps.orca.pipeline.agents import _TOK

        self.assertGreaterEqual(_TOK["HUNTER"], 8000)

    def test_analyst_max_tokens_increased(self):
        """orca.analyst call budget is at least 5000."""
        from apps.orca.pipeline.agents import _TOK

        self.assertGreaterEqual(_TOK["ANALYST"], 5000)

    def test_devil_max_tokens_increased(self):
        """orca.devil call budget is at least 4000."""
        from apps.orca.pipeline.agents import _TOK

        self.assertGreaterEqual(_TOK["DEVIL"], 4000)

    def test_reporter_max_tokens_increased(self):
        """orca.reporter MORNING call budget is at least 9000."""
        from apps.orca.pipeline.agents import _TOK

        self.assertGreaterEqual(_TOK["REPORTER_FULL"], 9000)

    def test_reporter_lite_max_tokens_increased(self):
        """orca.reporter lite call budget is at least 4000."""
        from apps.orca.pipeline.agents import _TOK

        self.assertGreaterEqual(_TOK["REPORTER_LITE"], 4000)

    def test_jackal_devil_hotfix_unchanged(self):
        """JACKAL Devil/Analyst max_tokens hotfix remains intact."""
        content = Path("apps/jackal/scanner.py").read_text(encoding="utf-8")
        self.assertEqual(content.count("max_tokens=1000"), 2)

    def test_postprocess_jackal_news_budget_increased(self):
        """orca.postprocess JACKAL news collection uses at least 2000 tokens."""
        from orca import postprocess

        captured = {}

        def fake_call_api(*args, **kwargs):
            captured.update(kwargs)
            return '{"news_items": []}'

        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            watchlist = tmp / "jackal_watchlist.json"
            watchlist.write_text(
                '{"tickers":["NVDA"],"details":{"NVDA":{"name":"Nvidia"}}}',
                encoding="utf-8",
            )
            with patch("shared.paths.DATA_DIR", tmp), \
                patch.object(postprocess.console, "print"), \
                patch("apps.orca.pipeline.agents.call_api", side_effect=fake_call_api):
                postprocess.collect_jackal_news({"raw_signals": []})

        self.assertEqual(captured["max_tokens"], 2000)
        self.assertEqual(captured["call_site"], "orca.postprocess")


if __name__ == "__main__":
    unittest.main()
