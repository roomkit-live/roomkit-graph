from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any


class FunctionRegistry:
    """Registry for custom Python functions used by FunctionNode(action="custom").

    Functions are registered by name and looked up at runtime during execution.
    """

    def __init__(self) -> None:
        self._functions: dict[str, Callable[..., Coroutine[Any, Any, Any]]] = {}

    def function(self, name: str) -> Callable:
        """Decorator to register a custom function by name.

        Usage:
            @registry.function("calculate_priority")
            async def calculate_priority(ctx):
                ...
        """
        raise NotImplementedError

    def register(self, name: str, func: Callable[..., Coroutine[Any, Any, Any]]) -> None:
        """Register a function programmatically."""
        raise NotImplementedError

    def get(self, name: str) -> Callable[..., Coroutine[Any, Any, Any]]:
        """Look up a registered function by name. Raises KeyError if not found."""
        raise NotImplementedError

    def has(self, name: str) -> bool:
        """Check if a function is registered."""
        raise NotImplementedError

    def list(self) -> list[str]:
        """Return all registered function names."""
        raise NotImplementedError
