import json
from pathlib import Path

import pytest

from prompt2langgraph.compiler.langgraph_py import compile_workflow_to_graph
from prompt2langgraph.ir.models import WorkflowSpec
from prompt2langgraph.registry.builtins import builtin_executor_registry


FIXTURES = Path(__file__).parent / "fixtures"


def load_workflow(name: str) -> WorkflowSpec:
    return WorkflowSpec.model_validate(json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def test_compiles_linear_llm_fixture_to_invokable_graph() -> None:
    workflow = load_workflow("linear_llm.json")

    graph = compile_workflow_to_graph(workflow, builtin_executor_registry())
    result = graph.invoke({"question": "hello"})

    assert result["question"] == "hello"
    assert result["answer"] == "Answer: hello"


def test_compiles_conditional_edge_to_route_by_expression() -> None:
    workflow = load_workflow("conditional_human_gate.json")

    graph = compile_workflow_to_graph(workflow, builtin_executor_registry())
    result = graph.invoke({"question": "hello", "confidence": 0.8})

    assert result["answer"] == "Answer: hello"
    assert "approval" not in result


@pytest.mark.parametrize(
    ("expr", "confidence"),
    [
        ("confidence < 0.75", 0.5),
        ("confidence <= 0.75", 0.75),
        ("confidence > 0.75", 0.8),
        ("confidence >= 0.75", 0.75),
        ("confidence == 0.75", 0.75),
        ("confidence != 0.75", 0.8),
    ],
)
def test_conditional_expression_supports_scalar_comparisons(expr: str, confidence: float) -> None:
    workflow = load_workflow("conditional_human_gate.json")
    condition = workflow.edges[0].condition
    assert condition is not None
    condition.expr = expr
    condition.routes = {"true": "compose", "false": "approval"}

    graph = compile_workflow_to_graph(workflow, builtin_executor_registry())
    result = graph.invoke({"question": "hello", "confidence": confidence})

    assert result["answer"] == "Answer: hello"
