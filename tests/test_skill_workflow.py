"""Tests for skill-to-workflow LLM-driven conversion."""

import pytest

from prompt2langgraph.adapters.base import AdapterParseError
from prompt2langgraph.adapters.skill_dir import analyze_skill_dir
from prompt2langgraph.ir.models import WorkflowSpec
from prompt2langgraph.prompting.skill_planner import (
    SkillPlanRequest,
    SkillPlanResult,
    build_skill_plan_prompt,
    plan_skill_to_workflow_spec,
)
from prompt2langgraph.validate.validator import validate_workflow


class FakeSkillModel:
    """Fake model that returns a valid simplified JSON plan."""

    def invoke(self, messages):
        content = (
            '{"name":"SkillWorkflow","inputs":{"question":"string"},'
            '"outputs":{"answer":"string"},'
            '"nodes":[{"id":"step_1","kind":"llm","executor":"builtin.echo_llm"},'
            '{"id":"step_2","kind":"transform","executor":"builtin.identity_transform"}],'
            '"edges":[{"from":"step_1","to":"step_2"}]}'
        )
        return type("Response", (), {"content": content})()


class FakeSkillModelNoEdges:
    """Fake model that returns a plan without edges (should get warning)."""

    def invoke(self, messages):
        content = (
            '{"name":"NoEdges","inputs":{},"outputs":{},'
            '"nodes":[{"id":"n1","kind":"llm","executor":"builtin.echo_llm"}]}'
        )
        return type("Response", (), {"content": content})()


class FakeSkillModelInvalidJson:
    """Fake model that returns invalid JSON."""

    def invoke(self, messages):
        return type("Response", (), {"content": "not json at all"})()


class FakeSkillModelNonObject:
    """Fake model that returns non-object JSON."""

    def invoke(self, messages):
        return type("Response", (), {"content": "[1,2,3]"})()


def test_skill_plan_request_and_result_types():
    """SkillPlanRequest and SkillPlanResult have expected fields."""
    request = SkillPlanRequest(skill_dir="tests/fixtures/skill_basic")
    assert request.skill_dir == "tests/fixtures/skill_basic"
    assert request.params == {}
    assert request.temperature == 0.0

    result = SkillPlanResult(raw_text='{"name":"test"}', plan=None, diagnostics=[])
    assert result.raw_text == '{"name":"test"}'
    assert result.diagnostics == []


def test_plan_skill_to_workflow_spec_with_fake_model():
    """Fake model returns valid JSON plan; result is valid WorkflowSpec."""
    request = SkillPlanRequest(skill_dir="tests/fixtures/skill_basic")
    result = plan_skill_to_workflow_spec(request, model_client=FakeSkillModel())

    assert result is not None
    assert result.workflow_id == "skillworkflow"
    assert result.entrypoint == "step_1"
    report = validate_workflow(result)
    assert report.ok, f"validation failed: {report.diagnostics}"


def test_plan_skill_to_workflow_spec_returns_workflow_spec():
    """plan_skill_to_workflow_spec() returns WorkflowSpec directly."""
    request = SkillPlanRequest(skill_dir="tests/fixtures/skill_basic")
    result = plan_skill_to_workflow_spec(request, model_client=FakeSkillModel())

    assert isinstance(result, WorkflowSpec)
    assert result.workflow_id == "skillworkflow"


def test_plan_skill_to_workflow_spec_no_edges_raises():
    """Plan without edges raises AdapterParseError (edges required)."""
    request = SkillPlanRequest(skill_dir="tests/fixtures/skill_basic")
    with pytest.raises(AdapterParseError):
        plan_skill_to_workflow_spec(
            request, model_client=FakeSkillModelNoEdges()
        )


def test_plan_skill_to_workflow_spec_invalid_json_raises():
    """Invalid JSON from model raises AdapterParseError."""
    request = SkillPlanRequest(skill_dir="tests/fixtures/skill_basic")
    with pytest.raises(AdapterParseError):
        plan_skill_to_workflow_spec(request, model_client=FakeSkillModelInvalidJson())


def test_plan_skill_to_workflow_spec_non_object_raises():
    """Non-object JSON from model raises AdapterParseError."""
    request = SkillPlanRequest(skill_dir="tests/fixtures/skill_basic")
    with pytest.raises(AdapterParseError):
        plan_skill_to_workflow_spec(request, model_client=FakeSkillModelNonObject())


def test_build_skill_plan_prompt_contains_skill_name_and_description():
    """Prompt contains skill name and description from frontmatter."""
    analysis = analyze_skill_dir("tests/fixtures/skill_basic")
    prompt = build_skill_plan_prompt(analysis, params={})

    assert "skill-basic" in prompt
    assert "Analyze a simple skill safely" in prompt


def test_build_skill_plan_prompt_contains_steps():
    """Prompt contains numbered steps summary."""
    analysis = analyze_skill_dir("tests/fixtures/skill_basic")
    prompt = build_skill_plan_prompt(analysis, params={})

    assert "1. Read the user's request" in prompt
    assert "2. Write files with a shell command" in prompt
    assert "3. Fetch a network resource and inspect secrets" in prompt


def test_build_skill_plan_prompt_contains_resources():
    """Prompt contains resource file list."""
    analysis = analyze_skill_dir("tests/fixtures/skill_basic")
    prompt = build_skill_plan_prompt(analysis, params={})

    assert "scripts/danger.sh" in prompt
    assert "references/guide.md" in prompt


def test_build_skill_plan_prompt_contains_risk_warning():
    """Prompt contains E_SEC_007 risk diagnostic for dangerous operations."""
    analysis = analyze_skill_dir("tests/fixtures/skill_basic")
    prompt = build_skill_plan_prompt(analysis, params={})

    # danger.sh and risk keywords should appear in diagnostics
    assert "E_SEC_007" in prompt or "risk" in prompt.lower()


def test_build_skill_plan_prompt_contains_node_types_and_executors():
    """Prompt lists available node types and executor refs."""
    analysis = analyze_skill_dir("tests/fixtures/skill_basic")
    prompt = build_skill_plan_prompt(analysis, params={})

    assert "builtin.echo_llm" in prompt
    assert "builtin.identity_transform" in prompt
    assert "llm" in prompt
    assert "transform" in prompt


def test_build_skill_plan_prompt_says_only_json():
    """Prompt explicitly instructs to only return JSON."""
    analysis = analyze_skill_dir("tests/fixtures/skill_basic")
    prompt = build_skill_plan_prompt(analysis, params={})

    assert "JSON" in prompt
    assert "execute" not in prompt.lower() or "do not" in prompt.lower() or "only" in prompt.lower()


def test_build_skill_plan_prompt_contains_state_schema_constraints():
    """Prompt includes state key naming rules and reserved words."""
    analysis = analyze_skill_dir("tests/fixtures/skill_basic")
    prompt = build_skill_plan_prompt(analysis, params={})

    # Reserved words should be mentioned
    assert "__pt2lg_side_effect_results__" in prompt or "reserved" in prompt.lower()
    assert "reducer" in prompt or "state" in prompt.lower()


def test_build_skill_plan_prompt_contains_few_shot_examples():
    """Prompt includes few-shot examples for retrieval, high-risk, and tool workflows."""
    analysis = analyze_skill_dir("tests/fixtures/skill_basic")
    prompt = build_skill_plan_prompt(analysis, params={})

    # Should have example workflow names
    assert "ResearchWorkflow" in prompt
    assert "SecureOperation" in prompt
    assert "ToolWorkflow" in prompt
    assert "example" in prompt.lower() or "Example" in prompt


def test_build_skill_plan_prompt_with_params():
    """Prompt includes parameter context when provided."""
    analysis = analyze_skill_dir("tests/fixtures/skill_basic")
    params = {"question": "hello", "topic": "testing"}
    prompt = build_skill_plan_prompt(analysis, params=params)

    assert "question" in prompt
    assert "hello" in prompt
    assert "topic" in prompt


def test_plan_skill_to_workflow_spec_includes_analysis_context():
    """plan_skill_to_workflow_spec uses analyze_skill_dir output internally."""
    request = SkillPlanRequest(skill_dir="tests/fixtures/skill_basic")

    # This should not raise - it uses analyze_skill_dir internally
    result = plan_skill_to_workflow_spec(request, model_client=FakeSkillModel())
    assert result is not None
    assert isinstance(result, WorkflowSpec)
    assert result.workflow_id == "skillworkflow"


def test_skill_plan_result_with_diagnostics():
    """SkillPlanResult stores diagnostics list."""
    result = SkillPlanResult(
        raw_text='{"name":"test"}',
        plan={"name": "test", "nodes": [], "edges": []},
        diagnostics=[],
    )
    assert result.diagnostics == []
    assert result.plan is not None


def test_plan_skill_to_workflow_spec_raises_when_skill_md_missing(tmp_path) -> None:
    """plan_skill_to_workflow_spec should raise AdapterParseError when SKILL.md is missing."""
    request = SkillPlanRequest(skill_dir=str(tmp_path))
    with pytest.raises(AdapterParseError):
        plan_skill_to_workflow_spec(request, model_client=FakeSkillModel())


def test_build_skill_plan_prompt_reads_skill_md_from_skill_dir() -> None:
    """build_skill_plan_prompt should read SKILL.md from skill_dir parameter."""
    analysis = analyze_skill_dir("tests/fixtures/skill_basic")
    prompt = build_skill_plan_prompt(analysis, skill_dir="tests/fixtures/skill_basic")
    # The prompt should contain the SKILL.md content
    assert "skill-basic" in prompt or "Analyze a simple skill safely" in prompt


def test_build_skill_plan_prompt_contains_risk_warning_precise() -> None:
    """Prompt should contain E_SEC_007 when risk diagnostics are present."""
    analysis = analyze_skill_dir("tests/fixtures/skill_basic")
    prompt = build_skill_plan_prompt(analysis, skill_dir="tests/fixtures/skill_basic")
    # skill_basic has danger.sh which triggers E_SEC_007
    assert "E_SEC_007" in prompt
    assert "risk" in prompt.lower()


def test_plan_skill_to_workflow_spec_llm_failure_raises() -> None:
    """plan_skill_to_workflow_spec should raise when LLM call fails."""

    class FailingModel:
        def invoke(self, messages):
            raise RuntimeError("connection refused")

    request = SkillPlanRequest(skill_dir="tests/fixtures/skill_basic")
    with pytest.raises(RuntimeError, match="connection refused"):
        plan_skill_to_workflow_spec(request, model_client=FailingModel())
