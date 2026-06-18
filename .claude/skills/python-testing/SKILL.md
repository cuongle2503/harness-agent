---
name: python-testing
description: Python testing strategies using pytest, TDD methodology, fixtures, mocking, parametrization, and coverage requirements.
origin: harness-agent
---

# Python Testing Patterns

Comprehensive testing strategies for the Harness Agent project.

## When to Activate

- Writing new Python code (follow TDD: red, green, refactor)
- Designing test suites
- Reviewing test coverage
- Setting up testing infrastructure

## TDD Mandate

Always follow the TDD cycle:

1. **RED**: Write a failing test for the desired behavior
2. **GREEN**: Write minimal code to make the test pass
3. **REFACTOR**: Improve code while keeping tests green

## Coverage Requirements

- **Target**: 80%+ overall
- **Critical paths**: 100% coverage required

```bash
pytest --cov=harness_agent --cov-report=term-missing --cov-report=html
```

## Fixtures

```python
# tests/conftest.py
import pytest
from harness_agent.core.agent import HarnessAgent
from harness_agent.core.tool_registry import ToolRegistry

@pytest.fixture
def tool_registry():
    registry = ToolRegistry()
    registry.register(SearchTool())
    registry.register(ReadTool())
    return registry

@pytest.fixture
def test_agent(tool_registry):
    return HarnessAgent(
        model="test-model",
        tools=tool_registry.list_tools(),
    )
```

## Parametrization

```python
@pytest.mark.parametrize("input,expected", [
    ({"task": "search"}, "search_result"),
    ({"task": "read"}, "read_result"),
    ({}, None),
])
def test_agent_routing(test_agent, input, expected):
    result = test_agent.invoke(input)
    assert result.get("type") == expected
```

## Mocking

```python
from unittest.mock import patch, AsyncMock

@patch("harness_agent.core.agent.LLMBackend")
def test_agent_with_mock_llm(mock_llm):
    mock_llm.return_value.generate.return_value = {"text": "mocked"}
    agent = HarnessAgent(model="mock")
    result = agent.invoke({"task": "test"})
    assert result["text"] == "mocked"
```

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── unit/
│   ├── test_agent.py        # Agent core tests
│   ├── test_tool_registry.py
│   └── test_memory.py
├── integration/
│   ├── test_agent_pipeline.py
│   └── test_mcp_tools.py
└── e2e/
    └── test_workflows.py
```

## Best Practices

- **DO**: Follow TDD, test one thing, use fixtures, mock external deps, test edge cases
- **DON'T**: Test implementation details, use complex conditionals, share state between tests, use print statements
