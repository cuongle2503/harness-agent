# Development Workflow

## Feature Implementation Workflow

### 0. Research & Reuse (mandatory)
- Search for existing implementations before writing new code
- Check PyPI for battle-tested libraries
- Prefer adapting proven approaches over net-new code

### 1. Plan First
- Use **planner** agent to create implementation plan
- Identify dependencies and risks
- Break down into independently deliverable phases

### 2. TDD Approach
- Use **tdd-workflow** skill
- Write tests first (RED)
- Implement to pass tests (GREEN)
- Refactor (IMPROVE)
- Verify 80%+ coverage

### 3. Code Review
- Use **code-reviewer** or **python-reviewer** agent immediately after writing code
- Address CRITICAL and HIGH issues
- Fix MEDIUM issues when possible

### 4. Commit & Push
- Conventional commits format: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`
- Comprehensive PR descriptions
- Include test plan

### 5. Pre-Review Checks
- All tests passing
- ruff linting clean
- mypy type checking clean
- Coverage at 80%+
