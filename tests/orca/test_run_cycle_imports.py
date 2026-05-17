import unittest


class RunCycleImportsTests(unittest.TestCase):
    def test_run_cycle_imports_load_cost(self):
        """run_cycle 안의 from orca.data import load_cost 가 작동"""
        from orca.data import load_cost

        self.assertTrue(callable(load_cost))

    def test_run_cycle_imports_update_weights(self):
        """run_cycle 안의 from orca.analysis import update_weights_from_accuracy 작동"""
        from apps.orca.analysis import update_weights_from_accuracy

        self.assertTrue(callable(update_weights_from_accuracy))

    def test_run_cycle_module_imports(self):
        """run_cycle 모듈 자체 import (회귀 방지)"""
        from apps.orca.pipeline.run_cycle import run_orca_cycle

        self.assertTrue(callable(run_orca_cycle))

    def test_run_cycle_no_local_data_analysis(self):
        """apps.orca.pipeline.data, .analysis는 존재 안 함"""
        with self.assertRaises(ModuleNotFoundError):
            import apps.orca.pipeline.data
        with self.assertRaises(ModuleNotFoundError):
            import apps.orca.pipeline.analysis


if __name__ == "__main__":
    unittest.main()
