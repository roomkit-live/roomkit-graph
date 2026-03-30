"""Tests for Trigger types — construction, enforcement, serialization."""

from __future__ import annotations

from roomkit_graph import (
    EventTrigger,
    ManualTrigger,
    ScheduledTrigger,
    Trigger,
    WebhookTrigger,
)

# --- Type enforcement ---


def test_webhook_trigger_type_enforced():
    t = WebhookTrigger(source_type="github")
    assert t.type == "webhook"
    assert t.source_type == "github"


def test_webhook_trigger_defaults():
    t = WebhookTrigger()
    assert t.type == "webhook"
    assert t.source_type == "generic"


def test_scheduled_trigger_type_enforced():
    t = ScheduledTrigger(schedule={"recurrence_type": "daily"})
    assert t.type == "scheduled"
    assert t.schedule["recurrence_type"] == "daily"


def test_scheduled_trigger_defaults():
    t = ScheduledTrigger()
    assert t.type == "scheduled"
    assert t.schedule == {}


def test_event_trigger_type_enforced():
    t = EventTrigger(event="notetaker.completed")
    assert t.type == "event"
    assert t.event == "notetaker.completed"


def test_event_trigger_defaults():
    t = EventTrigger()
    assert t.type == "event"
    assert t.event == ""


def test_manual_trigger_type_enforced():
    t = ManualTrigger()
    assert t.type == "manual"


# --- Serialization ---


def test_webhook_trigger_to_dict():
    t = WebhookTrigger(source_type="github")
    data = t.to_dict()

    assert data["type"] == "webhook"
    assert data["source_type"] == "github"


def test_scheduled_trigger_to_dict():
    t = ScheduledTrigger(
        schedule={"recurrence_type": "weekly", "days": [1, 3, 5]},
    )
    data = t.to_dict()

    assert data["type"] == "scheduled"
    assert data["schedule"]["recurrence_type"] == "weekly"
    assert data["schedule"]["days"] == [1, 3, 5]


def test_event_trigger_to_dict():
    t = EventTrigger(event="job.completed")
    data = t.to_dict()

    assert data["type"] == "event"
    assert data["event"] == "job.completed"


def test_manual_trigger_to_dict():
    t = ManualTrigger()
    data = t.to_dict()

    assert data["type"] == "manual"


# --- Deserialization (factory dispatch) ---


def test_trigger_from_dict_webhook():
    data = {"type": "webhook", "source_type": "stripe"}
    t = Trigger.from_dict(data)

    assert isinstance(t, WebhookTrigger)
    assert t.source_type == "stripe"


def test_trigger_from_dict_scheduled():
    data = {"type": "scheduled", "schedule": {"recurrence_type": "daily"}}
    t = Trigger.from_dict(data)

    assert isinstance(t, ScheduledTrigger)
    assert t.schedule["recurrence_type"] == "daily"


def test_trigger_from_dict_event():
    data = {"type": "event", "event": "meeting.ended"}
    t = Trigger.from_dict(data)

    assert isinstance(t, EventTrigger)
    assert t.event == "meeting.ended"


def test_trigger_from_dict_manual():
    data = {"type": "manual"}
    t = Trigger.from_dict(data)

    assert isinstance(t, ManualTrigger)


# --- Round-trip ---


def test_webhook_trigger_round_trip():
    original = WebhookTrigger(source_type="hubspot")
    data = original.to_dict()
    restored = Trigger.from_dict(data)

    assert isinstance(restored, WebhookTrigger)
    assert restored.source_type == original.source_type
    assert restored.type == original.type


def test_scheduled_trigger_round_trip():
    original = ScheduledTrigger(
        schedule={"recurrence_type": "monthly", "day_of_month": 15},
    )
    data = original.to_dict()
    restored = Trigger.from_dict(data)

    assert isinstance(restored, ScheduledTrigger)
    assert restored.schedule == original.schedule
