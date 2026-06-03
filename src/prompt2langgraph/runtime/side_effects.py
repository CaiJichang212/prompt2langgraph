"""Side-effect idempotency state for runtime execution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SideEffectIdempotencyStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._records: dict[str, dict[str, Any]] = {}
        if path is not None and path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._records = {
                    str(key): value for key, value in data.items() if isinstance(value, dict)
                }

    def get_success(
        self,
        workflow_id: str,
        thread_id: str,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        record = self._records.get(_record_key(workflow_id, thread_id, idempotency_key))
        if record is None or record.get("status") != "succeeded":
            return None
        output = record.get("output")
        return dict(output) if isinstance(output, dict) else None

    def record_success(
        self,
        workflow_id: str,
        thread_id: str,
        idempotency_key: str,
        *,
        output: dict[str, Any],
    ) -> None:
        self._records[_record_key(workflow_id, thread_id, idempotency_key)] = {
            "status": "succeeded",
            "output": dict(output),
        }
        self._flush()

    def _flush(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._records, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def side_effect_store_path(state_store_dir: Path | None) -> Path | None:
    if state_store_dir is None:
        return None
    return state_store_dir / "side_effects.json"


def _record_key(workflow_id: str, thread_id: str, idempotency_key: str) -> str:
    return "\0".join([workflow_id, thread_id, idempotency_key])
