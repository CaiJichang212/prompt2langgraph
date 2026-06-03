# v0.4 Phase 3C Runtime Config Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement v0.4 Phase 3C so generated bundles expose a minimal runtime config, dynamic tool bundles can be compiled and invoked, manifests report runtime requirements, and offline benchmark/engineering gates cover the 3C closure.

**Architecture:** Keep bundle artifacts as library-backed runtime artifacts rather than self-contained deployments. Extend generated `graph.py` with a small `RuntimeConfig` object and compatible `build_graph()`, `compile_graph()`, `invoke()`, and `invoke_graph()` entrypoints. Thread optional executor and tool registries through artifact compilation and CLI compile so dynamic tool workflows can be validated, bundled, and invoked without reintroducing 3A loader logic.

**Tech Stack:** Python 3.12, Typer CLI, Pydantic, LangGraph, pytest, existing `ExecutorRegistry`, `ToolCallableRegistry`, `compile_workflow_to_artifacts()`, golden bundle tests, `scripts/benchmark_compile.py`.

---

## Execution Rules

- Run this plan after Phase 3A and Phase 3B are implemented. If `src/prompt2langgraph/cli.py` does not contain Phase 3A helpers such as `_load_tool_modules()` and `_executor_registry_with_tools()`, stop and execute the 3A plan first.
- Do not duplicate the 3A tool-module loader in 3C. Reuse the CLI helpers added by 3A.
- Do not implement complete deployable bundles, secret manager integration, sandboxing, remote audit services, or LangChain Tool execution in 3C.
- Do not change dependency files for this phase.
- Commit steps require explicit user approval. If commits are not allowed, leave changes in the working tree and record the skipped commit in the handoff.

## Scope

This plan implements only v0.4 Phase 3C:

- Generated `graph.py` exposes `RuntimeConfig`, `build_graph(config=None)`, and `invoke(input_payload=None, config=None)`.
- Existing `compile_graph()` and `invoke_graph()` generated entrypoints remain compatible.
- `RuntimeConfig` supports `executor_registry`, `model_client`, `tool_registry`, `checkpointer`, and `policies`. The `policies` field must be a complete `PolicySpec` override, not a dict or partial merge.
- Artifact compilation accepts optional `executor_registry` and `tool_registry`. It uses the executor registry for validation, binding, compile smoke, lockfile registry hash, manifest executor bindings, and compile report registry hash. It uses the tool registry for compile-time `allowed_tool_refs` and registered-callable validation.
- CLI `pt2lg compile` accepts `--tool-module` after 3A is present, loads tool modules before simplified JSON plan adaptation, and passes the synthesized executor registry plus loaded tool registry to artifact compilation.
- Manifest output includes deterministic, secret-free runtime requirements: model refs, tool refs, checkpoint requirement, and policy summary.
- Golden bundle snapshots are updated for manifest/runtime-requirement changes.
- Offline engineering gates cover 10/100 node compile smoke, fanout/join compile smoke, tool workflow run smoke, side-effect interrupt/resume smoke through existing focused suites, and bundle load/invoke smoke.

## Current Source Facts

- `src/prompt2langgraph/compiler/codegen.py` currently generates `graph.py` with `build_graph()`, `compile_graph()`, and `invoke_graph(input_payload=None)` only; it always uses `builtin_executor_registry()`.
- `src/prompt2langgraph/runtime/artifacts.py` currently validates and compile-smokes with `builtin_executor_registry()` and does not accept `executor_registry` or `tool_registry`.
- `src/prompt2langgraph/ir/lockfile.py` already lets `build_workflow_lock()` and `build_manifest()` receive an executor registry, but `compile_workflow_to_artifacts()` does not pass an executor registry or tool registry through validation and artifact generation.
- `tests/test_artifacts.py` already has helpers for importing generated modules and tests for secret-free manifests, custom registry manifest binding, and old generated entrypoint compatibility.
- `tests/test_bundle_golden.py` compares JSON artifacts against `tests/golden/*`; manifest shape changes require golden updates.
- `tests/test_engineering_gates.py` and `scripts/benchmark_compile.py` already exist. 3C should extend them rather than create a parallel benchmark framework.
- Phase 3A is expected to add `tests/test_cli_tool_module.py`, `_write_tool_module()`, `_write_tool_json_plan()`, `_load_tool_modules()`, and `_executor_registry_with_tools()`.

## File Structure

- Modify `src/prompt2langgraph/compiler/codegen.py`: generated runtime config and compatible generated entrypoints.
- Modify `src/prompt2langgraph/runtime/artifacts.py`: optional executor/tool registry threading through artifact compilation.
- Modify `src/prompt2langgraph/ir/lockfile.py`: manifest runtime requirements and helper.
- Modify `src/prompt2langgraph/__init__.py`: public `compile_workflow(..., executor_registry=None, tool_registry=None)` wrapper.
- Modify `src/prompt2langgraph/cli.py`: `compile --tool-module`, reusing 3A loading helpers.
- Modify `tests/test_artifacts.py`: generated runtime config tests, dynamic tool bundle tests, runtime requirement manifest tests.
- Modify `tests/test_cli_tool_module.py`: CLI compile with tool module smoke.
- Modify `tests/test_engineering_gates.py`: Phase 3C offline benchmark smoke coverage.
- Modify `tests/test_bundle_golden.py` only if normalization needs adjustment. Prefer updating golden JSON snapshots with `scripts/update_golden.py`.
- Modify `README.md`, `AGENTS.md`, `CLAUDE.md`, `tests/prompts_skills_test/README.md`, and `docs/prompt2langgraph-v0.4-开发计划文档.md`: document Phase 3C status and gates.

---

### Task 1: Add Generated Runtime Config Tests

**Files:**
- Modify: `tests/test_artifacts.py`
- Reference: `src/prompt2langgraph/compiler/codegen.py`

- [ ] **Step 1: Add a dynamic tool workflow helper**

In `tests/test_artifacts.py`, after `import_generated_module()`, add:

```python
def tool_workflow() -> WorkflowSpec:
    return WorkflowSpec.model_validate(
        {
            "schema_version": "0.1",
            "workflow_id": "bundle_tool_smoke",
            "name": "Bundle Tool Smoke",
            "entrypoint": "call_tool",
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
            "nodes": [
                {
                    "id": "call_tool",
                    "kind": "tool",
                    "executor": {"ref": "fake.upper", "type": "python_callable"},
                    "inputs": {"question": {"state_key": "question"}},
                    "outputs": {"answer": {"state_key": "answer"}},
                    "params": {},
                }
            ],
            "edges": [],
            "policies": {"allowed_tool_refs": ["fake.upper"]},
            "metadata": {},
        }
    )
```

- [ ] **Step 2: Add generated builtin runtime config test**

Append this test to `tests/test_artifacts.py`:

```python
def test_generated_graph_runtime_config_supports_clients_and_old_entrypoints(
    tmp_path: Path,
) -> None:
    workflow = load_workflow("linear_llm.json")
    from prompt2langgraph.compiler.codegen import emit_generated_bundle

    (tmp_path / "workflow.ir.json").write_text(
        json.dumps(workflow.model_dump(mode="json"), ensure_ascii=False),
        encoding="utf-8",
    )
    generated = emit_generated_bundle(workflow, tmp_path)
    graph_module = import_generated_module(generated / "graph.py", "generated_graph_config")

    assert callable(graph_module.RuntimeConfig)
    assert callable(graph_module.build_graph)
    assert callable(graph_module.compile_graph)
    assert callable(graph_module.invoke)
    assert callable(graph_module.invoke_graph)

    graph = graph_module.build_graph(graph_module.RuntimeConfig())
    assert graph is not None
    assert graph_module.compile_graph() is not None
    assert graph_module.invoke({"question": "hello"}) == {"question": "hello", "answer": "Answer: hello"}
    assert graph_module.invoke_graph({"question": "hello"}) == {
        "question": "hello",
        "answer": "Answer: hello",
    }
```

- [ ] **Step 3: Add generated dynamic tool runtime config test**

Append this test to `tests/test_artifacts.py`:

```python
def test_generated_graph_runtime_config_runs_dynamic_tool_workflow(
    tmp_path: Path,
) -> None:
    workflow = tool_workflow()
    from prompt2langgraph.compiler.codegen import emit_generated_bundle
    from prompt2langgraph.registry.tool_executor import ToolCallableRegistry

    (tmp_path / "workflow.ir.json").write_text(
        json.dumps(workflow.model_dump(mode="json"), ensure_ascii=False),
        encoding="utf-8",
    )
    generated = emit_generated_bundle(workflow, tmp_path)
    graph_module = import_generated_module(generated / "graph.py", "generated_graph_tool_config")
    executor_registry = ExecutorRegistry(
        [
            ExecutorDefinition(
                ref="fake.upper",
                type=ExecutorType.PYTHON_CALLABLE,
                dynamic=True,
            )
        ]
    )
    tools = ToolCallableRegistry()
    tools.register("fake.upper", lambda inputs, params: {"answer": inputs["question"].upper()})

    result = graph_module.invoke(
        {"question": "hello"},
        graph_module.RuntimeConfig(
            executor_registry=executor_registry,
            tool_registry=tools,
        ),
    )

    assert result == {"question": "hello", "answer": "HELLO"}


def test_generated_graph_runtime_config_rejects_unauthorized_tool_policy(
    tmp_path: Path,
) -> None:
    workflow = tool_workflow()
    workflow.policies.allowed_tool_refs = []
    from prompt2langgraph.compiler.codegen import emit_generated_bundle
    from prompt2langgraph.registry.tool_executor import ToolCallableRegistry

    (tmp_path / "workflow.ir.json").write_text(
        json.dumps(workflow.model_dump(mode="json"), ensure_ascii=False),
        encoding="utf-8",
    )
    generated = emit_generated_bundle(workflow, tmp_path)
    graph_module = import_generated_module(
        generated / "graph.py",
        "generated_graph_unauthorized_tool_config",
    )
    executor_registry = ExecutorRegistry(
        [
            ExecutorDefinition(
                ref="fake.upper",
                type=ExecutorType.PYTHON_CALLABLE,
                dynamic=True,
            )
        ]
    )
    tools = ToolCallableRegistry()
    tools.register("fake.upper", lambda inputs, params: {"answer": inputs["question"].upper()})

    with pytest.raises(RuntimeError, match="runtime config validation failed"):
        graph_module.build_graph(
            graph_module.RuntimeConfig(
                executor_registry=executor_registry,
                tool_registry=tools,
            )
        )
```

- [ ] **Step 4: Run tests and verify they fail**

Run:

```bash
uv run pytest tests/test_artifacts.py::test_generated_graph_runtime_config_supports_clients_and_old_entrypoints tests/test_artifacts.py::test_generated_graph_runtime_config_runs_dynamic_tool_workflow tests/test_artifacts.py::test_generated_graph_runtime_config_rejects_unauthorized_tool_policy -v
```

Expected: tests fail because generated `graph.py` has no `RuntimeConfig` or `invoke()` entrypoint, cannot inject dynamic tool registries, and does not validate runtime tool authorization.

- [ ] **Step 5: Commit failing tests if allowed**

Run only after user approval:

```bash
git add tests/test_artifacts.py
git commit -m "test: cover generated runtime config entrypoints"
```

Expected: commit succeeds if commits are allowed.

---

### Task 2: Implement Generated Runtime Config

**Files:**
- Modify: `src/prompt2langgraph/compiler/codegen.py`
- Test: `tests/test_artifacts.py`

- [ ] **Step 1: Replace `_write_graph()` generated text**

In `src/prompt2langgraph/compiler/codegen.py`, replace the `text = '''...'''` payload inside `_write_graph()` with this complete generated module:

```python
    text = '''"""Generated graph entrypoint for this workflow bundle."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from prompt2langgraph.compiler.langgraph_py import compile_workflow_to_graph
from prompt2langgraph.ir.models import WorkflowSpec
from prompt2langgraph.registry.builtins import builtin_executor_registry
from prompt2langgraph.validate.validator import validate_workflow


@dataclass(frozen=True)
class RuntimeConfig:
    executor_registry: Any | None = None
    model_client: Any | None = None
    tool_registry: Any | None = None
    checkpointer: Any | None = None
    policies: Any | None = None


def load_workflow() -> WorkflowSpec:
    workflow_path = Path(__file__).resolve().parents[1] / "workflow.ir.json"
    data = json.loads(workflow_path.read_text(encoding="utf-8"))
    return WorkflowSpec.model_validate(data)


def build_graph(config: RuntimeConfig | None = None):
    selected = config or RuntimeConfig()
    workflow = load_workflow()
    effective_workflow = (
        workflow.model_copy(update={"policies": selected.policies})
        if selected.policies is not None
        else workflow
    )
    executors = selected.executor_registry or builtin_executor_registry()
    report = validate_workflow(
        effective_workflow,
        executors=executors,
        tool_registry=selected.tool_registry,
    )
    if not report.ok:
        diagnostics = [item.model_dump(mode="json") for item in report.diagnostics]
        raise RuntimeError(
            "generated bundle runtime config validation failed: "
            + json.dumps(diagnostics, ensure_ascii=False, sort_keys=True)
        )
    return compile_workflow_to_graph(
        effective_workflow,
        executors,
        checkpointer=selected.checkpointer,
        policies=selected.policies,
        model_client=selected.model_client,
        tool_registry=selected.tool_registry,
    )


def compile_graph():
    return build_graph()


def invoke(
    input_payload: dict[str, Any] | None = None,
    config: RuntimeConfig | None = None,
) -> dict[str, Any]:
    workflow = load_workflow()
    graph = build_graph(config)
    return graph.invoke(input_payload if input_payload is not None else sample_input(workflow))


def invoke_graph(input_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return invoke(input_payload)


def sample_input(workflow: WorkflowSpec | None = None) -> dict[str, Any]:
    selected = workflow or load_workflow()
    return {
        state_key: _sample_value(type_spec)
        for state_key, type_spec in selected.state_schema.input.items()
    }


def _sample_value(type_spec: Any) -> Any:
    type_name = type_spec.type.value
    if type_name in {"string", "artifact_ref", "any"}:
        return "sample"
    if type_name == "number":
        return 1.0
    if type_name == "integer":
        return 1
    if type_name == "boolean":
        return True
    if type_name == "array":
        return [_sample_value(type_spec.item_type)] if type_spec.item_type is not None else []
    if type_name == "object":
        return {}
    if type_name == "messages":
        return []
    return None


def _load_input(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f'input file "{path}" must contain a JSON object')
    return data


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run this generated LangGraph bundle.")
    parser.add_argument("--input", type=Path, help="JSON file containing workflow input state.")
    args = parser.parse_args(argv)
    input_payload = _load_input(args.input) if args.input is not None else None
    state = invoke(input_payload)
    print(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
'''
```

- [ ] **Step 2: Update existing generated module assertion**

In `tests/test_artifacts.py`, in `test_emit_generated_bundle_writes_importable_graph_module()`, replace:

```python
    assert "def build_graph()" in graph_py.read_text(encoding="utf-8")
```

with:

```python
    assert "class RuntimeConfig" in graph_py.read_text(encoding="utf-8")
    assert "def build_graph(config: RuntimeConfig | None = None)" in graph_py.read_text(
        encoding="utf-8"
    )
```

- [ ] **Step 3: Run generated runtime config tests**

Run:

```bash
uv run pytest tests/test_artifacts.py::test_emit_generated_bundle_writes_importable_graph_module tests/test_artifacts.py::test_generated_graph_runtime_config_supports_clients_and_old_entrypoints tests/test_artifacts.py::test_generated_graph_runtime_config_runs_dynamic_tool_workflow tests/test_artifacts.py::test_generated_graph_runtime_config_rejects_unauthorized_tool_policy -v
```

Expected: all three tests pass.

- [ ] **Step 4: Commit generated runtime config if allowed**

Run only after user approval:

```bash
git add src/prompt2langgraph/compiler/codegen.py tests/test_artifacts.py
git commit -m "feat: add runtime config to generated bundles"
```

Expected: commit succeeds if commits are allowed.

---

### Task 3: Thread Executor Registry Through Artifact Compilation

**Files:**
- Modify: `tests/test_artifacts.py`
- Modify: `src/prompt2langgraph/runtime/artifacts.py`
- Modify: `src/prompt2langgraph/__init__.py`
- Test: `tests/test_compile_flow.py`

- [ ] **Step 1: Add failing artifact compile test for dynamic tool registry**

Append this test to `tests/test_artifacts.py`:

```python
def test_compile_workflow_to_artifacts_accepts_registries_for_dynamic_tool(
    tmp_path: Path,
) -> None:
    from prompt2langgraph.runtime.artifacts import compile_workflow_to_artifacts
    from prompt2langgraph.registry.tool_executor import ToolCallableRegistry

    workflow = tool_workflow()
    tools = ToolCallableRegistry()
    tools.register("fake.upper", lambda inputs, params: {"answer": inputs["question"].upper()})
    executor_registry = ExecutorRegistry(
        [
            ExecutorDefinition(
                ref="fake.upper",
                type=ExecutorType.PYTHON_CALLABLE,
                dynamic=True,
            )
        ]
    )

    report, bundle_dir = compile_workflow_to_artifacts(
        workflow,
        out_dir=tmp_path,
        executor_registry=executor_registry,
        tool_registry=tools,
    )

    assert report.ok, report.diagnostics
    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["executor_bindings"]["call_tool"]["executor"] == "fake.upper"
    assert manifest["executor_bindings"]["call_tool"]["type"] == "python_callable"
    assert manifest["executor_bindings"]["call_tool"]["dynamic"] is True

    graph_module = import_generated_module(
        bundle_dir / "generated" / "graph.py",
        "compiled_dynamic_tool_graph",
    )
    result = graph_module.invoke(
        {"question": "hello"},
        graph_module.RuntimeConfig(
            executor_registry=executor_registry,
            tool_registry=tools,
        ),
    )

    assert result == {"question": "hello", "answer": "HELLO"}
```

- [ ] **Step 2: Add public compile workflow registry test**

Append this test to `tests/test_compile_flow.py`:

```python
def test_public_compile_workflow_accepts_registries(tmp_path: Path) -> None:
    from prompt2langgraph.ir.models import ExecutorType
    from prompt2langgraph.registry.executors import ExecutorDefinition, ExecutorRegistry
    from prompt2langgraph.registry.tool_executor import ToolCallableRegistry

    workflow = pt2lg.WorkflowSpec.model_validate(
        {
            "schema_version": "0.1",
            "workflow_id": "public_dynamic_compile",
            "name": "Public Dynamic Compile",
            "entrypoint": "call_tool",
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
            "nodes": [
                {
                    "id": "call_tool",
                    "kind": "tool",
                    "executor": {"ref": "fake.upper", "type": "python_callable"},
                    "inputs": {"question": {"state_key": "question"}},
                    "outputs": {"answer": {"state_key": "answer"}},
                    "params": {},
                }
            ],
            "edges": [],
            "policies": {"allowed_tool_refs": ["fake.upper"]},
            "metadata": {},
        }
    )
    executor_registry = ExecutorRegistry(
        [
            ExecutorDefinition(
                ref="fake.upper",
                type=ExecutorType.PYTHON_CALLABLE,
                dynamic=True,
            )
        ]
    )
    tools = ToolCallableRegistry()
    tools.register("fake.upper", lambda inputs, params: {"answer": inputs["question"].upper()})

    result = pt2lg.compile_workflow(
        workflow,
        out_dir=tmp_path,
        executor_registry=executor_registry,
        tool_registry=tools,
    )

    assert result.ok is True
    manifest = json.loads((result.output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["executor_bindings"]["call_tool"]["executor"] == "fake.upper"
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```bash
uv run pytest tests/test_artifacts.py::test_compile_workflow_to_artifacts_accepts_registries_for_dynamic_tool tests/test_compile_flow.py::test_public_compile_workflow_accepts_registries -v
```

Expected: tests fail because `compile_workflow_to_artifacts()` and public `compile_workflow()` do not accept `executor_registry` or `tool_registry`.

- [ ] **Step 4: Update artifact compile signatures**

In `src/prompt2langgraph/runtime/artifacts.py`, change the `compile_workflow_to_artifacts()` signature to:

```python
def compile_workflow_to_artifacts(
    workflow: WorkflowSpec,
    *,
    out_dir: Path | str,
    target: str = "langgraph-py",
    executor_registry: Any | None = None,
    tool_registry: Any | None = None,
) -> tuple[ValidationReport, Path]:
```

Then call `_validate_and_compile_target()` with:

```python
    report, normalized, resolved, bound = _validate_and_compile_target(
        workflow,
        target=target,
        timings_ms=timings_ms,
        executor_registry=executor_registry,
        tool_registry=tool_registry,
    )
```

And call `_write_compile_artifacts()` with:

```python
            executor_registry=executor_registry,
```

- [ ] **Step 5: Update `_write_compile_artifacts()`**

Add this parameter to `_write_compile_artifacts()`:

```python
    executor_registry: Any | None,
```

Inside `_write_compile_artifacts()`, build lock and manifest before `artifact_payloads`:

```python
    lock = build_workflow_lock(
        normalized,
        target=target,
        executor_registry=executor_registry,
    )
    manifest = build_manifest(
        normalized,
        target=target,
        executor_registry=executor_registry,
        node_policies=resolved.node_policies,
    )
```

Then replace the existing `artifact_payloads` block with:

```python
    artifact_payloads = {
        "workflow.ir.json": normalized.model_dump(mode="json"),
        "workflow.lock.json": lock,
        "manifest.json": manifest,
    }
```

When building the compile report, pass the matching registry hash:

```python
        registry_hash=lock["registry_hash"],
```

- [ ] **Step 6: Update `_validate_and_compile_target()`**

Change the signature to:

```python
def _validate_and_compile_target(
    workflow: WorkflowSpec,
    *,
    target: str,
    timings_ms: dict[str, float],
    executor_registry: Any | None = None,
    tool_registry: Any | None = None,
) -> tuple[ValidationReport, WorkflowSpec | None, ResolvedWorkflow | None, BoundWorkflow | None]:
```

At the top of the function, after normalization, select executors:

```python
    selected_executor_registry = executor_registry or builtin_executor_registry()
```

Replace validation, binding, and compile smoke calls with:

```python
    report = validate_workflow(
        normalized,
        executors=selected_executor_registry,
        tool_registry=tool_registry,
    )
```

```python
    bound = bind_workflow(normalized, executors=selected_executor_registry)
```

```python
        compile_workflow_to_graph(
            normalized,
            selected_executor_registry,
            tool_registry=tool_registry,
        )
```

- [ ] **Step 7: Update public API wrapper**

In `src/prompt2langgraph/__init__.py`, replace `compile_workflow()` with:

```python
def compile_workflow(
    workflow: WorkflowSpec,
    *,
    out_dir: Path | str,
    executor_registry: Any | None = None,
    tool_registry: Any | None = None,
) -> CompileResult:
    from prompt2langgraph.runtime.artifacts import CompileResult, compile_workflow_to_artifacts

    report, output_dir = compile_workflow_to_artifacts(
        workflow,
        out_dir=out_dir,
        executor_registry=executor_registry,
        tool_registry=tool_registry,
    )

    return CompileResult(
        ok=report.ok,
        output_dir=output_dir,
        diagnostics=[item.model_dump(mode="json") for item in report.diagnostics],
        artifacts={
            "workflow_ir": "workflow.ir.json",
            "lock": "workflow.lock.json",
            "manifest": "manifest.json",
            "compile_report": "compile_report.json",
            "mermaid": "graph.mmd",
        },
    )
```

- [ ] **Step 8: Run artifact and public compile tests**

Run:

```bash
uv run pytest tests/test_artifacts.py::test_compile_workflow_to_artifacts_accepts_registries_for_dynamic_tool tests/test_compile_flow.py::test_public_compile_workflow_accepts_registries -v
```

Expected: both tests pass.

- [ ] **Step 9: Commit registry threading if allowed**

Run only after user approval:

```bash
git add src/prompt2langgraph/runtime/artifacts.py src/prompt2langgraph/__init__.py tests/test_artifacts.py tests/test_compile_flow.py
git commit -m "feat: compile bundles with injected registries"
```

Expected: commit succeeds if commits are allowed.

---

### Task 4: Wire `--tool-module` Through CLI Compile

**Files:**
- Modify: `tests/test_cli_tool_module.py`
- Modify: `src/prompt2langgraph/cli.py`

- [ ] **Step 1: Add CLI compile tool-module test**

Append this test to `tests/test_cli_tool_module.py`:

```python
def test_cli_compile_loads_tool_module_before_json_plan_adapter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_tool_module(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    plan_path = tmp_path / "tool_plan.json"
    _write_tool_json_plan(plan_path)

    result = CliRunner().invoke(
        app,
        [
            "compile",
            str(plan_path),
            "--tool-module",
            "fake_cli_tools",
            "--out",
            str(tmp_path / "build"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    bundle_dir = tmp_path / "build" / "tool_plan_smoke"
    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["executor_bindings"]["call_tool"]["executor"] == "fake.upper"
    assert manifest["executor_bindings"]["call_tool"]["type"] == "python_callable"
    assert manifest["runtime_requirements"]["tool_refs"] == ["fake.upper"]
    assert (bundle_dir / "generated" / "graph.py").exists()
```

- [ ] **Step 2: Add CLI compile diagnostics tests**

Append these tests to `tests/test_cli_tool_module.py`:

```python
def test_cli_compile_with_tool_module_rejects_unauthorized_tool_ref(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_tool_module(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    plan_path = tmp_path / "unauthorized_tool_plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "name": "Unauthorized Tool Plan",
                "workflow_id": "unauthorized_tool_plan",
                "inputs": {"question": "string"},
                "outputs": {"answer": "string"},
                "nodes": [
                    {
                        "id": "call_tool",
                        "kind": "tool",
                        "executor": "fake.upper",
                        "inputs": {"question": "question"},
                        "outputs": {"answer": "answer"},
                    }
                ],
                "edges": [],
                "policies": {"allowed_tool_refs": []},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "compile",
            str(plan_path),
            "--tool-module",
            "fake_cli_tools",
            "--out",
            str(tmp_path / "build"),
            "--json",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert any(
        item["code"] == "E_SEC_015" and "fake.upper" in item["message"]
        for item in payload["diagnostics"]
    )
    assert "Traceback" not in result.stdout


def test_cli_compile_reports_tool_module_without_register_tools(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module_path = tmp_path / "bad_cli_tools.py"
    module_path.write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    plan_path = tmp_path / "tool_plan.json"
    _write_tool_json_plan(plan_path)

    result = CliRunner().invoke(
        app,
        [
            "compile",
            str(plan_path),
            "--tool-module",
            "bad_cli_tools",
            "--out",
            str(tmp_path / "build"),
            "--json",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["diagnostics"][0]["code"] == "E_RUNTIME_010"
    assert "register_tools" in payload["diagnostics"][0]["message"]
    assert "Traceback" not in result.stdout
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```bash
uv run pytest tests/test_cli_tool_module.py::test_cli_compile_loads_tool_module_before_json_plan_adapter tests/test_cli_tool_module.py::test_cli_compile_with_tool_module_rejects_unauthorized_tool_ref tests/test_cli_tool_module.py::test_cli_compile_reports_tool_module_without_register_tools -v
```

Expected: tests fail because `compile` does not accept `--tool-module`, does not pass registries into workflow loading/artifact compilation, or does not validate compile-time tool authorization.

- [ ] **Step 4: Update `compile()` signature**

In `src/prompt2langgraph/cli.py`, change the compile command signature to:

```python
def compile(
    workflow_json: Path,
    target: str = typer.Option("langgraph-py", "--target"),
    out: Path = COMPILE_OUT_OPTION,
    tool_module: list[str] = typer.Option([], "--tool-module"),
    json_output: bool = typer.Option(False, "--json", help="Emit a machine-readable report."),
) -> None:
```

- [ ] **Step 5: Load tool modules before workflow source parsing**

At the top of `compile()`, before `_load_workflow_or_report(...)`, add:

```python
    loaded_tool_registry = _load_tool_modules(tool_module)
    if isinstance(loaded_tool_registry, ValidationReport):
        _emit_compile_payload(False, None, loaded_tool_registry, json_output)
        raise typer.Exit(1)
    if not tool_module:
        loaded_tool_registry = None
    executor_registry = _executor_registry_with_tools(loaded_tool_registry)
```

Then replace:

```python
    workflow_or_report = _load_workflow_or_report(workflow_json)
```

with:

```python
    workflow_or_report = _load_workflow_or_report(
        workflow_json,
        executors=executor_registry,
    )
```

- [ ] **Step 6: Pass registries to artifact compilation**

Replace:

```python
    report, output_dir = compile_workflow_to_artifacts(workflow, out_dir=out, target=target)
```

with:

```python
    report, output_dir = compile_workflow_to_artifacts(
        workflow,
        out_dir=out,
        target=target,
        executor_registry=executor_registry,
        tool_registry=loaded_tool_registry,
    )
```

- [ ] **Step 7: Run CLI compile tests**

Run:

```bash
uv run pytest tests/test_cli_tool_module.py::test_cli_compile_loads_tool_module_before_json_plan_adapter tests/test_cli_tool_module.py::test_cli_compile_with_tool_module_rejects_unauthorized_tool_ref tests/test_cli_tool_module.py::test_cli_compile_reports_tool_module_without_register_tools -v
```

Expected: tests pass.

- [ ] **Step 8: Commit CLI compile tool module support if allowed**

Run only after user approval:

```bash
git add src/prompt2langgraph/cli.py tests/test_cli_tool_module.py
git commit -m "feat: support tool modules during CLI compile"
```

Expected: commit succeeds if commits are allowed.

---

### Task 5: Add Manifest Runtime Requirements

**Files:**
- Modify: `tests/test_artifacts.py`
- Modify: `src/prompt2langgraph/ir/lockfile.py`

- [ ] **Step 1: Add runtime requirements manifest tests**

Append these tests to `tests/test_artifacts.py`:

```python
def test_manifest_contains_secret_free_runtime_requirements() -> None:
    workflow = load_workflow("linear_llm.json")

    manifest = build_manifest(workflow)

    assert manifest["runtime_requirements"] == {
        "model_refs": [],
        "tool_refs": [],
        "checkpoint_required": False,
        "policy": {
            "external_call": False,
            "allow_side_effects": False,
            "allowed_models": [],
            "allowed_tool_refs": [],
        },
        "policy_overrides_supported": [
            "allow_side_effects",
            "allowed_models",
            "allowed_tool_refs",
            "default_timeout_s",
            "external_call",
        ],
    }
    assert "secret" not in json.dumps(manifest["runtime_requirements"]).lower()


def test_manifest_runtime_requirements_reports_dynamic_tool_refs() -> None:
    workflow = tool_workflow()
    executor_registry = ExecutorRegistry(
        [
            ExecutorDefinition(
                ref="fake.upper",
                type=ExecutorType.PYTHON_CALLABLE,
                dynamic=True,
            )
        ]
    )

    manifest = build_manifest(workflow, executor_registry=executor_registry)

    assert manifest["runtime_requirements"]["tool_refs"] == ["fake.upper"]
    assert manifest["runtime_requirements"]["model_refs"] == []
    assert manifest["runtime_requirements"]["checkpoint_required"] is False
    assert manifest["runtime_requirements"]["policy"]["allowed_tool_refs"] == ["fake.upper"]
```

- [ ] **Step 2: Update existing exact manifest expectation**

In `test_artifact_builders_emit_expected_minimal_shapes()`, add this field to the expected manifest dict after `"artifact_policy": {"large_objects": "artifact_ref"},`:

```python
        "runtime_requirements": {
            "model_refs": [],
            "tool_refs": [],
            "checkpoint_required": False,
            "policy": {
                "external_call": False,
                "allow_side_effects": False,
                "allowed_models": [],
                "allowed_tool_refs": [],
            },
            "policy_overrides_supported": [
                "allow_side_effects",
                "allowed_models",
                "allowed_tool_refs",
                "default_timeout_s",
                "external_call",
            ],
        },
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```bash
uv run pytest tests/test_artifacts.py::test_artifact_builders_emit_expected_minimal_shapes tests/test_artifacts.py::test_manifest_contains_secret_free_runtime_requirements tests/test_artifacts.py::test_manifest_runtime_requirements_reports_dynamic_tool_refs -v
```

Expected: tests fail because manifest has no `runtime_requirements`.

- [ ] **Step 4: Add `ExecutorType` import**

In `src/prompt2langgraph/ir/lockfile.py`, replace:

```python
from prompt2langgraph.ir.models import WorkflowSpec
```

with:

```python
from prompt2langgraph.ir.models import ExecutorType, WorkflowSpec
```

- [ ] **Step 5: Add runtime requirement helper**

In `src/prompt2langgraph/ir/lockfile.py`, after `build_manifest()`, add:

```python
def _runtime_requirements(workflow: WorkflowSpec) -> dict[str, Any]:
    model_refs = sorted(
        {
            node.executor.ref
            for node in workflow.nodes
            if node.executor.type is ExecutorType.LLM
        }
    )
    tool_refs = sorted(
        {
            node.executor.ref
            for node in workflow.nodes
            if node.executor.type is ExecutorType.PYTHON_CALLABLE
        }
    )
    checkpoint_required = any(
        node.kind in {"human_gate", "side_effect"}
        or node.executor.type.value == "human"
        for node in workflow.nodes
    )
    policies = workflow.policies
    return {
        "model_refs": model_refs,
        "tool_refs": tool_refs,
        "checkpoint_required": checkpoint_required,
        "policy": {
            "external_call": policies.external_call,
            "allow_side_effects": policies.allow_side_effects,
            "allowed_models": sorted(policies.allowed_models),
            "allowed_tool_refs": sorted(policies.allowed_tool_refs),
        },
        "policy_overrides_supported": [
            "allow_side_effects",
            "allowed_models",
            "allowed_tool_refs",
            "default_timeout_s",
            "external_call",
        ],
    }
```

- [ ] **Step 6: Add runtime requirements to manifest**

In `build_manifest()`, add this field to the manifest dict after `artifact_policy`:

```python
        "runtime_requirements": _runtime_requirements(normalized),
```

- [ ] **Step 7: Run runtime requirements tests**

Run:

```bash
uv run pytest tests/test_artifacts.py::test_artifact_builders_emit_expected_minimal_shapes tests/test_artifacts.py::test_manifest_contains_secret_free_runtime_requirements tests/test_artifacts.py::test_manifest_runtime_requirements_reports_dynamic_tool_refs -v
```

Expected: tests pass.

- [ ] **Step 8: Commit manifest runtime requirements if allowed**

Run only after user approval:

```bash
git add src/prompt2langgraph/ir/lockfile.py tests/test_artifacts.py
git commit -m "feat: describe runtime requirements in bundle manifests"
```

Expected: commit succeeds if commits are allowed.

---

### Task 6: Update Golden Bundle Snapshots

**Files:**
- Modify: `tests/golden/linear_llm/manifest.json`
- Modify: `tests/golden/conditional_human_gate/manifest.json`
- Modify: `tests/golden/loop_with_guard/manifest.json`
- Modify: `tests/golden/fanout_map_reduce/manifest.json`
- Test: `tests/test_bundle_golden.py`

- [ ] **Step 1: Verify golden snapshots fail before update**

Run:

```bash
uv run pytest tests/test_bundle_golden.py -v
```

Expected: tests fail because generated manifests now include `runtime_requirements`.

- [ ] **Step 2: Update golden snapshots**

Run:

```bash
uv run python scripts/update_golden.py --all --update
```

Expected: command prints each golden case as updated.

- [ ] **Step 3: Verify golden check mode**

Run:

```bash
uv run python scripts/update_golden.py --all --check
```

Expected: all cases print `ok` and the command exits with status 0.

- [ ] **Step 4: Run golden bundle tests**

Run:

```bash
uv run pytest tests/test_bundle_golden.py -v
```

Expected: all golden bundle tests pass.

- [ ] **Step 5: Commit golden snapshots if allowed**

Run only after user approval:

```bash
git add tests/golden
git commit -m "test: update bundle golden runtime requirements"
```

Expected: commit succeeds if commits are allowed.

---

### Task 7: Add Phase 3C Engineering Gate Smoke Tests

**Files:**
- Modify: `tests/test_engineering_gates.py`
- Reference: `scripts/benchmark_compile.py`
- Reference: `tests/fixtures/fanout_map_reduce.json`

- [ ] **Step 1: Add compile smoke gate tests**

Append these tests to `tests/test_engineering_gates.py`:

```python
def test_phase3c_benchmark_compile_smoke_covers_10_and_100_nodes(
    tmp_path: Path,
) -> None:
    benchmark_compile = _load_benchmark_compile()

    for node_count in (10, 100):
        workflow = benchmark_compile.build_linear_workflow(node_count=node_count)
        from prompt2langgraph.runtime.artifacts import compile_workflow_to_artifacts

        report, bundle_dir = compile_workflow_to_artifacts(workflow, out_dir=tmp_path)

        assert report.ok, report.diagnostics
        assert bundle_dir.name == f"benchmark_linear_{node_count}"
        assert (bundle_dir / "workflow.lock.json").exists()
        assert (bundle_dir / "generated" / "graph.py").exists()


def test_phase3c_fanout_join_compile_smoke(tmp_path: Path) -> None:
    from prompt2langgraph.ir.models import WorkflowSpec
    from prompt2langgraph.runtime.artifacts import compile_workflow_to_artifacts

    workflow = WorkflowSpec.model_validate(
        json.loads((ROOT / "tests" / "fixtures" / "fanout_map_reduce.json").read_text(encoding="utf-8"))
    )

    report, bundle_dir = compile_workflow_to_artifacts(workflow, out_dir=tmp_path)

    assert report.ok, report.diagnostics
    assert (bundle_dir / "manifest.json").exists()
    assert "join:" in (bundle_dir / "graph.mmd").read_text(encoding="utf-8")


def test_phase3c_benchmark_script_runs_offline_for_10_nodes() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/benchmark_compile.py",
            "--nodes",
            "10",
            "--max-seconds",
            "120",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["nodes"] == 10
    assert "timings_ms" in payload
```

- [ ] **Step 2: Run engineering gate tests**

Run:

```bash
uv run pytest tests/test_engineering_gates.py -v
```

Expected: all engineering gate tests pass.

- [ ] **Step 3: Run existing smoke suites that complete the 3C gate**

Run:

```bash
uv run pytest tests/test_artifacts.py tests/test_cli_tool_module.py tests/test_runner.py tests/test_side_effect_executor.py tests/test_bundle_golden.py tests/test_prompt_skill_corpus.py -v
```

Expected: all tests pass. This command covers generated bundle load/invoke smoke, tool run smoke, side-effect interrupt/resume smoke, bundle golden smoke, and offline prompt/skill corpus success metrics.

- [ ] **Step 4: Commit engineering gates if allowed**

Run only after user approval:

```bash
git add tests/test_engineering_gates.py
git commit -m "test: add phase3c engineering gate smokes"
```

Expected: commit succeeds if commits are allowed.

---

### Task 8: Document Phase 3C Runtime Config and Gates

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Modify: `tests/prompts_skills_test/README.md`
- Modify: `docs/prompt2langgraph-v0.4-开发计划文档.md`

- [ ] **Step 1: Update README bundle section**

Near the existing bundle contract section in `README.md`, add:

```markdown
### Runtime Config Bundles

Generated bundle code exposes `RuntimeConfig`, `build_graph(config=None)`,
`invoke(input_payload=None, config=None)`, and the compatible
`compile_graph()` / `invoke_graph()` entrypoints. `RuntimeConfig` can inject a
model client, tool registry, executor registry, checkpointer, and complete
`PolicySpec` policies override when running the generated graph through the
local `prompt2langgraph` library. The policies value is not a dict or partial
merge and must not be used to bypass compile-time tool authorization.

Bundle manifests include `runtime_requirements` with model refs, tool refs,
checkpoint requirement, and a secret-free policy summary. Manifests, lockfiles,
and compile reports must not contain real secrets or secret names.
```

- [ ] **Step 2: Update AGENTS and CLAUDE bundle notes**

Add this concise note to both `AGENTS.md` and `CLAUDE.md` near the bundle guidance:

```markdown
- v0.4 3C generated bundle `generated/graph.py` exposes `RuntimeConfig`,
  `build_graph(config=None)`, and `invoke(input_payload=None, config=None)`,
  while keeping `compile_graph()` and `invoke_graph()` compatible.
- `RuntimeConfig` supports local injection of executor registry, model client,
  tool registry, checkpointer, and complete `PolicySpec` policies override; it
  is not a deployable service wrapper or secret manager.
- `manifest.json` includes secret-free `runtime_requirements` for model refs,
  tool refs, checkpoint requirement, and policy summary.
```

- [ ] **Step 3: Update prompt/skill corpus README gates**

In `tests/prompts_skills_test/README.md`, add this note near the metric or regression section:

```markdown
Phase 3C engineering gates reuse this offline corpus and do not access the
network. Full 3C verification also runs generated bundle load/invoke, dynamic
tool bundle smoke, side-effect interrupt/resume smoke, and deterministic
10/100-node compile smoke.
```

- [ ] **Step 4: Update v0.4 development plan status**

In `docs/prompt2langgraph-v0.4-开发计划文档.md`, under the 3C sections, add wording equivalent to:

```markdown
3C implementation status: generated bundles expose a minimal RuntimeConfig,
artifact compilation accepts injected executor registries for dynamic tool
bundles, manifests report secret-free runtime requirements, and offline
engineering gates cover deterministic compile, corpus, tool, side-effect, and
bundle smokes. This does not implement standalone deployment bundles, secret
manager integration, sandboxing, remote audit services, or LangChain Tool
execution.
```

- [ ] **Step 5: Keep `LANGCHAIN_TOOL` reserved wording current**

In `README.md`, `AGENTS.md`, and `CLAUDE.md`, make sure existing `LANGCHAIN_TOOL`
notes say v0.4 keeps it reserved/experimental and does not provide end-to-end
execution. Use this wording if the current text is stale:

```markdown
- `LANGCHAIN_TOOL` remains reserved/experimental in v0.4 and is not a default
  executable capability. Use trusted Python tool modules plus
  `ExecutorType.PYTHON_CALLABLE` for the v0.4 tool execution path.
```

- [ ] **Step 6: Search docs for overclaims**

Run:

```bash
rg -n "runtime config|RuntimeConfig|deployable|secret manager|LANGCHAIN_TOOL|benchmark|3C" README.md AGENTS.md CLAUDE.md tests/prompts_skills_test/README.md docs/prompt2langgraph-v0.4-开发计划文档.md
```

Expected: output shows 3C behavior documented and does not claim standalone deployment, secret manager, sandbox, or LangChain Tool execution.

- [ ] **Step 7: Commit documentation if allowed**

Run only after user approval:

```bash
git add README.md AGENTS.md CLAUDE.md tests/prompts_skills_test/README.md docs/prompt2langgraph-v0.4-开发计划文档.md
git commit -m "docs: document phase3c runtime config bundles"
```

Expected: commit succeeds if commits are allowed.

---

### Task 9: Final Regression

**Files:**
- Test only

- [ ] **Step 1: Run focused Phase 3C tests**

Run:

```bash
uv run pytest tests/test_artifacts.py tests/test_bundle_golden.py tests/test_engineering_gates.py -v
```

Expected: all focused 3C tests pass.

- [ ] **Step 2: Run CLI and compile flow tests**

Run:

```bash
uv run pytest tests/test_cli_tool_module.py tests/test_cli.py tests/test_compile_flow.py tests/test_public_api.py -v
```

Expected: all CLI/public compile tests pass.

- [ ] **Step 3: Run runtime governance smoke suites**

Run:

```bash
uv run pytest tests/test_runner.py tests/test_side_effect_executor.py tests/test_integration_execution.py -v
```

Expected: all runtime governance smoke tests pass.

- [ ] **Step 4: Run prompt/skill offline corpus tests**

Run:

```bash
uv run pytest tests/test_prompt_pipeline.py tests/test_skill_workflow.py tests/test_prompt_skill_corpus.py -v
```

Expected: all prompt/skill offline tests pass and no network is required.

- [ ] **Step 5: Run full test suite**

Run:

```bash
uv run pytest
```

Expected: all tests pass.

- [ ] **Step 6: Commit final verification note if needed**

No code commit is required for this step. If any prior commit was skipped because commit approval was unavailable, record the uncommitted file list and the exact passing/failing test commands in the final handoff.

---

## Final Verification Checklist

- [ ] `uv run pytest tests/test_artifacts.py tests/test_bundle_golden.py tests/test_engineering_gates.py -v` passes.
- [ ] `uv run pytest tests/test_cli_tool_module.py tests/test_cli.py tests/test_compile_flow.py tests/test_public_api.py -v` passes.
- [ ] `uv run pytest tests/test_runner.py tests/test_side_effect_executor.py tests/test_integration_execution.py -v` passes.
- [ ] `uv run pytest tests/test_prompt_pipeline.py tests/test_skill_workflow.py tests/test_prompt_skill_corpus.py -v` passes.
- [ ] `uv run pytest` passes.
- [ ] Generated `graph.py` has `RuntimeConfig`, `build_graph(config=None)`, `invoke(input_payload=None, config=None)`, `compile_graph()`, and `invoke_graph()`.
- [ ] Dynamic tool bundle can be compiled with injected executor/tool registries and invoked with a generated `RuntimeConfig` tool registry.
- [ ] CLI `compile --tool-module` can compile an authorized simplified JSON plan with custom `python_callable` refs.
- [ ] CLI `compile --tool-module` rejects unauthorized or malformed tool-module workflows with stable diagnostics and no traceback.
- [ ] Manifest `runtime_requirements` lists model refs, tool refs, checkpoint requirement, and policy summary without secrets or secret names.
- [ ] Golden bundle snapshots match generated artifacts.
- [ ] Engineering gates remain offline and avoid brittle performance thresholds.
- [ ] `LANGCHAIN_TOOL` remains documented as reserved/experimental, not as a v0.4 executable path.
- [ ] Documentation states 3C behavior without implying deployable bundles, secret manager integration, sandboxing, remote audit, or LangChain Tool execution.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-02-v04-phase3c-runtime-config-bundle.md`. Two execution options:

1. Subagent-Driven (recommended) - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. Inline Execution - execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
