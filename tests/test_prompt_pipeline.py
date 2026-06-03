from prompt2langgraph.prompting.pipeline import plan_prompt, plan_skill
from prompt2langgraph.prompting.planner import PromptPlanRequest
from prompt2langgraph.prompting.skill_planner import SkillPlanRequest


class _FakeModel:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls = 0

    def invoke(self, messages):
        response = self.responses[self.calls]
        self.calls += 1
        return type("Response", (), {"content": response})()


class _FakeSkillModel:
    def invoke(self, messages):
        content = (
            '{"name":"SkillWorkflow","inputs":{"question":"string"},'
            '"outputs":{"answer":"string"},'
            '"nodes":[{"id":"step_1","kind":"llm","executor":"builtin.echo_llm"}],'
            '"edges":[]}'
        )
        return type("Response", (), {"content": content})()


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


def _valid_plan_text() -> str:
    return (
        '{"name":"Demo","inputs":{"question":"string"},"outputs":{"answer":"string"},'
        '"nodes":[{"id":"compose","kind":"llm","executor":"builtin.echo_llm"}],'
        '"edges":[]}'
    )


def _tool_executor_registry():
    from prompt2langgraph.ir.models import ExecutorType
    from prompt2langgraph.registry.builtins import builtin_executor_registry
    from prompt2langgraph.registry.executors import ExecutorDefinition

    registry = builtin_executor_registry()
    registry.register(
        ExecutorDefinition(
            ref="fake.upper",
            type=ExecutorType.PYTHON_CALLABLE,
            dynamic=True,
        )
    )
    return registry


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


def test_prompt_pipeline_reports_repair_llm_call_failure() -> None:
    class FailingRepairModel:
        def __init__(self) -> None:
            self.calls = 0

        def invoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                return type("Response", (), {"content": "not json"})()
            raise RuntimeError("repair unavailable")

    result = plan_prompt(
        PromptPlanRequest(prompt="repair call fails", repair_attempts=1),
        model_client=FailingRepairModel(),
        compile_smoke=True,
    )

    assert result.ok is False
    assert len(result.repair_attempts) == 1
    assert result.repair_attempts[0].trigger_stage == "parse"
    assert result.repair_attempts[0].ok is False
    assert any(diagnostic.code == "E_RUNTIME_010" for diagnostic in result.diagnostics)


def test_prompt_pipeline_reports_validation_failure_stage() -> None:
    result = plan_prompt(
        PromptPlanRequest(prompt="invalid executor"),
        model_client=_FakeModel(
            [
                (
                    '{"name":"Bad","nodes":[{"id":"compose","kind":"llm",'
                    '"executor":"builtin.nonexistent"}],"edges":[]}'
                )
            ]
        ),
        compile_smoke=True,
    )

    assert result.ok is False
    assert result.stages["parse"].ok is True
    assert result.stages["adapter"].ok is True
    assert result.stages["validation"].ok is False
    assert result.stages["compile_smoke"].skipped is True


def test_skill_pipeline_static_error_skips_generation() -> None:
    result = plan_skill(
        SkillPlanRequest(skill_dir="tests/prompts_skills_test/invalid/skill_no_frontmatter"),
        model_client=_FakeModel([_valid_plan_text()]),
        compile_smoke=True,
    )

    assert result.ok is False
    assert result.raw_text is None
    assert result.stages["generation"].skipped is True
    assert result.stages["parse"].skipped is True
    assert any(diagnostic.code == "E_SCHEMA_002" for diagnostic in result.diagnostics)


def test_skill_pipeline_preserves_static_risk_diagnostics() -> None:
    result = plan_skill(
        SkillPlanRequest(skill_dir="tests/fixtures/skill_basic"),
        model_client=_FakeSkillModel(),
        compile_smoke=True,
    )

    assert result.ok is True
    assert any(diagnostic.code == "E_SEC_007" for diagnostic in result.diagnostics)


def test_plan_prompt_reports_missing_tool_readiness() -> None:
    from prompt2langgraph.registry.tool_executor import ToolCallableRegistry

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
    from prompt2langgraph.registry.tool_executor import ToolCallableRegistry

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
    from prompt2langgraph.registry.tool_executor import ToolCallableRegistry

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
    from prompt2langgraph.registry.tool_executor import ToolCallableRegistry

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
    from prompt2langgraph.registry.tool_executor import ToolCallableRegistry

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
