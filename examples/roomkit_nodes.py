"""RoomKit handlers for roomkit-graph nodes, shared by the examples.

roomkit-graph ships no RoomKit handlers. These are the ones the examples
needed, kept in one module so what a RoomKit application has to write is in
plain sight. Every run's trigger data carries ``room_id``: the room the run
works in.

- ``AgentHandler``: an ``agent`` node runs a RoomKit agent on its prompt, in a
  child room of the run's room (``kit.delegate(..., wait=True)``).
- ``NotifyHandler``: a ``notification`` node sends a message into a room, so its
  transports deliver it (an SMS to the room's correspondent).
- ``AskHandler``: a ``human`` node does the same, then pauses the run until
  ``Runs.answer()`` brings the reply arriving in that room.
- ``WorkflowChannel``: the channel the workflow speaks from.
- ``Runs``: drives runs and keeps the paused ones by the room their answer
  will arrive in.
"""

from __future__ import annotations

import json
from typing import Any

from roomkit import (
    Channel,
    ChannelCategory,
    ChannelOutput,
    ChannelType,
    InboundMessage,
    RoomEvent,
    RoomKit,
    TextContent,
)
from roomkit.tasks.models import TaskStatus

from roomkit_graph import NodeHandler, NodeResult, WorkflowEngine

WORKFLOW_CHANNEL_ID = "workflow"


class WorkflowChannel(Channel):
    """The workflow's own voice in a room.

    What the workflow sends from it reaches the room's transports. It answers
    nothing, unlike an agent attached to the room, which would reply to every
    inbound message.
    """

    channel_type = ChannelType.SYSTEM
    category = ChannelCategory.INTELLIGENCE

    def __init__(self) -> None:
        super().__init__(WORKFLOW_CHANNEL_ID)

    async def handle_inbound(self, message: InboundMessage, context: Any) -> RoomEvent:
        msg = "The workflow channel receives nothing"
        raise TypeError(msg)

    async def deliver(self, event: RoomEvent, binding: Any, context: Any) -> ChannelOutput:
        return ChannelOutput.empty()


class AgentHandler(NodeHandler):
    """Runs ``config["agent"]`` on ``config["prompt"]``.

    The output is ``{"text": <answer>}``. With ``config["structured"]`` the agent
    must hand its work back through RoomKit's ``submit_result`` tool, and the
    output is that call: ``{"status", "summary", "data", ...}``.
    """

    def __init__(self, kit: RoomKit) -> None:
        self._kit = kit

    async def execute(self, node, context, engine) -> NodeResult:
        prompt = engine.template_resolver.resolve(node.config["prompt"])
        structured = bool(node.config.get("structured"))
        task = await self._kit.delegate(
            context.get("trigger.room_id"),
            node.config["agent"],
            prompt,
            wait=True,
            require_structured_result=structured,
        )
        result = await task.wait()
        if result.status != TaskStatus.COMPLETED:
            return NodeResult(status="failed", error=result.error)
        if not structured:
            return NodeResult(output={"text": result.output})
        payload = json.loads(result.output or "{}")
        if payload.get("status") == "failed":
            return NodeResult(status="failed", error=payload.get("reason"))
        return NodeResult(output=payload)


class NotifyHandler(NodeHandler):
    """Sends ``config["text"]`` into the room ``config["room"]`` names."""

    def __init__(self, kit: RoomKit) -> None:
        self._kit = kit

    async def execute(self, node, context, engine) -> NodeResult:
        room_id, text = await self._send(node, engine)
        return NodeResult(output={"room": room_id, "text": text})

    async def _send(self, node, engine) -> tuple[str, str]:
        room_id = engine.template_resolver.resolve(node.config["room"])
        text = engine.template_resolver.resolve(node.config["text"])
        if not await self._kit.store.binding_exists(room_id, WORKFLOW_CHANNEL_ID):
            await self._kit.attach_channel(room_id, WORKFLOW_CHANNEL_ID)
        # addressed_to=[]: a message for the people in the room, no agent's turn.
        await self._kit.send_event(
            room_id, WORKFLOW_CHANNEL_ID, TextContent(body=text), addressed_to=[]
        )
        return room_id, text


class AskHandler(NotifyHandler):
    """Asks in a room, then pauses until the reply arriving there."""

    async def execute(self, node, context, engine) -> NodeResult:
        room_id, _ = await self._send(node, engine)
        # Where the answer will come from; resume() replaces it with the answer.
        return NodeResult(output={"room": room_id}, status="waiting")


class Runs:
    """Drives runs; a run paused on an ``AskHandler`` node waits by its room."""

    def __init__(self) -> None:
        self._paused: dict[str, WorkflowEngine] = {}

    async def start(self, engine: WorkflowEngine, trigger_data: dict[str, Any]) -> None:
        await engine.start(trigger_data)
        await self._drive(engine)

    async def answer(self, room_id: str, data: dict[str, Any]) -> bool:
        """Resume the run waiting for *room_id*; False when none is."""
        engine = self._paused.pop(room_id, None)
        if engine is None:
            return False
        await engine.resume(engine.current_node_id, data)
        await self._drive(engine)
        return True

    async def _drive(self, engine: WorkflowEngine) -> None:
        while await engine.step():
            pass
        if engine.waiting:
            room_id = engine.context.get(f"{engine.current_node_id}.output.room")
            self._paused[room_id] = engine
