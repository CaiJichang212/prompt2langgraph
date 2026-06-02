# prompt2langgraph v0.4 Phase 1 Plan Semantics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement v0.4 Phase 1 Plan semantic fidelity so simplified JSON plans preserve `workflow_id`, `metadata`, reducers, policies, and join semantics across Prompt, Skill, validation, compile, run, and docs.

**Architecture:** Keep `WorkflowSpec` as the canonical IR and make `JSONPlanAdapter` the only simplified JSON plan normalization boundary. Update Prompt and Skill planner instructions to emit fields already supported by the adapter, then lock behavior with offline tests and CLI smoke fixtures.

**Tech Stack:** Python 3.12, Pydantic models, pytest, LangGraph runtime already wired through `prompt2langgraph`, existing builtin executor registry, existing CLI `pt2lg`.

---

## Repository Rules For This Plan

- Project root: `/Users/lzc/TNTprojectZ/AprojectZ/prompt2langgraph/prompt2langgraph`.
- Do not modify files outside this project root.
- Do not run network calls.
- Do not commit unless the user explicitly authorizes git commit. The "checkpoint" steps below mean: inspect status and prepare a concise commit summary only.
- Use `apply_patch` for manual edits.
- Preserve unrelated dirty worktree changes.
- After all tasks, run `uv run pytest`.

## Source Spec

Implement the project-level plan in:

- `docs/prompt2langgraph-v0.4-第一期实施计划文档.md`

The scope is Phase 1 only:

- JSON plan explicit `workflow_id`.
- JSON plan top-level `metadata`.
- Top-level `reducers` compatibility alias for `state_schema.reducers`.
- Existing `state_schema.reducers`, `policies`, and edge `join_sources` must not regress.
- Prompt planner and Skill planner schema text must match adapter behavior.
- JSON plan fanout smoke coverage must be offline and deterministic; join and security coverage reuse existing focused regression tests unless this plan explicitly adds new fixtures.
- README, AGENTS, CLAUDE, and corpus README must match current behavior.

## File Map

- Modify: `src/prompt2langgraph/adapters/json_plan.py`
  - Add explicit `workflow_id` selection.
  - Add metadata validation and pass-through.
  - Add top-level reducers compatibility and conflict diagnostics.

- Modify: `tests/test_json_plan_adapter.py`
  - Add adapter unit tests for `workflow_id`, `metadata`, top-level reducers, reducer conflicts, and direct run smoke.

- Create: `tests/fixtures/json_plan_fanout_run.json`
  - Direct simplified JSON plan fixture for CLI validate/compile/run smoke.

- Modify: `tests/prompts_skills_test/json_plans/reducer_append.json`
  - Ensure corpus covers reducer preservation; if it already uses `state_schema.reducers`, add top-level reducer coverage in a new fixture instead.

- Create: `tests/prompts_skills_test/json_plans/top_level_reducers.json`
  - Corpus wrapper fixture using `{ "json_plan": { ... } }`.

- Modify: `tests/prompts_skills_test/test_cases.json`
  - Register new top-level reducers corpus case.

- Modify: `tests/test_prompt_skill_corpus.py`
  - Add assertions only if the current generic expected fields do not already cover the new case.

- Modify: `src/prompt2langgraph/prompting/planner.py`
  - Update `SYSTEM_PROMPT` schema and rules.

- Modify: `tests/test_prompt_planner.py`
  - Add prompt text regression assertions.

- Modify: `src/prompt2langgraph/prompting/skill_planner.py`
  - Update state constraints, output format, and few-shot examples.

- Modify: `tests/test_skill_workflow.py`
  - Add skill planner prompt regression assertions.

- Modify: `README.md`
  - Align JSON plan fields, join status, reducer status, and `LANGCHAIN_TOOL` boundary.

- Modify: `AGENTS.md`
  - Align project current capability boundary.

- Modify: `CLAUDE.md`
  - Align project current capability boundary.

- Modify: `tests/prompts_skills_test/README.md`
  - Document corpus coverage for top-level reducers and join sources.

## Task 1: Add JSONPlanAdapter Contract Tests

**Files:**

- Modify: `tests/test_json_plan_adapter.py`

**Current source facts used by these snippets:**

- `builtin.identity_transform` returns `{"value": ...}` and its output schema key is `value`.
- `ReducerName` currently supports `append`, `add_messages`, `sum`, and `merge_dict`.
- Missing `metadata` should default to `{}`; explicitly provided `metadata` must be an object.

- [ ] **Step 1: Add tests for explicit `workflow_id` and fallback slug**

Append these tests near the existing normalization tests:

```python
def test_json_plan_explicit_workflow_id_overrides_name_slug() -> None:
    plan = {
        "workflow_id": "explicit_workflow",
        "name": "Name That Would Slug Differently",
        "nodes": [{"id": "first", "kind": "llm", "executor": "builtin.echo_llm"}],
        "edges": [],
    }

    workflow = json_plan_to_workflow_spec(plan)

    assert workflow.workflow_id == "explicit_workflow"


def test_json_plan_without_workflow_id_keeps_name_slug_fallback() -> None:
    plan = {
        "name": "Name Slug Fallback",
        "nodes": [{"id": "first", "kind": "llm", "executor": "builtin.echo_llm"}],
        "edges": [],
    }

    workflow = json_plan_to_workflow_spec(plan)

    assert workflow.workflow_id == "name_slug_fallback"
```

- [ ] **Step 2: Add tests for invalid explicit `workflow_id` diagnostics**

Append:

```python
@pytest.mark.parametrize("workflow_id", ["", "123bad", "bad-id", "bad id"])
def test_json_plan_reports_path_for_invalid_explicit_workflow_id(workflow_id: str) -> None:
    plan = {
        "workflow_id": workflow_id,
        "name": "Bad Workflow Id",
        "nodes": [{"id": "first", "kind": "llm", "executor": "builtin.echo_llm"}],
        "edges": [],
    }

    with pytest.raises(AdapterParseError) as exc_info:
        JSONPlanAdapter().parse(plan, source="bad_workflow_id.json")

    assert exc_info.value.source == "bad_workflow_id.json"
    assert exc_info.value.path == "workflow_id"
```

- [ ] **Step 3: Add tests for metadata pass-through and diagnostics**

Append:

```python
def test_json_plan_metadata_is_preserved() -> None:
    plan = {
        "workflow_id": "metadata_plan",
        "name": "Metadata Plan",
        "metadata": {"owner": "qa", "tags": ["phase1", "json-plan"]},
        "nodes": [{"id": "first", "kind": "llm", "executor": "builtin.echo_llm"}],
        "edges": [],
    }

    workflow = json_plan_to_workflow_spec(plan)

    assert workflow.metadata == {"owner": "qa", "tags": ["phase1", "json-plan"]}


def test_json_plan_reports_path_for_invalid_metadata() -> None:
    plan = {
        "workflow_id": "bad_metadata",
        "name": "Bad Metadata",
        "metadata": ["not", "an", "object"],
        "nodes": [{"id": "first", "kind": "llm", "executor": "builtin.echo_llm"}],
        "edges": [],
    }

    with pytest.raises(AdapterParseError) as exc_info:
        JSONPlanAdapter().parse(plan, source="bad_metadata.json")

    assert exc_info.value.source == "bad_metadata.json"
    assert exc_info.value.path == "metadata"


def test_json_plan_reports_path_for_null_metadata() -> None:
    plan = {
        "workflow_id": "null_metadata",
        "name": "Null Metadata",
        "metadata": None,
        "nodes": [{"id": "first", "kind": "llm", "executor": "builtin.echo_llm"}],
        "edges": [],
    }

    with pytest.raises(AdapterParseError) as exc_info:
        JSONPlanAdapter().parse(plan, source="null_metadata.json")

    assert exc_info.value.source == "null_metadata.json"
    assert exc_info.value.path == "metadata"
```

- [ ] **Step 4: Add tests for top-level reducers compatibility**

Append:

```python
def test_json_plan_top_level_reducers_map_to_state_schema_reducers() -> None:
    plan = {
        "workflow_id": "top_level_reducers",
        "name": "Top Level Reducers",
        "inputs": {"items": {"type": "array", "item_type": {"type": "string"}}},
        "outputs": {"results": {"type": "array", "item_type": {"type": "string"}}},
        "nodes": [
            {
                "id": "split",
                "kind": "transform",
                "executor": "builtin.identity_transform",
                "inputs": {"value": "items"},
                "outputs": {"value": "items"},
            },
            {
                "id": "process",
                "kind": "transform",
                "executor": "builtin.identity_transform",
                "inputs": {"value": "item"},
                "outputs": {"value": "results"},
            },
        ],
        "edges": [
            {
                "from": "split",
                "to": "process",
                "kind": "fanout",
                "map": {
                    "items_state_key": "items",
                    "item_state_key": "item",
                    "result_state_key": "results",
                },
            }
        ],
        "reducers": {"results": "append"},
    }

    workflow = json_plan_to_workflow_spec(plan)
    report = validate_workflow(workflow)

    assert workflow.state_schema.reducers["results"].value == "append"
    assert report.ok, f"validation failed: {report.diagnostics}"


def test_json_plan_accepts_matching_top_level_and_state_schema_reducers() -> None:
    plan = {
        "workflow_id": "matching_reducers",
        "name": "Matching Reducers",
        "nodes": [{"id": "first", "kind": "llm", "executor": "builtin.echo_llm"}],
        "edges": [],
        "state_schema": {"reducers": {"results": "append"}},
        "reducers": {"results": "append"},
    }

    workflow = json_plan_to_workflow_spec(plan)

    assert workflow.state_schema.reducers["results"].value == "append"
```

- [ ] **Step 5: Add tests for reducer conflict and invalid top-level reducer diagnostics**

Append:

```python
def test_json_plan_rejects_conflicting_reducer_locations() -> None:
    plan = {
        "workflow_id": "conflicting_reducers",
        "name": "Conflicting Reducers",
        "nodes": [{"id": "first", "kind": "llm", "executor": "builtin.echo_llm"}],
        "edges": [],
        "state_schema": {"reducers": {"results": "append"}},
        "reducers": {"results": "sum"},
    }

    with pytest.raises(AdapterParseError) as exc_info:
        JSONPlanAdapter().parse(plan, source="bad_reducers.json")

    assert exc_info.value.source == "bad_reducers.json"
    assert exc_info.value.path == "reducers"


def test_json_plan_reports_path_for_invalid_top_level_reducer_name() -> None:
    plan = {
        "workflow_id": "bad_top_level_reducer",
        "name": "Bad Top Level Reducer",
        "nodes": [{"id": "first", "kind": "llm", "executor": "builtin.echo_llm"}],
        "edges": [],
        "reducers": {"results": "unsupported"},
    }

    with pytest.raises(AdapterParseError) as exc_info:
        JSONPlanAdapter().parse(plan, source="bad_top_level_reducer.json")

    assert exc_info.value.source == "bad_top_level_reducer.json"
    assert exc_info.value.path == "reducers"
```

- [ ] **Step 6: Run the new tests and verify they fail before implementation**

Run:

```bash
uv run pytest tests/test_json_plan_adapter.py -v
```

Expected:

- `workflow_id` explicit override test fails because current adapter derives from `name`.
- `metadata` preservation test fails because current adapter writes `{}`.
- top-level reducers test fails because current adapter only reads `state_schema.reducers`.

## Task 2: Implement JSONPlanAdapter Field Preservation

**Files:**

- Modify: `src/prompt2langgraph/adapters/json_plan.py`

**Current source facts used by these snippets:**

- `WorkflowSpec.workflow_id` uses the same identifier rule as node ids: `^[A-Za-z_][A-Za-z0-9_]*$`.
- `metadata` defaults to `{}` only when the key is absent; if present, it must be an object.
- Reducer conflict must compare two already-valid reducer maps, not rely on an unsupported reducer name.

- [ ] **Step 1: Add workflow id selection, metadata validation, and reducer selection helpers**

Add these helpers near `_reducer_mapping`:

```python
def _workflow_id(plan: Mapping[str, Any], plan_name: str, *, source: str | None) -> str:
    if "workflow_id" not in plan:
        return _slugify_identifier(plan_name, source=source, path="name")
    value = _require_str(plan, "workflow_id", source=source, path="workflow_id")
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", value):
        raise AdapterParseError(
            "workflow_id must be a valid identifier",
            source=source,
            path="workflow_id",
        )
    return value


def _metadata_mapping(raw: Any, *, source: str | None) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise AdapterParseError("metadata must be an object", source=source, path="metadata")
    return dict(raw)


def _reducers_from_plan(
    plan: Mapping[str, Any],
    state_schema: Mapping[str, Any],
    *,
    source: str | None,
) -> dict[str, ReducerName]:
    has_state_reducers = "reducers" in state_schema
    has_top_level_reducers = "reducers" in plan
    state_reducers = _reducer_mapping(
        state_schema.get("reducers", {}),
        source=source,
        path="state_schema.reducers",
    )
    if not has_top_level_reducers:
        return state_reducers
    top_level_reducers = _reducer_mapping(
        plan.get("reducers", {}),
        source=source,
        path="reducers",
    )
    if has_state_reducers and state_reducers != top_level_reducers:
        raise AdapterParseError(
            "reducers conflicts with state_schema.reducers",
            source=source,
            path="reducers",
        )
    return top_level_reducers
```

- [ ] **Step 2: Change `_reducer_mapping` to accept a path**

Replace the existing `_reducer_mapping` signature and body with:

```python
def _reducer_mapping(
    raw: Any,
    *,
    source: str | None,
    path: str = "state_schema.reducers",
) -> dict[str, ReducerName]:
    if not isinstance(raw, Mapping):
        raise AdapterParseError(
            f"{path} must be a mapping",
            source=source,
            path=path,
        )
    try:
        return {name: ReducerName(value) for name, value in raw.items()}
    except ValueError as exc:
        raise AdapterParseError(
            f"{path} contains unsupported reducer",
            source=source,
            path=path,
        ) from exc
```

- [ ] **Step 3: Wire helpers into `json_plan_to_workflow_spec`**

In `json_plan_to_workflow_spec`, replace:

```python
workflow_id = _slugify_identifier(plan_name, source=source, path="name")
```

with:

```python
workflow_id = _workflow_id(plan, plan_name, source=source)
```

Replace:

```python
reducers = _reducer_mapping(state_schema.get("reducers", {}), source=source)
```

with:

```python
reducers = _reducers_from_plan(plan, state_schema, source=source)
metadata = _metadata_mapping(plan["metadata"], source=source) if "metadata" in plan else {}
```

Replace:

```python
"metadata": {},
```

with:

```python
"metadata": metadata,
```

- [ ] **Step 4: Run adapter tests**

Run:

```bash
uv run pytest tests/test_json_plan_adapter.py -v
```

Expected: all tests in `tests/test_json_plan_adapter.py` pass.

- [ ] **Step 5: Checkpoint without committing**

Run:

```bash
git diff -- src/prompt2langgraph/adapters/json_plan.py tests/test_json_plan_adapter.py
git status --short
```

Expected:

- Diff only contains adapter and adapter tests for this task.
- Do not commit unless the user explicitly authorizes it.

## Task 3: Add Direct JSON Plan Run Smoke Fixture

**Files:**

- Create: `tests/fixtures/json_plan_fanout_run.json`
- Modify: `tests/test_json_plan_adapter.py`

**Current source facts used by these snippets:**

- `builtin.identity_transform` accepts input key `value` and returns output key `value`.
- `compile_workflow_to_graph()` requires an explicit executor registry argument.
- `run_workflow()` builds the builtin executor registry by default, so the runtime smoke can call it without passing executors.

- [ ] **Step 1: Create direct fixture**

Create `tests/fixtures/json_plan_fanout_run.json` with:

```json
{
  "workflow_id": "json_plan_fanout_run",
  "name": "JSON Plan Fanout Run",
  "entrypoint": "split",
  "metadata": {
    "source": "v0.4-phase1-smoke"
  },
  "inputs": {
    "items": {
      "type": "array",
      "item_type": {
        "type": "string"
      }
    }
  },
  "outputs": {
    "results": {
      "type": "array",
      "item_type": {
        "type": "string"
      }
    }
  },
  "nodes": [
    {
      "id": "split",
      "kind": "transform",
      "executor": "builtin.identity_transform",
      "inputs": {
        "value": "items"
      },
      "outputs": {
        "value": "items"
      }
    },
    {
      "id": "process",
      "kind": "transform",
      "executor": "builtin.identity_transform",
      "inputs": {
        "value": "item"
      },
      "outputs": {
        "value": "results"
      }
    }
  ],
  "edges": [
    {
      "from": "split",
      "to": "process",
      "kind": "fanout",
      "map": {
        "items_state_key": "items",
        "item_state_key": "item",
        "result_state_key": "results"
      }
    }
  ],
  "reducers": {
    "results": "append"
  }
}
```

- [ ] **Step 2: Add a Python smoke test for validate/compile/run boundary**

Add imports at the top of `tests/test_json_plan_adapter.py` if missing:

```python
import json
from pathlib import Path

from prompt2langgraph.compiler.langgraph_py import compile_workflow_to_graph
from prompt2langgraph.registry.builtins import builtin_executor_registry
from prompt2langgraph.runtime.runner import run_workflow
```

Append:

```python
def test_json_plan_fanout_fixture_validates_compiles_and_runs() -> None:
    fixture = Path("tests/fixtures/json_plan_fanout_run.json")
    plan = json.loads(fixture.read_text(encoding="utf-8"))

    workflow = json_plan_to_workflow_spec(plan)
    report = validate_workflow(workflow)
    graph = compile_workflow_to_graph(workflow, builtin_executor_registry())
    result = run_workflow(workflow, {"items": ["alpha", "beta"]})

    assert report.ok, f"validation failed: {report.diagnostics}"
    assert graph is not None
    assert result.status == "succeeded"
    assert result.output["results"] == ["alpha", "beta"]
```

- [ ] **Step 3: Run adapter smoke test**

Run:

```bash
uv run pytest tests/test_json_plan_adapter.py::test_json_plan_fanout_fixture_validates_compiles_and_runs -v
```

Expected: pass.

- [ ] **Step 4: Run CLI smoke manually**

Run:

```bash
uv run pt2lg validate tests/fixtures/json_plan_fanout_run.json --json
uv run pt2lg compile tests/fixtures/json_plan_fanout_run.json --out build --json
uv run pt2lg run build/json_plan_fanout_run/workflow.lock.json --input '{"items":["alpha","beta"]}' --json
```

Expected:

- validate output includes `"ok": true`.
- compile output references `build/json_plan_fanout_run`.
- run output includes `"status": "succeeded"` and `results`.

## Task 4: Add Corpus Coverage For Top-Level Reducers

**Files:**

- Create: `tests/prompts_skills_test/json_plans/top_level_reducers.json`
- Modify: `tests/prompts_skills_test/test_cases.json`
- Modify: `tests/test_prompt_skill_corpus.py` only if needed.

**Current source facts used by these snippets:**

- Corpus JSON plan fixtures are wrapped as `{ "json_plan": { ... } }`; direct CLI fixtures are not wrapped.
- `tests/test_prompt_skill_corpus.py` already asserts `expected_reducers` when present; do not duplicate that block if it is already in the file.
- `builtin.identity_transform` output mappings must use output key `value`.

- [ ] **Step 1: Create corpus wrapper fixture**

Create `tests/prompts_skills_test/json_plans/top_level_reducers.json`:

```json
{
  "json_plan": {
    "workflow_id": "corpus_top_level_reducers",
    "name": "Corpus Top Level Reducers",
    "entrypoint": "split",
    "inputs": {
      "items": {
        "type": "array",
        "item_type": {
          "type": "string"
        }
      }
    },
    "outputs": {
      "results": {
        "type": "array",
        "item_type": {
          "type": "string"
        }
      }
    },
    "nodes": [
      {
        "id": "split",
        "kind": "transform",
        "executor": "builtin.identity_transform",
        "inputs": {
          "value": "items"
        },
        "outputs": {
          "value": "items"
        }
      },
      {
        "id": "process",
        "kind": "transform",
        "executor": "builtin.identity_transform",
        "inputs": {
          "value": "item"
        },
        "outputs": {
          "value": "results"
        }
      }
    ],
    "edges": [
      {
        "from": "split",
        "to": "process",
        "kind": "fanout",
        "map": {
          "items_state_key": "items",
          "item_state_key": "item",
          "result_state_key": "results"
        }
      }
    ],
    "reducers": {
      "results": "append"
    }
  }
}
```

- [ ] **Step 2: Register the corpus case**

Open `tests/prompts_skills_test/test_cases.json` and add this object to the `json_plan_tests` array:

```json
{
  "id": "json_plan_top_level_reducers",
  "json_plan_file": "json_plans/top_level_reducers.json",
  "expected_node_types": ["transform"],
  "expected_patterns": ["fanout"],
  "expected_reducers": {
    "results": "append"
  }
}
```

Keep valid JSON syntax: add or remove commas based on the surrounding list position.

- [ ] **Step 3: Run corpus tests**

Run:

```bash
uv run pytest tests/test_prompt_skill_corpus.py -v
```

Expected: pass.

- [ ] **Step 4: If the corpus test does not assert reducers for the new case, add this assertion**

Only if missing, add this inside `_assert_expected_shape` in `tests/test_prompt_skill_corpus.py`:

```python
if "expected_reducers" in case:
    assert {
        key: reducer.value for key, reducer in workflow.state_schema.reducers.items()
    } == case["expected_reducers"]
```

Run the corpus test again after editing.

## Task 5: Update Prompt Planner Schema Text

**Files:**

- Modify: `src/prompt2langgraph/prompting/planner.py`
- Modify: `tests/test_prompt_planner.py`

- [ ] **Step 1: Add prompt regression test**

Append to `tests/test_prompt_planner.py`:

```python
def test_system_prompt_documents_v04_phase1_json_plan_fields() -> None:
    from prompt2langgraph.prompting.planner import SYSTEM_PROMPT

    required_fragments = [
        '"workflow_id"',
        '"metadata"',
        '"state_schema"',
        '"reducers"',
        '"policies"',
        '"join_sources"',
        '"join"',
        "allowed_models",
        "allowed_tool_refs",
        "external_call",
        "fanout",
    ]

    for fragment in required_fragments:
        assert fragment in SYSTEM_PROMPT
```

- [ ] **Step 2: Run the prompt planner test and verify it fails if text is stale**

Run:

```bash
uv run pytest tests/test_prompt_planner.py::test_system_prompt_documents_v04_phase1_json_plan_fields -v
```

Expected: fail if `SYSTEM_PROMPT` still omits Phase 1 fields.

- [ ] **Step 3: Update `SYSTEM_PROMPT` schema**

In `src/prompt2langgraph/prompting/planner.py`, update the schema block so the top-level object includes these fields:

```text
  "workflow_id": string (optional, valid identifier; if omitted, derived from name),
  "metadata": object (optional, non-secret descriptive metadata),
  "entrypoint": string (optional, id of the first node; if omitted, inferred as the node with no incoming edges),
  "inputs": object (optional, mapping of input names to type strings or type objects),
  "outputs": object (optional, mapping of output names to type strings or type objects),
  "state_schema": object (optional, e.g. {"reducers": {"results": "append"}}),
  "reducers": object (optional compatibility alias for state_schema.reducers),
  "policies": object (optional, e.g. {"external_call": true, "allowed_models": ["qwen-plus"], "allowed_tool_refs": ["tool.echo"]})
```

Update edge kind text to include join:

```text
      "kind": string (optional, one of: "linear", "conditional", "loop", "fanout", "join"; defaults to "linear"),
      "join_sources": array of string (optional, required when kind="join"),
```

- [ ] **Step 4: Update `SYSTEM_PROMPT` rules**

Add or revise rules so they state:

```text
- Prefer "state_schema": {"reducers": {...}} for reducers; top-level "reducers" is accepted as a compatibility alias.
- For fanout edges, the workflow must define a reducer such as "append" for "map.result_state_key".
- For join edges, "join_sources" must list the upstream source node ids that must complete before the join target runs.
- For real LLM executor refs such as "llm.qwen-plus", set "policies.external_call" to true and include the model id in "policies.allowed_models".
- For Python callable tool executor refs, include the tool ref in "policies.allowed_tool_refs".
- Do not include secrets in "metadata", "params", or "policies".
```

- [ ] **Step 5: Run prompt planner tests**

Run:

```bash
uv run pytest tests/test_prompt_planner.py -v
```

Expected: pass.

## Task 6: Update Skill Planner Schema Text

**Files:**

- Modify: `src/prompt2langgraph/prompting/skill_planner.py`
- Modify: `tests/test_skill_workflow.py`

- [ ] **Step 1: Add skill prompt regression test**

Append to `tests/test_skill_workflow.py`:

```python
def test_build_skill_plan_prompt_documents_v04_phase1_json_plan_fields() -> None:
    analysis = analyze_skill_dir("tests/fixtures/skill_basic")
    prompt = build_skill_plan_prompt(analysis, skill_dir="tests/fixtures/skill_basic")

    required_fragments = [
        '"workflow_id"',
        '"metadata"',
        '"state_schema"',
        '"reducers"',
        '"policies"',
        '"join_sources"',
        "allowed_models",
        "allowed_tool_refs",
        "external_call",
        "fanout",
        "join",
    ]

    for fragment in required_fragments:
        assert fragment in prompt
```

- [ ] **Step 2: Run the new skill prompt test**

Run:

```bash
uv run pytest tests/test_skill_workflow.py::test_build_skill_plan_prompt_documents_v04_phase1_json_plan_fields -v
```

Expected: fail if the prompt still omits Phase 1 fields.

- [ ] **Step 3: Update state schema constraints**

In `src/prompt2langgraph/prompting/skill_planner.py`, replace the reducer rule in `state_constraints` with text equivalent to:

```text
2. **Reducer declaration**: If a state key is used in a fanout/reduce
   pattern, you MUST declare a reducer in `state_schema.reducers`,
   for example `{"state_schema": {"reducers": {"results": "append"}}}`.
   The top-level `reducers` field is accepted only as a compatibility alias.
```

- [ ] **Step 4: Update output format**

In the `output_format` string, add:

```text
  "workflow_id": string (optional, valid identifier),
  "metadata": object (optional, non-secret descriptive metadata),
```

Add top-level fields:

```text
  "state_schema": object (optional, e.g. {"reducers": {"results": "append"}}),
  "reducers": object (optional compatibility alias for state_schema.reducers),
  "policies": object (optional, e.g. {"external_call": true, "allowed_models": ["qwen-plus"], "allowed_tool_refs": ["tool.echo"]})
```

Keep edge kind text including `join` and `join_sources`.

- [ ] **Step 5: Update few-shot examples**

Update at least one few-shot example to include:

```json
"workflow_id": "research_workflow",
"metadata": {"source": "skill-planner-example"},
"state_schema": {"reducers": {"results": "append"}}
```

For tool examples, include:

```json
"policies": {
  "allowed_tool_refs": ["builtin.identity_transform"]
}
```

For real LLM examples, only use real LLM refs when also showing:

```json
"policies": {
  "external_call": true,
  "allowed_models": ["qwen-plus"]
}
```

Do not replace builtin deterministic examples with real external model examples.

- [ ] **Step 6: Run skill workflow tests**

Run:

```bash
uv run pytest tests/test_skill_workflow.py -v
```

Expected: pass.

## Task 7: Update Documentation For Phase 1 Behavior

**Files:**

- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `CLAUDE.md`
- Modify: `tests/prompts_skills_test/README.md`

- [ ] **Step 1: Scan for stale claims**

Run:

```bash
rg -n "join.*不可|join.*不支持|JOIN.*不可|reducers.*无法|无法表达.*reducers|LANGCHAIN_TOOL|reserved|experimental|join_sources|state_schema.reducers|workflow_id|metadata" README.md AGENTS.md CLAUDE.md tests/prompts_skills_test/README.md
```

Expected:

- Identify stale claims that contradict Phase 1 behavior.
- `LANGCHAIN_TOOL` may appear only if described as reserved or experimental.

- [ ] **Step 2: Update README JSON plan section**

Ensure README states:

```markdown
简化 JSON plan 支持 `workflow_id`、`metadata`、`inputs`、`outputs`、`state_schema.reducers`、兼容顶层 `reducers`、`policies` 和 edge 级 `join_sources`。推荐使用 `state_schema.reducers`；顶层 `reducers` 仅作为兼容别名。
```

Ensure README states:

```markdown
`join` 已支持编译与运行，但 join edge 必须声明 `join_sources`；fanout/reduce 场景还必须为 `map.result_state_key` 声明 reducer。
```

- [ ] **Step 3: Update AGENTS and CLAUDE capability boundaries**

Ensure both files state:

```markdown
JSON plan 适配保留显式 `workflow_id`、顶层 `metadata`、`policies`、`state_schema.reducers`、兼容顶层 `reducers` 和 edge 级 `join_sources`。
```

Ensure both files state:

```markdown
`LANGCHAIN_TOOL` 在 v0.4 第一期仍为 reserved/experimental，不作为默认可执行能力。
```

- [ ] **Step 4: Update corpus README**

Ensure `tests/prompts_skills_test/README.md` states:

```markdown
语料覆盖简化 JSON plan 的 linear、conditional、loop、fanout、join、side_effect、security、`state_schema.reducers`、兼容顶层 `reducers`、`policies` 和 `join_sources`。语料测试默认离线执行，不访问网络。
```

- [ ] **Step 5: Re-scan stale claims**

Run:

```bash
rg -n "join.*不可|join.*不支持|JOIN.*不可|reducers.*无法|无法表达.*reducers" README.md AGENTS.md CLAUDE.md tests/prompts_skills_test/README.md
rg -n "LANGCHAIN_TOOL" README.md AGENTS.md CLAUDE.md tests/prompts_skills_test/README.md
```

Expected:

- First command has no stale contradiction.
- Any `LANGCHAIN_TOOL` hit is accompanied by reserved or experimental wording.

## Task 8: Run Focused Regression Suite

**Files:**

- No edits unless failures reveal a scoped defect.

This task is the Phase 1 join/security smoke boundary. It does not create new join or security fixtures; it verifies that the existing join and security tests still cover those behaviors after the adapter and planner changes.

- [ ] **Step 1: Run adapter tests**

Run:

```bash
uv run pytest tests/test_json_plan_adapter.py -v
```

Expected: pass.

- [ ] **Step 2: Run planner tests**

Run:

```bash
uv run pytest tests/test_prompt_planner.py tests/test_skill_workflow.py -v
```

Expected: pass.

- [ ] **Step 3: Run corpus tests**

Run:

```bash
uv run pytest tests/test_prompt_skill_corpus.py -v
```

Expected: pass.

- [ ] **Step 4: Run join and security regression tests**

Run:

```bash
uv run pytest tests/test_join_execution.py tests/test_security_policy.py -v
```

Expected: pass.

- [ ] **Step 5: Run CLI and public API regression tests**

Run:

```bash
uv run pytest tests/test_public_api.py tests/test_cli.py -v
```

Expected: pass.

## Task 9: Run Final CLI Smoke And Full Regression

**Files:**

- No edits unless failures reveal a scoped defect.

- [ ] **Step 1: Run direct CLI validate smoke**

Run:

```bash
uv run pt2lg validate tests/fixtures/json_plan_fanout_run.json --json
```

Expected:

```json
{
  "ok": true
}
```

The actual output may include additional report fields.

- [ ] **Step 2: Run direct CLI compile smoke**

Run:

```bash
uv run pt2lg compile tests/fixtures/json_plan_fanout_run.json --out build --json
```

Expected:

- Command exits `0`.
- Output references `build/json_plan_fanout_run`.
- Bundle contains `workflow.lock.json`.

- [ ] **Step 3: Run direct CLI run smoke**

Run:

```bash
uv run pt2lg run build/json_plan_fanout_run/workflow.lock.json --input '{"items":["alpha","beta"]}' --json
```

Expected:

- Command exits `0`.
- Output includes `"status": "succeeded"`.
- Output includes `results`.

- [ ] **Step 4: Run full test suite**

Run:

```bash
uv run pytest
```

Expected: all tests pass.

- [ ] **Step 5: Final status summary**

Run:

```bash
git status --short
```

Prepare a summary with:

- Files changed by this implementation.
- Focused regression command results.
- CLI smoke command results.
- Full `uv run pytest` result.
- Any unrelated pre-existing dirty worktree files that were not touched.

Do not commit unless the user explicitly authorizes it.

## Completion Criteria

This plan is complete only when:

- Explicit `workflow_id` is preserved.
- Missing `workflow_id` still falls back to slugified `name`.
- Invalid explicit `workflow_id` reports `path="workflow_id"`.
- Top-level `metadata` is preserved.
- Invalid `metadata` reports `path="metadata"`.
- `state_schema.reducers` still works.
- Top-level `reducers` works as a compatibility alias.
- Conflicting reducer declarations report `path="reducers"`.
- Existing `policies` and `join_sources` behavior is preserved.
- JSON plan fanout fixture validates, compiles, and runs.
- Existing join and security regression tests continue to pass.
- Prompt planner and Skill planner schema text mention Phase 1 fields and policy constraints.
- Corpus includes top-level reducers coverage.
- README, AGENTS, CLAUDE, and corpus README match current behavior.
- No default test requires network access.
- `uv run pytest` passes.
