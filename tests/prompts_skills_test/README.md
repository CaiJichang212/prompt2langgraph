# Prompts and Skills Test Fixtures

Offline prompt and Skill corpus for testing `prompt2langgraph` prompt/skill ingestion.

This directory contains deterministic fixtures for prompt, Skill, JSON plan, and negative-case regression tests. It is a corpus for the prompt/skill ingestion surface, not a claim of full project coverage. Tests must not fetch the network.

## Directory Structure

```
prompts_skills_test/
├── skills/
│   ├── openai-curated/         # Skills from openai/skills patterns (7 skills)
│   ├── codex-skills/           # Skills from ComposioHQ/awesome-codex-skills (5 skills)
│   ├── anthropic-curated/      # Skills from anthropics/skills (2 skills)
│   └── mattpocock/             # Skills from mattpocock/skills and obra/superpowers (2 skills)
├── prompts/                    # Prompt fixtures (7 structured + 3 raw upstream snapshots)
│   ├── *.json                  # Structured prompt test cases used by the corpus tests
│   └── *.md                    # Raw upstream prompt snapshots used as source references
├── json_plans/                 # JSON Plan direct input tests (6 plans)
│   ├── linear_llm.json
│   ├── conditional_router.json
│   ├── loop_refine.json
│   ├── fanout_join.json
│   ├── side_effect_approval.json
│   └── reducer_append.json
├── invalid/                    # Negative test cases (12 cases)
│   ├── security_*.json         # Security policy violations
│   ├── parse_*.json            # Parse error cases
│   ├── schema_*.json           # Schema validation errors
│   └ registry_negative/       # Registry lookup failures
│   └ skill_negative/          # Skill parsing failures
│   └ skill_no_frontmatter/    # SKILL.md without frontmatter
├── test_cases.json             # Complete test case definitions
├── prompt_workflow_cases.json  # Prompt workflow mappings
├── source_manifest.json        # Source URLs and retrieval dates
└── README.md                   # This file
```

## Test Coverage Summary

| Category | Count | Coverage |
|----------|-------|----------|
| **Skill→Workflow cases** | 16 | Offline fake-model planning pipeline + validation + compile |
| **Structured Prompt→Workflow cases** | 7 | Offline fake-model planning pipeline + validation + compile |
| **Inline upstream/source plans** | 5 | Adapter + validation, compiling valid plans |
| **JSON Plans** | 6 | Direct JSON Plan input pathway + validation + compile |
| **Negative Cases** | 12 | Security, Parse, Schema, Registry, Skill errors |
| **Executable Corpus Cases** | 46 | Parameterized pytest cases, plus one manifest consistency check |

## Scope and Limitations

This corpus is useful for test-driven development around prompt and Skill ingestion, simplified JSON plan adaptation, validation diagnostics, compiler smoke coverage, and security boundary regressions.

It does not by itself cover the entire project. Full coverage still requires the existing tests for canonical IR models, normalization, lockfile/manifest/report generation, LangGraph compilation, artifact cleanup, local run/resume, checkpoint behavior, Mermaid rendering, CLI flows, public API, executor dispatch, and runtime external-call metrics.

## Workflow Pattern Coverage

| Pattern | Skills | Prompts | JSON Plans | Negative |
|---------|--------|---------|------------|----------|
| `linear` | 5 | 2 | 1 | - |
| `conditional` | 3 | 1 | 1 | - |
| `loop` | 2 | 1 | 1 | 1 (no guard) |
| `fanout`+`join` | 1 | 1 | 1 | 2 (no reducer, no sources) |
| `human_gate` | 1 | 1 | - | - |
| `side_effect` | 1 | 1 | 1 | 1 (no approval) |
| `reducer` | - | - | 1 | - |
| `security` | - | - | - | 4 |
| `parse` | - | - | - | 2 |
| `registry` | - | - | - | 1 |
| `skill` | - | - | - | 2 |

## Usage

### Skill → WorkflowSpec Tests

The default pytest path uses a deterministic fake model so these cases stay offline. The CLI examples below are manual smoke checks for live Skill planning and require local LLM configuration.

```bash
# Linear workflow
uv run pt2lg plan --skill-dir tests/prompts_skills_test/skills/openai-curated/linear-data-pipeline --json

# Conditional workflow
uv run pt2lg plan --skill-dir tests/prompts_skills_test/skills/openai-curated/conditional-support-triage --json

# Loop workflow
uv run pt2lg plan --skill-dir tests/prompts_skills_test/skills/openai-curated/loop-refine-content --json

# Fanout+Join workflow
uv run pt2lg plan --skill-dir tests/prompts_skills_test/skills/openai-curated/fanout-multi-source-research --json

# Human Gate workflow
uv run pt2lg plan --skill-dir tests/prompts_skills_test/skills/openai-curated/human-gate-deployment --json

# Side Effect workflow
uv run pt2lg plan --skill-dir tests/prompts_skills_test/skills/openai-curated/side-effect-file-organizer --json
```

### Prompt → WorkflowSpec Tests

```bash
# Linear workflow prompt
uv run pt2lg plan --prompt "Build a workflow that processes a user question: first retrieves relevant documents, then generates an answer using those documents, and finally formats the response." --json

# Conditional workflow prompt
uv run pt2lg plan --prompt "Build a support ticket routing workflow: analyze the ticket severity, if severity is critical route to emergency team, if severity is high route to priority team, otherwise route to standard team." --json

# Loop workflow prompt
uv run pt2lg plan --prompt "Build a content refinement workflow: generate initial draft, evaluate quality score, if score below 80 improve the content and re-evaluate, stop when score reaches 80 or after 5 iterations maximum." --json
```

### JSON Plan Direct Input Tests

```bash
# Test JSON Plan adapter
uv run python -c "
from prompt2langgraph.adapters.json_plan import json_plan_to_workflow_spec
import json
plan = json.load(open('tests/prompts_skills_test/json_plans/linear_llm.json'))
spec = json_plan_to_workflow_spec(plan['json_plan'])
print(spec)
"
```

### Negative Case Tests

```bash
# Security: external_call without policy
uv run python -c "
from prompt2langgraph.adapters.json_plan import json_plan_to_workflow_spec
from prompt2langgraph.validate.validator import validate_workflow
import json
plan = json.load(open('tests/prompts_skills_test/invalid/security_external_call_without_policy.json'))
spec = json_plan_to_workflow_spec(plan['json_plan'])
report = validate_workflow(spec)
print(report.diagnostics)  # Should contain E_SEC_013
"

# Parse: not JSON object
uv run python -c "
from prompt2langgraph.prompting.parser import parse_prompt_plan_text
result = parse_prompt_plan_text('This is plain text, not JSON')
# Should raise AdapterParseError
"
```

## Sources

| Source | URL | Stars | Used Skills/Prompts |
|--------|-----|-------|---------------------|
| openai/skills | https://github.com/openai/skills | 19.3k | yeet, linear-data-pipeline, conditional-support-triage, etc. |
| ComposioHQ/awesome-codex-skills | https://github.com/ComposioHQ/awesome-codex-skills | 10.7k | gh-fix-ci, webapp-testing, mcp-builder, etc. |
| anthropics/skills | https://github.com/anthropics/skills | - | skill-creator, webapp-testing |
| mattpocock/skills | https://github.com/mattpocock/skills | - | tdd |
| obra/superpowers | https://github.com/obra/superpowers | - | test-driven-development |
| f/awesome-chatgpt-prompts | https://github.com/f/awesome-chatgpt-prompts | 163k | Prompt patterns |

## Test Principles

1. **No network fetch**: All fixtures are offline snapshots.
2. **Fixed commits**: Sources are recorded in `source_manifest.json`.
3. **Clear expectations**: Each fixture has expected outcomes defined.
4. **Positive + Negative**: Both valid cases and error cases are covered.
5. **Security boundaries**: Security policy violations are explicitly tested.

## Running Tests

```bash
# Run all tests
uv run pytest tests/

# Run specific test file
uv run pytest tests/test_skill_workflow.py -v
uv run pytest tests/test_prompt_planner.py -v
uv run pytest tests/test_json_plan_adapter.py -v
uv run pytest tests/test_security_policy.py -v

# Run this corpus
uv run pytest tests/test_prompt_skill_corpus.py -v
```

## Notes

- Skills follow `SKILL.md` format with YAML frontmatter (`name`, `description`) + numbered steps.
- Structured prompt fixtures test `plan_prompt_to_workflow_spec()` through a deterministic fake model in pytest.
- JSON Plans test `json_plan_to_workflow_spec()` direct input pathway.
- Invalid cases test error handling and validation boundaries.
- Positive corpus cases assert expected node/edge patterns, validation success, and compiler smoke success.
- Live LLM output may vary by model and should remain outside the default offline test path.
