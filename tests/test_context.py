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


# --- Reserved scope prefixes: input / steps / trigger ---


def test_get_steps_exposes_node_output_directly():
    ctx = WorkflowContext()
    ctx.set("triage", {"severity": "critical", "title": "Login broken"})

    # steps.<id> is the node's output — no ".output" hop
    assert ctx.get("steps.triage.severity") == "critical"
    assert ctx.get("steps.triage") == {"severity": "critical", "title": "Login broken"}


def test_get_steps_start_is_unwrapped_trigger():
    ctx = WorkflowContext()
    ctx.set("start", {"input": {"skip": True, "id": 7}})

    assert ctx.get("steps.start") == {"skip": True, "id": 7}
    assert ctx.get("steps.start.skip") is True
    assert ctx.get("steps.start.id") == 7


def test_get_trigger_aliases_steps_start():
    ctx = WorkflowContext()
    ctx.set("start", {"input": {"skip": True}})

    assert ctx.get("trigger") == {"skip": True}
    assert ctx.get("trigger.skip") is True


def test_get_input_reads_current_input_scope():
    ctx = WorkflowContext()
    ctx.set_current_input({"amount": 500, "purpose": "Travel"})

    assert ctx.get("input.amount") == 500
    assert ctx.get("input.purpose") == "Travel"


def test_reserved_prefixes_missing_return_default():
    ctx = WorkflowContext()

    assert ctx.get("input.ghost") is None
    assert ctx.get("input.ghost", "fallback") == "fallback"
    assert ctx.get("steps.ghost.field") is None
    assert ctx.get("trigger.ghost", "fallback") == "fallback"


def test_legacy_output_paths_still_resolve():
    # Non-regression: node.output.field keeps working alongside the new scopes
    ctx = WorkflowContext()
    ctx.set("triage", {"severity": "high"})
    ctx.set("start", {"input": {"skip": False}})

    assert ctx.get("triage.output.severity") == "high"
    assert ctx.get("start.output.input.skip") is False


def test_current_input_is_not_serialized():
    ctx = WorkflowContext()
    ctx.set("triage", {"severity": "high"})
    ctx.set_current_input({"transient": True})

    restored = WorkflowContext.from_dict(ctx.to_dict())
    assert "input" not in restored.to_dict()
    assert restored.get("input.transient") is None
    assert restored.get("steps.triage.severity") == "high"
