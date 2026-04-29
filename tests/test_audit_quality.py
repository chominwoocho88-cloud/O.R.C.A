import importlib
import unittest


class AuditQualityScriptTests(unittest.TestCase):
    def test_dry_run_builds_markdown_without_running_commands(self) -> None:
        audit_quality = importlib.import_module("scripts.audit_quality")

        audit = audit_quality.build_audit(dry_run=True)
        markdown = audit_quality.render_markdown(audit)

        self.assertTrue(audit["dry_run"])
        self.assertIn(audit["status"], {"pass", "warn", "fail"})
        self.assertTrue(all(item["status"] == "skipped" for item in audit["checks"]["commands"]))
        self.assertIn("jackal_projection_state", audit["metrics"])
        self.assertIn("jackal_shadow_state", audit["metrics"])
        self.assertIn("jackal_recommendation_accuracy", audit["metrics"])
        self.assertIn("market_provider_quality", audit["metrics"])
        self.assertIn("ORCA/JACKAL Quality Audit", markdown)


if __name__ == "__main__":
    unittest.main()
