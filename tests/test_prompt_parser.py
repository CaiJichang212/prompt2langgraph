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
    for text in ["42", '"hello"', "true", "null"]:
        with pytest.raises(AdapterParseError, match="must contain an object"):
            parse_prompt_plan_text(text)


def test_parse_prompt_plan_text_uses_custom_source() -> None:
    with pytest.raises(AdapterParseError) as exc_info:
        parse_prompt_plan_text("[1]", source="custom_source")

    assert exc_info.value.source == "custom_source"


def test_parse_prompt_plan_text_accepts_fenced_json_object() -> None:
    plan = parse_prompt_plan_text(
        'Here is the plan:\n```json\n{"name":"Demo","nodes":[{"id":"compose","kind":"llm","executor":"builtin.echo_llm"}],"edges":[]}\n```'
    )

    assert plan["name"] == "Demo"


def test_parse_prompt_plan_text_accepts_single_object_inside_explanation() -> None:
    plan = parse_prompt_plan_text(
        'I will return one object: {"name":"Wrapped","nodes":[{"id":"compose","kind":"llm","executor":"builtin.echo_llm"}],"edges":[]} Done.'
    )

    assert plan["name"] == "Wrapped"


def test_parse_prompt_plan_text_accepts_object_then_suffix_text() -> None:
    plan = parse_prompt_plan_text(
        '{"name":"Suffix","nodes":[{"id":"compose","kind":"llm","executor":"builtin.echo_llm"}],"edges":[]} trailing explanation'
    )

    assert plan["name"] == "Suffix"


def test_parse_prompt_plan_text_rejects_multiple_json_objects() -> None:
    with pytest.raises(AdapterParseError) as exc_info:
        parse_prompt_plan_text(
            '{"name":"One","nodes":[],"edges":[]} {"name":"Two","nodes":[],"edges":[]}'
        )

    assert "multiple JSON objects" in str(exc_info.value)
    assert exc_info.value.source == "prompt"
    assert exc_info.value.path == "generated_text"


def test_parse_prompt_plan_text_rejects_fenced_and_body_json_objects() -> None:
    with pytest.raises(AdapterParseError) as exc_info:
        parse_prompt_plan_text(
            '```json\n{"name":"One","nodes":[],"edges":[]}\n```\n'
            '{"name":"Two","nodes":[],"edges":[]}'
        )

    assert "multiple JSON objects" in str(exc_info.value)
    assert exc_info.value.path == "generated_text"


def test_parse_prompt_plan_text_rejects_truncated_wrapped_json() -> None:
    with pytest.raises(AdapterParseError) as exc_info:
        parse_prompt_plan_text('prefix {"name":"Broken","nodes":[')

    assert "failed to parse" in str(exc_info.value) or "could not extract" in str(
        exc_info.value
    )
    assert exc_info.value.source == "prompt"


def test_parse_prompt_plan_text_rejects_top_level_array_containing_object() -> None:
    with pytest.raises(AdapterParseError) as exc_info:
        parse_prompt_plan_text('[{"name":"ArrayWrapped","nodes":[],"edges":[]}]')

    assert "must contain an object" in str(exc_info.value)
    assert exc_info.value.source == "prompt"


def test_parse_prompt_plan_text_rejects_fenced_array_containing_object() -> None:
    with pytest.raises(AdapterParseError) as exc_info:
        parse_prompt_plan_text('```json\n[{"name":"ArrayWrapped","nodes":[],"edges":[]}]\n```')

    assert "must contain an object" in str(exc_info.value)
    assert exc_info.value.source == "prompt"
