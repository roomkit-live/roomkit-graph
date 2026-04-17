from __future__ import annotations

import copy
from typing import Any


class WorkflowContext:
    """Accumulates outputs from each node during workflow execution.

    Structure: {node_id: {"output": <result>}, ...}
    Readable via dot-notation paths: "triage.output.severity"

    A transient write journal (``_writes``) records node_ids written since
    the last ``drain_writes()`` call. Streaming observers use it to compute
    per-step deltas in O(writes) instead of snapshotting the full context.
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._writes: list[str] = []

    def set(self, node_id: str, output: Any) -> None:
        """Store a node's output and record the write in the journal."""
        self._data[node_id] = {"output": output}
        self._writes.append(node_id)

    def drain_writes(self) -> list[str]:
        """Return node_ids written since the last drain, clearing the journal.

        Safe to call when no writes have occurred — returns an empty list.
        The journal is transient and not part of to_dict/from_dict.

        Note: tracks writes only. ``WorkflowContext`` has no delete API, so
        observers of the journal can assume keys are added or overwritten,
        never removed. If deletion is ever introduced, observers relying on
        the journal for deltas will need updating.
        """
        writes = self._writes
        self._writes = []
        return writes

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
        ctx._data = copy.deepcopy(data)
        return ctx
