"""Local runner for v0.1a Workflow IR."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from prompt2langgraph.compiler.langgraph_py import compile_workflow_to_graph
from prompt2langgraph.diagnostics.codes import E_RUNTIME_010, E_SCHEMA_002, E_TARGET_009
from prompt2langgraph.diagnostics.report import Diagnostic, DiagnosticLocation
from prompt2langgraph.ir.lockfile import sha256_canonical_json
from prompt2langgraph.ir.models import EdgeKind, WorkflowSpec
from prompt2langgraph.ir.normalize import normalize_workflow
from prompt2langgraph.registry.builtins import builtin_executor_registry
from prompt2langgraph.registry.executors import ExecutorRegistry
from prompt2langgraph.runtime.events import RunEvent, RunInterrupt, RunResult
from prompt2langgraph.validate.validator import validate_workflow

_THREAD_CHECKPOINTERS: dict[tuple[str, str], InMemorySaver] = {}
_PENDING_INTERRUPTS: set[tuple[str, str]] = set()


def run_workflow(
    workflow: WorkflowSpec,
    input_payload: dict[str, Any],
    *,
    executors: ExecutorRegistry | None = None,
    thread_id: str | None = None,
    resume_payload: Any | None = None,
) -> RunResult:
    run_id = _new_id("run")
    thread_id = thread_id or _new_id("thread")
    events = [RunEvent(type="run.started", run_id=run_id, thread_id=thread_id)]
    if resume_payload is not None:
        events.append(RunEvent(type="run.resumed", run_id=run_id, thread_id=thread_id))
    executor_registry = executors or builtin_executor_registry()

    report = validate_workflow(workflow, executors=executor_registry)
    if not report.ok:
        return _failed_result(run_id, thread_id, events, report.diagnostics)

    thread_key = _thread_key(workflow, thread_id)
    if resume_payload is not None and thread_key not in _PENDING_INTERRUPTS:
        return _failed_result(
            run_id,
            thread_id,
            events,
            [
                Diagnostic(
                    code=E_RUNTIME_010,
                    severity="error",
                    message=f'no pending interrupt for thread "{thread_id}"',
                )
            ],
        )

    input_diagnostics = [] if resume_payload is not None else _check_input_payload(workflow, input_payload)
    if input_diagnostics:
        return _failed_result(run_id, thread_id, events, input_diagnostics)

    target_diagnostics = _check_target_capabilities(workflow)
    if target_diagnostics:
        return _failed_result(run_id, thread_id, events, target_diagnostics)

    def record_node_event(event_type: str, node_id: str) -> None:
        events.append(RunEvent(type=event_type, run_id=run_id, thread_id=thread_id, node_id=node_id))

    try:
        checkpointer = _checkpointer_for(thread_key)
        graph = compile_workflow_to_graph(
            workflow,
            executor_registry,
            event_sink=record_node_event,
            checkpointer=checkpointer,
        )
        graph_input: dict[str, Any] | Command = (
            Command(resume=resume_payload) if resume_payload is not None else input_payload
        )
        final_state = graph.invoke(
            graph_input,
            config={"configurable": {"thread_id": thread_id}},
        )
    except Exception as exc:
        if resume_payload is not None:
            _clear_thread(thread_key)
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

    interrupt = _extract_interrupt(final_state, events)
    if interrupt is not None:
        _PENDING_INTERRUPTS.add(thread_key)
        return RunResult(
            status="waiting",
            run_id=run_id,
            thread_id=thread_id,
            output={},
            events=events,
            diagnostics=[],
            interrupt=interrupt,
        )

    _clear_thread(thread_key)
    events.append(RunEvent(type="run.finished", run_id=run_id, thread_id=thread_id))
    return RunResult(
        status="succeeded",
        run_id=run_id,
        thread_id=thread_id,
        output=_declared_output(workflow, final_state),
        events=events,
        diagnostics=[],
    )


def _checkpointer_for(thread_key: tuple[str, str]) -> InMemorySaver:
    return _THREAD_CHECKPOINTERS.setdefault(thread_key, InMemorySaver())


def _thread_key(workflow: WorkflowSpec, thread_id: str) -> tuple[str, str]:
    workflow_hash = sha256_canonical_json(normalize_workflow(workflow).model_dump(mode="json"))
    return workflow_hash, thread_id


def _clear_thread(thread_key: tuple[str, str]) -> None:
    _PENDING_INTERRUPTS.discard(thread_key)
    _THREAD_CHECKPOINTERS.pop(thread_key, None)


def _extract_interrupt(state: dict[str, Any], events: list[RunEvent]) -> RunInterrupt | None:
    interrupts = state.get("__interrupt__")
    if not interrupts:
        return None

    interrupt_value = interrupts[0].value
    payload = interrupt_value if isinstance(interrupt_value, dict) else {"value": interrupt_value}
    node_id = next((event.node_id for event in reversed(events) if event.type == "node.started"), None)
    node_id = node_id or "unknown"
    run_id = events[0].run_id
    thread_id = events[0].thread_id
    events.append(
        RunEvent(
            type="node.interrupted",
            run_id=run_id,
            thread_id=thread_id,
            node_id=node_id,
            payload=payload,
        )
    )
    return RunInterrupt(node_id=node_id, payload=payload)


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
        if edge.kind not in {EdgeKind.LINEAR, EdgeKind.CONDITIONAL}:
            diagnostics.append(
                Diagnostic(
                    code=E_TARGET_009,
                    severity="error",
                    message=f'edge kind "{edge.kind.value}" is not supported by v0.1c LangGraph compiler',
                    location=DiagnosticLocation(edge_id=edge.id),
                )
            )
    return diagnostics
