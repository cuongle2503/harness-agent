"""Integration tests for error recovery in agent pipelines."""

from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from harness_agent.core.agent import HarnessAgent
from harness_agent.core.exceptions import (
    ToolExecutionError,
    ToolNotFoundError,
)
from harness_agent.memory.hybrid_memory import HybridMemory
from harness_agent.tools.registry import ToolRegistry


class TestErrorRecoveryAgent:
    """Tests that agent survives and recovers from operational errors."""

    def test_agent_survives_empty_input(self) -> None:
        """Agent handles empty input dict without crash."""
        fake_llm = FakeListChatModel(responses=["I'm still working"])
        agent = HarnessAgent(llm=fake_llm, tools=[], system_prompt="Be helpful.")
        result = agent.invoke({})
        assert "messages" in result
        assert len(result["messages"]) > 0

    def test_agent_returns_valid_output_after_missing_key(self) -> None:
        """Agent produces valid output when messages key is missing."""
        fake_llm = FakeListChatModel(responses=["Output"])
        agent = HarnessAgent(llm=fake_llm, tools=[], system_prompt="")
        result = agent.invoke({"unexpected": "value"})
        assert "messages" in result


class TestErrorRecoveryMemory:
    """Tests that memory remains consistent after errors."""

    def test_memory_persists_after_get_error(self) -> None:
        """Memory still holds data after getting a missing key."""
        memory = HybridMemory()
        memory.store("important_key", "important_value")
        # Getting a missing key should not affect stored data
        assert memory.get("missing") is None
        assert memory.get("important_key") == "important_value"

    def test_memory_persists_after_invalid_retrieve(self) -> None:
        """Memory is consistent after retrieve with invalid k."""
        memory = HybridMemory()
        memory.store("k1", "v1", embedding=[0.1])
        result = memory.retrieve("query", k=0)
        assert result == []
        assert memory.get("k1") == "v1"

    def test_memory_clear_then_reuse(self) -> None:
        """Memory is fully functional after clear + new stores."""
        memory = HybridMemory()
        memory.store("a", 1, embedding=[0.1])
        memory.store("b", 2, embedding=[0.2])
        memory.clear()
        memory.store("c", 3, embedding=[0.3])
        assert len(memory) == 1
        assert memory.get("c") == 3
        results = memory.retrieve("query", k=10)
        assert len(results) == 1


class TestErrorRecoveryToolRegistry:
    """Tests that ToolRegistry recovers after errors."""

    def test_registry_usable_after_tool_not_found(self) -> None:
        """Registry still works after a ToolNotFoundError."""
        from tests.conftest import MockTool

        registry = ToolRegistry()
        registry.register(MockTool())

        # This raises
        with pytest.raises(ToolNotFoundError):
            registry.get("nonexistent")

        # Registry still functional
        result = registry.invoke_tool("mock_tool", param="test")
        assert result == "mock_result: test"

    def test_registry_list_tools_after_execution_error(self) -> None:
        """Registry still lists tools after a ToolExecutionError."""
        import langchain_core.tools

        class FailingTool(langchain_core.tools.BaseTool):
            name: str = "failer"
            description: str = "Always fails"

            def _run(self, **kwargs: object) -> str:
                msg = "intentional"
                raise RuntimeError(msg)

        registry = ToolRegistry()
        registry.register(FailingTool())

        with pytest.raises(ToolExecutionError):
            registry.invoke_tool("failer")

        # Listing should still work
        schemas = registry.list_tools()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "failer"

    def test_registry_register_after_get_error(self) -> None:
        """Registry can register new tools after get errors."""
        from tests.conftest import MockSearchTool, MockTool

        registry = ToolRegistry()
        registry.register(MockTool())

        with pytest.raises(ToolNotFoundError):
            registry.get("missing")

        # Register another tool
        registry.register(MockSearchTool())
        assert len(registry) == 2
