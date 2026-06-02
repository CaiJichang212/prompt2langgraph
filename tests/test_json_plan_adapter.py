import json
from pathlib import Path

import pytest

from prompt2langgraph.adapters.base import AdapterParseError
from prompt2langgraph.adapters.json_plan import JSONPlanAdapter, json_plan_to_workflow_spec
from prompt2langgraph.compiler.langgraph_py import compile_workflow_to_graph
from prompt2langgraph.diagnostics.codes import E_REDUCER_012
from prompt2langgraph.ir.models import TypeName, WorkflowSpec
from prompt2langgraph.registry.builtins import builtin_executor_registry
from prompt2langgraph.runtime.runner import run_workflow
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


def test_json_plan_explicit_workflow_id_overrides_name_slug() -> None:
    plan = {
        "workflow_id": "explicit_workflow",
        "name": "Name That Would Slug Differently",
        "nodes": [{"id": "first", "kind": "llm", "executor": "builtin.echo_llm"}],
        "edges": [],
    }

    workflow = json_plan_to_workflow_spec(plan)

    assert workflow.workflow_id == "explicit_workflow"


def test_json_plan_without_workflow_id_keeps_name_slug_fallback() -> None:
    plan = {
        "name": "Name Slug Fallback",
        "nodes": [{"id": "first", "kind": "llm", "executor": "builtin.echo_llm"}],
        "edges": [],
    }

    workflow = json_plan_to_workflow_spec(plan)

    assert workflow.workflow_id == "name_slug_fallback"


@pytest.mark.parametrize("workflow_id", ["", "123bad", "bad-id", "bad id"])
def test_json_plan_reports_path_for_invalid_explicit_workflow_id(workflow_id: str) -> None:
    plan = {
        "workflow_id": workflow_id,
        "name": "Bad Workflow Id",
        "nodes": [{"id": "first", "kind": "llm", "executor": "builtin.echo_llm"}],
        "edges": [],
    }

    with pytest.raises(AdapterParseError) as exc_info:
        JSONPlanAdapter().parse(plan, source="bad_workflow_id.json")

    assert exc_info.value.source == "bad_workflow_id.json"
    assert exc_info.value.path == "workflow_id"


def test_json_plan_metadata_is_preserved() -> None:
    plan = {
        "workflow_id": "metadata_plan",
        "name": "Metadata Plan",
        "metadata": {"owner": "qa", "tags": ["phase1", "json-plan"]},
        "nodes": [{"id": "first", "kind": "llm", "executor": "builtin.echo_llm"}],
        "edges": [],
    }

    workflow = json_plan_to_workflow_spec(plan)

    assert workflow.metadata == {"owner": "qa", "tags": ["phase1", "json-plan"]}


def test_json_plan_reports_path_for_invalid_metadata() -> None:
    plan = {
        "workflow_id": "bad_metadata",
        "name": "Bad Metadata",
        "metadata": ["not", "an", "object"],
        "nodes": [{"id": "first", "kind": "llm", "executor": "builtin.echo_llm"}],
        "edges": [],
    }

    with pytest.raises(AdapterParseError) as exc_info:
        JSONPlanAdapter().parse(plan, source="bad_metadata.json")

    assert exc_info.value.source == "bad_metadata.json"
    assert exc_info.value.path == "metadata"


def test_json_plan_reports_path_for_null_metadata() -> None:
    plan = {
        "workflow_id": "null_metadata",
        "name": "Null Metadata",
        "metadata": None,
        "nodes": [{"id": "first", "kind": "llm", "executor": "builtin.echo_llm"}],
        "edges": [],
    }

    with pytest.raises(AdapterParseError) as exc_info:
        JSONPlanAdapter().parse(plan, source="null_metadata.json")

    assert exc_info.value.source == "null_metadata.json"
    assert exc_info.value.path == "metadata"


def test_json_plan_top_level_reducers_map_to_state_schema_reducers() -> None:
    plan = {
        "workflow_id": "top_level_reducers",
        "name": "Top Level Reducers",
        "inputs": {"items": {"type": "array", "item_type": {"type": "string"}}},
        "outputs": {"results": {"type": "array", "item_type": {"type": "string"}}},
        "nodes": [
            {
                "id": "split",
                "kind": "transform",
                "executor": "builtin.identity_transform",
                "inputs": {"value": "items"},
                "outputs": {"value": "items"},
            },
            {
                "id": "process",
                "kind": "transform",
                "executor": "builtin.identity_transform",
                "inputs": {"value": "item"},
                "outputs": {"value": "results"},
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
        "reducers": {"results": "append"},
    }

    workflow = json_plan_to_workflow_spec(plan)
    report = validate_workflow(workflow)

    assert workflow.state_schema.reducers["results"].value == "append"
    assert report.ok, f"validation failed: {report.diagnostics}"


def test_json_plan_accepts_matching_top_level_and_state_schema_reducers() -> None:
    plan = {
        "workflow_id": "matching_reducers",
        "name": "Matching Reducers",
        "nodes": [{"id": "first", "kind": "llm", "executor": "builtin.echo_llm"}],
        "edges": [],
        "state_schema": {"reducers": {"results": "append"}},
        "reducers": {"results": "append"},
    }

    workflow = json_plan_to_workflow_spec(plan)

    assert workflow.state_schema.reducers["results"].value == "append"


def test_json_plan_rejects_conflicting_reducer_locations() -> None:
    plan = {
        "workflow_id": "conflicting_reducers",
        "name": "Conflicting Reducers",
        "nodes": [{"id": "first", "kind": "llm", "executor": "builtin.echo_llm"}],
        "edges": [],
        "state_schema": {"reducers": {"results": "append"}},
        "reducers": {"results": "sum"},
    }

    with pytest.raises(AdapterParseError) as exc_info:
        JSONPlanAdapter().parse(plan, source="bad_reducers.json")

    assert exc_info.value.source == "bad_reducers.json"
    assert exc_info.value.path == "reducers"


def test_json_plan_reports_path_for_invalid_top_level_reducer_name() -> None:
    plan = {
        "workflow_id": "bad_top_level_reducer",
        "name": "Bad Top Level Reducer",
        "nodes": [{"id": "first", "kind": "llm", "executor": "builtin.echo_llm"}],
        "edges": [],
        "reducers": {"results": "unsupported"},
    }

    with pytest.raises(AdapterParseError) as exc_info:
        JSONPlanAdapter().parse(plan, source="bad_top_level_reducer.json")

    assert exc_info.value.source == "bad_top_level_reducer.json"
    assert exc_info.value.path == "reducers"


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


def test_json_plan_preserves_policies_reducers_and_join_sources() -> None:
    plan = {
        "workflow_id": "join_plan",
        "name": "Join Plan",
        "entrypoint": "split",
        "inputs": {
            "items": {"type": "array", "item_type": {"type": "string"}},
            "item": "string",
        },
        "outputs": {
            "results": {"type": "array", "item_type": {"type": "string"}},
            "answer": "string",
        },
        "nodes": [
            {
                "id": "split",
                "kind": "transform",
                "executor": "builtin.identity_transform",
                "inputs": {"value": "items"},
                "outputs": {"value": "items"},
            },
            {
                "id": "process",
                "kind": "transform",
                "executor": "builtin.identity_transform",
                "inputs": {"value": "item"},
                "outputs": {"value": "results"},
            },
            {
                "id": "finish",
                "kind": "llm",
                "executor": "llm.qwen-plus",
                "inputs": {"question": "item"},
                "outputs": {"answer": "answer"},
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
            },
            {
                "from": "process",
                "to": "finish",
                "kind": "join",
                "join_sources": ["process", "split"],
            },
        ],
        "state_schema": {"reducers": {"results": "append"}},
        "policies": {"external_call": True, "allowed_models": ["qwen-plus"]},
    }

    workflow = json_plan_to_workflow_spec(plan)

    assert workflow.state_schema.reducers["results"].value == "append"
    assert workflow.policies.external_call is True
    assert workflow.policies.allowed_models == ["qwen-plus"]
    join_edge = next(edge for edge in workflow.edges if edge.kind.value == "join")
    assert join_edge.join_sources == ["process", "split"]


def test_json_plan_fanout_fixture_validates_compiles_and_runs() -> None:
    fixture = Path("tests/fixtures/json_plan_fanout_run.json")
    plan = json.loads(fixture.read_text(encoding="utf-8"))

    workflow = json_plan_to_workflow_spec(plan)
    report = validate_workflow(workflow)
    graph = compile_workflow_to_graph(workflow, builtin_executor_registry())
    result = run_workflow(workflow, {"items": ["alpha", "beta"]})

    assert report.ok, f"validation failed: {report.diagnostics}"
    assert graph is not None
    assert result.status == "succeeded"
    assert result.output["results"] == ["alpha", "beta"]


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
    assert exc_info.value.line is None
    assert exc_info.value.column is None
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


def test_json_plan_adapter_reports_path_for_invalid_join_sources() -> None:
    plan = {
        "name": "Bad Join Sources",
        "nodes": [
            {"id": "first", "kind": "llm", "executor": "builtin.echo_llm"},
            {"id": "second", "kind": "llm", "executor": "builtin.echo_llm"},
        ],
        "edges": [
            {
                "from": "first",
                "to": "second",
                "kind": "join",
                "join_sources": "first",
            }
        ],
    }

    with pytest.raises(AdapterParseError) as exc_info:
        JSONPlanAdapter().parse(plan, source="bad_join_sources.json")

    assert exc_info.value.source == "bad_join_sources.json"
    assert exc_info.value.path == "edges[0].join_sources"


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
