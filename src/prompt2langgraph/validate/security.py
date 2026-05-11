"""Security policy checks."""

from prompt2langgraph.diagnostics.codes import E_SIDE_008
from prompt2langgraph.diagnostics.report import Diagnostic, DiagnosticLocation
from prompt2langgraph.ir.models import WorkflowSpec
from prompt2langgraph.registry.nodes import NodeRegistry


def check_security(workflow: WorkflowSpec, nodes: NodeRegistry) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    for node in workflow.nodes:
        is_side_effect = node.kind == "side_effect" or (
            nodes.has(node.kind) and nodes.get(node.kind).side_effect
        )
        if not is_side_effect or workflow.policies.allow_side_effects:
            continue

        has_node_policy = node.security is not None and (
            node.security.requires_approval or node.security.idempotency_key is not None
        )
        if not has_node_policy:
            diagnostics.append(
                Diagnostic(
                    code=E_SIDE_008,
                    severity="error",
                    message="side_effect node requires approval or idempotency key",
                    location=DiagnosticLocation(node_id=node.id),
                )
            )

    return diagnostics

