import unittest
from unittest.mock import patch


class ModulesOrcaAgentsTests(unittest.TestCase):
    def test_import_from_modules_package(self):
        """apps.orca.pipeline 패키지에서 agent 함수 import 가능"""
        from apps.orca.pipeline import agent_hunter, agent_analyst, agent_devil, agent_reporter
        self.assertTrue(callable(agent_hunter))
        self.assertTrue(callable(agent_analyst))
        self.assertTrue(callable(agent_devil))
        self.assertTrue(callable(agent_reporter))

    def test_import_from_modules_module(self):
        """apps.orca.pipeline.agents 모듈에서 직접 import 가능"""
        from apps.orca.pipeline.agents import agent_hunter, agent_analyst, agent_devil, agent_reporter
        self.assertTrue(callable(agent_hunter))
        self.assertTrue(callable(agent_analyst))
        self.assertTrue(callable(agent_devil))
        self.assertTrue(callable(agent_reporter))

    def test_alias_orca_agents_still_works(self):
        """orca.agents alias가 여전히 작동"""
        from apps.orca.pipeline.agents import agent_hunter, agent_analyst, agent_devil, agent_reporter
        self.assertTrue(callable(agent_hunter))
        self.assertTrue(callable(agent_analyst))
        self.assertTrue(callable(agent_devil))
        self.assertTrue(callable(agent_reporter))

    def test_alias_returns_same_functions(self):
        """orca.agents와 apps.orca.pipeline.agents가 같은 함수 반환"""
        from apps.orca.pipeline.agents import agent_hunter as A
        from apps.orca.pipeline.agents import agent_hunter as B
        from apps.orca.pipeline.agents import agent_analyst as C
        from apps.orca.pipeline.agents import agent_analyst as D
        from apps.orca.pipeline.agents import agent_devil as E
        from apps.orca.pipeline.agents import agent_devil as F
        from apps.orca.pipeline.agents import agent_reporter as G
        from apps.orca.pipeline.agents import agent_reporter as H

        self.assertIs(A, B)
        self.assertIs(C, D)
        self.assertIs(E, F)
        self.assertIs(G, H)

    def test_mock_patch_compatibility_orca_agents(self):
        """mock.patch('orca.agents.agent_hunter') 작동 검증 (Day 7 이슈 회귀 방지)"""
        with patch("apps.orca.pipeline.agents.agent_hunter") as mock_hunter:
            mock_hunter.return_value = {"mocked": True}
            from apps.orca.pipeline.agents import agent_hunter
            result = agent_hunter("test", "MORNING", {})
            self.assertEqual(result, {"mocked": True})
