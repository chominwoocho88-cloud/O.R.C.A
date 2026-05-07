import unittest


class ModulesOrcaPipelineTests(unittest.TestCase):
    def test_import_from_modules_package(self):
        """modules.orca.pipeline 패키지에서 run_agent_pipeline import 가능"""
        from modules.orca.pipeline import run_agent_pipeline
        self.assertTrue(callable(run_agent_pipeline))

    def test_import_from_modules_module(self):
        """modules.orca.pipeline.pipeline 모듈에서 직접 import 가능"""
        from modules.orca.pipeline.pipeline import run_agent_pipeline
        self.assertTrue(callable(run_agent_pipeline))

    def test_alias_orca_pipeline_still_works(self):
        """orca.pipeline alias가 여전히 작동"""
        from orca.pipeline import run_agent_pipeline
        self.assertTrue(callable(run_agent_pipeline))

    def test_alias_returns_same_function(self):
        """orca.pipeline과 modules.orca.pipeline이 같은 함수 반환"""
        from orca.pipeline import run_agent_pipeline as A
        from modules.orca.pipeline.pipeline import run_agent_pipeline as B
        self.assertIs(A, B)
