---
name: test
description: Write and run tests following TDD methodology
---

# /test

## Overview

Write and run tests following Test-Driven Development methodology.

## When to Use

- Before implementing new features
- When fixing bugs (write regression test first)
- When refactoring (ensure tests still pass)
- Checking coverage status

## How It Works

1. Analyzes the target code
2. Writes failing tests first (RED)
3. Runs tests to confirm they fail
4. Guides implementation to pass tests (GREEN)
5. Suggests refactoring opportunities (IMPROVE)

## Commands

```bash
# Check current coverage
pytest --cov=harness_agent --cov-report=term-missing

# Run specific test file
pytest tests/unit/test_core.py -v
```
