from __future__ import annotations

import json
import re
from typing import Any

from prompt2langgraph.adapters.base import AdapterParseError

_FENCED_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def _complete_json_value(text: str) -> tuple[str, int, bool] | None:
    stripped = text.lstrip()
    leading_ws = len(text) - len(stripped)
    if not stripped:
        return None
    decoder = json.JSONDecoder()
    try:
        value, end = decoder.raw_decode(stripped)
    except json.JSONDecodeError:
        return None
    if stripped[end:].strip():
        return None
    return stripped[:end], leading_ws, isinstance(value, dict)


def _previous_non_whitespace(text: str, index: int) -> str | None:
    previous = index - 1
    while previous >= 0:
        if not text[previous].isspace():
            return text[previous]
        previous -= 1
    return None


def _json_object_candidates(text: str) -> list[tuple[str, int]]:
    decoder = json.JSONDecoder()
    candidates: list[tuple[str, int]] = []
    index = 0
    while index < len(text):
        start = text.find("{", index)
        if start == -1:
            break
        if _previous_non_whitespace(text, start) == "[":
            index = start + 1
            continue
        try:
            value, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(value, dict):
            candidates.append((text[start : start + end], start))
            index = start + end
        else:
            index = start + 1
    return candidates


def _candidate_search_texts(text: str) -> list[tuple[str, int, bool]]:
    fenced = [(match.group(1), match.start(1)) for match in _FENCED_BLOCK_RE.finditer(text)]
    return [*(search + (True,) for search in fenced), (text, 0, False)]


def _extract_single_json_object_text(text: str, *, source: str) -> tuple[str, int]:
    complete = _complete_json_value(text)
    if complete is not None:
        candidate, offset, _is_object = complete
        return candidate, offset

    candidates: list[tuple[str, int]] = []
    non_object_candidates: list[tuple[str, int]] = []
    seen_spans: set[tuple[int, int]] = set()
    for search_text, base_offset, is_fenced in _candidate_search_texts(text):
        if is_fenced:
            complete = _complete_json_value(search_text)
            if complete is not None:
                candidate, offset, is_object = complete
                if not is_object:
                    non_object_candidates.append((candidate, base_offset + offset))
                    continue
        for candidate, offset in _json_object_candidates(search_text):
            start = base_offset + offset
            end = start + len(candidate)
            if (start, end) in seen_spans:
                continue
            seen_spans.add((start, end))
            candidates.append((candidate, start))

    if len(candidates) > 1:
        raise AdapterParseError(
            "generated JSON plan contains multiple JSON objects",
            source=source,
            path="generated_text",
        )
    if len(candidates) == 1:
        return candidates[0]
    if non_object_candidates:
        return non_object_candidates[0]
    return text, 0


def parse_prompt_plan_text(text: str, *, source: str = "prompt") -> dict[str, Any]:
    candidate_text, candidate_offset = _extract_single_json_object_text(text, source=source)
    try:
        data = json.loads(candidate_text)
    except json.JSONDecodeError as exc:
        raise AdapterParseError(
            "failed to parse generated JSON plan",
            source=source,
            path=str(candidate_offset + exc.pos),
            line=exc.lineno,
            column=exc.colno,
        ) from exc
    if not isinstance(data, dict):
        raise AdapterParseError(
            "generated JSON plan must contain an object",
            source=source,
        )
    return data
