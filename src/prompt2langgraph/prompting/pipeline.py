from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, Field

from prompt2langgraph.adapters.base import AdapterParseError
from prompt2langgraph.adapters.json_plan import JSONPlanAdapter
from prompt2langgraph.adapters.skill_dir import SkillDirectoryAnalysis, analyze_skill_dir
from prompt2langgraph.diagnostics.codes import E_PARSE_001, E_RUNTIME_010, E_SCHEMA_002
from prompt2langgraph.diagnostics.report import Diagnostic, DiagnosticLocation, ValidationReport
from prompt2langgraph.ir.models import WorkflowSpec
from prompt2langgraph.prompting.parser import parse_prompt_plan_text
from prompt2langgraph.registry.builtins import builtin_executor_registry
from prompt2langgraph.registry.executors import ExecutorRegistry
from prompt2langgraph.registry.tool_executor import ToolCallableRegistry
from prompt2langgraph.validate.validator import validate_workflow

PlanningSource = Literal["prompt", "skill"]
PlanningStageName = Literal["generation", "parse", "adapter", "validation", "compile_smoke"]

STAGE_NAMES: tuple[PlanningStageName, ...] = (
    "generation",
    "parse",
    "adapter",
    "validation",
    "compile_smoke",
)


class PlanningStageStatus(BaseModel):
    ran: bool = False
    ok: bool = False
    skipped: bool = False
    reason: str | None = None
    diagnostics: list[Diagnostic] = Field(default_factory=list)


class RepairAttemptRecord(BaseModel):
    attempt_index: int
    trigger_stage: PlanningStageName
    diagnostic_codes: list[str] = Field(default_factory=list)
    raw_text_preview: str = ""
    ok: bool = False


class PlanningPipelineResult(BaseModel):
    ok: bool
    source: PlanningSource
    raw_text: str | None = None
    plan: dict[str, Any] | None = None
    workflow: WorkflowSpec | None = None
    validation_report: ValidationReport | None = None
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    stages: dict[PlanningStageName, PlanningStageStatus] = Field(default_factory=dict)
    repair_attempts: list[RepairAttemptRecord] = Field(default_factory=list)


def _initial_stages() -> dict[PlanningStageName, PlanningStageStatus]:
    return {
        name: PlanningStageStatus(skipped=True, reason="not run")
        for name in STAGE_NAMES
    }


def _ok_stage() -> PlanningStageStatus:
    return PlanningStageStatus(ran=True, ok=True)


def _error_stage(diagnostic: Diagnostic) -> PlanningStageStatus:
    return PlanningStageStatus(ran=True, ok=False, diagnostics=[diagnostic])


def _skip_remaining(
    stages: dict[PlanningStageName, PlanningStageStatus],
    after: PlanningStageName,
) -> None:
    seen = False
    for name in STAGE_NAMES:
        if seen:
            stages[name] = PlanningStageStatus(skipped=True, reason=f"{after} failed")
        if name == after:
            seen = True


def _first_failed_stage(result: PlanningPipelineResult) -> PlanningStageName:
    for name in STAGE_NAMES:
        stage = result.stages.get(name)
        if stage is not None and stage.ran and not stage.ok:
            return name
    return "generation"


def _stage_diagnostic_codes(result: PlanningPipelineResult, stage: PlanningStageName) -> list[str]:
    status = result.stages.get(stage)
    if status is None:
        return [diagnostic.code for diagnostic in result.diagnostics]
    return [diagnostic.code for diagnostic in status.diagnostics]


def _parse_diagnostic(exc: AdapterParseError, *, source: PlanningSource) -> Diagnostic:
    return Diagnostic(
        code=E_PARSE_001,
        severity="error",
        message=f"failed to parse generated {source} plan",
        location=DiagnosticLocation(
            source=exc.source or source,
            path=exc.path,
            line=exc.line,
            column=exc.column,
        ),
        hint=str(exc),
    )


def _adapter_diagnostic(exc: Exception, *, source: PlanningSource) -> Diagnostic:
    return Diagnostic(
        code=E_PARSE_001 if isinstance(exc, AdapterParseError) else E_SCHEMA_002,
        severity="error",
        message=f"generated {source} plan failed adapter validation",
        location=DiagnosticLocation(source=source),
        hint=str(exc),
    )


def _runtime_diagnostic(exc: Exception, *, source: PlanningSource, stage: str) -> Diagnostic:
    return Diagnostic(
        code=E_RUNTIME_010,
        severity="error",
        message=f"{stage} failed during {source} planning",
        location=DiagnosticLocation(source=source),
        hint=str(exc),
    )


def _result_for_raw_text(
    *,
    source: PlanningSource,
    raw_text: str,
    compile_smoke: bool,
    seed_diagnostics: list[Diagnostic] | None = None,
    executor_registry: ExecutorRegistry | None = None,
    tool_registry: ToolCallableRegistry | None = None,
) -> PlanningPipelineResult:
    executors = executor_registry or builtin_executor_registry()
    stages = _initial_stages()
    diagnostics = list(seed_diagnostics or [])
    stages["generation"] = _ok_stage()

    try:
        plan = parse_prompt_plan_text(raw_text, source=source)
    except AdapterParseError as exc:
        diagnostic = _parse_diagnostic(exc, source=source)
        diagnostics.append(diagnostic)
        stages["parse"] = _error_stage(diagnostic)
        _skip_remaining(stages, "parse")
        return PlanningPipelineResult(
            ok=False,
            source=source,
            raw_text=raw_text,
            diagnostics=diagnostics,
            stages=stages,
        )
    stages["parse"] = _ok_stage()

    try:
        workflow = JSONPlanAdapter(executors=executors).parse(plan, source=source)
    except Exception as exc:
        diagnostic = _adapter_diagnostic(exc, source=source)
        diagnostics.append(diagnostic)
        stages["adapter"] = _error_stage(diagnostic)
        _skip_remaining(stages, "adapter")
        return PlanningPipelineResult(
            ok=False,
            source=source,
            raw_text=raw_text,
            plan=plan,
            diagnostics=diagnostics,
            stages=stages,
        )
    stages["adapter"] = _ok_stage()

    validation_report = validate_workflow(
        workflow,
        executors=executors,
        tool_registry=tool_registry,
    )
    stages["validation"] = PlanningStageStatus(
        ran=True,
        ok=validation_report.ok,
        diagnostics=validation_report.diagnostics,
    )
    diagnostics.extend(validation_report.diagnostics)
    if not validation_report.ok:
        _skip_remaining(stages, "validation")
        return PlanningPipelineResult(
            ok=False,
            source=source,
            raw_text=raw_text,
            plan=plan,
            workflow=workflow,
            validation_report=validation_report,
            diagnostics=diagnostics,
            stages=stages,
        )

    if compile_smoke:
        try:
            from prompt2langgraph.compiler.langgraph_py import compile_workflow_to_graph

            compile_workflow_to_graph(workflow, executors, tool_registry=tool_registry)
        except Exception as exc:
            diagnostic = _runtime_diagnostic(exc, source=source, stage="compile smoke")
            diagnostics.append(diagnostic)
            stages["compile_smoke"] = _error_stage(diagnostic)
            return PlanningPipelineResult(
                ok=False,
                source=source,
                raw_text=raw_text,
                plan=plan,
                workflow=workflow,
                validation_report=validation_report,
                diagnostics=diagnostics,
                stages=stages,
            )
        stages["compile_smoke"] = _ok_stage()
    else:
        stages["compile_smoke"] = PlanningStageStatus(
            skipped=True,
            reason="compile_smoke disabled",
        )

    return PlanningPipelineResult(
        ok=True,
        source=source,
        raw_text=raw_text,
        plan=plan,
        workflow=workflow,
        validation_report=validation_report,
        diagnostics=diagnostics,
        stages=stages,
    )


def _run_with_generation(
    *,
    source: PlanningSource,
    generate: Callable[[], str],
    compile_smoke: bool,
    repair_attempts: int,
    repair_context: dict[str, Any],
    get_repair_model_client: Callable[[], object | None],
    seed_diagnostics: list[Diagnostic] | None = None,
    executor_registry: ExecutorRegistry | None = None,
    tool_registry: ToolCallableRegistry | None = None,
) -> PlanningPipelineResult:
    seed = list(seed_diagnostics or [])
    try:
        raw_text = generate()
    except Exception as exc:
        diagnostic = _runtime_diagnostic(exc, source=source, stage="LLM call")
        stages = _initial_stages()
        stages["generation"] = _error_stage(diagnostic)
        _skip_remaining(stages, "generation")
        return PlanningPipelineResult(
            ok=False,
            source=source,
            diagnostics=[*seed, diagnostic],
            stages=stages,
        )

    result = _result_for_raw_text(
        source=source,
        raw_text=raw_text,
        compile_smoke=compile_smoke,
        seed_diagnostics=seed,
        executor_registry=executor_registry,
        tool_registry=tool_registry,
    )

    attempts: list[RepairAttemptRecord] = []
    for attempt_index in range(1, repair_attempts + 1):
        if result.ok:
            break
        trigger_stage = _first_failed_stage(result)
        messages = _build_repair_messages(
            source=source,
            raw_text=result.raw_text or "",
            diagnostics=result.diagnostics,
            trigger_stage=trigger_stage,
            context=repair_context,
        )
        try:
            repaired_text = _invoke_model_messages(get_repair_model_client(), messages)
        except Exception as exc:
            diagnostic = _runtime_diagnostic(exc, source=source, stage="repair LLM call")
            result.diagnostics.append(diagnostic)
            attempts.append(
                RepairAttemptRecord(
                    attempt_index=attempt_index,
                    trigger_stage=trigger_stage,
                    diagnostic_codes=_stage_diagnostic_codes(result, trigger_stage),
                    raw_text_preview="",
                    ok=False,
                )
            )
            break

        repaired_result = _result_for_raw_text(
            source=source,
            raw_text=repaired_text,
            compile_smoke=compile_smoke,
            seed_diagnostics=seed,
            executor_registry=executor_registry,
            tool_registry=tool_registry,
        )
        attempts.append(
            RepairAttemptRecord(
                attempt_index=attempt_index,
                trigger_stage=trigger_stage,
                diagnostic_codes=_stage_diagnostic_codes(result, trigger_stage),
                raw_text_preview=repaired_text[:500],
                ok=repaired_result.ok,
            )
        )
        result = repaired_result

    result.repair_attempts = attempts
    return result


def _build_repair_messages(
    *,
    source: PlanningSource,
    raw_text: str,
    diagnostics: list[Diagnostic],
    trigger_stage: PlanningStageName,
    context: dict[str, Any],
) -> list[dict[str, str]]:
    diagnostic_summary = [
        {
            "code": diagnostic.code,
            "severity": diagnostic.severity,
            "message": diagnostic.message,
            "hint": diagnostic.hint,
        }
        for diagnostic in diagnostics
        if diagnostic.severity == "error"
    ][:8]
    objective = context.get("prompt") or context.get("skill_dir") or source
    payload = {
        "source": source,
        "objective": str(objective)[:1000],
        "trigger_stage": trigger_stage,
        "diagnostics": diagnostic_summary,
        "raw_text_preview": raw_text[:1000],
        "required_output": "Return exactly one simplified JSON plan object and no markdown.",
    }
    return [
        {
            "role": "system",
            "content": (
                "Repair a prompt2langgraph simplified JSON plan. "
                "Do not include explanations, markdown fences, or secrets."
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def _invoke_model_messages(model_client: object | None, messages: list[dict[str, str]]) -> str:
    if model_client is None:
        raise RuntimeError("repair requires an existing model client")
    from prompt2langgraph.prompting.planner import _extract_response_content

    return _extract_response_content(model_client.invoke(messages))


def plan_prompt(
    request: Any,
    *,
    model_client: object | None = None,
    compile_smoke: bool = False,
    executor_registry: ExecutorRegistry | None = None,
    tool_registry: ToolCallableRegistry | None = None,
) -> PlanningPipelineResult:
    client_ref = {"client": model_client}

    return _run_with_generation(
        source="prompt",
        generate=lambda: _generate_prompt_raw_text(request, client_ref),
        compile_smoke=compile_smoke,
        repair_attempts=getattr(request, "repair_attempts", 0),
        repair_context={"prompt": getattr(request, "prompt", "")},
        get_repair_model_client=lambda: client_ref["client"],
        executor_registry=executor_registry,
        tool_registry=tool_registry,
    )


def plan_skill(
    request: Any,
    *,
    model_client: object | None = None,
    compile_smoke: bool = False,
    analysis: SkillDirectoryAnalysis | None = None,
    executor_registry: ExecutorRegistry | None = None,
    tool_registry: ToolCallableRegistry | None = None,
) -> PlanningPipelineResult:
    skill_analysis = analysis or analyze_skill_dir(request.skill_dir)
    seed_diagnostics = list(skill_analysis.report.diagnostics)
    fatal_diagnostics = [item for item in seed_diagnostics if item.severity == "error"]
    if fatal_diagnostics:
        stages = _initial_stages()
        stages["generation"] = PlanningStageStatus(
            skipped=True,
            reason="skill static analysis failed",
            diagnostics=fatal_diagnostics,
        )
        _skip_remaining(stages, "generation")
        return PlanningPipelineResult(
            ok=False,
            source="skill",
            diagnostics=seed_diagnostics,
            stages=stages,
        )

    client_ref = {"client": model_client}

    return _run_with_generation(
        source="skill",
        generate=lambda: _generate_skill_raw_text(
            request,
            skill_analysis,
            client_ref,
        ),
        compile_smoke=compile_smoke,
        repair_attempts=getattr(request, "repair_attempts", 0),
        repair_context={
            "skill_dir": getattr(request, "skill_dir", ""),
            "params": getattr(request, "params", {}),
        },
        get_repair_model_client=lambda: client_ref["client"],
        seed_diagnostics=seed_diagnostics,
        executor_registry=executor_registry,
        tool_registry=tool_registry,
    )


def _generate_prompt_raw_text(request: Any, client_ref: dict[str, object | None]) -> str:
    from prompt2langgraph.prompting.planner import build_model_client, generate_plan_text

    if client_ref["client"] is None:
        client_ref["client"] = build_model_client(request)
    return generate_plan_text(request, model_client=client_ref["client"]).raw_text


def _generate_skill_raw_text(
    request: Any,
    analysis: SkillDirectoryAnalysis,
    client_ref: dict[str, object | None],
) -> str:
    from prompt2langgraph.prompting.skill_planner import _build_model_client, generate_skill_plan_text

    if client_ref["client"] is None:
        client_ref["client"] = _build_model_client(request)
    return generate_skill_plan_text(
        request,
        analysis=analysis,
        model_client=client_ref["client"],
    ).raw_text


__all__ = [
    "PlanningPipelineResult",
    "PlanningSource",
    "PlanningStageName",
    "PlanningStageStatus",
    "RepairAttemptRecord",
    "plan_prompt",
    "plan_skill",
]
