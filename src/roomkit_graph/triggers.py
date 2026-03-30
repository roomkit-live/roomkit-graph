from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_TRIGGER_REGISTRY: dict[str, type[Trigger]] = {}


@dataclass(frozen=True)
class Trigger:
    """Base trigger — how a workflow is started."""

    type: str = ""
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {"type": self.type, **{k: v for k, v in self._extra_fields().items()}}

    def _extra_fields(self) -> dict[str, Any]:
        """Subclass-specific fields for serialization."""
        return {}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Trigger:
        """Deserialize from a dict. Dispatches to the correct subclass."""
        trigger_type = data.get("type", "")
        trigger_cls = _TRIGGER_REGISTRY.get(trigger_type, cls)
        return trigger_cls._from_dict_fields(data)

    @classmethod
    def _from_dict_fields(cls, data: dict[str, Any]) -> Trigger:
        """Reconstruct from dict fields. Override in subclasses."""
        return cls(type=data.get("type", ""), config=data.get("config", {}))

    def __init_subclass__(cls, trigger_type: str = "", **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if trigger_type:
            _TRIGGER_REGISTRY[trigger_type] = cls


@dataclass(frozen=True)
class WebhookTrigger(Trigger, trigger_type="webhook"):
    """Triggered by an inbound webhook."""

    source_type: str = "generic"

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", "webhook")

    def _extra_fields(self) -> dict[str, Any]:
        return {"source_type": self.source_type}

    @classmethod
    def _from_dict_fields(cls, data: dict[str, Any]) -> WebhookTrigger:
        return cls(source_type=data.get("source_type", "generic"), config=data.get("config", {}))


@dataclass(frozen=True)
class ScheduledTrigger(Trigger, trigger_type="scheduled"):
    """Triggered on a recurring schedule."""

    schedule: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", "scheduled")

    def _extra_fields(self) -> dict[str, Any]:
        return {"schedule": self.schedule}

    @classmethod
    def _from_dict_fields(cls, data: dict[str, Any]) -> ScheduledTrigger:
        return cls(schedule=data.get("schedule", {}), config=data.get("config", {}))


@dataclass(frozen=True)
class EventTrigger(Trigger, trigger_type="event"):
    """Triggered by an internal event."""

    event: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", "event")

    def _extra_fields(self) -> dict[str, Any]:
        return {"event": self.event}

    @classmethod
    def _from_dict_fields(cls, data: dict[str, Any]) -> EventTrigger:
        return cls(event=data.get("event", ""), config=data.get("config", {}))


@dataclass(frozen=True)
class ManualTrigger(Trigger, trigger_type="manual"):
    """Triggered manually by a user."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", "manual")

    @classmethod
    def _from_dict_fields(cls, data: dict[str, Any]) -> ManualTrigger:
        return cls(config=data.get("config", {}))
