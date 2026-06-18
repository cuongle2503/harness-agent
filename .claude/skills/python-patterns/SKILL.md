---
name: python-patterns
description: Pythonic idioms, PEP 8 standards, type hints, and best practices for building robust, efficient, and maintainable Python applications.
origin: harness-agent
---

# Python Development Patterns

Idiomatic Python patterns and best practices for the Harness Agent project.

## When to Activate

- Writing new Python code
- Reviewing Python code
- Refactoring existing Python code
- Designing Python packages/modules

## Core Principles

### 1. Readability Counts
Code should be obvious and easy to understand. Use descriptive names.

```python
# Good
def get_active_agents(agents: list[Agent]) -> list[Agent]:
    return [a for a in agents if a.is_active]

# Bad
def get_active(a):
    return [x for x in a if x.act]
```

### 2. EAFP - Easier to Ask Forgiveness Than Permission
```python
# Good: EAFP
def get_tool(name: str) -> BaseTool:
    try:
        return registry[name]
    except KeyError:
        raise ToolNotFoundError(f"Tool not found: {name}")

# Bad: LBYL
def get_tool(name: str) -> BaseTool:
    if name in registry:
        return registry[name]
    raise ToolNotFoundError(f"Tool not found: {name}")
```

### 3. Type Hints (MANDATORY)
Every public function must have complete type annotations.

```python
from typing import Optional, Any

def invoke_agent(
    agent: HarnessAgent,
    input: dict[str, Any],
    config: RunnableConfig | None = None,
) -> AgentResult:
    """Invoke an agent and return its result."""
    ...
```

### 4. Data Classes for Data
```python
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class AgentConfig:
    model: str
    temperature: float = 0.0
    max_tokens: int = 4096
    tools: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
```

## Anti-Patterns to Avoid
- ❌ Bare `except:` → catch specific exceptions
- ❌ Mutable default arguments
- ❌ `type() ==` → `isinstance()`
- ❌ `value == None` → `value is None`
- ❌ `from module import *`
- ❌ String concatenation in loops → `"".join()`

## LangChain-Specific Patterns

### Runnable Protocol
```python
from langchain_core.runnables import Runnable, RunnableConfig

class MyAgent(Runnable):
    def invoke(self, input: dict, config: RunnableConfig | None = None) -> dict:
        ...
```

### Tool Definition
```python
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

class SearchInput(BaseModel):
    query: str = Field(..., description="Search query")
    max_results: int = Field(default=5, ge=1, le=20)

class SearchTool(BaseTool):
    name: str = "search"
    description: str = "Search the knowledge base"
    args_schema: type[BaseModel] = SearchInput

    def _run(self, query: str, max_results: int = 5) -> str:
        ...
```

## Python Tooling

```bash
# Formatting
black src/ tests/
isort src/ tests/

# Linting
ruff check .

# Type checking
mypy src/

# Testing
pytest --cov=harness_agent --cov-report=term-missing
```
