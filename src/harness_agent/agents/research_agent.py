"""Research agent factory — creates agent with web search and URL fetch."""

from __future__ import annotations

from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend
from deepagents.middleware import FilesystemMiddleware, SubAgentMiddleware
from deepagents.middleware.subagents import SubAgent
from langchain.agents.middleware import AgentMiddleware, TodoListMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

from harness_agent.prompts import load_prompt


def create_research_agent(
    model: BaseChatModel,
    search_tool: BaseTool,
    fetch_tool: BaseTool | None = None,
    *,
    backend: CompositeBackend | None = None,
    store: Any = None,
) -> CompiledStateGraph:  # type: ignore[type-arg]
    """Create a research agent with web search and URL fetching.

    Per ADR-004, the researcher subagent uses deepseek-v4-flash,
    has web_search and fetch_url tools, and ToolRetryMiddleware.

    Args:
        model: The BaseChatModel for the main agent and subagent.
        search_tool: A BaseTool for web search (e.g., web_search).
        fetch_tool: Optional BaseTool for URL fetching (e.g., fetch_url).
        backend: Optional CompositeBackend (creates default if None).
        store: Optional BaseStore for persistent memory.

    Returns:
        A compiled LangGraph StateGraph ready for invoke/stream.
    """
    effective_backend = backend or CompositeBackend(
        default=StateBackend(), routes={}
    )

    tools: list[BaseTool] = [search_tool]
    if fetch_tool is not None:
        tools.append(fetch_tool)

    researcher_subagent: SubAgent = {
        "name": "researcher",
        "description": (
            "Web research specialist. Use for: technology evaluation, "
            "documentation lookup, data gathering, competitive analysis. "
            "Returns structured research summaries with citations."
        ),
        "system_prompt": load_prompt("researcher"),
        "tools": tools,
        "model": model,
        "middleware": [],
    }

    middleware: list[AgentMiddleware] = [
        TodoListMiddleware(),  # type: ignore[list-item]
        FilesystemMiddleware(backend=effective_backend),  # type: ignore[list-item]
        SubAgentMiddleware(
            backend=effective_backend,
            subagents=[researcher_subagent],
        ),
    ]

    return create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=load_prompt("main_agent"),
        middleware=middleware,
        backend=effective_backend,
        store=store,
    )
