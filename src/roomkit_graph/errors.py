from __future__ import annotations


class GraphError(Exception):
    """Base exception for roomkit-graph."""


class GraphValidationError(GraphError):
    """Graph definition is invalid."""


class ConditionError(GraphError):
    """Condition evaluation failed."""


class TemplateError(GraphError):
    """Template resolution failed."""


class ExecutionError(GraphError):
    """Workflow execution failed."""


class NoValidTransitionError(ExecutionError):
    """No outgoing edge matched after node completion."""
