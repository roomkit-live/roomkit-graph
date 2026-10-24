"""A review loop: an agent drafts, an editor answers by SMS, until it is approved.

    start ──▶ draft ──▶ review ──"OK"──▶ publish ──▶ end
                ▲          │
                └─feedback─┘

A writer agent drafts an SMS announcement. The editor receives each draft by
SMS and the run pauses; their reply resumes it. "OK" publishes the draft to a
subscriber; anything else is feedback, and the run goes back to the writer.

On its way back, ``draft`` reads what sent it there: ``{{input.text}}`` is the
editor's feedback, and ``{{steps.draft.text}}`` the draft it replaces. On the
first pass neither exists, and ``default(...)`` stands in for them.

The editor is simulated, texting in through ``kit.process_inbound()`` the way
an SMS webhook would. The SMS provider is RoomKit's mock, which prints what
would have been sent.

Requires:
    uv sync --extra examples
    export ANTHROPIC_API_KEY=...

Run with:
    uv run python examples/review_loop.py
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

from roomkit_graph import Condition, Edge, Graph, ManualTrigger, Node, WorkflowEngine
from roomkit_graph.roomkit import RoomRuns, room_handlers

MODEL = "claude-sonnet-5-5"
EDITOR = "+15550107777"
SUBSCRIBER = "+15550108888"


class PrintingSMSProvider(MockSMSProvider):
    """The mock, made visible: what would leave shows up on the terminal."""

    async def send(self, event: RoomEvent, to: str, from_: str | None = None):
        print(f"\n  📱 → {to}:\n{event.content.body}")
        return await super().send(event, to, from_)


def review_graph() -> Graph:
    graph = Graph(id="review-loop", name="Review loop", trigger=ManualTrigger())
    graph.add_nodes(
        Node("start", type="start"),
        Node(
            "draft",
            type="agent",
            config={
                "agent": "writer",
                "prompt": (
                    "Write an SMS announcement, three short lines at most: {{trigger.brief}}\n"
                    'Your previous draft: {{steps.draft.text | default("none yet")}}\n'
                    'The editor\'s feedback on it: {{input.text | default("none yet")}}\n'
                    "Answer with the announcement only."
                ),
            },
        ),
        Node(
            "review",
            type="human",
            config={
                "room": "editor",
                "text": "{{input.text}}\n\nReply OK to publish, or say what to change.",
            },
        ),
        Node(
            "publish", type="notification", config={"room": "news", "text": "{{steps.draft.text}}"}
        ),
        Node("end", type="end"),
    )
    graph.add_edges(
        Edge("start", "draft"),
        Edge("draft", "review"),
        Edge("review", "publish", condition=Condition.field("input.text").in_(["OK", "Ok", "ok"])),
        Edge("review", "draft", condition=Condition.otherwise()),
        Edge("publish", "end"),
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
        Agent(
            "writer",
            provider=provider,
            role="Announcement writer",
            description="Writes short, concrete product announcements.",
        )
    )
    # The run's own room, where the writer works; the editor's room, where
    # drafts are texted and replies come back; the subscriber's, for publishing.
    await kit.create_room(room_id="newsroom")
    await kit.create_room(room_id="editor")
    await kit.attach_channel("editor", "sms", metadata={"phone_number": EDITOR})
    await kit.store.add_participant(Participant(id=EDITOR, room_id="editor", channel_id="sms"))
    await kit.create_room(room_id="news")
    await kit.attach_channel("news", "sms", metadata={"phone_number": SUBSCRIBER})
    return kit


async def main() -> None:
    kit = await setup_kit()
    runs = RoomRuns()

    async def sms_in(sender: str, text: str) -> None:
        """What an SMS webhook does: hand the message to RoomKit, then to the runs."""
        print(f"\n  💬 {sender}: {text}")
        result = await kit.process_inbound(
            InboundMessage(channel_id="sms", sender_id=sender, content=TextContent(body=text))
        )
        await runs.answer(result.event.room_id, {"from": sender, "text": text})

    try:
        engine = WorkflowEngine(review_graph(), handlers=room_handlers(kit))
        brief = "our app now books a table in two taps, from today, for every restaurant"
        await runs.start(engine, {"room_id": "newsroom", "brief": brief})
        await sms_in(EDITOR, "Too long. Lead with 'two taps' and drop 'for every restaurant'.")
        await sms_in(EDITOR, "OK")
    finally:
        await kit.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    if "ANTHROPIC_API_KEY" not in os.environ:
        sys.exit("Set ANTHROPIC_API_KEY to run this example.")
    asyncio.run(main())
