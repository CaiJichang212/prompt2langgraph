from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from prompt2langgraph.binding.binder import BoundWorkflow
from prompt2langgraph.diagnostics.codes import E_TARGET_009
from prompt2langgraph.diagnostics.report import Diagnostic, ValidationReport
from prompt2langgraph.ir.lockfile import (
    REQUIRED_GENERATED_FILES,
    build_compile_report,
    build_manifest,
    build_workflow_lock,
    sha256_canonical_json,
)
from prompt2langgraph.ir.models import WorkflowSpec
from prompt2langgraph.ir.normalize import normalize_workflow
from prompt2langgraph.policy.resolver import ResolvedWorkflow
from prompt2langgraph.registry.builtins import builtin_executor_registry
from prompt2langgraph.validate.validator import validate_workflow
from prompt2langgraph.visualization.mermaid import workflow_to_mermaid


@dataclass(frozen=True)
class BundlePaths:
    root: Path
    lockfile: Path
    workflow_ir: Path
    manifest: Path
    compile_report: Path
    mermaid: Path
    generated_dir: Path

    @classmethod
    def from_lockfile(cls, lockfile: Path | str) -> "BundlePaths":
        lock_path = Path(lockfile)
        root = lock_path.parent
        return cls(
            root=root,
            lockfile=lock_path,
            workflow_ir=root / "workflow.ir.json",
            manifest=root / "manifest.json",
            compile_report=root / "compile_report.json",
            mermaid=root / "graph.mmd",
            generated_dir=root / "generated",
        )


class CompileResult(BaseModel):
    ok: bool
    output_dir: Path
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


def compile_workflow_to_artifacts(
    workflow: WorkflowSpec,
    *,
    out_dir: Path | str,
    target: str = "langgraph-py",
) -> tuple[ValidationReport, Path]:
    total_started_at = perf_counter()
    timings_ms: dict[str, float] = {}
    report, normalized, resolved, bound = _validate_and_compile_target(
        workflow, target=target, timings_ms=timings_ms
    )
    output_dir = Path(out_dir) / workflow.workflow_id
    if report.ok:
        # Type narrowing: when report.ok is True, these values are guaranteed to be non-None
        assert normalized is not None
        assert resolved is not None
        assert bound is not None
        _write_compile_artifacts(
            normalized,
            output_dir,
            target=target,
            report=report,
            compile_id=_new_compile_id(),
            timings_ms=timings_ms,
            total_started_at=total_started_at,
            resolved=resolved,
            bound=bound,
        )
    else:
        _remove_stale_bundle_artifacts(output_dir)
    return report, output_dir


def load_json_file(path: Path | str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f'JSON file "{path}" must contain an object')
    return data


def load_bundle_lock(bundle: BundlePaths | Path | str) -> dict[str, Any]:
    paths = bundle if isinstance(bundle, BundlePaths) else BundlePaths.from_lockfile(bundle)
    return load_json_file(paths.lockfile)


def validate_bundle(bundle: BundlePaths | Path | str) -> tuple[dict[str, Any], WorkflowSpec]:
    paths = bundle if isinstance(bundle, BundlePaths) else BundlePaths.from_lockfile(bundle)
    lock = load_bundle_lock(paths)
    workflow = WorkflowSpec.model_validate(load_json_file(paths.workflow_ir))
    normalized = normalize_workflow(workflow)

    if lock.get("schema_version") != "0.1":
        raise ValueError('workflow.lock.json field "schema_version" must be "0.1"')
    if lock.get("workflow_id") != normalized.workflow_id:
        raise ValueError(
            'workflow.lock.json field "workflow_id" does not match workflow.ir.json'
        )

    workflow_hash = sha256_canonical_json(normalized.model_dump(mode="json"))
    if lock.get("workflow_hash") != workflow_hash:
        raise ValueError(
            'workflow.lock.json field "workflow_hash" does not match workflow.ir.json'
        )

    generated_files = lock.get("generated_files")
    if not isinstance(generated_files, list) or not all(
        isinstance(item, str) for item in generated_files
    ):
        raise ValueError('workflow.lock.json field "generated_files" must be a list of strings')
    missing_files = REQUIRED_GENERATED_FILES.difference(generated_files)
    if missing_files:
        missing = ", ".join(sorted(missing_files))
        raise ValueError(
            f'workflow.lock.json field "generated_files" is missing required artifact(s): {missing}'
        )

    return lock, normalized


def load_bundle_workflow(bundle: BundlePaths | Path | str) -> WorkflowSpec:
    _, workflow = validate_bundle(bundle)
    return workflow


def load_bundle_mermaid(bundle: BundlePaths | Path | str) -> str:
    paths = bundle if isinstance(bundle, BundlePaths) else BundlePaths.from_lockfile(bundle)
    validate_bundle(paths)
    return paths.mermaid.read_text(encoding="utf-8")


def _write_compile_artifacts(
    normalized: WorkflowSpec,
    output_dir: Path,
    *,
    target: str,
    report: ValidationReport,
    compile_id: str,
    timings_ms: dict[str, float],
    total_started_at: float,
    resolved: ResolvedWorkflow,
    bound: BoundWorkflow,
) -> None:
    artifact_started_at = perf_counter()
    output_dir.mkdir(parents=True, exist_ok=True)
    from prompt2langgraph.compiler.codegen import emit_generated_bundle

    artifact_payloads = {
        "workflow.ir.json": normalized.model_dump(mode="json"),
        "workflow.lock.json": build_workflow_lock(normalized, target=target),
        "manifest.json": build_manifest(
            normalized, target=target, node_policies=resolved.node_policies
        ),
    }
    for name, payload in artifact_payloads.items():
        (output_dir / name).write_text(_json_dumps(payload), encoding="utf-8")
    emit_generated_bundle(normalized, output_dir)
    (output_dir / "graph.mmd").write_text(workflow_to_mermaid(normalized), encoding="utf-8")
    timings_ms["artifact_write"] = _elapsed_ms(artifact_started_at)
    timings_ms["total"] = _elapsed_ms(total_started_at)

    compile_report = build_compile_report(
        normalized,
        diagnostics=report,
        compile_id=compile_id,
        timings_ms=timings_ms,
        executor_bindings=bound.executor_bindings,
    )
    (output_dir / "compile_report.json").write_text(_json_dumps(compile_report), encoding="utf-8")


def _remove_stale_bundle_artifacts(output_dir: Path) -> None:
    if not output_dir.exists():
        return
    for name in REQUIRED_GENERATED_FILES:
        path = output_dir / name
        if path.is_file():
            path.unlink()
    generated_dir = output_dir / "generated"
    if generated_dir.is_dir():
        shutil.rmtree(generated_dir)


def _validate_and_compile_target(
    workflow: WorkflowSpec,
    *,
    target: str,
    timings_ms: dict[str, float],
) -> tuple[ValidationReport, WorkflowSpec | None, ResolvedWorkflow | None, BoundWorkflow | None]:
    # Step 1: Normalize
    normalize_started_at = perf_counter()
    normalized = normalize_workflow(workflow)
    timings_ms["normalize"] = _elapsed_ms(normalize_started_at)

    # Step 2: Validate
    validate_started_at = perf_counter()
    report = validate_workflow(normalized)
    timings_ms["validate"] = _elapsed_ms(validate_started_at)

    if not report.ok:
        # Return normalized but empty resolved/bound for early exit
        return report, normalized, None, None

    # Step 3: Resolve policies
    resolve_started_at = perf_counter()
    from prompt2langgraph.policy.resolver import resolve_policies

    resolved = resolve_policies(normalized)
    timings_ms["resolve_policies"] = _elapsed_ms(resolve_started_at)

    # Step 4: Bind workflow
    bind_started_at = perf_counter()
    from prompt2langgraph.binding.binder import bind_workflow

    bound = bind_workflow(normalized)
    timings_ms["bind_workflow"] = _elapsed_ms(bind_started_at)

    # Step 5: Target capability check
    if target != "langgraph-py":
        return (
            ValidationReport(
                diagnostics=[
                    Diagnostic(
                        code=E_TARGET_009,
                        severity="error",
                        message=f'target "{target}" is not supported',
                    )
                ]
            ),
            normalized,
            resolved,
            bound,
        )

    # Step 6: Compile
    compile_started_at = perf_counter()
    try:
        from prompt2langgraph.compiler.langgraph_py import compile_workflow_to_graph

        compile_workflow_to_graph(normalized, builtin_executor_registry())
    except Exception as exc:
        report = ValidationReport(
            diagnostics=[
                Diagnostic(
                    code=E_TARGET_009,
                    severity="error",
                    message="workflow failed to compile for target langgraph-py",
                    hint=str(exc),
                )
            ]
        )
    finally:
        timings_ms["target_compile"] = _elapsed_ms(compile_started_at)

    return report, normalized, resolved, bound


def _new_compile_id() -> str:
    return f"compile_{uuid4().hex}"


def _elapsed_ms(started_at: float) -> float:
    return (perf_counter() - started_at) * 1000


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
