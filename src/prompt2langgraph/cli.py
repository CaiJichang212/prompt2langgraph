"""Command line interface for prompt2langgraph v0.1."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError

from prompt2langgraph.adapters.json_plan import json_plan_to_workflow_spec
from prompt2langgraph.diagnostics.codes import E_PARSE_001, E_SCHEMA_002, E_TARGET_009
from prompt2langgraph.diagnostics.report import Diagnostic, DiagnosticLocation, ValidationReport
from prompt2langgraph.ir.lockfile import build_compile_report, build_manifest, build_workflow_lock
from prompt2langgraph.ir.models import WorkflowSpec
from prompt2langgraph.ir.normalize import normalize_workflow
from prompt2langgraph.registry.builtins import builtin_executor_registry
from prompt2langgraph.validate.validator import validate_workflow
from prompt2langgraph.visualization.mermaid import workflow_to_mermaid


app = typer.Typer(no_args_is_help=True)


@app.command()
def validate(
    workflow_json: Path,
    json_output: bool = typer.Option(False, "--json", help="Emit a machine-readable report."),
) -> None:
    """Validate a Workflow IR or simplified JSON plan."""

    workflow_or_report = _load_workflow_or_report(workflow_json)
    if isinstance(workflow_or_report, ValidationReport):
        _emit_validation_report(workflow_or_report, json_output)
        raise typer.Exit(1)

    report = validate_workflow(workflow_or_report)
    _emit_validation_report(report, json_output)
    if not report.ok:
        raise typer.Exit(1)


@app.command()
def compile(
    workflow_json: Path,
    target: str = typer.Option("langgraph-py", "--target"),
    out: Path = typer.Option(Path("build"), "--out"),
    json_output: bool = typer.Option(False, "--json", help="Emit a machine-readable report."),
) -> None:
    """Compile a Workflow IR or simplified JSON plan into local artifacts."""

    workflow_or_report = _load_workflow_or_report(workflow_json)
    if isinstance(workflow_or_report, ValidationReport):
        _emit_compile_payload(False, None, workflow_or_report, json_output)
        raise typer.Exit(1)

    workflow = workflow_or_report
    report = validate_workflow(workflow)
    if report.ok and target != "langgraph-py":
        report = ValidationReport(
            diagnostics=[
                Diagnostic(
                    code=E_TARGET_009,
                    severity="error",
                    message=f'target "{target}" is not supported',
                )
            ]
        )

    if report.ok:
        try:
            from prompt2langgraph.compiler.langgraph_py import compile_workflow_to_graph

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

    if not report.ok:
        _emit_compile_payload(False, None, report, json_output)
        raise typer.Exit(1)

    output_dir = out / workflow.workflow_id
    _write_compile_artifacts(workflow, output_dir, target=target, report=report)
    _emit_compile_payload(True, output_dir, report, json_output)


@app.command()
def run(
    workflow_json: Path,
    input: Path = typer.Option(..., "--input"),
    json_output: bool = typer.Option(False, "--json", help="Emit a machine-readable result."),
) -> None:
    """Run a Workflow IR or simplified JSON plan with a JSON input payload."""

    workflow_or_report = _load_workflow_or_report(workflow_json)
    if isinstance(workflow_or_report, ValidationReport):
        result_payload = {
            "status": "failed",
            "output": {},
            "diagnostics": [item.model_dump(mode="json") for item in workflow_or_report.diagnostics],
        }
        _emit(result_payload, json_output, "run failed")
        raise typer.Exit(1)

    input_payload = _load_json(input)
    if isinstance(input_payload, ValidationReport):
        result_payload = {
            "status": "failed",
            "output": {},
            "diagnostics": [item.model_dump(mode="json") for item in input_payload.diagnostics],
        }
        _emit(result_payload, json_output, "run failed")
        raise typer.Exit(1)

    from prompt2langgraph.runtime.runner import run_workflow

    result = run_workflow(workflow_or_report, input_payload)
    _emit(result.model_dump(mode="json"), json_output, result.status)
    if result.status != "succeeded":
        raise typer.Exit(1)


@app.command()
def graph(
    workflow_json: Path,
    format: str = typer.Option("mermaid", "--format"),
    json_output: bool = typer.Option(False, "--json", help="Emit a machine-readable graph payload."),
) -> None:
    """Render a workflow graph."""

    workflow_or_report = _load_workflow_or_report(workflow_json)
    if isinstance(workflow_or_report, ValidationReport):
        _emit_validation_report(workflow_or_report, json_output)
        raise typer.Exit(1)
    if format != "mermaid":
        report = ValidationReport(
            diagnostics=[
                Diagnostic(
                    code=E_TARGET_009,
                    severity="error",
                    message=f'graph format "{format}" is not supported',
                )
            ]
        )
        _emit_validation_report(report, json_output)
        raise typer.Exit(1)

    mermaid = workflow_to_mermaid(workflow_or_report)
    _emit({"format": "mermaid", "graph": mermaid}, json_output, mermaid)


def _load_workflow_or_report(path: Path) -> WorkflowSpec | ValidationReport:
    raw = _load_json(path)
    if isinstance(raw, ValidationReport):
        return raw
    try:
        if isinstance(raw, dict) and "schema_version" in raw:
            return WorkflowSpec.model_validate(raw)
        if isinstance(raw, dict):
            return json_plan_to_workflow_spec(raw)
    except ValidationError as exc:
        return ValidationReport(
            diagnostics=[
                Diagnostic(
                    code=E_SCHEMA_002,
                    severity="error",
                    message="workflow schema validation failed",
                    location=DiagnosticLocation(path=".".join(str(part) for part in error["loc"])),
                    hint=error["msg"],
                )
                for error in exc.errors()
            ]
        )
    except (KeyError, TypeError, ValueError) as exc:
        return ValidationReport(
            diagnostics=[
                Diagnostic(
                    code=E_PARSE_001,
                    severity="error",
                    message=f'failed to parse workflow file "{path}"',
                    location=DiagnosticLocation(source=str(path)),
                    hint=str(exc),
                )
            ]
        )
    return ValidationReport(
        diagnostics=[
            Diagnostic(
                code=E_PARSE_001,
                severity="error",
                message=f'workflow file "{path}" must contain a JSON object',
                location=DiagnosticLocation(source=str(path)),
            )
        ]
    )


def _load_json(path: Path) -> dict[str, Any] | ValidationReport:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return ValidationReport(
            diagnostics=[
                Diagnostic(
                    code=E_PARSE_001,
                    severity="error",
                    message=f'failed to read JSON file "{path}"',
                    location=DiagnosticLocation(source=str(path)),
                    hint=str(exc),
                )
            ]
        )
    except json.JSONDecodeError as exc:
        return ValidationReport(
            diagnostics=[
                Diagnostic(
                    code=E_PARSE_001,
                    severity="error",
                    message=f'failed to parse JSON file "{path}"',
                    location=DiagnosticLocation(source=str(path), path=str(exc.pos)),
                    hint=exc.msg,
                )
            ]
        )
    if not isinstance(data, dict):
        return ValidationReport(
            diagnostics=[
                Diagnostic(
                    code=E_PARSE_001,
                    severity="error",
                    message=f'JSON file "{path}" must contain an object',
                    location=DiagnosticLocation(source=str(path)),
                )
            ]
        )
    return data


def _write_compile_artifacts(
    workflow: WorkflowSpec,
    output_dir: Path,
    *,
    target: str,
    report: ValidationReport,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    normalized = normalize_workflow(workflow)
    artifacts = {
        "workflow.ir.json": normalized.model_dump(mode="json"),
        "workflow.lock.json": build_workflow_lock(normalized, target=target),
        "manifest.json": build_manifest(normalized, target=target),
        "compile_report.json": build_compile_report(normalized, diagnostics=report),
    }
    for name, payload in artifacts.items():
        (output_dir / name).write_text(_json_dumps(payload), encoding="utf-8")
    (output_dir / "graph.mmd").write_text(workflow_to_mermaid(normalized), encoding="utf-8")


def _emit_validation_report(report: ValidationReport, json_output: bool) -> None:
    payload = report.model_dump(mode="json")
    payload["ok"] = report.ok
    _emit(payload, json_output, "ok" if report.ok else "validation failed")


def _emit_compile_payload(
    ok: bool,
    output_dir: Path | None,
    report: ValidationReport,
    json_output: bool,
) -> None:
    payload: dict[str, Any] = {
        "ok": ok,
        "diagnostics": [item.model_dump(mode="json") for item in report.diagnostics],
    }
    if output_dir is not None:
        payload["output_dir"] = str(output_dir)
    _emit(payload, json_output, "compile succeeded" if ok else "compile failed")


def _emit(payload: dict[str, Any], json_output: bool, text: str) -> None:
    if json_output:
        typer.echo(_json_dumps(payload))
    else:
        typer.echo(text)


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
