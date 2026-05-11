"""State selector and executor schema checks."""

from prompt2langgraph.diagnostics.codes import E_SCHEMA_002, E_TYPE_003
from prompt2langgraph.diagnostics.report import Diagnostic, DiagnosticLocation
from prompt2langgraph.ir.models import TypeName, TypeSpec, WorkflowSpec
from prompt2langgraph.registry.executors import ExecutorRegistry


def check_types(workflow: WorkflowSpec, executors: ExecutorRegistry) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    state_types = {**workflow.state_schema.channels, **workflow.state_schema.private}

    for node in workflow.nodes:
        if not executors.has(node.executor.ref):
            continue

        executor = executors.get(node.executor.ref)
        for input_name, selector in node.inputs.items():
            actual = state_types.get(selector.state_key)
            if actual is None:
                diagnostics.append(
                    Diagnostic(
                        code=E_SCHEMA_002,
                        severity="error",
                        message=f'node input "{input_name}" references undeclared state key "{selector.state_key}"',
                        location=DiagnosticLocation(node_id=node.id, state_key=selector.state_key),
                    )
                )
                continue

            expected = executor.input_schema.get(input_name)
            if expected is not None and not _types_compatible(expected, actual):
                diagnostics.append(
                    Diagnostic(
                        code=E_TYPE_003,
                        severity="error",
                        message=(
                            f'node "{node.id}" input "{input_name}" expects '
                            f"{expected.type.value}, got {actual.type.value}"
                        ),
                        location=DiagnosticLocation(node_id=node.id, state_key=selector.state_key),
                    )
                )

        for input_name in sorted(set(executor.input_schema) - set(node.inputs)):
            diagnostics.append(
                Diagnostic(
                    code=E_TYPE_003,
                    severity="error",
                    message=f'node "{node.id}" is missing required input mapping "{input_name}"',
                    location=DiagnosticLocation(node_id=node.id),
                )
            )

        for output_name, selector in node.outputs.items():
            actual = state_types.get(selector.state_key)
            if actual is None:
                diagnostics.append(
                    Diagnostic(
                        code=E_SCHEMA_002,
                        severity="error",
                        message=f'node output "{output_name}" references undeclared state key "{selector.state_key}"',
                        location=DiagnosticLocation(node_id=node.id, state_key=selector.state_key),
                    )
                )
                continue

            expected = executor.output_schema.get(output_name)
            if expected is not None and not _types_compatible(expected, actual):
                diagnostics.append(
                    Diagnostic(
                        code=E_TYPE_003,
                        severity="error",
                        message=(
                            f'node "{node.id}" output "{output_name}" expects '
                            f"{expected.type.value}, got {actual.type.value}"
                        ),
                        location=DiagnosticLocation(node_id=node.id, state_key=selector.state_key),
                    )
                )

        for output_name in sorted(set(executor.output_schema) - set(node.outputs)):
            diagnostics.append(
                Diagnostic(
                    code=E_TYPE_003,
                    severity="error",
                    message=f'node "{node.id}" is missing required output mapping "{output_name}"',
                    location=DiagnosticLocation(node_id=node.id),
                )
            )

    return diagnostics


def _types_compatible(expected: TypeSpec, actual: TypeSpec) -> bool:
    if expected.type is TypeName.ANY or actual.type is TypeName.ANY:
        return True
    return expected.type is actual.type
