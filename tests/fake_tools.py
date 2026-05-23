"""Pre-registered fake tool callables for testing."""
from typing import Any

from prompt2langgraph.registry.executors import ExecutorHandler


def fake_tool_echo(inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return {"output": inputs.get("input", "")}


def fake_tool_upper(inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return {"output": str(inputs.get("input", "")).upper()}


def fake_tool_fail(inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    raise RuntimeError("fake tool failure")


FAKE_TOOLS: dict[str, ExecutorHandler] = {
    "fake.echo": fake_tool_echo,
    "fake.upper": fake_tool_upper,
    "fake.fail": fake_tool_fail,
}
