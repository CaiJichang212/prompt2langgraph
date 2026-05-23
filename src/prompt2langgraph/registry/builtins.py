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
    from langgraph.types import interrupt

    approval = interrupt({"message": params.get("message", "Approve this run?")})
    return {"approval": approval}


def join(inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return dict(inputs)


def builtin_node_registry() -> NodeRegistry:
    return NodeRegistry(
        [
            NodeDefinition(
                kind="llm",
                description="Deterministic mock LLM node for v0.1 local execution.",
                input_schema={"question": STRING},
                output_schema={"answer": STRING},
                param_schema={"template": STRING},
                default_timeout_s=120,
            ),
            NodeDefinition(
                kind="tool",
                description="Registered tool execution node.",
                required_capabilities=("tool",),
                default_timeout_s=60,
            ),
            NodeDefinition(
                kind="retriever",
                description="Mock retriever node that returns an artifact reference.",
                input_schema={"question": STRING},
                output_schema={"docs_ref": ARTIFACT_REF},
                default_timeout_s=60,
            ),
            NodeDefinition(
                kind="transform",
                description="Pure state transformation node.",
                required_capabilities=("transform",),
                default_timeout_s=60,
            ),
            NodeDefinition(
                kind="router",
                description="State-based routing node.",
                required_capabilities=("route",),
                default_timeout_s=60,
            ),
            NodeDefinition(
                kind="human_gate",
                description="Human approval gate that interrupts execution.",
                param_schema={"message": STRING},
                required_capabilities=("interrupt",),
                default_timeout_s=60,
            ),
            NodeDefinition(
                kind="join",
                description="Branch join node for reduced state.",
                required_capabilities=("join",),
                default_timeout_s=60,
            ),
            NodeDefinition(
                kind="side_effect",
                description="External side-effect node requiring approval or idempotency.",
                side_effect=True,
                required_capabilities=("side_effect",),
                default_timeout_s=60,
            ),
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
            ExecutorDefinition(
                ref="llm.qwen-plus",
                type=ExecutorType.LLM,
                dynamic=True,
                input_schema={"question": STRING},
                output_schema={"answer": STRING},
                handler=None,
            ),
        ]
    )
