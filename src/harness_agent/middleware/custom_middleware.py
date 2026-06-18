"""Custom middleware implementations.

Full logging/metrics middleware deferred to Phase 7 (Monitoring).
Phase 3 provides the minimal LoggingMiddleware stub.
"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware


class LoggingMiddleware(AgentMiddleware):
    """Logs tool calls for observability.

    Minimal implementation for Phase 3 — passes through all calls.
    Full logging (structured logs, metrics, spans) deferred to Phase 7.
    """

    def wrap_tool_call(self, request: Any, handler: Any) -> Any:
        """Wrap tool calls with passthrough logging.

        Args:
            request: The tool call request.
            handler: The next handler in the chain.

        Returns:
            The result from the handler.
        """
        # Pass through — full logging deferred to Phase 7
        return handler(request)
