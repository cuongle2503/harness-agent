"""Integration tests for the full monitoring pipeline.

Tests the /metrics and /dashboard endpoints, middleware-metrics integration,
and structured log output format.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from harness_agent.deployment.server import ServerConfig, create_server_app
from harness_agent.monitoring.metrics import AgentMetrics
from harness_agent.monitoring.middleware import StructuredLoggingMiddleware


@pytest.fixture
def metrics() -> AgentMetrics:
    """Fresh AgentMetrics instance."""
    return AgentMetrics()


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient with a fresh server app."""
    config = ServerConfig(assistant_id="test-monitoring")
    app = create_server_app(config)
    return TestClient(app)


# ── /metrics endpoint ───────────────────────────────────────────────────────


class TestMetricsEndpoint:
    """Tests for GET /metrics."""

    def test_metrics_endpoint_returns_200(self, client: TestClient) -> None:
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_response_is_valid_json(self, client: TestClient) -> None:
        response = client.get("/metrics")
        data = response.json()
        assert isinstance(data, dict)

    def test_metrics_contains_all_9_key_metrics(self, client: TestClient) -> None:
        response = client.get("/metrics")
        data = response.json()
        required_keys = [
            "tool_calls", "tool_errors", "model_calls", "model_errors",
            "tool_call_latency_ms", "llm_call_latency_ms",
            "subagent_spawn_count", "token_usage_total",
            "summarization_triggers", "error_rate", "hitl_approval_rate",
            "task_completion_rate", "total_tasks", "completed_tasks",
            "avg_response_time_ms",
        ]
        for key in required_keys:
            assert key in data, f"Missing key: {key}"

    def test_metrics_all_zero_at_start(self, client: TestClient) -> None:
        response = client.get("/metrics")
        data = response.json()
        assert data["tool_calls"] == 0
        assert data["tool_errors"] == 0
        assert data["model_calls"] == 0
        assert data["error_rate"] == 0.0


# ── /dashboard endpoint ─────────────────────────────────────────────────────


class TestDashboardEndpoint:
    """Tests for GET /dashboard."""

    def test_dashboard_endpoint_returns_200(self, client: TestClient) -> None:
        response = client.get("/dashboard")
        assert response.status_code == 200

    def test_dashboard_has_eight_panels(self, client: TestClient) -> None:
        response = client.get("/dashboard")
        data = response.json()
        # All 8 panel fields should be present
        panel_fields = [
            "agent_status",
            "uptime_seconds",
            "request_rate_per_minute",
            "error_rate",
            "latency_p50_ms",
            "latency_p95_ms",
            "latency_p99_ms",
            "token_usage_per_minute",
            "estimated_cost_usd",
            "subagent_spawns_per_minute",
            "subagent_avg_duration_ms",
            "hitl_approval_rate",
            "hitl_pending_count",
            "memory_items",
        ]
        for field in panel_fields:
            assert field in data, f"Missing dashboard field: {field}"

    def test_dashboard_agent_status_is_healthy(self, client: TestClient) -> None:
        response = client.get("/dashboard")
        data = response.json()
        assert data["agent_status"] == "healthy"


# ── Middleware + Metrics Integration ────────────────────────────────────────


class TestMiddlewareMetricsIntegration:
    """Integration tests for StructuredLoggingMiddleware ↔ AgentMetrics."""

    def test_middleware_updates_shared_metrics(self, metrics: AgentMetrics) -> None:
        mw = StructuredLoggingMiddleware(metrics=metrics)

        class Req:
            tool = type("T", (), {"name": "search"})()
            runtime = type("R", (), {"thread_id": "t1"})()

        mw.wrap_tool_call(Req(), lambda r: "ok")
        assert metrics.tool_calls == 1
        assert len(metrics.tool_latencies) == 1

    def test_metrics_persist_across_calls(self, metrics: AgentMetrics) -> None:
        mw = StructuredLoggingMiddleware(metrics=metrics)

        class Req:
            tool = type("T", (), {"name": "search"})()
            runtime = type("R", (), {"thread_id": "t1"})()

        mw.wrap_tool_call(Req(), lambda r: "ok")
        mw.wrap_tool_call(Req(), lambda r: "ok")
        assert metrics.tool_calls == 2

    def test_error_rate_computed_from_multiple_calls(self, metrics: AgentMetrics) -> None:
        mw = StructuredLoggingMiddleware(metrics=metrics)

        class Req:
            tool = type("T", (), {"name": "search"})()
            runtime = type("R", (), {"thread_id": "t1"})()

        mw.wrap_tool_call(Req(), lambda r: "ok")

        def fail(r: object) -> str:
            raise ValueError("fail")

        with pytest.raises(ValueError):
            mw.wrap_tool_call(Req(), fail)
        # 1 success + 1 error = 50% error rate
        assert metrics.error_rate == 0.5


# ── Log Event Output ────────────────────────────────────────────────────────


class TestLoggingOutput:
    """Tests for structured log output format."""

    def test_logevent_to_json_is_valid(self) -> None:
        from harness_agent.monitoring.middleware import LogEvent

        event = LogEvent(
            event="tool_call",
            timestamp="2026-06-19T12:00:00Z",
            thread_id="thread-1",
            duration_ms=150.0,
            status="success",
            metadata={"tool": "search"},
        )
        parsed = json.loads(event.to_json())
        assert parsed["event"] == "tool_call"
        assert parsed["thread_id"] == "thread-1"
        assert parsed["duration_ms"] == 150.0
        assert parsed["tool"] == "search"

    def test_logevent_error_includes_error_fields(self) -> None:
        from harness_agent.monitoring.middleware import LogEvent

        event = LogEvent(
            event="tool_call_error",
            timestamp="2026-06-19T12:00:00Z",
            thread_id="t1",
            duration_ms=100.0,
            status="error",
            metadata={
                "tool": "bad_tool",
                "error": "something went wrong",
                "error_type": "ValueError",
            },
        )
        parsed = json.loads(event.to_json())
        assert parsed["status"] == "error"
        assert parsed["error"] == "something went wrong"
        assert parsed["error_type"] == "ValueError"

    @pytest.mark.asyncio
    async def test_async_middleware_produces_log_events(
        self, metrics: AgentMetrics
    ) -> None:
        mw = StructuredLoggingMiddleware(metrics=metrics)

        class Req:
            tool = type("T", (), {"name": "search"})()
            runtime = type("R", (), {"thread_id": "t1"})()

        async def handler(r: object) -> str:
            return "async ok"

        result = await mw.awrap_tool_call(Req(), handler)
        assert result == "async ok"
        assert metrics.tool_calls == 1


# ── /sessions endpoint ────────────────────────────────────────────────────────


class TestSessionsEndpoint:
    """Tests for GET /sessions."""

    def test_sessions_endpoint_returns_200(self, client: TestClient) -> None:
        response = client.get("/sessions")
        assert response.status_code == 200

    def test_sessions_endpoint_returns_list(self, client: TestClient) -> None:
        response = client.get("/sessions")
        data = response.json()
        assert isinstance(data, list)

    def test_sessions_starts_empty(self, client: TestClient) -> None:
        """Before any agent invocations, session list should be empty."""
        response = client.get("/sessions")
        data = response.json()
        assert data == []

    def test_sessions_endpoint_valid_json(self, client: TestClient) -> None:
        """Sessions data is valid JSON with correct schema when empty."""
        response = client.get("/sessions")
        data = response.json()
        assert isinstance(data, list)
        assert response.headers["content-type"] == "application/json"
