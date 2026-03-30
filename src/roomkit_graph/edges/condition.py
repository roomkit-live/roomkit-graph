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
        return ConditionBuilder(path)

    @classmethod
    def otherwise(cls) -> Condition:
        """Default fallback edge — matches when no other condition does."""
        return cls(type="otherwise")

    @classmethod
    def all_(cls, *conditions: Condition) -> Condition:
        """All conditions must be true (AND)."""
        return cls(type="all", conditions=conditions)

    @classmethod
    def any_(cls, *conditions: Condition) -> Condition:
        """At least one condition must be true (OR)."""
        return cls(type="any", conditions=conditions)

    @classmethod
    def not_(cls, condition: Condition) -> Condition:
        """Negate a condition."""
        return cls(type="not", conditions=(condition,))

    # --- Evaluation ---

    def evaluate(self, context: WorkflowContext) -> bool:
        """Evaluate this condition against a WorkflowContext."""
        return self._evaluate_value(lambda path: context.get(path, _MISSING))

    def evaluate_dict(self, context: dict[str, Any]) -> bool:
        """Evaluate against a raw dict. Missing paths return False (not error)."""
        return self._evaluate_value(lambda path: _walk_dict(context, path))

    def _evaluate_value(self, resolve: Any) -> bool:
        """Core evaluation logic — resolve is a callable that maps path → value."""
        if self.type == "otherwise":
            return True
        if self.type == "all":
            return all(c._evaluate_value(resolve) for c in self.conditions)
        if self.type == "any":
            return any(c._evaluate_value(resolve) for c in self.conditions)
        if self.type == "not":
            return not self.conditions[0]._evaluate_value(resolve)
        if self.type == "field":
            return self._evaluate_field(resolve)
        return False

    def _evaluate_field(self, resolve: Any) -> bool:
        """Evaluate a field condition against a resolved value."""
        value = resolve(self.path) if self.path else _MISSING
        if value is _MISSING:
            return False
        if self.op == "eq":
            return value == self.value
        if self.op == "neq":
            return value != self.value
        if self.op == "in":
            return value in self.value
        if self.op == "not_in":
            return value not in self.value
        if self.op == "contains":
            return self.value in str(value)
        if self.op == "gt":
            return value > self.value
        if self.op == "lt":
            return value < self.value
        return self.op == "exists"

    # --- Serialization ---

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        data: dict[str, Any] = {"type": self.type}
        if self.type == "field":
            data["path"] = self.path
            data["op"] = self.op
            data["value"] = self.value
        elif self.type in ("all", "any", "not"):
            data["conditions"] = [c.to_dict() for c in self.conditions]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Condition:
        """Deserialize from a dict."""
        ctype = data["type"]
        if ctype == "field":
            return cls(type="field", path=data["path"], op=data["op"], value=data.get("value"))
        if ctype == "otherwise":
            return cls(type="otherwise")
        if ctype in ("all", "any", "not"):
            children = tuple(cls.from_dict(c) for c in data.get("conditions", []))
            return cls(type=ctype, conditions=children)
        return cls(type=ctype)


_MISSING = object()


def _walk_dict(data: dict[str, Any], path: str) -> Any:
    """Walk a nested dict by dot-notation path. Returns _MISSING if not found."""
    parts = path.split(".")
    current: Any = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return _MISSING
    return current


class ConditionBuilder:
    """Fluent builder for field conditions: Condition.field("path").equals("value")."""

    def __init__(self, path: str) -> None:
        self._path = path

    def _build(self, op: str, value: Any = None) -> Condition:
        return Condition(type="field", path=self._path, op=op, value=value)

    def equals(self, value: Any) -> Condition:
        return self._build("eq", value)

    def not_equals(self, value: Any) -> Condition:
        return self._build("neq", value)

    def in_(self, values: list[Any]) -> Condition:
        return self._build("in", values)

    def not_in(self, values: list[Any]) -> Condition:
        return self._build("not_in", values)

    def contains(self, value: str) -> Condition:
        return self._build("contains", value)

    def gt(self, value: int | float) -> Condition:
        return self._build("gt", value)

    def lt(self, value: int | float) -> Condition:
        return self._build("lt", value)

    def exists(self) -> Condition:
        return self._build("exists")
