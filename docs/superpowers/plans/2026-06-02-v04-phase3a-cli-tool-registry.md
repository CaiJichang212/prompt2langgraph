# v0.4 Phase 3A CLI Tool Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement v0.4 Phase 3A so CLI can load trusted Python tool modules before workflow parsing, run/resume `PYTHON_CALLABLE` tool workflows, and expose Skill planning tool readiness.

**Architecture:** Keep the existing validator, adapter, compiler, and runner boundaries. Add a small CLI runtime-client layer that loads `--tool-module`, builds a `ToolCallableRegistry`, synthesizes dynamic `ExecutorDefinition(type=PYTHON_CALLABLE)`, and passes the same executor registry through parse, validate, and run. Add `ToolReadiness` to the existing planning pipeline as a reporting field only; it does not replace validator security checks.

**Tech Stack:** Python 3.12, Typer CLI, Pydantic, LangGraph runtime, pytest, `ToolCallableRegistry`, `ExecutorRegistry`, existing fake test tools.

---

## Execution Constraints

- This plan contains commit steps because it is an agent execution plan. When executing inside this repository, do not run any `git commit` command unless the user has explicitly approved committing in that session.
- If commits are not approved, still run the listed `git add`/`git commit` steps mentally as checkpoints: leave the worktree changes unstaged or staged according to the active session rules, and record the skipped commit and reason in the task handoff.
- Do not change project configuration, dependency files, or CI files for this phase. Phase 3A must be implemented with current project dependencies.
- Treat every `--tool-module` value as trusted Python import code, not as sandboxed input. The CLI must produce stable diagnostics for import/register failures and must not let module-provided tool refs override existing executor refs.

## Scope

This plan implements only v0.4 Phase 3A:

- CLI `run` / `resume` support `--tool-module <module>`.
- Tool modules expose `register_tools(registry)`.
- Tool refs registered by modules are also registered as dynamic `PYTHON_CALLABLE` executor definitions.
- Workflow source loading uses the synthesized executor registry before JSON plan adaptation.
- CLI run/resume passes the synthesized executor registry and tool registry to `run_workflow()`.
- Planning results expose required, allowed, registered, missing, and unauthorized tool refs.

This plan does not implement retry, audit, side-effect idempotency, runtime config bundle, benchmark gates, or `LANGCHAIN_TOOL` execution.

## Current Source Facts

- `src/prompt2langgraph/cli.py` currently loads the workflow before building runtime clients in `run()` and `resume()`.
- `_build_runtime_clients(workflow)` currently returns `(model_client, tool_registry)` and creates an empty `ToolCallableRegistry()` for `PYTHON_CALLABLE` nodes.
- `_load_workflow_or_report(path)` calls `JSONPlanAdapter().parse(...)` without an injected executor registry.
- `JSONPlanAdapter(executors=...)` already supports executor registry injection.
- `run_workflow(..., executors=..., tool_registry=...)` already accepts both executor and tool registries.
- `ToolCallableRegistry` already supports `register()`, `has()`, `get()`, and `refs()`.
- `ExecutorDefinition(ref=..., type=ExecutorType.PYTHON_CALLABLE, dynamic=True)` is the runtime executor shape needed by `_invoke_executor()`.
- `validate_workflow(..., tool_registry=...)` only runs `check_tool_refs()` when a tool registry is explicitly passed.

## File Structure

- Modify `src/prompt2langgraph/cli.py`: add tool-module loading, runtime client struct, executor registry synthesis, run/resume wiring, and workflow loader registry injection.
- Modify `src/prompt2langgraph/prompting/pipeline.py`: add `ToolReadiness`, compute it after adapter success, and include it in `PlanningPipelineResult`.
- Modify `src/prompt2langgraph/prompting/__init__.py`: add `ToolReadiness` to the lazy planning pipeline export set and `__all__`.
- Modify `src/prompt2langgraph/__init__.py`: add `ToolReadiness` to the lazy planning pipeline export set and `__all__`.
- Modify `tests/test_cli.py`: update tests that patch `_build_runtime_clients()` to return the new runtime client object.
- Create `tests/test_cli_tool_module.py`: focused CLI tool-module tests.
- Modify `tests/test_prompt_pipeline.py`: add tool readiness unit tests.
- Modify `tests/test_cli.py`: assert `pt2lg plan --json` emits `tool_readiness` when the planning result contains it.
- Modify `README.md`, `AGENTS.md`, `CLAUDE.md`, and `docs/prompt2langgraph-v0.4-开发计划文档.md`: document the 3A behavior after implementation.

---

### Task 1: Add CLI Tool Module Run Tests

**Files:**
- Create: `tests/test_cli_tool_module.py`
- Reference: `src/prompt2langgraph/cli.py`

- [ ] **Step 1: Write failing CLI run tests**

Create `tests/test_cli_tool_module.py` with this content:

```python
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from prompt2langgraph.cli import app


def _write_tool_module(tmp_path: Path) -> None:
    module_path = tmp_path / "fake_cli_tools.py"
    module_path.write_text(
        '''
def register_tools(registry):
    def upper(inputs, params):
        return {"answer": str(inputs["question"]).upper()}

    registry.register("fake.upper", upper)
''',
        encoding="utf-8",
    )


def _write_tool_ir(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "workflow_id": "tool_cli_smoke",
                "name": "Tool CLI Smoke",
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
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_tool_json_plan(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "name": "Tool Plan Smoke",
                "workflow_id": "tool_plan_smoke",
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
                "policies": {"allowed_tool_refs": ["fake.upper"]},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_cli_run_loads_tool_module_for_workflow_ir(tmp_path: Path, monkeypatch) -> None:
    _write_tool_module(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    workflow_path = tmp_path / "tool_workflow.json"
    _write_tool_ir(workflow_path)
    input_path = tmp_path / "input.json"
    input_path.write_text('{"question":"hello"}', encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "run",
            str(workflow_path),
            "--input",
            str(input_path),
            "--tool-module",
            "fake_cli_tools",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "succeeded"
    assert payload["output"] == {"answer": "HELLO"}


def test_cli_run_loads_tool_module_before_json_plan_adapter(
    tmp_path: Path, monkeypatch
) -> None:
    _write_tool_module(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    plan_path = tmp_path / "tool_plan.json"
    _write_tool_json_plan(plan_path)
    input_path = tmp_path / "input.json"
    input_path.write_text('{"question":"hello"}', encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "run",
            str(plan_path),
            "--input",
            str(input_path),
            "--tool-module",
            "fake_cli_tools",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "succeeded"
    assert payload["output"] == {"answer": "HELLO"}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
uv run pytest tests/test_cli_tool_module.py -v
```

Expected: both tests fail because Typer reports no such option `--tool-module`.

- [ ] **Step 3: Commit failing tests**

Run:

```bash
git add tests/test_cli_tool_module.py
git commit -m "test: cover CLI tool module run path"
```

Expected: commit succeeds if commits are allowed in the execution environment. If commits are not allowed, keep the file unstaged and record the reason in the task handoff.

---

### Task 2: Implement Tool Module Loading and Workflow Parse Order

**Files:**
- Modify: `src/prompt2langgraph/cli.py`
- Test: `tests/test_cli_tool_module.py`

- [ ] **Step 1: Add runtime client structure and loader helpers**

In `src/prompt2langgraph/cli.py`, add these imports near the top:

```python
import importlib
from dataclasses import dataclass
```

Add this dataclass after `RUN_INPUT_OPTION`:

```python
@dataclass(frozen=True)
class RuntimeClients:
    model_client: Any | None
    tool_registry: Any | None
    executor_registry: Any
```

Add these helpers before `_build_runtime_clients()`:

```python
def _load_tool_modules(
    module_names: list[str],
) -> Any | ValidationReport:
    from prompt2langgraph.registry.tool_executor import ToolCallableRegistry

    class _CliToolCallableRegistry(ToolCallableRegistry):
        def register(self, ref: str, callable: Any) -> None:
            if self.has(ref):
                raise ValueError(f'tool ref "{ref}" is already registered')
            super().register(ref, callable)

    registry = _CliToolCallableRegistry()
    for module_name in module_names:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            return ValidationReport(
                diagnostics=[
                    Diagnostic(
                        code=E_RUNTIME_010,
                        severity="error",
                        message=f'failed to import tool module "{module_name}"',
                        location=DiagnosticLocation(source=module_name),
                        hint=str(exc),
                    )
                ]
            )
        register_tools = getattr(module, "register_tools", None)
        if not callable(register_tools):
            return ValidationReport(
                diagnostics=[
                    Diagnostic(
                        code=E_RUNTIME_010,
                        severity="error",
                        message=f'tool module "{module_name}" must define register_tools(registry)',
                        location=DiagnosticLocation(source=module_name),
                    )
                ]
            )
        try:
            register_tools(registry)
        except Exception as exc:
            return ValidationReport(
                diagnostics=[
                    Diagnostic(
                        code=E_RUNTIME_010,
                        severity="error",
                        message=f'tool module "{module_name}" failed while registering tools',
                        location=DiagnosticLocation(source=module_name),
                        hint=str(exc),
                    )
                ]
            )
    return registry


def _executor_registry_with_tools(tool_registry: Any | None) -> Any | ValidationReport:
    from prompt2langgraph.ir.models import ExecutorType
    from prompt2langgraph.registry.builtins import builtin_executor_registry
    from prompt2langgraph.registry.executors import ExecutorDefinition

    registry = builtin_executor_registry()
    if tool_registry is None:
        return registry
    for ref in tool_registry.refs():
        if registry.has(ref):
            return ValidationReport(
                diagnostics=[
                    Diagnostic(
                        code=E_RUNTIME_010,
                        severity="error",
                        message=f'tool ref "{ref}" cannot override an existing executor ref',
                        location=DiagnosticLocation(source=ref),
                    )
                ]
            )
        registry.register(
            ExecutorDefinition(ref=ref, type=ExecutorType.PYTHON_CALLABLE, dynamic=True)
        )
    return registry
```

- [ ] **Step 2: Update workflow loaders to accept executor registry**

Replace the signatures and adapter construction:

```python
def _load_workflow_or_report(
    path: Path,
    *,
    executors: Any | None = None,
) -> WorkflowSpec | ValidationReport:
```

Inside the function, replace:

```python
return JSONPlanAdapter().parse(raw, source=str(path))
```

with:

```python
return JSONPlanAdapter(executors=executors).parse(raw, source=str(path))
```

Replace `_load_workflow_source_or_report` with:

```python
def _load_workflow_source_or_report(
    path: Path,
    *,
    executors: Any | None = None,
) -> WorkflowSpec | ValidationReport:
    if path.name == "workflow.lock.json":
        try:
            from prompt2langgraph.runtime.artifacts import load_bundle_workflow

            return load_bundle_workflow(path)
        except (OSError, ValueError, json.JSONDecodeError, ValidationError) as exc:
            return ValidationReport(
                diagnostics=[
                    Diagnostic(
                        code=E_PARSE_001,
                        severity="error",
                        message=f'failed to load workflow bundle "{path}"',
                        location=DiagnosticLocation(source=str(path)),
                        hint=str(exc),
                    )
                ]
            )
    return _load_workflow_or_report(path, executors=executors)
```

- [ ] **Step 3: Update `_build_runtime_clients()`**

Replace `_build_runtime_clients()` with:

```python
def _build_runtime_clients(
    workflow: WorkflowSpec,
    *,
    loaded_tool_registry: Any | None = None,
    executor_registry: Any | None = None,
) -> RuntimeClients:
    """Build runtime clients for CLI run/resume."""
    from prompt2langgraph.ir.models import ExecutorType
    from prompt2langgraph.registry.tool_executor import ToolCallableRegistry

    model_client = None
    tool_registry = loaded_tool_registry
    selected_executor_registry = executor_registry or _executor_registry_with_tools(tool_registry)

    has_llm_node = any(n.executor.type is ExecutorType.LLM for n in workflow.nodes)
    has_tool_node = any(n.executor.type is ExecutorType.PYTHON_CALLABLE for n in workflow.nodes)

    if has_llm_node and workflow.policies.external_call:
        from prompt2langgraph.llm.provider import build_llm_client

        model_client = build_llm_client()

    if has_tool_node and tool_registry is None:
        tool_registry = ToolCallableRegistry()

    return RuntimeClients(
        model_client=model_client,
        tool_registry=tool_registry,
        executor_registry=selected_executor_registry,
    )
```

- [ ] **Step 4: Update `run()` option and loading order**

Update the `run()` signature:

```python
def run(
    workflow_json: Path,
    input: Path = RUN_INPUT_OPTION,
    tool_module: list[str] = typer.Option([], "--tool-module"),
    json_output: bool = typer.Option(False, "--json", help="Emit a machine-readable result."),
) -> None:
```

At the top of `run()`, before loading workflow source, insert:

```python
    loaded_tool_registry = _load_tool_modules(tool_module)
    if isinstance(loaded_tool_registry, ValidationReport):
        result_payload = {
            "status": "failed",
            "output": {},
            "diagnostics": [item.model_dump(mode="json") for item in loaded_tool_registry.diagnostics],
        }
        _emit(result_payload, json_output, "run failed")
        raise typer.Exit(1)
    if not tool_module:
        loaded_tool_registry = None
    executor_registry = _executor_registry_with_tools(loaded_tool_registry)
    if isinstance(executor_registry, ValidationReport):
        result_payload = {
            "status": "failed",
            "output": {},
            "diagnostics": [item.model_dump(mode="json") for item in executor_registry.diagnostics],
        }
        _emit(result_payload, json_output, "run failed")
        raise typer.Exit(1)
```

Then replace:

```python
workflow_or_report = _load_workflow_source_or_report(workflow_json)
```

with:

```python
workflow_or_report = _load_workflow_source_or_report(
    workflow_json, executors=executor_registry
)
```

Replace:

```python
model_client, tool_registry = _build_runtime_clients(workflow_or_report)
```

with:

```python
clients = _build_runtime_clients(
    workflow_or_report,
    loaded_tool_registry=loaded_tool_registry,
    executor_registry=executor_registry,
)
```

Update the `run_workflow()` call:

```python
        executors=clients.executor_registry,
        model_client=clients.model_client,
        tool_registry=clients.tool_registry,
```

- [ ] **Step 5: Run Task 1 tests**

Run:

```bash
uv run pytest tests/test_cli_tool_module.py -v
```

Expected: `test_cli_run_loads_tool_module_for_workflow_ir` and `test_cli_run_loads_tool_module_before_json_plan_adapter` pass.

- [ ] **Step 6: Commit implementation**

Run:

```bash
git add src/prompt2langgraph/cli.py tests/test_cli_tool_module.py
git commit -m "feat: load CLI tool modules before workflow parsing"
```

Expected: commit succeeds if commits are allowed.

---

### Task 3: Add CLI Tool Module Failure Diagnostics

**Files:**
- Modify: `tests/test_cli_tool_module.py`
- Modify: `src/prompt2langgraph/cli.py`

- [ ] **Step 1: Add failure tests**

Append these tests to `tests/test_cli_tool_module.py`:

```python
def test_cli_run_without_tool_module_fails_for_python_callable_ir(tmp_path: Path) -> None:
    workflow_path = tmp_path / "tool_workflow.json"
    _write_tool_ir(workflow_path)
    input_path = tmp_path / "input.json"
    input_path.write_text('{"question":"hello"}', encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["run", str(workflow_path), "--input", str(input_path), "--json"],
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert any(
        item["code"] in {"E_BIND_006", "E_SEC_015"}
        and "fake.upper" in item["message"]
        for item in payload["diagnostics"]
    )
    assert "Traceback" not in result.stdout


def test_cli_run_reports_tool_module_without_register_tools(
    tmp_path: Path, monkeypatch
) -> None:
    module_path = tmp_path / "bad_cli_tools.py"
    module_path.write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    workflow_path = tmp_path / "tool_workflow.json"
    _write_tool_ir(workflow_path)
    input_path = tmp_path / "input.json"
    input_path.write_text('{"question":"hello"}', encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "run",
            str(workflow_path),
            "--input",
            str(input_path),
            "--tool-module",
            "bad_cli_tools",
            "--json",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert payload["diagnostics"][0]["code"] == "E_RUNTIME_010"
    assert "register_tools" in payload["diagnostics"][0]["message"]
    assert "Traceback" not in result.stdout


def test_cli_run_reports_duplicate_tool_ref_from_modules(
    tmp_path: Path, monkeypatch
) -> None:
    _write_tool_module(tmp_path)
    duplicate_path = tmp_path / "duplicate_cli_tools.py"
    duplicate_path.write_text(
        '''
def register_tools(registry):
    registry.register("fake.upper", lambda inputs, params: {"answer": "duplicate"})
''',
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    workflow_path = tmp_path / "tool_workflow.json"
    _write_tool_ir(workflow_path)
    input_path = tmp_path / "input.json"
    input_path.write_text('{"question":"hello"}', encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "run",
            str(workflow_path),
            "--input",
            str(input_path),
            "--tool-module",
            "fake_cli_tools",
            "--tool-module",
            "duplicate_cli_tools",
            "--json",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert payload["diagnostics"][0]["code"] == "E_RUNTIME_010"
    assert "already registered" in payload["diagnostics"][0]["hint"]
    assert "Traceback" not in result.stdout


def test_cli_run_rejects_tool_ref_that_overrides_builtin_executor(
    tmp_path: Path, monkeypatch
) -> None:
    module_path = tmp_path / "shadow_cli_tools.py"
    module_path.write_text(
        '''
def register_tools(registry):
    registry.register("builtin.echo_llm", lambda inputs, params: {"answer": "shadowed"})
''',
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    workflow_path = tmp_path / "tool_workflow.json"
    _write_tool_ir(workflow_path)
    input_path = tmp_path / "input.json"
    input_path.write_text('{"question":"hello"}', encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "run",
            str(workflow_path),
            "--input",
            str(input_path),
            "--tool-module",
            "shadow_cli_tools",
            "--json",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert payload["diagnostics"][0]["code"] == "E_RUNTIME_010"
    assert "cannot override" in payload["diagnostics"][0]["message"]
    assert "builtin.echo_llm" in payload["diagnostics"][0]["message"]
    assert "Traceback" not in result.stdout
```

- [ ] **Step 2: Run tests**

Run:

```bash
uv run pytest tests/test_cli_tool_module.py -v
```

Expected: missing-register, duplicate-ref, and builtin-override tests pass through loader diagnostics. The no-module test passes through existing validator or runner diagnostics.

- [ ] **Step 3: Keep diagnostics on existing validation path**

Do not add a special-case CLI diagnostic for missing `--tool-module`. The expected diagnostics must come from existing validator or runner paths. Keep the test assertion broad enough to accept `E_BIND_006` from executor binding or `E_SEC_015` from tool policy checks, but require the message to include `fake.upper`.

- [ ] **Step 4: Commit diagnostics tests**

Run:

```bash
git add tests/test_cli_tool_module.py src/prompt2langgraph/cli.py
git commit -m "test: cover CLI tool module diagnostics"
```

Expected: commit succeeds if commits are allowed.

---

### Task 4: Wire `--tool-module` Through Resume

**Files:**
- Modify: `tests/test_cli_tool_module.py`
- Modify: `src/prompt2langgraph/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add resume test**

Append this helper and test to `tests/test_cli_tool_module.py`:

```python
def _write_human_then_tool_ir(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "0.1",
                "workflow_id": "human_then_tool",
                "name": "Human Then Tool",
                "entrypoint": "approve",
                "state_schema": {
                    "input": {"question": {"type": "string"}},
                    "output": {"answer": {"type": "string"}},
                    "channels": {
                        "question": {"type": "string"},
                        "approval": {"type": "string"},
                        "answer": {"type": "string"},
                    },
                    "private": {},
                    "reducers": {},
                },
                "nodes": [
                    {
                        "id": "approve",
                        "kind": "human_gate",
                        "executor": {"ref": "builtin.human_gate", "type": "builtin"},
                        "inputs": {},
                        "outputs": {"approval": {"state_key": "approval"}},
                        "params": {"message": "Approve tool call?"},
                    },
                    {
                        "id": "call_tool",
                        "kind": "tool",
                        "executor": {"ref": "fake.upper", "type": "python_callable"},
                        "inputs": {"question": {"state_key": "question"}},
                        "outputs": {"answer": {"state_key": "answer"}},
                        "params": {},
                    },
                ],
                "edges": [
                    {
                        "id": "approve_to_tool",
                        "source": "approve",
                        "target": "call_tool",
                        "kind": "linear",
                    }
                ],
                "policies": {"allowed_tool_refs": ["fake.upper"]},
                "metadata": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_cli_resume_uses_tool_module_after_interrupt(tmp_path: Path, monkeypatch) -> None:
    _write_tool_module(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    workflow_path = tmp_path / "human_then_tool.json"
    _write_human_then_tool_ir(workflow_path)

    waiting_result = CliRunner().invoke(
        app,
        [
            "run",
            str(workflow_path),
            "--input",
            '{"question":"hello"}',
            "--tool-module",
            "fake_cli_tools",
            "--json",
        ],
    )
    assert waiting_result.exit_code != 0
    waiting = json.loads(waiting_result.stdout)
    assert waiting["status"] == "waiting"

    resume_result = CliRunner().invoke(
        app,
        [
            "resume",
            str(workflow_path),
            "--thread-id",
            waiting["thread_id"],
            "--resume",
            '"approved"',
            "--tool-module",
            "fake_cli_tools",
            "--json",
        ],
    )

    assert resume_result.exit_code == 0, resume_result.output
    resumed = json.loads(resume_result.stdout)
    assert resumed["status"] == "succeeded"
    assert resumed["output"] == {"answer": "HELLO"}
```

- [ ] **Step 2: Run the resume test and verify it fails**

Run:

```bash
uv run pytest tests/test_cli_tool_module.py::test_cli_resume_uses_tool_module_after_interrupt -v
```

Expected: fails because `resume` does not accept `--tool-module`.

- [ ] **Step 3: Update `resume()` signature and loading order**

Update the `resume()` signature:

```python
def resume(
    workflow_json: Path,
    thread_id: str = typer.Option(..., "--thread-id"),
    resume: str = typer.Option(..., "--resume"),
    tool_module: list[str] = typer.Option([], "--tool-module"),
    json_output: bool = typer.Option(False, "--json", help="Emit a machine-readable result."),
) -> None:
```

At the top of `resume()`, before workflow loading, add the same loading block used in `run()`:

```python
    loaded_tool_registry = _load_tool_modules(tool_module)
    if isinstance(loaded_tool_registry, ValidationReport):
        result_payload = {
            "status": "failed",
            "output": {},
            "diagnostics": [item.model_dump(mode="json") for item in loaded_tool_registry.diagnostics],
        }
        _emit(result_payload, json_output, "resume failed")
        raise typer.Exit(1)
    if not tool_module:
        loaded_tool_registry = None
    executor_registry = _executor_registry_with_tools(loaded_tool_registry)
    if isinstance(executor_registry, ValidationReport):
        result_payload = {
            "status": "failed",
            "output": {},
            "diagnostics": [item.model_dump(mode="json") for item in executor_registry.diagnostics],
        }
        _emit(result_payload, json_output, "resume failed")
        raise typer.Exit(1)
```

Load the workflow with:

```python
workflow_or_report = _load_workflow_source_or_report(
    workflow_json, executors=executor_registry
)
```

Build clients with:

```python
clients = _build_runtime_clients(
    workflow_or_report,
    loaded_tool_registry=loaded_tool_registry,
    executor_registry=executor_registry,
)
```

Pass clients to `run_workflow()`:

```python
        executors=clients.executor_registry,
        model_client=clients.model_client,
        tool_registry=clients.tool_registry,
```

- [ ] **Step 4: Update existing patched test**

In `tests/test_cli.py`, update `test_resume_command_calls_build_runtime_clients()` so the mock returns `RuntimeClients` instead of a tuple:

```python
from prompt2langgraph.cli import RuntimeClients
from prompt2langgraph.registry.builtins import builtin_executor_registry

mock_build.return_value = RuntimeClients(
    model_client=None,
    tool_registry=None,
    executor_registry=builtin_executor_registry(),
)
```

Keep `mock_build.assert_called_once()`.

- [ ] **Step 5: Run CLI tests**

Run:

```bash
uv run pytest tests/test_cli_tool_module.py tests/test_cli.py -v
```

Expected: all CLI tests pass.

- [ ] **Step 6: Commit resume wiring**

Run:

```bash
git add src/prompt2langgraph/cli.py tests/test_cli.py tests/test_cli_tool_module.py
git commit -m "feat: support tool modules during CLI resume"
```

Expected: commit succeeds if commits are allowed.

---

### Task 5: Add Tool Readiness to Planning Pipeline

**Files:**
- Modify: `src/prompt2langgraph/prompting/pipeline.py`
- Modify: `src/prompt2langgraph/prompting/__init__.py`
- Modify: `src/prompt2langgraph/__init__.py`
- Modify: `tests/test_prompt_pipeline.py`

- [ ] **Step 1: Add failing planning tests**

Append these tests to `tests/test_prompt_pipeline.py`:

```python
from prompt2langgraph.ir.models import ExecutorType
from prompt2langgraph.registry.builtins import builtin_executor_registry
from prompt2langgraph.registry.executors import ExecutorDefinition
from prompt2langgraph.registry.tool_executor import ToolCallableRegistry


class FakeToolPlanModel:
    def invoke(self, messages):
        content = (
            '{"name":"ToolPlan","workflow_id":"tool_plan",'
            '"inputs":{"question":"string"},"outputs":{"answer":"string"},'
            '"nodes":[{"id":"call_tool","kind":"tool","executor":"fake.upper",'
            '"inputs":{"question":"question"},"outputs":{"answer":"answer"}}],'
            '"edges":[],"policies":{"allowed_tool_refs":["fake.upper"]}}'
        )
        return type("Response", (), {"content": content})()


class FakeUnauthorizedToolPlanModel:
    def invoke(self, messages):
        content = (
            '{"name":"ToolPlan","workflow_id":"tool_plan",'
            '"inputs":{"question":"string"},"outputs":{"answer":"string"},'
            '"nodes":[{"id":"call_tool","kind":"tool","executor":"fake.upper",'
            '"inputs":{"question":"question"},"outputs":{"answer":"answer"}}],'
            '"edges":[]}'
        )
        return type("Response", (), {"content": content})()


class FakeNodeAuthorizedToolPlanModel:
    def invoke(self, messages):
        content = (
            '{"name":"ToolPlan","workflow_id":"tool_plan",'
            '"inputs":{"question":"string"},"outputs":{"answer":"string"},'
            '"nodes":[{"id":"call_tool","kind":"tool","executor":"fake.upper",'
            '"inputs":{"question":"question"},"outputs":{"answer":"answer"},'
            '"security":{"allowed_tool_refs":["fake.upper"]}}],'
            '"edges":[]}'
        )
        return type("Response", (), {"content": content})()


def _tool_executor_registry():
    registry = builtin_executor_registry()
    registry.register(
        ExecutorDefinition(
            ref="fake.upper",
            type=ExecutorType.PYTHON_CALLABLE,
            dynamic=True,
        )
    )
    return registry


def test_plan_prompt_reports_missing_tool_readiness() -> None:
    from prompt2langgraph.prompting.pipeline import plan_prompt
    from prompt2langgraph.prompting.planner import PromptPlanRequest

    result = plan_prompt(
        PromptPlanRequest(prompt="Use a fake tool"),
        model_client=FakeToolPlanModel(),
        executor_registry=_tool_executor_registry(),
        tool_registry=ToolCallableRegistry(),
    )

    assert result.workflow is not None
    assert result.tool_readiness is not None
    assert result.tool_readiness.required_tool_refs == ["fake.upper"]
    assert result.tool_readiness.allowed_tool_refs == ["fake.upper"]
    assert result.tool_readiness.registered_tool_refs == []
    assert result.tool_readiness.missing_tool_refs == ["fake.upper"]
    assert result.tool_readiness.unauthorized_tool_refs == []


def test_plan_prompt_reports_registered_tool_readiness() -> None:
    from prompt2langgraph.prompting.pipeline import plan_prompt
    from prompt2langgraph.prompting.planner import PromptPlanRequest

    tools = ToolCallableRegistry()
    tools.register("fake.upper", lambda inputs, params: {"answer": "ok"})
    result = plan_prompt(
        PromptPlanRequest(prompt="Use a fake tool"),
        model_client=FakeToolPlanModel(),
        executor_registry=_tool_executor_registry(),
        tool_registry=tools,
    )

    assert result.tool_readiness is not None
    assert result.tool_readiness.registered_tool_refs == ["fake.upper"]
    assert result.tool_readiness.missing_tool_refs == []


def test_plan_prompt_reports_unauthorized_tool_readiness() -> None:
    from prompt2langgraph.prompting.pipeline import plan_prompt
    from prompt2langgraph.prompting.planner import PromptPlanRequest

    tools = ToolCallableRegistry()
    tools.register("fake.upper", lambda inputs, params: {"answer": "ok"})
    result = plan_prompt(
        PromptPlanRequest(prompt="Use a fake tool"),
        model_client=FakeUnauthorizedToolPlanModel(),
        executor_registry=_tool_executor_registry(),
        tool_registry=tools,
    )

    assert result.workflow is not None
    assert result.tool_readiness is not None
    assert result.tool_readiness.required_tool_refs == ["fake.upper"]
    assert result.tool_readiness.allowed_tool_refs == []
    assert result.tool_readiness.unauthorized_tool_refs == ["fake.upper"]


def test_plan_prompt_respects_node_level_tool_readiness_authorization() -> None:
    from prompt2langgraph.prompting.pipeline import plan_prompt
    from prompt2langgraph.prompting.planner import PromptPlanRequest

    tools = ToolCallableRegistry()
    tools.register("fake.upper", lambda inputs, params: {"answer": "ok"})
    result = plan_prompt(
        PromptPlanRequest(prompt="Use a node-authorized fake tool"),
        model_client=FakeNodeAuthorizedToolPlanModel(),
        executor_registry=_tool_executor_registry(),
        tool_registry=tools,
    )

    assert result.ok is True
    assert result.workflow is not None
    assert result.workflow.policies.allowed_tool_refs == []
    assert result.workflow.nodes[0].security is not None
    assert result.workflow.nodes[0].security.allowed_tool_refs == ["fake.upper"]
    assert result.tool_readiness is not None
    assert result.tool_readiness.allowed_tool_refs == ["fake.upper"]
    assert result.tool_readiness.unauthorized_tool_refs == []


def test_plan_skill_reports_tool_readiness() -> None:
    from prompt2langgraph.prompting.pipeline import plan_skill
    from prompt2langgraph.prompting.skill_planner import SkillPlanRequest

    result = plan_skill(
        SkillPlanRequest(skill_dir="tests/fixtures/skill_basic"),
        model_client=FakeToolPlanModel(),
        executor_registry=_tool_executor_registry(),
        tool_registry=ToolCallableRegistry(),
    )

    assert result.source == "skill"
    assert result.workflow is not None
    assert result.tool_readiness is not None
    assert result.tool_readiness.required_tool_refs == ["fake.upper"]
    assert result.tool_readiness.allowed_tool_refs == ["fake.upper"]
    assert result.tool_readiness.missing_tool_refs == ["fake.upper"]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
uv run pytest tests/test_prompt_pipeline.py -v
```

Expected: fails with `PlanningPipelineResult` missing `tool_readiness`.

- [ ] **Step 3: Add `ToolReadiness` model and helper**

In `src/prompt2langgraph/prompting/pipeline.py`, add `ExecutorType` import:

```python
from prompt2langgraph.ir.models import ExecutorType, WorkflowSpec
```

Replace the existing `WorkflowSpec` import line with this combined import.

Add the model after `RepairAttemptRecord`:

```python
class ToolReadiness(BaseModel):
    required_tool_refs: list[str] = Field(default_factory=list)
    allowed_tool_refs: list[str] = Field(default_factory=list)
    registered_tool_refs: list[str] = Field(default_factory=list)
    missing_tool_refs: list[str] = Field(default_factory=list)
    unauthorized_tool_refs: list[str] = Field(default_factory=list)
```

Add a field to `PlanningPipelineResult`:

```python
    tool_readiness: ToolReadiness | None = None
```

Add this helper near `_stage_diagnostic_codes()`:

```python
def _tool_readiness_for(
    workflow: WorkflowSpec,
    tool_registry: ToolCallableRegistry | None,
) -> ToolReadiness:
    required_refs: set[str] = set()
    allowed_refs: set[str] = set()
    unauthorized_refs: set[str] = set()
    for node in workflow.nodes:
        if node.executor.type is not ExecutorType.PYTHON_CALLABLE:
            continue
        ref = node.executor.ref
        required_refs.add(ref)
        if node.security is not None and node.security.allowed_tool_refs is not None:
            effective_allowed = node.security.allowed_tool_refs
        else:
            effective_allowed = workflow.policies.allowed_tool_refs
        allowed_refs.update(effective_allowed or [])
        if not effective_allowed or ref not in effective_allowed:
            unauthorized_refs.add(ref)

    required = sorted(required_refs)
    allowed = sorted(allowed_refs)
    registered = tool_registry.refs() if tool_registry is not None else []
    return ToolReadiness(
        required_tool_refs=required,
        allowed_tool_refs=allowed,
        registered_tool_refs=registered,
        missing_tool_refs=sorted(set(required) - set(registered)),
        unauthorized_tool_refs=sorted(unauthorized_refs),
    )
```

- [ ] **Step 4: Attach readiness after adapter success**

In `_result_for_raw_text()`, after adapter success and before validation:

```python
    tool_readiness = _tool_readiness_for(workflow, tool_registry)
```

In every `PlanningPipelineResult(...)` returned after `workflow=workflow` is available, include:

```python
            tool_readiness=tool_readiness,
```

This includes validation failure, compile smoke failure, and success returns. Do not attach tool readiness before adapter success, because there is no `WorkflowSpec`.

Add `"ToolReadiness"` to `__all__`.

- [ ] **Step 5: Re-export `ToolReadiness` through existing lazy export patterns**

In `src/prompt2langgraph/prompting/__init__.py`, add `"ToolReadiness"` to the `__getattr__` name set and to `__all__`.

In `src/prompt2langgraph/__init__.py`, add `"ToolReadiness"` to the `__getattr__` name set and to `__all__`.

The exact additions are:

```python
        "ToolReadiness",
```

- [ ] **Step 6: Run planning tests**

Run:

```bash
uv run pytest tests/test_prompt_pipeline.py -v
```

Expected: all prompt pipeline tests pass.

- [ ] **Step 7: Commit planning readiness**

Run:

```bash
git add src/prompt2langgraph/prompting/pipeline.py src/prompt2langgraph/prompting/__init__.py src/prompt2langgraph/__init__.py tests/test_prompt_pipeline.py
git commit -m "feat: report tool readiness in planning pipeline"
```

Expected: commit succeeds if commits are allowed.

---

### Task 6: Emit Tool Readiness from CLI Plan

**Files:**
- Modify: `src/prompt2langgraph/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add CLI JSON output test**

Add this test to `tests/test_cli.py`:

```python
def test_plan_command_outputs_tool_readiness(monkeypatch) -> None:
    from prompt2langgraph.prompting.pipeline import ToolReadiness

    class FakeResult:
        ok = True
        plan = {"name": "ToolPlan", "nodes": [], "edges": []}
        diagnostics = []
        repair_attempts = []
        validation_report = None
        stages = {}
        tool_readiness = ToolReadiness(
            required_tool_refs=["fake.upper"],
            allowed_tool_refs=["fake.upper"],
            registered_tool_refs=[],
            missing_tool_refs=["fake.upper"],
            unauthorized_tool_refs=[],
        )

    monkeypatch.setattr(
        "prompt2langgraph.prompting.plan_prompt",
        lambda *args, **kwargs: FakeResult(),
    )

    result = CliRunner().invoke(
        app,
        ["plan", "--prompt", "Use a fake tool", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["tool_readiness"]["required_tool_refs"] == ["fake.upper"]
    assert payload["tool_readiness"]["missing_tool_refs"] == ["fake.upper"]


def test_plan_skill_command_outputs_tool_readiness(monkeypatch) -> None:
    from prompt2langgraph.prompting.pipeline import ToolReadiness

    class FakeResult:
        ok = True
        plan = {"name": "SkillToolPlan", "nodes": [], "edges": []}
        diagnostics = []
        repair_attempts = []
        validation_report = None
        stages = {}
        tool_readiness = ToolReadiness(
            required_tool_refs=["fake.upper"],
            allowed_tool_refs=["fake.upper"],
            registered_tool_refs=[],
            missing_tool_refs=["fake.upper"],
            unauthorized_tool_refs=[],
        )

    monkeypatch.setattr(
        "prompt2langgraph.prompting.plan_skill",
        lambda *args, **kwargs: FakeResult(),
    )

    result = CliRunner().invoke(
        app,
        ["plan", "--skill-dir", "tests/fixtures/skill_basic", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["tool_readiness"]["required_tool_refs"] == ["fake.upper"]
    assert payload["tool_readiness"]["missing_tool_refs"] == ["fake.upper"]
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
uv run pytest tests/test_cli.py::test_plan_command_outputs_tool_readiness tests/test_cli.py::test_plan_skill_command_outputs_tool_readiness -v
```

Expected: both tests fail because `_emit_planning_result()` does not include `tool_readiness`.

- [ ] **Step 3: Emit readiness in `_emit_planning_result()`**

In `src/prompt2langgraph/cli.py`, after repair attempts are emitted, add:

```python
    tool_readiness = getattr(result, "tool_readiness", None)
    if tool_readiness is not None:
        payload["tool_readiness"] = tool_readiness.model_dump(mode="json")
```

- [ ] **Step 4: Run CLI plan test**

Run:

```bash
uv run pytest tests/test_cli.py::test_plan_command_outputs_tool_readiness tests/test_cli.py::test_plan_skill_command_outputs_tool_readiness -v
```

Expected: both tests pass.

- [ ] **Step 5: Commit CLI readiness output**

Run:

```bash
git add src/prompt2langgraph/cli.py tests/test_cli.py
git commit -m "feat: emit tool readiness from plan command"
```

Expected: commit succeeds if commits are allowed.

---

### Task 7: Documentation and Regression

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Modify: `docs/prompt2langgraph-v0.4-开发计划文档.md`

- [ ] **Step 1: Update README**

Add a short section near runtime tool documentation:

```markdown
### CLI Tool Module

`pt2lg run` and `pt2lg resume` can load trusted Python tool modules with
`--tool-module <module>`. The module must define `register_tools(registry)`
and register callables through `ToolCallableRegistry.register(ref, callable)`.

Tool execution still requires workflow policy authorization through
`allowed_tool_refs`. The CLI loads the tool module before workflow parsing so
simplified JSON plans can reference custom `python_callable` executor refs.
This is not a sandbox and does not execute arbitrary shell commands. Tool refs
must be unique across loaded modules and cannot override built-in or existing
executor refs.
```

- [ ] **Step 2: Update AGENTS and CLAUDE**

Add equivalent concise notes:

```markdown
- CLI `run` / `resume` 支持 `--tool-module <module>` 加载受信任 Python module。
- module 必须暴露 `register_tools(registry)`，并通过 `ToolCallableRegistry.register(ref, callable)` 注册工具。
- tool module 必须先于 workflow parse/load 加载；简化 JSON plan 的自定义 tool ref 依赖该顺序。
- `--tool-module` 不是 sandbox，不支持任意 shell；tool 执行仍需 `allowed_tool_refs` 授权。
- tool ref 不允许重复注册，也不允许覆盖内置或既有 executor ref。
```

- [ ] **Step 3: Update v0.4 development plan status**

In `docs/prompt2langgraph-v0.4-开发计划文档.md`, update the 3A section to mark CLI tool registry loading and Skill required tool refs as implemented after tests pass. Use wording that does not imply retry, audit, idempotency, or runtime config bundle are done.

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/test_cli_tool_module.py tests/test_cli.py tests/test_prompt_pipeline.py -v
```

Expected: all focused tests pass.

- [ ] **Step 5: Run security and integration tests**

Run:

```bash
uv run pytest tests/test_tool_executor.py tests/test_security_policy.py tests/test_integration_execution.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Run full test suite**

Run:

```bash
uv run pytest
```

Expected: all tests pass.

- [ ] **Step 7: Commit documentation and regression**

Run:

```bash
git add README.md AGENTS.md CLAUDE.md docs/prompt2langgraph-v0.4-开发计划文档.md
git commit -m "docs: document v04 phase3a tool module workflow"
```

Expected: commit succeeds if commits are allowed.

---

## Final Verification Checklist

- [ ] `uv run pytest tests/test_cli_tool_module.py -v` passes.
- [ ] `uv run pytest tests/test_cli.py -v` passes.
- [ ] `uv run pytest tests/test_prompt_pipeline.py -v` passes.
- [ ] `uv run pytest tests/test_tool_executor.py tests/test_security_policy.py tests/test_integration_execution.py -v` passes.
- [ ] `uv run pytest` passes.
- [ ] CLI `run` supports `--tool-module` for canonical Workflow IR.
- [ ] CLI `run` supports `--tool-module` for simplified JSON plan before adapter parsing.
- [ ] CLI `resume` supports `--tool-module` after an interrupt.
- [ ] CLI rejects duplicate tool refs from loaded modules with `E_RUNTIME_010`.
- [ ] CLI rejects tool refs that would override built-in or existing executor refs with `E_RUNTIME_010`.
- [ ] Planning results include `tool_readiness` in Python API.
- [ ] Planning `tool_readiness` respects node-level `security.allowed_tool_refs` before workflow-level `policies.allowed_tool_refs`.
- [ ] Prompt and Skill planning both include `tool_readiness` in Python API.
- [ ] CLI `pt2lg plan --prompt ... --json` and `pt2lg plan --skill-dir ... --json` include `tool_readiness` when present.
- [ ] Documentation states that `--tool-module` is trusted Python code, not a sandbox.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-02-v04-phase3a-cli-tool-registry.md`. Two execution options:

1. Subagent-Driven (recommended) - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. Inline Execution - execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
