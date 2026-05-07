"""
orca.agents (DEPRECATED ALIAS)
==============================

이 모듈은 backward-compatible alias입니다.
실제 코드는 modules/orca/pipeline/agents.py 로 이동됨 (Day 8 commit).

신규 코드는 다음 경로 사용 권장:
    from modules.orca.pipeline.agents import agent_hunter, ...
또는:
    from modules.orca.pipeline import agent_hunter, ...

Day 7 학습 패턴: mock.patch 호환성을 위해 wildcard re-export.
"""

import sys as _sys

from modules.orca.pipeline import agents as _agents
from modules.orca.pipeline.agents import *  # noqa: F401,F403
from modules.orca.pipeline.agents import (
    ANALYST_SYSTEM_BASE,
    API_KEY,
    DEVIL_SYSTEM,
    HUNTER_SYSTEM,
    KST,
    MODEL_ANALYST,
    MODEL_DEVIL,
    MODEL_HUNTER,
    MODEL_REPORTER_FULL,
    MODEL_REPORTER_LITE,
    REPORTER_SYSTEM,
    _DEFAULT_HAIKU,
    _DEFAULT_SONNET,
    _HUNTER_QUERIES,
    _THESIS_KILLER_ALLOWED_EVENTS,
    _THESIS_KILLER_BLOCKED_EVENTS,
    _TOK,
    _llm_client,
    _normalize_thesis_killers,
    agent_analyst,
    agent_devil,
    agent_hunter,
    agent_reporter,
    call_api,
    console,
    get_mode_context,
    parse_json,
)

try:
    from rich.console import Console as _Console

    _agents.console = _Console()
except Exception:
    pass

__all__ = [
    "ANALYST_SYSTEM_BASE",
    "API_KEY",
    "DEVIL_SYSTEM",
    "HUNTER_SYSTEM",
    "KST",
    "MODEL_ANALYST",
    "MODEL_DEVIL",
    "MODEL_HUNTER",
    "MODEL_REPORTER_FULL",
    "MODEL_REPORTER_LITE",
    "REPORTER_SYSTEM",
    "_DEFAULT_HAIKU",
    "_DEFAULT_SONNET",
    "_HUNTER_QUERIES",
    "_THESIS_KILLER_ALLOWED_EVENTS",
    "_THESIS_KILLER_BLOCKED_EVENTS",
    "_TOK",
    "_llm_client",
    "_normalize_thesis_killers",
    "agent_analyst",
    "agent_devil",
    "agent_hunter",
    "agent_reporter",
    "call_api",
    "console",
    "get_mode_context",
    "parse_json",
]

_sys.modules[__name__] = _agents
