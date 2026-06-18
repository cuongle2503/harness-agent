"""Tests for AgentOrchestrator."""

from __future__ import annotations

from typing import Any

from harness_agent.core.orchestrator import AgentOrchestrator


class TestAgentOrchestratorInit:
    """Tests for AgentOrchestrator constructor."""

    def test_stores_agents_dict(self) -> None:
        agents: dict[str, Any] = {"agent1": "mock_agent", "agent2": "mock_agent2"}
        orch = AgentOrchestrator(agents=agents)
        assert orch.agents is agents
        assert len(orch.agents) == 2

    def test_empty_agents_dict(self) -> None:
        orch = AgentOrchestrator(agents={})
        assert orch.agents == {}
        assert len(orch.agents) == 0

    def test_single_agent(self) -> None:
        agents = {"main": object()}
        orch = AgentOrchestrator(agents=agents)
        assert "main" in orch.agents

    def test_agents_by_name(self) -> None:
        """Verify agents are accessible by name."""
        agent_a = {"name": "a"}
        agent_b = {"name": "b"}
        orch = AgentOrchestrator(agents={"a": agent_a, "b": agent_b})
        assert orch.agents["a"] is agent_a
        assert orch.agents["b"] is agent_b
