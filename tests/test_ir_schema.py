import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from prompt2langgraph.diagnostics.report import Diagnostic, ValidationReport
from prompt2langgraph.ir.models import LoopGuard, TypeName, TypeSpec, WorkflowSpec
from prompt2langgraph.ir.normalize import normalize_workflow

FIXTURES = Path(__file__).parent / "fixtures"


def test_validation_report_ok_allows_warnings() -> None:
    report = ValidationReport(
        diagnostics=[
            Diagnostic(
                code="W_EXAMPLE",
                severity="warning",
                message="Example warning.",
            )
        ]
    )

    assert report.ok is True


def test_validation_report_ok_rejects_errors() -> None:
    report = ValidationReport(
        diagnostics=[
            Diagnostic(
                code="E_SCHEMA_002",
                severity="error",
                message="Example error.",
            )
        ]
    )

    assert report.ok is False


def test_loads_linear_llm_fixture_into_workflow_spec() -> None:
    workflow = WorkflowSpec.model_validate_json(
        (FIXTURES / "linear_llm.json").read_text(encoding="utf-8")
    )

    assert workflow.schema_version == "0.1"
    assert workflow.workflow_id == "linear_llm"
    assert workflow.entrypoint == "compose"
    assert workflow.state_schema.channels["question"].type is TypeName.STRING
    assert workflow.nodes[0].executor.ref == "builtin.echo_llm"


def test_loads_linear_retriever_llm_fixture_into_workflow_spec() -> None:
    workflow = WorkflowSpec.model_validate_json(
        (FIXTURES / "linear_retriever_llm.json").read_text(encoding="utf-8")
    )

    assert workflow.workflow_id == "linear_retriever_llm"
    assert workflow.state_schema.channels["docs_ref"].type is TypeName.ARTIFACT_REF
    assert [node.kind for node in workflow.nodes] == ["retriever", "transform", "llm"]
    assert [edge.kind.value for edge in workflow.edges] == ["linear", "linear"]


def test_type_spec_supports_messages_and_artifact_ref_channels() -> None:
    messages = TypeSpec(type=TypeName.MESSAGES)
    artifact = TypeSpec(type=TypeName.ARTIFACT_REF)

    assert messages.type is TypeName.MESSAGES
    assert artifact.type is TypeName.ARTIFACT_REF


def test_workflow_rejects_invalid_identifiers() -> None:
    data = json.loads((FIXTURES / "linear_llm.json").read_text(encoding="utf-8"))
    data["nodes"][0]["id"] = "not-valid"

    with pytest.raises(ValidationError):
        WorkflowSpec.model_validate(data)


def test_workflow_requires_non_empty_id_and_name() -> None:
    data = json.loads((FIXTURES / "linear_llm.json").read_text(encoding="utf-8"))
    data["workflow_id"] = ""
    data["name"] = ""

    with pytest.raises(ValidationError):
        WorkflowSpec.model_validate(data)


def test_state_schema_requires_input_and_output_channels() -> None:
    data = json.loads((FIXTURES / "linear_llm.json").read_text(encoding="utf-8"))
    del data["state_schema"]["channels"]["answer"]

    with pytest.raises(ValidationError):
        WorkflowSpec.model_validate(data)


def test_loop_guard_requires_positive_max_iterations() -> None:
    with pytest.raises(ValidationError):
        LoopGuard(max_iterations=0)


def test_normalize_workflow_orders_nodes_and_edges_by_id() -> None:
    data = json.loads((FIXTURES / "linear_llm.json").read_text(encoding="utf-8"))
    data["nodes"].append(
        {
            "id": "archive",
            "kind": "transform",
            "executor": {"ref": "builtin.identity_transform", "type": "builtin"},
            "inputs": {},
            "outputs": {},
            "params": {},
        }
    )
    data["edges"] = [
        {"id": "z_edge", "source": "compose", "target": "archive", "kind": "linear"},
        {"id": "a_edge", "source": "archive", "target": "compose", "kind": "linear"},
    ]

    normalized = normalize_workflow(WorkflowSpec.model_validate(data))

    assert [node.id for node in normalized.nodes] == ["archive", "compose"]
    assert [edge.id for edge in normalized.edges] == ["a_edge", "z_edge"]


def test_recursive_type_spec_supports_array_items_and_object_properties() -> None:
    spec = TypeSpec(
        type=TypeName.OBJECT,
        properties={
            "items": TypeSpec(type=TypeName.ARRAY, item_type=TypeSpec(type=TypeName.STRING))
        },
    )

    assert spec.properties["items"].item_type is not None
    assert spec.properties["items"].item_type.type is TypeName.STRING
