"""Local runner for v0.1a Workflow IR."""

from __future__ import annotations

import base64
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from time import perf_counter
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
from prompt2langgraph.runtime.events import ExternalCallRecord, RunEvent, RunInterrupt, RunMetrics, RunResult
from prompt2langgraph.validate.validator import validate_workflow

_THREAD_CHECKPOINTERS: dict[tuple[str, str], InMemorySaver] = {}
_PENDING_INTERRUPTS: set[tuple[str, str]] = set()
_NO_RESUME = object()
LOCAL_STATE_FORMAT_VERSION = 1


def run_workflow(
    workflow: WorkflowSpec,
    input_payload: dict[str, Any],
    *,
    executors: ExecutorRegistry | None = None,
    thread_id: str | None = None,
    resume_payload: Any = _NO_RESUME,
    state_store_dir: Path | None = None,
    model_client: Any | None = None,
    tool_registry: Any | None = None,
) -> RunResult:
    started_at = perf_counter()
    run_id = _new_id("run")
    thread_id = thread_id or _new_id("thread")
    is_resume = resume_payload is not _NO_RESUME
    events = [RunEvent(type="run.started", run_id=run_id, thread_id=thread_id)]
    if is_resume:
        events.append(RunEvent(type="run.resumed", run_id=run_id, thread_id=thread_id))
    executor_registry = executors or builtin_executor_registry()

    report = validate_workflow(workflow, executors=executor_registry)
    if not report.ok:
        return _failed_result(run_id, thread_id, events, report.diagnostics, started_at)

    thread_key = _thread_key(workflow, thread_id)
    if is_resume and state_store_dir is not None:
        state_diagnostic = _load_thread_state(thread_key, state_store_dir)
        if state_diagnostic is not None:
            return _failed_result(run_id, thread_id, events, [state_diagnostic], started_at)
    if is_resume and thread_key not in _PENDING_INTERRUPTS:
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
            started_at,
        )

    input_diagnostics = [] if is_resume else _check_input_payload(workflow, input_payload)
    if input_diagnostics:
        return _failed_result(run_id, thread_id, events, input_diagnostics, started_at)

    target_diagnostics = _check_target_capabilities(workflow)
    if target_diagnostics:
        if is_resume:
            _clear_thread(thread_key, state_store_dir)
        return _failed_result(run_id, thread_id, events, target_diagnostics, started_at)

    external_calls: list[ExternalCallRecord] = []

    def _error_sink(exc: Exception) -> None:
        from prompt2langgraph.registry.executors import ExecutorError

        if isinstance(exc, ExecutorError):
            external_calls.append(
                ExternalCallRecord(
                    node_id=exc.node_id or "unknown",
                    executor_ref=exc.executor_ref or "unknown",
                    status="failed",
                    error_code=exc.code,
                )
            )

    def _metrics_sink(record: ExternalCallRecord) -> None:
        external_calls.append(record)

    def record_node_event(event_type: str, node_id: str) -> None:
        events.append(
            RunEvent(type=event_type, run_id=run_id, thread_id=thread_id, node_id=node_id)
        )

    try:
        checkpointer = _checkpointer_for(thread_key)
        graph = compile_workflow_to_graph(
            workflow,
            executor_registry,
            event_sink=record_node_event,
            checkpointer=checkpointer,
            policies=workflow.policies,
            model_client=model_client,
            tool_registry=tool_registry,
            error_sink=_error_sink,
            metrics_sink=_metrics_sink,
        )
        graph_input: dict[str, Any] | Command = (
            Command(resume=resume_payload) if is_resume else input_payload
        )
        final_state = graph.invoke(
            graph_input,
            config={"configurable": {"thread_id": thread_id}},
        )
    except Exception as exc:
        if is_resume:
            _clear_thread(thread_key, state_store_dir)
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
            started_at,
            external_calls=external_calls,
        )

    interrupt = _extract_interrupt(final_state, events)
    if interrupt is not None:
        _PENDING_INTERRUPTS.add(thread_key)
        if state_store_dir is not None:
            _save_thread_state(thread_key, state_store_dir)
        return RunResult(
            status="waiting",
            run_id=run_id,
            thread_id=thread_id,
            output={},
            events=events,
            diagnostics=[],
            interrupt=interrupt,
            metrics=RunMetrics(
                duration_ms=_duration_ms(started_at),
                call_count=len(external_calls),
                total_latency_ms=sum(r.latency_ms for r in external_calls if r.latency_ms is not None) or None,
            ),
            external_calls=external_calls,
        )

    _clear_thread(thread_key, state_store_dir)
    events.append(RunEvent(type="run.finished", run_id=run_id, thread_id=thread_id))
    return RunResult(
        status="succeeded",
        run_id=run_id,
        thread_id=thread_id,
        output=_declared_output(workflow, final_state),
        events=events,
        diagnostics=[],
        metrics=RunMetrics(
            duration_ms=_duration_ms(started_at),
            call_count=len(external_calls),
            total_latency_ms=sum(r.latency_ms for r in external_calls if r.latency_ms is not None) or None,
        ),
        external_calls=external_calls,
    )


def _checkpointer_for(thread_key: tuple[str, str]) -> InMemorySaver:
    return _THREAD_CHECKPOINTERS.setdefault(thread_key, InMemorySaver())


def _thread_key(workflow: WorkflowSpec, thread_id: str) -> tuple[str, str]:
    workflow_hash = sha256_canonical_json(normalize_workflow(workflow).model_dump(mode="json"))
    return workflow_hash, thread_id


def _clear_thread(thread_key: tuple[str, str], state_store_dir: Path | None = None) -> None:
    _PENDING_INTERRUPTS.discard(thread_key)
    _THREAD_CHECKPOINTERS.pop(thread_key, None)
    if state_store_dir is not None:
        _state_file(thread_key, state_store_dir).unlink(missing_ok=True)


# Runtime Persistence Contract
# ============================
# The JSON snapshot helpers below (_save_thread_state, _load_thread_state, and
# related serialization functions) provide a best-effort local resume format for
# the CLI. This format is coupled to the current LangGraph InMemorySaver internals
# and must NOT be treated as a stable interchange format. The structure may change
# across LangGraph or prompt2langgraph versions; the version check only prevents
# restoring incompatible local snapshots as pending interrupts. It is intended
# solely for short-lived local development workflows and should not be used for
# long-term storage or cross-system communication.
def _save_thread_state(thread_key: tuple[str, str], state_store_dir: Path) -> None:
    checkpointer = _THREAD_CHECKPOINTERS.get(thread_key)
    if checkpointer is None:
        return

    workflow_hash, thread_id = thread_key
    state_store_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "format_version": LOCAL_STATE_FORMAT_VERSION,
        "workflow_hash": workflow_hash,
        "thread_id": thread_id,
        "pending": thread_key in _PENDING_INTERRUPTS,
        "storage": _serialize_storage(checkpointer, thread_id),
        "writes": _serialize_writes(checkpointer, thread_id),
        "blobs": _serialize_blobs(checkpointer, thread_id),
    }
    _state_file(thread_key, state_store_dir).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _load_thread_state(thread_key: tuple[str, str], state_store_dir: Path) -> Diagnostic | None:
    path = _state_file(thread_key, state_store_dir)
    if not path.exists():
        return None

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format_version") != LOCAL_STATE_FORMAT_VERSION:
        return Diagnostic(
            code=E_RUNTIME_010,
            severity="error",
            message="local runtime state format version is missing or unsupported",
            hint=(
                "Remove the stale .pt2lg-runtime state file and re-run the workflow "
                "to create a fresh pending interrupt."
            ),
        )
    if payload.get("workflow_hash") != thread_key[0] or payload.get("thread_id") != thread_key[1]:
        return None

    checkpointer = InMemorySaver()
    _restore_storage(checkpointer, payload.get("storage", []))
    _restore_writes(checkpointer, payload.get("writes", []))
    _restore_blobs(checkpointer, payload.get("blobs", []))
    _THREAD_CHECKPOINTERS[thread_key] = checkpointer
    if payload.get("pending") is True:
        _PENDING_INTERRUPTS.add(thread_key)
    return None


def _state_file(thread_key: tuple[str, str], state_store_dir: Path) -> Path:
    digest = hashlib.sha256("\0".join(thread_key).encode("utf-8")).hexdigest()
    return state_store_dir / f"{digest}.json"


def _serialize_storage(checkpointer: InMemorySaver, thread_id: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for checkpoint_ns, checkpoints in checkpointer.storage.get(thread_id, {}).items():
        for checkpoint_id, (checkpoint, metadata, parent_checkpoint_id) in checkpoints.items():
            entries.append(
                {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                    "checkpoint": _serialize_typed_bytes(checkpoint),
                    "metadata": _serialize_typed_bytes(metadata),
                    "parent_checkpoint_id": parent_checkpoint_id,
                }
            )
    return entries


def _serialize_writes(checkpointer: InMemorySaver, thread_id: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for (write_thread_id, checkpoint_ns, checkpoint_id), writes in checkpointer.writes.items():
        if write_thread_id != thread_id:
            continue
        for (key_task_id, idx), (task_id, channel, value, task_path) in writes.items():
            entries.append(
                {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                    "key_task_id": key_task_id,
                    "idx": idx,
                    "task_id": task_id,
                    "channel": channel,
                    "value": _serialize_typed_bytes(value),
                    "task_path": task_path,
                }
            )
    return entries


def _serialize_blobs(checkpointer: InMemorySaver, thread_id: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for (blob_thread_id, checkpoint_ns, channel, version), value in checkpointer.blobs.items():
        if blob_thread_id != thread_id:
            continue
        entries.append(
            {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "channel": channel,
                "version": version,
                "value": _serialize_typed_bytes(value),
            }
        )
    return entries


def _restore_storage(checkpointer: InMemorySaver, entries: list[dict[str, Any]]) -> None:
    storage = defaultdict(lambda: defaultdict(dict))
    for entry in entries:
        storage[entry["thread_id"]][entry["checkpoint_ns"]][entry["checkpoint_id"]] = (
            _deserialize_typed_bytes(entry["checkpoint"]),
            _deserialize_typed_bytes(entry["metadata"]),
            entry["parent_checkpoint_id"],
        )
    checkpointer.storage = storage


def _restore_writes(checkpointer: InMemorySaver, entries: list[dict[str, Any]]) -> None:
    writes = defaultdict(dict)
    for entry in entries:
        key = (entry["thread_id"], entry["checkpoint_ns"], entry["checkpoint_id"])
        writes[key][(entry["key_task_id"], entry["idx"])] = (
            entry["task_id"],
            entry["channel"],
            _deserialize_typed_bytes(entry["value"]),
            entry["task_path"],
        )
    checkpointer.writes = writes


def _restore_blobs(checkpointer: InMemorySaver, entries: list[dict[str, Any]]) -> None:
    blobs = defaultdict(None)
    for entry in entries:
        blobs[(entry["thread_id"], entry["checkpoint_ns"], entry["channel"], entry["version"])] = (
            _deserialize_typed_bytes(entry["value"])
        )
    checkpointer.blobs = blobs


def _serialize_typed_bytes(value: tuple[str, bytes]) -> dict[str, str]:
    value_type, data = value
    return {"type": value_type, "data": base64.b64encode(data).decode("ascii")}


def _deserialize_typed_bytes(value: dict[str, str]) -> tuple[str, bytes]:
    return value["type"], base64.b64decode(value["data"].encode("ascii"))


def _extract_interrupt(state: dict[str, Any], events: list[RunEvent]) -> RunInterrupt | None:
    interrupts = state.get("__interrupt__")
    if not interrupts:
        return None

    interrupt_value = interrupts[0].value
    payload = interrupt_value if isinstance(interrupt_value, dict) else {"value": interrupt_value}
    node_id = next(
        (event.node_id for event in reversed(events) if event.type == "node.started"), None
    )
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


def _duration_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 3)


def _declared_output(workflow: WorkflowSpec, state: dict[str, Any]) -> dict[str, Any]:
    return {key: state[key] for key in workflow.state_schema.output if key in state}


def _failed_result(
    run_id: str,
    thread_id: str,
    events: list[RunEvent],
    diagnostics: list[Diagnostic],
    started_at: float,
    external_calls: list[ExternalCallRecord] | None = None,
) -> RunResult:
    events.append(RunEvent(type="run.failed", run_id=run_id, thread_id=thread_id))
    calls = external_calls or []
    return RunResult(
        status="failed",
        run_id=run_id,
        thread_id=thread_id,
        output={},
        events=events,
        diagnostics=diagnostics,
        metrics=RunMetrics(
            duration_ms=_duration_ms(started_at),
            call_count=len(calls),
            total_latency_ms=sum(r.latency_ms for r in calls if r.latency_ms is not None) or None,
        ),
        external_calls=calls,
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
    supported = {EdgeKind.LINEAR, EdgeKind.CONDITIONAL, EdgeKind.LOOP, EdgeKind.FANOUT}
    for edge in workflow.edges:
        if edge.kind not in supported:
            diagnostics.append(
                Diagnostic(
                    code=E_TARGET_009,
                    severity="error",
                    message=(
                        f'edge kind "{edge.kind.value}" is not supported by the LangGraph runner'
                    ),
                    location=DiagnosticLocation(edge_id=edge.id),
                )
            )
    return diagnostics
