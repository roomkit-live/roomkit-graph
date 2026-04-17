"""Tests for WorkflowEngine.stream() observer-side streaming API."""

from __future__ import annotations

from typing import Any

import pytest

from roomkit_graph import (
    Edge,
    ExecutionError,
    Graph,
    ManualTrigger,
    Node,
    NodeHandler,
    NodeResult,
    WorkflowContext,
    WorkflowEngine,
)


def _linear_graph() -> Graph:
    """start → work → end"""
    g = Graph(id="linear", name="Linear", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node(
            "work",
            type="function",
            config={"action": "set_context", "values": {"done": True}},
        ),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "work"), Edge("work", "end"))
    return g


class _EmittingHandler(NodeHandler):
    """Handler that emits custom events during execution."""

    def __init__(self, payloads: list[Any]) -> None:
        self._payloads = payloads

    async def execute(
        self, node: Node, context: WorkflowContext, engine: WorkflowEngine
    ) -> NodeResult:
        for p in self._payloads:
            engine.emit(p)
        return NodeResult(output={"ran": node.id}, status="completed")


class _WaitingHandler(NodeHandler):
    async def execute(
        self, node: Node, context: WorkflowContext, engine: WorkflowEngine
    ) -> NodeResult:
        return NodeResult(output={"paused": True}, status="waiting")


class _FailingHandler(NodeHandler):
    async def execute(
        self, node: Node, context: WorkflowContext, engine: WorkflowEngine
    ) -> NodeResult:
        return NodeResult(output=None, status="failed", error="boom")


# --- values mode ---


async def test_stream_values_emits_snapshots() -> None:
    g = _linear_graph()
    engine = WorkflowEngine(g)

    events = [e async for e in engine.stream(modes=("values",))]

    assert all(e["mode"] == "values" for e in events)
    # Initial snapshot + one per step (start, work, end)
    assert len(events) == 4
    # Final snapshot contains all node outputs
    final = events[-1]["payload"]
    assert "start" in final
    assert "work" in final


# --- updates mode ---


async def test_stream_updates_emits_deltas() -> None:
    g = _linear_graph()
    engine = WorkflowEngine(g)

    events = [e async for e in engine.stream(modes=("updates",))]

    # Three steps (start, work, end), end writes no output so only 2 deltas
    modes = [e["mode"] for e in events]
    assert modes == ["updates", "updates"]
    # First delta is from start, second from work
    assert "start" in events[0]["payload"]
    assert "work" in events[1]["payload"]
    assert events[1]["payload"]["work"] == {"output": {"done": True}}


# --- node mode ---


async def test_stream_node_phases() -> None:
    g = _linear_graph()
    engine = WorkflowEngine(g)

    events = [e async for e in engine.stream(modes=("node",))]

    # Every step emits start + complete — three steps: start, work, end
    phases = [(e["node_id"], e["payload"]["phase"]) for e in events]
    assert phases == [
        ("start", "start"),
        ("start", "complete"),
        ("work", "start"),
        ("work", "complete"),
        ("end", "start"),
        ("end", "complete"),
    ]
    assert all(
        e["payload"]["status"] == "completed"
        for e in events
        if e["payload"]["phase"] == "complete"
    )


# --- custom mode ---


async def test_stream_custom_from_handler() -> None:
    g = Graph(id="custom", name="Custom", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("agent", type="agent"),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "agent"), Edge("agent", "end"))

    engine = WorkflowEngine(
        g,
        handlers={"agent": _EmittingHandler([{"step": 1}, {"step": 2}])},
    )

    events = [e async for e in engine.stream(modes=("custom",))]

    assert [e["payload"] for e in events] == [{"step": 1}, {"step": 2}]
    assert all(e["node_id"] == "agent" for e in events)


# --- mode ordering ---


async def test_stream_multi_mode_ordering() -> None:
    g = Graph(id="order", name="Order", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("agent", type="agent"),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "agent"), Edge("agent", "end"))

    engine = WorkflowEngine(g, handlers={"agent": _EmittingHandler([{"progress": 1}])})

    events = [e async for e in engine.stream(modes=("values", "updates", "node", "custom"))]

    # Find the agent step — within it, ordering must be:
    # node:start, custom, node:complete, updates, values
    # Locate by finding node:start for "agent"
    agent_idx = next(
        i
        for i, e in enumerate(events)
        if e["mode"] == "node" and e["node_id"] == "agent" and e["payload"]["phase"] == "start"
    )
    slice_modes = [e["mode"] for e in events[agent_idx : agent_idx + 5]]
    slice_detail = [
        e["payload"].get("phase") if e["mode"] == "node" else None
        for e in events[agent_idx : agent_idx + 5]
    ]
    assert slice_modes == ["node", "custom", "node", "updates", "values"]
    assert slice_detail[0] == "start"
    assert slice_detail[2] == "complete"


# --- error propagation ---


async def test_stream_propagates_execution_error() -> None:
    g = Graph(id="fail", name="Fail", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("bad", type="agent"),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "bad"), Edge("bad", "end"))

    engine = WorkflowEngine(g, handlers={"agent": _FailingHandler()})

    collected = []
    with pytest.raises(ExecutionError):
        async for e in engine.stream(modes=("node",)):
            collected.append(e)

    # Last event before the exception should be node:complete status=failed
    assert collected[-1]["mode"] == "node"
    assert collected[-1]["payload"] == {
        "phase": "complete",
        "node_id": "bad",
        "status": "failed",
    }


# --- waiting/pause ---


async def test_stream_pauses_on_waiting() -> None:
    g = Graph(id="wait", name="Wait", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("human", type="human"),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "human"), Edge("human", "end"))

    engine = WorkflowEngine(g, handlers={"human": _WaitingHandler()})

    events = [e async for e in engine.stream(modes=("node",))]

    # Stream terminates cleanly with human's complete event as the last one
    assert events[-1]["mode"] == "node"
    assert events[-1]["node_id"] == "human"
    assert events[-1]["payload"] == {
        "phase": "complete",
        "node_id": "human",
        "status": "waiting",
    }


# --- engine.emit() outside a stream is a no-op ---


async def test_emit_outside_stream_is_noop() -> None:
    g = _linear_graph()
    engine = WorkflowEngine(g)

    # Should not raise even though no stream is active
    engine.emit({"anything": True})

    # Subsequent run() should work normally
    ctx = await engine.run()
    assert ctx.has("work.output")


# --- sequence numbers ---


async def test_stream_seq_is_monotonic() -> None:
    g = Graph(id="seq", name="Seq", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("agent", type="agent"),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "agent"), Edge("agent", "end"))

    engine = WorkflowEngine(g, handlers={"agent": _EmittingHandler([{"a": 1}, {"b": 2}])})

    events = [e async for e in engine.stream(modes=("values", "updates", "node", "custom"))]

    seqs = [e["seq"] for e in events]
    assert seqs == sorted(seqs)
    assert seqs[0] == 0
    assert len(set(seqs)) == len(seqs)


# --- multi-stream guard ---


async def test_stream_guard_rejects_concurrent_stream() -> None:
    g = _linear_graph()
    engine = WorkflowEngine(g)

    gen = engine.stream(modes=("updates",))
    # Advance the first iterator once so _stream_buffer is set
    await gen.__anext__()

    with pytest.raises(RuntimeError, match="single-shot"):
        async for _ in engine.stream(modes=("updates",)):
            pass

    # Drain the original stream cleanly so the engine resets _stream_buffer
    async for _ in gen:
        pass

    # Now a fresh stream on a fresh engine should work
    engine2 = WorkflowEngine(_linear_graph())
    events = [e async for e in engine2.stream(modes=("updates",))]
    assert len(events) >= 1


# --- parallel handler: emit() attribution ---


async def test_stream_custom_attributes_to_parallel_child() -> None:
    """engine.emit() inside a parallel child must attribute to the child,
    not the parent parallel node."""
    g = Graph(id="par", name="Par", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("fanout", type="parallel"),
        Node("a", type="agent", parent="fanout"),
        Node("b", type="agent", parent="fanout"),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "fanout"), Edge("fanout", "end"))

    engine = WorkflowEngine(
        g,
        handlers={
            "agent": _EmittingHandler([{"hi": "from-child"}]),
        },
    )

    events = [e async for e in engine.stream(modes=("custom",))]

    # Two custom events, one per child, each attributed to the correct child
    attribs = sorted(e["node_id"] for e in events)
    assert attribs == ["a", "b"]
    assert all(e["payload"] == {"hi": "from-child"} for e in events)


# --- WorkflowContext.drain_writes() ---


def test_drain_writes_tracks_sets_and_clears() -> None:
    ctx = WorkflowContext()
    assert ctx.drain_writes() == []

    ctx.set("a", {"x": 1})
    ctx.set("b", {"y": 2})
    ctx.set("a", {"x": 3})  # duplicate write

    writes = ctx.drain_writes()
    assert writes == ["a", "b", "a"]
    # Second drain is empty
    assert ctx.drain_writes() == []


def test_drain_writes_not_in_serialization() -> None:
    ctx = WorkflowContext()
    ctx.set("a", {"x": 1})
    # to_dict/from_dict should not carry the journal
    data = ctx.to_dict()
    assert "_writes" not in data
    restored = WorkflowContext.from_dict(data)
    assert restored.drain_writes() == []
