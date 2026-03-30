"""Tests for GraphOrchestration — RoomKit integration."""

from __future__ import annotations

from roomkit_graph import Edge, Graph, GraphOrchestration, ManualTrigger, Node


def test_graph_orchestration_instantiation():
    g = Graph(id="test", name="Test", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("agent", type="agent", config={"agent_id": "a1"}),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "agent"), Edge("agent", "end"))

    orch = GraphOrchestration(g)
    assert orch.graph is g


def test_graph_orchestration_get_agent_node_ids():
    g = Graph(id="test", name="Test", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("a1", type="agent", config={"agent_id": "triage"}),
        Node("a2", type="agent", config={"agent_id": "labeler"}),
        Node("notify", type="notification", config={"channel": "slack"}),
        Node("end", type="end"),
    )
    g.add_edges(
        Edge("start", "a1"),
        Edge("a1", "a2"),
        Edge("a2", "notify"),
        Edge("notify", "end"),
    )

    orch = GraphOrchestration(g)
    agent_ids = orch.get_agent_node_ids()

    assert len(agent_ids) == 2
    assert set(agent_ids) == {"triage", "labeler"}


def test_graph_orchestration_agents_returns_injected():
    """When agents are injected (by Luge), agents() returns them."""
    g = Graph(id="test", name="Test", trigger=ManualTrigger())
    g.add_nodes(Node("start", type="start"), Node("end", type="end"))
    g.add_edges(Edge("start", "end"))

    # Simulate Luge injecting resolved agents
    mock_agents = ["agent1", "agent2"]  # In reality these are Agent instances
    orch = GraphOrchestration(g, agents=mock_agents)

    assert orch.agents() == ["agent1", "agent2"]


def test_graph_orchestration_agents_empty_by_default():
    g = Graph(id="test", name="Test", trigger=ManualTrigger())
    g.add_nodes(Node("start", type="start"), Node("end", type="end"))
    g.add_edges(Edge("start", "end"))

    orch = GraphOrchestration(g)
    assert orch.agents() == []
