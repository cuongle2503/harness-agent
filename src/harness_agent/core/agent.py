"""HarnessAgent — base agent implementing the LangChain Runnable protocol."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOOL_ITERATIONS = 50


class HarnessAgent(Runnable[dict[str, Any], dict[str, Any]]):
    """Base agent following the LangChain Runnable protocol.

    Supports tool calling: when the LLM returns tool_calls, this agent
    executes the tools and feeds results back to the LLM in a loop
    (up to max_tool_iterations).

    Attributes:
        llm: The language model (with tools bound if tools provided).
        system_prompt: Optional system prompt prepended to messages.
        max_tool_iterations: Max tool-calling loop iterations per turn.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        tools: list[BaseTool] | None = None,
        system_prompt: str = "",
        max_tool_iterations: int = DEFAULT_MAX_TOOL_ITERATIONS,
    ) -> None:
        self._tools = tools or []
        self._tool_map = {t.name: t for t in self._tools}
        self.llm = llm.bind_tools(self._tools) if self._tools else llm
        self.system_prompt = system_prompt
        self.max_tool_iterations = max_tool_iterations

    def _execute_tools(
        self, tool_calls: list[dict[str, Any]],
        config: RunnableConfig | None = None,
    ) -> list[ToolMessage]:
        """Execute a list of tool calls and return ToolMessages.

        Passes config through so callbacks (e.g., metrics recording)
        receive on_tool_start / on_tool_end events.
        """
        results: list[ToolMessage] = []
        for tc in tool_calls:
            tool_name = tc.get("name", "")
            tool_args = tc.get("args", {})
            tool_id = tc.get("id", "")
            tool = self._tool_map.get(tool_name)
            if tool is None:
                msg = f"Unknown tool: {tool_name}"
            else:
                try:
                    result = tool.invoke(tool_args, config)
                    msg = str(result)
                except Exception as e:
                    msg = f"Tool error: {e}"
            results.append(ToolMessage(content=msg, tool_call_id=tool_id))
        return results

    def invoke(
        self,
        input: dict[str, Any],
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        messages = list(input.get("messages", []))
        if self.system_prompt:
            messages = [SystemMessage(content=self.system_prompt), *messages]

        iteration = 0
        while iteration < self.max_tool_iterations:
            iteration += 1
            response = self.llm.invoke(messages, config)
            messages.append(response)

            tool_calls = getattr(response, "tool_calls", None)
            if not tool_calls:
                # No tool calls — final response
                return {"messages": messages}

            # Execute tools and append results
            tool_msgs = self._execute_tools(tool_calls, config)
            messages.extend(tool_msgs)

        # Max iterations reached
        logger.warning(
            "Max tool iterations (%d) reached", self.max_tool_iterations
        )
        return {"messages": messages}

    async def ainvoke(
        self,
        input: dict[str, Any],
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        messages = list(input.get("messages", []))
        if self.system_prompt:
            messages = [SystemMessage(content=self.system_prompt), *messages]

        iteration = 0
        while iteration < self.max_tool_iterations:
            iteration += 1
            response = await self.llm.ainvoke(messages, config)
            messages.append(response)

            tool_calls = getattr(response, "tool_calls", None)
            if not tool_calls:
                return {"messages": messages}

            tool_msgs = self._execute_tools(tool_calls, config)
            messages.extend(tool_msgs)

        logger.warning(
            "Max tool iterations (%d) reached", self.max_tool_iterations
        )
        return {"messages": messages}
