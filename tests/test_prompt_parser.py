import pytest

from prompt2langgraph.adapters.base import AdapterParseError
from prompt2langgraph.prompting.parser import parse_prompt_plan_text


def test_parse_prompt_plan_text_returns_object_for_valid_json() -> None:
    plan = parse_prompt_plan_text(
        '{"name":"Demo","nodes":[{"id":"compose","kind":"llm","executor":"builtin.echo_llm"}],"edges":[]}'
    )
    assert plan["name"] == "Demo"


def test_parse_prompt_plan_text_rejects_non_object_json() -> None:
    with pytest.raises(AdapterParseError) as exc_info:
        parse_prompt_plan_text("[1, 2, 3]")

    assert "must contain an object" in str(exc_info.value)
    assert exc_info.value.source == "prompt"


def test_parse_prompt_plan_text_rejects_empty_string() -> None:
    with pytest.raises(AdapterParseError) as exc_info:
        parse_prompt_plan_text("")

    assert "failed to parse" in str(exc_info.value)
    assert exc_info.value.source == "prompt"


def test_parse_prompt_plan_text_rejects_json_primitives() -> None:
    for text in ['42', '"hello"', "true", "null"]:
        with pytest.raises(AdapterParseError, match="must contain an object"):
            parse_prompt_plan_text(text)


def test_parse_prompt_plan_text_uses_custom_source() -> None:
    with pytest.raises(AdapterParseError) as exc_info:
        parse_prompt_plan_text("[1]", source="custom_source")

    assert exc_info.value.source == "custom_source"
