"""Integration tests — cross-module interactions."""

from __future__ import annotations

from roomkit_graph import (
    Condition,
    Edge,
    Graph,
    ManualTrigger,
    Node,
    TemplateResolver,
    WebhookTrigger,
    WorkflowContext,
    WorkflowExecutor,
)

# --- Graph + Condition + Serialization round-trip ---


def _content_review_graph() -> Graph:
    """README Example 2: content review with human-in-the-loop loop."""
    g = Graph(
        id="content-review",
        name="Content Review & Publish",
        description="AI drafts content, human reviews, loop until approved",
        trigger=ManualTrigger(),
    )
    g.add_nodes(
        Node("start", type="start"),
        Node(
            "draft",
            type="agent",
            config={
                "agent_id": "writer-agent",
                "prompt_template": "Write a blog post about: {{start.input.topic}}",
            },
        ),
        Node(
            "review",
            type="human",
            config={
                "prompt": "Review this draft. Approve or reject with feedback.",
                "actions": ["approve", "reject"],
                "timeout": "72h",
            },
        ),
        Node(
            "revise",
            type="agent",
            config={
                "agent_id": "writer-agent",
                "prompt_template": "Revise based on feedback:\n{{review.output.feedback}}",
            },
        ),
        Node(
            "publish",
            type="notification",
            config={"channel": "slack", "template": "Published: {{draft.output.title}}"},
        ),
        Node("end", type="end"),
    )
    g.add_edges(
        Edge("start", "draft"),
        Edge("draft", "review"),
        Edge(
            "review",
            "publish",
            condition=Condition.field("review.output.action").equals("approve"),
        ),
        Edge(
            "review", "revise", condition=Condition.field("review.output.action").equals("reject")
        ),
        Edge("revise", "review"),  # loop back
        Edge("publish", "end"),
    )
    return g


def test_content_review_graph_validates():
    g = _content_review_graph()
    errors = g.validate()
    assert errors == []


def test_content_review_round_trip():
    g = _content_review_graph()
    data = g.to_dict()
    restored = Graph.from_dict(data)

    assert restored.id == "content-review"
    assert len(restored.nodes) == 6
    assert len(restored.edges) == 6

    # Verify loop-back edge exists
    revise_edges = restored.get_outgoing_edges("revise")
    assert len(revise_edges) == 1
    assert revise_edges[0].target == "review"

    # Verify conditional edges
    review_edges = restored.get_outgoing_edges("review")
    assert len(review_edges) == 2
    conditions = [e.condition.type for e in review_edges]
    assert "field" in conditions


# --- WorkflowContext + Condition.evaluate() ---


def test_condition_evaluates_against_workflow_context():
    ctx = WorkflowContext()
    ctx.set("triage", {"severity": "critical", "category": "auth"})

    cond_match = Condition.field("triage.output.severity").equals("critical")
    cond_no_match = Condition.field("triage.output.severity").equals("low")

    assert cond_match.evaluate(ctx) is True
    assert cond_no_match.evaluate(ctx) is False


def test_composite_condition_against_context():
    ctx = WorkflowContext()
    ctx.set("extract", {"amount": 5000, "category": "travel"})

    cond = Condition.all_(
        Condition.field("extract.output.amount").gt(1000),
        Condition.field("extract.output.category").equals("travel"),
    )

    assert cond.evaluate(ctx) is True


# --- TemplateResolver + WorkflowContext ---


def test_resolver_with_workflow_context():
    ctx = WorkflowContext()
    ctx.set("start", {"topic": "AI Workflows"})
    ctx.set("draft", {"title": "Building AI Workflows", "body": "..."})

    resolver = TemplateResolver(ctx)

    result = resolver.resolve("Published: {{draft.output.title}}")
    assert result == "Published: Building AI Workflows"


def test_resolver_dict_with_workflow_context():
    ctx = WorkflowContext()
    ctx.set("extract", {"submitter": "alice@co.com", "amount": 500})

    resolver = TemplateResolver(ctx)
    result = resolver.resolve_dict(
        {
            "to": "{{extract.output.submitter}}",
            "subject": "Expense: ${{extract.output.amount}}",
        }
    )

    assert result["to"] == "alice@co.com"
    assert result["subject"] == "Expense: $500"


# --- Executor + injectable context (resume scenario) ---


async def test_executor_with_injected_context():
    """Executor can resume from a previously saved context."""
    g = Graph(id="test", name="Test", trigger=ManualTrigger())
    g.add_nodes(
        Node("start", type="start"),
        Node("review", type="human", config={"prompt": "Approve?"}),
        Node("end", type="end"),
    )
    g.add_edges(Edge("start", "review"), Edge("review", "end"))

    # Simulate saved context from a previous run
    saved = WorkflowContext()
    saved.set("start", {"input": {"data": "original"}})

    executor = WorkflowExecutor(g, context=saved)

    # Context should be the injected one, not a fresh instance
    assert executor.context.get("start.output.input") == {"data": "original"}


# --- Full graph with all node types serialization ---


def test_all_node_types_in_graph():
    g = Graph(id="full", name="Full", trigger=WebhookTrigger(source_type="github"))
    g.add_nodes(
        Node("start", type="start"),
        Node("triage", type="agent", config={"agent_id": "triage"}),
        Node("checks", type="parallel", config={"join": "all"}),
        Node("sec", type="agent", config={"agent_id": "sec"}, parent="checks"),
        Node("comp", type="function", config={"action": "http_request"}, parent="checks"),
        Node("review", type="human", config={"prompt": "Approve?", "timeout": "24h"}),
        Node("pipeline", type="orchestration", config={"orchestration_id": "pipe-1"}),
        Node("notify", type="notification", config={"channel": "slack"}),
        Node("end", type="end"),
    )
    g.add_edges(
        Edge("start", "triage"),
        Edge("triage", "checks"),
        Edge("checks", "review"),
        Edge(
            "review",
            "pipeline",
            condition=Condition.field("review.output.action").equals("approve"),
        ),
        Edge(
            "review", "notify", condition=Condition.field("review.output.action").equals("reject")
        ),
        Edge("pipeline", "end"),
        Edge("notify", "end"),
    )

    errors = g.validate()
    assert errors == []

    data = g.to_dict()
    restored = Graph.from_dict(data)

    assert len(restored.nodes) == 9
    assert len(restored.edges) == 7
    assert restored.trigger.type == "webhook"
