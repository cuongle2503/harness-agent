"""Integration tests for agent pipeline — HarnessAgent + ToolRegistry + Memory."""

import pytest
from langchain_core.messages import HumanMessage

from harness_agent.core.agent import HarnessAgent
from harness_agent.memory.hybrid_memory import HybridMemory
from harness_agent.tools.registry import ToolRegistry


class TestAgentPipelineIntegration:
    """End-to-end tests for HarnessAgent with tools and memory."""

    def test_full_pipeline_invoke(
        self, harness_agent: HarnessAgent
    ) -> None:
        """Agent with fake LLM produces valid output."""
        result = harness_agent.invoke({
            "messages": [HumanMessage(content="What can you do?")]
        })
        assert "messages" in result
        assert len(result["messages"]) >= 2  # system + user + ai

    def test_registry_to_agent_tools(
        self, empty_registry: ToolRegistry
    ) -> None:
        """Tools from registry can be passed to agent."""
        from unittest.mock import MagicMock

        from tests.conftest import MockTool

        tool = MockTool()
        empty_registry.register(tool)
        tools = [empty_registry.get("mock_tool")]

        # Use mock LLM that supports bind_tools
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        agent = HarnessAgent(llm=mock_llm, tools=tools, system_prompt="Test")
        assert agent._tools == tools

    def test_memory_integration_with_agent(
        self, hybrid_memory: HybridMemory
    ) -> None:
        """Memory operations work correctly across stores."""
        hybrid_memory.store("session_1", {"preference": "dark_mode"})
        ctx = hybrid_memory.get_context("session_1")
        assert "session_1" in ctx["session_id"]
        assert "session_1" in ctx["items"]

    def test_multiple_memory_operations(
        self, hybrid_memory_with_data: HybridMemory
    ) -> None:
        """Multiple memory operations maintain consistency."""
        memory = hybrid_memory_with_data
        assert len(memory) == 4

        # Store new item
        memory.store("key5", "value5", embedding=[1.0, 2.0, 3.0])
        assert len(memory) == 5

        # Retrieve vector items
        results = memory.retrieve("query", k=10)
        assert len(results) == 4  # key2, key3, key4, key5 have embeddings

        # Delete and verify
        memory.delete("key5")
        assert len(memory) == 4
        assert memory.get("key5") is None

    def test_tool_registry_error_handling(
        self, empty_registry: ToolRegistry
    ) -> None:
        """Tool registry properly handles errors in agent pipeline context."""
        from harness_agent.core.exceptions import ToolNotFoundError

        with pytest.raises(ToolNotFoundError):
            empty_registry.get("missing_tool")


class TestAgentMemoryIntegration:
    """Integration between agent and memory components."""

    def test_agent_system_prompt_with_memory_marker(
        self, harness_agent: HarnessAgent, hybrid_memory: HybridMemory
    ) -> None:
        """System prompt can reference memory paths."""
        agent_with_memory_prompt = HarnessAgent(
            llm=harness_agent.llm,
            tools=[],
            system_prompt="Memory at /memories/ for persistence.",
        )
        result = agent_with_memory_prompt.invoke({
            "messages": [HumanMessage(content="Remember: I like Python")]
        })
        assert "messages" in result
