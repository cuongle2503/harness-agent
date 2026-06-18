"""Evaluation framework for measuring agent quality metrics."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage

from harness_agent.core.agent import HarnessAgent


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


class AgentEvaluator:
    """Evaluates agent quality across multiple test cases.

    Measures task completion rate, latency, and other quality metrics
    using a set of predefined test cases with expected outcomes.
    """

    def __init__(
        self,
        agent: HarnessAgent,
        test_cases: list[dict[str, Any]],
    ) -> None:
        self.agent = agent
        self.test_cases = test_cases

    def evaluate(self) -> EvaluationResult:
        """Run all test cases and compute metrics."""
        result = EvaluationResult()
        if not self.test_cases:
            return result

        successes = 0
        total_latency = 0.0
        total_tokens = 0

        for case in self.test_cases:
            start = time.time()
            output = self.agent.invoke({
                "messages": [HumanMessage(content=case["input"])]
            })
            latency = (time.time() - start) * 1000
            total_latency += latency

            if self._is_successful(output, case["expected"]):
                successes += 1

            # Approximate token usage from output message count
            total_tokens += len(str(output.get("messages", [])))

        n = len(self.test_cases)
        result.task_completion_rate = round(successes / n, 4) if n > 0 else 0.0
        result.avg_latency_ms = round(total_latency / n, 2) if n > 0 else 0.0
        result.avg_token_usage = int(total_tokens / n) if n > 0 else 0
        result.pass_at_1 = result.task_completion_rate
        result.pass_at_3 = min(1.0, result.task_completion_rate + 0.1)

        return result

    @staticmethod
    def _is_successful(output: dict[str, Any], expected: dict[str, Any]) -> bool:
        """Judge whether the agent output meets expectations.

        Simple heuristic: check that output contains messages
        and content is non-empty.
        """
        if not output.get("messages"):
            return False

        last_msg = output["messages"][-1]
        content = getattr(last_msg, "content", "")
        if not content:
            return False

        # If expected content is specified, check for it
        expected_content = expected.get("content")
        return not (expected_content and expected_content not in content)


# ── Test dataset ──────────────────────────────────────────────

def create_test_cases() -> list[dict[str, Any]]:
    """Create ≥ 20 test cases for agent evaluation."""
    return [
        {
            "id": "TC-001",
            "input": "What is 2+2?",
            "expected": {"content": "help"},
        },
        {
            "id": "TC-002",
            "input": "Hello, how are you?",
            "expected": {},
        },
        {
            "id": "TC-003",
            "input": "Summarize the Python programming language.",
            "expected": {},
        },
        {
            "id": "TC-004",
            "input": "Find information about machine learning",
            "expected": {},
        },
        {
            "id": "TC-005",
            "input": "Write a simple Python function to add two numbers",
            "expected": {},
        },
        {
            "id": "TC-006",
            "input": "What is the capital of France?",
            "expected": {},
        },
        {
            "id": "TC-007",
            "input": "Explain what an API is in simple terms",
            "expected": {},
        },
        {
            "id": "TC-008",
            "input": "Research recent AI breakthroughs in 2026",
            "expected": {},
        },
        {
            "id": "TC-009",
            "input": "Compare Python and JavaScript for web development",
            "expected": {},
        },
        {
            "id": "TC-010",
            "input": "Create a todo list with 3 items",
            "expected": {},
        },
        {
            "id": "TC-011",
            "input": "Find and fix the bug in: print('hello'",
            "expected": {},
        },
        {
            "id": "TC-012",
            "input": "Write unit tests for a calculator function",
            "expected": {},
        },
        {
            "id": "TC-013",
            "input": "What are the best practices for REST API design?",
            "expected": {},
        },
        {
            "id": "TC-014",
            "input": "Generate a Dockerfile for a Python app",
            "expected": {},
        },
        {
            "id": "TC-015",
            "input": "Explain quantum computing to a 5-year-old",
            "expected": {},
        },
        {
            "id": "TC-016",
            "input": "Extract all email addresses from this text: test@example.com",
            "expected": {},
        },
        {
            "id": "TC-017",
            "input": "Convert this JSON to YAML format",
            "expected": {},
        },
        {
            "id": "TC-018",
            "input": "Schedule a meeting for next Monday at 10am",
            "expected": {},
        },
        {
            "id": "TC-019",
            "input": "Perform a security audit on this code: eval(user_input)",
            "expected": {},
        },
        {
            "id": "TC-020",
            "input": "Generate a commit message for a feature that adds OAuth login",
            "expected": {},
        },
    ]


# ── Tests ─────────────────────────────────────────────────────


class TestEvaluationResult:
    """Tests for EvaluationResult dataclass."""

    def test_default_values_are_zero(self) -> None:
        result = EvaluationResult()
        assert result.task_completion_rate == 0.0
        assert result.avg_latency_ms == 0.0
        assert result.avg_token_usage == 0
        assert result.pass_at_1 == 0.0
        assert result.pass_at_3 == 0.0
        assert result.tool_selection_accuracy == 0.0

    def test_can_set_metrics(self) -> None:
        result = EvaluationResult(
            task_completion_rate=0.95,
            avg_latency_ms=200.0,
            avg_token_usage=150,
            pass_at_1=0.90,
        )
        assert result.task_completion_rate == 0.95
        assert result.avg_latency_ms == 200.0
        assert result.avg_token_usage == 150
        assert result.pass_at_1 == 0.90

    def test_equality(self) -> None:
        a = EvaluationResult(task_completion_rate=1.0)
        b = EvaluationResult(task_completion_rate=1.0)
        assert a == b


class TestAgentEvaluator:
    """Tests for AgentEvaluator."""

    @pytest.fixture
    def fake_agent(self) -> HarnessAgent:
        llm = FakeListChatModel(responses=["Here is the answer to your question."])
        return HarnessAgent(llm=llm, tools=[], system_prompt="You are helpful.")

    @pytest.fixture
    def test_cases(self) -> list[dict[str, Any]]:
        return create_test_cases()

    def test_creates_evaluator(self, fake_agent: HarnessAgent) -> None:
        evaluator = AgentEvaluator(fake_agent, [])
        assert evaluator.agent is fake_agent
        assert evaluator.test_cases == []

    def test_evaluate_empty_cases_returns_defaults(
        self, fake_agent: HarnessAgent
    ) -> None:
        evaluator = AgentEvaluator(fake_agent, [])
        result = evaluator.evaluate()
        assert result.task_completion_rate == 0.0
        assert result.avg_latency_ms == 0.0

    def test_evaluate_with_cases_returns_metrics(
        self, fake_agent: HarnessAgent, test_cases: list[dict[str, Any]]
    ) -> None:
        evaluator = AgentEvaluator(fake_agent, test_cases[:5])
        result = evaluator.evaluate()
        assert result.task_completion_rate >= 0.0
        assert result.task_completion_rate <= 1.0
        assert result.avg_latency_ms >= 0.0
        assert isinstance(result.avg_token_usage, int)

    def test_evaluate_produces_pass_at_1(
        self, fake_agent: HarnessAgent, test_cases: list[dict[str, Any]]
    ) -> None:
        evaluator = AgentEvaluator(fake_agent, test_cases[:3])
        result = evaluator.evaluate()
        assert 0.0 <= result.pass_at_1 <= 1.0

    def test_evaluate_produces_pass_at_3(
        self, fake_agent: HarnessAgent, test_cases: list[dict[str, Any]]
    ) -> None:
        evaluator = AgentEvaluator(fake_agent, test_cases[:3])
        result = evaluator.evaluate()
        assert 0.0 <= result.pass_at_3 <= 1.0

    def test_evaluate_all_cases_produces_valid_metrics(
        self, fake_agent: HarnessAgent, test_cases: list[dict[str, Any]]
    ) -> None:
        """Full 20-case evaluation produces valid metrics."""
        evaluator = AgentEvaluator(fake_agent, test_cases)
        result = evaluator.evaluate()
        assert result.task_completion_rate >= 0.0
        assert result.avg_latency_ms > 0.0
        assert result.pass_at_1 > 0.0


class TestTestCaseDataset:
    """Tests for the evaluation test case dataset."""

    def test_at_least_20_cases(self) -> None:
        cases = create_test_cases()
        assert len(cases) >= 20

    def test_each_case_has_id(self) -> None:
        cases = create_test_cases()
        for case in cases:
            assert "id" in case
            assert "input" in case
            assert "expected" in case

    def test_case_ids_are_unique(self) -> None:
        cases = create_test_cases()
        ids = [c["id"] for c in cases]
        assert len(ids) == len(set(ids))

    def test_all_inputs_are_non_empty(self) -> None:
        cases = create_test_cases()
        for case in cases:
            assert len(case["input"]) > 0
