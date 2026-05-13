"""State selector and executor schema checks."""

from prompt2langgraph.diagnostics.codes import E_SCHEMA_002, E_TYPE_003
from prompt2langgraph.diagnostics.report import Diagnostic, DiagnosticLocation
from prompt2langgraph.ir.models import TypeName, TypeSpec, WorkflowSpec
from prompt2langgraph.registry.executors import ExecutorRegistry
from prompt2langgraph.registry.nodes import NodeRegistry


def check_types(workflow: WorkflowSpec, executors: ExecutorRegistry, nodes: NodeRegistry) -> list[Diagnostic]:
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

        node_definition = nodes.get(node.kind) if nodes.has(node.kind) else None
        if node_definition is not None:
            diagnostics.extend(_check_params(node.id, node.params, node_definition.param_schema))

    return diagnostics


def _types_compatible(expected: TypeSpec, actual: TypeSpec) -> bool:
    if expected.type is TypeName.ANY or actual.type is TypeName.ANY:
        return True
    return expected.type is actual.type


def _check_params(node_id: str, params: dict[str, object], schema: dict[str, TypeSpec]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for name, expected in schema.items():
        if name not in params:
            continue
        if not _value_matches_type(params[name], expected):
            diagnostics.append(
                Diagnostic(
                    code=E_TYPE_003,
                    severity="error",
                    message=f'node "{node_id}" param "{name}" expects {expected.type.value}',
                    location=DiagnosticLocation(node_id=node_id, path=f"params.{name}"),
                )
            )
    for name in sorted(set(params) - set(schema)):
        diagnostics.append(
            Diagnostic(
                code=E_TYPE_003,
                severity="warning",
                message=f'node "{node_id}" param "{name}" is not declared by node kind schema',
                location=DiagnosticLocation(node_id=node_id, path=f"params.{name}"),
            )
        )
    return diagnostics


def _value_matches_type(value: object, expected: TypeSpec) -> bool:
    if expected.type is TypeName.ANY:
        return True
    if expected.type is TypeName.STRING:
        return isinstance(value, str)
    if expected.type is TypeName.NUMBER:
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected.type is TypeName.INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    if expected.type is TypeName.BOOLEAN:
        return isinstance(value, bool)
    if expected.type is TypeName.OBJECT:
        if not isinstance(value, dict):
            return False
        return all(
            name not in value or _value_matches_type(value[name], property_spec)
            for name, property_spec in expected.properties.items()
        )
    if expected.type is TypeName.ARRAY:
        if not isinstance(value, list):
            return False
        if expected.item_type is None:
            return True
        return all(_value_matches_type(item, expected.item_type) for item in value)
    if expected.type is TypeName.MESSAGES:
        return isinstance(value, list)
    if expected.type is TypeName.ARTIFACT_REF:
        return isinstance(value, str)
    return False
