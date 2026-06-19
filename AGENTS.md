# AGENTS.md

Agent behavior and context for Claude Code when working in this repository.

## Project Identity

This is the **Harness Agent** — a deep agent framework for multi-agent orchestration built with Python and LangChain. It's the infrastructure layer that powers AI agent systems, not the end-user application itself.

## Agent Capabilities

### Available Agent Types
| Agent | Purpose |
|-------|---------|
| `harness-architect` | Design agent harnesses, tool schemas, memory architectures, orchestration |
| `planner` | Create implementation plans for features and refactoring |
| `code-reviewer` | General code review for quality, security, maintainability |
| `python-reviewer` | Python-specific code review (PEP 8, type hints, LangChain patterns) |
| `security-reviewer` | Security vulnerability detection |
| `Explore` | Read-only codebase search and exploration |

### Available Skills
| Skill | Purpose |
|-------|---------|
| `tdd-workflow` | RED → GREEN → REFACTOR cycle |
| `python-testing` | pytest strategies, fixtures, coverage |
| `python-patterns` | Pythonic idioms and best practices |
| `langchain-patterns` | LangChain/LangGraph agent patterns |
| `agent-harness-construction` | Design and optimize agent action spaces |
| `code-review` | Code quality review |
| `security-scan` | Security vulnerability scan |
| `plan` | Implementation planning |
| `verify` | Verify changes work correctly |

## Development Context

### Current Phase: 8 (Maintenance & Iteration)
All 9 AIDLC phases are complete. The project is in maintenance mode with:
- Memory-driven improvement loops
- Regression test suite (9 BUG cases)
- Evaluation framework (20+ test cases)
- A/B testing framework
- Monthly review schedule

### When Making Changes
1. Consult `docs/guides/plans/` for the relevant phase plan
2. Follow TDD: write tests first, implement, refactor
3. Run `python-reviewer` after code changes
4. Run `security-reviewer` before commits
5. Update `CHANGELOG.md` for notable changes
6. Add regression tests for bug fixes

### Key Conventions
- **Language**: Python 3.11+, type hints mandatory
- **Commits**: Conventional commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `chore:`)
- **Testing**: 80%+ coverage, pytest with asyncio
- **Linting**: ruff, mypy, pyright clean
- **Package Manager**: uv

### Documentation Map
| Doc | When to read |
|-----|-------------|
| `docs/deep-agents/` | Framework reference (9 docs) |
| `docs/guides/aidlc-lifecycle.md` | Understanding the 9-phase lifecycle |
| `docs/guides/plans/` | Phase-specific implementation plans |
| `CLAUDE.md` | Project conventions and commands |
| `CHANGELOG.md` | Version history |
| `memories/` | Agent memory, preferences, feedback |

### Memory System
The agent uses a hybrid memory system:
- `/memories/preferences.md` — User preferences (language, style, tools)
- `/memories/feedback.md` — Correction history with WHY
- `/memories/learnings.md` — Patterns discovered over time
- `/memories/context.md` — Project-specific context

Memory is persisted via CompositeBackend routing:
- `/memories/*` → StoreBackend (persistent, user-scoped)
- `/output/*` → FilesystemBackend (real disk output)
- `/*` (default) → StateBackend (ephemeral session)
