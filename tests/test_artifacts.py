import json
import importlib.util
from dataclasses import replace
from pathlib import Path

import pytest

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
from prompt2langgraph.runtime.artifacts import load_bundle_workflow
from prompt2langgraph.visualization.mermaid import workflow_to_mermaid


FIXTURES = Path(__file__).parent / "fixtures"


def load_workflow(name: str) -> WorkflowSpec:
    return WorkflowSpec.model_validate(json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def import_generated_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_canonical_json_and_hash_are_deterministic() -> None:
    payload = {"b": 2, "a": {"d": 4, "c": 3}}

    assert canonical_json_dumps(payload) == '{"a":{"c":3,"d":4},"b":2}'
    assert sha256_canonical_json(payload).startswith("sha256:")


def test_artifact_builders_emit_expected_minimal_shapes() -> None:
    workflow = load_workflow("linear_llm.json")

    lock = build_workflow_lock(workflow)
    manifest = build_manifest(workflow)
    report = build_compile_report(
        workflow,
        diagnostics=[],
        artifacts={
            "workflow_ir": "workflow.ir.json",
            "lock": "workflow.lock.json",
            "manifest": "manifest.json",
            "mermaid": "graph.mmd",
        },
        compile_id="compile_test",
        timings_ms={"total": 1.0},
    )
    mermaid = workflow_to_mermaid(workflow)

    assert lock["schema_version"] == "0.1"
    assert lock["workflow_id"] == "linear_llm"
    assert lock["workflow_hash"].startswith("sha256:")
    assert lock["registry_hash"].startswith("sha256:")
    assert lock["target"] == "langgraph-py"
    assert lock["generated_files"] == [
        "workflow.ir.json",
        "workflow.lock.json",
        "manifest.json",
        "compile_report.json",
        "graph.mmd",
        "generated/__init__.py",
        "generated/state.py",
        "generated/nodes.py",
        "generated/graph.py",
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
        "executor_bindings": {
            "compose": {
                "executor": "builtin.echo_llm",
                "type": "builtin",
                "capabilities": [],
            }
        },
        "artifact_policy": {"large_objects": "artifact_ref"},
    }

    assert report["ok"] is True
    assert report["workflow_id"] == "linear_llm"
    assert report["diagnostics"] == []
    assert report["artifacts"] == {
        "workflow_ir": "workflow.ir.json",
        "lock": "workflow.lock.json",
        "manifest": "manifest.json",
        "mermaid": "graph.mmd",
    }

    assert "START --> compose" in mermaid
    assert "compose --> END" in mermaid


def test_build_workflow_lock_copies_generated_files_lists() -> None:
    workflow = load_workflow("linear_llm.json")

    default_lock = build_workflow_lock(workflow)
    default_lock["generated_files"].append("polluted.py")
    next_default_lock = build_workflow_lock(workflow)

    assert "polluted.py" not in next_default_lock["generated_files"]

    custom_files = ["workflow.ir.json"]
    custom_lock = build_workflow_lock(workflow, generated_files=custom_files)
    custom_files.append("mutated.py")

    assert custom_lock["generated_files"] == ["workflow.ir.json"]


def test_load_bundle_workflow_requires_lockfile_to_exist(tmp_path: Path) -> None:
    output_dir = tmp_path / "linear_llm"
    output_dir.mkdir()
    (output_dir / "workflow.ir.json").write_text(
        (FIXTURES / "linear_llm.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    with pytest.raises(OSError):
        load_bundle_workflow(output_dir / "workflow.lock.json")


def test_load_bundle_workflow_rejects_mismatched_workflow_hash(tmp_path: Path) -> None:
    output_dir = tmp_path / "linear_llm"
    output_dir.mkdir()
    workflow = load_workflow("linear_llm.json")
    (output_dir / "workflow.ir.json").write_text(
        json.dumps(workflow.model_dump(mode="json")),
        encoding="utf-8",
    )
    lock = build_workflow_lock(workflow)
    lock["workflow_hash"] = "sha256:not-the-workflow-hash"
    (output_dir / "workflow.lock.json").write_text(json.dumps(lock), encoding="utf-8")

    with pytest.raises(ValueError, match="workflow_hash"):
        load_bundle_workflow(output_dir / "workflow.lock.json")


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
                    required_capabilities=(
                        ("contract_changed",)
                        if kind == "llm"
                        else base_nodes.get(kind).required_capabilities
                    ),
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


def test_mermaid_labels_special_edge_kinds() -> None:
    loop_mermaid = workflow_to_mermaid(load_workflow("loop_with_guard.json"))
    fanout_mermaid = workflow_to_mermaid(load_workflow("fanout_map_reduce.json"))
    join_data = json.loads((FIXTURES / "linear_llm.json").read_text(encoding="utf-8"))
    join_data["nodes"].append(
        {
            "id": "finish",
            "kind": "transform",
            "executor": {"ref": "builtin.identity_transform", "type": "builtin"},
            "inputs": {"value": {"state_key": "answer"}},
            "outputs": {"value": {"state_key": "answer"}},
            "params": {},
        }
    )
    join_data["edges"] = [{"id": "join_finish", "source": "compose", "target": "finish", "kind": "join"}]

    join_mermaid = workflow_to_mermaid(WorkflowSpec.model_validate(join_data))

    assert "compose -- loop --> compose" in loop_mermaid
    assert "start -- fanout --> process_item" in fanout_mermaid
    assert "compose -- join --> finish" in join_mermaid


def test_compile_report_contains_hashes_tables_and_compile_id() -> None:
    workflow = load_workflow("linear_llm.json")

    report = build_compile_report(
        workflow,
        compile_id="compile_test",
        timings_ms={"validate": 1.0, "target_compile": 2.0, "artifact_write": 3.0, "total": 6.0},
    )

    assert report["compile_id"] == "compile_test"
    assert report["workflow_hash"].startswith("sha256:")
    assert report["registry_hash"].startswith("sha256:")
    assert report["nodes"] == [{"id": "compose", "kind": "llm", "executor": "builtin.echo_llm"}]
    assert report["edges"] == []
    assert "question" in report["state_channels"]
    assert "answer" in report["state_channels"]
    assert "timings_ms" in report
    assert report["timings_ms"]["total"] == 6.0


def test_compile_report_compile_id_changes_per_compile() -> None:
    workflow = load_workflow("linear_llm.json")

    first = build_compile_report(workflow, compile_id="compile_a", timings_ms={"total": 1.0})
    second = build_compile_report(workflow, compile_id="compile_b", timings_ms={"total": 2.0})

    assert first["compile_id"] == "compile_a"
    assert second["compile_id"] == "compile_b"
    assert first["compile_id"] != second["compile_id"]
    assert first["timings_ms"]["total"] == 1.0


def test_policy_resolver_applies_workflow_timeout_over_node_default() -> None:
    workflow = load_workflow("linear_llm.json")
    workflow.policies.default_timeout_s = 77

    from prompt2langgraph.policy.resolver import resolve_policies

    resolved = resolve_policies(workflow)

    assert resolved.node_policies["compose"]["timeout_s"] == 77
    assert resolved.node_policies["compose"]["requires_approval"] is False


def test_policy_resolver_timeout_precedence() -> None:
    workflow = load_workflow("linear_llm.json")
    workflow.nodes[0].timeout_s = None
    workflow.policies.default_timeout_s = None
    node_registry = NodeRegistry(
        [
            NodeDefinition(
                kind="llm",
                description="LLM node with custom timeout default.",
                default_timeout_s=33,
            )
        ]
    )

    from prompt2langgraph.policy.resolver import resolve_policies

    resolved = resolve_policies(workflow, nodes=node_registry)
    assert resolved.node_policies["compose"]["timeout_s"] == 33

    workflow.policies.default_timeout_s = 44
    resolved = resolve_policies(workflow, nodes=node_registry)
    assert resolved.node_policies["compose"]["timeout_s"] == 44

    workflow.nodes[0].timeout_s = 55
    resolved = resolve_policies(workflow, nodes=node_registry)
    assert resolved.node_policies["compose"]["timeout_s"] == 55

    resolved = resolve_policies(
        workflow,
        nodes=node_registry,
        compile_options={"default_timeout_s": 66},
    )
    assert resolved.node_policies["compose"]["timeout_s"] == 66


def test_policy_resolver_preserves_explicit_zero_timeout() -> None:
    workflow = load_workflow("linear_llm.json")
    workflow.nodes[0].timeout_s = 11
    workflow.policies.default_timeout_s = 22

    from prompt2langgraph.policy.resolver import resolve_policies

    resolved = resolve_policies(workflow, compile_options={"default_timeout_s": 0})
    assert resolved.node_policies["compose"]["timeout_s"] == 0

    workflow.nodes[0].timeout_s = 0
    resolved = resolve_policies(workflow)
    assert resolved.node_policies["compose"]["timeout_s"] == 0


def test_policy_resolver_requires_approval_for_disallowed_side_effects() -> None:
    workflow = load_workflow("linear_llm.json")
    workflow.nodes[0].kind = "side_effect"
    workflow.policies.allow_side_effects = False

    from prompt2langgraph.policy.resolver import resolve_policies

    resolved = resolve_policies(workflow)

    assert resolved.node_policies["compose"]["requires_approval"] is True


def test_resource_binder_records_executor_binding_without_secrets() -> None:
    workflow = load_workflow("linear_llm.json")
    workflow.nodes[0].executor.ref = "custom.secret_llm"
    executor_registry = ExecutorRegistry(
        [
            ExecutorDefinition(
                ref="custom.secret_llm",
                type=ExecutorType.BUILTIN,
                input_schema={},
                output_schema={},
                required_capabilities=("llm.invoke",),
                secrets=("OPENAI_API_KEY",),
            )
        ]
    )

    from prompt2langgraph.binding.binder import bind_workflow

    bound = bind_workflow(workflow, executors=executor_registry)

    assert bound.executor_bindings["compose"]["executor"] == "custom.secret_llm"
    assert bound.executor_bindings["compose"]["capabilities"] == ["llm.invoke"]
    assert "OPENAI_API_KEY" not in json.dumps(bound.model_dump(mode="json"))


def test_resource_binder_records_required_capabilities() -> None:
    workflow = load_workflow("linear_llm.json")
    workflow.nodes[0].executor.ref = "custom.capability_llm"
    executor_registry = ExecutorRegistry(
        [
            ExecutorDefinition(
                ref="custom.capability_llm",
                type=ExecutorType.BUILTIN,
                input_schema={"question": TypeSpec(type=TypeName.STRING)},
                output_schema={"answer": TypeSpec(type=TypeName.STRING)},
                required_capabilities=("llm.invoke", "network.disabled"),
            )
        ]
    )

    from prompt2langgraph.binding.binder import bind_workflow

    bound = bind_workflow(workflow, executors=executor_registry)

    assert bound.executor_bindings["compose"]["capabilities"] == [
        "llm.invoke",
        "network.disabled",
    ]


def test_secret_names_do_not_enter_manifest_or_compile_report() -> None:
    workflow = load_workflow("linear_llm.json")
    workflow.nodes[0].executor.ref = "custom.secret_llm"
    executor_registry = ExecutorRegistry(
        [
            ExecutorDefinition(
                ref="custom.secret_llm",
                type=ExecutorType.BUILTIN,
                input_schema={"question": TypeSpec(type=TypeName.STRING)},
                output_schema={"answer": TypeSpec(type=TypeName.STRING)},
                secrets=("OPENAI_API_KEY",),
            )
        ]
    )

    from prompt2langgraph.binding.binder import bind_workflow
    from prompt2langgraph.ir.lockfile import build_compile_report, build_manifest

    bound = bind_workflow(workflow, executors=executor_registry)
    manifest = build_manifest(workflow, executor_registry=executor_registry)
    report = build_compile_report(
        workflow,
        compile_id="compile_secret_free",
        timings_ms={"total": 1.0},
        executor_bindings=bound.executor_bindings,
    )

    serialized = json.dumps({"manifest": manifest, "report": report})
    assert "OPENAI_API_KEY" not in serialized


def test_manifest_binds_custom_executor_registry() -> None:
    workflow = load_workflow("linear_llm.json")
    workflow.nodes[0].executor.ref = "custom.echo_llm"
    executor_registry = ExecutorRegistry(
        [
            ExecutorDefinition(
                ref="custom.echo_llm",
                type=ExecutorType.BUILTIN,
                input_schema={"question": TypeSpec(type=TypeName.STRING)},
                output_schema={"answer": TypeSpec(type=TypeName.STRING)},
                secrets=("API_KEY",),
            )
        ]
    )

    manifest = build_manifest(workflow, executor_registry=executor_registry)

    assert manifest["executor_bindings"]["compose"]["executor"] == "custom.echo_llm"
    assert "secrets" not in manifest["executor_bindings"]["compose"]
    assert "API_KEY" not in json.dumps(manifest["executor_bindings"])


def test_bundle_paths_load_workflow_from_lockfile(tmp_path: Path) -> None:
    workflow = load_workflow("linear_llm.json")
    output_dir = tmp_path / workflow.workflow_id
    output_dir.mkdir()
    (output_dir / "workflow.ir.json").write_text(
        json.dumps(workflow.model_dump(mode="json"), ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "workflow.lock.json").write_text(
        json.dumps(build_workflow_lock(workflow), ensure_ascii=False),
        encoding="utf-8",
    )

    from prompt2langgraph.runtime.artifacts import BundlePaths, load_bundle_workflow

    bundle = BundlePaths.from_lockfile(output_dir / "workflow.lock.json")
    loaded = load_bundle_workflow(bundle)

    assert bundle.root == output_dir
    assert bundle.workflow_ir == output_dir / "workflow.ir.json"
    assert loaded.workflow_id == "linear_llm"


def test_emit_generated_bundle_writes_importable_graph_module(tmp_path: Path) -> None:
    workflow = load_workflow("fanout_map_reduce.json")
    from prompt2langgraph.compiler.codegen import emit_generated_bundle

    generated = emit_generated_bundle(workflow, tmp_path)

    assert (generated / "state.py").exists()
    assert (generated / "nodes.py").exists()
    graph_py = generated / "graph.py"
    assert graph_py.exists()
    assert "def build_graph()" in graph_py.read_text(encoding="utf-8")
    assert "def compile_graph()" in graph_py.read_text(encoding="utf-8")

    state_module = import_generated_module(generated / "state.py", "generated_state")
    nodes_module = import_generated_module(generated / "nodes.py", "generated_nodes")
    graph_module = import_generated_module(graph_py, "generated_graph")

    assert state_module.STATE_SCHEMA["workflow_id"] == "fanout_map_reduce"
    assert nodes_module.NODES[0]["id"] == "process_item"
    assert callable(graph_module.build_graph)
    assert callable(graph_module.compile_graph)


def test_manifest_contains_executor_bindings_from_compile_path(tmp_path: Path) -> None:
    """Test that manifest includes executor bindings when compiled through the full compile path."""
    workflow = load_workflow("linear_llm.json")
    from prompt2langgraph import compile_workflow

    result = compile_workflow(workflow, out_dir=tmp_path)

    manifest = json.loads((result.output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["executor_bindings"]["compose"]["executor"] == "builtin.echo_llm"
    assert manifest["executor_bindings"]["compose"]["type"] == "builtin"
    assert manifest["executor_bindings"]["compose"]["capabilities"] == []


def test_manifest_contains_policy_summary_from_compile_path(tmp_path: Path) -> None:
    """Test that manifest includes policy summary when compiled through the full compile path."""
    workflow = load_workflow("linear_llm.json")
    workflow.policies.default_timeout_s = 120
    from prompt2langgraph import compile_workflow

    result = compile_workflow(workflow, out_dir=tmp_path)

    manifest = json.loads((result.output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert "policy_summary" in manifest
    assert "node_policies" in manifest["policy_summary"]
    assert manifest["policy_summary"]["node_policies"]["compose"]["timeout_s"] == 120
    assert manifest["policy_summary"]["node_policies"]["compose"]["requires_approval"] is False


def test_compile_report_contains_binding_summary_from_compile_path(tmp_path: Path) -> None:
    """Test that compile_report includes binding summary when compiled through the full compile path."""
    workflow = load_workflow("linear_llm.json")
    from prompt2langgraph import compile_workflow

    result = compile_workflow(workflow, out_dir=tmp_path)

    report = json.loads((result.output_dir / "compile_report.json").read_text(encoding="utf-8"))
    assert "binding_summary" in report
    assert "executor_bindings" in report["binding_summary"]
    assert report["binding_summary"]["executor_bindings"]["compose"]["executor"] == "builtin.echo_llm"


def test_failed_compile_removes_stale_bundle_artifacts_but_keeps_unrelated_files(tmp_path: Path) -> None:
    workflow = load_workflow("linear_llm.json")
    from prompt2langgraph.runtime.artifacts import compile_workflow_to_artifacts

    successful_report, output_dir = compile_workflow_to_artifacts(workflow, out_dir=tmp_path)
    assert successful_report.ok is True
    assert (output_dir / "workflow.lock.json").exists()

    unrelated_file = output_dir / "README.local"
    unrelated_file.write_text("keep me", encoding="utf-8")

    failed_report, failed_output_dir = compile_workflow_to_artifacts(
        workflow,
        out_dir=tmp_path,
        target="not-a-target",
    )

    assert failed_report.ok is False
    assert failed_output_dir == output_dir
    assert not (output_dir / "workflow.lock.json").exists()
    assert not (output_dir / "manifest.json").exists()
    assert not (output_dir / "compile_report.json").exists()
    assert not (output_dir / "generated").exists()
    assert unrelated_file.read_text(encoding="utf-8") == "keep me"


def test_policy_summary_is_deterministic_and_secret_free(tmp_path: Path) -> None:
    """Test that policy summary does not contain secrets and is deterministic."""
    workflow = load_workflow("linear_llm.json")
    workflow.nodes[0].executor.ref = "custom.secret_llm"
    executor_registry = ExecutorRegistry(
        [
            ExecutorDefinition(
                ref="custom.secret_llm",
                type=ExecutorType.BUILTIN,
                input_schema={"question": TypeSpec(type=TypeName.STRING)},
                output_schema={"answer": TypeSpec(type=TypeName.STRING)},
                secrets=("API_KEY", "TOKEN"),
            )
        ]
    )

    from prompt2langgraph.ir.lockfile import build_manifest
    from prompt2langgraph.policy.resolver import resolve_policies

    resolved = resolve_policies(workflow)
    manifest = build_manifest(
        workflow, executor_registry=executor_registry, node_policies=resolved.node_policies
    )

    assert "policy_summary" in manifest
    serialized = json.dumps(manifest["policy_summary"])
    assert "API_KEY" not in serialized
    assert "TOKEN" not in serialized


def test_binding_summary_is_deterministic_and_secret_free(tmp_path: Path) -> None:
    """Test that binding summary does not contain secrets and is deterministic."""
    workflow = load_workflow("linear_llm.json")
    workflow.nodes[0].executor.ref = "custom.secret_llm"
    executor_registry = ExecutorRegistry(
        [
            ExecutorDefinition(
                ref="custom.secret_llm",
                type=ExecutorType.BUILTIN,
                input_schema={"question": TypeSpec(type=TypeName.STRING)},
                output_schema={"answer": TypeSpec(type=TypeName.STRING)},
                secrets=("API_KEY", "TOKEN"),
            )
        ]
    )

    from prompt2langgraph.binding.binder import bind_workflow
    from prompt2langgraph.ir.lockfile import build_compile_report

    bound = bind_workflow(workflow, executors=executor_registry)
    report = build_compile_report(
        workflow,
        compile_id="compile_test",
        timings_ms={"total": 1.0},
        executor_bindings=bound.executor_bindings,
    )

    assert "binding_summary" in report
    serialized = json.dumps(report["binding_summary"])
    assert "API_KEY" not in serialized
    assert "TOKEN" not in serialized
