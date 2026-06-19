"""Unit tests for alert rules and evaluator."""

from __future__ import annotations

import pytest

from harness_agent.monitoring.alerts import (
    AlertEvaluator,
    AlertRule,
    AlertSeverity,
    default_alert_rules,
)
from harness_agent.monitoring.metrics import AgentMetrics


class TestDefaultAlertRules:
    """Tests for default_alert_rules()."""

    def test_returns_eight_rules(self) -> None:
        rules = default_alert_rules()
        assert len(rules) == 8

    def test_critical_rules_have_runbooks(self) -> None:
        rules = default_alert_rules()
        critical = [r for r in rules if r.severity == AlertSeverity.CRITICAL]
        for rule in critical:
            assert rule.runbook_url != "", (
                f"CRITICAL rule '{rule.name}' missing runbook_url"
            )

    def test_all_rules_have_unique_names(self) -> None:
        rules = default_alert_rules()
        names = [r.name for r in rules]
        assert len(names) == len(set(names))


class TestAlertRule:
    """Tests for AlertRule dataclass."""

    def test_enabled_by_default(self) -> None:
        rule = AlertRule(
            name="test",
            description="test rule",
            severity=AlertSeverity.LOW,
            condition_fn="check_error_rate",
            threshold=0.1,
        )
        assert rule.enabled is True

    def test_disabled_rule_not_evaluated(self) -> None:
        metrics = AgentMetrics()
        # Create very high error rate
        metrics.record_tool_call("x", 100, success=False)

        rule = AlertRule(
            name="disabled_rule",
            description="should not fire",
            severity=AlertSeverity.CRITICAL,
            condition_fn="check_error_rate",
            threshold=0.0,
            enabled=False,
        )
        evaluator = AlertEvaluator(rules=[rule], metrics=metrics)
        alerts = evaluator.evaluate()
        assert len(alerts) == 0


class TestAlertSeverity:
    """Tests for AlertSeverity enum."""

    def test_severity_values_are_strings(self) -> None:
        assert AlertSeverity.CRITICAL.value == "CRITICAL"
        assert AlertSeverity.HIGH.value == "HIGH"
        assert AlertSeverity.MEDIUM.value == "MEDIUM"
        assert AlertSeverity.LOW.value == "LOW"

    @pytest.mark.parametrize("sev", list(AlertSeverity))
    def test_severity_is_string(self, sev: AlertSeverity) -> None:
        assert isinstance(sev.value, str)
        assert sev.value == sev.name


class TestAlertEvaluator:
    """Tests for AlertEvaluator."""

    def test_evaluate_no_alerts_when_healthy(self) -> None:
        metrics = AgentMetrics()
        evaluator = AlertEvaluator(metrics=metrics)
        alerts = evaluator.evaluate()
        assert len(alerts) == 0

    def test_evaluate_fires_on_breached_threshold(self) -> None:
        metrics = AgentMetrics()
        # Create 50% error rate (threshold is 5%)
        metrics.record_tool_call("a", 100, success=True)
        metrics.record_tool_call("b", 100, success=False)
        evaluator = AlertEvaluator(metrics=metrics)
        alerts = evaluator.evaluate()
        assert len(alerts) >= 1
        error_alert = [a for a in alerts if a.rule_name == "high_error_rate"]
        assert len(error_alert) == 1
        assert error_alert[0].severity == AlertSeverity.CRITICAL

    def test_evaluate_no_duplicate_alerts(self) -> None:
        """Already-fired rule should not fire again."""
        metrics = AgentMetrics()
        metrics.record_tool_call("a", 100, success=False)  # 100% error
        evaluator = AlertEvaluator(metrics=metrics)
        first = evaluator.evaluate()
        assert len(first) >= 1
        second = evaluator.evaluate()
        assert len(second) == 0  # No new alerts

    def test_evaluate_resets_when_condition_clears(self) -> None:
        """When condition returns to normal, rule should be un-fired."""
        metrics = AgentMetrics()
        metrics.record_tool_call("a", 100, success=False)  # 100% error
        evaluator = AlertEvaluator(metrics=metrics)
        first = evaluator.evaluate()
        assert len(first) >= 1
        # Now fix the condition
        metrics.reset()
        metrics.record_tool_call("a", 100, success=True)  # 0% error
        # Still no new alerts, and the rule should clear from fired set
        second = evaluator.evaluate()
        assert len(second) == 0
        assert evaluator.get_fired_rules() == []

    def test_evaluate_low_hitl_approval_fires(self) -> None:
        """Low HITL approval (< 50%) should fire. The condition is inverted."""
        metrics = AgentMetrics()
        metrics.record_hitl_decision("write", approved=False)
        metrics.record_hitl_decision("write", approved=False)
        metrics.record_hitl_decision("write", approved=True)
        # Approval rate = 1/3 ≈ 33% < 50% threshold
        evaluator = AlertEvaluator(
            rules=[
                AlertRule(
                    name="low_hitl_approval",
                    description="HITL below 50%",
                    severity=AlertSeverity.MEDIUM,
                    condition_fn="check_hitl_approval_rate",
                    threshold=0.50,
                )
            ],
            metrics=metrics,
        )
        alerts = evaluator.evaluate()
        assert len(alerts) == 1

    def test_health_check_fail_counting(self) -> None:
        evaluator = AlertEvaluator(
            rules=[
                AlertRule(
                    name="health_check_fail",
                    description="3 consecutive fails",
                    severity=AlertSeverity.CRITICAL,
                    condition_fn="check_health_failures",
                    threshold=3.0,
                )
            ],
            metrics=AgentMetrics(),
        )
        evaluator.record_health_fail()
        evaluator.record_health_fail()
        # 2 failures — not enough to trigger
        alerts = evaluator.evaluate()
        assert len(alerts) == 0
        evaluator.record_health_fail()
        # 3 failures — should trigger
        alerts = evaluator.evaluate()
        assert len(alerts) == 1

    def test_health_pass_resets_counter(self) -> None:
        evaluator = AlertEvaluator(
            rules=[
                AlertRule(
                    name="health_check_fail",
                    description="3 consecutive fails",
                    severity=AlertSeverity.CRITICAL,
                    condition_fn="check_health_failures",
                    threshold=3.0,
                )
            ],
            metrics=AgentMetrics(),
        )
        evaluator.record_health_fail()
        evaluator.record_health_fail()
        evaluator.record_health_pass()  # Resets counter
        alerts = evaluator.evaluate()
        assert len(alerts) == 0

    def test_get_fired_rules_returns_sorted(self) -> None:
        metrics = AgentMetrics()
        metrics.record_tool_call("a", 100, success=False)  # 100% error
        evaluator = AlertEvaluator(metrics=metrics)
        evaluator.evaluate()
        fired = evaluator.get_fired_rules()
        assert "high_error_rate" in fired
        assert fired == sorted(fired)

    def test_no_metrics_defaults_to_zero(self) -> None:
        evaluator = AlertEvaluator(metrics=None)
        alerts = evaluator.evaluate()
        assert len(alerts) == 0
