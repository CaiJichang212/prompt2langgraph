from __future__ import annotations

import argparse
import filecmp
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from prompt2langgraph.ir.models import WorkflowSpec
from prompt2langgraph.runtime.artifacts import compile_workflow_to_artifacts

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
GOLDEN = ROOT / "tests" / "golden"
CASES = ("linear_llm", "conditional_human_gate", "loop_with_guard", "fanout_map_reduce")
JSON_ARTIFACTS = ("workflow.ir.json", "workflow.lock.json", "manifest.json", "compile_report.json")
TEXT_ARTIFACTS = ("graph.mmd",)
ARTIFACTS = JSON_ARTIFACTS + TEXT_ARTIFACTS


def main() -> int:
    parser = argparse.ArgumentParser(description="Check or update compile golden snapshots.")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--case", choices=CASES)
    selection.add_argument("--all", action="store_true")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--update", action="store_true")
    args = parser.parse_args()

    cases = CASES if args.all else (args.case,)
    changed: list[str] = []
    for case_name in cases:
        with tempfile.TemporaryDirectory(prefix=f"pt2lg-golden-{case_name}-") as tmp:
            bundle_dir = _compile_case(case_name, Path(tmp))
            if args.update:
                _update_case(case_name, bundle_dir)
                print(f"{case_name}: updated")
            else:
                case_changed = _check_case(case_name, bundle_dir)
                changed.extend(case_changed)
                print(f"{case_name}: {'changed' if case_changed else 'ok'}")

    if changed:
        for path in changed:
            print(path)
        return 1
    return 0


def _compile_case(case_name: str, out_dir: Path) -> Path:
    workflow = WorkflowSpec.model_validate(
        json.loads((FIXTURES / f"{case_name}.json").read_text(encoding="utf-8"))
    )
    report, bundle_dir = compile_workflow_to_artifacts(workflow, out_dir=out_dir)
    if not report.ok:
        diagnostics = [diagnostic.model_dump(mode="json") for diagnostic in report.diagnostics]
        raise SystemExit(f"{case_name}: compile failed: {diagnostics}")
    return bundle_dir


def _check_case(case_name: str, bundle_dir: Path) -> list[str]:
    changed: list[str] = []
    for artifact in ARTIFACTS:
        expected = GOLDEN / case_name / artifact
        actual = _normalized_artifact(bundle_dir / artifact, artifact)
        if not expected.exists() or not _matches_expected(actual, expected, artifact):
            changed.append(str(expected.relative_to(ROOT)))
    return changed


def _update_case(case_name: str, bundle_dir: Path) -> None:
    target_dir = GOLDEN / case_name
    target_dir.mkdir(parents=True, exist_ok=True)
    for artifact in ARTIFACTS:
        _write_golden_artifact(bundle_dir / artifact, target_dir / artifact, artifact)


def _write_golden_artifact(source: Path, target: Path, artifact: str) -> None:
    if artifact in JSON_ARTIFACTS:
        data = _read_normalized_json(source, artifact)
        target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return
    shutil.copyfile(source, target)


def _normalized_artifact(path: Path, artifact: str) -> Path:
    if artifact not in JSON_ARTIFACTS:
        return path

    data = _read_normalized_json(path, artifact)
    normalized = path.parent / f".normalized.{artifact}"
    normalized.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return normalized


def _matches_expected(actual: Path, expected: Path, artifact: str) -> bool:
    if artifact not in JSON_ARTIFACTS:
        return filecmp.cmp(actual, expected, shallow=False)
    expected_data = _read_normalized_json(expected, artifact)
    actual_data = json.loads(actual.read_text(encoding="utf-8"))
    return actual_data == expected_data


def _read_normalized_json(path: Path, artifact: str) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if artifact == "compile_report.json":
        data["compile_id"] = "<compile_id>"
        data["timings_ms"] = "<timings_ms>"
    return data


if __name__ == "__main__":
    sys.exit(main())
