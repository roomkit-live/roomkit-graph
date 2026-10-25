# roomkit-graph

A workflow graph engine for Python. A workflow is a directed graph of nodes and
edges, stored as plain data (JSON); the engine walks it step by step, routes on
serializable conditions, pauses on steps that wait for a person, and resumes later,
in the same process or another one.

The engine does the walking. The steps that do real work — calling an AI agent,
asking a person, sending a notification — run through handlers: your own, or
those of `roomkit_graph.roomkit`, which run them with
[RoomKit](https://github.com/roomkit-live/roomkit) agents and rooms. The engine
has no runtime dependencies.

## Install

```bash
pip install roomkit-graph              # the engine alone
pip install "roomkit-graph[roomkit]"   # with the RoomKit handlers
```

## What the engine does, what you bring

| roomkit-graph provides | Your application provides |
|---|---|
| Graph model, validation, JSON round-trip | Handlers for `agent`, `human`, `notification`, `orchestration` and any custom node type — or [RoomKit's](#with-roomkit) for the first three |
| Condition DSL for edge routing, also serializable | Where trigger data comes from: webhooks, schedules and events are descriptions, the engine fires nothing |
| `{{...}}` templates over previous step outputs | Where the engine state is stored between a pause and a resume |
| Step-by-step execution, pause and resume | Real delays, retries and timeouts |
| State serialization (`to_dict` / `from_dict`) | |
| Streaming of execution events | |
| Built-in `start`, `end`, `function`, `condition`, `switch`, `log`, `parallel` nodes | |

## Quick start

Two handlers stand in for an AI agent and a notifier; the graph routes on what
the first one returns.

```python
import asyncio

from roomkit_graph import (
    Condition, Edge, Graph, Node, NodeHandler, NodeResult, WebhookTrigger, WorkflowEngine,
)


class TriageHandler(NodeHandler):
    """Stands in for an AI agent: replace the body with your model call."""

    async def execute(self, node, context, engine):
        prompt = engine.template_resolver.resolve(node.config["prompt"])
        severity = "critical" if "down" in prompt.lower() else "low"
        return NodeResult(output={"severity": severity})


class NotifyHandler(NodeHandler):
    """Stands in for Slack, email or SMS: replace the body with your sender."""

    async def execute(self, node, context, engine):
        message = engine.template_resolver.resolve(node.config["template"])
        print(f"[notify] {message}")
        return NodeResult(output={"sent": message})


graph = Graph(id="bug-triage", name="Bug Triage", trigger=WebhookTrigger(source_type="github"))
graph.add_nodes(
    Node("start", type="start"),
    Node("triage", type="agent", config={"prompt": "Classify: {{trigger.title}}"}),
    Node("page", type="notification", config={"template": "Critical: {{trigger.title}}"}),
    Node("end", type="end"),
)
graph.add_edges(
    Edge("start", "triage"),
    Edge("triage", "page", condition=Condition.field("input.severity").equals("critical")),
    Edge("triage", "end", condition=Condition.otherwise()),
    Edge("page", "end"),
)
graph.validate_or_raise()


async def main():
    engine = WorkflowEngine(
        graph, handlers={"agent": TriageHandler(), "notification": NotifyHandler()}
    )
    context = await engine.run(trigger_data={"title": "Checkout is down"})
    print(context.get("triage.output.severity"))  # critical


asyncio.run(main())
```

The graph is data: `graph.to_dict()` gives JSON you can store, version or edit in
a UI, and `Graph.from_dict(...)` reads it back.

## Node types

| Type | Built in | What it does |
|---|---|---|
| `start` | yes | Entry point. The trigger data is its output |
| `end` | yes | Completes the run |
| `function` | yes | `set_context`, `json_transform`, `delay`, `custom` — see [Function nodes](#function-nodes) |
| `condition` | yes | Evaluates one condition, outputs `{"result": bool}`. A missing or invalid condition gives `False` |
| `switch` | yes | Reads a context path, outputs `{"value": ...}` for outgoing edges to match |
| `log` | yes | Copies context paths into its output, for inspection |
| `parallel` | yes | Runs its child nodes concurrently — see [Parallel nodes](#parallel-nodes) |
| `agent` | no | Yours: run an AI agent |
| `orchestration` | no | Yours: run several agents together |
| `human` | no | Yours: ask a person, usually returning `waiting` |
| `notification` | no | Yours: send a message and continue |

Any other string is a valid node type as long as a handler is registered for it.
A node whose type has no handler fails the run with `ExecutionError`.

## Writing a handler

A handler implements one method and returns a `NodeResult`:

```python
class MyHandler(NodeHandler):
    async def execute(self, node, context, engine) -> NodeResult:
        ...
```

- `node.config` holds the node's settings from the graph.
- `engine.template_resolver.resolve(text)` fills `{{...}}` templates from the context.
- `NodeResult.output` is stored as the node's output, readable by later steps.
- `NodeResult.status` is `"completed"` (default, the engine moves on), `"waiting"`
  (the run pauses on this node) or `"failed"` (the run stops with `ExecutionError`,
  carrying `NodeResult.error`).

Handlers are passed per engine and override the built-in ones for the same type:
`WorkflowEngine(graph, handlers={"agent": MyHandler()})`.

## Context and templates

Each node's output is stored under `<node_id>.output`. Templates and conditions
read it with dot paths:

```
{{triage.output.severity}}       # a field of a previous step's output
{{start.output.input.title}}     # the trigger data, long form
```

Three reserved prefixes shorten the common reads:

| Prefix | Reads |
|---|---|
| `trigger.<path>` | The trigger data (`trigger.title`) |
| `steps.<id>.<path>` | A node's output without the `output` hop (`steps.triage.severity`) |
| `input.<path>` | In a node's templates: the output of the node the run came from — the branch taken at a merge, what sent the run back in a loop. In a node's outgoing edge conditions: that node's own output |

A node named `trigger`, `steps` or `input` is shadowed by these prefixes.

A path that is not there raises `TemplateError`. When it may legitimately be
missing — a step on the other branch, a loop's first pass — `default(...)` names
what stands in for it, as a JSON value:

```
{{steps.page.text | default("not paged")}}
{{input.feedback | default("none yet")}}
{{steps.count.total | default(0)}}
```

`resolve()` always returns a string. `resolve_value()` keeps the type when the
template is exactly one placeholder: `"{{triage.output.tags}}"` returns the list,
`"Tags: {{triage.output.tags}}"` returns a string.

## Edges and conditions

```python
Condition.field("triage.output.severity").equals("critical")
Condition.field("triage.output.severity").not_equals("low")
Condition.field("extract.output.amount").gt(1000)          # also .lt()
Condition.field("extract.output.tags").contains("urgent")
Condition.field("extract.output.status").in_(["approved", "accepted"])  # also .not_in()
Condition.field("review.output.manager").exists()

Condition.all_(cond_a, cond_b)
Condition.any_(cond_a, cond_b)
Condition.not_(cond_a)
Condition.otherwise()
```

When a node has several outgoing edges, the engine picks, in this order:

1. the first conditional edge, in definition order, whose condition is true;
2. otherwise the edge with no condition;
3. otherwise the `Condition.otherwise()` edge.

If none applies, the run stops with `NoValidTransitionError`. A node other than
`end` with no outgoing edge completes the run.

Edges may point back to an earlier node (a revise → review loop). The engine has
no iteration limit; a loop ends when a condition sends the run elsewhere.

Conditions serialize with the graph:

```json
{"type": "field", "path": "triage.output.severity", "op": "eq", "value": "critical"}
{"type": "all", "conditions": [
    {"type": "field", "path": "extract.output.amount", "op": "gt", "value": 1000},
    {"type": "field", "path": "extract.output.category", "op": "eq", "value": "travel"}
]}
{"type": "otherwise"}
```

## Pause and resume

A handler that returns `status="waiting"` pauses the run on its node. The engine
state serializes to JSON, so the answer can arrive hours later in another process:

```python
class ApprovalHandler(NodeHandler):
    """Asks a person, then pauses: the answer comes back through resume()."""

    async def execute(self, node, context, engine):
        send_question(engine.template_resolver.resolve(node.config["question"]))
        return NodeResult(status="waiting")


engine = WorkflowEngine(graph, handlers=handlers)
await engine.run(trigger_data={"amount": 120})
engine.waiting                    # True: paused on engine.current_node_id, "approve"
save(engine.to_dict())            # {"context": {...}, "current_node_id": ..., "waiting": True}

# Later, possibly in another process
engine = WorkflowEngine.from_dict(graph, load(), handlers=handlers)
await engine.resume("approve", {"action": "approve"})
while await engine.step():
    pass
```

`resume(node_id, data)` stores `data` as the waiting node's output and moves to
the next node; edges leaving the waiting node route on it
(`Condition.field("approve.output.action").equals("approve")`).

`engine.start()` then `engine.step()` run one node at a time; `engine.run()` is
both, until the run completes or pauses.

## Seeing what a run does

`verbose()` prints every run's progress on stderr as it happens — each step,
each agent's turn with its duration, tokens and tools, each message sent, each
pause:

```python
from roomkit_graph import verbose

verbose()                 # content=False hides prompts, answers and message texts
```

```
[research-crew bec462ed] ▶ research (agent)
[research-crew bec462ed]   researcher · Senior research analyst · working…
[research-crew bec462ed]   asked: Research AI agents in customer support. List the ten most…
[research-crew bec462ed]   researcher answered · 12.8 s · 84 → 1,596 tokens
[research-crew bec462ed]   answer: **AI agents in customer support: ten things that matter** 1…
[research-crew bec462ed] ✓ research · 13.8 s
[support-triage b3da3aaf] ⏸ page · waiting for an answer
```

`verbose(messages=True)` prints each agent's text as the agent writes it,
instead of its answer cut to one line, a `✎` line per line of text:

```
[research-crew d5c72753]   researcher · Senior research analyst · working…
[research-crew d5c72753]   ✎ **AI agents in customer support: ten things that matter**
[research-crew d5c72753]   ✎ 1. **Fact: Assistive AI has the best evidence.** A large NBER study…
```

It reads the `TEXT_DELTA` ephemerals RoomKit publishes in a delegated task's
child room, for an agent that asks for it; for another agent, no text arrives
and nothing else changes:

```python
kit.register_channel(Agent("writer", provider=provider, publish_text_deltas=True))
```

Each line names its graph and run (`engine.run_id`), so runs that interleave
stay apart. The `roomkit_graph` logger then prints there only; `close()` on the
handler `verbose()` returns gives it back.

The same records go to the `roomkit_graph` loggers for your own handlers: steps,
durations and pauses at INFO, a failed node at WARNING. What a person or a model
wrote — a prompt, an answer, a message — is logged at DEBUG only. Each record
carries its fields in `record.roomkit_graph` (`event`, `run`, `graph`, `node`,
and the event's own: `seconds`, `tokens_in`, `tools`...).

## Streaming execution events

`engine.stream()` yields typed events as the run progresses — for dashboards,
webhooks or audit logs. Pick one or more modes:

| Mode | Emitted when | Payload |
|---|---|---|
| `values` | Before start and after each step | Full context snapshot |
| `updates` | After each step | Outputs written that step, keyed by node id |
| `lifecycle` | Before and after each node | `{phase, node_id, status}` (status: `completed` / `waiting` / `failed`) |
| `custom` | When a handler calls `engine.emit(...)` | Handler-defined payload |

```python
async for event in engine.stream(trigger_data, modes=("updates", "lifecycle")):
    if event["mode"] == "lifecycle" and event["payload"]["phase"] == "start":
        print(f"→ {event['node_id']}")
    elif event["mode"] == "updates":
        await websocket.send_json(event["payload"])
```

A handler reports progress inside its node with `engine.emit(payload)`; outside
`stream()` the call does nothing, so the same handler works in both modes.

When a handler fails, a last `lifecycle` event with `status="failed"` is yielded
before `ExecutionError` propagates. When a node waits, the stream ends; after
`resume(...)`, start a new `stream()`.

## Parallel nodes

A `parallel` node runs the nodes that name it as `parent`, concurrently, and
continues once all of them are done:

```python
graph.add_nodes(
    Node("checks", type="parallel"),
    Node("security", type="agent", config={...}, parent="checks"),
    Node("compliance", type="agent", config={...}, parent="checks"),
    Node("summarize", type="agent", config={...}),
)
graph.add_edges(Edge("analyze", "checks"), Edge("checks", "summarize"))

# After the parallel node:
#   security.output    → that child's output
#   checks.output      → {"security": ..., "compliance": ...}
```

Children are run by their parallel node only: give them no edges. If one child
fails, the parallel node fails. A child cannot pause: `waiting` inside a parallel
node is a failure. Waiting for the first child only (`join: "any"`) is not
implemented.

## Function nodes

```python
# Write fixed values as the node's output
Node("tag", type="function", config={
    "action": "set_context", "values": {"status": "in_progress"},
})

# Build a structure from templates (types kept for single placeholders)
Node("reshape", type="function", config={
    "action": "json_transform",
    "template": {"name": "{{extract.output.first}} {{extract.output.last}}"},
})

# Call your own function by name
Node("prioritize", type="function", config={
    "action": "custom", "function": "calculate_priority",
})
```

`custom` functions are looked up in `graph_registry`:

```python
from roomkit_graph import graph_registry


@graph_registry.function("calculate_priority")
async def calculate_priority(context, config):
    return {"priority": "P1" if context.get("trigger.tier") == "enterprise" else "P2"}
```

To keep a set of functions apart — per tenant, per test — pass your own
registry instead: `handlers={"function": FunctionHandler(registry=FunctionRegistry())}`.

The built-in `delay` action does not wait: it outputs `{"delayed": "<duration>"}`.
A real delay — usually a pause the application resumes later — belongs in your
own handler.

## Triggers

`WebhookTrigger`, `ScheduledTrigger`, `EventTrigger` and `ManualTrigger` describe
how a workflow is meant to start, and serialize with the graph. The engine does
not listen to anything: your application reads `graph.trigger`, receives the
webhook or runs the schedule, and calls `engine.run(trigger_data=...)`.

## Validation

`graph.validate()` returns a list of errors (empty when valid);
`graph.validate_or_raise()` raises `GraphValidationError`. It checks: exactly one
`start` node, at least one `end` node, edges pointing to existing nodes, no edge
into `start`, no edge out of an `end`, every node reachable from `start`.

## With RoomKit

`roomkit_graph.roomkit` (`pip install "roomkit-graph[roomkit]"`) runs nodes with
[RoomKit](https://github.com/roomkit-live/roomkit). Every run works in a room,
named by its trigger data's `room_id`:

| Node | Config | What happens |
|---|---|---|
| `agent` | `agent`, `prompt`, optional `structured`, `room` | The RoomKit agent works on the prompt in a child room of the run's room; the output is `{"text": ...}`, or with `structured` the agent's `submit_result` call (`{"status", "summary", "data", ...}`) |
| `notification` | `text`, optional `room` | The text is written into the room in the application's name, so its transports deliver it — an SMS to the room's correspondent — and none of its agents answers it |
| `human` | `text`, optional `room` | Sent the same way, then the run pauses until the answer arrives in that room |

```python
from roomkit_graph.roomkit import RoomRuns, room_handlers

runs = RoomRuns()
engine = WorkflowEngine(graph, handlers=room_handlers(kit))
await runs.start(engine, {"room_id": room.id, "topic": "..."})

# Where your app receives a message (an SMS webhook, say):
result = await kit.process_inbound(message)
await runs.answer(result.event.room_id, {"text": message.content.body})
```

`RoomRuns.answer()` resumes the run paused on that room, if any; when several
wait there, the one that asked first. It holds paused runs in memory; to survive
a restart, store `engine.to_dict()` and rebuild with `WorkflowEngine.from_dict()`.

The workflow writes in a room as the application, with RoomKit's `kit.post()`:
the room's transports deliver its messages, they solicit none of the room's
agents, and each one's metadata names the graph, run and node that sent it
(`{"workflow": {"graph": ..., "run": ..., "node": ...}}`). A room a
`Discussion` runs takes them like any other.

## Examples

Runnable examples are in [`examples/`](examples/):

```bash
uv run python examples/graph_definition.py   # build, validate, serialize
uv run python examples/workflow_engine.py    # conditions, templates, execution
uv run python examples/streaming.py          # the four stream modes and emit()

# With RoomKit agents: uv sync --extra examples, and ANTHROPIC_API_KEY set
uv run python examples/research_crew.py "AI agents in customer support"
uv run python examples/support_triage.py     # SMS in, page the on-call, SMS out
uv run python examples/review_loop.py        # draft, editor's feedback by SMS, until OK
uv run python examples/order_desk.py         # agents with their own tools and a skill
```

## Status

Alpha. The API may change between minor versions until 1.0; breaking changes are
listed in the [changelog](CHANGELOG.md).

## License

MIT
