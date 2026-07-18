from __future__ import annotations

import copy
from typing import Any


class WorkflowContext:
    """Accumulates outputs from each node during workflow execution.

    Structure: ``{node_id: {"output": <result>}, ...}``, readable via
    dot-notation paths: ``"triage.output.severity"``.

    On top of that raw layout, ``get`` understands three **reserved scope
    prefixes** so templates (``{{...}}``) and edge conditions share one
    resolution point:

    - ``input.<...>``      — the "current input" the engine sets before each
      node runs (its predecessor's output) and before evaluating a node's
      outgoing edges (that node's own output). See ``set_current_input``.
    - ``steps.<id>.<...>`` — a node's stored **output** directly (no ``output``
      hop). ``steps.start`` is the unwrapped trigger payload.
    - ``trigger.<...>``    — alias for ``steps.start``.

    A node literally named ``input``/``steps``/``trigger`` is shadowed by these
    reserved prefixes.

    A transient write journal (``_writes``) records node_ids written since
    the last ``drain_writes()`` call. Streaming observers use it to compute
    per-step deltas in O(writes) instead of snapshotting the full context.
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._writes: list[str] = []
        # Transient scope for ``input.*`` paths — set by the engine per step,
        # derived from ``_data``, and therefore not serialized (like _writes).
        self._current_input: Any = None

    def set(self, node_id: str, output: Any) -> None:
        """Store a node's output and record the write in the journal."""
        self._data[node_id] = {"output": output}
        self._writes.append(node_id)

    def set_current_input(self, value: Any) -> None:
        """Set the scope that ``input.*`` paths resolve against.

        The engine calls this with the unwrapped output of a node's
        predecessor(s) before running it, and with a node's own output before
        evaluating that node's outgoing edges.
        """
        self._current_input = value

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
        """Get a value by dot-notation path (e.g. 'triage.output.severity').

        Paths starting with a reserved scope prefix (``input``/``steps``/
        ``trigger``) resolve against that scope; all others walk the raw
        ``{node_id: {"output": ...}}`` layout for backward compatibility.
        """
        parts = path.split(".")
        resolver = self._SCOPE_RESOLVERS.get(parts[0])
        if resolver is not None:
            return resolver(self, parts, default)
        return self._walk(self._data, parts, default)

    def has(self, path: str) -> bool:
        """Check if a path exists in the context."""
        sentinel = object()
        return self.get(path, sentinel) is not sentinel

    # --- Reserved scope resolvers (dispatched by get) ---

    def _resolve_input(self, parts: list[str], default: Any) -> Any:
        return self._walk(self._current_input, parts[1:], default)

    def _resolve_trigger(self, parts: list[str], default: Any) -> Any:
        return self._walk(self._trigger_payload(), parts[1:], default)

    def _resolve_steps(self, parts: list[str], default: Any) -> Any:
        rest = parts[1:]
        if not rest:
            return default
        node_id, sub = rest[0], rest[1:]
        if node_id == "start":
            return self._walk(self._trigger_payload(), sub, default)
        entry = self._data.get(node_id)
        if not isinstance(entry, dict):
            return default
        return self._walk(entry.get("output"), sub, default)

    def _trigger_payload(self) -> Any:
        """The unwrapped trigger data.

        The engine stores ``start.output`` as ``{"input": <trigger>}``; the
        ``trigger`` / ``steps.start`` scopes expose ``<trigger>`` directly.
        """
        return self._walk(self._data, ["start", "output", "input"], None)

    @staticmethod
    def _walk(root: Any, parts: list[str], default: Any) -> Any:
        """Walk ``root`` by dot-notation ``parts``; return ``default`` if absent."""
        current = root
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        return current

    _SCOPE_RESOLVERS = {
        "input": _resolve_input,
        "trigger": _resolve_trigger,
        "steps": _resolve_steps,
    }

    # --- Serialization ---

    def to_dict(self) -> dict[str, Any]:
        """Return the full context as a deep-copied dict."""
        return copy.deepcopy(self._data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowContext:
        """Restore context from a dict."""
        ctx = cls()
        ctx._data = copy.deepcopy(data)
        return ctx
