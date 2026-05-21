from __future__ import annotations

import json
from typing import Any

from prompt2langgraph.adapters.base import AdapterParseError


def parse_prompt_plan_text(text: str, *, source: str = "prompt") -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AdapterParseError(
            "failed to parse generated JSON plan",
            source=source,
            path=str(exc.pos),
            line=exc.lineno,
            column=exc.colno,
        ) from exc
    if not isinstance(data, dict):
        raise AdapterParseError(
            "generated JSON plan must contain an object",
            source=source,
        )
    return data
