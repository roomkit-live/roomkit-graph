"""Tests for WorkflowEngine — edge evaluation and execution flow."""

from __future__ import annotations

import pytest

from roomkit_graph import (
    Condition,
    Edge,
    ExecutionError,
    FunctionRegistry,
    Graph,
    ManualTrigger,
    Node,
    NodeHandler,
    NodeResult,
    WorkflowContext,
    WorkflowEngine,
)
from roomkit_graph.handlers import FunctionHandler


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
    """Full pause/resume cycle with a handler that returns status=waiting."""

    class HumanHandler(NodeHandler):
        async def execute(self, node, context, engine):
            # Check if input already arrived (resume case)
            existing = context.get(f"{node.id}.output")
            if existing is not None:
                return NodeResult(output=existing, status="completed")
            return NodeResult(output=None, status="waiting")

    g = Graph(id="human", name="Human", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("review", type="human", config={"prompt": "Approve?"}),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "review"), Edge("review", "end"))

    executor = WorkflowEngine(g, handlers={"human": HumanHandler()})
    await executor.start()

    # step from start → review
    advanced = await executor.step()
    assert advanced is True
    assert executor.current_node_id == "review"

    # step executes review handler → sets waiting, returns True
    advanced = await executor.step()
    assert advanced is True
    assert executor.current_node_id == "review"

    # step while waiting — returns False without re-executing
    advanced = await executor.step()
    assert advanced is False
    assert executor.current_node_id == "review"

    # Provide human input — resume advances past the waiting node
    await executor.resume("review", {"action": "approve", "feedback": "LGTM"})
    assert executor.context.get("review.output.action") == "approve"
    assert executor.current_node_id == "end"

    # step at end → completes
    advanced = await executor.step()
    assert advanced is False
    assert executor.current_node_id is None


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


# --- Custom handler injection ---


async def test_custom_handler_injection():
    """Consumer-provided handlers execute and store output in context."""

    class AgentHandler(NodeHandler):
        async def execute(self, node, context, engine):
            return NodeResult(output={"response": "handled"}, status="completed")

    g = Graph(id="custom", name="Custom", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("agent", type="agent", config={"agent_id": "test"}),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "agent"), Edge("agent", "end"))

    executor = WorkflowEngine(g, handlers={"agent": AgentHandler()})
    ctx = await executor.run()

    assert ctx.get("agent.output.response") == "handled"


async def test_custom_handler_overrides_builtin():
    """Consumer handlers override built-in handlers."""

    class CustomStartHandler(NodeHandler):
        async def execute(self, node, context, engine):
            return NodeResult(output={"custom": True}, status="completed")

    g = Graph(id="override", name="Override", trigger=ManualTrigger())
    g.add_nodes(Node("start", type="start"), Node("end", type="end"))
    g.add_edges(Edge("start", "end"))

    executor = WorkflowEngine(g, handlers={"start": CustomStartHandler()})
    ctx = await executor.run()

    assert ctx.get("start.output.custom") is True


# --- Missing handler ---


async def test_missing_handler_raises():
    """Nodes with no registered handler raise ExecutionError."""
    g = Graph(id="test", name="Test", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("notify", type="notification"),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "notify"), Edge("notify", "end"))

    executor = WorkflowEngine(g)
    await executor.start()
    await executor.step()  # start → notify

    with pytest.raises(ExecutionError, match="No handler registered"):
        await executor.step()  # notify → raises


# --- Handler failure ---


async def test_handler_failure_raises_execution_error():
    """Handler returning status=failed raises ExecutionError."""
    g = Graph(id="fail", name="Fail", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("bad", type="function", config={"action": "nonexistent"}),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "bad"), Edge("bad", "end"))

    executor = WorkflowEngine(g)
    await executor.start()
    await executor.step()  # start → bad

    with pytest.raises(ExecutionError, match="Unknown function action"):
        await executor.step()  # bad → raises


# --- Edge evaluation: mixed conditional + unconditional ---


def test_evaluate_edges_conditional_takes_priority_over_unconditional():
    """Conditional edges are evaluated before unconditional fallback."""
    g = Graph(id="mixed", name="Mixed", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("a", type="function", config={"action": "set_context", "values": {}}),
        Node("cond_target", type="end"),
        Node("uncond_target", type="end"),
    )
    # Add unconditional FIRST — should not shadow the conditional
    g.add_edges(
        Edge("start", "a"),
        Edge("a", "uncond_target"),
        Edge("a", "cond_target", Condition.field("a.output.route").equals("go")),
    )

    executor = WorkflowEngine(g)
    executor.context.set("a", {"route": "go"})

    next_id = executor.evaluate_edges("a")
    assert next_id == "cond_target"


def test_evaluate_edges_unconditional_when_no_condition_matches():
    """Unconditional edge is used when no conditional edge matches."""
    g = Graph(id="mixed2", name="Mixed2", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("a", type="function", config={"action": "set_context", "values": {}}),
        Node("cond_target", type="end"),
        Node("uncond_target", type="end"),
    )
    g.add_edges(
        Edge("start", "a"),
        Edge("a", "cond_target", Condition.field("a.output.route").equals("never")),
        Edge("a", "uncond_target"),
    )

    executor = WorkflowEngine(g)
    executor.context.set("a", {"route": "something_else"})

    next_id = executor.evaluate_edges("a")
    assert next_id == "uncond_target"


def test_evaluate_edges_first_match_wins():
    """When multiple conditional edges match, the first one (definition order) wins."""
    g = Graph(id="first_match", name="FirstMatch", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("a", type="function", config={"action": "set_context", "values": {}}),
        Node("first_target", type="end"),
        Node("second_target", type="end"),
    )
    # Both conditions match the same value — first-added edge should win
    g.add_edges(
        Edge("start", "a"),
        Edge("a", "first_target", Condition.field("a.output.x").equals("yes")),
        Edge("a", "second_target", Condition.field("a.output.x").equals("yes")),
    )

    executor = WorkflowEngine(g)
    executor.context.set("a", {"x": "yes"})

    assert executor.evaluate_edges("a") == "first_target"


# --- Engine state serialization ---


async def test_engine_to_dict_and_from_dict():
    """Engine state round-trips through serialization."""

    class HumanHandler(NodeHandler):
        async def execute(self, node, context, engine):
            return NodeResult(output=None, status="waiting")

    g = Graph(id="persist", name="Persist", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("review", type="human"),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "review"), Edge("review", "end"))

    handlers = {"human": HumanHandler()}
    executor = WorkflowEngine(g, handlers=handlers)
    await executor.start(trigger_data={"msg": "hello"})
    await executor.step()  # start → review
    await executor.step()  # review → handler sets waiting

    # Serialize
    state = executor.to_dict()
    assert state["current_node_id"] == "review"
    assert state["waiting"] is True
    assert "context" in state

    # Restore
    restored = WorkflowEngine.from_dict(g, state, handlers=handlers)
    assert restored.current_node_id == "review"
    assert restored._waiting is True
    assert restored.context.get("start.output.input") == {"msg": "hello"}


# --- FunctionHandler: json_transform ---


async def test_function_handler_json_transform():
    """json_transform action resolves templates in a dict structure."""
    g = Graph(id="transform", name="Transform", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node(
            "prep",
            type="function",
            config={"action": "set_context", "values": {"name": "Alice"}},
        ),
        Node(
            "transform",
            type="function",
            config={
                "action": "json_transform",
                "template": {"greeting": "Hello, {{prep.output.name}}!"},
            },
        ),
        Node("end", type="end"),
    )
    g.add_edges(
        Edge("start", "prep"),
        Edge("prep", "transform"),
        Edge("transform", "end"),
    )

    executor = WorkflowEngine(g)
    ctx = await executor.run()

    assert ctx.get("transform.output.greeting") == "Hello, Alice!"


# --- FunctionHandler: custom action with registry ---


async def test_function_handler_custom_action():
    """Custom function action executes a registered function."""
    registry = FunctionRegistry()

    @registry.function("double")
    async def double(context, config):
        val = config.get("input_value", 0)
        return {"result": val * 2}

    g = Graph(id="custom_fn", name="CustomFn", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node(
            "compute",
            type="function",
            config={"action": "custom", "function": "double", "input_value": 21},
        ),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "compute"), Edge("compute", "end"))

    executor = WorkflowEngine(g, handlers={"function": FunctionHandler(registry=registry)})
    ctx = await executor.run()

    assert ctx.get("compute.output.result") == 42


async def test_function_handler_custom_sync():
    """Custom function action works with sync functions too."""
    registry = FunctionRegistry()

    @registry.function("add_one")
    def add_one(context, config):
        return {"value": config.get("x", 0) + 1}

    g = Graph(id="sync_fn", name="SyncFn", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("calc", type="function", config={"action": "custom", "function": "add_one", "x": 9}),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "calc"), Edge("calc", "end"))

    executor = WorkflowEngine(g, handlers={"function": FunctionHandler(registry=registry)})
    ctx = await executor.run()

    assert ctx.get("calc.output.value") == 10


async def test_function_handler_custom_no_registry():
    """Custom action without registry returns failed result."""
    g = Graph(id="no_reg", name="NoReg", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("fn", type="function", config={"action": "custom", "function": "missing"}),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "fn"), Edge("fn", "end"))

    executor = WorkflowEngine(g)
    await executor.start()
    await executor.step()  # start → fn

    with pytest.raises(ExecutionError, match="No function registry configured"):
        await executor.step()


async def test_function_handler_custom_unknown_function():
    """Custom action with unknown function name returns failed result."""
    registry = FunctionRegistry()

    g = Graph(id="unknown_fn", name="UnknownFn", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("fn", type="function", config={"action": "custom", "function": "nope"}),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "fn"), Edge("fn", "end"))

    executor = WorkflowEngine(g, handlers={"function": FunctionHandler(registry=registry)})
    await executor.start()
    await executor.step()  # start → fn

    with pytest.raises(ExecutionError, match="Unknown custom function"):
        await executor.step()


# --- ParallelHandler ---


async def test_parallel_executes_children():
    """ParallelHandler executes all children and stores outputs in context."""

    class MockAgent(NodeHandler):
        async def execute(self, node, context, engine):
            return NodeResult(output={"result": f"done-{node.id}"}, status="completed")

    g = Graph(id="par", name="Par", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("checks", type="parallel", config={"join": "all"}),
        Node("a", type="agent", config={}, parent="checks"),
        Node("b", type="agent", config={}, parent="checks"),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "checks"), Edge("checks", "end"))

    executor = WorkflowEngine(g, handlers={"agent": MockAgent()})
    ctx = await executor.run()

    # Children stored individually
    assert ctx.get("a.output.result") == "done-a"
    assert ctx.get("b.output.result") == "done-b"
    # Parallel node aggregates
    assert ctx.get("checks.output.a") == {"result": "done-a"}
    assert ctx.get("checks.output.b") == {"result": "done-b"}


async def test_parallel_no_children():
    """Parallel node with no children returns empty output."""
    g = Graph(id="empty_par", name="EmptyPar", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("checks", type="parallel"),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "checks"), Edge("checks", "end"))

    executor = WorkflowEngine(g)
    ctx = await executor.run()

    assert ctx.get("checks.output") == {}


async def test_parallel_child_failure():
    """Parallel node fails if any child handler returns failed."""

    class FailAgent(NodeHandler):
        async def execute(self, node, context, engine):
            if node.id == "bad":
                return NodeResult(output=None, status="failed", error="boom")
            return NodeResult(output={"ok": True}, status="completed")

    g = Graph(id="par_fail", name="ParFail", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("checks", type="parallel"),
        Node("good", type="agent", config={}, parent="checks"),
        Node("bad", type="agent", config={}, parent="checks"),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "checks"), Edge("checks", "end"))

    executor = WorkflowEngine(g, handlers={"agent": FailAgent()})
    await executor.start()
    await executor.step()  # start → checks

    with pytest.raises(ExecutionError, match="boom"):
        await executor.step()  # checks → fails


async def test_parallel_missing_child_handler():
    """Parallel node fails when a child has no registered handler."""
    g = Graph(id="par_miss", name="ParMiss", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("checks", type="parallel"),
        Node("child", type="notification", config={}, parent="checks"),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "checks"), Edge("checks", "end"))

    executor = WorkflowEngine(g)
    await executor.start()
    await executor.step()  # start → checks

    with pytest.raises(ExecutionError, match="No handler registered for child"):
        await executor.step()


async def test_parallel_child_exception():
    """Parallel node fails gracefully when a child handler raises."""

    class ExplodingHandler(NodeHandler):
        async def execute(self, node, context, engine):
            msg = "unexpected error"
            raise RuntimeError(msg)

    g = Graph(id="par_exc", name="ParExc", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("checks", type="parallel"),
        Node("child", type="agent", config={}, parent="checks"),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "checks"), Edge("checks", "end"))

    executor = WorkflowEngine(g, handlers={"agent": ExplodingHandler()})
    await executor.start()
    await executor.step()  # start → checks

    with pytest.raises(ExecutionError, match="unexpected error"):
        await executor.step()
