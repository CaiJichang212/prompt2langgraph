import json
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from prompt2langgraph.cli import app


FIXTURES = Path(__file__).parent / "fixtures"


def test_validate_command_outputs_machine_readable_report() -> None:
    result = CliRunner().invoke(
        app,
        ["validate", str(FIXTURES / "linear_llm.json"), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["diagnostics"] == []


def test_validate_command_exits_nonzero_for_invalid_workflow() -> None:
    result = CliRunner().invoke(
        app,
        ["validate", str(FIXTURES / "invalid_unknown_node.json"), "--json"],
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert any(item["code"] == "E_DEP_004" for item in payload["diagnostics"])


def test_validate_command_reports_schema_errors_as_schema_diagnostics(tmp_path: Path) -> None:
    workflow_file = tmp_path / "missing_workflow_id.json"
    workflow_file.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "name": "Missing Workflow ID",
                "entrypoint": "compose",
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
                "nodes": [],
                "edges": [],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["validate", str(workflow_file), "--json"])

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert any(item["code"] == "E_SCHEMA_002" for item in payload["diagnostics"])


def test_compile_command_emits_expected_artifacts(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "compile",
            str(FIXTURES / "linear_llm.json"),
            "--target",
            "langgraph-py",
            "--out",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    build_dir = tmp_path / "linear_llm"
    assert payload["ok"] is True
    assert payload["output_dir"] == str(build_dir)
    assert (build_dir / "workflow.ir.json").exists()
    assert (build_dir / "workflow.lock.json").exists()
    assert (build_dir / "manifest.json").exists()
    assert (build_dir / "compile_report.json").exists()
    assert (build_dir / "graph.mmd").exists()


def test_run_command_invokes_workflow_with_input_file(tmp_path: Path) -> None:
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps({"question": "hello"}), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["run", str(FIXTURES / "linear_llm.json"), "--input", str(input_file), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "succeeded"
    assert payload["output"] == {"answer": "Answer: hello"}


def test_run_command_accepts_inline_json_input() -> None:
    result = CliRunner().invoke(
        app,
        ["run", str(FIXTURES / "linear_llm.json"), "--input", '{"question":"hello"}', "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "succeeded"
    assert payload["output"] == {"answer": "Answer: hello"}


def test_run_command_invokes_conditional_workflow_with_input_file(tmp_path: Path) -> None:
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps({"question": "hello", "confidence": 0.9}), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["run", str(FIXTURES / "conditional_human_gate.json"), "--input", str(input_file), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "succeeded"
    assert payload["output"] == {"answer": "Answer: hello"}


def test_graph_command_outputs_mermaid() -> None:
    result = CliRunner().invoke(
        app,
        ["graph", str(FIXTURES / "linear_llm.json"), "--format", "mermaid"],
    )

    assert result.exit_code == 0
    assert "flowchart LR" in result.stdout
    assert "START --> compose" in result.stdout


def test_cli_module_import_does_not_eagerly_import_langgraph() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import prompt2langgraph.cli; "
                "print(any(name.startswith('langgraph') for name in sys.modules))"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "False"
