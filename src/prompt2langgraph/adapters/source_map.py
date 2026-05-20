"""Source location helpers shared by source adapters."""

from __future__ import annotations

from pydantic import BaseModel


class SourceLocation(BaseModel):
    source: str | None = None
    path: str | None = None
    line: int | None = None
    column: int | None = None
