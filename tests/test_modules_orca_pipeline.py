import unittest


class ModulesOrcaPipelineTests(unittest.TestCase):
    def test_import_from_modules_package(self):
        """apps.orca.pipeline 패키지에서 run_agent_pipeline import 가능"""
        from apps.orca.pipeline import run_agent_pipeline
        self.assertTrue(callable(run_agent_pipeline))

    def test_import_from_modules_module(self):
        """apps.orca.pipeline.pipeline 모듈에서 직접 import 가능"""
        from apps.orca.pipeline.pipeline import run_agent_pipeline
        self.assertTrue(callable(run_agent_pipeline))

    def test_alias_orca_pipeline_still_works(self):
        """orca.pipeline alias가 여전히 작동"""
        from apps.orca.pipeline.pipeline import run_agent_pipeline
        self.assertTrue(callable(run_agent_pipeline))

    def test_alias_returns_same_function(self):
        """orca.pipeline과 apps.orca.pipeline이 같은 함수 반환"""
        from apps.orca.pipeline.pipeline import run_agent_pipeline as A
        from apps.orca.pipeline.pipeline import run_agent_pipeline as B
        self.assertIs(A, B)
