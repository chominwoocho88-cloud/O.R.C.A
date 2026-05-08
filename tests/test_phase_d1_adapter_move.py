import unittest


class PhaseD1AdapterMoveTests(unittest.TestCase):
    def test_modules_jackal_pipeline_adapter_imports(self):
        """modules.jackal.pipeline.adapter 신규 위치 import"""
        import modules.jackal.pipeline.adapter

        self.assertTrue(hasattr(modules.jackal.pipeline.adapter, "__name__"))

    def test_jackal_adapter_alias_works(self):
        """jackal.adapter 옛 위치 alias 작동"""
        import jackal.adapter

        self.assertTrue(hasattr(jackal.adapter, "__name__"))

    def test_alias_returns_same_object(self):
        """alias가 같은 객체 반환 (mock.patch 호환)"""
        from jackal.adapter import load_orca_context as A
        from modules.jackal.pipeline.adapter import load_orca_context as B

        self.assertIs(A, B)

    def test_phase_b3_intact(self):
        """Phase B-3 회귀 방지 (shared.paths 사용)"""
        from jackal.adapter import _JACKAL_DIR
        from shared.paths import JACKAL_LEGACY_DIR

        self.assertEqual(_JACKAL_DIR, JACKAL_LEGACY_DIR)

    def test_jackal_full_imports(self):
        """jackal 전체 import (회귀 방지)"""
        from jackal import (
            adapter,
            shield,
            compact,
            evolution,
            tracker,
            scanner,
            hunter,
            core,
            backtest,
        )

        self.assertTrue(adapter and shield and compact)
        self.assertTrue(evolution and tracker and scanner and hunter)
        self.assertTrue(core and backtest)


if __name__ == "__main__":
    unittest.main()
