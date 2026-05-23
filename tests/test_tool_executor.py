"""Tests for ToolExecutor and ToolCallableRegistry."""

from __future__ import annotations

import time

import pytest

from prompt2langgraph.diagnostics.codes import E_SEC_015
from prompt2langgraph.registry.executors import ExecutorError
from prompt2langgraph.registry.tool_executor import ToolCallableRegistry, ToolExecutor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _echo_tool(inputs: dict, params: dict) -> dict:
    return {"echo": inputs.get("msg", ""), "params": params}


def _failing_tool(inputs: dict, params: dict) -> dict:
    raise ValueError("tool internal error")


def _slow_tool(inputs: dict, params: dict) -> dict:
    time.sleep(10)
    return {"done": True}


@pytest.fixture()
def registry() -> ToolCallableRegistry:
    reg = ToolCallableRegistry()
    reg.register("echo", _echo_tool)
    reg.register("fail", _failing_tool)
    reg.register("slow", _slow_tool)
    return reg


# ---------------------------------------------------------------------------
# ToolExecutor: registered tool returns correct result
# ---------------------------------------------------------------------------

class TestToolExecutorRegistered:
    def test_returns_correct_result(self, registry: ToolCallableRegistry) -> None:
        executor = ToolExecutor(registry, "echo")
        result = executor({"msg": "hello"}, {"key": "val"})
        assert result == {"echo": "hello", "params": {"key": "val"}}


# ---------------------------------------------------------------------------
# ToolExecutor: unregistered ref raises ExecutorError E_SEC_015
# ---------------------------------------------------------------------------

class TestToolExecutorUnregistered:
    def test_raises_executor_error(self, registry: ToolCallableRegistry) -> None:
        executor = ToolExecutor(registry, "nonexistent")
        with pytest.raises(ExecutorError) as exc_info:
            executor({}, {})
        assert exc_info.value.code == E_SEC_015
        assert "nonexistent" in exc_info.value.message


# ---------------------------------------------------------------------------
# ToolExecutor: callable exception propagates as ExecutorError E_SEC_015
# ---------------------------------------------------------------------------

class TestToolExecutorCallableError:
    def test_propagates_as_executor_error(self, registry: ToolCallableRegistry) -> None:
        executor = ToolExecutor(registry, "fail")
        with pytest.raises(ExecutorError) as exc_info:
            executor({}, {})
        assert exc_info.value.code == E_SEC_015
        assert "tool internal error" in exc_info.value.message


# ---------------------------------------------------------------------------
# ToolCallableRegistry: has / get / refs
# ---------------------------------------------------------------------------

class TestToolCallableRegistry:
    def test_has_registered(self, registry: ToolCallableRegistry) -> None:
        assert registry.has("echo") is True
        assert registry.has("fail") is True
        assert registry.has("nonexistent") is False

    def test_get_registered(self, registry: ToolCallableRegistry) -> None:
        handler = registry.get("echo")
        assert handler is _echo_tool

    def test_get_unregistered_raises_key_error(self, registry: ToolCallableRegistry) -> None:
        with pytest.raises(KeyError, match="nonexistent"):
            registry.get("nonexistent")

    def test_refs_returns_sorted(self, registry: ToolCallableRegistry) -> None:
        assert registry.refs() == ["echo", "fail", "slow"]

    def test_empty_registry(self) -> None:
        reg = ToolCallableRegistry()
        assert reg.refs() == []
        assert reg.has("anything") is False


# ---------------------------------------------------------------------------
# ToolExecutor: timeout raises ExecutorError E_SEC_015
# ---------------------------------------------------------------------------

class TestToolExecutorTimeout:
    def test_timeout_raises_executor_error(self, registry: ToolCallableRegistry) -> None:
        executor = ToolExecutor(registry, "slow", timeout_s=1)
        with pytest.raises(ExecutorError) as exc_info:
            executor({}, {})
        assert exc_info.value.code == E_SEC_015
        assert "timed out" in exc_info.value.message


# ---------------------------------------------------------------------------
# ExecutorError.to_diagnostic()
# ---------------------------------------------------------------------------

class TestExecutorErrorDiagnostic:
    def test_to_diagnostic_without_node_id(self) -> None:
        err = ExecutorError(E_SEC_015, "tool ref not registered", hint="check registry")
        diag = err.to_diagnostic()
        assert diag.code == E_SEC_015
        assert diag.severity == "error"
        assert diag.message == "tool ref not registered"
        assert diag.hint == "check registry"
        assert diag.location is None

    def test_to_diagnostic_with_node_id(self) -> None:
        err = ExecutorError(E_SEC_015, "tool ref not registered", node_id="node_1")
        diag = err.to_diagnostic()
        assert diag.location is not None
        assert diag.location.node_id == "node_1"
