"""A/B testing framework for comparing two agent versions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ABTestResult:
    """Results of an A/B test between two agent versions.

    Attributes:
        a_better: Number of cases where agent A was judged better.
        b_better: Number of cases where agent B was judged better.
        tie: Number of cases where both were judged equal.
        a_metrics: Optional EvaluationResult for agent A.
        b_metrics: Optional EvaluationResult for agent B.
        cases: Per-case judgments for detailed analysis.
    """

    a_better: int = 0
    b_better: int = 0
    tie: int = 0
    a_metrics: dict[str, Any] | None = None
    b_metrics: dict[str, Any] | None = None
    cases: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Total number of judged cases."""
        return self.a_better + self.b_better + self.tie

    @property
    def a_win_rate(self) -> float:
        """Fraction of cases where A won (excluding ties)."""
        decisive = self.a_better + self.b_better
        return round(self.a_better / decisive, 4) if decisive > 0 else 0.5

    @property
    def is_a_winner(self) -> bool:
        """True if A won more cases than B."""
        return self.a_better > self.b_better

    def is_statistically_significant(
        self, min_cases: int = 10, min_margin: float = 0.1
    ) -> bool:
        """Simple significance check.

        Requires at least `min_cases` and a margin of `min_margin`
        between the win rates.

        Args:
            min_cases: Minimum total cases for significance.
            min_margin: Minimum win rate difference for significance.

        Returns:
            True if results appear statistically meaningful.
        """
        decisive = self.a_better + self.b_better
        if decisive < min_cases:
            return False
        margin = abs(self.a_better - self.b_better) / decisive
        return margin >= min_margin

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON output."""
        return {
            "a_better": self.a_better,
            "b_better": self.b_better,
            "tie": self.tie,
            "total": self.total,
            "a_win_rate": self.a_win_rate,
            "is_a_winner": self.is_a_winner,
            "is_statistically_significant": self.is_statistically_significant(),
            "a_metrics": self.a_metrics,
            "b_metrics": self.b_metrics,
            "cases": self.cases,
        }


class AgentABTester:
    """A/B test between two agent versions.

    Used to compare agent A (current) vs agent B (candidate) across
    a set of test cases. Results are judged by an LLM judge model
    or by simple heuristic comparison.

    Use cases:
        - Comparing system prompt changes
        - Evaluating model upgrades
        - Testing tool additions/removals
        - Assessing middleware pipeline changes
    """

    def __init__(
        self,
        agent_a: Any,
        agent_b: Any,
        judge_model: Any | None = None,
    ) -> None:
        """Initialize the A/B tester.

        Args:
            agent_a: Current agent (control).
            agent_b: Candidate agent (treatment).
            judge_model: Optional LLM to judge which response is better.
                        If None, uses simple length/quality heuristic.
        """
        self.agent_a = agent_a
        self.agent_b = agent_b
        self.judge = judge_model

    async def compare(self, test_cases: list[str]) -> ABTestResult:
        """Compare agent A vs agent B across all test cases.

        Args:
            test_cases: List of user query strings to test.

        Returns:
            ABTestResult with comparison outcomes.
        """
        results = ABTestResult()

        for i, case in enumerate(test_cases):
            try:
                result_a = await self.agent_a.ainvoke(
                    {"messages": [{"role": "user", "content": case}]}
                )
            except Exception as exc:
                results.cases.append({
                    "index": i,
                    "input": case,
                    "judgment": "error_a",
                    "error": str(exc),
                })
                results.b_better += 1
                continue

            try:
                result_b = await self.agent_b.ainvoke(
                    {"messages": [{"role": "user", "content": case}]}
                )
            except Exception as exc:
                results.cases.append({
                    "index": i,
                    "input": case,
                    "judgment": "error_b",
                    "error": str(exc),
                })
                results.a_better += 1
                continue

            judgment = await self._judge(case, result_a, result_b)

            if judgment == "a":
                results.a_better += 1
            elif judgment == "b":
                results.b_better += 1
            else:
                results.tie += 1

            results.cases.append({
                "index": i,
                "input": case,
                "judgment": judgment,
                "a_content": self._extract_content(result_a),
                "b_content": self._extract_content(result_b),
            })

        return results

    async def _judge(
        self,
        query: str,
        result_a: dict[str, Any],
        result_b: dict[str, Any],
    ) -> str:
        """Judge which result is better.

        If a judge model is configured, uses LLM-as-judge.
        Otherwise falls back to a simple length + quality heuristic.

        Args:
            query: The original user query.
            result_a: Agent A's response.
            result_b: Agent B's response.

        Returns:
            "a", "b", or "tie".
        """
        if self.judge is not None:
            return await self._llm_judge(query, result_a, result_b)
        return self._heuristic_judge(result_a, result_b)

    async def _llm_judge(
        self,
        query: str,
        result_a: dict[str, Any],
        result_b: dict[str, Any],
    ) -> str:
        """Use an LLM judge to compare responses."""
        content_a = self._extract_content(result_a)
        content_b = self._extract_content(result_b)

        judge_prompt = (
            "You are an impartial judge evaluating two AI responses. "
            "Compare them for accuracy, helpfulness, clarity, and completeness. "
            'Reply with only "A", "B", or "TIE".\n\n'
            f"User query: {query}\n\n"
            f"--- Response A ---\n{content_a[:2000]}\n\n"
            f"--- Response B ---\n{content_b[:2000]}\n\n"
            "Which response is better? (A/B/TIE):"
        )

        try:
            judge_result = await self.judge.ainvoke(
                {"messages": [{"role": "user", "content": judge_prompt}]}
            )
            answer = self._extract_content(judge_result).strip().upper()

            if "A" in answer and "B" not in answer:
                return "a"
            elif "B" in answer and "A" not in answer:
                return "b"
            elif "TIE" in answer:
                return "tie"
            # Ambiguous — treat as tie
            return "tie"
        except Exception:
            return "tie"

    @staticmethod
    def _heuristic_judge(
        result_a: dict[str, Any],
        result_b: dict[str, Any],
    ) -> str:
        """Simple heuristic: compare response length and structure.

        Longer, more structured responses are preferred, but extreme
        brevity or verbosity is penalized.
        """
        content_a = AgentABTester._extract_content(result_a)
        content_b = AgentABTester._extract_content(result_b)

        len_a = len(content_a)
        len_b = len(content_b)

        # If one is empty and the other isn't
        if not content_a and not content_b:
            return "tie"
        if not content_a:
            return "b"
        if not content_b:
            return "a"

        # Prefer responses in a reasonable range (50-2000 chars)
        a_in_range = 50 <= len_a <= 2000
        b_in_range = 50 <= len_b <= 2000

        if a_in_range and not b_in_range:
            return "a"
        if b_in_range and not a_in_range:
            return "b"

        # If both in range or both out of range, compare by structure
        a_lines = content_a.count("\n") + 1
        b_lines = content_b.count("\n") + 1

        # Slightly prefer structured (multi-line) responses
        if a_lines > 1 and b_lines <= 1:
            return "a"
        if b_lines > 1 and a_lines <= 1:
            return "b"

        return "tie"

    @staticmethod
    def _extract_content(result: dict[str, Any]) -> str:
        """Extract text content from an agent result dict."""
        messages = result.get("messages", [])
        if not messages:
            return ""
        last_msg = messages[-1]
        return str(getattr(last_msg, "content", ""))
