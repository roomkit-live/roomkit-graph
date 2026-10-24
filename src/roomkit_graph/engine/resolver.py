from __future__ import annotations

import json
import re
from typing import Any

from roomkit_graph.engine.context import WorkflowContext
from roomkit_graph.errors import TemplateError

_PLACEHOLDER = re.compile(r"\{\{(.+?)\}\}")
# Matches a string that is exactly one {{path}} placeholder (with optional whitespace).
# Uses [^{}]+ to prevent matching "{{a}}{{b}}" as a single placeholder.
_EXACT_PLACEHOLDER = re.compile(r"\A\s*\{\{([^{}]+)\}\}\s*\Z")
# "path | default(<JSON value>)": the only filter a placeholder takes.
_DEFAULT = re.compile(r"\A(?P<path>[^|]+?)\s*\|\s*default\((?P<value>.*)\)\Z", re.DOTALL)

_MISSING = object()
_NO_DEFAULT = object()


def _split(expression: str) -> tuple[str, Any]:
    """The path a placeholder reads, and its default (``_NO_DEFAULT`` if none)."""
    expression = expression.strip()
    if "|" not in expression:
        return expression, _NO_DEFAULT
    match = _DEFAULT.match(expression)
    if match is None:
        msg = f"Unknown template filter in: {expression}"
        raise TemplateError(msg)
    try:
        default = json.loads(match["value"])
    except json.JSONDecodeError as exc:
        msg = (
            "default() takes a JSON value (a quoted string, number, true, false, null): "
            f"{match['value']}"
        )
        raise TemplateError(msg) from exc
    return match["path"].strip(), default


class TemplateResolver:
    """Resolves {{node_id.output.field}} templates against a WorkflowContext.

    A placeholder whose path may be missing names a stand-in with
    ``{{path | default("...")}}``; without one, a missing path raises
    ``TemplateError``.
    """

    def __init__(self, context: WorkflowContext) -> None:
        self._context = context

    def resolve(self, template: str) -> str:
        """Resolve all {{...}} placeholders in a string template.

        Always returns a string. For raw value passthrough when the
        template is a single placeholder, use resolve_value() instead.
        """
        return _PLACEHOLDER.sub(lambda match: str(self._lookup(match.group(1))), template)

    def resolve_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively resolve templates in a dict structure."""
        return {k: self.resolve_value(v) for k, v in data.items()}

    def resolve_value(self, value: Any) -> Any:
        """Resolve templates in any value (str, dict, list, or passthrough).

        When a string is exactly a single ``{{path}}`` placeholder with no
        surrounding text, returns the raw context value (dict, list, int, etc.)
        without stringifying. Mixed templates like ``"Count: {{path}}"`` still
        return a string via resolve().
        """
        if isinstance(value, str):
            match = _EXACT_PLACEHOLDER.fullmatch(value)
            if match:
                return self._lookup(match.group(1))
            return self.resolve(value)
        if isinstance(value, dict):
            return self.resolve_dict(value)
        if isinstance(value, list):
            return [self.resolve_value(item) for item in value]
        return value

    def _lookup(self, expression: str) -> Any:
        """The value a placeholder's expression names, or its default."""
        path, default = _split(expression)
        value = self._context.get(path, _MISSING)
        if value is not _MISSING:
            return value
        if default is not _NO_DEFAULT:
            return default
        msg = f"Template path not found: {path}"
        raise TemplateError(msg)
