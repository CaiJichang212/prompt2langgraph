"""Tests for JOIN edge compilation, execution, and validation."""

import json
from pathlib import Path

import pytest

from prompt2langgraph.compiler.langgraph_py import compile_workflow_to_graph
from prompt2langgraph.ir.models import EdgeKind, EdgeSpec, WorkflowSpec
from prompt2langgraph.registry.builtins import builtin_executor_registry
from prompt2langgraph.runtime.runner import run_workflow
from prompt2langgraph.validate.join_check import check_join_edges
from prompt2langgraph.validate.validator import validate_workflow
from prompt2langgraph.visualization.mermaid import workflow_to_mermaid

FIXTURES = Path(__file__).parent / "fixtures"


def load_workflow(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def load_workflow_spec(name: str) -> WorkflowSpec:
    return WorkflowSpec.model_validate(load_workflow(name))


class TestJoinEdgeValidation:
    """Tests for JOIN edge validation logic."""

    def test_join_check_detects_unknown_node_in_join_sources(self) -> None:
        """E_JOIN_003: join_sources references unknown node."""
        workflow_data = load_workflow("fanout_with_join.json")
        # Add a JOIN edge with invalid join_sources
        workflow_data["edges"].append({
            "id": "bad_join",
            "source": "unknown_node",
            "target": "join_aggregate",
            "kind": "join",
            "join_sources": ["unknown_node", "fake_node"],
        })

        workflow = WorkflowSpec.model_validate(workflow_data)
        diagnostics = check_join_edges(workflow)

        join_diags = [d for d in diagnostics if d.code == "E_JOIN_003"]
        assert len(join_diags) == 2  # Two invalid sources
        assert any("unknown_node" in d.message for d in join_diags)
        assert any("fake_node" in d.message for d in join_diags)

    def test_join_check_warns_source_not_in_join_sources(self) -> None:
        """W_JOIN_001: source field not in join_sources (warning)."""
        workflow_data = load_workflow("fanout_with_join.json")
        # The join edge has source="process" but join_sources=["process"]
        # If we change it so source is different, we should get a warning
        workflow_data["edges"][2]["source"] = "some_other_node"

        workflow = WorkflowSpec.model_validate(workflow_data)
        diagnostics = check_join_edges(workflow)

        warn_diags = [d for d in diagnostics if d.code == "W_JOIN_001"]
        assert len(warn_diags) == 1
        assert "some_other_node" in warn_diags[0].message

    def test_join_check_detects_duplicate_join_target(self) -> None:
        """E_JOIN_005: same target referenced by multiple JOIN edges."""
        workflow_data = load_workflow("fanout_with_join.json")
        # Add another JOIN edge targeting the same node
        workflow_data["edges"].append({
            "id": "bad_join2",
            "source": "split",
            "target": "join_aggregate",
            "kind": "join",
            "join_sources": ["split"],
        })

        workflow = WorkflowSpec.model_validate(workflow_data)
        diagnostics = check_join_edges(workflow)

        join_target_diags = [d for d in diagnostics if d.code == "E_JOIN_005"]
        assert len(join_target_diags) >= 1
        assert any("join_aggregate" in d.message for d in join_target_diags)

    def test_join_check_detects_linear_edge_to_same_target(self) -> None:
        """E_JOIN_004: join_sources node already has LINEAR edge to same target."""
        workflow_data = load_workflow("fanout_with_join.json")
        # Add a linear edge from process to join_aggregate (same as join target)
        workflow_data["edges"].append({
            "id": "linear_to_join",
            "source": "process",
            "target": "join_aggregate",
            "kind": "linear",
        })

        workflow = WorkflowSpec.model_validate(workflow_data)
        diagnostics = check_join_edges(workflow)

        # The E_JOIN_004 check is only for edges in join_sources, so process is the source
        # and join_aggregate is the target. The linear edge also goes to join_aggregate.
        # This should trigger E_JOIN_004 for the join edge
        dup_edge_diags = [d for d in diagnostics if d.code == "E_JOIN_004"]
        assert len(dup_edge_diags) == 1
        assert "process" in dup_edge_diags[0].message
        assert "join_aggregate" in dup_edge_diags[0].message


class TestJoinEdgeMermaid:
    """Tests for JOIN edge Mermaid rendering."""

    def test_join_edge_renders_all_join_sources(self) -> None:
        """JOIN edge should render all sources from join_sources."""
        workflow = WorkflowSpec.model_validate(load_workflow("fanout_with_join.json"))
        mermaid = workflow_to_mermaid(workflow)

        # Should have join labels for the fanout->process and process->join_aggregate
        assert "join:join_processed" in mermaid
        # The join edge should show process -> join_aggregate with join label
        assert "process -- join:" in mermaid or "join:" in mermaid


class TestJoinEdgeSchema:
    """Tests for JOIN edge schema validation."""

    def test_join_edge_requires_join_sources(self) -> None:
        """JOIN edge without join_sources should fail validation with E_JOIN_001."""
        edge_data = {
            "id": "join_ab",
            "source": "a",
            "target": "c",
            "kind": "join",
        }
        edge = EdgeSpec.model_validate(edge_data)
        assert edge.join_sources is None
        workflow_data = {
            "schema_version": "0.1",
            "workflow_id": "test",
            "name": "Test",
            "entrypoint": "a",
            "state_schema": {
                "input": {"a": {"type": "string"}},
                "output": {"c": {"type": "string"}},
                "channels": {"a": {"type": "string"}, "c": {"type": "string"}},
                "private": {},
                "reducers": {},
            },
            "nodes": [
                {"id": "a", "kind": "transform", "executor": {"ref": "builtin.identity_transform", "type": "builtin"}, "inputs": {}, "outputs": {}, "params": {}},
                {"id": "c", "kind": "transform", "executor": {"ref": "builtin.identity_transform", "type": "builtin"}, "inputs": {}, "outputs": {}, "params": {}},
            ],
            "edges": [edge_data],
            "policies": {},
            "metadata": {},
        }
        workflow = WorkflowSpec.model_validate(workflow_data)
        diagnostics = check_join_edges(workflow)
        assert any(d.code == "E_JOIN_001" for d in diagnostics)

    def test_join_edge_rejects_single_source(self) -> None:
        """JOIN edge with only one source should fail at validation level (E_JOIN_002)."""
        edge_data = {
            "id": "join_ab",
            "source": "a",
            "target": "c",
            "kind": "join",
            "join_sources": ["a"],  # Only 1 source - should fail validation
        }
        # Schema validation passes since we only check type, not length
        edge = EdgeSpec.model_validate(edge_data)
        assert edge.join_sources == ["a"]
        # But validation should catch it
        workflow_data = {
            "schema_version": "0.1",
            "workflow_id": "test",
            "name": "Test",
            "entrypoint": "a",
            "state_schema": {
                "input": {"a": {"type": "string"}},
                "output": {"c": {"type": "string"}},
                "channels": {"a": {"type": "string"}, "c": {"type": "string"}},
                "private": {},
                "reducers": {},
            },
            "nodes": [
                {"id": "a", "kind": "transform", "executor": {"ref": "builtin.identity_transform", "type": "builtin"}, "inputs": {}, "outputs": {}, "params": {}},
                {"id": "c", "kind": "transform", "executor": {"ref": "builtin.identity_transform", "type": "builtin"}, "inputs": {}, "outputs": {}, "params": {}},
            ],
            "edges": [edge_data],
            "policies": {},
            "metadata": {},
        }
        workflow = WorkflowSpec.model_validate(workflow_data)
        diagnostics = check_join_edges(workflow)
        assert any(d.code == "E_JOIN_002" for d in diagnostics)

    def test_join_edge_accepts_multiple_sources(self) -> None:
        """JOIN edge with multiple sources should pass validation."""
        edge_data = {
            "id": "join_ab",
            "source": "a",
            "target": "c",
            "kind": "join",
            "join_sources": ["a", "b"],
        }
        edge = EdgeSpec.model_validate(edge_data)
        assert edge.join_sources == ["a", "b"]

    def test_non_join_edge_can_have_null_join_sources(self) -> None:
        """Non-JOIN edges should have join_sources=None by default."""
        edge_data = {
            "id": "linear_ab",
            "source": "a",
            "target": "b",
            "kind": "linear",
        }
        edge = EdgeSpec.model_validate(edge_data)
        assert edge.join_sources is None


class TestJoinEdgeCompilation:
    """Tests for JOIN edge compilation into LangGraph."""

    def test_compile_join_workflow_succeeds(self) -> None:
        """JOIN edge with join_sources should compile successfully."""
        workflow = load_workflow_spec("fanout_to_join.json")
        executors = builtin_executor_registry()
        graph = compile_workflow_to_graph(workflow, executors)
        assert graph is not None

    def test_compile_join_workflow_validates_first(self) -> None:
        """Valid JOIN workflow should pass validation."""
        workflow = load_workflow_spec("fanout_to_join.json")
        report = validate_workflow(workflow)
        assert report.ok

    def test_compile_join_with_duplicate_edge_warns(self, caplog) -> None:
        """JOIN with source that already has linear edge to target should warn."""
        workflow_data = load_workflow("fanout_with_join.json")
        # Add a linear edge from process to join_aggregate (same as join target)
        workflow_data["edges"].append({
            "id": "linear_to_join_dup",
            "source": "process",
            "target": "join_aggregate",
            "kind": "linear",
        })
        workflow = WorkflowSpec.model_validate(workflow_data)
        executors = builtin_executor_registry()
        # Should compile but warn about duplicate edge
        with pytest.warns(UserWarning, match="duplicate edge"):
            compile_workflow_to_graph(workflow, executors)


class TestJoinEdgeExecution:
    """Tests for JOIN edge end-to-end execution."""

    def test_run_join_workflow_succeeds(self) -> None:
        """Valid JOIN workflow should execute successfully."""
        workflow = load_workflow_spec("fanout_to_join.json")
        result = run_workflow(workflow, {"query": "test"})
        assert result.status == "succeeded"
        # The finish node waits for both branch_a and branch_b, then reads result_b
        assert "done" in result.output
        assert result.output["done"] == "test"


class TestJoinEdgeExecutionEvents:
    """Tests for JOIN edge execution event sequence."""

    def test_run_join_workflow_records_events_for_all_branches(self) -> None:
        """JOIN execution should record node.started/finished for all branches and join target."""
        workflow = load_workflow_spec("fanout_to_join.json")
        result = run_workflow(workflow, {"query": "test"})
        assert result.status == "succeeded"

        event_types = [e.type for e in result.events]
        assert "run.started" in event_types
        assert "run.finished" in event_types

        # All branches and the join target should have started/finished
        started_nodes = [e.node_id for e in result.events if e.type == "node.started"]
        finished_nodes = [e.node_id for e in result.events if e.type == "node.finished"]
        # fanout_to_join has branch_a, branch_b, finish nodes
        assert "branch_a" in started_nodes
        assert "branch_b" in started_nodes
        assert "finish" in started_nodes
        assert "finish" in finished_nodes


class TestJoinEdgeMermaidDetailed:
    """Detailed tests for JOIN edge Mermaid rendering."""

    def test_join_edge_renders_each_join_source(self) -> None:
        """Each join_source should have its own line in Mermaid output."""
        workflow = WorkflowSpec.model_validate(load_workflow("fanout_with_join.json"))
        mermaid = workflow_to_mermaid(workflow)

        # The join edge should have lines from each join_source to the target
        for edge in workflow.edges:
            if edge.kind is EdgeKind.JOIN and edge.join_sources:
                for source in edge.join_sources:
                    assert source in mermaid, f"join_source {source} missing from mermaid"
                assert f"join:{edge.id}" in mermaid

    def test_join_edge_empty_join_sources_falls_back_to_source(self) -> None:
        """JOIN edge with no join_sources should fallback to edge.source in mermaid."""
        from prompt2langgraph.ir.models import EdgeKind as EK

        # Build a minimal workflow with a JOIN edge that has no join_sources
        # (edge.source will be used as fallback in mermaid)
        data = load_workflow("fanout_with_join.json")
        # Remove join_sources from the join edge
        for edge in data["edges"]:
            if edge.get("kind") == "join":
                edge.pop("join_sources", None)
        workflow = WorkflowSpec.model_validate(data)
        mermaid = workflow_to_mermaid(workflow)
        # Just verify it doesn't crash — the actual rendering uses edge.source
        assert isinstance(mermaid, str)
        assert len(mermaid) > 0


class TestJoinReducerAggregation:
    """Tests for JOIN with reducer aggregation — multiple branches writing
    to the same state key, aggregated via reducer."""

    def test_fanout_join_reduce_aggregates_results(self) -> None:
        """Two branches write to the same 'results' key with append reducer;
        after JOIN, results should contain items from both branches."""
        workflow = load_workflow_spec("fanout_join_reduce.json")
        report = validate_workflow(workflow)
        assert report.ok, f"validation failed: {report.diagnostics}"

        result = run_workflow(
            workflow,
            {"items": ["alpha", "beta"]},
        )

        assert result.status == "succeeded"
        # Both branch_a and branch_b write to 'results' with append reducer,
        # so results should contain items from both branches
        results = result.output.get("results", [])
        assert isinstance(results, list)
        # Each branch outputs the items array; with append reducer,
        # we expect two entries (one from each branch)
        assert len(results) >= 2

    def test_fanout_join_reduce_compiles_successfully(self) -> None:
        """Compile fanout-join-reduce workflow to graph without errors."""
        from prompt2langgraph.registry.builtins import builtin_executor_registry

        workflow = load_workflow_spec("fanout_join_reduce.json")
        graph = compile_workflow_to_graph(workflow, builtin_executor_registry())
        assert graph is not None
