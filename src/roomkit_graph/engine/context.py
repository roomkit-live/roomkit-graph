from __future__ import annotations

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
        raise NotImplementedError

    def get(self, path: str, default: Any = None) -> Any:
        """Get a value by dot-notation path (e.g. 'triage.output.severity')."""
        raise NotImplementedError

    def has(self, path: str) -> bool:
        """Check if a path exists in the context."""
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:
        """Return the full context as a dict."""
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowContext:
        """Restore context from a dict."""
        raise NotImplementedError
