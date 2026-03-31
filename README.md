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
| **Function** | Transform data, delays, or custom Python logic |
| **Parallel** | Run children concurrently, join when all/any complete |
| **Condition** | Evaluate a condition and store the boolean result for downstream branching |
| **Switch** | Read a context value for multi-way branching on outgoing edges |

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
        "prompt_template": "Triage this issue. Classify severity.\n\n{{start.output.input}}"
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

# Validate before running
graph.validate_or_raise()
```

## Running a Workflow

The `WorkflowEngine` drives execution step by step. Built-in handlers cover start, end, function, condition, and switch nodes. Provide handlers for your app-specific node types:

```python
from roomkit_graph import WorkflowEngine, NodeHandler, NodeResult

class AgentHandler(NodeHandler):
    async def execute(self, node, context, engine):
        # Your agent execution logic here
        result = await call_agent(node.config["agent_id"], context)
        return NodeResult(output=result, status="completed")

class HumanHandler(NodeHandler):
    async def execute(self, node, context, engine):
        return NodeResult(output=None, status="waiting")

# Run to completion
engine = WorkflowEngine(graph, handlers={
    "agent": AgentHandler(),
    "human": HumanHandler(),
    "notification": NotificationHandler(),
})
ctx = await engine.run(trigger_data={"issue_id": "123"})
```

### Step-by-Step Execution

```python
engine = WorkflowEngine(graph, handlers=handlers)
await engine.start(trigger_data={"issue_id": "123"})

while await engine.step():
    print(f"At node: {engine.current_node_id}")
```

### Pause and Resume (Human-in-the-Loop)

When a handler returns `status="waiting"`, the engine pauses. Resume with external input:

```python
# Engine pauses at a human node...
await engine.resume("review", {"action": "approve", "feedback": "Looks good"})

# resume() stores the input and advances past the waiting node.
# Call step() to continue execution.
while await engine.step():
    pass
```

### Persist and Restore Engine State

Serialize engine state for cross-process pause/resume (e.g. human-in-the-loop over HTTP):

```python
# Save
state = engine.to_dict()
# state = {"context": {...}, "current_node_id": "review", "waiting": True}
save_to_db(state)

# Restore later (possibly in a different process)
state = load_from_db()
engine = WorkflowEngine.from_dict(graph, state, handlers=handlers)
await engine.resume("review", {"action": "approve"})
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
        "prompt_template": "Write a blog post about: {{start.output.input.topic}}"
    }),
    Node("review", type="human", config={
        "prompt": "Review this draft. Approve or reject with feedback.",
        "actions": ["approve", "reject"],
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
         condition=Condition.field("review.output.action").equals("approve")),
    Edge("review", "revise",
         condition=Condition.field("review.output.action").equals("reject")),
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

Transform data or run custom logic between steps:

```python
# Data transform
Node("reshape", type="function", config={
    "action": "json_transform",
    "template": {
        "name": "{{extract.output.first}} {{extract.output.last}}",
        "priority": "{{extract.output.tier}}"
    }
})

# Set context values
Node("tag", type="function", config={
    "action": "set_context",
    "values": {"status": "in_progress", "assigned": True}
})

# Delay
Node("wait", type="function", config={
    "action": "delay",
    "duration": "30m"
})

# Custom Python function (registered at runtime)
from roomkit_graph import FunctionRegistry, FunctionHandler

registry = FunctionRegistry()

@registry.function("calculate_priority")
async def calculate_priority(context, config):
    severity = context.get("triage.output.severity")
    tier = context.get("enrich.output.tier")
    return {"priority": "P1" if severity == "critical" and tier == "enterprise" else "P2"}

Node("prioritize", type="function", config={
    "action": "custom",
    "function": "calculate_priority"
})

# Wire registry to the engine
engine = WorkflowEngine(graph, handlers={
    "function": FunctionHandler(registry=registry),
    # ... other handlers
})
```

## Conditions

Serializable condition DSL for edge routing:

```python
# Field comparisons
Condition.field("triage.output.severity").equals("critical")
Condition.field("extract.output.amount").gt(1000)
Condition.field("extract.output.tags").contains("urgent")
Condition.field("extract.output.status").in_(["approved", "accepted"])
Condition.field("review.output.manager").exists()

# Composites
Condition.all_(
    Condition.field("triage.output.severity").equals("critical"),
    Condition.field("triage.output.team").equals("backend"),
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
    {"type": "field", "path": "extract.output.amount", "op": "gt", "value": 1000},
    {"type": "field", "path": "extract.output.category", "op": "eq", "value": "travel"}
]}
{"type": "otherwise"}
```

## Graph Validation

Validate graph structure before execution:

```python
# Returns list of error strings (empty = valid)
errors = graph.validate()

# Or raise GraphValidationError directly
graph.validate_or_raise()
```

Checks performed: single start node, at least one end node, valid edge references, start has no incoming edges, end nodes have no outgoing edges, all nodes reachable from start.

## Cross-Step Context

Steps reference previous outputs with `{{node_id.output.field}}` templates:

```
{{start.output.input}}               # trigger payload
{{start.output.input.title}}         # nested field from trigger
{{triage.output.severity}}           # previous step output
{{draft.output.title}}               # any upstream node's output
```

Resolved at runtime from the workflow context before each step executes.

## How It Maps to RoomKit

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

## Status

Early development. API is not stable.

## License

MIT
