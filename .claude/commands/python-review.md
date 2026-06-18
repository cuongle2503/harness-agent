---
name: python-review
description: Review Python code for quality, security, and Pythonic patterns
---

# /python-review

## Overview

Run a comprehensive Python code review focusing on PEP 8, type hints, security, and Pythonic patterns.

## When to Use

- After writing or modifying Python code
- Before committing Python changes
- When reviewing PRs

## How It Works

1. Spawns the **python-reviewer** subagent
2. Runs `git diff -- '*.py'` to find changes
3. Runs static analysis: `ruff check`, `mypy`
4. Produces a categorized review with severity levels

## Review Categories

- **CRITICAL**: Security vulnerabilities, data loss risks
- **HIGH**: Type safety, error handling, anti-patterns
- **MEDIUM**: Best practices, code quality
- **LOW**: Style, naming, documentation
