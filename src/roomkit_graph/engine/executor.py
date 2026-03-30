from __future__ import annotations

from typing import TYPE_CHECKING, Any

from roomkit_graph.engine.context import WorkflowContext

if TYPE_CHECKING:
    from roomkit_graph.graph import Graph


class WorkflowExecutor:
    """Main execution engine — runs a workflow graph step by step.

    Reads the current phase from WorkflowContext, executes the node,
    evaluates outgoing edges, and transitions to the next node.
    """

    def __init__(self, graph: Graph, context: WorkflowContext | None = None) -> None:
        self._graph = graph
        self._context = context or WorkflowContext()

    @property
    def context(self) -> WorkflowContext:
        return self._context

    @property
    def current_node_id(self) -> str | None:
        """The node currently being executed, or None if not started / completed."""
        raise NotImplementedError

    async def start(self, trigger_data: dict[str, Any] | None = None) -> None:
        """Start workflow execution from the start node."""
        raise NotImplementedError

    async def step(self) -> bool:
        """Execute the current node and advance to the next.

        Returns True if the workflow advanced, False if it's complete or waiting.
        """
        raise NotImplementedError

    async def run(self, trigger_data: dict[str, Any] | None = None) -> WorkflowContext:
        """Run the entire workflow to completion. Returns the final context."""
        raise NotImplementedError

    async def resume(self, node_id: str, input_data: Any) -> None:
        """Resume a paused workflow (e.g. after human input) with external data."""
        raise NotImplementedError

    def evaluate_edges(self, node_id: str) -> str | None:
        """Evaluate outgoing edges and return the next node ID, or None."""
        raise NotImplementedError
