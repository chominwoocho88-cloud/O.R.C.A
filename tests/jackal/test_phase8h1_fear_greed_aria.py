import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


class Phase8h1FearGreedAriaTests(unittest.TestCase):
    def test_scanner_context_loads_fear_greed_from_baseline_snapshot(self):
        from apps.jackal import scanner
        from apps.jackal.pipeline import adapter

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            baseline = tmp_path / "morning_baseline.json"
            memory = tmp_path / "memory.json"
            news = tmp_path / "jackal_news.json"
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
                patch.object(adapter, "ORCA_BASELINE", baseline),
                patch.object(adapter, "ORCA_MEMORY", memory),
                patch.object(adapter, "ORCA_SENTIMENT", sentiment),
                patch.object(adapter, "JACKAL_NEWS", news),
            ):
                ctx = scanner._load_orca_context()

        self.assertEqual(ctx["fear_greed"], "24")
        self.assertEqual(ctx["fear_greed_label"], "Extreme Fear")

    def test_scanner_context_falls_back_to_sentiment_fear_greed(self):
        from apps.jackal import scanner
        from apps.jackal.pipeline import adapter

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            baseline = tmp_path / "morning_baseline.json"
            memory = tmp_path / "memory.json"
            news = tmp_path / "jackal_news.json"
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
                patch.object(adapter, "ORCA_BASELINE", baseline),
                patch.object(adapter, "ORCA_MEMORY", memory),
                patch.object(adapter, "ORCA_SENTIMENT", sentiment),
                patch.object(adapter, "JACKAL_NEWS", news),
            ):
                ctx = scanner._load_orca_context()

        self.assertEqual(ctx["sentiment_score"], 61)
        self.assertEqual(ctx["fear_greed"], 37.0)

    def test_scanner_context_uses_adapter_baseline_schema_for_sector_flows(self):
        from apps.jackal import scanner
        from apps.jackal.pipeline import adapter

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            baseline = tmp_path / "morning_baseline.json"
            memory = tmp_path / "memory.json"
            news = tmp_path / "jackal_news.json"
            sentiment = tmp_path / "sentiment.json"
            rotation = tmp_path / "rotation.json"
            baseline.write_text(
                json.dumps(
                    {
                        "market_regime": "risk_on",
                        "trend_phase": "up",
                        "confidence": "high",
                        "inflows": [{"zone": "semis"}, {"zone": "software"}],
                        "outflows": [{"zone": "defensives"}],
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.object(scanner, "ORCA_BASELINE", baseline),
                patch.object(scanner, "ORCA_SENTIMENT", sentiment),
                patch.object(scanner, "ORCA_ROTATION", rotation),
                patch.object(adapter, "ORCA_BASELINE", baseline),
                patch.object(adapter, "ORCA_MEMORY", memory),
                patch.object(adapter, "JACKAL_NEWS", news),
            ):
                ctx = scanner._load_orca_context()

        self.assertEqual(ctx["regime"], "risk_on")
        self.assertEqual(ctx["regime_source"], "baseline")
        self.assertEqual(ctx["trend"], "up")
        self.assertEqual(ctx["confidence"], "high")
        self.assertEqual(ctx["key_inflows"], ["semis", "software"])
        self.assertEqual(ctx["key_outflows"], ["defensives"])

    def test_scanner_context_uses_adapter_memory_fallback(self):
        from apps.jackal import scanner
        from apps.jackal.pipeline import adapter

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            baseline = tmp_path / "morning_baseline.json"
            memory = tmp_path / "memory.json"
            news = tmp_path / "jackal_news.json"
            sentiment = tmp_path / "sentiment.json"
            rotation = tmp_path / "rotation.json"
            memory.write_text(
                json.dumps(
                    [
                        {
                            "analysis_date": "2026-05-18",
                            "market_regime": "memory_regime",
                            "inflows": [{"zone": "AI"}],
                            "outflows": [{"zone": "bonds"}],
                        }
                    ]
                ),
                encoding="utf-8",
            )

            with (
                patch.object(scanner, "ORCA_BASELINE", baseline),
                patch.object(scanner, "ORCA_SENTIMENT", sentiment),
                patch.object(scanner, "ORCA_ROTATION", rotation),
                patch.object(adapter, "ORCA_BASELINE", baseline),
                patch.object(adapter, "ORCA_MEMORY", memory),
                patch.object(adapter, "JACKAL_NEWS", news),
            ):
                ctx = scanner._load_orca_context()

        self.assertEqual(ctx["regime"], "memory_regime")
        self.assertEqual(ctx["regime_source"], "memory")
        self.assertEqual(ctx["key_inflows"], ["AI"])

    def test_scanner_context_preserves_rotation_overlay(self):
        from apps.jackal import scanner
        from apps.jackal.pipeline import adapter

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            baseline = tmp_path / "morning_baseline.json"
            memory = tmp_path / "memory.json"
            news = tmp_path / "jackal_news.json"
            sentiment = tmp_path / "sentiment.json"
            rotation = tmp_path / "rotation.json"
            baseline.write_text(json.dumps({"market_regime": "risk_on"}), encoding="utf-8")
            rotation.write_text(
                json.dumps(
                    {
                        "ranking": [["semis", 1.0], ["utilities", 0.1]],
                        "rotation_signal": {"from": "bonds", "to": "semis"},
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.object(scanner, "ORCA_BASELINE", baseline),
                patch.object(scanner, "ORCA_SENTIMENT", sentiment),
                patch.object(scanner, "ORCA_ROTATION", rotation),
                patch.object(adapter, "ORCA_BASELINE", baseline),
                patch.object(adapter, "ORCA_MEMORY", memory),
                patch.object(adapter, "JACKAL_NEWS", news),
            ):
                ctx = scanner._load_orca_context()

        self.assertEqual(ctx["top_sector"], "semis")
        self.assertEqual(ctx["bottom_sector"], "utilities")
        self.assertEqual(ctx["rotation_from"], "bonds")
        self.assertEqual(ctx["rotation_to"], "semis")

    def test_scanner_scan_log_records_orca_regime_source(self):
        from apps.jackal import scanner

        with (
            patch.object(scanner, "_load_weights", return_value={}),
            patch.object(scanner, "select_scanner_swing_info", return_value={}),
            patch.object(scanner, "build_scanner_reason_payload", return_value=("reason", [])),
        ):
            entry = scanner._build_scan_log_entry(
                now_kst=datetime(2026, 5, 19, tzinfo=timezone.utc),
                ticker="AAPL",
                market="US",
                info={"name": "Apple"},
                tech={"price": 100.0, "rsi": 45, "bb_pos": 50, "vol_ratio": 1.1},
                macro={"fred": {"vix": 18, "hy_spread": 3.2, "yield_curve": 0.1}},
                aria={
                    "regime": "risk_on",
                    "regime_source": "baseline",
                    "sentiment_score": 61,
                    "trend": "up",
                },
                quality={"signal_family": "rsi", "quality_score": 70, "quality_label": "ok", "reasons": []},
                analyst={"analyst_score": 72, "confidence": "high", "signals_fired": ["rsi"], "bull_case": "case"},
                devil={"devil_score": 20, "verdict": "ok", "devil_parse_ok": True},
                final={"final_score": 75, "signal_type": "watch", "is_entry": True, "reason": "reason"},
                canonical_signal_family="rsi",
            )

        self.assertEqual(entry["orca_regime_source"], "baseline")

    def test_adapter_context_loads_fear_greed_from_baseline_snapshot(self):
        from apps.jackal.pipeline import adapter

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
        from apps.jackal.pipeline import adapter

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
