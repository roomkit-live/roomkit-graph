from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from roomkit_graph.edges.condition import Condition


@dataclass(frozen=True)
class Edge:
    """Connection between two nodes in a workflow graph."""

    source: str
    target: str
    condition: Condition | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Edge:
        """Deserialize from a dict."""
        raise NotImplementedError
