# Luge migration report — streaming mode rename

**Audience:** Luge team, anyone else consuming `roomkit_graph.WorkflowEngine.stream()`.
**Scope:** pre-release polish on an unreleased API. Not tagged yet — no version to pin against.

## What changed

The `StreamMode` literal `"node"` was renamed to `"lifecycle"` to avoid collision with the `node_id` field present on every event payload.

```python
# Before
StreamMode = Literal["values", "updates", "node", "custom"]

# After
StreamMode = Literal["values", "updates", "lifecycle", "custom"]
```

All payloads, helper names, and docs updated accordingly. No change to event shape, ordering, attribution, or the `custom` / `updates` / `values` modes.

## Call sites to update

Search for `"node"` as a string literal in `modes=` tuples and in event routing by `event["mode"]`.

### 1. `modes=` tuples passed to `stream()`

```python
# Before
async for event in engine.stream(trigger_data, modes=("updates", "node")):
    ...

# After
async for event in engine.stream(trigger_data, modes=("updates", "lifecycle")):
    ...
```

### 2. Routing on `event["mode"]`

```python
# Before
if event["mode"] == "node" and event["payload"]["phase"] == "start":
    ...

# After
if event["mode"] == "lifecycle" and event["payload"]["phase"] == "start":
    ...
```

### 3. Downstream serialization / logging

If the Luge cockpit (or any other consumer) persists the raw `event["mode"]` string to a DB, WebSocket wire format, or log line, the stored value will now be `"lifecycle"`. Backfill or dual-read if the old value is present in historical records.

## What did NOT change

- Event shape: still `{"mode", "payload", "node_id", "seq"}`.
- Payload contents for lifecycle events: still `{"phase": "start"|"complete", "node_id": ..., "status": ..., "type": ...}`.
- Per-step ordering: `lifecycle:start` → `custom*` → `lifecycle:complete` → `updates` → `values`.
- ContextVar attribution for `emit()` inside `ParallelHandler` children.
- Multi-stream guard (`RuntimeError` if `stream()` is called while one is active).
- The `engine.emit()` API and its no-op-outside-stream semantics.

## Verification

```bash
cd path/to/luge
rg '"node"' --type py          # find remaining string usages
rg "modes=\([^)]*\bnode\b" --type py  # find modes-tuple usages specifically
```

A grep for the literal `"node"` in a `modes=` or `event["mode"] ==` context is sufficient — other uses of the word `node` in the codebase (e.g. `node_id`, `graph.nodes`, `NodeType`) are unaffected.

## Other polish that shipped alongside

- `drain_writes()` docstring now documents the "no deletions" invariant.
- `stream()` docstring clarifies the initial `values` event is trigger-seeded, not empty.
- New runnable `examples/streaming.py` demonstrating all four modes + handler `emit()`.

## Tagging

Once Luge (or the main consumer) has migrated, `roomkit-graph` will be tagged for a pre-release. Until then, the API is considered in flux.
