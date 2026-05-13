from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from prompt2langgraph.ir.models import WorkflowSpec
from prompt2langgraph.registry.builtins import builtin_executor_registry
from prompt2langgraph.registry.executors import ExecutorRegistry


class BoundWorkflow(BaseModel):
    workflow: WorkflowSpec
    executor_bindings: dict[str, dict[str, Any]] = Field(default_factory=dict)


def bind_workflow(
    workflow: WorkflowSpec,
    *,
    executors: ExecutorRegistry | None = None,
) -> BoundWorkflow:
    registry = executors or builtin_executor_registry()
    bindings: dict[str, dict[str, Any]] = {}
    for node in workflow.nodes:
        executor = registry.get(node.executor.ref)
        bindings[node.id] = {
            "executor": executor.ref,
            "type": executor.type.value,
            "capabilities": list(executor.required_capabilities),
        }
    return BoundWorkflow(workflow=workflow, executor_bindings=bindings)
