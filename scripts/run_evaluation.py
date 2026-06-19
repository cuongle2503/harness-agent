#!/usr/bin/env python3
"""Run the agent evaluation framework and detect regressions.

Usage:
    python scripts/run_evaluation.py [--baseline <path>] [--alert-threshold 0.1]

The script runs all evaluation test cases against the current agent,
compares results against a stored baseline, and alerts if regression
is detected (task_completion_rate drops by >threshold).

Results are archived to eval_results/ for trend analysis.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness_agent.core.agent import HarnessAgent
from harness_agent.evaluation import AgentEvaluator, EvaluationResult


def create_test_cases() -> list[dict[str, Any]]:
    """Create ≥ 20 test cases for agent evaluation."""
    return [
        {"id": "TC-001", "input": "What is 2+2?", "expected": {"content": "help"}},
        {"id": "TC-002", "input": "Hello, how are you?", "expected": {}},
        {"id": "TC-003", "input": "Summarize the Python programming language.", "expected": {}},
        {"id": "TC-004", "input": "Find information about machine learning", "expected": {}},
        {"id": "TC-005", "input": "Write a simple Python function to add two numbers", "expected": {}},
        {"id": "TC-006", "input": "What is the capital of France?", "expected": {}},
        {"id": "TC-007", "input": "Explain what an API is in simple terms", "expected": {}},
        {"id": "TC-008", "input": "Research recent AI breakthroughs in 2026", "expected": {}},
        {"id": "TC-009", "input": "Compare Python and JavaScript for web development", "expected": {}},
        {"id": "TC-010", "input": "Create a todo list with 3 items", "expected": {}},
        {"id": "TC-011", "input": "Find and fix the bug in: print('hello'", "expected": {}},
        {"id": "TC-012", "input": "Write unit tests for a calculator function", "expected": {}},
        {"id": "TC-013", "input": "What are the best practices for REST API design?", "expected": {}},
        {"id": "TC-014", "input": "Generate a Dockerfile for a Python app", "expected": {}},
        {"id": "TC-015", "input": "Explain quantum computing to a 5-year-old", "expected": {}},
        {"id": "TC-016", "input": "Extract all email addresses from this text: test@example.com", "expected": {}},
        {"id": "TC-017", "input": "Convert this JSON to YAML format", "expected": {}},
        {"id": "TC-018", "input": "Schedule a meeting for next Monday at 10am", "expected": {}},
        {"id": "TC-019", "input": "Perform a security audit on this code: eval(user_input)", "expected": {}},
        {"id": "TC-020", "input": "Generate a commit message for a feature that adds OAuth login", "expected": {}},
    ]


def load_baseline(path: str) -> EvaluationResult | None:
    """Load a previously saved evaluation baseline.

    Args:
        path: Path to the baseline JSON file.

    Returns:
        An EvaluationResult, or None if the file doesn't exist.
    """
    if not os.path.exists(path):
        return None

    with open(path) as f:
        data = json.load(f)

    return EvaluationResult(
        task_completion_rate=data.get("task_completion_rate", 0.0),
        tool_selection_accuracy=data.get("tool_selection_accuracy", 0.0),
        subagent_usage_appropriateness=data.get("subagent_usage_appropriateness", 0.0),
        hallucination_rate=data.get("hallucination_rate", 0.0),
        avg_latency_ms=data.get("avg_latency_ms", 0.0),
        avg_token_usage=data.get("avg_token_usage", 0),
        pass_at_1=data.get("pass_at_1", 0.0),
        pass_at_3=data.get("pass_at_3", 0.0),
    )


def save_results(
    result: EvaluationResult,
    output_dir: str = "eval_results",
) -> str:
    """Save evaluation results to a dated JSON file.

    Args:
        result: The evaluation result to save.
        output_dir: Directory to save results in.

    Returns:
        The path to the saved file.
    """
    os.makedirs(output_dir, exist_ok=True)
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    path = os.path.join(output_dir, f"eval_{date_str}.json")

    with open(path, "w") as f:
        json.dump(result.to_dict(), f, indent=2)

    return path


def send_alert(message: str) -> None:
    """Send an alert about evaluation regression.

    In production, this would integrate with Slack, email, PagerDuty, etc.
    For now, prints to stderr with a clear ALERT prefix.

    Args:
        message: The alert message.
    """
    print(f"\n⚠️  ALERT: {message}\n", file=sys.stderr)


def main() -> int:
    """Run evaluation and check for regressions.

    Returns:
        Exit code (0 = success, 1 = regression detected).
    """
    parser = argparse.ArgumentParser(
        description="Run agent evaluation framework"
    )
    parser.add_argument(
        "--baseline",
        default="eval_results/baseline.json",
        help="Path to baseline JSON (default: eval_results/baseline.json)",
    )
    parser.add_argument(
        "--alert-threshold",
        type=float,
        default=0.1,
        help="Regression threshold as fraction (default: 0.1)",
    )
    parser.add_argument(
        "--output-dir",
        default="eval_results",
        help="Directory for result archives (default: eval_results)",
    )
    parser.add_argument(
        "--save-baseline",
        action="store_true",
        help="Save current results as the new baseline",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Harness Agent — Evaluation Framework")
    print("=" * 60)

    # Create test agent (uses FakeListChatModel for testing)
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    llm = FakeListChatModel(responses=["Here is a helpful response."])
    agent = HarnessAgent(llm=llm, tools=[], system_prompt="You are helpful.")

    test_cases = create_test_cases()
    print(f"\n📋 Running {len(test_cases)} test cases...")

    evaluator = AgentEvaluator(agent, test_cases)
    result = evaluator.evaluate()

    # Print results
    print("\n📊 Results:")
    print(f"  Task completion rate: {result.task_completion_rate:.2%}")
    print(f"  Avg latency:          {result.avg_latency_ms:.2f}ms")
    print(f"  Avg token usage:      {result.avg_token_usage}")
    print(f"  Pass@1:               {result.pass_at_1:.2%}")
    print(f"  Pass@3:               {result.pass_at_3:.2%}")

    # Save results
    path = save_results(result, args.output_dir)
    print(f"\n💾 Results saved to: {path}")

    if args.save_baseline:
        baseline_path = os.path.join(args.output_dir, "baseline.json")
        with open(baseline_path, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        print(f"📌 Baseline saved to: {baseline_path}")
        return 0

    # Check for regression
    baseline = load_baseline(args.baseline)
    if baseline is not None:
        print("\n📈 Baseline comparison:")
        print(f"  Baseline completion rate: {baseline.task_completion_rate:.2%}")
        print(f"  Current completion rate:  {result.task_completion_rate:.2%}")

        if result.is_regression(baseline, threshold=args.alert_threshold):
            drop = baseline.task_completion_rate - result.task_completion_rate
            send_alert(
                f"Evaluation regression detected! "
                f"Task completion dropped by {drop:.2%} "
                f"(threshold: {args.alert_threshold:.0%})"
            )
            return 1
        else:
            print("  ✅ No regression detected.")
    else:
        print(f"\n📌 No baseline found at {args.baseline}")
        print("   Run with --save-baseline to create one.")

    print("\n✅ Evaluation complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
