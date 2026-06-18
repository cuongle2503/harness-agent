"""Tests for ToolSource, ToolSpec, and ToolInventory."""

from __future__ import annotations

import pytest

from harness_agent.tool_inventory import ToolInventory, ToolSource, ToolSpec


class TestToolSource:
    """Tests for ToolSource enum."""

    def test_builtin_value(self) -> None:
        assert ToolSource.BUILTIN.value == "builtin"

    def test_custom_value(self) -> None:
        assert ToolSource.CUSTOM.value == "custom"

    def test_mcp_value(self) -> None:
        assert ToolSource.MCP.value == "mcp"

    @pytest.mark.parametrize("source", [
        ToolSource.BUILTIN,
        ToolSource.CUSTOM,
        ToolSource.MCP,
    ])
    def test_enum_is_tool_source(self, source: ToolSource) -> None:
        assert isinstance(source, ToolSource)


class TestToolSpec:
    """Tests for ToolSpec dataclass."""

    def test_create_minimal_spec(self) -> None:
        spec = ToolSpec(
            name="test_tool",
            category="Test",
            source=ToolSource.CUSTOM,
        )
        assert spec.name == "test_tool"
        assert spec.category == "Test"
        assert spec.source == ToolSource.CUSTOM
        assert spec.middleware is None
        assert spec.description == ""
        assert spec.enabled is True
        assert spec.notes == ""

    def test_create_full_spec(self) -> None:
        spec = ToolSpec(
            name="web_search",
            category="External API",
            source=ToolSource.CUSTOM,
            middleware=None,
            description="Search the web.",
            enabled=True,
            notes="Needs API key.",
        )
        assert spec.name == "web_search"
        assert spec.description == "Search the web."
        assert spec.notes == "Needs API key."

    def test_create_builtin_spec_with_middleware(self) -> None:
        spec = ToolSpec(
            name="read_file",
            category="File System",
            source=ToolSource.BUILTIN,
            middleware="FilesystemMiddleware",
            description="Read a file.",
        )
        assert spec.source == ToolSource.BUILTIN
        assert spec.middleware == "FilesystemMiddleware"

    def test_equality(self) -> None:
        a = ToolSpec(name="x", category="c", source=ToolSource.CUSTOM)
        b = ToolSpec(name="x", category="c", source=ToolSource.CUSTOM)
        assert a == b

    def test_disabled_spec(self) -> None:
        spec = ToolSpec(
            name="disabled_tool",
            category="Test",
            source=ToolSource.CUSTOM,
            enabled=False,
        )
        assert spec.enabled is False


class TestToolInventoryCreateDefault:
    """Tests for ToolInventory.create_default()."""

    @pytest.fixture
    def inventory(self) -> ToolInventory:
        return ToolInventory.create_default()

    def test_creates_non_empty_inventory(self, inventory: ToolInventory) -> None:
        assert len(inventory.tools) > 0

    def test_has_expected_category_count(self, inventory: ToolInventory) -> None:
        categories = inventory.by_category()
        assert len(categories) >= 4  # File System, Shell, Planning, Delegate, Memory, etc.

    def test_all_builtins_have_middleware(self, inventory: ToolInventory) -> None:
        for tool in inventory.builtins():
            assert tool.middleware is not None, f"{tool.name} has no middleware"

    def test_all_custom_have_no_middleware(self, inventory: ToolInventory) -> None:
        for tool in inventory.custom():
            assert tool.middleware is None, f"{tool.name} should not have middleware"

    def test_custom_tools_count(self, inventory: ToolInventory) -> None:
        custom = inventory.custom()
        assert len(custom) >= 4  # web_search, fetch_url, execute_python, query_database

    def test_all_enabled_by_default(self, inventory: ToolInventory) -> None:
        enabled = inventory.enabled()
        assert len(enabled) == len(inventory.tools)


class TestToolInventoryMethods:
    """Tests for ToolInventory instance methods."""

    @pytest.fixture
    def inventory(self) -> ToolInventory:
        return ToolInventory.create_default()

    def test_by_category_returns_grouped_dict(self, inventory: ToolInventory) -> None:
        result = inventory.by_category()
        assert isinstance(result, dict)
        for tools in result.values():
            assert isinstance(tools, list)
            for t in tools:
                assert isinstance(t, ToolSpec)

    def test_by_category_keys_are_strings(self, inventory: ToolInventory) -> None:
        result = inventory.by_category()
        for key in result:
            assert isinstance(key, str)

    def test_builtins_returns_only_builtin(self, inventory: ToolInventory) -> None:
        builtins = inventory.builtins()
        assert len(builtins) > 0
        for t in builtins:
            assert t.source == ToolSource.BUILTIN

    def test_custom_returns_only_custom(self, inventory: ToolInventory) -> None:
        custom = inventory.custom()
        for t in custom:
            assert t.source == ToolSource.CUSTOM

    def test_enabled_returns_all_by_default(self, inventory: ToolInventory) -> None:
        enabled = inventory.enabled()
        assert len(enabled) == len(inventory.tools)

    def test_summary_returns_non_empty_string(self, inventory: ToolInventory) -> None:
        result = inventory.summary()
        assert isinstance(result, str)
        assert len(result) > 100  # A summary should be substantial
        assert "Tool Inventory Summary" in result

    def test_summary_mentions_categories(self, inventory: ToolInventory) -> None:
        result = inventory.summary()
        categories = inventory.by_category()
        for category in categories:
            assert category in result


class TestToolInventoryEmpty:
    """Tests for empty ToolInventory."""

    def test_empty_inventory_length(self) -> None:
        inv = ToolInventory()
        assert len(inv.tools) == 0

    def test_empty_inventory_by_category(self) -> None:
        inv = ToolInventory()
        assert inv.by_category() == {}

    def test_empty_inventory_builtins(self) -> None:
        inv = ToolInventory()
        assert inv.builtins() == []

    def test_empty_inventory_custom(self) -> None:
        inv = ToolInventory()
        assert inv.custom() == []

    def test_empty_inventory_summary(self) -> None:
        inv = ToolInventory()
        result = inv.summary()
        assert "Tool Inventory Summary" in result
