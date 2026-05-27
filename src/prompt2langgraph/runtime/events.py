"""Runtime event and result models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from prompt2langgraph.diagnostics.report import Diagnostic


class RunEvent(BaseModel):
    type: str
    run_id: str | None = None
    thread_id: str | None = None
    node_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class RunInterrupt(BaseModel):
    node_id: str
    kind: Literal["human_gate", "side_effect_approval"] = "human_gate"
    payload: dict[str, Any] = Field(default_factory=dict)


class RunMetrics(BaseModel):
    duration_ms: float | None = None
    token_count: int | None = None
    retry_count: int = 0
    tool_call_count: int = 0
    call_count: int = 0
    total_latency_ms: float | None = None


class ExternalCallRecord(BaseModel):
    node_id: str
    executor_ref: str
    model: str | None = None
    latency_ms: float | None = None
    token_count: int | None = None
    status: Literal["succeeded", "failed"]
    error_code: str | None = None


class RunResult(BaseModel):
    status: Literal["succeeded", "failed", "waiting"]
    run_id: str
    thread_id: str
    output: dict[str, Any] = Field(default_factory=dict)
    events: list[RunEvent] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    interrupt: RunInterrupt | None = None
    metrics: RunMetrics = Field(default_factory=RunMetrics)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    external_calls: list[ExternalCallRecord] = Field(default_factory=list)
    side_effect_rejections: dict[str, str] = Field(default_factory=dict)
