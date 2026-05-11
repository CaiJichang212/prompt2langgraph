"""Node registry definitions."""

from dataclasses import dataclass, field

from prompt2langgraph.ir.models import TypeSpec


@dataclass(frozen=True)
class NodeDefinition:
    kind: str
    input_schema: dict[str, TypeSpec] = field(default_factory=dict)
    output_schema: dict[str, TypeSpec] = field(default_factory=dict)
    planner_enabled: bool = True
    deprecated: bool = False
    side_effect: bool = False
    capabilities: tuple[str, ...] = ()
    retry: int | None = None
    timeout_s: int | None = None


class NodeRegistry:
    def __init__(self, definitions: list[NodeDefinition] | None = None) -> None:
        self._definitions: dict[str, NodeDefinition] = {}
        for definition in definitions or []:
            self.register(definition)

    def register(self, definition: NodeDefinition) -> None:
        self._definitions[definition.kind] = definition

    def get(self, kind: str) -> NodeDefinition:
        return self._definitions[kind]

    def has(self, kind: str) -> bool:
        return kind in self._definitions

    def kinds(self) -> list[str]:
        return sorted(self._definitions)

