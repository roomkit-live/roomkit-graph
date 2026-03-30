"""Smoke test — verifies the package imports and basic instantiation."""

from __future__ import annotations


def test_import_public_api():
    from roomkit_graph import (
        NodeType,
        __version__,
    )

    assert __version__
    assert NodeType.AGENT == "agent"
    assert NodeType.START == "start"
    assert NodeType.END == "end"
    assert NodeType.HUMAN == "human"
    assert NodeType.NOTIFICATION == "notification"
    assert NodeType.FUNCTION == "function"
    assert NodeType.PARALLEL == "parallel"
    assert NodeType.ORCHESTRATION == "orchestration"


def test_node_type_coercion():
    """Node accepts string type and coerces to NodeType enum."""
    from roomkit_graph import Node, NodeType

    node = Node("my-node", type="agent")
    assert node.type == NodeType.AGENT
    assert node.id == "my-node"


def test_trigger_types_enforced():
    """Trigger subclasses enforce their type field via __post_init__."""
    from roomkit_graph import (
        EventTrigger,
        ManualTrigger,
        ScheduledTrigger,
        WebhookTrigger,
    )

    assert WebhookTrigger().type == "webhook"
    assert ScheduledTrigger().type == "scheduled"
    assert EventTrigger().type == "event"
    assert ManualTrigger().type == "manual"

    # Type is enforced — cannot be overridden
    assert WebhookTrigger(source_type="github").type == "webhook"


def test_error_hierarchy():
    from roomkit_graph import (
        ConditionError,
        ExecutionError,
        GraphError,
        GraphValidationError,
        NoValidTransitionError,
        TemplateError,
    )

    assert issubclass(GraphValidationError, GraphError)
    assert issubclass(ConditionError, GraphError)
    assert issubclass(TemplateError, GraphError)
    assert issubclass(ExecutionError, GraphError)
    assert issubclass(NoValidTransitionError, ExecutionError)


def test_graph_registry_is_singleton():
    from roomkit_graph import FunctionRegistry, graph_registry

    assert isinstance(graph_registry, FunctionRegistry)
