import pytest

from prompt2langgraph.adapters.base import AdapterParseError
from prompt2langgraph.adapters.json_plan import JSONPlanAdapter


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
