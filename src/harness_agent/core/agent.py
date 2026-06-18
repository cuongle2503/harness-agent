"""HarnessAgent — base agent implementing the LangChain Runnable protocol."""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.tools import BaseTool


class HarnessAgent(Runnable[dict[str, Any], dict[str, Any]]):
    """Base agent following the LangChain Runnable protocol.

    Attributes:
        llm: The language model (with tools bound if tools provided).
        system_prompt: Optional system prompt prepended to messages.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        tools: list[BaseTool] | None = None,
        system_prompt: str = "",
    ) -> None:
        tools = tools or []
        self.llm = llm.bind_tools(tools) if tools else llm
        self._tools = tools
        self.system_prompt = system_prompt

    def invoke(
        self,
        input: dict[str, Any],
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        messages = list(input.get("messages", []))
        if self.system_prompt:
            messages = [SystemMessage(content=self.system_prompt), *messages]
        response = self.llm.invoke(messages, config)
        return {"messages": [*messages, response]}

    async def ainvoke(
        self,
        input: dict[str, Any],
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        messages = list(input.get("messages", []))
        if self.system_prompt:
            messages = [SystemMessage(content=self.system_prompt), *messages]
        response = await self.llm.ainvoke(messages, config)
        return {"messages": [*messages, response]}
