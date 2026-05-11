"""Small tool router scaffold for ARC-Neuron MCP integration."""
from __future__ import annotations

from typing import Any, Callable, Dict


class ToolRouter:
    def __init__(self) -> None:
        self._tools: Dict[str, Callable[..., Any]] = {}

    def register(self, name: str, fn: Callable[..., Any]) -> None:
        self._tools[name] = fn

    def call(self, name: str, **kwargs: Any) -> Any:
        if name not in self._tools:
            raise KeyError(f"Tool not registered: {name}")
        return self._tools[name](**kwargs)

    def list_tools(self) -> list[str]:
        return sorted(self._tools)
