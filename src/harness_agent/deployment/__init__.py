"""Deployment package for the agent harness.

Phase 6 deployment modes:
- CLI: Interactive command-line agent for development
- Server: FastAPI HTTP server for production
- Multi-tenant: Tenant-isolated agent manager
"""

from harness_agent.deployment.cli import CLIAgent, create_cli_agent
from harness_agent.deployment.multi_tenant import TenantAgentManager
from harness_agent.deployment.server import (
    AgentRequest,
    AgentResponse,
    create_server_app,
)

__all__ = [
    "AgentRequest",
    "AgentResponse",
    "CLIAgent",
    "TenantAgentManager",
    "create_cli_agent",
    "create_server_app",
]
