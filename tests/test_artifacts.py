import json
from dataclasses import replace
from pathlib import Path

from prompt2langgraph.ir.lockfile import (
    build_compile_report,
    build_manifest,
    build_workflow_lock,
    canonical_json_dumps,
    sha256_canonical_json,
)
from prompt2langgraph.ir.models import ExecutorType, TypeName, TypeSpec, WorkflowSpec
from prompt2langgraph.registry.builtins import builtin_executor_registry, builtin_node_registry
from prompt2langgraph.registry.executors import ExecutorDefinition, ExecutorRegistry
from prompt2langgraph.registry.nodes import NodeDefinition, NodeRegistry
from prompt2langgraph.visualization.mermaid import workflow_to_mermaid


FIXTURES = Path(__file__).parent / "fixtures"


def load_workflow(name: str) -> WorkflowSpec:
    return WorkflowSpec.model_validate(json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def test_canonical_json_and_hash_are_deterministic() -> None:
    payload = {"b": 2, "a": {"d": 4, "c": 3}}

    assert canonical_json_dumps(payload) == '{"a":{"c":3,"d":4},"b":2}'
    assert sha256_canonical_json(payload).startswith("sha256:")


def test_artifact_builders_emit_expected_minimal_shapes() -> None:
    workflow = load_workflow("linear_llm.json")

    lock = build_workflow_lock(workflow)
    manifest = build_manifest(workflow)
    report = build_compile_report(workflow, diagnostics=[], artifacts={
        "workflow_ir": "workflow.ir.json",
        "lock": "workflow.lock.json",
        "manifest": "manifest.json",
        "mermaid": "graph.mmd",
    })
    mermaid = workflow_to_mermaid(workflow)

    assert lock["schema_version"] == "0.1"
    assert lock["workflow_id"] == "linear_llm"
    assert lock["workflow_hash"].startswith("sha256:")
    assert lock["registry_hash"].startswith("sha256:")
    assert lock["target"] == "langgraph-py"
    assert lock["generated_files"] == [
        "workflow.ir.json",
        "manifest.json",
        "compile_report.json",
        "graph.mmd",
    ]

    assert manifest == {
        "workflow_id": "linear_llm",
        "entrypoint": "compose",
        "target": "langgraph-py",
        "nodes": [{"id": "compose", "kind": "llm", "executor": "builtin.echo_llm"}],
        "edges": [],
        "state_keys": ["answer", "question"],
        "interrupt_nodes": [],
        "side_effect_nodes": [],
    }

    assert report == {
        "ok": True,
        "workflow_id": "linear_llm",
        "diagnostics": [],
        "artifacts": {
            "workflow_ir": "workflow.ir.json",
            "lock": "workflow.lock.json",
            "manifest": "manifest.json",
            "mermaid": "graph.mmd",
        },
    }

    assert "START --> compose" in mermaid
    assert "compose --> END" in mermaid


def test_registry_hash_changes_when_registry_contract_changes() -> None:
    workflow = load_workflow("linear_llm.json")
    base_lock = build_workflow_lock(workflow)
    base_nodes = builtin_node_registry()
    base_executors = builtin_executor_registry()
    changed_lock = build_workflow_lock(
        workflow,
        node_registry=NodeRegistry(
            [
                replace(
                    base_nodes.get(kind),
                    capabilities=("contract_changed",) if kind == "llm" else base_nodes.get(kind).capabilities,
                )
                for kind in base_nodes.kinds()
            ]
        ),
        executor_registry=ExecutorRegistry(
            [
                replace(
                    base_executors.get(ref),
                    output_schema={"answer": TypeSpec(type=TypeName.OBJECT)}
                    if ref == "builtin.echo_llm"
                    else base_executors.get(ref).output_schema,
                )
                for ref in base_executors.refs()
            ]
        ),
    )

    assert changed_lock["registry_hash"] != base_lock["registry_hash"]


def test_mermaid_renders_all_conditional_routes() -> None:
    workflow = load_workflow("conditional_human_gate.json")

    mermaid = workflow_to_mermaid(workflow)

    assert "route -- true --> approval" in mermaid
    assert "route -- false --> compose" in mermaid
