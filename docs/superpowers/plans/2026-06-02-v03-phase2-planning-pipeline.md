# prompt2langgraph v0.3 Phase 2 Planning Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement v0.3 Phase 2 Prompt/Skill planning reliability so generated plans are parsed, diagnosed, optionally repaired, validated, compile-smoked, and evaluated offline.

**Architecture:** Keep `WorkflowSpec`, `JSONPlanAdapter`, `validate_workflow()`, and `compile_workflow_to_graph()` as existing boundaries. Add a focused `prompting.pipeline` layer that orchestrates generation, parse, adapter, validation, compile smoke, repair attempts, and structured diagnostics while preserving the old `plan_*_to_workflow_spec()` compatibility behavior.

**Tech Stack:** Python 3.12, Pydantic, Typer CLI, pytest, existing builtin executor registry, existing fake model test style, offline corpus fixtures.

---

## Repository Rules For This Plan

- Project root: `/Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph`.
- Source root: `src/prompt2langgraph`.
- Test root: `tests`.
- Use `apply_patch` for manual edits.
- Do not run network calls.
- Do not commit unless the user explicitly authorizes git commit. Checkpoint steps mean inspect status and prepare a concise summary only.
- Preserve unrelated dirty worktree changes.
- After all implementation tasks, run `uv run pytest`.

## Source Spec

Implement the project-level plan in:

- `docs/prompt2langgraph-v0.3-第二期实施计划.md`

Core contracts:

- `parse_prompt_plan_text()` keeps its signature and raises `AdapterParseError` on failure.
- `plan_prompt_to_workflow_spec()` and `plan_skill_to_workflow_spec()` keep compatibility behavior and do not default to validation or compile smoke.
- New `plan_prompt()` and `plan_skill()` structured APIs live in `src/prompt2langgraph/prompting/pipeline.py`.
- CLI `--validate` outputs validation only; CLI `--compile-smoke` outputs validation and compile smoke.
- Default tests stay offline and deterministic.

## File Map

- Modify: `src/prompt2langgraph/prompting/parser.py`
  - Extract single JSON objects from fenced blocks and wrapped text.
  - Reject multiple object candidates.

- Create: `src/prompt2langgraph/prompting/pipeline.py`
  - Define stage/result models.
  - Implement prompt and skill planning pipelines.
  - Implement repair attempts and compile smoke.

- Modify: `src/prompt2langgraph/prompting/planner.py`
  - Add `repair_attempts` to `PromptPlanRequest`.
  - Keep compatibility wrapper behavior.

- Modify: `src/prompt2langgraph/prompting/skill_planner.py`
  - Add `repair_attempts` to `SkillPlanRequest`.
  - Keep compatibility wrapper behavior and `analysis` injection.

- Modify: `src/prompt2langgraph/prompting/__init__.py`
  - Export pipeline APIs and result models.

- Modify: `src/prompt2langgraph/__init__.py`
  - Export pipeline APIs and result models.

- Modify: `src/prompt2langgraph/cli.py`
  - Add `--repair-attempts` and `--compile-smoke`.
  - Route prompt and skill planning through structured pipeline.

- Modify: `tests/test_prompt_parser.py`
  - Add parser robustness tests.

- Create: `tests/test_prompt_pipeline.py`
  - Add prompt/skill pipeline tests.

- Modify: `tests/test_prompt_planner.py`
  - Add request field and compatibility wrapper regression tests.

- Modify: `tests/test_skill_workflow.py`
  - Add request field and compatibility wrapper regression tests.

- Modify: `tests/test_public_api.py`
  - Add public exports for structured pipeline APIs.

- Modify: `tests/test_cli.py`
  - Add CLI compile smoke and repair tests.

- Modify: `tests/test_prompt_skill_corpus.py`
  - Add offline pipeline metric coverage.

- Modify docs after code behavior is final:
  - `README.md`
  - `CLAUDE.md`
  - `AGENTS.md`
  - `docs/prompt2langgraph-v0.3-开发计划文档.md`
  - `tests/prompts_skills_test/README.md`

## Task 1: Parser Robustness

**Files:**

- Modify: `tests/test_prompt_parser.py`
- Modify: `src/prompt2langgraph/prompting/parser.py`

**Current source facts used by this task:**

- `parse_prompt_plan_text(text, *, source="prompt") -> dict[str, Any]` exists.
- It currently calls `json.loads(text)` directly.
- Tests already import `pytest`, `AdapterParseError`, and `parse_prompt_plan_text`.

- [ ] **Step 1: Add failing parser tests**

Append to `tests/test_prompt_parser.py`:

```python
def test_parse_prompt_plan_text_accepts_fenced_json_object() -> None:
    plan = parse_prompt_plan_text(
        'Here is the plan:\n```json\n{"name":"Demo","nodes":[{"id":"compose","kind":"llm","executor":"builtin.echo_llm"}],"edges":[]}\n```'
    )

    assert plan["name"] == "Demo"


def test_parse_prompt_plan_text_accepts_single_object_inside_explanation() -> None:
    plan = parse_prompt_plan_text(
        'I will return one object: {"name":"Wrapped","nodes":[{"id":"compose","kind":"llm","executor":"builtin.echo_llm"}],"edges":[]} Done.'
    )

    assert plan["name"] == "Wrapped"


def test_parse_prompt_plan_text_accepts_object_then_suffix_text() -> None:
    plan = parse_prompt_plan_text(
        '{"name":"Suffix","nodes":[{"id":"compose","kind":"llm","executor":"builtin.echo_llm"}],"edges":[]} trailing explanation'
    )

    assert plan["name"] == "Suffix"


def test_parse_prompt_plan_text_rejects_multiple_json_objects() -> None:
    with pytest.raises(AdapterParseError) as exc_info:
        parse_prompt_plan_text(
            '{"name":"One","nodes":[],"edges":[]} {"name":"Two","nodes":[],"edges":[]}'
        )

    assert "multiple JSON objects" in str(exc_info.value)
    assert exc_info.value.source == "prompt"
    assert exc_info.value.path == "generated_text"


def test_parse_prompt_plan_text_rejects_fenced_and_body_json_objects() -> None:
    with pytest.raises(AdapterParseError) as exc_info:
        parse_prompt_plan_text(
            '```json\n{"name":"One","nodes":[],"edges":[]}\n```\n'
            '{"name":"Two","nodes":[],"edges":[]}'
        )

    assert "multiple JSON objects" in str(exc_info.value)
    assert exc_info.value.path == "generated_text"


def test_parse_prompt_plan_text_rejects_truncated_wrapped_json() -> None:
    with pytest.raises(AdapterParseError) as exc_info:
        parse_prompt_plan_text('prefix {"name":"Broken","nodes":[')

    assert "failed to parse" in str(exc_info.value) or "could not extract" in str(exc_info.value)
    assert exc_info.value.source == "prompt"
```

- [ ] **Step 2: Run parser tests and verify failure**

Run:

```bash
uv run pytest tests/test_prompt_parser.py -v
```

Expected: the new wrapped/fenced/suffix tests fail before implementation.

- [ ] **Step 3: Implement robust JSON object extraction**

Replace `src/prompt2langgraph/prompting/parser.py` with:

```python
from __future__ import annotations

import json
import re
from typing import Any

from prompt2langgraph.adapters.base import AdapterParseError

_FENCED_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def _json_object_candidates(text: str) -> list[tuple[str, int]]:
    decoder = json.JSONDecoder()
    candidates: list[tuple[str, int]] = []
    index = 0
    while index < len(text):
        start = text.find("{", index)
        if start == -1:
            break
        try:
            value, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(value, dict):
            candidates.append((text[start : start + end], start))
            index = start + end
        else:
            index = start + 1
    return candidates


def _candidate_search_texts(text: str) -> list[tuple[str, int]]:
    fenced = [(match.group(1), match.start(1)) for match in _FENCED_BLOCK_RE.finditer(text)]
    return [*fenced, (text, 0)]


def _extract_single_json_object_text(text: str, *, source: str) -> tuple[str, int]:
    candidates: list[tuple[str, int]] = []
    seen_spans: set[tuple[int, int]] = set()
    for search_text, base_offset in _candidate_search_texts(text):
        for candidate, offset in _json_object_candidates(search_text):
            start = base_offset + offset
            end = start + len(candidate)
            if (start, end) in seen_spans:
                continue
            seen_spans.add((start, end))
            candidates.append((candidate, start))

    if len(candidates) > 1:
        raise AdapterParseError(
            "generated JSON plan contains multiple JSON objects",
            source=source,
            path="generated_text",
        )
    if len(candidates) == 1:
        return candidates[0]
    return text, 0


def parse_prompt_plan_text(text: str, *, source: str = "prompt") -> dict[str, Any]:
    candidate_text, candidate_offset = _extract_single_json_object_text(text, source=source)
    try:
        data = json.loads(candidate_text)
    except json.JSONDecodeError as exc:
        raise AdapterParseError(
            "failed to parse generated JSON plan",
            source=source,
            path=str(candidate_offset + exc.pos),
            line=exc.lineno,
            column=exc.colno,
        ) from exc
    if not isinstance(data, dict):
        raise AdapterParseError(
            "generated JSON plan must contain an object",
            source=source,
        )
    return data
```

- [ ] **Step 4: Run parser tests and verify pass**

Run:

```bash
uv run pytest tests/test_prompt_parser.py -v
```

Expected: all parser tests pass.

- [ ] **Step 5: Checkpoint**

Run:

```bash
git status --short
```

Expected: only `src/prompt2langgraph/prompting/parser.py` and `tests/test_prompt_parser.py` are changed for this task.

## Task 2: Pipeline Models And Prompt Success Path

**Files:**

- Create: `src/prompt2langgraph/prompting/pipeline.py`
- Create: `tests/test_prompt_pipeline.py`

**Current source facts used by this task:**

- `PromptPlanRequest` exists in `prompting/planner.py`.
- `generate_plan_text(request, model_client=...)` returns `PromptPlanResult(raw_text=...)`.
- `JSONPlanAdapter().parse(plan, source="prompt")` returns `WorkflowSpec`.
- `validate_workflow(workflow, executors=..., tool_registry=...)` returns `ValidationReport`.
- `validate_workflow()` only checks tool callable registration when `tool_registry` is explicitly non-`None`; pipeline defaults must preserve that compatibility behavior.
- `compile_workflow_to_graph(workflow, executors)` returns a compiled graph or raises.
- Pipeline snippets type request objects as `Any` only to avoid eager importing planner modules at CLI import time; prompt requests must expose `prompt`, `model`, `base_url`, `api_key`, `temperature`, and later `repair_attempts`.

- [ ] **Step 1: Add prompt pipeline success test**

Create `tests/test_prompt_pipeline.py` with:

```python
from prompt2langgraph.prompting.pipeline import plan_prompt
from prompt2langgraph.prompting.planner import PromptPlanRequest


class _FakeModel:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls = 0

    def invoke(self, messages):
        response = self.responses[self.calls]
        self.calls += 1
        return type("Response", (), {"content": response})()


def _valid_plan_text() -> str:
    return (
        '{"name":"Demo","inputs":{"question":"string"},"outputs":{"answer":"string"},'
        '"nodes":[{"id":"compose","kind":"llm","executor":"builtin.echo_llm"}],'
        '"edges":[]}'
    )


def test_prompt_pipeline_reports_all_success_stages() -> None:
    result = plan_prompt(
        PromptPlanRequest(prompt="answer a question"),
        model_client=_FakeModel([_valid_plan_text()]),
        compile_smoke=True,
    )

    assert result.ok is True
    assert result.plan is not None
    assert result.workflow is not None
    assert result.validation_report is not None
    assert result.validation_report.ok is True
    assert result.stages["generation"].ok is True
    assert result.stages["parse"].ok is True
    assert result.stages["adapter"].ok is True
    assert result.stages["validation"].ok is True
    assert result.stages["compile_smoke"].ok is True
```

- [ ] **Step 2: Run the new test and verify import failure**

Run:

```bash
uv run pytest tests/test_prompt_pipeline.py::test_prompt_pipeline_reports_all_success_stages -v
```

Expected: FAIL with `ModuleNotFoundError` or import error for `prompt2langgraph.prompting.pipeline`.

- [ ] **Step 3: Create pipeline models and prompt success path**

Create `src/prompt2langgraph/prompting/pipeline.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, Field

from prompt2langgraph.adapters.base import AdapterParseError
from prompt2langgraph.adapters.json_plan import JSONPlanAdapter
from prompt2langgraph.compiler.langgraph_py import compile_workflow_to_graph
from prompt2langgraph.diagnostics.codes import E_PARSE_001, E_RUNTIME_010, E_SCHEMA_002
from prompt2langgraph.diagnostics.report import (
    Diagnostic,
    DiagnosticLocation,
    ValidationReport,
)
from prompt2langgraph.ir.models import WorkflowSpec
from prompt2langgraph.prompting.parser import parse_prompt_plan_text
from prompt2langgraph.registry.builtins import builtin_executor_registry
from prompt2langgraph.registry.executors import ExecutorRegistry
from prompt2langgraph.registry.tool_executor import ToolCallableRegistry
from prompt2langgraph.validate.validator import validate_workflow

PlanningSource = Literal["prompt", "skill"]
PlanningStageName = Literal["generation", "parse", "adapter", "validation", "compile_smoke"]
STAGE_NAMES: tuple[PlanningStageName, ...] = (
    "generation",
    "parse",
    "adapter",
    "validation",
    "compile_smoke",
)


class PlanningStageStatus(BaseModel):
    ran: bool = False
    ok: bool = False
    skipped: bool = False
    reason: str | None = None
    diagnostics: list[Diagnostic] = Field(default_factory=list)


class RepairAttemptRecord(BaseModel):
    attempt_index: int
    trigger_stage: PlanningStageName
    diagnostic_codes: list[str] = Field(default_factory=list)
    raw_text_preview: str = ""
    ok: bool = False


class PlanningPipelineResult(BaseModel):
    ok: bool
    source: PlanningSource
    raw_text: str | None = None
    plan: dict[str, Any] | None = None
    workflow: WorkflowSpec | None = None
    validation_report: ValidationReport | None = None
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    stages: dict[PlanningStageName, PlanningStageStatus] = Field(default_factory=dict)
    repair_attempts: list[RepairAttemptRecord] = Field(default_factory=list)


def _initial_stages() -> dict[PlanningStageName, PlanningStageStatus]:
    return {name: PlanningStageStatus(skipped=True, reason="not run") for name in STAGE_NAMES}


def _ok_stage() -> PlanningStageStatus:
    return PlanningStageStatus(ran=True, ok=True)


def _error_stage(diagnostic: Diagnostic) -> PlanningStageStatus:
    return PlanningStageStatus(ran=True, ok=False, diagnostics=[diagnostic])


def _skip_remaining(
    stages: dict[PlanningStageName, PlanningStageStatus],
    after: PlanningStageName,
) -> None:
    seen = False
    for name in STAGE_NAMES:
        if seen:
            stages[name] = PlanningStageStatus(skipped=True, reason=f"{after} failed")
        if name == after:
            seen = True


def _parse_diagnostic(exc: AdapterParseError, *, source: PlanningSource) -> Diagnostic:
    return Diagnostic(
        code=E_PARSE_001,
        severity="error",
        message=f"failed to parse generated {source} plan",
        location=DiagnosticLocation(
            source=exc.source or source,
            path=exc.path,
            line=exc.line,
            column=exc.column,
        ),
        hint=str(exc),
    )


def _adapter_diagnostic(exc: Exception, *, source: PlanningSource) -> Diagnostic:
    return Diagnostic(
        code=E_PARSE_001 if isinstance(exc, AdapterParseError) else E_SCHEMA_002,
        severity="error",
        message=f"generated {source} plan failed adapter validation",
        location=DiagnosticLocation(source=source),
        hint=str(exc),
    )


def _runtime_diagnostic(exc: Exception, *, source: PlanningSource, stage: str) -> Diagnostic:
    return Diagnostic(
        code=E_RUNTIME_010,
        severity="error",
        message=f"{stage} failed during {source} plan generation",
        location=DiagnosticLocation(source=source),
        hint=str(exc),
    )


def _result_for_raw_text(
    *,
    source: PlanningSource,
    raw_text: str,
    compile_smoke: bool,
    seed_diagnostics: list[Diagnostic] | None = None,
    executor_registry: ExecutorRegistry | None = None,
    tool_registry: ToolCallableRegistry | None = None,
) -> PlanningPipelineResult:
    executors = executor_registry or builtin_executor_registry()
    stages = _initial_stages()
    diagnostics = list(seed_diagnostics or [])
    stages["generation"] = _ok_stage()

    try:
        plan = parse_prompt_plan_text(raw_text, source=source)
    except AdapterParseError as exc:
        diagnostic = _parse_diagnostic(exc, source=source)
        diagnostics.append(diagnostic)
        stages["parse"] = _error_stage(diagnostic)
        _skip_remaining(stages, "parse")
        return PlanningPipelineResult(
            ok=False,
            source=source,
            raw_text=raw_text,
            diagnostics=diagnostics,
            stages=stages,
        )
    stages["parse"] = _ok_stage()

    try:
        workflow = JSONPlanAdapter(executors=executors).parse(plan, source=source)
    except Exception as exc:
        diagnostic = _adapter_diagnostic(exc, source=source)
        diagnostics.append(diagnostic)
        stages["adapter"] = _error_stage(diagnostic)
        _skip_remaining(stages, "adapter")
        return PlanningPipelineResult(
            ok=False,
            source=source,
            raw_text=raw_text,
            plan=plan,
            diagnostics=diagnostics,
            stages=stages,
        )
    stages["adapter"] = _ok_stage()

    validation_report = validate_workflow(workflow, executors=executors, tool_registry=tool_registry)
    stages["validation"] = PlanningStageStatus(
        ran=True,
        ok=validation_report.ok,
        diagnostics=validation_report.diagnostics,
    )
    diagnostics.extend(validation_report.diagnostics)
    if not validation_report.ok:
        _skip_remaining(stages, "validation")
        return PlanningPipelineResult(
            ok=False,
            source=source,
            raw_text=raw_text,
            plan=plan,
            workflow=workflow,
            validation_report=validation_report,
            diagnostics=diagnostics,
            stages=stages,
        )

    if compile_smoke:
        try:
            compile_workflow_to_graph(workflow, executors)
        except Exception as exc:
            diagnostic = _runtime_diagnostic(exc, source=source, stage="compile smoke")
            diagnostics.append(diagnostic)
            stages["compile_smoke"] = _error_stage(diagnostic)
            return PlanningPipelineResult(
                ok=False,
                source=source,
                raw_text=raw_text,
                plan=plan,
                workflow=workflow,
                validation_report=validation_report,
                diagnostics=diagnostics,
                stages=stages,
            )
        stages["compile_smoke"] = _ok_stage()
    else:
        stages["compile_smoke"] = PlanningStageStatus(skipped=True, reason="compile_smoke disabled")

    return PlanningPipelineResult(
        ok=True,
        source=source,
        raw_text=raw_text,
        plan=plan,
        workflow=workflow,
        validation_report=validation_report,
        diagnostics=diagnostics,
        stages=stages,
    )


def _run_with_generation(
    *,
    source: PlanningSource,
    generate: Callable[[], str],
    compile_smoke: bool,
    seed_diagnostics: list[Diagnostic] | None = None,
    executor_registry: ExecutorRegistry | None = None,
    tool_registry: ToolCallableRegistry | None = None,
) -> PlanningPipelineResult:
    try:
        raw_text = generate()
    except Exception as exc:
        diagnostic = _runtime_diagnostic(exc, source=source, stage="LLM call")
        stages = _initial_stages()
        stages["generation"] = _error_stage(diagnostic)
        _skip_remaining(stages, "generation")
        return PlanningPipelineResult(
            ok=False,
            source=source,
            diagnostics=[*(seed_diagnostics or []), diagnostic],
            stages=stages,
        )
    return _result_for_raw_text(
        source=source,
        raw_text=raw_text,
        compile_smoke=compile_smoke,
        seed_diagnostics=seed_diagnostics,
        executor_registry=executor_registry,
        tool_registry=tool_registry,
    )


def plan_prompt(
    request: Any,
    *,
    model_client: object | None = None,
    compile_smoke: bool = False,
    executor_registry: ExecutorRegistry | None = None,
    tool_registry: ToolCallableRegistry | None = None,
) -> PlanningPipelineResult:
    from prompt2langgraph.prompting.planner import generate_plan_text

    return _run_with_generation(
        source="prompt",
        generate=lambda: generate_plan_text(request, model_client=model_client).raw_text,
        compile_smoke=compile_smoke,
        executor_registry=executor_registry,
        tool_registry=tool_registry,
    )
```

- [ ] **Step 4: Run prompt pipeline success test**

Run:

```bash
uv run pytest tests/test_prompt_pipeline.py::test_prompt_pipeline_reports_all_success_stages -v
```

Expected: PASS.

- [ ] **Step 5: Checkpoint**

Run:

```bash
git status --short
```

Expected: `src/prompt2langgraph/prompting/pipeline.py` and `tests/test_prompt_pipeline.py` are present among changed files.

## Task 3: Pipeline Failure Stages And Prompt Repair

**Files:**

- Modify: `src/prompt2langgraph/prompting/pipeline.py`
- Modify: `src/prompt2langgraph/prompting/planner.py`
- Modify: `tests/test_prompt_pipeline.py`
- Modify: `tests/test_prompt_planner.py`

**Current source facts used by this task:**

- `PromptPlanRequest` is a Pydantic model in `planner.py`.
- Fake models in tests expose `.invoke(messages)` and return objects with `.content`.
- `prompting.planner._extract_response_content()` already handles string/list/None content.

- [ ] **Step 1: Add request field test**

Append to `tests/test_prompt_planner.py`:

```python
def test_prompt_plan_request_accepts_repair_attempts() -> None:
    request = PromptPlanRequest(prompt="repair a plan", repair_attempts=2)

    assert request.repair_attempts == 2
```

- [ ] **Step 2: Add prompt pipeline failure and repair tests**

Append to `tests/test_prompt_pipeline.py`:

```python
def test_prompt_pipeline_stops_after_parse_failure() -> None:
    result = plan_prompt(
        PromptPlanRequest(prompt="bad plan"),
        model_client=_FakeModel(["not json"]),
        compile_smoke=True,
    )

    assert result.ok is False
    assert result.stages["generation"].ok is True
    assert result.stages["parse"].ok is False
    assert result.stages["adapter"].skipped is True
    assert result.stages["validation"].skipped is True
    assert result.stages["compile_smoke"].skipped is True
    assert any(diagnostic.code == "E_PARSE_001" for diagnostic in result.diagnostics)


def test_prompt_pipeline_reports_validation_failure() -> None:
    result = plan_prompt(
        PromptPlanRequest(prompt="bad executor"),
        model_client=_FakeModel(
            [
                (
                    '{"name":"Bad","nodes":[{"id":"n1","kind":"llm",'
                    '"executor":"builtin.nonexistent"}],"edges":[]}'
                )
            ]
        ),
        compile_smoke=True,
    )

    assert result.ok is False
    assert result.workflow is not None
    assert result.validation_report is not None
    assert result.validation_report.ok is False
    assert result.stages["validation"].ok is False
    assert result.stages["compile_smoke"].skipped is True


def test_prompt_pipeline_repairs_parse_failure() -> None:
    result = plan_prompt(
        PromptPlanRequest(prompt="repair bad plan", repair_attempts=1),
        model_client=_FakeModel(["not json", _valid_plan_text()]),
        compile_smoke=True,
    )

    assert result.ok is True
    assert len(result.repair_attempts) == 1
    assert result.repair_attempts[0].trigger_stage == "parse"
    assert result.repair_attempts[0].ok is True


def test_prompt_pipeline_can_disable_repair() -> None:
    result = plan_prompt(
        PromptPlanRequest(prompt="repair disabled", repair_attempts=0),
        model_client=_FakeModel(["not json", _valid_plan_text()]),
        compile_smoke=True,
    )

    assert result.ok is False
    assert result.repair_attempts == []
```

- [ ] **Step 3: Run new tests and verify failure**

Run:

```bash
uv run pytest tests/test_prompt_planner.py::test_prompt_plan_request_accepts_repair_attempts tests/test_prompt_pipeline.py::test_prompt_pipeline_repairs_parse_failure -v
```

Expected: FAIL because `repair_attempts` and repair loop are not implemented.

- [ ] **Step 4: Add `repair_attempts` to `PromptPlanRequest`**

Patch `src/prompt2langgraph/prompting/planner.py`:

```python
class PromptPlanRequest(BaseModel):
    prompt: str = Field(min_length=1)
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    repair_attempts: int = Field(default=0, ge=0, le=3)
```

- [ ] **Step 5: Add repair helpers and loop**

Patch `src/prompt2langgraph/prompting/pipeline.py` with these additions:

```python
def _diagnostic_codes(diagnostics: list[Diagnostic]) -> list[str]:
    return [diagnostic.code for diagnostic in diagnostics if diagnostic.severity == "error"]


def _first_failed_stage(result: PlanningPipelineResult) -> PlanningStageName:
    for name in STAGE_NAMES:
        status = result.stages.get(name)
        if status is not None and status.ran and not status.ok:
            return name
    return "generation"


def _build_repair_messages(
    *,
    source: PlanningSource,
    original_goal: str,
    diagnostics: list[Diagnostic],
    raw_text: str | None,
) -> list[dict[str, str]]:
    diagnostic_summary = [
        {
            "code": diagnostic.code,
            "message": diagnostic.message,
            "hint": diagnostic.hint,
        }
        for diagnostic in diagnostics[-5:]
    ]
    raw_preview = (raw_text or "")[:1200]
    return [
        {
            "role": "system",
            "content": (
                "Repair the simplified JSON plan for prompt2langgraph. "
                "Return ONLY one JSON object, no markdown fences or explanations. "
                "Do not include secrets."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Source: {source}\n"
                f"Original goal:\n{original_goal[:1200]}\n\n"
                f"Diagnostics:\n{diagnostic_summary}\n\n"
                f"Previous raw output preview:\n{raw_preview}\n\n"
                "Return a corrected simplified JSON plan object."
            ),
        },
    ]


def _invoke_model_messages(model_client: object, messages: list[dict[str, str]]) -> str:
    from prompt2langgraph.prompting.planner import _extract_response_content

    response = model_client.invoke(messages)
    return _extract_response_content(response)


def _with_repairs(
    *,
    source: PlanningSource,
    initial_result: PlanningPipelineResult,
    model_client: object | None,
    repair_attempts: int,
    original_goal: str,
    compile_smoke: bool,
    seed_diagnostics: list[Diagnostic] | None = None,
    executor_registry: ExecutorRegistry | None = None,
    tool_registry: ToolCallableRegistry | None = None,
) -> PlanningPipelineResult:
    if initial_result.ok or repair_attempts <= 0 or model_client is None:
        return initial_result

    repair_records: list[RepairAttemptRecord] = []
    current = initial_result
    for attempt_index in range(1, repair_attempts + 1):
        trigger_stage = _first_failed_stage(current)
        messages = _build_repair_messages(
            source=source,
            original_goal=original_goal,
            diagnostics=current.diagnostics,
            raw_text=current.raw_text,
        )
        try:
            raw_text = _invoke_model_messages(model_client, messages)
        except Exception as exc:
            diagnostic = _runtime_diagnostic(exc, source=source, stage="repair LLM call")
            current.diagnostics.append(diagnostic)
            repair_records.append(
                RepairAttemptRecord(
                    attempt_index=attempt_index,
                    trigger_stage=trigger_stage,
                    diagnostic_codes=[diagnostic.code],
                    raw_text_preview="",
                    ok=False,
                )
            )
            break

        repaired = _result_for_raw_text(
            source=source,
            raw_text=raw_text,
            compile_smoke=compile_smoke,
            seed_diagnostics=seed_diagnostics,
            executor_registry=executor_registry,
            tool_registry=tool_registry,
        )
        repair_records.append(
            RepairAttemptRecord(
                attempt_index=attempt_index,
                trigger_stage=trigger_stage,
                diagnostic_codes=_diagnostic_codes(current.diagnostics),
                raw_text_preview=raw_text[:200],
                ok=repaired.ok,
            )
        )
        current = repaired
        if current.ok:
            break

    current.repair_attempts = repair_records
    return current
```

Then replace `plan_prompt()` in `pipeline.py` with:

```python
def plan_prompt(
    request: Any,
    *,
    model_client: object | None = None,
    compile_smoke: bool = False,
    executor_registry: ExecutorRegistry | None = None,
    tool_registry: ToolCallableRegistry | None = None,
) -> PlanningPipelineResult:
    from prompt2langgraph.prompting.planner import build_model_client, generate_plan_text

    client = model_client or build_model_client(request)
    initial = _run_with_generation(
        source="prompt",
        generate=lambda: generate_plan_text(request, model_client=client).raw_text,
        compile_smoke=compile_smoke,
        executor_registry=executor_registry,
        tool_registry=tool_registry,
    )
    return _with_repairs(
        source="prompt",
        initial_result=initial,
        model_client=client,
        repair_attempts=request.repair_attempts,
        original_goal=request.prompt,
        compile_smoke=compile_smoke,
        executor_registry=executor_registry,
        tool_registry=tool_registry,
    )
```

- [ ] **Step 6: Run prompt pipeline tests**

Run:

```bash
uv run pytest tests/test_prompt_pipeline.py tests/test_prompt_planner.py::test_prompt_plan_request_accepts_repair_attempts -v
```

Expected: PASS.

- [ ] **Step 7: Checkpoint**

Run:

```bash
git status --short
```

Expected: planner, pipeline, and prompt tests changed.

## Task 4: Skill Pipeline And Static Risk Diagnostics

**Files:**

- Modify: `src/prompt2langgraph/prompting/pipeline.py`
- Modify: `src/prompt2langgraph/prompting/skill_planner.py`
- Modify: `tests/test_prompt_pipeline.py`
- Modify: `tests/test_skill_workflow.py`

**Current source facts used by this task:**

- `SkillPlanRequest` exists in `skill_planner.py`.
- `analyze_skill_dir()` returns `SkillDirectoryAnalysis` with `report.diagnostics`.
- `generate_skill_plan_text(request, analysis=..., model_client=...)` returns `SkillPlanResult`.
- `tests/fixtures/skill_basic` currently produces `E_SEC_007` risk diagnostics.
- Skill requests passed to pipeline must expose `skill_dir`, `params`, `model`, `base_url`, `api_key`, `temperature`, and `repair_attempts`.

- [ ] **Step 1: Add skill request field test**

Append to `tests/test_skill_workflow.py`:

```python
def test_skill_plan_request_accepts_repair_attempts() -> None:
    request = SkillPlanRequest(skill_dir="tests/fixtures/skill_basic", repair_attempts=2)

    assert request.repair_attempts == 2
```

- [ ] **Step 2: Add skill pipeline tests**

Append to `tests/test_prompt_pipeline.py`:

```python
from prompt2langgraph.prompting.pipeline import plan_skill
from prompt2langgraph.prompting.skill_planner import SkillPlanRequest


class _FakeSkillModel:
    def invoke(self, messages):
        content = (
            '{"name":"SkillWorkflow","inputs":{"question":"string"},'
            '"outputs":{"answer":"string"},'
            '"nodes":[{"id":"step_1","kind":"llm","executor":"builtin.echo_llm"}],'
            '"edges":[]}'
        )
        return type("Response", (), {"content": content})()


def test_skill_pipeline_preserves_static_risk_diagnostics() -> None:
    result = plan_skill(
        SkillPlanRequest(skill_dir="tests/fixtures/skill_basic"),
        model_client=_FakeSkillModel(),
        compile_smoke=True,
    )

    assert result.ok is True
    assert any(diagnostic.code == "E_SEC_007" for diagnostic in result.diagnostics)


def test_skill_pipeline_static_error_prevents_generation(tmp_path) -> None:
    model = _FakeModel([_valid_plan_text()])

    result = plan_skill(
        SkillPlanRequest(skill_dir=str(tmp_path)),
        model_client=model,
        compile_smoke=True,
    )

    assert result.ok is False
    assert model.calls == 0
    assert result.stages["generation"].skipped is True
    assert any(diagnostic.severity == "error" for diagnostic in result.diagnostics)
```

- [ ] **Step 3: Run new tests and verify failure**

Run:

```bash
uv run pytest tests/test_skill_workflow.py::test_skill_plan_request_accepts_repair_attempts tests/test_prompt_pipeline.py::test_skill_pipeline_preserves_static_risk_diagnostics -v
```

Expected: FAIL until skill request and `plan_skill()` exist.

- [ ] **Step 4: Add `repair_attempts` to `SkillPlanRequest`**

Patch `src/prompt2langgraph/prompting/skill_planner.py`:

```python
class SkillPlanRequest(BaseModel):
    skill_dir: str
    params: dict[str, str] = Field(default_factory=dict)
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    repair_attempts: int = Field(default=0, ge=0, le=3)
```

- [ ] **Step 5: Implement `plan_skill()`**

Append to `src/prompt2langgraph/prompting/pipeline.py`:

```python
def _skill_static_error_result(
    *,
    diagnostics: list[Diagnostic],
) -> PlanningPipelineResult:
    stages = _initial_stages()
    stages["generation"] = PlanningStageStatus(skipped=True, reason="skill analysis failed")
    _skip_remaining(stages, "generation")
    return PlanningPipelineResult(
        ok=False,
        source="skill",
        diagnostics=diagnostics,
        stages=stages,
    )


def _skill_original_goal(request: Any, analysis: Any) -> str:
    return (
        f"Skill directory: {request.skill_dir}\n"
        f"Skill name: {analysis.name}\n"
        f"Skill description: {analysis.description}\n"
        f"Skill steps: {analysis.steps}\n"
        f"Skill resources: {analysis.resources.model_dump(mode='json')}\n"
        f"Requested params: {getattr(request, 'params', {})}"
    )


def plan_skill(
    request: Any,
    *,
    model_client: object | None = None,
    analysis: Any | None = None,
    compile_smoke: bool = False,
    executor_registry: ExecutorRegistry | None = None,
    tool_registry: ToolCallableRegistry | None = None,
) -> PlanningPipelineResult:
    from prompt2langgraph.adapters.skill_dir import analyze_skill_dir
    from prompt2langgraph.prompting.skill_planner import _build_model_client, generate_skill_plan_text

    analysis = analysis or analyze_skill_dir(request.skill_dir)
    analysis_diagnostics = list(analysis.report.diagnostics)
    fatal_diagnostics = [item for item in analysis_diagnostics if item.severity == "error"]
    if fatal_diagnostics:
        return _skill_static_error_result(diagnostics=analysis_diagnostics)

    client = model_client or _build_model_client(request)
    initial = _run_with_generation(
        source="skill",
        generate=lambda: generate_skill_plan_text(
            request,
            analysis=analysis,
            model_client=client,
        ).raw_text,
        compile_smoke=compile_smoke,
        seed_diagnostics=analysis_diagnostics,
        executor_registry=executor_registry,
        tool_registry=tool_registry,
    )
    return _with_repairs(
        source="skill",
        initial_result=initial,
        model_client=client,
        repair_attempts=request.repair_attempts,
        original_goal=_skill_original_goal(request, analysis),
        compile_smoke=compile_smoke,
        seed_diagnostics=analysis_diagnostics,
        executor_registry=executor_registry,
        tool_registry=tool_registry,
    )
```

- [ ] **Step 6: Run skill pipeline tests**

Run:

```bash
uv run pytest tests/test_prompt_pipeline.py tests/test_skill_workflow.py::test_skill_plan_request_accepts_repair_attempts -v
```

Expected: PASS.

- [ ] **Step 7: Checkpoint**

Run:

```bash
git status --short
```

Expected: skill planner, pipeline, and tests changed.

## Task 5: Public API And Compatibility Wrappers

**Files:**

- Modify: `src/prompt2langgraph/prompting/__init__.py`
- Modify: `src/prompt2langgraph/__init__.py`
- Modify: `src/prompt2langgraph/prompting/planner.py`
- Modify: `src/prompt2langgraph/prompting/skill_planner.py`
- Modify: `tests/test_public_api.py`
- Modify: `tests/test_prompt_planner.py`
- Modify: `tests/test_skill_workflow.py`

**Current source facts used by this task:**

- Public API currently exports `PromptPlanRequest`, `PromptPlanResult`, `SkillPlanRequest`, `SkillPlanResult`, `plan_prompt_to_workflow_spec`, and `plan_skill_to_workflow_spec`.
- Compatibility wrappers currently return `WorkflowSpec` and raise on parse/adapt failures.

- [ ] **Step 1: Add public API export tests**

Append to `tests/test_public_api.py`:

```python
def test_public_api_exports_structured_planning_entrypoints() -> None:
    assert "plan_prompt" in pt2lg.__all__
    assert "plan_skill" in pt2lg.__all__
    assert "plan_prompt_to_workflow_spec" in pt2lg.__all__
    assert "plan_skill_to_workflow_spec" in pt2lg.__all__
    assert "PlanningPipelineResult" in pt2lg.__all__
    assert callable(pt2lg.plan_prompt)
    assert callable(pt2lg.plan_skill)
    assert callable(pt2lg.plan_prompt_to_workflow_spec)
    assert callable(pt2lg.plan_skill_to_workflow_spec)
```

- [ ] **Step 2: Add compatibility wrapper regression tests**

Append to `tests/test_prompt_planner.py`:

```python
def test_plan_prompt_to_workflow_spec_does_not_default_to_validation() -> None:
    from prompt2langgraph.validate.validator import validate_workflow

    class FakeUnknownExecutorModel:
        def invoke(self, messages):
            return type(
                "Response",
                (),
                {
                    "content": (
                        '{"name":"UnknownExecutor",'
                        '"nodes":[{"id":"n1","kind":"llm","executor":"builtin.nonexistent"}],'
                        '"edges":[]}'
                    )
                },
            )()

    workflow = plan_prompt_to_workflow_spec(
        PromptPlanRequest(prompt="unknown executor"),
        model_client=FakeUnknownExecutorModel(),
    )

    assert workflow.workflow_id == "unknownexecutor"
    assert validate_workflow(workflow).ok is False
```

Append to `tests/test_skill_workflow.py`:

```python
def test_plan_skill_to_workflow_spec_does_not_default_to_validation() -> None:
    from prompt2langgraph.validate.validator import validate_workflow

    class FakeUnknownExecutorSkillModel:
        def invoke(self, messages):
            return type(
                "Response",
                (),
                {
                    "content": (
                        '{"name":"UnknownExecutorSkill",'
                        '"nodes":[{"id":"n1","kind":"llm","executor":"builtin.nonexistent"}],'
                        '"edges":[]}'
                    )
                },
            )()

    workflow = plan_skill_to_workflow_spec(
        SkillPlanRequest(skill_dir="tests/fixtures/skill_basic"),
        model_client=FakeUnknownExecutorSkillModel(),
    )

    assert workflow.workflow_id == "unknownexecutorskill"
    assert validate_workflow(workflow).ok is False
```

- [ ] **Step 3: Run export and compatibility tests and verify failure**

Run:

```bash
uv run pytest tests/test_public_api.py::test_public_api_exports_structured_planning_entrypoints -v
```

Expected: FAIL until exports are added.

- [ ] **Step 4: Export structured pipeline APIs from `prompting/__init__.py`**

Patch `src/prompt2langgraph/prompting/__init__.py`:

```python
from prompt2langgraph.prompting.pipeline import (
    PlanningPipelineResult,
    PlanningStageStatus,
    RepairAttemptRecord,
    plan_prompt,
    plan_skill,
)
```

Add these names to `__all__`:

```python
    "PlanningPipelineResult",
    "PlanningStageStatus",
    "RepairAttemptRecord",
    "plan_prompt",
    "plan_skill",
```

- [ ] **Step 5: Export structured pipeline APIs from top-level `__init__.py`**

Patch `src/prompt2langgraph/__init__.py` imports:

```python
from prompt2langgraph.prompting import (
    PlanningPipelineResult,
    PlanningStageStatus,
    PromptPlanRequest,
    PromptPlanResult,
    RepairAttemptRecord,
    SkillPlanRequest,
    SkillPlanResult,
    plan_prompt,
    plan_prompt_to_workflow_spec,
    plan_skill,
    plan_skill_to_workflow_spec,
)
```

Add these names to `__all__`:

```python
    "PlanningPipelineResult",
    "PlanningStageStatus",
    "RepairAttemptRecord",
    "plan_prompt",
    "plan_skill",
    "plan_skill_to_workflow_spec",
```

- [ ] **Step 6: Keep wrappers compatible**

Do not make `plan_prompt_to_workflow_spec()` or `plan_skill_to_workflow_spec()` call validation or compile smoke by default. If delegating to pipeline, call with `compile_smoke=False` and raise `AdapterParseError` when `result.workflow is None`. The simpler acceptable implementation is to leave both wrappers on their current direct `generate -> parse -> adapter` path.

- [ ] **Step 7: Run public and planner tests**

Run:

```bash
uv run pytest tests/test_public_api.py tests/test_prompt_planner.py tests/test_skill_workflow.py -v
```

Expected: PASS.

- [ ] **Step 8: Checkpoint**

Run:

```bash
git status --short
```

Expected: public exports and compatibility tests changed.

## Task 6: CLI Structured Pipeline Integration

**Files:**

- Modify: `src/prompt2langgraph/cli.py`
- Modify: `tests/test_cli.py`

**Current source facts used by this task:**

- `plan()` currently accepts `--prompt`, `--skill-dir`, `--validate`, `--json`, and `--param`.
- Prompt CLI tests monkeypatch `prompt2langgraph.prompting.planner.build_model_client`.
- Skill CLI tests monkeypatch `prompt2langgraph.llm.provider.build_llm_client`.
- Existing output must keep `payload["plan"]`.

- [ ] **Step 1: Add CLI tests**

Append to `tests/test_cli.py`:

```python
def test_prompt_plan_command_compile_smoke_includes_stage_result(monkeypatch) -> None:
    class FakeModel:
        def invoke(self, messages):
            return type(
                "Response",
                (),
                {
                    "content": (
                        '{"name":"Demo","inputs":{"question":"string"},"outputs":{"answer":"string"},'
                        '"nodes":[{"id":"compose","kind":"llm","executor":"builtin.echo_llm"}],'
                        '"edges":[]}'
                    )
                },
            )()

    monkeypatch.setattr(
        "prompt2langgraph.prompting.planner.build_model_client",
        lambda request: FakeModel(),
    )

    result = CliRunner().invoke(
        app,
        ["plan", "--prompt", "build a simple workflow", "--compile-smoke", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["plan"]["name"] == "Demo"
    assert payload["validation"]["ok"] is True
    assert payload["compile_smoke"]["ok"] is True


def test_prompt_plan_command_validate_does_not_emit_compile_smoke(monkeypatch) -> None:
    class FakeModel:
        def invoke(self, messages):
            return type(
                "Response",
                (),
                {
                    "content": (
                        '{"name":"Demo","nodes":[{"id":"compose","kind":"llm",'
                        '"executor":"builtin.echo_llm"}],"edges":[]}'
                    )
                },
            )()

    monkeypatch.setattr(
        "prompt2langgraph.prompting.planner.build_model_client",
        lambda request: FakeModel(),
    )

    result = CliRunner().invoke(
        app,
        ["plan", "--prompt", "build a simple workflow", "--validate", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "validation" in payload
    assert "compile_smoke" not in payload


def test_prompt_plan_command_repair_attempts_are_reported(monkeypatch) -> None:
    class FakeModel:
        def __init__(self) -> None:
            self.calls = 0

        def invoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                return type("Response", (), {"content": "not json"})()
            return type(
                "Response",
                (),
                {
                    "content": (
                        '{"name":"Demo","nodes":[{"id":"compose","kind":"llm",'
                        '"executor":"builtin.echo_llm"}],"edges":[]}'
                    )
                },
            )()

    model = FakeModel()
    monkeypatch.setattr(
        "prompt2langgraph.prompting.planner.build_model_client",
        lambda request: model,
    )

    result = CliRunner().invoke(
        app,
        ["plan", "--prompt", "repair workflow", "--repair-attempts", "1", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert len(payload["repair_attempts"]) == 1


def test_skill_plan_command_compile_smoke_includes_stage_result(monkeypatch) -> None:
    class FakeModel:
        def invoke(self, messages):
            return type(
                "Response",
                (),
                {
                    "content": (
                        '{"name":"SkillDemo","nodes":[{"id":"compose","kind":"llm",'
                        '"executor":"builtin.echo_llm"}],"edges":[]}'
                    )
                },
            )()

    monkeypatch.setattr(
        "prompt2langgraph.llm.provider.build_llm_client",
        lambda config: FakeModel(),
    )

    result = CliRunner().invoke(
        app,
        [
            "plan",
            "--skill-dir",
            "tests/fixtures/skill_basic",
            "--compile-smoke",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["plan"]["name"] == "SkillDemo"
    assert payload["validation"]["ok"] is True
    assert payload["compile_smoke"]["ok"] is True


def test_skill_plan_command_repair_attempts_are_reported(monkeypatch) -> None:
    class FakeModel:
        def __init__(self) -> None:
            self.calls = 0

        def invoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                return type("Response", (), {"content": "not json"})()
            return type(
                "Response",
                (),
                {
                    "content": (
                        '{"name":"SkillDemo","nodes":[{"id":"compose","kind":"llm",'
                        '"executor":"builtin.echo_llm"}],"edges":[]}'
                    )
                },
            )()

    model = FakeModel()
    monkeypatch.setattr(
        "prompt2langgraph.llm.provider.build_llm_client",
        lambda config: model,
    )

    result = CliRunner().invoke(
        app,
        [
            "plan",
            "--skill-dir",
            "tests/fixtures/skill_basic",
            "--repair-attempts",
            "1",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert len(payload["repair_attempts"]) == 1
```

- [ ] **Step 2: Run CLI tests and verify failure**

Run:

```bash
uv run pytest tests/test_cli.py::test_prompt_plan_command_compile_smoke_includes_stage_result -v
```

Expected: FAIL because `--compile-smoke` does not exist.

- [ ] **Step 3: Add CLI options and pass them through**

Patch `src/prompt2langgraph/cli.py` function signatures.

In `plan()` add:

```python
    compile_smoke: bool = typer.Option(False, "--compile-smoke"),  # noqa: B008
    repair_attempts: int = typer.Option(0, "--repair-attempts", min=0, max=3),  # noqa: B008
```

Pass both values to `_run_skill_plan(...)` and `_run_prompt_plan(...)`.

In `_run_prompt_plan(...)` add parameters:

```python
    compile_smoke: bool,
    repair_attempts: int,
```

In `_run_skill_plan(...)` add parameters:

```python
    compile_smoke: bool,
    repair_attempts: int,
```

- [ ] **Step 4: Add CLI payload helpers**

Add these helpers in `src/prompt2langgraph/cli.py` near `_run_prompt_plan()`:

```python
def _stage_payload(status: Any) -> dict[str, Any]:
    payload = status.model_dump(mode="json")
    payload["ok"] = status.ok
    return payload


def _validation_payload(report: ValidationReport | None) -> dict[str, Any]:
    if report is None:
        return {"ok": False, "diagnostics": []}
    payload = report.model_dump(mode="json")
    payload["ok"] = report.ok
    return payload


def _planning_payload(result: Any, *, include_validation: bool, include_compile_smoke: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": result.ok,
        "plan": result.plan,
    }
    if result.diagnostics:
        payload["diagnostics"] = [item.model_dump(mode="json") for item in result.diagnostics]
    if result.repair_attempts:
        payload["repair_attempts"] = [
            item.model_dump(mode="json") for item in result.repair_attempts
        ]
    if include_validation:
        payload["validation"] = _validation_payload(result.validation_report)
    if include_compile_smoke:
        payload["compile_smoke"] = _stage_payload(result.stages["compile_smoke"])
    return payload
```

- [ ] **Step 5: Route prompt CLI through pipeline**

Replace the entire `_run_prompt_plan()` body. Remove the old direct `generate_plan_text()`, `parse_prompt_plan_text()`, adapter, validation, and exception-handling flow from this function; the pipeline result now owns staged diagnostics and runtime errors.

```python
    from prompt2langgraph.prompting.planner import PromptPlanRequest
    from prompt2langgraph.prompting.pipeline import plan_prompt

    request = PromptPlanRequest(
        prompt=prompt,
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
        repair_attempts=repair_attempts,
    )
    result = plan_prompt(request, compile_smoke=compile_smoke)
    payload = _planning_payload(
        result,
        include_validation=validate_output or compile_smoke,
        include_compile_smoke=compile_smoke,
    )
    fallback_text = _json_dumps(result.plan or {})
    _emit(payload, json_output, fallback_text)
    if not result.ok:
        raise typer.Exit(1) from None
```

- [ ] **Step 6: Route skill CLI through pipeline**

Replace the entire `_run_skill_plan()` body after the existing CLI `params` parsing block. Remove the old static-analysis precheck, direct `generate_skill_plan_text()`, direct parse/adapt/validate flow, and exception handling from this function; `plan_skill()` now preserves static diagnostics and emits the staged result.

```python
    from prompt2langgraph.prompting.skill_planner import SkillPlanRequest
    from prompt2langgraph.prompting.pipeline import plan_skill

    request = SkillPlanRequest(
        skill_dir=str(skill_dir),
        params=params,
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
        repair_attempts=repair_attempts,
    )
    result = plan_skill(request, compile_smoke=compile_smoke)
    payload = _planning_payload(
        result,
        include_validation=validate_output or compile_smoke,
        include_compile_smoke=compile_smoke,
    )
    fallback_text = _json_dumps(result.plan or {})
    _emit(payload, json_output, fallback_text)
    if not result.ok:
        raise typer.Exit(1) from None
```

- [ ] **Step 7: Run CLI tests**

Run:

```bash
uv run pytest tests/test_cli.py -v
```

Expected: PASS.

- [ ] **Step 8: Checkpoint**

Run:

```bash
git status --short
```

Expected: CLI and CLI tests changed.

## Task 7: Corpus Pipeline Evaluation

**Files:**

- Modify: `tests/test_prompt_skill_corpus.py`
- Modify: `tests/prompts_skills_test/README.md`

**Current source facts used by this task:**

- `tests/test_prompt_skill_corpus.py` already defines `_build_corpus_executor_registry()`, `_FakePlanModel`, `_offline_plan_for_case()`, `_prompt_to_workflow_cases()`, and `_skill_to_workflow_cases()`.
- Corpus default tests must not call live network.

- [ ] **Step 1: Add pipeline imports**

Patch imports in `tests/test_prompt_skill_corpus.py`:

```python
from prompt2langgraph.prompting.pipeline import plan_prompt, plan_skill
```

- [ ] **Step 2: Add prompt pipeline corpus test**

Append to `tests/test_prompt_skill_corpus.py`:

```python
@pytest.mark.parametrize("case", _prompt_to_workflow_cases(), ids=_case_id)
def test_prompt_skill_corpus_prompt_cases_pass_pipeline_offline(case: dict[str, Any]) -> None:
    data = _load_json(CORPUS / str(case["prompt_file"]))
    assert isinstance(data, dict)

    result = plan_prompt(
        PromptPlanRequest(prompt=str(data["prompt"])),
        model_client=_FakePlanModel(
            _offline_plan_for_case(case),
            expected_message_content=(str(data["prompt"]),),
        ),
        compile_smoke=True,
        executor_registry=_build_corpus_executor_registry(),
    )

    assert result.ok is True
    assert result.stages["parse"].ok is True
    assert result.stages["validation"].ok is True
    assert result.stages["compile_smoke"].ok is True
    assert result.workflow is not None
    _assert_expected_shape(result.workflow, case)
```

- [ ] **Step 3: Add skill pipeline corpus test**

Append to `tests/test_prompt_skill_corpus.py`:

```python
@pytest.mark.parametrize("case", _skill_to_workflow_cases(), ids=_case_id)
def test_prompt_skill_corpus_skill_cases_pass_pipeline_offline(case: dict[str, Any]) -> None:
    skill_dir = CORPUS / str(case["skill_dir"])
    analysis = analyze_skill_dir(skill_dir)

    result = plan_skill(
        SkillPlanRequest(skill_dir=str(skill_dir)),
        analysis=analysis,
        model_client=_FakePlanModel(
            _offline_plan_for_case(case),
            expected_message_content=_skill_expected_message_content(skill_dir, analysis),
        ),
        compile_smoke=True,
        executor_registry=_build_corpus_executor_registry(),
    )

    assert result.ok is True
    assert result.stages["parse"].ok is True
    assert result.stages["validation"].ok is True
    assert result.stages["compile_smoke"].ok is True
    assert result.workflow is not None
    _assert_expected_shape(result.workflow, case)
```

- [ ] **Step 4: Run corpus tests**

Run:

```bash
uv run pytest tests/test_prompt_skill_corpus.py -v
```

Expected: PASS.

- [ ] **Step 5: Update corpus README**

In `tests/prompts_skills_test/README.md`, add a short section:

```markdown
## v0.3 Phase 2 Planning Pipeline Metrics

The default corpus tests exercise Prompt and Skill planning through deterministic fake model responses. The offline gate requires:

- parse success: 100%
- validation success: 100%
- compile smoke success: 100%

Live LLM evaluation is manual only and must not be part of default `pytest`.
```

- [ ] **Step 6: Checkpoint**

Run:

```bash
git status --short
```

Expected: corpus test and corpus README changed.

## Task 8: Documentation Sync And Final Verification

**Files:**

- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `AGENTS.md`
- Modify: `docs/prompt2langgraph-v0.3-开发计划文档.md`
- Review: `docs/prompt2langgraph-v0.3-第二期实施计划.md`

**Current source facts used by this task:**

- Project instructions require README, CLAUDE, and AGENTS sync for documentation changes.
- v0.3 second phase still excludes CLI tool registry, MCP, direct workflow execution from prompts, and `LANGCHAIN_TOOL` execution.

- [ ] **Step 1: Update README**

Add or adjust Prompt/Skill planning text to state:

```markdown
Prompt and Skill planning now use a structured planning pipeline: generation, parse, adapter, validation, and optional compile smoke. `pt2lg plan --validate` reports validation diagnostics. `pt2lg plan --compile-smoke` additionally verifies that the validated workflow can compile to a LangGraph graph without writing a bundle or executing the workflow. `--repair-attempts N` can ask the model to repair invalid generated plan text, but repaired output still re-enters parse, adapter, validation, and compile-smoke checks.
```

- [ ] **Step 2: Update CLAUDE.md and AGENTS.md**

Add the same capability boundary in both files:

```markdown
Prompt/Skill planning uses a structured offline-testable pipeline. Prompt and Skill inputs still generate simplified JSON plan only; they do not directly run workflows. Repair attempts are optional and must re-enter parse/adapt/validate/compile-smoke checks. Default tests must not call live LLM endpoints.
```

- [ ] **Step 3: Update v0.3 project plan**

In `docs/prompt2langgraph-v0.3-开发计划文档.md`, update the second phase completion language to match implemented behavior:

```markdown
第二期完成后，Prompt/Skill planning 具备结构化 pipeline 结果，能区分 generation、parse、adapter、validation 和 compile smoke 阶段；repair attempts 可配置并默认离线可测；Skill 静态风险诊断保留在 planning result 中；默认测试不访问网络。
```

- [ ] **Step 4: Run focused phase 2 tests**

Run:

```bash
uv run pytest tests/test_prompt_parser.py -v
uv run pytest tests/test_prompt_pipeline.py -v
uv run pytest tests/test_prompt_planner.py tests/test_skill_workflow.py -v
uv run pytest tests/test_prompt_skill_corpus.py -v
uv run pytest tests/test_public_api.py tests/test_cli.py -v
uv run pytest tests/test_engineering_gates.py -v
```

Expected: all commands pass.

- [ ] **Step 5: Run full test suite**

Run:

```bash
uv run pytest
```

Expected: full suite passes.

- [ ] **Step 6: Final checkpoint**

Run:

```bash
git status --short
```

Expected: only files listed in this implementation plan are changed. Prepare a concise summary for the user; do not commit unless explicitly asked.

## Self-Review Checklist For Implementers

Before reporting completion:

- Parser supports pure JSON, fenced JSON, wrapped single object, object with suffix text, non-object rejection, invalid JSON rejection, truncated JSON rejection, and multiple object rejection.
- Pipeline result includes `ok`, `source`, `raw_text`, `plan`, `workflow`, `validation_report`, `diagnostics`, `stages`, and `repair_attempts`.
- Prompt and Skill compatibility wrappers do not default to validation or compile smoke.
- CLI `--validate` does not emit `compile_smoke`.
- CLI `--compile-smoke` emits `validation` and `compile_smoke`.
- Corpus pipeline tests inject `_build_corpus_executor_registry()`.
- Default tests do not call network endpoints.
- `uv run pytest` passes.
