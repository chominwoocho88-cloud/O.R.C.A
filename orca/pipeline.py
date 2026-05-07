"""
orca.pipeline (DEPRECATED ALIAS)
=================================

이 모듈은 backward-compatible alias입니다.
실제 코드는 modules/orca/pipeline/pipeline.py 로 이동됨 (Day 7 commit).

신규 코드는 다음 경로 사용 권장:
    from modules.orca.pipeline import run_agent_pipeline

이 alias는 호출부 마이그레이션 완료 후 제거 예정.
"""

import sys as _sys

from modules.orca.pipeline import pipeline as _pipeline
from modules.orca.pipeline.pipeline import run_agent_pipeline

__all__ = ["run_agent_pipeline"]

_sys.modules[__name__] = _pipeline
