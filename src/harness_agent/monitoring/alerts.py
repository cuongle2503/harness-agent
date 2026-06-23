"""Alert rules, severity levels, and evaluation engine.

Phase 7.4 — Defines 8 default alert rules with severity classification
and an AlertEvaluator that checks current metrics against thresholds.

See: docs/guides/plans/07-monitoring.md §7.4
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class AlertSeverity(StrEnum):
    """Alert severity levels matching the Phase 7 plan."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class AlertRule:
    """A single alerting rule definition.

    Attributes:
        name: Short identifier for this rule (e.g. "high_error_rate").
        description: Human-readable description of the trigger condition.
        severity: Alert severity level.
        condition_fn: Name of the evaluation function to call.
        threshold: Numeric threshold that triggers the alert.
        duration_minutes: How long the condition must persist before firing.
        runbook_url: Link to the runbook for this alert.
        enabled: Whether this rule is currently active.
    """

    name: str
    description: str
    severity: AlertSeverity
    condition_fn: str
    threshold: float
    duration_minutes: float = 5.0
    runbook_url: str = ""
    enabled: bool = True


@dataclass
class Alert:
    """A fired alert instance.

    Attributes:
        rule_name: The rule that triggered this alert.
        severity: Severity of the alert.
        current_value: The metric value that breached the threshold.
        threshold: The threshold value that was breached.
        timestamp_iso: ISO-8601 timestamp when the alert fired.
    """

    rule_name: str
    severity: AlertSeverity
    current_value: float
    threshold: float
    timestamp_iso: str


def default_alert_rules() -> list[AlertRule]:
    """Return the default set of 8 alert rules from the Phase 7 plan."""
    return [
        AlertRule(
            name="high_error_rate",
            description="Error rate exceeds 5% for 5 minutes",
            severity=AlertSeverity.CRITICAL,
            condition_fn="check_error_rate",
            threshold=0.05,
            duration_minutes=5.0,
            runbook_url="docs/runbooks/high-error-rate.md",
        ),
        AlertRule(
            name="slow_tool_execution",
            description="Average tool latency exceeds 5000ms",
            severity=AlertSeverity.HIGH,
            condition_fn="check_tool_latency",
            threshold=5000.0,
            duration_minutes=5.0,
            runbook_url="docs/runbooks/slow-tool-execution.md",
        ),
        AlertRule(
            name="excessive_subagents",
            description="More than 20 subagents spawned per task",
            severity=AlertSeverity.MEDIUM,
            condition_fn="check_subagent_count",
            threshold=20.0,
            duration_minutes=1.0,
        ),
        AlertRule(
            name="high_token_usage",
            description="Token usage exceeds 100K per task",
            severity=AlertSeverity.MEDIUM,
            condition_fn="check_token_usage",
            threshold=100_000.0,
            duration_minutes=1.0,
        ),
        AlertRule(
            name="too_many_summarizations",
            description="More than 5 summarization triggers per session",
            severity=AlertSeverity.LOW,
            condition_fn="check_summarization_triggers",
            threshold=5.0,
            duration_minutes=1.0,
        ),
        AlertRule(
            name="low_hitl_approval",
            description="HITL approval rate below 50%",
            severity=AlertSeverity.MEDIUM,
            condition_fn="check_hitl_approval_rate",
            threshold=0.50,
            duration_minutes=10.0,
        ),
        AlertRule(
            name="health_check_fail",
            description="3 consecutive health check failures",
            severity=AlertSeverity.CRITICAL,
            condition_fn="check_health_failures",
            threshold=3.0,
            duration_minutes=1.0,
            runbook_url="docs/runbooks/health-check-fail.md",
        ),
        AlertRule(
            name="high_memory_usage",
            description="Memory usage exceeds 80% of limit",
            severity=AlertSeverity.HIGH,
            condition_fn="check_memory_usage",
            threshold=80.0,
            duration_minutes=5.0,
        ),
    ]


class AlertEvaluator:
    """Evaluates alert rules against current agent metrics.

    Maintains a fired-state set to prevent duplicate alerts and supports
    cooldown periods to avoid alert storms.

    Attributes:
        rules: The alert rules to evaluate.
        metrics: The ``AgentMetrics`` instance to check against.
    """

    def __init__(
        self,
        rules: list[AlertRule] | None = None,
        metrics: Any = None,
    ) -> None:
        self.rules = rules or default_alert_rules()
        self.metrics = metrics  # AgentMetrics reference
        self._fired: set[str] = set()
        self._last_fired: dict[str, float] = {}
        self._consecutive_health_failures: int = 0

    def evaluate(self) -> list[Alert]:
        """Evaluate all enabled rules and return any newly-fired alerts.

        Rules that are already in fired state do not re-fire (prevents
        duplicates). When a previously-breached condition returns to normal
        the rule is removed from the fired set.

        Returns:
            List of newly-fired Alerts (may be empty).
        """
        now = time.monotonic()
        fired: list[Alert] = []

        for rule in self.rules:
            if not rule.enabled:
                continue

            current = self._get_current_value(rule)
            triggered = self._is_triggered(rule, current)

            if triggered and rule.name not in self._fired:
                self._fired.add(rule.name)
                self._last_fired[rule.name] = now
                fired.append(
                    Alert(
                        rule_name=rule.name,
                        severity=rule.severity,
                        current_value=round(current, 4),
                        threshold=rule.threshold,
                        timestamp_iso=time.strftime(
                            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                        ),
                    )
                )
            elif not triggered and rule.name in self._fired:
                self._fired.discard(rule.name)

        return fired

    def _get_current_value(self, rule: AlertRule) -> float:
        """Resolve the current metric value for a given rule."""
        if self.metrics is None:
            # When no metrics, default to healthy state for all rules
            if rule.condition_fn == "check_hitl_approval_rate":
                return 1.0  # No decisions = 100% approval (healthy)
            return 0.0
        m = self.metrics
        fn = rule.condition_fn
        if fn == "check_error_rate":
            return float(m.error_rate)
        elif fn == "check_tool_latency":
            return float(m.tool_call_latency_ms)
        elif fn == "check_subagent_count":
            return float(m.subagent_spawn_count)
        elif fn == "check_token_usage":
            return float(m.token_usage_total)
        elif fn == "check_summarization_triggers":
            return float(m.summarization_triggers_count)
        elif fn == "check_hitl_approval_rate":
            return float(m.hitl_approval_rate)
        elif fn == "check_health_failures":
            return float(self._consecutive_health_failures)
        elif fn == "check_memory_usage":
            return 0.0  # Placeholder — needs psutil
        return 0.0

    def _is_triggered(self, rule: AlertRule, current: float) -> bool:
        """Determine if the current value breaches the rule's threshold.

        Most rules trigger when ``current > threshold``.
        ``check_hitl_approval_rate`` is inverted: triggers when
        ``current < threshold`` (low approval is bad).
        """
        fn = rule.condition_fn
        if fn == "check_hitl_approval_rate":
            return current < rule.threshold
        elif fn == "check_health_failures":
            return current >= rule.threshold
        return current > rule.threshold

    def record_health_pass(self) -> None:
        """Reset consecutive health check failure counter."""
        self._consecutive_health_failures = 0

    def record_health_fail(self) -> None:
        """Increment consecutive health check failure counter."""
        self._consecutive_health_failures += 1

    def get_fired_rules(self) -> list[str]:
        """Return the names of currently-fired alert rules."""
        return sorted(self._fired)
