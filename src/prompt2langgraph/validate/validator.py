"""Top-level deterministic Workflow IR validator."""

from typing import Any

from pydantic import ValidationError

from prompt2langgraph.diagnostics.codes import E_BIND_006, E_DEP_004, E_SCHEMA_002
from prompt2langgraph.diagnostics.report import Diagnostic, DiagnosticLocation, ValidationReport
from prompt2langgraph.ir.models import WorkflowSpec
from prompt2langgraph.registry.builtins import builtin_executor_registry, builtin_node_registry
from prompt2langgraph.registry.executors import ExecutorRegistry
from prompt2langgraph.registry.nodes import NodeRegistry
from prompt2langgraph.validate.graphcheck import check_graph
from prompt2langgraph.validate.security import check_security
from prompt2langgraph.validate.typecheck import check_types


def validate_workflow(
    workflow: WorkflowSpec | dict[str, Any],
    *,
    nodes: NodeRegistry | None = None,
    executors: ExecutorRegistry | None = None,
) -> ValidationReport:
    node_registry = nodes or builtin_node_registry()
    executor_registry = executors or builtin_executor_registry()

    try:
        spec = workflow if isinstance(workflow, WorkflowSpec) else WorkflowSpec.model_validate(workflow)
    except ValidationError as exc:
        return ValidationReport(
            diagnostics=[
                Diagnostic(
                    code=E_SCHEMA_002,
                    severity="error",
                    message="workflow schema validation failed",
                    location=DiagnosticLocation(path=".".join(str(part) for part in error["loc"])),
                    hint=error["msg"],
                )
                for error in exc.errors()
            ]
        )

    diagnostics: list[Diagnostic] = []
    diagnostics.extend(_check_registries(spec, node_registry, executor_registry))
    diagnostics.extend(check_graph(spec))
    diagnostics.extend(check_types(spec, executor_registry, node_registry))
    diagnostics.extend(check_security(spec, node_registry))
    return ValidationReport(diagnostics=diagnostics)


def _check_registries(
    workflow: WorkflowSpec,
    nodes: NodeRegistry,
    executors: ExecutorRegistry,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    for node in workflow.nodes:
        if not nodes.has(node.kind):
            diagnostics.append(
                Diagnostic(
                    code=E_DEP_004,
                    severity="error",
                    message=f'node kind "{node.kind}" is not registered',
                    location=DiagnosticLocation(node_id=node.id),
                )
            )

        if not executors.has(node.executor.ref):
            diagnostics.append(
                Diagnostic(
                    code=E_BIND_006,
                    severity="error",
                    message=f'node "{node.id}" references unregistered executor "{node.executor.ref}"',
                    location=DiagnosticLocation(node_id=node.id),
                )
            )
            continue

        executor = executors.get(node.executor.ref)
        if node.executor.type is not executor.type:
            diagnostics.append(
                Diagnostic(
                    code=E_BIND_006,
                    severity="error",
                    message=(
                        f'node "{node.id}" executor "{node.executor.ref}" declares type '
                        f'"{node.executor.type.value}", expected "{executor.type.value}"'
                    ),
                    location=DiagnosticLocation(node_id=node.id),
                )
            )

    return diagnostics
