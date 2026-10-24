# roomkit-graph Examples

Runnable examples demonstrating roomkit-graph features. Each file has a docstring
explaining what it does and a run command.

```bash
# Run any example:
uv run python examples/<example>.py
```

## Graph Definition

| Example | Feature | Description |
|---------|---------|-------------|
| `graph_definition.py` | Graph, Validation, Serialization | Build a bug triage workflow with branching, validate, serialize to JSON and round-trip |
| `workflow_engine.py` | Conditions, Templates, Execution | Evaluate conditions, resolve templates, run linear and branching workflows |
| `streaming.py` | Observer-side streaming | Watch a workflow via `stream()` in all four modes + handler `emit()` for intra-node progress |

## With RoomKit agents

These run real models: `uv sync --extra examples`, then set `ANTHROPIC_API_KEY`.

| Example | Feature | Description |
|---------|---------|-------------|
| `research_crew.py` | Agents in sequence | The CrewAI quickstart: a researcher, then a writer, on a topic you pass |
| `support_triage.py` | SMS in and out, structured result, pause on a person | A customer's SMS starts a run; urgent ones page the on-call engineer by SMS and wait for their reply |
| `review_loop.py` | A loop, `input` on the way back, `default(...)` | A writer drafts, the editor answers by SMS, and the run loops until they reply OK |

They run their nodes through `roomkit_graph.roomkit`.
