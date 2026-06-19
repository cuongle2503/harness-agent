"""Unit tests for StructuredLoggingMiddleware."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from harness_agent.monitoring.metrics import AgentMetrics
from harness_agent.monitoring.middleware import (
    LogEvent,
    StructuredLoggingMiddleware,
)


class MockRequest:
    """Minimal mock of a tool/model call request with runtime thread_id."""

    def __init__(self, tool: str = "test_tool", thread_id: str = "thread-1") -> None:
        self.tool = MagicMock()
        self.tool.name = tool
        self.runtime = MagicMock()
        self.runtime.thread_id = thread_id
        self.model = "deepseek-v4-flash"


class MockResult:
    """Minimal mock of an LLM result with usage_metadata."""

    def __init__(self, tokens: int = 42) -> None:
        self.usage_metadata = {"total_tokens": tokens}


# ── LogEvent ────────────────────────────────────────────────────────────────


class TestLogEvent:
    """Tests for LogEvent dataclass."""

    def test_to_json_produces_valid_json(self) -> None:
        event = LogEvent(
            event="tool_call",
            timestamp="2026-06-19T12:00:00Z",
            thread_id="thread-1",
            duration_ms=150.5,
            status="success",
            metadata={"tool": "search"},
        )
        json_str = event.to_json()
        parsed = json.loads(json_str)
        assert parsed["event"] == "tool_call"
        assert parsed["thread_id"] == "thread-1"

    def test_to_json_includes_all_fields(self) -> None:
        event = LogEvent(
            event="model_call",
            timestamp="2026-06-19T12:00:00Z",
            thread_id="t1",
            duration_ms=500.0,
            status="success",
            metadata={"model": "deepseek", "tokens": 42},
        )
        parsed = json.loads(event.to_json())
        assert parsed["event"] == "model_call"
        assert parsed["duration_ms"] == 500.0
        assert parsed["status"] == "success"
        assert parsed["model"] == "deepseek"
        assert parsed["tokens"] == 42

    def test_default_metadata_is_empty_dict(self) -> None:
        event = LogEvent(
            event="test",
            timestamp="",
            thread_id="",
            duration_ms=0,
            status="pending",
        )
        assert event.metadata == {}


# ── StructuredLoggingMiddleware Init ─────────────────────────────────────────


class TestStructuredLoggingMiddlewareInit:
    """Tests for middleware initialization."""

    def test_default_config_used(self) -> None:
        mw = StructuredLoggingMiddleware()
        assert mw.config is not None
        assert mw.metrics is not None

    def test_custom_metrics_accepted(self) -> None:
        metrics = AgentMetrics()
        mw = StructuredLoggingMiddleware(metrics=metrics)
        assert mw.metrics is metrics

    def test_inherits_agent_middleware(self) -> None:
        from langchain.agents.middleware import AgentMiddleware
        mw = StructuredLoggingMiddleware()
        assert isinstance(mw, AgentMiddleware)


# ── wrap_tool_call ──────────────────────────────────────────────────────────


class TestWrapToolCall:
    """Tests for synchronous wrap_tool_call."""

    def test_successful_call_updates_metrics(self) -> None:
        metrics = AgentMetrics()
        mw = StructuredLoggingMiddleware(metrics=metrics)
        def handler(r: object) -> str:
            return "result"
        result = mw.wrap_tool_call(MockRequest("search"), handler)
        assert result == "result"
        assert metrics.tool_calls == 1
        assert metrics.tool_errors == 0

    def test_failed_call_updates_error_metrics(self) -> None:
        metrics = AgentMetrics()
        mw = StructuredLoggingMiddleware(metrics=metrics)

        def failing_handler(r: object) -> str:
            raise ValueError("tool failed")

        with pytest.raises(ValueError, match="tool failed"):
            mw.wrap_tool_call(MockRequest("bad_tool"), failing_handler)
        assert metrics.tool_calls == 0
        assert metrics.tool_errors == 1

    def test_error_propagates_after_logging(self) -> None:
        mw = StructuredLoggingMiddleware()

        def handler(r: object) -> str:
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            mw.wrap_tool_call(MockRequest("x"), handler)

    def test_latency_tracked_for_tool_calls(self) -> None:
        metrics = AgentMetrics()
        mw = StructuredLoggingMiddleware(metrics=metrics)
        mw.wrap_tool_call(MockRequest("search"), lambda r: "result")
        assert len(metrics.tool_latencies) == 1
        assert metrics.tool_latencies[0] >= 0


# ── wrap_model_call ──────────────────────────────────────────────────────────


class TestWrapModelCall:
    """Tests for synchronous wrap_model_call."""

    def test_successful_call_updates_metrics(self) -> None:
        metrics = AgentMetrics()
        mw = StructuredLoggingMiddleware(metrics=metrics)
        mw.wrap_model_call(MockRequest(), lambda r: MockResult(42))
        assert metrics.model_calls == 1
        assert metrics.model_errors == 0
        assert metrics.total_tokens == 42

    def test_failed_call_updates_error_metrics(self) -> None:
        metrics = AgentMetrics()
        mw = StructuredLoggingMiddleware(metrics=metrics)

        def failing_handler(r: object) -> str:
            raise ConnectionError("timeout")

        with pytest.raises(ConnectionError, match="timeout"):
            mw.wrap_model_call(MockRequest(), failing_handler)
        assert metrics.model_calls == 0
        assert metrics.model_errors == 1

    def test_error_propagates_after_logging(self) -> None:
        mw = StructuredLoggingMiddleware()

        def handler(r: object) -> str:
            raise RuntimeError("api error")

        with pytest.raises(RuntimeError, match="api error"):
            mw.wrap_model_call(MockRequest(), handler)


# ── Async wrappers ──────────────────────────────────────────────────────────


class TestAsyncWrappers:
    """Tests for async wrap_tool_call and wrap_model_call."""

    @pytest.mark.asyncio
    async def test_awrap_tool_call_success(self) -> None:
        metrics = AgentMetrics()
        mw = StructuredLoggingMiddleware(metrics=metrics)

        async def handler(r: object) -> str:
            return "async result"

        result = await mw.awrap_tool_call(MockRequest("search"), handler)
        assert result == "async result"
        assert metrics.tool_calls == 1

    @pytest.mark.asyncio
    async def test_awrap_tool_call_error(self) -> None:
        metrics = AgentMetrics()
        mw = StructuredLoggingMiddleware(metrics=metrics)

        async def handler(r: object) -> str:
            raise ValueError("async fail")

        with pytest.raises(ValueError, match="async fail"):
            await mw.awrap_tool_call(MockRequest("bad"), handler)
        assert metrics.tool_errors == 1

    @pytest.mark.asyncio
    async def test_awrap_model_call_success(self) -> None:
        metrics = AgentMetrics()
        mw = StructuredLoggingMiddleware(metrics=metrics)

        async def handler(r: object) -> MockResult:
            return MockResult(100)

        await mw.awrap_model_call(MockRequest(), handler)
        assert metrics.model_calls == 1
        assert metrics.total_tokens == 100

    @pytest.mark.asyncio
    async def test_awrap_model_call_error(self) -> None:
        metrics = AgentMetrics()
        mw = StructuredLoggingMiddleware(metrics=metrics)

        async def handler(r: object) -> str:
            raise RuntimeError("async model fail")

        with pytest.raises(RuntimeError, match="async model fail"):
            await mw.awrap_model_call(MockRequest(), handler)
        assert metrics.model_errors == 1


# ── Public event recording ──────────────────────────────────────────────────


class TestEventRecording:
    """Tests for public record_* methods."""

    def test_record_subagent_spawn_emits_event(self) -> None:
        metrics = AgentMetrics()
        mw = StructuredLoggingMiddleware(metrics=metrics)
        mw.record_subagent_spawn("researcher", "t1")
        assert metrics.subagent_spawns == 1

    def test_record_subagent_complete_emits_event(self) -> None:
        metrics = AgentMetrics()
        mw = StructuredLoggingMiddleware(metrics=metrics)
        mw.record_subagent_complete("researcher", "t1", 500.0)
        assert metrics.subagent_completes == 1

    def test_record_summarization_emits_event(self) -> None:
        metrics = AgentMetrics()
        mw = StructuredLoggingMiddleware(metrics=metrics)
        mw.record_summarization("auto", 10000, 2000, "t1")
        assert metrics.summarization_triggers == 1

    def test_record_hitl_approval_emits_event_approved(self) -> None:
        metrics = AgentMetrics()
        mw = StructuredLoggingMiddleware(metrics=metrics)
        mw.record_hitl_approval("write_file", True, "t1")
        assert metrics.hitl_approvals == 1

    def test_record_hitl_approval_emits_event_rejected(self) -> None:
        metrics = AgentMetrics()
        mw = StructuredLoggingMiddleware(metrics=metrics)
        mw.record_hitl_approval("write_file", False, "t1")
        assert metrics.hitl_rejections == 1


# ── Correlation ID extraction ───────────────────────────────────────────────


class TestCorrelationIdExtraction:
    """Tests for _extract_thread_id."""

    def test_thread_id_from_runtime(self) -> None:
        mw = StructuredLoggingMiddleware()
        req = MockRequest(thread_id="my-thread")
        tid = mw._extract_thread_id(req)
        assert tid == "my-thread"

    def test_thread_id_from_configurable_dict(self) -> None:
        mw = StructuredLoggingMiddleware()
        req = {"configurable": {"thread_id": "cfg-thread"}}
        tid = mw._extract_thread_id(req)
        assert tid == "cfg-thread"

    def test_thread_id_fallback_unknown(self) -> None:
        mw = StructuredLoggingMiddleware()
        tid = mw._extract_thread_id("plain_string")
        assert tid == "unknown"


# ── Tool name extraction ────────────────────────────────────────────────────


class TestToolNameExtraction:
    """Tests for _extract_tool_name."""

    def test_tool_name_from_object(self) -> None:
        mw = StructuredLoggingMiddleware()
        req = MockRequest("my_tool")
        assert mw._extract_tool_name(req) == "my_tool"

    def test_tool_name_from_dict(self) -> None:
        mw = StructuredLoggingMiddleware()
        req = {"tool_call": {"name": "dict_tool"}}
        assert mw._extract_tool_name(req) == "dict_tool"

    def test_tool_name_fallback_unknown(self) -> None:
        mw = StructuredLoggingMiddleware()
        assert mw._extract_tool_name("not_a_request") == "unknown"


# ── Lifecycle hooks ──────────────────────────────────────────────────────────


class TestLifecycleHooks:
    """Tests for before_agent / after_agent hooks."""

    def test_before_agent_returns_none(self) -> None:
        mw = StructuredLoggingMiddleware()
        # AgentState needs at least 'messages' key
        state: dict[str, Any] = {"messages": []}
        assert mw.before_agent(state, None) is None  # type: ignore[arg-type]

    def test_after_agent_returns_none(self) -> None:
        mw = StructuredLoggingMiddleware()
        state: dict[str, Any] = {"messages": []}
        assert mw.after_agent(state, None) is None  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_abefore_agent_returns_none(self) -> None:
        mw = StructuredLoggingMiddleware()
        state: dict[str, Any] = {"messages": []}
        assert await mw.abefore_agent(state, None) is None  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_aafter_agent_returns_none(self) -> None:
        mw = StructuredLoggingMiddleware()
        state: dict[str, Any] = {"messages": []}
        assert await mw.aafter_agent(state, None) is None  # type: ignore[arg-type]
