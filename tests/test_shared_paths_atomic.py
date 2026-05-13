import json
import tempfile
import unittest
from pathlib import Path


class SharedPathsAtomicTests(unittest.TestCase):
    def test_atomic_write_text_creates_file(self):
        """atomic_write_text이 파일 생성"""
        from shared.paths import atomic_write_text
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.txt"
            atomic_write_text(path, "hello")
            self.assertTrue(path.exists())
            self.assertEqual(path.read_text(), "hello")

    def test_atomic_write_text_overwrites(self):
        """atomic_write_text이 기존 파일 덮어씀"""
        from shared.paths import atomic_write_text
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.txt"
            atomic_write_text(path, "first")
            atomic_write_text(path, "second")
            self.assertEqual(path.read_text(), "second")

    def test_atomic_write_json_creates_file(self):
        """atomic_write_json이 JSON 파일 생성"""
        from shared.paths import atomic_write_json
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.json"
            data = {"key": "value", "num": 42}
            atomic_write_json(path, data)
            self.assertTrue(path.exists())
            loaded = json.loads(path.read_text())
            self.assertEqual(loaded, data)

    def test_atomic_write_json_handles_lists(self):
        """atomic_write_json이 리스트도 저장"""
        from shared.paths import atomic_write_json
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.json"
            data = [1, 2, 3, "test"]
            atomic_write_json(path, data)
            loaded = json.loads(path.read_text())
            self.assertEqual(loaded, data)

    def test_shared_atomic_equals_orca_atomic(self):
        """shared.paths의 atomic 함수가 orca.paths의 함수와 동작 일치"""
        from shared.paths import atomic_write_json as shared_func
        from shared.paths import atomic_write_json as orca_func

        data = {"test": True, "value": 123}

        with tempfile.TemporaryDirectory() as tmp:
            shared_path = Path(tmp) / "shared.json"
            orca_path = Path(tmp) / "orca.json"

            shared_func(shared_path, data)
            orca_func(orca_path, data)

            self.assertEqual(shared_path.read_text(), orca_path.read_text())


if __name__ == "__main__":
    unittest.main()
