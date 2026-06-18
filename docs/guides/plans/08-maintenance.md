# Phase 8: Maintenance & Iteration Plan

> **Mục tiêu**: Thiết lập quy trình cải tiến liên tục: memory feedback loop, regression tests, A/B testing, versioning, và monthly review.

## Prerequisites

- [ ] Phase 7: Monitoring hoàn thành
- [ ] Agent đang chạy trong production
- [ ] Monitoring & alerting hoạt động
- [ ] Đã đọc [AIDLC Lifecycle §8](../aidlc-lifecycle.md#8-maintenance--iteration)

---

## Step-by-Step Workflow

### Step 8.1: Memory-Driven Improvement Loop

**Mục tiêu**: Agent tự học và cải thiện qua memory feedback.

**Cách thực hiện**: Dựa trên [AIDLC Lifecycle §8.1](../aidlc-lifecycle.md#81-memory-driven-improvement)

```python
agent = create_deep_agent(
    model=model,
    memory=[
        "/memories/preferences.md",
        "/memories/feedback.md",
        "/memories/learnings.md",
    ],
    backend=CompositeBackend(
        default=StateBackend(),
        routes={
            "/memories/": StoreBackend(
                namespace=lambda rt: [rt.server_info.user.identity],
            ),
        },
    ),
    system_prompt="""When you receive feedback:
    1. Acknowledge the feedback
    2. Update /memories/feedback.md with:
       - What went wrong
       - Why it went wrong
       - How to avoid it next time
    3. Apply the corrected behavior immediately""",
)
```

**Memory File Structure**:

```
/memories/
├── preferences.md     # User preferences (language, style, tools)
├── feedback.md        # Correction history with WHY
├── learnings.md       # Patterns discovered over time
└── context.md         # Project-specific context updates
```

**Feedback Integration Workflow**:

```
User Feedback → Phân tích → Cập nhật → Test → Deploy
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
              Memory Update  Prompt Fix   Tool Adjust
              (/memories/)   (system)     (tools/schema)
```

**Checklist**:
- [ ] Memory feedback loop active
- [ ] `/memories/feedback.md` configured
- [ ] Agent updates memory on user correction
- [ ] Feedback captured with WHY (not just what)
- [ ] Memory verified across sessions
- [ ] Stale memory cleanup process defined

---

### Step 8.2: Regression Test Suite Maintenance

**Mục tiêu**: Mọi bug fix đều có regression test.

**Cách thực hiện**: Dựa trên [AIDLC Lifecycle §8.2](../aidlc-lifecycle.md#82-continuous-evaluation)

```python
# tests/regression/test_regression.py
REGRESSION_CASES = [
    {
        "id": "BUG-001",
        "date": "2026-06-18",
        "input": "Research X and Y in parallel",
        "expected_behavior": "spawns_two_subagents",
        "fix_commit": "abc123",
    },
    {
        "id": "BUG-002",
        "date": "2026-06-20",
        "input": "",
        "expected_behavior": "handles_empty_input_gracefully",
        "fix_commit": "def456",
    },
    # Thêm bug mới vào đây
]

@pytest.mark.parametrize("case", REGRESSION_CASES)
@pytest.mark.regression
async def test_regression(case):
    """Verify bug cũ không tái xuất hiện."""
    agent = create_research_agent(model, search_tool, fetch_tool)
    result = await agent.ainvoke({
        "messages": [{"role": "user", "content": case["input"]}]
    })
    # Verify expected behavior based on case
    assert len(result["messages"][-1].content) > 0
```

**Bug Fix Workflow**:
1. Phát hiện bug (user report / monitoring alert)
2. Viết regression test (RED)
3. Fix bug (GREEN)
4. Add to REGRESSION_CASES
5. Commit: `fix: [BUG-XXX] description`

**Tools hỗ trợ**:
- **Skill `tdd-workflow`**: RED → GREEN → REFACTOR cho bug fix
- **Skill `test`**: Viết regression test
- **Agent `python-reviewer`**: Review fix

**Checklist**:
- [ ] Regression test suite exists and runs in CI
- [ ] Every bug fix has corresponding regression test
- [ ] Regression tests parametrized with BUG-ID
- [ ] Regression suite run monthly at minimum
- [ ] New bugs added to suite within same sprint

---

### Step 8.3: A/B Testing Framework

**Mục tiêu**: A/B test agent changes trước khi promote.

**Cách thực hiện**: Dựa trên [AIDLC Lifecycle §8.3](../aidlc-lifecycle.md#83-ab-testing-agent-changes)

```python
from dataclasses import dataclass
import random

@dataclass
class ABTestResult:
    a_better: int = 0
    b_better: int = 0
    tie: int = 0
    a_metrics: dict | None = None
    b_metrics: dict | None = None

class AgentABTester:
    """A/B test giữa hai version agent."""

    def __init__(self, agent_a, agent_b, judge_model):
        self.agent_a = agent_a
        self.agent_b = agent_b
        self.judge = judge_model

    async def compare(self, test_cases: list[str]) -> ABTestResult:
        results = ABTestResult()
        for case in test_cases:
            result_a = await self.agent_a.ainvoke({
                "messages": [{"role": "user", "content": case}]
            })
            result_b = await self.agent_b.ainvoke({
                "messages": [{"role": "user", "content": case}]
            })

            # Judge: which is better?
            judgment = await self._judge(case, result_a, result_b)
            if judgment == "a":
                results.a_better += 1
            elif judgment == "b":
                results.b_better += 1
            else:
                results.tie += 1
        return results

    async def _judge(self, query: str, result_a: dict, result_b: dict) -> str:
        """Use LLM judge to compare responses."""
        ...
```

**Khi nào A/B test**:
- Thay đổi system prompt
- Thay đổi model
- Thêm/bớt tools
- Thay đổi middleware pipeline order
- Thay đổi summarization thresholds

**Checklist**:
- [ ] A/B testing framework implemented
- [ ] Judge model configured
- [ ] Test case dataset maintained (≥ 20 cases)
- [ ] Statistical significance checks
- [ ] A/B test results documented before promote

---

### Step 8.4: Versioning Strategy

**Mục tiêu**: Semantic versioning cho agent.

```python
# src/harness_agent/__init__.py
__version__ = "1.2.0"
```

**CHANGELOG.md**:

```markdown
# Changelog

## [1.2.0] - 2026-06-18
### Added
- SummarizationMiddleware để xử lý context dài
- Researcher subagent có thêm fetch_url tool

### Changed
- System prompt updated với citation requirements
- Model upgraded from deepseek-v4-flash to deepseek-v4-flash

### Fixed
- BUG-003: Subagent timeout khi research topic quá rộng
- BUG-004: Memory không persist sau session restart

## [1.1.0] - 2026-06-01
### Added
- HITL approval cho write_file và execute_command

### Fixed
- BUG-001: Path traversal trong file tools
- BUG-002: Empty input gây crash

## [1.0.0] - 2026-05-15
### Added
- Initial release: Research agent với subagent delegation
- Tool registry với MCP protocol support
- Hybrid memory: vector + key-value + conversation buffer
```

**Semantic Versioning**:
- **MAJOR** (X.0.0): Breaking changes (API, tool interface, behavior)
- **MINOR** (0.X.0): New features, new tools, new middleware
- **PATCH** (0.0.X): Bug fixes, performance improvements

**Checklist**:
- [ ] Version number in `__init__.py`
- [ ] `CHANGELOG.md` maintained
- [ ] Semantic versioning followed
- [ ] Git tags for releases (`v1.2.0`)
- [ ] Breaking changes documented with migration guide

---

### Step 8.5: Continuous Evaluation Pipeline

**Mục tiêu**: Chạy evaluation định kỳ để detect regression.

```python
# scripts/run_evaluation.py
import asyncio
import json
from harness_agent.evaluation import AgentEvaluator

async def main():
    evaluator = AgentEvaluator(agent, test_cases)
    results = await evaluator.evaluate()

    # Save results
    with open(f"eval_results_{date}.json", "w") as f:
        json.dump(results.__dict__, f, indent=2)

    # Alert if regression
    baseline = load_baseline()
    if results.task_completion_rate < baseline.task_completion_rate * 0.9:
        send_alert("Evaluation regression detected!")

if __name__ == "__main__":
    asyncio.run(main())
```

**Checklist**:
- [ ] Evaluation script created
- [ ] Baseline metrics stored
- [ ] Regression detection (10% drop threshold)
- [ ] Automated evaluation run (weekly)
- [ ] Results archived for trend analysis

---

### Step 8.6: Dependency Management

**Mục tiêu**: Keep dependencies up to date và secure.

```bash
# Check outdated packages
pip list --outdated

# Security audit
pip-audit

# Update dependencies
uv pip install --upgrade deepagents langchain langgraph
```

**Checklist**:
- [ ] Monthly dependency review schedule
- [ ] Security advisories monitored
- [ ] `pip-audit` run monthly
- [ ] Breaking changes in dependencies reviewed trước khi upgrade
- [ ] Dependency upgrades tested trước khi deploy

---

### Step 8.7: Prompt Optimization

**Mục tiêu**: Liên tục optimize prompts để giảm token usage và cải thiện quality.

**Cách thực hiện**:
1. Review token usage trends từ monitoring (Phase 7)
2. Identify high-token prompts
3. A/B test optimized version
4. Deploy nếu cải thiện

**Tools hỗ trợ**:
- **Skill `agent-harness-construction`**: Context budgeting, prompt optimization
- **Skill `simplify`**: Simplify verbose prompts

**Checklist**:
- [ ] Token usage trends reviewed monthly
- [ ] High-cost prompts identified
- [ ] Optimizations A/B tested
- [ ] Context budget respected (<2000 tokens invariant parts)

---

### Step 8.8: Monthly Review Schedule

**Mục tiêu**: Monthly review toàn diện.

**Monthly Review Checklist** (từ [AIDLC Lifecycle §8.6](../aidlc-lifecycle.md#86-maintenance-checklist-hàng-tháng)):

#### Performance
- [ ] Review token usage trends
- [ ] Optimize prompts nếu cần
- [ ] Check summarization triggers — adjust thresholds
- [ ] Review latency metrics (P50, P95, P99)

#### Quality
- [ ] Run regression test suite
- [ ] Run evaluation framework
- [ ] Review task completion rate
- [ ] Check error rate trends

#### Security
- [ ] Review security advisories cho dependencies
- [ ] Run `pip-audit`
- [ ] Rotate secrets if near expiration
- [ ] Review HITL approval patterns

#### Memory
- [ ] Audit memory files — remove outdated content
- [ ] Check memory size (not too large)
- [ ] Verify memory persists correctly

#### Model
- [ ] Test với model mới nhất
- [ ] Compare performance (A/B test)
- [ ] Upgrade nếu cải thiện

#### Documentation
- [ ] Cập nhật `CLAUDE.md` với learnings mới
- [ ] Cập nhật `CHANGELOG.md`
- [ ] Cập nhật ADRs nếu decisions thay đổi
- [ ] Update project context trong `/memories/`

#### Infrastructure
- [ ] Review resource usage (CPU, memory, disk)
- [ ] Scale up/down nếu cần
- [ ] Check backup strategy
- [ ] Test disaster recovery

---

### Step 8.9: Knowledge Base Maintenance

**Mục tiêu**: Cập nhật project knowledge base.

**Files cần cập nhật**:

| File | When | Content |
|------|------|---------|
| `CLAUDE.md` | Monthly | Project conventions, new patterns |
| `AGENTS.md` | Per feature | Agent behavior, context |
| `CHANGELOG.md` | Per release | Version history |
| `docs/adr/` | Per decision | Architecture decisions |
| `/memories/learnings.md` | Continuous | Agent-discovered patterns |

**Checklist**:
- [ ] `CLAUDE.md` updated monthly
- [ ] `AGENTS.md` updated per feature
- [ ] ADRs updated when decisions change
- [ ] Memory files pruned (remove outdated)

---

## Phase 8 Completion Checklist

### Feedback Loop
- [ ] Memory feedback loop active
- [ ] Agent updates memory on correction
- [ ] Feedback captured with WHY

### Regression
- [ ] Regression test suite maintained
- [ ] Every bug has regression test
- [ ] Monthly regression run

### A/B Testing
- [ ] A/B testing framework ready
- [ ] Test case dataset maintained
- [ ] Results documented

### Versioning
- [ ] Semantic versioning followed
- [ ] CHANGELOG.md maintained
- [ ] Git tags for releases

### Continuous Evaluation
- [ ] Weekly automated evaluation
- [ ] Regression detection
- [ ] Baseline comparison

### Dependencies & Security
- [ ] Monthly dependency review
- [ ] Security advisories monitored
- [ ] Secret rotation schedule

### Monthly Review
- [ ] All 8 monthly review sections checked
- [ ] Action items tracked
- [ ] Improvements prioritized

### Knowledge Base
- [ ] Documentation updated
- [ ] Memory files maintained
- [ ] Project context current

---

## AIDLC Cycle Complete

🎉 Tất cả 9 giai đoạn AIDLC đã hoàn thành! Quay lại [Phase 0](00-foundation.md) để bắt đầu iteration tiếp theo.

## References

| Tài liệu | Section |
|----------|---------|
| [AIDLC Lifecycle](../aidlc-lifecycle.md) | §8 Maintenance & Iteration |
| [Memory](../../deep-agents/06-memory.md) | Memory feedback loop |
| [Skills: agent-harness-construction](../../../.claude/skills/agent-harness-construction/SKILL.md) | Context budgeting |
| [Skills: simplify](../../../.claude/skills/) | Code/prompt simplification |
| [Rules: Python Coding Style](../../../.claude/rules/python/coding-style.md) | Code quality maintenance |
