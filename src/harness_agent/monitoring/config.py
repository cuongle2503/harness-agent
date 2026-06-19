"""Monitoring configuration dataclasses.

Phase 7.1-7.4 — Streaming, logging, alerting, and tracing configuration.
See: AIDLC Lifecycle §7, docs/guides/plans/07-monitoring.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from logging import CRITICAL, DEBUG, ERROR, INFO, WARNING
from typing import Any


@dataclass
class StreamingConfig:
    """Multi-mode streaming configuration for real-time monitoring.

    Attributes:
        modes: Stream modes to enable. Default includes messages, updates,
            custom, and tasks for comprehensive monitoring.
        subgraphs: Whether to enable subgraph streaming for subagent tracking.
        version: Stream protocol version ("v1" or "v2").
        route_to_monitoring: Whether to route stream events to monitoring system.
        custom_events_enabled: Whether to emit custom events for long-running tasks.
    """

    modes: list[str] = field(default_factory=lambda: [
        "messages", "updates", "custom", "tasks",
    ])
    subgraphs: bool = True
    version: str = "v2"
    route_to_monitoring: bool = True
    custom_events_enabled: bool = True

    def to_stream_kwargs(self) -> dict[str, Any]:
        """Convert to kwargs for agent.astream()."""
        return {
            "stream_mode": self.modes,
            "subgraphs": self.subgraphs,
            "version": self.version,
        }


@dataclass
class LoggingConfig:
    """Structured JSON logging configuration.

    Attributes:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Path to log file. None disables file logging.
        log_format: Output format — "json" for structured, "text" for human-readable.
        rotation_size_mb: Max log file size in MB before rotation (default 10).
        backup_count: Number of rotated log files to retain.
        exclude_sensitive: Whether to redact PII/API keys from log output.
        correlation_id_field: Field name for correlation ID in log events.
        enable_console: Whether to also log to stderr.
    """

    log_level: int = INFO
    log_file: str | None = "agent.log"
    log_format: str = "json"
    rotation_size_mb: int = 10
    backup_count: int = 5
    exclude_sensitive: bool = True
    correlation_id_field: str = "thread_id"
    enable_console: bool = True

    def level_name(self) -> str:
        """Return the human-readable log level name."""
        names = {
            DEBUG: "DEBUG",
            INFO: "INFO",
            WARNING: "WARNING",
            ERROR: "ERROR",
            CRITICAL: "CRITICAL",
        }
        return names.get(self.log_level, "INFO")


@dataclass
class AlertChannelConfig:
    """Configuration for a single alert notification channel.

    Attributes:
        channel_type: Channel type — "slack", "pagerduty", "email", or "webhook".
        enabled: Whether this channel is currently active.
        endpoint: Webhook URL, email address, or service key.
        min_severity: Minimum severity level to route to this channel.
    """

    channel_type: str
    enabled: bool = False
    endpoint: str = ""
    min_severity: str = "HIGH"


@dataclass
class AlertConfig:
    """Global alerting configuration.

    Attributes:
        enabled: Master toggle for all alerting.
        channels: Configured notification channels.
        rule_check_interval_seconds: How often alert rules are evaluated.
        cooldown_seconds: Minimum seconds between repeated alerts of the same type.
    """

    enabled: bool = True
    channels: list[AlertChannelConfig] = field(default_factory=list)
    rule_check_interval_seconds: float = 30.0
    cooldown_seconds: float = 300.0
