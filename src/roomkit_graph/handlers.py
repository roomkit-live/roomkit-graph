from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from roomkit_graph.engine.executor import WorkflowEngine
    from roomkit_graph.nodes.base import Node

from roomkit_graph.engine.context import WorkflowContext


@dataclass
class NodeResult:
    """Result of executing a single node."""

    output: Any = None
    status: str = "completed"  # completed, failed, waiting
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StepResult:
    """Result of a single engine step (node execution + edge evaluation)."""

    node_id: str
    node_result: NodeResult
    next_node_id: str | None = None
    advanced: bool = True  # False if workflow complete or waiting


class NodeHandler(ABC):
    """Interface for executing a specific node type.

    Implement this to provide app-specific execution logic.
    roomkit-graph provides built-in handlers for start, end, and function nodes.
    Consumer apps (e.g. Luge) provide handlers for agent, orchestration,
    notification, human, and other app-specific node types.
    """

    @abstractmethod
    async def execute(
        self,
        node: Node,
        context: WorkflowContext,
        engine: WorkflowEngine,
    ) -> NodeResult:
        """Execute a node and return the result.

        Args:
            node: The node to execute (has id, type, config).
            context: The workflow context with all previous node outputs.
            engine: The workflow engine (for accessing graph, template resolver, etc.).

        Returns:
            NodeResult with output (stored in context), status, and optional error.
            Return status="waiting" for nodes that pause (human input, approval).
        """


class StartHandler(NodeHandler):
    """Built-in handler for start nodes. Trigger data is already in context."""

    async def execute(
        self, node: Node, context: WorkflowContext, engine: WorkflowEngine
    ) -> NodeResult:
        return NodeResult(output=context.get("start.output"), status="completed")


class EndHandler(NodeHandler):
    """Built-in handler for end nodes. Marks workflow as complete."""

    async def execute(
        self, node: Node, context: WorkflowContext, engine: WorkflowEngine
    ) -> NodeResult:
        return NodeResult(output=None, status="completed")


class FunctionHandler(NodeHandler):
    """Built-in handler for function nodes.

    Supports built-in actions:
    - set_context: Write values to workflow context
    - delay: Wait (no-op in base implementation, override for real delays)

    Override or extend for app-specific actions (http_request, custom, etc.).
    """

    async def execute(
        self, node: Node, context: WorkflowContext, engine: WorkflowEngine
    ) -> NodeResult:
        config = node.config
        action = config.get("action", "")

        if action == "set_context":
            return NodeResult(output=config.get("values", {}), status="completed")

        if action == "delay":
            return NodeResult(output={"delayed": config.get("duration", "0s")}, status="completed")

        if action == "json_transform" and engine.template_resolver:
            template = config.get("template", {})
            resolved = engine.template_resolver.resolve_value(template)
            return NodeResult(output=resolved, status="completed")

        return NodeResult(
            output=None,
            status="failed",
            error=f"Unknown function action: {action}",
        )
