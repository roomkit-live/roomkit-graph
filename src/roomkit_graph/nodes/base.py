from __future__ import annotations

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
            self.type = NodeType(self.type)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Node:
        """Deserialize from a dict."""
        raise NotImplementedError
