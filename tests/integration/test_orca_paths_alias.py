import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class OrcaPathsAliasTests(unittest.TestCase):
    def test_orca_paths_data_dir_imports(self):
        """orca.paths.DATA_DIR 여전히 import 가능"""
        from shared.paths import DATA_DIR
        self.assertIsInstance(DATA_DIR, Path)

    def test_orca_paths_package_dir_imports(self):
        """orca.paths.PACKAGE_DIR (ORCA 전용) 여전히 작동"""
        from shared.paths import PACKAGE_DIR
        self.assertIsInstance(PACKAGE_DIR, Path)

    def test_alias_data_dir_is_same(self):
        """orca.paths.DATA_DIR is shared.paths.DATA_DIR (같은 객체)"""
        from shared.paths import DATA_DIR as A
        from shared.paths import DATA_DIR as B
        self.assertIs(A, B)

    def test_alias_memory_file_is_same(self):
        from shared.paths import MEMORY_FILE as A
        from shared.paths import MEMORY_FILE as B
        self.assertIs(A, B)

    def test_alias_state_db_file_is_same(self):
        from shared.paths import STATE_DB_FILE as A
        from shared.paths import STATE_DB_FILE as B
        self.assertIs(A, B)

    def test_alias_baseline_file_is_same(self):
        from shared.paths import BASELINE_FILE as A
        from shared.paths import BASELINE_FILE as B
        self.assertIs(A, B)

    def test_alias_jackal_db_file_is_same(self):
        from shared.paths import JACKAL_DB_FILE as A
        from shared.paths import JACKAL_DB_FILE as B
        self.assertIs(A, B)

    def test_alias_atomic_write_json_is_same(self):
        from shared.paths import atomic_write_json as A
        from shared.paths import atomic_write_json as B
        self.assertIs(A, B)

    def test_alias_atomic_write_text_is_same(self):
        from shared.paths import atomic_write_text as A
        from shared.paths import atomic_write_text as B
        self.assertIs(A, B)

    def test_package_dir_is_orca_legacy_dir(self):
        """orca.paths.PACKAGE_DIR is shared.paths.ORCA_LEGACY_DIR"""
        from shared.paths import PACKAGE_DIR as A
        from shared.paths import ORCA_LEGACY_DIR as B
        self.assertIs(A, B)

    def test_mock_patch_compatibility(self):
        """mock.patch('orca.paths.DATA_DIR') 작동 (alias가 module 객체 호환)"""
        with tempfile.TemporaryDirectory() as tmp:
            patched_path = Path(tmp)
            with patch("shared.paths.DATA_DIR", patched_path):
                from shared.paths import DATA_DIR
                self.assertIs(DATA_DIR, patched_path)

    def test_orca_and_jackal_callers_import_paths(self):
        """ORCA + JACKAL 호출부가 여전히 orca.paths import 가능"""
        from orca import postprocess
        from apps.orca import state, persist
        from apps.orca.research import research_report
        from apps.jackal import hunter, scanner
        from apps.jackal import tracker

        self.assertTrue(hasattr(state, "__name__"))
        self.assertTrue(hasattr(persist, "__name__"))
        self.assertTrue(hasattr(postprocess, "__name__"))
        self.assertTrue(hasattr(research_report, "__name__"))
        self.assertTrue(hasattr(hunter, "__name__"))
        self.assertTrue(hasattr(scanner, "__name__"))
        self.assertTrue(hasattr(tracker, "__name__"))


if __name__ == "__main__":
    unittest.main()
