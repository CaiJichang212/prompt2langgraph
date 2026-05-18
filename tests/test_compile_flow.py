import json
from pathlib import Path

import prompt2langgraph as pt2lg


FIXTURES = Path(__file__).parent / "fixtures"


def load_workflow(name: str) -> pt2lg.WorkflowSpec:
    return pt2lg.WorkflowSpec.model_validate(
        json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    )


def test_compile_flow_emits_policy_binding_and_timings(tmp_path: Path) -> None:
    result = pt2lg.compile_workflow(load_workflow("linear_llm.json"), out_dir=tmp_path)

    assert result.ok is True
    manifest = json.loads((result.output_dir / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads((result.output_dir / "compile_report.json").read_text(encoding="utf-8"))

    assert "policy_summary" in manifest
    assert "compose" in manifest["policy_summary"]["node_policies"]
    assert "binding_summary" in report
    assert "compose" in report["binding_summary"]["executor_bindings"]
    assert {"normalize", "validate", "resolve_policies", "bind_workflow", "target_compile", "artifact_write", "total"}.issubset(
        set(report["timings_ms"])
    )
