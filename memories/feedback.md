# Feedback History

> Correction history captured by the agent. Each entry records what went wrong,
> why it went wrong, and how to avoid it next time.

## Initial Setup — 2026-06-19

### What was set up
- Phase 8 Maintenance plan implementation
- Memory feedback loop, regression tests, A/B testing, versioning, evaluation pipeline
- All eight steps of the maintenance plan

### Why this approach
- The AIDLC lifecycle requires continuous improvement after initial deployment
- Each bug fix needs a regression test to prevent recurrence
- Semantic versioning ensures upgrade predictability
- Monthly reviews keep the project healthy

### How to apply going forward
- After each bug fix, add a regression test to `tests/regression/test_regression.py`
- After each release, update `CHANGELOG.md` following semantic versioning
- Run `scripts/run_evaluation.py` before each release
- Review memory files monthly and prune outdated content
- Use `AgentABTester` before promoting prompt/model changes

---

## Pattern: Bug Fix Workflow
1. Detect bug (user report / monitoring alert)
2. Write regression test (RED)
3. Fix bug (GREEN)  
4. Add to REGRESSION_CASES
5. Commit: `fix: [BUG-XXX] description`

## Pattern: Monthly Review
- Performance: token usage, latency, thresholds
- Quality: regression suite, evaluation framework
- Security: pip-audit, secret rotation, advisories
- Memory: audit files, check size, verify persistence
- Model: test latest, A/B compare, upgrade if better
- Documentation: CLAUDE.md, CHANGELOG.md, ADRs
