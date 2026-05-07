# shared/llm/

LLM 클라이언트와 prompt 관리.

현재 상태: shared/llm/client.py로 이동 완료 (Day 3 commit).
Day 4: 모든 호출부가 새 경로로 마이그레이션 완료.

## 사용

```python
from shared.llm.client import LLMClient, LLMResponse, LLMFailure

client = LLMClient(api_key=os.environ["ANTHROPIC_API_KEY"])
response = client.call(
    system="...",
    user="...",
    model="claude-sonnet-4-6",
    max_tokens=2000,
    call_site="my_module.my_function",
)
```

## call_site 명명 규칙

- orca.{hunter,analyst,devil,reporter}
- orca.{verification,lessons,breaking,calendar,postprocess,backtest}
- jackal.hunter.{suggest,quick_scan,analyst,devil}
- jackal.scanner.{analyst,devil,suggest}
- jackal.evolution
- jackal.compact
