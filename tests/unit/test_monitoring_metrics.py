"""Unit tests for AgentMetrics dataclass."""

from __future__ import annotations

import json

import pytest

from harness_agent.monitoring.metrics import AgentMetrics


class TestAgentMetricsDefaults:
    """Tests for default state of AgentMetrics."""

    def test_all_counters_start_at_zero(self) -> None:
        m = AgentMetrics()
        assert m.tool_calls == 0
        assert m.tool_errors == 0
        assert m.model_calls == 0
        assert m.model_errors == 0
        assert m.subagent_spawns == 0
        assert m.subagent_completes == 0
        assert m.total_tokens == 0
        assert m.total_tasks == 0
        assert m.completed_tasks == 0

    def test_latency_lists_start_empty(self) -> None:
        m = AgentMetrics()
        assert m.tool_latencies == []
        assert m.model_latencies == []

    def test_total_latency_ms_starts_at_zero(self) -> None:
        m = AgentMetrics()
        assert m.total_latency_ms == 0.0


class TestAgentMetricsRecording:
    """Tests for mutation/recording methods."""

    def test_record_tool_call_success_increments_counter(self) -> None:
        m = AgentMetrics()
        m.record_tool_call("search", 150.0, success=True)
        assert m.tool_calls == 1
        assert m.tool_errors == 0

    def test_record_tool_call_failure_increments_error_counter(self) -> None:
        m = AgentMetrics()
        m.record_tool_call("search", 150.0, success=False)
        assert m.tool_calls == 0
        assert m.tool_errors == 1

    def test_record_tool_call_adds_to_latency_list(self) -> None:
        m = AgentMetrics()
        m.record_tool_call("search", 150.0, success=True)
        assert m.tool_latencies == [150.0]

    def test_record_model_call_tracks_tokens(self) -> None:
        m = AgentMetrics()
        m.record_model_call(500.0, success=True, tokens=42)
        assert m.model_calls == 1
        assert m.total_tokens == 42

    def test_record_model_call_failure(self) -> None:
        m = AgentMetrics()
        m.record_model_call(500.0, success=False)
        assert m.model_calls == 0
        assert m.model_errors == 1

    def test_record_subagent_spawn_tracks_count(self) -> None:
        m = AgentMetrics()
        m.record_subagent_spawn("researcher")
        m.record_subagent_spawn("coder")
        assert m.subagent_spawns == 2

    def test_record_subagent_complete(self) -> None:
        m = AgentMetrics()
        m.record_subagent_complete("researcher")
        assert m.subagent_completes == 1

    def test_record_summarization_increments_counter(self) -> None:
        m = AgentMetrics()
        m.record_summarization(10000, 2000)
        assert m.summarization_triggers == 1

    def test_record_hitl_decision_approved(self) -> None:
        m = AgentMetrics()
        m.record_hitl_decision("write_file", approved=True)
        assert m.hitl_approvals == 1
        assert m.hitl_rejections == 0

    def test_record_hitl_decision_rejected(self) -> None:
        m = AgentMetrics()
        m.record_hitl_decision("write_file", approved=False)
        assert m.hitl_approvals == 0
        assert m.hitl_rejections == 1

    def test_record_task_start(self) -> None:
        m = AgentMetrics()
        m.record_task_start()
        assert m.total_tasks == 1

    def test_record_task_complete(self) -> None:
        m = AgentMetrics()
        m.record_task_complete(1500.0)
        assert m.completed_tasks == 1
        assert m.total_latency_ms == 1500.0


class TestAgentMetricsComputedProperties:
    """Tests for the 9 computed key metrics."""

    def test_tool_call_latency_ms_averages_correctly(self) -> None:
        m = AgentMetrics()
        m.record_tool_call("a", 100.0, success=True)
        m.record_tool_call("b", 200.0, success=True)
        assert m.tool_call_latency_ms == 150.0

    def test_tool_call_latency_ms_empty_returns_zero(self) -> None:
        m = AgentMetrics()
        assert m.tool_call_latency_ms == 0.0

    def test_llm_call_latency_ms_handles_empty_list(self) -> None:
        m = AgentMetrics()
        assert m.llm_call_latency_ms == 0.0

    def test_llm_call_latency_ms_calculates(self) -> None:
        m = AgentMetrics()
        m.record_model_call(300.0, success=True)
        m.record_model_call(500.0, success=True)
        assert m.llm_call_latency_ms == 400.0

    def test_error_rate_zero_when_no_calls(self) -> None:
        m = AgentMetrics()
        assert m.error_rate == 0.0

    def test_error_rate_calculates_correctly(self) -> None:
        m = AgentMetrics()
        m.record_tool_call("a", 100.0, success=True)
        m.record_tool_call("b", 200.0, success=True)
        m.record_tool_call("c", 300.0, success=False)
        # 1 error out of 3 total calls = 1/3
        assert m.error_rate == pytest.approx(1.0 / 3.0)

    def test_hitl_approval_rate_defaults_to_1(self) -> None:
        """When no decisions made, approval rate should be 1.0 (optimistic)."""
        m = AgentMetrics()
        assert m.hitl_approval_rate == 1.0

    def test_hitl_approval_rate_calculates(self) -> None:
        m = AgentMetrics()
        m.record_hitl_decision("write", approved=True)
        m.record_hitl_decision("exec", approved=False)
        assert m.hitl_approval_rate == 0.5

    def test_task_completion_rate_defaults_to_1(self) -> None:
        m = AgentMetrics()
        assert m.task_completion_rate == 1.0

    def test_task_completion_rate_calculates(self) -> None:
        m = AgentMetrics()
        m.record_task_start()
        m.record_task_start()
        m.record_task_complete(1000.0)
        assert m.task_completion_rate == 0.5

    def test_avg_response_time_ms_with_no_tasks(self) -> None:
        m = AgentMetrics()
        assert m.avg_response_time_ms == 0.0

    def test_avg_response_time_ms_calculates(self) -> None:
        m = AgentMetrics()
        m.record_task_complete(1000.0)
        m.record_task_complete(3000.0)
        assert m.avg_response_time_ms == 2000.0

    def test_subagent_spawn_count_matches(self) -> None:
        m = AgentMetrics()
        m.record_subagent_spawn("a")
        m.record_subagent_spawn("b")
        assert m.subagent_spawn_count == 2


class TestAgentMetricsDict:
    """Tests for to_dict() serialization."""

    def test_to_dict_returns_all_required_keys(self) -> None:
        m = AgentMetrics()
        d = m.to_dict()
        required = [
            "tool_calls", "tool_errors", "model_calls", "model_errors",
            "tool_call_latency_ms", "llm_call_latency_ms",
            "subagent_spawn_count", "token_usage_total",
            "summarization_triggers", "error_rate", "hitl_approval_rate",
            "task_completion_rate", "total_tasks", "completed_tasks",
            "avg_response_time_ms", "p50_tool_latency_ms",
            "p95_tool_latency_ms", "p99_tool_latency_ms",
        ]
        for key in required:
            assert key in d, f"Missing key: {key}"

    def test_to_dict_serializable_to_json(self) -> None:
        m = AgentMetrics()
        m.record_tool_call("search", 150.0, success=True)
        d = m.to_dict()
        json_str = json.dumps(d)
        assert json_str
        parsed = json.loads(json_str)
        assert parsed["tool_calls"] == 1


class TestAgentMetricsReset:
    """Tests for reset()."""

    def test_reset_zeros_all_counters(self) -> None:
        m = AgentMetrics()
        m.record_tool_call("a", 100.0, success=True)
        m.record_model_call(200.0, success=True, tokens=10)
        m.record_subagent_spawn("x")
        m.record_task_complete(500.0)
        m.reset()
        assert m.tool_calls == 0
        assert m.model_calls == 0
        assert m.total_tokens == 0
        assert m.subagent_spawns == 0
        assert m.completed_tasks == 0

    def test_reset_clears_latency_lists(self) -> None:
        m = AgentMetrics()
        m.record_tool_call("a", 100.0, success=True)
        m.reset()
        assert m.tool_latencies == []
        assert m.model_latencies == []

    def test_reset_zeros_latency_total(self) -> None:
        m = AgentMetrics()
        m.record_task_complete(500.0)
        m.reset()
        assert m.total_latency_ms == 0.0


class TestAgentMetricsPercentile:
    """Tests for _percentile()."""

    def test_percentile_empty_returns_zero(self) -> None:
        assert AgentMetrics._percentile([], 50) == 0.0

    def test_percentile_single_value(self) -> None:
        assert AgentMetrics._percentile([5.0], 50) == 5.0
        assert AgentMetrics._percentile([5.0], 95) == 5.0

    @pytest.mark.parametrize("p,expected", [
        (50, 5.5),
        (95, 9.55),
        (99, 9.91),
    ])
    def test_percentile_distribution(self, p: float, expected: float) -> None:
        data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        result = AgentMetrics._percentile(data, p)
        assert result == pytest.approx(expected)


class TestAgentMetricsLatencyWindow:
    """Tests for the rolling latency window."""

    def test_latency_window_respected(self) -> None:
        m = AgentMetrics(_max_latency_window=3)
        m.record_tool_call("a", 1.0, success=True)
        m.record_tool_call("b", 2.0, success=True)
        m.record_tool_call("c", 3.0, success=True)
        m.record_tool_call("d", 4.0, success=True)
        # Only last 3 values retained
        assert m.tool_latencies == [2.0, 3.0, 4.0]

    def test_model_latency_window_respected(self) -> None:
        m = AgentMetrics(_max_latency_window=2)
        m.record_model_call(1.0, success=True)
        m.record_model_call(2.0, success=True)
        m.record_model_call(3.0, success=True)
        assert m.model_latencies == [2.0, 3.0]
