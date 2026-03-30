"""Tests for FunctionRegistry — custom function registration and lookup."""

from __future__ import annotations

import pytest

from roomkit_graph import FunctionRegistry


def test_register_and_get():
    registry = FunctionRegistry()

    async def my_func(ctx):
        return {"result": "ok"}

    registry.register("my_func", my_func)
    assert registry.get("my_func") is my_func


def test_decorator_registration():
    registry = FunctionRegistry()

    @registry.function("calculate")
    async def calculate(ctx):
        return {"value": 42}

    assert registry.has("calculate")
    assert registry.get("calculate") is calculate


def test_get_missing_raises():
    registry = FunctionRegistry()

    with pytest.raises(KeyError):
        registry.get("nonexistent")


def test_has():
    registry = FunctionRegistry()

    async def f(ctx):
        pass

    registry.register("f", f)

    assert registry.has("f") is True
    assert registry.has("g") is False


def test_list_functions():
    registry = FunctionRegistry()

    async def a(ctx):
        pass

    async def b(ctx):
        pass

    registry.register("alpha", a)
    registry.register("beta", b)

    names = registry.list()
    assert sorted(names) == ["alpha", "beta"]


def test_list_empty():
    registry = FunctionRegistry()
    assert registry.list() == []


def test_register_duplicate_overwrites():
    registry = FunctionRegistry()

    async def v1(ctx):
        return 1

    async def v2(ctx):
        return 2

    registry.register("func", v1)
    registry.register("func", v2)

    assert registry.get("func") is v2
