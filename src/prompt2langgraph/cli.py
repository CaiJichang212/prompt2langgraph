"""Command line interface for prompt2langgraph v0.1."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError

from prompt2langgraph.adapters.base import AdapterParseError
from prompt2langgraph.adapters.ir import IRAdapter
from prompt2langgraph.adapters.json_plan import JSONPlanAdapter
from prompt2langgraph.diagnostics.codes import (
    E_PARSE_001,
    E_RUNTIME_010,
    E_SCHEMA_002,
    E_TARGET_009,
)
from prompt2langgraph.diagnostics.report import (
    Diagnostic,
    DiagnosticLocation,
    ValidationReport,
)
from prompt2langgraph.ir.models import WorkflowSpec
from prompt2langgraph.validate.validator import validate_workflow
from prompt2langgraph.visualization.mermaid import workflow_to_mermaid

app = typer.Typer(no_args_is_help=True)
COMPILE_OUT_OPTION = typer.Option(Path("build"), "--out")
RUN_INPUT_OPTION = typer.Option(..., "--input")


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
    out: Path = COMPILE_OUT_OPTION,
    json_output: bool = typer.Option(False, "--json", help="Emit a machine-readable report."),
) -> None:
    """Compile a Workflow IR or simplified JSON plan into local artifacts."""

    workflow_or_report = _load_workflow_or_report(workflow_json)
    if isinstance(workflow_or_report, ValidationReport):
        _emit_compile_payload(False, None, workflow_or_report, json_output)
        raise typer.Exit(1)

    workflow = workflow_or_report
    from prompt2langgraph.runtime.artifacts import compile_workflow_to_artifacts

    report, output_dir = compile_workflow_to_artifacts(workflow, out_dir=out, target=target)
    _emit_compile_payload(report.ok, output_dir if report.ok else None, report, json_output)
    if not report.ok:
        raise typer.Exit(1)


@app.command()
def run(
    workflow_json: Path,
    input: Path = RUN_INPUT_OPTION,
    json_output: bool = typer.Option(False, "--json", help="Emit a machine-readable result."),
) -> None:
    """Run a Workflow IR or simplified JSON plan with a JSON input payload."""

    workflow_or_report = _load_workflow_source_or_report(workflow_json)
    if isinstance(workflow_or_report, ValidationReport):
        result_payload = {
            "status": "failed",
            "output": {},
            "diagnostics": [
                item.model_dump(mode="json") for item in workflow_or_report.diagnostics
            ],
        }
        _emit(result_payload, json_output, "run failed")
        raise typer.Exit(1)

    input_payload = _load_input_payload(input)
    if isinstance(input_payload, ValidationReport):
        result_payload = {
            "status": "failed",
            "output": {},
            "diagnostics": [item.model_dump(mode="json") for item in input_payload.diagnostics],
        }
        _emit(result_payload, json_output, "run failed")
        raise typer.Exit(1)

    from prompt2langgraph.runtime.runner import run_workflow

    from prompt2langgraph.ir.models import ExecutorType

    model_client = None
    tool_registry = None

    has_llm_node = any(
        n.executor.type is ExecutorType.LLM for n in workflow_or_report.nodes
    )
    has_tool_node = any(
        n.executor.type is ExecutorType.PYTHON_CALLABLE for n in workflow_or_report.nodes
    )

    if has_llm_node and workflow_or_report.policies.external_call:
        from prompt2langgraph.llm.provider import build_llm_client

        model_client = build_llm_client()

    if has_tool_node:
        from prompt2langgraph.registry.tool_executor import ToolCallableRegistry

        tool_registry = ToolCallableRegistry()

    result = run_workflow(
        workflow_or_report,
        input_payload,
        model_client=model_client,
        tool_registry=tool_registry,
        state_store_dir=_runtime_state_store_dir(workflow_json),
    )
    _emit(result.model_dump(mode="json"), json_output, result.status)
    if result.status != "succeeded":
        raise typer.Exit(1)


@app.command()
def graph(
    workflow_json: Path,
    format: str = typer.Option("mermaid", "--format"),
    json_output: bool = typer.Option(
        False, "--json", help="Emit a machine-readable graph payload."
    ),
) -> None:
    """Render a workflow graph."""

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

    if workflow_json.name == "workflow.lock.json":
        try:
            from prompt2langgraph.runtime.artifacts import load_bundle_mermaid

            mermaid = load_bundle_mermaid(workflow_json)
        except OSError as exc:
            report = ValidationReport(
                diagnostics=[
                    Diagnostic(
                        code=E_PARSE_001,
                        severity="error",
                        message=f'failed to read bundle graph for "{workflow_json}"',
                        location=DiagnosticLocation(source=str(workflow_json)),
                        hint=str(exc),
                    )
                ]
            )
            _emit_validation_report(report, json_output)
            raise typer.Exit(1) from None
        _emit({"format": "mermaid", "graph": mermaid}, json_output, mermaid)
        return

    workflow_or_report = _load_workflow_source_or_report(workflow_json)
    if isinstance(workflow_or_report, ValidationReport):
        _emit_validation_report(workflow_or_report, json_output)
        raise typer.Exit(1)

    mermaid = workflow_to_mermaid(workflow_or_report)
    _emit({"format": "mermaid", "graph": mermaid}, json_output, mermaid)


@app.command()
def plan(
    prompt: str = typer.Option(..., "--prompt"),
    model: str | None = typer.Option(None, "--model"),
    base_url: str | None = typer.Option(None, "--base-url"),
    api_key: str | None = typer.Option(None, "--api-key"),
    temperature: float = typer.Option(0.0, "--temperature"),
    validate_output: bool = typer.Option(False, "--validate"),
    json_output: bool = typer.Option(False, "--json", help="Emit a machine-readable plan."),
) -> None:
    """Generate a simplified JSON plan from a prompt using an LLM."""

    from prompt2langgraph.prompting import PromptPlanRequest
    from prompt2langgraph.prompting.parser import parse_prompt_plan_text
    from prompt2langgraph.prompting.planner import generate_plan_text

    request = PromptPlanRequest(
        prompt=prompt,
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
    )
    try:
        result = generate_plan_text(request)
        plan_data = parse_prompt_plan_text(result.raw_text)
    except AdapterParseError as exc:
        report = ValidationReport(
            diagnostics=[
                Diagnostic(
                    code=E_PARSE_001,
                    severity="error",
                    message="failed to parse generated prompt plan",
                    location=DiagnosticLocation(
                        source=exc.source or "prompt",
                        path=exc.path,
                        line=exc.line,
                        column=exc.column,
                    ),
                    hint=str(exc),
                )
            ]
        )
        _emit_validation_report(report, json_output)
        raise typer.Exit(1) from None
    except Exception as exc:
        report = ValidationReport(
            diagnostics=[
                Diagnostic(
                    code=E_RUNTIME_010,
                    severity="error",
                    message="LLM call failed during prompt plan generation",
                    location=DiagnosticLocation(source="prompt"),
                    hint=str(exc),
                )
            ]
        )
        _emit_validation_report(report, json_output)
        raise typer.Exit(1) from None

    payload: dict[str, Any] = {"ok": True, "plan": plan_data}

    if validate_output:
        try:
            workflow = JSONPlanAdapter().parse(plan_data, source="prompt")
        except (AdapterParseError, ValidationError) as exc:
            validation_report = ValidationReport(
                diagnostics=[
                    Diagnostic(
                        code=E_PARSE_001 if isinstance(exc, AdapterParseError) else E_SCHEMA_002,
                        severity="error",
                        message="generated plan failed adapter validation",
                        location=DiagnosticLocation(source="prompt"),
                        hint=str(exc),
                    )
                ]
            )
            payload["validation"] = validation_report.model_dump(mode="json")
            payload["validation"]["ok"] = False
            _emit(payload, json_output, _json_dumps(plan_data))
            raise typer.Exit(1) from None

        validation_report = validate_workflow(workflow)
        payload["validation"] = validation_report.model_dump(mode="json")
        payload["validation"]["ok"] = validation_report.ok
        if not validation_report.ok:
            _emit(payload, json_output, _json_dumps(plan_data))
            raise typer.Exit(1) from None

    _emit(payload, json_output, _json_dumps(plan_data))


@app.command()
def resume(
    workflow_json: Path,
    thread_id: str = typer.Option(..., "--thread-id"),
    resume: str = typer.Option(..., "--resume"),
    json_output: bool = typer.Option(False, "--json", help="Emit a machine-readable result."),
) -> None:
    """Resume a waiting Workflow IR or compiled bundle."""

    workflow_or_report = _load_workflow_source_or_report(workflow_json)
    if isinstance(workflow_or_report, ValidationReport):
        result_payload = {
            "status": "failed",
            "output": {},
            "diagnostics": [
                item.model_dump(mode="json") for item in workflow_or_report.diagnostics
            ],
        }
        _emit(result_payload, json_output, "resume failed")
        raise typer.Exit(1)

    resume_payload = _parse_resume_payload(resume)
    from prompt2langgraph.runtime.runner import run_workflow

    result = run_workflow(
        workflow_or_report,
        {},
        thread_id=thread_id,
        resume_payload=resume_payload,
        state_store_dir=_runtime_state_store_dir(workflow_json),
    )
    _emit(result.model_dump(mode="json"), json_output, result.status)
    if result.status != "succeeded":
        raise typer.Exit(1)


def _load_workflow_or_report(path: Path) -> WorkflowSpec | ValidationReport:
    raw = _load_json(path)
    if isinstance(raw, ValidationReport):
        return raw
    try:
        if isinstance(raw, dict) and "schema_version" in raw:
            return IRAdapter().parse(raw, source=str(path))
        if isinstance(raw, dict):
            return JSONPlanAdapter().parse(raw, source=str(path))
    except ValidationError as exc:
        return ValidationReport(
            diagnostics=[
                Diagnostic(
                    code=E_SCHEMA_002,
                    severity="error",
                    message="workflow schema validation failed",
                    location=DiagnosticLocation(
                        source=str(path),
                        path=".".join(str(part) for part in error["loc"]),
                    ),
                    hint=error["msg"],
                )
                for error in exc.errors()
            ]
        )
    except AdapterParseError as exc:
        return ValidationReport(
            diagnostics=[
                Diagnostic(
                    code=E_PARSE_001,
                    severity="error",
                    message=f'failed to parse workflow file "{path}"',
                    location=DiagnosticLocation(
                        source=exc.source or str(path),
                        path=exc.path,
                        line=exc.line,
                        column=exc.column,
                    ),
                    hint=str(exc),
                )
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


def _load_workflow_source_or_report(path: Path) -> WorkflowSpec | ValidationReport:
    if path.name == "workflow.lock.json":
        try:
            from prompt2langgraph.runtime.artifacts import load_bundle_workflow

            return load_bundle_workflow(path)
        except (OSError, ValueError, json.JSONDecodeError, ValidationError) as exc:
            return ValidationReport(
                diagnostics=[
                    Diagnostic(
                        code=E_PARSE_001,
                        severity="error",
                        message=f'failed to load workflow bundle "{path}"',
                        location=DiagnosticLocation(source=str(path)),
                        hint=str(exc),
                    )
                ]
            )
    return _load_workflow_or_report(path)


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


def _load_input_payload(value: Path) -> dict[str, Any] | ValidationReport:
    raw_value = str(value).strip()
    if raw_value.startswith("{"):
        try:
            data = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            return ValidationReport(
                diagnostics=[
                    Diagnostic(
                        code=E_PARSE_001,
                        severity="error",
                        message="failed to parse inline JSON input",
                        location=DiagnosticLocation(source=raw_value, path=str(exc.pos)),
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
                        message="inline JSON input must contain an object",
                        location=DiagnosticLocation(source=raw_value),
                    )
                ]
            )
        return data
    return _load_json(value)


def _parse_resume_payload(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _runtime_state_store_dir(workflow_json: Path) -> Path:
    if workflow_json.name == "workflow.lock.json":
        return workflow_json.parent / ".pt2lg-runtime"
    return Path.cwd() / ".pt2lg-runtime"


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
