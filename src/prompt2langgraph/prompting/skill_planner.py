"""LLM-driven Skill → simplified JSON plan converter."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from prompt2langgraph.adapters.json_plan import JSONPlanAdapter
from prompt2langgraph.adapters.skill_dir import SkillDirectoryAnalysis, analyze_skill_dir
from prompt2langgraph.diagnostics.report import Diagnostic
from prompt2langgraph.ir.models import WorkflowSpec
from prompt2langgraph.prompting.parser import parse_prompt_plan_text

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI


class SkillPlanRequest(BaseModel):
    skill_dir: str
    params: dict[str, str] = Field(default_factory=dict)
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)


class SkillPlanResult(BaseModel):
    raw_text: str
    plan: dict[str, Any] | None = None
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    workflow_spec: WorkflowSpec | None = None


_SKILL_MD_MAX_CHARS = 8000


def build_skill_plan_prompt(
    analysis: SkillDirectoryAnalysis,
    *,
    skill_dir: Path | str | None = None,
    params: dict[str, str] | None = None,
) -> str:
    """Build an LLM prompt for converting a Skill to a simplified JSON plan.

    The prompt includes:
    - SKILL.md original text
    - Step summary from static analysis
    - Resource file list
    - Risk diagnostic summary
    - Parameter context
    - Available node types and executor references
    - State schema constraints
    - Few-shot examples
    """
    parts = ["# Skill to Workflow Conversion Request\n"]

    # SKILL.md original text — prefer skill_dir parameter for reliable path resolution
    skill_md = Path(skill_dir) / "SKILL.md" if skill_dir else None
    if skill_md is not None and skill_md.exists():
        try:
            raw_text = skill_md.read_text(encoding="utf-8")
            if len(raw_text) > _SKILL_MD_MAX_CHARS:
                truncated = raw_text[:_SKILL_MD_MAX_CHARS]
                parts.append(
                    f"## SKILL.md (truncated to {_SKILL_MD_MAX_CHARS} chars)\n{truncated}\n"
                    f"<!-- NOTE: SKILL.md was truncated ({len(raw_text) - _SKILL_MD_MAX_CHARS}"
                    f" chars omitted) -->\n"
                )
            else:
                parts.append(f"## SKILL.md (original)\n{raw_text}\n")
        except OSError:
            parts.append(f"## SKILL.md\n<!-- failed to read {skill_md} -->\n")
    elif analysis.name:
        parts.append(f"## SKILL.md\n<!-- {analysis.name} not found, using analysis context -->\n")

    # Skill metadata
    parts.append("## Skill Metadata\n")
    parts.append(f"- name: {analysis.name}\n")
    parts.append(f"- description: {analysis.description}\n")

    # Numbered steps summary
    if analysis.steps:
        parts.append("\n## Steps Summary\n")
        for i, step in enumerate(analysis.steps, start=1):
            parts.append(f"{i}. {step}\n")

    # Draft nodes from analysis
    if analysis.draft_nodes:
        parts.append("\n## Draft Nodes (from static analysis)\n")
        for node in analysis.draft_nodes:
            parts.append(f"- `{node.id}`: {node.summary}\n")

    # Resource files
    if analysis.resources.scripts or analysis.resources.references or analysis.resources.assets:
        parts.append("\n## Resource Files\n")
        if analysis.resources.scripts:
            parts.append("### scripts/\n")
            for s in analysis.resources.scripts:
                parts.append(f"- {s}\n")
        if analysis.resources.references:
            parts.append("### references/\n")
            for r in analysis.resources.references:
                parts.append(f"- {r}\n")
        if analysis.resources.assets:
            parts.append("### assets/\n")
            for a in analysis.resources.assets:
                parts.append(f"- {a}\n")

    # Risk diagnostics
    risk_diags = [d for d in analysis.report.diagnostics if d.code == "E_SEC_007"]
    if risk_diags:
        parts.append("\n## Risk Diagnostics (E_SEC_007)\n")
        for diag in risk_diags:
            parts.append(f"- [{diag.severity.upper()}] {diag.message}")
            if diag.location:
                loc = diag.location
                parts.append(f"  (source: {loc.source}")
                if loc.line:
                    parts.append(f", line: {loc.line}")
                parts.append(")\n")

    # Parameter context
    if params:
        parts.append("\n## Parameter Context\n")
        for key, value in params.items():
            parts.append(f"- {key}: {value}\n")

    # State schema constraints
    state_constraints = """
## State Schema Constraints

When generating the JSON plan, follow these state schema rules:

1. **State key naming**: Must be valid Python identifiers
   (alphanumeric + underscore, cannot start with digit).
2. **Reducer declaration**: If a state key is used in a fanout/reduce
   pattern, you MUST declare a reducer in the workflow's `reducers`
   field (e.g., `{"results": "append"}`).
3. **Reserved words** (cannot be used as state keys):
   - `__pt2lg_side_effect_results__`
   - `__pt2lg_side_effect_records__`
   - `__interrupt__`
   - `approval` (used by `human_gate` node)
"""
    parts.append(state_constraints)

    # Available node types and executors
    node_types_table = """
## Available Node Types and Executors

Use these registered node kinds and executor refs in your plan:

| Node Kind   | Executor Ref              | Description                      |
|-------------|--------------------------|----------------------------------|
| llm         | builtin.echo_llm         | Mock LLM (for testing)           |
| tool        | builtin.*                | Tool executor                    |
| retriever   | builtin.mock_retriever  | Mock retriever (for testing)     |
| transform   | builtin.identity_transform | Pass-through transform         |
| router      | builtin.route           | Conditional router               |
| human_gate  | builtin.human_gate      | Human approval gate (interrupt)  |
| join        | builtin.join            | Synchronization join             |
| side_effect | builtin.*               | Side effect node (needs approval)|
"""
    parts.append(node_types_table)

    # Output format
    output_format = """
## Output Format

**IMPORTANT**: Return ONLY a JSON object conforming to the simplified
JSON plan schema below. Do NOT execute any scripts or commands.
Do NOT include markdown fences or explanations.

{
  "name": string (required, workflow name),
  "nodes": [
    {
      "id": string (required, unique node identifier),
      "kind": string (required, one of: llm, tool, retriever,
        transform, router, human_gate, join, side_effect),
      "executor": string (required, executor reference),
      "inputs": object (optional),
      "outputs": object (optional),
      "params": object (optional)
    }
  ],
  "edges": [
    {
      "from": string (required),
      "to": string (required),
      "kind": string (optional, one of: linear, conditional,
        loop, fanout, join; defaults to linear),
      "condition": object (optional),
      "join_sources": array of string (optional, required when kind="join"),
      "loop_guard": object (optional),
      "map": object (optional)
    }
  ],
  "entrypoint": string (optional),
  "inputs": object (optional),
  "outputs": object (optional),
  "reducers": object (optional, e.g. {"results": "append"})
}
"""
    parts.append(output_format)

    # Few-shot examples
    few_shot_section = """
## Few-Shot Examples

### Example 1: Multi-Node Retrieval-Augmented Workflow

For workflows that retrieve information then process it in multiple llm stages:

{
  "name": "ResearchWorkflow",
  "inputs": {"topic": "string"},
  "outputs": {"final_summary": "string"},
  "nodes": [
    {
      "id": "search_docs",
      "kind": "retriever",
      "executor": "builtin.mock_retriever",
      "params": {"k": 5},
      "outputs": {"retrieved_docs": "retrieved_docs"}
    },
    {
      "id": "summarize",
      "kind": "llm",
      "executor": "builtin.echo_llm",
      "inputs": {"topic": "topic", "docs": "retrieved_docs"},
      "outputs": {"summary": "summary"},
      "params": {"template": "Summarizing docs about {topic}: {docs}"}
    },
    {
      "id": "polish",
      "kind": "llm",
      "executor": "builtin.echo_llm",
      "inputs": {"summary": "summary"},
      "outputs": {"final_summary": "final_summary"},
      "params": {"template": "Polishing: {summary}"}
    }
  ],
  "edges": [
    {"from": "search_docs", "to": "summarize"},
    {"from": "summarize", "to": "polish"}
  ]
}

### Example 2: High-Risk Workflow with Human Gate and Side Effect

For workflows with dangerous operations (file writes, shell execution,
network access, secrets), combine a `human_gate` for manual review and a
`side_effect` node with `requires_approval`:

{
  "name": "SecureOperation",
  "inputs": {"data": "string"},
  "outputs": {"result": "string"},
  "nodes": [
    {
      "id": "review",
      "kind": "human_gate",
      "executor": "builtin.human_gate",
      "inputs": {"data": "data"},
      "outputs": {"approved": "approved", "data": "data"},
      "params": {"message": "Review sensitive operation with: {data}. Approve?"}
    },
    {
      "id": "execute_write",
      "kind": "side_effect",
      "executor": "builtin.side_effect",
      "inputs": {"data": "data"},
      "outputs": {"result": "result"},
      "params": {"action": "file_write"},
      "security": {"requires_approval": true}
    }
  ],
  "edges": [
    {"from": "review", "to": "execute_write"}
  ]
}

### Example 3: Workflow with Tool Node

For workflows that need to call external tools, use a `tool` node
with an executor reference and declare it in `allowed_tool_refs`:

{
  "name": "ToolWorkflow",
  "inputs": {"query": "string"},
  "outputs": {"answer": "string"},
  "nodes": [
    {
      "id": "search",
      "kind": "tool",
      "executor": "tool.web_search",
      "inputs": {"query": "query"},
      "outputs": {"result": "search_result"}
    },
    {
      "id": "summarize",
      "kind": "llm",
      "executor": "builtin.echo_llm",
      "inputs": {"text": "search_result"},
      "outputs": {"text": "answer"}
    }
  ],
  "edges": [
    {"from": "search", "to": "summarize"}
  ],
  "policy": {
    "external_call": true,
    "allowed_tool_refs": ["tool.web_search"]
  }
}

Now convert the Skill above to a simplified JSON plan.
"""
    parts.append(few_shot_section)

    return "".join(parts)


def _build_model_client(request: SkillPlanRequest) -> ChatOpenAI:
    from prompt2langgraph.llm.provider import build_llm_client

    return build_llm_client(
        model=request.model,
        base_url=request.base_url,
        api_key=request.api_key,
        temperature=request.temperature,
    )


def generate_skill_plan_text(
    request: SkillPlanRequest,
    *,
    analysis: SkillDirectoryAnalysis,
    model_client: object | None = None,
) -> SkillPlanResult:
    """Generate raw plan text from LLM for a skill directory."""
    from prompt2langgraph.prompting.planner import _extract_response_content

    client = model_client or _build_model_client(request)
    prompt = build_skill_plan_prompt(analysis, skill_dir=request.skill_dir, params=request.params)
    system_msg = (
        "You generate simplified JSON plans. Return ONLY JSON, no markdown fences or explanations."
    )
    response = client.invoke(
        [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ]
    )
    return SkillPlanResult(raw_text=_extract_response_content(response))


def plan_skill_to_workflow_spec(
    request: SkillPlanRequest,
    *,
    model_client: object | None = None,
    analysis: SkillDirectoryAnalysis | None = None,
) -> SkillPlanResult:
    """Convert a Skill directory to a WorkflowSpec via LLM-generated JSON plan.

    Reads SKILL.md, analyzes the skill directory, sends context to LLM,
    parses the returned JSON plan, and converts it to WorkflowSpec.

    Args:
        request: Skill plan request with skill_dir, params, model config.
        model_client: Optional pre-built LLM client (uses build_llm_client() if None).
        analysis: Optional precomputed SkillDirectoryAnalysis (avoids double analysis
            when the caller has already run analyze_skill_dir(), e.g. CLI).

    Returns a SkillPlanResult containing:
    - workflow_spec: the generated WorkflowSpec (None on failure)
    - diagnostics: static analysis diagnostics from analyze_skill_dir()
    - raw_text: the LLM's raw output
    - plan: the parsed JSON plan dict

    Raises:
        AdapterParseError: If SKILL.md is missing, LLM output cannot be parsed,
            or JSON plan cannot be adapted to WorkflowSpec.
        RuntimeError: If the LLM call itself fails.
    """
    # Verify SKILL.md exists and is readable
    skill_path = Path(request.skill_dir)
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        from prompt2langgraph.adapters.base import AdapterParseError

        raise AdapterParseError(
            f"failed to read skill file {skill_md}: file does not exist",
            source="skill",
        )

    # Static analysis (reuse precomputed if provided)
    if analysis is None:
        analysis = analyze_skill_dir(request.skill_dir)

    # Generate plan text
    result = generate_skill_plan_text(
        request,
        analysis=analysis,
        model_client=model_client,
    )
    # Propagate static analysis diagnostics for caller observability
    result.diagnostics = list(analysis.report.diagnostics)

    # Parse JSON
    try:
        result.plan = parse_prompt_plan_text(result.raw_text, source="skill")
    except Exception as exc:
        from prompt2langgraph.adapters.base import AdapterParseError

        raise AdapterParseError(
            f"failed to parse generated JSON plan: {result.raw_text[:2000]}",
            source="skill",
        ) from exc

    # Convert to WorkflowSpec
    result.workflow_spec = JSONPlanAdapter().parse(result.plan, source="skill")
    return result
