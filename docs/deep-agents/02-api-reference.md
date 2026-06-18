# 2. API Reference: `create_deep_agent`

## Function Signature

```python
from deepagents import create_deep_agent

create_deep_agent(
    model: str | BaseChatModel | None = None,
    tools: Sequence[BaseTool | Callable | dict[str, Any]] | None = None,
    *,
    system_prompt: str | SystemMessage | None = None,
    middleware: Sequence[AgentMiddleware] = (),
    subagents: Sequence[SubAgent | CompiledSubAgent | AsyncSubAgent] | None = None,
    skills: list[str] | None = None,
    memory: list[str] | None = None,
    permissions: list[FilesystemPermission] | None = None,
    backend: BackendProtocol | BackendFactory | None = None,
    interrupt_on: dict[str, bool | InterruptOnConfig] | None = None,
    response_format: ResponseFormat[ResponseT] | type[ResponseT] | dict[str, Any] | None = None,
    state_schema: type[DeepAgentState] | None = None,
    context_schema: type[ContextT] | None = None,
    checkpointer: Checkpointer | None = None,
    store: BaseStore | None = None,
    debug: bool = False,
    name: str | None = None,
    cache: BaseCache | None = None,
) -> CompiledStateGraph[AgentState[ResponseT], ContextT, _InputAgentState, _OutputAgentState[ResponseT]]
```

**Yêu cầu**: Deep agent yêu cầu LLM hỗ trợ **tool calling**.

## Tham số chi tiết

### `model` — `str | BaseChatModel | None`

Chat model để sử dụng. Hỗ trợ cả string shorthand và BaseChatModel instance.

```python
# String shorthand
agent = create_deep_agent(model="deepseek-v4-flash")

# Hoặc từ ChatDeepSeek trực tiếp
from langchain_deepseek import ChatDeepSeek
model = ChatDeepSeek(model="deepseek-v4-flash")
agent = create_deep_agent(model=model)

# Hoặc từ ChatDeepSeek trực tiếp
from langchain_deepseek import ChatDeepSeek
model = ChatDeepSeek(model="deepseek-v4-flash")
agent = create_deep_agent(model=model)
```

### `tools` — `Sequence[BaseTool | Callable | dict[str, Any]] | None`

Danh sách các tools có sẵn cho agent.

```python
from langchain.tools import tool

@tool
def search(query: str) -> str:
    """Search the web for a query."""
    return f"Results for: {query}"

@tool
def calculate(expression: str) -> float:
    """Evaluate a math expression."""
    return eval(expression)

agent = create_deep_agent(
    model="deepseek-v4-flash",
    tools=[search, calculate],
)
```

### `system_prompt` — `str | SystemMessage | None`

System prompt để cấu hình hành vi agent.

```python
agent = create_deep_agent(
    model="deepseek-v4-flash",
    system_prompt="""You are a helpful coding assistant.
- Write clean, well-documented code
- Always include type hints
- Follow PEP 8 conventions""",
)
```

### `middleware` — `Sequence[AgentMiddleware]`

Danh sách middleware để áp dụng. **Đây là tham số quan trọng nhất** quyết định capabilities của agent.

```python
from langchain.agents.middleware import TodoListMiddleware
from deepagents.middleware import FilesystemMiddleware, SubAgentMiddleware
from deepagents.middleware.summarization import SummarizationMiddleware

agent = create_deep_agent(
    model="deepseek-v4-flash",
    middleware=[
        TodoListMiddleware(),
        FilesystemMiddleware(backend=backend),
        SummarizationMiddleware(model="deepseek-v4-flash", backend=backend),
        SubAgentMiddleware(backend=backend, subagents=[...]),
    ],
)
```

Xem chi tiết: [Middleware](03-middleware.md)

### `subagents` — `Sequence[SubAgent | CompiledSubAgent | AsyncSubAgent] | None`

Danh sách sub-agent có sẵn để main agent ủy quyền qua `task` tool.

```python
subagents = [
    {
        "name": "researcher",
        "description": "Research agent for web searches and data gathering",
        "system_prompt": "You are a researcher...",
        "tools": [search],
        "model": "deepseek-v4-flash",
    },
    {
        "name": "coder",
        "description": "Code execution and analysis agent",
        "system_prompt": "You are a coder...",
        "tools": [execute_code],
        "model": "deepseek-v4-flash",
    },
]

agent = create_deep_agent(
    model="deepseek-v4-flash",
    subagents=subagents,
)
```

### `memory` — `list[str] | None`

Danh sách đường dẫn file memory để load. Các file này sẽ được đọc và inject vào system prompt.

```python
agent = create_deep_agent(
    model="deepseek-v4-flash",
    memory=[
        "/memories/preferences.md",
        "/memories/user_info.md",
        "/policies/compliance.md",
    ],
)
```

### `backend` — `BackendProtocol | BackendFactory | None`

Backend để quản lý file storage.

```python
from deepagents.backends import (
    StateBackend,
    StoreBackend,
    FilesystemBackend,
    CompositeBackend,
)

# Ephemeral (default)
backend = StateBackend()

# Persistent filesystem
backend = FilesystemBackend(root_dir="/data")

# Hybrid: ephemeral + persistent /memories/
backend = CompositeBackend(
    default=StateBackend(),
    routes={"/memories/": StoreBackend()},
)
```

Xem chi tiết: [Backends](04-backends.md)

### `permissions` — `list[FilesystemPermission] | None`

Quyền truy cập file system cho agent.

```python
permissions = [
    {"path": "/workspace/**", "permissions": ["read", "write"]},
    {"path": "/data/**", "permissions": ["read"]},
]
```

### `interrupt_on` — `dict[str, bool | InterruptOnConfig] | None`

Cấu hình điểm dừng để human-in-the-loop.

```python
interrupt_on = {
    "tool_calls": True,  # Dừng trước mỗi tool call
    "file_writes": True,  # Dừng trước mỗi lần ghi file
}
```

### `checkpointer` — `Checkpointer | None`

Checkpointer để lưu/khôi phục state của agent.

```python
from langgraph.checkpoint.memory import InMemorySaver

checkpointer = InMemorySaver()
agent = create_deep_agent(
    model="deepseek-v4-flash",
    checkpointer=checkpointer,
)

# Sử dụng thread_id để track conversation
config = {"configurable": {"thread_id": "user-session-1"}}
agent.invoke({"messages": [{"role": "user", "content": "Hello"}]}, config)
# Agent nhớ context từ lần invoke trước
```

### `store` — `BaseStore | None`

LangGraph Store cho long-term memory (persistent cross-thread).

```python
from langgraph.store.memory import InMemoryStore

store = InMemoryStore()
agent = create_deep_agent(
    model="deepseek-v4-flash",
    store=store,
)
```

### `response_format` — `ResponseFormat | type | dict | None`

Định dạng response mong muốn (structured output).

```python
from pydantic import BaseModel

class AnalysisResult(BaseModel):
    summary: str
    score: float
    recommendations: list[str]

agent = create_deep_agent(
    model="deepseek-v4-flash",
    response_format=AnalysisResult,
)
```

### `debug` — `bool`

Bật debug mode để log chi tiết.

```python
agent = create_deep_agent(model="deepseek-v4-flash", debug=True)
```

### `name` — `str | None`

Tên của agent (dùng trong multi-agent systems).

### `cache` — `BaseCache | None`

Cache cho LLM calls.

## Return Value

`CompiledStateGraph[AgentState, ContextT, InputState, OutputState]`

Đây là một LangGraph `CompiledStateGraph`, có thể dùng tất cả các phương thức của LangGraph:

| Method | Mô tả |
|--------|-------|
| `invoke(input, config)` | Chạy đồng bộ |
| `ainvoke(input, config)` | Chạy bất đồng bộ |
| `stream(input, config, stream_mode)` | Stream từng bước |
| `astream(input, config, stream_mode)` | Async stream |
| `get_state(config)` | Lấy state hiện tại |
| `update_state(config, values)` | Cập nhật state |

## Ví dụ hoàn chỉnh

```python
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from deepagents.middleware import FilesystemMiddleware, SubAgentMiddleware
from langchain.agents.middleware import TodoListMiddleware
from langchain_deepseek import ChatDeepSeek
from langchain.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

# 1. Định nghĩa tools
@tool
def search(query: str) -> str:
    """Search the web."""
    return f"Search results for: {query}"

@tool
def calculate(expr: str) -> float:
    """Calculate math expression."""
    return float(eval(expr))

# 2. Khởi tạo model
model = ChatDeepSeek(model="deepseek-v4-flash")

# 3. Cấu hình hybrid backend
backend = CompositeBackend(
    default=StateBackend(),
    routes={"/memories/": StoreBackend()},
)

# 4. Tạo subagent definitions
researcher_subagent = {
    "name": "researcher",
    "description": "Research topics using web search and return structured summaries.",
    "system_prompt": "You are a researcher. Use the search tool to find information.",
    "tools": [search],
    "model": "deepseek-v4-flash",
}

# 5. Tạo agent
agent = create_deep_agent(
    model=model,
    tools=[search, calculate],
    system_prompt="You are a helpful assistant with research and calculation abilities.",
    middleware=[
        TodoListMiddleware(),
        FilesystemMiddleware(backend=backend),
        SubAgentMiddleware(backend=backend, subagents=[researcher_subagent]),
    ],
    backend=backend,
    checkpointer=InMemorySaver(),
    memory=["/memories/preferences.md"],
)

# 6. Sử dụng
config = {"configurable": {"thread_id": "session-1"}}

result = agent.invoke(
    {
        "messages": [{
            "role": "user",
            "content": "Research quantum computing advances and calculate 2^10"
        }]
    },
    config=config,
)

print(result["messages"][-1].content)
```
