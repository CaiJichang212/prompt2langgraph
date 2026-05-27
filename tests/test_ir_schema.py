import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from prompt2langgraph.diagnostics.report import Diagnostic, ValidationReport
from prompt2langgraph.ir.models import (
    LoopGuard,
    PolicySpec,
    SecurityPolicy,
    TypeName,
    TypeSpec,
    WorkflowSpec,
)
from prompt2langgraph.ir.normalize import normalize_workflow
from prompt2langgraph.registry.executors import ExecutorDefinition, ExecutorType

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


def test_policy_spec_defaults() -> None:
    policy = PolicySpec()
    assert policy.allow_side_effects is False
    assert policy.default_timeout_s == 60
    assert policy.external_call is False
    assert policy.allowed_models == []
    assert policy.collect_metrics is False
    assert policy.allowed_tool_refs == []


def test_security_policy_defaults() -> None:
    security = SecurityPolicy()
    assert security.requires_approval is False
    assert security.idempotency_key is None
    assert security.allowed_tool_refs is None


def test_executor_definition_dynamic_default() -> None:
    executor = ExecutorDefinition(ref="test", type=ExecutorType.BUILTIN)
    assert executor.dynamic is False


def test_old_workflow_json_gets_policy_defaults() -> None:
    data = json.loads((FIXTURES / "linear_llm.json").read_text(encoding="utf-8"))
    # 确保旧 JSON 中没有新增的 policy 字段
    policies = data.get("policies", {})
    assert "external_call" not in policies
    assert "allowed_models" not in policies
    assert "collect_metrics" not in policies
    assert "allowed_tool_refs" not in policies

    workflow = WorkflowSpec.model_validate(data)
    assert workflow.policies.external_call is False
    assert workflow.policies.allowed_models == []
    assert workflow.policies.collect_metrics is False
    assert workflow.policies.allowed_tool_refs == []


# ---- 旧 fixture 兼容性测试 ----

# 所有有效 fixture 文件名（不含 invalid_ 前缀的）
_VALID_FIXTURES = [
    "linear_llm.json",
    "linear_retriever_llm.json",
    "conditional_human_gate.json",
    "loop_with_guard.json",
    "fanout_map_reduce.json",
    "side_effect_allowed.json",
    "tool_identity.json",
]


@pytest.mark.parametrize("fixture_name", _VALID_FIXTURES)
def test_old_fixture_policies_get_default_values(fixture_name: str) -> None:
    """旧 fixture JSON（policies 为空对象或缺少新增字段）经 model_validate 后默认值补齐。"""
    data = json.loads((FIXTURES / fixture_name).read_text(encoding="utf-8"))
    policies = data.get("policies", {})
    # 确认旧 JSON 中不含新增字段
    assert "external_call" not in policies
    assert "allowed_models" not in policies
    assert "collect_metrics" not in policies
    assert "allowed_tool_refs" not in policies

    workflow = WorkflowSpec.model_validate(data)
    assert workflow.policies.external_call is False
    assert workflow.policies.allowed_models == []
    assert workflow.policies.collect_metrics is False
    assert workflow.policies.allowed_tool_refs == []


def test_workflow_without_policies_field_gets_defaults() -> None:
    """完全缺少 policies 字段的旧 JSON 也能正确加载并获得默认值。"""
    data = json.loads((FIXTURES / "linear_llm.json").read_text(encoding="utf-8"))
    del data["policies"]

    workflow = WorkflowSpec.model_validate(data)
    assert workflow.policies.external_call is False
    assert workflow.policies.allowed_models == []
    assert workflow.policies.collect_metrics is False
    assert workflow.policies.allowed_tool_refs == []
    assert workflow.policies.allow_side_effects is False
    assert workflow.policies.default_timeout_s == 60


def test_normalize_workflow_sorts_join_sources() -> None:
    """normalize_workflow should sort join_sources for deterministic hashing."""
    data = json.loads((FIXTURES / "fanout_with_join.json").read_text(encoding="utf-8"))
    # Reverse the join_sources order
    for edge in data["edges"]:
        if edge.get("kind") == "join" and edge.get("join_sources"):
            edge["join_sources"] = list(reversed(edge["join_sources"]))

    workflow = WorkflowSpec.model_validate(data)
    normalized = normalize_workflow(workflow)

    for edge in normalized.edges:
        if edge.kind.value == "join" and edge.join_sources:
            assert edge.join_sources == sorted(edge.join_sources)


def test_normalize_join_sources_produces_stable_hash() -> None:
    """Workflows with different join_sources order should produce same lockfile hash after normalize."""
    from prompt2langgraph.ir.lockfile import build_workflow_lock

    data_a = json.loads((FIXTURES / "fanout_with_join.json").read_text(encoding="utf-8"))
    data_b = json.loads((FIXTURES / "fanout_with_join.json").read_text(encoding="utf-8"))

    # Reverse join_sources in data_b
    for edge in data_b["edges"]:
        if edge.get("kind") == "join" and edge.get("join_sources"):
            edge["join_sources"] = list(reversed(edge["join_sources"]))

    workflow_a = WorkflowSpec.model_validate(data_a)
    workflow_b = WorkflowSpec.model_validate(data_b)

    lock_a = build_workflow_lock(workflow_a)
    lock_b = build_workflow_lock(workflow_b)

    assert lock_a["workflow_hash"] == lock_b["workflow_hash"]


def test_non_join_edge_with_join_sources_raises_validation_error() -> None:
    """Non-JOIN edge with join_sources should fail Pydantic validation."""
    from pydantic import ValidationError
    from prompt2langgraph.ir.models import EdgeSpec

    with pytest.raises(ValidationError, match="join_sources is only valid for JOIN edges"):
        EdgeSpec(
            id="bad_edge",
            source="a",
            target="b",
            kind="linear",
            join_sources=["a", "b"],
        )
