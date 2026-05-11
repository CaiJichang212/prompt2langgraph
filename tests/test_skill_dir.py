from pathlib import Path

from prompt2langgraph.adapters.skill_dir import analyze_skill_dir


FIXTURES = Path(__file__).parent / "fixtures"


def test_analyze_skill_dir_reads_frontmatter_steps_resources_and_warnings() -> None:
    analysis = analyze_skill_dir(FIXTURES / "skill_basic")

    assert analysis.name == "skill-basic"
    assert analysis.description == "Analyze a simple skill safely."
    assert analysis.steps == [
        "Read the user's request.",
        "Write files with a shell command.",
        "Fetch a network resource and inspect secrets.",
    ]
    assert analysis.resources.scripts == ["scripts/danger.sh"]
    assert analysis.resources.references == ["references/guide.md"]
    assert analysis.resources.assets == ["assets/example.txt"]
    assert [node.summary for node in analysis.draft_nodes] == analysis.steps
    assert [node.id for node in analysis.draft_nodes] == ["step_1", "step_2", "step_3"]
    assert analysis.report.ok
    assert {diagnostic.severity for diagnostic in analysis.report.diagnostics} == {"warning"}
    assert {diagnostic.code for diagnostic in analysis.report.diagnostics} == {"E_SEC_007"}
    assert {diagnostic.message for diagnostic in analysis.report.diagnostics} == {
        "skill language mentions file writes",
        "skill language mentions shell execution",
        "skill language mentions network access",
        "skill language mentions secrets",
    }


def test_analyze_skill_dir_reports_missing_skill_file(tmp_path: Path) -> None:
    analysis = analyze_skill_dir(tmp_path)

    assert analysis.name == ""
    assert analysis.description == ""
    assert analysis.steps == []
    assert analysis.report.ok is False
    assert [diagnostic.code for diagnostic in analysis.report.diagnostics] == ["E_PARSE_001"]


def test_analyze_skill_dir_reports_missing_required_frontmatter_fields(tmp_path: Path) -> None:
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text("---\nname: incomplete\n---\n\n1. Do one thing.\n", encoding="utf-8")

    analysis = analyze_skill_dir(tmp_path)

    assert analysis.name == "incomplete"
    assert analysis.description == ""
    assert analysis.steps == ["Do one thing."]
    assert analysis.report.ok is False
    assert any(
        diagnostic.code == "E_SCHEMA_002" and "description" in diagnostic.message
        for diagnostic in analysis.report.diagnostics
    )
