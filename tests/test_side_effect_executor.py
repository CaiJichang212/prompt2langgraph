"""Tests for side_effect approval interrupt flow."""

import json
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from prompt2langgraph.ir.models import (
    EdgeKind,
    EdgeSpec,
    ExecutorRef,
    ExecutorType,
    NodeSpec,
    PolicySpec,
    SecurityPolicy,
    StateSchema,
    StateSelector,
    TypeName,
    TypeSpec,
    WorkflowSpec,
)
from prompt2langgraph.runtime.runner import run_workflow

FIXTURES = Path(__file__).parent / "fixtures"


def load_workflow(name: str) -> WorkflowSpec:
    return WorkflowSpec.model_validate(json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def test_side_effect_approval_interrupt_creates_waiting_state():
    """Test that requires_approval=True side_effect node creates waiting state with interrupt."""
    workflow = load_workflow("side_effect_requires_approval.json")
    checkpointer = InMemorySaver()

    waiting = run_workflow(
        workflow,
        {"question": "hello"},
        thread_id="side-effect-test-thread",
        checkpointer=checkpointer,
    )

    assert waiting.status == "waiting"
    assert waiting.interrupt is not None
    assert waiting.interrupt.node_id == "record_effect"
    assert waiting.interrupt.kind == "side_effect_approval"
    assert waiting.output == {}


def test_side_effect_resume_approved_succeeds():
    """Test that approved resume payload allows side_effect to execute."""
    workflow = load_workflow("side_effect_requires_approval.json")
    checkpointer = InMemorySaver()

    waiting = run_workflow(
        workflow,
        {"question": "hello"},
        thread_id="side-effect-approve-thread",
        checkpointer=checkpointer,
    )

    assert waiting.status == "waiting"

    # Resume with approved decision
    resumed = run_workflow(
        workflow,
        {},
        thread_id="side-effect-approve-thread",
        resume_payload={"decision": "approved"},
        checkpointer=checkpointer,
    )

    assert resumed.status == "succeeded"
    assert resumed.thread_id == "side-effect-approve-thread"
    assert resumed.output == {"effect_result": "hello"}


def test_side_effect_resume_rejected_completes_with_rejected_output():
    """Test that rejected resume payload prevents side_effect execution."""
    workflow = load_workflow("side_effect_requires_approval.json")
    checkpointer = InMemorySaver()

    waiting = run_workflow(
        workflow,
        {"question": "hello"},
        thread_id="side-effect-reject-thread",
        checkpointer=checkpointer,
    )

    assert waiting.status == "waiting"

    # Resume with rejected decision
    resumed = run_workflow(
        workflow,
        {},
        thread_id="side-effect-reject-thread",
        resume_payload={"decision": "rejected", "reason": "manual reject"},
        checkpointer=checkpointer,
    )

    # When rejected, the node finishes but output keys are set to None
    # and rejection reason is stored in RunResult.side_effect_rejections
    assert resumed.status == "succeeded"
    assert resumed.thread_id == "side-effect-reject-thread"
    assert resumed.output.get("effect_result") is None
    assert resumed.side_effect_rejections.get("rejected") == "manual reject"


def test_side_effect_allowed_path_no_interrupt():
    """Test that allow_side_effects=True path still works without interrupt."""
    workflow = load_workflow("side_effect_allowed.json")

    result = run_workflow(workflow, {"question": "hello"})

    assert result.status == "succeeded"
    assert result.output == {"effect_result": "hello"}
    assert result.interrupt is None


def test_side_effect_idempotency_store_persists_successful_output(tmp_path: Path) -> None:
    from prompt2langgraph.runtime.side_effects import SideEffectIdempotencyStore

    path = tmp_path / "side_effects.json"
    store = SideEffectIdempotencyStore(path)
    key = ("workflow_a", "thread_a", "record_effect", "write-file")

    assert store.get_success(*key) is None
    store.record_success(*key, output={"effect_result": "done"})

    reloaded = SideEffectIdempotencyStore(path)
    assert reloaded.get_success(*key) == {"effect_result": "done"}


def test_side_effect_idempotency_skips_duplicate_success(tmp_path: Path) -> None:
    from prompt2langgraph.ir.models import ExecutorType, SecurityPolicy
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


def test_side_effect_idempotency_scope_includes_node_id(tmp_path: Path) -> None:
    from prompt2langgraph.registry.executors import ExecutorDefinition, ExecutorRegistry

    calls: list[str] = []

    def record_effect(inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        calls.append(inputs["value"])
        return {"value": inputs["value"]}

    workflow = WorkflowSpec(
        schema_version="0.1",
        workflow_id="side_effect_scope",
        name="Side Effect Scope",
        entrypoint="write_one",
        state_schema=StateSchema(
            input={"question": TypeSpec(type=TypeName.STRING)},
            output={
                "effect_one": TypeSpec(type=TypeName.STRING),
                "effect_two": TypeSpec(type=TypeName.STRING),
            },
            channels={
                "question": TypeSpec(type=TypeName.STRING),
                "effect_one": TypeSpec(type=TypeName.STRING),
                "effect_two": TypeSpec(type=TypeName.STRING),
            },
        ),
        nodes=[
            NodeSpec(
                id="write_one",
                kind="side_effect",
                executor=ExecutorRef(
                    ref="builtin.identity_transform",
                    type=ExecutorType.BUILTIN,
                ),
                inputs={"value": StateSelector(state_key="question")},
                outputs={"value": StateSelector(state_key="effect_one")},
                security=SecurityPolicy(idempotency_key="shared-key"),
            ),
            NodeSpec(
                id="write_two",
                kind="side_effect",
                executor=ExecutorRef(
                    ref="builtin.identity_transform",
                    type=ExecutorType.BUILTIN,
                ),
                inputs={"value": StateSelector(state_key="question")},
                outputs={"value": StateSelector(state_key="effect_two")},
                security=SecurityPolicy(idempotency_key="shared-key"),
            ),
        ],
        edges=[
            EdgeSpec(
                id="e1",
                source="write_one",
                target="write_two",
                kind=EdgeKind.LINEAR,
            )
        ],
        policies=PolicySpec(allow_side_effects=True),
    )
    registry = ExecutorRegistry(
        [
            ExecutorDefinition(
                ref="builtin.identity_transform",
                type=ExecutorType.BUILTIN,
                handler=record_effect,
            )
        ]
    )

    result = run_workflow(
        workflow,
        {"question": "hello"},
        thread_id="same-thread",
        state_store_dir=tmp_path / ".pt2lg-runtime",
        executors=registry,
    )

    assert result.status == "succeeded"
    assert result.output == {"effect_one": "hello", "effect_two": "hello"}
    assert calls == ["hello", "hello"]


def test_side_effect_idempotency_does_not_record_invalid_executor_output(
    tmp_path: Path,
) -> None:
    from prompt2langgraph.ir.models import ExecutorType, SecurityPolicy
    from prompt2langgraph.registry.executors import ExecutorDefinition, ExecutorRegistry

    workflow = load_workflow("side_effect_allowed.json")
    workflow.nodes[0].security = SecurityPolicy(idempotency_key="valid-output-only")
    calls: list[str] = []

    def invalid_write(inputs, params):
        calls.append("invalid")
        return {"wrong": inputs["value"]}

    def valid_write(inputs, params):
        calls.append("valid")
        return {"value": inputs["value"]}

    first = run_workflow(
        workflow,
        {"question": "bad"},
        thread_id="same-thread",
        state_store_dir=tmp_path / ".pt2lg-runtime",
        executors=ExecutorRegistry(
            [
                ExecutorDefinition(
                    ref="builtin.identity_transform",
                    type=ExecutorType.BUILTIN,
                    handler=invalid_write,
                )
            ]
        ),
    )
    second = run_workflow(
        workflow,
        {"question": "good"},
        thread_id="same-thread",
        state_store_dir=tmp_path / ".pt2lg-runtime",
        executors=ExecutorRegistry(
            [
                ExecutorDefinition(
                    ref="builtin.identity_transform",
                    type=ExecutorType.BUILTIN,
                    handler=valid_write,
                )
            ]
        ),
    )

    assert first.status == "failed"
    assert second.status == "succeeded"
    assert second.output == {"effect_result": "good"}
    assert calls == ["invalid", "valid"]


def test_side_effect_without_idempotency_key_is_not_retried() -> None:
    from prompt2langgraph.diagnostics.codes import E_LLM_001
    from prompt2langgraph.ir.models import ExecutorType, RetryPolicy
    from prompt2langgraph.registry.executors import (
        ExecutorDefinition,
        ExecutorError,
        ExecutorRegistry,
    )

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
    from prompt2langgraph.registry.executors import (
        ExecutorDefinition,
        ExecutorError,
        ExecutorRegistry,
    )

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


def test_run_workflow_accepts_audit_sink_and_records_idempotency_skip_event(
    tmp_path: Path,
) -> None:
    from prompt2langgraph.ir.models import ExecutorType, SecurityPolicy
    from prompt2langgraph.registry.executors import ExecutorDefinition, ExecutorRegistry

    class CollectingAuditSink:
        def __init__(self) -> None:
            self.records: list[Any] = []

        def write(self, record: Any) -> None:
            self.records.append(record)

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
    audit_sink = CollectingAuditSink()

    first = run_workflow(
        workflow,
        {"question": "hello"},
        thread_id="same-thread",
        state_store_dir=tmp_path / ".pt2lg-runtime",
        executors=registry,
        audit_sink=audit_sink,
    )
    second = run_workflow(
        workflow,
        {"question": "hello again"},
        thread_id="same-thread",
        state_store_dir=tmp_path / ".pt2lg-runtime",
        executors=registry,
        audit_sink=audit_sink,
    )

    assert first.status == "succeeded"
    assert second.status == "succeeded"
    assert calls == [1]
    assert any(
        record.event_type == "side_effect.skipped_by_idempotency" for record in audit_sink.records
    )


def test_side_effect_node_event_sequence_for_approval():
    """Test that node events are recorded correctly for approval flow."""
    workflow = load_workflow("side_effect_requires_approval.json")
    checkpointer = InMemorySaver()

    waiting = run_workflow(
        workflow,
        {"question": "hello"},
        thread_id="side-effect-events-thread",
        checkpointer=checkpointer,
    )

    event_types = [event.type for event in waiting.events]
    assert "run.started" in event_types
    assert "node.started" in event_types
    assert "node.interrupted" in event_types


def test_side_effect_node_event_sequence_after_approved_resume():
    """Test that node events are correct after approved resume."""
    workflow = load_workflow("side_effect_requires_approval.json")
    checkpointer = InMemorySaver()

    run_workflow(  # first run to create interrupt
        workflow,
        {"question": "hello"},
        thread_id="side-effect-resume-events-thread",
        checkpointer=checkpointer,
    )

    resumed = run_workflow(
        workflow,
        {},
        thread_id="side-effect-resume-events-thread",
        resume_payload={"decision": "approved"},
        checkpointer=checkpointer,
    )

    event_types = [event.type for event in resumed.events]
    assert "run.started" in event_types
    assert "run.resumed" in event_types
    assert "node.started" in event_types
    assert "node.finished" in event_types
    assert "run.finished" in event_types


def test_run_interrupt_kind_field_exists():
    """Test that RunInterrupt has kind field for human_gate."""
    workflow = load_workflow("conditional_human_gate.json")

    waiting = run_workflow(
        workflow,
        {"question": "hello", "confidence": 0.5},
        thread_id="human-gate-kind-test",
    )

    assert waiting.interrupt is not None
    assert waiting.interrupt.kind == "human_gate"


def test_side_effect_approval_interrupt_payload_contains_node_info():
    """Test that side_effect approval interrupt payload contains node info."""
    workflow = load_workflow("side_effect_requires_approval.json")
    checkpointer = InMemorySaver()

    waiting = run_workflow(
        workflow,
        {"question": "test payload"},
        thread_id="side-effect-payload-thread",
        checkpointer=checkpointer,
    )

    assert waiting.interrupt is not None
    assert waiting.interrupt.kind == "side_effect_approval"
    payload = waiting.interrupt.payload
    # Payload should contain node_id, executor_ref, action, inputs, params, idempotency_key
    assert "node_id" in payload
    assert payload["node_id"] == "record_effect"
    assert "executor_ref" in payload
    assert "action" in payload
    assert "inputs" in payload
    assert "params" in payload
    assert "idempotency_key" in payload


def test_side_effect_resume_rejected_event_sequence():
    """Test that rejected resume produces correct event sequence."""
    workflow = load_workflow("side_effect_requires_approval.json")
    checkpointer = InMemorySaver()

    waiting = run_workflow(
        workflow,
        {"question": "hello"},
        thread_id="side-effect-reject-events-thread",
        checkpointer=checkpointer,
    )
    assert waiting.status == "waiting"

    resumed = run_workflow(
        workflow,
        {},
        thread_id="side-effect-reject-events-thread",
        resume_payload={"decision": "rejected", "reason": "test reject"},
        checkpointer=checkpointer,
    )

    assert resumed.status == "succeeded"
    event_types = [event.type for event in resumed.events]
    assert "run.started" in event_types
    assert "run.resumed" in event_types
    assert "node.started" in event_types
    assert "node.finished" in event_types
    assert "run.finished" in event_types


def test_side_effect_unrecognized_decision_treated_as_rejected():
    """Test that unrecognized decision format is treated as rejected."""
    workflow = load_workflow("side_effect_requires_approval.json")
    checkpointer = InMemorySaver()

    waiting = run_workflow(
        workflow,
        {"question": "hello"},
        thread_id="side-effect-unrecognized-thread",
        checkpointer=checkpointer,
    )
    assert waiting.status == "waiting"

    # Resume with an unrecognized decision format
    resumed = run_workflow(
        workflow,
        {},
        thread_id="side-effect-unrecognized-thread",
        resume_payload={"unknown_key": "maybe"},
        checkpointer=checkpointer,
    )

    # Should complete with output keys set to None and rejection in side_effect_rejections
    assert resumed.status == "succeeded"
    assert resumed.output.get("effect_result") is None
    assert "rejected" in resumed.side_effect_rejections
