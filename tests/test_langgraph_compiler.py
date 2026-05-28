import json
from pathlib import Path

import pytest

from prompt2langgraph.compiler.langgraph_py import compile_workflow_to_graph
from prompt2langgraph.ir.models import (
    ExecutorType,
    PolicySpec,
    ReducerName,
    StateSelector,
    TypeName,
    TypeSpec,
    WorkflowSpec,
)
from prompt2langgraph.registry.builtins import builtin_executor_registry
from prompt2langgraph.registry.executors import ExecutorDefinition, ExecutorError, ExecutorRegistry
from prompt2langgraph.registry.tool_executor import ToolCallableRegistry

FIXTURES = Path(__file__).parent / "fixtures"


def load_workflow(name: str) -> WorkflowSpec:
    return WorkflowSpec.model_validate(json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def test_compiles_linear_llm_fixture_to_invokable_graph() -> None:
    workflow = load_workflow("linear_llm.json")

    graph = compile_workflow_to_graph(workflow, builtin_executor_registry())
    result = graph.invoke({"question": "hello"})

    assert result["question"] == "hello"
    assert result["answer"] == "Answer: hello"


def test_compiles_multi_node_retriever_llm_fixture_to_invokable_graph() -> None:
    workflow = load_workflow("linear_retriever_llm.json")

    graph = compile_workflow_to_graph(workflow, builtin_executor_registry())
    result = graph.invoke({"question": "hello"})

    assert result["docs_ref"] == "mock://retriever/hello"
    assert result["context"] == "mock://retriever/hello"
    assert result["answer"] == "Answer from mock://retriever/hello"


def test_add_messages_reducer_combines_message_updates_across_linear_nodes() -> None:
    message_type = TypeSpec(type=TypeName.MESSAGES)
    workflow = WorkflowSpec.model_validate(
        {
            "schema_version": "0.1",
            "workflow_id": "messages_add_messages",
            "name": "Messages Add Messages",
            "entrypoint": "first",
            "state_schema": {
                "input": {"messages": {"type": "messages"}},
                "output": {"messages": {"type": "messages"}},
                "channels": {"messages": {"type": "messages"}},
                "private": {},
                "reducers": {"messages": "add_messages"},
            },
            "nodes": [
                {
                    "id": "first",
                    "kind": "transform",
                    "executor": {"ref": "test.first_message", "type": "builtin"},
                    "inputs": {},
                    "outputs": {"messages": {"state_key": "messages"}},
                    "params": {},
                },
                {
                    "id": "second",
                    "kind": "transform",
                    "executor": {"ref": "test.second_message", "type": "builtin"},
                    "inputs": {},
                    "outputs": {"messages": {"state_key": "messages"}},
                    "params": {},
                },
            ],
            "edges": [
                {"id": "first_to_second", "source": "first", "target": "second", "kind": "linear"}
            ],
            "policies": {},
            "metadata": {},
        }
    )
    builtins = builtin_executor_registry()
    registry = ExecutorRegistry(
        [
            *[builtins.get(ref) for ref in builtins.refs()],
            ExecutorDefinition(
                ref="test.first_message",
                type=ExecutorType.BUILTIN,
                input_schema={},
                output_schema={"messages": message_type},
                handler=lambda inputs, params: {"messages": [{"role": "user", "content": "hello"}]},
            ),
            ExecutorDefinition(
                ref="test.second_message",
                type=ExecutorType.BUILTIN,
                input_schema={},
                output_schema={"messages": message_type},
                handler=lambda inputs, params: {
                    "messages": [{"role": "assistant", "content": "hi"}]
                },
            ),
        ]
    )

    graph = compile_workflow_to_graph(workflow, registry)
    result = graph.invoke({"messages": [{"role": "system", "content": "seed"}]})

    assert result["messages"] == [
        {"role": "system", "content": "seed"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]


def test_compiles_conditional_edge_to_route_by_expression() -> None:
    workflow = load_workflow("conditional_human_gate.json")

    graph = compile_workflow_to_graph(workflow, builtin_executor_registry())
    result = graph.invoke({"question": "hello", "confidence": 0.8})

    assert result["answer"] == "Answer: hello"
    assert "approval" not in result


@pytest.mark.parametrize(
    ("expr", "confidence"),
    [
        ("confidence < 0.75", 0.5),
        ("confidence <= 0.75", 0.75),
        ("confidence > 0.75", 0.8),
        ("confidence >= 0.75", 0.75),
        ("confidence == 0.75", 0.75),
        ("confidence != 0.75", 0.8),
    ],
)
def test_conditional_expression_supports_scalar_comparisons(expr: str, confidence: float) -> None:
    workflow = load_workflow("conditional_human_gate.json")
    condition = workflow.edges[0].condition
    assert condition is not None
    condition.expr = expr
    condition.routes = {"true": "compose", "false": "approval"}

    graph = compile_workflow_to_graph(workflow, builtin_executor_registry())
    result = graph.invoke({"question": "hello", "confidence": confidence})

    assert result["answer"] == "Answer: hello"


def test_compiles_guarded_loop_until_max_iterations_then_continues() -> None:
    workflow = load_workflow("loop_with_guard.json")

    events: list[tuple[str, str]] = []
    graph = compile_workflow_to_graph(
        workflow,
        builtin_executor_registry(),
        event_sink=lambda event_type, node_id: events.append((event_type, node_id)),
    )
    result = graph.invoke({"question": "hello"})

    assert result["answer"] == "Answer: hello"
    assert result["_loop_counts"] == {"retry": 2}
    assert [event for event in events if event == ("node.started", "compose")] == [
        ("node.started", "compose"),
        ("node.started", "compose"),
    ]
    assert ("node.started", "finalize") in events


def test_compiles_fanout_to_send_items_and_reduce_results() -> None:
    workflow = load_workflow("fanout_map_reduce.json")

    graph = compile_workflow_to_graph(workflow, builtin_executor_registry())
    result = graph.invoke({"items": ["alpha", "beta"]})

    assert result["items"] == ["alpha", "beta"]
    assert sorted(result["results"]) == ["alpha", "beta"]


def test_fanout_mapper_receives_original_state_context() -> None:
    workflow = load_workflow("fanout_map_reduce.json")
    workflow.state_schema.channels["prefix"] = TypeSpec(type=TypeName.STRING)
    workflow.nodes[1].inputs["prefix"] = StateSelector(state_key="prefix")

    builtins = builtin_executor_registry()
    registry = ExecutorRegistry(
        [
            *[builtins.get(ref) for ref in builtins.refs()],
            ExecutorDefinition(
                ref="test.prefix_item",
                type=ExecutorType.BUILTIN,
                input_schema={
                    "value": TypeSpec(type=TypeName.STRING),
                    "prefix": TypeSpec(type=TypeName.STRING),
                },
                output_schema={"value": TypeSpec(type=TypeName.STRING)},
                handler=lambda inputs, params: {"value": f"{inputs['prefix']}:{inputs['value']}"},
            ),
        ]
    )
    workflow.nodes[1].executor.ref = "test.prefix_item"

    graph = compile_workflow_to_graph(workflow, registry)
    result = graph.invoke({"items": ["alpha", "beta"], "prefix": "p"})

    assert sorted(result["results"]) == ["p:alpha", "p:beta"]


def test_non_fanout_append_reducer_preserves_scalar_output() -> None:
    workflow = load_workflow("linear_llm.json")
    workflow.state_schema.reducers["answer"] = ReducerName.APPEND

    graph = compile_workflow_to_graph(workflow, builtin_executor_registry())
    result = graph.invoke({"question": "hello", "answer": "seed:"})

    assert result["answer"] == "seed:Answer: hello"


# --- Dynamic Executor Dispatch tests ---


def _make_llm_workflow() -> WorkflowSpec:
    """Create a minimal workflow with a single dynamic LLM node."""
    return WorkflowSpec.model_validate(
        {
            "schema_version": "0.1",
            "workflow_id": "dynamic_llm_test",
            "name": "Dynamic LLM Test",
            "entrypoint": "ask",
            "state_schema": {
                "input": {"question": {"type": "string"}},
                "output": {"answer": {"type": "string"}},
                "channels": {"question": {"type": "string"}, "answer": {"type": "string"}},
                "private": {},
                "reducers": {},
            },
            "nodes": [
                {
                    "id": "ask",
                    "kind": "llm",
                    "executor": {"ref": "llm.test-model", "type": "llm"},
                    "inputs": {"question": {"state_key": "question"}},
                    "outputs": {"answer": {"state_key": "answer"}},
                    "params": {},
                },
            ],
            "edges": [],
            "policies": {},
            "metadata": {},
        }
    )


def _make_mixed_workflow() -> WorkflowSpec:
    """Create a workflow with a BUILTIN node followed by a dynamic LLM node."""
    return WorkflowSpec.model_validate(
        {
            "schema_version": "0.1",
            "workflow_id": "mixed_builtin_llm",
            "name": "Mixed Builtin LLM",
            "entrypoint": "transform",
            "state_schema": {
                "input": {"question": {"type": "string"}},
                "output": {"answer": {"type": "string"}},
                "channels": {
                    "question": {"type": "string"},
                    "context": {"type": "string"},
                    "answer": {"type": "string"},
                },
                "private": {},
                "reducers": {},
            },
            "nodes": [
                {
                    "id": "transform",
                    "kind": "transform",
                    "executor": {"ref": "builtin.identity_transform", "type": "builtin"},
                    "inputs": {"value": {"state_key": "question"}},
                    "outputs": {"value": {"state_key": "context"}},
                    "params": {},
                },
                {
                    "id": "ask",
                    "kind": "llm",
                    "executor": {"ref": "llm.test-model", "type": "llm"},
                    "inputs": {"question": {"state_key": "context"}},
                    "outputs": {"answer": {"state_key": "answer"}},
                    "params": {},
                },
            ],
            "edges": [
                {"id": "transform_to_ask", "source": "transform", "target": "ask", "kind": "linear"},
            ],
            "policies": {},
            "metadata": {},
        }
    )


def _make_tool_workflow() -> WorkflowSpec:
    """Create a minimal workflow with a single dynamic Tool node."""
    return WorkflowSpec.model_validate(
        {
            "schema_version": "0.1",
            "workflow_id": "dynamic_tool_test",
            "name": "Dynamic Tool Test",
            "entrypoint": "call_tool",
            "state_schema": {
                "input": {"question": {"type": "string"}},
                "output": {"result": {"type": "string"}},
                "channels": {"question": {"type": "string"}, "result": {"type": "string"}},
                "private": {},
                "reducers": {},
            },
            "nodes": [
                {
                    "id": "call_tool",
                    "kind": "tool",
                    "executor": {"ref": "tool.my_tool", "type": "python_callable"},
                    "inputs": {"question": {"state_key": "question"}},
                    "outputs": {"result": {"state_key": "result"}},
                    "params": {},
                },
            ],
            "edges": [],
            "policies": {},
            "metadata": {},
        }
    )


def test_dynamic_llm_executor_with_fake_model() -> None:
    """Compile and run a workflow with a dynamic LLM node using a fake model."""
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    fake_model = GenericFakeChatModel(messages=iter(["fake response"]))
    workflow = _make_llm_workflow()
    builtins = builtin_executor_registry()
    registry = ExecutorRegistry(
        [
            *[builtins.get(ref) for ref in builtins.refs()],
            ExecutorDefinition(
                ref="llm.test-model",
                type=ExecutorType.LLM,
                dynamic=True,
                input_schema={"question": TypeSpec(type=TypeName.STRING)},
                output_schema={"answer": TypeSpec(type=TypeName.STRING)},
                handler=None,
            ),
        ]
    )

    graph = compile_workflow_to_graph(workflow, registry, model_client=fake_model)
    result = graph.invoke({"question": "hello"})

    assert result["answer"] == "fake response"


def test_dynamic_llm_node_raises_executor_error_when_no_model_client() -> None:
    """LLM node without model_client should raise ExecutorError with E_SEC_013."""
    workflow = _make_llm_workflow()
    builtins = builtin_executor_registry()
    registry = ExecutorRegistry(
        [
            *[builtins.get(ref) for ref in builtins.refs()],
            ExecutorDefinition(
                ref="llm.test-model",
                type=ExecutorType.LLM,
                dynamic=True,
                input_schema={"question": TypeSpec(type=TypeName.STRING)},
                output_schema={"answer": TypeSpec(type=TypeName.STRING)},
                handler=None,
            ),
        ]
    )

    graph = compile_workflow_to_graph(workflow, registry)
    with pytest.raises(ExecutorError) as exc_info:
        graph.invoke({"question": "hello"})

    assert exc_info.value.code == "E_SEC_013"
    assert exc_info.value.node_id == "ask"


def test_mixed_builtin_and_llm_nodes_execute_correctly() -> None:
    """BUILTIN node and dynamic LLM node in the same workflow both execute."""
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    fake_model = GenericFakeChatModel(messages=iter(["llm answer"]))
    workflow = _make_mixed_workflow()
    builtins = builtin_executor_registry()
    registry = ExecutorRegistry(
        [
            *[builtins.get(ref) for ref in builtins.refs()],
            ExecutorDefinition(
                ref="llm.test-model",
                type=ExecutorType.LLM,
                dynamic=True,
                input_schema={"question": TypeSpec(type=TypeName.STRING)},
                output_schema={"answer": TypeSpec(type=TypeName.STRING)},
                handler=None,
            ),
        ]
    )

    graph = compile_workflow_to_graph(workflow, registry, model_client=fake_model)
    result = graph.invoke({"question": "hello"})

    # BUILTIN identity_transform passes "hello" through to context
    assert result["context"] == "hello"
    # Dynamic LLM node receives context as question input
    assert result["answer"] == "llm answer"


def test_dynamic_tool_executor_with_tool_registry() -> None:
    """Compile and run a workflow with a dynamic Tool node using ToolCallableRegistry."""
    workflow = _make_tool_workflow()
    builtins = builtin_executor_registry()
    registry = ExecutorRegistry(
        [
            *[builtins.get(ref) for ref in builtins.refs()],
            ExecutorDefinition(
                ref="tool.my_tool",
                type=ExecutorType.PYTHON_CALLABLE,
                dynamic=True,
                input_schema={"question": TypeSpec(type=TypeName.STRING)},
                output_schema={"result": TypeSpec(type=TypeName.STRING)},
                handler=None,
            ),
        ]
    )

    tool_reg = ToolCallableRegistry()
    tool_reg.register(
        "tool.my_tool",
        lambda inputs, params: {"result": f"tool:{inputs['question']}"},
    )

    graph = compile_workflow_to_graph(workflow, registry, tool_registry=tool_reg)
    result = graph.invoke({"question": "hello"})

    assert result["result"] == "tool:hello"


def test_dynamic_tool_node_raises_executor_error_when_no_tool_registry() -> None:
    """Tool node without tool_registry should raise ExecutorError with E_SEC_015."""
    workflow = _make_tool_workflow()
    builtins = builtin_executor_registry()
    registry = ExecutorRegistry(
        [
            *[builtins.get(ref) for ref in builtins.refs()],
            ExecutorDefinition(
                ref="tool.my_tool",
                type=ExecutorType.PYTHON_CALLABLE,
                dynamic=True,
                input_schema={"question": TypeSpec(type=TypeName.STRING)},
                output_schema={"result": TypeSpec(type=TypeName.STRING)},
                handler=None,
            ),
        ]
    )

    graph = compile_workflow_to_graph(workflow, registry)
    with pytest.raises(ExecutorError) as exc_info:
        graph.invoke({"question": "hello"})

    assert exc_info.value.code == "E_SEC_015"
    assert exc_info.value.node_id == "call_tool"


def test_collect_metrics_error_sink_and_metrics_sink_both_called_on_error() -> None:
    """When error_sink and metrics_sink both exist, only error_sink is called for failed ExecutorError.

    metrics_sink is skipped when error_sink is present to avoid double-counting:
    the runner's _error_sink wrapper already converts the error to an ExternalCallRecord.
    metrics_sink is only used as a standalone fallback when error_sink is None.
    """
    from prompt2langgraph.registry.executors import ExecutorError

    failed_calls: list = []
    error_calls: list = []

    def _metrics_sink(record: dict) -> None:
        failed_calls.append(record)

    def _error_sink(exc: ExecutorError) -> None:
        error_calls.append(exc)

    workflow = _make_tool_workflow()
    builtins = builtin_executor_registry()
    registry = ExecutorRegistry(
        [
            *[builtins.get(ref) for ref in builtins.refs()],
            ExecutorDefinition(
                ref="tool.my_tool",
                type=ExecutorType.PYTHON_CALLABLE,
                dynamic=True,
                input_schema={"question": TypeSpec(type=TypeName.STRING)},
                output_schema={"result": TypeSpec(type=TypeName.STRING)},
                handler=None,
            ),
        ]
    )

    tool_reg = ToolCallableRegistry()
    # Register a tool that fails
    tool_reg.register("tool.my_tool", lambda inputs, params: (_ for _ in ()).throw(RuntimeError("boom")))

    graph = compile_workflow_to_graph(
        workflow,
        registry,
        tool_registry=tool_reg,
        policies=PolicySpec(collect_metrics=True),
        error_sink=_error_sink,
        metrics_sink=_metrics_sink,
    )

    with pytest.raises(ExecutorError):
        graph.invoke({"question": "hello"})

    # error_sink received the error
    assert len(error_calls) == 1
    # metrics_sink should NOT be called when error_sink is present (avoid double-counting)
    assert len(failed_calls) == 0


def test_collect_metrics_success_record_emitted() -> None:
    """Successful external call should emit ExternalCallRecord via metrics_sink."""
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    records: list = []

    def _metrics_sink(record: dict) -> None:
        records.append(record)

    workflow = _make_llm_workflow()
    fake_model = GenericFakeChatModel(messages=iter(["ok"]))
    builtins = builtin_executor_registry()
    registry = ExecutorRegistry(
        [
            *[builtins.get(ref) for ref in builtins.refs()],
            ExecutorDefinition(
                ref="llm.test-model",
                type=ExecutorType.LLM,
                dynamic=True,
                input_schema={"question": TypeSpec(type=TypeName.STRING)},
                output_schema={"answer": TypeSpec(type=TypeName.STRING)},
                handler=None,
            ),
        ]
    )

    graph = compile_workflow_to_graph(
        workflow,
        registry,
        model_client=fake_model,
        policies=PolicySpec(collect_metrics=True),
        metrics_sink=_metrics_sink,
    )
    result = graph.invoke({"question": "hello"})

    assert result["answer"] == "ok"
    # Only successful record, no error_sink so metrics_sink gets the failed path too (if any)
    assert len(records) == 1
    assert records[0].status == "succeeded"
