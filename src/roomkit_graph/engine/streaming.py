"""Streaming event types for WorkflowEngine.stream().

Events are emitted at well-defined points during execution so external
observers (dashboards, webhooks, audit logs) can react without mutating
the graph.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Literal, TypedDict

StreamMode = Literal["values", "updates", "node", "custom"]
"""Which view of execution to emit.

- ``values``: full context snapshot before start + after each step (expensive)
- ``updates``: compact delta keyed by node_id written that step
- ``node``: lifecycle events (``phase="start"`` / ``phase="complete"``)
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


# Task-local current node id, used by WorkflowEngine.emit() to attribute
# custom events to the right node even when handlers run concurrently
# (e.g. ParallelHandler children). ContextVar snapshots propagate across
# asyncio.TaskGroup boundaries, so each child task sees its own value.
_current_node_var: ContextVar[str | None] = ContextVar("roomkit_graph_current_node", default=None)
