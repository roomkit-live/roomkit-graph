from __future__ import annotations

import re
from typing import Any

from roomkit_graph.engine.context import WorkflowContext
from roomkit_graph.errors import TemplateError

_PLACEHOLDER = re.compile(r"\{\{(.+?)\}\}")


class TemplateResolver:
    """Resolves {{node_id.output.field}} templates against a WorkflowContext."""

    def __init__(self, context: WorkflowContext) -> None:
        self._context = context

    def resolve(self, template: str) -> str:
        """Resolve all {{...}} placeholders in a string template."""
        _missing = object()

        def _replace(match: re.Match[str]) -> str:
            path = match.group(1).strip()
            value = self._context.get(path, _missing)
            if value is _missing:
                msg = f"Template path not found: {path}"
                raise TemplateError(msg)
            return str(value)

        return _PLACEHOLDER.sub(_replace, template)

    def resolve_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively resolve templates in a dict structure."""
        return {k: self.resolve_value(v) for k, v in data.items()}

    def resolve_value(self, value: Any) -> Any:
        """Resolve templates in any value (str, dict, list, or passthrough)."""
        if isinstance(value, str):
            return self.resolve(value)
        if isinstance(value, dict):
            return self.resolve_dict(value)
        if isinstance(value, list):
            return [self.resolve_value(item) for item in value]
        return value
