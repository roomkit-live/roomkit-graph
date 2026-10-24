"""Tests for run logging and verbose() — what a run tells while it runs."""

from __future__ import annotations

import io
import logging

import pytest

from roomkit_graph import (
    Edge,
    ExecutionError,
    Graph,
    ManualTrigger,
    Node,
    NodeHandler,
    NodeResult,
    WorkflowEngine,
    verbose,
)


class _Ask(NodeHandler):
    async def execute(self, node, context, engine):
        return NodeResult(status="waiting")


class _Boom(NodeHandler):
    async def execute(self, node, context, engine):
        msg = "provider down"
        raise RuntimeError(msg)


def _graph(middle_type: str) -> Graph:
    g = Graph(id="g", name="G", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("prep", type="function", config={"action": "set_context", "values": {}}),
        Node("ask", type=middle_type),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "prep"), Edge("prep", "ask"), Edge("ask", "end"))
    return g


def _events(caplog) -> list[tuple[str, str | None]]:
    return [
        (r.roomkit_graph["event"], r.roomkit_graph["node"])
        for r in caplog.records
        if hasattr(r, "roomkit_graph")
    ]


async def test_a_run_logs_each_step_its_pause_and_its_end(caplog):
    caplog.set_level(logging.DEBUG, logger="roomkit_graph")
    engine = WorkflowEngine(_graph("ask"), handlers={"ask": _Ask()})

    await engine.run()
    await engine.resume("ask", {"text": "ok"})
    while await engine.step():
        pass

    assert _events(caplog) == [
        ("run.start", None),
        ("node.start", "start"),
        ("node.complete", "start"),
        ("node.start", "prep"),
        ("node.complete", "prep"),
        ("node.start", "ask"),
        ("node.wait", "ask"),
        ("node.resume", "ask"),
        ("run.complete", None),
    ]
    assert {r.roomkit_graph["run"] for r in caplog.records} == {engine.run_id}


class _Refuses(NodeHandler):
    async def execute(self, node, context, engine):
        return NodeResult(status="failed", error="no quota")


@pytest.mark.parametrize(
    ("handler", "error", "logged"),
    [
        (_Boom(), RuntimeError, "RuntimeError('provider down')"),
        (_Refuses(), ExecutionError, "no quota"),
    ],
)
async def test_a_failing_node_is_logged_before_its_error_propagates(
    caplog, handler, error, logged
):
    caplog.set_level(logging.DEBUG, logger="roomkit_graph")
    engine = WorkflowEngine(_graph("broken"), handlers={"broken": handler})

    with pytest.raises(error):
        await engine.run()

    failed = [r for r in caplog.records if r.roomkit_graph["event"] == "node.fail"]
    assert [(r.levelno, r.roomkit_graph["node"], r.roomkit_graph["error"]) for r in failed] == [
        (logging.WARNING, "ask", logged)
    ]


async def test_verbose_prints_a_line_per_step_and_close_restores_the_logger():
    logger = logging.getLogger("roomkit_graph")
    before = (logger.level, logger.propagate)
    out = io.StringIO()
    handler = verbose(stream=out)
    try:
        engine = WorkflowEngine(_graph("ask"), handlers={"ask": _Ask()})
        await engine.run()
    finally:
        handler.close()

    prefix = f"[g {engine.run_id}] "
    lines = [line.removeprefix(prefix) for line in out.getvalue().splitlines()]
    assert lines[0] == "▶ run started"
    assert "▶ prep (function)" in lines
    assert lines[-1] == "⏸ ask · waiting for an answer"
    assert (logger.level, logger.propagate, handler in logger.handlers) == (*before, False)


async def test_verbose_shows_control_characters_escaped_not_obeyed():
    """A customer's text or an error cannot drive the terminal: no escape reaches it."""

    class _Hostile(NodeHandler):
        async def execute(self, node, context, engine):
            return NodeResult(status="failed", error="bad\x1b[2J\x1b]0;owned\x07 ‮drow")

    out = io.StringIO()
    handler = verbose(stream=out)
    try:
        with pytest.raises(ExecutionError):
            await WorkflowEngine(_graph("hostile"), handlers={"hostile": _Hostile()}).run()
    finally:
        handler.close()

    shown = out.getvalue()
    assert "\x1b" not in shown and "\x07" not in shown and "‮" not in shown
    assert "bad\\x1b[2J\\x1b]0;owned\\x07 \\u202edrow" in shown


def _record(run: str, event: str, **fields) -> None:
    logging.getLogger("roomkit_graph").debug(
        event, extra={"roomkit_graph": {"event": event, "run": run, "graph": "g", **fields}}
    )


def test_verbose_messages_prints_text_as_written_runs_kept_apart():
    out = io.StringIO()
    handler = verbose(messages=True, stream=out)
    try:
        _record("a", "agent.text", node="write", agent="writer", text="Hello wor")
        _record("b", "node.start", node="classify", type="agent")
        _record("a", "agent.text", node="write", agent="writer", text="ld\nsecond line")
        _record("a", "agent.answer", node="write", agent="writer", text="Hello world...")
        _record("c", "agent.answer", node="draft", agent="writer", text="Shown cut")
    finally:
        handler.close()

    assert out.getvalue().splitlines() == [
        "[g a]   ✎ Hello wor",
        "[g b] ▶ classify (agent)",
        "[g a]   ✎ ld",
        "[g a]   ✎ second line",
        "[g c]   answer: Shown cut",
    ]
