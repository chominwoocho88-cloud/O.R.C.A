import unittest
from unittest.mock import patch


class ModulesOrcaRunCycleTests(unittest.TestCase):
    def test_import_from_modules_package(self):
        """modules.orca.pipeline에서 run_orca_cycle import 가능"""
        from modules.orca.pipeline import run_orca_cycle
        self.assertTrue(callable(run_orca_cycle))

    def test_import_from_modules_module(self):
        """modules.orca.pipeline.run_cycle 모듈에서 직접 import 가능"""
        from modules.orca.pipeline.run_cycle import run_orca_cycle
        self.assertTrue(callable(run_orca_cycle))

    def test_alias_orca_run_cycle_still_works(self):
        """orca.run_cycle alias가 여전히 작동"""
        from orca.run_cycle import run_orca_cycle
        self.assertTrue(callable(run_orca_cycle))

    def test_alias_returns_same_function(self):
        """orca.run_cycle과 modules.orca.pipeline.run_cycle이 같은 함수 반환"""
        from orca.run_cycle import run_orca_cycle as A
        from modules.orca.pipeline.run_cycle import run_orca_cycle as B
        self.assertIs(A, B)

    def test_mock_patch_compatibility(self):
        """mock.patch('orca.run_cycle.run_orca_cycle') 작동 (Day 7-8 호환성 회귀 방지)"""
        with patch("orca.run_cycle.run_orca_cycle") as mock_cycle:
            mock_cycle.return_value = {"mocked": True}
            from orca.run_cycle import run_orca_cycle
            result = run_orca_cycle(mode="MORNING", memory=[])
            self.assertEqual(result, {"mocked": True})

    def test_orca_main_still_imports_run_cycle(self):
        """orca/main.py가 여전히 run_orca_cycle을 import할 수 있음 (진입점 회귀 방지)"""
        import orca.main
        self.assertTrue(hasattr(orca.main, "__name__"))
