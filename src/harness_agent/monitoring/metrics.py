"""AgentMetrics — collect and expose observability metrics.

Phase 7.3 — Tracks all 9 key metrics plus operational counters.
See: docs/guides/plans/07-monitoring.md §7.3
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentMetrics:
    """Collect and expose agent observability metrics.

    Tracks 13 raw counters and exposes 9 computed key metrics.
    Uses a rolling window for latency data to bound memory usage.

    Key metrics (computed properties):
    1. tool_call_latency_ms    — Avg tool execution time
    2. llm_call_latency_ms     — Avg LLM response time
    3. subagent_spawn_count    — Total subagents spawned
    4. token_usage_total       — Cumulative token consumption
    5. summarization_triggers  — Total context summarizations
    6. error_rate              — Fraction of calls that errored
    7. hitl_approval_rate      — Fraction of HITL decisions approved
    8. task_completion_rate    — Fraction of tasks completed
    9. avg_response_time_ms    — Avg end-to-end task duration

    Attributes:
        tool_calls: Successful tool invocations.
        tool_errors: Failed tool invocations.
        model_calls: Successful LLM calls.
        model_errors: Failed LLM calls.
        subagent_spawns: Total subagents spawned.
        subagent_completes: Subagents that completed successfully.
        summarization_triggers: Context summarization triggers.
        hitl_approvals: HITL approvals granted.
        hitl_rejections: HITL approvals denied.
        total_tokens: Cumulative tokens used.
        total_tasks: Tasks received.
        completed_tasks: Tasks completed successfully.
        total_latency_ms: Cumulative task latency sum.
        tool_latencies: Rolling window of tool call latencies (ms).
        model_latencies: Rolling window of LLM call latencies (ms).
    """

    # Raw counters
    tool_calls: int = 0
    tool_errors: int = 0
    model_calls: int = 0
    model_errors: int = 0
    subagent_spawns: int = 0
    subagent_completes: int = 0
    summarization_triggers: int = 0
    hitl_approvals: int = 0
    hitl_rejections: int = 0
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tasks: int = 0
    completed_tasks: int = 0

    # Latency accumulators
    total_latency_ms: float = 0.0
    tool_latencies: deque[float] = field(default_factory=lambda: deque(maxlen=100))
    model_latencies: deque[float] = field(default_factory=lambda: deque(maxlen=100))
    latency_window: int = field(default=100, repr=False)

    def __post_init__(self) -> None:
        """Re-create deques if a custom latency_window was provided."""
        if self.latency_window != 100:
            self.tool_latencies = deque(self.tool_latencies, maxlen=self.latency_window)
            self.model_latencies = deque(self.model_latencies, maxlen=self.latency_window)

    # ------------------------------------------------------------------
    # Computed properties — the 9 key metrics
    # ------------------------------------------------------------------

    @property
    def tool_call_latency_ms(self) -> float:
        """Key metric #1: Average tool call latency in milliseconds."""
        if not self.tool_latencies:
            return 0.0
        return sum(self.tool_latencies) / len(self.tool_latencies)

    @property
    def llm_call_latency_ms(self) -> float:
        """Key metric #2: Average LLM call latency in milliseconds."""
        if not self.model_latencies:
            return 0.0
        return sum(self.model_latencies) / len(self.model_latencies)

    @property
    def subagent_spawn_count(self) -> int:
        """Key metric #3: Total subagents spawned."""
        return self.subagent_spawns

    @property
    def token_usage_total(self) -> int:
        """Key metric #4: Cumulative token usage."""
        return self.total_tokens

    @property
    def summarization_triggers_count(self) -> int:
        """Key metric #5: Total summarization triggers."""
        return self.summarization_triggers

    @property
    def error_rate(self) -> float:
        """Key metric #6: Error rate as a fraction (0.0–1.0).

        Denominator includes both successes and errors for an accurate
        error ratio.
        """
        total = (
            self.tool_calls
            + self.tool_errors
            + self.model_calls
            + self.model_errors
        )
        errors = self.tool_errors + self.model_errors
        return errors / total if total > 0 else 0.0

    @property
    def hitl_approval_rate(self) -> float:
        """Key metric #7: HITL approval rate as a fraction (0.0–1.0).

        Defaults to 1.0 when no decisions have been made (optimistic).
        """
        total = self.hitl_approvals + self.hitl_rejections
        return self.hitl_approvals / total if total > 0 else 1.0

    @property
    def task_completion_rate(self) -> float:
        """Key metric #8: Task completion rate as a fraction (0.0–1.0).

        Defaults to 1.0 when no tasks have been received.
        """
        return (
            self.completed_tasks / self.total_tasks
            if self.total_tasks > 0
            else 1.0
        )

    @property
    def avg_response_time_ms(self) -> float:
        """Key metric #9: Average end-to-end response time in milliseconds."""
        return (
            self.total_latency_ms / self.completed_tasks
            if self.completed_tasks > 0
            else 0.0
        )

    # ------------------------------------------------------------------
    # Mutation methods
    # ------------------------------------------------------------------

    def record_tool_call(
        self, tool_name: str, latency_ms: float, *, success: bool = True
    ) -> None:
        """Record a tool call event with latency.

        Args:
            tool_name: Name of the tool that was invoked.
            latency_ms: Execution time in milliseconds.
            success: Whether the call succeeded.
        """
        if success:
            self.tool_calls += 1
        else:
            self.tool_errors += 1
        self._append_latency(self.tool_latencies, latency_ms)

    def record_model_call(
        self,
        latency_ms: float,
        *,
        success: bool = True,
        tokens: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Record an LLM call event with latency and token count.

        Args:
            latency_ms: Response time in milliseconds.
            success: Whether the call succeeded.
            tokens: Token count for this call (backward compat; prefer
                ``input_tokens`` + ``output_tokens``).
            input_tokens: Input/prompt tokens consumed by this call.
            output_tokens: Output/completion tokens generated by this call.
        """
        if success:
            self.model_calls += 1
        else:
            self.model_errors += 1
        # Use input+output when provided, otherwise fall back to `tokens`
        total = input_tokens + output_tokens
        if total > 0:
            self.total_tokens += total
            self.input_tokens += input_tokens
            self.output_tokens += output_tokens
        elif tokens > 0:
            self.total_tokens += tokens
        self._append_latency(self.model_latencies, latency_ms)

    def record_subagent_spawn(self, subagent_name: str) -> None:
        """Record a subagent spawn event.

        Args:
            subagent_name: Name of the spawned subagent.
        """
        self.subagent_spawns += 1

    def record_subagent_complete(self, subagent_name: str) -> None:
        """Record a subagent completion event.

        Args:
            subagent_name: Name of the completed subagent.
        """
        self.subagent_completes += 1

    def record_summarization(
        self, tokens_before: int, tokens_after: int
    ) -> None:
        """Record a context summarization event.

        Args:
            tokens_before: Token count before summarization.
            tokens_after: Token count after summarization.
        """
        self.summarization_triggers += 1

    def record_hitl_decision(
        self, tool_name: str, *, approved: bool
    ) -> None:
        """Record a human-in-the-loop approval decision.

        Args:
            tool_name: Name of the tool being approved/rejected.
            approved: Whether the action was approved.
        """
        if approved:
            self.hitl_approvals += 1
        else:
            self.hitl_rejections += 1

    def record_task_start(self) -> None:
        """Record a new task being received by the agent."""
        self.total_tasks += 1

    def record_task_complete(self, latency_ms: float) -> None:
        """Record a task completing successfully.

        Args:
            latency_ms: End-to-end task duration in milliseconds.
        """
        self.completed_tasks += 1
        self.total_latency_ms += latency_ms

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Export all metrics as a JSON-serializable dictionary."""
        return {
            "tool_calls": self.tool_calls,
            "tool_errors": self.tool_errors,
            "model_calls": self.model_calls,
            "model_errors": self.model_errors,
            "tool_call_latency_ms": round(self.tool_call_latency_ms, 2),
            "llm_call_latency_ms": round(self.llm_call_latency_ms, 2),
            "subagent_spawn_count": self.subagent_spawn_count,
            "subagent_completes": self.subagent_completes,
            "token_usage_total": self.token_usage_total,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "summarization_triggers": self.summarization_triggers_count,
            "error_rate": round(self.error_rate, 4),
            "hitl_approval_rate": round(self.hitl_approval_rate, 4),
            "hitl_approvals": self.hitl_approvals,
            "hitl_rejections": self.hitl_rejections,
            "task_completion_rate": round(self.task_completion_rate, 4),
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "avg_response_time_ms": round(self.avg_response_time_ms, 2),
            "p50_tool_latency_ms": round(
                self._percentile(self.tool_latencies, 50), 2
            ),
            "p95_tool_latency_ms": round(
                self._percentile(self.tool_latencies, 95), 2
            ),
            "p99_tool_latency_ms": round(
                self._percentile(self.tool_latencies, 99), 2
            ),
        }

    def reset(self) -> None:
        """Reset all counters and clear latency windows."""
        self.tool_calls = 0
        self.tool_errors = 0
        self.model_calls = 0
        self.model_errors = 0
        self.subagent_spawns = 0
        self.subagent_completes = 0
        self.summarization_triggers = 0
        self.hitl_approvals = 0
        self.hitl_rejections = 0
        self.total_tokens = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tasks = 0
        self.completed_tasks = 0
        self.total_latency_ms = 0.0
        self.tool_latencies.clear()
        self.model_latencies.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _append_latency(self, target: deque[float], value: float) -> None:
        """Append a latency value (deque handles maxlen cap automatically)."""
        target.append(value)

    @staticmethod
    def _percentile(data: Sequence[float], percentile: float) -> float:
        """Compute a percentile from a list of values.

        Uses linear interpolation between the two closest ranks.
        Returns 0.0 for empty data.

        Args:
            data: Sorted list of numeric values.
            percentile: Percentile to compute (0–100).

        Returns:
            The percentile value.
        """
        if not data:
            return 0.0
        sorted_data = sorted(data)
        k = (len(sorted_data) - 1) * (percentile / 100.0)
        f = int(k)
        c = k - f
        if f + 1 < len(sorted_data):
            return sorted_data[f] * (1 - c) + sorted_data[f + 1] * c
        return sorted_data[f]
