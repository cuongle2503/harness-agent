"""Code agent factory — creates agent with file ops and code execution."""

from __future__ import annotations

from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend
from deepagents.middleware import FilesystemMiddleware, SubAgentMiddleware
from deepagents.middleware.subagents import SubAgent
from deepagents.middleware.summarization import create_summarization_middleware
from langchain.agents.middleware import AgentMiddleware, TodoListMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

from harness_agent.prompts import load_prompt


def create_code_agent(
    model: BaseChatModel,
    *,
    code_tools: list[BaseTool] | None = None,
    backend: CompositeBackend | None = None,
    store: Any = None,
    summarization_model: BaseChatModel | str = "deepseek-v4-flash",
) -> CompiledStateGraph:  # type: ignore[type-arg]
    """Create a code agent with file manipulation and code execution.

    Per ADR-004, the coder subagent uses deepseek-v4-pro,
    has file tools + execute_python + execute_command,
    and ContextEditingMiddleware + ToolRetryMiddleware.

    Args:
        model: The BaseChatModel for the main agent and subagent.
        code_tools: Optional list of BaseTools for the coder.
        backend: Optional CompositeBackend (creates default if None).
        store: Optional BaseStore for persistent memory.
        summarization_model: Model for SummarizationMiddleware (BaseChatModel or string ID).

    Returns:
        A compiled LangGraph StateGraph ready for invoke/stream.
    """
    effective_backend = backend or CompositeBackend(
        default=StateBackend(), routes={}
    )

    tools = code_tools or []

    coder_subagent: SubAgent = {
        "name": "coder",
        "description": (
            "Software engineer specialist. Use for: code generation, "
            "refactoring, debugging, test writing, script creation. "
            "Returns complete, working code with explanation."
        ),
        "system_prompt": load_prompt("coder"),
        "tools": tools,
        "model": model,
        "middleware": [],
    }

    middleware: list[AgentMiddleware] = [
        TodoListMiddleware(),  # type: ignore[list-item]
        FilesystemMiddleware(backend=effective_backend),  # type: ignore[list-item]
        create_summarization_middleware(
            model=summarization_model,  # type: ignore[arg-type]
            backend=effective_backend,
        ),
        SubAgentMiddleware(
            backend=effective_backend,
            subagents=[coder_subagent],
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
