import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class BaselineFallbackAuditTests(unittest.TestCase):
    def test_record_baseline_fallback_skips_baseline_source(self):
        from apps.jackal.baseline_audit import record_baseline_fallback

        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "baseline_fallback_audit.log"
            record_baseline_fallback(
                component="scanner",
                regime_source="baseline",
                regime="risk_on",
                baseline_exists=True,
                memory_exists=True,
                audit_log_path=audit_path,
            )

        self.assertFalse(audit_path.exists())

    def test_record_baseline_fallback_appends_memory_entry(self):
        from apps.jackal.baseline_audit import record_baseline_fallback

        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "baseline_fallback_audit.log"
            record_baseline_fallback(
                component="scanner",
                regime_source="memory",
                regime="memory_regime",
                baseline_exists=False,
                memory_exists=True,
                extra={"ticker": "AAPL"},
                audit_log_path=audit_path,
            )
            entry = json.loads(audit_path.read_text(encoding="utf-8").strip())

        self.assertEqual(entry["component"], "scanner")
        self.assertEqual(entry["regime_source"], "memory")
        self.assertEqual(entry["regime"], "memory_regime")
        self.assertFalse(entry["baseline_exists"])
        self.assertTrue(entry["memory_exists"])
        self.assertEqual(entry["extra"], {"ticker": "AAPL"})
        self.assertIn("+09:00", entry["ts"])

    def test_record_baseline_fallback_appends_fallback_and_none_entries(self):
        from apps.jackal.baseline_audit import record_baseline_fallback

        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "baseline_fallback_audit.log"
            for source in ("fallback", "none"):
                record_baseline_fallback(
                    component="hunter",
                    regime_source=source,
                    regime="mixed",
                    baseline_exists=False,
                    memory_exists=False,
                    audit_log_path=audit_path,
                )
            rows = [
                json.loads(line)
                for line in audit_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual([row["regime_source"] for row in rows], ["fallback", "none"])

    def test_record_baseline_fallback_is_fail_safe(self):
        from apps.jackal.baseline_audit import record_baseline_fallback

        with tempfile.TemporaryDirectory() as tmp:
            blocked_parent = Path(tmp) / "not_a_dir"
            blocked_parent.write_text("file blocks mkdir", encoding="utf-8")
            audit_path = blocked_parent / "baseline_fallback_audit.log"
            record_baseline_fallback(
                component="scanner",
                regime_source="memory",
                regime="memory_regime",
                baseline_exists=False,
                memory_exists=True,
                audit_log_path=audit_path,
            )

    def test_scanner_records_non_baseline_context(self):
        from apps.jackal import scanner

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            baseline = tmp_path / "morning_baseline.json"
            memory = tmp_path / "memory.json"
            memory.write_text("[]", encoding="utf-8")
            with (
                patch.object(scanner, "BASELINE_FILE", baseline),
                patch.object(scanner, "MEMORY_FILE", memory),
                patch.object(scanner, "ORCA_BASELINE", baseline),
                patch.object(scanner, "ORCA_SENTIMENT", tmp_path / "sentiment.json"),
                patch.object(scanner, "ORCA_ROTATION", tmp_path / "rotation.json"),
                patch.object(
                    scanner,
                    "load_shared_orca_context",
                    return_value={"regime": "memory_regime", "regime_source": "memory"},
                ),
                patch.object(scanner, "record_baseline_fallback") as record,
            ):
                scanner._load_orca_context()

        record.assert_called_once_with(
            component="scanner",
            regime_source="memory",
            regime="memory_regime",
            baseline_exists=False,
            memory_exists=True,
        )

    def test_scanner_skips_baseline_context_audit(self):
        from apps.jackal import scanner

        with (
            patch.object(
                scanner,
                "load_shared_orca_context",
                return_value={"regime": "risk_on", "regime_source": "baseline"},
            ),
            patch.object(scanner, "record_baseline_fallback") as record,
        ):
            scanner._load_orca_context()

        record.assert_not_called()

    def test_hunter_records_non_baseline_context_before_regime_gate(self):
        from apps.jackal import hunter

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            baseline = tmp_path / "morning_baseline.json"
            memory = tmp_path / "memory.json"
            memory.write_text("[]", encoding="utf-8")
            with (
                patch.object(hunter, "BASELINE_FILE", baseline),
                patch.object(hunter, "MEMORY_FILE", memory),
                patch.object(hunter, "_orca_baseline_exists", return_value=False),
                patch.object(hunter, "_load_orca_context", return_value={"regime": "", "regime_source": "none"}),
                patch.object(hunter, "_send_status", return_value=None),
                patch.object(hunter, "record_baseline_fallback") as record,
            ):
                result = hunter.run_hunt()

        self.assertEqual(result, {"hunted": 0, "alerted": 0})
        record.assert_called_once_with(
            component="hunter",
            regime_source="none",
            regime="",
            baseline_exists=False,
            memory_exists=True,
        )


if __name__ == "__main__":
    unittest.main()
