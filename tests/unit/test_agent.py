"""Tests for HarnessAgent implementing the Runnable protocol."""

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable

from harness_agent.core.agent import HarnessAgent


class TestHarnessAgentRunnableProtocol:
    """Verify HarnessAgent implements the LangChain Runnable protocol."""

    def test_is_runnable(self, harness_agent: HarnessAgent) -> None:
        assert isinstance(harness_agent, Runnable)

    def test_has_invoke(self, harness_agent: HarnessAgent) -> None:
        assert hasattr(harness_agent, "invoke")
        assert callable(harness_agent.invoke)

    def test_has_ainvoke(self, harness_agent: HarnessAgent) -> None:
        assert hasattr(harness_agent, "ainvoke")
        assert callable(harness_agent.ainvoke)

    def test_has_stream(self, harness_agent: HarnessAgent) -> None:
        # stream is inherited from Runnable base
        assert hasattr(harness_agent, "stream")

    def test_has_astream(self, harness_agent: HarnessAgent) -> None:
        assert hasattr(harness_agent, "astream")


class TestHarnessAgentInvoke:
    """Tests for HarnessAgent.invoke()."""

    def test_invoke_returns_messages(
        self, harness_agent: HarnessAgent
    ) -> None:
        result = harness_agent.invoke({
            "messages": [HumanMessage(content="Hello")]
        })
        assert "messages" in result
        assert len(result["messages"]) > 0

    def test_invoke_includes_ai_response(
        self, harness_agent: HarnessAgent
    ) -> None:
        result = harness_agent.invoke({
            "messages": [HumanMessage(content="Hi")]
        })
        messages = result["messages"]
        # Last message should be from the AI
        assert isinstance(messages[-1], AIMessage)
        assert messages[-1].content == "Hello, I am an agent."

    def test_invoke_includes_system_prompt(
        self, harness_agent: HarnessAgent
    ) -> None:
        result = harness_agent.invoke({
            "messages": [HumanMessage(content="Test")]
        })
        messages = result["messages"]
        # First message should be the system prompt
        assert isinstance(messages[0], SystemMessage)
        assert messages[0].content == "You are a test agent."

    def test_invoke_without_system_prompt(self, fake_llm: FakeListChatModel) -> None:
        agent = HarnessAgent(llm=fake_llm, tools=[], system_prompt="")
        result = agent.invoke({
            "messages": [HumanMessage(content="Test")]
        })
        messages = result["messages"]
        # No SystemMessage should be prepended
        assert not any(
            isinstance(m, SystemMessage) for m in messages
        )

    def test_invoke_empty_messages(
        self, harness_agent: HarnessAgent
    ) -> None:
        result = harness_agent.invoke({"messages": []})
        assert "messages" in result
        assert len(result["messages"]) > 0

    def test_invoke_no_messages_key(
        self, harness_agent: HarnessAgent
    ) -> None:
        result = harness_agent.invoke({})
        assert "messages" in result
        assert len(result["messages"]) > 0

    def test_invoke_preserves_original_messages(
        self, harness_agent: HarnessAgent
    ) -> None:
        original = HumanMessage(content="Important question")
        result = harness_agent.invoke({"messages": [original]})
        assert result["messages"][-2] is original if result["messages"][0] != original else True


class TestHarnessAgentAinvoke:
    """Tests for HarnessAgent.ainvoke()."""

    @pytest.mark.asyncio
    async def test_ainvoke_returns_messages(
        self, harness_agent: HarnessAgent
    ) -> None:
        result = await harness_agent.ainvoke({
            "messages": [HumanMessage(content="Hello async")]
        })
        assert "messages" in result
        assert len(result["messages"]) > 0

    @pytest.mark.asyncio
    async def test_ainvoke_includes_system_prompt(
        self, harness_agent: HarnessAgent
    ) -> None:
        result = await harness_agent.ainvoke({
            "messages": [HumanMessage(content="Test")]
        })
        messages = result["messages"]
        assert isinstance(messages[0], SystemMessage)
        assert messages[0].content == "You are a test agent."

    @pytest.mark.asyncio
    async def test_ainvoke_without_system_prompt(
        self, fake_llm: FakeListChatModel
    ) -> None:
        agent = HarnessAgent(llm=fake_llm, tools=[], system_prompt="")
        result = await agent.ainvoke({
            "messages": [HumanMessage(content="Test")]
        })
        messages = result["messages"]
        assert not any(
            isinstance(m, SystemMessage) for m in messages
        )


class TestHarnessAgentTools:
    """Tests for tool binding behavior."""

    def test_agent_with_tools_binds_to_llm(self, fake_llm: FakeListChatModel) -> None:
        from tests.conftest import MockTool

        tool = MockTool()
        # FakeListChatModel doesn't support bind_tools, so test with
        # a plain mock that allows it. We test tool storage only.
        from unittest.mock import MagicMock

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        agent = HarnessAgent(llm=mock_llm, tools=[tool])
        assert agent._tools == [tool]
        mock_llm.bind_tools.assert_called_once_with([tool])

    def test_agent_with_no_tools_works(self, harness_agent: HarnessAgent) -> None:
        result = harness_agent.invoke({
            "messages": [HumanMessage(content="No tools needed")]
        })
        assert "messages" in result

    def test_agent_with_none_tools_works(self, fake_llm: FakeListChatModel) -> None:
        agent = HarnessAgent(llm=fake_llm, tools=None)
        assert agent._tools == []


class TestHarnessAgentEdgeCases:
    """Edge case tests for HarnessAgent."""

    def test_agent_stores_system_prompt(
        self, harness_agent: HarnessAgent
    ) -> None:
        assert harness_agent.system_prompt == "You are a test agent."

    def test_agent_config_passthrough(
        self, harness_agent: HarnessAgent
    ) -> None:
        """Config dict should be accepted (no assertion it's passed through)."""
        result = harness_agent.invoke(
            {"messages": [HumanMessage(content="Test")]},
            config={"tags": ["test"]},
        )
        assert "messages" in result
