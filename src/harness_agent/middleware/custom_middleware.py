"""Custom middleware implementations.

Phase 7 — LoggingMiddleware now re-exports StructuredLoggingMiddleware
from the monitoring package for full structured JSON event logging.
"""

from __future__ import annotations

from harness_agent.monitoring.middleware import (
    StructuredLoggingMiddleware as LoggingMiddleware,
)

__all__ = ["LoggingMiddleware"]
