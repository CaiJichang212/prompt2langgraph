"""Safe JSONL audit sink for runtime events."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class AuditRecord(BaseModel):
    run_id: str
    thread_id: str
    workflow_id: str
    node_id: str | None = None
    event_type: str
    status: Literal["started", "succeeded", "failed", "waiting", "rejected", "retry"]
    latency_ms: float | None = None
    error_code: str | None = None
    retry_count: int = 0
    timestamp: str


class JsonlAuditSink:
    def __init__(self, path: Path) -> None:
        self.path = path

    def write(self, record: AuditRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.model_dump(mode="json"), sort_keys=True) + "\n")


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def audit_path_for_state_store(state_store_dir: Path | None) -> Path | None:
    if state_store_dir is None:
        return None
    return state_store_dir / "audit.log.jsonl"
