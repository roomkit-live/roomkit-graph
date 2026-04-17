# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
