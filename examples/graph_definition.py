"""Define, validate, and serialize a workflow graph.

Builds a bug triage workflow with conditional branching, validates it,
serializes to JSON, and round-trips back to verify the graph is intact.

Run with:
    uv run python examples/graph_definition.py
"""

from __future__ import annotations

import asyncio
import json

from roomkit_graph import Condition, Edge, Graph, Node, WebhookTrigger


async def main() -> None:
    # --- Build the graph -----------------------------------------------------
    graph = Graph(
        id="bug-triage",
        name="Bug Triage Workflow",
        description="Triage incoming GitHub issues, escalate critical ones",
        trigger=WebhookTrigger(source_type="github"),
    )

    graph.add_nodes(
        Node("start", type="start"),
        Node(
            "triage",
            type="agent",
            config={
                "agent_id": "triage-agent",
                "prompt_template": (
                    "Triage this GitHub issue. "
                    "Classify severity (critical/high/medium/low) and category.\n\n"
                    "{{start.input}}"
                ),
            },
        ),
        Node(
            "escalate",
            type="notification",
            config={
                "channel": "slack",
                "template": "Critical bug: {{triage.output.title}}",
            },
        ),
        Node(
            "assign",
            type="agent",
            config={
                "agent_id": "labeler-agent",
                "prompt_template": "Assign labels and team:\n\n{{triage.output}}",
            },
        ),
        Node("end", type="end"),
    )

    graph.add_edges(
        Edge("start", "triage"),
        Edge(
            "triage",
            "escalate",
            condition=Condition.field("triage.output.severity").equals("critical"),
        ),
        Edge("triage", "assign", condition=Condition.otherwise()),
        Edge("escalate", "end"),
        Edge("assign", "end"),
    )

    # --- Validate ------------------------------------------------------------
    errors = graph.validate()
    if errors:
        print("Validation errors:")
        for err in errors:
            print(f"  - {err}")
        return

    print("Graph is valid!")
    print(f"  Nodes: {len(graph.nodes)}")
    print(f"  Edges: {len(graph.edges)}")
    print()

    # --- Serialize to JSON ---------------------------------------------------
    data = graph.to_dict()
    json_str = json.dumps(data, indent=2)
    print("Serialized to JSON:")
    print(json_str)
    print()

    # --- Round-trip -----------------------------------------------------------
    restored = Graph.from_dict(json.loads(json_str))
    print("Round-trip verification:")
    print(f"  ID match: {restored.id == graph.id}")
    print(f"  Nodes match: {len(restored.nodes) == len(graph.nodes)}")
    print(f"  Edges match: {len(restored.edges) == len(graph.edges)}")
    print(f"  Trigger match: {restored.trigger.type == graph.trigger.type}")

    # Verify conditions survived
    conditional = [e for e in restored.edges if e.condition is not None]
    print(f"  Conditional edges: {len(conditional)}")
    for edge in conditional:
        print(f"    {edge.source} -> {edge.target}: {edge.condition.to_dict()}")


if __name__ == "__main__":
    asyncio.run(main())
