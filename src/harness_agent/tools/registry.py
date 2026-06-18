"""ToolRegistry — central registry for MCP-compatible tools."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from harness_agent.core.exceptions import ToolExecutionError, ToolNotFoundError


class ToolRegistry:
    """Central registry for tools.

    Wraps a dict[str, BaseTool] with consistent error handling
    per ADR-009 and ADR-010.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool. Duplicate names are overwritten silently.

        Args:
            tool: A BaseTool instance to register.

        Raises:
            TypeError: If tool is not a BaseTool instance.
        """
        if not isinstance(tool, BaseTool):
            raise TypeError(
                f"Expected BaseTool instance, got {type(tool).__name__}"
            )
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        """Get a tool by name.

        Args:
            name: The tool name to look up.

        Returns:
            The registered BaseTool instance.

        Raises:
            ToolNotFoundError: If the tool is not found.
        """
        if name not in self._tools:
            raise ToolNotFoundError(name)
        return self._tools[name]

    def list_tools(self) -> list[dict[str, Any]]:
        """List all registered tools as JSON-serializable schemas.

        Returns:
            List of tool schemas with name, description, and parameters.
        """
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameters": (
                    t.args_schema.model_json_schema()  # type: ignore[union-attr]
                    if t.args_schema
                    else {}
                ),
            }
            for t in self._tools.values()
        ]

    def invoke_tool(self, name: str, **kwargs: Any) -> Any:
        """Invoke a registered tool by name.

        Args:
            name: The tool name.
            **kwargs: Arguments passed to the tool's invoke method.

        Returns:
            The tool's return value.

        Raises:
            ToolNotFoundError: If the tool is not found.
            ToolExecutionError: If the tool execution fails.
        """
        tool = self.get(name)
        try:
            return tool.invoke(kwargs)
        except Exception as exc:
            raise ToolExecutionError(name, exc) from exc

    @classmethod
    def from_inventory(cls, inventory: Any) -> ToolRegistry:
        """Create a registry from a ToolInventory instance.

        This is a forward-looking classmethod for integration with the
        existing ToolInventory from tools.py. In Phase 3, it returns
        an empty registry; full integration is deferred to Phase 4+.

        Args:
            inventory: A ToolInventory instance (unused in Phase 3).

        Returns:
            A new, empty ToolRegistry.
        """
        return cls()

    def __len__(self) -> int:
        return len(self._tools)
