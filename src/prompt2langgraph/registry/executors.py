"""Executor registry definitions."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from prompt2langgraph.ir.models import ExecutorType, TypeSpec

ExecutorHandler = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ExecutorDefinition:
    ref: str
    type: ExecutorType
    input_schema: dict[str, TypeSpec] = field(default_factory=dict)
    output_schema: dict[str, TypeSpec] = field(default_factory=dict)
    secrets: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    handler: ExecutorHandler | None = None

    def invoke(self, inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        if self.handler is None:
            return {}
        return self.handler(inputs, params)


class ExecutorRegistry:
    def __init__(self, definitions: list[ExecutorDefinition] | None = None) -> None:
        self._definitions: dict[str, ExecutorDefinition] = {}
        for definition in definitions or []:
            self.register(definition)

    def register(self, definition: ExecutorDefinition) -> None:
        self._definitions[definition.ref] = definition

    def get(self, ref: str) -> ExecutorDefinition:
        return self._definitions[ref]

    def has(self, ref: str) -> bool:
        return ref in self._definitions

    def refs(self) -> list[str]:
        return sorted(self._definitions)

