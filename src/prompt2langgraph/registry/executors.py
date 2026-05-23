"""Executor registry definitions."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from prompt2langgraph.ir.models import ExecutorType, TypeSpec

ExecutorHandler = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


class ExecutorError(RuntimeError):
    """Unified error wrapper for dynamic executors (LLM, Tool)."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        hint: str | None = None,
        node_id: str | None = None,
        executor_ref: str | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.hint = hint
        self.node_id = node_id
        self.executor_ref = executor_ref
        super().__init__(message)

    def to_diagnostic(self) -> Diagnostic:
        from prompt2langgraph.diagnostics.report import Diagnostic, DiagnosticLocation

        return Diagnostic(
            code=self.code,
            severity="error",
            message=self.message,
            location=DiagnosticLocation(node_id=self.node_id) if self.node_id else None,
            hint=self.hint,
        )


@dataclass(frozen=True)
class ExecutorDefinition:
    ref: str
    type: ExecutorType
    input_schema: dict[str, TypeSpec] = field(default_factory=dict)
    output_schema: dict[str, TypeSpec] = field(default_factory=dict)
    secrets: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    handler: ExecutorHandler | None = None
    dynamic: bool = False

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
