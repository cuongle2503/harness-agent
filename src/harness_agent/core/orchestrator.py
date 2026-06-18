"""AgentOrchestrator — multi-agent orchestration using LangGraph state machines."""

from __future__ import annotations

from typing import Any


class AgentOrchestrator:
    """Multi-agent orchestration using LangGraph state machines.

    This is a placeholder for Phase 3. Full LangGraph-based orchestration
    (with StateGraph nodes, conditional routing, and checkpointing) will be
    implemented in Phase 4+ when subagent orchestration patterns mature.
    """

    def __init__(self, agents: dict[str, Any]) -> None:
        self.agents = agents
