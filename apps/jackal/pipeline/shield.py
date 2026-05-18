"""
JACKAL shield module.
Jackal Shield - 蹂댁븞 + 鍮꾩슜 ?먮룞 泥댄겕 ?쒖뒪??
[Bug Fix 2] _check_budget()??compact_log留??쎌뼱 ??API 鍮꾩슜 誘몄쭛怨????섏젙
  - data/llm_log.jsonl usage ledger ?곕룞
  - _check_budget() / _detect_spike() 紐⑤몢 usage_log ?곗꽑 ?ъ슜

寃????ぉ:
  1. API ???몄텧 (.env, *.py, *.json, *.yml ?먯꽌 ?⑦꽩 ?먯깋)
  2. ?쇱씪 ?좏겙 ?덉궛 珥덇낵 ?щ? (usage_log 湲곕컲 ????API 鍮꾩슜)
  3. 鍮꾩젙???좏겙 湲됱쬆 媛먯? (?꾩씪 ?鍮?300% ?댁긽)
  4. skills/ ?붾젆?좊━ 鍮꾩젙???뚯씪 ?먯?
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

from shared.paths import JACKAL_LEGACY_DIR
from shared.llm.usage_reader import read_jackal_today_tokens, read_jackal_tokens_by_date

log = logging.getLogger("jackal_shield")

_BASE      = JACKAL_LEGACY_DIR
_REPO_ROOT = JACKAL_LEGACY_DIR.parent   # repo root ??API ???ㅼ틪 踰붿쐞

# ??? ?ㅼ젙 ?????????????????????????????????????????????????????????
_DAILY_TOKEN_BUDGET = int(os.getenv("JACKAL_DAILY_BUDGET", "500000"))
_SPIKE_MULTIPLIER   = float(os.getenv("JACKAL_SPIKE_MULTIPLIER", "3.0"))
_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}", re.I),
    re.compile(r"sk-[A-Za-z0-9]{20,}", re.I),
    # [Fix] os.environ.get ?뺥깭???ㅼ젣 ??媛믪씠 ?꾨땲誘濡??쒖쇅
    re.compile(r"ANTHROPIC_API_KEY\s*=\s*['\"][A-Za-z0-9\-_]{20,}['\"]", re.I),
    re.compile(r"api[_\-]?key\s*[:=]\s*['\"][A-Za-z0-9\-_]{20,}['\"]", re.I),
]
_EXCLUDE_DIRS    = {".git", "__pycache__", "node_modules", ".venv", "venv"}
_SCAN_EXTENSIONS = {".py", ".json", ".yml", ".yaml", ".env", ".txt", ".md"}

class JackalShield:
    """Run repository secret scans and lightweight JACKAL budget checks."""

    def __init__(self, scan_root: Path = _REPO_ROOT):
        self.scan_root  = Path(scan_root)
        self.compact_log = _BASE / "compact_log.json"

    # ?? 怨듦컻 硫붿꽌??????????????????????????????????????????????????
    def scan(self) -> dict:
        """
        ?꾩껜 ?ㅼ틪 ?ㅽ뻾.
        Returns: {issues, abort, stats}
        """
        issues = []
        stats  = {}

        # 1. API ???몄텧 ?ㅼ틪
        leaked = self._scan_secrets()
        for item in leaked:
            issues.append(f"?뵎 API???몄텧 ?섏떖: {item}")

        # 2. ?쇱씪 ?좏겙 ?덉궛 泥댄겕 (usage_log 湲곕컲)
        budget = self._check_budget()
        stats["today_tokens"]  = budget["today_tokens"]
        stats["daily_budget"]  = _DAILY_TOKEN_BUDGET
        stats["budget_source"] = budget["source"]
        if budget["exceeded"]:
            issues.append(
                f"?뮯 ?쇱씪 ?좏겙 ?덉궛 珥덇낵: "
                f"{budget['today_tokens']:,} / {_DAILY_TOKEN_BUDGET:,} "
                f"[{budget['source']}]"
            )

        # 3. ?좏겙 湲됱쬆 媛먯?
        spike = self._detect_spike()
        stats["spike_ratio"] = spike["ratio"]
        if spike["detected"]:
            issues.append(f"?뱢 ?좏겙 湲됱쬆 媛먯?: ?꾩씪 ?鍮?{spike['ratio']:.1f}諛?利앷?")

        # 4. skills/ ?댁긽 ?뚯씪 ?먯?
        for s in self._check_skills():
            issues.append(f"?좑툘  skills/ ?댁긽 ?뚯씪: {s}")

        # abort 議곌굔: API ???몄텧 OR ?덉궛 2諛?珥덇낵
        abort = bool(leaked) or budget["today_tokens"] > _DAILY_TOKEN_BUDGET * 2

        return {
            "issues":     issues,
            "abort":      abort,
            "stats":      stats,
            "scanned_at": datetime.now().isoformat(),
        }

    # ?? API ???몄텧 ?ㅼ틪 ???????????????????????????????????????????
    def _scan_secrets(self) -> list:
        found = []
        for path in self._iter_files():
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for pattern in _SECRET_PATTERNS:
                if pattern.search(content):
                    rel = str(path.relative_to(self.scan_root))
                    if rel not in found:
                        found.append(rel)
                    break
        return found

    def _iter_files(self):
        for p in self.scan_root.rglob("*"):
            if any(excl in p.parts for excl in _EXCLUDE_DIRS):
                continue
            if p.suffix in _SCAN_EXTENSIONS and p.is_file():
                yield p

    # ?? ?좏겙 ?덉궛 泥댄겕 (Bug Fix: usage_log ?곗꽑) ??????????????????
    def _check_budget(self) -> dict:
        """
        Read actual JACKAL usage from data/llm_log.jsonl.
        Fall back to compact_log when no shared LLM ledger entries exist.
        """
        today = datetime.now().date().isoformat()

        today_tokens = read_jackal_today_tokens(today=today)
        if today_tokens > 0:
            return {
                "today_tokens": today_tokens,
                "exceeded":     today_tokens > _DAILY_TOKEN_BUDGET,
                "source":       "llm_log",
            }

        # ?대갚: compact_log
        compact_logs = self._load_compact_log()
        today_tokens = sum(
            e.get("tokens_before", 0)
            for e in compact_logs
            if e.get("timestamp", "")[:10] == today
        )
        return {
            "today_tokens": today_tokens,
            "exceeded":     today_tokens > _DAILY_TOKEN_BUDGET,
            "source":       "compact_log(fallback)",
        }

    # ?? 湲됱쬆 媛먯? (Bug Fix: usage_log ?곗꽑) ??????????????????????
    def _detect_spike(self) -> dict:
        today     = datetime.now().date()
        yesterday = (today - timedelta(days=1)).isoformat()
        today_str = today.isoformat()

        usage_by_date = read_jackal_tokens_by_date()
        if usage_by_date:
            today_t = usage_by_date.get(today_str, 0)
            yest_t = usage_by_date.get(yesterday, 0)
        else:
            token_key = "tokens_before"
            logs      = self._load_compact_log()
            today_t = sum(e.get(token_key, 0) for e in logs
                          if e.get("timestamp", "")[:10] == today_str)
            yest_t  = sum(e.get(token_key, 0) for e in logs
                          if e.get("timestamp", "")[:10] == yesterday)

        if yest_t == 0:
            return {"detected": False, "ratio": 0.0}
        ratio = today_t / yest_t
        return {"detected": ratio >= _SPIKE_MULTIPLIER, "ratio": round(ratio, 2)}

    # ?? skills/ ?댁긽 ?먯? ?????????????????????????????????????????
    def _check_skills(self) -> list:
        skills_dir = _BASE / "skills"
        if not skills_dir.exists():
            # ?좉퇋 ?ㅼ튂 ?먮뒗 ?꾩쭅 Evolution 誘몄떎?????댁뒋 ?꾨떂, ?붾쾭洹몃쭔
            log.debug("skills/ ?붾젆?좊━ ?놁쓬 (Evolution 誘몄떎??or ?좉퇋 ?ㅼ튂)")
            return []
        files = list(skills_dir.iterdir())
        if not files:
            log.debug("skills/ 鍮꾩뼱?덉쓬 (?꾩쭅 Skill 誘몄깮??")
            return []
        issues = []
        for p in files:
            if p.suffix != ".json":
                issues.append(f"{p.name} (鍮껲SON ?뚯씪)")
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                issues.append(f"{p.name} (?뚯떛 ?ㅻ쪟)")
                continue
            missing = {"name", "description", "trigger", "action"} - set(data.keys())
            if missing:
                issues.append(f"{p.name} (?꾨뱶 ?꾨씫: {missing})")
        return issues

    # ?? ?좏떥 ???????????????????????????????????????????????????????
    def _load_compact_log(self) -> list:
        if not self.compact_log.exists():
            return []
        try:
            return json.loads(self.compact_log.read_text(encoding="utf-8"))
        except Exception:
            return []

# ??? ?⑤룆 ?ㅽ뻾 ????????????????????????????????????????????????????
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
    shield = JackalShield()
    result = shield.scan()

    print(f"\n{'='*50}")
    print("?썳截? Jackal Shield ?ㅼ틪 寃곌낵")
    print(f"{'='*50}")
    if result["issues"]:
        print(f"?좑툘  諛쒓껄???댁뒋 {len(result['issues'])}嫄?")
        for issue in result["issues"]:
            print(f"  {issue}")
    else:
        print("  ???댁긽 ?놁쓬")

    print(f"\n  ?듦퀎:")
    for k, v in result["stats"].items():
        print(f"    {k}: {v:,}" if isinstance(v, int) else f"    {k}: {v}")
    print(f"  abort: {result['abort']}")
    print(f"{'='*50}\n")



