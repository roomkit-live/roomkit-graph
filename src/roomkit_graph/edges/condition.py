from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from roomkit_graph.engine.context import WorkflowContext


@dataclass(frozen=True)
class Condition:
    """Serializable condition for edge routing.

    Conditions are data, not code — they round-trip through dict/JSON
    for DB storage and UI builders.
    """

    type: str  # "field", "otherwise", "all", "any", "not"
    path: str | None = None
    op: str | None = None  # "eq", "neq", "in", "not_in", "contains", "gt", "lt", "exists"
    value: Any = None
    conditions: tuple[Condition, ...] = field(default_factory=tuple)

    # --- Builder API ---

    @classmethod
    def field(cls, path: str) -> ConditionBuilder:
        """Start building a field condition: Condition.field("node.output.x").equals("y")."""
        raise NotImplementedError

    @classmethod
    def otherwise(cls) -> Condition:
        """Default fallback edge — matches when no other condition does."""
        raise NotImplementedError

    @classmethod
    def all_(cls, *conditions: Condition) -> Condition:
        """All conditions must be true (AND)."""
        raise NotImplementedError

    @classmethod
    def any_(cls, *conditions: Condition) -> Condition:
        """At least one condition must be true (OR)."""
        raise NotImplementedError

    @classmethod
    def not_(cls, condition: Condition) -> Condition:
        """Negate a condition."""
        raise NotImplementedError

    # --- Evaluation ---

    def evaluate(self, context: WorkflowContext) -> bool:
        """Evaluate this condition against a WorkflowContext."""
        raise NotImplementedError

    def evaluate_dict(self, context: dict[str, Any]) -> bool:
        """Evaluate this condition against a raw dict (for standalone use)."""
        raise NotImplementedError

    # --- Serialization ---

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Condition:
        """Deserialize from a dict."""
        raise NotImplementedError


class ConditionBuilder:
    """Fluent builder for field conditions: Condition.field("path").equals("value")."""

    def __init__(self, path: str) -> None:
        self._path = path

    def equals(self, value: Any) -> Condition:
        raise NotImplementedError

    def not_equals(self, value: Any) -> Condition:
        raise NotImplementedError

    def in_(self, values: list[Any]) -> Condition:
        raise NotImplementedError

    def not_in(self, values: list[Any]) -> Condition:
        raise NotImplementedError

    def contains(self, value: str) -> Condition:
        raise NotImplementedError

    def gt(self, value: int | float) -> Condition:
        raise NotImplementedError

    def lt(self, value: int | float) -> Condition:
        raise NotImplementedError

    def exists(self) -> Condition:
        raise NotImplementedError
