from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from prompt2langgraph.cli import app
from prompt2langgraph.ir.lockfile import build_workflow_lock
from prompt2langgraph.ir.models import WorkflowSpec


def _write_tool_module(tmp_path: Path) -> None:
    module_path = tmp_path / "fake_cli_tools.py"
    module_path.write_text(
        """
def register_tools(registry):
    def upper(inputs, params):
        return {"answer": str(inputs["question"]).upper()}

    registry.register("fake.upper", upper)
""",
        encoding="utf-8",
    )


def _write_tool_ir(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "workflow_id": "tool_cli_smoke",
                "name": "Tool CLI Smoke",
                "entrypoint": "call_tool",
                "state_schema": {
                    "input": {"question": {"type": "string"}},
                    "output": {"answer": {"type": "string"}},
                    "channels": {
                        "question": {"type": "string"},
                        "answer": {"type": "string"},
                    },
                    "private": {},
                    "reducers": {},
                },
                "nodes": [
                    {
                        "id": "call_tool",
                        "kind": "tool",
                        "executor": {"ref": "fake.upper", "type": "python_callable"},
                        "inputs": {"question": {"state_key": "question"}},
                        "outputs": {"answer": {"state_key": "answer"}},
                        "params": {},
                    }
                ],
                "edges": [],
                "policies": {"allowed_tool_refs": ["fake.upper"]},
                "metadata": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_tool_bundle(tmp_path: Path, workflow_path: Path) -> Path:
    workflow = WorkflowSpec.model_validate(json.loads(workflow_path.read_text(encoding="utf-8")))
    bundle_dir = tmp_path / workflow.workflow_id
    bundle_dir.mkdir()
    (bundle_dir / "workflow.ir.json").write_text(
        workflow.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (bundle_dir / "workflow.lock.json").write_text(
        json.dumps(build_workflow_lock(workflow), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return bundle_dir / "workflow.lock.json"


def _write_tool_json_plan(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "name": "Tool Plan Smoke",
                "workflow_id": "tool_plan_smoke",
                "inputs": {"question": "string"},
                "outputs": {"answer": "string"},
                "nodes": [
                    {
                        "id": "call_tool",
                        "kind": "tool",
                        "executor": "fake.upper",
                        "inputs": {"question": "question"},
                        "outputs": {"answer": "answer"},
                    }
                ],
                "edges": [],
                "policies": {"allowed_tool_refs": ["fake.upper"]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_human_then_tool_ir(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "workflow_id": "human_then_tool",
                "name": "Human Then Tool",
                "entrypoint": "approve",
                "state_schema": {
                    "input": {"question": {"type": "string"}},
                    "output": {"answer": {"type": "string"}},
                    "channels": {
                        "question": {"type": "string"},
                        "approval": {"type": "string"},
                        "answer": {"type": "string"},
                    },
                    "private": {},
                    "reducers": {},
                },
                "nodes": [
                    {
                        "id": "approve",
                        "kind": "human_gate",
                        "executor": {"ref": "builtin.human_gate", "type": "builtin"},
                        "inputs": {},
                        "outputs": {"approval": {"state_key": "approval"}},
                        "params": {"message": "Approve tool call?"},
                    },
                    {
                        "id": "call_tool",
                        "kind": "tool",
                        "executor": {"ref": "fake.upper", "type": "python_callable"},
                        "inputs": {"question": {"state_key": "question"}},
                        "outputs": {"answer": {"state_key": "answer"}},
                        "params": {},
                    },
                ],
                "edges": [
                    {
                        "id": "approve_to_tool",
                        "source": "approve",
                        "target": "call_tool",
                        "kind": "linear",
                    }
                ],
                "policies": {"allowed_tool_refs": ["fake.upper"]},
                "metadata": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_cli_run_loads_tool_module_for_workflow_ir(tmp_path: Path, monkeypatch) -> None:
    _write_tool_module(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    workflow_path = tmp_path / "tool_workflow.json"
    _write_tool_ir(workflow_path)
    input_path = tmp_path / "input.json"
    input_path.write_text('{"question":"hello"}', encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "run",
            str(workflow_path),
            "--input",
            str(input_path),
            "--tool-module",
            "fake_cli_tools",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "succeeded"
    assert payload["output"] == {"answer": "HELLO"}


def test_cli_run_loads_tool_module_for_workflow_lock_json(tmp_path: Path, monkeypatch) -> None:
    _write_tool_module(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    workflow_path = tmp_path / "tool_workflow.json"
    _write_tool_ir(workflow_path)
    lockfile = _write_tool_bundle(tmp_path, workflow_path)
    input_path = tmp_path / "input.json"
    input_path.write_text('{"question":"hello"}', encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "run",
            str(lockfile),
            "--input",
            str(input_path),
            "--tool-module",
            "fake_cli_tools",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "succeeded"
    assert payload["output"] == {"answer": "HELLO"}


def test_cli_run_loads_tool_module_before_json_plan_adapter(tmp_path: Path, monkeypatch) -> None:
    _write_tool_module(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    plan_path = tmp_path / "tool_plan.json"
    _write_tool_json_plan(plan_path)
    input_path = tmp_path / "input.json"
    input_path.write_text('{"question":"hello"}', encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "run",
            str(plan_path),
            "--input",
            str(input_path),
            "--tool-module",
            "fake_cli_tools",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "succeeded"
    assert payload["output"] == {"answer": "HELLO"}


def test_cli_compile_loads_tool_module_before_json_plan_adapter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_tool_module(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    plan_path = tmp_path / "tool_plan.json"
    _write_tool_json_plan(plan_path)

    result = CliRunner().invoke(
        app,
        [
            "compile",
            str(plan_path),
            "--tool-module",
            "fake_cli_tools",
            "--out",
            str(tmp_path / "build"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    bundle_dir = tmp_path / "build" / "tool_plan_smoke"
    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["executor_bindings"]["call_tool"]["executor"] == "fake.upper"
    assert manifest["executor_bindings"]["call_tool"]["type"] == "python_callable"
    assert manifest["runtime_requirements"]["tool_refs"] == ["fake.upper"]
    assert (bundle_dir / "generated" / "graph.py").exists()


def test_cli_compile_with_tool_module_rejects_unauthorized_tool_ref(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_tool_module(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    plan_path = tmp_path / "unauthorized_tool_plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "name": "Unauthorized Tool Plan",
                "workflow_id": "unauthorized_tool_plan",
                "inputs": {"question": "string"},
                "outputs": {"answer": "string"},
                "nodes": [
                    {
                        "id": "call_tool",
                        "kind": "tool",
                        "executor": "fake.upper",
                        "inputs": {"question": "question"},
                        "outputs": {"answer": "answer"},
                    }
                ],
                "edges": [],
                "policies": {"allowed_tool_refs": []},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "compile",
            str(plan_path),
            "--tool-module",
            "fake_cli_tools",
            "--out",
            str(tmp_path / "build"),
            "--json",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert any(
        item["code"] == "E_SEC_015" and "fake.upper" in item["message"]
        for item in payload["diagnostics"]
    )
    assert "Traceback" not in result.stdout


def test_cli_compile_reports_tool_module_without_register_tools(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module_path = tmp_path / "bad_cli_tools.py"
    module_path.write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    plan_path = tmp_path / "tool_plan.json"
    _write_tool_json_plan(plan_path)

    result = CliRunner().invoke(
        app,
        [
            "compile",
            str(plan_path),
            "--tool-module",
            "bad_cli_tools",
            "--out",
            str(tmp_path / "build"),
            "--json",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["diagnostics"][0]["code"] == "E_RUNTIME_010"
    assert "register_tools" in payload["diagnostics"][0]["message"]
    assert "Traceback" not in result.stdout


def test_cli_run_without_tool_module_fails_for_python_callable_ir(tmp_path: Path) -> None:
    workflow_path = tmp_path / "tool_workflow.json"
    _write_tool_ir(workflow_path)
    input_path = tmp_path / "input.json"
    input_path.write_text('{"question":"hello"}', encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["run", str(workflow_path), "--input", str(input_path), "--json"],
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert any(
        item["code"] in {"E_BIND_006", "E_SEC_015"} and "fake.upper" in item["message"]
        for item in payload["diagnostics"]
    )
    assert "Traceback" not in result.stdout


def test_cli_run_reports_tool_module_without_register_tools(tmp_path: Path, monkeypatch) -> None:
    module_path = tmp_path / "bad_cli_tools.py"
    module_path.write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    workflow_path = tmp_path / "tool_workflow.json"
    _write_tool_ir(workflow_path)
    input_path = tmp_path / "input.json"
    input_path.write_text('{"question":"hello"}', encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "run",
            str(workflow_path),
            "--input",
            str(input_path),
            "--tool-module",
            "bad_cli_tools",
            "--json",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert payload["diagnostics"][0]["code"] == "E_RUNTIME_010"
    assert "register_tools" in payload["diagnostics"][0]["message"]
    assert "Traceback" not in result.stdout


def test_cli_run_reports_duplicate_tool_ref_from_modules(tmp_path: Path, monkeypatch) -> None:
    _write_tool_module(tmp_path)
    duplicate_path = tmp_path / "duplicate_cli_tools.py"
    duplicate_path.write_text(
        """
def register_tools(registry):
    registry.register("fake.upper", lambda inputs, params: {"answer": "duplicate"})
""",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    workflow_path = tmp_path / "tool_workflow.json"
    _write_tool_ir(workflow_path)
    input_path = tmp_path / "input.json"
    input_path.write_text('{"question":"hello"}', encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "run",
            str(workflow_path),
            "--input",
            str(input_path),
            "--tool-module",
            "fake_cli_tools",
            "--tool-module",
            "duplicate_cli_tools",
            "--json",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert payload["diagnostics"][0]["code"] == "E_RUNTIME_010"
    assert "already registered" in payload["diagnostics"][0]["hint"]
    assert "Traceback" not in result.stdout


def test_cli_run_rejects_tool_ref_that_overrides_builtin_executor(
    tmp_path: Path, monkeypatch
) -> None:
    module_path = tmp_path / "shadow_cli_tools.py"
    module_path.write_text(
        """
def register_tools(registry):
    registry.register("builtin.echo_llm", lambda inputs, params: {"answer": "shadowed"})
""",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    workflow_path = tmp_path / "tool_workflow.json"
    _write_tool_ir(workflow_path)
    input_path = tmp_path / "input.json"
    input_path.write_text('{"question":"hello"}', encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "run",
            str(workflow_path),
            "--input",
            str(input_path),
            "--tool-module",
            "shadow_cli_tools",
            "--json",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert payload["diagnostics"][0]["code"] == "E_RUNTIME_010"
    assert "cannot override" in payload["diagnostics"][0]["message"]
    assert "builtin.echo_llm" in payload["diagnostics"][0]["message"]
    assert "Traceback" not in result.stdout


def test_cli_resume_uses_tool_module_after_interrupt(tmp_path: Path, monkeypatch) -> None:
    _write_tool_module(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    workflow_path = tmp_path / "human_then_tool.json"
    _write_human_then_tool_ir(workflow_path)

    waiting_result = CliRunner().invoke(
        app,
        [
            "run",
            str(workflow_path),
            "--input",
            '{"question":"hello"}',
            "--tool-module",
            "fake_cli_tools",
            "--json",
        ],
    )
    assert waiting_result.exit_code != 0
    waiting = json.loads(waiting_result.stdout)
    assert waiting["status"] == "waiting"

    resume_result = CliRunner().invoke(
        app,
        [
            "resume",
            str(workflow_path),
            "--thread-id",
            waiting["thread_id"],
            "--resume",
            '"approved"',
            "--tool-module",
            "fake_cli_tools",
            "--json",
        ],
    )

    assert resume_result.exit_code == 0, resume_result.output
    resumed = json.loads(resume_result.stdout)
    assert resumed["status"] == "succeeded"
    assert resumed["output"] == {"answer": "HELLO"}


def test_cli_resume_uses_tool_module_from_workflow_lock_json(tmp_path: Path, monkeypatch) -> None:
    _write_tool_module(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    workflow_path = tmp_path / "human_then_tool.json"
    _write_human_then_tool_ir(workflow_path)
    lockfile = _write_tool_bundle(tmp_path, workflow_path)

    waiting_result = CliRunner().invoke(
        app,
        [
            "run",
            str(lockfile),
            "--input",
            '{"question":"hello"}',
            "--tool-module",
            "fake_cli_tools",
            "--json",
        ],
    )
    assert waiting_result.exit_code != 0
    waiting = json.loads(waiting_result.stdout)
    assert waiting["status"] == "waiting"

    resume_result = CliRunner().invoke(
        app,
        [
            "resume",
            str(lockfile),
            "--thread-id",
            waiting["thread_id"],
            "--resume",
            '"approved"',
            "--tool-module",
            "fake_cli_tools",
            "--json",
        ],
    )

    assert resume_result.exit_code == 0, resume_result.output
    resumed = json.loads(resume_result.stdout)
    assert resumed["status"] == "succeeded"
    assert resumed["output"] == {"answer": "HELLO"}


def test_build_runtime_clients_rejects_executor_registry_diagnostics() -> None:
    from prompt2langgraph.cli import _build_runtime_clients
    from prompt2langgraph.registry.tool_executor import ToolCallableRegistry

    workflow = WorkflowSpec.model_validate(
        {
            "schema_version": "0.1",
            "workflow_id": "shadow_runtime_clients",
            "name": "Shadow Runtime Clients",
            "entrypoint": "call_tool",
            "state_schema": {
                "input": {"question": {"type": "string"}},
                "output": {"answer": {"type": "string"}},
                "channels": {
                    "question": {"type": "string"},
                    "answer": {"type": "string"},
                },
                "private": {},
                "reducers": {},
            },
            "nodes": [
                {
                    "id": "call_tool",
                    "kind": "tool",
                    "executor": {"ref": "builtin.echo_llm", "type": "python_callable"},
                    "inputs": {"question": {"state_key": "question"}},
                    "outputs": {"answer": {"state_key": "answer"}},
                    "params": {},
                }
            ],
            "edges": [],
            "policies": {"allowed_tool_refs": ["builtin.echo_llm"]},
            "metadata": {},
        }
    )
    tools = ToolCallableRegistry()
    tools.register("builtin.echo_llm", lambda inputs, params: {"answer": "shadowed"})

    try:
        _build_runtime_clients(workflow, loaded_tool_registry=tools)
    except RuntimeError as exc:
        assert "cannot override" in str(exc)
    else:
        raise AssertionError("_build_runtime_clients accepted a diagnostic registry")
