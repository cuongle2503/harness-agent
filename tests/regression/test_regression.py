"""Regression tests for previously fixed bugs.

Each bug fix should have a corresponding regression test
to prevent regression when the codebase evolves.
"""

from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage

from harness_agent.core.agent import HarnessAgent
from harness_agent.memory.hybrid_memory import HybridMemory
from harness_agent.tools.registry import ToolRegistry

# ── Known regression cases ──────────────────────────────────────

REGRESSION_CASES = [
    {
        "id": "BUG-001",
        "title": "Empty input dict should not crash agent",
        "input": {},
        "expected_behavior": "returns_messages",
    },
    {
        "id": "BUG-002",
        "title": "Non-list messages should not crash agent",
        "input": {"messages": "not_a_list_string"},
        "expected_behavior": "handles_gracefully",
    },
    {
        "id": "BUG-003",
        "title": "Empty messages list should produce output",
        "input": {"messages": []},
        "expected_behavior": "returns_response",
    },
    {
        "id": "BUG-004",
        "title": "Missing messages key should not crash agent",
        "input": {"unexpected": "value"},
        "expected_behavior": "handles_missing_key",
    },
]


class TestRegressionAgent:
    """Regression tests for agent bugs."""

    @pytest.fixture
    def agent(self) -> HarnessAgent:
        llm = FakeListChatModel(responses=["I handled your request."])
        return HarnessAgent(llm=llm, tools=[], system_prompt="Be helpful.")

    @pytest.mark.parametrize("case", REGRESSION_CASES)
    def test_regression_case(
        self, agent: HarnessAgent, case: dict[str, str]
    ) -> None:
        """Verify that known bugs do not regress."""
        result = agent.invoke(cast_input(case["input"]))
        assert "messages" in result, f"Regression {case['id']}: {case['title']}"
        assert len(result["messages"]) > 0, (
            f"Regression {case['id']}: {case['title']}"
        )


class TestRegressionMemory:
    """Regression tests for memory bugs."""

    @pytest.fixture
    def memory(self) -> HybridMemory:
        return HybridMemory()

    def test_delete_during_iteration_is_safe(self, memory: HybridMemory) -> None:
        """BUG-005: Delete during key iteration should not raise KeyError."""
        memory.store("a", 1)
        memory.store("b", 2)
        memory.store("c", 3)

        ctx = memory.get_context("session")
        for key in list(ctx["items"]):
            memory.delete(key)

        assert len(memory) == 0

    def test_clear_then_store_works(self, memory: HybridMemory) -> None:
        """BUG-006: Clear then store should produce valid state."""
        memory.store("a", 1, embedding=[0.1])
        memory.clear()
        memory.store("b", 2, embedding=[0.2])

        assert memory.get("a") is None
        assert memory.get("b") == 2
        results = memory.retrieve("query", k=10)
        assert len(results) == 1

    def test_retrieve_zero_k_returns_empty(self, memory: HybridMemory) -> None:
        """BUG-007: retrieve with k=0 should return empty, not error."""
        memory.store("a", 1, embedding=[0.1])
        results = memory.retrieve("query", k=0)
        assert results == []
        assert memory.get("a") == 1  # data unaffected


class TestRegressionToolRegistry:
    """Regression tests for ToolRegistry bugs."""

    @pytest.fixture
    def registry(self) -> ToolRegistry:
        return ToolRegistry()

    def test_duplicate_register_overwrites_safely(
        self, registry: ToolRegistry
    ) -> None:
        """BUG-008: Duplicate tool registration should overwrite, not error."""
        from tests.conftest import MockTool

        tool1 = MockTool()
        tool2 = MockTool()  # Same name "mock_tool"

        registry.register(tool1)
        registry.register(tool2)

        # Should still have only one tool
        schemas = registry.list_tools()
        assert len(schemas) == 1
        assert schemas[0]["name"] == "mock_tool"

    def test_get_after_register_unregister_pattern(
        self, registry: ToolRegistry
    ) -> None:
        """BUG-009: Re-register after get-error should work."""
        from harness_agent.core.exceptions import ToolNotFoundError
        from tests.conftest import MockTool

        with pytest.raises(ToolNotFoundError):
            registry.get("mock_tool")

        registry.register(MockTool())
        assert registry.get("mock_tool") is not None


# ── Helpers ──────────────────────────────────────────────────────


def cast_input(input_val: dict | str) -> dict:
    """Cast input to the format expected by agent.invoke."""
    if isinstance(input_val, dict):
        return input_val
    return {"messages": [HumanMessage(content=input_val)]}
