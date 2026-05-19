import json
from pathlib import Path

import pytest

from prompt2langgraph.compiler.langgraph_py import compile_workflow_to_graph
from prompt2langgraph.ir.models import ExecutorType, ReducerName, StateSelector, TypeName, TypeSpec, WorkflowSpec
from prompt2langgraph.registry.builtins import builtin_executor_registry
from prompt2langgraph.registry.executors import ExecutorDefinition, ExecutorRegistry


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
            "edges": [{"id": "first_to_second", "source": "first", "target": "second", "kind": "linear"}],
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
                handler=lambda inputs, params: {"messages": [{"role": "assistant", "content": "hi"}]},
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
                input_schema={"value": TypeSpec(type=TypeName.STRING), "prefix": TypeSpec(type=TypeName.STRING)},
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
