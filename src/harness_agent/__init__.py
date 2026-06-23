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
from harness_agent.deployment import (
    AgentRequest,
    AgentResponse,
    CLIAgent,
    TenantAgentManager,
    create_cli_agent,
    create_server_app,
)
from harness_agent.evaluation import (
    ABTestResult,
    AgentABTester,
    AgentEvaluator,
    EvaluationResult,
)
from harness_agent.memory.hybrid_memory import HybridMemory, MemoryItem
from harness_agent.monitoring import (
    AgentMetrics,
    AlertConfig,
    AlertEvaluator,
    AlertRule,
    AlertSeverity,
    HealthDashboardResponse,
    LoggingConfig,
    MetricsResponse,
    StreamingConfig,
    StructuredLoggingMiddleware,
    TracingConfig,
    configure_debug_mode,
    configure_tracing,
    is_debug_enabled,
)
from harness_agent.security import (
    HITLApprovalDeniedError,
    HumanInTheLoopMiddleware,
    PermissionBoundary,
    PIIMiddleware,
    SandboxConfig,
    safe_run,
)
from harness_agent.tools.registry import ToolRegistry

from harness_agent.loaders import (
    BackendConfig,
    BackendRouteConfig,
    ConfigLoader,
    ConfigParseError,
    DEFAULT_MIDDLEWARE_ORDER,
    FeaturesConfig,
    HarnessConfig,
    MiddlewareParamConfig,
    SecurityConfig,
)

__version__ = "0.2.0"

__all__ = [
    "ABTestResult",
    "AgentABTester",
    "AgentEvaluator",
    "AgentExecutionError",
    "AgentMetrics",
    "AgentOrchestrator",
    "AgentRequest",
    "AgentResponse",
    "AlertConfig",
    "AlertEvaluator",
    "AlertRule",
    "AlertSeverity",
    "BackendConfig",
    "BackendRouteConfig",
    "CLIAgent",
    "ConfigLoader",
    "ConfigParseError",
    "DEFAULT_MIDDLEWARE_ORDER",
    "EvaluationResult",
    "FeaturesConfig",
    "HITLApprovalDeniedError",
    "HarnessAgent",
    "HarnessConfig",
    "HarnessError",
    "HealthDashboardResponse",
    "HumanInTheLoopMiddleware",
    "HybridMemory",
    "LoggingConfig",
    "MemoryItem",
    "MetricsResponse",
    "MiddlewareParamConfig",
    "PIIMiddleware",
    "PermissionBoundary",
    "SandboxConfig",
    "SecurityConfig",
    "StreamingConfig",
    "StructuredLoggingMiddleware",
    "SubagentTimeoutError",
    "TenantAgentManager",
    "ToolExecutionError",
    "ToolNotFoundError",
    "ToolRegistry",
    "TracingConfig",
    "configure_debug_mode",
    "configure_tracing",
    "create_cli_agent",
    "create_server_app",
    "is_debug_enabled",
    "safe_run",
]
