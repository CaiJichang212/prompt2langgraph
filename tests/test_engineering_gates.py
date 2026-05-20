import hashlib
import importlib.util
import json
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_LINEAR = ROOT / "tests" / "golden" / "linear_llm"


def _load_benchmark_compile():
    spec = importlib.util.spec_from_file_location(
        "benchmark_compile",
        ROOT / "scripts" / "benchmark_compile.py",
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_update_golden():
    spec = importlib.util.spec_from_file_location(
        "update_golden",
        ROOT / "scripts" / "update_golden.py",
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_ruff_is_declared_as_dev_dependency() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    dev_dependencies = pyproject["dependency-groups"]["dev"]

    assert any(dependency.startswith("ruff") for dependency in dev_dependencies)


def test_update_golden_check_mode_does_not_write_golden() -> None:
    before = _file_hashes(GOLDEN_LINEAR)

    result = subprocess.run(
        [
            sys.executable,
            "scripts/update_golden.py",
            "--case",
            "linear_llm",
            "--check",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "linear_llm" in result.stdout
    assert _file_hashes(GOLDEN_LINEAR) == before


def test_update_golden_update_mode_writes_normalized_compile_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    update_golden = _load_update_golden()
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    monkeypatch.setattr(update_golden, "GOLDEN", tmp_path / "golden")

    for artifact in update_golden.ARTIFACTS:
        source = GOLDEN_LINEAR / artifact
        target = bundle_dir / artifact
        if artifact == "compile_report.json":
            data = json.loads(source.read_text(encoding="utf-8"))
            data["compile_id"] = "compile_non_deterministic"
            data["timings_ms"] = {"total": 123.456}
            target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        else:
            target.write_bytes(source.read_bytes())

    update_golden._update_case("linear_llm", bundle_dir)

    compile_report = (tmp_path / "golden" / "linear_llm" / "compile_report.json").read_text(
        encoding="utf-8"
    )
    assert "compile_non_deterministic" not in compile_report
    assert "123.456" not in compile_report
    assert '"compile_id": "<compile_id>"' in compile_report
    assert '"timings_ms": "<timings_ms>"' in compile_report


def test_benchmark_linear_workflow_generator_has_stable_ids() -> None:
    build_linear_workflow = _load_benchmark_compile().build_linear_workflow
    workflow = build_linear_workflow(node_count=3)

    assert workflow.workflow_id == "benchmark_linear_3"
    assert [node.id for node in workflow.nodes] == ["node_1", "node_2", "node_3"]
    assert [edge.id for edge in workflow.edges] == [
        "edge_node_1_node_2",
        "edge_node_2_node_3",
    ]
