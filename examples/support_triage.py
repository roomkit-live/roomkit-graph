"""Support triage over SMS: a text starts a run, urgent ones page the on-call.

    SMS in ──▶ classify ──urgent──▶ page on-call ──(waits for "OK")──┐
                   └────────────────────────────────────────────────┴──▶ answer ──▶ reply SMS

A customer's SMS lands in their RoomKit room and starts a run. An agent
classifies it with a structured result. When it is urgent, the on-call
engineer gets an SMS in their own room and the run pauses there; their reply
resumes it. A second agent writes the answer, and the workflow texts it back
to the customer. The nodes run through ``roomkit_graph.roomkit``.

The people are simulated: two customers and the on-call engineer text in
through ``kit.process_inbound()``, the way an SMS webhook would. The SMS
provider is RoomKit's mock, which prints what would have been sent.

Requires:
    uv sync --extra examples
    export ANTHROPIC_API_KEY=...

Run with:
    uv run python examples/support_triage.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from pydantic import SecretStr
from roomkit import InboundMessage, Participant, RoomEvent, RoomKit, SMSChannel, TextContent
from roomkit.channels.agent import Agent
from roomkit.providers.anthropic import AnthropicAIProvider, AnthropicConfig
from roomkit.providers.sms.mock import MockSMSProvider

from roomkit_graph import Condition, Edge, EventTrigger, Graph, Node, WorkflowEngine, verbose
from roomkit_graph.roomkit import RoomRuns, room_handlers

MODEL = "claude-sonnet-5-5"
ON_CALL = "+15550109999"
ON_CALL_ROOM = "on-call"


class PrintingSMSProvider(MockSMSProvider):
    """The mock, made visible: what would leave shows up on the terminal."""

    async def send(self, event: RoomEvent, to: str, from_: str | None = None):
        print(f"  📱 → {to}: {event.content.body}")
        return await super().send(event, to, from_)


def triage_graph() -> Graph:
    graph = Graph(id="support-triage", name="Support triage", trigger=EventTrigger(event="sms"))
    graph.add_nodes(
        Node("start", type="start"),
        Node(
            "classify",
            type="agent",
            config={
                "agent": "triage",
                "structured": True,
                "prompt": (
                    "A customer texted: {{trigger.text}}\n"
                    'Submit data {"urgent": true} when the service is down or the '
                    'customer is losing money, else {"urgent": false}; the summary '
                    "says the problem in a few words."
                ),
            },
        ),
        Node(
            "page",
            type="human",
            config={
                "room": ON_CALL_ROOM,
                "text": "URGENT from {{trigger.from}}: {{steps.classify.summary}} Reply OK to take it.",
            },
        ),
        Node(
            "answer",
            type="agent",
            config={
                "agent": "support",
                "prompt": (
                    "Write the SMS answering this customer, under 300 characters.\n"
                    "They wrote: {{trigger.text}}\n"
                    "Triage: {{steps.classify.summary}} "
                    "(urgent: {{steps.classify.data.urgent}}).\n"
                    'On-call engineer\'s reply: {{steps.page.text | default("not paged")}}'
                ),
            },
        ),
        Node(
            "reply",
            type="notification",
            config={"room": "{{trigger.room_id}}", "text": "{{steps.answer.text}}"},
        ),
        Node("end", type="end"),
    )
    graph.add_edges(
        Edge("start", "classify"),
        Edge("classify", "page", condition=Condition.field("input.data.urgent").equals(True)),
        Edge("classify", "answer", condition=Condition.otherwise()),
        Edge("page", "answer"),
        Edge("answer", "reply"),
        Edge("reply", "end"),
    )
    graph.validate_or_raise()
    return graph


async def setup_kit() -> RoomKit:
    provider = AnthropicAIProvider(
        AnthropicConfig(api_key=SecretStr(os.environ["ANTHROPIC_API_KEY"]), model=MODEL)
    )
    kit = RoomKit()
    kit.register_channel(SMSChannel("sms", provider=PrintingSMSProvider()))
    kit.register_channel(
        Agent("triage", provider=provider, role="Support triage", description="Sorts requests.")
    )
    kit.register_channel(
        Agent(
            "support",
            provider=provider,
            role="Support agent",
            description="Answers customers by SMS: short, warm, concrete.",
        )
    )
    # The on-call engineer's own room: what the workflow sends there is texted
    # to them, and their replies come back to it.
    await kit.create_room(room_id=ON_CALL_ROOM)
    await kit.attach_channel(ON_CALL_ROOM, "sms", metadata={"phone_number": ON_CALL})
    await kit.store.add_participant(
        Participant(id=ON_CALL, room_id=ON_CALL_ROOM, channel_id="sms")
    )
    return kit


async def main() -> None:
    kit = await setup_kit()
    graph = triage_graph()
    handlers = room_handlers(kit)
    runs = RoomRuns()

    async def sms_in(sender: str, text: str) -> None:
        """What an SMS webhook does: hand the message to RoomKit, then to the runs."""
        print(f"\n  💬 {sender}: {text}")
        result = await kit.process_inbound(
            InboundMessage(channel_id="sms", sender_id=sender, content=TextContent(body=text))
        )
        room_id = result.event.room_id
        if await runs.answer(room_id, {"from": sender, "text": text}):
            return
        trigger = {"room_id": room_id, "from": sender, "text": text}
        await runs.start(WorkflowEngine(graph, handlers=handlers), trigger)

    try:
        await sms_in("+15550100001", "Your checkout has been failing for 20 minutes, I can't pay!")
        await sms_in(ON_CALL, "OK, on it")
        await sms_in("+15550100002", "Hi, how do I change the email on my account?")
    finally:
        await kit.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    verbose()  # each step on stderr as it happens; content=False hides the texts
    if "ANTHROPIC_API_KEY" not in os.environ:
        sys.exit("Set ANTHROPIC_API_KEY to run this example.")
    asyncio.run(main())
