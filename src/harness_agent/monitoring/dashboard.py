"""Health dashboard data models and metric serialization.

Phase 7.6 — Pydantic response models for the /metrics and /dashboard
endpoints plus the build_dashboard_response helper.

See: docs/guides/plans/07-monitoring.md §7.6
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from harness_agent.monitoring.metrics import AgentMetrics

# ---------------------------------------------------------------------------
# /metrics response
# ---------------------------------------------------------------------------


class MetricsResponse(BaseModel):
    """Response model for the ``GET /metrics`` endpoint.

    Contains all 9 key metrics plus percentile distributions.
    """

    tool_calls: int = Field(..., description="Total successful tool invocations")
    tool_errors: int = Field(..., description="Total tool call failures")
    model_calls: int = Field(..., description="Total successful LLM invocations")
    model_errors: int = Field(..., description="Total LLM call failures")
    tool_call_latency_ms: float = Field(
        ..., description="Average tool call latency (ms)"
    )
    llm_call_latency_ms: float = Field(
        ..., description="Average LLM call latency (ms)"
    )
    subagent_spawn_count: int = Field(
        ..., description="Total subagents spawned"
    )
    token_usage_total: int = Field(..., description="Cumulative token usage")
    input_tokens: int = Field(..., description="Total input/prompt tokens")
    output_tokens: int = Field(..., description="Total output/completion tokens")
    summarization_triggers: int = Field(
        ..., description="Total summarization triggers"
    )
    error_rate: float = Field(..., description="Error rate (0.0–1.0)")
    hitl_approval_rate: float = Field(
        ..., description="HITL approval rate (0.0–1.0)"
    )
    task_completion_rate: float = Field(
        ..., description="Task completion rate (0.0–1.0)"
    )
    total_tasks: int = Field(..., description="Total tasks received")
    completed_tasks: int = Field(..., description="Tasks completed successfully")
    avg_response_time_ms: float = Field(
        ..., description="Average response time (ms)"
    )
    p50_tool_latency_ms: float = Field(..., description="P50 tool latency (ms)")
    p95_tool_latency_ms: float = Field(..., description="P95 tool latency (ms)")
    p99_tool_latency_ms: float = Field(..., description="P99 tool latency (ms)")


# ---------------------------------------------------------------------------
# /dashboard response — 8 panels
# ---------------------------------------------------------------------------


class HealthDashboardResponse(BaseModel):
    """Response model for the ``GET /dashboard`` endpoint.

    Maps to the 8 dashboard panels:
    1. Agent Status — healthy / degraded / down + uptime
    2. Request Rate — requests per minute
    3. Error Rate — error fraction
    4. Latency — P50, P95, P99
    5. Token Usage — tokens/min + cost estimate
    6. Subagent Activity — spawns/min + avg duration
    7. HITL Status — approval rate + pending count
    8. Memory Usage — items stored
    """

    # Panel 1: Agent Status
    agent_status: str = Field(..., description="Agent status: healthy, degraded, down")
    uptime_seconds: float = Field(..., description="Agent uptime in seconds")

    # Panel 2: Request Rate
    request_rate_per_minute: float = Field(
        ..., description="Requests per minute"
    )

    # Panel 3: Error Rate
    error_rate: float = Field(..., description="Error rate (0.0–1.0)")

    # Panel 4: Latency
    latency_p50_ms: float = Field(..., description="P50 latency (ms)")
    latency_p95_ms: float = Field(..., description="P95 latency (ms)")
    latency_p99_ms: float = Field(..., description="P99 latency (ms)")

    # Panel 5: Token Usage
    token_usage_per_minute: float = Field(..., description="Tokens per minute")
    estimated_cost_usd: float = Field(..., description="Estimated cost in USD")

    # Panel 6: Subagent Activity
    subagent_spawns_per_minute: float = Field(
        ..., description="Subagent spawns per minute"
    )
    subagent_avg_duration_ms: float = Field(
        ..., description="Average subagent duration (ms)"
    )

    # Panel 7: HITL Status
    hitl_approval_rate: float = Field(
        ..., description="HITL approval rate (0.0–1.0)"
    )
    hitl_pending_count: int = Field(
        ..., description="HITL pending approvals"
    )

    # Panel 8: Memory Usage
    memory_items: int = Field(..., description="Memory items stored")


# ---------------------------------------------------------------------------
# Dashboard builder
# ---------------------------------------------------------------------------


def build_dashboard_response(
    metrics: AgentMetrics,
    *,
    uptime_seconds: float = 0.0,
    memory_item_count: int = 0,
) -> HealthDashboardResponse:
    """Build a health dashboard response from an AgentMetrics instance.

    Args:
        metrics: The AgentMetrics collector to read from.
        uptime_seconds: Server uptime in seconds.
        memory_item_count: Number of items in the memory store.

    Returns:
        A populated HealthDashboardResponse ready for JSON serialization.
    """
    return HealthDashboardResponse(
        agent_status="healthy",
        uptime_seconds=round(uptime_seconds, 2),
        request_rate_per_minute=_rate_per_minute(
            metrics.total_tasks, uptime_seconds
        ),
        error_rate=round(metrics.error_rate, 4),
        latency_p50_ms=round(
            AgentMetrics._percentile(metrics.tool_latencies, 50), 2
        ),
        latency_p95_ms=round(
            AgentMetrics._percentile(metrics.tool_latencies, 95), 2
        ),
        latency_p99_ms=round(
            AgentMetrics._percentile(metrics.tool_latencies, 99), 2
        ),
        token_usage_per_minute=_rate_per_minute(
            metrics.token_usage_total, uptime_seconds
        ),
        estimated_cost_usd=round(metrics.token_usage_total * 0.000000435, 6),
        subagent_spawns_per_minute=_rate_per_minute(
            metrics.subagent_spawn_count, uptime_seconds
        ),
        subagent_avg_duration_ms=0.0,  # Requires per-subagent timing
        hitl_approval_rate=round(metrics.hitl_approval_rate, 4),
        hitl_pending_count=0,
        memory_items=memory_item_count,
    )


def _rate_per_minute(count: int, uptime_seconds: float) -> float:
    """Convert a cumulative count to a per-minute rate.

    Returns 0.0 when uptime is zero or negative.
    """
    if uptime_seconds <= 0:
        return 0.0
    return round(count / (uptime_seconds / 60.0), 2)
