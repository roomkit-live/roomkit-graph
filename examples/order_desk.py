"""An order desk: two agents, each with its own tools, one with a skill.

    start ──▶ investigate ──▶ resolve ──▶ end

A customer complains about an order. The investigator finds the facts with
two tools (``lookup_order``, ``track_shipment``). The resolver applies the
shop's refund policy, an Agent Skill (``skills/refund-policy/SKILL.md``) it
loads when it needs it, issues the refund with a tool (``issue_refund``) and
writes the reply.

The graph only names the agents: their tools and skills are the agents' own,
set on the RoomKit ``Agent``, and they use them in the child room each task
runs in. ``verbose(messages=True)`` shows the tools each one called and its
text as it writes it.

The shop's data is a few dicts: no key but the model's.

Requires:
    uv sync --extra examples
    export ANTHROPIC_API_KEY=...

Run with:
    uv run python examples/order_desk.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from pydantic import SecretStr
from roomkit import RoomKit
from roomkit.channels.agent import Agent
from roomkit.providers.ai.base import AITool
from roomkit.providers.anthropic import AnthropicAIProvider, AnthropicConfig
from roomkit.skills.registry import SkillRegistry

from roomkit_graph import Edge, Graph, ManualTrigger, Node, WorkflowEngine, verbose
from roomkit_graph.roomkit import room_handlers

MODEL = "claude-sonnet-5-5"
SKILLS_DIR = Path(__file__).resolve().parent / "skills"

ORDERS = {
    "1042": {
        "customer": "Marie",
        "items": [{"name": "espresso machine", "price": 249.0}],
        "amount": 249.0,
        "tracking": "TRK-88",
    }
}
SHIPMENTS = {
    "TRK-88": {
        "status": "delivered",
        "promised": "2026-10-14",
        "delivered": "2026-10-22",
        "note": "box dented, carrier photo on file",
    }
}
REFUNDS: list[dict[str, Any]] = []


def _tool(name: str, description: str, **properties: dict[str, Any]) -> AITool:
    return AITool(
        name=name,
        description=description,
        parameters={"type": "object", "properties": properties, "required": list(properties)},
    )


INVESTIGATOR_TOOLS = [
    _tool("lookup_order", "An order by its number", order_id={"type": "string"}),
    _tool("track_shipment", "A shipment by its tracking id", tracking={"type": "string"}),
]
RESOLVER_TOOLS = [
    _tool(
        "issue_refund",
        "Refund part of an order to the customer",
        order_id={"type": "string"},
        amount={"type": "number"},
        reason={"type": "string"},
    ),
]


async def investigator_tools(name: str, arguments: dict[str, Any]) -> str:
    if name == "lookup_order":
        return json.dumps(ORDERS.get(arguments["order_id"], {"error": "no such order"}))
    if name == "track_shipment":
        return json.dumps(SHIPMENTS.get(arguments["tracking"], {"error": "no such shipment"}))
    return json.dumps({"error": f"unknown tool {name}"})


async def resolver_tools(name: str, arguments: dict[str, Any]) -> str:
    if name != "issue_refund":
        return json.dumps({"error": f"unknown tool {name}"})
    order = ORDERS.get(arguments["order_id"])
    already = sum(r["amount"] for r in REFUNDS if r["order_id"] == arguments["order_id"])
    if order is None or already + arguments["amount"] > order["amount"]:
        return json.dumps({"error": "refused: more than the order amount"})
    REFUNDS.append(dict(arguments))
    return json.dumps({"refunded": arguments["amount"], "order_id": arguments["order_id"]})


def desk_graph() -> Graph:
    graph = Graph(id="order-desk", name="Order desk", trigger=ManualTrigger())
    graph.add_nodes(
        Node("start", type="start"),
        Node(
            "investigate",
            type="agent",
            config={
                "agent": "investigator",
                "prompt": (
                    "A customer writes: {{trigger.message}}\n"
                    "Find their order and what happened to its delivery. Report the facts "
                    "only: order, amount, items, promised and actual dates, any damage."
                ),
            },
        ),
        Node(
            "resolve",
            type="agent",
            config={
                "agent": "resolver",
                "prompt": (
                    "A customer writes: {{trigger.message}}\n"
                    "The facts:\n{{input.text}}\n"
                    "Apply our refund policy, issue what it grants, and write the reply "
                    "to the customer."
                ),
            },
        ),
        Node("end", type="end"),
    )
    graph.add_edges(
        Edge("start", "investigate"), Edge("investigate", "resolve"), Edge("resolve", "end")
    )
    graph.validate_or_raise()
    return graph


def load_skills() -> SkillRegistry:
    """The shop's skills, read from disk before the event loop starts."""
    skills = SkillRegistry()
    skills.discover(SKILLS_DIR)
    return skills


async def main(skills: SkillRegistry) -> None:
    provider = AnthropicAIProvider(
        AnthropicConfig(
            api_key=SecretStr(os.environ["ANTHROPIC_API_KEY"]), model=MODEL, max_tokens=2048
        )
    )
    kit = RoomKit()
    kit.register_channel(
        Agent(
            "investigator",
            provider=provider,
            role="Order investigator",
            description="Finds what happened to an order, from the shop's systems.",
            tools=INVESTIGATOR_TOOLS,
            tool_handler=investigator_tools,
        )
    )
    kit.register_channel(
        Agent(
            "resolver",
            provider=provider,
            role="Customer care lead",
            description="Decides what the shop owes a customer and answers them.",
            tools=RESOLVER_TOOLS,
            tool_handler=resolver_tools,
            skills=skills,
        )
    )
    room = await kit.create_room()

    try:
        engine = WorkflowEngine(desk_graph(), handlers=room_handlers(kit))
        message = "Order 1042 arrived a week late and the machine's box was dented. Not happy."
        context = await engine.run(trigger_data={"room_id": room.id, "message": message})
        print(context.get("resolve.output.text"))
        print(f"\nRefunds issued: {REFUNDS}")
    finally:
        await kit.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    verbose(messages=True)  # each step on stderr; agents' text as they write it (RoomKit 0.109+)
    if "ANTHROPIC_API_KEY" not in os.environ:
        sys.exit("Set ANTHROPIC_API_KEY to run this example.")
    asyncio.run(main(load_skills()))
