"""Shared test fixtures for the harness-agent test suite."""

from __future__ import annotations

import pytest
from langchain_core.language_models.fake_chat_models import (
    FakeListChatModel,
    FakeMessagesListChatModel,
)
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from harness_agent.core.agent import HarnessAgent
from harness_agent.memory.hybrid_memory import HybridMemory
from harness_agent.tools.registry import ToolRegistry


@pytest.fixture
def anyio_backend() -> str:
    """Use asyncio backend for all async tests."""
    return "asyncio"


@pytest.fixture
def fake_llm() -> FakeListChatModel:
    """A fake LLM that returns a fixed string response.

    Monkey-patches ``bind_tools`` to return ``self`` because
    ``FakeListChatModel.bind_tools()`` raises ``NotImplementedError``
    in some LangChain versions. Tests that pass real tool lists
    (e.g., ``BASIC_TOOLS``) need ``bind_tools`` to at least not crash.

    Uses ``object.__setattr__`` to bypass Pydantic's field validation.
    """
    llm = FakeListChatModel(responses=["Hello, I am an agent."])
    # FakeListChatModel is a Pydantic model — can't set arbitrary attrs
    # via normal assignment.  Use object.__setattr__ to bypass validation.
    object.__setattr__(llm, "bind_tools", lambda *args: llm)
    return llm


@pytest.fixture
def fake_messages_llm() -> FakeMessagesListChatModel:
    """A fake LLM that returns pre-defined messages (supports tool calls)."""
    return FakeMessagesListChatModel(
        responses=[
            AIMessage(content="I'll help with that."),
            AIMessage(content="Task completed."),
        ]
    )


@pytest.fixture
def harness_agent(fake_llm: FakeListChatModel) -> HarnessAgent:
    """A HarnessAgent with a fake LLM and system prompt."""
    return HarnessAgent(
        llm=fake_llm,
        tools=[],
        system_prompt="You are a test agent.",
    )


@pytest.fixture
def empty_registry() -> ToolRegistry:
    """An empty ToolRegistry instance."""
    return ToolRegistry()


class MockToolInput(BaseModel):
    """Mock input schema for test tools."""

    param: str = Field(..., description="A test parameter")


class MockTool(BaseTool):
    """A mock BaseTool implementation for testing."""

    name: str = "mock_tool"
    description: str = "A mock tool for testing."
    args_schema: type[BaseModel] = MockToolInput

    def _run(self, param: str) -> str:
        return f"mock_result: {param}"


class MockSearchTool(BaseTool):
    """A mock search tool for testing."""

    name: str = "web_search"
    description: str = "Search the web for information."
    args_schema: type[BaseModel] = MockToolInput

    def _run(self, param: str) -> str:
        return f'{{"results": ["result for {param}"], "query": "{param}"}}'


@pytest.fixture
def sample_tool() -> MockTool:
    """A sample mock tool."""
    return MockTool()


@pytest.fixture
def sample_search_tool() -> MockSearchTool:
    """A sample mock search tool."""
    return MockSearchTool()


@pytest.fixture
def registry_with_tools(
    empty_registry: ToolRegistry, sample_tool: MockTool
) -> ToolRegistry:
    """A ToolRegistry with one registered tool."""
    empty_registry.register(sample_tool)
    return empty_registry


@pytest.fixture
def hybrid_memory() -> HybridMemory:
    """A fresh HybridMemory instance."""
    return HybridMemory()


@pytest.fixture
def hybrid_memory_with_data() -> HybridMemory:
    """A HybridMemory pre-populated with sample data."""
    memory = HybridMemory()
    memory.store("key1", "value1")
    memory.store("key2", "value2", embedding=[0.1, 0.2, 0.3])
    memory.store("key3", "value3", embedding=[0.4, 0.5, 0.6])
    memory.store("key4", "value4", embedding=[0.7, 0.8, 0.9])
    return memory
