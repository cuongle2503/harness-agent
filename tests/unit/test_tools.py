"""Tests for ToolRegistry and custom tools."""

import pytest
from langchain_core.tools import BaseTool

from harness_agent.core.exceptions import (
    HarnessError,
    ToolExecutionError,
    ToolNotFoundError,
)
from harness_agent.tools.registry import ToolRegistry


class TestToolRegistryRegister:
    """Tests for ToolRegistry.register()."""

    def test_register_tool_adds_to_registry(
        self, empty_registry: ToolRegistry, sample_tool: BaseTool
    ) -> None:
        empty_registry.register(sample_tool)
        assert len(empty_registry) == 1
        assert empty_registry.get(sample_tool.name) is sample_tool

    def test_register_multiple_tools(
        self, empty_registry: ToolRegistry, sample_tool: BaseTool, sample_search_tool: BaseTool
    ) -> None:
        empty_registry.register(sample_tool)
        empty_registry.register(sample_search_tool)
        assert len(empty_registry) == 2

    def test_register_duplicate_overwrites(
        self, registry_with_tools: ToolRegistry, sample_tool: BaseTool
    ) -> None:
        assert len(registry_with_tools) == 1
        # Re-registering the same name should overwrite
        registry_with_tools.register(sample_tool)
        assert len(registry_with_tools) == 1

    def test_register_non_base_tool_raises(
        self, empty_registry: ToolRegistry
    ) -> None:
        with pytest.raises(TypeError, match="BaseTool"):
            empty_registry.register("not_a_tool")  # type: ignore[arg-type]

    def test_empty_registry_length(self, empty_registry: ToolRegistry) -> None:
        assert len(empty_registry) == 0


class TestToolRegistryGet:
    """Tests for ToolRegistry.get()."""

    def test_get_registered_tool_returns_tool(
        self, registry_with_tools: ToolRegistry, sample_tool: BaseTool
    ) -> None:
        result = registry_with_tools.get("mock_tool")
        assert result is sample_tool

    def test_get_nonexistent_raises_tool_not_found(
        self, empty_registry: ToolRegistry
    ) -> None:
        with pytest.raises(ToolNotFoundError) as exc_info:
            empty_registry.get("nonexistent")
        assert exc_info.value.tool_name == "nonexistent"
        assert "[FATAL]" in str(exc_info.value)

    def test_get_nonexistent_is_harness_error(
        self, empty_registry: ToolRegistry
    ) -> None:
        with pytest.raises(HarnessError):
            empty_registry.get("nonexistent")


class TestToolRegistryListTools:
    """Tests for ToolRegistry.list_tools()."""

    def test_list_empty_registry(self, empty_registry: ToolRegistry) -> None:
        schemas = empty_registry.list_tools()
        assert schemas == []

    def test_list_returns_schemas(
        self, registry_with_tools: ToolRegistry
    ) -> None:
        schemas = registry_with_tools.list_tools()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "mock_tool"
        assert "description" in schemas[0]
        assert "parameters" in schemas[0]

    def test_list_tools_name_matches(
        self, registry_with_tools: ToolRegistry, sample_search_tool: BaseTool
    ) -> None:
        registry_with_tools.register(sample_search_tool)
        schemas = registry_with_tools.list_tools()
        names = {s["name"] for s in schemas}
        assert "mock_tool" in names
        assert "web_search" in names


class TestToolRegistryInvokeTool:
    """Tests for ToolRegistry.invoke_tool()."""

    def test_invoke_registered_tool(
        self, registry_with_tools: ToolRegistry
    ) -> None:
        result = registry_with_tools.invoke_tool("mock_tool", param="hello")
        assert result == "mock_result: hello"

    def test_invoke_tool_not_found_raises(
        self, empty_registry: ToolRegistry
    ) -> None:
        with pytest.raises(ToolNotFoundError):
            empty_registry.invoke_tool("nonexistent", param="test")

    def test_invoke_tool_execution_error_wraps(
        self, empty_registry: ToolRegistry
    ) -> None:
        class FailingTool(BaseTool):
            name: str = "failing_tool"
            description: str = "Always fails"
            args_schema: type = type(
                "Args", (object,), {"model_json_schema": lambda cls=None: {}}
            )

            def _run(self, **kwargs: object) -> str:
                raise RuntimeError("simulated failure")

        empty_registry.register(FailingTool())
        with pytest.raises(ToolExecutionError) as exc_info:
            empty_registry.invoke_tool("failing_tool")
        assert exc_info.value.tool_name == "failing_tool"
        assert isinstance(exc_info.value.original_error, RuntimeError)
        assert "[ERROR]" in str(exc_info.value)


