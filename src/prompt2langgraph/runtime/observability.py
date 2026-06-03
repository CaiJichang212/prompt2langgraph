"""Runtime observability helpers."""

from __future__ import annotations

from collections.abc import Iterable
from time import perf_counter

from prompt2langgraph.runtime.events import ExternalCallRecord, RunMetrics


def duration_ms_since(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 3)


class RuntimeMetricsCollector:
    def __init__(self) -> None:
        self.external_calls: list[ExternalCallRecord] = []
        self.retry_count = 0

    def record_external_call(self, record: ExternalCallRecord) -> None:
        self.external_calls.append(record)

    def record_retry(self) -> None:
        self.retry_count += 1

    def metrics(self, *, duration_ms: float) -> RunMetrics:
        return RunMetrics(
            duration_ms=duration_ms,
            retry_count=self.retry_count,
            tool_call_count=sum(1 for item in self.external_calls if item.category == "tool"),
            call_count=len(self.external_calls),
            total_latency_ms=_sum_latency(self.external_calls),
            token_count=_sum_tokens(self.external_calls),
        )


def _sum_latency(records: Iterable[ExternalCallRecord]) -> float | None:
    total = sum(item.latency_ms for item in records if item.latency_ms is not None)
    return total or None


def _sum_tokens(records: Iterable[ExternalCallRecord]) -> int | None:
    total = sum(item.token_count for item in records if item.token_count is not None)
    return total or None
