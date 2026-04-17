"""Observer-side streaming — watch a workflow as it runs.

Demonstrates ``WorkflowEngine.stream()`` across all four modes
(``values``, ``updates``, ``lifecycle``, ``custom``) and shows a handler
using ``engine.emit(...)`` to surface intra-node progress.

Run with:
    uv run python examples/streaming.py
"""

from __future__ import annotations

import asyncio

from roomkit_graph import (
    Edge,
    Graph,
    ManualTrigger,
    Node,
    NodeHandler,
    NodeResult,
    WorkflowEngine,
)


class EmittingAgentHandler(NodeHandler):
    """Simulates an agent that reports intra-node progress via engine.emit()."""

    async def execute(self, node, context, engine):
        engine.emit({"stage": "planning", "node": node.id})
        await asyncio.sleep(0)  # yield once to simulate async work
        engine.emit({"stage": "tool_call", "tool": "search"})
        await asyncio.sleep(0)
        engine.emit({"stage": "finalizing"})
        return NodeResult(output={"response": f"{node.id} answered"}, status="completed")


def _build_graph() -> Graph:
    """start -> triage -> research -> end"""
    g = Graph(id="streaming-demo", name="Streaming Demo", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node(
            "triage",
            type="function",
            config={"action": "set_context", "values": {"severity": "high"}},
        ),
        Node("research", type="agent"),
        Node("end", type="end"),
    )
    g.add_edges(
        Edge("start", "triage"),
        Edge("triage", "research"),
        Edge("research", "end"),
    )
    return g


async def _demo_updates_and_custom() -> None:
    """Compact delta per step + handler-emitted custom events."""
    print("=== updates + custom (typical dashboard feed) ===\n")
    engine = WorkflowEngine(_build_graph(), handlers={"agent": EmittingAgentHandler()})
    async for event in engine.stream(
        trigger_data={"topic": "RAG pipeline"}, modes=("updates", "custom")
    ):
        if event["mode"] == "updates":
            for node_id, entry in event["payload"].items():
                print(f"  [updates] {node_id}: {entry}")
        else:  # custom
            print(f"  [custom]  {event['node_id']}: {event['payload']}")
    print()


async def _demo_lifecycle() -> None:
    """Per-node start/complete events — good for step-by-step UI."""
    print("=== lifecycle (step-by-step progress UI) ===\n")
    engine = WorkflowEngine(_build_graph(), handlers={"agent": EmittingAgentHandler()})
    async for event in engine.stream(modes=("lifecycle",)):
        phase = event["payload"]["phase"]
        status = event["payload"].get("status", "")
        marker = ">" if phase == "start" else "="
        print(f"  {marker} {event['node_id']:<10} {phase:<8} {status}")
    print()


async def _demo_values() -> None:
    """Full snapshots — expensive but simplest for debugging/audit."""
    print("=== values (full snapshots, for audit/debug) ===\n")
    engine = WorkflowEngine(_build_graph(), handlers={"agent": EmittingAgentHandler()})
    seq = 0
    async for event in engine.stream(modes=("values",)):
        keys = sorted(event["payload"].keys())
        print(f"  snapshot #{seq}: keys={keys}")
        seq += 1
    print()


async def _demo_multi_mode() -> None:
    """All four modes interleaved — shows the full event stream shape."""
    print("=== all modes (full event stream) ===\n")
    engine = WorkflowEngine(_build_graph(), handlers={"agent": EmittingAgentHandler()})
    async for event in engine.stream(modes=("lifecycle", "custom", "updates", "values")):
        mode = event["mode"]
        node_id = event["node_id"] or "-"
        seq = event["seq"]
        if mode == "lifecycle":
            detail = f"{event['payload']['phase']} {event['payload'].get('status', '')}"
        elif mode == "custom":
            detail = str(event["payload"])
        elif mode == "updates":
            detail = f"keys={list(event['payload'].keys())}"
        else:  # values
            detail = f"snapshot({len(event['payload'])} keys)"
        print(f"  #{seq:>2} {mode:<9} {node_id:<10} {detail}")
    print()


async def main() -> None:
    await _demo_updates_and_custom()
    await _demo_lifecycle()
    await _demo_values()
    await _demo_multi_mode()


if __name__ == "__main__":
    asyncio.run(main())
