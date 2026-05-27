"""Command line interface for prompt2langgraph v0.1."""

from __future__ import annotations

import hashlib
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

    from uuid import uuid4

    from prompt2langgraph.ir.lockfile import sha256_canonical_json
    from prompt2langgraph.ir.normalize import normalize_workflow
    from prompt2langgraph.runtime.runner import run_workflow

    model_client, tool_registry = _build_runtime_clients(workflow_or_report)

    thread_id = f"cli_{uuid4().hex}"
    # Compute thread_key using the same method as _thread_key in runner.py
    workflow_hash = sha256_canonical_json(
        normalize_workflow(workflow_or_report).model_dump(mode="json")
    )
    thread_key = (workflow_hash, thread_id)
    checkpointer, checkpointer_diagnostics = _build_cli_checkpointer(
        workflow_json, thread_id, thread_key
    )
    if checkpointer_diagnostics is not None:
        result_payload = {
            "status": "failed",
            "output": {},
            "diagnostics": [item.model_dump(mode="json") for item in checkpointer_diagnostics],
        }
        _emit(result_payload, json_output, "run failed")
        raise typer.Exit(1)

    result = run_workflow(
        workflow_or_report,
        input_payload,
        thread_id=thread_id,
        model_client=model_client,
        tool_registry=tool_registry,
        state_store_dir=_runtime_state_store_dir(workflow_json),
        checkpointer=checkpointer,
    )
    _emit(result.model_dump(mode="json"), json_output, _status_text(result))
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
    prompt: str | None = typer.Option(None, "--prompt"),  # noqa: B008
    skill_dir: Path | None = typer.Option(None, "--skill-dir"),  # noqa: B008
    model: str | None = typer.Option(None, "--model"),  # noqa: B008
    base_url: str | None = typer.Option(None, "--base-url"),  # noqa: B008
    api_key: str | None = typer.Option(None, "--api-key"),  # noqa: B008
    temperature: float = typer.Option(0.0, "--temperature"),  # noqa: B008
    validate_output: bool = typer.Option(False, "--validate"),  # noqa: B008
    json_output: bool = typer.Option(False, "--json", help="Emit a machine-readable plan."),  # noqa: B008
    param: list[str] = typer.Option([], "--param"),  # noqa: B008
) -> None:
    """Generate a simplified JSON plan from a prompt or skill directory using an LLM."""

    # Mutual exclusion check
    if prompt is None and skill_dir is None:
        _emit_validation_report(
            ValidationReport(
                diagnostics=[
                    Diagnostic(
                        code=E_PARSE_001,
                        severity="error",
                        message="must specify either --prompt or --skill-dir",
                        location=DiagnosticLocation(source="plan"),
                    )
                ]
            ),
            json_output,
        )
        raise typer.Exit(1) from None

    if prompt is not None and skill_dir is not None:
        _emit_validation_report(
            ValidationReport(
                diagnostics=[
                    Diagnostic(
                        code=E_PARSE_001,
                        severity="error",
                        message="cannot specify both --prompt and --skill-dir",
                        location=DiagnosticLocation(source="plan"),
                    )
                ]
            ),
            json_output,
        )
        raise typer.Exit(1) from None

    # Parse param list
    params = _parse_plan_params(param, json_output)

    if skill_dir is not None:
        _run_skill_plan(
            skill_dir,
            params,
            model,
            base_url,
            api_key,
            temperature,
            validate_output,
            json_output,
        )
    else:
        _run_prompt_plan(
            prompt,
            model,
            base_url,
            api_key,
            temperature,
            validate_output,
            json_output,
        )


def _parse_plan_params(param_list: list[str], json_output: bool = False) -> dict[str, str]:
    """Parse a list of key=value strings into a dictionary.

    Raises typer.Exit if any item is malformed.
    """
    params: dict[str, str] = {}
    for item in param_list:
        if "=" not in item:
            report = ValidationReport(
                diagnostics=[
                    Diagnostic(
                        code=E_PARSE_001,
                        severity="error",
                        message=f"--param value must be key=value, got {item!r}",
                        location=DiagnosticLocation(source="plan"),
                    )
                ]
            )
            _emit_validation_report(report, json_output)
            raise typer.Exit(1) from None
        key, value = item.split("=", 1)
        if not key.strip():
            report = ValidationReport(
                diagnostics=[
                    Diagnostic(
                        code=E_PARSE_001,
                        severity="error",
                        message=f"--param key must not be empty, got {item!r}",
                        location=DiagnosticLocation(source="plan"),
                    )
                ]
            )
            _emit_validation_report(report, json_output)
            raise typer.Exit(1) from None
        params[key] = value
    return params


def _run_prompt_plan(
    prompt: str,
    model: str | None,
    base_url: str | None,
    api_key: str | None,
    temperature: float,
    validate_output: bool,
    json_output: bool,
) -> None:
    """Execute the prompt plan generation path."""
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


def _run_skill_plan(
    skill_dir: Path,
    params: dict[str, str],
    model: str | None,
    base_url: str | None,
    api_key: str | None,
    temperature: float,
    validate_output: bool,
    json_output: bool,
) -> None:
    """Execute the skill plan generation path.

    Uses plan_skill_to_workflow_spec() as the single entry point for
    Skill → JSON plan → WorkflowSpec conversion. Pre-checks static
    analysis for fatal errors before the LLM call.
    """
    from prompt2langgraph.adapters.base import AdapterParseError
    from prompt2langgraph.adapters.skill_dir import analyze_skill_dir
    from prompt2langgraph.prompting import SkillPlanRequest
    from prompt2langgraph.prompting.skill_planner import plan_skill_to_workflow_spec

    request = SkillPlanRequest(
        skill_dir=str(skill_dir),
        params=params,
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
    )

    # Step 1: Static analysis — check for fatal errors before LLM call
    analysis = analyze_skill_dir(str(skill_dir))
    fatal_diagnostics = [d for d in analysis.report.diagnostics if d.severity == "error"]
    if fatal_diagnostics:
        report = ValidationReport(diagnostics=fatal_diagnostics)
        _emit_validation_report(report, json_output)
        raise typer.Exit(1) from None

    # Step 2–4: LLM generate → parse → adapt (single entry point)
    # Pass precomputed analysis to avoid double analyze_skill_dir()
    try:
        result = plan_skill_to_workflow_spec(request, analysis=analysis)
    except AdapterParseError as exc:
        # Distinguish error phase from exception message
        msg = str(exc).lower()
        if "failed to read skill file" in msg:
            code = E_PARSE_001
            hint = "SKILL.md is missing or unreadable"
        elif "failed to parse generated json plan" in msg:
            code = E_PARSE_001
            hint = "LLM output could not be parsed as JSON plan"
        elif "failed to adapt" in msg or "json plan" in msg:
            code = E_PARSE_001
            hint = "JSON plan could not be adapted to WorkflowSpec"
        else:
            code = E_PARSE_001
            hint = str(exc)
        report = ValidationReport(
            diagnostics=[
                Diagnostic(
                    code=code,
                    severity="error",
                    message="skill plan generation failed",
                    location=DiagnosticLocation(
                        source=exc.source or "skill",
                        path=exc.path,
                        line=exc.line,
                        column=exc.column,
                    ),
                    hint=hint,
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
                    message="LLM call failed during skill plan generation",
                    location=DiagnosticLocation(source="skill"),
                    hint=str(exc),
                )
            ]
        )
        _emit_validation_report(report, json_output)
        raise typer.Exit(1) from None

    # Output the original simplified JSON plan (not the IR dump)
    # to stay consistent with the --prompt path output format
    plan_data = result.plan or {}
    payload: dict[str, Any] = {"ok": True, "plan": plan_data}

    # Include static analysis diagnostics in output
    if result.diagnostics:
        payload["diagnostics"] = [d.model_dump(mode="json") for d in result.diagnostics]

    if validate_output and result.workflow_spec is not None:
        validation_report = validate_workflow(result.workflow_spec)
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
    from prompt2langgraph.ir.lockfile import sha256_canonical_json
    from prompt2langgraph.ir.normalize import normalize_workflow
    from prompt2langgraph.runtime.runner import run_workflow

    model_client, tool_registry = _build_runtime_clients(workflow_or_report)

    # Compute thread_key using the same method as _thread_key in runner.py
    workflow_hash = sha256_canonical_json(
        normalize_workflow(workflow_or_report).model_dump(mode="json")
    )
    thread_key = (workflow_hash, thread_id)
    checkpointer, checkpointer_diagnostics = _build_cli_checkpointer(
        workflow_json, thread_id, thread_key
    )
    if checkpointer_diagnostics is not None:
        result_payload = {
            "status": "failed",
            "output": {},
            "diagnostics": [item.model_dump(mode="json") for item in checkpointer_diagnostics],
        }
        _emit(result_payload, json_output, "resume failed")
        raise typer.Exit(1)

    result = run_workflow(
        workflow_or_report,
        {},
        thread_id=thread_id,
        resume_payload=resume_payload,
        model_client=model_client,
        tool_registry=tool_registry,
        state_store_dir=_runtime_state_store_dir(workflow_json),
        checkpointer=checkpointer,
    )
    _emit(result.model_dump(mode="json"), json_output, _status_text(result))
    if result.status != "succeeded":
        raise typer.Exit(1)


def _build_runtime_clients(workflow: WorkflowSpec) -> tuple[Any, Any]:
    """根据 workflow 节点类型构造 model_client 和 tool_registry。

    注意：CLI 自动构造的 tool_registry 是一个空 ToolCallableRegistry()。
    若 workflow 包含 PYTHON_CALLABLE 节点，需通过 Python API 注入已注册
    callable 的 tool_registry，否则运行时校验会报 E_SEC_015。
    """
    from prompt2langgraph.ir.models import ExecutorType

    model_client = None
    tool_registry = None

    has_llm_node = any(n.executor.type is ExecutorType.LLM for n in workflow.nodes)
    has_tool_node = any(n.executor.type is ExecutorType.PYTHON_CALLABLE for n in workflow.nodes)

    if has_llm_node and workflow.policies.external_call:
        from prompt2langgraph.llm.provider import build_llm_client

        model_client = build_llm_client()

    if has_tool_node:
        from prompt2langgraph.registry.tool_executor import ToolCallableRegistry

        tool_registry = ToolCallableRegistry()

    return model_client, tool_registry


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


def _build_cli_checkpointer(
    workflow_json: Path,
    thread_id: str,
    thread_key: tuple[str, str] | None = None,
) -> tuple[Any, list[Diagnostic] | None]:
    """Construct CLI-specific SQLite checkpointer.

    Path is `<bundle_dir>/.pt2lg-runtime/<thread_hash>.db`.
    If langgraph-checkpoint-sqlite is unavailable or initialization fails, returns (None, diagnostics).

    When thread_key is provided, uses it to compute the thread_hash (matching _thread_key in runner).
    Otherwise falls back to using workflow_json path for backward compatibility.
    """  # noqa: E501
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError:
        return None, None

    import sqlite3

    runtime_dir = _runtime_state_store_dir(workflow_json)
    if thread_key is not None:
        # Use the same hash computation as _thread_key in runner.py
        thread_hash = hashlib.sha256(f"{thread_key[0]}:{thread_key[1]}".encode()).hexdigest()[:16]
    else:
        # Fallback: use workflow_json path (legacy behavior)
        thread_hash = hashlib.sha256(f"{workflow_json}:{thread_id}".encode()).hexdigest()[:16]
    db_path = runtime_dir / f"{thread_hash}.db"

    try:
        runtime_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        checkpointer = SqliteSaver(conn)
        if callable(getattr(checkpointer, "setup", None)):
            checkpointer.setup()
        return checkpointer, None
    except Exception as exc:  # pragma: no cover
        return None, [
            Diagnostic(
                code=E_RUNTIME_010,
                severity="error",
                message="failed to initialize SQLite checkpointer",
                location=DiagnosticLocation(source=str(db_path)),
                hint=str(exc),
            )
        ]


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


def _status_text(result: Any) -> str:
    """Generate human-readable status text, distinguishing interrupt kinds."""
    if result.status == "waiting" and result.interrupt is not None:
        thread_id = getattr(result, "thread_id", "unknown")
        if result.interrupt.kind == "side_effect_approval":
            return (
                "Workflow is waiting for side effect approval."
                f" Resume with: pt2lg resume ... --thread-id {thread_id}"
            )
        return (
            "Workflow is waiting for human approval."
            f" Resume with: pt2lg resume ... --thread-id {thread_id}"
        )
    return result.status


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
