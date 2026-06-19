# User Preferences

> Auto-updated by agent based on observed patterns and explicit feedback.
> Last updated: 2026-06-19

## Language & Communication
- **Language**: Vietnamese (primary), English (technical)
- **Code comments**: English
- **Commit messages**: English, conventional commits format

## Coding Style
- **Type hints**: Mandatory on all public functions
- **Line length**: 88 characters (Black default)
- **Testing**: TDD workflow (RED → GREEN → REFACTOR)
- **Coverage**: 80%+ target, 100% on critical paths

## Tool Preferences
- **Package manager**: uv
- **Linter**: ruff
- **Type checker**: mypy + pyright
- **Test runner**: pytest with asyncio

## Project Conventions
- **Branch naming**: `feat/<desc>`, `fix/<desc>`
- **PR workflow**: Branch → TDD → Review → Squash merge
- **Code review**: Required before merge
- **Security scan**: Required before commit
