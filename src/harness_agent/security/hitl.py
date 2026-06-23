"""Human-in-the-Loop (HITL) middleware.

Phase 5 — Security Hardening (per AIDLC §5.5 HITL Configuration).

Intercepts dangerous tool calls and requires human approval before execution.
Based on LangChain's AgentMiddleware pattern.

Approval flow:
1. Tool call is intercepted
2. Approval callback is invoked with tool details
3. If callback returns True → proceed
4. If callback returns False → raise HITLApprovalDeniedError
5. If no callback configured → deny by default (fail-safe)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware

from harness_agent.core.exceptions import HarnessError

logger = logging.getLogger(__name__)


class HITLApprovalDeniedError(HarnessError):
    """Raised when a human operator denies a tool call."""

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        super().__init__(
            f"[HITL] Tool '{tool_name}' execution denied — approval required"
        )


class HumanInTheLoopMiddleware(AgentMiddleware):
    """Middleware that requires human approval for dangerous tool calls.

    Tool risk classification:
    ┌──────────────────┬───────────────┬──────────────────┐
    │ Tool             │ Risk Level    │ Requires Approval │
    ├──────────────────┼───────────────┼──────────────────┤
    │ read_file        │ Low           │ No               │
    │ write_file       │ HIGH          │ YES              │
    │ edit_file        │ HIGH          │ YES              │
    │ execute_command  │ CRITICAL      │ YES              │
    │ task (subagent)  │ HIGH          │ YES              │
    │ glob/grep        │ Low           │ No               │
    │ web_search       │ Low           │ No               │
    │ fetch_url        │ Medium        │ YES (production) │
    │ execute_python   │ CRITICAL      │ YES              │
    └──────────────────┴───────────────┴──────────────────┘

    Attributes:
        interrupt_on: Dict mapping tool names to whether approval is required.
        production_mode: If True, all non-read-only tools require approval.
        approval_callback: Callable(tool_name, request) -> bool.
            Return True to approve, False to deny.
            If None, all dangerous calls are DENIED (fail-safe).
    """

    def __init__(
        self,
        interrupt_on: dict[str, bool] | None = None,
        production_mode: bool = False,
        approval_callback: Callable[[str, Any], bool] | None = None,
    ) -> None:
        super().__init__()
        self.interrupt_on = interrupt_on or _DEFAULT_DANGEROUS_TOOLS
        self.production_mode = production_mode
        self.approval_callback = approval_callback

    def wrap_tool_call(self, request: Any, handler: Any) -> Any:
        """Intercept tool calls and require human approval for dangerous ones.

        If approval is required:
        1. Call approval_callback(tool_name, request) if configured
        2. If callback returns True → proceed
        3. If callback returns False or is not configured → deny

        Args:
            request: The tool call request with a 'tool' attribute.
            handler: The next handler in the middleware chain.

        Returns:
            The result from the handler.

        Raises:
            HITLApprovalDeniedError: If the tool call is denied.
        """
        tool_name = getattr(request, "tool", "unknown")

        if self._requires_approval(tool_name):
            logger.info(
                "HITL: Tool '%s' requires approval (production=%s)",
                tool_name, self.production_mode,
            )

            approved = False
            if self.approval_callback is not None:
                try:
                    approved = self.approval_callback(tool_name, request)
                except Exception as exc:
                    logger.exception(
                        "HITL approval callback failed for tool '%s'", tool_name
                    )
                    raise HITLApprovalDeniedError(tool_name) from exc

            if not approved:
                raise HITLApprovalDeniedError(tool_name)

        return handler(request)

    def _requires_approval(self, tool_name: str) -> bool:
        """Check if a tool requires human approval.

        Args:
            tool_name: The name of the tool being called.

        Returns:
            True if human approval is required.
        """
        if self.production_mode:
            # In production, ALL tools except read-only ones need approval
            return tool_name not in _READ_ONLY_TOOLS
        return self.interrupt_on.get(tool_name, False)


# Tools that require human approval (development mode)
_DEFAULT_DANGEROUS_TOOLS: dict[str, bool] = {
    "write_file": True,
    "execute_command": True,
    "task": True,
    "edit_file": True,
    "execute_python": True,
    "fetch_url": False,  # Validated by input schema — lower risk
}

# Tools that are always safe (read-only)
_READ_ONLY_TOOLS: set[str] = {
    "read_file", "glob", "grep", "web_search",
}


__all__ = ["HITLApprovalDeniedError", "HumanInTheLoopMiddleware"]
