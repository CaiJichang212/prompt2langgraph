from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from prompt2langgraph.ir.models import WorkflowSpec
from prompt2langgraph.registry.builtins import builtin_node_registry
from prompt2langgraph.registry.nodes import NodeRegistry


class ResolvedWorkflow(BaseModel):
    workflow: WorkflowSpec
    node_policies: dict[str, dict[str, Any]] = Field(default_factory=dict)
    external_call: bool = False
    allowed_models: list[str] = Field(default_factory=list)
    collect_metrics: bool = False
    allowed_tool_refs: list[str] = Field(default_factory=list)


def resolve_policies(
    workflow: WorkflowSpec,
    *,
    nodes: NodeRegistry | None = None,
    compile_options: dict[str, Any] | None = None,
) -> ResolvedWorkflow:
    registry = nodes or builtin_node_registry()
    options = compile_options or {}
    node_policies: dict[str, dict[str, Any]] = {}
    for node in workflow.nodes:
        definition = registry.get(node.kind) if registry.has(node.kind) else None
        timeout_candidates = (
            options.get("default_timeout_s"),
            node.timeout_s,
            workflow.policies.default_timeout_s,
            definition.default_timeout_s if definition is not None else None,
            60,
        )
        timeout_s = next(candidate for candidate in timeout_candidates if candidate is not None)
        requires_approval = (
            bool(node.security.requires_approval) if node.security is not None else False
        )
        if (
            definition is not None
            and definition.side_effect
            and not workflow.policies.allow_side_effects
        ):
            requires_approval = True
        node_policies[node.id] = {
            "timeout_s": timeout_s,
            "requires_approval": requires_approval,
        }
    return ResolvedWorkflow(
        workflow=workflow,
        node_policies=node_policies,
        external_call=workflow.policies.external_call,
        allowed_models=workflow.policies.allowed_models,
        collect_metrics=workflow.policies.collect_metrics,
        allowed_tool_refs=workflow.policies.allowed_tool_refs,
    )
