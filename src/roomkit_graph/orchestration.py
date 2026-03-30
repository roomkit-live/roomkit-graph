from __future__ import annotations

from typing import TYPE_CHECKING, Any

from roomkit.orchestration.base import Orchestration

from roomkit_graph.graph import Graph

if TYPE_CHECKING:
    from roomkit import RoomKit
    from roomkit.channels.agent import Agent


class GraphOrchestration(Orchestration):
    """RoomKit Orchestration implementation that executes a workflow graph.

    Usage:
        graph = Graph(...)
        orchestration = GraphOrchestration(graph)
        kit = RoomKit(store=store, orchestration=orchestration)
    """

    def __init__(self, graph: Graph, **kwargs: Any) -> None:
        self._graph = graph

    @property
    def graph(self) -> Graph:
        return self._graph

    def agents(self) -> list[Agent]:
        """Return all agents referenced by AgentNodes in the graph."""
        raise NotImplementedError

    async def install(self, kit: RoomKit, room_id: str) -> None:
        """Install hooks, routing, and state for graph execution in a room."""
        raise NotImplementedError
