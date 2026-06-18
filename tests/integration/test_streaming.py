"""Integration tests for agent streaming capabilities."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage

from harness_agent.core.agent import HarnessAgent


class TestHarnessAgentStream:
    """Tests for HarnessAgent.stream() — synchronous streaming."""

    def test_stream_returns_iterator(self) -> None:
        """stream() returns an iterator."""
        fake_llm = FakeListChatModel(responses=["Hello"])
        agent = HarnessAgent(llm=fake_llm, tools=[], system_prompt="You are helpful.")

        result = agent.stream({"messages": [HumanMessage(content="Hi")]})
        assert isinstance(result, Iterator)

        chunks = list(result)
        assert len(chunks) > 0

    def test_stream_with_system_prompt(self) -> None:
        """Streaming includes system prompt prepended."""
        fake_llm = FakeListChatModel(responses=["Response"])
        agent = HarnessAgent(
            llm=fake_llm, tools=[], system_prompt="You are a test agent."
        )

        result = list(agent.stream({"messages": [HumanMessage(content="Test")]}))
        assert len(result) > 0

    def test_stream_with_empty_messages(self) -> None:
        """Streaming handles empty messages gracefully."""
        fake_llm = FakeListChatModel(responses=["Still works"])
        agent = HarnessAgent(llm=fake_llm, tools=[], system_prompt="")

        result = list(agent.stream({"messages": []}))
        assert len(result) > 0

    def test_stream_with_no_messages_key(self) -> None:
        """Streaming handles missing messages key."""
        fake_llm = FakeListChatModel(responses=["Output"])
        agent = HarnessAgent(llm=fake_llm, tools=[], system_prompt="")

        result = list(agent.stream({}))
        assert len(result) > 0


class TestHarnessAgentAstream:
    """Tests for HarnessAgent.astream() — asynchronous streaming."""

    @pytest.mark.asyncio
    async def test_astream_returns_async_iterator(self) -> None:
        """astream() returns an async iterator."""
        fake_llm = FakeListChatModel(responses=["Hello async"])
        agent = HarnessAgent(
            llm=fake_llm, tools=[], system_prompt="You are helpful."
        )

        result = agent.astream({"messages": [HumanMessage(content="Hi")]})
        assert isinstance(result, AsyncIterator)

        chunks = []
        async for chunk in result:
            chunks.append(chunk)
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_astream_with_system_prompt(self) -> None:
        """Async streaming includes system prompt."""
        fake_llm = FakeListChatModel(responses=["Async response"])
        agent = HarnessAgent(
            llm=fake_llm, tools=[], system_prompt="You are a test agent."
        )

        chunks = []
        async for chunk in agent.astream(
            {"messages": [HumanMessage(content="Test")]}
        ):
            chunks.append(chunk)
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_astream_with_empty_messages(self) -> None:
        """Async streaming handles empty messages."""
        fake_llm = FakeListChatModel(responses=["Async still works"])
        agent = HarnessAgent(llm=fake_llm, tools=[], system_prompt="")

        chunks = []
        async for chunk in agent.astream({"messages": []}):
            chunks.append(chunk)
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_astream_with_no_messages_key(self) -> None:
        """Async streaming handles missing messages key."""
        fake_llm = FakeListChatModel(responses=["Async output"])
        agent = HarnessAgent(llm=fake_llm, tools=[], system_prompt="")

        chunks = []
        async for chunk in agent.astream({}):
            chunks.append(chunk)
        assert len(chunks) > 0
