"""Observer-side streaming for WorkflowEngine.

Defines the event types (StreamMode, StreamEvent), the task-local current
node ContextVar used by ``engine.emit()`` for attribution, and the
_StreamingMixin that provides ``stream()`` and ``emit()`` on top of the
engine's execution loop.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Literal, TypedDict

from roomkit_graph.errors import ExecutionError

if TYPE_CHECKING:
    from roomkit_graph.engine.context import WorkflowContext
    from roomkit_graph.graph import Graph

StreamMode = Literal["values", "updates", "lifecycle", "custom"]
"""Which view of execution to emit.

- ``values``: full context snapshot before start + after each step (expensive)
- ``updates``: compact delta keyed by node_id written that step
- ``lifecycle``: per-node start/complete events (``phase="start"`` / ``phase="complete"``)
- ``custom``: handler-emitted events via ``engine.emit(...)``
"""


class StreamEvent(TypedDict):
    """One event yielded by ``WorkflowEngine.stream()``.

    ``seq`` is monotonic within a single stream() call and resets on each call.
    ``node_id`` may be None for events that are not tied to a specific node
    (e.g. the initial ``values`` snapshot before any step runs).
    """

    mode: StreamMode
    payload: Any
    node_id: str | None
    seq: int


# Task-local current node id, used by emit() to attribute custom events to
# the right node even when handlers run concurrently (e.g. ParallelHandler
# children). ContextVar snapshots propagate across asyncio.TaskGroup
# boundaries, so each child task sees its own value.
_current_node_var: ContextVar[str | None] = ContextVar("roomkit_graph_current_node", default=None)


class _StreamingMixin:
    """Provides stream() and emit() on top of WorkflowEngine.

    Assumes the host class exposes ``_graph``, ``_context``, ``_current``,
    ``_waiting``, ``start()`` and ``step()`` — all provided by WorkflowEngine.
    """

    _stream_buffer: list[StreamEvent] | None = None
    _stream_seq: int = 0

    if TYPE_CHECKING:
        _graph: Graph
        _context: WorkflowContext
        _current: str | None
        _waiting: bool

        async def start(self, trigger_data: dict[str, Any] | None = None) -> None: ...
        async def step(self) -> bool: ...

    def emit(self, payload: Any) -> None:
        """Emit a custom stream event from within a handler.

        Attributes the event to the currently executing node via a task-local
        ContextVar so parallel children are attributed correctly. Outside a
        ``stream()`` context this is a no-op, so handlers can call it
        unconditionally.

        Emit synchronously from ``execute()``. Events emitted from
        fire-and-forget tasks that outlive ``execute()`` will land on the
        next step's drain and appear out of order relative to that node's
        ``node:complete`` event.
        """
        if self._stream_buffer is None:
            return
        self._stream_buffer.append(
            self._make_event("custom", payload, node_id=_current_node_var.get())
        )

    def _next_seq(self) -> int:
        seq = self._stream_seq
        self._stream_seq += 1
        return seq

    def _make_event(
        self,
        mode: StreamMode,
        payload: Any,
        *,
        node_id: str | None = None,
    ) -> StreamEvent:
        return {
            "mode": mode,
            "payload": payload,
            "node_id": node_id,
            "seq": self._next_seq(),
        }

    def _drain_custom(self, mode_set: set[StreamMode]) -> list[StreamEvent]:
        """Pull pending custom events, filter by mode_set, clear the buffer."""
        if self._stream_buffer is None:
            return []
        out = [ev for ev in self._stream_buffer if ev["mode"] in mode_set]
        self._stream_buffer.clear()
        return out

    def _lifecycle_complete_event(self, node_id: str, *, failed: bool) -> StreamEvent:
        if failed:
            status = "failed"
        elif self._waiting:
            status = "waiting"
        else:
            status = "completed"
        return self._make_event(
            "lifecycle",
            {"phase": "complete", "node_id": node_id, "status": status},
            node_id=node_id,
        )

    async def stream(
        self,
        trigger_data: dict[str, Any] | None = None,
        *,
        modes: Iterable[StreamMode] = ("updates",),
    ) -> AsyncIterator[StreamEvent]:
        """Run the workflow and yield typed events as it executes.

        Drives the same start/step loop as ``run()`` but yields events at
        well-defined points. Single-shot per engine instance; calling while
        a stream is already active raises RuntimeError.

        Event ordering per step:
            1. lifecycle (phase="start")
            2. any custom events emitted by the handler
            3. lifecycle (phase="complete", status=completed|waiting|failed)
            4. updates (delta of node_ids written this step)
            5. values (full snapshot)

        The initial ``values`` event (yielded before the first step) contains
        the context already seeded by ``start()`` with the trigger data — it
        is not an empty snapshot.

        Args:
            trigger_data: Input passed to the start node (same as ``run()``).
            modes: Which event modes to emit. Defaults to ``("updates",)``.

        Yields:
            StreamEvent dicts. Errors from handlers propagate through the
            iterator after a final ``lifecycle`` complete event is yielded.
        """
        if self._stream_buffer is not None:
            msg = "stream() is single-shot; a stream is already active on this engine"
            raise RuntimeError(msg)

        mode_set = set(modes)
        self._stream_buffer = []
        self._stream_seq = 0

        try:
            await self.start(trigger_data)
            self._context.drain_writes()  # discard start() seed

            if "values" in mode_set:
                yield self._make_event("values", self._context.to_dict())

            while True:
                node_id = self._current
                if node_id is None:
                    break
                node = self._graph.get_node(node_id)

                if "lifecycle" in mode_set:
                    yield self._make_event(
                        "lifecycle",
                        {"phase": "start", "node_id": node_id, "type": str(node.type)},
                        node_id=node_id,
                    )

                token = _current_node_var.set(node_id)
                failed = False
                try:
                    try:
                        advanced = await self.step()
                    except ExecutionError:
                        failed = True
                        raise
                finally:
                    _current_node_var.reset(token)
                    for ev in self._drain_custom(mode_set):
                        yield ev
                    if "lifecycle" in mode_set:
                        yield self._lifecycle_complete_event(node_id, failed=failed)

                written = self._context.drain_writes()
                if "updates" in mode_set and written:
                    delta = {nid: self._context.get(nid) for nid in written}
                    yield self._make_event("updates", delta, node_id=node_id)

                if "values" in mode_set:
                    yield self._make_event("values", self._context.to_dict())

                if not advanced or self._waiting:
                    break
        finally:
            self._stream_buffer = None
