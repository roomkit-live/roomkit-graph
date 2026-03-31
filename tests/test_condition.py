"""Tests for Condition — builder API, evaluation, serialization."""

from __future__ import annotations

import pytest

from roomkit_graph import Condition, ConditionError, WorkflowContext

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


# --- Evaluation with WorkflowContext ---


def _ctx(**nodes: dict) -> WorkflowContext:
    """Helper: build context with node outputs."""
    ctx = WorkflowContext()
    for node_id, output in nodes.items():
        ctx.set(node_id, output)
    return ctx


def test_evaluate_eq_true():
    cond = Condition.field("triage.output.severity").equals("critical")
    ctx = _ctx(triage={"severity": "critical"})

    assert cond.evaluate(ctx) is True


def test_evaluate_eq_false():
    cond = Condition.field("triage.output.severity").equals("critical")
    ctx = _ctx(triage={"severity": "low"})

    assert cond.evaluate(ctx) is False


def test_evaluate_in_true():
    cond = Condition.field("review.output.status").in_(["approved", "accepted"])
    ctx = _ctx(review={"status": "approved"})

    assert cond.evaluate(ctx) is True


def test_evaluate_in_false():
    cond = Condition.field("review.output.status").in_(["approved", "accepted"])
    ctx = _ctx(review={"status": "rejected"})

    assert cond.evaluate(ctx) is False


def test_evaluate_contains_true():
    cond = Condition.field("triage.output.tags").contains("urgent")
    ctx = _ctx(triage={"tags": "urgent-fix-needed"})

    assert cond.evaluate(ctx) is True


def test_evaluate_gt_true():
    cond = Condition.field("extract.output.amount").gt(100)
    ctx = _ctx(extract={"amount": 250})

    assert cond.evaluate(ctx) is True


def test_evaluate_lt_true():
    cond = Condition.field("extract.output.score").lt(50)
    ctx = _ctx(extract={"score": 30})

    assert cond.evaluate(ctx) is True


def test_evaluate_exists_true():
    cond = Condition.field("extract.output.email").exists()
    ctx = _ctx(extract={"email": "test@example.com"})

    assert cond.evaluate(ctx) is True


def test_evaluate_exists_false():
    cond = Condition.field("extract.output.email").exists()
    ctx = _ctx(extract={"name": "test"})

    assert cond.evaluate(ctx) is False


def test_evaluate_otherwise_always_true():
    cond = Condition.otherwise()
    assert cond.evaluate(WorkflowContext()) is True
    assert cond.evaluate(_ctx(any={"thing": True})) is True


def test_evaluate_all_true():
    cond = Condition.all_(
        Condition.field("triage.output.severity").equals("critical"),
        Condition.field("triage.output.team").equals("backend"),
    )
    ctx = _ctx(triage={"severity": "critical", "team": "backend"})

    assert cond.evaluate(ctx) is True


def test_evaluate_all_false():
    cond = Condition.all_(
        Condition.field("triage.output.severity").equals("critical"),
        Condition.field("triage.output.team").equals("backend"),
    )
    ctx = _ctx(triage={"severity": "critical", "team": "frontend"})

    assert cond.evaluate(ctx) is False


def test_evaluate_any_true():
    cond = Condition.any_(
        Condition.field("triage.output.priority").equals("P1"),
        Condition.field("triage.output.escalated").equals(True),
    )
    ctx = _ctx(triage={"priority": "P2", "escalated": True})

    assert cond.evaluate(ctx) is True


def test_evaluate_not_true():
    cond = Condition.not_(Condition.field("review.output.status").equals("closed"))
    ctx = _ctx(review={"status": "open"})

    assert cond.evaluate(ctx) is True


def test_evaluate_not_false():
    cond = Condition.not_(Condition.field("review.output.status").equals("closed"))
    ctx = _ctx(review={"status": "closed"})

    assert cond.evaluate(ctx) is False


def test_evaluate_missing_path_returns_false():
    cond = Condition.field("nonexistent.output.path").equals("value")
    ctx = _ctx(other={"data": True})

    assert cond.evaluate(ctx) is False


# --- evaluate_dict (standalone, raw dict) ---


def test_evaluate_dict_eq():
    cond = Condition.field("severity").equals("critical")
    assert cond.evaluate_dict({"severity": "critical"}) is True
    assert cond.evaluate_dict({"severity": "low"}) is False


def test_evaluate_dict_otherwise():
    cond = Condition.otherwise()
    assert cond.evaluate_dict({}) is True


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
    assert restored.to_dict() == data


# --- Unknown operator ---


def test_unknown_operator_raises_condition_error():
    """An unrecognized operator raises ConditionError, not silent False."""
    cond = Condition(type="field", path="x", op="gte", value=10)
    ctx = WorkflowContext()
    ctx.set("node", {"x": 20})

    # Evaluate against dict (evaluate_dict)
    with pytest.raises(ConditionError, match="Unknown condition operator: 'gte'"):
        cond.evaluate_dict({"x": 20})


def test_unknown_operator_raises_with_context():
    """Unknown operator raises ConditionError against WorkflowContext too."""
    cond = Condition(type="field", path="node.output.val", op="lte", value=5)
    ctx = WorkflowContext()
    ctx.set("node", {"val": 3})

    with pytest.raises(ConditionError, match="Unknown condition operator: 'lte'"):
        cond.evaluate(ctx)
