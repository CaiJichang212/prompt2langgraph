import json
from pathlib import Path
from typing import Any

import pytest

from prompt2langgraph.ir.models import WorkflowSpec
from prompt2langgraph.runtime.artifacts import compile_workflow_to_artifacts


FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = Path(__file__).parent / "golden"

CASES = [
    "linear_llm",
    "conditional_human_gate",
    "loop_with_guard",
    "fanout_map_reduce",
]

JSON_ARTIFACTS = [
    "workflow.ir.json",
    "workflow.lock.json",
    "manifest.json",
    "compile_report.json",
]

TEXT_ARTIFACTS = [
    "graph.mmd",
]


@pytest.mark.parametrize("case_name", CASES)
def test_bundle_artifacts_match_golden_snapshots(case_name: str, tmp_path: Path) -> None:
    workflow = WorkflowSpec.model_validate(
        json.loads((FIXTURES / f"{case_name}.json").read_text(encoding="utf-8"))
    )

    report, bundle_dir = compile_workflow_to_artifacts(workflow, out_dir=tmp_path)

    assert report.ok, report.diagnostics
    assert bundle_dir.name == case_name
    for artifact in JSON_ARTIFACTS:
        assert _read_normalized_json(bundle_dir / artifact, artifact) == _read_normalized_json(
            GOLDEN / case_name / artifact,
            artifact,
        )
    for artifact in TEXT_ARTIFACTS:
        assert (bundle_dir / artifact).read_text(encoding="utf-8") == (
            GOLDEN / case_name / artifact
        ).read_text(encoding="utf-8")
    lock = json.loads((bundle_dir / "workflow.lock.json").read_text(encoding="utf-8"))
    for artifact in lock["generated_files"]:
        assert (bundle_dir / artifact).exists()


def _read_normalized_json(path: Path, artifact: str) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if artifact == "compile_report.json":
        assert "compile_id" in data
        assert "timings_ms" in data
        data["compile_id"] = "<compile_id>"
        data["timings_ms"] = "<timings_ms>"
    return data
