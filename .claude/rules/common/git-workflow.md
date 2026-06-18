# Git Workflow

## Commit Format

```
<type>: <description>

[optional body]

[optional footer]
```

**Types:** feat, fix, refactor, docs, test, chore, perf, ci

**Examples:**
- `feat: add tool registry with MCP protocol support`
- `fix: prevent race condition in agent orchestrator`
- `refactor: extract memory backend to strategy pattern`
- `test: add integration tests for agent pipeline`
- `docs: update CLAUDE.md with tool usage patterns`

## Branching

- `main` — production-ready code
- Feature branches: `feat/<description>`
- Fix branches: `fix/<description>`

## PR Workflow
1. Create branch from `main`
2. Implement with TDD
3. Run full test suite + lint + type check
4. Create PR with summary + test plan
5. Address review feedback
6. Squash merge to `main`
