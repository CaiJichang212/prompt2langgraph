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
    assert {
        "normalize",
        "validate",
        "resolve_policies",
        "bind_workflow",
        "target_compile",
        "artifact_write",
        "total",
    }.issubset(set(report["timings_ms"]))


def test_lockfile_hash_deterministic() -> None:
    """同一 WorkflowSpec 两次计算 lockfile hash 结果一致。"""
    from prompt2langgraph.ir.lockfile import sha256_canonical_json
    from prompt2langgraph.ir.normalize import normalize_workflow

    wf = load_workflow("linear_llm.json")
    hash1 = sha256_canonical_json(normalize_workflow(wf).model_dump(mode="json"))
    hash2 = sha256_canonical_json(normalize_workflow(wf).model_dump(mode="json"))
    assert hash1 == hash2
    assert hash1.startswith("sha256:")
    assert len(hash1) == 71  # 7 + 64 hex chars


def test_compile_flow_accepts_multi_node_retriever_llm_fixture(tmp_path: Path) -> None:
    result = pt2lg.compile_workflow(load_workflow("linear_retriever_llm.json"), out_dir=tmp_path)

    assert result.ok is True
    assert result.output_dir == tmp_path / "linear_retriever_llm"
    assert (result.output_dir / "workflow.lock.json").exists()

    manifest = json.loads((result.output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert {node["id"] for node in manifest["nodes"]} == {"retrieve", "prepare_context", "compose"}
    assert {(edge["source"], edge["target"], edge["kind"]) for edge in manifest["edges"]} == {
        ("retrieve", "prepare_context", "linear"),
        ("prepare_context", "compose", "linear"),
    }
