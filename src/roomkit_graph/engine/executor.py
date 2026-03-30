from __future__ import annotations

from typing import TYPE_CHECKING, Any

from roomkit_graph.engine.context import WorkflowContext
from roomkit_graph.errors import NoValidTransitionError
from roomkit_graph.nodes.base import NodeType

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
        self._current: str | None = None
        self._waiting: bool = False  # True when paused at a human node

    @property
    def context(self) -> WorkflowContext:
        return self._context

    @property
    def current_node_id(self) -> str | None:
        """The node currently being executed, or None if not started / completed."""
        return self._current

    async def start(self, trigger_data: dict[str, Any] | None = None) -> None:
        """Start workflow execution from the start node."""
        start_node = next(
            (n for n in self._graph.nodes.values() if n.type == NodeType.START),
            None,
        )
        if start_node is None:
            msg = "Graph has no start node"
            raise ValueError(msg)
        self._current = start_node.id
        self._context.set("start", {"input": trigger_data})

    async def step(self) -> bool:
        """Execute the current node and advance to the next.

        Returns True if the workflow advanced, False if it's complete or waiting.
        """
        if self._current is None:
            return False

        node = self._graph.get_node(self._current)

        # End node — workflow complete
        if node.type == NodeType.END:
            self._current = None
            return False

        # Human node — pause and wait for resume()
        if node.type == NodeType.HUMAN and not self._waiting:
            self._waiting = True
            return True  # advanced to human node, now waiting

        # Execute node based on type
        if node.type == NodeType.FUNCTION:
            self._execute_function(node)

        # Evaluate edges and advance
        next_id = self.evaluate_edges(self._current)
        if next_id is None:
            self._current = None
            return False

        self._current = next_id
        self._waiting = False
        return True

    async def run(self, trigger_data: dict[str, Any] | None = None) -> WorkflowContext:
        """Run the entire workflow to completion. Returns the final context."""
        await self.start(trigger_data)
        while await self.step():
            pass
        return self._context

    async def resume(self, node_id: str, input_data: Any) -> None:
        """Resume a paused workflow (e.g. after human input) with external data."""
        self._context.set(node_id, input_data)
        self._waiting = False

    def evaluate_edges(self, node_id: str) -> str | None:
        """Evaluate outgoing edges and return the next node ID, or None."""
        edges = self._graph.get_outgoing_edges(node_id)
        if not edges:
            return None

        # Try conditional edges first
        otherwise_edge = None
        for edge in edges:
            if edge.condition is None:
                # Unconditional edge — return immediately
                return edge.target
            if edge.condition.type == "otherwise":
                otherwise_edge = edge
                continue
            if edge.condition.evaluate(self._context):
                return edge.target

        # Fall back to otherwise
        if otherwise_edge is not None:
            return otherwise_edge.target

        msg = f"No valid transition from node '{node_id}'"
        raise NoValidTransitionError(msg)

    def _execute_function(self, node: Any) -> None:
        """Execute a function node synchronously."""
        config = node.config
        action = config.get("action", "")
        if action == "set_context":
            values = config.get("values", {})
            self._context.set(node.id, values)
