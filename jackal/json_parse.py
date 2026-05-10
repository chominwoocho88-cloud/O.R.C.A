"""LLM JSON parsing helpers for JACKAL."""

from __future__ import annotations

import json
import re


def safe_parse_json(text: str, *, schema_keys: list[str] | None = None) -> dict:
    """Parse JSON from mixed LLM output while tolerating explanation text."""
    if not text:
        return {}

    candidates: list[dict] = []
    for block in re.findall(r"`{3,}(?:json)?\s*([\s\S]*?)\s*`{3,}", text, re.IGNORECASE):
        obj = _try_parse_json_object(block)
        if obj:
            candidates.append(obj)
        candidates.extend(_extract_balanced_objects(block))

    candidates.extend(_extract_balanced_objects(text))
    selected = _select_json_candidate(candidates, schema_keys or [])
    if selected:
        return selected

    m = re.search(r"\{[\s\S]*\}", text)
    fallback_text = m.group() if m else text[text.find("{") :] if "{" in text else ""
    return _try_parse_json_object(fallback_text) or {}


def _select_json_candidate(candidates: list[dict], schema_keys: list[str]) -> dict:
    if not candidates:
        return {}
    if schema_keys:
        matching = [obj for obj in candidates if any(key in obj for key in schema_keys)]
        if matching:
            return max(matching, key=lambda obj: (sum(key in obj for key in schema_keys), len(obj)))
    return max(candidates, key=len)


def _extract_balanced_objects(text: str) -> list[dict]:
    objects: list[dict] = []
    i = 0
    while i < len(text):
        if text[i] != "{":
            i += 1
            continue

        start = i
        depth = 0
        in_string = False
        escape = False
        j = i
        matched_end = None

        while j < len(text):
            ch = text[j]
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = not in_string
            elif not in_string:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        matched_end = j + 1
                        break
            j += 1

        if matched_end is None:
            i = start + 1
            continue

        obj = _try_parse_json_object(text[start:matched_end])
        if obj:
            objects.append(obj)
        i = matched_end

    return objects


def _try_parse_json_object(text: str) -> dict:
    if not text:
        return {}
    value = str(text).strip()
    if not value:
        return {}

    fixed = re.sub(r",\s*([}\]])", r"\1", value)
    repaired = fixed
    repaired += "]" * max(repaired.count("[") - repaired.count("]"), 0)
    repaired += "}" * max(repaired.count("{") - repaired.count("}"), 0)

    for candidate in (value, fixed, repaired):
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return {}
