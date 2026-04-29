import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import check_requirements_drift


class RequirementsDriftTests(unittest.TestCase):
    def test_collect_requirements_drift_warns_on_pin_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            req = Path(tmpdir) / "requirements.txt"
            req.write_text("examplepkg==1.0.0\nloosepkg\n", encoding="utf-8")

            def fake_version(name: str) -> str:
                if name == "examplepkg":
                    return "2.0.0"
                if name == "loosepkg":
                    return "0.1.0"
                raise check_requirements_drift.metadata.PackageNotFoundError(name)

            with patch.object(check_requirements_drift.metadata, "version", side_effect=fake_version):
                report = check_requirements_drift.collect_requirements_drift(req)

        self.assertEqual(report["status"], "warn")
        self.assertEqual(report["drift_count"], 1)
        self.assertEqual(report["missing_count"], 0)
        self.assertEqual(report["items"][0]["reason"], "version_drift")


if __name__ == "__main__":
    unittest.main()
