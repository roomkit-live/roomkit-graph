"""Workflow engine — build, evaluate conditions, resolve templates, and execute.

Demonstrates the full engine without RoomKit: builds a graph with conditional
branching, simulates node outputs, evaluates conditions, resolves templates,
and runs the executor through a linear workflow.

Run with:
    uv run python examples/workflow_engine.py
"""

from __future__ import annotations

import asyncio

from roomkit_graph import (
    Condition,
    Edge,
    Graph,
    ManualTrigger,
    Node,
    NodeHandler,
    NodeResult,
    TemplateResolver,
    WebhookTrigger,
    WorkflowContext,
    WorkflowEngine,
)


async def main() -> None:
    # --- 1. Condition evaluation ---------------------------------------------
    print("=== Condition Evaluation ===\n")

    ctx = WorkflowContext()
    ctx.set("triage", {"severity": "critical", "category": "auth", "title": "Login broken"})

    cond_critical = Condition.field("triage.output.severity").equals("critical")
    cond_low = Condition.field("triage.output.severity").equals("low")
    cond_fallback = Condition.otherwise()

    print(f"  severity == 'critical': {cond_critical.evaluate(ctx)}")
    print(f"  severity == 'low':      {cond_low.evaluate(ctx)}")
    print(f"  otherwise:              {cond_fallback.evaluate(ctx)}")

    # Composite conditions
    cond_urgent = Condition.all_(
        Condition.field("triage.output.severity").in_(["critical", "high"]),
        Condition.field("triage.output.category").equals("auth"),
    )
    print(f"  critical+auth (AND):    {cond_urgent.evaluate(ctx)}")
    print()

    # --- 2. Template resolution ----------------------------------------------
    print("=== Template Resolution ===\n")

    ctx.set("start", {"issue": "Users cannot log in", "reporter": "alice@co.com"})
    resolver = TemplateResolver(ctx)

    template = "Bug: {{triage.output.title}} ({{triage.output.severity}}) — reported by {{start.output.reporter}}"
    print(f"  Template:  {template}")
    print(f"  Resolved:  {resolver.resolve(template)}")

    notification = resolver.resolve_dict(
        {
            "channel": "slack",
            "message": "Alert: {{triage.output.title}}",
            "metadata": {"severity": "{{triage.output.severity}}"},
        }
    )
    print(f"  Dict:      {notification}")
    print()

    # --- 3. Workflow execution -----------------------------------------------
    print("=== Workflow Execution ===\n")

    graph = Graph(
        id="simple-flow",
        name="Simple Linear Flow",
        trigger=ManualTrigger(),
    )

    graph.add_nodes(
        Node("start", type="start"),
        Node(
            "init",
            type="function",
            config={
                "action": "set_context",
                "values": {"initialized": True, "step": 1},
            },
        ),
        Node(
            "process",
            type="function",
            config={
                "action": "set_context",
                "values": {"processed": True, "step": 2},
            },
        ),
        Node("end", type="end"),
    )

    graph.add_edges(
        Edge("start", "init"),
        Edge("init", "process"),
        Edge("process", "end"),
    )

    executor = WorkflowEngine(graph)
    result = await executor.run(trigger_data={"message": "Go!"})

    print(f"  Trigger: {result.get('start.output.input')}")
    print(f"  Init:    {result.get('init.output')}")
    print(f"  Process: {result.get('process.output')}")
    print(f"  Done:    current_node={executor.current_node_id}")
    print()

    # --- 4. Edge evaluation with branching -----------------------------------
    print("=== Edge Evaluation (Branching) ===\n")

    branch_graph = Graph(
        id="branching",
        name="Branching Flow",
        trigger=WebhookTrigger(source_type="github"),
    )

    branch_graph.add_nodes(
        Node("start", type="start"),
        Node(
            "check",
            type="function",
            config={
                "action": "set_context",
                "values": {"priority": "high"},
            },
        ),
        Node(
            "urgent",
            type="function",
            config={
                "action": "set_context",
                "values": {"route": "urgent-path"},
            },
        ),
        Node(
            "normal",
            type="function",
            config={
                "action": "set_context",
                "values": {"route": "normal-path"},
            },
        ),
        Node("end", type="end"),
    )

    branch_graph.add_edges(
        Edge("start", "check"),
        Edge(
            "check",
            "urgent",
            condition=Condition.field("check.output.priority").in_(["critical", "high"]),
        ),
        Edge("check", "normal", condition=Condition.otherwise()),
        Edge("urgent", "end"),
        Edge("normal", "end"),
    )

    executor2 = WorkflowEngine(branch_graph)
    result2 = await executor2.run(trigger_data={"issue": "Bug report"})

    print(f"  Priority: {result2.get('check.output.priority')}")
    print(f"  Route:    {result2.get('urgent.output.route', result2.get('normal.output.route'))}")
    print(f"  Took urgent path: {result2.has('urgent.output')}")
    print(f"  Took normal path: {result2.has('normal.output')}")
    print()

    # --- 5. Parallel execution --------------------------------------------------
    print("=== Parallel Execution ===\n")

    class CheckHandler(NodeHandler):
        """Mock handler that simulates a check."""

        async def execute(self, node, context, engine):
            return NodeResult(
                output={"passed": True, "detail": f"{node.id} completed"},
                status="completed",
            )

    par_graph = Graph(id="parallel-demo", name="Parallel Demo", trigger=ManualTrigger())
    par_graph.add_nodes(
        Node("start", type="start"),
        Node("checks", type="parallel", config={"join": "all"}),
        Node("security", type="agent", config={}, parent="checks"),
        Node("compliance", type="agent", config={}, parent="checks"),
        Node("end", type="end"),
    )
    par_graph.add_edges(
        Edge("start", "checks"),
        Edge("checks", "end"),
    )

    executor3 = WorkflowEngine(par_graph, handlers={"agent": CheckHandler()})
    result3 = await executor3.run()

    print(f"  Security:   {result3.get('security.output')}")
    print(f"  Compliance: {result3.get('compliance.output')}")
    print(f"  Aggregate:  {result3.get('checks.output')}")
    print()

    # --- 6. Template passthrough ------------------------------------------------
    print("=== Template Passthrough ===\n")

    ctx2 = WorkflowContext()
    ctx2.set("enrich", {"employee": {"name": "Alice", "role": "Engineer"}, "count": 42})
    resolver2 = TemplateResolver(ctx2)

    # Single placeholder → raw value (dict passthrough)
    raw_dict = resolver2.resolve_value("{{enrich.output.employee}}")
    print(f"  Passthrough dict: {raw_dict} (type={type(raw_dict).__name__})")

    # Single placeholder → raw value (int passthrough)
    raw_int = resolver2.resolve_value("{{enrich.output.count}}")
    print(f"  Passthrough int:  {raw_int} (type={type(raw_int).__name__})")

    # Mixed text → string interpolation (as before)
    mixed = resolver2.resolve_value("Employee: {{enrich.output.employee.name}}")
    print(f"  Mixed text:       {mixed} (type={type(mixed).__name__})")


if __name__ == "__main__":
    asyncio.run(main())
