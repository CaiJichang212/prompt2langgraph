from __future__ import annotations

import json
from pathlib import Path

from prompt2langgraph.ir.models import WorkflowSpec


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
    (generated / "__init__.py").write_text('"""Generated prompt2langgraph bundle."""\n', encoding="utf-8")


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
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    text = (
        '"""Generated state metadata for this workflow bundle."""\n\n'
        "import json\n\n"
        f"STATE_SCHEMA = json.loads({payload_json!r})\n"
    )
    (generated / "state.py").write_text(text, encoding="utf-8")


def _write_nodes(workflow: WorkflowSpec, generated: Path) -> None:
    payload = [
        {"id": node.id, "kind": node.kind, "executor": node.executor.ref}
        for node in sorted(workflow.nodes, key=lambda item: item.id)
    ]
    text = (
        '"""Generated node metadata for this workflow bundle."""\n\n'
        "NODES = "
        + json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )
    (generated / "nodes.py").write_text(text, encoding="utf-8")


def _write_graph(generated: Path) -> None:
    text = '''"""Generated graph entrypoint for this workflow bundle."""

from __future__ import annotations

import json
from pathlib import Path

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
'''
    (generated / "graph.py").write_text(text, encoding="utf-8")
