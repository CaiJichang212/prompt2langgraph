import pytest

from prompt2langgraph.adapters.base import AdapterParseError
from prompt2langgraph.adapters.json_plan import JSONPlanAdapter, json_plan_to_workflow_spec
from prompt2langgraph.diagnostics.codes import E_REDUCER_012
from prompt2langgraph.ir.models import TypeName, WorkflowSpec
from prompt2langgraph.validate.validator import validate_workflow


def test_json_plan_adapter_normalizes_simplified_plan_to_workflow_spec() -> None:
    plan = {
        "name": "Research Answer",
        "inputs": {"question": "string"},
        "outputs": {"answer": "string"},
        "nodes": [
            {"id": "retrieve", "kind": "retriever", "executor": "builtin.mock_retriever"},
            {"id": "answer", "kind": "llm", "executor": "builtin.echo_llm"},
        ],
        "edges": [
            {"from": "retrieve", "to": "answer"},
        ],
    }

    workflow = json_plan_to_workflow_spec(plan)

    assert isinstance(workflow, WorkflowSpec)
    assert workflow.schema_version == "0.1"
    assert workflow.workflow_id == "research_answer"
    assert workflow.entrypoint == "retrieve"
    assert workflow.state_schema.input["question"].type is TypeName.STRING
    assert workflow.state_schema.output["answer"].type is TypeName.STRING

    retrieve = next(node for node in workflow.nodes if node.id == "retrieve")
    answer = next(node for node in workflow.nodes if node.id == "answer")

    assert retrieve.executor.ref == "builtin.mock_retriever"
    assert retrieve.inputs["question"].state_key == "question"
    assert retrieve.outputs["docs_ref"].state_key == "docs_ref"
    assert answer.executor.ref == "builtin.echo_llm"
    assert answer.inputs["question"].state_key == "question"
    assert answer.outputs["answer"].state_key == "answer"
    assert workflow.edges[0].source == "retrieve"
    assert workflow.edges[0].target == "answer"
    assert workflow.edges[0].kind.value == "linear"
    assert workflow.state_schema.channels["docs_ref"].type is TypeName.ARTIFACT_REF


def test_json_plan_adapter_infers_entrypoint_from_root_node_not_list_order() -> None:
    plan = {
        "name": "Research Answer",
        "inputs": {"question": "string"},
        "outputs": {"answer": "string"},
        "nodes": [
            {"id": "answer", "kind": "llm", "executor": "builtin.echo_llm"},
            {"id": "retrieve", "kind": "retriever", "executor": "builtin.mock_retriever"},
        ],
        "edges": [{"from": "retrieve", "to": "answer"}],
    }

    workflow = json_plan_to_workflow_spec(plan)

    assert workflow.entrypoint == "retrieve"


def test_json_plan_accepts_source_target_edge_aliases() -> None:
    plan = {
        "workflow_id": "alias_plan",
        "name": "Alias Plan",
        "entrypoint": "first",
        "nodes": [
            {"id": "first", "kind": "llm", "executor": "builtin.echo_llm"},
            {"id": "second", "kind": "transform", "executor": "builtin.identity_transform"},
        ],
        "edges": [
            {"id": "first_to_second", "source": "first", "target": "second", "kind": "linear"}
        ],
        "inputs": {"question": "string"},
        "outputs": {"answer": "string"},
    }

    workflow = json_plan_to_workflow_spec(plan)

    assert workflow.edges[0].source == "first"
    assert workflow.edges[0].target == "second"


def test_json_plan_conditional_edge_preserves_condition_expr_and_routes() -> None:
    plan = {
        "workflow_id": "conditional_plan",
        "name": "Conditional Plan",
        "entrypoint": "route",
        "inputs": {"question": "string", "confidence": "number"},
        "outputs": {"answer": "string"},
        "nodes": [
            {"id": "route", "kind": "router", "executor": "builtin.route"},
            {"id": "answer", "kind": "llm", "executor": "builtin.echo_llm"},
            {"id": "review", "kind": "human_gate", "executor": "builtin.human_gate"},
        ],
        "edges": [
            {
                "from": "route",
                "to": "answer",
                "kind": "conditional",
                "condition": {
                    "expr": "confidence >= 0.8",
                    "routes": {"true": "answer", "false": "review"},
                },
            }
        ],
    }

    workflow = json_plan_to_workflow_spec(plan)

    edge = workflow.edges[0]
    assert edge.kind.value == "conditional"
    assert edge.condition is not None
    assert edge.condition.expr == "confidence >= 0.8"
    assert edge.condition.routes == {"true": "answer", "false": "review"}


def test_json_plan_loop_edge_preserves_loop_guard_max_iterations() -> None:
    plan = {
        "workflow_id": "loop_plan",
        "name": "Loop Plan",
        "entrypoint": "refine",
        "inputs": {"question": "string"},
        "outputs": {"answer": "string"},
        "nodes": [
            {"id": "refine", "kind": "llm", "executor": "builtin.echo_llm"},
        ],
        "edges": [
            {
                "from": "refine",
                "to": "refine",
                "kind": "loop",
                "loop_guard": {"max_iterations": 3},
            }
        ],
    }

    workflow = json_plan_to_workflow_spec(plan)

    edge = workflow.edges[0]
    assert edge.kind.value == "loop"
    assert edge.loop_guard is not None
    assert edge.loop_guard.max_iterations == 3


def test_json_plan_fanout_edge_preserves_map_but_validation_requires_workflow_ir_reducer() -> None:
    plan = {
        "workflow_id": "fanout_plan",
        "name": "Fanout Plan",
        "entrypoint": "split",
        "inputs": {
            "items": {"type": "array", "item_type": {"type": "string"}},
        },
        "outputs": {
            "results": {"type": "array", "item_type": {"type": "string"}},
        },
        "nodes": [
            {
                "id": "split",
                "kind": "transform",
                "executor": "builtin.identity_transform",
                "inputs": {"value": "items"},
                "outputs": {"result": "items"},
            },
            {
                "id": "process",
                "kind": "transform",
                "executor": "builtin.identity_transform",
                "inputs": {"value": "item"},
                "outputs": {"result": "results"},
            },
        ],
        "edges": [
            {
                "from": "split",
                "to": "process",
                "kind": "fanout",
                "map": {
                    "items_state_key": "items",
                    "item_state_key": "item",
                    "result_state_key": "results",
                },
            }
        ],
    }

    workflow = json_plan_to_workflow_spec(plan)

    edge = workflow.edges[0]
    assert edge.kind.value == "fanout"
    assert edge.map is not None
    assert edge.map.items_state_key == "items"
    assert edge.map.item_state_key == "item"
    assert edge.map.result_state_key == "results"
    assert workflow.state_schema.reducers == {}

    report = validate_workflow(workflow)

    assert any(
        diagnostic.code == E_REDUCER_012
        and diagnostic.location is not None
        and diagnostic.location.state_key == "results"
        for diagnostic in report.diagnostics
    )


def test_json_plan_adapter_rejects_empty_nodes_with_clear_error() -> None:
    plan = {
        "name": "Empty Workflow",
        "inputs": {},
        "outputs": {},
        "nodes": [],
        "edges": [],
    }

    with pytest.raises(ValueError, match="nodes must contain at least one node"):
        json_plan_to_workflow_spec(plan)


def test_json_plan_adapter_reports_source_and_json_path_for_parse_errors() -> None:
    plan = {
        "name": "Bad Edge",
        "nodes": [{"id": "first", "kind": "llm", "executor": "builtin.echo_llm"}],
        "edges": [{"id": "missing_target", "from": "first"}],
    }

    with pytest.raises(AdapterParseError) as exc_info:
        JSONPlanAdapter().parse(plan, source="bad_plan.json")

    assert exc_info.value.source == "bad_plan.json"
    assert exc_info.value.path == "edges[0].to"
    assert '"to" or "target"' in str(exc_info.value)


def test_json_plan_adapter_reports_path_for_invalid_selector_mapping() -> None:
    for invalid_inputs in (["question"], []):
        plan = {
            "name": "Bad Selectors",
            "nodes": [
                {
                    "id": "first",
                    "kind": "llm",
                    "executor": "builtin.echo_llm",
                    "inputs": invalid_inputs,
                }
            ],
            "edges": [],
        }

        with pytest.raises(AdapterParseError) as exc_info:
            JSONPlanAdapter().parse(plan, source="bad_selectors.json")

        assert exc_info.value.source == "bad_selectors.json"
        assert exc_info.value.path == "nodes[0].inputs"


def test_json_plan_adapter_reports_path_for_empty_slug_name() -> None:
    plan = {
        "name": "!!!",
        "nodes": [{"id": "first", "kind": "llm", "executor": "builtin.echo_llm"}],
        "edges": [],
    }

    with pytest.raises(AdapterParseError) as exc_info:
        JSONPlanAdapter().parse(plan, source="bad_name.json")

    assert exc_info.value.source == "bad_name.json"
    assert exc_info.value.path == "name"


def test_json_plan_adapter_reports_path_for_invalid_edge_kind() -> None:
    plan = {
        "name": "Bad Edge Kind",
        "nodes": [
            {"id": "first", "kind": "llm", "executor": "builtin.echo_llm"},
            {"id": "second", "kind": "llm", "executor": "builtin.echo_llm"},
        ],
        "edges": [{"from": "first", "to": "second", "kind": "unsupported"}],
    }

    with pytest.raises(AdapterParseError) as exc_info:
        JSONPlanAdapter().parse(plan, source="bad_edge_kind.json")

    assert exc_info.value.source == "bad_edge_kind.json"
    assert exc_info.value.path == "edges[0].kind"


def test_json_plan_adapter_reports_parent_path_for_nested_edge_validation() -> None:
    plan = {
        "name": "Bad Condition",
        "nodes": [
            {"id": "first", "kind": "router", "executor": "builtin.route"},
            {"id": "second", "kind": "llm", "executor": "builtin.echo_llm"},
        ],
        "edges": [
            {
                "from": "first",
                "to": "second",
                "kind": "conditional",
                "condition": {"routes": {"true": "second"}},
            }
        ],
    }

    with pytest.raises(AdapterParseError) as exc_info:
        JSONPlanAdapter().parse(plan, source="bad_condition.json")

    assert exc_info.value.source == "bad_condition.json"
    assert exc_info.value.path == "edges[0].condition.expr"


def test_json_plan_adapter_rejects_ambiguous_entrypoint_without_unique_root() -> None:
    plan = {
        "name": "Ambiguous Workflow",
        "inputs": {"question": "string"},
        "outputs": {"answer": "string"},
        "nodes": [
            {"id": "retrieve", "kind": "retriever", "executor": "builtin.mock_retriever"},
            {"id": "draft", "kind": "llm", "executor": "builtin.echo_llm"},
        ],
        "edges": [],
    }

    with pytest.raises(ValueError, match="could not infer a unique entrypoint"):
        json_plan_to_workflow_spec(plan)
