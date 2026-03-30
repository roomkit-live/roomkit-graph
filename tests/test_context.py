"""Tests for WorkflowContext — cross-step state management."""

from __future__ import annotations

from roomkit_graph import WorkflowContext


def test_set_and_get():
    ctx = WorkflowContext()
    ctx.set("triage", {"severity": "critical", "title": "Login broken"})

    assert ctx.get("triage.output.severity") == "critical"
    assert ctx.get("triage.output.title") == "Login broken"


def test_get_full_output():
    ctx = WorkflowContext()
    ctx.set("extract", {"amount": 500, "purpose": "Travel"})

    output = ctx.get("extract.output")
    assert output == {"amount": 500, "purpose": "Travel"}


def test_get_nested_path():
    ctx = WorkflowContext()
    ctx.set("enrich", {"employee": {"name": "Alice", "department": "Engineering"}})

    assert ctx.get("enrich.output.employee.name") == "Alice"


def test_get_missing_returns_default():
    ctx = WorkflowContext()

    assert ctx.get("nonexistent.output.field") is None
    assert ctx.get("nonexistent.output.field", "fallback") == "fallback"


def test_has_existing():
    ctx = WorkflowContext()
    ctx.set("start", {"input": "hello"})

    assert ctx.has("start.output") is True
    assert ctx.has("start.output.input") is True


def test_has_missing():
    ctx = WorkflowContext()

    assert ctx.has("ghost.output") is False


def test_to_dict():
    ctx = WorkflowContext()
    ctx.set("start", {"input": "data"})
    ctx.set("triage", {"severity": "high"})

    data = ctx.to_dict()
    assert "start" in data
    assert "triage" in data
    assert data["start"]["output"]["input"] == "data"


def test_from_dict():
    data = {
        "start": {"output": {"input": "data"}},
        "triage": {"output": {"severity": "high"}},
    }

    ctx = WorkflowContext.from_dict(data)
    assert ctx.get("start.output.input") == "data"
    assert ctx.get("triage.output.severity") == "high"


def test_round_trip():
    ctx = WorkflowContext()
    ctx.set("start", {"payload": {"title": "Bug"}})
    ctx.set("agent", {"result": "Fixed"})

    data = ctx.to_dict()
    restored = WorkflowContext.from_dict(data)

    assert restored.get("start.output.payload.title") == "Bug"
    assert restored.get("agent.output.result") == "Fixed"


def test_overwrite_node_output():
    ctx = WorkflowContext()
    ctx.set("step", {"v": 1})
    ctx.set("step", {"v": 2})

    assert ctx.get("step.output.v") == 2
