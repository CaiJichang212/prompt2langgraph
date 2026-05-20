from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from time import perf_counter

from prompt2langgraph.ir.models import (
    EdgeKind,
    EdgeSpec,
    ExecutorRef,
    ExecutorType,
    NodeSpec,
    StateSchema,
    StateSelector,
    TypeName,
    TypeSpec,
    WorkflowSpec,
)
from prompt2langgraph.runtime.artifacts import compile_workflow_to_artifacts

ANY = TypeSpec(type=TypeName.ANY)


def build_linear_workflow(*, node_count: int) -> WorkflowSpec:
    if node_count < 1:
        raise ValueError("node_count must be at least 1")

    channels = {f"value_{index}": ANY for index in range(node_count + 1)}
    nodes = [
        NodeSpec(
            id=f"node_{index}",
            kind="transform",
            executor=ExecutorRef(ref="builtin.identity_transform", type=ExecutorType.BUILTIN),
            inputs={"value": StateSelector(state_key=f"value_{index - 1}")},
            outputs={"value": StateSelector(state_key=f"value_{index}")},
        )
        for index in range(1, node_count + 1)
    ]
    edges = [
        EdgeSpec(
            id=f"edge_node_{index}_node_{index + 1}",
            source=f"node_{index}",
            target=f"node_{index + 1}",
            kind=EdgeKind.LINEAR,
        )
        for index in range(1, node_count)
    ]

    return WorkflowSpec(
        schema_version="0.1",
        workflow_id=f"benchmark_linear_{node_count}",
        name=f"Benchmark Linear {node_count}",
        entrypoint="node_1",
        state_schema=StateSchema(
            input={"value_0": ANY},
            output={f"value_{node_count}": ANY},
            channels=channels,
        ),
        nodes=nodes,
        edges=edges,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile a deterministic benchmark workflow.")
    parser.add_argument("--nodes", type=int, required=True)
    parser.add_argument("--max-seconds", type=float, required=True)
    args = parser.parse_args()

    started_at = perf_counter()
    workflow = build_linear_workflow(node_count=args.nodes)
    with tempfile.TemporaryDirectory(prefix="pt2lg-benchmark-") as tmp:
        report, bundle_dir = compile_workflow_to_artifacts(workflow, out_dir=Path(tmp))
        duration_seconds = perf_counter() - started_at
        timings_ms = _read_timings(bundle_dir)

    ok = report.ok and duration_seconds <= args.max_seconds
    payload = {
        "ok": ok,
        "nodes": args.nodes,
        "max_seconds": args.max_seconds,
        "duration_seconds": round(duration_seconds, 6),
        "timings_ms": timings_ms,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if ok else 1


def _read_timings(bundle_dir: Path) -> dict[str, float]:
    report = json.loads((bundle_dir / "compile_report.json").read_text(encoding="utf-8"))
    return report["timings_ms"]


if __name__ == "__main__":
    sys.exit(main())
