import json
from pathlib import Path

from prompt2langgraph.ir.models import ExecutorType, TypeName, TypeSpec, WorkflowSpec
from prompt2langgraph.registry.executors import ExecutorDefinition, ExecutorRegistry
from prompt2langgraph.runtime.runner import run_workflow


FIXTURES = Path(__file__).parent / "fixtures"


def load_workflow(name: str) -> WorkflowSpec:
    return WorkflowSpec.model_validate(json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def test_run_workflow_invokes_linear_llm_and_returns_declared_output() -> None:
    result = run_workflow(load_workflow("linear_llm.json"), {"question": "hello"})

    assert result.status == "succeeded"
    assert result.run_id.startswith("run_")
    assert result.thread_id.startswith("thread_")
    assert result.output == {"answer": "Answer: hello"}
    assert result.diagnostics == []
    assert [event.type for event in result.events] == [
        "run.started",
        "node.started",
        "node.finished",
        "run.finished",
    ]
    assert result.events[1].node_id == "compose"


def test_run_workflow_returns_validation_diagnostics_without_invoking() -> None:
    data = json.loads((FIXTURES / "linear_llm.json").read_text(encoding="utf-8"))
    data["nodes"][0]["executor"]["ref"] = "missing.executor"
    workflow = WorkflowSpec.model_validate(data)

    result = run_workflow(workflow, {"question": "hello"})

    assert result.status == "failed"
    assert result.output == {}
    assert any(diagnostic.code == "E_BIND_006" for diagnostic in result.diagnostics)


def test_run_workflow_rejects_missing_required_input_payload_key() -> None:
    result = run_workflow(load_workflow("linear_llm.json"), {})

    assert result.status == "failed"
    assert result.output == {}
    assert any(
        diagnostic.code == "E_SCHEMA_002" and diagnostic.location.state_key == "question"
        for diagnostic in result.diagnostics
    )


def test_run_workflow_wraps_runtime_exceptions_as_diagnostics() -> None:
    data = json.loads((FIXTURES / "linear_llm.json").read_text(encoding="utf-8"))
    data["nodes"][0]["params"] = {"template": "Answer: {missing}"}
    workflow = WorkflowSpec.model_validate(data)

    result = run_workflow(workflow, {"question": "hello"})

    assert result.status == "failed"
    assert result.output == {}
    assert any(diagnostic.code == "E_RUNTIME_010" for diagnostic in result.diagnostics)


def test_run_workflow_fails_when_executor_omits_declared_output() -> None:
    registry = ExecutorRegistry(
        [
            ExecutorDefinition(
                ref="builtin.echo_llm",
                type=ExecutorType.BUILTIN,
                input_schema={"question": TypeSpec(type=TypeName.STRING)},
                output_schema={"answer": TypeSpec(type=TypeName.STRING)},
                handler=lambda inputs, params: {},
            )
        ]
    )

    result = run_workflow(load_workflow("linear_llm.json"), {"question": "hello"}, executors=registry)

    assert result.status == "failed"
    assert result.output == {}
    assert any(diagnostic.code == "E_RUNTIME_010" and "answer" in diagnostic.hint for diagnostic in result.diagnostics)


def test_run_workflow_reports_actual_node_events_for_failed_node() -> None:
    data = json.loads((FIXTURES / "linear_llm.json").read_text(encoding="utf-8"))
    data["nodes"][0]["params"] = {"template": "Answer: {missing}"}
    workflow = WorkflowSpec.model_validate(data)

    result = run_workflow(workflow, {"question": "hello"})

    assert [event.type for event in result.events] == ["run.started", "node.started", "run.failed"]
    assert result.events[1].node_id == "compose"


def test_run_workflow_rejects_unsupported_edge_kind_as_target_diagnostic() -> None:
    result = run_workflow(load_workflow("conditional_human_gate.json"), {"question": "hello", "confidence": 0.5})

    assert result.status == "failed"
    assert result.output == {}
    assert any(diagnostic.code == "E_TARGET_009" for diagnostic in result.diagnostics)
