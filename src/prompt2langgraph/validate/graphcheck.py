"""Graph structure checks for Workflow IR."""

import re
from collections import Counter, defaultdict, deque

from prompt2langgraph.diagnostics.codes import E_LOOP_005, E_REDUCER_012, E_ROUTE_011, E_SCHEMA_002, E_TYPE_003
from prompt2langgraph.diagnostics.report import Diagnostic, DiagnosticLocation
from prompt2langgraph.ir.models import EdgeKind, TypeName, WorkflowSpec


CONDITION_PATTERN = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(<=|>=|==|!=|<|>)\s*(.+?)\s*$")


def check_graph(workflow: WorkflowSpec) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    node_ids = [node.id for node in workflow.nodes]
    node_id_set = set(node_ids)

    for node_id, count in Counter(node_ids).items():
        if count > 1:
            diagnostics.append(
                Diagnostic(
                    code=E_SCHEMA_002,
                    severity="error",
                    message=f'duplicate node id "{node_id}"',
                    location=DiagnosticLocation(node_id=node_id),
                )
            )

    edge_ids = [edge.id for edge in workflow.edges]
    for edge_id, count in Counter(edge_ids).items():
        if count > 1:
            diagnostics.append(
                Diagnostic(
                    code=E_SCHEMA_002,
                    severity="error",
                    message=f'duplicate edge id "{edge_id}"',
                    location=DiagnosticLocation(edge_id=edge_id),
                )
            )

    if workflow.entrypoint not in node_id_set:
        diagnostics.append(
            Diagnostic(
                code=E_SCHEMA_002,
                severity="error",
                message=f'entrypoint "{workflow.entrypoint}" is not a node',
                location=DiagnosticLocation(node_id=workflow.entrypoint),
            )
        )

    outgoing: dict[str, list[str]] = defaultdict(list)
    dynamic_sources: set[str] = set()
    static_sources: set[str] = set()

    for edge in workflow.edges:
        if edge.source not in node_id_set:
            diagnostics.append(
                Diagnostic(
                    code=E_SCHEMA_002,
                    severity="error",
                    message=f'edge source "{edge.source}" is not a node',
                    location=DiagnosticLocation(edge_id=edge.id, node_id=edge.source),
                )
            )
        if edge.target not in node_id_set:
            diagnostics.append(
                Diagnostic(
                    code=E_SCHEMA_002,
                    severity="error",
                    message=f'edge target "{edge.target}" is not a node',
                    location=DiagnosticLocation(edge_id=edge.id, node_id=edge.target),
                )
            )

        outgoing[edge.source].extend(_reachable_targets(edge))
        if edge.kind in {EdgeKind.CONDITIONAL, EdgeKind.LOOP, EdgeKind.FANOUT}:
            dynamic_sources.add(edge.source)
        else:
            static_sources.add(edge.source)

        if edge.kind is EdgeKind.LOOP and edge.loop_guard is None:
            diagnostics.append(
                Diagnostic(
                    code=E_LOOP_005,
                    severity="error",
                    message="loop edge requires loop_guard.max_iterations",
                    location=DiagnosticLocation(edge_id=edge.id),
                )
            )

        if edge.kind is EdgeKind.CONDITIONAL:
            diagnostics.extend(_check_condition(edge, workflow))

        if edge.condition is not None:
            for route_target in edge.condition.routes.values():
                if route_target not in node_id_set:
                    diagnostics.append(
                        Diagnostic(
                            code=E_SCHEMA_002,
                            severity="error",
                            message=f'condition route target "{route_target}" is not a node',
                            location=DiagnosticLocation(edge_id=edge.id, node_id=route_target),
                        )
                    )

        if edge.kind is EdgeKind.FANOUT:
            diagnostics.extend(_check_fanout(edge, workflow))

    for source in sorted(dynamic_sources & static_sources):
        diagnostics.append(
            Diagnostic(
                code=E_ROUTE_011,
                severity="error",
                message=f'node "{source}" mixes dynamic routing and static outgoing edges',
                location=DiagnosticLocation(node_id=source),
            )
        )

    diagnostics.extend(_check_reachability(workflow.entrypoint, node_id_set, outgoing))
    diagnostics.extend(_check_exit_path(workflow.entrypoint, node_id_set, outgoing))
    return diagnostics


def _reachable_targets(edge) -> list[str]:
    if edge.kind is EdgeKind.CONDITIONAL and edge.condition is not None:
        return list(edge.condition.routes.values())
    return [edge.target]


def _check_condition(edge, workflow: WorkflowSpec) -> list[Diagnostic]:
    if edge.condition is None:
        return [
            Diagnostic(
                code=E_ROUTE_011,
                severity="error",
                message="conditional edge requires condition",
                location=DiagnosticLocation(edge_id=edge.id),
            )
        ]

    diagnostics: list[Diagnostic] = []
    route_keys = set(edge.condition.routes)
    if not {"true", "false"}.issubset(route_keys):
        diagnostics.append(
            Diagnostic(
                code=E_ROUTE_011,
                severity="error",
                message='conditional routes must include "true" and "false"',
                location=DiagnosticLocation(edge_id=edge.id),
            )
        )

    match = CONDITION_PATTERN.match(edge.condition.expr)
    if match is None:
        diagnostics.append(
            Diagnostic(
                code=E_ROUTE_011,
                severity="error",
                message=f'unsupported conditional expression "{edge.condition.expr}"',
                location=DiagnosticLocation(edge_id=edge.id),
                hint='supported form: "<state_key> <comparison> <literal>"',
            )
        )
        return diagnostics

    state_key = match.group(1)
    state_types = {**workflow.state_schema.channels, **workflow.state_schema.private}
    if state_key not in state_types:
        diagnostics.append(
            Diagnostic(
                code=E_SCHEMA_002,
                severity="error",
                message=f'conditional expression references undeclared state key "{state_key}"',
                location=DiagnosticLocation(edge_id=edge.id, state_key=state_key),
            )
        )

    return diagnostics


def _check_fanout(edge, workflow: WorkflowSpec) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    state_types = {**workflow.state_schema.channels, **workflow.state_schema.private}

    if edge.map is None:
        return [
            Diagnostic(
                code=E_SCHEMA_002,
                severity="error",
                message="fanout edge requires map spec",
                location=DiagnosticLocation(edge_id=edge.id),
            )
        ]

    for state_key in (edge.map.items_state_key, edge.map.item_state_key, edge.map.result_state_key):
        if state_key not in state_types:
            diagnostics.append(
                Diagnostic(
                    code=E_SCHEMA_002,
                    severity="error",
                    message=f'fanout map references undeclared state key "{state_key}"',
                    location=DiagnosticLocation(edge_id=edge.id, state_key=state_key),
                )
            )

    items_type = state_types.get(edge.map.items_state_key)
    if items_type is not None and items_type.type is not TypeName.ARRAY:
        diagnostics.append(
            Diagnostic(
                code=E_TYPE_003,
                severity="error",
                message=f'fanout items state "{edge.map.items_state_key}" must be array',
                location=DiagnosticLocation(edge_id=edge.id, state_key=edge.map.items_state_key),
            )
        )

    item_type = state_types.get(edge.map.item_state_key)
    if items_type is not None and item_type is not None and items_type.item_type is not None:
        if not _types_compatible(items_type.item_type, item_type):
            diagnostics.append(
                Diagnostic(
                    code=E_TYPE_003,
                    severity="error",
                    message=(
                        f'fanout item state "{edge.map.item_state_key}" expects '
                        f"{items_type.item_type.type.value}, got {item_type.type.value}"
                    ),
                    location=DiagnosticLocation(edge_id=edge.id, state_key=edge.map.item_state_key),
                )
            )

    result_type = state_types.get(edge.map.result_state_key)
    if result_type is not None and result_type.type is not TypeName.ARRAY:
        diagnostics.append(
            Diagnostic(
                code=E_TYPE_003,
                severity="error",
                message=f'fanout result state "{edge.map.result_state_key}" must be array',
                location=DiagnosticLocation(edge_id=edge.id, state_key=edge.map.result_state_key),
            )
        )

    if edge.map.result_state_key not in workflow.state_schema.reducers:
        diagnostics.append(
            Diagnostic(
                code=E_REDUCER_012,
                severity="error",
                message=f'fanout result state "{edge.map.result_state_key}" requires a reducer',
                location=DiagnosticLocation(edge_id=edge.id, state_key=edge.map.result_state_key),
            )
        )

    return diagnostics


def _types_compatible(expected, actual) -> bool:
    if expected.type is TypeName.ANY or actual.type is TypeName.ANY:
        return True
    return expected.type is actual.type


def _check_reachability(
    entrypoint: str,
    node_ids: set[str],
    outgoing: dict[str, list[str]],
) -> list[Diagnostic]:
    if entrypoint not in node_ids:
        return []

    seen: set[str] = set()
    queue: deque[str] = deque([entrypoint])
    while queue:
        node_id = queue.popleft()
        if node_id in seen:
            continue
        seen.add(node_id)
        for target in outgoing.get(node_id, []):
            if target in node_ids:
                queue.append(target)

    diagnostics: list[Diagnostic] = []
    for node_id in sorted(node_ids - seen):
        diagnostics.append(
            Diagnostic(
                code=E_SCHEMA_002,
                severity="error",
                message=f'node "{node_id}" is unreachable from entrypoint',
                location=DiagnosticLocation(node_id=node_id),
            )
        )
    return diagnostics


def _check_exit_path(
    entrypoint: str,
    node_ids: set[str],
    outgoing: dict[str, list[str]],
) -> list[Diagnostic]:
    if entrypoint not in node_ids:
        return []

    terminal_nodes = {node_id for node_id in node_ids if not outgoing.get(node_id)}
    if not terminal_nodes:
        return [
            Diagnostic(
                code=E_SCHEMA_002,
                severity="error",
                message="graph has no exit path to a terminal node",
                location=DiagnosticLocation(node_id=entrypoint),
            )
        ]

    can_reach_terminal: set[str] = set()
    reverse: dict[str, list[str]] = defaultdict(list)
    for source, targets in outgoing.items():
        for target in targets:
            reverse[target].append(source)

    queue: deque[str] = deque(terminal_nodes)
    while queue:
        node_id = queue.popleft()
        if node_id in can_reach_terminal:
            continue
        can_reach_terminal.add(node_id)
        queue.extend(reverse.get(node_id, []))

    if entrypoint in can_reach_terminal:
        return []

    return [
        Diagnostic(
            code=E_SCHEMA_002,
            severity="error",
            message="entrypoint has no exit path to a terminal node",
            location=DiagnosticLocation(node_id=entrypoint),
        )
    ]
