"""Security policy checks."""

from __future__ import annotations

from prompt2langgraph.diagnostics.codes import (
    E_SEC_013,
    E_SEC_014,
    E_SEC_015,
    E_SIDE_008,
    W_SIDE_001,
)
from prompt2langgraph.diagnostics.report import Diagnostic, DiagnosticLocation
from prompt2langgraph.ir.models import ExecutorType, ReducerName, WorkflowSpec
from prompt2langgraph.registry.nodes import NodeRegistry
from prompt2langgraph.registry.tool_executor import ToolCallableRegistry


def check_security(workflow: WorkflowSpec, nodes: NodeRegistry) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    for node in workflow.nodes:
        is_side_effect = node.kind == "side_effect" or (
            nodes.has(node.kind) and nodes.get(node.kind).side_effect
        )
        if not is_side_effect or workflow.policies.allow_side_effects:
            continue

        has_node_policy = node.security is not None and (
            node.security.requires_approval or node.security.idempotency_key is not None
        )
        if not has_node_policy:
            diagnostics.append(
                Diagnostic(
                    code=E_SIDE_008,
                    severity="error",
                    message="side_effect node requires approval or idempotency key",
                    location=DiagnosticLocation(node_id=node.id),
                )
            )

    return diagnostics


def check_external_policy(workflow: WorkflowSpec) -> list[Diagnostic]:
    """检查：存在 ExecutorType.LLM 节点但 external_call=False 时报 E_SEC_013。
    ExecutorType.BUILTIN 的 llm 节点不受此约束。"""
    diagnostics: list[Diagnostic] = []
    if workflow.policies.external_call:
        return diagnostics
    for node in workflow.nodes:
        if node.executor.type is ExecutorType.LLM:
            diagnostics.append(
                Diagnostic(
                    code=E_SEC_013,
                    severity="error",
                    message=f'node "{node.id}" uses LLM executor but external_call is not enabled',
                    location=DiagnosticLocation(node_id=node.id),
                )
            )
    return diagnostics


def check_model_whitelist(workflow: WorkflowSpec) -> list[Diagnostic]:
    """检查：ExecutorType.LLM 节点的 ref 格式为 llm.<model_id>，
    model_id 不在 allowed_models 时报 E_SEC_014。
    ref 不以 llm. 开头的跳过。"""
    diagnostics: list[Diagnostic] = []
    allowed = workflow.policies.allowed_models
    for node in workflow.nodes:
        if node.executor.type is not ExecutorType.LLM:
            continue
        ref = node.executor.ref
        if not ref.startswith("llm."):
            continue
        model_id = ref[4:]
        if model_id not in allowed:
            diagnostics.append(
                Diagnostic(
                    code=E_SEC_014,
                    severity="error",
                    message=f'model "{model_id}" is not in allowed_models whitelist',
                    location=DiagnosticLocation(node_id=node.id),
                )
            )
    return diagnostics


def check_tool_refs(
    workflow: WorkflowSpec, tool_registry: ToolCallableRegistry
) -> list[Diagnostic]:
    """检查对象：仅 ExecutorType.PYTHON_CALLABLE 节点（LANGCHAIN_TOOL 跳过）。
    检查 1：ref 不在 allowed_tool_refs（全局或节点级）时报 E_SEC_015。
      节点级 node.security.allowed_tool_refs 优先，None 时继承全局 policies.allowed_tool_refs。
      空列表 [] 按默认安全原则报 E_SEC_015。
    检查 2：ref 未在 ToolCallableRegistry 注册时报 E_SEC_015。"""
    diagnostics: list[Diagnostic] = []
    for node in workflow.nodes:
        if node.executor.type is not ExecutorType.PYTHON_CALLABLE:
            continue
        ref = node.executor.ref
        # 确定有效的 allowed_tool_refs
        if node.security is not None and node.security.allowed_tool_refs is not None:
            effective_allowed = node.security.allowed_tool_refs
        else:
            effective_allowed = workflow.policies.allowed_tool_refs
        # 检查 1：白名单检查（None 或空列表按默认安全原则报错）
        if not effective_allowed or ref not in effective_allowed:
            diagnostics.append(
                Diagnostic(
                    code=E_SEC_015,
                    severity="error",
                    message=f'tool ref "{ref}" is not authorized for node "{node.id}"',
                    location=DiagnosticLocation(node_id=node.id),
                )
            )
        # 检查 2：注册检查
        if not tool_registry.has(ref):
            diagnostics.append(
                Diagnostic(
                    code=E_SEC_015,
                    severity="error",
                    message=f'tool ref "{ref}" is not registered in ToolCallableRegistry',
                    location=DiagnosticLocation(node_id=node.id),
                )
            )
    return diagnostics


def check_side_effect_reducer(workflow: WorkflowSpec) -> list[Diagnostic]:
    """检查：若 workflow 包含 side_effect 节点，检查 __pt2lg_side_effect_rejected__ reducer。

    __pt2lg_side_effect_rejected__ 是 compiler 实际写入的拒绝信号 key。
    未声明 APPEND reducer 时输出 warning diagnostic（不阻断），
    因为多个 side_effect 节点的拒绝信息会被覆盖。
    """
    diagnostics: list[Diagnostic] = []
    has_side_effect = any(node.kind == "side_effect" for node in workflow.nodes)
    if not has_side_effect:
        return diagnostics

    key = "__pt2lg_side_effect_rejected__"
    reducer = workflow.state_schema.reducers.get(key)
    if reducer is not ReducerName.APPEND:
        current = reducer.value if reducer is not None else "not declared"
        diagnostics.append(
            Diagnostic(
                code=W_SIDE_001,
                severity="warning",
                message=(
                    f"workflow contains side_effect nodes but '{key}'"
                    f" reducer is not APPEND (current: {current})"
                ),
                hint=(
                    f"side effect rejections from multiple nodes may be overwritten;"
                    f" add '{key}' with 'append' reducer to state_schema.reducers"
                ),
            )
        )
    return diagnostics
