# roomkit-graph Examples

Runnable examples demonstrating roomkit-graph features. Each file is self-contained
with a docstring explaining what it does and a run command.

```bash
# Run any example:
uv run python examples/<example>.py
```

## Graph Definition

| Example | Feature | Description |
|---------|---------|-------------|
| `graph_definition.py` | Graph, Validation, Serialization | Build a bug triage workflow with branching, validate, serialize to JSON and round-trip |
| `workflow_engine.py` | Conditions, Templates, Execution | Evaluate conditions, resolve templates, run linear and branching workflows |
