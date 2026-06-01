import json
from pathlib import Path
from typing import Any

import pytest

from prompt2langgraph.adapters.base import AdapterParseError
from prompt2langgraph.adapters.json_plan import json_plan_to_workflow_spec
from prompt2langgraph.adapters.skill_dir import analyze_skill_dir
from prompt2langgraph.ir.models import EdgeKind, WorkflowSpec
from prompt2langgraph.prompting.parser import parse_prompt_plan_text
from prompt2langgraph.registry.executors import ExecutorDefinition, ExecutorRegistry
from prompt2langgraph.registry.tool_executor import ToolCallableRegistry
from prompt2langgraph.validate.validator import validate_workflow

CORPUS = Path(__file__).parent / "prompts_skills_test"


def _load_json(path: Path) -> dict[str, Any] | list[Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _case_id(case: dict[str, Any]) -> str:
    return str(case["id"])


def _test_cases() -> dict[str, Any]:
    data = _load_json(CORPUS / "test_cases.json")
    assert isinstance(data, dict)
    return data["test_cases"]


def _json_plan_cases() -> list[dict[str, Any]]:
    return list(_test_cases()["json_plan_tests"])


def _negative_cases() -> list[dict[str, Any]]:
    return list(_test_cases()["negative_tests"])


def _prompt_workflow_cases() -> list[dict[str, Any]]:
    data = _load_json(CORPUS / "prompt_workflow_cases.json")
    assert isinstance(data, list)
    return data


def _load_plan_from_case(case: dict[str, Any]) -> dict[str, Any]:
    path = CORPUS / str(case["json_plan_file"])
    data = _load_json(path)
    assert isinstance(data, dict)
    plan = data["json_plan"]
    assert isinstance(plan, dict)
    return plan


def _build_corpus_executor_registry() -> ExecutorRegistry:
    from prompt2langgraph.ir.models import ExecutorType, TypeName, TypeSpec
    from prompt2langgraph.registry.builtins import builtin_executor_registry

    registry = builtin_executor_registry()
    llm_executor = registry.get("llm.qwen-plus")
    registry.register(
        ExecutorDefinition(
            ref="llm.gpt-4",
            type=llm_executor.type,
            dynamic=llm_executor.dynamic,
            input_schema=llm_executor.input_schema,
            output_schema=llm_executor.output_schema,
            handler=llm_executor.handler,
        )
    )
    registry.register(
        ExecutorDefinition(
            ref="tool.unregistered_tool",
            type=ExecutorType.PYTHON_CALLABLE,
            input_schema={"value": TypeSpec(type=TypeName.ANY)},
            output_schema={"value": TypeSpec(type=TypeName.ANY)},
            handler=lambda inputs, params: dict(inputs),
        )
    )
    return registry


def _validation_error_codes(workflow: WorkflowSpec) -> list[str]:
    tool_registry = ToolCallableRegistry()
    report = validate_workflow(
        workflow,
        executors=_build_corpus_executor_registry(),
        tool_registry=tool_registry,
    )
    return [diagnostic.code for diagnostic in report.diagnostics if diagnostic.severity == "error"]


@pytest.mark.parametrize("case", _json_plan_cases(), ids=_case_id)
def test_prompt_skill_corpus_json_plans_are_valid(case: dict[str, Any]) -> None:
    workflow = json_plan_to_workflow_spec(
        _load_plan_from_case(case),
        executors=_build_corpus_executor_registry(),
        source=case["json_plan_file"],
    )

    node_types = {node.kind for node in workflow.nodes}
    assert set(case["expected_node_types"]).issubset(node_types)
    edge_kinds = {edge.kind.value for edge in workflow.edges}
    assert set(case["expected_patterns"]).issubset(edge_kinds | node_types)

    if "expected_loop_guard" in case:
        loop_edges = [edge for edge in workflow.edges if edge.kind is EdgeKind.LOOP]
        assert loop_edges
        assert loop_edges[0].loop_guard is not None
        assert (
            loop_edges[0].loop_guard.max_iterations == case["expected_loop_guard"]["max_iterations"]
        )

    if "expected_join_sources" in case:
        join_edges = [edge for edge in workflow.edges if edge.kind is EdgeKind.JOIN]
        assert join_edges
        assert join_edges[0].join_sources == case["expected_join_sources"]

    if "expected_reducers" in case:
        assert {
            key: reducer.value for key, reducer in workflow.state_schema.reducers.items()
        } == case["expected_reducers"]

    if "expected_security_policy" in case:
        side_effect_nodes = [node for node in workflow.nodes if node.kind == "side_effect"]
        assert side_effect_nodes
        assert side_effect_nodes[0].security is not None
        assert (
            side_effect_nodes[0].security.requires_approval
            is case["expected_security_policy"]["requires_approval"]
        )

    assert _validation_error_codes(workflow) == []


@pytest.mark.parametrize("case", _prompt_workflow_cases(), ids=_case_id)
def test_prompt_workflow_inline_plans_match_expected_validity(case: dict[str, Any]) -> None:
    workflow = json_plan_to_workflow_spec(case["plan"], executors=_build_corpus_executor_registry())
    codes = _validation_error_codes(workflow)

    if case["expected_valid"]:
        assert codes == []
    else:
        assert set(case["expected_error_codes"]).issubset(set(codes))


@pytest.mark.parametrize("case", _negative_cases(), ids=_case_id)
def test_prompt_skill_corpus_negative_cases_report_expected_errors(
    case: dict[str, Any],
) -> None:
    expected = case["expected_error"]

    if case["test_category"] == "parse_negative":
        data = _load_json(CORPUS / str(case["test_file"]))
        assert isinstance(data, dict)
        with pytest.raises(AdapterParseError):
            parse_prompt_plan_text(str(data["llm_output"]))
        return

    if case.get("test_function") == "analyze_skill_dir":
        analysis = analyze_skill_dir(CORPUS / str(case["skill_dir"]))
        assert expected in [diagnostic.code for diagnostic in analysis.report.diagnostics]
        return

    if case["test_category"] == "skill_negative":
        data = _load_json(CORPUS / str(case["test_file"]))
        assert isinstance(data, dict)
        skill_dir = CORPUS / "invalid" / "skill_no_frontmatter"
        analysis = analyze_skill_dir(skill_dir)
        assert expected in [diagnostic.code for diagnostic in analysis.report.diagnostics]
        assert data["skill_content"].startswith("# My Skill")
        return

    data = _load_json(CORPUS / str(case["test_file"]))
    assert isinstance(data, dict)
    workflow = json_plan_to_workflow_spec(
        data["json_plan"],
        executors=_build_corpus_executor_registry(),
        source=case["test_file"],
    )

    assert expected in _validation_error_codes(workflow)
