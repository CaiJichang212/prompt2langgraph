"""LangGraph Python compiler for validated Workflow IR."""

from __future__ import annotations

import operator
import re
from collections.abc import Callable
from typing import Annotated, Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from typing_extensions import TypedDict

from prompt2langgraph.ir.models import ConditionSpec, EdgeKind, EdgeSpec, NodeSpec, ReducerName, TypeName, TypeSpec, WorkflowSpec
from prompt2langgraph.registry.executors import ExecutorRegistry


NodeEventSink = Callable[[str, str], None]


def compile_workflow_to_graph(
    workflow: WorkflowSpec,
    executors: ExecutorRegistry,
    *,
    event_sink: NodeEventSink | None = None,
):
    """Compile a validated WorkflowSpec into an invokable LangGraph graph."""

    builder = StateGraph(_state_schema_for(workflow))
    loop_edges_by_source = _loop_edges_by_source(workflow)
    loop_sources = set(loop_edges_by_source)
    fanout_result_keys = _fanout_result_keys(workflow)

    for node in workflow.nodes:
        builder.add_node(
            node.id,
            _node_wrapper(
                node,
                executors,
                event_sink,
                loop_edges_by_source.get(node.id, []),
                workflow.state_schema.reducers,
                fanout_result_keys,
            ),
        )

    builder.add_edge(START, workflow.entrypoint)

    outgoing_sources: set[str] = set()
    for edge in workflow.edges:
        if edge.kind is EdgeKind.LINEAR:
            if edge.source in loop_sources:
                continue
            builder.add_edge(edge.source, edge.target)
        elif edge.kind is EdgeKind.CONDITIONAL:
            if edge.condition is None:
                raise ValueError(f'conditional edge "{edge.id}" requires condition')
            builder.add_conditional_edges(
                edge.source,
                _condition_router(edge.condition),
                edge.condition.routes,
            )
        elif edge.kind is EdgeKind.LOOP:
            if edge.loop_guard is None:
                raise ValueError(f'loop edge "{edge.id}" requires loop_guard')
            continuation = _loop_continuation(workflow, edge)
            builder.add_conditional_edges(
                edge.source,
                _loop_router(edge),
                {"loop": edge.target, "done": continuation},
            )
        elif edge.kind is EdgeKind.FANOUT:
            if edge.map is None:
                raise ValueError(f'fanout edge "{edge.id}" requires map')
            builder.add_conditional_edges(edge.source, _fanout_router(edge))
        else:
            raise ValueError(f'edge "{edge.id}" kind "{edge.kind.value}" is not supported by v0.1c compiler')
        outgoing_sources.add(edge.source)

    for node in workflow.nodes:
        if node.id not in outgoing_sources:
            builder.add_edge(node.id, END)

    return builder.compile()


def _state_schema_for(workflow: WorkflowSpec) -> type[TypedDict]:
    fields: dict[str, Any] = {}
    state_types = {**workflow.state_schema.channels, **workflow.state_schema.private}
    for edge in workflow.edges:
        if edge.kind is EdgeKind.LOOP and edge.loop_guard is not None:
            state_types.setdefault(edge.loop_guard.counter_key, TypeSpec(type=TypeName.OBJECT))

    for state_key, type_spec in state_types.items():
        annotation = _python_type_for(type_spec)
        reducer = workflow.state_schema.reducers.get(state_key)
        if reducer is not None:
            annotation = Annotated[annotation, _reducer_for(reducer)]
        fields[state_key] = annotation

    return TypedDict(f"{workflow.workflow_id.title().replace('_', '')}State", fields, total=False)


def _python_type_for(type_spec: TypeSpec) -> Any:
    if type_spec.type is TypeName.STRING:
        return str
    if type_spec.type is TypeName.NUMBER:
        return float
    if type_spec.type is TypeName.INTEGER:
        return int
    if type_spec.type is TypeName.BOOLEAN:
        return bool
    if type_spec.type is TypeName.ARRAY:
        item_type = _python_type_for(type_spec.item_type) if type_spec.item_type is not None else Any
        return list[item_type]
    if type_spec.type is TypeName.OBJECT:
        return dict[str, Any]
    if type_spec.type is TypeName.MESSAGES:
        return list[Any]
    return Any


def _reducer_for(name: ReducerName) -> Callable[[Any, Any], Any]:
    if name is ReducerName.APPEND:
        return operator.add
    if name is ReducerName.SUM:
        return operator.add
    if name is ReducerName.MERGE_DICT:
        return _merge_dict
    if name is ReducerName.ADD_MESSAGES:
        return operator.add
    raise ValueError(f'unsupported reducer "{name.value}"')


def _merge_dict(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {**left, **right}


def _node_wrapper(
    node: NodeSpec,
    executors: ExecutorRegistry,
    event_sink: NodeEventSink | None,
    loop_edges: list[EdgeSpec],
    reducers: dict[str, ReducerName],
    fanout_result_keys: set[str],
):
    executor = executors.get(node.executor.ref)

    def invoke_node(state: dict[str, Any]) -> dict[str, Any]:
        if event_sink is not None:
            event_sink("node.started", node.id)
        inputs = {
            input_name: _state_value(state, selector.state_key, node.id)
            for input_name, selector in node.inputs.items()
        }
        raw_outputs = executor.invoke(inputs, node.params)
        update = {}
        for output_name, selector in node.outputs.items():
            if output_name not in raw_outputs:
                raise RuntimeError(f'node "{node.id}" executor omitted declared output "{output_name}"')
            output_value = raw_outputs[output_name]
            if (
                selector.state_key in fanout_result_keys
                and reducers.get(selector.state_key) is ReducerName.APPEND
                and not isinstance(output_value, list)
            ):
                output_value = [output_value]
            update[selector.state_key] = output_value
        for edge in loop_edges:
            if edge.loop_guard is None:
                continue
            counter_key = edge.loop_guard.counter_key
            counts = dict(state.get(counter_key, {}))
            counts[edge.id] = int(counts.get(edge.id, 0)) + 1
            update[counter_key] = counts
        if event_sink is not None:
            event_sink("node.finished", node.id)
        return update

    return invoke_node


def _state_value(state: dict[str, Any], state_key: str, node_id: str) -> Any:
    if state_key not in state:
        raise RuntimeError(f'node "{node_id}" input state key "{state_key}" is missing')
    return state[state_key]


_CONDITION_PATTERN = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(<=|>=|==|!=|<|>)\s*(.+?)\s*$")


def _condition_router(condition: ConditionSpec) -> Callable[[dict[str, Any]], str]:
    state_key, comparison, expected = _parse_condition_expr(condition.expr)

    def route(state: dict[str, Any]) -> str:
        if state_key not in state:
            raise RuntimeError(f'conditional expression state key "{state_key}" is missing')
        actual = state[state_key]
        return "true" if _compare(actual, comparison, expected) else "false"

    return route


def _parse_condition_expr(expr: str) -> tuple[str, str, Any]:
    match = _CONDITION_PATTERN.match(expr)
    if match is None:
        raise ValueError(f'unsupported conditional expression "{expr}"')
    state_key, comparison, raw_expected = match.groups()
    return state_key, comparison, _parse_literal(raw_expected)


def _parse_literal(raw_value: str) -> Any:
    value = raw_value.strip()
    if value in {"true", "false"}:
        return value == "true"
    if value in {"null", "none"}:
        return None
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _compare(actual: Any, comparison: str, expected: Any) -> bool:
    if comparison == "<":
        return actual < expected
    if comparison == "<=":
        return actual <= expected
    if comparison == ">":
        return actual > expected
    if comparison == ">=":
        return actual >= expected
    if comparison == "==":
        return actual == expected
    if comparison == "!=":
        return actual != expected
    raise ValueError(f'unsupported comparison operator "{comparison}"')


def _loop_edges_by_source(workflow: WorkflowSpec) -> dict[str, list[EdgeSpec]]:
    loop_edges: dict[str, list[EdgeSpec]] = {}
    for edge in workflow.edges:
        if edge.kind is EdgeKind.LOOP:
            loop_edges.setdefault(edge.source, []).append(edge)
    return loop_edges


def _fanout_result_keys(workflow: WorkflowSpec) -> set[str]:
    return {edge.map.result_state_key for edge in workflow.edges if edge.kind is EdgeKind.FANOUT and edge.map is not None}


def _loop_router(edge: EdgeSpec) -> Callable[[dict[str, Any]], str]:
    if edge.loop_guard is None:
        raise ValueError(f'loop edge "{edge.id}" requires loop_guard')
    guard = edge.loop_guard

    def route(state: dict[str, Any]) -> str:
        counts = state.get(guard.counter_key, {})
        current_count = int(counts.get(edge.id, 0))
        return "loop" if current_count < guard.max_iterations else "done"

    return route


def _loop_continuation(workflow: WorkflowSpec, loop_edge: EdgeSpec) -> str:
    for edge in workflow.edges:
        if edge.kind is EdgeKind.LINEAR and edge.source == loop_edge.source:
            return edge.target
    return END


def _fanout_router(edge: EdgeSpec) -> Callable[[dict[str, Any]], list[Send]]:
    if edge.map is None:
        raise ValueError(f'fanout edge "{edge.id}" requires map')
    map_spec = edge.map

    def route(state: dict[str, Any]) -> list[Send]:
        items = state.get(map_spec.items_state_key, [])
        return [Send(edge.target, {**state, map_spec.item_state_key: item}) for item in items]

    return route
