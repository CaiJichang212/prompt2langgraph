"""Shared source adapter interfaces and parse errors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from prompt2langgraph.ir.models import WorkflowSpec


class AdapterParseError(ValueError):
    """Parse failure with source and JSON path context."""

    def __init__(
        self,
        message: str,
        *,
        source: str | None = None,
        path: str | None = None,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        super().__init__(message)
        self.source = source
        self.path = path
        self.line = line
        self.column = column


class SourceAdapter(ABC):
    """Adapter from parsed source data into canonical WorkflowSpec."""

    @abstractmethod
    def parse(self, data: Mapping[str, Any], *, source: str | None = None) -> WorkflowSpec:
        """Parse already-loaded source data into WorkflowSpec."""
