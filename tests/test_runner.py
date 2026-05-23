import json
from pathlib import Path

import pytest

from prompt2langgraph.ir.models import ExecutorType, TypeName, TypeSpec, WorkflowSpec
from prompt2langgraph.registry.executors import ExecutorDefinition, ExecutorRegistry
from prompt2langgraph.runtime import runner
from prompt2langgraph.runtime.events import ExternalCallRecord, RunMetrics, RunResult
from prompt2langgraph.runtime.runner import run_workflow

FIXTURES = Path(__file__).parent / "fixtures"


def load_workflow(name: str) -> WorkflowSpec:
    return WorkflowSpec.model_validate(json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def test_run_workflow_invokes_linear_llm_and_returns_declared_output() -> None:
    result = run_workflow(load_workflow("linear_llm.json"), {"question": "hello"})

    assert result.status == "succeeded"
    assert result.run_id.startswith("run_")
    assert result.thread_id.startswith("thread_")
    assert result.output == {"answer": "Answer: hello"}
    assert result.diagnostics == []
    assert [event.type for event in result.events] == [
        "run.started",
        "node.started",
        "node.finished",
        "run.finished",
    ]
    assert result.events[1].node_id == "compose"


def test_run_workflow_invokes_multi_node_retriever_llm_chain() -> None:
    result = run_workflow(load_workflow("linear_retriever_llm.json"), {"question": "hello"})

    assert result.status == "succeeded"
    assert result.output == {
        "docs_ref": "mock://retriever/hello",
        "answer": "Answer from mock://retriever/hello",
    }
    assert [event.node_id for event in result.events if event.type == "node.started"] == [
        "retrieve",
        "prepare_context",
        "compose",
    ]
    assert result.diagnostics == []


def test_run_workflow_invokes_tool_node_workflow() -> None:
    result = run_workflow(load_workflow("tool_identity.json"), {"question": "hello"})

    assert result.status == "succeeded"
    assert result.output == {"tool_result": "hello"}
    assert [event.node_id for event in result.events if event.type == "node.started"] == [
        "call_tool"
    ]
    assert result.diagnostics == []


def test_run_workflow_invokes_allowed_side_effect_node() -> None:
    result = run_workflow(load_workflow("side_effect_allowed.json"), {"question": "hello"})

    assert result.status == "succeeded"
    assert result.output == {"effect_result": "hello"}
    assert [event.node_id for event in result.events if event.type == "node.started"] == [
        "record_effect"
    ]
    assert result.diagnostics == []


def test_run_workflow_returns_metrics() -> None:
    result = run_workflow(load_workflow("linear_llm.json"), {"question": "hello"})

    assert result.status == "succeeded"
    assert result.metrics.duration_ms is not None
    assert result.metrics.retry_count == 0
    assert result.metrics.tool_call_count == 0
    assert result.tool_calls == []


def test_run_workflow_returns_validation_diagnostics_without_invoking() -> None:
    data = json.loads((FIXTURES / "linear_llm.json").read_text(encoding="utf-8"))
    data["nodes"][0]["executor"]["ref"] = "missing.executor"
    workflow = WorkflowSpec.model_validate(data)

    result = run_workflow(workflow, {"question": "hello"})

    assert result.status == "failed"
    assert result.output == {}
    assert result.metrics.duration_ms is not None
    assert result.tool_calls == []
    assert any(diagnostic.code == "E_BIND_006" for diagnostic in result.diagnostics)


def test_run_workflow_rejects_missing_required_input_payload_key() -> None:
    result = run_workflow(load_workflow("linear_llm.json"), {})

    assert result.status == "failed"
    assert result.output == {}
    assert any(
        diagnostic.code == "E_SCHEMA_002" and diagnostic.location.state_key == "question"
        for diagnostic in result.diagnostics
    )


def test_run_workflow_wraps_runtime_exceptions_as_diagnostics() -> None:
    data = json.loads((FIXTURES / "linear_llm.json").read_text(encoding="utf-8"))
    data["nodes"][0]["params"] = {"template": "Answer: {missing}"}
    workflow = WorkflowSpec.model_validate(data)

    result = run_workflow(workflow, {"question": "hello"})

    assert result.status == "failed"
    assert result.output == {}
    assert any(diagnostic.code == "E_RUNTIME_010" for diagnostic in result.diagnostics)


def test_run_workflow_fails_when_executor_omits_declared_output() -> None:
    registry = ExecutorRegistry(
        [
            ExecutorDefinition(
                ref="builtin.echo_llm",
                type=ExecutorType.BUILTIN,
                input_schema={"question": TypeSpec(type=TypeName.STRING)},
                output_schema={"answer": TypeSpec(type=TypeName.STRING)},
                handler=lambda inputs, params: {},
            )
        ]
    )

    result = run_workflow(
        load_workflow("linear_llm.json"), {"question": "hello"}, executors=registry
    )

    assert result.status == "failed"
    assert result.output == {}
    assert any(
        diagnostic.code == "E_RUNTIME_010" and "answer" in diagnostic.hint
        for diagnostic in result.diagnostics
    )


def test_run_workflow_reports_actual_node_events_for_failed_node() -> None:
    data = json.loads((FIXTURES / "linear_llm.json").read_text(encoding="utf-8"))
    data["nodes"][0]["params"] = {"template": "Answer: {missing}"}
    workflow = WorkflowSpec.model_validate(data)

    result = run_workflow(workflow, {"question": "hello"})

    assert [event.type for event in result.events] == ["run.started", "node.started", "run.failed"]
    assert result.events[1].node_id == "compose"


def test_run_workflow_rejects_unsupported_edge_kind_as_target_diagnostic() -> None:
    result = run_workflow(load_workflow("invalid_join_edge.json"), {"question": "hello"})

    assert result.status == "failed"
    assert result.output == {}
    assert any(diagnostic.code == "E_TARGET_009" for diagnostic in result.diagnostics)


def test_run_workflow_waits_at_human_gate_and_resumes_with_same_thread() -> None:
    workflow = load_workflow("conditional_human_gate.json")

    waiting = run_workflow(workflow, {"question": "hello", "confidence": 0.5})

    assert waiting.status == "waiting"
    assert waiting.interrupt is not None
    assert waiting.interrupt.node_id == "approval"
    assert waiting.interrupt.payload == {"message": "Approve low-confidence answer?"}
    assert waiting.output == {}
    assert waiting.metrics.duration_ms is not None
    assert waiting.tool_calls == []
    assert [event.type for event in waiting.events] == [
        "run.started",
        "node.started",
        "node.finished",
        "node.started",
        "node.interrupted",
    ]
    assert waiting.events[-1].node_id == "approval"

    resumed = run_workflow(
        workflow,
        {},
        thread_id=waiting.thread_id,
        resume_payload="approved",
    )

    assert resumed.status == "succeeded"
    assert resumed.thread_id == waiting.thread_id
    assert resumed.output == {"answer": "Answer: hello"}
    assert [event.type for event in resumed.events] == [
        "run.started",
        "run.resumed",
        "node.started",
        "node.finished",
        "node.started",
        "node.finished",
        "run.finished",
    ]


def test_run_workflow_rejects_resume_without_pending_interrupt() -> None:
    workflow = load_workflow("conditional_human_gate.json")

    result = run_workflow(workflow, {}, thread_id="missing_thread", resume_payload="approved")

    assert result.status == "failed"
    assert result.output == {}
    assert any(
        diagnostic.code == "E_RUNTIME_010" and "no pending interrupt" in diagnostic.message
        for diagnostic in result.diagnostics
    )


def test_run_workflow_rejects_second_resume_after_interrupt_completes() -> None:
    workflow = load_workflow("conditional_human_gate.json")
    waiting = run_workflow(workflow, {"question": "hello", "confidence": 0.5})
    resumed = run_workflow(workflow, {}, thread_id=waiting.thread_id, resume_payload="approved")

    second_resume = run_workflow(
        workflow, {}, thread_id=waiting.thread_id, resume_payload="approved again"
    )

    assert resumed.status == "succeeded"
    assert second_resume.status == "failed"
    assert second_resume.output == {}
    assert any(
        diagnostic.code == "E_RUNTIME_010" and "no pending interrupt" in diagnostic.message
        for diagnostic in second_resume.diagnostics
    )


def test_run_workflow_rejects_resume_when_workflow_changed_for_same_thread() -> None:
    workflow = load_workflow("conditional_human_gate.json")
    changed_data = json.loads(
        (FIXTURES / "conditional_human_gate.json").read_text(encoding="utf-8")
    )
    changed_data["nodes"][2]["params"] = {"template": "Changed: {question}"}
    changed_workflow = WorkflowSpec.model_validate(changed_data)
    waiting = run_workflow(workflow, {"question": "hello", "confidence": 0.5})

    result = run_workflow(
        changed_workflow, {}, thread_id=waiting.thread_id, resume_payload="approved"
    )

    assert result.status == "failed"
    assert result.output == {}
    assert any(
        diagnostic.code == "E_RUNTIME_010" and "no pending interrupt" in diagnostic.message
        for diagnostic in result.diagnostics
    )


def test_run_workflow_invokes_guarded_loop() -> None:
    result = run_workflow(load_workflow("loop_with_guard.json"), {"question": "hello"})

    assert result.status == "succeeded"
    assert result.output == {"answer": "Answer: hello"}
    assert [event.node_id for event in result.events if event.type == "node.started"] == [
        "compose",
        "compose",
        "finalize",
    ]
    assert result.diagnostics == []


def test_run_workflow_invokes_fanout_map_reduce() -> None:
    result = run_workflow(load_workflow("fanout_map_reduce.json"), {"items": ["alpha", "beta"]})

    assert result.status == "succeeded"
    assert sorted(result.output["results"]) == ["alpha", "beta"]
    assert result.diagnostics == []


def test_run_workflow_persists_state_to_store_dir_and_removes_on_resume(tmp_path: Path) -> None:
    """Test runtime state isolation and cleanup after successful resume."""
    workflow = load_workflow("conditional_human_gate.json")
    state_store_dir = tmp_path / ".pt2lg-runtime"

    # First run should create a waiting state and persist to state_store_dir
    waiting = run_workflow(
        workflow,
        {"question": "hello", "confidence": 0.5},
        state_store_dir=state_store_dir,
    )

    assert waiting.status == "waiting"
    assert waiting.interrupt is not None

    # State directory should exist and contain state file
    assert state_store_dir.exists()
    state_files = list(state_store_dir.glob("*.json"))
    assert len(state_files) == 1, "Expected exactly one state file after interrupt"
    state_payload = json.loads(state_files[0].read_text(encoding="utf-8"))
    assert state_payload["format_version"] == runner.LOCAL_STATE_FORMAT_VERSION

    # Resume should succeed and clean up state file
    resumed = run_workflow(
        workflow,
        {},
        thread_id=waiting.thread_id,
        resume_payload="approved",
        state_store_dir=state_store_dir,
    )

    assert resumed.status == "succeeded"
    assert resumed.thread_id == waiting.thread_id

    # State file should be removed after successful resume
    remaining_state_files = list(state_store_dir.glob("*.json"))
    assert remaining_state_files == [], "State file should be removed after successful resume"


@pytest.mark.parametrize("format_version", [None, runner.LOCAL_STATE_FORMAT_VERSION + 1])
def test_run_workflow_rejects_incompatible_state_store_file_format_version(
    tmp_path: Path,
    format_version: int | None,
) -> None:
    workflow = load_workflow("conditional_human_gate.json")
    state_store_dir = tmp_path / ".pt2lg-runtime"

    waiting = run_workflow(
        workflow,
        {"question": "hello", "confidence": 0.5},
        state_store_dir=state_store_dir,
    )
    assert waiting.status == "waiting"

    state_file = next(state_store_dir.glob("*.json"))
    state_payload = json.loads(state_file.read_text(encoding="utf-8"))
    if format_version is None:
        state_payload.pop("format_version")
    else:
        state_payload["format_version"] = format_version
    state_file.write_text(json.dumps(state_payload), encoding="utf-8")

    # Simulate a new process where only the local state file is available.
    runner._clear_thread(runner._thread_key(workflow, waiting.thread_id))

    result = run_workflow(
        workflow,
        {},
        thread_id=waiting.thread_id,
        resume_payload="approved",
        state_store_dir=state_store_dir,
    )

    assert result.status == "failed"
    assert result.output == {}
    assert any(
        diagnostic.code == "E_RUNTIME_010" and "state format version" in diagnostic.message
        for diagnostic in result.diagnostics
    )


def test_run_workflow_ignores_incompatible_state_store_file_for_new_run(tmp_path: Path) -> None:
    workflow = load_workflow("conditional_human_gate.json")
    state_store_dir = tmp_path / ".pt2lg-runtime"

    waiting = run_workflow(
        workflow,
        {"question": "hello", "confidence": 0.5},
        state_store_dir=state_store_dir,
    )
    assert waiting.status == "waiting"

    state_file = next(state_store_dir.glob("*.json"))
    state_payload = json.loads(state_file.read_text(encoding="utf-8"))
    state_payload.pop("format_version")
    state_file.write_text(json.dumps(state_payload), encoding="utf-8")

    # Simulate a new process where only the stale local resume file remains.
    runner._clear_thread(runner._thread_key(workflow, waiting.thread_id))

    result = run_workflow(
        workflow,
        {"question": "hello", "confidence": 0.9},
        thread_id=waiting.thread_id,
        state_store_dir=state_store_dir,
    )

    assert result.status == "succeeded"
    assert result.output == {"answer": "Answer: hello"}
    assert result.diagnostics == []


def test_run_metrics_new_fields_default_values() -> None:
    """RunMetrics 新增字段 call_count 和 total_latency_ms 默认值正确。"""
    metrics = RunMetrics()
    assert metrics.call_count == 0
    assert metrics.total_latency_ms is None


def test_external_call_record_fields() -> None:
    """ExternalCallRecord 字段正确。"""
    record = ExternalCallRecord(
        node_id="compose",
        executor_ref="builtin.echo_llm",
        model="qwen-plus",
        latency_ms=123.4,
        token_count=50,
        status="succeeded",
    )
    assert record.node_id == "compose"
    assert record.executor_ref == "builtin.echo_llm"
    assert record.model == "qwen-plus"
    assert record.latency_ms == 123.4
    assert record.token_count == 50
    assert record.status == "succeeded"
    assert record.error_code is None


def test_external_call_record_failed_status() -> None:
    """失败调用记录 status="failed"。"""
    record = ExternalCallRecord(
        node_id="compose",
        executor_ref="unknown",
        status="failed",
        error_code="E_SEC_013",
    )
    assert record.status == "failed"
    assert record.error_code == "E_SEC_013"


def test_run_result_external_calls_default_empty() -> None:
    """RunResult.external_calls 默认为空列表。"""
    result = RunResult(
        status="succeeded",
        run_id="run_test",
        thread_id="thread_test",
    )
    assert result.external_calls == []


def test_run_workflow_result_contains_external_calls_field() -> None:
    """run_workflow 返回的 RunResult 包含 external_calls 字段。"""
    result = run_workflow(load_workflow("linear_llm.json"), {"question": "hello"})
    assert result.status == "succeeded"
    assert hasattr(result, "external_calls")
    assert isinstance(result.external_calls, list)


def test_run_metrics_populated_from_external_calls() -> None:
    """RunMetrics.call_count 和 total_latency_ms 从 external_calls 汇总。"""
    result = run_workflow(load_workflow("linear_llm.json"), {"question": "hello"})
    assert result.status == "succeeded"
    # builtin executor 不产生 external_calls，所以 call_count 应为 0
    assert result.metrics.call_count == 0
    assert result.metrics.total_latency_ms is None


def test_executor_error_carries_executor_ref() -> None:
    """ExecutorError.executor_ref 字段正确传递到 _error_sink 的 ExternalCallRecord。"""
    from prompt2langgraph.registry.executors import ExecutorError

    err = ExecutorError("E_SEC_013", "test error", executor_ref="llm.qwen-plus")
    assert err.executor_ref == "llm.qwen-plus"


def test_executor_error_executor_ref_default_none() -> None:
    """ExecutorError.executor_ref 默认为 None。"""
    from prompt2langgraph.registry.executors import ExecutorError

    err = ExecutorError("E_SEC_013", "test error")
    assert err.executor_ref is None
