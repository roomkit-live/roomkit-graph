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


def test_graph_orchestration_agents_returns_agent_nodes():
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
    agents = orch.agents()

    # Should return agents for the 2 agent nodes, not notification or start/end
    assert len(agents) == 2
