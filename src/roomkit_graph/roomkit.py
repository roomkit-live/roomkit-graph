"""Run roomkit-graph nodes with RoomKit: ``pip install "roomkit-graph[roomkit]"``.

Every run works in a room, named by its trigger data's ``room_id``:

- ``agent`` nodes run a RoomKit agent on their prompt, in a child room of the
  run's room (``kit.delegate(..., wait=True)``);
- ``notification`` nodes send a message into a room, so its transports deliver
  it (an SMS to the room's correspondent);
- ``human`` nodes do the same, then pause the run until ``RoomRuns.answer()``
  brings the reply that arrives in that room.

``room_handlers(kit)`` gives the three handlers; ``RoomRuns`` drives runs and
keeps the paused ones by the room their answer will arrive in::

    runs = RoomRuns()
    engine = WorkflowEngine(graph, handlers=room_handlers(kit))
    await runs.start(engine, {"room_id": room.id, "topic": "..."})
    ...
    await runs.answer(room_id, {"text": reply})   # from an inbound message
"""

from __future__ import annotations

import json
from typing import Any

try:
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
except ImportError as exc:  # pragma: no cover - only without the extra
    msg = 'roomkit_graph.roomkit needs RoomKit: pip install "roomkit-graph[roomkit]"'
    raise ImportError(msg) from exc

from roomkit_graph.engine.context import WorkflowContext
from roomkit_graph.engine.executor import WorkflowEngine
from roomkit_graph.handlers import NodeHandler, NodeResult
from roomkit_graph.nodes.base import Node

WORKFLOW_CHANNEL_ID = "workflow"
_RUN_ROOM = "{{trigger.room_id}}"


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

    The agent works in a child room of ``config["room"]`` (default: the run's
    room). The output is ``{"text": <answer>}``. With ``config["structured"]``
    the agent must hand its work back through RoomKit's ``submit_result`` tool,
    and the output is that call: ``{"status", "summary", "data", ...}``.
    """

    def __init__(self, kit: RoomKit) -> None:
        self._kit = kit

    async def execute(
        self, node: Node, context: WorkflowContext, engine: WorkflowEngine
    ) -> NodeResult:
        resolve = engine.template_resolver.resolve
        structured = bool(node.config.get("structured"))
        task = await self._kit.delegate(
            resolve(node.config.get("room", _RUN_ROOM)),
            node.config["agent"],
            resolve(node.config["prompt"]),
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
    """Sends ``config["text"]`` into ``config["room"]`` (default: the run's room).

    The message comes from the ``WorkflowChannel``, attached to the room on
    first use. The output is ``{"room": <room id>, "text": <text sent>}``.
    """

    def __init__(self, kit: RoomKit) -> None:
        self._kit = kit
        if self._kit.get_channel(WORKFLOW_CHANNEL_ID) is None:
            self._kit.register_channel(WorkflowChannel())

    async def execute(
        self, node: Node, context: WorkflowContext, engine: WorkflowEngine
    ) -> NodeResult:
        room_id, text = await self._send(node, engine)
        return NodeResult(output={"room": room_id, "text": text})

    async def _send(self, node: Node, engine: WorkflowEngine) -> tuple[str, str]:
        resolve = engine.template_resolver.resolve
        room_id = resolve(node.config.get("room", _RUN_ROOM))
        text = resolve(node.config["text"])
        if not await self._kit.store.binding_exists(room_id, WORKFLOW_CHANNEL_ID):
            await self._kit.attach_channel(room_id, WORKFLOW_CHANNEL_ID)
        # addressed_to=[]: a message for the people in the room, no agent's turn.
        await self._kit.send_event(
            room_id, WORKFLOW_CHANNEL_ID, TextContent(body=text), addressed_to=[]
        )
        return room_id, text


class AskHandler(NotifyHandler):
    """Asks in a room like ``NotifyHandler``, then pauses the run.

    While paused, the node's output is ``{"room": <room id>}``: where the answer
    will arrive. ``resume()`` replaces it with the answer.
    """

    async def execute(
        self, node: Node, context: WorkflowContext, engine: WorkflowEngine
    ) -> NodeResult:
        room_id, _ = await self._send(node, engine)
        return NodeResult(output={"room": room_id}, status="waiting")


def room_handlers(kit: RoomKit) -> dict[str, NodeHandler]:
    """The ``agent``, ``notification`` and ``human`` handlers, run by *kit*."""
    return {
        "agent": AgentHandler(kit),
        "notification": NotifyHandler(kit),
        "human": AskHandler(kit),
    }


class RoomRuns:
    """Drives runs; keeps a run paused on an ``AskHandler`` node by its room.

    The paused runs are held in memory: an application that must survive a
    restart stores ``engine.to_dict()`` instead and rebuilds the engine with
    ``WorkflowEngine.from_dict()``.
    """

    def __init__(self) -> None:
        # room id → the paused run and the node it waits on
        self._paused: dict[str, tuple[WorkflowEngine, str]] = {}

    async def start(self, engine: WorkflowEngine, trigger_data: dict[str, Any]) -> None:
        """Start a run and drive it until it completes or pauses."""
        await engine.start(trigger_data)
        await self._drive(engine)

    async def answer(self, room_id: str, data: dict[str, Any]) -> bool:
        """Resume the run waiting for *room_id* with *data*; False when none is."""
        paused = self._paused.pop(room_id, None)
        if paused is None:
            return False
        engine, node_id = paused
        await engine.resume(node_id, data)
        await self._drive(engine)
        return True

    async def _drive(self, engine: WorkflowEngine) -> None:
        while await engine.step():
            pass
        node_id = engine.current_node_id
        if engine.waiting and node_id is not None:
            room_id = engine.context.get(f"{node_id}.output.room")
            self._paused[room_id] = (engine, node_id)
