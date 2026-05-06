# ORCA LLMClient

`orca.llm_client.LLMClient` is the provider adapter boundary for ORCA LLM calls.
It preserves existing caller behavior while adding fail-fast credential checks,
usage capture, and append-only JSONL audit logs.

## Basic Usage

```python
from orca.llm_client import LLMClient

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
orca.backtest
```

Reserve `jackal.*` for the next sprint when JACKAL Anthropic calls move behind
the same adapter.

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

- Migrate JACKAL direct Anthropic SDK calls to `LLMClient`.
- Deprecate `jackal.shield.log_usage()` after JACKAL logs flow through JSONL.
- Build a dashboard comparing estimated cost in `orca_cost.json` with observed
  token usage in `llm_log.jsonl`.
