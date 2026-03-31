from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from roomkit_graph.edges.edge import Edge
from roomkit_graph.errors import GraphValidationError
from roomkit_graph.nodes.base import Node, NodeType
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
        if node.id in self.nodes:
            msg = f"Duplicate node id: {node.id}"
            raise ValueError(msg)
        self.nodes[node.id] = node

    def add_nodes(self, *nodes: Node) -> None:
        """Add multiple nodes to the graph."""
        for node in nodes:
            self.add_node(node)

    def add_edge(self, edge: Edge) -> None:
        """Add a single edge to the graph."""
        self.edges.append(edge)

    def add_edges(self, *edges: Edge) -> None:
        """Add multiple edges to the graph."""
        for edge in edges:
            self.add_edge(edge)

    def get_node(self, node_id: str) -> Node:
        """Get a node by ID. Raises KeyError if not found."""
        return self.nodes[node_id]

    def get_outgoing_edges(self, node_id: str) -> list[Edge]:
        """Get all edges originating from a node."""
        return [e for e in self.edges if e.source == node_id]

    def get_incoming_edges(self, node_id: str) -> list[Edge]:
        """Get all edges targeting a node."""
        return [e for e in self.edges if e.target == node_id]

    def get_children(self, parent_id: str) -> list[Node]:
        """Get child nodes of a parallel node."""
        return [n for n in self.nodes.values() if n.parent == parent_id]

    def validate(self) -> list[str]:
        """Validate the graph structure. Returns list of error messages (empty = valid)."""
        errors: list[str] = []

        # Count start and end nodes
        start_nodes = [n for n in self.nodes.values() if n.type == NodeType.START]
        end_nodes = [n for n in self.nodes.values() if n.type == NodeType.END]

        if len(start_nodes) == 0:
            errors.append("Graph must have exactly one start node")
        elif len(start_nodes) > 1:
            ids = ", ".join(n.id for n in start_nodes)
            errors.append(
                f"Graph must have exactly one start node, found {len(start_nodes)}: {ids}"
            )

        if len(end_nodes) == 0:
            errors.append("Graph must have at least one end node")

        # Check edge references
        for edge in self.edges:
            if edge.source not in self.nodes:
                errors.append(f"Edge source references nonexistent node: {edge.source}")
            if edge.target not in self.nodes:
                errors.append(f"Edge target references nonexistent node: {edge.target}")

        # Check start has no incoming edges
        if start_nodes:
            start_id = start_nodes[0].id
            incoming = self.get_incoming_edges(start_id)
            if incoming:
                errors.append(f"Start node '{start_id}' must not have incoming edges")

        # Check end nodes have no outgoing edges
        for end_node in end_nodes:
            outgoing = self.get_outgoing_edges(end_node.id)
            if outgoing:
                errors.append(f"End node '{end_node.id}' must not have outgoing edges")

        # Check reachability from start (BFS)
        if start_nodes and not errors:
            reachable: set[str] = set()
            queue: deque[str] = deque([start_nodes[0].id])
            while queue:
                nid = queue.popleft()
                if nid in reachable:
                    continue
                reachable.add(nid)
                # Follow outgoing edges
                for edge in self.get_outgoing_edges(nid):
                    if edge.target not in reachable:
                        queue.append(edge.target)
                # Include children of parallel nodes
                for child in self.get_children(nid):
                    if child.id not in reachable:
                        queue.append(child.id)

            # Report unreachable nodes (exclude children — they're reachable via parent)
            for node in self.nodes.values():
                if node.id not in reachable:
                    errors.append(f"Node '{node.id}' is not reachable from start")

        return errors

    def validate_or_raise(self) -> None:
        """Validate and raise GraphValidationError if the graph is invalid."""
        errors = self.validate()
        if errors:
            raise GraphValidationError("; ".join(errors))

    def to_dict(self) -> dict[str, Any]:
        """Serialize the full graph to a JSON-compatible dict."""
        data: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "trigger": self.trigger.to_dict(),
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": [edge.to_dict() for edge in self.edges],
        }
        if self.description is not None:
            data["description"] = self.description
        if self.version != 1:
            data["version"] = self.version
        if self.metadata:
            data["metadata"] = self.metadata
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Graph:
        """Deserialize a graph from a dict."""
        trigger = Trigger.from_dict(data["trigger"])
        graph = cls(
            id=data["id"],
            name=data["name"],
            trigger=trigger,
            description=data.get("description"),
            version=data.get("version", 1),
            metadata=data.get("metadata", {}),
        )
        for node_data in data.get("nodes", []):
            graph.add_node(Node.from_dict(node_data))
        for edge_data in data.get("edges", []):
            graph.add_edge(Edge.from_dict(edge_data))
        return graph
