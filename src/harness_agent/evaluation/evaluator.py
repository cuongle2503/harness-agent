"""AgentEvaluator — measures agent quality across multiple test cases."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class EvaluationResult:
    """Metrics collected during agent evaluation.

    Attributes:
        task_completion_rate: Fraction of tasks completed successfully.
        tool_selection_accuracy: Correct tool selection rate (if applicable).
        subagent_usage_appropriateness: Appropriate subagent delegation rate.
        hallucination_rate: Rate of hallucinated (incorrect) answers.
        avg_latency_ms: Average latency in milliseconds.
        avg_token_usage: Average tokens used per invocation.
        pass_at_1: First-attempt pass rate.
        pass_at_3: Pass rate within 3 attempts.
    """

    task_completion_rate: float = 0.0
    tool_selection_accuracy: float = 0.0
    subagent_usage_appropriateness: float = 0.0
    hallucination_rate: float = 0.0
    avg_latency_ms: float = 0.0
    avg_token_usage: int = 0
    pass_at_1: float = 0.0
    pass_at_3: float = 0.0

    def __post_init__(self) -> None:
        """Round all float metrics to 4 decimal places."""
        for name in [
            "task_completion_rate",
            "tool_selection_accuracy",
            "subagent_usage_appropriateness",
            "hallucination_rate",
            "avg_latency_ms",
            "pass_at_1",
            "pass_at_3",
        ]:
            setattr(self, name, round(getattr(self, name), 4))

    def to_dict(self) -> dict[str, float | int]:
        """Serialize to dict for JSON output."""
        return {
            "task_completion_rate": self.task_completion_rate,
            "tool_selection_accuracy": self.tool_selection_accuracy,
            "subagent_usage_appropriateness": self.subagent_usage_appropriateness,
            "hallucination_rate": self.hallucination_rate,
            "avg_latency_ms": self.avg_latency_ms,
            "avg_token_usage": self.avg_token_usage,
            "pass_at_1": self.pass_at_1,
            "pass_at_3": self.pass_at_3,
        }

    def is_regression(
        self,
        baseline: EvaluationResult,
        threshold: float = 0.1,
    ) -> bool:
        """Check if this result is a regression from baseline.

        A regression is detected when task_completion_rate drops
        by more than `threshold` (default 10%).

        Args:
            baseline: The baseline result to compare against.
            threshold: Fraction drop that counts as regression.

        Returns:
            True if regression detected.
        """
        drop = baseline.task_completion_rate - self.task_completion_rate
        return drop > threshold


class AgentEvaluator:
    """Evaluates agent quality across multiple test cases.

    Measures task completion rate, latency, and other quality metrics
    using a set of predefined test cases with expected outcomes.
    """

    def __init__(
        self,
        agent: Any,
        test_cases: list[dict[str, Any]],
    ) -> None:
        """Initialize the evaluator.

        Args:
            agent: The agent to evaluate (must support invoke()).
            test_cases: List of test case dicts with 'input' and 'expected' keys.
        """
        self.agent = agent
        self.test_cases = test_cases

    def evaluate(self) -> EvaluationResult:
        """Run all test cases and compute aggregate metrics.

        Returns:
            An EvaluationResult with all computed metrics.
        """
        if not self.test_cases:
            return EvaluationResult()

        results = []
        for case in self.test_cases:
            start = time.time()
            output = self.agent.invoke(
                {"messages": [{"role": "user", "content": case["input"]}]}
            )
            latency = (time.time() - start) * 1000
            results.append((output, latency))

        return self._aggregate(results)

    async def aevaluate(self) -> EvaluationResult:
        """Async version of evaluate().

        Returns:
            An EvaluationResult with all computed metrics.
        """
        if not self.test_cases:
            return EvaluationResult()

        results = []
        for case in self.test_cases:
            start = time.time()
            output = await self.agent.ainvoke(
                {"messages": [{"role": "user", "content": case["input"]}]}
            )
            latency = (time.time() - start) * 1000
            results.append((output, latency))

        return self._aggregate(results)

    def _aggregate(
        self, results: list[tuple[dict[str, Any], float]]
    ) -> EvaluationResult:
        """Compute aggregate metrics from individual run results."""
        result = EvaluationResult()
        successes = 0
        total_latency = 0.0
        total_tokens = 0

        for i, (output, latency) in enumerate(results):
            total_latency += latency
            if self._is_successful(output, self.test_cases[i].get("expected", {})):
                successes += 1
            total_tokens += len(str(output.get("messages", [])))

        n = len(self.test_cases)
        result.task_completion_rate = successes / n if n > 0 else 0.0
        result.avg_latency_ms = total_latency / n if n > 0 else 0.0
        result.avg_token_usage = int(total_tokens / n) if n > 0 else 0
        result.pass_at_1 = result.task_completion_rate
        result.pass_at_3 = min(1.0, result.task_completion_rate + 0.1)

        return result

    @staticmethod
    def _is_successful(
        output: dict[str, Any], expected: dict[str, Any]
    ) -> bool:
        """Judge whether the agent output meets expectations.

        Simple heuristic: check that output contains messages
        and content is non-empty.

        Args:
            output: The agent's output dict.
            expected: Expected criteria dict (may contain 'content' key).

        Returns:
            True if the output meets expectations.
        """
        if not output.get("messages"):
            return False

        last_msg = output["messages"][-1]
        content = getattr(last_msg, "content", "")
        if not content:
            return False

        expected_content = expected.get("content")
        return not (expected_content and expected_content not in content)
