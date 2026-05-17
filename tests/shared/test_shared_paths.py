import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class SharedPathsTests(unittest.TestCase):
    def test_import_repo_root(self):
        from shared.paths import REPO_ROOT
        self.assertIsInstance(REPO_ROOT, Path)
        self.assertTrue(REPO_ROOT.exists())

    def test_import_data_and_reports_dirs(self):
        from shared.paths import DATA_DIR, REPORTS_DIR
        self.assertIsInstance(DATA_DIR, Path)
        self.assertIsInstance(REPORTS_DIR, Path)
        self.assertTrue(DATA_DIR.is_dir())

    def test_import_legacy_dirs(self):
        from shared.paths import ORCA_LEGACY_DIR, JACKAL_LEGACY_DIR
        self.assertTrue(ORCA_LEGACY_DIR.is_dir())
        self.assertTrue(JACKAL_LEGACY_DIR.is_dir())

    def test_repo_root_is_correct(self):
        """REPO_ROOT가 실제 repo 루트를 가리키는지 확인 (특정 파일 존재로 검증)"""
        from shared.paths import REPO_ROOT
        self.assertTrue((REPO_ROOT / "orca").is_dir())
        self.assertTrue((REPO_ROOT / "jackal").is_dir())
        self.assertTrue((REPO_ROOT / "shared").is_dir())

    def test_data_dir_path(self):
        from shared.paths import REPO_ROOT, DATA_DIR
        self.assertEqual(DATA_DIR, REPO_ROOT / "data")

    def test_jackal_legacy_dir_path(self):
        from shared.paths import REPO_ROOT, JACKAL_LEGACY_DIR
        self.assertEqual(JACKAL_LEGACY_DIR, REPO_ROOT / "jackal")

    def test_orca_data_files(self):
        from shared.paths import (
            MEMORY_FILE, ACCURACY_FILE, BASELINE_FILE,
            STATE_DB_FILE, JACKAL_DB_FILE, DATA_DIR,
        )
        for path in [MEMORY_FILE, ACCURACY_FILE, BASELINE_FILE, STATE_DB_FILE, JACKAL_DB_FILE]:
            self.assertEqual(path.parent, DATA_DIR)

    def test_jackal_legacy_files(self):
        from shared.paths import (
            JACKAL_LEGACY_DIR,
            JACKAL_WEIGHTS_FILE, JACKAL_USAGE_LOG_FILE,
            JACKAL_HUNT_LOG_FILE, JACKAL_HUNT_COOLDOWN_FILE,
        )
        for path in [
            JACKAL_WEIGHTS_FILE,
            JACKAL_USAGE_LOG_FILE,
            JACKAL_HUNT_LOG_FILE,
            JACKAL_HUNT_COOLDOWN_FILE,
        ]:
            self.assertEqual(path.parent, JACKAL_LEGACY_DIR)

    def test_consistency_with_orca_paths(self):
        """shared.paths가 orca.paths와 동일한 경로를 가리켜야 함"""
        import shared.paths as sp
        import shared.paths as op

        self.assertEqual(sp.PACKAGE_DIR, op.PACKAGE_DIR)
        self.assertEqual(sp.DATA_DIR, op.DATA_DIR)
        self.assertEqual(sp.REPORTS_DIR, op.REPORTS_DIR)
        self.assertEqual(sp.MEMORY_FILE, op.MEMORY_FILE)
        self.assertEqual(sp.ACCURACY_FILE, op.ACCURACY_FILE)
        self.assertEqual(sp.SENTIMENT_FILE, op.SENTIMENT_FILE)
        self.assertEqual(sp.ROTATION_FILE, op.ROTATION_FILE)
        self.assertEqual(sp.WEIGHTS_FILE, op.WEIGHTS_FILE)
        self.assertEqual(sp.LESSONS_FILE, op.LESSONS_FILE)
        self.assertEqual(sp.COST_FILE, op.COST_FILE)
        self.assertEqual(sp.PATTERN_DB_FILE, op.PATTERN_DB_FILE)
        self.assertEqual(sp.STATE_DB_FILE, op.STATE_DB_FILE)
        self.assertEqual(sp.JACKAL_DB_FILE, op.JACKAL_DB_FILE)
        self.assertEqual(sp.BASELINE_FILE, op.BASELINE_FILE)
        self.assertEqual(sp.DATA_FILE, op.DATA_FILE)
        self.assertEqual(sp.BREAKING_FILE, op.BREAKING_FILE)
        self.assertEqual(sp.DASHBOARD_FILE, op.DASHBOARD_FILE)

    def test_env_override_takes_priority(self):
        """ORCA_REPO_ROOT 환경변수 설정 시 그것이 사용됨"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.dict(os.environ, {"ORCA_REPO_ROOT": tmp_dir}):
                from shared.paths import _resolve_repo_root
                resolved = _resolve_repo_root()
                self.assertEqual(resolved, Path(tmp_dir).resolve())

    def test_env_override_absent_uses_fallback(self):
        """ORCA_REPO_ROOT 없으면 __file__ 기반 fallback"""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ORCA_REPO_ROOT", None)
            from shared.paths import _resolve_repo_root
            import shared.paths
            resolved = _resolve_repo_root()
            shared_paths_file = Path(shared.paths.__file__).resolve()
            expected_from_shared = shared_paths_file.parents[1]
            self.assertEqual(resolved, expected_from_shared)

    def test_ensure_dirs_idempotent(self):
        """ensure_dirs가 여러 번 호출되어도 안전"""
        from shared.paths import ensure_dirs, DATA_DIR, REPORTS_DIR
        ensure_dirs()
        ensure_dirs()
        self.assertTrue(DATA_DIR.is_dir())
        self.assertTrue(REPORTS_DIR.is_dir())


if __name__ == "__main__":
    unittest.main()
