from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Trigger:
    """Base trigger — how a workflow is started."""

    type: str
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Trigger:
        """Deserialize from a dict."""
        raise NotImplementedError


@dataclass(frozen=True)
class WebhookTrigger(Trigger):
    """Triggered by an inbound webhook."""

    type: str = "webhook"
    source_type: str = "generic"


@dataclass(frozen=True)
class ScheduledTrigger(Trigger):
    """Triggered on a recurring schedule."""

    type: str = "scheduled"
    schedule: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EventTrigger(Trigger):
    """Triggered by an internal event."""

    type: str = "event"
    event: str = ""


@dataclass(frozen=True)
class ManualTrigger(Trigger):
    """Triggered manually by a user."""

    type: str = "manual"
