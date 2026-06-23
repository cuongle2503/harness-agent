"""AgentOrchestrator — multi-agent orchestration using LangGraph state machines."""

from __future__ import annotations

from typing import Any


class AgentOrchestrator:
    """Multi-agent orchestration using LangGraph state machines.

    Not yet implemented. Full LangGraph-based orchestration (with StateGraph
    nodes, conditional routing, and checkpointing) will be added when
    subagent orchestration patterns mature.
    """

    def __init__(self, agents: dict[str, Any]) -> None:
        self.agents = agents

    def run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(
            "AgentOrchestrator is not yet implemented. "
            "Full LangGraph orchestration is planned for a future phase."
        )
