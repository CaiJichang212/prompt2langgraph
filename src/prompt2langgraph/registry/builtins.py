"""Builtin node and executor definitions for local deterministic tests."""

from typing import Any

from prompt2langgraph.ir.models import ExecutorType, TypeName, TypeSpec
from prompt2langgraph.registry.executors import ExecutorDefinition, ExecutorRegistry
from prompt2langgraph.registry.nodes import NodeDefinition, NodeRegistry


STRING = TypeSpec(type=TypeName.STRING)
ARTIFACT_REF = TypeSpec(type=TypeName.ARTIFACT_REF)
ANY = TypeSpec(type=TypeName.ANY)


def echo_llm(inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    template = params.get("template", "{question}")
    answer = str(template).format(**inputs)
    return {"answer": answer}


def mock_retriever(inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    question = inputs.get("question", "")
    return {"docs_ref": f"mock://retriever/{question}"}


def identity_transform(inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return dict(inputs)


def route(inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return dict(inputs)


def human_gate(inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return {"approval": params.get("message", "Approve this run?")}


def join(inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return dict(inputs)


def builtin_node_registry() -> NodeRegistry:
    return NodeRegistry(
        [
            NodeDefinition(kind="llm", input_schema={"question": STRING}, output_schema={"answer": STRING}),
            NodeDefinition(kind="tool", capabilities=("tool",)),
            NodeDefinition(
                kind="retriever",
                input_schema={"question": STRING},
                output_schema={"docs_ref": ARTIFACT_REF},
            ),
            NodeDefinition(kind="transform", capabilities=("transform",)),
            NodeDefinition(kind="router", capabilities=("route",)),
            NodeDefinition(kind="human_gate", capabilities=("interrupt",)),
            NodeDefinition(kind="join", capabilities=("join",)),
            NodeDefinition(kind="side_effect", side_effect=True, capabilities=("side_effect",)),
        ]
    )


def builtin_executor_registry() -> ExecutorRegistry:
    return ExecutorRegistry(
        [
            ExecutorDefinition(
                ref="builtin.echo_llm",
                type=ExecutorType.BUILTIN,
                input_schema={"question": STRING},
                output_schema={"answer": STRING},
                handler=echo_llm,
            ),
            ExecutorDefinition(
                ref="builtin.mock_retriever",
                type=ExecutorType.BUILTIN,
                input_schema={"question": STRING},
                output_schema={"docs_ref": ARTIFACT_REF},
                handler=mock_retriever,
            ),
            ExecutorDefinition(
                ref="builtin.identity_transform",
                type=ExecutorType.BUILTIN,
                input_schema={"value": ANY},
                output_schema={"value": ANY},
                handler=identity_transform,
            ),
            ExecutorDefinition(
                ref="builtin.route",
                type=ExecutorType.BUILTIN,
                input_schema={},
                output_schema={},
                handler=route,
            ),
            ExecutorDefinition(
                ref="builtin.human_gate",
                type=ExecutorType.BUILTIN,
                input_schema={},
                output_schema={"approval": STRING},
                handler=human_gate,
            ),
            ExecutorDefinition(
                ref="builtin.join",
                type=ExecutorType.BUILTIN,
                input_schema={"docs_ref": ARTIFACT_REF},
                output_schema={},
                handler=join,
            ),
        ]
    )
