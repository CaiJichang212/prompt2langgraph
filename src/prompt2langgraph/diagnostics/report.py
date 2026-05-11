"""Structured diagnostics produced by validation and runtime stages."""

from typing import Literal

from pydantic import BaseModel, Field


class DiagnosticLocation(BaseModel):
    source: str | None = None
    node_id: str | None = None
    edge_id: str | None = None
    state_key: str | None = None
    path: str | None = None


class Diagnostic(BaseModel):
    code: str
    severity: Literal["error", "warning", "info"]
    message: str
    location: DiagnosticLocation | None = None
    hint: str | None = None


class ValidationReport(BaseModel):
    diagnostics: list[Diagnostic] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(item.severity == "error" for item in self.diagnostics)
