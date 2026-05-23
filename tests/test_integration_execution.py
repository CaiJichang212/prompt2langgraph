"""Integration tests: LLM executor + tool executor full-chain with fake providers."""

from __future__ import annotations

import pytest

from prompt2langgraph.ir.models import (
    EdgeKind,
    EdgeSpec,
    ExecutorRef,
    ExecutorType,
    NodeSpec,
    PolicySpec,
    StateSchema,
    TypeName,
    TypeSpec,
    WorkflowSpec,
)
from prompt2langgraph.registry.builtins import builtin_executor_registry
from prompt2langgraph.registry.executors import ExecutorDefinition
from prompt2langgraph.registry.tool_executor import ToolCallableRegistry
from prompt2langgraph.runtime.runner import run_workflow

from fake_provider import fake_chat_model
from fake_tools import FAKE_TOOLS, fake_tool_echo, fake_tool_fail, fake_tool_upper

STRING = TypeSpec(type=TypeName.STRING)


# ---------------------------------------------------------------------------
# Workflow builders
# ---------------------------------------------------------------------------


def _llm_workflow() -> WorkflowSpec:
    """Single LLM node workflow using llm.qwen-plus executor."""
    return WorkflowSpec(
        schema_version="0.1",
        workflow_id="test_llm_integration",
        name="Test LLM Integration",
        entrypoint="llm_node",
        state_schema=StateSchema(
            input={"question": STRING},
            output={"answer": STRING},
            channels={"question": STRING, "answer": STRING},
        ),
        nodes=[
            NodeSpec(
                id="llm_node",
                kind="llm",
                executor=ExecutorRef(ref="llm.qwen-plus", type=ExecutorType.LLM),
                inputs={"question": {"state_key": "question"}},
                outputs={"answer": {"state_key": "answer"}},
            ),
        ],
        edges=[],
        policies=PolicySpec(external_call=True, allowed_models=["qwen-plus"]),
    )


def _mixed_builtin_llm_workflow() -> WorkflowSpec:
    """BUILTIN echo_llm node followed by an LLM node."""
    return WorkflowSpec(
        schema_version="0.1",
        workflow_id="test_mixed_integration",
        name="Test Mixed BUILTIN+LLM",
        entrypoint="echo_node",
        state_schema=StateSchema(
            input={"question": STRING},
            output={"answer": STRING},
            channels={"question": STRING, "draft": STRING, "answer": STRING},
        ),
        nodes=[
            NodeSpec(
                id="echo_node",
                kind="llm",
                executor=ExecutorRef(ref="builtin.echo_llm", type=ExecutorType.BUILTIN),
                inputs={"question": {"state_key": "question"}},
                outputs={"answer": {"state_key": "draft"}},
                params={"template": "Draft: {question}"},
            ),
            NodeSpec(
                id="llm_node",
                kind="llm",
                executor=ExecutorRef(ref="llm.qwen-plus", type=ExecutorType.LLM),
                inputs={"question": {"state_key": "draft"}},
                outputs={"answer": {"state_key": "answer"}},
            ),
        ],
        edges=[
            EdgeSpec(id="e1", source="echo_node", target="llm_node", kind=EdgeKind.LINEAR),
        ],
        policies=PolicySpec(external_call=True, allowed_models=["qwen-plus"]),
    )


def _tool_workflow() -> WorkflowSpec:
    """Single Tool node workflow using fake.echo executor."""
    return WorkflowSpec(
        schema_version="0.1",
        workflow_id="test_tool_integration",
        name="Test Tool Integration",
        entrypoint="tool_node",
        state_schema=StateSchema(
            input={"input": STRING},
            output={"output": STRING},
            channels={"input": STRING, "output": STRING},
        ),
        nodes=[
            NodeSpec(
                id="tool_node",
                kind="tool",
                executor=ExecutorRef(ref="fake.echo", type=ExecutorType.PYTHON_CALLABLE),
                inputs={"input": {"state_key": "input"}},
                outputs={"output": {"state_key": "output"}},
            ),
        ],
        edges=[],
        policies=PolicySpec(allowed_tool_refs=["fake.echo"]),
    )


def _tool_upper_workflow() -> WorkflowSpec:
    """Tool node workflow using fake.upper executor."""
    return WorkflowSpec(
        schema_version="0.1",
        workflow_id="test_tool_upper_integration",
        name="Test Tool Upper Integration",
        entrypoint="tool_node",
        state_schema=StateSchema(
            input={"input": STRING},
            output={"output": STRING},
            channels={"input": STRING, "output": STRING},
        ),
        nodes=[
            NodeSpec(
                id="tool_node",
                kind="tool",
                executor=ExecutorRef(ref="fake.upper", type=ExecutorType.PYTHON_CALLABLE),
                inputs={"input": {"state_key": "input"}},
                outputs={"output": {"state_key": "output"}},
            ),
        ],
        edges=[],
        policies=PolicySpec(allowed_tool_refs=["fake.upper"]),
    )


def _tool_fail_workflow() -> WorkflowSpec:
    """Tool node workflow using fake.fail executor."""
    return WorkflowSpec(
        schema_version="0.1",
        workflow_id="test_tool_fail_integration",
        name="Test Tool Fail Integration",
        entrypoint="tool_node",
        state_schema=StateSchema(
            input={"input": STRING},
            output={"output": STRING},
            channels={"input": STRING, "output": STRING},
        ),
        nodes=[
            NodeSpec(
                id="tool_node",
                kind="tool",
                executor=ExecutorRef(ref="fake.fail", type=ExecutorType.PYTHON_CALLABLE),
                inputs={"input": {"state_key": "input"}},
                outputs={"output": {"state_key": "output"}},
            ),
        ],
        edges=[],
        policies=PolicySpec(allowed_tool_refs=["fake.fail"]),
    )


def _llm_metrics_workflow() -> WorkflowSpec:
    """LLM node workflow with collect_metrics=True."""
    return WorkflowSpec(
        schema_version="0.1",
        workflow_id="test_llm_metrics",
        name="Test LLM Metrics",
        entrypoint="llm_node",
        state_schema=StateSchema(
            input={"question": STRING},
            output={"answer": STRING},
            channels={"question": STRING, "answer": STRING},
        ),
        nodes=[
            NodeSpec(
                id="llm_node",
                kind="llm",
                executor=ExecutorRef(ref="llm.qwen-plus", type=ExecutorType.LLM),
                inputs={"question": {"state_key": "question"}},
                outputs={"answer": {"state_key": "answer"}},
            ),
        ],
        edges=[],
        policies=PolicySpec(
            external_call=True, allowed_models=["qwen-plus"], collect_metrics=True
        ),
    )


# ---------------------------------------------------------------------------
# Executor registries with dynamic tool executors
# ---------------------------------------------------------------------------


def _executor_registry_with_tools() -> "ExecutorDefinition":
    """Return a copy of the builtin registry plus dynamic tool executor definitions."""
    base = builtin_executor_registry()
    for ref, handler in FAKE_TOOLS.items():
        base.register(
            ExecutorDefinition(
                ref=ref,
                type=ExecutorType.PYTHON_CALLABLE,
                dynamic=True,
                input_schema={"input": STRING},
                output_schema={"output": STRING},
                handler=None,
            )
        )
    return base


def _tool_registry_with_fakes() -> ToolCallableRegistry:
    """Return a ToolCallableRegistry with all fake tools registered."""
    registry = ToolCallableRegistry()
    for ref, handler in FAKE_TOOLS.items():
        registry.register(ref, handler)
    return registry


# ---------------------------------------------------------------------------
# 1. LLM node + fake provider full-chain execution
# ---------------------------------------------------------------------------


class TestLLMIntegration:
    def test_llm_node_with_fake_provider(self) -> None:
        workflow = _llm_workflow()
        model = fake_chat_model("hello from fake llm")

        result = run_workflow(
            workflow,
            {"question": "hello"},
            model_client=model,
        )

        assert result.status == "succeeded"
        assert "answer" in result.output
        assert result.output["answer"] == "hello from fake llm"
        assert result.diagnostics == []

    def test_llm_node_events(self) -> None:
        workflow = _llm_workflow()
        model = fake_chat_model("response")

        result = run_workflow(
            workflow,
            {"question": "test"},
            model_client=model,
        )

        assert result.status == "succeeded"
        event_types = [e.type for e in result.events]
        assert event_types == ["run.started", "node.started", "node.finished", "run.finished"]
        assert result.events[1].node_id == "llm_node"


# ---------------------------------------------------------------------------
# 2. BUILTIN node + LLM node mixed execution
# ---------------------------------------------------------------------------


class TestMixedBuiltinLLM:
    def test_mixed_execution(self) -> None:
        workflow = _mixed_builtin_llm_workflow()
        model = fake_chat_model("final answer")

        result = run_workflow(
            workflow,
            {"question": "hello"},
            model_client=model,
        )

        assert result.status == "succeeded"
        assert result.output["answer"] == "final answer"
        assert result.diagnostics == []

    def test_mixed_execution_events(self) -> None:
        workflow = _mixed_builtin_llm_workflow()
        model = fake_chat_model("final answer")

        result = run_workflow(
            workflow,
            {"question": "hello"},
            model_client=model,
        )

        assert result.status == "succeeded"
        started_nodes = [e.node_id for e in result.events if e.type == "node.started"]
        assert started_nodes == ["echo_node", "llm_node"]


# ---------------------------------------------------------------------------
# 3. Tool node + fake tool registry full-chain execution
# ---------------------------------------------------------------------------


class TestToolIntegration:
    def test_tool_echo_node(self) -> None:
        workflow = _tool_workflow()
        executors = _executor_registry_with_tools()
        tools = _tool_registry_with_fakes()

        result = run_workflow(
            workflow,
            {"input": "hello tool"},
            executors=executors,
            tool_registry=tools,
        )

        assert result.status == "succeeded"
        assert result.output["output"] == "hello tool"
        assert result.diagnostics == []

    def test_tool_upper_node(self) -> None:
        workflow = _tool_upper_workflow()
        executors = _executor_registry_with_tools()
        tools = _tool_registry_with_fakes()

        result = run_workflow(
            workflow,
            {"input": "hello"},
            executors=executors,
            tool_registry=tools,
        )

        assert result.status == "succeeded"
        assert result.output["output"] == "HELLO"
        assert result.diagnostics == []

    def test_tool_node_events(self) -> None:
        workflow = _tool_workflow()
        executors = _executor_registry_with_tools()
        tools = _tool_registry_with_fakes()

        result = run_workflow(
            workflow,
            {"input": "test"},
            executors=executors,
            tool_registry=tools,
        )

        assert result.status == "succeeded"
        event_types = [e.type for e in result.events]
        assert event_types == ["run.started", "node.started", "node.finished", "run.finished"]
        assert result.events[1].node_id == "tool_node"


# ---------------------------------------------------------------------------
# 4. LLM node + collect_metrics=True records ExternalCallRecord
# ---------------------------------------------------------------------------


class TestLLMMetrics:
    def test_collect_metrics_records_external_call(self) -> None:
        workflow = _llm_metrics_workflow()
        model = fake_chat_model("metrics response")

        result = run_workflow(
            workflow,
            {"question": "hello"},
            model_client=model,
        )

        assert result.status == "succeeded"
        assert result.output["answer"] == "metrics response"
        assert len(result.external_calls) == 1
        call = result.external_calls[0]
        assert call.node_id == "llm_node"
        assert call.executor_ref == "llm.qwen-plus"
        assert call.status == "succeeded"

    def test_collect_metrics_populates_metrics_summary(self) -> None:
        workflow = _llm_metrics_workflow()
        model = fake_chat_model("metrics response")

        result = run_workflow(
            workflow,
            {"question": "hello"},
            model_client=model,
        )

        assert result.status == "succeeded"
        assert result.metrics.call_count == 1


# ---------------------------------------------------------------------------
# 5. Tool node failure records failed ExternalCallRecord
# ---------------------------------------------------------------------------


class TestToolFailure:
    def test_tool_fail_records_failed_external_call(self) -> None:
        workflow = _tool_fail_workflow()
        executors = _executor_registry_with_tools()
        tools = _tool_registry_with_fakes()

        result = run_workflow(
            workflow,
            {"input": "trigger failure"},
            executors=executors,
            tool_registry=tools,
        )

        assert result.status == "failed"
        assert len(result.external_calls) == 1
        call = result.external_calls[0]
        assert call.node_id == "tool_node"
        assert call.executor_ref == "fake.fail"
        assert call.status == "failed"
        assert call.error_code is not None

    def test_tool_fail_result_has_diagnostics(self) -> None:
        workflow = _tool_fail_workflow()
        executors = _executor_registry_with_tools()
        tools = _tool_registry_with_fakes()

        result = run_workflow(
            workflow,
            {"input": "trigger failure"},
            executors=executors,
            tool_registry=tools,
        )

        assert result.status == "failed"
        assert result.output == {}
        assert any(
            "fake tool failure" in diag.hint or "fake tool failure" in diag.message
            for diag in result.diagnostics
        )

    def test_tool_fail_metrics_call_count_is_one(self) -> None:
        """验证失败场景下 metrics.call_count 为 1，且 external_calls 只有一条记录。"""
        workflow = _tool_fail_workflow()
        executors = _executor_registry_with_tools()
        tools = _tool_registry_with_fakes()

        result = run_workflow(
            workflow,
            {"input": "trigger failure"},
            executors=executors,
            tool_registry=tools,
        )

        assert result.status == "failed"
        # Bug fix: should be exactly 1, not 2 (was double-recorded)
        assert len(result.external_calls) == 1
        assert result.metrics.call_count == 1
