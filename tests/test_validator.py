import json
from pathlib import Path

from prompt2langgraph.ir.models import ExecutorType, TypeName
from prompt2langgraph.registry.builtins import (
    builtin_executor_registry,
    builtin_node_registry,
)
from prompt2langgraph.validate.validator import validate_workflow


FIXTURES = Path(__file__).parent / "fixtures"


def load_workflow(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_builtin_node_registry_contains_required_kinds() -> None:
    registry = builtin_node_registry()

    assert set(registry.kinds()) == {
        "llm",
        "tool",
        "retriever",
        "transform",
        "router",
        "human_gate",
        "join",
        "side_effect",
    }
    assert registry.get("side_effect").side_effect is True
    assert registry.get("llm").planner_enabled is True


def test_builtin_executor_registry_contains_required_executors() -> None:
    registry = builtin_executor_registry()

    assert set(registry.refs()) == {
        "builtin.echo_llm",
        "builtin.mock_retriever",
        "builtin.identity_transform",
        "builtin.route",
        "builtin.human_gate",
        "builtin.join",
    }
    assert registry.get("builtin.echo_llm").type is ExecutorType.BUILTIN
    assert registry.get("builtin.echo_llm").output_schema["answer"].type is TypeName.STRING


def test_builtin_echo_llm_formats_template_without_calling_llm() -> None:
    executor = builtin_executor_registry().get("builtin.echo_llm")

    result = executor.invoke(
        {"question": "hello"},
        {"template": "Answer: {question}"},
    )

    assert result == {"answer": "Answer: hello"}


def test_builtin_mock_retriever_returns_artifact_reference() -> None:
    executor = builtin_executor_registry().get("builtin.mock_retriever")

    result = executor.invoke({"question": "hello"}, {})

    assert result == {"docs_ref": "mock://retriever/hello"}


def test_builtin_identity_transform_returns_inputs() -> None:
    executor = builtin_executor_registry().get("builtin.identity_transform")

    result = executor.invoke({"value": {"nested": True}}, {})

    assert result == {"value": {"nested": True}}


def test_validator_accepts_valid_linear_ir() -> None:
    report = validate_workflow(load_workflow("linear_llm.json"))

    assert report.ok is True
    assert report.diagnostics == []


def test_validator_accepts_conditional_routes_as_reachable() -> None:
    report = validate_workflow(load_workflow("conditional_human_gate.json"))

    assert report.ok is True
    assert report.diagnostics == []


def test_validator_rejects_unknown_node_kind() -> None:
    report = validate_workflow(load_workflow("invalid_unknown_node.json"))

    assert report.ok is False
    assert any(item.code == "E_DEP_004" and item.location.node_id == "mystery" for item in report.diagnostics)


def test_validator_rejects_unknown_executor() -> None:
    workflow = load_workflow("linear_llm.json")
    workflow["nodes"][0]["executor"]["ref"] = "missing.executor"

    report = validate_workflow(workflow)

    assert report.ok is False
    assert any(item.code == "E_BIND_006" and item.location.node_id == "compose" for item in report.diagnostics)


def test_validator_rejects_executor_type_mismatch() -> None:
    workflow = load_workflow("linear_llm.json")
    workflow["nodes"][0]["executor"]["type"] = "llm"

    report = validate_workflow(workflow)

    assert report.ok is False
    assert any(item.code == "E_BIND_006" and item.location.node_id == "compose" for item in report.diagnostics)


def test_validator_rejects_missing_required_executor_input_mapping() -> None:
    workflow = load_workflow("linear_llm.json")
    workflow["nodes"][0]["inputs"] = {}

    report = validate_workflow(workflow)

    assert report.ok is False
    assert any(item.code == "E_TYPE_003" and item.location.node_id == "compose" for item in report.diagnostics)


def test_validator_rejects_missing_required_executor_output_mapping() -> None:
    workflow = load_workflow("linear_llm.json")
    workflow["nodes"][0]["outputs"] = {}

    report = validate_workflow(workflow)

    assert report.ok is False
    assert any(item.code == "E_TYPE_003" and item.location.node_id == "compose" for item in report.diagnostics)


def test_validator_rejects_type_mismatch() -> None:
    report = validate_workflow(load_workflow("invalid_type_mismatch.json"))

    assert report.ok is False
    assert any(item.code == "E_TYPE_003" and item.location.state_key == "question" for item in report.diagnostics)


def test_validator_rejects_loop_without_guard() -> None:
    report = validate_workflow(load_workflow("invalid_loop_without_guard.json"))

    assert report.ok is False
    assert any(item.code == "E_LOOP_005" and item.location.edge_id == "retry" for item in report.diagnostics)


def test_validator_rejects_route_conflict() -> None:
    report = validate_workflow(load_workflow("invalid_route_conflict.json"))

    assert report.ok is False
    assert any(item.code == "E_ROUTE_011" and item.location.node_id == "route" for item in report.diagnostics)


def test_validator_rejects_fanout_without_reducer() -> None:
    report = validate_workflow(load_workflow("invalid_fanout_without_reducer.json"))

    assert report.ok is False
    assert any(item.code == "E_REDUCER_012" and item.location.state_key == "results" for item in report.diagnostics)


def test_validator_rejects_graph_without_exit_path() -> None:
    workflow = load_workflow("linear_llm.json")
    workflow["workflow_id"] = "invalid_no_exit_path"
    workflow["name"] = "Invalid No Exit Path"
    workflow["edges"] = [
        {
            "id": "loop_forever",
            "source": "compose",
            "target": "compose",
            "kind": "loop",
            "loop_guard": {"max_iterations": 3},
        }
    ]

    report = validate_workflow(workflow)

    assert report.ok is False
    assert any(item.code == "E_SCHEMA_002" and item.location.node_id == "compose" for item in report.diagnostics)


def test_validator_rejects_unapproved_side_effect() -> None:
    workflow = load_workflow("linear_llm.json")
    workflow["workflow_id"] = "side_effect_unapproved"
    workflow["name"] = "Side Effect Unapproved"
    workflow["entrypoint"] = "send_email"
    workflow["nodes"] = [
        {
            "id": "send_email",
            "kind": "side_effect",
            "executor": {"ref": "builtin.identity_transform", "type": "builtin"},
            "inputs": {"value": {"state_key": "question"}},
            "outputs": {},
            "params": {},
        }
    ]

    report = validate_workflow(workflow)

    assert report.ok is False
    assert any(item.code == "E_SIDE_008" and item.location.node_id == "send_email" for item in report.diagnostics)
