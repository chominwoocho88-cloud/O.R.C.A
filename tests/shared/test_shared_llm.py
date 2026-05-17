from __future__ import annotations

import unittest


class SharedLLMTests(unittest.TestCase):
    def test_import_from_shared_llm_package(self):
        """shared.llm 패키지에서 LLMClient/LLMResponse/LLMFailure import 가능"""
        from shared.llm import LLMClient, LLMFailure, LLMResponse

        self.assertTrue(callable(LLMClient))
        self.assertTrue(callable(LLMResponse))
        self.assertTrue(callable(LLMFailure))

    def test_import_from_shared_llm_client_module(self):
        """shared.llm.client 모듈에서 직접 import 가능"""
        from shared.llm.client import LLMClient, LLMFailure, LLMResponse

        self.assertTrue(callable(LLMClient))
        self.assertTrue(callable(LLMResponse))
        self.assertTrue(callable(LLMFailure))

    def test_alias_orca_llm_client_still_works(self):
        """orca.llm_client alias가 여전히 작동"""
        from orca.llm_client import LLMClient, LLMFailure, LLMResponse

        self.assertTrue(callable(LLMClient))
        self.assertTrue(callable(LLMResponse))
        self.assertTrue(callable(LLMFailure))

    def test_alias_returns_same_class(self):
        """orca.llm_client과 shared.llm.client이 같은 클래스 반환"""
        from orca.llm_client import LLMClient as AliasLLMClient
        from shared.llm.client import LLMClient as RealLLMClient

        self.assertIs(AliasLLMClient, RealLLMClient)


if __name__ == "__main__":
    unittest.main()
