"""Mermaid rendering for Workflow IR."""

from __future__ import annotations

from prompt2langgraph.ir.models import EdgeKind, WorkflowSpec
from prompt2langgraph.ir.normalize import normalize_workflow


def workflow_to_mermaid(workflow: WorkflowSpec) -> str:
    normalized = normalize_workflow(workflow)
    lines = ["flowchart LR", '    START(["START"])', '    END(["END"])']

    for node in normalized.nodes:
        lines.append(f'    {node.id}["{node.id}"]')

    lines.append(f"    START --> {normalized.entrypoint}")
    for edge in normalized.edges:
        lines.extend(_edge_lines(edge))

    terminal_nodes = _terminal_nodes(normalized)
    for node_id in terminal_nodes:
        lines.append(f"    {node_id} --> END")

    return "\n".join(lines)


def _edge_lines(edge) -> list[str]:
    if edge.kind is EdgeKind.CONDITIONAL and edge.condition is not None:
        return [
            f"    {edge.source} -- {route} --> {target}"
            for route, target in edge.condition.routes.items()
        ]
    return [f"    {edge.source} --> {edge.target}"]


def _terminal_nodes(workflow: WorkflowSpec) -> list[str]:
    outgoing = {edge.source for edge in workflow.edges}
    return [node.id for node in workflow.nodes if node.id not in outgoing]
