"""Adversarial robustness tests for agent components."""


import pytest
from langchain_core.messages import HumanMessage

from harness_agent.core.agent import HarnessAgent
from harness_agent.core.exceptions import (
    HarnessError,
    ToolExecutionError,
    ToolNotFoundError,
)
from harness_agent.memory.hybrid_memory import HybridMemory
from harness_agent.tools.registry import ToolRegistry


class TestAgentRobustMalformedInput:
    """Agent handles malformed or unexpected inputs gracefully."""

    def test_empty_input_dict(self, harness_agent: HarnessAgent) -> None:
        """Agent should handle empty input dict."""
        result = harness_agent.invoke({})
        assert "messages" in result

    def test_none_messages_list(self, harness_agent: HarnessAgent) -> None:
        """Agent should handle missing 'messages' key."""
        result = harness_agent.invoke({"other_key": "value"})
        assert "messages" in result

    def test_empty_messages_list(self, harness_agent: HarnessAgent) -> None:
        """Agent should handle empty messages list."""
        result = harness_agent.invoke({"messages": []})
        assert "messages" in result
        assert len(result["messages"]) > 0  # at least system + response

    def test_non_list_messages(self, harness_agent: HarnessAgent) -> None:
        """Agent should not crash on non-list messages value."""
        # list() handles conversion gracefully
        result = harness_agent.invoke({"messages": "not_a_list"})
        assert "messages" in result


class TestAgentRobustLargeInput:
    """Agent handles large or edge-case inputs."""

    def test_very_long_message(self, harness_agent: HarnessAgent) -> None:
        """Agent handles a very long user message."""
        long_text = "test " * 1000
        result = harness_agent.invoke({
            "messages": [HumanMessage(content=long_text)]
        })
        assert "messages" in result

    def test_special_characters_in_message(
        self, harness_agent: HarnessAgent
    ) -> None:
        """Agent handles unicode and special characters."""
        special = "🔥 Unicode  \n \t \\ / $ ` ' \" <tag>"
        result = harness_agent.invoke({
            "messages": [HumanMessage(content=special)]
        })
        assert "messages" in result


class TestToolRegistryRobustness:
    """ToolRegistry handles adversarial registration and invocation."""

    def test_register_non_tool_rejected(
        self, empty_registry: ToolRegistry
    ) -> None:
        """Registering a non-BaseTool raises TypeError."""
        with pytest.raises(TypeError, match="BaseTool"):
            empty_registry.register("string_instead_of_tool")  # type: ignore[arg-type]

        with pytest.raises(TypeError, match="BaseTool"):
            empty_registry.register(42)  # type: ignore[arg-type]

    def test_get_empty_name(self, empty_registry: ToolRegistry) -> None:
        """Looking up empty string name still raises ToolNotFoundError."""
        with pytest.raises(ToolNotFoundError):
            empty_registry.get("")

    def test_invoke_tool_with_wrong_kwargs(
        self, empty_registry: ToolRegistry
    ) -> None:
        """Invoking a tool with wrong kwargs raises ToolExecutionError."""
        from tests.conftest import MockTool

        tool = MockTool()
        empty_registry.register(tool)

        with pytest.raises(ToolExecutionError):
            empty_registry.invoke_tool("mock_tool", wrong_param="value")


class TestMemoryRobustness:
    """HybridMemory handles edge cases and adversarial inputs."""

    def test_store_none_value(self, hybrid_memory: HybridMemory) -> None:
        """Storing None as value should work."""
        hybrid_memory.store("none_key", None)
        assert hybrid_memory.get("none_key") is None
        assert len(hybrid_memory) == 1

    def test_store_empty_string_key(self, hybrid_memory: HybridMemory) -> None:
        """Storing with empty string key works."""
        hybrid_memory.store("", "empty_key_value")
        assert hybrid_memory.get("") == "empty_key_value"

    def test_delete_during_iteration(self, hybrid_memory: HybridMemory) -> None:
        """Delete during iteration over keys is safe."""
        hybrid_memory.store("a", 1)
        hybrid_memory.store("b", 2)
        hybrid_memory.store("c", 3)

        ctx = hybrid_memory.get_context("test")
        for key in list(ctx["items"]):  # use list to copy
            hybrid_memory.delete(key)

        assert len(hybrid_memory) == 0

    def test_retrieve_with_zero_k(
        self, hybrid_memory: HybridMemory
    ) -> None:
        """Retrieve with k=0 returns empty list."""
        hybrid_memory.store("k", "v", embedding=[0.1])
        results = hybrid_memory.retrieve("query", k=0)
        assert results == []

    def test_clear_then_use(self, hybrid_memory: HybridMemory) -> None:
        """Memory is usable after clear."""
        hybrid_memory.store("a", 1)
        hybrid_memory.clear()
        assert len(hybrid_memory) == 0
        # Can still store new data
        hybrid_memory.store("b", 2)
        assert hybrid_memory.get("b") == 2


class TestErrorPropagation:
    """Error handling follows ADR-009 contract."""

    def test_tool_not_found_is_not_retryable(self) -> None:
        """ToolNotFoundError should be recognized as a fatal config error."""
        exc = ToolNotFoundError("missing")
        assert "[FATAL]" in str(exc)
        assert exc.tool_name == "missing"

    def test_tool_execution_is_retryable(self) -> None:
        """ToolExecutionError carries original error for retry decisions."""
        original = ValueError("transient failure")
        exc = ToolExecutionError("tool_name", original)
        assert "[ERROR]" in str(exc)
        assert exc.original_error is original

    def test_harness_error_catches_all(self) -> None:
        """HarnessError is the base — can catch all harness errors."""
        errors = [
            ToolNotFoundError("t1"),
            ToolExecutionError("t2", RuntimeError("fail")),
        ]
        for err in errors:
            with pytest.raises(HarnessError):
                raise err
