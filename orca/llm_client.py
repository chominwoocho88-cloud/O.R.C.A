"""
orca.llm_client (DEPRECATED ALIAS)
==================================

이 모듈은 backward-compatible alias입니다.
실제 코드는 shared/llm/client.py 로 이동됨 (Day 3 commit).

신규 코드는 다음 경로 사용 권장:
    from shared.llm.client import LLMClient, LLMResponse, LLMFailure

또는:
    from shared.llm import LLMClient, LLMResponse, LLMFailure

이 alias는 다음 sprint에서 호출부 마이그레이션 완료 후 제거 예정.
"""

from shared.llm.client import LLMClient, LLMResponse, LLMFailure

__all__ = ["LLMClient", "LLMResponse", "LLMFailure"]
