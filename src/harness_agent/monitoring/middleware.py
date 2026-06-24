"""StructuredLoggingMiddleware — JSON event logging for agent activity.

Phase 7.2 — Wraps tool and model calls with timing, structured logging,
and automatic metrics recording. All events carry a correlation ID.

See: docs/guides/plans/07-monitoring.md §7.2
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from langchain.agents.middleware import AgentMiddleware

from harness_agent.monitoring.config import LoggingConfig
from harness_agent.monitoring.metrics import AgentMetrics

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Log event data model
# ---------------------------------------------------------------------------


@dataclass
class LogEvent:
    """Schema for a single structured log event.

    Attributes:
        event: Event type name (e.g. "tool_call", "model_call_error").
        timestamp: ISO-8601 timestamp (UTC).
        thread_id: Correlation ID for tracing across events.
        duration_ms: Elapsed milliseconds.
        status: "success", "error", or "pending".
        metadata: Extra event-specific key-value pairs.
    """

    event: str
    timestamp: str
    thread_id: str
    duration_ms: float
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Serialize to a single-line JSON string."""
        return json.dumps(
            {
                "event": self.event,
                "timestamp": self.timestamp,
                "thread_id": self.thread_id,
                "duration_ms": self.duration_ms,
                "status": self.status,
                **self.metadata,
            },
            default=str,
        )


# ---------------------------------------------------------------------------
# Structured logging middleware
# ---------------------------------------------------------------------------


class StructuredLoggingMiddleware(AgentMiddleware):
    """Middleware that emits structured JSON log events for all agent activity.

    Wraps ``wrap_tool_call`` and ``wrap_model_call`` (both sync and async)
    with timing, structured event emission, and automatic metrics recording.
    Every event includes a correlation ID (``thread_id``) for tracing.

    Log event types emitted:
    - ``tool_call`` / ``tool_call_error``
    - ``model_call`` / ``model_call_error``
    - ``subagent_spawn`` / ``subagent_complete``
    - ``summarization``
    - ``hitl_approval``

    Attributes:
        config: Logging configuration controlling output and format.
        metrics: Shared ``AgentMetrics`` collector that this middleware
            writes into on every event.
    """

    def __init__(
        self,
        config: LoggingConfig | None = None,
        metrics: AgentMetrics | None = None,
    ) -> None:
        super().__init__()
        self.config = config or LoggingConfig()
        self.metrics = metrics or AgentMetrics()

    # ------------------------------------------------------------------
    # Synchronous wrappers
    # ------------------------------------------------------------------

    def wrap_tool_call(self, request: Any, handler: Any) -> Any:
        """Wrap a synchronous tool call with logging and metrics."""
        tool_name = self._extract_tool_name(request)
        thread_id = self._extract_thread_id(request)
        start = time.monotonic()
        try:
            result = handler(request)
            elapsed = (time.monotonic() - start) * 1000
            self.metrics.record_tool_call(tool_name, elapsed, success=True)
            self._emit(
                LogEvent(
                    event="tool_call",
                    timestamp=self._now_iso(),
                    thread_id=thread_id,
                    duration_ms=round(elapsed, 2),
                    status="success",
                    metadata={"tool": tool_name},
                )
            )
            return result
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            self.metrics.record_tool_call(tool_name, elapsed, success=False)
            self._emit(
                LogEvent(
                    event="tool_call_error",
                    timestamp=self._now_iso(),
                    thread_id=thread_id,
                    duration_ms=round(elapsed, 2),
                    status="error",
                    metadata={
                        "tool": tool_name,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    },
                )
            )
            raise

    def wrap_model_call(self, request: Any, handler: Any) -> Any:
        """Wrap a synchronous model call with logging and metrics."""
        thread_id = self._extract_thread_id(request)
        model = getattr(request, "model", "unknown")
        start = time.monotonic()
        try:
            result = handler(request)
            elapsed = (time.monotonic() - start) * 1000
            tokens_total, tokens_in, tokens_out = self._extract_tokens(result)
            self.metrics.record_model_call(
                elapsed,
                success=True,
                tokens=tokens_total,
                input_tokens=tokens_in,
                output_tokens=tokens_out,
            )
            self._emit(
                LogEvent(
                    event="model_call",
                    timestamp=self._now_iso(),
                    thread_id=thread_id,
                    duration_ms=round(elapsed, 2),
                    status="success",
                    metadata={
                        "model": model,
                        "tokens": tokens_total,
                        "input_tokens": tokens_in,
                        "output_tokens": tokens_out,
                    },
                )
            )
            return result
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            self.metrics.record_model_call(elapsed, success=False)
            self._emit(
                LogEvent(
                    event="model_call_error",
                    timestamp=self._now_iso(),
                    thread_id=thread_id,
                    duration_ms=round(elapsed, 2),
                    status="error",
                    metadata={
                        "model": model,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    },
                )
            )
            raise

    # ------------------------------------------------------------------
    # Async wrappers
    # ------------------------------------------------------------------

    async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
        """Wrap an asynchronous tool call with logging and metrics."""
        tool_name = self._extract_tool_name(request)
        thread_id = self._extract_thread_id(request)
        start = time.monotonic()
        try:
            result = await handler(request)
            elapsed = (time.monotonic() - start) * 1000
            self.metrics.record_tool_call(tool_name, elapsed, success=True)
            self._emit(
                LogEvent(
                    event="tool_call",
                    timestamp=self._now_iso(),
                    thread_id=thread_id,
                    duration_ms=round(elapsed, 2),
                    status="success",
                    metadata={"tool": tool_name},
                )
            )
            return result
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            self.metrics.record_tool_call(tool_name, elapsed, success=False)
            self._emit(
                LogEvent(
                    event="tool_call_error",
                    timestamp=self._now_iso(),
                    thread_id=thread_id,
                    duration_ms=round(elapsed, 2),
                    status="error",
                    metadata={
                        "tool": tool_name,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    },
                )
            )
            raise

    async def awrap_model_call(self, request: Any, handler: Any) -> Any:
        """Wrap an asynchronous model call with logging and metrics."""
        thread_id = self._extract_thread_id(request)
        model = getattr(request, "model", "unknown")
        start = time.monotonic()
        try:
            result = await handler(request)
            elapsed = (time.monotonic() - start) * 1000
            tokens_total, tokens_in, tokens_out = self._extract_tokens(result)
            self.metrics.record_model_call(
                elapsed,
                success=True,
                tokens=tokens_total,
                input_tokens=tokens_in,
                output_tokens=tokens_out,
            )
            self._emit(
                LogEvent(
                    event="model_call",
                    timestamp=self._now_iso(),
                    thread_id=thread_id,
                    duration_ms=round(elapsed, 2),
                    status="success",
                    metadata={
                        "model": model,
                        "tokens": tokens_total,
                        "input_tokens": tokens_in,
                        "output_tokens": tokens_out,
                    },
                )
            )
            return result
        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            self.metrics.record_model_call(elapsed, success=False)
            self._emit(
                LogEvent(
                    event="model_call_error",
                    timestamp=self._now_iso(),
                    thread_id=thread_id,
                    duration_ms=round(elapsed, 2),
                    status="error",
                    metadata={
                        "model": model,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    },
                )
            )
            raise

    # ------------------------------------------------------------------
    # Public event recording (called by orchestrator / external code)
    # ------------------------------------------------------------------

    def record_subagent_spawn(
        self, subagent_name: str, thread_id: str
    ) -> None:
        """Emit a ``subagent_spawn`` event and update metrics."""
        self.metrics.record_subagent_spawn(subagent_name)
        self._emit(
            LogEvent(
                event="subagent_spawn",
                timestamp=self._now_iso(),
                thread_id=thread_id,
                duration_ms=0.0,
                status="pending",
                metadata={"subagent_name": subagent_name},
            )
        )

    def record_subagent_complete(
        self, subagent_name: str, thread_id: str, duration_ms: float
    ) -> None:
        """Emit a ``subagent_complete`` event and update metrics."""
        self.metrics.record_subagent_complete(subagent_name)
        self._emit(
            LogEvent(
                event="subagent_complete",
                timestamp=self._now_iso(),
                thread_id=thread_id,
                duration_ms=round(duration_ms, 2),
                status="success",
                metadata={"subagent_name": subagent_name},
            )
        )

    def record_summarization(
        self,
        trigger: str,
        tokens_before: int,
        tokens_after: int,
        thread_id: str,
    ) -> None:
        """Emit a ``summarization`` event and update metrics."""
        self.metrics.record_summarization(tokens_before, tokens_after)
        self._emit(
            LogEvent(
                event="summarization",
                timestamp=self._now_iso(),
                thread_id=thread_id,
                duration_ms=0.0,
                status="success",
                metadata={
                    "trigger": trigger,
                    "tokens_before": tokens_before,
                    "tokens_after": tokens_after,
                },
            )
        )

    def record_hitl_approval(
        self, tool: str, approved: bool, thread_id: str
    ) -> None:
        """Emit a ``hitl_approval`` event and update metrics."""
        self.metrics.record_hitl_decision(tool, approved=approved)
        self._emit(
            LogEvent(
                event="hitl_approval",
                timestamp=self._now_iso(),
                thread_id=thread_id,
                duration_ms=0.0,
                status="success" if approved else "error",
                metadata={"tool": tool, "approved": approved},
            )
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _emit(self, event: LogEvent) -> None:
        """Emit a log event at the appropriate level.

        Error events are logged at ERROR level; everything else at INFO.
        """
        level = logging.ERROR if event.status == "error" else logging.INFO
        logger.log(level, event.to_json())

    @staticmethod
    def _now_iso() -> str:
        """Return current UTC time as ISO-8601 string (second precision)."""
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    @staticmethod
    def _extract_tool_name(request: Any) -> str:
        """Extract the tool name from a request object.

        Handles multiple request shapes:
        - Object with ``tool`` attribute (LangGraph-style).
        - Dict with ``tool_call.name`` key.
        """
        if hasattr(request, "tool"):
            tool: Any = request.tool
            name: Any = getattr(tool, "name", None)
            return str(name) if name is not None else str(tool)
        if isinstance(request, dict):
            tc: dict[str, Any] = request.get("tool_call", {})
            if isinstance(tc, dict) and "name" in tc:
                return str(tc["name"])
            return "unknown"
        return "unknown"

    @staticmethod
    def _extract_thread_id(request: Any) -> str:
        """Extract the correlation / thread ID from a request.

        Checks multiple locations:
        - ``request.runtime.thread_id`` (LangGraph runtime).
        - ``request.config["configurable"]["thread_id"]``.
        - ``request["configurable"]["thread_id"]`` (plain dict).
        """
        if hasattr(request, "runtime"):
            runtime: Any = getattr(request, "runtime", None)
            if runtime is not None and hasattr(runtime, "thread_id"):
                return str(runtime.thread_id)
        if hasattr(request, "config"):
            config: Any = request.config
            if isinstance(config, dict):
                return str(
                    config.get("configurable", {}).get("thread_id", "unknown")
                )
        if isinstance(request, dict):
            return str(
                request.get("configurable", {}).get("thread_id", "unknown")
            )
        return "unknown"

    @staticmethod
    def _extract_tokens(result: Any) -> tuple[int, int, int]:
        """Extract token counts from a model result.

        Returns (total_tokens, input_tokens, output_tokens).
        """
        total = 0
        inp = 0
        out = 0
        um: dict[str, Any] = {}
        if hasattr(result, "usage_metadata"):
            um = result.usage_metadata or {}
        elif isinstance(result, dict):
            um = result.get("usage_metadata", {})
        if isinstance(um, dict):
            total = int(um.get("total_tokens", 0))
            inp = int(um.get("input_tokens", 0))
            out = int(um.get("output_tokens", 0))
            # Fallback: compute total from input+output if total isn't set
            if not total and (inp or out):
                total = inp + out
        return total, inp, out
