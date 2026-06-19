"""Monitoring and observability package for the agent harness.

Phase 7 modules:
- config: Streaming, logging, and alert dataclass configurations
- streaming: Multi-mode streaming configuration and event routing
- metrics: AgentMetrics dataclass with 9 key metrics
- middleware: StructuredLoggingMiddleware extending AgentMiddleware
- alerts: Alert rules, severity levels, alert evaluator
- tracing: LangChain tracing environment setup
- dashboard: Health dashboard data models and /metrics response
- debug: Debug mode toggle (DEEPAGENTS_DEBUG)
"""

from harness_agent.monitoring.alerts import (
    Alert,
    AlertEvaluator,
    AlertRule,
    AlertSeverity,
    default_alert_rules,
)
from harness_agent.monitoring.config import (
    AlertChannelConfig,
    AlertConfig,
    LoggingConfig,
    StreamingConfig,
)
from harness_agent.monitoring.dashboard import (
    HealthDashboardResponse,
    MetricsResponse,
    build_dashboard_response,
)
from harness_agent.monitoring.debug import (
    configure_debug_mode,
    is_debug_enabled,
)
from harness_agent.monitoring.metrics import AgentMetrics
from harness_agent.monitoring.middleware import (
    LogEvent,
    StructuredLoggingMiddleware,
)
from harness_agent.monitoring.streaming import (
    StreamEvent,
    route_stream_to_monitoring,
)
from harness_agent.monitoring.tracing import TracingConfig, configure_tracing

__all__ = [
    "AgentMetrics",
    "Alert",
    "AlertChannelConfig",
    "AlertConfig",
    "AlertEvaluator",
    "AlertRule",
    "AlertSeverity",
    "HealthDashboardResponse",
    "LogEvent",
    "LoggingConfig",
    "MetricsResponse",
    "StreamEvent",
    "StreamingConfig",
    "StructuredLoggingMiddleware",
    "TracingConfig",
    "build_dashboard_response",
    "configure_debug_mode",
    "configure_tracing",
    "default_alert_rules",
    "is_debug_enabled",
    "route_stream_to_monitoring",
]
