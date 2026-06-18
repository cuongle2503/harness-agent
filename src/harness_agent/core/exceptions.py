"""Exception hierarchy for the agent harness (ADR-009)."""

from __future__ import annotations

_UNSET = object()


class HarnessError(Exception):
    """Base exception for all harness errors."""


class ToolNotFoundError(HarnessError):
    """Raised when a tool is not found in the registry."""

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        super().__init__(
            f"[FATAL][TOOL_NOT_FOUND] Tool '{tool_name}' not found in registry"
        )


class AgentExecutionError(HarnessError):
    """Raised when an agent execution fails.

    Supports pickle roundtrip: when unpickling, original_error
    reconstructs from the stored message and agent_id.
    """

    def __init__(
        self,
        agent_id: str,
        original_error: Exception | None = None,
        *,
        _message: str | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.original_error = original_error
        msg = _message or (
            f"[ERROR][AGENT_EXEC_FAILED] Agent '{agent_id}'"
            f" execution failed: {original_error}"
        )
        super().__init__(msg)

    def __reduce__(self) -> tuple:
        return (
            AgentExecutionError,
            (self.agent_id, self.original_error),
            {"_message": super().__str__()},
        )


class SubagentTimeoutError(HarnessError):
    """Raised when a subagent times out."""

    def __init__(
        self,
        agent_id: str,
        timeout_seconds: float | None = None,
        *,
        _message: str | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.timeout_seconds = timeout_seconds
        msg = _message or (
            f"[WARN][SUBAGENT_TIMEOUT] Subagent '{agent_id}' timed out"
            + (f" after {timeout_seconds}s" if timeout_seconds is not None else "")
        )
        super().__init__(msg)

    def __reduce__(self) -> tuple:
        return (
            SubagentTimeoutError,
            (self.agent_id, self.timeout_seconds),
            {"_message": super().__str__()},
        )


class ToolExecutionError(HarnessError):
    """Raised when a tool execution fails.

    Supports pickle roundtrip: when unpickling, original_error
    reconstructs from the stored message and tool_name.
    """

    def __init__(
        self,
        tool_name: str,
        original_error: Exception | None = None,
        *,
        _message: str | None = None,
    ) -> None:
        self.tool_name = tool_name
        self.original_error = original_error
        msg = _message or (
            f"[ERROR][TOOL_EXEC_FAILED] Tool '{tool_name}'"
            f" execution failed: {original_error}"
        )
        super().__init__(msg)

    def __reduce__(self) -> tuple:
        return (
            ToolExecutionError,
            (self.tool_name, self.original_error),
            {"_message": super().__str__()},
        )
