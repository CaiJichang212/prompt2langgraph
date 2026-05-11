"""Local runner for v0.1a Workflow IR."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from prompt2langgraph.compiler.langgraph_py import compile_workflow_to_graph
from prompt2langgraph.diagnostics.codes import E_RUNTIME_010, E_SCHEMA_002, E_TARGET_009
from prompt2langgraph.diagnostics.report import Diagnostic, DiagnosticLocation
from prompt2langgraph.ir.models import EdgeKind, WorkflowSpec
from prompt2langgraph.registry.builtins import builtin_executor_registry
from prompt2langgraph.registry.executors import ExecutorRegistry
from prompt2langgraph.runtime.events import RunEvent, RunResult
from prompt2langgraph.validate.validator import validate_workflow


def run_workflow(
    workflow: WorkflowSpec,
    input_payload: dict[str, Any],
    *,
    executors: ExecutorRegistry | None = None,
) -> RunResult:
    run_id = _new_id("run")
    thread_id = _new_id("thread")
    events = [RunEvent(type="run.started", run_id=run_id, thread_id=thread_id)]
    executor_registry = executors or builtin_executor_registry()

    report = validate_workflow(workflow, executors=executor_registry)
    if not report.ok:
        return _failed_result(run_id, thread_id, events, report.diagnostics)

    input_diagnostics = _check_input_payload(workflow, input_payload)
    if input_diagnostics:
        return _failed_result(run_id, thread_id, events, input_diagnostics)

    target_diagnostics = _check_target_capabilities(workflow)
    if target_diagnostics:
        return _failed_result(run_id, thread_id, events, target_diagnostics)

    def record_node_event(event_type: str, node_id: str) -> None:
        events.append(RunEvent(type=event_type, run_id=run_id, thread_id=thread_id, node_id=node_id))

    try:
        graph = compile_workflow_to_graph(workflow, executor_registry, event_sink=record_node_event)
        final_state = graph.invoke(
            input_payload,
            config={"configurable": {"thread_id": thread_id}},
        )
    except Exception as exc:
        return _failed_result(
            run_id,
            thread_id,
            events,
            [
                Diagnostic(
                    code=E_RUNTIME_010,
                    severity="error",
                    message="workflow runtime invocation failed",
                    hint=str(exc),
                )
            ],
        )

    events.append(RunEvent(type="run.finished", run_id=run_id, thread_id=thread_id))
    return RunResult(
        status="succeeded",
        run_id=run_id,
        thread_id=thread_id,
        output=_declared_output(workflow, final_state),
        events=events,
        diagnostics=[],
    )


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _declared_output(workflow: WorkflowSpec, state: dict[str, Any]) -> dict[str, Any]:
    return {key: state[key] for key in workflow.state_schema.output if key in state}


def _failed_result(
    run_id: str,
    thread_id: str,
    events: list[RunEvent],
    diagnostics: list[Diagnostic],
) -> RunResult:
    events.append(RunEvent(type="run.failed", run_id=run_id, thread_id=thread_id))
    return RunResult(
        status="failed",
        run_id=run_id,
        thread_id=thread_id,
        output={},
        events=events,
        diagnostics=diagnostics,
    )


def _check_input_payload(workflow: WorkflowSpec, input_payload: dict[str, Any]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for state_key in workflow.state_schema.input:
        if state_key not in input_payload:
            diagnostics.append(
                Diagnostic(
                    code=E_SCHEMA_002,
                    severity="error",
                    message=f'required input state key "{state_key}" is missing',
                    location=DiagnosticLocation(state_key=state_key),
                )
            )
    return diagnostics


def _check_target_capabilities(workflow: WorkflowSpec) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for edge in workflow.edges:
        if edge.kind is not EdgeKind.LINEAR:
            diagnostics.append(
                Diagnostic(
                    code=E_TARGET_009,
                    severity="error",
                    message=f'edge kind "{edge.kind.value}" is not supported by v0.1a LangGraph compiler',
                    location=DiagnosticLocation(edge_id=edge.id),
                )
            )
    return diagnostics
