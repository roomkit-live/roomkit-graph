from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class NodeType(StrEnum):
    START = "start"
    END = "end"
    AGENT = "agent"
    ORCHESTRATION = "orchestration"
    HUMAN = "human"
    NOTIFICATION = "notification"
    FUNCTION = "function"
    PARALLEL = "parallel"
    CONDITION = "condition"
    SWITCH = "switch"


@dataclass
class Node:
    """A step in a workflow graph."""

    id: str
    type: NodeType | str
    config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    parent: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.type, str):
            with contextlib.suppress(ValueError):
                self.type = NodeType(self.type)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        type_val = self.type.value if isinstance(self.type, NodeType) else self.type
        data: dict[str, Any] = {"id": self.id, "type": type_val}
        if self.config:
            data["config"] = self.config
        if self.metadata:
            data["metadata"] = self.metadata
        if self.parent is not None:
            data["parent"] = self.parent
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Node:
        """Deserialize from a dict."""
        return cls(
            id=data["id"],
            type=data["type"],
            config=data.get("config", {}),
            metadata=data.get("metadata", {}),
            parent=data.get("parent"),
        )
