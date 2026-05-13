import unittest


class PhaseD2ShieldMoveTests(unittest.TestCase):
    def test_modules_jackal_pipeline_shield_imports(self):
        """apps.jackal.pipeline.shield 신규 위치 import"""
        import apps.jackal.pipeline.shield

        self.assertTrue(hasattr(apps.jackal.pipeline.shield, "__name__"))

    def test_jackal_shield_alias_works(self):
        """jackal.shield 옛 위치 alias 작동"""
        import apps.jackal.shield

        self.assertTrue(hasattr(apps.jackal.shield, "__name__"))

    def test_alias_returns_same_object(self):
        """alias가 같은 객체 반환 (mock.patch 호환)"""
        from apps.jackal.shield import JackalShield as A
        from apps.jackal.pipeline.shield import JackalShield as B

        self.assertIs(A, B)

    def test_phase_d1_intact(self):
        """Phase D-1 회귀 방지 (adapter alias 그대로)"""
        from apps.jackal.pipeline.adapter import load_orca_context as A
        from apps.jackal.pipeline.adapter import load_orca_context as B

        self.assertIs(A, B)

    def test_phase_b3_intact(self):
        """Phase B-3 회귀 방지 (jackal 3 파일)"""
        from apps.jackal.pipeline import adapter
        from apps.jackal import shield, compact

        self.assertTrue(adapter and shield and compact)

    def test_jackal_full_imports(self):
        """jackal 전체 import (회귀 방지)"""
        from apps.jackal import hunter, scanner
        from jackal import backtest
        from apps.jackal.pipeline import adapter
        from apps.jackal import shield, compact, evolution, tracker, core

        self.assertTrue(adapter and shield and compact)
        self.assertTrue(evolution and tracker and scanner and hunter)
        self.assertTrue(core and backtest)


if __name__ == "__main__":
    unittest.main()
