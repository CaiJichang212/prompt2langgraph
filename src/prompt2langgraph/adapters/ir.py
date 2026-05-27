"""Adapter for canonical Workflow IR input."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from prompt2langgraph.adapters.base import SourceAdapter
from prompt2langgraph.ir.models import WorkflowSpec


class IRAdapter(SourceAdapter):
    """Parse canonical Workflow IR mappings."""

    def parse(self, data: Mapping[str, Any], *, source: str | None = None) -> WorkflowSpec:
        return WorkflowSpec.model_validate(data)

    def emit(self, workflow: WorkflowSpec) -> dict[str, Any]:
        """Serialize a WorkflowSpec to a plain dict."""
        return workflow.model_dump(mode="json")
