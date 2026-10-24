"""Tests for roomkit_graph.roomkit — nodes run by RoomKit agents and rooms."""

from __future__ import annotations

import pytest
from roomkit import RoomKit, SMSChannel
from roomkit.channels.ai import AIChannel
from roomkit.providers.ai.base import AIResponse, AIToolCall
from roomkit.providers.ai.mock import MockAIProvider
from roomkit.providers.sms.mock import MockSMSProvider

from roomkit_graph import Edge, Graph, ManualTrigger, Node, WorkflowEngine
from roomkit_graph.roomkit import RoomRuns, room_handlers


@pytest.fixture
async def kit():
    kit = RoomKit()
    yield kit
    await kit.close()


def _one_agent_graph(config: dict) -> Graph:
    g = Graph(id="agent", name="Agent", trigger=ManualTrigger())
    g.add_nodes(Node("start", type="start"), Node("work", type="agent", config=config))
    g.add_nodes(Node("end", type="end"))
    g.add_edges(Edge("start", "work"), Edge("work", "end"))
    return g


async def test_agent_node_outputs_the_agent_answer(kit):
    kit.register_channel(AIChannel("writer", provider=MockAIProvider(["A short report."])))
    room = await kit.create_room()
    graph = _one_agent_graph({"agent": "writer", "prompt": "Write about {{trigger.topic}}"})

    ctx = await WorkflowEngine(graph, handlers=room_handlers(kit)).run(
        {"room_id": room.id, "topic": "graphs"}
    )

    assert ctx.get("work.output.text") == "A short report."


async def test_structured_agent_node_outputs_the_submitted_result(kit):
    submitted = AIToolCall(
        id="call-1",
        name="submit_result",
        arguments={"status": "completed", "summary": "Checkout down", "data": {"urgent": True}},
    )
    provider = MockAIProvider(
        ai_responses=[AIResponse(content="", tool_calls=[submitted]), AIResponse(content="Done.")]
    )
    kit.register_channel(AIChannel("triage", provider=provider))
    room = await kit.create_room()
    graph = _one_agent_graph({"agent": "triage", "prompt": "Classify", "structured": True})

    ctx = await WorkflowEngine(graph, handlers=room_handlers(kit)).run({"room_id": room.id})

    assert ctx.get("steps.work.summary") == "Checkout down"
    assert ctx.get("steps.work.data.urgent") is True


async def test_human_node_pauses_until_the_answer_arrives_in_its_room(kit):
    sms = MockSMSProvider()
    kit.register_channel(SMSChannel("sms", provider=sms))
    await kit.create_room(room_id="ops")
    await kit.attach_channel("ops", "sms", metadata={"phone_number": "+15550109999"})
    g = Graph(id="approve", name="Approve", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("ask", type="human", config={"room": "ops", "text": "Refund {{trigger.amount}}?"}),
        Node("done", type="notification", config={"room": "ops", "text": "Noted: {{input.text}}"}),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "ask"), Edge("ask", "done"), Edge("done", "end"))
    engine = WorkflowEngine(g, handlers=room_handlers(kit))
    runs = RoomRuns()

    await runs.start(engine, {"room_id": "ops", "amount": 120})
    assert engine.waiting is True
    assert await runs.answer("elsewhere", {"text": "yes"}) is False
    assert await runs.answer("ops", {"text": "yes"}) is True

    assert [(s["to"], s["event"].content.body) for s in sms.sent] == [
        ("+15550109999", "Refund 120?"),
        ("+15550109999", "Noted: yes"),
    ]
    assert engine.current_node_id is None


async def test_runs_paused_on_one_room_are_answered_in_the_order_they_asked(kit):
    sms = MockSMSProvider()
    kit.register_channel(SMSChannel("sms", provider=sms))
    await kit.create_room(room_id="on-call")
    await kit.attach_channel("on-call", "sms", metadata={"phone_number": "+15550109999"})
    g = Graph(id="page", name="Page", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("page", type="human", config={"room": "on-call", "text": "Take {{trigger.case}}?"}),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "page"), Edge("page", "end"))
    runs = RoomRuns()
    first = WorkflowEngine(g, handlers=room_handlers(kit))
    second = WorkflowEngine(g, handlers=room_handlers(kit))

    await runs.start(first, {"room_id": "on-call", "case": "A"})
    await runs.start(second, {"room_id": "on-call", "case": "B"})
    assert await runs.answer("on-call", {"text": "OK"}) is True
    assert (first.current_node_id, second.waiting) == (None, True)
    assert await runs.answer("on-call", {"text": "OK"}) is True
    assert second.current_node_id is None
    assert await runs.answer("on-call", {"text": "OK"}) is False
