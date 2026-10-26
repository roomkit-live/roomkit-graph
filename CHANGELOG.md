# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] — 2026-10-25

### Added
- A run acts for the organization its trigger data's `organization_id` names:
  `agent`, `notification` and `human` nodes pass it to RoomKit (`delegate`,
  `post`, and the child room's `subscribe_room`), so a node aimed at another
  organization's room raises `RoomNotFoundError` and nothing is asked or
  sent. A run that names none reaches any room, as before.

### Fixed
- Only the start node may be named `start`: a run's context keeps its
  trigger data under that id (`trigger.*`, `steps.start`), and another node
  named so replaced it with its own output, the run's room and organization
  included. `Graph.validate()` reports it, and `WorkflowEngine.start()` and
  `from_dict()` refuse such a graph, validated or not; `resume()` refuses the
  id `start`, which no node waits under.

## [0.3.0] — 2026-10-25

### Changed
- Requires RoomKit 0.109.0 or later (`roomkit>=0.109.0` in the `roomkit` and
  `examples` extras), whose agents publish their text as `TEXT_DELTA`.
- **Breaking:** `input.<...>` in a node's templates is the output of the node
  the run came from. A node with several incoming edges got
  `{source_id: output}` for every one of them, `None` for the branches not
  taken, so a merge or a loop could not read what brought the run there.
  Engine state records it as `previous_node_id`; state saved without it
  restores with the former reading. Migrate `{{input.<source_id>.x}}` on a
  merge node to `{{input.x}}`, or to `{{steps.<source_id>.x}}`.
- `WorkflowEngine.template_resolver` is typed `TemplateResolver`: it never
  returned `None`, and handlers had to narrow it.
- README rewritten to describe what the engine does and what handlers bring:
  triggers start nothing, the built-in `delay` does not wait, parallel nodes
  join on all children only.
- A commit-msg hook and a CI check keep downstream application names out of
  commit messages.

### Added
- `examples/order_desk.py`: agent nodes whose agents carry their own tools,
  and one an Agent Skill (`examples/skills/refund-policy/SKILL.md`): the graph
  names the agents, RoomKit runs their tools and skills in each task's room.
- `verbose(messages=True)`: each agent's text printed as the agent writes it.
  `AgentHandler` subscribes to the delegated task's child room from
  `ON_TASK_DELEGATED` when content is logged, and logs each `TEXT_DELTA` as an
  `agent.text` record at DEBUG. RoomKit publishes them for an agent created
  with `publish_text_deltas=True`, as the examples' agents are; for another
  agent none arrives.
- `verbose()`: every run's progress on stderr as it happens — each step, each
  agent's turn with its duration, tokens (cache included) and tools, each
  message sent, each pause and resume — one line each, prefixed by graph and
  run. `content=False` hides prompts, answers and message texts.
- Run logging on the `roomkit_graph` loggers: steps, durations and pauses at
  INFO, a failed node at WARNING, what a person or a model wrote at DEBUG
  only. Each record carries its fields in `record.roomkit_graph`.
- `WorkflowEngine.run_id`: a short id, new at each `start()` and kept in
  engine state, naming the run in logs.
- `{{path | default(<JSON value>)}}` in templates: what stands in for a path
  that is not there, instead of `TemplateError` — a step on the other branch,
  a loop's first pass.
- `roomkit_graph.roomkit`, behind the `roomkit` extra: `agent`, `notification`
  and `human` nodes run with RoomKit agents and rooms (`room_handlers(kit)`),
  `RoomRuns` resuming a run paused on a person when their answer arrives in
  the room. `notification` and `human` nodes write as the application, with
  RoomKit's `kit.post()`: the room's transports deliver the message, no
  agent of the room answers it, and its metadata names the graph, run and
  node under `workflow`.
- `WorkflowEngine.waiting` — whether the run is paused on `current_node_id`
  until `resume()`. It was only readable through `to_dict()["waiting"]`.
- Examples run by RoomKit agents, behind the `examples` extra:
  `research_crew.py` (a researcher then a writer, the CrewAI quickstart),
  `support_triage.py` (an SMS starts a run, urgent ones page the on-call by SMS
  and wait for the reply) and `review_loop.py` (drafts and the editor's
  feedback by SMS, until approved).

### Fixed
- A `custom` function node run by the default `FunctionHandler` looks up
  `graph_registry`. It failed with "No function registry configured", so a
  function registered on the exported `graph_registry` was never found.

### Removed
- The `roomkit` runtime dependency: no module imported it since the
  `GraphOrchestration` removal, and installing `roomkit-graph` pulled RoomKit
  in. RoomKit is now the `roomkit` extra, for `roomkit_graph.roomkit` only.
- The `httpx` extra: nothing in the package uses it.

## [0.2.0] — 2026-07-18

### Added
- Native reserved scope prefixes in `WorkflowContext.get()`, resolved at the
  single point shared by `TemplateResolver` and edge-condition evaluation:
  - `input.<...>` — the "current input" the engine sets per step (a node's
    predecessor output before it runs; the routing node's own output before its
    outgoing edges are evaluated).
  - `steps.<id>.<...>` — a node's stored output directly (no `output` hop);
    `steps.start` is the unwrapped trigger payload.
  - `trigger.<...>` — alias for `steps.start`.
  These now resolve identically in templates (`{{input.x}}`) and in edge
  conditions (`Condition.field("input.skip")`), so a condition edge can route on
  trigger/predecessor data without a helper node. `{{node.output.field}}` paths
  are unchanged. A node literally named `input`/`steps`/`trigger` is shadowed by
  the reserved prefix.

## [0.1.0] — 2026-05-22

First public release. No code changes from `0.1.0a2`; this cut drops
the alpha-N suffix and graduates the Trove classifier from Pre-Alpha
to Alpha now that the engine, streaming surface, persistence, and
built-in handler set are feature-complete and exercised by the full
test suite, examples, and CI.

### Changed
- README "Status" section rephrased — Alpha, with the API allowed to
  evolve between minor versions until 1.0.
- Trove classifier `Development Status` → `3 - Alpha`.

### Fixed
- `examples/graph_definition.py` template path corrected from
  `{{start.input}}` to `{{start.output.input}}` to match the engine's
  context layout (other examples and the README were already correct).
- `NodeHandler` and `WorkflowEngine` docstrings list the full set of
  built-in handlers (start, end, function, condition, switch, log,
  parallel) instead of only the first three.
- `CONTRIBUTING.md` checklists rewritten to reference the actual file
  layout (single `handlers.py`, flat `tests/`, condition operators on
  `Condition._evaluate_field`).

## [0.1.0a2] — 2026-04-17

### Added
- `WorkflowEngine.stream()` — async iterator over typed execution events, with four modes: `values` (full snapshots), `updates` (per-step deltas), `lifecycle` (per-node start/complete), and `custom` (handler-emitted).
- `WorkflowEngine.emit(payload)` — handler-side API to surface intra-node progress. No-op outside a `stream()` context. Uses a task-local `ContextVar` so events inside `ParallelHandler` children attribute to the correct child, not the parallel parent.
- `WorkflowContext.drain_writes()` — transient write journal used by `stream()` to compute `updates` deltas in O(writes) rather than snapshotting the full context each step.
- `ParallelHandler` — built-in handler for parallel nodes, runs children concurrently via `asyncio.TaskGroup` and aggregates results under the parallel node's id.
- Structured passthrough in `TemplateResolver` — resolves nested dict/list values recursively.
- Runnable `examples/streaming.py` demonstrating all four modes and `emit()` from a handler.

### Changed
- **Breaking:** `StreamMode` literal `"node"` renamed to `"lifecycle"` to avoid collision with the `node_id` field present on every event payload. No other shape changes. See commit `989530c` for the migration snippet.
- First-match-wins edge resolution is now the canonical and documented semantics (conditional edges evaluated in definition order; first matching condition wins).

### Fixed
- `WorkflowContext.from_dict()` uses `deepcopy` to match the `to_dict()` contract so round-tripping produces a fully detached copy.
- `LogHandler` skips empty path strings instead of dumping the full context for a whitespace-only entry.

## [0.1.0a1] — earlier pre-alpha

Initial pre-alpha: graph/node/edge model, conditions with composites (AND/OR/NOT), template resolution, `WorkflowEngine` with `start`/`step`/`run`/`resume`, persistence via `to_dict`/`from_dict`, built-in handlers (start, end, function, condition, switch, log), triggers, and CI.
