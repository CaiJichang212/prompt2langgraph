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
    assert payload["diagnostics"][0]["location"]["source"] == str(workflow_file)
    assert payload["diagnostics"][0]["location"]["path"] == "workflow_id"


def test_validate_command_reports_json_plan_parse_errors_as_diagnostics(tmp_path: Path) -> None:
    bad_plans = [
        {"name": "Missing Nodes", "edges": []},
        {"name": "Bad Nodes", "nodes": "not-a-list", "edges": []},
        {
            "name": "Bad Edge",
            "nodes": [{"id": "first", "kind": "llm", "executor": "builtin.echo_llm"}],
            "edges": [{"id": "missing_endpoint", "from": "first"}],
        },
        {
            "name": "Non Object Edge",
            "nodes": [{"id": "first", "kind": "llm", "executor": "builtin.echo_llm"}],
            "edges": ["not-an-object"],
        },
    ]

    for index, plan in enumerate(bad_plans):
        plan_file = tmp_path / f"bad_plan_{index}.json"
        plan_file.write_text(json.dumps(plan), encoding="utf-8")

        result = CliRunner().invoke(app, ["validate", str(plan_file), "--json"])

        assert result.exit_code != 0
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert any(item["code"] == "E_PARSE_001" for item in payload["diagnostics"])
        assert payload["diagnostics"][0]["location"]["source"] == str(plan_file)
        assert "Traceback" not in result.stdout


def test_validate_command_reports_json_plan_parse_error_path(tmp_path: Path) -> None:
    plan_file = tmp_path / "bad_edge.json"
    plan_file.write_text(
        json.dumps(
            {
                "name": "Bad Edge",
                "nodes": [{"id": "first", "kind": "llm", "executor": "builtin.echo_llm"}],
                "edges": [{"id": "missing_target", "from": "first"}],
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["validate", str(plan_file), "--json"])

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    diagnostic = payload["diagnostics"][0]
    assert diagnostic["code"] == "E_PARSE_001"
    assert diagnostic["location"]["source"] == str(plan_file)
    assert diagnostic["location"]["path"] == "edges[0].to"
    assert diagnostic["location"]["line"] is None
    assert diagnostic["location"]["column"] is None
    assert "Traceback" not in result.stdout


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

    report = json.loads((build_dir / "compile_report.json").read_text(encoding="utf-8"))
    manifest = json.loads((build_dir / "manifest.json").read_text(encoding="utf-8"))

    assert report["compile_id"].startswith("compile_")
    assert {
        "normalize",
        "validate",
        "resolve_policies",
        "bind_workflow",
        "target_compile",
        "artifact_write",
        "total",
    }.issubset(set(report["timings_ms"]))
    assert "binding_summary" in report
    assert (
        report["binding_summary"]["executor_bindings"]["compose"]["executor"] == "builtin.echo_llm"
    )
    assert "policy_summary" in manifest
    assert manifest["policy_summary"]["node_policies"]["compose"]["timeout_s"] == 60


def test_compile_command_reports_unsupported_target_as_json_without_traceback(
    tmp_path: Path,
) -> None:
    result = CliRunner().invoke(
        app,
        [
            "compile",
            str(FIXTURES / "linear_llm.json"),
            "--target",
            "not-a-target",
            "--out",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert any(item["code"] == "E_TARGET_009" for item in payload["diagnostics"])
    assert "Traceback" not in result.stdout


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
        [
            "run",
            str(FIXTURES / "conditional_human_gate.json"),
            "--input",
            str(input_file),
            "--json",
        ],
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


def test_cli_help_lists_core_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in ["validate", "compile", "run", "resume", "graph", "plan"]:
        assert command in result.stdout


def test_compile_command_emits_generated_bundle_files(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        [
            "compile",
            str(FIXTURES / "linear_llm.json"),
            "--out",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    build_dir = tmp_path / "linear_llm"
    for generated_file in [
        build_dir / "generated" / "state.py",
        build_dir / "generated" / "nodes.py",
        build_dir / "generated" / "graph.py",
    ]:
        assert generated_file.exists()
        source = generated_file.read_text(encoding="utf-8")
        assert source.strip()
        compile(source, str(generated_file), "exec")


def test_run_command_accepts_workflow_lock_json_after_compile(tmp_path: Path) -> None:
    compile_result = CliRunner().invoke(
        app,
        ["compile", str(FIXTURES / "linear_llm.json"), "--out", str(tmp_path), "--json"],
    )
    assert compile_result.exit_code == 0

    lockfile = tmp_path / "linear_llm" / "workflow.lock.json"
    run_result = CliRunner().invoke(
        app,
        ["run", str(lockfile), "--input", '{"question":"hello"}', "--json"],
    )

    assert run_result.exit_code == 0
    payload = json.loads(run_result.stdout)
    assert payload["status"] == "succeeded"
    assert payload["output"] == {"answer": "Answer: hello"}


def test_graph_command_accepts_workflow_lock_json_after_compile(tmp_path: Path) -> None:
    compile_result = CliRunner().invoke(
        app,
        ["compile", str(FIXTURES / "linear_llm.json"), "--out", str(tmp_path), "--json"],
    )
    assert compile_result.exit_code == 0

    lockfile = tmp_path / "linear_llm" / "workflow.lock.json"
    graph_result = CliRunner().invoke(
        app,
        ["graph", str(lockfile), "--format", "mermaid", "--json"],
    )

    assert graph_result.exit_code == 0
    payload = json.loads(graph_result.stdout)
    assert payload["format"] == "mermaid"
    assert "START --> compose" in payload["graph"]


def test_resume_command_continues_pending_interrupt_from_lockfile(tmp_path: Path) -> None:
    compile_result = CliRunner().invoke(
        app,
        [
            "compile",
            str(FIXTURES / "conditional_human_gate.json"),
            "--out",
            str(tmp_path),
            "--json",
        ],
    )
    assert compile_result.exit_code == 0
    lockfile = tmp_path / "conditional_human_gate" / "workflow.lock.json"

    waiting_result = CliRunner().invoke(
        app,
        ["run", str(lockfile), "--input", '{"question":"hello","confidence":0.5}', "--json"],
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
            "--json",
        ],
    )

    assert resume_result.exit_code == 0
    resumed = json.loads(resume_result.stdout)
    assert resumed["status"] == "succeeded"
    assert resumed["output"] == {"answer": "Answer: hello"}


def test_resume_command_accepts_json_null_payload_from_lockfile(tmp_path: Path) -> None:
    compile_result = CliRunner().invoke(
        app,
        [
            "compile",
            str(FIXTURES / "conditional_human_gate.json"),
            "--out",
            str(tmp_path),
            "--json",
        ],
    )
    assert compile_result.exit_code == 0
    lockfile = tmp_path / "conditional_human_gate" / "workflow.lock.json"

    waiting_result = CliRunner().invoke(
        app,
        ["run", str(lockfile), "--input", '{"question":"hello","confidence":0.5}', "--json"],
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
            "null",
            "--json",
        ],
    )

    assert resume_result.exit_code != 0
    resumed = json.loads(resume_result.stdout)
    assert resumed["status"] == "failed"
    assert any(event["type"] == "run.resumed" for event in resumed["events"])
    assert not any(
        item["code"] == "E_SCHEMA_002"
        and 'required input state key "question" is missing' in item["message"]
        for item in resumed["diagnostics"]
    )


def test_prompt_plan_command_emits_json_plan_payload(monkeypatch) -> None:
    class FakeModel:
        def invoke(self, messages):
            return type(
                "Response",
                (),
                {
                    "content": (
                        '{"name":"Demo",'
                        '"nodes":[{"id":"compose","kind":"llm",'
                        '"executor":"builtin.echo_llm"}],"edges":[]}'
                    )
                },
            )()

    def fake_build_model_client(request):
        return FakeModel()

    monkeypatch.setattr(
        "prompt2langgraph.prompting.planner.build_model_client",
        fake_build_model_client,
    )

    result = CliRunner().invoke(
        app,
        ["plan", "--prompt", "build a simple workflow", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["plan"]["name"] == "Demo"


def test_prompt_plan_command_reports_parse_failure_as_json(monkeypatch) -> None:
    class FakeModel:
        def invoke(self, messages):
            return type("Response", (), {"content": "[1,2,3]"})()

    def fake_build_model_client(request):
        return FakeModel()

    monkeypatch.setattr(
        "prompt2langgraph.prompting.planner.build_model_client",
        fake_build_model_client,
    )

    result = CliRunner().invoke(
        app,
        ["plan", "--prompt", "bad workflow", "--json"],
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert any(item["code"] == "E_PARSE_001" for item in payload["diagnostics"])


def test_prompt_plan_command_reports_json_decode_failure_as_diagnostic(monkeypatch) -> None:
    class FakeModel:
        def invoke(self, messages):
            return type("Response", (), {"content": "not valid json at all"})()

    def fake_build_model_client(request):
        return FakeModel()

    monkeypatch.setattr(
        "prompt2langgraph.prompting.planner.build_model_client",
        fake_build_model_client,
    )

    result = CliRunner().invoke(
        app,
        ["plan", "--prompt", "broken output", "--json"],
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert any(item["code"] == "E_PARSE_001" for item in payload["diagnostics"])


def test_prompt_plan_command_reports_llm_call_failure_as_diagnostic(monkeypatch) -> None:
    def fake_build_model_client(request):
        class FakeModel:
            def invoke(self, messages):
                raise RuntimeError("connection refused")

        return FakeModel()

    monkeypatch.setattr(
        "prompt2langgraph.prompting.planner.build_model_client",
        fake_build_model_client,
    )

    result = CliRunner().invoke(
        app,
        ["plan", "--prompt", "trigger llm error", "--json"],
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert any(item["code"] == "E_RUNTIME_010" for item in payload["diagnostics"])
    assert "Traceback" not in result.stdout


def test_prompt_plan_command_passes_temperature_to_request(monkeypatch) -> None:
    captured_temperature = None

    class FakeModel:
        def invoke(self, messages):
            return type(
                "Response",
                (),
                {
                    "content": (
                        '{"name":"Demo",'
                        '"nodes":[{"id":"compose","kind":"llm",'
                        '"executor":"builtin.echo_llm"}],"edges":[]}'
                    )
                },
            )()

    def fake_build_model_client(request):
        nonlocal captured_temperature
        captured_temperature = request.temperature
        return FakeModel()

    monkeypatch.setattr(
        "prompt2langgraph.prompting.planner.build_model_client",
        fake_build_model_client,
    )

    result = CliRunner().invoke(
        app,
        ["plan", "--prompt", "build a simple workflow", "--temperature", "0.7", "--json"],
    )

    assert result.exit_code == 0
    assert captured_temperature == 0.7


def test_prompt_plan_command_validate_flag_includes_validation_result(monkeypatch) -> None:
    class FakeModel:
        def invoke(self, messages):
            return type(
                "Response",
                (),
                {
                    "content": (
                        '{"name":"Demo",'
                        '"nodes":[{"id":"compose","kind":"llm",'
                        '"executor":"builtin.echo_llm"}],"edges":[]}'
                    )
                },
            )()

    def fake_build_model_client(request):
        return FakeModel()

    monkeypatch.setattr(
        "prompt2langgraph.prompting.planner.build_model_client",
        fake_build_model_client,
    )

    result = CliRunner().invoke(
        app,
        ["plan", "--prompt", "build a simple workflow", "--validate", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert "validation" in payload
    assert payload["validation"]["ok"] is True


def test_prompt_plan_command_validate_flag_reports_invalid_plan(monkeypatch) -> None:
    class FakeModel:
        def invoke(self, messages):
            return type(
                "Response",
                (),
                {
                    "content": (
                        '{"name":"Bad",'
                        '"nodes":[{"id":"n1","kind":"llm",'
                        '"executor":"builtin.nonexistent"}],"edges":[]}'
                    )
                },
            )()

    def fake_build_model_client(request):
        return FakeModel()

    monkeypatch.setattr(
        "prompt2langgraph.prompting.planner.build_model_client",
        fake_build_model_client,
    )

    result = CliRunner().invoke(
        app,
        ["plan", "--prompt", "build a bad workflow", "--validate", "--json"],
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert "validation" in payload
    assert payload["validation"]["ok"] is False


def test_prompt_plan_command_validate_flag_reports_adapter_parse_error(monkeypatch) -> None:
    class FakeModel:
        def invoke(self, messages):
            return type(
                "Response",
                (),
                {
                    "content": (
                        '{"name":"BadEdge",'
                        '"nodes":[{"id":"n1","kind":"llm","executor":"builtin.echo_llm"}],'
                        '"edges":[{"from":"n1"}]}'
                    )
                },
            )()

    def fake_build_model_client(request):
        return FakeModel()

    monkeypatch.setattr(
        "prompt2langgraph.prompting.planner.build_model_client",
        fake_build_model_client,
    )

    result = CliRunner().invoke(
        app,
        ["plan", "--prompt", "build a workflow with bad edge", "--validate", "--json"],
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert "validation" in payload
    assert payload["validation"]["ok"] is False
    assert any(item["code"] == "E_PARSE_001" for item in payload["validation"]["diagnostics"])


def test_resume_command_continues_pending_interrupt_across_processes(tmp_path: Path) -> None:
    compile_result = CliRunner().invoke(
        app,
        [
            "compile",
            str(FIXTURES / "conditional_human_gate.json"),
            "--out",
            str(tmp_path),
            "--json",
        ],
    )
    assert compile_result.exit_code == 0
    lockfile = tmp_path / "conditional_human_gate" / "workflow.lock.json"

    waiting_result = subprocess.run(
        [
            "uv",
            "run",
            "pt2lg",
            "run",
            str(lockfile),
            "--input",
            '{"question":"hello","confidence":0.5}',
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert waiting_result.returncode != 0
    waiting = json.loads(waiting_result.stdout)
    assert waiting["status"] == "waiting"
    state_store = lockfile.parent / ".pt2lg-runtime"
    assert list(state_store.glob("*.json"))

    resume_result = subprocess.run(
        [
            "uv",
            "run",
            "pt2lg",
            "resume",
            str(lockfile),
            "--thread-id",
            waiting["thread_id"],
            "--resume",
            '"approved"',
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert resume_result.returncode == 0
    resumed = json.loads(resume_result.stdout)
    assert resumed["status"] == "succeeded"
    assert resumed["output"] == {"answer": "Answer: hello"}
    assert list(state_store.glob("*.json")) == []
