"""Tests for full graph serialization — round-trip through dict and JSON."""

from __future__ import annotations

import json

from roomkit_graph import (
    Condition,
    Edge,
    Graph,
    ManualTrigger,
    Node,
    ScheduledTrigger,
    WebhookTrigger,
)


def _bug_triage_graph() -> Graph:
    """The bug triage example from the README."""
    g = Graph(
        id="bug-triage",
        name="Bug Triage",
        description="Triage incoming GitHub issues",
        trigger=WebhookTrigger(source_type="github"),
    )
    g.add_nodes(
        Node("start", type="start"),
        Node("triage", type="agent", config={"agent_id": "triage-agent"}),
        Node("escalate", type="notification", config={"channel": "slack", "template": "Critical!"}),
        Node("assign", type="agent", config={"agent_id": "labeler-agent"}),
        Node("end", type="end"),
    )
    g.add_edges(
        Edge("start", "triage"),
        Edge("triage", "escalate", Condition.field("triage.output.severity").equals("critical")),
        Edge("triage", "assign", Condition.otherwise()),
        Edge("escalate", "end"),
        Edge("assign", "end"),
    )
    return g


def _parallel_graph() -> Graph:
    """Graph with parallel node and children."""
    g = Graph(id="parallel", name="Parallel", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("checks", type="parallel", config={"join": "all"}),
        Node("sec", type="agent", config={"agent_id": "security"}, parent="checks"),
        Node("comp", type="agent", config={"agent_id": "compliance"}, parent="checks"),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "checks"), Edge("checks", "end"))
    return g


# --- Node serialization ---


def test_node_to_dict():
    node = Node("triage", type="agent", config={"agent_id": "a1"}, metadata={"label": "Triage"})
    data = node.to_dict()

    assert data["id"] == "triage"
    assert data["type"] == "agent"
    assert data["config"]["agent_id"] == "a1"
    assert data["metadata"]["label"] == "Triage"


def test_node_from_dict():
    data = {"id": "triage", "type": "agent", "config": {"agent_id": "a1"}}
    node = Node.from_dict(data)

    assert node.id == "triage"
    assert node.type.value == "agent"
    assert node.config["agent_id"] == "a1"


def test_node_with_parent_serialization():
    node = Node("child", type="agent", parent="par")
    data = node.to_dict()

    assert data["parent"] == "par"

    restored = Node.from_dict(data)
    assert restored.parent == "par"


# --- Edge serialization ---


def test_edge_to_dict_no_condition():
    edge = Edge("start", "end")
    data = edge.to_dict()

    assert data["source"] == "start"
    assert data["target"] == "end"
    assert "condition" not in data or data["condition"] is None


def test_edge_to_dict_with_condition():
    edge = Edge("a", "b", Condition.field("a.output.x").equals(True))
    data = edge.to_dict()

    assert data["condition"]["type"] == "field"
    assert data["condition"]["path"] == "a.output.x"


def test_edge_from_dict():
    data = {
        "source": "a",
        "target": "b",
        "condition": {"type": "field", "path": "x", "op": "eq", "value": 1},
    }
    edge = Edge.from_dict(data)

    assert edge.source == "a"
    assert edge.target == "b"
    assert edge.condition is not None
    assert edge.condition.type == "field"


# --- Trigger serialization ---


def test_webhook_trigger_to_dict():
    trigger = WebhookTrigger(source_type="github")
    data = trigger.to_dict()

    assert data["type"] == "webhook"
    assert data["source_type"] == "github"


def test_scheduled_trigger_to_dict():
    trigger = ScheduledTrigger(schedule={"recurrence_type": "daily", "times_of_day": ["09:00"]})
    data = trigger.to_dict()

    assert data["type"] == "scheduled"
    assert data["schedule"]["recurrence_type"] == "daily"


# --- Full graph serialization ---


def test_graph_to_dict():
    g = _bug_triage_graph()
    data = g.to_dict()

    assert data["id"] == "bug-triage"
    assert data["name"] == "Bug Triage"
    assert data["description"] == "Triage incoming GitHub issues"
    assert data["trigger"]["type"] == "webhook"
    assert data["trigger"]["source_type"] == "github"
    assert len(data["nodes"]) == 5
    assert len(data["edges"]) == 5


def test_graph_from_dict():
    g = _bug_triage_graph()
    data = g.to_dict()

    restored = Graph.from_dict(data)

    assert restored.id == "bug-triage"
    assert restored.name == "Bug Triage"
    assert len(restored.nodes) == 5
    assert len(restored.edges) == 5
    assert restored.trigger.type == "webhook"


def test_graph_round_trip_preserves_conditions():
    g = _bug_triage_graph()
    data = g.to_dict()
    restored = Graph.from_dict(data)

    # Check conditions survived
    conditional_edges = [e for e in restored.edges if e.condition is not None]
    assert len(conditional_edges) == 2

    field_cond = [e for e in conditional_edges if e.condition.type == "field"]
    otherwise_cond = [e for e in conditional_edges if e.condition.type == "otherwise"]
    assert len(field_cond) == 1
    assert len(otherwise_cond) == 1


def test_graph_round_trip_preserves_parallel():
    g = _parallel_graph()
    data = g.to_dict()
    restored = Graph.from_dict(data)

    children = restored.get_children("checks")
    assert len(children) == 2
    assert {c.id for c in children} == {"sec", "comp"}


def test_graph_to_json_string():
    g = _bug_triage_graph()
    data = g.to_dict()

    # Must be JSON-serializable
    json_str = json.dumps(data)
    parsed = json.loads(json_str)

    restored = Graph.from_dict(parsed)
    assert restored.id == g.id
    assert len(restored.nodes) == len(g.nodes)


def test_graph_from_raw_json():
    """Deserialize from a raw JSON structure (what a UI/DB would produce)."""
    raw = {
        "id": "from-ui",
        "name": "UI-Created Workflow",
        "trigger": {"type": "manual"},
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "step1", "type": "function", "config": {"action": "delay", "duration": "5m"}},
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"source": "start", "target": "step1"},
            {"source": "step1", "target": "end"},
        ],
    }

    g = Graph.from_dict(raw)

    assert g.id == "from-ui"
    assert len(g.nodes) == 3
    assert len(g.edges) == 2
    assert g.nodes["step1"].config["action"] == "delay"
    assert g.validate() == []
