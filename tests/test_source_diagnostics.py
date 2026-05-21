import pytest

from prompt2langgraph.adapters.base import AdapterParseError
from prompt2langgraph.adapters.json_plan import JSONPlanAdapter
from prompt2langgraph.prompting.parser import parse_prompt_plan_text


def test_json_plan_parse_error_preserves_source_and_path() -> None:
    plan = {
        "name": "Bad Edge",
        "nodes": [{"id": "first", "kind": "llm", "executor": "builtin.echo_llm"}],
        "edges": [{"id": "missing_target", "from": "first"}],
    }

    with pytest.raises(AdapterParseError) as exc_info:
        JSONPlanAdapter().parse(plan, source="bad_plan.json")

    assert exc_info.value.source == "bad_plan.json"
    assert exc_info.value.path == "edges[0].to"
    assert exc_info.value.line is None
    assert exc_info.value.column is None


def test_prompt_plan_parse_error_preserves_source_and_position() -> None:
    with pytest.raises(AdapterParseError) as exc_info:
        parse_prompt_plan_text('{"name":', source="prompt")

    assert exc_info.value.source == "prompt"
    # path stores the character offset from json.JSONDecodeError.pos
    assert exc_info.value.path is not None
    assert exc_info.value.path.isdigit()
    assert exc_info.value.line == 1
    assert exc_info.value.column is not None
