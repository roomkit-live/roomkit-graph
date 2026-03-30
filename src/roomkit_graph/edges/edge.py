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
        data: dict[str, Any] = {"source": self.source, "target": self.target}
        if self.condition is not None:
            data["condition"] = self.condition.to_dict()
        if self.metadata:
            data["metadata"] = self.metadata
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Edge:
        """Deserialize from a dict."""
        condition = None
        if data.get("condition"):
            condition = Condition.from_dict(data["condition"])
        return cls(
            source=data["source"],
            target=data["target"],
            condition=condition,
            metadata=data.get("metadata", {}),
        )
