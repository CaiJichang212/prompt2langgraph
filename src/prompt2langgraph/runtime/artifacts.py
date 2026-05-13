from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from prompt2langgraph.ir.models import WorkflowSpec


@dataclass(frozen=True)
class BundlePaths:
    root: Path
    lockfile: Path
    workflow_ir: Path
    manifest: Path
    compile_report: Path
    mermaid: Path
    generated_dir: Path

    @classmethod
    def from_lockfile(cls, lockfile: Path | str) -> "BundlePaths":
        lock_path = Path(lockfile)
        root = lock_path.parent
        return cls(
            root=root,
            lockfile=lock_path,
            workflow_ir=root / "workflow.ir.json",
            manifest=root / "manifest.json",
            compile_report=root / "compile_report.json",
            mermaid=root / "graph.mmd",
            generated_dir=root / "generated",
        )


class CompileResult(BaseModel):
    ok: bool
    output_dir: Path
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


def load_json_file(path: Path | str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f'JSON file "{path}" must contain an object')
    return data


def load_bundle_workflow(bundle: BundlePaths | Path | str) -> WorkflowSpec:
    paths = bundle if isinstance(bundle, BundlePaths) else BundlePaths.from_lockfile(bundle)
    return WorkflowSpec.model_validate(load_json_file(paths.workflow_ir))


def load_bundle_mermaid(bundle: BundlePaths | Path | str) -> str:
    paths = bundle if isinstance(bundle, BundlePaths) else BundlePaths.from_lockfile(bundle)
    return paths.mermaid.read_text(encoding="utf-8")
