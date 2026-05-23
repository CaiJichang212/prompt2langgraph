"""Tests for security policy validation: check_external_policy, check_model_whitelist, check_tool_refs."""

from prompt2langgraph.ir.models import (
    EdgeKind,
    EdgeSpec,
    ExecutorRef,
    ExecutorType,
    NodeSpec,
    PolicySpec,
    SecurityPolicy,
    StateSchema,
    TypeName,
    TypeSpec,
    WorkflowSpec,
)
from prompt2langgraph.registry.tool_executor import ToolCallableRegistry
from prompt2langgraph.validate.security import (
    check_external_policy,
    check_model_whitelist,
    check_tool_refs,
)


def _make_workflow(
    *,
    nodes: list[NodeSpec],
    policies: PolicySpec | None = None,
) -> WorkflowSpec:
    """Helper to build a minimal WorkflowSpec with given nodes and policies."""
    return WorkflowSpec(
        schema_version="0.1",
        workflow_id="test_wf",
        name="Test Workflow",
        entrypoint=nodes[0].id if nodes else "start",
        state_schema=StateSchema(
            input={"question": TypeSpec(type=TypeName.STRING)},
            output={"answer": TypeSpec(type=TypeName.STRING)},
            channels={
                "question": TypeSpec(type=TypeName.STRING),
                "answer": TypeSpec(type=TypeName.STRING),
            },
        ),
        nodes=nodes,
        edges=[],
        policies=policies or PolicySpec(),
    )


# ── check_external_policy ──────────────────────────────────────────────


def test_llm_node_external_call_false_reports_e_sec_013() -> None:
    """LLM 节点 + external_call=False → 报 E_SEC_013"""
    wf = _make_workflow(
        nodes=[
            NodeSpec(
                id="llm_node",
                kind="llm",
                executor=ExecutorRef(ref="llm.qwen-plus", type=ExecutorType.LLM),
            ),
        ],
        policies=PolicySpec(external_call=False),
    )
    diags = check_external_policy(wf)
    assert len(diags) == 1
    assert diags[0].code == "E_SEC_013"
    assert diags[0].location.node_id == "llm_node"


def test_llm_node_external_call_true_passes() -> None:
    """LLM 节点 + external_call=True → 通过"""
    wf = _make_workflow(
        nodes=[
            NodeSpec(
                id="llm_node",
                kind="llm",
                executor=ExecutorRef(ref="llm.qwen-plus", type=ExecutorType.LLM),
            ),
        ],
        policies=PolicySpec(external_call=True),
    )
    diags = check_external_policy(wf)
    assert diags == []


def test_builtin_llm_node_external_call_false_passes() -> None:
    """BUILTIN 类型 LLM 节点 + external_call=False → 通过"""
    wf = _make_workflow(
        nodes=[
            NodeSpec(
                id="builtin_llm",
                kind="llm",
                executor=ExecutorRef(ref="builtin.echo_llm", type=ExecutorType.BUILTIN),
            ),
        ],
        policies=PolicySpec(external_call=False),
    )
    diags = check_external_policy(wf)
    assert diags == []


# ── check_model_whitelist ──────────────────────────────────────────────


def test_llm_node_empty_allowed_models_reports_e_sec_014() -> None:
    """LLM 节点 + allowed_models=[] → 报 E_SEC_014"""
    wf = _make_workflow(
        nodes=[
            NodeSpec(
                id="llm_node",
                kind="llm",
                executor=ExecutorRef(ref="llm.qwen-plus", type=ExecutorType.LLM),
            ),
        ],
        policies=PolicySpec(allowed_models=[]),
    )
    diags = check_model_whitelist(wf)
    assert len(diags) == 1
    assert diags[0].code == "E_SEC_014"
    assert diags[0].location.node_id == "llm_node"


def test_llm_node_model_in_whitelist_passes() -> None:
    """LLM 节点 + allowed_models=["qwen-plus"] → 通过"""
    wf = _make_workflow(
        nodes=[
            NodeSpec(
                id="llm_node",
                kind="llm",
                executor=ExecutorRef(ref="llm.qwen-plus", type=ExecutorType.LLM),
            ),
        ],
        policies=PolicySpec(allowed_models=["qwen-plus"]),
    )
    diags = check_model_whitelist(wf)
    assert diags == []


# ── check_tool_refs ────────────────────────────────────────────────────


def test_tool_node_unregistered_ref_reports_e_sec_015() -> None:
    """Tool 节点 + 未注册 ref → 报 E_SEC_015"""
    registry = ToolCallableRegistry()
    wf = _make_workflow(
        nodes=[
            NodeSpec(
                id="tool_node",
                kind="tool",
                executor=ExecutorRef(ref="tool.unknown", type=ExecutorType.PYTHON_CALLABLE),
            ),
        ],
        policies=PolicySpec(allowed_tool_refs=["tool.unknown"]),
    )
    diags = check_tool_refs(wf, registry)
    # ref 在白名单但未注册 → 报 E_SEC_015（注册检查）
    assert any(d.code == "E_SEC_015" for d in diags)


def test_tool_node_registered_and_in_whitelist_passes() -> None:
    """Tool 节点 + 已注册 + 在白名单 → 通过"""
    registry = ToolCallableRegistry()
    registry.register("tool.search", lambda inputs, params: inputs)
    wf = _make_workflow(
        nodes=[
            NodeSpec(
                id="tool_node",
                kind="tool",
                executor=ExecutorRef(ref="tool.search", type=ExecutorType.PYTHON_CALLABLE),
            ),
        ],
        policies=PolicySpec(allowed_tool_refs=["tool.search"]),
    )
    diags = check_tool_refs(wf, registry)
    assert diags == []


def test_tool_node_registered_empty_whitelist_reports_e_sec_015() -> None:
    """Tool 节点 + 已注册 + 空白名单 → 报 E_SEC_015"""
    registry = ToolCallableRegistry()
    registry.register("tool.search", lambda inputs, params: inputs)
    wf = _make_workflow(
        nodes=[
            NodeSpec(
                id="tool_node",
                kind="tool",
                executor=ExecutorRef(ref="tool.search", type=ExecutorType.PYTHON_CALLABLE),
            ),
        ],
        policies=PolicySpec(allowed_tool_refs=[]),
    )
    diags = check_tool_refs(wf, registry)
    assert any(d.code == "E_SEC_015" for d in diags)


def test_langchain_tool_node_not_checked_by_check_tool_refs() -> None:
    """LANGCHAIN_TOOL 节点不受 check_tool_refs() 检查"""
    registry = ToolCallableRegistry()
    wf = _make_workflow(
        nodes=[
            NodeSpec(
                id="lc_tool",
                kind="tool",
                executor=ExecutorRef(ref="lc.some_tool", type=ExecutorType.LANGCHAIN_TOOL),
            ),
        ],
    )
    diags = check_tool_refs(wf, registry)
    assert diags == []


def test_node_level_allowed_tool_refs_overrides_global() -> None:
    """Tool 节点 + 节点级 allowed_tool_refs 优先于全局"""
    registry = ToolCallableRegistry()
    registry.register("tool.search", lambda inputs, params: inputs)
    # 全局白名单不含 tool.search，但节点级包含
    wf = _make_workflow(
        nodes=[
            NodeSpec(
                id="tool_node",
                kind="tool",
                executor=ExecutorRef(ref="tool.search", type=ExecutorType.PYTHON_CALLABLE),
                security=SecurityPolicy(allowed_tool_refs=["tool.search"]),
            ),
        ],
        policies=PolicySpec(allowed_tool_refs=[]),
    )
    diags = check_tool_refs(wf, registry)
    assert diags == []
