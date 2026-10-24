"""Run logging: one record per thing a run does, with its fields attached.

Every record goes to a ``roomkit_graph`` logger and carries a
``roomkit_graph`` attribute: the event (``node.start``, ``agent.done``...), the
run, the graph, the node, and the event's own fields. A plain log handler
prints the message; ``roomkit_graph.verbose()`` renders the fields.

INFO records name steps, durations and counts. What a person or a model
wrote — a prompt, an answer, a message — goes at DEBUG only.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from roomkit_graph.engine.executor import WorkflowEngine

FIELDS = "roomkit_graph"


def log_run(
    logger: logging.Logger,
    level: int,
    engine: WorkflowEngine,
    event: str,
    message: str,
    *args: Any,
    node: str | None = None,
    **fields: Any,
) -> None:
    """Log *event* of *engine*'s run, *message* formatted with *args*."""
    if not logger.isEnabledFor(level):
        return
    record = {"event": event, "run": engine.run_id, "graph": engine.graph.id, "node": node}
    logger.log(level, message, *args, extra={FIELDS: record | fields})
