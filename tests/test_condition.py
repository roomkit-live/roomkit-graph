"""Tests for Condition — builder API, evaluation, serialization."""

from __future__ import annotations

import pytest

from roomkit_graph import Condition


# --- Builder API ---


def test_field_equals():
    cond = Condition.field("triage.output.severity").equals("critical")

    assert cond.type == "field"
    assert cond.path == "triage.output.severity"
    assert cond.op == "eq"
    assert cond.value == "critical"


def test_field_not_equals():
    cond = Condition.field("status").not_equals("closed")

    assert cond.type == "field"
    assert cond.op == "neq"
    assert cond.value == "closed"


def test_field_in():
    cond = Condition.field("severity").in_(["high", "critical"])

    assert cond.type == "field"
    assert cond.op == "in"
    assert cond.value == ["high", "critical"]


def test_field_not_in():
    cond = Condition.field("status").not_in(["draft", "archived"])

    assert cond.op == "not_in"


def test_field_contains():
    cond = Condition.field("tags").contains("urgent")

    assert cond.op == "contains"
    assert cond.value == "urgent"


def test_field_gt():
    cond = Condition.field("amount").gt(1000)

    assert cond.op == "gt"
    assert cond.value == 1000


def test_field_lt():
    cond = Condition.field("score").lt(50)

    assert cond.op == "lt"
    assert cond.value == 50


def test_field_exists():
    cond = Condition.field("manager_email").exists()

    assert cond.op == "exists"


def test_otherwise():
    cond = Condition.otherwise()

    assert cond.type == "otherwise"


def test_all():
    c1 = Condition.field("severity").equals("critical")
    c2 = Condition.field("team").equals("backend")
    cond = Condition.all_(c1, c2)

    assert cond.type == "all"
    assert len(cond.conditions) == 2


def test_any():
    c1 = Condition.field("priority").equals("P1")
    c2 = Condition.field("escalated").equals(True)
    cond = Condition.any_(c1, c2)

    assert cond.type == "any"
    assert len(cond.conditions) == 2


def test_not():
    inner = Condition.field("status").equals("closed")
    cond = Condition.not_(inner)

    assert cond.type == "not"
    assert len(cond.conditions) == 1


# --- Evaluation ---


def test_evaluate_eq_true():
    cond = Condition.field("triage.output.severity").equals("critical")
    ctx = {"triage": {"output": {"severity": "critical"}}}

    assert cond.evaluate(ctx) is True


def test_evaluate_eq_false():
    cond = Condition.field("triage.output.severity").equals("critical")
    ctx = {"triage": {"output": {"severity": "low"}}}

    assert cond.evaluate(ctx) is False


def test_evaluate_in_true():
    cond = Condition.field("status").in_(["approved", "accepted"])
    ctx = {"status": "approved"}

    assert cond.evaluate(ctx) is True


def test_evaluate_in_false():
    cond = Condition.field("status").in_(["approved", "accepted"])
    ctx = {"status": "rejected"}

    assert cond.evaluate(ctx) is False


def test_evaluate_contains_true():
    cond = Condition.field("tags").contains("urgent")
    ctx = {"tags": "urgent-fix-needed"}

    assert cond.evaluate(ctx) is True


def test_evaluate_gt_true():
    cond = Condition.field("amount").gt(100)
    ctx = {"amount": 250}

    assert cond.evaluate(ctx) is True


def test_evaluate_lt_true():
    cond = Condition.field("score").lt(50)
    ctx = {"score": 30}

    assert cond.evaluate(ctx) is True


def test_evaluate_exists_true():
    cond = Condition.field("email").exists()
    ctx = {"email": "test@example.com"}

    assert cond.evaluate(ctx) is True


def test_evaluate_exists_false():
    cond = Condition.field("email").exists()
    ctx = {"name": "test"}

    assert cond.evaluate(ctx) is False


def test_evaluate_otherwise_always_true():
    cond = Condition.otherwise()
    assert cond.evaluate({}) is True
    assert cond.evaluate({"any": "thing"}) is True


def test_evaluate_all_true():
    cond = Condition.all_(
        Condition.field("severity").equals("critical"),
        Condition.field("team").equals("backend"),
    )
    ctx = {"severity": "critical", "team": "backend"}

    assert cond.evaluate(ctx) is True


def test_evaluate_all_false():
    cond = Condition.all_(
        Condition.field("severity").equals("critical"),
        Condition.field("team").equals("backend"),
    )
    ctx = {"severity": "critical", "team": "frontend"}

    assert cond.evaluate(ctx) is False


def test_evaluate_any_true():
    cond = Condition.any_(
        Condition.field("priority").equals("P1"),
        Condition.field("escalated").equals(True),
    )
    ctx = {"priority": "P2", "escalated": True}

    assert cond.evaluate(ctx) is True


def test_evaluate_not_true():
    cond = Condition.not_(Condition.field("status").equals("closed"))
    ctx = {"status": "open"}

    assert cond.evaluate(ctx) is True


def test_evaluate_not_false():
    cond = Condition.not_(Condition.field("status").equals("closed"))
    ctx = {"status": "closed"}

    assert cond.evaluate(ctx) is False


def test_evaluate_missing_path_returns_false():
    cond = Condition.field("nonexistent.path").equals("value")
    ctx = {"other": "data"}

    assert cond.evaluate(ctx) is False


# --- Serialization ---


def test_field_condition_to_dict():
    cond = Condition.field("severity").equals("critical")
    data = cond.to_dict()

    assert data == {"type": "field", "path": "severity", "op": "eq", "value": "critical"}


def test_otherwise_to_dict():
    cond = Condition.otherwise()
    data = cond.to_dict()

    assert data == {"type": "otherwise"}


def test_composite_to_dict():
    cond = Condition.all_(
        Condition.field("a").equals(1),
        Condition.field("b").gt(10),
    )
    data = cond.to_dict()

    assert data["type"] == "all"
    assert len(data["conditions"]) == 2
    assert data["conditions"][0]["path"] == "a"
    assert data["conditions"][1]["op"] == "gt"


def test_condition_from_dict_field():
    data = {"type": "field", "path": "severity", "op": "eq", "value": "critical"}
    cond = Condition.from_dict(data)

    assert cond.type == "field"
    assert cond.path == "severity"
    assert cond.op == "eq"
    assert cond.value == "critical"


def test_condition_from_dict_otherwise():
    cond = Condition.from_dict({"type": "otherwise"})
    assert cond.type == "otherwise"


def test_condition_from_dict_composite():
    data = {
        "type": "all",
        "conditions": [
            {"type": "field", "path": "a", "op": "eq", "value": 1},
            {"type": "field", "path": "b", "op": "gt", "value": 10},
        ],
    }
    cond = Condition.from_dict(data)

    assert cond.type == "all"
    assert len(cond.conditions) == 2


def test_condition_round_trip():
    original = Condition.all_(
        Condition.field("severity").in_(["critical", "high"]),
        Condition.not_(Condition.field("status").equals("closed")),
    )

    data = original.to_dict()
    restored = Condition.from_dict(data)

    assert restored.type == original.type
    assert len(restored.conditions) == len(original.conditions)
    # Structural equality
    assert restored.to_dict() == data
