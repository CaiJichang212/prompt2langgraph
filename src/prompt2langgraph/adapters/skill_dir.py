"""Pre-analysis adapter for Codex-style skill directories."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from prompt2langgraph.diagnostics.codes import E_PARSE_001, E_SCHEMA_002, E_SEC_007
from prompt2langgraph.diagnostics.report import Diagnostic, DiagnosticLocation, ValidationReport


class SkillResources(BaseModel):
    scripts: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    assets: list[str] = Field(default_factory=list)


class DraftSkillNode(BaseModel):
    id: str
    summary: str


class SkillDirectoryAnalysis(BaseModel):
    name: str
    description: str
    steps: list[str] = Field(default_factory=list)
    resources: SkillResources = Field(default_factory=SkillResources)
    draft_nodes: list[DraftSkillNode] = Field(default_factory=list)
    report: ValidationReport = Field(default_factory=ValidationReport)


_NUMBERED_STEP_RE = re.compile(r"^\s*\d+\.\s+(.+?)\s*$")
_RISK_PATTERNS = (
    (
        "file writes",
        re.compile(
            r"\b(writes?|write|editing?|edit|create|save)\b.*\b(files?|paths?)\b", re.IGNORECASE
        ),
    ),
    (
        "shell execution",
        re.compile(r"\b(shell|bash|zsh|command|commands|execute|run)\b", re.IGNORECASE),
    ),
    (
        "network access",
        re.compile(r"\b(network|http|https|fetch|download|upload|api)\b", re.IGNORECASE),
    ),
    ("secrets", re.compile(r"\b(secret|secrets|token|password|api[_ -]?key)\b", re.IGNORECASE)),
)


def analyze_skill_dir(path: Path | str) -> SkillDirectoryAnalysis:
    """Read skill metadata and obvious static risk signals without executing files."""

    skill_dir = Path(path)
    skill_md = skill_dir / "SKILL.md"
    diagnostics: list[Diagnostic] = []
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError as exc:
        return SkillDirectoryAnalysis(
            name="",
            description="",
            resources=SkillResources(
                scripts=_resource_paths(skill_dir, "scripts"),
                references=_resource_paths(skill_dir, "references"),
                assets=_resource_paths(skill_dir, "assets"),
            ),
            report=ValidationReport(
                diagnostics=[
                    Diagnostic(
                        code=E_PARSE_001,
                        severity="error",
                        message=f'failed to read skill file "{skill_md}"',
                        location=DiagnosticLocation(source=str(skill_md)),
                        hint=str(exc),
                    )
                ]
            ),
        )
    frontmatter, frontmatter_lines, body = _split_frontmatter(text)
    steps = _numbered_steps(body)
    diagnostics.extend(
        _frontmatter_diagnostics(frontmatter, frontmatter_lines, source=str(skill_md))
    )
    diagnostics.extend(_risk_warnings(text, source=str(skill_md)))
    return SkillDirectoryAnalysis(
        name=frontmatter.get("name", ""),
        description=frontmatter.get("description", ""),
        steps=steps,
        resources=SkillResources(
            scripts=_resource_paths(skill_dir, "scripts"),
            references=_resource_paths(skill_dir, "references"),
            assets=_resource_paths(skill_dir, "assets"),
        ),
        draft_nodes=[
            DraftSkillNode(id=f"step_{index}", summary=step)
            for index, step in enumerate(steps, start=1)
        ],
        report=ValidationReport(diagnostics=diagnostics),
    )


def _split_frontmatter(text: str) -> tuple[dict[str, str], dict[str, int], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, {}, text

    frontmatter: dict[str, str] = {}
    frontmatter_lines: dict[str, int] = {}
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return frontmatter, frontmatter_lines, "\n".join(lines[index + 1 :])
        if ":" in line:
            key, value = line.split(":", 1)
            field_name = key.strip()
            frontmatter[field_name] = value.strip().strip("\"'")
            frontmatter_lines[field_name] = index + 1
    return frontmatter, frontmatter_lines, ""


def _numbered_steps(text: str) -> list[str]:
    steps: list[str] = []
    for line in text.splitlines():
        match = _NUMBERED_STEP_RE.match(line)
        if match is not None:
            steps.append(match.group(1))
    return steps


def _resource_paths(skill_dir: Path, dirname: str) -> list[str]:
    resource_dir = skill_dir / dirname
    if not resource_dir.exists():
        return []
    return sorted(
        path.relative_to(skill_dir).as_posix() for path in resource_dir.rglob("*") if path.is_file()
    )


def _risk_warnings(text: str, *, source: str) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for label, pattern in _RISK_PATTERNS:
        location = _first_pattern_location(text, pattern, source=source)
        if location is not None:
            diagnostics.append(
                Diagnostic(
                    code=E_SEC_007,
                    severity="warning",
                    message=f"skill language mentions {label}",
                    location=location,
                )
            )
    return diagnostics


def _frontmatter_diagnostics(
    frontmatter: dict[str, str],
    frontmatter_lines: dict[str, int],
    *,
    source: str,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for field_name in ("name", "description"):
        if not frontmatter.get(field_name):
            diagnostics.append(
                Diagnostic(
                    code=E_SCHEMA_002,
                    severity="error",
                    message=f'skill frontmatter field "{field_name}" is required',
                    location=DiagnosticLocation(
                        source=source,
                        path=field_name,
                        line=frontmatter_lines.get(field_name) or 1,
                    ),
                )
            )
    return diagnostics


def _first_pattern_location(
    text: str,
    pattern: re.Pattern[str],
    *,
    source: str,
) -> DiagnosticLocation | None:
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = pattern.search(line)
        if match is not None:
            return DiagnosticLocation(
                source=source,
                line=line_number,
                column=match.start() + 1,
            )
    return None
