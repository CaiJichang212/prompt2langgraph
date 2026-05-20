from __future__ import annotations

from pprint import pformat
from pathlib import Path

from prompt2langgraph.ir.models import ReducerName, TypeName, TypeSpec, WorkflowSpec


def emit_generated_bundle(workflow: WorkflowSpec, output_dir: Path | str) -> Path:
    root = Path(output_dir)
    generated = root / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    _write_init(generated)
    _write_state(workflow, generated)
    _write_nodes(workflow, generated)
    _write_graph(generated)
    return generated


def _write_init(generated: Path) -> None:
    (generated / "__init__.py").write_text(
        '"""Generated prompt2langgraph bundle."""\n', encoding="utf-8"
    )


def _write_state(workflow: WorkflowSpec, generated: Path) -> None:
    state_schema = workflow.state_schema.model_dump(mode="json")
    payload = {
        "workflow_id": workflow.workflow_id,
        "input": state_schema["input"],
        "output": state_schema["output"],
        "channels": state_schema["channels"],
        "private": state_schema["private"],
        "reducers": state_schema["reducers"],
    }
    state_class_name = _state_class_name(workflow)
    state_fields = {
        **workflow.state_schema.channels,
        **workflow.state_schema.private,
    }
    field_lines = [
        f"    {state_key}: {_state_annotation(type_spec, workflow.state_schema.reducers.get(state_key))}"
        for state_key, type_spec in state_fields.items()
    ]
    if not field_lines:
        field_lines = ["    pass"]

    text = (
        '"""Generated state definitions and metadata for this workflow bundle."""\n\n'
        f"{_state_imports(state_fields, workflow.state_schema.reducers)}\n\n"
        f"{_merge_dict_definition(workflow.state_schema.reducers)}"
        f"STATE_SCHEMA = {pformat(payload, sort_dicts=True, width=100)}\n\n\n"
        f"class {state_class_name}(TypedDict, total=False):\n"
        + "\n".join(field_lines)
        + "\n\n\n"
        f"State = {state_class_name}\n"
    )
    (generated / "state.py").write_text(text, encoding="utf-8")


def _write_nodes(workflow: WorkflowSpec, generated: Path) -> None:
    payload = [
        {"id": node.id, "kind": node.kind, "executor": node.executor.ref}
        for node in sorted(workflow.nodes, key=lambda item: item.id)
    ]
    text = (
        '"""Generated node metadata for this workflow bundle."""\n\n'
        f"NODES = {pformat(payload, sort_dicts=True, width=100)}\n"
    )
    (generated / "nodes.py").write_text(text, encoding="utf-8")


def _state_class_name(workflow: WorkflowSpec) -> str:
    return f"{workflow.workflow_id.title().replace('_', '')}State"


def _state_imports(
    state_fields: dict[str, TypeSpec], reducers: dict[str, ReducerName]
) -> str:
    typing_imports = []
    if reducers:
        typing_imports.append("Annotated")
    if any(_type_needs_any(type_spec) for type_spec in state_fields.values()) or any(
        reducer is ReducerName.MERGE_DICT for reducer in reducers.values()
    ):
        typing_imports.append("Any")

    lines = []
    if typing_imports:
        lines.append(f"from typing import {', '.join(typing_imports)}")
    if any(
        reducer in {ReducerName.APPEND, ReducerName.SUM}
        for reducer in reducers.values()
    ):
        lines.append("import operator")
    if any(reducer is ReducerName.ADD_MESSAGES for reducer in reducers.values()):
        lines.append("from langgraph.graph.message import add_messages")
    lines.append("from typing_extensions import TypedDict")
    return "\n".join(lines)


def _merge_dict_definition(reducers: dict[str, ReducerName]) -> str:
    if not any(reducer is ReducerName.MERGE_DICT for reducer in reducers.values()):
        return ""
    return (
        "def _merge_dict(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:\n"
        "    return {**left, **right}\n\n\n"
    )


def _state_annotation(type_spec: TypeSpec, reducer: ReducerName | None = None) -> str:
    annotation = _type_annotation(type_spec)
    if reducer is None:
        return annotation
    return f"Annotated[{annotation}, {_reducer_annotation(reducer)}]"


def _type_annotation(type_spec: TypeSpec) -> str:
    if type_spec.type is TypeName.STRING:
        return "str"
    if type_spec.type is TypeName.NUMBER:
        return "float"
    if type_spec.type is TypeName.INTEGER:
        return "int"
    if type_spec.type is TypeName.BOOLEAN:
        return "bool"
    if type_spec.type is TypeName.ARRAY:
        item_annotation = (
            _type_annotation(type_spec.item_type)
            if type_spec.item_type is not None
            else "Any"
        )
        return f"list[{item_annotation}]"
    if type_spec.type is TypeName.OBJECT:
        return "dict[str, Any]"
    if type_spec.type is TypeName.MESSAGES:
        return "list[Any]"
    if type_spec.type is TypeName.ARTIFACT_REF:
        return "str"
    return "Any"


def _type_needs_any(type_spec: TypeSpec) -> bool:
    if type_spec.type in {TypeName.ANY, TypeName.OBJECT, TypeName.MESSAGES}:
        return True
    if type_spec.type is TypeName.ARRAY:
        return type_spec.item_type is None or _type_needs_any(type_spec.item_type)
    return False


def _reducer_annotation(reducer: ReducerName) -> str:
    if reducer in {ReducerName.APPEND, ReducerName.SUM}:
        return "operator.add"
    if reducer is ReducerName.MERGE_DICT:
        return "_merge_dict"
    if reducer is ReducerName.ADD_MESSAGES:
        return "add_messages"
    raise ValueError(f'unsupported reducer "{reducer.value}"')


def _write_graph(generated: Path) -> None:
    text = '''"""Generated graph entrypoint for this workflow bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from prompt2langgraph.compiler.langgraph_py import compile_workflow_to_graph
from prompt2langgraph.ir.models import WorkflowSpec
from prompt2langgraph.registry.builtins import builtin_executor_registry


def load_workflow() -> WorkflowSpec:
    workflow_path = Path(__file__).resolve().parents[1] / "workflow.ir.json"
    data = json.loads(workflow_path.read_text(encoding="utf-8"))
    return WorkflowSpec.model_validate(data)


def build_graph():
    return compile_workflow_to_graph(load_workflow(), builtin_executor_registry())


def compile_graph():
    return build_graph()


def invoke_graph(input_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    workflow = load_workflow()
    graph = compile_workflow_to_graph(workflow, builtin_executor_registry())
    return graph.invoke(input_payload if input_payload is not None else sample_input(workflow))


def sample_input(workflow: WorkflowSpec | None = None) -> dict[str, Any]:
    selected = workflow or load_workflow()
    return {
        state_key: _sample_value(type_spec)
        for state_key, type_spec in selected.state_schema.input.items()
    }


def _sample_value(type_spec: Any) -> Any:
    type_name = type_spec.type.value
    if type_name in {"string", "artifact_ref", "any"}:
        return "sample"
    if type_name == "number":
        return 1.0
    if type_name == "integer":
        return 1
    if type_name == "boolean":
        return True
    if type_name == "array":
        return [_sample_value(type_spec.item_type)] if type_spec.item_type is not None else []
    if type_name == "object":
        return {}
    if type_name == "messages":
        return []
    return None


def _load_input(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f'input file "{path}" must contain a JSON object')
    return data


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run this generated LangGraph bundle.")
    parser.add_argument("--input", type=Path, help="JSON file containing workflow input state.")
    args = parser.parse_args(argv)
    input_payload = _load_input(args.input) if args.input is not None else None
    state = invoke_graph(input_payload)
    print(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
'''
    (generated / "graph.py").write_text(text, encoding="utf-8")
