# Shared LLMClient

`shared.llm.client.LLMClient` is the provider adapter boundary for ORCA and
JACKAL LLM calls. It preserves existing caller behavior while adding fail-fast
credential checks, usage capture, and append-only JSONL audit logs.

## Basic Usage

```python
from shared.llm.client import LLMClient, LLMResponse, LLMFailure

client = LLMClient(api_key=os.environ.get("ANTHROPIC_API_KEY"), fail_fast=True)
response = client.call(
    system="You are ORCA.",
    user="Return JSON.",
    model="claude-sonnet-4-6",
    max_tokens=2000,
    use_search=True,
    max_retries=2,
    call_site="orca.analyst",
)
text = response.text
```

The old `orca.llm_client` path remains as a backward-compatible alias:

```python
from orca.llm_client import LLMClient, LLMResponse, LLMFailure
```

`orca.agents.call_api()` still returns `str` so existing ORCA agent callers do
not need to know about `LLMResponse`.

## JSONL Log

Default path:

```text
data/llm_log.jsonl
```

Success event:

```json
{"ts":"2026-05-06T14:30:01+09:00","type":"success","call_site":"orca.hunter","model":"claude-haiku-4-5","input_tokens":1234,"output_tokens":567,"cache_read_tokens":0,"cache_creation_tokens":0,"web_search_count":6,"stop_reason":"end_turn","elapsed_ms":31000,"attempt":1}
```

Failure event:

```json
{"ts":"2026-05-06T14:30:05+09:00","type":"failure","call_site":"orca.analyst","model":"claude-sonnet-4-6","error_type":"auth_failed","message":"...","attempt":1,"elapsed_ms":150}
```

Each line is a complete JSON object. The file is append-only and intended for
cost visibility, failure auditing, and later comparison against
`data/orca_cost.json`.

## call_site Names

Use stable dotted names:

```text
orca.hunter
orca.analyst
orca.devil
orca.reporter
orca.verification
orca.lessons
orca.breaking
orca.calendar
orca.postprocess
apps.orca.backtest
apps.jackal.hunter.suggest
apps.jackal.hunter.quick_scan
apps.jackal.hunter.analyst
apps.jackal.hunter.devil
apps.jackal.scanner.analyst
apps.jackal.scanner.devil
apps.jackal.scanner.suggest
apps.jackal.evolution
apps.jackal.compact
```

## Fail-Fast Mode

`LLMClient(api_key="", fail_fast=True)` raises immediately:

```text
ANTHROPIC_API_KEY missing - LLM client requires API key
```

ORCA also checks credentials at boot for LLM-required modes:

```text
MORNING, AFTERNOON, EVENING, DAWN, WEEKLY, MONTHLY
```

This prevents a scheduled run from silently producing fallback output when the
LLM credential is missing.

## Next Sprint

- JACKAL direct Anthropic SDK calls migrated to `LLMClient` (Day 2 commit).
- shared/llm/ split completed (Day 3 commit).
- Call-site migration completed (Day 4). All ORCA and JACKAL callers import
  `shared.llm.client` directly.
- Create `shared/broker/kis.py`.
- JACKAL usage tracking now reads `data/llm_log.jsonl` as the single source.
- Build a dashboard comparing estimated cost in `orca_cost.json` with observed
  token usage in `llm_log.jsonl`.
