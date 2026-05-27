"""Normalization helpers for Workflow IR."""

from prompt2langgraph.ir.models import WorkflowSpec


def normalize_workflow(workflow: WorkflowSpec) -> WorkflowSpec:
    """Return a copy with deterministic node and edge ordering."""
    edges = sorted(workflow.edges, key=lambda edge: edge.id)
    # Sort join_sources within each edge for deterministic hashing
    normalized_edges = []
    for edge in edges:
        if edge.join_sources is not None:
            edge = edge.model_copy(update={"join_sources": sorted(edge.join_sources)})
        normalized_edges.append(edge)
    return workflow.model_copy(
        update={
            "nodes": sorted(workflow.nodes, key=lambda node: node.id),
            "edges": normalized_edges,
        }
    )
