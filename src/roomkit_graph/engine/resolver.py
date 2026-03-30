from __future__ import annotations

from typing import Any

from roomkit_graph.engine.context import WorkflowContext


class TemplateResolver:
    """Resolves {{node_id.output.field}} templates against a WorkflowContext."""

    def __init__(self, context: WorkflowContext) -> None:
        self._context = context

    def resolve(self, template: str) -> str:
        """Resolve all {{...}} placeholders in a string template."""
        raise NotImplementedError

    def resolve_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively resolve templates in a dict structure."""
        raise NotImplementedError

    def resolve_value(self, value: Any) -> Any:
        """Resolve templates in any value (str, dict, list, or passthrough)."""
        raise NotImplementedError
