import json
from pathlib import Path

import prompt2langgraph as pt2lg

FIXTURES = Path(__file__).parent / "fixtures"


def test_public_api_exports_core_functions() -> None:
    workflow = pt2lg.WorkflowSpec.model_validate(
        json.loads((FIXTURES / "linear_llm.json").read_text(encoding="utf-8"))
    )

    report = pt2lg.validate_workflow(workflow)
    result = pt2lg.run_workflow(workflow, {"question": "hello"})

    assert report.ok is True
    assert result.status == "succeeded"
    assert result.output == {"answer": "Answer: hello"}
    assert "CompileResult" in pt2lg.__all__
    assert "compile_workflow" in pt2lg.__all__


def test_public_compile_workflow_returns_compile_result(tmp_path: Path) -> None:
    workflow = pt2lg.WorkflowSpec.model_validate(
        json.loads((FIXTURES / "linear_llm.json").read_text(encoding="utf-8"))
    )

    result = pt2lg.compile_workflow(workflow, out_dir=tmp_path)

    assert result.ok is True
    assert result.output_dir == tmp_path / "linear_llm"
    assert (result.output_dir / "workflow.lock.json").exists()

    report = json.loads((result.output_dir / "compile_report.json").read_text(encoding="utf-8"))
    manifest = json.loads((result.output_dir / "manifest.json").read_text(encoding="utf-8"))

    assert report["compile_id"].startswith("compile_")
    assert "target_compile" in report["timings_ms"]
    assert "binding_summary" in report
    assert "policy_summary" in manifest


def test_public_compile_workflow_rejects_langgraph_compile_failures(tmp_path: Path) -> None:
    data = json.loads((FIXTURES / "linear_llm.json").read_text(encoding="utf-8"))
    data["nodes"].append(
        {
            "id": "finish",
            "kind": "transform",
            "executor": {"ref": "builtin.identity_transform", "type": "builtin"},
            "inputs": {"value": {"state_key": "answer"}},
            "outputs": {"value": {"state_key": "answer"}},
            "params": {},
        }
    )
    data["edges"] = [
        {"id": "unsupported_join", "source": "compose", "target": "finish", "kind": "join"}
    ]
    workflow = pt2lg.WorkflowSpec.model_validate(data)

    result = pt2lg.compile_workflow(workflow, out_dir=tmp_path)

    assert result.ok is False
    assert not (result.output_dir / "workflow.lock.json").exists()
    assert any(item["code"] == "E_TARGET_009" for item in result.diagnostics)


class _FakeModel:
    def invoke(self, messages):
        return type(
            "Response",
            (),
            {
                "content": (
                    '{"name":"Demo","inputs":{"question":"string"},'
                    '"outputs":{"answer":"string"},'
                    '"nodes":[{"id":"compose","kind":"llm","executor":"builtin.echo_llm"}],'
                    '"edges":[]}'
                )
            },
        )()


def test_public_api_exports_prompt_planning_entrypoints() -> None:
    request = pt2lg.PromptPlanRequest(prompt="answer a question")
    workflow = pt2lg.plan_prompt_to_workflow_spec(request, model_client=_FakeModel())

    assert workflow.workflow_id == "demo"
    assert "PromptPlanRequest" in pt2lg.__all__
    assert "PromptPlanResult" in pt2lg.__all__
    assert "plan_prompt_to_workflow_spec" in pt2lg.__all__


def test_public_prompt_workflow_can_be_validated() -> None:
    workflow = pt2lg.plan_prompt_to_workflow_spec(
        pt2lg.PromptPlanRequest(prompt="answer a question"),
        model_client=_FakeModel(),
    )
    report = pt2lg.validate_workflow(workflow)

    assert report.ok is True
