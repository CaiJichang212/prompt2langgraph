# v0.4 Phase 3B Runtime Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement v0.4 Phase 3B so `RetryPolicy`, side-effect idempotency, audit JSONL, and runtime metrics have minimal executable semantics.

**Architecture:** Keep Workflow IR unchanged except for using the existing `NodeSpec.retry` and `SecurityPolicy.idempotency_key` fields. Add focused runtime helpers for retry classification, observability, audit, and side-effect idempotency; wire them through the compiler node wrapper and runner without introducing 3C runtime config bundle behavior. Retry is implemented as a compiler wrapper around node executor invocation, not as LangGraph native retry.

**Tech Stack:** Python 3.12, Pydantic, LangGraph runtime, pytest, existing `ExecutorError`, `RunMetrics`, `ExternalCallRecord`, `side_effect_handler`, `run_workflow()`, and Typer CLI.

---

## Scope

This plan implements only v0.4 Phase 3B:

- `NodeSpec.retry.max_attempts` affects runtime execution.
- Retryable errors are explicit and narrow: LLM timeout (`E_LLM_001`), retryable LLM API errors (`E_LLM_002` with timeout/5xx/server wording), and tool timeout (`E_SEC_015` with `timed out` wording).
- Non-retryable errors include business/runtime output errors, missing model/tool clients, unauthorized or unregistered tools, invalid LLM input, and side-effect rejection.
- Side-effect retries require `security.idempotency_key`.
- Side-effect idempotency is scoped by `(workflow_id, thread_id, idempotency_key)` and records successful raw executor output.
- A repeated side-effect with an already successful idempotency key returns the stored raw output and does not invoke the executor again.
- Audit writes JSONL records to `.pt2lg-runtime/audit.log.jsonl` when `run_workflow()` receives `state_store_dir`.
- Audit records contain only safe metadata fields: `run_id`, `thread_id`, `workflow_id`, `node_id`, `event_type`, `status`, `latency_ms`, `error_code`, `timestamp`, and optional `retry_count`.
- Runtime metrics report per-run `retry_count`, `tool_call_count`, `call_count`, and `total_latency_ms`; external call records include per-call latency and status.

This plan does not implement Phase 3A CLI tool module loading, Phase 3C runtime config bundle, LangGraph native retry policies, complete provider token accounting, distributed idempotency storage, full observability dashboards, arbitrary payload auditing, or LangChain Tool execution.

## Current Source Facts

- `RetryPolicy` already exists with `max_attempts: int = 1` in `src/prompt2langgraph/ir/models.py`.
- `NodeSpec.retry` already exists and is parsed by Pydantic and the JSON plan adapter.
- `SecurityPolicy.idempotency_key` already exists.
- `side_effect_handler()` currently interrupts for `requires_approval` or `idempotency_key`, then returns an internal approval signal.
- `compile_workflow_to_graph()` builds every node through `_node_wrapper()`, which is the right place to apply wrapper retry and side-effect idempotency.
- `run_workflow()` already creates `run_id`, `thread_id`, runtime events, `external_calls`, and `RunMetrics`.
- `RunMetrics` already includes `retry_count`, `tool_call_count`, `call_count`, and `total_latency_ms`.
- `ExternalCallRecord` already includes `node_id`, `executor_ref`, `model`, `latency_ms`, `token_count`, `status`, and `error_code`.
- CLI `run` and `resume` already pass `state_store_dir=_runtime_state_store_dir(workflow_json)`, where bundle workflows use `<bundle_dir>/.pt2lg-runtime` and non-bundle workflows use `Path.cwd() / ".pt2lg-runtime"`.

## File Structure

- Create `src/prompt2langgraph/runtime/retry.py`: retry classification and retry execution helper.
- Create `src/prompt2langgraph/runtime/observability.py`: runtime metrics collector and safe external call record creation.
- Create `src/prompt2langgraph/runtime/audit.py`: JSONL audit event model and file sink.
- Create `src/prompt2langgraph/runtime/side_effects.py`: side-effect idempotency record and JSON-backed store.
- Modify `src/prompt2langgraph/compiler/langgraph_py.py`: wrap executor invocation with retry, emit latency-aware call records, and use side-effect idempotency store.
- Modify `src/prompt2langgraph/runtime/runner.py`: create observability/audit/idempotency helpers and include aggregated metrics in all results.
- Modify `src/prompt2langgraph/runtime/events.py`: add optional safe fields to `ExternalCallRecord` if needed by tests.
- Modify `src/prompt2langgraph/runtime/__init__.py`: export new runtime helpers only if this file already exports runtime API; otherwise leave it unchanged.
- Modify `tests/test_runtime_retry.py`: retry classifier and helper tests.
- Modify `tests/test_langgraph_compiler.py`: compiler-level retry behavior tests.
- Modify `tests/test_runner.py`: metrics aggregation and audit wiring tests.
- Modify `tests/test_side_effect_executor.py`: idempotency and side-effect retry tests.
- Modify `tests/test_cli.py`: CLI audit file regression.
- Modify `README.md`, `AGENTS.md`, `CLAUDE.md`, and `docs/prompt2langgraph-v0.4-开发计划文档.md`: document 3B status after tests pass.

## Execution Rules

- Do not modify `pyproject.toml`, lock files, or CI configuration.
- Do not commit unless the user explicitly approves commits in the current execution session. If commits are not allowed, complete the task worktree changes and record that the commit step was skipped.
- Keep 3A and untracked plan/document files intact. Do not delete, reset, or overwrite unrelated user changes.
- Run focused tests after each task and broader regression at the end.

**Execution status:** Phase 3B implementation and verification are complete in the
working tree. Commit steps were intentionally skipped because the user has not
approved `git commit` in this session.

---

### Task 1: Add Retry Classifier

**Files:**
- Create: `src/prompt2langgraph/runtime/retry.py`
- Create: `tests/test_runtime_retry.py`

- [x] **Step 1: Write failing retry classifier tests**

Create `tests/test_runtime_retry.py`:

```python
from __future__ import annotations

from prompt2langgraph.diagnostics.codes import (
    E_LLM_001,
    E_LLM_002,
    E_LLM_003,
    E_SEC_013,
    E_SEC_015,
    E_SIDE_008,
)
from prompt2langgraph.registry.executors import ExecutorError
from prompt2langgraph.runtime.retry import should_retry_executor_error


def test_retry_classifier_allows_llm_timeout() -> None:
    assert should_retry_executor_error(ExecutorError(E_LLM_001, "LLM call timed out"))


def test_retry_classifier_allows_retryable_llm_api_errors() -> None:
    assert should_retry_executor_error(ExecutorError(E_LLM_002, "LLM API error: 503 server error"))
    assert should_retry_executor_error(ExecutorError(E_LLM_002, "LLM API error: request timeout"))


def test_retry_classifier_rejects_non_retryable_llm_api_errors() -> None:
    assert not should_retry_executor_error(ExecutorError(E_LLM_002, "LLM API error: invalid api key"))
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
```

- [x] **Step 2: Run retry tests and verify they fail**

Run:

```bash
uv run pytest tests/test_runtime_retry.py -v
```

Expected: fails with `ModuleNotFoundError: No module named 'prompt2langgraph.runtime.retry'`.

- [x] **Step 3: Implement retry classifier**

Create `src/prompt2langgraph/runtime/retry.py`:

```python
"""Runtime retry policy helpers."""

from __future__ import annotations

from prompt2langgraph.diagnostics.codes import E_LLM_001, E_LLM_002, E_SEC_015
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


def should_retry_executor_error(error: ExecutorError) -> bool:
    """Return True only for runtime errors that are safe to retry by default."""
    if error.code == E_LLM_001:
        return True
    if error.code == E_LLM_002:
        message = f"{error.message} {error.hint or ''}".lower()
        return any(marker in message for marker in _RETRYABLE_LLM_API_MARKERS)
    if error.code == E_SEC_015:
        message = f"{error.message} {error.hint or ''}".lower()
        return "timed out" in message or "timeout" in message
    return False
```

- [x] **Step 4: Run retry tests**

Run:

```bash
uv run pytest tests/test_runtime_retry.py -v
```

Expected: all tests in `tests/test_runtime_retry.py` pass.

- [x] **Step 5: Commit retry classifier** — skipped; commit not approved.

If commits are approved, run:

```bash
git add src/prompt2langgraph/runtime/retry.py tests/test_runtime_retry.py
git commit -m "feat: add runtime retry classifier"
```

Expected: commit succeeds. If commits are not approved, skip this step and leave the files unstaged or staged according to the user's instruction.

---

### Task 2: Add Retry Execution Helper Tests

**Files:**
- Modify: `tests/test_runtime_retry.py`
- Modify: `src/prompt2langgraph/runtime/retry.py`

- [x] **Step 1: Add failing helper tests**

Append to `tests/test_runtime_retry.py`:

```python
from prompt2langgraph.ir.models import (
    ExecutorRef,
    ExecutorType,
    NodeSpec,
    RetryPolicy,
)


def _retry_node(max_attempts: int | None) -> NodeSpec:
    return NodeSpec(
        id="retry_node",
        kind="llm",
        executor=ExecutorRef(ref="llm.qwen-plus", type=ExecutorType.LLM),
        retry=RetryPolicy(max_attempts=max_attempts) if max_attempts is not None else None,
    )


def test_run_with_retry_retries_until_success() -> None:
    from prompt2langgraph.runtime.retry import run_with_retry

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
    from prompt2langgraph.runtime.retry import run_with_retry

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


def test_run_with_retry_does_not_retry_non_retryable_errors() -> None:
    from prompt2langgraph.runtime.retry import run_with_retry

    calls: list[int] = []

    def invoke(attempt: int) -> dict[str, str]:
        calls.append(attempt)
        raise ExecutorError(E_SEC_015, "tool ref 'fake.missing' is not registered")

    try:
        run_with_retry(_retry_node(3), invoke)
    except ExecutorError as exc:
        assert exc.code == E_SEC_015
    else:
        raise AssertionError("expected ExecutorError")

    assert calls == [1]
```

- [x] **Step 2: Run helper tests**

Run:

```bash
uv run pytest tests/test_runtime_retry.py -v
```

Expected: fails with `ImportError` because `run_with_retry` is not implemented yet.

- [x] **Step 3: Ensure helper implementation is present**

Append these imports near the top of `src/prompt2langgraph/runtime/retry.py`:

```python
from collections.abc import Callable
from time import sleep
from typing import TypeVar

from prompt2langgraph.ir.models import NodeSpec
```

Add this type variable after imports:

```python
T = TypeVar("T")
```

Add these helpers after `should_retry_executor_error()`:

```python
def max_attempts_for_node(node: NodeSpec) -> int:
    """Normalize NodeSpec.retry.max_attempts to a runtime attempt count."""
    if node.retry is None:
        return 1
    return max(1, int(node.retry.max_attempts))


def run_with_retry(
    node: NodeSpec,
    invoke: Callable[[int], T],
    *,
    retry_sink: Callable[[str, int], None] | None = None,
    sleep_s: float = 0.0,
) -> T:
    """Run a node executor with the node's retry policy.

    The callable receives the 1-based attempt number. Only ExecutorError values
    classified by should_retry_executor_error() are retried.
    """
    max_attempts = max_attempts_for_node(node)
    attempt = 1
    while True:
        try:
            return invoke(attempt)
        except ExecutorError as exc:
            if attempt >= max_attempts or not should_retry_executor_error(exc):
                raise
            attempt += 1
            if retry_sink is not None:
                retry_sink(node.id, attempt)
            if sleep_s > 0:
                sleep(sleep_s)
```

- [x] **Step 4: Run helper tests again**

Run:

```bash
uv run pytest tests/test_runtime_retry.py -v
```

Expected: all retry tests pass.

- [x] **Step 5: Commit retry helper tests** — skipped; commit not approved.

If commits are approved, run:

```bash
git add src/prompt2langgraph/runtime/retry.py tests/test_runtime_retry.py
git commit -m "test: cover runtime retry helper"
```

Expected: commit succeeds if there are new changes. If Task 1 already committed the helper and this task only added tests, commit only the test file.

---

### Task 3: Wire Retry Through Compiler Node Execution

**Files:**
- Modify: `src/prompt2langgraph/compiler/langgraph_py.py`
- Modify: `tests/test_langgraph_compiler.py`
- Modify: `tests/test_runner.py`

- [x] **Step 1: Add compiler retry integration tests**

Append to `tests/test_langgraph_compiler.py`:

```python
def test_node_wrapper_retries_retryable_executor_error() -> None:
    from prompt2langgraph.diagnostics.codes import E_LLM_001
    from prompt2langgraph.ir.models import (
        ExecutorRef,
        ExecutorType,
        NodeSpec,
        RetryPolicy,
    )
    from prompt2langgraph.registry.executors import (
        ExecutorDefinition,
        ExecutorError,
        ExecutorRegistry,
    )
    from prompt2langgraph.compiler.langgraph_py import _node_wrapper

    calls: list[int] = []
    retries: list[tuple[str, int]] = []

    def flaky(inputs, params):
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            raise ExecutorError(E_LLM_001, "LLM call timed out")
        return {"answer": "ok"}

    node = NodeSpec(
        id="compose",
        kind="llm",
        executor=ExecutorRef(ref="test.flaky", type=ExecutorType.BUILTIN),
        outputs={"answer": {"state_key": "answer"}},
        retry=RetryPolicy(max_attempts=2),
    )
    wrapper = _node_wrapper(
        node,
        ExecutorRegistry(
            [ExecutorDefinition(ref="test.flaky", type=ExecutorType.BUILTIN, handler=flaky)]
        ),
        event_sink=None,
        loop_edges=[],
        reducers={},
        fanout_result_keys=set(),
        retry_sink=lambda node_id, attempt: retries.append((node_id, attempt)),
    )

    assert wrapper({}) == {"answer": "ok"}
    assert calls == [1, 2]
    assert retries == [("compose", 2)]


def test_node_wrapper_does_not_retry_non_retryable_executor_error() -> None:
    from prompt2langgraph.diagnostics.codes import E_SEC_015
    from prompt2langgraph.ir.models import (
        ExecutorRef,
        ExecutorType,
        NodeSpec,
        RetryPolicy,
    )
    from prompt2langgraph.registry.executors import (
        ExecutorDefinition,
        ExecutorError,
        ExecutorRegistry,
    )
    from prompt2langgraph.compiler.langgraph_py import _node_wrapper

    calls: list[int] = []

    def unauthorized(inputs, params):
        calls.append(len(calls) + 1)
        raise ExecutorError(E_SEC_015, "tool ref 'fake.write' is not authorized")

    node = NodeSpec(
        id="call_tool",
        kind="tool",
        executor=ExecutorRef(ref="test.unauthorized", type=ExecutorType.BUILTIN),
        outputs={"answer": {"state_key": "answer"}},
        retry=RetryPolicy(max_attempts=3),
    )
    wrapper = _node_wrapper(
        node,
        ExecutorRegistry(
            [
                ExecutorDefinition(
                    ref="test.unauthorized",
                    type=ExecutorType.BUILTIN,
                    handler=unauthorized,
                )
            ]
        ),
        event_sink=None,
        loop_edges=[],
        reducers={},
        fanout_result_keys=set(),
    )

    try:
        wrapper({})
    except ExecutorError as exc:
        assert exc.code == E_SEC_015
    else:
        raise AssertionError("expected ExecutorError")

    assert calls == [1]
```

- [x] **Step 2: Add runner retry metric test**

Append to `tests/test_runner.py`:

```python
def test_run_workflow_reports_retry_count_for_retryable_node() -> None:
    from prompt2langgraph.diagnostics.codes import E_LLM_001
    from prompt2langgraph.ir.models import ExecutorType, RetryPolicy
    from prompt2langgraph.registry.executors import ExecutorDefinition, ExecutorError, ExecutorRegistry

    workflow = load_workflow("linear_llm.json")
    workflow.nodes[0].retry = RetryPolicy(max_attempts=2)
    calls: list[int] = []

    def flaky(inputs, params):
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            raise ExecutorError(E_LLM_001, "LLM call timed out")
        return {"answer": "Answer: hello"}

    registry = ExecutorRegistry(
        [
            ExecutorDefinition(
                ref="builtin.echo_llm",
                type=ExecutorType.BUILTIN,
                handler=flaky,
            )
        ]
    )

    result = run_workflow(workflow, {"question": "hello"}, executors=registry)

    assert result.status == "succeeded"
    assert calls == [1, 2]
    assert result.metrics.retry_count == 1
```

- [x] **Step 3: Run retry integration tests and verify they fail**

Run:

```bash
uv run pytest tests/test_langgraph_compiler.py::test_node_wrapper_retries_retryable_executor_error tests/test_langgraph_compiler.py::test_node_wrapper_does_not_retry_non_retryable_executor_error tests/test_runner.py::test_run_workflow_reports_retry_count_for_retryable_node -v
```

Expected: fails because `_node_wrapper()` does not accept `retry_sink` and does not use `run_with_retry()`.

- [x] **Step 4: Update compiler signatures**

In `src/prompt2langgraph/compiler/langgraph_py.py`, update `compile_workflow_to_graph()` signature:

```python
def compile_workflow_to_graph(
    workflow: WorkflowSpec,
    executors: ExecutorRegistry,
    *,
    event_sink: NodeEventSink | None = None,
    checkpointer: Any | None = None,
    policies: PolicySpec | None = None,
    model_client: Any | None = None,
    tool_registry: Any | None = None,
    error_sink: Callable[[Any], None] | None = None,
    metrics_sink: Callable[[Any], None] | None = None,
    retry_sink: Callable[[str, int], None] | None = None,
):
```

In the `builder.add_node(... _node_wrapper(...))` call, add:

```python
                retry_sink=retry_sink,
```

Update `_node_wrapper()` signature:

```python
def _node_wrapper(
    node: NodeSpec,
    executors: ExecutorRegistry,
    event_sink: NodeEventSink | None,
    loop_edges: list[EdgeSpec],
    reducers: dict[str, ReducerName],
    fanout_result_keys: set[str],
    *,
    policies: PolicySpec | None = None,
    model_client: Any | None = None,
    tool_registry: Any | None = None,
    error_sink: Callable[[Any], None] | None = None,
    metrics_sink: Callable[[Any], None] | None = None,
    retry_sink: Callable[[str, int], None] | None = None,
):
```

- [x] **Step 5: Wrap executor invocation with retry**

In `invoke_node()`, replace the single `_invoke_executor(...)` call inside the `try:` block with:

```python
            from prompt2langgraph.runtime.retry import run_with_retry

            raw_outputs = run_with_retry(
                node,
                lambda attempt: _invoke_executor(
                    node,
                    executor,
                    inputs,
                    params,
                    policies=effective_policies,
                    model_client=model_client,
                    tool_registry=tool_registry,
                    metrics_sink=metrics_sink,
                ),
                retry_sink=retry_sink,
            )
```

Keep the existing `except ExecutorError` block unchanged after this replacement.

- [x] **Step 6: Wire retry sink in runner**

In `src/prompt2langgraph/runtime/runner.py`, before compiling the graph, add:

```python
    retry_count = 0

    def _retry_sink(node_id: str, attempt: int) -> None:
        nonlocal retry_count
        retry_count += 1
        events.append(
            RunEvent(
                type="node.retry",
                run_id=run_id,
                thread_id=thread_id,
                node_id=node_id,
                payload={"attempt": attempt},
            )
        )
```

Pass it to `compile_workflow_to_graph()`:

```python
            retry_sink=_retry_sink,
```

In every `RunMetrics(...)` construction in `run_workflow()` and `_failed_result()`, include `retry_count=retry_count` where `retry_count` is in scope. For `_failed_result()`, first update the signature:

```python
def _failed_result(
    run_id: str,
    thread_id: str,
    events: list[RunEvent],
    diagnostics: list[Diagnostic],
    started_at: float,
    external_calls: list[ExternalCallRecord] | None = None,
    retry_count: int = 0,
) -> RunResult:
```

Then add:

```python
            retry_count=retry_count,
```

to its `RunMetrics`.

For every `_failed_result(...)` call after `_retry_sink` is defined, pass `retry_count=retry_count`.

- [x] **Step 7: Run retry integration tests**

Run:

```bash
uv run pytest tests/test_runtime_retry.py tests/test_langgraph_compiler.py::test_node_wrapper_retries_retryable_executor_error tests/test_langgraph_compiler.py::test_node_wrapper_does_not_retry_non_retryable_executor_error tests/test_runner.py::test_run_workflow_reports_retry_count_for_retryable_node -v
```

Expected: all selected tests pass.

- [x] **Step 8: Commit compiler retry wiring** — skipped; commit not approved.

If commits are approved, run:

```bash
git add src/prompt2langgraph/compiler/langgraph_py.py src/prompt2langgraph/runtime/runner.py tests/test_langgraph_compiler.py tests/test_runner.py
git commit -m "feat: apply retry policy during node execution"
```

Expected: commit succeeds if commits are approved.

---

### Task 4: Add Runtime Observability Collector

**Files:**
- Create: `src/prompt2langgraph/runtime/observability.py`
- Modify: `src/prompt2langgraph/runtime/events.py`
- Modify: `src/prompt2langgraph/runtime/runner.py`
- Modify: `src/prompt2langgraph/compiler/langgraph_py.py`
- Modify: `tests/test_runner.py`
- Modify: `tests/test_integration_execution.py`

- [x] **Step 1: Add metrics aggregation tests**

Append to `tests/test_runner.py`:

```python
def test_run_workflow_metrics_count_tool_calls_and_latency() -> None:
    from prompt2langgraph.ir.models import ExecutorType
    from prompt2langgraph.registry.executors import ExecutorDefinition
    from prompt2langgraph.registry.builtins import builtin_executor_registry
    from prompt2langgraph.registry.tool_executor import ToolCallableRegistry

    workflow = load_workflow("tool_identity.json")
    workflow.policies.collect_metrics = True

    registry = builtin_executor_registry()
    registry.register(
        ExecutorDefinition(ref="fake.identity", type=ExecutorType.PYTHON_CALLABLE, dynamic=True)
    )
    workflow.nodes[0].executor.ref = "fake.identity"
    workflow.nodes[0].executor.type = ExecutorType.PYTHON_CALLABLE
    workflow.policies.allowed_tool_refs = ["fake.identity"]

    tools = ToolCallableRegistry()
    tools.register("fake.identity", lambda inputs, params: {"value": inputs["value"]})

    result = run_workflow(
        workflow,
        {"question": "hello"},
        executors=registry,
        tool_registry=tools,
    )

    assert result.status == "succeeded"
    assert result.metrics.call_count == 1
    assert result.metrics.tool_call_count == 1
    assert result.metrics.total_latency_ms is not None
    assert result.external_calls[0].latency_ms is not None
    assert result.external_calls[0].status == "succeeded"
```

- [x] **Step 2: Run metrics test and verify it fails**

Run:

```bash
uv run pytest tests/test_runner.py::test_run_workflow_metrics_count_tool_calls_and_latency -v
```

Expected: fails because current `ExternalCallRecord.latency_ms` is not set and `tool_call_count` stays 0.

- [x] **Step 3: Add optional attempt and category fields**

In `src/prompt2langgraph/runtime/events.py`, update `ExternalCallRecord`:

```python
class ExternalCallRecord(BaseModel):
    node_id: str
    executor_ref: str
    model: str | None = None
    latency_ms: float | None = None
    token_count: int | None = None
    status: Literal["succeeded", "failed"]
    error_code: str | None = None
    attempt: int = 1
    category: Literal["llm", "tool", "side_effect", "external"] = "external"
```

- [x] **Step 4: Create observability collector**

Create `src/prompt2langgraph/runtime/observability.py`:

```python
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
```

- [x] **Step 5: Emit latency-aware external call records**

In `src/prompt2langgraph/compiler/langgraph_py.py`, import `perf_counter` near the top:

```python
from time import perf_counter
```

In `_invoke_executor()`, measure dynamic LLM and dynamic tool execution on both success and failure.

For the LLM branch, replace:

```python
        result = llm_executor(inputs, params)
        if policies.collect_metrics and metrics_sink is not None:
            metrics_sink(
                ExternalCallRecord(
                    node_id=node.id,
                    executor_ref=executor.ref,
                    model=getattr(model_client, "model_name", None)
                    or getattr(model_client, "model", None),
                    status="succeeded",
                )
            )
        return result
```

with:

```python
        started_at = perf_counter()
        try:
            result = llm_executor(inputs, params)
        except ExecutorError as exc:
            if policies.collect_metrics and metrics_sink is not None:
                metrics_sink(
                    ExternalCallRecord(
                        node_id=node.id,
                        executor_ref=executor.ref,
                        model=getattr(model_client, "model_name", None)
                        or getattr(model_client, "model", None),
                        latency_ms=round((perf_counter() - started_at) * 1000, 3),
                        status="failed",
                        error_code=exc.code,
                        category="llm",
                    )
                )
            raise
        if policies.collect_metrics and metrics_sink is not None:
            metrics_sink(
                ExternalCallRecord(
                    node_id=node.id,
                    executor_ref=executor.ref,
                    model=getattr(model_client, "model_name", None)
                    or getattr(model_client, "model", None),
                    latency_ms=round((perf_counter() - started_at) * 1000, 3),
                    status="succeeded",
                    category="llm",
                )
            )
        return result
```

For the tool branch, replace:

```python
        result = tool_executor(inputs, params)
        if policies.collect_metrics and metrics_sink is not None:
            metrics_sink(
                ExternalCallRecord(
                    node_id=node.id,
                    executor_ref=executor.ref,
                    status="succeeded",
                )
            )
        return result
```

with:

```python
        started_at = perf_counter()
        try:
            result = tool_executor(inputs, params)
        except ExecutorError as exc:
            if policies.collect_metrics and metrics_sink is not None:
                metrics_sink(
                    ExternalCallRecord(
                        node_id=node.id,
                        executor_ref=executor.ref,
                        latency_ms=round((perf_counter() - started_at) * 1000, 3),
                        status="failed",
                        error_code=exc.code,
                        category="tool",
                    )
                )
            raise
        if policies.collect_metrics and metrics_sink is not None:
            metrics_sink(
                ExternalCallRecord(
                    node_id=node.id,
                    executor_ref=executor.ref,
                    latency_ms=round((perf_counter() - started_at) * 1000, 3),
                    status="succeeded",
                    category="tool",
                )
            )
        return result
```

In the side-effect builtin success record, add:

```python
                            category="side_effect",
```

In the `_node_wrapper()` `except ExecutorError as exc:` block, avoid duplicating dynamic LLM/tool failure records when `collect_metrics=True`.

Replace:

```python
            if error_sink is not None:
                error_sink(exc)
            if (
                error_sink is None
                and effective_policies.collect_metrics
                and metrics_sink is not None
            ):
                metrics_sink(
                    ExternalCallRecord(
                        node_id=node.id,
                        executor_ref=executor.ref,
                        status="failed",
                        error_code=exc.code,
                    )
                )
```

with:

```python
            from prompt2langgraph.ir.models import ExecutorType

            dynamic_external_failure = executor.dynamic and executor.type in {
                ExecutorType.LLM,
                ExecutorType.PYTHON_CALLABLE,
            }
            if error_sink is not None and not (
                effective_policies.collect_metrics and dynamic_external_failure
            ):
                error_sink(exc)
            if (
                effective_policies.collect_metrics
                and metrics_sink is not None
                and not dynamic_external_failure
            ):
                metrics_sink(
                    ExternalCallRecord(
                        node_id=node.id,
                        executor_ref=executor.ref,
                        status="failed",
                        error_code=exc.code,
                        category="external",
                    )
                )
```

- [x] **Step 6: Use collector in runner**

In `src/prompt2langgraph/runtime/runner.py`, initialize the collector immediately after the `events` list is created and before any validation or resume early-return path:

```python
    from prompt2langgraph.runtime.observability import RuntimeMetricsCollector

    metrics_collector = RuntimeMetricsCollector()
    external_calls = metrics_collector.external_calls
```

Do not leave collector initialization at the old `external_calls: list[ExternalCallRecord] = []` location because validation, resume, input, and target checks can return before that point.

Remove the old line:

```python
    external_calls: list[ExternalCallRecord] = []
```

In `_metrics_sink`, keep:

```python
    def _metrics_sink(record: ExternalCallRecord) -> None:
        metrics_collector.record_external_call(record)
```

In `_retry_sink`, replace the direct `retry_count += 1` increment from Task 3 with:

```python
        metrics_collector.record_retry()
```

Remove the local `retry_count` variable introduced in Task 3. For every `_failed_result(...)` call after the collector exists, pass:

```python
            retry_count=metrics_collector.retry_count,
```

Replace successful and waiting `RunMetrics(...)` construction with:

```python
            metrics=metrics_collector.metrics(duration_ms=_duration_ms(started_at)),
```

Update `_failed_result()` to accept `retry_count` until the next step, then replace its `RunMetrics(...)` with:

```python
        metrics=RunMetrics(
            duration_ms=_duration_ms(started_at),
            retry_count=retry_count,
            call_count=len(calls),
            tool_call_count=sum(1 for item in calls if item.category == "tool"),
            total_latency_ms=sum(r.latency_ms for r in calls if r.latency_ms is not None) or None,
            token_count=sum(r.token_count for r in calls if r.token_count is not None) or None,
        ),
```

- [x] **Step 7: Run metrics tests**

Run:

```bash
uv run pytest tests/test_runner.py::test_run_workflow_metrics_count_tool_calls_and_latency tests/test_integration_execution.py -v
```

Expected: selected runner test and integration tests pass.

- [x] **Step 8: Commit observability collector** — skipped; commit not approved.

If commits are approved, run:

```bash
git add src/prompt2langgraph/runtime/observability.py src/prompt2langgraph/runtime/events.py src/prompt2langgraph/runtime/runner.py src/prompt2langgraph/compiler/langgraph_py.py tests/test_runner.py tests/test_integration_execution.py
git commit -m "feat: aggregate runtime call metrics"
```

Expected: commit succeeds if commits are approved.

---

### Task 5: Add Audit JSONL Sink

**Files:**
- Create: `src/prompt2langgraph/runtime/audit.py`
- Modify: `src/prompt2langgraph/runtime/runner.py`
- Modify: `tests/test_runner.py`
- Modify: `tests/test_cli.py`

- [x] **Step 1: Add audit sink unit tests**

Append to `tests/test_runner.py`:

```python
def test_run_workflow_writes_audit_log_without_payloads(tmp_path: Path) -> None:
    workflow = load_workflow("linear_llm.json")
    runtime_dir = tmp_path / ".pt2lg-runtime"

    result = run_workflow(
        workflow,
        {"question": "secret question text"},
        state_store_dir=runtime_dir,
    )

    assert result.status == "succeeded"
    audit_path = runtime_dir / "audit.log.jsonl"
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert lines
    records = [json.loads(line) for line in lines]
    assert {record["event_type"] for record in records} >= {"run.started", "run.finished"}
    serialized = "\n".join(lines)
    assert "secret question text" not in serialized
    assert "api_key" not in serialized.lower()
```

- [x] **Step 2: Run audit test and verify it fails**

Run:

```bash
uv run pytest tests/test_runner.py::test_run_workflow_writes_audit_log_without_payloads -v
```

Expected: fails because no audit file is written.

- [x] **Step 3: Implement audit module**

Create `src/prompt2langgraph/runtime/audit.py`:

```python
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
```

- [x] **Step 4: Wire audit in runner**

In `src/prompt2langgraph/runtime/runner.py`, after `metrics_collector` is initialized near the top of `run_workflow()` and before validation, add:

```python
    from prompt2langgraph.runtime.audit import (
        AuditRecord,
        JsonlAuditSink,
        audit_path_for_state_store,
        utc_timestamp,
    )

    audit_path = audit_path_for_state_store(state_store_dir)
    audit_sink = JsonlAuditSink(audit_path) if audit_path is not None else None

    def _audit(
        event_type: str,
        status: str,
        *,
        node_id: str | None = None,
        latency_ms: float | None = None,
        error_code: str | None = None,
        retry_count: int = 0,
    ) -> None:
        if audit_sink is None:
            return
        audit_sink.write(
            AuditRecord(
                run_id=run_id,
                thread_id=thread_id,
                workflow_id=workflow.workflow_id,
                node_id=node_id,
                event_type=event_type,
                status=status,
                latency_ms=latency_ms,
                error_code=error_code,
                retry_count=retry_count,
                timestamp=utc_timestamp(),
            )
        )
```

Immediately after defining `_audit`, add:

```python
    _audit("run.started", "started")
```

In `_retry_sink`, after adding the `node.retry` event, add:

```python
        _audit("node.retry", "retry", node_id=node_id, retry_count=metrics_collector.retry_count)
```

Before returning waiting result, add:

```python
        _audit("run.waiting", "waiting", node_id=interrupt.node_id)
```

Before returning succeeded result, add:

```python
    _audit(
        "run.finished",
        "succeeded",
        latency_ms=_duration_ms(started_at),
        retry_count=metrics_collector.retry_count,
    )
```

In `_failed_result()`, do not add audit yet because it lacks sink context. Instead, for every failure return in `run_workflow()` after `_audit` exists, including validation, local state load, missing interrupt, input validation, target validation, and runtime invocation failures, call:

```python
        _audit(
            "run.failed",
            "failed",
            error_code=diagnostics[0].code if diagnostics else None,
            retry_count=metrics_collector.retry_count,
        )
```

immediately before returning `_failed_result(...)`.

- [x] **Step 5: Add CLI audit regression test**

Append to `tests/test_cli.py`:

```python
def test_cli_run_writes_audit_log_for_workflow_json(tmp_path: Path, monkeypatch) -> None:
    workflow_path = tmp_path / "workflow.json"
    workflow_path.write_text(
        (Path(__file__).parent / "fixtures" / "linear_llm.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        app,
        ["run", str(workflow_path), "--input", '{"question":"hello"}', "--json"],
    )

    assert result.exit_code == 0, result.output
    audit_path = tmp_path / ".pt2lg-runtime" / "audit.log.jsonl"
    assert audit_path.exists()
    assert "run.finished" in audit_path.read_text(encoding="utf-8")
```

Ensure `Path` is imported in `tests/test_cli.py`; if it is not already imported, add:

```python
from pathlib import Path
```

- [x] **Step 6: Run audit tests**

Run:

```bash
uv run pytest tests/test_runner.py::test_run_workflow_writes_audit_log_without_payloads tests/test_cli.py::test_cli_run_writes_audit_log_for_workflow_json -v
```

Expected: both tests pass.

- [x] **Step 7: Commit audit sink** — skipped; commit not approved.

If commits are approved, run:

```bash
git add src/prompt2langgraph/runtime/audit.py src/prompt2langgraph/runtime/runner.py tests/test_runner.py tests/test_cli.py
git commit -m "feat: write safe runtime audit log"
```

Expected: commit succeeds if commits are approved.

---

### Task 6: Add Side-Effect Idempotency Store

**Files:**
- Create: `src/prompt2langgraph/runtime/side_effects.py`
- Modify: `src/prompt2langgraph/compiler/langgraph_py.py`
- Modify: `src/prompt2langgraph/runtime/runner.py`
- Modify: `tests/test_side_effect_executor.py`

- [x] **Step 1: Add idempotency store unit test**

Append to `tests/test_side_effect_executor.py`:

```python
def test_side_effect_idempotency_store_persists_successful_output(tmp_path: Path) -> None:
    from prompt2langgraph.runtime.side_effects import SideEffectIdempotencyStore

    path = tmp_path / "side_effects.json"
    store = SideEffectIdempotencyStore(path)
    key = ("workflow_a", "thread_a", "write-file")

    assert store.get_success(*key) is None
    store.record_success(*key, output={"effect_result": "done"})

    reloaded = SideEffectIdempotencyStore(path)
    assert reloaded.get_success(*key) == {"effect_result": "done"}
```

- [x] **Step 2: Run idempotency store test and verify it fails**

Run:

```bash
uv run pytest tests/test_side_effect_executor.py::test_side_effect_idempotency_store_persists_successful_output -v
```

Expected: fails because `prompt2langgraph.runtime.side_effects` does not exist.

- [x] **Step 3: Implement idempotency store**

Create `src/prompt2langgraph/runtime/side_effects.py`:

```python
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
                    str(key): value
                    for key, value in data.items()
                    if isinstance(value, dict)
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
```

- [x] **Step 4: Run idempotency store test**

Run:

```bash
uv run pytest tests/test_side_effect_executor.py::test_side_effect_idempotency_store_persists_successful_output -v
```

Expected: test passes.

- [x] **Step 5: Add side-effect runtime idempotency test**

Append to `tests/test_side_effect_executor.py`:

```python
def test_side_effect_idempotency_skips_duplicate_success(tmp_path: Path) -> None:
    from prompt2langgraph.ir.models import ExecutorType
    from prompt2langgraph.ir.models import SecurityPolicy
    from prompt2langgraph.registry.executors import ExecutorDefinition, ExecutorRegistry

    workflow = load_workflow("side_effect_allowed.json")
    workflow.nodes[0].security = SecurityPolicy(idempotency_key="write-once")
    calls: list[int] = []

    def write_once(inputs, params):
        calls.append(len(calls) + 1)
        return {"value": inputs["value"]}

    registry = ExecutorRegistry(
        [
            ExecutorDefinition(
                ref="builtin.identity_transform",
                type=ExecutorType.BUILTIN,
                handler=write_once,
            )
        ]
    )

    first = run_workflow(
        workflow,
        {"question": "hello"},
        thread_id="same-thread",
        state_store_dir=tmp_path / ".pt2lg-runtime",
        executors=registry,
    )
    second = run_workflow(
        workflow,
        {"question": "hello again"},
        thread_id="same-thread",
        state_store_dir=tmp_path / ".pt2lg-runtime",
        executors=registry,
    )

    assert first.status == "succeeded"
    assert second.status == "succeeded"
    assert calls == [1]
    assert second.output == {"effect_result": "hello"}
```

- [x] **Step 6: Run side-effect runtime idempotency test and verify it fails**

Run:

```bash
uv run pytest tests/test_side_effect_executor.py::test_side_effect_idempotency_skips_duplicate_success -v
```

Expected: fails because compiler does not consult the idempotency store.

- [x] **Step 7: Wire idempotency store through runner and compiler**

In `src/prompt2langgraph/compiler/langgraph_py.py`, update `compile_workflow_to_graph()` signature:

```python
    side_effect_store: Any | None = None,
    workflow_id: str | None = None,
    thread_id: str | None = None,
```

Pass those values into `_node_wrapper(...)`:

```python
                side_effect_store=side_effect_store,
                workflow_id=workflow_id or workflow.workflow_id,
                thread_id=thread_id,
```

Update `_node_wrapper()` signature:

```python
    side_effect_store: Any | None = None,
    workflow_id: str | None = None,
    thread_id: str | None = None,
```

Inside `invoke_node()`, immediately after `params = node.params` and before the existing `if node.kind == "side_effect":` approval block, add:

```python
        idempotency_key = (
            node.security.idempotency_key
            if node.kind == "side_effect" and node.security is not None
            else None
        )
        idempotency_hit_outputs = None
        if (
            node.kind == "side_effect"
            and idempotency_key
            and side_effect_store is not None
            and workflow_id is not None
            and thread_id is not None
        ):
            stored_outputs = side_effect_store.get_success(
                workflow_id,
                thread_id,
                idempotency_key,
            )
            if stored_outputs is not None:
                idempotency_hit_outputs = stored_outputs
```

Then change the side-effect approval condition from:

```python
        if node.kind == "side_effect":
```

to:

```python
        if node.kind == "side_effect" and idempotency_hit_outputs is None:
```

This makes duplicate successful side effects skip both approval and executor invocation.

In the `try:` block where Task 3 added `raw_outputs = run_with_retry(...)`, replace that block with:

```python
            if idempotency_hit_outputs is not None:
                raw_outputs = idempotency_hit_outputs
            else:
                raw_outputs = run_with_retry(
                    node,
                    lambda attempt: _invoke_executor(
                        node,
                        executor,
                        inputs,
                        params,
                        policies=effective_policies,
                        model_client=model_client,
                        tool_registry=tool_registry,
                        metrics_sink=metrics_sink,
                    ),
                    retry_sink=retry_sink,
                )
                if (
                    node.kind == "side_effect"
                    and idempotency_key
                    and side_effect_store is not None
                    and workflow_id is not None
                    and thread_id is not None
                ):
                    side_effect_store.record_success(
                        workflow_id,
                        thread_id,
                        idempotency_key,
                        output=raw_outputs,
                    )
```

This replaces the `raw_outputs = run_with_retry(...)` block added in Task 3 and ensures successful side-effect output is recorded only after the executor succeeds.

In `src/prompt2langgraph/runtime/runner.py`, before `compile_workflow_to_graph(...)`, add:

```python
        from prompt2langgraph.runtime.side_effects import (
            SideEffectIdempotencyStore,
            side_effect_store_path,
        )

        side_effect_store = SideEffectIdempotencyStore(
            side_effect_store_path(state_store_dir)
        )
```

Pass these arguments to `compile_workflow_to_graph(...)`:

```python
            side_effect_store=side_effect_store,
            workflow_id=workflow.workflow_id,
            thread_id=thread_id,
```

- [x] **Step 8: Run side-effect idempotency tests**

Run:

```bash
uv run pytest tests/test_side_effect_executor.py::test_side_effect_idempotency_store_persists_successful_output tests/test_side_effect_executor.py::test_side_effect_idempotency_skips_duplicate_success -v
```

Expected: both tests pass.

- [x] **Step 9: Commit idempotency store** — skipped; commit not approved.

If commits are approved, run:

```bash
git add src/prompt2langgraph/runtime/side_effects.py src/prompt2langgraph/compiler/langgraph_py.py src/prompt2langgraph/runtime/runner.py tests/test_side_effect_executor.py
git commit -m "feat: persist side effect idempotency records"
```

Expected: commit succeeds if commits are approved.

---

### Task 7: Constrain Side-Effect Retry Semantics

**Files:**
- Modify: `src/prompt2langgraph/runtime/retry.py`
- Modify: `tests/test_side_effect_executor.py`

- [x] **Step 1: Add side-effect retry guard tests**

Append to `tests/test_side_effect_executor.py`:

```python
def test_side_effect_without_idempotency_key_is_not_retried() -> None:
    from prompt2langgraph.diagnostics.codes import E_LLM_001
    from prompt2langgraph.ir.models import ExecutorType, RetryPolicy
    from prompt2langgraph.registry.executors import ExecutorDefinition, ExecutorError, ExecutorRegistry

    workflow = load_workflow("side_effect_allowed.json")
    workflow.nodes[0].retry = RetryPolicy(max_attempts=3)
    workflow.nodes[0].security = None
    calls: list[int] = []

    def flaky_write(inputs, params):
        calls.append(len(calls) + 1)
        raise ExecutorError(E_LLM_001, "LLM call timed out")

    result = run_workflow(
        workflow,
        {"question": "hello"},
        executors=ExecutorRegistry(
            [
                ExecutorDefinition(
                    ref="builtin.identity_transform",
                    type=ExecutorType.BUILTIN,
                    handler=flaky_write,
                )
            ]
        ),
    )

    assert result.status == "failed"
    assert calls == [1]


def test_side_effect_with_idempotency_key_can_retry_retryable_error(tmp_path: Path) -> None:
    from prompt2langgraph.diagnostics.codes import E_LLM_001
    from prompt2langgraph.ir.models import ExecutorType, RetryPolicy, SecurityPolicy
    from prompt2langgraph.registry.executors import ExecutorDefinition, ExecutorError, ExecutorRegistry

    workflow = load_workflow("side_effect_allowed.json")
    workflow.nodes[0].retry = RetryPolicy(max_attempts=2)
    workflow.nodes[0].security = SecurityPolicy(idempotency_key="retry-write")
    calls: list[int] = []

    def flaky_write(inputs, params):
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            raise ExecutorError(E_LLM_001, "LLM call timed out")
        return {"value": inputs["value"]}

    result = run_workflow(
        workflow,
        {"question": "hello"},
        state_store_dir=tmp_path / ".pt2lg-runtime",
        executors=ExecutorRegistry(
            [
                ExecutorDefinition(
                    ref="builtin.identity_transform",
                    type=ExecutorType.BUILTIN,
                    handler=flaky_write,
                )
            ]
        ),
    )

    assert result.status == "succeeded"
    assert calls == [1, 2]
    assert result.metrics.retry_count == 1
```

- [x] **Step 2: Run side-effect retry tests and verify first one fails**

Run:

```bash
uv run pytest tests/test_side_effect_executor.py::test_side_effect_without_idempotency_key_is_not_retried tests/test_side_effect_executor.py::test_side_effect_with_idempotency_key_can_retry_retryable_error -v
```

Expected: first test fails if side-effect retry is unconstrained; second passes once idempotency store wiring is present.

- [x] **Step 3: Update retry helper to reject unsafe side-effect retry**

In `src/prompt2langgraph/runtime/retry.py`, add this helper:

```python
def node_allows_retry(node: NodeSpec, error: ExecutorError) -> bool:
    if node.kind == "side_effect":
        if node.security is None or not node.security.idempotency_key:
            return False
    return should_retry_executor_error(error)
```

In `run_with_retry()`, replace:

```python
            if attempt >= max_attempts or not should_retry_executor_error(exc):
```

with:

```python
            if attempt >= max_attempts or not node_allows_retry(node, exc):
```

- [x] **Step 4: Run side-effect retry tests**

Run:

```bash
uv run pytest tests/test_side_effect_executor.py::test_side_effect_without_idempotency_key_is_not_retried tests/test_side_effect_executor.py::test_side_effect_with_idempotency_key_can_retry_retryable_error -v
```

Expected: both tests pass.

- [x] **Step 5: Commit side-effect retry constraints** — skipped; commit not approved.

If commits are approved, run:

```bash
git add src/prompt2langgraph/runtime/retry.py tests/test_side_effect_executor.py
git commit -m "fix: require idempotency for side effect retry"
```

Expected: commit succeeds if commits are approved.

---

### Task 8: Preserve Audit and Metrics on Failure and Waiting Paths

**Files:**
- Modify: `src/prompt2langgraph/runtime/runner.py`
- Modify: `tests/test_runner.py`

- [x] **Step 1: Add failure audit and retry metrics test**

Append to `tests/test_runner.py`:

```python
def test_failed_retry_run_preserves_retry_metrics_and_audit(tmp_path: Path) -> None:
    from prompt2langgraph.diagnostics.codes import E_LLM_001
    from prompt2langgraph.ir.models import ExecutorType, RetryPolicy
    from prompt2langgraph.registry.executors import ExecutorDefinition, ExecutorError, ExecutorRegistry

    workflow = load_workflow("linear_llm.json")
    workflow.nodes[0].retry = RetryPolicy(max_attempts=2)

    def always_timeout(inputs, params):
        raise ExecutorError(E_LLM_001, "LLM call timed out")

    result = run_workflow(
        workflow,
        {"question": "hello"},
        state_store_dir=tmp_path / ".pt2lg-runtime",
        executors=ExecutorRegistry(
            [
                ExecutorDefinition(
                    ref="builtin.echo_llm",
                    type=ExecutorType.BUILTIN,
                    handler=always_timeout,
                )
            ]
        ),
    )

    assert result.status == "failed"
    assert result.metrics.retry_count == 1
    audit_text = (tmp_path / ".pt2lg-runtime" / "audit.log.jsonl").read_text(encoding="utf-8")
    assert "run.failed" in audit_text
    assert "E_RUNTIME_010" in audit_text


def test_waiting_run_writes_audit_without_full_interrupt_payload(tmp_path: Path) -> None:
    workflow = load_workflow("side_effect_requires_approval.json")
    result = run_workflow(
        workflow,
        {"question": "payload must not be audited"},
        state_store_dir=tmp_path / ".pt2lg-runtime",
    )

    assert result.status == "waiting"
    audit_text = (tmp_path / ".pt2lg-runtime" / "audit.log.jsonl").read_text(encoding="utf-8")
    assert "run.waiting" in audit_text
    assert "payload must not be audited" not in audit_text
```

- [x] **Step 2: Run failure/waiting audit tests**

Run:

```bash
uv run pytest tests/test_runner.py::test_failed_retry_run_preserves_retry_metrics_and_audit tests/test_runner.py::test_waiting_run_writes_audit_without_full_interrupt_payload -v
```

Expected: tests fail until all failure return paths call `_audit()` with safe metadata.

- [x] **Step 3: Audit every failure return after `_audit` exists**

In `src/prompt2langgraph/runtime/runner.py`, for each return of `_failed_result(...)` after `_audit` is defined, add this immediately before the return:

```python
        _audit(
            "run.failed",
            "failed",
            error_code=diagnostics[0].code if diagnostics else None,
            retry_count=metrics_collector.retry_count,
        )
```

For inline diagnostic lists where there is no `diagnostics` local variable, bind first:

```python
                diagnostics = [
                    Diagnostic(
                        code=E_RUNTIME_010,
                        severity="error",
                        message=f'no pending interrupt for thread "{thread_id}"',
                    )
                ]
                _audit(
                    "run.failed",
                    "failed",
                    error_code=diagnostics[0].code,
                    retry_count=metrics_collector.retry_count,
                )
                return _failed_result(
                    run_id,
                    thread_id,
                    events,
                    diagnostics,
                    started_at,
                    retry_count=metrics_collector.retry_count,
                )
```

Do the same for runtime invocation exceptions before returning `_failed_result(...)`.

- [x] **Step 4: Run failure/waiting audit tests**

Run:

```bash
uv run pytest tests/test_runner.py::test_failed_retry_run_preserves_retry_metrics_and_audit tests/test_runner.py::test_waiting_run_writes_audit_without_full_interrupt_payload -v
```

Expected: both tests pass.

- [x] **Step 5: Commit failure/waiting observability** — skipped; commit not approved.

If commits are approved, run:

```bash
git add src/prompt2langgraph/runtime/runner.py tests/test_runner.py
git commit -m "fix: preserve runtime observability on non-success paths"
```

Expected: commit succeeds if commits are approved.

---

### Task 9: Document Phase 3B Runtime Semantics

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Modify: `docs/prompt2langgraph-v0.4-开发计划文档.md`

- [x] **Step 1: Update README runtime section**

Add near the runtime execution documentation in `README.md`:

```markdown
### Runtime Retry, Metrics, and Audit

`NodeSpec.retry.max_attempts` enables a small wrapper retry policy during runtime
execution. The runtime retries only narrow transient failures: LLM timeout,
retryable LLM API errors that look like timeout/5xx/server failures, and tool
timeout. Security failures, missing model/tool clients, unregistered or
unauthorized tools, invalid LLM inputs, omitted outputs, and side-effect
rejections are not retried by default.

`side_effect` retry requires `security.idempotency_key`. Successful side-effect
execution is recorded by `(workflow_id, thread_id, idempotency_key)`, and a later
run with the same key returns the stored executor output without invoking the
executor again.

When CLI execution uses `.pt2lg-runtime`, the runtime writes safe audit metadata
to `.pt2lg-runtime/audit.log.jsonl`. Audit records do not include full input
payloads, API keys, secrets, full model responses, or full tool parameters.
```

- [x] **Step 2: Update AGENTS and CLAUDE**

Add equivalent concise notes to `AGENTS.md` and `CLAUDE.md`:

```markdown
- v0.4 3B implements wrapper retry for `NodeSpec.retry.max_attempts`; retryable errors are intentionally narrow: LLM timeout, retryable LLM API timeout/5xx/server failures, and tool timeout.
- Security errors, missing clients, unauthorized/unregistered tools, invalid LLM input, output contract errors, and side-effect rejection are not default retry targets.
- `side_effect` retry requires `security.idempotency_key`; successful side-effect output is stored by `(workflow_id, thread_id, idempotency_key)` and reused for duplicate executions.
- Runtime audit writes safe metadata to `.pt2lg-runtime/audit.log.jsonl` and must not include secrets, full payloads, API keys, full model responses, or sensitive tool parameters.
```

- [x] **Step 3: Update v0.4 development plan status**

In `docs/prompt2langgraph-v0.4-开发计划文档.md`, update the 3B sections to state:

```markdown
3B implementation status: minimal runtime retry, side-effect idempotency,
safe audit JSONL, and aggregate metrics are implemented. This does not imply
Phase 3C runtime config bundle support, distributed idempotency storage,
LangGraph native retry policy integration, or full provider token accounting.
```

Place this note under the 3B headings without marking 3C complete.

- [x] **Step 4: Run documentation grep checks**

Run:

```bash
rg -n "3B|retry|idempotency|audit|runtime config bundle|LangGraph native retry" README.md AGENTS.md CLAUDE.md docs/prompt2langgraph-v0.4-开发计划文档.md
```

Expected: output shows 3B documented and does not claim 3C runtime config bundle is implemented.

- [x] **Step 5: Commit documentation** — skipped; commit not approved.

If commits are approved, run:

```bash
git add README.md AGENTS.md CLAUDE.md docs/prompt2langgraph-v0.4-开发计划文档.md
git commit -m "docs: document v04 phase3b runtime semantics"
```

Expected: commit succeeds if commits are approved.

---

### Task 10: Focused and Full Regression

**Files:**
- Test: `tests/test_runtime_retry.py`
- Test: `tests/test_langgraph_compiler.py`
- Test: `tests/test_runner.py`
- Test: `tests/test_side_effect_executor.py`
- Test: `tests/test_tool_executor.py`
- Test: `tests/test_llm_executor.py`
- Test: `tests/test_integration_execution.py`
- Test: `tests/test_cli.py`

- [x] **Step 1: Run focused Phase 3B tests**

Run:

```bash
uv run pytest tests/test_runtime_retry.py tests/test_langgraph_compiler.py tests/test_runner.py tests/test_side_effect_executor.py -v
```

Expected: all focused 3B tests pass.

- [x] **Step 2: Run executor and integration regression**

Run:

```bash
uv run pytest tests/test_tool_executor.py tests/test_llm_executor.py tests/test_integration_execution.py tests/test_security_policy.py -v
```

Expected: all executor/security/integration tests pass.

- [x] **Step 3: Run CLI regression**

Run:

```bash
uv run pytest tests/test_cli.py -v
```

Expected: all CLI tests pass.

- [x] **Step 4: Run full test suite**

Run:

```bash
uv run pytest
```

Expected: full suite passes.

- [x] **Step 5: Commit final regression checkpoint** — skipped; commit not approved.

If commits are approved and regression changes were needed, run:

```bash
git add src/prompt2langgraph tests README.md AGENTS.md CLAUDE.md docs/prompt2langgraph-v0.4-开发计划文档.md
git commit -m "test: cover v04 phase3b runtime regression"
```

Expected: commit succeeds only if there are uncommitted changes from regression fixes and commits are approved.

---

## Final Verification Checklist

- [x] `uv run pytest tests/test_runtime_retry.py -v` passes.
- [x] `uv run pytest tests/test_langgraph_compiler.py -v` passes.
- [x] `uv run pytest tests/test_runner.py -v` passes.
- [x] `uv run pytest tests/test_side_effect_executor.py -v` passes.
- [x] `uv run pytest tests/test_tool_executor.py tests/test_llm_executor.py tests/test_integration_execution.py tests/test_security_policy.py -v` passes.
- [x] `uv run pytest tests/test_cli.py -v` passes.
- [x] `uv run pytest` passes.
- [x] Retryable LLM timeout errors retry up to `max_attempts`.
- [x] Retryable LLM API timeout/5xx/server errors retry up to `max_attempts`.
- [x] Tool timeout retries up to `max_attempts`.
- [x] Unauthorized/unregistered tools do not retry.
- [x] Missing model/tool clients do not retry.
- [x] Invalid LLM input and output contract errors do not retry.
- [x] Side-effect rejection does not retry.
- [x] Side-effect retry requires `security.idempotency_key`.
- [x] Duplicate side-effect idempotency key in the same workflow/thread returns stored output without executor invocation.
- [x] `.pt2lg-runtime/audit.log.jsonl` contains safe metadata and no full input payloads or secrets.
- [x] `RunMetrics.retry_count`, `tool_call_count`, `call_count`, and `total_latency_ms` are populated from runtime execution.
- [x] Documentation states 3B is implemented without implying 3C runtime config bundle is complete.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-02-v04-phase3b-runtime-semantics.md`. Two execution options:

1. Subagent-Driven (recommended) - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. Inline Execution - execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
