"""Tests for WorkflowEngine — edge evaluation and execution flow."""

from __future__ import annotations

import pytest

from roomkit_graph import (
    Condition,
    Edge,
    Graph,
    ManualTrigger,
    Node,
    WorkflowContext,
    WorkflowEngine,
)


def _linear_graph() -> Graph:
    """start → agent → end"""
    g = Graph(id="linear", name="Linear", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("work", type="function", config={"action": "set_context", "values": {"done": True}}),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "work"), Edge("work", "end"))
    return g


def _branching_graph() -> Graph:
    """start → check → (critical: escalate, otherwise: assign) → end"""
    g = Graph(id="branch", name="Branch", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("check", type="function", config={"action": "set_context", "values": {}}),
        Node("escalate", type="notification", config={"channel": "slack"}),
        Node("assign", type="notification", config={"channel": "email"}),
        Node("end", type="end"),
    )
    g.add_edges(
        Edge("start", "check"),
        Edge("check", "escalate", Condition.field("check.output.severity").equals("critical")),
        Edge("check", "assign", Condition.otherwise()),
        Edge("escalate", "end"),
        Edge("assign", "end"),
    )
    return g


# --- Edge evaluation ---


def test_evaluate_edges_unconditional():
    g = _linear_graph()
    executor = WorkflowEngine(g)
    executor.context.set("start", {})

    next_id = executor.evaluate_edges("start")
    assert next_id == "work"


def test_evaluate_edges_conditional_match():
    g = _branching_graph()
    executor = WorkflowEngine(g)
    executor.context.set("check", {"severity": "critical"})

    next_id = executor.evaluate_edges("check")
    assert next_id == "escalate"


def test_evaluate_edges_otherwise_fallback():
    g = _branching_graph()
    executor = WorkflowEngine(g)
    executor.context.set("check", {"severity": "low"})

    next_id = executor.evaluate_edges("check")
    assert next_id == "assign"


def test_evaluate_edges_end_node_returns_none():
    g = _linear_graph()
    executor = WorkflowEngine(g)

    next_id = executor.evaluate_edges("end")
    assert next_id is None


def test_evaluate_edges_no_match_raises():
    g = Graph(id="test", name="Test", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("a", type="agent"),
        Node("end", type="end"),
    )
    # Only a conditional edge, no otherwise
    g.add_edges(
        Edge("start", "a"),
        Edge("a", "end", Condition.field("a.output.x").equals("never")),
    )

    executor = WorkflowEngine(g)
    executor.context.set("a", {"x": "something_else"})

    from roomkit_graph import NoValidTransitionError

    with pytest.raises(NoValidTransitionError):
        executor.evaluate_edges("a")


# --- Execution lifecycle ---


async def test_start_sets_initial_state():
    g = _linear_graph()
    executor = WorkflowEngine(g)

    await executor.start(trigger_data={"message": "hello"})

    assert executor.current_node_id == "start"
    assert executor.context.get("start.output.input") == {"message": "hello"}


async def test_run_linear_workflow():
    """Full run of a simple linear graph should complete."""
    g = _linear_graph()
    executor = WorkflowEngine(g)

    result = await executor.run(trigger_data={"message": "go"})

    assert isinstance(result, WorkflowContext)
    # Should have passed through all nodes
    assert result.has("start.output")
    assert result.has("work.output")


async def test_step_advances():
    g = _linear_graph()
    executor = WorkflowEngine(g)
    await executor.start()

    advanced = await executor.step()
    assert advanced is True


async def test_step_returns_false_at_end():
    g = Graph(id="minimal", name="Minimal", trigger=ManualTrigger())
    g.add_nodes(Node("start", type="start"), Node("end", type="end"))
    g.add_edges(Edge("start", "end"))

    executor = WorkflowEngine(g)
    await executor.start()

    # step from start → end
    await executor.step()
    # step at end → should return False (complete)
    advanced = await executor.step()
    assert advanced is False


async def test_resume_after_human_node():
    g = Graph(id="human", name="Human", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node(
            "review",
            type="human",
            config={
                "prompt": "Approve?",
                "actions": ["approve", "reject"],
            },
        ),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "review"), Edge("review", "end"))

    executor = WorkflowEngine(g)
    await executor.start()
    await executor.step()  # start → review (should pause)

    assert executor.current_node_id == "review"

    # Simulate human providing input
    await executor.resume("review", {"action": "approve", "feedback": "Looks good"})

    assert executor.context.get("review.output.action") == "approve"


async def test_step_before_start_returns_false():
    g = _linear_graph()
    executor = WorkflowEngine(g)

    # Stepping before start() should return False (not started)
    advanced = await executor.step()
    assert advanced is False


async def test_executor_with_injected_context():
    g = _linear_graph()
    ctx = WorkflowContext()
    ctx.set("start", {"input": "restored"})

    executor = WorkflowEngine(g, context=ctx)
    assert executor.context.get("start.output.input") == "restored"
