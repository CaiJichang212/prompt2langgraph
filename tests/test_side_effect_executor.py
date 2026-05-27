"""Tests for side_effect approval interrupt flow."""

import json
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver

from prompt2langgraph.ir.models import WorkflowSpec
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
