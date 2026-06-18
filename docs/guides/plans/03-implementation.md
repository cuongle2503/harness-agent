# Phase 3: Implementation Plan

> **Mục tiêu**: Implement agent theo TDD workflow: RED → GREEN → REFACTOR. Viết code sạch, có type hints, pass linting.

## Prerequisites

- [ ] Phase 2: Architecture hoàn thành
- [ ] Tất cả ADRs đã được viết và review
- [ ] Middleware pipeline đã được thiết kế
- [ ] Backend strategy đã được xác định
- [ ] Subagent definitions đã sẵn sàng
- [ ] Đã đọc [AIDLC Lifecycle §3](../aidlc-lifecycle.md#3-implementation)

---

## Step-by-Step Workflow

### Step 3.1: Project Structure Setup

**Mục tiêu**: Tạo cấu trúc thư mục chuẩn cho dự án.

**Cấu trúc target**:

```
src/
├── harness_agent/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── agent.py           # HarnessAgent (Runnable)
│   │   └── orchestrator.py    # AgentOrchestrator (LangGraph)
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── registry.py        # ToolRegistry
│   │   ├── file_tools.py      # File operations
│   │   ├── search_tools.py    # Web search
│   │   └── code_tools.py      # Code execution
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── hybrid_memory.py   # HybridMemory
│   │   └── backends.py        # Custom backends
│   ├── middleware/
│   │   ├── __init__.py
│   │   └── custom_middleware.py
│   └── agents/
│       ├── __init__.py
│       ├── research_agent.py
│       └── code_agent.py

tests/
├── conftest.py                # Shared fixtures
├── unit/
│   ├── test_agent.py
│   ├── test_tools.py
│   ├── test_memory.py
│   └── test_middleware.py
├── integration/
│   ├── test_agent_pipeline.py
│   └── test_subagent_orchestration.py
└── adversarial/
    └── test_agent_robustness.py
```

**Tools hỗ trợ**:
- **Rule**: `.claude/rules/python/coding-style.md` — File organization, type hints
- **Rule**: `.claude/rules/python/patterns.md` — Agent pattern, tool registry, memory pattern

**Checklist**:
- [ ] Project structure created
- [ ] `__init__.py` files với `__all__` exports
- [ ] Package names follow Python conventions
- [ ] File sizes < 800 lines target

---

### Step 3.2: RED Phase — Write Tests First

**Mục tiêu**: Viết test cho từng component TRƯỚC KHI code.

**Cách thực hiện**: Tuân theo TDD workflow

**Tools hỗ trợ**:
- **Skill `tdd-workflow`**: Hướng dẫn RED → GREEN → REFACTOR
- **Skill `test`**: Viết và chạy tests
- **Rule**: `.claude/rules/python/testing.md` — TDD mandate, test structure, fixtures

#### 3.2.1: Unit Tests cho Tools

```python
# tests/unit/test_tools.py
import pytest
from pydantic import ValidationError
from harness_agent.tools.registry import ToolRegistry
from harness_agent.tools.search_tools import search

class TestSearchTool:
    def test_valid_input_returns_results(self):
        result = search.invoke({"query": "AI advances", "max_results": 5})
        assert "AI advances" in result

    def test_empty_query_rejected(self):
        with pytest.raises(ValidationError):
            search.invoke({"query": ""})

    def test_max_results_clamped(self):
        with pytest.raises(ValidationError):
            search.invoke({"query": "test", "max_results": 100})

class TestToolRegistry:
    def test_register_and_get_tool(self):
        registry = ToolRegistry()
        registry.register(search)
        assert registry.get("search") is not None

    def test_list_tools_returns_schemas(self):
        registry = ToolRegistry()
        registry.register(search)
        schemas = registry.list_tools()
        assert any(s["name"] == "search" for s in schemas)

    def test_get_nonexistent_tool_raises(self):
        registry = ToolRegistry()
        with pytest.raises(KeyError):
            registry.get("nonexistent")
```

#### 3.2.2: Unit Tests cho Agent Core

```python
# tests/unit/test_agent.py
import pytest
from unittest.mock import MagicMock
from harness_agent.core.agent import HarnessAgent

class TestHarnessAgent:
    def test_agent_invoke_returns_messages(self, test_agent):
        result = test_agent.invoke({
            "messages": [{"role": "user", "content": "Hello"}]
        })
        assert "messages" in result
        assert len(result["messages"]) > 0

    def test_agent_uses_tools_when_needed(self, test_agent_with_tools):
        result = test_agent_with_tools.invoke({
            "messages": [{"role": "user", "content": "Search for Python patterns"}]
        })
        tool_calls = [
            msg for msg in result["messages"]
            if hasattr(msg, "tool_calls") and msg.tool_calls
        ]
        assert len(tool_calls) > 0
```

#### 3.2.3: Unit Tests cho Memory

```python
# tests/unit/test_memory.py
class TestHybridMemory:
    def test_store_and_retrieve(self, hybrid_memory):
        hybrid_memory.store("key1", "value1")
        assert hybrid_memory.get("key1") == "value1"

    def test_vector_search(self, hybrid_memory):
        hybrid_memory.store("doc1", "Python is great", embedding=[0.1, 0.2])
        hybrid_memory.store("doc2", "JavaScript is popular", embedding=[0.3, 0.4])
        results = hybrid_memory.retrieve("Python programming", k=1)
        assert len(results) == 1
        assert "Python" in results[0].value
```

**Checklist**:
- [ ] Unit tests written cho tất cả tools
- [ ] Unit tests written cho agent core
- [ ] Unit tests written cho memory
- [ ] Unit tests written cho middleware (nếu custom)
- [ ] Tests cover edge cases (empty input, invalid input, etc.)
- [ ] Tests sử dụng fixtures từ `conftest.py`
- [ ] Tests run và FAIL (RED phase confirmed)

---

### Step 3.3: GREEN Phase — Minimal Implementation

**Mục tiêu**: Viết code tối thiểu để pass tests.

**Cách thực hiện**: Implement từng component theo thứ tự dependency.

#### 3.3.1: Tool Registry

```python
# src/harness_agent/tools/registry.py
from typing import Any
from langchain_core.tools import BaseTool
from pydantic import BaseModel

class ToolSchema(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]

class ToolRegistry:
    """Central registry for MCP-compatible tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found in registry")
        return self._tools[name]

    def list_tools(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name=t.name,
                description=t.description,
                parameters=t.args_schema.schema() if t.args_schema else {},
            )
            for t in self._tools.values()
        ]

    def invoke_tool(self, name: str, **kwargs: Any) -> Any:
        tool = self.get(name)
        return tool.invoke(kwargs)
```

#### 3.3.2: HarnessAgent (Runnable Protocol)

```python
# src/harness_agent/core/agent.py
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph
from typing import Any

class HarnessAgent(Runnable):
    """Base agent following LangChain Runnable protocol."""

    def __init__(
        self,
        llm: BaseChatModel,
        tools: list[BaseTool],
        system_prompt: str = "",
    ) -> None:
        self.llm = llm.bind_tools(tools)
        self.tools = tools
        self.system_prompt = system_prompt

    def invoke(
        self, input: dict[str, Any], config: RunnableConfig | None = None
    ) -> dict[str, Any]:
        messages = input.get("messages", [])
        if self.system_prompt:
            messages = [{"role": "system", "content": self.system_prompt}] + messages
        response = self.llm.invoke(messages, config)
        return {"messages": messages + [response]}

    async def ainvoke(
        self, input: dict[str, Any], config: RunnableConfig | None = None
    ) -> dict[str, Any]:
        messages = input.get("messages", [])
        if self.system_prompt:
            messages = [{"role": "system", "content": self.system_prompt}] + messages
        response = await self.llm.ainvoke(messages, config)
        return {"messages": messages + [response]}
```

#### 3.3.3: HybridMemory

```python
# src/harness_agent/memory/hybrid_memory.py
from typing import Any

class MemoryItem:
    def __init__(self, key: str, value: Any, embedding: list[float] | None = None):
        self.key = key
        self.value = value
        self.embedding = embedding

class HybridMemory:
    """Hybrid memory: key-value + vector store + conversation buffer."""

    def __init__(self) -> None:
        self._kv: dict[str, Any] = {}
        self._vector_items: list[MemoryItem] = []

    def store(self, key: str, value: Any, embedding: list[float] | None = None) -> None:
        item = MemoryItem(key, value, embedding)
        self._kv[key] = item
        if embedding:
            self._vector_items.append(item)

    def get(self, key: str) -> Any | None:
        item = self._kv.get(key)
        return item.value if item else None

    def retrieve(self, query: str, k: int = 5) -> list[MemoryItem]:
        # Simplified: return most recent k items
        return self._vector_items[-k:]

    def get_context(self, session_id: str) -> dict[str, Any]:
        return {"session_id": session_id, "items": list(self._kv.keys())}
```

**Checklist**:
- [ ] ToolRegistry implemented và pass tests
- [ ] HarnessAgent implemented và pass tests
- [ ] HybridMemory implemented và pass tests
- [ ] Custom tools implemented với Pydantic input schema
- [ ] Tất cả tests GREEN

---

### Step 3.4: Agent Factory Implementation

**Mục tiêu**: Implement agent factory sử dụng `create_deep_agent()`.

**Cách thực hiện**: Build trên architecture từ Phase 2.

```python
# src/harness_agent/agents/research_agent.py
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from deepagents.middleware import FilesystemMiddleware, SubAgentMiddleware
from deepagents.middleware.summarization import SummarizationMiddleware
from langchain.agents.middleware import TodoListMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

def create_research_agent(
    model: BaseChatModel,
    search_tool: BaseTool,
    fetch_tool: BaseTool,
    *,
    store: Any = None,
    summarization_model: str = "deepseek-v4-flash",
) -> CompiledStateGraph:
    """Tạo research agent với đầy đủ capabilities."""
    backend = CompositeBackend(
        default=StateBackend(),
        routes={"/memories/": StoreBackend(store=store)} if store else {},
    )

    researcher_subagent = {
        "name": "researcher",
        "description": "Research topics using web search and return structured summaries with citations.",
        "system_prompt": (
            "You are a thorough researcher. For each research task:\n"
            "1. Search for relevant information\n"
            "2. Cross-reference multiple sources\n"
            "3. Synthesize findings into a structured summary\n"
            "4. Include citations for all claims\n"
            "5. Note any conflicting information between sources"
        ),
        "tools": [search_tool, fetch_tool],
        "model": model,
        "middleware": [],
    }

    return create_deep_agent(
        model=model,
        tools=[search_tool],
        system_prompt=(
            "You are a research coordinator. When users ask research questions:\n"
            "1. Use write_todos to plan the research steps\n"
            "2. Delegate to the researcher subagent for deep investigation\n"
            "3. Synthesize findings into a clear, structured response"
        ),
        middleware=[
            TodoListMiddleware(),
            FilesystemMiddleware(backend=backend),
            SubAgentMiddleware(backend=backend, subagents=[researcher_subagent]),
            SummarizationMiddleware(model=summarization_model, backend=backend),
        ],
        backend=backend,
        store=store,
    )
```

**Tools hỗ trợ**:
- **Skill `langchain-patterns`**: Runnable protocol, StateGraph patterns
- **MCP `context7`**: `resolve-library-id` → `query-docs` cho deepagents API
- **Agent `python-reviewer`**: Review code ngay sau khi viết

**Checklist**:
- [ ] Agent factory function implemented
- [ ] `create_deep_agent()` called with correct parameters
- [ ] Middleware pipeline khớp với Phase 2 design
- [ ] Backend strategy khớp với Phase 2 design
- [ ] Subagents configured đúng definitions
- [ ] System prompt rõ ràng, có cấu trúc
- [ ] Type hints đầy đủ

---

### Step 3.5: Error Handling

**Mục tiêu**: Implement custom exception hierarchy và error handling.

**Cách thực hiện**: Theo [AIDLC Lifecycle §3 Pattern 3](../aidlc-lifecycle.md#pattern-3-error-handling)

```python
# src/harness_agent/core/exceptions.py
class HarnessError(Exception):
    """Base exception for all harness errors."""

class ToolNotFoundError(HarnessError):
    """Raised when a tool is not found in the registry."""

class AgentExecutionError(HarnessError):
    """Raised when an agent execution fails."""
    def __init__(self, agent_id: str, original_error: Exception) -> None:
        self.agent_id = agent_id
        self.original_error = original_error
        super().__init__(f"Agent {agent_id} failed: {original_error}")

class SubagentTimeoutError(HarnessError):
    """Raised when a subagent times out."""

class ToolExecutionError(HarnessError):
    """Raised when a tool execution fails."""
    def __init__(self, tool_name: str, original_error: Exception) -> None:
        self.tool_name = tool_name
        self.original_error = original_error
        super().__init__(f"Tool '{tool_name}' failed: {original_error}")
```

**Checklist**:
- [ ] Exception hierarchy defined
- [ ] Base exception `HarnessError`
- [ ] Specific exceptions: `ToolNotFoundError`, `AgentExecutionError`, `SubagentTimeoutError`, `ToolExecutionError`
- [ ] Error handling trong agent logic (try/except với fallback)
- [ ] Error messages không leak sensitive data

---

### Step 3.6: REFACTOR Phase

**Mục tiêu**: Cải thiện code quality sau khi tests pass.

**Cách thực hiện**:

**Tools hỗ trợ**:
- **Skill `simplify`**: Review và simplify code
- **Agent `python-reviewer`**: Python-specific code review
- **Agent `code-reviewer`**: General code review
- **Hook `PostToolUse`**: Tự động chạy ruff sau mỗi file edit

**Refactor checklist**:
- [ ] Extract magic strings thành constants
- [ ] Tách system prompt ra file riêng (`prompts/`)
- [ ] Thêm type hints đầy đủ cho tất cả public functions
- [ ] Thêm docstrings cho tất cả public functions
- [ ] Functions < 50 lines
- [ ] Files < 800 lines
- [ ] No deep nesting (>4 levels)
- [ ] Proper context managers (`with` statements)
- [ ] `ruff check src/` clean
- [ ] `mypy src/` clean
- [ ] `python-reviewer` agent review completed
- [ ] `code-reviewer` agent review completed
- [ ] `simplify` skill applied

---

### Step 3.7: Commit

**Mục tiêu**: Commit code với conventional commit format.

```bash
git add src/ tests/
git commit -m "feat: implement agent core with TDD workflow

- ToolRegistry with MCP protocol support
- HarnessAgent implementing Runnable protocol
- HybridMemory: vector + key-value + conversation buffer
- Research agent factory with subagent delegation
- Custom exception hierarchy
- 80%+ test coverage

Co-Authored-By: Claude <noreply@anthropic.com>"
```

**Tools hỗ trợ**:
- **Rule**: `.claude/rules/common/git-workflow.md` — Commit format
- **Hook `Stop`**: Tự động chạy pytest + ruff trước khi kết thúc

**Checklist**:
- [ ] All tests passing
- [ ] `ruff check src/ tests/` clean
- [ ] `mypy src/` clean
- [ ] Coverage ≥ 80%
- [ ] Committed with conventional format

---

## Phase 3 Completion Checklist

### Code Quality
- [ ] Type hints on all public functions
- [ ] Docstrings on all public functions
- [ ] Functions < 50 lines
- [ ] Files < 800 lines
- [ ] No deep nesting
- [ ] Proper error handling
- [ ] Context managers for resources

### Tests
- [ ] Unit tests written first (RED)
- [ ] Minimal implementation (GREEN)
- [ ] Code refactored (IMPROVE)
- [ ] All tests passing
- [ ] Coverage ≥ 80%

### Linting & Type Check
- [ ] `ruff check src/ tests/` clean
- [ ] `mypy src/` clean

### Review
- [ ] `python-reviewer` agent review done
- [ ] `code-reviewer` agent review done
- [ ] `simplify` skill applied
- [ ] CRITICAL issues fixed
- [ ] HIGH issues fixed

### Commit
- [ ] Conventional commit format
- [ ] Comprehensive commit message

---

## Next Phase

→ [Phase 4: Testing & QA](04-testing.md)

## References

| Tài liệu | Section |
|----------|---------|
| [AIDLC Lifecycle](../aidlc-lifecycle.md) | §3 Implementation |
| [API Reference](../../deep-agents/02-api-reference.md) | `create_deep_agent()` |
| [Middleware](../../deep-agents/03-middleware.md) | Middleware configuration |
| [Backends](../../deep-agents/04-backends.md) | Backend configuration |
| [Subagents](../../deep-agents/05-subagents.md) | Subagent implementation |
| [Memory](../../deep-agents/06-memory.md) | Memory implementation |
| [Rules: Python Coding Style](../../../.claude/rules/python/coding-style.md) | PEP 8, type hints |
| [Rules: Python Patterns](../../../.claude/rules/python/patterns.md) | Architecture patterns |
| [Rules: Python Testing](../../../.claude/rules/python/testing.md) | TDD, fixtures |
| [Skills: tdd-workflow](../../../.claude/skills/tdd-workflow/SKILL.md) | TDD cycle |
| [Skills: langchain-patterns](../../../.claude/skills/langchain-patterns/SKILL.md) | Runnable, StateGraph |
