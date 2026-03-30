"""Tests for Graph — creation, node/edge management, validation, serialization."""

from __future__ import annotations

import pytest

from roomkit_graph import (
    Condition,
    Edge,
    Graph,
    ManualTrigger,
    Node,
    WebhookTrigger,
)


# --- Graph construction ---


def test_add_single_node():
    g = Graph(id="test", name="Test", trigger=ManualTrigger())
    g.add_node(Node("start", type="start"))

    assert "start" in g.nodes
    assert g.nodes["start"].id == "start"


def test_add_multiple_nodes():
    g = Graph(id="test", name="Test", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("agent", type="agent", config={"agent_id": "a1"}),
        Node("end", type="end"),
    )

    assert len(g.nodes) == 3


def test_add_duplicate_node_raises():
    g = Graph(id="test", name="Test", trigger=ManualTrigger())
    g.add_node(Node("start", type="start"))

    with pytest.raises(ValueError, match="start"):
        g.add_node(Node("start", type="end"))


def test_add_single_edge():
    g = Graph(id="test", name="Test", trigger=ManualTrigger())
    g.add_nodes(Node("start", type="start"), Node("end", type="end"))
    g.add_edge(Edge("start", "end"))

    assert len(g.edges) == 1
    assert g.edges[0].source == "start"
    assert g.edges[0].target == "end"


def test_add_multiple_edges():
    g = Graph(id="test", name="Test", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("a", type="agent"),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "a"), Edge("a", "end"))

    assert len(g.edges) == 2


def test_get_node():
    g = Graph(id="test", name="Test", trigger=ManualTrigger())
    g.add_node(Node("start", type="start"))

    node = g.get_node("start")
    assert node.id == "start"


def test_get_node_missing_raises():
    g = Graph(id="test", name="Test", trigger=ManualTrigger())

    with pytest.raises(KeyError):
        g.get_node("nonexistent")


def test_get_outgoing_edges():
    g = Graph(id="test", name="Test", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("a", type="agent"),
        Node("b", type="agent"),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "a"), Edge("start", "b"), Edge("a", "end"))

    outgoing = g.get_outgoing_edges("start")
    assert len(outgoing) == 2
    assert all(e.source == "start" for e in outgoing)


def test_get_incoming_edges():
    g = Graph(id="test", name="Test", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("a", type="agent"),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "a"), Edge("a", "end"))

    incoming = g.get_incoming_edges("end")
    assert len(incoming) == 1
    assert incoming[0].source == "a"


def test_get_children():
    g = Graph(id="test", name="Test", trigger=ManualTrigger())
    g.add_nodes(
        Node("par", type="parallel", config={"join": "all"}),
        Node("c1", type="agent", parent="par"),
        Node("c2", type="notification", parent="par"),
    )

    children = g.get_children("par")
    assert len(children) == 2
    assert {c.id for c in children} == {"c1", "c2"}


# --- Validation ---


def _make_valid_graph() -> Graph:
    """Helper: minimal valid graph (start → agent → end)."""
    g = Graph(id="valid", name="Valid", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("work", type="agent", config={"agent_id": "a1"}),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "work"), Edge("work", "end"))
    return g


def test_validate_valid_graph():
    g = _make_valid_graph()
    errors = g.validate()
    assert errors == []


def test_validate_no_start_node():
    g = Graph(id="test", name="Test", trigger=ManualTrigger())
    g.add_nodes(Node("end", type="end"))

    errors = g.validate()
    assert any("start" in e.lower() for e in errors)


def test_validate_no_end_node():
    g = Graph(id="test", name="Test", trigger=ManualTrigger())
    g.add_nodes(Node("start", type="start"))

    errors = g.validate()
    assert any("end" in e.lower() for e in errors)


def test_validate_multiple_start_nodes():
    g = Graph(id="test", name="Test", trigger=ManualTrigger())
    g.add_nodes(
        Node("start1", type="start"),
        Node("start2", type="start"),
        Node("end", type="end"),
    )

    errors = g.validate()
    assert any("start" in e.lower() for e in errors)


def test_validate_edge_references_nonexistent_node():
    g = Graph(id="test", name="Test", trigger=ManualTrigger())
    g.add_nodes(Node("start", type="start"), Node("end", type="end"))
    g.add_edge(Edge("start", "ghost"))

    errors = g.validate()
    assert any("ghost" in e for e in errors)


def test_validate_start_has_incoming_edge():
    g = Graph(id="test", name="Test", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("work", type="agent"),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "work"), Edge("work", "start"), Edge("work", "end"))

    errors = g.validate()
    assert any("start" in e.lower() and "incoming" in e.lower() for e in errors)


def test_validate_end_has_outgoing_edge():
    g = Graph(id="test", name="Test", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("end", type="end"),
        Node("extra", type="agent"),
    )
    g.add_edges(Edge("start", "end"), Edge("end", "extra"))

    errors = g.validate()
    assert any("end" in e.lower() and "outgoing" in e.lower() for e in errors)


def test_validate_unreachable_node():
    g = Graph(id="test", name="Test", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("work", type="agent"),
        Node("orphan", type="agent"),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "work"), Edge("work", "end"))

    errors = g.validate()
    assert any("orphan" in e for e in errors)


# --- Serialization ---


def test_graph_to_dict():
    g = _make_valid_graph()
    data = g.to_dict()

    assert data["id"] == "valid"
    assert data["name"] == "Valid"
    assert data["trigger"]["type"] == "manual"
    assert len(data["nodes"]) == 3
    assert len(data["edges"]) == 2


def test_graph_round_trip():
    g = _make_valid_graph()
    data = g.to_dict()
    restored = Graph.from_dict(data)

    assert restored.id == g.id
    assert restored.name == g.name
    assert len(restored.nodes) == len(g.nodes)
    assert len(restored.edges) == len(g.edges)
    assert restored.trigger.type == g.trigger.type


def test_graph_from_dict_with_conditions():
    data = {
        "id": "test",
        "name": "Test",
        "trigger": {"type": "webhook", "source_type": "github"},
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "a", "type": "agent", "config": {"agent_id": "a1"}},
            {"id": "b", "type": "agent", "config": {"agent_id": "b1"}},
            {"id": "end", "type": "end"},
        ],
        "edges": [
            {"source": "start", "target": "a"},
            {
                "source": "a",
                "target": "b",
                "condition": {"type": "field", "path": "a.output.ok", "op": "eq", "value": True},
            },
            {"source": "a", "target": "end", "condition": {"type": "otherwise"}},
            {"source": "b", "target": "end"},
        ],
    }

    g = Graph.from_dict(data)
    assert len(g.nodes) == 4
    assert len(g.edges) == 4
    assert g.edges[1].condition is not None
    assert g.edges[1].condition.type == "field"
    assert g.edges[2].condition.type == "otherwise"
