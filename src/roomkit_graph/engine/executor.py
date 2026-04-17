from __future__ import annotations

from typing import TYPE_CHECKING, Any

from roomkit_graph.engine.context import WorkflowContext
from roomkit_graph.engine.resolver import TemplateResolver
from roomkit_graph.engine.streaming import _StreamingMixin
from roomkit_graph.errors import ExecutionError, NoValidTransitionError
from roomkit_graph.handlers import (
    ConditionHandler,
    EndHandler,
    FunctionHandler,
    LogHandler,
    NodeHandler,
    ParallelHandler,
    StartHandler,
    SwitchHandler,
)
from roomkit_graph.nodes.base import NodeType

if TYPE_CHECKING:
    from roomkit_graph.graph import Graph


# Built-in handlers for generic node types
_BUILTIN_HANDLERS: dict[NodeType, NodeHandler] = {
    NodeType.START: StartHandler(),
    NodeType.END: EndHandler(),
    NodeType.FUNCTION: FunctionHandler(),
    NodeType.CONDITION: ConditionHandler(),
    NodeType.SWITCH: SwitchHandler(),
    NodeType.LOG: LogHandler(),
    NodeType.PARALLEL: ParallelHandler(),
}


class WorkflowEngine(_StreamingMixin):
    """Workflow execution engine — drives a graph step by step.

    The engine manages the execution loop: start -> execute node -> evaluate edges
    -> next node -> end. Node execution is delegated to pluggable NodeHandlers.

    Built-in handlers cover start, end, and function nodes.
    Consumer apps provide handlers for agent, orchestration, notification, human, etc.

    Observer-side streaming (``stream()`` / ``emit()``) comes from
    ``_StreamingMixin``; see ``engine/streaming.py``.
    """

    def __init__(
        self,
        graph: Graph,
        handlers: dict[NodeType | str, NodeHandler] | None = None,
        context: WorkflowContext | None = None,
    ) -> None:
        self._graph = graph
        self._context = context or WorkflowContext()
        self._handlers: dict[NodeType | str, NodeHandler] = {**_BUILTIN_HANDLERS}
        if handlers:
            self._handlers.update(handlers)
        self._current: str | None = None
        self._waiting: bool = False
        self._template_resolver: TemplateResolver | None = None

    @property
    def graph(self) -> Graph:
        return self._graph

    @property
    def context(self) -> WorkflowContext:
        return self._context

    @property
    def current_node_id(self) -> str | None:
        """The node currently being executed, or None if not started / completed."""
        return self._current

    @property
    def template_resolver(self) -> TemplateResolver | None:
        """Template resolver bound to current context. Created lazily."""
        if self._template_resolver is None:
            self._template_resolver = TemplateResolver(self._context)
        return self._template_resolver

    def get_handler(self, node_type: NodeType | str) -> NodeHandler | None:
        """Look up the handler for a node type."""
        return self._handlers.get(node_type)

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
        Raises ExecutionError if a handler fails or no handler is registered.
        """
        if self._current is None:
            return False

        node = self._graph.get_node(self._current)

        # End node — workflow complete
        if node.type == NodeType.END:
            handler = self.get_handler(NodeType.END)
            if handler:
                await handler.execute(node, self._context, self)
            self._current = None
            return False

        # If waiting for external input (human node), don't advance
        if self._waiting:
            return False

        # Execute node via handler
        handler = self.get_handler(node.type)
        if handler is None:
            msg = f"No handler registered for node type '{node.type}'"
            raise ExecutionError(msg)

        result = await handler.execute(node, self._context, self)

        # Store output in context
        if result.output is not None:
            self._context.set(node.id, result.output)

        # If node is waiting (human input, approval), pause
        if result.status == "waiting":
            self._waiting = True
            return True

        # If node failed, raise
        if result.status == "failed":
            msg = f"Node '{node.id}' failed: {result.error or 'unknown error'}"
            raise ExecutionError(msg)

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
        """Resume a paused workflow (e.g. after human input) with external data.

        Stores the input in context as the node's output, clears the waiting flag,
        and advances past the waiting node by evaluating outgoing edges.
        """
        self._context.set(node_id, input_data)
        self._waiting = False
        # Advance past the waiting node
        if self._current == node_id:
            next_id = self.evaluate_edges(node_id)
            if next_id is not None:
                self._current = next_id

    def evaluate_edges(self, node_id: str) -> str | None:
        """Evaluate outgoing edges and return the next node ID, or None.

        Resolution order (first-match-wins):

        1. **Conditional edges** are evaluated in definition order (the order
           they were added to the graph). The *first* edge whose condition
           evaluates to True wins — remaining conditionals are skipped.
        2. **Unconditional edge** (no condition) is used as a default path
           when no conditional edge matched.
        3. **Otherwise edge** (condition.type == "otherwise") is the explicit
           catch-all fallback.

        If none of the above produce a target, raises NoValidTransitionError.

        Args:
            node_id: The source node whose outgoing edges to evaluate.

        Returns:
            The ID of the next node, or None if the node has no outgoing edges.
        """
        edges = self._graph.get_outgoing_edges(node_id)
        if not edges:
            return None

        # Separate edge types and evaluate conditionals first
        otherwise_edge = None
        unconditional_edge = None
        for edge in edges:
            if edge.condition is None:
                unconditional_edge = edge
                continue
            if edge.condition.type == "otherwise":
                otherwise_edge = edge
                continue
            if edge.condition.evaluate(self._context):
                return edge.target

        # Unconditional fallback (default path when no condition matched)
        if unconditional_edge is not None:
            return unconditional_edge.target

        # Otherwise fallback (explicit catch-all)
        if otherwise_edge is not None:
            return otherwise_edge.target

        msg = f"No valid transition from node '{node_id}'"
        raise NoValidTransitionError(msg)

    # --- Serialization ---

    def to_dict(self) -> dict[str, Any]:
        """Serialize engine state for persistence (pause/resume across processes)."""
        return {
            "context": self._context.to_dict(),
            "current_node_id": self._current,
            "waiting": self._waiting,
        }

    @classmethod
    def from_dict(
        cls,
        graph: Graph,
        data: dict[str, Any],
        handlers: dict[NodeType | str, NodeHandler] | None = None,
    ) -> WorkflowEngine:
        """Restore engine from serialized state."""
        ctx = WorkflowContext.from_dict(data["context"])
        engine = cls(graph, handlers=handlers, context=ctx)
        engine._current = data.get("current_node_id")
        engine._waiting = data.get("waiting", False)
        return engine
