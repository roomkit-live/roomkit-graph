"""Run roomkit-graph nodes with RoomKit: ``pip install "roomkit-graph[roomkit]"``.

Every run works in a room, named by its trigger data's ``room_id``:

- ``agent`` nodes run a RoomKit agent on their prompt, in a child room of the
  run's room (``kit.delegate(..., wait=True)``);
- ``notification`` nodes write into a room in the application's name
  (``kit.post()``), so its transports deliver it (an SMS to the room's
  correspondent) and none of its agents answers it;
- ``human`` nodes do the same, then pause the run until ``RoomRuns.answer()``
  brings the reply that arrives in that room.

A host serving several organizations names the one a run acts for in its
trigger data's ``organization_id``: every room the run reaches is checked
against it (RoomKit's ``organization_id``), and another organization's raises
``RoomNotFoundError``.

``room_handlers(kit)`` gives the three handlers; ``RoomRuns`` drives runs and
keeps the paused ones by the room their answer will arrive in::

    runs = RoomRuns()
    engine = WorkflowEngine(graph, handlers=room_handlers(kit))
    await runs.start(engine, {"room_id": room.id, "topic": "..."})
    ...
    await runs.answer(room_id, {"text": reply})   # from an inbound message
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import time
import weakref
from collections import deque
from dataclasses import dataclass
from typing import Any

try:
    from roomkit import EventType, HookExecution, HookTrigger, RoomKit
    from roomkit.models.task import DelegatedTaskResult
    from roomkit.tasks.models import TaskStatus
except ImportError as exc:  # pragma: no cover - only without the extra
    msg = 'roomkit_graph.roomkit needs RoomKit: pip install "roomkit-graph[roomkit]"'
    raise ImportError(msg) from exc

from roomkit_graph._log import log_run
from roomkit_graph.engine.context import WorkflowContext
from roomkit_graph.engine.executor import WorkflowEngine
from roomkit_graph.handlers import NodeHandler, NodeResult
from roomkit_graph.nodes.base import Node

_RUN_ROOM = "{{trigger.room_id}}"

logger = logging.getLogger("roomkit_graph.roomkit")

_TEXT_DELTA = "text_delta"
"""The ephemeral an agent's answer text is published in as it is written,
by an agent created with ``publish_text_deltas=True``; others publish none."""
_QUIET_S = 0.02
_SETTLE_S = 0.5


@dataclass
class _LiveText:
    """A delegation whose agent's text is logged as it is written."""

    engine: WorkflowEngine
    node: Node
    agent: str
    organization_id: str | None = None
    subscription: str | None = None
    last_seen: float = 0.0

    async def on_ephemeral(self, event: Any) -> None:
        if getattr(event.type, "value", event.type) != _TEXT_DELTA:
            return
        self.last_seen = time.monotonic()
        text = (event.data or {}).get("text", "")
        if text:
            log_run(
                logger,
                logging.DEBUG,
                self.engine,
                "agent.text",
                "%s writes: %s",
                self.agent,
                text,
                node=self.node.id,
                agent=self.agent,
                text=text,
            )

    async def settle(self) -> None:
        """Let the text still on its way arrive: a quiet of ``_QUIET_S``,
        ``_SETTLE_S`` at most. Unsubscribing drops what is still queued."""
        deadline = time.monotonic() + _SETTLE_S
        while time.monotonic() < deadline:
            await asyncio.sleep(_QUIET_S / 4)
            if time.monotonic() - self.last_seen >= _QUIET_S:
                return


_WATCHED: contextvars.ContextVar[_LiveText | None] = contextvars.ContextVar(
    "roomkit_graph_live_text", default=None
)
_HOOKED: weakref.WeakSet[RoomKit] = weakref.WeakSet()


def _hook_live_text(kit: RoomKit) -> None:
    """Once per kit: when a node watching its agent's text delegates, subscribe
    to the task's child room before the agent starts (``ON_TASK_DELEGATED``
    runs before it)."""
    if kit in _HOOKED:
        return
    _HOOKED.add(kit)

    @kit.hook(
        HookTrigger.ON_TASK_DELEGATED,
        execution=HookExecution.ASYNC,
        name="roomkit_graph_live_text",
    )
    async def _subscribe(event: Any, context: Any) -> None:
        watch = _WATCHED.get()
        metadata = event.metadata or {}
        if watch is None or watch.subscription is not None:
            return
        if metadata.get("agent_id") != watch.agent or "child_room_id" not in metadata:
            return
        watch.subscription = await kit.subscribe_room(
            metadata["child_room_id"], watch.on_ephemeral, organization_id=watch.organization_id
        )


class AgentHandler(NodeHandler):
    """Runs ``config["agent"]`` on ``config["prompt"]``.

    The agent works in a child room of ``config["room"]`` (default: the run's
    room). The output is ``{"text": <answer>}``. With ``config["structured"]``
    the agent must hand its work back through RoomKit's ``submit_result`` tool,
    and the output is that call: ``{"status", "summary", "data", ...}``.
    """

    def __init__(self, kit: RoomKit) -> None:
        self._kit = kit
        _hook_live_text(kit)

    async def execute(
        self, node: Node, context: WorkflowContext, engine: WorkflowEngine
    ) -> NodeResult:
        structured = bool(node.config.get("structured"))
        result = await self._delegate(node, engine, structured)
        await self._log_done(node, engine, result)
        if result.status != TaskStatus.COMPLETED:
            return NodeResult(status="failed", error=result.error)
        if not structured:
            return NodeResult(output={"text": result.output})
        payload = json.loads(result.output or "{}")
        if payload.get("status") == "failed":
            return NodeResult(status="failed", error=payload.get("reason"))
        return NodeResult(output=payload)

    async def _delegate(
        self, node: Node, engine: WorkflowEngine, structured: bool
    ) -> DelegatedTaskResult:
        resolve = engine.template_resolver.resolve
        agent_id = node.config["agent"]
        prompt = resolve(node.config["prompt"])
        role = getattr(self._kit.get_channel(agent_id), "role", None)
        log_run(
            logger,
            logging.INFO,
            engine,
            "agent.start",
            "Agent %s works on %s",
            agent_id,
            node.id,
            node=node.id,
            agent=agent_id,
            role=role,
        )
        log_run(
            logger,
            logging.DEBUG,
            engine,
            "agent.prompt",
            "Prompt to %s: %s",
            agent_id,
            prompt,
            node=node.id,
            agent=agent_id,
            text=prompt,
        )
        room_id = resolve(node.config.get("room", _RUN_ROOM))
        return await self._run_task(engine, node, room_id, agent_id, prompt, structured)

    async def _run_task(
        self,
        engine: WorkflowEngine,
        node: Node,
        room_id: str,
        agent_id: str,
        prompt: str,
        structured: bool,
    ) -> DelegatedTaskResult:
        """Delegate; the agent's text is logged as it is written when content is."""
        organization_id = _organization(engine)
        watch = None
        if logger.isEnabledFor(logging.DEBUG):
            watch = _LiveText(engine, node, agent_id, organization_id)
        token = _WATCHED.set(watch)
        try:
            task = await self._kit.delegate(
                room_id,
                agent_id,
                prompt,
                wait=True,
                require_structured_result=structured,
                organization_id=organization_id,
            )
            return await task.wait()
        finally:
            _WATCHED.reset(token)
            if watch is not None and watch.subscription is not None:
                await watch.settle()
                await self._kit.unsubscribe_room(watch.subscription)

    async def _log_done(
        self, node: Node, engine: WorkflowEngine, result: DelegatedTaskResult
    ) -> None:
        """The agent's turn as RoomKit recorded it: duration, tokens, tools called."""
        agent_id = result.agent_id
        usage = result.metadata.get("turns", {}).get(agent_id, {}).get("ai_usage") or {}
        # RoomKit's usage counters are disjoint: the input is their sum.
        read = usage.get("cache_read_input_tokens") or 0
        tokens_in = (usage.get("input_tokens") or 0) + read
        tokens_in += usage.get("cache_creation_input_tokens") or 0
        events = await self._kit.store.list_events(result.child_room_id, limit=1000)
        tools = [
            getattr(event.content, "tool_name", "?")
            for event in events
            if event.type == EventType.TOOL_CALL_START
        ]
        log_run(
            logger,
            logging.INFO,
            engine,
            "agent.done",
            "Agent %s answered in %.1f s",
            agent_id,
            result.duration_ms / 1000,
            node=node.id,
            agent=agent_id,
            status=str(result.status),
            seconds=result.duration_ms / 1000,
            tokens_in=tokens_in if usage else None,
            tokens_cached=read,
            tokens_out=usage.get("output_tokens"),
            tools=tools,
        )
        log_run(
            logger,
            logging.DEBUG,
            engine,
            "agent.answer",
            "Answer from %s: %s",
            agent_id,
            result.output,
            node=node.id,
            agent=agent_id,
            text=result.output or "",
        )


class NotifyHandler(NodeHandler):
    """Sends ``config["text"]`` into ``config["room"]`` (default: the run's room).

    The message is the application's own (RoomKit's ``kit.post()``): the
    room's transports deliver it, no agent of the room answers it, and its
    metadata names the graph, run and node that sent it, under ``workflow``.
    The output is ``{"room": <room id>, "text": <text sent>}``.
    """

    def __init__(self, kit: RoomKit) -> None:
        self._kit = kit

    async def execute(
        self, node: Node, context: WorkflowContext, engine: WorkflowEngine
    ) -> NodeResult:
        room_id, text = await self._send(node, engine, "message.sent")
        return NodeResult(output={"room": room_id, "text": text})

    async def _send(self, node: Node, engine: WorkflowEngine, event: str) -> tuple[str, str]:
        resolve = engine.template_resolver.resolve
        room_id = resolve(node.config.get("room", _RUN_ROOM))
        text = resolve(node.config["text"])
        sender = {"graph": engine.graph.id, "run": engine.run_id, "node": node.id}
        await self._kit.post(
            room_id, text, metadata={"workflow": sender}, organization_id=_organization(engine)
        )
        log_run(
            logger,
            logging.INFO,
            engine,
            event,
            "Sent into room %s",
            room_id,
            node=node.id,
            room=room_id,
        )
        log_run(
            logger,
            logging.DEBUG,
            engine,
            "message.text",
            "Text sent: %s",
            text,
            node=node.id,
            text=text,
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
        room_id, _ = await self._send(node, engine, "question.sent")
        return NodeResult(output={"room": room_id}, status="waiting")


def _organization(engine: WorkflowEngine) -> str | None:
    """The organization the run acts for: its trigger data's
    ``organization_id``, ``None`` when it names none."""
    return engine.context.get("trigger.organization_id")


def room_handlers(kit: RoomKit) -> dict[str, NodeHandler]:
    """The ``agent``, ``notification`` and ``human`` handlers, run by *kit*."""
    return {
        "agent": AgentHandler(kit),
        "notification": NotifyHandler(kit),
        "human": AskHandler(kit),
    }


class RoomRuns:
    """Drives runs; keeps a run paused on an ``AskHandler`` node by its room.

    Several runs may wait on one room (two incidents paging the same on-call
    engineer): each answer arriving there resumes the run that asked first,
    so none is dropped and none is answered twice. Whoever the room delivers
    a message from answers; RoomKit routes a sender's messages to their own
    room, so a room with one correspondent is answered by that correspondent.

    The paused runs are held in memory: an application that must survive a
    restart stores ``engine.to_dict()`` instead and rebuilds the engine with
    ``WorkflowEngine.from_dict()``.
    """

    def __init__(self) -> None:
        # room id → the runs paused on it, oldest question first, with their node
        self._paused: dict[str, deque[tuple[WorkflowEngine, str]]] = {}

    async def start(self, engine: WorkflowEngine, trigger_data: dict[str, Any]) -> None:
        """Start a run and drive it until it completes or pauses."""
        await engine.start(trigger_data)
        await self._drive(engine)

    async def answer(self, room_id: str, data: dict[str, Any]) -> bool:
        """Resume the run that asked first in *room_id* with *data*; False when none waits."""
        waiting = self._paused.get(room_id)
        if not waiting:
            return False
        engine, node_id = waiting.popleft()
        if not waiting:
            del self._paused[room_id]
        await engine.resume(node_id, data)
        await self._drive(engine)
        return True

    async def _drive(self, engine: WorkflowEngine) -> None:
        while await engine.step():
            pass
        node_id = engine.current_node_id
        if engine.waiting and node_id is not None:
            room_id = engine.context.get(f"{node_id}.output.room")
            self._paused.setdefault(room_id, deque()).append((engine, node_id))
