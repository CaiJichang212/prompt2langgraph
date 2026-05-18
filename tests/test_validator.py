import json
from pathlib import Path

from prompt2langgraph.ir.models import ExecutorType, TypeName, TypeSpec, WorkflowSpec
from prompt2langgraph.registry.builtins import (
    builtin_executor_registry,
    builtin_node_registry,
)
from prompt2langgraph.registry.nodes import NodeDefinition, NodeRegistry
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


def test_compile_rejects_join_edge_as_unsupported_target_capability(tmp_path: Path) -> None:
    workflow = WorkflowSpec.model_validate(load_workflow("linear_llm.json"))
    data = workflow.model_dump(mode="json")
    data["nodes"].append(
        {
            "id": "finish",
            "kind": "transform",
            "executor": {"ref": "builtin.identity_transform", "type": "builtin"},
            "inputs": {"value": {"state_key": "answer"}},
            "outputs": {"value": {"state_key": "answer"}},
            "params": {},
        }
    )
    data["edges"] = [{"id": "unsupported_join", "source": "compose", "target": "finish", "kind": "join"}]
    workflow = WorkflowSpec.model_validate(data)

    from prompt2langgraph.runtime.artifacts import compile_workflow_to_artifacts

    report, output_dir = compile_workflow_to_artifacts(workflow, out_dir=tmp_path)

    assert report.ok is False
    assert not (output_dir / "workflow.lock.json").exists()
    assert any(item.code == "E_TARGET_009" for item in report.diagnostics)


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


def test_validator_accepts_guarded_loop_with_continuation() -> None:
    report = validate_workflow(load_workflow("loop_with_guard.json"))

    assert report.ok is True
    assert report.diagnostics == []


def test_validator_rejects_multiple_loop_edges_from_same_source() -> None:
    report = validate_workflow(load_workflow("invalid_loop_multiple_loop_edges_same_source.json"))

    assert report.ok is False
    assert any(item.code == "E_ROUTE_011" and item.location.node_id == "compose" for item in report.diagnostics)


def test_validator_rejects_multiple_loop_continuations_from_same_source() -> None:
    report = validate_workflow(load_workflow("invalid_loop_multiple_continuations.json"))

    assert report.ok is False
    assert any(item.code == "E_ROUTE_011" and item.location.node_id == "compose" for item in report.diagnostics)


def test_validator_rejects_route_conflict() -> None:
    report = validate_workflow(load_workflow("invalid_route_conflict.json"))

    assert report.ok is False
    assert any(item.code == "E_ROUTE_011" and item.location.node_id == "route" for item in report.diagnostics)


def test_validator_rejects_condition_expr_with_undeclared_state_key() -> None:
    workflow = load_workflow("conditional_human_gate.json")
    workflow["edges"][0]["condition"]["expr"] = "score < 0.75"

    report = validate_workflow(workflow)

    assert report.ok is False
    assert any(item.code == "E_SCHEMA_002" and item.location.state_key == "score" for item in report.diagnostics)


def test_validator_rejects_unsupported_condition_expr() -> None:
    workflow = load_workflow("conditional_human_gate.json")
    workflow["edges"][0]["condition"]["expr"] = "confidence between 0 and 1"

    report = validate_workflow(workflow)

    assert report.ok is False
    assert any(item.code == "E_ROUTE_011" and item.location.edge_id == "route_by_confidence" for item in report.diagnostics)


def test_validator_rejects_conditional_routes_without_true_and_false() -> None:
    workflow = load_workflow("conditional_human_gate.json")
    workflow["edges"][0]["condition"]["routes"] = {"yes": "compose", "no": "approval"}

    report = validate_workflow(workflow)

    assert report.ok is False
    assert any(item.code == "E_ROUTE_011" and item.location.edge_id == "route_by_confidence" for item in report.diagnostics)


def test_validator_rejects_fanout_without_reducer() -> None:
    report = validate_workflow(load_workflow("invalid_fanout_without_reducer.json"))

    assert report.ok is False
    assert any(item.code == "E_REDUCER_012" and item.location.state_key == "results" for item in report.diagnostics)


def test_validator_accepts_fanout_with_append_reducer() -> None:
    report = validate_workflow(load_workflow("fanout_map_reduce.json"))

    assert report.ok is True
    assert report.diagnostics == []


def test_validator_rejects_fanout_items_state_that_is_not_array() -> None:
    workflow = load_workflow("fanout_map_reduce.json")
    workflow["state_schema"]["channels"]["items"] = {"type": "string"}
    workflow["state_schema"]["input"]["items"] = {"type": "string"}

    report = validate_workflow(workflow)

    assert report.ok is False
    assert any(item.code == "E_TYPE_003" and item.location.state_key == "items" for item in report.diagnostics)


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


def test_builtin_node_definitions_expose_v01_contract_fields() -> None:
    node = builtin_node_registry().get("llm")

    assert node.description
    assert "template" in node.param_schema
    assert node.required_capabilities == ()
    assert node.default_timeout_s is not None


def test_validator_rejects_wrong_param_type() -> None:
    workflow = load_workflow("linear_llm.json")
    workflow["nodes"][0]["params"] = {"template": 123}

    report = validate_workflow(workflow)

    assert report.ok is False
    assert any(item.code == "E_TYPE_003" and item.location.node_id == "compose" for item in report.diagnostics)


def test_validator_rejects_array_param_item_type_mismatch() -> None:
    workflow = load_workflow("linear_llm.json")
    workflow["nodes"][0]["kind"] = "custom"
    workflow["nodes"][0]["params"] = {"tags": ["ok", 123]}
    nodes = NodeRegistry(
        [
            NodeDefinition(
                kind="custom",
                description="Custom node for validator tests.",
                param_schema={
                    "tags": TypeSpec(
                        type=TypeName.ARRAY,
                        item_type=TypeSpec(type=TypeName.STRING),
                    )
                },
            )
        ]
    )

    report = validate_workflow(workflow, nodes=nodes)

    assert report.ok is False
    assert any(
        item.code == "E_TYPE_003"
        and item.location.node_id == "compose"
        and item.location.path == "params.tags"
        for item in report.diagnostics
    )


def test_validator_rejects_object_param_property_type_mismatch() -> None:
    workflow = load_workflow("linear_llm.json")
    workflow["nodes"][0]["kind"] = "custom"
    workflow["nodes"][0]["params"] = {"options": {"retries": "three"}}
    nodes = NodeRegistry(
        [
            NodeDefinition(
                kind="custom",
                description="Custom node for validator tests.",
                param_schema={
                    "options": TypeSpec(
                        type=TypeName.OBJECT,
                        properties={"retries": TypeSpec(type=TypeName.INTEGER)},
                    )
                },
            )
        ]
    )

    report = validate_workflow(workflow, nodes=nodes)

    assert report.ok is False
    assert any(
        item.code == "E_TYPE_003"
        and item.location.node_id == "compose"
        and item.location.path == "params.options"
        for item in report.diagnostics
    )
