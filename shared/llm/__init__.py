"""shared.llm: LLM 클라이언트와 prompt 관리.

사용:
    from shared.llm.client import LLMClient, LLMResponse, LLMFailure
"""

from shared.llm.client import LLMClient, LLMResponse, LLMFailure

__all__ = ["LLMClient", "LLMResponse", "LLMFailure"]
