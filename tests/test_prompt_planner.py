from prompt2langgraph.prompting.planner import PromptPlanRequest, PromptPlanResult


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
