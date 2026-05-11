"""Normalization helpers for Workflow IR."""

from prompt2langgraph.ir.models import WorkflowSpec


def normalize_workflow(workflow: WorkflowSpec) -> WorkflowSpec:
    """Return a copy with deterministic node and edge ordering."""
    return workflow.model_copy(
        update={
            "nodes": sorted(workflow.nodes, key=lambda node: node.id),
            "edges": sorted(workflow.edges, key=lambda edge: edge.id),
        }
    )
