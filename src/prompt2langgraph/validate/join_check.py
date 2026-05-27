"""JOIN edge validation checks for Workflow IR."""

from collections import Counter

from prompt2langgraph.diagnostics.codes import (
    E_JOIN_001,
    E_JOIN_002,
    E_JOIN_003,
    E_JOIN_004,
    E_JOIN_005,
    E_JOIN_006,
    W_JOIN_001,
    W_JOIN_002,
)
from prompt2langgraph.diagnostics.report import Diagnostic, DiagnosticLocation
from prompt2langgraph.ir.models import EdgeKind, WorkflowSpec


def check_join_edges(workflow: WorkflowSpec) -> list[Diagnostic]:
    """Validate JOIN edges in the workflow.

    Checks:
    - E_JOIN_001: join_sources is missing/empty, or target appears in join_sources
    - E_JOIN_002: join_sources has fewer than 2 elements
    - E_JOIN_003: join_sources references non-existent nodes
    - E_JOIN_004: join_sources node already has a LINEAR/CONDITIONAL edge to the same target
    - E_JOIN_005: same target is referenced by multiple JOIN edges
    - E_JOIN_006: join_sources contains duplicate node ids
    - W_JOIN_001: source field not in join_sources (warning, non-blocking)
    - W_JOIN_002: multiple join_sources write same state key without reducer (warning)
    """
    diagnostics: list[Diagnostic] = []
    node_ids = {node.id for node in workflow.nodes}

    join_targets: list[str] = []

    # Pre-build index: (source, target) -> set of edge kinds for O(1) E_JOIN_004 lookup
    direct_edges: dict[tuple[str, str], set[EdgeKind]] = {}
    for edge in workflow.edges:
        if edge.kind in {EdgeKind.LINEAR, EdgeKind.CONDITIONAL, EdgeKind.FANOUT, EdgeKind.LOOP}:
            direct_edges.setdefault((edge.source, edge.target), set()).add(edge.kind)

    for edge in workflow.edges:
        if edge.kind is not EdgeKind.JOIN:
            continue

        join_targets.append(edge.target)

        # E_JOIN_001: join_sources is missing or empty
        if not edge.join_sources:
            diagnostics.append(
                Diagnostic(
                    code=E_JOIN_001,
                    severity="error",
                    message="JOIN edge requires join_sources field (v0.2 migration)",
                    location=DiagnosticLocation(edge_id=edge.id),
                )
            )
            continue

        # E_JOIN_001: target node appears in its own join_sources (self-referencing)
        if edge.target in edge.join_sources:
            diagnostics.append(
                Diagnostic(
                    code=E_JOIN_001,
                    severity="error",
                    message=(
                        f'join target "{edge.target}" appears in its own join_sources; '
                        f"a node cannot join to itself"
                    ),
                    location=DiagnosticLocation(edge_id=edge.id, node_id=edge.target),
                )
            )

        # E_JOIN_002: check join_sources has at least 2 elements
        # Do dedup check first (E_JOIN_006) so counts are accurate
        if len(set(edge.join_sources)) != len(edge.join_sources):
            duplicates = [
                src for src, cnt in Counter(edge.join_sources).items() if cnt > 1
            ]
            diagnostics.append(
                Diagnostic(
                    code=E_JOIN_006,
                    severity="error",
                    message=(
                        f"join_sources contains duplicate entries: "
                        f'{", ".join(duplicates)}'
                    ),
                    location=DiagnosticLocation(edge_id=edge.id),
                )
            )

        if len(edge.join_sources) < 2:
            diagnostics.append(
                Diagnostic(
                    code=E_JOIN_002,
                    severity="error",
                    message="join_sources must have at least 2 elements",
                    location=DiagnosticLocation(edge_id=edge.id),
                )
            )

        # E_JOIN_003: check join_sources references valid nodes
        for source_id in edge.join_sources:
            if source_id not in node_ids:
                diagnostics.append(
                    Diagnostic(
                        code=E_JOIN_003,
                        severity="error",
                        message=f'join_sources references unknown node "{source_id}"',
                        location=DiagnosticLocation(edge_id=edge.id, node_id=source_id),
                    )
                )

        # E_JOIN_004: check if any join_sources node already has a direct edge
        for source_id in edge.join_sources:
            key = (source_id, edge.target)
            if key in direct_edges:
                kinds = direct_edges[key]
                kind_label = next(iter(kinds)).value
                diagnostics.append(
                    Diagnostic(
                        code=E_JOIN_004,
                        severity="error",
                        message=(
                            f'join_sources node "{source_id}" already has a '
                            f'{kind_label} edge to target "{edge.target}"'
                        ),
                        location=DiagnosticLocation(edge_id=edge.id, node_id=source_id),
                    )
                )

        # W_JOIN_001: source field not in join_sources (warning)
        if edge.source not in edge.join_sources:
            diagnostics.append(
                Diagnostic(
                    code=W_JOIN_001,
                    severity="warning",
                    message=f'join edge source "{edge.source}" is not in join_sources',
                    location=DiagnosticLocation(edge_id=edge.id, node_id=edge.source),
                    hint="source field is not used in compilation or visualization; join_sources defines actual fan-in sources",  # noqa: E501
                )
            )

    # E_JOIN_005: same target referenced by multiple JOIN edges
    for target, count in Counter(join_targets).items():
        if count > 1:
            conflicting_ids = [
                edge.id for edge in workflow.edges
                if edge.kind is EdgeKind.JOIN and edge.target == target
            ]
            diagnostics.append(
                Diagnostic(
                    code=E_JOIN_005,
                    severity="error",
                    message=(
                        f'join target "{target}" is referenced by multiple JOIN edges: '
                        f'{", ".join(conflicting_ids)}'
                    ),
                    location=DiagnosticLocation(edge_id=conflicting_ids[0], node_id=target),
                )
            )

    # W_JOIN_002: multiple join_sources write to same state key without reducer
    _check_join_reducer_warnings(workflow, diagnostics)

    return diagnostics


def _check_join_reducer_warnings(
    workflow: WorkflowSpec, diagnostics: list[Diagnostic]
) -> None:
    """Warn when multiple JOIN source nodes write the same state key without a reducer."""
    reducers = workflow.state_schema.reducers
    for edge in workflow.edges:
        if edge.kind is not EdgeKind.JOIN or not edge.join_sources:
            continue
        # Collect output state keys from each join_sources node
        source_outputs: dict[str, set[str]] = {}
        for node in workflow.nodes:
            if node.id in edge.join_sources:
                source_outputs[node.id] = {
                    selector.state_key for selector in node.outputs.values()
                }
        # Find keys written by multiple sources
        key_sources: dict[str, list[str]] = {}
        for src, keys in source_outputs.items():
            for key in keys:
                key_sources.setdefault(key, []).append(src)
        for key, sources in key_sources.items():
            if len(sources) <= 1:
                continue
            if key in reducers:
                continue
            diagnostics.append(
                Diagnostic(
                    code=W_JOIN_002,
                    severity="warning",
                    message=(
                        f'state key "{key}" is written by multiple join_sources '
                        f'({", ".join(sorted(sources))}) without a reducer; '
                        f"parallel writes may be overwritten non-deterministically"
                    ),
                    location=DiagnosticLocation(edge_id=edge.id, state_key=key),
                    hint=f'add "{key}" with an appropriate reducer to state_schema.reducers',
                )
            )