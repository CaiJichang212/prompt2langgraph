from __future__ import annotations

from prompt2langgraph.diagnostics.codes import (
    E_LLM_001,
    E_LLM_002,
    E_LLM_003,
    E_SEC_013,
    E_SEC_015,
    E_SIDE_008,
)
from prompt2langgraph.ir.models import ExecutorRef, ExecutorType, NodeSpec, RetryPolicy
from prompt2langgraph.registry.executors import ExecutorError
from prompt2langgraph.runtime.retry import run_with_retry, should_retry_executor_error


def test_retry_classifier_allows_llm_timeout() -> None:
    assert should_retry_executor_error(ExecutorError(E_LLM_001, "LLM call timed out"))


def test_retry_classifier_allows_retryable_llm_api_errors() -> None:
    assert should_retry_executor_error(ExecutorError(E_LLM_002, "LLM API error: 503 server error"))
    assert should_retry_executor_error(ExecutorError(E_LLM_002, "LLM API error: request timeout"))


def test_retry_classifier_rejects_non_retryable_llm_api_errors() -> None:
    assert not should_retry_executor_error(
        ExecutorError(E_LLM_002, "LLM API error: invalid api key")
    )
    assert not should_retry_executor_error(ExecutorError(E_LLM_003, "inputs must contain messages"))


def test_retry_classifier_allows_tool_timeout_only() -> None:
    assert should_retry_executor_error(ExecutorError(E_SEC_015, "tool 'slow' timed out after 1s"))
    assert not should_retry_executor_error(
        ExecutorError(E_SEC_015, "tool ref 'fake.missing' is not registered")
    )
    assert not should_retry_executor_error(
        ExecutorError(E_SEC_015, "tool ref 'fake.write' is not authorized")
    )


def test_retry_classifier_rejects_security_and_side_effect_errors() -> None:
    assert not should_retry_executor_error(ExecutorError(E_SEC_013, "model_client missing"))
    assert not should_retry_executor_error(ExecutorError(E_SIDE_008, "side effect rejected"))


def _retry_node(max_attempts: int | None) -> NodeSpec:
    return NodeSpec(
        id="retry_node",
        kind="llm",
        executor=ExecutorRef(ref="llm.qwen-plus", type=ExecutorType.LLM),
        retry=RetryPolicy(max_attempts=max_attempts) if max_attempts is not None else None,
    )


def test_run_with_retry_retries_until_success() -> None:
    calls: list[int] = []
    retries: list[tuple[str, int]] = []

    def invoke(attempt: int) -> dict[str, str]:
        calls.append(attempt)
        if attempt == 1:
            raise ExecutorError(E_LLM_001, "LLM call timed out")
        return {"answer": "ok"}

    result = run_with_retry(
        _retry_node(2),
        invoke,
        retry_sink=lambda node_id, attempt: retries.append((node_id, attempt)),
    )

    assert result == {"answer": "ok"}
    assert calls == [1, 2]
    assert retries == [("retry_node", 2)]


def test_run_with_retry_stops_at_max_attempts() -> None:
    calls: list[int] = []

    def invoke(attempt: int) -> dict[str, str]:
        calls.append(attempt)
        raise ExecutorError(E_LLM_001, "LLM call timed out")

    try:
        run_with_retry(_retry_node(3), invoke)
    except ExecutorError as exc:
        assert exc.code == E_LLM_001
    else:
        raise AssertionError("expected ExecutorError")

    assert calls == [1, 2, 3]


def test_run_with_retry_does_not_retry_non_retryable_error() -> None:
    calls: list[int] = []

    def invoke(attempt: int) -> dict[str, str]:
        calls.append(attempt)
        raise ExecutorError(E_LLM_003, "inputs must contain messages")

    try:
        run_with_retry(_retry_node(3), invoke)
    except ExecutorError as exc:
        assert exc.code == E_LLM_003
    else:
        raise AssertionError("expected ExecutorError")

    assert calls == [1]
