import json
import subprocess
import sys
from pathlib import Path

import pytest

import prompt2langgraph as pt2lg

EXAMPLES = Path(__file__).parent / "examples"

VALID_EXAMPLE_INPUTS = [
    (
        "linear_research",
        "input.json",
        {
            "docs_ref": "mock://retriever/summarize vector search",
            "answer": "Research answer from mock://retriever/summarize vector search",
        },
    ),
    (
        "conditional_human_gate",
        "input_high_confidence.json",
        {"answer": "Answer: hello"},
    ),
    ("fanout_map_reduce", "input.json", {"results": ["alpha", "beta", "gamma"]}),
]


def load_workflow(path: Path) -> pt2lg.WorkflowSpec:
    return pt2lg.WorkflowSpec.model_validate(json.loads(path.read_text(encoding="utf-8")))


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_linear_research_example_validates_and_runs() -> None:
    workflow = load_workflow(EXAMPLES / "linear_research" / "workflow.json")
    input_payload = load_json(EXAMPLES / "linear_research" / "input.json")

    report = pt2lg.validate_workflow(workflow)
    result = pt2lg.run_workflow(workflow, input_payload)

    assert report.ok is True
    assert result.status == "succeeded"
    assert result.output == {
        "docs_ref": "mock://retriever/summarize vector search",
        "answer": "Research answer from mock://retriever/summarize vector search",
    }


def test_conditional_human_gate_example_covers_direct_and_waiting_paths() -> None:
    workflow = load_workflow(EXAMPLES / "conditional_human_gate" / "workflow.json")
    high_confidence = load_json(EXAMPLES / "conditional_human_gate" / "input_high_confidence.json")
    low_confidence = load_json(EXAMPLES / "conditional_human_gate" / "input_low_confidence.json")
    resume_payload = load_json(EXAMPLES / "conditional_human_gate" / "resume_approved.json")

    direct = pt2lg.run_workflow(workflow, high_confidence)
    waiting = pt2lg.run_workflow(workflow, low_confidence)
    resumed = pt2lg.run_workflow(
        workflow, {}, thread_id=waiting.thread_id, resume_payload=resume_payload
    )

    assert direct.status == "succeeded"
    assert direct.output == {"answer": "Answer: hello"}
    assert waiting.status == "waiting"
    assert waiting.interrupt is not None
    assert resumed.status == "succeeded"
    assert resumed.thread_id == waiting.thread_id
    assert resumed.output == {"answer": "Answer: hello"}


def test_fanout_map_reduce_example_validates_runs_and_compiles(tmp_path: Path) -> None:
    workflow = load_workflow(EXAMPLES / "fanout_map_reduce" / "workflow.json")
    input_payload = load_json(EXAMPLES / "fanout_map_reduce" / "input.json")

    report = pt2lg.validate_workflow(workflow)
    result = pt2lg.run_workflow(workflow, input_payload)
    compile_result = pt2lg.compile_workflow(workflow, out_dir=tmp_path)

    assert report.ok is True
    assert result.status == "succeeded"
    assert sorted(result.output["results"]) == ["alpha", "beta", "gamma"]
    assert compile_result.ok is True
    assert (compile_result.output_dir / "workflow.lock.json").exists()


@pytest.mark.parametrize(("example_name", "input_name", "expected_output"), VALID_EXAMPLE_INPUTS)
def test_valid_examples_compile_to_executable_generated_graph(
    tmp_path: Path,
    example_name: str,
    input_name: str,
    expected_output: dict[str, object],
) -> None:
    workflow = load_workflow(EXAMPLES / example_name / "workflow.json")
    input_path = EXAMPLES / example_name / input_name

    compile_result = pt2lg.compile_workflow(workflow, out_dir=tmp_path)
    script_path = compile_result.output_dir / "generated" / "graph.py"

    assert compile_result.ok is True
    completed = subprocess.run(
        [sys.executable, str(script_path), "--input", str(input_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    state = json.loads(completed.stdout)

    for key, value in expected_output.items():
        if isinstance(value, list):
            assert sorted(state[key]) == sorted(value)
        else:
            assert state[key] == value


def test_generated_graph_script_without_input_uses_schema_sample(
    tmp_path: Path,
) -> None:
    workflow = load_workflow(EXAMPLES / "conditional_human_gate" / "workflow.json")
    compile_result = pt2lg.compile_workflow(workflow, out_dir=tmp_path)
    script_path = compile_result.output_dir / "generated" / "graph.py"

    completed = subprocess.run(
        [sys.executable, str(script_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    state = json.loads(completed.stdout)

    assert state["confidence"] == 1.0
    assert state["answer"] == "Answer: sample"


@pytest.mark.parametrize(
    ("filename", "expected_code"),
    [
        ("unknown_node.json", "E_DEP_004"),
        ("type_mismatch.json", "E_TYPE_003"),
    ],
)
def test_invalid_examples_return_expected_validation_diagnostics(
    filename: str, expected_code: str
) -> None:
    workflow = load_json(EXAMPLES / "invalid" / filename)

    report = pt2lg.validate_workflow(workflow)

    assert report.ok is False
    assert any(diagnostic.code == expected_code for diagnostic in report.diagnostics)


def test_invalid_join_edge_example_is_rejected_by_compile_target(
    tmp_path: Path,
) -> None:
    workflow = load_workflow(EXAMPLES / "invalid" / "join_edge.json")

    result = pt2lg.compile_workflow(workflow, out_dir=tmp_path)

    assert result.ok is False
    assert any(diagnostic["code"] == "E_TARGET_009" for diagnostic in result.diagnostics)
    assert not (result.output_dir / "workflow.lock.json").exists()
