"""Harness Agent — Deep agent framework for multi-agent orchestration."""

from harness_agent.core.agent import HarnessAgent
from harness_agent.core.exceptions import (
    AgentExecutionError,
    HarnessError,
    SubagentTimeoutError,
    ToolExecutionError,
    ToolNotFoundError,
)
from harness_agent.core.orchestrator import AgentOrchestrator
from harness_agent.deployment import (  # noqa: E402, F401
    AgentRequest,
    AgentResponse,
    CLIAgent,
    TenantAgentManager,
    create_cli_agent,
    create_server_app,
)
from harness_agent.memory.hybrid_memory import HybridMemory, MemoryItem
from harness_agent.security import (  # noqa: E402, F401
    HITLApprovalDeniedError,
    HumanInTheLoopMiddleware,
    PermissionBoundary,
    PIIMiddleware,
    SandboxConfig,
    safe_run,
)
from harness_agent.tools.registry import ToolRegistry

__version__ = "0.1.0"

__all__ = [
    "AgentExecutionError",
    "AgentOrchestrator",
    "AgentRequest",
    "AgentResponse",
    "CLIAgent",
    "HITLApprovalDeniedError",
    "HarnessAgent",
    "HarnessError",
    "HumanInTheLoopMiddleware",
    "HybridMemory",
    "MemoryItem",
    "PIIMiddleware",
    "PermissionBoundary",
    "SandboxConfig",
    "SubagentTimeoutError",
    "TenantAgentManager",
    "ToolExecutionError",
    "ToolNotFoundError",
    "ToolRegistry",
    "create_cli_agent",
    "create_server_app",
    "safe_run",
]
