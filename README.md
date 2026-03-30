# roomkit-graph

Workflow graph engine for [RoomKit](https://github.com/roomkit-live/roomkit). Define multi-step workflows as directed graphs and execute them inside RoomKit rooms — with AI agents, human decisions, notifications, and data transforms.

Each workflow run is a RoomKit room. Steps produce messages. The full execution history is a conversation you can read, audit, and interact with.

## Why

RoomKit gives you rooms, agents, orchestration, hooks, and persistence. But there's no way to compose them into multi-step business processes — "when X happens, do A, then based on the result do B or C, wait for approval, then notify."

Existing workflow engines (n8n, Airflow, Temporal) are full platforms. `roomkit-graph` is a library you embed in your app.

## Design Principles

- **Conversation-native** — each run IS a room. Steps produce events. Open a run and read it like a chat thread.
- **AI-first** — Agent and Orchestration are first-class nodes, not HTTP calls to an LLM.
- **Serializable** — graphs are data (JSON), not code. Build UIs, store in databases, version and share.
- **RoomKit-native** — uses rooms, channels, hooks, ConversationState, delegation. No reinvention.
- **Lightweight** — depends on `roomkit`, nothing else. No separate services.

## Node Types

| Node | Purpose |
|---|---|
| **Start** | Entry point — receives trigger payload |
| **End** | Marks workflow complete |
| **Agent** | Run an AI agent (any RoomKit-supported provider) |
| **Orchestration** | Run a multi-agent strategy (Pipeline, Swarm, Supervisor, Loop) |
| **Human** | Pause workflow, wait for human input or approval |
| **Notification** | Send a notification (Slack, email, etc.) and continue |
| **Function** | Transform data, HTTP calls, delays, or custom Python logic |
| **Parallel** | Run children concurrently, join when all/any complete |

## Quick Example

```python
from roomkit_graph import Graph, Node, Edge, Condition, WebhookTrigger

graph = Graph(
    id="bug-triage",
    name="Bug Triage",
    trigger=WebhookTrigger(source_type="github"),
)

graph.add_nodes(
    Node("start", type="start"),
    Node("triage", type="agent", config={
        "agent_id": "triage-agent",
        "prompt_template": "Triage this issue. Classify severity.\n\n{{start.input}}"
    }),
    Node("escalate", type="notification", config={
        "channel": "slack",
        "template": "Critical bug: {{triage.output.title}}"
    }),
    Node("assign", type="agent", config={
        "agent_id": "labeler-agent",
        "prompt_template": "Assign labels and team:\n\n{{triage.output}}"
    }),
    Node("end", type="end"),
)

graph.add_edges(
    Edge("start", "triage"),
    Edge("triage", "escalate",
         condition=Condition.field("triage.output.severity").equals("critical")),
    Edge("triage", "assign",
         condition=Condition.otherwise()),
    Edge("escalate", "end"),
    Edge("assign", "end"),
)
```

## More Examples

### Content Review with Human-in-the-Loop

AI drafts content, human reviews, revision loop until approved:

```python
graph = Graph(id="content-review", name="Content Review", trigger=ManualTrigger())

graph.add_nodes(
    Node("start", type="start"),
    Node("draft", type="agent", config={
        "agent_id": "writer-agent",
        "prompt_template": "Write a blog post about: {{start.input.topic}}"
    }),
    Node("review", type="human", config={
        "prompt": "Review this draft. Approve or reject with feedback.",
        "actions": ["approve", "reject"],
        "timeout": "72h"
    }),
    Node("revise", type="agent", config={
        "agent_id": "writer-agent",
        "prompt_template": "Revise based on feedback:\n{{review.output.feedback}}"
    }),
    Node("publish", type="notification", config={
        "channel": "slack",
        "template": "Published: {{draft.output.title}}"
    }),
    Node("end", type="end"),
)

graph.add_edges(
    Edge("start", "draft"),
    Edge("draft", "review"),
    Edge("review", "publish",
         condition=Condition.field("review.action").equals("approve")),
    Edge("review", "revise",
         condition=Condition.field("review.action").equals("reject")),
    Edge("revise", "review"),  # loop back
    Edge("publish", "end"),
)
```

### Parallel Execution

Run multiple steps concurrently and join:

```python
graph.add_nodes(
    Node("start", type="start"),
    Node("analyze", type="agent", config={"agent_id": "analyzer"}),
    Node("checks", type="parallel", config={"join": "all"}),
    Node("security", type="agent", config={"agent_id": "security-agent"},
         parent="checks"),
    Node("compliance", type="agent", config={"agent_id": "compliance-agent"},
         parent="checks"),
    Node("notify", type="notification", config={"channel": "slack"},
         parent="checks"),
    Node("summarize", type="agent", config={"agent_id": "summarizer"}),
    Node("end", type="end"),
)

graph.add_edges(
    Edge("start", "analyze"),
    Edge("analyze", "checks"),
    Edge("checks", "summarize"),
    Edge("summarize", "end"),
)
```

### Function Nodes

Transform data, call APIs, or run custom logic between steps:

```python
# HTTP request
Node("enrich", type="function", config={
    "action": "http_request",
    "method": "GET",
    "url": "https://api.internal/employees/{{extract.output.id}}"
})

# Data transform
Node("reshape", type="function", config={
    "action": "json_transform",
    "template": {
        "name": "{{extract.output.first}} {{extract.output.last}}",
        "priority": "{{extract.output.tier}}"
    }
})

# Delay
Node("wait", type="function", config={
    "action": "delay",
    "duration": "30m"
})

# Custom Python function (registered at runtime)
@graph_registry.function("calculate_priority")
async def calculate_priority(ctx: NodeContext) -> dict:
    severity = ctx.get("triage.output.severity")
    tier = ctx.get("enrich.output.tier")
    return {"priority": "P1" if severity == "critical" and tier == "enterprise" else "P2"}

Node("prioritize", type="function", config={
    "action": "custom",
    "function": "calculate_priority"
})
```

## Conditions

Serializable condition DSL for edge routing:

```python
# Field comparisons
Condition.field("triage.output.severity").equals("critical")
Condition.field("amount").gt(1000)
Condition.field("tags").contains("urgent")
Condition.field("status").in_(["approved", "accepted"])
Condition.field("manager").exists()

# Composites
Condition.all_(
    Condition.field("severity").equals("critical"),
    Condition.field("team").equals("backend"),
)
Condition.any_(cond1, cond2)
Condition.not_(cond)

# Default fallback
Condition.otherwise()
```

All conditions serialize to JSON for storage and UI builders:

```json
{"type": "field", "path": "triage.output.severity", "op": "eq", "value": "critical"}
{"type": "all", "conditions": [
    {"type": "field", "path": "amount", "op": "gt", "value": 1000},
    {"type": "field", "path": "category", "op": "eq", "value": "travel"}
]}
{"type": "otherwise"}
```

## How It Works with RoomKit

`roomkit-graph` implements RoomKit's `Orchestration` interface:

```python
from roomkit import RoomKit
from roomkit_graph import GraphOrchestration

orchestration = GraphOrchestration(graph)
kit = RoomKit(store=store, orchestration=orchestration)
```

Under the hood:

| roomkit-graph | RoomKit primitive |
|---|---|
| Workflow run | Room |
| Current step | `ConversationState.phase` |
| Step context | `ConversationState.context` |
| Agent step | Agent channel + `on_event()` |
| Orchestration step | `kit.delegate()` (child room) |
| Human step | Room pause + inbound message |
| Notification step | `kit.deliver()` |
| Parallel step | Multiple `kit.delegate()` + join |
| Transitions | `ConversationRouter` + hooks |
| Audit trail | Room events |
| Persistence | `ConversationStore` |

## Cross-Step Context

Steps reference previous outputs with `{{node_id.output.field}}` templates:

```
{{start.input}}                      # trigger payload
{{start.input.title}}                # nested field
{{triage.output.severity}}           # previous step output
{{parallel.security.output}}         # parallel child output
```

Resolved at runtime from the workflow context before each step executes.

## Status

Early development. API is not stable.

## License

MIT
