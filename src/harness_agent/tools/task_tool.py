"""Fallback task tool for subagent delegation without deepagents.

When the deepagents package is not installed, this tool provides
subagent delegation by spawning temporary HarnessAgent instances
with the subagent's system_prompt and tools.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from harness_agent.core.agent import HarnessAgent

logger = logging.getLogger(__name__)


class TaskInput(BaseModel):
    """Input schema for the task delegation tool."""

    subagent_type: str = Field(
        ..., description="Name of the subagent to delegate to"
    )
    task: str = Field(
        ..., description="Task description for the subagent to execute"
    )


class TaskTool(BaseTool):
    """Delegate a task to a configured subagent.

    Looks up the subagent by name, creates a temporary HarnessAgent
    with the subagent's system_prompt and tools, invokes it, and
    returns the result.
    """

    name: str = "task"
    description: str = (
        "Delegate a task to a subagent. The subagent runs independently "
        "and returns a result. Use subagent_type to specify which subagent "
        "to use, and task to describe what it should do."
    )
    args_schema: type[BaseModel] = TaskInput

    subagent_defs: list[dict[str, Any]] = Field(default_factory=list)
    llm: Any = None

    model_config = {"arbitrary_types_allowed": True}

    def _run(self, subagent_type: str, task: str) -> str:
        subagent_def = self._find_subagent(subagent_type)
        if subagent_def is None:
            available = [d["name"] for d in self.subagent_defs]
            return (
                f"Unknown subagent '{subagent_type}'. "
                f"Available: {available}"
            )

        agent = self._create_subagent(subagent_def)
        try:
            result = agent.invoke(
                {"messages": [{"role": "user", "content": task}]}
            )
            messages = result.get("messages", [])
            if messages:
                return str(messages[-1].content)
            return "(no response from subagent)"
        except Exception as e:
            logger.error("Subagent '%s' failed: %s", subagent_type, e)
            return f"Subagent error: {e}"

    async def _arun(self, subagent_type: str, task: str) -> str:
        subagent_def = self._find_subagent(subagent_type)
        if subagent_def is None:
            available = [d["name"] for d in self.subagent_defs]
            return (
                f"Unknown subagent '{subagent_type}'. "
                f"Available: {available}"
            )

        agent = self._create_subagent(subagent_def)
        try:
            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": task}]}
            )
            messages = result.get("messages", [])
            if messages:
                return str(messages[-1].content)
            return "(no response from subagent)"
        except Exception as e:
            logger.error("Subagent '%s' failed: %s", subagent_type, e)
            return f"Subagent error: {e}"

    def _find_subagent(self, name: str) -> dict[str, Any] | None:
        for d in self.subagent_defs:
            if d["name"] == name:
                return d
        return None

    def _create_subagent(self, subagent_def: dict[str, Any]) -> HarnessAgent:
        tools: list[BaseTool] = subagent_def.get("tools", [])
        system_prompt: str = subagent_def.get("system_prompt", "")
        return HarnessAgent(
            llm=self.llm,
            tools=tools if tools else None,
            system_prompt=system_prompt,
            max_tool_iterations=20,
        )


def create_task_tool(
    subagent_defs: list[dict[str, Any]], llm: BaseChatModel
) -> BaseTool:
    """Create a task delegation tool for the fallback agent path.

    Args:
        subagent_defs: List of subagent definition dicts from SubAgentLoader.
        llm: The LLM instance to use for subagent execution.

    Returns:
        A configured TaskTool instance.
    """
    return TaskTool(subagent_defs=subagent_defs, llm=llm)
