from prompt2langgraph.prompting.planner import (
    PromptPlanRequest,
    PromptPlanResult,
    generate_plan_text,
    plan_prompt_to_workflow_spec,
)


def test_prompting_module_exports_request_and_result_types() -> None:
    request = PromptPlanRequest(prompt="build a simple answer workflow")
    result = PromptPlanResult(
        raw_text='{"name":"Demo","nodes":[],"edges":[]}',
        plan=None,
        diagnostics=[],
    )

    assert request.prompt == "build a simple answer workflow"
    assert result.raw_text.startswith("{")


def test_load_prompt_planner_config_reads_env(monkeypatch) -> None:
    from prompt2langgraph.prompting.config import load_prompt_planner_config

    monkeypatch.setenv("MODEL", "qwen-plus")
    monkeypatch.setenv("BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("API_KEY", "secret")

    config = load_prompt_planner_config()

    assert config.model == "qwen-plus"
    assert config.base_url == "https://example.com/v1"
    assert config.api_key == "secret"


class FakeModel:
    def invoke(self, messages):
        return type(
            "Response",
            (),
            {
                "content": (
                    '{"name":"Demo","nodes":[{"id":"compose",'
                    '"kind":"llm","executor":"builtin.echo_llm"}],"edges":[]}'
                )
            },
        )()


def test_generate_plan_text_uses_model_and_returns_text() -> None:
    request = PromptPlanRequest(prompt="build a simple answer workflow")

    result = generate_plan_text(request, model_client=FakeModel())

    assert result.raw_text.startswith("{")
    assert '"name":"Demo"' in result.raw_text


def test_build_model_client_accepts_openai_style_config(monkeypatch) -> None:
    from prompt2langgraph.prompting.planner import build_model_client

    monkeypatch.setenv("MODEL", "qwen-turbo")
    monkeypatch.setenv("BASE_URL", "https://env.example.com/v1")
    monkeypatch.setenv("API_KEY", "env-key")

    request = PromptPlanRequest(
        prompt="build a workflow",
        model="qwen-plus",
        base_url="https://example.com/v1",
        api_key="test-key",
        temperature=0.2,
    )

    client = build_model_client(request)

    assert client.model_name == "qwen-plus"
    assert str(client.openai_api_base) == "https://example.com/v1"


def test_build_model_client_uses_env_defaults_when_request_fields_missing(monkeypatch) -> None:
    from prompt2langgraph.prompting.planner import build_model_client

    monkeypatch.setenv("MODEL", "qwen-plus")
    monkeypatch.setenv("BASE_URL", "https://env.example.com/v1")
    monkeypatch.setenv("API_KEY", "env-key")

    request = PromptPlanRequest(prompt="build a workflow")
    client = build_model_client(request)

    assert client.model_name == "qwen-plus"
    assert str(client.openai_api_base) == "https://env.example.com/v1"


def test_build_model_client_defaults_to_qwen_plus_when_no_config(monkeypatch) -> None:
    from prompt2langgraph.prompting.config import PromptPlannerConfig
    from prompt2langgraph.prompting.planner import build_model_client

    monkeypatch.setattr(
        "prompt2langgraph.prompting.planner.load_prompt_planner_config",
        lambda: PromptPlannerConfig(),
    )

    request = PromptPlanRequest(prompt="build a workflow", api_key="dummy-key")
    client = build_model_client(request)

    assert client.model_name == "qwen-plus"


class FakeListModel:
    def invoke(self, messages):
        return type(
            "Response",
            (),
            {
                "content": [
                    '{"name":"Demo","nodes":[{"id":"compose",'
                    '"kind":"llm","executor":"builtin.echo_llm"}],"edges":[]}'
                ]
            },
        )()


def test_generate_plan_text_handles_list_content() -> None:
    request = PromptPlanRequest(prompt="build a simple answer workflow")

    result = generate_plan_text(request, model_client=FakeListModel())

    assert result.raw_text.startswith("{")
    assert '"name":"Demo"' in result.raw_text


class FakeWorkflowModel:
    def invoke(self, messages):
        return type(
            "Response",
            (),
            {
                "content": (
                    '{"name":"Demo","inputs":{"question":"string"},'
                    '"outputs":{"answer":"string"},'
                    '"nodes":[{"id":"compose","kind":"llm","executor":"builtin.echo_llm"}],'
                    '"edges":[]}'
                )
            },
        )()


def test_plan_prompt_to_workflow_spec_reuses_json_plan_adapter() -> None:
    workflow = plan_prompt_to_workflow_spec(
        PromptPlanRequest(prompt="answer a question"),
        model_client=FakeWorkflowModel(),
    )

    assert workflow.workflow_id == "demo"
    assert workflow.entrypoint == "compose"


class FakeBadModel:
    def invoke(self, messages):
        return type("Response", (), {"content": "[1,2,3]"})()


def test_plan_prompt_to_workflow_spec_raises_parse_error_for_non_object_output() -> None:
    import pytest

    from prompt2langgraph.adapters.base import AdapterParseError

    with pytest.raises(AdapterParseError):
        plan_prompt_to_workflow_spec(
            PromptPlanRequest(prompt="bad plan"),
            model_client=FakeBadModel(),
        )


class FakeInvalidJsonModel:
    def invoke(self, messages):
        return type("Response", (), {"content": "I don't know"})()


def test_plan_prompt_to_workflow_spec_raises_parse_error_for_invalid_json() -> None:
    import pytest

    from prompt2langgraph.adapters.base import AdapterParseError

    with pytest.raises(AdapterParseError):
        plan_prompt_to_workflow_spec(
            PromptPlanRequest(prompt="invalid json"),
            model_client=FakeInvalidJsonModel(),
        )


class FakeMissingFieldsModel:
    def invoke(self, messages):
        return type("Response", (), {"content": '{"name":"Demo"}'})()


def test_plan_prompt_to_workflow_spec_raises_parse_error_for_missing_required_fields() -> None:
    import pytest

    from prompt2langgraph.adapters.base import AdapterParseError

    with pytest.raises(AdapterParseError):
        plan_prompt_to_workflow_spec(
            PromptPlanRequest(prompt="missing fields"),
            model_client=FakeMissingFieldsModel(),
        )
