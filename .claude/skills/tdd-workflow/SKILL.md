---
name: tdd-workflow
description: Test-Driven Development workflow — write tests first, implement to pass, refactor to improve. 80%+ coverage required.
origin: harness-agent
---

# TDD Workflow

Test-Driven Development workflow for the Harness Agent project.

## When to Activate

- Implementing new features
- Fixing bugs (write regression test first)
- Refactoring existing code
- Any code change that affects behavior

## The TDD Cycle

### 1. RED — Write a Failing Test

```python
# tests/unit/test_agent.py
def test_agent_invoke_returns_result():
    agent = HarnessAgent(model="test", tools=[])
    result = agent.invoke({"task": "hello"})
    assert result is not None
    assert "output" in result
```

### 2. GREEN — Write Minimal Implementation

```python
# src/harness_agent/core/agent.py
class HarnessAgent:
    def invoke(self, input: dict) -> dict:
        return {"output": "Hello from agent", "status": "success"}
```

### 3. REFACTOR — Improve While Keeping Green

- Extract helper methods
- Add type hints
- Improve error handling
- Optimize where needed

## Test Types

### Unit Tests
Test individual functions, classes, and methods in isolation.

```python
def test_tool_registry_register():
    registry = ToolRegistry()
    registry.register(SearchTool())
    assert "search" in registry.list_tool_names()
```

### Integration Tests
Test interactions between components (agent + tools + memory).

```python
def test_agent_with_tools():
    agent = HarnessAgent(model="test", tools=[SearchTool()])
    result = agent.invoke({"task": "search for python patterns"})
    assert result["status"] == "success"
```

### E2E Tests
Test complete workflows from user input to final output.

```python
def test_full_research_workflow():
    orchestrator = AgentOrchestrator(agents={...})
    result = orchestrator.run(Task("Research LangChain patterns"))
    assert result.completed
    assert len(result.artifacts) > 0
```

## Coverage Commands

```bash
# Run tests with coverage
pytest --cov=harness_agent --cov-report=term-missing

# Fail if coverage below threshold
pytest --cov=harness_agent --cov-fail-under=80

# Generate HTML report
pytest --cov=harness_agent --cov-report=html
```

## Best Practices
- Write the test FIRST, watch it FAIL
- Keep tests independent (no shared state)
- Use descriptive test names: `test_<what>_<when>_<expected>`
- One assertion per test when possible
- Use fixtures for shared setup
- Mock external dependencies
