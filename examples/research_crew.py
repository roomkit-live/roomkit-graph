"""A research crew: one agent researches a topic, another writes it up.

The CrewAI quickstart as a roomkit-graph workflow, run by RoomKit agents:

    start ──▶ research ──▶ write ──▶ end

Each agent has a role and a description, like a CrewAI agent's role and
backstory. The graph sets the order, as a CrewAI sequential process does.
RoomKit runs each agent in a child room of the run's room and hands its
answer back to the graph (``roomkit_graph.roomkit``).

Requires:
    uv sync --extra examples
    export ANTHROPIC_API_KEY=...

Run with:
    uv run python examples/research_crew.py "AI agents in customer support"
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

from pydantic import SecretStr
from roomkit import RoomKit
from roomkit.channels.agent import Agent
from roomkit.providers.anthropic import AnthropicAIProvider, AnthropicConfig

from roomkit_graph import Edge, Graph, ManualTrigger, Node, WorkflowEngine, verbose
from roomkit_graph.roomkit import room_handlers

MODEL = "claude-sonnet-5-5"


def crew_graph() -> Graph:
    graph = Graph(id="research-crew", name="Research crew", trigger=ManualTrigger())
    graph.add_nodes(
        Node("start", type="start"),
        Node(
            "research",
            type="agent",
            config={
                "agent": "researcher",
                "prompt": (
                    "Research {{trigger.topic}}. List the ten most important facts, "
                    "trends and open questions, one line each."
                ),
            },
        ),
        Node(
            "write",
            type="agent",
            config={
                "agent": "writer",
                "prompt": (
                    "Write a short report on {{trigger.topic}} for a busy reader, "
                    "from these research notes:\n\n{{input.text}}"
                ),
            },
        ),
        Node("end", type="end"),
    )
    graph.add_edges(Edge("start", "research"), Edge("research", "write"), Edge("write", "end"))
    graph.validate_or_raise()
    return graph


async def main(topic: str) -> None:
    provider = AnthropicAIProvider(
        AnthropicConfig(
            api_key=SecretStr(os.environ["ANTHROPIC_API_KEY"]), model=MODEL, max_tokens=2048
        )
    )
    kit = RoomKit()
    kit.register_channel(
        Agent(
            "researcher",
            provider=provider,
            role="Senior research analyst",
            description="Finds what matters on a topic and separates facts from hype.",
            publish_text_deltas=True,  # its text, live, for verbose(messages=True)
        )
    )
    kit.register_channel(
        Agent(
            "writer",
            provider=provider,
            role="Report writer",
            description="Turns research notes into a clear, short report.",
            publish_text_deltas=True,  # its text, live, for verbose(messages=True)
        )
    )
    room = await kit.create_room()

    try:
        engine = WorkflowEngine(crew_graph(), handlers=room_handlers(kit))
        context = await engine.run(trigger_data={"room_id": room.id, "topic": topic})
        print(context.get("write.output.text"))
    finally:
        await kit.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    verbose(messages=True)  # each step on stderr; agents' text as they write it
    if "ANTHROPIC_API_KEY" not in os.environ:
        sys.exit("Set ANTHROPIC_API_KEY to run this example.")
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "AI agents in customer support"))
