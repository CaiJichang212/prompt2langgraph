import json
from pathlib import Path

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
