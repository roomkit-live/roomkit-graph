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
    import pytest

    from roomkit_graph import TemplateError

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


# --- Passthrough mode: single {{path}} returns raw value ---


def test_resolve_value_passthrough_dict():
    """Single placeholder resolving to a dict returns the dict, not str(dict)."""
    ctx = _ctx_with_data()
    resolver = TemplateResolver(ctx)

    result = resolver.resolve_value("{{enrich.output.employee}}")
    assert result == {"name": "Alice", "email": "alice@co.com"}
    assert isinstance(result, dict)


def test_resolve_value_passthrough_int():
    """Single placeholder resolving to an int returns the int."""
    ctx = WorkflowContext()
    ctx.set("calc", {"count": 42})
    resolver = TemplateResolver(ctx)

    result = resolver.resolve_value("{{calc.output.count}}")
    assert result == 42
    assert isinstance(result, int)


def test_resolve_value_passthrough_bool():
    """Single placeholder resolving to a bool returns the bool."""
    ctx = WorkflowContext()
    ctx.set("check", {"passed": True})
    resolver = TemplateResolver(ctx)

    result = resolver.resolve_value("{{check.output.passed}}")
    assert result is True


def test_resolve_value_passthrough_with_whitespace():
    """Whitespace around the placeholder is tolerated."""
    ctx = _ctx_with_data()
    resolver = TemplateResolver(ctx)

    result = resolver.resolve_value("  {{ enrich.output.employee }}  ")
    assert result == {"name": "Alice", "email": "alice@co.com"}


def test_resolve_value_mixed_text_still_stringifies():
    """Placeholder with surrounding text still returns a string."""
    ctx = WorkflowContext()
    ctx.set("calc", {"count": 42})
    resolver = TemplateResolver(ctx)

    result = resolver.resolve_value("Count: {{calc.output.count}}")
    assert result == "Count: 42"
    assert isinstance(result, str)


def test_resolve_value_multiple_placeholders_still_stringifies():
    """Multiple placeholders in one string still returns a string."""
    ctx = _ctx_with_data()
    resolver = TemplateResolver(ctx)

    result = resolver.resolve_value("{{triage.output.severity}} in {{triage.output.category}}")
    assert result == "critical in auth"
    assert isinstance(result, str)


def test_resolve_still_returns_str():
    """resolve() always returns a string, even for single placeholders."""
    ctx = WorkflowContext()
    ctx.set("calc", {"count": 42})
    resolver = TemplateResolver(ctx)

    result = resolver.resolve("{{calc.output.count}}")
    assert result == "42"
    assert isinstance(result, str)


def test_resolve_value_passthrough_missing_raises():
    """Single-placeholder passthrough still raises TemplateError for missing paths."""
    import pytest

    from roomkit_graph import TemplateError

    ctx = WorkflowContext()
    resolver = TemplateResolver(ctx)

    with pytest.raises(TemplateError):
        resolver.resolve_value("{{ghost.output.field}}")
