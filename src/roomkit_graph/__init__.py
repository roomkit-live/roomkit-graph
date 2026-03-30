from __future__ import annotations

from roomkit_graph._version import __version__
from roomkit_graph.edges.condition import Condition
from roomkit_graph.edges.edge import Edge
from roomkit_graph.engine.context import WorkflowContext
from roomkit_graph.engine.executor import WorkflowExecutor
from roomkit_graph.engine.resolver import TemplateResolver
from roomkit_graph.errors import (
    ConditionError,
    ExecutionError,
    GraphError,
    GraphValidationError,
    NoValidTransitionError,
    TemplateError,
)
from roomkit_graph.graph import Graph
from roomkit_graph.nodes.base import Node, NodeType
from roomkit_graph.orchestration import GraphOrchestration
from roomkit_graph.registry import FunctionRegistry
from roomkit_graph.triggers import (
    EventTrigger,
    ManualTrigger,
    ScheduledTrigger,
    Trigger,
    WebhookTrigger,
)

graph_registry = FunctionRegistry()
"""Module-level function registry for custom FunctionNode actions."""

__all__ = [
    "__version__",
    # Graph
    "Graph",
    # Nodes
    "Node",
    "NodeType",
    # Edges
    "Edge",
    "Condition",
    # Triggers
    "Trigger",
    "WebhookTrigger",
    "ScheduledTrigger",
    "EventTrigger",
    "ManualTrigger",
    # Engine
    "WorkflowContext",
    "WorkflowExecutor",
    "TemplateResolver",
    # Orchestration
    "GraphOrchestration",
    # Registry
    "FunctionRegistry",
    "graph_registry",
    # Errors
    "GraphError",
    "GraphValidationError",
    "ConditionError",
    "TemplateError",
    "ExecutionError",
    "NoValidTransitionError",
]
