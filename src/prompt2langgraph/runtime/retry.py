"""Runtime retry policy helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from prompt2langgraph.diagnostics.codes import E_LLM_001, E_LLM_002, E_SEC_015
from prompt2langgraph.ir.models import NodeSpec
from prompt2langgraph.registry.executors import ExecutorError

_RETRYABLE_LLM_API_MARKERS = (
    "timeout",
    "timed out",
    "5xx",
    "500",
    "502",
    "503",
    "504",
    "server error",
    "temporarily unavailable",
)


RetrySink = Callable[[str, int], None]


def should_retry_executor_error(error: ExecutorError) -> bool:
    """Return True only for runtime errors that are safe to retry by default."""
    if error.code == E_LLM_001:
        return True
    if error.code == E_LLM_002:
        message = _error_text(error)
        return any(marker in message for marker in _RETRYABLE_LLM_API_MARKERS)
    if error.code == E_SEC_015:
        message = _error_text(error)
        return "timed out" in message or "timeout" in message
    return False


def node_allows_retry(node: NodeSpec, error: ExecutorError) -> bool:
    if node.kind == "side_effect":
        if node.security is None or not node.security.idempotency_key:
            return False
    return should_retry_executor_error(error)


def max_attempts_for_node(node: NodeSpec) -> int:
    """Normalize NodeSpec.retry.max_attempts to a runtime attempt count."""
    if node.retry is None:
        return 1
    return max(1, int(node.retry.max_attempts))


def run_with_retry(
    node: NodeSpec,
    invoke: Callable[[int], dict[str, Any]],
    *,
    retry_sink: RetrySink | None = None,
) -> dict[str, Any]:
    """Invoke a node executor with narrow ExecutorError retry semantics."""
    max_attempts = max_attempts_for_node(node)
    attempt = 1
    while True:
        try:
            return invoke(attempt)
        except ExecutorError as exc:
            if attempt >= max_attempts or not node_allows_retry(node, exc):
                raise
            attempt += 1
            if retry_sink is not None:
                retry_sink(node.id, attempt)


def _error_text(error: ExecutorError) -> str:
    return f"{error.message} {error.hint or ''}".lower()
