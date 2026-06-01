import json
from pathlib import Path
from typing import Any

import pytest

from prompt2langgraph.adapters.base import AdapterParseError
from prompt2langgraph.adapters.json_plan import json_plan_to_workflow_spec
from prompt2langgraph.adapters.skill_dir import analyze_skill_dir
from prompt2langgraph.compiler.langgraph_py import compile_workflow_to_graph
from prompt2langgraph.ir.models import EdgeKind, WorkflowSpec
from prompt2langgraph.prompting.parser import parse_prompt_plan_text
from prompt2langgraph.prompting.planner import PromptPlanRequest, plan_prompt_to_workflow_spec
from prompt2langgraph.prompting.skill_planner import SkillPlanRequest, plan_skill_to_workflow_spec
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


def _test_catalog() -> dict[str, Any]:
    data = _load_json(CORPUS / "test_cases.json")
    assert isinstance(data, dict)
    return data


def _json_plan_cases() -> list[dict[str, Any]]:
    return list(_test_cases()["json_plan_tests"])


def _skill_to_workflow_cases() -> list[dict[str, Any]]:
    return list(_test_cases()["skill_to_workflow_tests"])


def _prompt_to_workflow_cases() -> list[dict[str, Any]]:
    return list(_test_cases()["prompt_to_workflow_tests"])


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


def _assert_valid_and_compilable(workflow: WorkflowSpec) -> None:
    assert _validation_error_codes(workflow) == []
    graph = compile_workflow_to_graph(workflow, _build_corpus_executor_registry())
    assert graph is not None


def _assert_expected_shape(workflow: WorkflowSpec, case: dict[str, Any]) -> None:
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


def _executor_for_kind(kind: str) -> str:
    return {
        "llm": "builtin.echo_llm",
        "retriever": "builtin.mock_retriever",
        "router": "builtin.route",
        "human_gate": "builtin.human_gate",
        "side_effect": "builtin.side_effect",
    }.get(kind, "builtin.identity_transform")


def _node(node_id: str, kind: str, *, output_key: str | None = None) -> dict[str, Any]:
    output_state_key = output_key or f"{node_id}_value"
    node: dict[str, Any] = {
        "id": node_id,
        "kind": kind,
        "executor": _executor_for_kind(kind),
        "inputs": {"value": "value"},
        "outputs": {"value": output_state_key},
    }
    if kind == "llm":
        node["inputs"] = {"question": "question"}
        node["outputs"] = {"answer": output_state_key}
    elif kind == "retriever":
        node["inputs"] = {"question": "question"}
        node["outputs"] = {"docs_ref": output_state_key}
    elif kind == "router":
        node["inputs"] = {"value": "value"}
        node["outputs"] = {}
    elif kind == "human_gate":
        node["outputs"] = {"approval": "approval", "value": output_state_key}
    elif kind == "side_effect":
        node["security"] = {"requires_approval": True}
    return node


def _offline_plan_for_case(case: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic simplified plan matching a catalog case.

    The corpus tests keep LLM calls outside the default path. These plans let the
    prompt/skill planner pipeline exercise parse, adapt, validate, and compile
    behavior while the model response itself stays deterministic.
    """
    patterns = set(case["expected_patterns"])
    node_types = list(dict.fromkeys(case["expected_node_types"]))

    if {"conditional", "fanout", "join"}.issubset(patterns):
        join_sources = ["process_chunk_a", "process_chunk_b"]
        return {
            "name": case["id"],
            "entrypoint": "route_input",
            "inputs": {
                "question": "string",
                "value": "string",
                "confidence": "number",
                "items": {"type": "array", "item_type": {"type": "string"}},
                "item": "string",
            },
            "outputs": {
                "answer": "string",
                "chunk_results": {"type": "array", "item_type": {"type": "string"}},
            },
            "state_schema": {"reducers": {"chunk_results": "append"}},
            "nodes": [
                _node("route_input", "router"),
                _node("prepare_items", "transform", output_key="items"),
                *[_node(source, "tool", output_key="chunk_results") for source in join_sources],
                _node("aggregate", "join", output_key="answer"),
                _node("review", "human_gate", output_key="answer"),
                _node("persist", "side_effect", output_key="answer"),
            ],
            "edges": [
                {
                    "from": "route_input",
                    "to": "prepare_items",
                    "kind": "conditional",
                    "condition": {
                        "expr": "confidence >= 0.8",
                        "routes": {"true": "prepare_items", "false": "review"},
                    },
                },
                {
                    "from": "prepare_items",
                    "to": "process_chunk_a",
                    "kind": "fanout",
                    "map": {
                        "items_state_key": "items",
                        "item_state_key": "item",
                        "result_state_key": "chunk_results",
                    },
                },
                {
                    "from": "prepare_items",
                    "to": "process_chunk_b",
                    "kind": "fanout",
                    "map": {
                        "items_state_key": "items",
                        "item_state_key": "item",
                        "result_state_key": "chunk_results",
                    },
                },
                {
                    "from": "process_chunk_a",
                    "to": "aggregate",
                    "kind": "join",
                    "join_sources": join_sources,
                },
                {"from": "aggregate", "to": "review"},
                {"from": "review", "to": "persist"},
            ],
        }

    if "fanout" in patterns:
        join_sources = case.get(
            "expected_join_sources",
            ["search_web", "search_academic", "search_news"],
        )
        nodes = [
            _node("prepare_items", "transform", output_key="items"),
            *[_node(source, "tool", output_key=f"{source}_results") for source in join_sources],
        ]
        if "join" in patterns or "join" in node_types:
            nodes.append(_node("aggregate", "join", output_key="combined"))
        if "llm" in node_types:
            nodes.append(_node("synthesize", "llm", output_key="answer"))
        edges = [
            {
                "from": "prepare_items",
                "to": source,
                "kind": "fanout",
                "map": {
                    "items_state_key": "items",
                    "item_state_key": "item",
                    "result_state_key": f"{source}_results",
                },
            }
            for source in join_sources
        ]
        if "join" in patterns or "join" in node_types:
            edges.append(
                {
                    "from": join_sources[0],
                    "to": "aggregate",
                    "kind": "join",
                    "join_sources": join_sources,
                }
            )
            if "llm" in node_types:
                edges.append({"from": "aggregate", "to": "synthesize"})
        return {
            "name": case["id"],
            "entrypoint": "prepare_items",
            "inputs": {
                "question": "string",
                "value": "string",
                "items": {"type": "array", "item_type": {"type": "string"}},
                "item": "string",
            },
            "outputs": {
                "answer": "string",
                **{
                    f"{source}_results": {"type": "array", "item_type": {"type": "string"}}
                    for source in join_sources
                },
            },
            "state_schema": {
                "reducers": {f"{source}_results": "append" for source in join_sources}
            },
            "nodes": nodes,
            "edges": edges,
        }

    if "conditional" in patterns:
        terminal_kind = (
            "human_gate"
            if "human_gate" in node_types
            else "tool"
            if "tool" in node_types
            else "transform"
        )
        nodes = [
            _node("route", "router"),
            _node("high_path", terminal_kind, output_key="answer"),
            _node("normal_path", "transform", output_key="answer"),
        ]
        edges: list[dict[str, Any]] = [
            {
                "from": "route",
                "to": "normal_path",
                "kind": "conditional",
                "condition": {
                    "expr": "confidence >= 0.8",
                    "routes": {"true": "normal_path", "false": "high_path"},
                },
            }
        ]
        if "linear" in patterns:
            edges.append({"from": "high_path", "to": "normal_path"})
        return {
            "name": case["id"],
            "entrypoint": "route",
            "inputs": {"question": "string", "value": "string", "confidence": "number"},
            "outputs": {"answer": "string"},
            "nodes": nodes,
            "edges": edges,
        }

    if "loop" in patterns:
        ordered_kinds = node_types or ["transform"]
        first_kind = ordered_kinds[0]
        tail_nodes = [
            _node(f"after_loop_{index}", kind, output_key="answer")
            for index, kind in enumerate(ordered_kinds[1:] or ["transform"], start=1)
        ]
        return {
            "name": case["id"],
            "entrypoint": "refine",
            "inputs": {"question": "string", "value": "string"},
            "outputs": {"answer": "string"},
            "nodes": [_node("refine", first_kind, output_key="answer"), *tail_nodes],
            "edges": [
                {
                    "from": "refine",
                    "to": "refine",
                    "kind": "loop",
                    "loop_guard": case.get("expected_loop_guard", {"max_iterations": 5}),
                },
                {"from": "refine", "to": tail_nodes[0]["id"]},
            ],
        }

    ordered_kinds = [kind for kind in node_types if kind != "linear"] or ["transform"]
    if "linear" in patterns and len(ordered_kinds) == 1:
        ordered_kinds.append("transform")
    nodes = [
        _node(f"step_{index}", kind, output_key="answer" if index == len(ordered_kinds) else None)
        for index, kind in enumerate(ordered_kinds, start=1)
    ]
    edges = [
        {"from": nodes[index]["id"], "to": nodes[index + 1]["id"]}
        for index in range(len(nodes) - 1)
    ]
    return {
        "name": case["id"],
        "entrypoint": "step_1",
        "inputs": {"question": "string", "value": "string"},
        "outputs": {"answer": "string"},
        "nodes": nodes,
        "edges": edges,
    }


class _FakePlanModel:
    def __init__(
        self,
        plan: dict[str, Any],
        *,
        expected_message_content: tuple[str, ...] = (),
    ) -> None:
        self._plan = plan
        self._expected_message_content = expected_message_content

    def invoke(self, messages: list[dict[str, str]]) -> object:
        assert messages
        message_text = "\n".join(str(message.get("content", "")) for message in messages)
        for expected in self._expected_message_content:
            assert expected in message_text, f"expected model prompt content missing: {expected}"
        return type("Response", (), {"content": json.dumps(self._plan)})()


def test_fake_plan_model_rejects_missing_expected_prompt_content() -> None:
    model = _FakePlanModel(
        {"name": "demo", "nodes": [], "edges": []},
        expected_message_content=("source marker",),
    )

    with pytest.raises(AssertionError, match="source marker"):
        model.invoke([{"role": "user", "content": "unrelated content"}])


def _skill_expected_message_content(skill_dir: Path, analysis: Any) -> tuple[str, ...]:
    raw_skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    first_non_empty_line = next(
        line.strip() for line in raw_skill.splitlines() if line.strip() and line.strip() != "---"
    )
    expected = [first_non_empty_line, analysis.name, analysis.description]
    if analysis.steps:
        expected.append(analysis.steps[0])
    return tuple(item for item in expected if item)


def test_prompt_skill_corpus_manifest_total_matches_declared_cases() -> None:
    catalog = _test_catalog()
    cases = catalog["test_cases"]
    actual_total = sum(len(items) for items in cases.values())

    assert catalog["coverage_summary"]["total_test_cases"] == actual_total


@pytest.mark.parametrize("case", _skill_to_workflow_cases(), ids=_case_id)
def test_prompt_skill_corpus_skill_cases_are_offline_plannable(case: dict[str, Any]) -> None:
    skill_dir = CORPUS / str(case["skill_dir"])
    analysis = analyze_skill_dir(skill_dir)
    error_codes = [
        diagnostic.code
        for diagnostic in analysis.report.diagnostics
        if diagnostic.severity == "error"
    ]
    assert error_codes == []

    workflow = plan_skill_to_workflow_spec(
        SkillPlanRequest(skill_dir=str(skill_dir)),
        analysis=analysis,
        model_client=_FakePlanModel(
            _offline_plan_for_case(case),
            expected_message_content=_skill_expected_message_content(skill_dir, analysis),
        ),
    )

    _assert_expected_shape(workflow, case)
    _assert_valid_and_compilable(workflow)


@pytest.mark.parametrize("case", _prompt_to_workflow_cases(), ids=_case_id)
def test_prompt_skill_corpus_prompt_cases_are_offline_plannable(case: dict[str, Any]) -> None:
    data = _load_json(CORPUS / str(case["prompt_file"]))
    assert isinstance(data, dict)
    assert data["prompt"]

    workflow = plan_prompt_to_workflow_spec(
        PromptPlanRequest(prompt=str(data["prompt"])),
        model_client=_FakePlanModel(
            _offline_plan_for_case(case),
            expected_message_content=(str(data["prompt"]),),
        ),
    )

    _assert_expected_shape(workflow, case)
    _assert_valid_and_compilable(workflow)


@pytest.mark.parametrize("case", _json_plan_cases(), ids=_case_id)
def test_prompt_skill_corpus_json_plans_are_valid(case: dict[str, Any]) -> None:
    workflow = json_plan_to_workflow_spec(
        _load_plan_from_case(case),
        executors=_build_corpus_executor_registry(),
        source=case["json_plan_file"],
    )

    _assert_expected_shape(workflow, case)
    _assert_valid_and_compilable(workflow)


@pytest.mark.parametrize("case", _prompt_workflow_cases(), ids=_case_id)
def test_prompt_workflow_inline_plans_match_expected_validity(case: dict[str, Any]) -> None:
    workflow = json_plan_to_workflow_spec(case["plan"], executors=_build_corpus_executor_registry())
    codes = _validation_error_codes(workflow)

    if case["expected_valid"]:
        _assert_valid_and_compilable(workflow)
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
