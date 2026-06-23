"""Custom middleware for the agent harness."""

from harness_agent.monitoring.middleware import (
    StructuredLoggingMiddleware as LoggingMiddleware,
)

__all__ = ["LoggingMiddleware"]
