import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class Phase8h1FearGreedAriaTests(unittest.TestCase):
    def test_scanner_context_loads_fear_greed_from_baseline_snapshot(self):
        from jackal import scanner

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            baseline = tmp_path / "morning_baseline.json"
            sentiment = tmp_path / "sentiment.json"
            rotation = tmp_path / "rotation.json"
            baseline.write_text(
                json.dumps(
                    {
                        "market_regime": "risk_on",
                        "trend_phase": "up",
                        "market_snapshot": {
                            "fear_greed_value": "24",
                            "fear_greed_rating": "Extreme Fear",
                        },
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.object(scanner, "ORCA_BASELINE", baseline),
                patch.object(scanner, "ORCA_SENTIMENT", sentiment),
                patch.object(scanner, "ORCA_ROTATION", rotation),
            ):
                ctx = scanner._load_orca_context()

        self.assertEqual(ctx["fear_greed"], "24")
        self.assertEqual(ctx["fear_greed_label"], "Extreme Fear")

    def test_scanner_context_falls_back_to_sentiment_fear_greed(self):
        from jackal import scanner

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            baseline = tmp_path / "morning_baseline.json"
            sentiment = tmp_path / "sentiment.json"
            rotation = tmp_path / "rotation.json"
            baseline.write_text(json.dumps({"market_regime": "mixed"}), encoding="utf-8")
            sentiment.write_text(
                json.dumps({"current": {"score": 61, "level": "Greed", "fear_greed": 37.0}}),
                encoding="utf-8",
            )

            with (
                patch.object(scanner, "ORCA_BASELINE", baseline),
                patch.object(scanner, "ORCA_SENTIMENT", sentiment),
                patch.object(scanner, "ORCA_ROTATION", rotation),
            ):
                ctx = scanner._load_orca_context()

        self.assertEqual(ctx["sentiment_score"], 61)
        self.assertEqual(ctx["fear_greed"], 37.0)

    def test_adapter_context_loads_fear_greed_from_baseline_snapshot(self):
        from modules.jackal.pipeline import adapter

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            baseline = tmp_path / "morning_baseline.json"
            memory = tmp_path / "memory.json"
            news = tmp_path / "jackal_news.json"
            baseline.write_text(
                json.dumps(
                    {
                        "market_regime": "risk_off",
                        "market_snapshot": {
                            "fear_greed_value": "72",
                            "fear_greed_rating": "Greed",
                        },
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.object(adapter, "ORCA_BASELINE", baseline),
                patch.object(adapter, "ORCA_MEMORY", memory),
                patch.object(adapter, "JACKAL_NEWS", news),
            ):
                ctx = adapter.load_orca_context()

        self.assertEqual(ctx["fear_greed"], "72")
        self.assertEqual(ctx["fear_greed_label"], "Greed")

    def test_adapter_context_falls_back_to_sentiment_fear_greed(self):
        from modules.jackal.pipeline import adapter

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            baseline = tmp_path / "morning_baseline.json"
            memory = tmp_path / "memory.json"
            sentiment = tmp_path / "sentiment.json"
            news = tmp_path / "jackal_news.json"
            sentiment.write_text(
                json.dumps({"current": {"fear_greed": 68.0}}),
                encoding="utf-8",
            )

            with (
                patch.object(adapter, "ORCA_BASELINE", baseline),
                patch.object(adapter, "ORCA_MEMORY", memory),
                patch.object(adapter, "ORCA_SENTIMENT", sentiment),
                patch.object(adapter, "JACKAL_NEWS", news),
            ):
                ctx = adapter.load_orca_context()

        self.assertEqual(ctx["fear_greed"], 68.0)


if __name__ == "__main__":
    unittest.main()
