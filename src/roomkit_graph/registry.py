from __future__ import annotations

from collections.abc import Callable
from typing import Any


class FunctionRegistry:
    """Registry for custom Python functions used by FunctionNode(action="custom").

    Functions are registered by name and looked up at runtime during execution.
    Accepts both sync and async callables — sync functions are auto-wrapped at execution time.
    """

    def __init__(self) -> None:
        self._functions: dict[str, Callable[..., Any]] = {}

    def function(self, name: str) -> Callable:
        """Decorator to register a custom function by name.

        Usage:
            @registry.function("calculate_priority")
            async def calculate_priority(ctx):
                ...
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._functions[name] = func
            return func

        return decorator

    def register(self, name: str, func: Callable[..., Any]) -> None:
        """Register a function programmatically."""
        self._functions[name] = func

    def get(self, name: str) -> Callable[..., Any]:
        """Look up a registered function by name. Raises KeyError if not found."""
        return self._functions[name]

    def has(self, name: str) -> bool:
        """Check if a function is registered."""
        return name in self._functions

    def list(self) -> list[str]:
        """Return all registered function names."""
        return list(self._functions.keys())
