"""Public API for prompt2langgraph."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from prompt2langgraph.diagnostics.codes import E_TARGET_009
from prompt2langgraph.diagnostics.report import Diagnostic, DiagnosticLocation, ValidationReport
from prompt2langgraph.ir.models import WorkflowSpec
from prompt2langgraph.validate.validator import validate_workflow


def compile_workflow(workflow: WorkflowSpec, *, out_dir: Path | str) -> CompileResult:
    report = validate_workflow(workflow)
    output_dir = Path(out_dir) / workflow.workflow_id
    if report.ok:
        try:
            from prompt2langgraph.compiler.langgraph_py import compile_workflow_to_graph
            from prompt2langgraph.registry.builtins import builtin_executor_registry

            compile_workflow_to_graph(workflow, builtin_executor_registry())
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
    if report.ok:
        from prompt2langgraph.cli import _write_compile_artifacts

        _write_compile_artifacts(workflow, output_dir, target="langgraph-py", report=report)
    from prompt2langgraph.runtime.artifacts import CompileResult

    return CompileResult(
        ok=report.ok,
        output_dir=output_dir,
        diagnostics=[item.model_dump(mode="json") for item in report.diagnostics],
        artifacts={
            "workflow_ir": "workflow.ir.json",
            "lock": "workflow.lock.json",
            "manifest": "manifest.json",
            "compile_report": "compile_report.json",
            "mermaid": "graph.mmd",
        },
    )


def run_workflow(*args: Any, **kwargs: Any) -> Any:
    from prompt2langgraph.runtime.runner import run_workflow as _run_workflow

    return _run_workflow(*args, **kwargs)


def __getattr__(name: str) -> Any:
    if name == "CompileResult":
        from prompt2langgraph.runtime.artifacts import CompileResult

        return CompileResult
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CompileResult",
    "Diagnostic",
    "DiagnosticLocation",
    "ValidationReport",
    "WorkflowSpec",
    "compile_workflow",
    "run_workflow",
    "validate_workflow",
]
