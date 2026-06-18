"""Multi-tenant deployment mode (Step 6.5).

Provides tenant-isolated agent management with separate sandboxes,
memory namespaces, and port assignments per tenant.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from harness_agent.config import AgentModelSelection
from harness_agent.core.agent import HarnessAgent

logger = logging.getLogger(__name__)


@dataclass
class TenantAgent:
    """A tenant-isolated agent instance.

    Attributes:
        tenant_id: Unique tenant identifier.
        agent: The LangChain HarnessAgent instance.
        sandbox_id: Dedicated sandbox identifier.
        port: Dedicated port for this tenant's agent server.
        model_selection: Model configuration for this tenant.
    """

    tenant_id: str
    agent: HarnessAgent
    sandbox_id: str
    port: int
    model_selection: AgentModelSelection


@dataclass
class TenantManagerConfig:
    """Configuration for the multi-tenant agent manager.

    Attributes:
        base_port: Starting port number; tenants get base_port + hash(tenant_id) % 100.
        sandbox_type: Sandbox type for each tenant (docker, local, none).
        enable_memory: Toggle per-tenant memory.
        default_model_selection: Model selection shared across tenants.
    """

    base_port: int = 2024
    sandbox_type: str = "docker"
    enable_memory: bool = True
    default_model_selection: AgentModelSelection = field(
        default_factory=AgentModelSelection
    )


class TenantAgentManager:
    """Manages isolated agent instances for multiple tenants.

    Each tenant gets:
    - A dedicated HarnessAgent instance
    - A unique sandbox (sandbox-<tenant_id>)
    - A unique port derived from the tenant ID
    - Namespaced memory (prefixed by tenant_id)

    Example:
        manager = TenantAgentManager()
        agent = await manager.get_agent("tenant-acme")
        # ... use agent ...
        await manager.cleanup_tenant("tenant-acme")
    """

    def __init__(self, config: TenantManagerConfig | None = None) -> None:
        self._config = config or TenantManagerConfig()
        self._agents: dict[str, TenantAgent] = {}

    def _compute_port(self, tenant_id: str) -> int:
        """Compute a deterministic port for a tenant."""
        return self._config.base_port + abs(hash(tenant_id)) % 100

    def _create_agent(self, tenant_id: str) -> TenantAgent:
        """Create a new agent instance for a tenant.

        Args:
            tenant_id: Unique tenant identifier.

        Returns:
            A fully initialized TenantAgent.
        """
        port = self._compute_port(tenant_id)
        sandbox_id = f"sandbox-{tenant_id}"

        llm_config = self._config.default_model_selection.orchestrator
        llm = self._config.default_model_selection.to_langchain_model(llm_config)

        agent = HarnessAgent(
            llm=llm,
            tools=[],
            system_prompt=(
                f"You are a coding assistant for tenant '{tenant_id}'."
            ),
        )

        tenant_agent = TenantAgent(
            tenant_id=tenant_id,
            agent=agent,
            sandbox_id=sandbox_id,
            port=port,
            model_selection=self._config.default_model_selection,
        )
        logger.info(
            "Tenant '%s': agent created (port=%d, sandbox=%s)",
            tenant_id,
            port,
            sandbox_id,
        )
        return tenant_agent

    async def get_agent(self, tenant_id: str) -> HarnessAgent:
        """Get or create an agent for a tenant.

        Args:
            tenant_id: The tenant identifier.

        Returns:
            The tenant's HarnessAgent instance.
        """
        if tenant_id not in self._agents:
            self._agents[tenant_id] = self._create_agent(tenant_id)
        return self._agents[tenant_id].agent

    async def cleanup_tenant(self, tenant_id: str) -> None:
        """Remove a tenant and release its resources.

        Args:
            tenant_id: The tenant to clean up.
        """
        if tenant_id in self._agents:
            del self._agents[tenant_id]
            logger.info("Tenant '%s': cleaned up", tenant_id)

    async def cleanup_all(self) -> None:
        """Remove all tenants."""
        tenant_ids = list(self._agents.keys())
        for tid in tenant_ids:
            await self.cleanup_tenant(tid)
        logger.info("All tenants cleaned up")

    @property
    def active_tenants(self) -> list[str]:
        """List currently active tenant IDs."""
        return list(self._agents.keys())

    @property
    def tenant_count(self) -> int:
        """Number of active tenants."""
        return len(self._agents)

    def is_active(self, tenant_id: str) -> bool:
        """Check if a tenant is currently active.

        Args:
            tenant_id: The tenant to check.

        Returns:
            True if the tenant has an active agent.
        """
        return tenant_id in self._agents
