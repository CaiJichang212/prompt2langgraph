"""Adapter for simplified JSON plan input."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from prompt2langgraph.adapters.base import AdapterParseError, SourceAdapter
from prompt2langgraph.ir.models import (
    ConditionSpec,
    EdgeKind,
    EdgeSpec,
    ExecutorRef,
    ExecutorType,
    LoopGuard,
    MapSpec,
    NodeSpec,
    PolicySpec,
    ReducerName,
    RetryPolicy,
    SecurityPolicy,
    StateSelector,
    TypeName,
    TypeSpec,
    WorkflowSpec,
)
from prompt2langgraph.registry.builtins import builtin_executor_registry
from prompt2langgraph.registry.executors import ExecutorRegistry


class JSONPlanAdapter(SourceAdapter):
    """Parse simplified JSON plan mappings."""

    def __init__(self, *, executors: ExecutorRegistry | None = None) -> None:
        self.executors = executors

    def parse(self, data: Mapping[str, Any], *, source: str | None = None) -> WorkflowSpec:
        try:
            return json_plan_to_workflow_spec(data, executors=self.executors, source=source)
        except AdapterParseError as exc:
            if exc.source is None and source is not None:
                raise AdapterParseError(
                    str(exc),
                    source=source,
                    path=exc.path,
                    line=exc.line,
                    column=exc.column,
                ) from exc
            raise


def json_plan_to_workflow_spec(
    plan: Mapping[str, Any],
    *,
    executors: ExecutorRegistry | None = None,
    source: str | None = None,
) -> WorkflowSpec:
    """Normalize a simplified JSON plan into canonical WorkflowSpec."""

    executor_registry = executors or builtin_executor_registry()
    plan_name = _require_str(plan, "name", source=source, path="name")
    node_specs = [
        _node_spec(node, executor_registry, source=source, index=index)
        for index, node in enumerate(_require_list(plan, "nodes", source=source, path="nodes"))
    ]
    if not node_specs:
        raise AdapterParseError("nodes must contain at least one node", source=source, path="nodes")
    workflow_id = _workflow_id(plan, plan_name, source=source)
    edge_specs = [
        _edge_spec(edge, index=index, source=source)
        for index, edge in enumerate(
            _require_list(plan, "edges", source=source, path="edges"), start=1
        )
    ]
    entrypoint = (
        _require_str(plan, "entrypoint", source=source, path="entrypoint")
        if "entrypoint" in plan
        else _infer_entrypoint(node_specs, edge_specs, source=source)
    )
    input_specs = _type_mapping(plan.get("inputs", {}))
    output_specs = _type_mapping(plan.get("outputs", {}))
    channels = _collect_channels(input_specs, output_specs, node_specs, executor_registry)
    state_schema = plan.get("state_schema", {})
    if not isinstance(state_schema, Mapping):
        raise AdapterParseError(
            "state_schema must be an object", source=source, path="state_schema"
        )
    reducers = _reducers_from_plan(plan, state_schema, source=source)
    metadata = _metadata_mapping(plan["metadata"], source=source) if "metadata" in plan else {}
    policies = _validate_nested(
        PolicySpec,
        plan.get("policies", {}),
        source=source,
        path="policies",
    )

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
                "reducers": reducers,
            },
            "nodes": [node.model_dump(mode="json") for node in node_specs],
            "edges": [edge.model_dump(mode="json") for edge in edge_specs],
            "policies": policies.model_dump(mode="json"),
            "metadata": metadata,
        }
    )
    return workflow


def _node_spec(
    node: Any,
    executors: ExecutorRegistry,
    *,
    source: str | None,
    index: int,
) -> NodeSpec:
    if not isinstance(node, Mapping):
        raise AdapterParseError(
            f"node {index} must be an object", source=source, path=f"nodes[{index}]"
        )
    executor_ref = _require_str(node, "executor", source=source, path=f"nodes[{index}].executor")
    executor = executors.get(executor_ref) if executors.has(executor_ref) else None
    input_schema = executor.input_schema if executor is not None else {}
    output_schema = executor.output_schema if executor is not None else {}

    explicit_inputs = node.get("inputs", {})
    explicit_outputs = node.get("outputs", {})
    inputs = _selector_mapping(
        explicit_inputs, input_schema, source=source, path=f"nodes[{index}].inputs"
    )
    outputs = _selector_mapping(
        explicit_outputs, output_schema, source=source, path=f"nodes[{index}].outputs"
    )

    return NodeSpec(
        id=_require_str(node, "id", source=source, path=f"nodes[{index}].id"),
        kind=_require_str(node, "kind", source=source, path=f"nodes[{index}].kind"),
        executor=ExecutorRef(
            ref=executor_ref,
            type=executor.type if executor is not None else ExecutorType.BUILTIN,
        ),
        inputs=inputs,
        outputs=outputs,
        params=dict(node.get("params", {})),
        retry=_validate_nested(
            RetryPolicy, node["retry"], source=source, path=f"nodes[{index}].retry"
        )
        if "retry" in node
        else None,
        timeout_s=node.get("timeout_s"),
        security=_validate_nested(
            SecurityPolicy, node["security"], source=source, path=f"nodes[{index}].security"
        )
        if "security" in node
        else None,
    )


def _edge_spec(edge: Mapping[str, Any], *, index: int, source: str | None) -> EdgeSpec:
    if not isinstance(edge, Mapping):
        raise AdapterParseError(
            f"edge {index} must be an object", source=source, path=f"edges[{index - 1}]"
        )
    edge_source = _edge_endpoint(
        edge, "from", "source", source=source, path=f"edges[{index - 1}].from"
    )
    target = _edge_endpoint(edge, "to", "target", source=source, path=f"edges[{index - 1}].to")
    kind_path = f"edges[{index - 1}].kind"
    try:
        kind = EdgeKind(edge.get("kind", EdgeKind.LINEAR.value))
    except ValueError as exc:
        raise AdapterParseError(str(exc), source=source, path=kind_path) from exc
    return EdgeSpec(
        id=str(edge.get("id") or _stable_edge_id(edge_source, target, index)),
        source=edge_source,
        target=target,
        kind=kind,
        condition=_validate_nested(
            ConditionSpec,
            edge["condition"],
            source=source,
            path=f"edges[{index - 1}].condition",
        )
        if "condition" in edge
        else None,
        map=_validate_nested(MapSpec, edge["map"], source=source, path=f"edges[{index - 1}].map")
        if "map" in edge
        else None,
        loop_guard=_validate_nested(
            LoopGuard,
            edge["loop_guard"],
            source=source,
            path=f"edges[{index - 1}].loop_guard",
        )
        if "loop_guard" in edge
        else None,
        join_sources=_join_sources(
            edge.get("join_sources"),
            source=source,
            path=f"edges[{index - 1}].join_sources",
        )
        if "join_sources" in edge
        else None,
    )


def _edge_endpoint(
    edge: Mapping[str, Any],
    primary: str,
    alias: str,
    *,
    source: str | None,
    path: str,
) -> str:
    value = edge.get(primary, edge.get(alias))
    if not isinstance(value, str) or not value:
        raise AdapterParseError(
            f'edge "{edge.get("id", "<unknown>")}" must define "{primary}" or "{alias}"',
            source=source,
            path=path,
        )
    return value


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
                input_type = _schema_type_for_selector(
                    node.inputs, executor.input_schema, selector.state_key
                )
            channels.setdefault(selector.state_key, input_type or _any_type())
        for selector in node.outputs.values():
            output_type = None
            if executor is not None:
                output_type = _schema_type_for_selector(
                    node.outputs, executor.output_schema, selector.state_key
                )
            channels.setdefault(selector.state_key, output_type or _any_type())
    return channels


def _selector_mapping(
    explicit_mapping: Any,
    schema: dict[str, TypeSpec],
    *,
    source: str | None = None,
    path: str | None = None,
) -> dict[str, StateSelector]:
    if not isinstance(explicit_mapping, Mapping):
        raise AdapterParseError(
            "node inputs and outputs must be mappings", source=source, path=path
        )
    if explicit_mapping:
        return {
            name: StateSelector.model_validate(
                value if isinstance(value, Mapping) else {"state_key": value}
            )
            for name, value in explicit_mapping.items()
        }
    return {name: StateSelector(state_key=name) for name in schema}


def _validate_nested(model: Any, value: Any, *, source: str | None, path: str) -> Any:
    try:
        return model.model_validate(value)
    except ValidationError as exc:
        first_error = exc.errors()[0]
        nested_path = ".".join(str(part) for part in first_error["loc"])
        full_path = f"{path}.{nested_path}" if nested_path else path
        raise AdapterParseError(f"{path} validation failed", source=source, path=full_path) from exc


def _type_mapping(raw: Any) -> dict[str, TypeSpec]:
    if not isinstance(raw, Mapping):
        raise TypeError("plan inputs and outputs must be mappings")
    return {name: _type_spec(value) for name, value in raw.items()}


def _workflow_id(plan: Mapping[str, Any], plan_name: str, *, source: str | None) -> str:
    if "workflow_id" not in plan:
        return _slugify_identifier(plan_name, source=source, path="name")
    value = _require_str(plan, "workflow_id", source=source, path="workflow_id")
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", value):
        raise AdapterParseError(
            "workflow_id must be a valid identifier",
            source=source,
            path="workflow_id",
        )
    return value


def _metadata_mapping(raw: Any, *, source: str | None) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise AdapterParseError("metadata must be an object", source=source, path="metadata")
    return dict(raw)


def _reducers_from_plan(
    plan: Mapping[str, Any],
    state_schema: Mapping[str, Any],
    *,
    source: str | None,
) -> dict[str, ReducerName]:
    has_state_reducers = "reducers" in state_schema
    has_top_level_reducers = "reducers" in plan
    state_reducers = _reducer_mapping(
        state_schema.get("reducers", {}),
        source=source,
        path="state_schema.reducers",
    )
    if not has_top_level_reducers:
        return state_reducers
    top_level_reducers = _reducer_mapping(
        plan.get("reducers", {}),
        source=source,
        path="reducers",
    )
    if has_state_reducers and state_reducers != top_level_reducers:
        raise AdapterParseError(
            "reducers conflicts with state_schema.reducers",
            source=source,
            path="reducers",
        )
    return top_level_reducers


def _reducer_mapping(
    raw: Any,
    *,
    source: str | None,
    path: str = "state_schema.reducers",
) -> dict[str, ReducerName]:
    if not isinstance(raw, Mapping):
        raise AdapterParseError(
            f"{path} must be a mapping",
            source=source,
            path=path,
        )
    try:
        return {name: ReducerName(value) for name, value in raw.items()}
    except ValueError as exc:
        raise AdapterParseError(
            f"{path} contains unsupported reducer",
            source=source,
            path=path,
        ) from exc


def _join_sources(raw: Any, *, source: str | None, path: str) -> list[str]:
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise AdapterParseError("join_sources must be a list of strings", source=source, path=path)
    return raw


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


def _require_str(
    data: Mapping[str, Any],
    key: str,
    *,
    source: str | None = None,
    path: str | None = None,
) -> str:
    try:
        value = data[key]
    except KeyError as exc:
        raise AdapterParseError(
            f"{key} must be a non-empty string", source=source, path=path or key
        ) from exc
    if not isinstance(value, str) or not value:
        raise AdapterParseError(
            f"{key} must be a non-empty string", source=source, path=path or key
        )
    return value


def _require_list(
    data: Mapping[str, Any],
    key: str,
    *,
    source: str | None = None,
    path: str | None = None,
) -> list[Any]:
    try:
        value = data[key]
    except KeyError as exc:
        raise AdapterParseError(f"{key} must be a list", source=source, path=path or key) from exc
    if not isinstance(value, list):
        raise AdapterParseError(f"{key} must be a list", source=source, path=path or key)
    return value


def _slugify_identifier(
    value: str,
    *,
    source: str | None = None,
    path: str | None = None,
) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value.strip().lower()).strip("_")
    if not slug:
        raise AdapterParseError(
            "name must produce a non-empty workflow_id", source=source, path=path
        )
    if slug[0].isdigit():
        slug = f"workflow_{slug}"
    return slug


def _stable_edge_id(source: str, target: str, index: int) -> str:
    return f"{source}_to_{target}" if index == 1 else f"{source}_to_{target}_{index}"


def _infer_entrypoint(
    nodes: list[NodeSpec],
    edges: list[EdgeSpec],
    *,
    source: str | None = None,
) -> str:
    node_ids = {node.id for node in nodes}
    targets = {edge.target for edge in edges if edge.target in node_ids}
    roots = sorted(node_ids - targets)
    if len(roots) != 1:
        raise AdapterParseError(
            "could not infer a unique entrypoint", source=source, path="entrypoint"
        )
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
