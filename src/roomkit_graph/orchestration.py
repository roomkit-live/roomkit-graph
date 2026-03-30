from __future__ import annotations

from typing import TYPE_CHECKING, Any

from roomkit.orchestration.base import Orchestration

from roomkit_graph.graph import Graph
from roomkit_graph.nodes.base import NodeType

if TYPE_CHECKING:
    from roomkit import RoomKit
    from roomkit.channels.agent import Agent


class GraphOrchestration(Orchestration):
    """RoomKit Orchestration implementation that executes a workflow graph.

    Usage:
        graph = Graph(...)
        orchestration = GraphOrchestration(graph, agents=resolved_agents)
        kit = RoomKit(store=store, orchestration=orchestration)
    """

    def __init__(
        self,
        graph: Graph,
        agents: list[Agent] | None = None,
        agent_map: dict[str, Agent] | None = None,
        notification_config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._graph = graph
        self._agents = agents or []
        self._agent_map = agent_map or {}
        self._notification_config = notification_config or {}

    @property
    def graph(self) -> Graph:
        return self._graph

    def agents(self) -> list[Agent]:
        """Return all agents for this orchestration.

        When agents are injected (by Luge's OrchestrationService), returns those.
        Otherwise returns an empty list — the consumer is responsible for providing agents.
        """
        return list(self._agents)

    def get_agent_node_ids(self) -> list[str]:
        """Return agent_id values from all AgentNodes in the graph."""
        return [
            n.config["agent_id"]
            for n in self._graph.nodes.values()
            if n.type == NodeType.AGENT and "agent_id" in n.config
        ]

    async def install(self, kit: RoomKit, room_id: str) -> None:
        """Install hooks, routing, and state for graph execution in a room."""
        raise NotImplementedError
