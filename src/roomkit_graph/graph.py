from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from roomkit_graph.edges.edge import Edge
from roomkit_graph.nodes.base import Node
from roomkit_graph.triggers import Trigger


@dataclass
class Graph:
    """Workflow graph definition — a directed graph of nodes connected by edges.

    Graphs are serializable to/from dict/JSON for DB storage and UI builders.
    """

    id: str
    name: str
    trigger: Trigger
    description: str | None = None
    version: int = 1
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_node(self, node: Node) -> None:
        """Add a single node to the graph."""
        raise NotImplementedError

    def add_nodes(self, *nodes: Node) -> None:
        """Add multiple nodes to the graph."""
        raise NotImplementedError

    def add_edge(self, edge: Edge) -> None:
        """Add a single edge to the graph."""
        raise NotImplementedError

    def add_edges(self, *edges: Edge) -> None:
        """Add multiple edges to the graph."""
        raise NotImplementedError

    def get_node(self, node_id: str) -> Node:
        """Get a node by ID. Raises KeyError if not found."""
        raise NotImplementedError

    def get_outgoing_edges(self, node_id: str) -> list[Edge]:
        """Get all edges originating from a node."""
        raise NotImplementedError

    def get_incoming_edges(self, node_id: str) -> list[Edge]:
        """Get all edges targeting a node."""
        raise NotImplementedError

    def get_children(self, parent_id: str) -> list[Node]:
        """Get child nodes of a parallel node."""
        raise NotImplementedError

    def validate(self) -> list[str]:
        """Validate the graph structure. Returns list of error messages (empty = valid).

        Checks:
        - Exactly one start node
        - At least one end node
        - All edge sources/targets reference existing nodes
        - Start node has no incoming edges
        - End nodes have no outgoing edges
        - All non-start nodes are reachable from start
        - Parallel node children have parent set correctly
        """
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:
        """Serialize the full graph to a JSON-compatible dict."""
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Graph:
        """Deserialize a graph from a dict."""
        raise NotImplementedError
