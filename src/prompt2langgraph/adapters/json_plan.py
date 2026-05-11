"""Adapter for simplified JSON plan input."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from prompt2langgraph.ir.models import (
    ConditionSpec,
    EdgeKind,
    EdgeSpec,
    ExecutorRef,
    ExecutorType,
    MapSpec,
    LoopGuard,
    NodeSpec,
    RetryPolicy,
    SecurityPolicy,
    StateSelector,
    TypeName,
    TypeSpec,
    WorkflowSpec,
)
from prompt2langgraph.registry.builtins import builtin_executor_registry
from prompt2langgraph.registry.executors import ExecutorRegistry


def json_plan_to_workflow_spec(
    plan: Mapping[str, Any],
    *,
    executors: ExecutorRegistry | None = None,
) -> WorkflowSpec:
    """Normalize a simplified JSON plan into canonical WorkflowSpec."""

    executor_registry = executors or builtin_executor_registry()
    plan_name = _require_str(plan, "name")
    node_specs = [_node_spec(node, executor_registry) for node in _require_list(plan, "nodes")]
    if not node_specs:
        raise ValueError("nodes must contain at least one node")
    workflow_id = _slugify_identifier(plan_name)
    edge_specs = [
        _edge_spec(edge, index=index)
        for index, edge in enumerate(_require_list(plan, "edges"), start=1)
    ]
    entrypoint = _require_str(plan, "entrypoint") if "entrypoint" in plan else _infer_entrypoint(node_specs, edge_specs)
    input_specs = _type_mapping(plan.get("inputs", {}))
    output_specs = _type_mapping(plan.get("outputs", {}))
    channels = _collect_channels(input_specs, output_specs, node_specs, executor_registry)

    workflow = WorkflowSpec.model_validate(
        {
            "schema_version": "0.1",
            "workflow_id": workflow_id,
            "name": plan_name,
            "entrypoint": entrypoint,
            "state_schema": {
                "input": input_specs,
                "output": output_specs,
                "channels": channels,
                "private": {},
                "reducers": {},
            },
            "nodes": [node.model_dump(mode="json") for node in node_specs],
            "edges": [edge.model_dump(mode="json") for edge in edge_specs],
            "policies": {},
            "metadata": {},
        }
    )
    return workflow


def _node_spec(node: Mapping[str, Any], executors: ExecutorRegistry) -> NodeSpec:
    executor_ref = _require_str(node, "executor")
    executor = executors.get(executor_ref) if executors.has(executor_ref) else None
    input_schema = executor.input_schema if executor is not None else {}
    output_schema = executor.output_schema if executor is not None else {}

    explicit_inputs = node.get("inputs", {})
    explicit_outputs = node.get("outputs", {})
    inputs = _selector_mapping(explicit_inputs, input_schema)
    outputs = _selector_mapping(explicit_outputs, output_schema)

    return NodeSpec(
        id=_require_str(node, "id"),
        kind=_require_str(node, "kind"),
        executor=ExecutorRef(
            ref=executor_ref,
            type=executor.type if executor is not None else ExecutorType.BUILTIN,
        ),
        inputs=inputs,
        outputs=outputs,
        params=dict(node.get("params", {})),
        retry=RetryPolicy.model_validate(node["retry"]) if "retry" in node else None,
        timeout_s=node.get("timeout_s"),
        security=SecurityPolicy.model_validate(node["security"]) if "security" in node else None,
    )


def _edge_spec(edge: Mapping[str, Any], *, index: int) -> EdgeSpec:
    source = _require_str(edge, "from")
    target = _require_str(edge, "to")
    kind = EdgeKind(edge.get("kind", EdgeKind.LINEAR.value))
    return EdgeSpec(
        id=str(edge.get("id") or _stable_edge_id(source, target, index)),
        source=source,
        target=target,
        kind=kind,
        condition=ConditionSpec.model_validate(edge["condition"]) if "condition" in edge else None,
        map=MapSpec.model_validate(edge["map"]) if "map" in edge else None,
        loop_guard=LoopGuard.model_validate(edge["loop_guard"]) if "loop_guard" in edge else None,
    )


def _collect_channels(
    inputs: dict[str, TypeSpec],
    outputs: dict[str, TypeSpec],
    nodes: list[NodeSpec],
    executors: ExecutorRegistry,
) -> dict[str, TypeSpec]:
    channels = dict(inputs)
    channels.update(outputs)
    for node in nodes:
        executor = executors.get(node.executor.ref) if executors.has(node.executor.ref) else None
        for selector in node.inputs.values():
            input_type = None
            if executor is not None:
                input_type = _schema_type_for_selector(node.inputs, executor.input_schema, selector.state_key)
            channels.setdefault(selector.state_key, input_type or _any_type())
        for selector in node.outputs.values():
            output_type = None
            if executor is not None:
                output_type = _schema_type_for_selector(node.outputs, executor.output_schema, selector.state_key)
            channels.setdefault(selector.state_key, output_type or _any_type())
    return channels


def _selector_mapping(
    explicit_mapping: Any,
    schema: dict[str, TypeSpec],
) -> dict[str, StateSelector]:
    if explicit_mapping:
        return {
            name: StateSelector.model_validate(value if isinstance(value, Mapping) else {"state_key": value})
            for name, value in explicit_mapping.items()
        }
    return {name: StateSelector(state_key=name) for name in schema}


def _type_mapping(raw: Any) -> dict[str, TypeSpec]:
    if not isinstance(raw, Mapping):
        raise TypeError("plan inputs and outputs must be mappings")
    return {name: _type_spec(value) for name, value in raw.items()}


def _type_spec(value: Any) -> TypeSpec:
    if isinstance(value, TypeSpec):
        return value
    if isinstance(value, str):
        return TypeSpec(type=TypeName(value))
    if isinstance(value, Mapping):
        data = dict(value)
        if "type" in data and isinstance(data["type"], str):
            data["type"] = TypeName(data["type"])
        if "item_type" in data and data["item_type"] is not None:
            data["item_type"] = _type_spec(data["item_type"])
        if "properties" in data:
            data["properties"] = {key: _type_spec(spec) for key, spec in data["properties"].items()}
        return TypeSpec.model_validate(data)
    raise TypeError(f"unsupported type spec value: {value!r}")


def _require_str(data: Mapping[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str) or not value:
        raise ValueError(f'{key} must be a non-empty string')
    return value


def _require_list(data: Mapping[str, Any], key: str) -> list[Any]:
    value = data[key]
    if not isinstance(value, list):
        raise ValueError(f'{key} must be a list')
    return value


def _slugify_identifier(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value.strip().lower()).strip("_")
    if not slug:
        raise ValueError("name must produce a non-empty workflow_id")
    if slug[0].isdigit():
        slug = f"workflow_{slug}"
    return slug


def _stable_edge_id(source: str, target: str, index: int) -> str:
    return f"{source}_to_{target}" if index == 1 else f"{source}_to_{target}_{index}"


def _infer_entrypoint(nodes: list[NodeSpec], edges: list[EdgeSpec]) -> str:
    node_ids = {node.id for node in nodes}
    targets = {edge.target for edge in edges if edge.target in node_ids}
    roots = sorted(node_ids - targets)
    if len(roots) != 1:
        raise ValueError("could not infer a unique entrypoint")
    return roots[0]


def _schema_type_for_selector(
    selectors: dict[str, StateSelector],
    schema: dict[str, TypeSpec],
    state_key: str,
) -> TypeSpec | None:
    for name, selector in selectors.items():
        if selector.state_key == state_key and name in schema:
            return schema[name]
    return None


def _any_type() -> TypeSpec:
    return TypeSpec.model_validate({"type": "any"})
