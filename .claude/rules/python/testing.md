# Python Testing Rules

## TDD Mandate

Always follow TDD: **RED → GREEN → REFACTOR**

1. Write a failing test for desired behavior
2. Write minimal code to pass
3. Refactor while keeping tests green

## Coverage Requirements

- **Target**: 80%+ overall
- **Critical paths**: 100% (agent core, tool execution, memory operations)

## Test Structure

```
tests/
├── conftest.py          # Shared fixtures
├── unit/                # Unit tests
│   ├── test_core.py
│   ├── test_tools.py
│   └── test_memory.py
├── integration/         # Integration tests
│   ├── test_agent_pipeline.py
│   └── test_mcp_tools.py
└── e2e/                 # End-to-end tests
    └── test_workflows.py
```

## Fixtures

Use `conftest.py` for shared fixtures. Each test should be independent.

```python
@pytest.fixture
def agent_config():
    return AgentConfig(model="claude-sonnet-4-6", temperature=0.0)

@pytest.fixture
def mock_tool_registry():
    registry = ToolRegistry()
    registry.register(MockTool())
    return registry
```

## Parametrization

Use `@pytest.mark.parametrize` for edge cases:

```python
@pytest.mark.parametrize("input,expected", [
    ("hello", "HELLO"),
    ("", ""),
    (None, None),
])
def test_transform(input, expected):
    assert transform(input) == expected
```

## Mocking

- Mock external APIs with `unittest.mock.patch`
- Use `autospec=True` for safety
- Don't mock what you don't own — wrap in adapters
