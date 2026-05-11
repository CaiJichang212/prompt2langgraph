import pytest

from prompt2langgraph.adapters.json_plan import json_plan_to_workflow_spec
from prompt2langgraph.ir.models import TypeName, WorkflowSpec


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
