"""Public API for prompt2langgraph."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from prompt2langgraph.diagnostics.report import Diagnostic, DiagnosticLocation, ValidationReport
from prompt2langgraph.ir.models import WorkflowSpec
from prompt2langgraph.validate.validator import validate_workflow


def compile_workflow(workflow: WorkflowSpec, *, out_dir: Path | str) -> CompileResult:
    from prompt2langgraph.runtime.artifacts import CompileResult, compile_workflow_to_artifacts

    report, output_dir = compile_workflow_to_artifacts(workflow, out_dir=out_dir)

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
