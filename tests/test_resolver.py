"""Tests for TemplateResolver — {{node.output.field}} interpolation."""

from __future__ import annotations

from roomkit_graph import TemplateResolver, WorkflowContext


def _ctx_with_data() -> WorkflowContext:
    ctx = WorkflowContext()
    ctx.set("start", {"title": "Bug report", "body": "Login is broken"})
    ctx.set("triage", {"severity": "critical", "category": "auth"})
    ctx.set("enrich", {"employee": {"name": "Alice", "email": "alice@co.com"}})
    return ctx


def test_resolve_simple():
    ctx = _ctx_with_data()
    resolver = TemplateResolver(ctx)

    result = resolver.resolve("Severity: {{triage.output.severity}}")
    assert result == "Severity: critical"


def test_resolve_multiple_placeholders():
    ctx = _ctx_with_data()
    resolver = TemplateResolver(ctx)

    result = resolver.resolve("{{triage.output.severity}} bug in {{triage.output.category}}")
    assert result == "critical bug in auth"


def test_resolve_nested_path():
    ctx = _ctx_with_data()
    resolver = TemplateResolver(ctx)

    result = resolver.resolve("Assigned to: {{enrich.output.employee.name}}")
    assert result == "Assigned to: Alice"


def test_resolve_full_output():
    ctx = _ctx_with_data()
    resolver = TemplateResolver(ctx)

    result = resolver.resolve("{{start.output.title}}")
    assert result == "Bug report"


def test_resolve_missing_placeholder_raises():
    ctx = _ctx_with_data()
    resolver = TemplateResolver(ctx)

    # Missing path should raise TemplateError
    from roomkit_graph import TemplateError

    import pytest

    with pytest.raises(TemplateError):
        resolver.resolve("{{ghost.output.field}}")


def test_resolve_no_placeholders():
    ctx = _ctx_with_data()
    resolver = TemplateResolver(ctx)

    result = resolver.resolve("Plain text with no templates")
    assert result == "Plain text with no templates"


def test_resolve_dict():
    ctx = _ctx_with_data()
    resolver = TemplateResolver(ctx)

    data = {
        "title": "{{start.output.title}}",
        "severity": "{{triage.output.severity}}",
        "static": "no-change",
    }

    result = resolver.resolve_dict(data)
    assert result["title"] == "Bug report"
    assert result["severity"] == "critical"
    assert result["static"] == "no-change"


def test_resolve_dict_nested():
    ctx = _ctx_with_data()
    resolver = TemplateResolver(ctx)

    data = {
        "employee": {
            "name": "{{enrich.output.employee.name}}",
            "email": "{{enrich.output.employee.email}}",
        }
    }

    result = resolver.resolve_dict(data)
    assert result["employee"]["name"] == "Alice"
    assert result["employee"]["email"] == "alice@co.com"


def test_resolve_value_string():
    ctx = _ctx_with_data()
    resolver = TemplateResolver(ctx)

    result = resolver.resolve_value("{{triage.output.severity}}")
    assert result == "critical"


def test_resolve_value_dict():
    ctx = _ctx_with_data()
    resolver = TemplateResolver(ctx)

    result = resolver.resolve_value({"key": "{{triage.output.severity}}"})
    assert result == {"key": "critical"}


def test_resolve_value_list():
    ctx = _ctx_with_data()
    resolver = TemplateResolver(ctx)

    result = resolver.resolve_value(["{{triage.output.severity}}", "static"])
    assert result == ["critical", "static"]


def test_resolve_value_passthrough():
    ctx = _ctx_with_data()
    resolver = TemplateResolver(ctx)

    assert resolver.resolve_value(42) == 42
    assert resolver.resolve_value(True) is True
    assert resolver.resolve_value(None) is None
