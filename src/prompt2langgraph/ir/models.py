"""Pydantic models for the canonical Workflow IR."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

ID_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_identifier(value: str) -> str:
    if not ID_PATTERN.match(value):
        raise ValueError("must match ^[A-Za-z_][A-Za-z0-9_]*$")
    return value


class TypeName(StrEnum):
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    OBJECT = "object"
    ARRAY = "array"
    MESSAGES = "messages"
    ARTIFACT_REF = "artifact_ref"
    ANY = "any"


class EdgeKind(StrEnum):
    LINEAR = "linear"
    CONDITIONAL = "conditional"
    LOOP = "loop"
    FANOUT = "fanout"
    JOIN = "join"


class ExecutorType(StrEnum):
    BUILTIN = "builtin"
    PYTHON_CALLABLE = "python_callable"
    LANGCHAIN_TOOL = "langchain_tool"
    LLM = "llm"
    HUMAN = "human"


class ReducerName(StrEnum):
    APPEND = "append"
    ADD_MESSAGES = "add_messages"
    SUM = "sum"
    MERGE_DICT = "merge_dict"


class TypeSpec(BaseModel):
    type: TypeName
    item_type: TypeSpec | None = None
    properties: dict[str, TypeSpec] = Field(default_factory=dict)


class StateSelector(BaseModel):
    state_key: str

    @field_validator("state_key")
    @classmethod
    def state_key_matches_identifier(cls, value: str) -> str:
        return _validate_identifier(value)


class ExecutorRef(BaseModel):
    ref: str
    type: ExecutorType


class ConditionSpec(BaseModel):
    expr: str
    routes: dict[str, str]


class LoopGuard(BaseModel):
    max_iterations: int = Field(ge=1)
    counter_key: str = "_loop_counts"

    @field_validator("counter_key")
    @classmethod
    def counter_key_matches_identifier(cls, value: str) -> str:
        return _validate_identifier(value)


class MapSpec(BaseModel):
    items_state_key: str
    item_state_key: str
    result_state_key: str

    @field_validator("items_state_key", "item_state_key", "result_state_key")
    @classmethod
    def state_keys_match_identifier(cls, value: str) -> str:
        return _validate_identifier(value)


class RetryPolicy(BaseModel):
    max_attempts: int = 1


class SecurityPolicy(BaseModel):
    requires_approval: bool = False
    idempotency_key: str | None = None
    allowed_tool_refs: list[str] | None = None


class PolicySpec(BaseModel):
    allow_side_effects: bool = False
    default_timeout_s: int = 60
    external_call: bool = False
    allowed_models: list[str] = Field(default_factory=list)
    collect_metrics: bool = False
    allowed_tool_refs: list[str] = Field(default_factory=list)


class StateSchema(BaseModel):
    input: dict[str, TypeSpec] = Field(default_factory=dict)
    output: dict[str, TypeSpec] = Field(default_factory=dict)
    channels: dict[str, TypeSpec] = Field(default_factory=dict)
    private: dict[str, TypeSpec] = Field(default_factory=dict)
    reducers: dict[str, ReducerName] = Field(default_factory=dict)

    @field_validator("input", "output", "channels", "private", "reducers")
    @classmethod
    def state_keys_match_identifier(cls, value: dict[str, Any]) -> dict[str, Any]:
        for key in value:
            _validate_identifier(key)
        return value

    @model_validator(mode="after")
    def channels_include_input_and_output(self) -> StateSchema:
        missing = (set(self.input) | set(self.output)) - set(self.channels)
        if missing:
            joined = ", ".join(sorted(missing))
            raise ValueError(f"channels must include input and output keys: {joined}")
        return self


class NodeSpec(BaseModel):
    id: str
    kind: str
    executor: ExecutorRef
    inputs: dict[str, StateSelector] = Field(default_factory=dict)
    outputs: dict[str, StateSelector] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    retry: RetryPolicy | None = None
    timeout_s: int | None = None
    security: SecurityPolicy | None = None

    @field_validator("id")
    @classmethod
    def id_matches_identifier(cls, value: str) -> str:
        return _validate_identifier(value)


class EdgeSpec(BaseModel):
    id: str
    source: str
    target: str
    kind: EdgeKind
    condition: ConditionSpec | None = None
    map: MapSpec | None = None
    loop_guard: LoopGuard | None = None

    @field_validator("id", "source", "target")
    @classmethod
    def ids_match_identifier(cls, value: str) -> str:
        return _validate_identifier(value)


class WorkflowSpec(BaseModel):
    schema_version: str
    workflow_id: str
    name: str
    entrypoint: str
    state_schema: StateSchema
    nodes: list[NodeSpec]
    edges: list[EdgeSpec]
    policies: PolicySpec = Field(default_factory=PolicySpec)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("workflow_id", "entrypoint")
    @classmethod
    def ids_match_identifier(cls, value: str) -> str:
        return _validate_identifier(value)

    @field_validator("workflow_id", "name")
    @classmethod
    def workflow_fields_are_non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("must be non-empty")
        return value
