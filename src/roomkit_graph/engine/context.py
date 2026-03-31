from __future__ import annotations

import copy
from typing import Any


class WorkflowContext:
    """Accumulates outputs from each node during workflow execution.

    Structure: {node_id: {"output": <result>}, ...}
    Readable via dot-notation paths: "triage.output.severity"
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def set(self, node_id: str, output: Any) -> None:
        """Store a node's output."""
        self._data[node_id] = {"output": output}

    def get(self, path: str, default: Any = None) -> Any:
        """Get a value by dot-notation path (e.g. 'triage.output.severity')."""
        parts = path.split(".")
        current: Any = self._data
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        return current

    def has(self, path: str) -> bool:
        """Check if a path exists in the context."""
        sentinel = object()
        return self.get(path, sentinel) is not sentinel

    def to_dict(self) -> dict[str, Any]:
        """Return the full context as a deep-copied dict."""
        return copy.deepcopy(self._data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowContext:
        """Restore context from a dict."""
        ctx = cls()
        ctx._data = dict(data)
        return ctx
