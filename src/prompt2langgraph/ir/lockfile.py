"""Artifact builders for lockfile, manifest, and compile report."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from typing import Any

from prompt2langgraph.binding.binder import bind_workflow
from prompt2langgraph.diagnostics.report import Diagnostic, ValidationReport
from prompt2langgraph.ir.models import WorkflowSpec
from prompt2langgraph.ir.normalize import normalize_workflow
from prompt2langgraph.registry.builtins import builtin_executor_registry, builtin_node_registry
from prompt2langgraph.registry.executors import ExecutorRegistry
from prompt2langgraph.registry.nodes import NodeRegistry

REQUIRED_GENERATED_FILES = {
    "workflow.ir.json",
    "workflow.lock.json",
    "manifest.json",
    "compile_report.json",
    "graph.mmd",
    "generated/__init__.py",
    "generated/state.py",
    "generated/nodes.py",
    "generated/graph.py",
}

DEFAULT_GENERATED_FILES = [
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


def canonical_json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_canonical_json(value: Any) -> str:
    digest = hashlib.sha256(canonical_json_dumps(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def build_workflow_lock(
    workflow: WorkflowSpec,
    *,
    target: str = "langgraph-py",
    compile_options: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
    node_registry: NodeRegistry | None = None,
    executor_registry: ExecutorRegistry | None = None,
    generated_files: list[str] | None = None,
) -> dict[str, Any]:
    normalized = normalize_workflow(workflow)
    node_registry = node_registry or builtin_node_registry()
    executor_registry = executor_registry or builtin_executor_registry()
    compile_options = compile_options or {}
    policy = policy or normalized.policies.model_dump(mode="json")

    return {
        "schema_version": "0.1",
        "workflow_id": normalized.workflow_id,
        "workflow_hash": sha256_canonical_json(normalized.model_dump(mode="json")),
        "registry_hash": sha256_canonical_json(
            _registry_contract(node_registry, executor_registry)
        ),
        "target": target,
        "prompt2langgraph_version": _package_version("prompt2langgraph"),
        "langgraph_version": _package_version("langgraph"),
        "compile_options_hash": sha256_canonical_json(compile_options),
        "policy_hash": sha256_canonical_json(policy),
        "generated_files": list(generated_files)
        if generated_files is not None
        else list(DEFAULT_GENERATED_FILES),
    }


def build_manifest(
    workflow: WorkflowSpec,
    *,
    target: str = "langgraph-py",
    executor_registry: ExecutorRegistry | None = None,
    node_policies: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized = normalize_workflow(workflow)
    bound = bind_workflow(normalized, executors=executor_registry)
    manifest = {
        "workflow_id": normalized.workflow_id,
        "entrypoint": normalized.entrypoint,
        "target": target,
        "nodes": [
            {
                "id": node.id,
                "kind": node.kind,
                "executor": node.executor.ref,
            }
            for node in normalized.nodes
        ],
        "edges": [
            {
                "source": edge.source,
                "target": edge.target,
                "kind": edge.kind.value,
            }
            for edge in normalized.edges
        ],
        "state_keys": sorted(normalized.state_schema.channels),
        "interrupt_nodes": [
            node.id
            for node in normalized.nodes
            if node.kind == "human_gate" or node.executor.type.value == "human"
        ],
        "side_effect_nodes": [node.id for node in normalized.nodes if node.kind == "side_effect"],
        "executor_bindings": bound.executor_bindings,
        "artifact_policy": {"large_objects": "artifact_ref"},
    }
    if node_policies is not None:
        manifest["policy_summary"] = {"node_policies": node_policies}
    return manifest


def build_compile_report(
    workflow: WorkflowSpec,
    *,
    diagnostics: list[Diagnostic | dict[str, Any]] | ValidationReport | None = None,
    artifacts: dict[str, str] | None = None,
    ok: bool | None = None,
    compile_id: str,
    timings_ms: dict[str, float],
    registry_hash: str | None = None,
    executor_bindings: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized = normalize_workflow(workflow)
    diagnostic_items = _diagnostic_items(diagnostics)
    report = {
        "ok": ok
        if ok is not None
        else not any(item["severity"] == "error" for item in diagnostic_items),
        "compile_id": compile_id,
        "workflow_id": normalized.workflow_id,
        "workflow_hash": sha256_canonical_json(normalized.model_dump(mode="json")),
        "registry_hash": registry_hash
        or sha256_canonical_json(
            _registry_contract(builtin_node_registry(), builtin_executor_registry())
        ),
        "timings_ms": dict(timings_ms),
        "nodes": [
            {"id": node.id, "kind": node.kind, "executor": node.executor.ref}
            for node in normalized.nodes
        ],
        "edges": [
            {"id": edge.id, "source": edge.source, "target": edge.target, "kind": edge.kind.value}
            for edge in normalized.edges
        ],
        "state_channels": {
            key: value.model_dump(mode="json")
            for key, value in sorted(normalized.state_schema.channels.items())
        },
        "diagnostics": diagnostic_items,
        "artifacts": artifacts
        or {
            "workflow_ir": "workflow.ir.json",
            "lock": "workflow.lock.json",
            "manifest": "manifest.json",
            "mermaid": "graph.mmd",
        },
    }
    if executor_bindings is not None:
        report["binding_summary"] = {"executor_bindings": executor_bindings}
    return report


def _diagnostic_items(
    diagnostics: list[Diagnostic | dict[str, Any]] | ValidationReport | None,
) -> list[dict[str, Any]]:
    if diagnostics is None:
        return []
    if isinstance(diagnostics, ValidationReport):
        items = diagnostics.diagnostics
    else:
        items = diagnostics
    return [
        item.model_dump(mode="json") if isinstance(item, Diagnostic) else dict(item)
        for item in items
    ]


def _package_version(name: str) -> str:
    try:
        return package_version(name)
    except PackageNotFoundError:
        return "0.1.0" if name == "prompt2langgraph" else "unknown"


def _registry_contract(
    node_registry: NodeRegistry,
    executor_registry: ExecutorRegistry,
) -> dict[str, Any]:
    return {
        "nodes": [
            _normalize_dataclass(asdict(node_registry.get(kind))) for kind in node_registry.kinds()
        ],
        "executors": [
            _normalize_dataclass(asdict(executor_registry.get(ref)))
            for ref in executor_registry.refs()
        ],
    }


def _normalize_dataclass(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _normalize_dataclass(inner) for key, inner in value.items() if key != "handler"
        }
    if isinstance(value, list):
        return [_normalize_dataclass(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_dataclass(item) for item in value]
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value
